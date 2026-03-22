// ==========================================================================
// AETERNA Synth Module — Subtractive/FM/Morphing Synthesizer
// ==========================================================================
// v0.0.20.685 — Phase R8B (Voice + Filter)
//
// AETERNA is an advanced synthesizer with:
//   - R8A: Oscillators (Sine, Saw, Square, Triangle, Noise, PolyBLEP, FM, Unison)
//   - R8B: Voice + Filter (Biquad, AEG/FEG ADSR, Voice Pool, Glide)
//   - R8C: Modulation Matrix (planned)
//   - R8D: Parameter Sync + Presets (planned)
//
// Rules:
//   ✅ All DSP is zero-alloc in process()
//   ✅ Voice pool is pre-allocated (max 32 voices)
//   ✅ Lock-free MIDI input via crossbeam bounded channel
//   ❌ NO allocations in audio thread
// ==========================================================================

pub mod oscillator;
pub mod voice;
pub mod modulation;
pub mod wavetable;
pub mod unison;

// Re-exports
#[allow(unused_imports)]
pub use oscillator::{
    OscillatorState, Waveform,
    gen_sine, gen_saw_polyblep, gen_square_polyblep, gen_triangle,
    gen_morphed, white_noise, pink_noise, polyblep,
    MAX_UNISON,
};

#[allow(unused_imports)]
pub use voice::{
    AeternaVoice, AeternaVoicePool, AeternaVoiceParams,
    AeternaFilterMode, VoiceStealMode,
    MAX_POLYPHONY, midi_to_freq,
};

#[allow(unused_imports)]
pub use modulation::{
    ModMatrix, ModSlot, ModSource, ModDestination, ModOutput,
    VoiceModState, LfoParams,
    MAX_MOD_SLOTS, NUM_LFOS,
};

#[allow(unused_imports)]
pub use wavetable::{WavetableBank, FRAME_SIZE, MAX_FRAMES};

#[allow(unused_imports)]
pub use unison::{UnisonEngine, UnisonMode, MAX_UNISON_VOICES};

// ---------------------------------------------------------------------------
// AeternaInstrument — implements InstrumentNode
// ---------------------------------------------------------------------------

use crossbeam_channel::{bounded, Receiver, Sender, TrySendError, TryRecvError};
use std::any::Any;

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use crate::dsp::lfo::LfoShape;
use super::{InstrumentNode, MidiEvent};

/// Maximum MIDI events buffered per process cycle.
const MIDI_RING_CAPACITY: usize = 256;

/// Maximum parameter change commands per process cycle.
const PARAM_RING_CAPACITY: usize = 64;

// ---------------------------------------------------------------------------
// Parameter Change Commands (lock-free delivery to audio thread)
// ---------------------------------------------------------------------------

/// Commands sent from the GUI/command thread to change AETERNA parameters.
///
/// Delivered via a bounded channel (lock-free SPSC on audio thread side).
#[derive(Debug, Clone)]
pub enum AeternaCommand {
    // --- Oscillator ---
    SetWaveform(Waveform),
    SetShape(f32),
    SetFmAmount(f32),
    SetFmRatio(f32),
    SetSubLevel(f32),
    SetSubOctave(u8),
    SetUnisonVoices(u8),
    SetUnisonDetune(f32),
    SetUnisonSpread(f32),

    // --- Filter ---
    SetFilterMode(AeternaFilterMode),
    SetFilterCutoff(f32),
    SetFilterResonance(f32),
    SetFilterKeyTrack(f32),

    // --- AEG ---
    SetAegAttack(f32),
    SetAegDecay(f32),
    SetAegSustain(f32),
    SetAegRelease(f32),

    // --- FEG ---
    SetFegAttack(f32),
    SetFegDecay(f32),
    SetFegSustain(f32),
    SetFegRelease(f32),
    SetFegAmount(f32),

    // --- Glide ---
    SetGlideTime(f32),

    // --- Master ---
    SetMasterGain(f32),
    SetMasterPan(f32),

    // --- Velocity ---
    SetVelocitySensitivity(f32),

    // --- Voice ---
    SetStealMode(VoiceStealMode),

    // --- Modulation Matrix (R8C) ---
    SetModSlot { index: usize, source: ModSource, destination: ModDestination, amount: f32, bipolar: bool },
    SetLfoRate { lfo: usize, rate_hz: f32 },
    SetLfoShape { lfo: usize, shape: LfoShape },
}

// ---------------------------------------------------------------------------
// AeternaInstrument — the full synthesizer as an InstrumentNode
// ---------------------------------------------------------------------------

/// AETERNA Synthesizer instrument.
///
/// Implements InstrumentNode for integration into the Rust AudioGraph.
///
/// Signal flow:
/// ```text
///   MIDI → Voice Pool → (Osc + Filter + AEG/FEG per voice) → Sum → Master Gain/Pan → Output
/// ```
pub struct AeternaInstrument {
    /// Unique instrument ID.
    id: String,
    /// Sample rate.
    sample_rate: u32,
    /// Buffer size.
    buffer_size: usize,

    /// MIDI event channel (command → audio thread).
    midi_tx: Sender<MidiEvent>,
    midi_rx: Receiver<MidiEvent>,

    /// Parameter command channel (command → audio thread).
    cmd_tx: Sender<AeternaCommand>,
    cmd_rx: Receiver<AeternaCommand>,

    /// Voice pool (pre-allocated).
    voice_pool: AeternaVoicePool,

    /// Shared voice parameters (read on audio thread, written via commands).
    params: AeternaVoiceParams,

    /// Modulation matrix (R8C).
    mod_matrix: ModMatrix,
}

impl AeternaInstrument {
    /// Create a new AETERNA instrument.
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING_CAPACITY);
        let (cmd_tx, cmd_rx) = bounded(PARAM_RING_CAPACITY);

        Self {
            id,
            sample_rate,
            buffer_size,
            midi_tx,
            midi_rx,
            cmd_tx,
            cmd_rx,
            voice_pool: AeternaVoicePool::new(MAX_POLYPHONY, sample_rate as f32),
            params: AeternaVoiceParams::default(),
            mod_matrix: ModMatrix::new(),
        }
    }

    /// Get the parameter command sender (for the command/GUI thread).
    pub fn command_sender(&self) -> Sender<AeternaCommand> {
        self.cmd_tx.clone()
    }

    /// Apply a parameter command on the audio thread.
    fn apply_command(&mut self, cmd: AeternaCommand) {
        match cmd {
            AeternaCommand::SetWaveform(w) => self.params.waveform = w,
            AeternaCommand::SetShape(v) => self.params.shape = v.clamp(0.0, 1.0),
            AeternaCommand::SetFmAmount(v) => self.params.fm_amount = v.clamp(0.0, 1.0),
            AeternaCommand::SetFmRatio(v) => self.params.fm_ratio = v.clamp(0.1, 32.0),
            AeternaCommand::SetSubLevel(v) => self.params.sub_level = v.clamp(0.0, 1.0),
            AeternaCommand::SetSubOctave(v) => self.params.sub_octave = v.clamp(1, 2),
            AeternaCommand::SetUnisonVoices(v) => self.params.unison_voices = v.clamp(1, MAX_UNISON as u8),
            AeternaCommand::SetUnisonDetune(v) => self.params.unison_detune = v.clamp(0.0, 100.0),
            AeternaCommand::SetUnisonSpread(v) => self.params.unison_spread = v.clamp(0.0, 1.0),

            AeternaCommand::SetFilterMode(m) => self.params.filter_mode = m,
            AeternaCommand::SetFilterCutoff(v) => self.params.filter_cutoff = v.clamp(0.0, 1.0),
            AeternaCommand::SetFilterResonance(v) => self.params.filter_resonance = v.clamp(0.0, 1.0),
            AeternaCommand::SetFilterKeyTrack(v) => self.params.filter_key_track = v.clamp(0.0, 1.0),

            AeternaCommand::SetAegAttack(v) => self.params.aeg_attack = v.clamp(0.001, 10.0),
            AeternaCommand::SetAegDecay(v) => self.params.aeg_decay = v.clamp(0.001, 10.0),
            AeternaCommand::SetAegSustain(v) => self.params.aeg_sustain = v.clamp(0.0, 1.0),
            AeternaCommand::SetAegRelease(v) => self.params.aeg_release = v.clamp(0.001, 30.0),

            AeternaCommand::SetFegAttack(v) => self.params.feg_attack = v.clamp(0.001, 10.0),
            AeternaCommand::SetFegDecay(v) => self.params.feg_decay = v.clamp(0.001, 10.0),
            AeternaCommand::SetFegSustain(v) => self.params.feg_sustain = v.clamp(0.0, 1.0),
            AeternaCommand::SetFegRelease(v) => self.params.feg_release = v.clamp(0.001, 30.0),
            AeternaCommand::SetFegAmount(v) => self.params.feg_amount = v.clamp(-1.0, 1.0),

            AeternaCommand::SetGlideTime(v) => self.params.glide_time = v.clamp(0.0, 5.0),

            AeternaCommand::SetMasterGain(v) => self.params.master_gain = v.clamp(0.0, 2.0),
            AeternaCommand::SetMasterPan(v) => self.params.master_pan = v.clamp(-1.0, 1.0),

            AeternaCommand::SetVelocitySensitivity(v) => self.params.velocity_sensitivity = v.clamp(0.0, 1.0),

            AeternaCommand::SetStealMode(m) => self.voice_pool.set_steal_mode(m),

            AeternaCommand::SetModSlot { index, source, destination, amount, bipolar } => {
                self.mod_matrix.set_slot(index, source, destination, amount, bipolar);
            }
            AeternaCommand::SetLfoRate { lfo, rate_hz } => {
                self.mod_matrix.set_lfo_rate(lfo, rate_hz);
            }
            AeternaCommand::SetLfoShape { lfo, shape } => {
                self.mod_matrix.set_lfo_shape(lfo, shape);
            }
        }
    }

    // =======================================================================
    // R8D — State Save/Load + Factory Presets
    // =======================================================================

    /// Save the complete instrument state as a list of key-value pairs.
    ///
    /// This can be serialized to JSON/MessagePack for project save.
    pub fn save_state(&self) -> Vec<(String, f64)> {
        let p = &self.params;
        let mut state = vec![
            ("shape".into(), p.shape as f64),
            ("fm_amount".into(), p.fm_amount as f64),
            ("fm_ratio".into(), p.fm_ratio as f64),
            ("sub_level".into(), p.sub_level as f64),
            ("sub_octave".into(), p.sub_octave as f64),
            ("unison_voices".into(), p.unison_voices as f64),
            ("unison_detune".into(), p.unison_detune as f64),
            ("unison_spread".into(), p.unison_spread as f64),
            ("filter_cutoff".into(), p.filter_cutoff as f64),
            ("filter_resonance".into(), p.filter_resonance as f64),
            ("filter_key_track".into(), p.filter_key_track as f64),
            ("aeg_attack".into(), p.aeg_attack as f64),
            ("aeg_decay".into(), p.aeg_decay as f64),
            ("aeg_sustain".into(), p.aeg_sustain as f64),
            ("aeg_release".into(), p.aeg_release as f64),
            ("feg_attack".into(), p.feg_attack as f64),
            ("feg_decay".into(), p.feg_decay as f64),
            ("feg_sustain".into(), p.feg_sustain as f64),
            ("feg_release".into(), p.feg_release as f64),
            ("feg_amount".into(), p.feg_amount as f64),
            ("glide_time".into(), p.glide_time as f64),
            ("master_gain".into(), p.master_gain as f64),
            ("master_pan".into(), p.master_pan as f64),
            ("velocity_sensitivity".into(), p.velocity_sensitivity as f64),
        ];
        // Save mod slots
        for (i, slot) in self.mod_matrix.slots.iter().enumerate() {
            state.push((format!("mod{}_amount", i), slot.amount as f64));
            state.push((format!("mod{}_bipolar", i), if slot.bipolar { 1.0 } else { 0.0 }));
        }
        // Save LFO rates
        for (i, lp) in self.mod_matrix.lfo_params.iter().enumerate() {
            state.push((format!("lfo{}_rate", i), lp.rate_hz as f64));
        }
        state
    }

    /// Load a parameter by key-value.
    ///
    /// Used for state restore from project file.
    pub fn load_param(&mut self, key: &str, value: f64) {
        let v = value as f32;
        match key {
            "shape" => self.params.shape = v.clamp(0.0, 1.0),
            "fm_amount" => self.params.fm_amount = v.clamp(0.0, 1.0),
            "fm_ratio" => self.params.fm_ratio = v.clamp(0.1, 32.0),
            "sub_level" => self.params.sub_level = v.clamp(0.0, 1.0),
            "sub_octave" => self.params.sub_octave = (v as u8).clamp(1, 2),
            "unison_voices" => self.params.unison_voices = (v as u8).clamp(1, 16),
            "unison_detune" => self.params.unison_detune = v.clamp(0.0, 100.0),
            "unison_spread" => self.params.unison_spread = v.clamp(0.0, 1.0),
            "filter_cutoff" => self.params.filter_cutoff = v.clamp(0.0, 1.0),
            "filter_resonance" => self.params.filter_resonance = v.clamp(0.0, 1.0),
            "filter_key_track" => self.params.filter_key_track = v.clamp(0.0, 1.0),
            "aeg_attack" => self.params.aeg_attack = v.clamp(0.001, 10.0),
            "aeg_decay" => self.params.aeg_decay = v.clamp(0.001, 10.0),
            "aeg_sustain" => self.params.aeg_sustain = v.clamp(0.0, 1.0),
            "aeg_release" => self.params.aeg_release = v.clamp(0.001, 30.0),
            "feg_attack" => self.params.feg_attack = v.clamp(0.001, 10.0),
            "feg_decay" => self.params.feg_decay = v.clamp(0.001, 10.0),
            "feg_sustain" => self.params.feg_sustain = v.clamp(0.0, 1.0),
            "feg_release" => self.params.feg_release = v.clamp(0.001, 30.0),
            "feg_amount" => self.params.feg_amount = v.clamp(-1.0, 1.0),
            "glide_time" => self.params.glide_time = v.clamp(0.0, 5.0),
            "master_gain" => self.params.master_gain = v.clamp(0.0, 2.0),
            "master_pan" => self.params.master_pan = v.clamp(-1.0, 1.0),
            "velocity_sensitivity" => self.params.velocity_sensitivity = v.clamp(0.0, 1.0),
            _ => {} // unknown key → ignore
        }
    }

    /// Apply a factory preset by name.
    ///
    /// Returns `true` if the preset was found and applied.
    pub fn apply_preset(&mut self, name: &str) -> bool {
        let preset: Option<AeternaVoiceParams> = match name {
            "Init" | "init" => Some(AeternaVoiceParams::default()),
            "Warm Pad" | "warm_pad" => {
                let mut p = AeternaVoiceParams::default();
                p.waveform = Waveform::Saw;
                p.shape = 0.0;
                p.filter_cutoff = 0.45;
                p.filter_resonance = 0.15;
                p.aeg_attack = 0.3;
                p.aeg_decay = 0.5;
                p.aeg_sustain = 0.6;
                p.aeg_release = 1.0;
                p.feg_attack = 0.2;
                p.feg_decay = 0.8;
                p.feg_sustain = 0.2;
                p.feg_amount = 0.4;
                p.unison_voices = 4;
                p.unison_detune = 20.0;
                p.unison_spread = 0.8;
                p.master_gain = 0.5;
                Some(p)
            }
            "Pluck Lead" | "pluck_lead" => {
                let mut p = AeternaVoiceParams::default();
                p.waveform = Waveform::Saw;
                p.filter_cutoff = 0.6;
                p.filter_resonance = 0.3;
                p.aeg_attack = 0.001;
                p.aeg_decay = 0.3;
                p.aeg_sustain = 0.0;
                p.aeg_release = 0.2;
                p.feg_attack = 0.001;
                p.feg_decay = 0.15;
                p.feg_sustain = 0.0;
                p.feg_amount = 0.7;
                p.master_gain = 0.65;
                Some(p)
            }
            "Fat Bass" | "fat_bass" => {
                let mut p = AeternaVoiceParams::default();
                p.waveform = Waveform::Square;
                p.filter_mode = AeternaFilterMode::Lp24;
                p.filter_cutoff = 0.35;
                p.filter_resonance = 0.25;
                p.aeg_attack = 0.005;
                p.aeg_decay = 0.2;
                p.aeg_sustain = 0.8;
                p.aeg_release = 0.15;
                p.feg_attack = 0.001;
                p.feg_decay = 0.2;
                p.feg_amount = 0.5;
                p.sub_level = 0.6;
                p.sub_octave = 1;
                p.master_gain = 0.6;
                Some(p)
            }
            "Bright Keys" | "bright_keys" => {
                let mut p = AeternaVoiceParams::default();
                p.waveform = Waveform::Saw;
                p.filter_cutoff = 0.75;
                p.filter_resonance = 0.1;
                p.aeg_attack = 0.001;
                p.aeg_decay = 0.8;
                p.aeg_sustain = 0.3;
                p.aeg_release = 0.5;
                p.feg_attack = 0.001;
                p.feg_decay = 0.4;
                p.feg_sustain = 0.1;
                p.feg_amount = 0.3;
                p.fm_amount = 0.15;
                p.fm_ratio = 2.0;
                p.master_gain = 0.55;
                Some(p)
            }
            _ => None,
        };

        if let Some(p) = preset {
            self.params = p;
            true
        } else {
            false
        }
    }

    /// List available factory preset names.
    pub fn preset_names() -> &'static [&'static str] {
        &["Init", "Warm Pad", "Pluck Lead", "Fat Bass", "Bright Keys"]
    }
}

impl InstrumentNode for AeternaInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        // Non-blocking send; if ring is full, drop oldest by receiving one first
        if let Err(TrySendError::Full(evt)) = self.midi_tx.try_send(event) {
            let _ = self.midi_rx.try_recv(); // drop oldest
            let _ = self.midi_tx.try_send(evt);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext) {
        let sr = ctx.sample_rate as f32;
        let frames = ctx.frames;

        // Drain parameter commands
        loop {
            match self.cmd_rx.try_recv() {
                Ok(cmd) => self.apply_command(cmd),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }

        // Drain MIDI events
        loop {
            match self.midi_rx.try_recv() {
                Ok(evt) => {
                    match evt {
                        MidiEvent::NoteOn { note, velocity } => {
                            self.voice_pool.note_on(note, velocity, &self.params, sr);
                        }
                        MidiEvent::NoteOff { note } => {
                            self.voice_pool.note_off(note);
                        }
                        MidiEvent::CC { cc, value } => {
                            match cc {
                                1 => self.mod_matrix.mod_wheel = value, // CC1 = Mod Wheel
                                120 => self.voice_pool.all_sound_off(),
                                123 => self.voice_pool.all_notes_off(),
                                _ => {}
                            }
                        }
                        MidiEvent::AllNotesOff => self.voice_pool.all_notes_off(),
                        MidiEvent::AllSoundOff => self.voice_pool.all_sound_off(),
                    }
                }
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }

        // Render all active voices into buffer
        buffer.silence();
        self.voice_pool.render(
            &mut buffer.data,
            frames,
            buffer.channels,
            &self.params,
            sr,
            &self.mod_matrix,
        );

        // Apply master gain and pan
        buffer.apply_gain(self.params.master_gain);
        if self.params.master_pan.abs() > 0.001 {
            buffer.apply_pan(self.params.master_pan);
        }
    }

    fn instrument_id(&self) -> &str {
        &self.id
    }

    fn instrument_name(&self) -> &str {
        "AETERNA"
    }

    fn instrument_type(&self) -> &str {
        "aeterna"
    }

    fn set_sample_rate(&mut self, sample_rate: u32) {
        self.sample_rate = sample_rate;
        self.voice_pool.set_sample_rate(sample_rate as f32);
    }

    fn set_buffer_size(&mut self, buffer_size: usize) {
        self.buffer_size = buffer_size;
    }

    fn active_voice_count(&self) -> usize {
        self.voice_pool.active_count()
    }

    fn max_polyphony(&self) -> usize {
        self.voice_pool.max_polyphony()
    }

    fn as_any_mut(&mut self) -> &mut dyn Any {
        self
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_ctx(frames: usize, sr: u32) -> ProcessContext {
        ProcessContext {
            frames,
            sample_rate: sr,
            position_samples: 0,
            position_beats: 0.0,
            is_playing: true,
            bpm: 120.0,
            time_sig_num: 4,
            time_sig_den: 4,
        }
    }

    #[test]
    fn test_aeterna_instrument_creation() {
        let inst = AeternaInstrument::new("aeterna_1".to_string(), 44100, 512);
        assert_eq!(inst.instrument_id(), "aeterna_1");
        assert_eq!(inst.instrument_type(), "aeterna");
        assert_eq!(inst.instrument_name(), "AETERNA");
        assert_eq!(inst.active_voice_count(), 0);
        assert_eq!(inst.max_polyphony(), MAX_POLYPHONY);
    }

    #[test]
    fn test_aeterna_instrument_process() {
        let mut inst = AeternaInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        // Play a note
        inst.push_midi(MidiEvent::NoteOn { note: 69, velocity: 0.9 });

        // Process
        inst.process(&mut buffer, &ctx);

        // Should have audio output
        let max_abs: f32 = buffer.data.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max_abs > 0.01, "Should produce audio: max={}", max_abs);
        assert_eq!(inst.active_voice_count(), 1);
    }

    #[test]
    fn test_aeterna_instrument_note_off() {
        let mut inst = AeternaInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.process(&mut buffer, &ctx);
        assert_eq!(inst.active_voice_count(), 1);

        inst.push_midi(MidiEvent::NoteOff { note: 60 });
        inst.process(&mut buffer, &ctx);
        assert!(inst.active_voice_count() >= 1);
    }

    #[test]
    fn test_aeterna_instrument_all_sound_off() {
        let mut inst = AeternaInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.8 });
        inst.push_midi(MidiEvent::NoteOn { note: 67, velocity: 0.8 });
        inst.process(&mut buffer, &ctx);
        assert_eq!(inst.active_voice_count(), 3);

        inst.push_midi(MidiEvent::AllSoundOff);
        inst.process(&mut buffer, &ctx);
        assert_eq!(inst.active_voice_count(), 0);
    }

    #[test]
    fn test_aeterna_command_channel() {
        let mut inst = AeternaInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        let sender = inst.command_sender();
        sender.try_send(AeternaCommand::SetFilterCutoff(0.3)).unwrap();
        sender.try_send(AeternaCommand::SetFilterResonance(0.5)).unwrap();
        sender.try_send(AeternaCommand::SetWaveform(Waveform::Square)).unwrap();

        inst.process(&mut buffer, &ctx);

        assert!((inst.params.filter_cutoff - 0.3).abs() < 0.001);
        assert!((inst.params.filter_resonance - 0.5).abs() < 0.001);
        assert_eq!(inst.params.waveform, Waveform::Square);
    }

    #[test]
    fn test_aeterna_polyphonic_chord() {
        let mut inst = AeternaInstrument::new("test".to_string(), 44100, 512);
        let ctx = make_ctx(512, 44100);
        let mut buffer = AudioBuffer::new(512, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.7 });
        inst.push_midi(MidiEvent::NoteOn { note: 67, velocity: 0.6 });

        inst.process(&mut buffer, &ctx);

        assert_eq!(inst.active_voice_count(), 3);
        let max_abs: f32 = buffer.data.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max_abs > 0.01, "Chord should produce audio: max={}", max_abs);
    }
}
