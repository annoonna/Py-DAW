// ==========================================================================
// BachOrgel — Additive organ synthesizer
// ==========================================================================
// v0.0.20.694 — Phase R11A
//
// A pipe organ emulation using additive synthesis:
//   - 9 organ stops (16', 8', 5⅓', 4', 2⅔', 2', 1⅗', 1⅓', 1')
//   - Per-pipe detuning for warm chorus effect
//   - Simple rotary speaker emulation (tremolo + chorus)
//   - 16-voice polyphony
//
// Rules:
//   ✅ render_sample() zero-alloc
//   ✅ Pre-allocated voice array
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::f32::consts::PI;
use crossbeam_channel::{bounded, Receiver, Sender, TrySendError};
use std::any::Any;

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use super::{InstrumentNode, MidiEvent};

const TWO_PI: f32 = 2.0 * PI;
const MAX_VOICES: usize = 16;
const NUM_PIPES: usize = 9;
const MIDI_RING: usize = 256;

// Pipe multipliers: Hammond drawbar footages
// 16'  8'  5⅓'  4'  2⅔'  2'  1⅗'  1⅓'  1'
const PIPE_MULTS: [f32; NUM_PIPES] = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0];

// Per-pipe detuning in cents for organic chorus effect
const PIPE_DETUNE: [f32; NUM_PIPES] = [-1.8, 0.0, -0.9, 1.2, -1.5, 2.1, 0.7, -2.2, 1.6];

// ---------------------------------------------------------------------------
// Voice
// ---------------------------------------------------------------------------

struct OrgelVoice {
    note: u8,
    freq: f32,
    velocity: f32,
    active: bool,
    released: bool,
    age: u32,
    release_age: u32,
    /// Per-pipe phases.
    pipe_phases: [f32; NUM_PIPES],
    seq: u64,
}

impl OrgelVoice {
    fn new() -> Self {
        Self {
            note: 0, freq: 440.0, velocity: 0.0,
            active: false, released: false,
            age: 0, release_age: 0,
            pipe_phases: [0.0; NUM_PIPES],
            seq: 0,
        }
    }

    fn note_on(&mut self, note: u8, velocity: f32, seq: u64) {
        self.note = note;
        self.freq = 440.0 * 2.0f32.powf((note as f32 - 69.0) / 12.0);
        self.velocity = velocity;
        self.active = true;
        self.released = false;
        self.age = 0;
        self.release_age = 0;
        self.pipe_phases = [0.0; NUM_PIPES];
        self.seq = seq;
    }

    fn note_off(&mut self) {
        if self.active && !self.released {
            self.released = true;
            self.release_age = 0;
        }
    }

    fn kill(&mut self) {
        self.active = false;
    }

    /// Render one sample of additive organ sound.
    #[inline]
    fn render_sample(&mut self, drawbars: &[f32; NUM_PIPES], sr: f32, attack_ms: f32, release_ms: f32) -> f32 {
        if !self.active {
            return 0.0;
        }

        let mut sum = 0.0f32;

        for i in 0..NUM_PIPES {
            if drawbars[i] < 0.001 {
                continue;
            }
            // Detuned pipe frequency
            let pipe_freq = self.freq * PIPE_MULTS[i] * 2.0f32.powf(PIPE_DETUNE[i] / 1200.0);
            let dt = pipe_freq / sr;
            self.pipe_phases[i] = (self.pipe_phases[i] + dt).rem_euclid(1.0);

            sum += (self.pipe_phases[i] * TWO_PI).sin() * drawbars[i];
        }

        // Simple AEG: attack + release
        let attack_samples = (attack_ms * 0.001 * sr).max(1.0);
        let release_samples = (release_ms * 0.001 * sr).max(1.0);

        let env = if self.released {
            let r = 1.0 - (self.release_age as f32 / release_samples).min(1.0);
            self.release_age += 1;
            if r <= 0.001 {
                self.active = false;
                return 0.0;
            }
            r
        } else {
            let a = (self.age as f32 / attack_samples).min(1.0);
            self.age += 1;
            a
        };

        sum * env * self.velocity * 0.2 // normalize level
    }
}

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

/// BachOrgel parameters.
pub struct OrgelParams {
    /// 9 drawbar levels (0.0–1.0), matching Hammond 16'..1'.
    pub drawbars: [f32; NUM_PIPES],
    /// Attack time in ms.
    pub attack_ms: f32,
    /// Release time in ms.
    pub release_ms: f32,
    /// Master gain.
    pub gain: f32,
    /// Rotary speaker speed (0 = slow, 1 = fast).
    pub rotary_speed: f32,
    /// Rotary mix (0–1).
    pub rotary_mix: f32,
}

impl Default for OrgelParams {
    fn default() -> Self {
        Self {
            // Classic Hammond registration: 888000000
            drawbars: [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            attack_ms: 10.0,
            release_ms: 80.0,
            gain: 0.7,
            rotary_speed: 0.0,
            rotary_mix: 0.3,
        }
    }
}

// ---------------------------------------------------------------------------
// BachOrgelInstrument
// ---------------------------------------------------------------------------

pub struct BachOrgelInstrument {
    id: String,
    sample_rate: u32,
    midi_tx: Sender<MidiEvent>,
    midi_rx: Receiver<MidiEvent>,
    voices: [OrgelVoice; MAX_VOICES],
    params: OrgelParams,
    seq_counter: u64,
    /// Rotary LFO phase.
    rotary_phase: f32,
}

impl BachOrgelInstrument {
    pub fn new(id: String, sample_rate: u32, _buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING);
        let voices = std::array::from_fn(|_| OrgelVoice::new());
        Self {
            id, sample_rate,
            midi_tx, midi_rx,
            voices,
            params: OrgelParams::default(),
            seq_counter: 0,
            rotary_phase: 0.0,
        }
    }

    /// Set drawbar level (0-8 index, 0.0–1.0 level).
    pub fn set_drawbar(&mut self, index: usize, level: f32) {
        if index < NUM_PIPES {
            self.params.drawbars[index] = level.clamp(0.0, 1.0);
        }
    }

    /// Apply a classic registration preset.
    pub fn set_registration(&mut self, name: &str) {
        self.params.drawbars = match name {
            "Full" => [0.8, 1.0, 0.6, 1.0, 0.6, 1.0, 0.4, 0.3, 0.2],
            "Jazz" => [0.0, 0.8, 0.0, 0.6, 0.0, 0.4, 0.0, 0.0, 0.0],
            "Gospel" => [0.6, 1.0, 0.8, 1.0, 0.8, 1.0, 0.6, 0.5, 0.4],
            "Ballad" => [0.0, 0.6, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],
            "Rock" => [0.9, 1.0, 0.5, 1.0, 0.5, 0.8, 0.3, 0.2, 0.1],
            _ => [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0], // default
        };
    }

    fn alloc_voice(&self) -> usize {
        for (i, v) in self.voices.iter().enumerate() {
            if !v.active { return i; }
        }
        let mut oldest = 0;
        let mut oldest_seq = u64::MAX;
        for (i, v) in self.voices.iter().enumerate() {
            if v.seq < oldest_seq { oldest_seq = v.seq; oldest = i; }
        }
        oldest
    }
}

impl InstrumentNode for BachOrgelInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        if let Err(TrySendError::Full(evt)) = self.midi_tx.try_send(event) {
            let _ = self.midi_rx.try_recv();
            let _ = self.midi_tx.try_send(evt);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext) {
        let sr = ctx.sample_rate as f32;

        // Drain MIDI
        loop {
            match self.midi_rx.try_recv() {
                Ok(evt) => match evt {
                    MidiEvent::NoteOn { note, velocity } => {
                        self.seq_counter += 1;
                        let idx = self.alloc_voice();
                        self.voices[idx].note_on(note, velocity, self.seq_counter);
                    }
                    MidiEvent::NoteOff { note } => {
                        for v in &mut self.voices {
                            if v.active && v.note == note { v.note_off(); }
                        }
                    }
                    MidiEvent::AllNotesOff => {
                        for v in &mut self.voices { if v.active { v.note_off(); } }
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
        let rotary_rate = if self.params.rotary_speed > 0.5 { 6.0 } else { 0.8 }; // Hz
        let rotary_depth = self.params.rotary_mix * 0.3;

        for frame in 0..ctx.frames {
            let mut mix = 0.0f32;

            for voice in &mut self.voices {
                mix += voice.render_sample(&self.params.drawbars, sr, self.params.attack_ms, self.params.release_ms);
            }

            // Simple rotary speaker: amplitude modulation + slight stereo pan
            let rot_val = (self.rotary_phase * TWO_PI).sin();
            self.rotary_phase = (self.rotary_phase + rotary_rate / sr).rem_euclid(1.0);

            let rotary_mod = 1.0 + rot_val * rotary_depth;
            mix *= self.params.gain * rotary_mod;

            // Stereo with rotary panning
            let pan = rot_val * self.params.rotary_mix * 0.4;
            let idx = frame * buffer.channels;
            if idx + 1 < buffer.data.len() {
                let x = (pan + 1.0) * 0.5;
                buffer.data[idx] = mix * (x * std::f32::consts::FRAC_PI_2).cos();
                buffer.data[idx + 1] = mix * (x * std::f32::consts::FRAC_PI_2).sin();
            }
        }
    }

    fn instrument_id(&self) -> &str { &self.id }
    fn instrument_name(&self) -> &str { "BachOrgel" }
    fn instrument_type(&self) -> &str { "bach_orgel" }
    fn set_sample_rate(&mut self, sr: u32) { self.sample_rate = sr; }
    fn set_buffer_size(&mut self, _bs: usize) {}
    fn active_voice_count(&self) -> usize { self.voices.iter().filter(|v| v.active).count() }
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
            frames, sample_rate: sr, position_samples: 0,
            position_beats: 0.0, is_playing: true, bpm: 120.0,
            time_sig_num: 4, time_sig_den: 4,
        }
    }

    #[test]
    fn test_orgel_creation() {
        let inst = BachOrgelInstrument::new("orgel".to_string(), 44100, 512);
        assert_eq!(inst.instrument_type(), "bach_orgel");
        assert_eq!(inst.active_voice_count(), 0);
    }

    #[test]
    fn test_orgel_produces_audio() {
        let mut inst = BachOrgelInstrument::new("t".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buf = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.process(&mut buf, &ctx);

        let max: f32 = buf.data.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max > 0.005, "Organ should produce audio: {}", max);
    }

    #[test]
    fn test_orgel_polyphony() {
        let mut inst = BachOrgelInstrument::new("t".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buf = AudioBuffer::new(256, 2);

        for n in 60..66 {
            inst.push_midi(MidiEvent::NoteOn { note: n, velocity: 0.7 });
        }
        inst.process(&mut buf, &ctx);
        assert_eq!(inst.active_voice_count(), 6);
    }

    #[test]
    fn test_registration_preset() {
        let mut inst = BachOrgelInstrument::new("t".to_string(), 44100, 512);
        inst.set_registration("Gospel");
        assert!(inst.params.drawbars[0] > 0.5);
        assert!(inst.params.drawbars[1] > 0.9);
    }
}
