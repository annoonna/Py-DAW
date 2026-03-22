// ==========================================================================
// Fusion Synth Module — Semi-modular hybrid synthesizer
// ==========================================================================
// v0.0.20.693 — Phase R10A+B+C
//
// A modular synthesizer with swappable oscillator, filter, and envelope
// types. Signal path: OSC → FILTER → AMP (AEG).
//
// Components:
//   R10A: Oscillators (Sine, Triangle, Pulse, Saw, Phase1, Swarm, Bite)
//   R10B: Filters (SVF, Ladder, Comb) + Envelopes (ADSR, AR, AD, Pluck)
//   R10C: Voice management + InstrumentNode implementation
//
// Rules:
//   ✅ All DSP is zero-alloc in process()
//   ✅ Voice pool pre-allocated
//   ✅ Lock-free MIDI via crossbeam channel
//   ❌ NO allocations in audio thread
// ==========================================================================

pub mod oscillators;
pub mod filters;
pub mod envelopes;

#[allow(unused_imports)]
pub use oscillators::{FusionOscType, FusionOscParams, FusionOscState};
#[allow(unused_imports)]
pub use filters::{FusionFilterType, FusionFilterParams, FusionFilter, SvfMode};
#[allow(unused_imports)]
pub use envelopes::{FusionEnvType, FusionEnvParams, FusionEnvelope};

use crossbeam_channel::{bounded, Receiver, Sender, TrySendError};
use std::any::Any;

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use super::{InstrumentNode, MidiEvent};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_VOICES: usize = 8;
const MIDI_RING_CAPACITY: usize = 256;
const PARAM_RING_CAPACITY: usize = 64;

// ---------------------------------------------------------------------------
// Fusion Voice
// ---------------------------------------------------------------------------

/// A single Fusion synthesis voice: OSC → FILTER → AEG.
struct FusionVoice {
    osc: FusionOscState,
    filter: FusionFilter,
    aeg: FusionEnvelope,
    feg: FusionEnvelope,
    /// MIDI note.
    note: u8,
    /// Velocity (0–1).
    velocity: f32,
    /// Base frequency (Hz).
    freq: f32,
    /// Whether this voice is active.
    active: bool,
    /// Age for voice stealing.
    age: u64,
    /// Sequence number.
    seq: u64,
}

impl FusionVoice {
    fn new(sr: f32) -> Self {
        Self {
            osc: FusionOscState::new(),
            filter: FusionFilter::new(),
            aeg: FusionEnvelope::new(sr),
            feg: FusionEnvelope::new(sr),
            note: 0,
            velocity: 0.0,
            freq: 440.0,
            active: false,
            age: 0,
            seq: 0,
        }
    }

    fn note_on(
        &mut self,
        note: u8,
        velocity: f32,
        params: &FusionParams,
        sr: f32,
        seq: u64,
    ) {
        self.note = note;
        self.velocity = velocity;
        self.freq = 440.0 * 2.0f32.powf((note as f32 - 69.0) / 12.0);
        self.active = true;
        self.age = 0;
        self.seq = seq;

        self.osc.reset();
        self.filter.reset();
        self.aeg.set_sample_rate(sr);
        self.feg.set_sample_rate(sr);
        self.aeg.gate_on(velocity, &params.aeg);
        self.feg.gate_on(velocity, &params.feg);
    }

    fn note_off(&mut self, params: &FusionParams) {
        self.aeg.gate_off(&params.aeg);
        self.feg.gate_off(&params.feg);
    }

    fn kill(&mut self) {
        self.aeg.kill();
        self.feg.kill();
        self.active = false;
    }

    #[inline]
    fn is_active(&self) -> bool {
        self.active && self.aeg.is_active()
    }

    /// Render one sample.
    #[inline]
    fn render_sample(&mut self, params: &FusionParams, sr: f32) -> f32 {
        if !self.is_active() {
            self.active = false;
            return 0.0;
        }

        // Oscillator
        let osc_freq = params.osc.calc_freq(self.freq);
        let raw = self.osc.render_sample(osc_freq, sr, &params.osc, 0.0);

        // Filter EG → cutoff modulation
        let feg_val = self.feg.process(&params.feg);

        // Filter
        let filtered = self.filter.process_sample(
            raw, &params.filter, feg_val, self.freq, sr,
        );

        // Amplitude EG
        let aeg_val = self.aeg.process(&params.aeg);
        self.age += 1;

        if !self.aeg.is_active() {
            self.active = false;
        }

        filtered * aeg_val
    }
}

// ---------------------------------------------------------------------------
// Shared Parameters
// ---------------------------------------------------------------------------

/// All Fusion parameters.
#[derive(Clone)]
pub struct FusionParams {
    pub osc: FusionOscParams,
    pub filter: FusionFilterParams,
    pub aeg: FusionEnvParams,
    pub feg: FusionEnvParams,
    /// Sub oscillator level (0–1).
    pub sub_level: f32,
    /// Noise level (0–1).
    pub noise_level: f32,
    /// Master gain (0–2).
    pub gain: f32,
    /// Master pan (-1..+1).
    pub pan: f32,
    /// Glide time in seconds.
    pub glide: f32,
}

impl Default for FusionParams {
    fn default() -> Self {
        Self {
            osc: FusionOscParams::default(),
            filter: FusionFilterParams::default(),
            aeg: FusionEnvParams::default(),
            feg: FusionEnvParams {
                env_type: FusionEnvType::Adsr,
                attack: 0.01,
                decay: 0.3,
                sustain: 0.3,
                release: 0.4,
                velocity_sens: 0.5,
                pluck_decay: 0.5,
            },
            sub_level: 0.0,
            noise_level: 0.0,
            gain: 1.0,
            pan: 0.0,
            glide: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Parameter Commands
// ---------------------------------------------------------------------------

/// Commands for real-time parameter updates.
#[derive(Debug, Clone)]
pub enum FusionCommand {
    SetOscType(FusionOscType),
    SetOscParam { key: String, value: f32 },
    SetFilterType(FusionFilterType),
    SetFilterParam { key: String, value: f32 },
    SetAegParam { key: String, value: f32 },
    SetFegParam { key: String, value: f32 },
    SetGain(f32),
    SetPan(f32),
    SetSubLevel(f32),
    SetNoiseLevel(f32),
}

// ---------------------------------------------------------------------------
// FusionInstrument
// ---------------------------------------------------------------------------

/// Fusion semi-modular synthesizer.
pub struct FusionInstrument {
    id: String,
    sample_rate: u32,
    buffer_size: usize,
    midi_tx: Sender<MidiEvent>,
    midi_rx: Receiver<MidiEvent>,
    cmd_tx: Sender<FusionCommand>,
    cmd_rx: Receiver<FusionCommand>,
    voices: Vec<FusionVoice>,
    params: FusionParams,
    seq_counter: u64,
    /// Simple noise RNG state.
    noise_rng: u32,
}

impl FusionInstrument {
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING_CAPACITY);
        let (cmd_tx, cmd_rx) = bounded(PARAM_RING_CAPACITY);
        let sr = sample_rate as f32;
        let mut voices = Vec::with_capacity(MAX_VOICES);
        for _ in 0..MAX_VOICES {
            voices.push(FusionVoice::new(sr));
        }
        Self {
            id, sample_rate, buffer_size,
            midi_tx, midi_rx, cmd_tx, cmd_rx,
            voices, params: FusionParams::default(),
            seq_counter: 0, noise_rng: 0xABCD1234,
        }
    }

    pub fn command_sender(&self) -> Sender<FusionCommand> {
        self.cmd_tx.clone()
    }

    fn apply_command(&mut self, cmd: FusionCommand) {
        match cmd {
            FusionCommand::SetOscType(t) => self.params.osc.osc_type = t,
            FusionCommand::SetOscParam { key, value } => {
                match key.as_str() {
                    "pitch_st" => self.params.osc.pitch_st = value.clamp(-7.0, 7.0),
                    "octave_shift" => self.params.osc.octave_shift = (value as i8).clamp(-2, 3),
                    "pulse_width" => self.params.osc.pulse_width = value.clamp(0.01, 0.99),
                    "skew" => self.params.osc.skew = value.clamp(-1.0, 1.0),
                    "fold" => self.params.osc.fold = value.clamp(0.0, 1.0),
                    "swarm_detune" => self.params.osc.swarm_detune = value.clamp(0.0, 1.0),
                    "swarm_voices" => self.params.osc.swarm_voices = (value as u8).clamp(2, 8),
                    "bite_bits" => self.params.osc.bite_bits = (value as u8).clamp(1, 16),
                    "bite_downsample" => self.params.osc.bite_downsample = (value as u8).clamp(1, 64),
                    "phase1_amount" => self.params.osc.phase1_amount = value.clamp(0.0, 1.0),
                    _ => {}
                }
            }
            FusionCommand::SetFilterType(t) => self.params.filter.filter_type = t,
            FusionCommand::SetFilterParam { key, value } => {
                match key.as_str() {
                    "cutoff" => self.params.filter.cutoff = value.clamp(20.0, 20000.0),
                    "resonance" => self.params.filter.resonance = value.clamp(0.0, 1.0),
                    "key_track" => self.params.filter.key_track = value.clamp(0.0, 1.0),
                    "env_amount" => self.params.filter.env_amount = value.clamp(-1.0, 1.0),
                    "drive" => self.params.filter.drive = value.clamp(0.0, 1.0),
                    "mode" => self.params.filter.svf_mode = match value as u8 {
                        1 => SvfMode::HighPass,
                        2 => SvfMode::BandPass,
                        _ => SvfMode::LowPass,
                    },
                    _ => {}
                }
            }
            FusionCommand::SetAegParam { key, value } => {
                match key.as_str() {
                    "attack" => self.params.aeg.attack = value.clamp(0.001, 10.0),
                    "decay" => self.params.aeg.decay = value.clamp(0.001, 10.0),
                    "sustain" => self.params.aeg.sustain = value.clamp(0.0, 1.0),
                    "release" => self.params.aeg.release = value.clamp(0.001, 30.0),
                    "velocity_sens" => self.params.aeg.velocity_sens = value.clamp(0.0, 1.0),
                    _ => {}
                }
            }
            FusionCommand::SetFegParam { key, value } => {
                match key.as_str() {
                    "attack" => self.params.feg.attack = value.clamp(0.001, 10.0),
                    "decay" => self.params.feg.decay = value.clamp(0.001, 10.0),
                    "sustain" => self.params.feg.sustain = value.clamp(0.0, 1.0),
                    "release" => self.params.feg.release = value.clamp(0.001, 30.0),
                    "env_amount" => self.params.filter.env_amount = value.clamp(-1.0, 1.0),
                    _ => {}
                }
            }
            FusionCommand::SetGain(v) => self.params.gain = v.clamp(0.0, 2.0),
            FusionCommand::SetPan(v) => self.params.pan = v.clamp(-1.0, 1.0),
            FusionCommand::SetSubLevel(v) => self.params.sub_level = v.clamp(0.0, 1.0),
            FusionCommand::SetNoiseLevel(v) => self.params.noise_level = v.clamp(0.0, 1.0),
        }
    }

    /// Find a free voice or steal oldest.
    fn alloc_voice(&self) -> usize {
        // Free voice first
        for (i, v) in self.voices.iter().enumerate() {
            if !v.is_active() {
                return i;
            }
        }
        // Steal oldest
        let mut oldest = 0;
        let mut oldest_seq = u64::MAX;
        for (i, v) in self.voices.iter().enumerate() {
            if v.seq < oldest_seq {
                oldest_seq = v.seq;
                oldest = i;
            }
        }
        oldest
    }

    /// Generate white noise sample (LCG).
    #[inline]
    fn noise_sample(&mut self) -> f32 {
        self.noise_rng = self.noise_rng.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFFFFFF;
        (self.noise_rng as f32 / 0x40000000 as f32) - 1.0
    }
}

impl InstrumentNode for FusionInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        if let Err(TrySendError::Full(evt)) = self.midi_tx.try_send(event) {
            let _ = self.midi_rx.try_recv();
            let _ = self.midi_tx.try_send(evt);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext) {
        let sr = ctx.sample_rate as f32;
        let frames = ctx.frames;

        // Drain commands
        loop {
            match self.cmd_rx.try_recv() {
                Ok(cmd) => self.apply_command(cmd),
                Err(_) => break,
            }
        }

        // Drain MIDI
        loop {
            match self.midi_rx.try_recv() {
                Ok(evt) => match evt {
                    MidiEvent::NoteOn { note, velocity } => {
                        self.seq_counter += 1;
                        let idx = self.alloc_voice();
                        self.voices[idx].note_on(note, velocity, &self.params, sr, self.seq_counter);
                    }
                    MidiEvent::NoteOff { note } => {
                        for v in &mut self.voices {
                            if v.active && v.note == note {
                                v.note_off(&self.params);
                            }
                        }
                    }
                    MidiEvent::AllNotesOff => {
                        for v in &mut self.voices {
                            if v.active { v.note_off(&self.params); }
                        }
                    }
                    MidiEvent::AllSoundOff => {
                        for v in &mut self.voices { v.kill(); }
                    }
                    _ => {}
                },
                Err(_) => break,
            }
        }

        // Render
        buffer.silence();
        let noise_level = self.params.noise_level;

        for frame in 0..frames {
            let mut mix = 0.0f32;

            for voice in &mut self.voices {
                if voice.is_active() {
                    mix += voice.render_sample(&self.params, sr);
                }
            }

            // Add noise
            if noise_level > 0.001 {
                mix += self.noise_sample() * noise_level * 0.3;
            }

            // Master gain
            mix *= self.params.gain;

            // Write stereo (with pan)
            let idx = frame * buffer.channels;
            if idx + 1 < buffer.data.len() {
                if self.params.pan.abs() > 0.001 {
                    let x = (self.params.pan + 1.0) * 0.5;
                    let pan_l = (x * std::f32::consts::FRAC_PI_2).cos();
                    let pan_r = (x * std::f32::consts::FRAC_PI_2).sin();
                    buffer.data[idx] = mix * pan_l;
                    buffer.data[idx + 1] = mix * pan_r;
                } else {
                    buffer.data[idx] = mix;
                    buffer.data[idx + 1] = mix;
                }
            }
        }
    }

    fn instrument_id(&self) -> &str { &self.id }
    fn instrument_name(&self) -> &str { "Fusion" }
    fn instrument_type(&self) -> &str { "fusion" }

    fn set_sample_rate(&mut self, sample_rate: u32) {
        self.sample_rate = sample_rate;
        let sr = sample_rate as f32;
        for v in &mut self.voices {
            v.aeg.set_sample_rate(sr);
            v.feg.set_sample_rate(sr);
        }
    }

    fn set_buffer_size(&mut self, buffer_size: usize) {
        self.buffer_size = buffer_size;
    }

    fn active_voice_count(&self) -> usize {
        self.voices.iter().filter(|v| v.is_active()).count()
    }

    fn max_polyphony(&self) -> usize { MAX_VOICES }

    fn as_any_mut(&mut self) -> &mut dyn Any { self }
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
    fn test_fusion_creation() {
        let inst = FusionInstrument::new("fusion_1".to_string(), 44100, 512);
        assert_eq!(inst.instrument_type(), "fusion");
        assert_eq!(inst.instrument_name(), "Fusion");
        assert_eq!(inst.active_voice_count(), 0);
        assert_eq!(inst.max_polyphony(), MAX_VOICES);
    }

    #[test]
    fn test_fusion_note_on() {
        let mut inst = FusionInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.process(&mut buffer, &ctx);

        assert_eq!(inst.active_voice_count(), 1);
        let max_abs: f32 = buffer.data.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max_abs > 0.01, "Should produce audio: max={}", max_abs);
    }

    #[test]
    fn test_fusion_polyphony() {
        let mut inst = FusionInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.7 });
        inst.push_midi(MidiEvent::NoteOn { note: 67, velocity: 0.6 });
        inst.process(&mut buffer, &ctx);

        assert_eq!(inst.active_voice_count(), 3);
    }

    #[test]
    fn test_fusion_note_off() {
        let mut inst = FusionInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.process(&mut buffer, &ctx);
        assert_eq!(inst.active_voice_count(), 1);

        inst.push_midi(MidiEvent::NoteOff { note: 60 });
        inst.process(&mut buffer, &ctx);
        // Still in release
        assert!(inst.active_voice_count() >= 1);
    }

    #[test]
    fn test_fusion_all_sound_off() {
        let mut inst = FusionInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        for note in 60..68 {
            inst.push_midi(MidiEvent::NoteOn { note, velocity: 0.8 });
        }
        inst.process(&mut buffer, &ctx);

        inst.push_midi(MidiEvent::AllSoundOff);
        inst.process(&mut buffer, &ctx);
        assert_eq!(inst.active_voice_count(), 0);
    }

    #[test]
    fn test_fusion_command_channel() {
        let mut inst = FusionInstrument::new("test".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buffer = AudioBuffer::new(256, 2);

        let sender = inst.command_sender();
        sender.try_send(FusionCommand::SetOscType(FusionOscType::Saw)).unwrap();
        sender.try_send(FusionCommand::SetGain(0.5)).unwrap();

        inst.process(&mut buffer, &ctx);

        assert_eq!(inst.params.osc.osc_type, FusionOscType::Saw);
        assert!((inst.params.gain - 0.5).abs() < 0.001);
    }
}
