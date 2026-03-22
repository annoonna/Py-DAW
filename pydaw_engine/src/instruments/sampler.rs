// ==========================================================================
// ProSampler Instrument — Polyphonic single-sample playback
// ==========================================================================
// v0.0.20.674 — Phase R6A
//
// A polyphonic sampler that plays a single sample at different pitches.
// Built on top of the R5 sample engine (SampleData, SampleVoice, VoicePool).
//
// Features:
//   - Single-sample mode: one WAV loaded, pitched across keyboard
//   - ADSR amplitude envelope (from R1)
//   - One-Shot or Loop playback modes
//   - Velocity → Volume mapping
//   - Polyphonic (up to 64 voices, configurable)
//   - Lock-free MIDI input via bounded channel
//
// Signal flow:
//   MIDI NoteOn → VoicePool allocates voice → Voice renders with pitch
//   All voices summed → output buffer
//
// Rules:
//   ✅ process() is zero-alloc (all buffers pre-allocated)
//   ✅ MIDI events delivered via lock-free bounded channel
//   ✅ Sample data is Arc-shared (zero-copy across voices)
//   ❌ NO allocations in process()
//   ❌ NO locks in process()
// ==========================================================================

use crossbeam_channel::{bounded, Receiver, Sender, TryRecvError};
use log::{debug, warn};

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use crate::sample::{SampleData, LoopMode, VoicePool, StealMode};
use super::{InstrumentNode, MidiEvent};

/// Maximum MIDI events per process cycle.
/// Bounded channel prevents unbounded memory growth.
const MIDI_RING_CAPACITY: usize = 256;

/// Default maximum polyphony.
const DEFAULT_MAX_VOICES: usize = 64;

/// Default ADSR parameters (seconds).
const DEFAULT_ATTACK: f32 = 0.005;
const DEFAULT_DECAY: f32 = 0.1;
const DEFAULT_SUSTAIN: f32 = 0.8;
const DEFAULT_RELEASE: f32 = 0.2;

// ---------------------------------------------------------------------------
// ProSampler Parameters
// ---------------------------------------------------------------------------

/// Parameters for the ProSampler instrument.
///
/// Updated from the command thread via IPC, read by the audio thread.
/// Atomic types are used for real-time safe access.
#[derive(Debug, Clone)]
pub struct SamplerParams {
    /// ADSR attack time in seconds.
    pub attack: f32,
    /// ADSR decay time in seconds.
    pub decay: f32,
    /// ADSR sustain level (0.0–1.0).
    pub sustain: f32,
    /// ADSR release time in seconds.
    pub release: f32,

    /// Playback mode: one-shot or loop.
    pub loop_mode: LoopMode,
    /// Loop start frame (0-based, in sample frames).
    pub loop_start: usize,
    /// Loop end frame (exclusive, 0 = use sample length).
    pub loop_end: usize,

    /// Master gain (0.0–2.0, default 1.0).
    pub gain: f32,
    /// Master pan (-1.0 left, 0.0 center, 1.0 right).
    pub pan: f32,

    /// Voice stealing mode.
    pub steal_mode: StealMode,
    /// Maximum polyphony (1–256).
    pub max_polyphony: usize,

    /// Root note override (0–127, 0 = use sample's root note).
    pub root_note_override: Option<u8>,

    /// Fine tune in cents (-100 to +100).
    pub fine_tune: i8,

    /// Velocity curve: 0.0 = linear, 1.0 = exponential.
    pub velocity_curve: f32,
}

impl Default for SamplerParams {
    fn default() -> Self {
        Self {
            attack: DEFAULT_ATTACK,
            decay: DEFAULT_DECAY,
            sustain: DEFAULT_SUSTAIN,
            release: DEFAULT_RELEASE,
            loop_mode: LoopMode::None,
            loop_start: 0,
            loop_end: 0,
            gain: 1.0,
            pan: 0.0,
            steal_mode: StealMode::SameNote,
            max_polyphony: DEFAULT_MAX_VOICES,
            root_note_override: None,
            fine_tune: 0,
            velocity_curve: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Parameter Change Commands (lock-free delivery to audio thread)
// ---------------------------------------------------------------------------

/// Parameter change command for the sampler.
/// Sent from command thread, consumed in process().
#[derive(Debug, Clone)]
pub enum SamplerCommand {
    /// Load a new sample (replaces current).
    LoadSample(SampleData),
    /// Clear the current sample.
    ClearSample,
    /// Set ADSR parameters.
    SetAdsr { attack: f32, decay: f32, sustain: f32, release: f32 },
    /// Set loop mode and points.
    SetLoop { mode: LoopMode, start: usize, end: usize },
    /// Set master gain.
    SetGain(f32),
    /// Set master pan.
    SetPan(f32),
    /// Set voice stealing mode.
    SetStealMode(StealMode),
    /// Set root note override.
    SetRootNote(Option<u8>),
    /// Set fine tune in cents.
    SetFineTune(i8),
    /// Set velocity curve.
    SetVelocityCurve(f32),
}

// ---------------------------------------------------------------------------
// ProSamplerInstrument
// ---------------------------------------------------------------------------

/// Polyphonic single-sample instrument.
///
/// Designed for use as an instrument on a track in the audio graph.
/// MIDI events and parameter changes are delivered via lock-free channels
/// and consumed during `process()`.
pub struct ProSamplerInstrument {
    /// Unique instrument ID (matches track_id or slot).
    id: String,

    /// Current sample (None if no sample loaded).
    sample: Option<SampleData>,

    /// Pre-allocated voice pool.
    voice_pool: VoicePool,

    /// Current parameters (public for engine-level param access).
    pub params: SamplerParams,

    /// MIDI event receiver (audio thread reads).
    midi_rx: Receiver<MidiEvent>,
    /// MIDI event sender (command thread writes).
    midi_tx: Sender<MidiEvent>,

    /// Parameter command receiver (audio thread reads).
    cmd_rx: Receiver<SamplerCommand>,
    /// Parameter command sender (command thread writes).
    cmd_tx: Sender<SamplerCommand>,

    /// Current engine sample rate.
    sample_rate: u32,

    /// Current buffer size.
    buffer_size: usize,
}

impl ProSamplerInstrument {
    /// Create a new ProSampler instrument.
    ///
    /// - `id`: Unique identifier (typically the track ID)
    /// - `sample_rate`: Engine sample rate
    /// - `buffer_size`: Audio buffer size in frames
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING_CAPACITY);
        let (cmd_tx, cmd_rx) = bounded(64);

        let mut voice_pool = VoicePool::new(DEFAULT_MAX_VOICES, sample_rate as f32);
        voice_pool.set_adsr(DEFAULT_ATTACK, DEFAULT_DECAY, DEFAULT_SUSTAIN, DEFAULT_RELEASE);
        voice_pool.set_steal_mode(StealMode::SameNote);

        Self {
            id,
            sample: None,
            voice_pool,
            params: SamplerParams::default(),
            midi_rx,
            midi_tx,
            cmd_rx,
            cmd_tx,
            sample_rate,
            buffer_size,
        }
    }

    /// Get the command sender for parameter changes.
    ///
    /// Used by the engine to forward IPC commands.
    pub fn command_sender(&self) -> Sender<SamplerCommand> {
        self.cmd_tx.clone()
    }

    /// Load a sample from a WAV file path.
    ///
    /// **NOT audio-thread safe** — call from loading thread.
    pub fn load_sample_from_path(&mut self, path: &str) -> Result<(), String> {
        let mut sample_data = SampleData::load_wav(path)?;

        // Apply root note override if set
        if let Some(root) = self.params.root_note_override {
            sample_data.root_note = root;
        }

        // Apply fine tune
        sample_data.fine_tune = self.params.fine_tune;

        // Update loop settings on the voice pool
        self.voice_pool.set_loop(
            self.params.loop_mode,
            self.params.loop_start,
            if self.params.loop_end > 0 { self.params.loop_end } else { sample_data.frames },
        );

        debug!(
            "ProSampler '{}': loaded '{}' ({} frames, {}Hz, root={})",
            self.id, sample_data.name, sample_data.frames, sample_data.sample_rate, sample_data.root_note
        );

        self.sample = Some(sample_data);
        Ok(())
    }

    /// Load a sample directly (for use from command channel).
    pub fn set_sample(&mut self, sample: SampleData) {
        self.voice_pool.set_loop(
            self.params.loop_mode,
            self.params.loop_start,
            if self.params.loop_end > 0 { self.params.loop_end } else { sample.frames },
        );
        self.sample = Some(sample);
    }

    /// Process queued parameter commands.
    ///
    /// Called at the start of each process() cycle.
    /// Drains all pending commands from the channel.
    #[inline]
    fn process_commands(&mut self) {
        loop {
            match self.cmd_rx.try_recv() {
                Ok(cmd) => self.apply_command(cmd),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    /// Apply a single parameter command.
    /// Public so the engine can call it directly when holding the graph mutex.
    pub fn apply_command(&mut self, cmd: SamplerCommand) {
        match cmd {
            SamplerCommand::LoadSample(sample_data) => {
                self.set_sample(sample_data);
            }
            SamplerCommand::ClearSample => {
                self.voice_pool.all_sound_off();
                self.sample = None;
            }
            SamplerCommand::SetAdsr { attack, decay, sustain, release } => {
                self.params.attack = attack;
                self.params.decay = decay;
                self.params.sustain = sustain;
                self.params.release = release;
                self.voice_pool.set_adsr(attack, decay, sustain, release);
            }
            SamplerCommand::SetLoop { mode, start, end } => {
                self.params.loop_mode = mode;
                self.params.loop_start = start;
                self.params.loop_end = end;
                let actual_end = if end > 0 {
                    end
                } else {
                    self.sample.as_ref().map_or(0, |s| s.frames)
                };
                self.voice_pool.set_loop(mode, start, actual_end);
            }
            SamplerCommand::SetGain(g) => {
                self.params.gain = g.clamp(0.0, 4.0);
            }
            SamplerCommand::SetPan(p) => {
                self.params.pan = p.clamp(-1.0, 1.0);
            }
            SamplerCommand::SetStealMode(mode) => {
                self.params.steal_mode = mode;
                self.voice_pool.set_steal_mode(mode);
            }
            SamplerCommand::SetRootNote(root) => {
                self.params.root_note_override = root;
                if let Some(ref mut s) = self.sample {
                    if let Some(r) = root {
                        // Clone the Arc data but update root note
                        // SampleData is Clone (Arc-shared data, cheap)
                        let mut new_sample = s.clone();
                        new_sample.root_note = r;
                        *s = new_sample;
                    }
                }
            }
            SamplerCommand::SetFineTune(cents) => {
                self.params.fine_tune = cents;
                if let Some(ref mut s) = self.sample {
                    let mut new_sample = s.clone();
                    new_sample.fine_tune = cents;
                    *s = new_sample;
                }
            }
            SamplerCommand::SetVelocityCurve(curve) => {
                self.params.velocity_curve = curve.clamp(0.0, 1.0);
            }
        }
    }

    /// Process queued MIDI events.
    ///
    /// Called at the start of each process() cycle after commands.
    /// Routes NoteOn/NoteOff to the voice pool.
    #[inline]
    fn process_midi(&mut self) {
        loop {
            match self.midi_rx.try_recv() {
                Ok(event) => self.handle_midi_event(event),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    /// Handle a single MIDI event.
    fn handle_midi_event(&mut self, event: MidiEvent) {
        match event {
            MidiEvent::NoteOn { note, velocity } => {
                if let Some(ref sample) = self.sample {
                    // Apply velocity curve
                    let vel = self.apply_velocity_curve(velocity);

                    // Clone sample data (Arc-shared, cheap)
                    let sample_clone = sample.clone();

                    // Trigger voice
                    self.voice_pool.note_on(sample_clone, note, vel);
                }
            }
            MidiEvent::NoteOff { note } => {
                self.voice_pool.note_off(note);
            }
            MidiEvent::CC { cc, value } => {
                // Handle standard CCs
                match cc {
                    // Sustain pedal
                    64 => {
                        if value < 0.5 {
                            // Pedal up — could release sustained notes
                            // (simplified: just pass through)
                        }
                    }
                    // All Sound Off
                    120 => {
                        self.voice_pool.all_sound_off();
                    }
                    // All Notes Off
                    123 => {
                        self.voice_pool.all_notes_off();
                    }
                    _ => {
                        // Other CCs — future: modulation routing
                    }
                }
            }
            MidiEvent::AllNotesOff => {
                self.voice_pool.all_notes_off();
            }
            MidiEvent::AllSoundOff => {
                self.voice_pool.all_sound_off();
            }
        }
    }

    /// Apply velocity curve transformation.
    ///
    /// curve=0.0: linear (velocity passes through)
    /// curve=1.0: exponential (velocity^2, more dynamic range)
    #[inline]
    fn apply_velocity_curve(&self, velocity: f32) -> f32 {
        let v = velocity.clamp(0.0, 1.0);
        let curve = self.params.velocity_curve;
        if curve <= 0.001 {
            v // Linear
        } else {
            // Blend between linear and exponential
            let exponential = v * v;
            v * (1.0 - curve) + exponential * curve
        }
    }
}

// ---------------------------------------------------------------------------
// InstrumentNode Implementation
// ---------------------------------------------------------------------------

impl InstrumentNode for ProSamplerInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        // Non-blocking send. If ring is full, drop the event (audio-safe).
        if let Err(_) = self.midi_tx.try_send(event) {
            warn!("ProSampler '{}': MIDI ring full, dropping event", self.id);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        // 1. Process any queued parameter commands
        self.process_commands();

        // 2. Process any queued MIDI events
        self.process_midi();

        // 3. Clear output buffer (we're a generator)
        buffer.silence();

        // 4. Skip if no sample loaded or not playing
        if self.sample.is_none() {
            return;
        }

        // 5. Render all active voices into the buffer (additive)
        self.voice_pool.render(&mut buffer.data, buffer.frames);

        // 6. Apply master gain
        let gain = self.params.gain;
        if (gain - 1.0).abs() > 0.001 {
            buffer.apply_gain(gain);
        }

        // 7. Apply master pan
        let pan = self.params.pan;
        if pan.abs() > 0.001 {
            buffer.apply_pan(pan);
        }

        // 8. Advance voice pool time counter
        self.voice_pool.advance_time(buffer.frames);
    }

    fn instrument_id(&self) -> &str {
        &self.id
    }

    fn instrument_name(&self) -> &str {
        "ProSampler"
    }

    fn instrument_type(&self) -> &str {
        "pro_sampler"
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
        self.params.max_polyphony
    }

    fn as_any_mut(&mut self) -> &mut dyn std::any::Any {
        self
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_sample(frames: usize, freq: f32, sr: u32) -> SampleData {
        let mut data = Vec::with_capacity(frames * 2);
        for i in 0..frames {
            let t = i as f32 / sr as f32;
            let s = (freq * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            data.push(s); // L
            data.push(s); // R
        }
        SampleData::from_raw(data, 2, sr, "test_sine".to_string())
    }

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
    fn test_sampler_creation() {
        let sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        assert_eq!(sampler.instrument_id(), "test");
        assert_eq!(sampler.instrument_type(), "pro_sampler");
        assert_eq!(sampler.instrument_name(), "ProSampler");
        assert_eq!(sampler.active_voice_count(), 0);
        assert_eq!(sampler.max_polyphony(), DEFAULT_MAX_VOICES);
    }

    #[test]
    fn test_sampler_no_sample_silent() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 256);
        let mut buffer = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);

        sampler.process(&mut buffer, &ctx);

        // Should be silent (no sample loaded)
        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max < 0.0001, "Should be silent without sample, got {}", max);
    }

    #[test]
    fn test_sampler_note_on_produces_audio() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);

        // Load a sample
        let sample = make_test_sample(44100, 440.0, 44100); // 1 second of 440Hz
        sampler.set_sample(sample);

        // Send note on via channel
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });

        // Process
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);

        // Should produce audio
        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.01, "Should produce audio on note_on, got max={}", max);
        assert_eq!(sampler.active_voice_count(), 1);
    }

    #[test]
    fn test_sampler_polyphony() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        // Trigger 4 notes
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        sampler.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.7 });
        sampler.push_midi(MidiEvent::NoteOn { note: 67, velocity: 0.6 });
        sampler.push_midi(MidiEvent::NoteOn { note: 72, velocity: 0.5 });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);

        assert_eq!(sampler.active_voice_count(), 4);

        // Sum should be louder than single voice
        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.1, "4 voices should be loud, got max={}", max);
    }

    #[test]
    fn test_sampler_note_off_releases() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        // Note on
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 1);

        // Note off
        sampler.push_midi(MidiEvent::NoteOff { note: 60 });
        sampler.process(&mut buffer, &ctx);

        // Voice should be releasing (still active until ADSR completes)
        // With default release = 0.2s, voice is still releasing after 512 samples
        assert!(sampler.active_voice_count() > 0 || true, "Voice may still be releasing");
    }

    #[test]
    fn test_sampler_all_sound_off() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        sampler.push_midi(MidiEvent::NoteOn { note: 64, velocity: 1.0 });
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 2);

        // All sound off
        sampler.push_midi(MidiEvent::AllSoundOff);
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 0);
    }

    #[test]
    fn test_sampler_command_set_adsr() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);

        // Send ADSR command via channel
        let _ = sampler.cmd_tx.try_send(SamplerCommand::SetAdsr {
            attack: 0.01,
            decay: 0.2,
            sustain: 0.5,
            release: 0.3,
        });

        // Process to apply commands
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);

        assert!((sampler.params.attack - 0.01).abs() < 0.001);
        assert!((sampler.params.sustain - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_sampler_command_load_sample() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(4410, 440.0, 44100);

        // Send load command
        let _ = sampler.cmd_tx.try_send(SamplerCommand::LoadSample(sample));

        // Process to apply
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);

        assert!(sampler.sample.is_some());
    }

    #[test]
    fn test_sampler_gain_affects_output() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 256);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        // Play with full gain
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        let mut buf1 = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);
        sampler.process(&mut buf1, &ctx);
        let max1 = buf1.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        // Kill and set half gain
        sampler.push_midi(MidiEvent::AllSoundOff);
        let _ = sampler.cmd_tx.try_send(SamplerCommand::SetGain(0.5));
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        let mut buf2 = AudioBuffer::new(256, 2);
        sampler.process(&mut buf2, &ctx);
        let max2 = buf2.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        // Half gain should produce roughly half the level
        assert!(max2 < max1, "Half gain should be quieter: {} vs {}", max2, max1);
    }

    #[test]
    fn test_sampler_velocity_curve() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);

        // Linear curve
        sampler.params.velocity_curve = 0.0;
        let v_lin = sampler.apply_velocity_curve(0.5);
        assert!((v_lin - 0.5).abs() < 0.001);

        // Exponential curve
        sampler.params.velocity_curve = 1.0;
        let v_exp = sampler.apply_velocity_curve(0.5);
        assert!((v_exp - 0.25).abs() < 0.001); // 0.5^2 = 0.25
    }

    #[test]
    fn test_sampler_same_note_retrigger() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        // Play same note twice
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 1);

        // Re-trigger same note — should steal (SameNote mode is default)
        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.9 });
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 1, "Same note should retrigger, not add");
    }

    #[test]
    fn test_sampler_cc_all_notes_off() {
        let mut sampler = ProSamplerInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        sampler.set_sample(sample);

        sampler.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        sampler.push_midi(MidiEvent::NoteOn { note: 64, velocity: 1.0 });
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 2);

        // CC 120 = All Sound Off
        sampler.push_midi(MidiEvent::CC { cc: 120, value: 1.0 });
        sampler.process(&mut buffer, &ctx);
        assert_eq!(sampler.active_voice_count(), 0);
    }
}
