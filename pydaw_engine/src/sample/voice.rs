// ==========================================================================
// Sample Voice — Single playing instance of a sample
// ==========================================================================
// v0.0.20.671 — Phase R5B
//
// Each voice plays one sample with:
//   - Pitch shifting via playback rate (cubic interpolation from R1)
//   - ADSR envelope (from R1)
//   - Loop modes: None, Forward, PingPong
//   - Velocity → volume mapping
//
// Rules:
//   ✅ Zero heap allocations in render()
//   ✅ All state is pre-allocated
//   ✅ Cubic interpolation for high-quality pitch shifting
//   ❌ NO allocations, locks, or panics in audio thread
// ==========================================================================

use crate::dsp::envelope::AdsrEnvelope;
use crate::dsp::interpolation::interpolate_cubic;
use crate::sample::SampleData;

/// Voice state.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceState {
    /// Voice is idle (not playing).
    Idle,
    /// Voice is actively playing (attack/decay/sustain).
    Playing,
    /// Voice is in release phase (note-off received).
    Releasing,
}

/// Loop mode for sample playback.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LoopMode {
    /// No looping — play once then stop.
    None,
    /// Forward loop — loop from loop_end back to loop_start.
    Forward,
    /// Ping-pong — alternate forward/backward between loop points.
    PingPong,
}

/// A single sample voice — one playing instance.
///
/// Pre-allocated, reused from VoicePool. When idle, costs zero CPU.
pub struct SampleVoice {
    /// Current state.
    state: VoiceState,

    /// The sample being played (Arc-shared, cheap to clone).
    sample: Option<SampleData>,

    /// Current playback position (fractional frame index into sample).
    position: f64,

    /// Playback rate (1.0 = original pitch, 2.0 = octave up, etc.).
    /// Includes both pitch and sample-rate conversion.
    playback_rate: f64,

    /// Playback direction for PingPong (+1.0 or -1.0).
    direction: f64,

    /// ADSR amplitude envelope.
    envelope: AdsrEnvelope,

    /// Velocity gain (0.0 – 1.0).
    velocity_gain: f32,

    /// MIDI note number (for voice identification / stealing).
    note: u8,

    // --- Loop settings ---
    /// Loop mode.
    loop_mode: LoopMode,

    /// Loop start frame (0-based).
    loop_start: usize,

    /// Loop end frame (exclusive).
    loop_end: usize,

    // --- Voice metadata ---
    /// When this voice was started (sample counter, for age-based stealing).
    start_time: u64,

    /// Unique voice ID (for tracking).
    voice_id: u32,
}

impl SampleVoice {
    /// Create a new idle voice.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            state: VoiceState::Idle,
            sample: None,
            position: 0.0,
            playback_rate: 1.0,
            direction: 1.0,
            envelope: AdsrEnvelope::new(0.005, 0.1, 0.8, 0.2, sample_rate),
            velocity_gain: 1.0,
            note: 0,
            loop_mode: LoopMode::None,
            loop_start: 0,
            loop_end: 0,
            start_time: 0,
            voice_id: 0,
        }
    }

    /// Trigger note-on. Starts playing the sample.
    ///
    /// - `sample`: The sample to play
    /// - `note`: MIDI note number (determines pitch)
    /// - `velocity`: MIDI velocity (0.0 – 1.0, determines volume)
    /// - `engine_sr`: Current engine sample rate
    /// - `time`: Current global sample counter (for age tracking)
    pub fn note_on(
        &mut self,
        sample: SampleData,
        note: u8,
        velocity: f32,
        engine_sr: u32,
        time: u64,
    ) {
        self.playback_rate = sample.playback_rate(note, engine_sr);
        self.sample = Some(sample);
        self.note = note;
        self.velocity_gain = velocity.clamp(0.0, 1.0);
        self.position = 0.0;
        self.direction = 1.0;
        self.start_time = time;
        self.state = VoiceState::Playing;
        self.envelope.note_on();
    }

    /// Trigger note-off. Voice enters release phase.
    pub fn note_off(&mut self) {
        if self.state == VoiceState::Playing {
            self.state = VoiceState::Releasing;
            self.envelope.note_off();
        }
    }

    /// Force-kill the voice immediately (no release).
    pub fn kill(&mut self) {
        self.state = VoiceState::Idle;
        self.envelope.kill();
        self.sample = None;
    }

    /// Is this voice currently producing audio?
    #[inline]
    pub fn is_active(&self) -> bool {
        self.state != VoiceState::Idle
    }

    /// Get current state.
    #[inline]
    pub fn state(&self) -> VoiceState {
        self.state
    }

    /// Get the MIDI note this voice is playing.
    #[inline]
    pub fn note(&self) -> u8 {
        self.note
    }

    /// Get the start time (for age-based voice stealing).
    #[inline]
    pub fn start_time(&self) -> u64 {
        self.start_time
    }

    /// Get current envelope level (for quietest-voice stealing).
    #[inline]
    pub fn current_level(&self) -> f32 {
        self.envelope.current() * self.velocity_gain
    }

    /// Set ADSR parameters.
    pub fn set_adsr(&mut self, attack: f32, decay: f32, sustain: f32, release: f32) {
        self.envelope.set_params(attack, decay, sustain, release);
    }

    /// Set sample rate (for ADSR recalculation).
    pub fn set_sample_rate(&mut self, sr: f32) {
        self.envelope.set_sample_rate(sr);
    }

    /// Set loop parameters.
    pub fn set_loop(&mut self, mode: LoopMode, start: usize, end: usize) {
        self.loop_mode = mode;
        self.loop_start = start;
        self.loop_end = end;
    }

    /// Render this voice into a stereo buffer (additive).
    ///
    /// **AUDIO THREAD** — zero-alloc, no panics.
    /// Adds this voice's output to `output` (does not overwrite).
    ///
    /// Returns the number of frames rendered (may be less if voice finishes).
    #[inline]
    pub fn render(&mut self, output: &mut [f32], frames: usize) -> usize {
        if self.state == VoiceState::Idle {
            return 0;
        }

        let sample = match &self.sample {
            Some(s) => s,
            None => {
                self.state = VoiceState::Idle;
                return 0;
            }
        };

        let sample_frames = sample.frames;
        if sample_frames == 0 {
            self.state = VoiceState::Idle;
            return 0;
        }

        let data = &sample.data;
        let vel = self.velocity_gain;
        let rate = self.playback_rate;
        let loop_mode = self.loop_mode;
        let loop_start = self.loop_start;
        let loop_end = if self.loop_end > 0 { self.loop_end } else { sample_frames };

        let mut rendered = 0;

        for frame in 0..frames {
            // Get envelope value
            let env = self.envelope.process();

            // Check if envelope finished (voice done)
            if !self.envelope.is_active() {
                self.state = VoiceState::Idle;
                self.sample = None;
                break;
            }

            let gain = env * vel;

            // Read sample with cubic interpolation
            let pos = self.position;
            let idx = pos as usize;
            let frac = (pos - idx as f64) as f32;

            let (l, r) = if idx + 2 < sample_frames {
                // Full cubic interpolation (4 points)
                let i0 = if idx > 0 { idx - 1 } else { 0 };
                let i1 = idx;
                let i2 = idx + 1;
                let i3 = idx + 2;

                let l = interpolate_cubic(
                    data[i0 * 2], data[i1 * 2], data[i2 * 2], data[i3 * 2], frac,
                );
                let r = interpolate_cubic(
                    data[i0 * 2 + 1], data[i1 * 2 + 1], data[i2 * 2 + 1], data[i3 * 2 + 1], frac,
                );
                (l, r)
            } else if idx < sample_frames {
                // Near end — linear fallback
                let (l0, r0) = (data[idx * 2], data[idx * 2 + 1]);
                if idx + 1 < sample_frames {
                    let (l1, r1) = (data[(idx + 1) * 2], data[(idx + 1) * 2 + 1]);
                    (l0 + (l1 - l0) * frac, r0 + (r1 - r0) * frac)
                } else {
                    (l0, r0)
                }
            } else {
                (0.0, 0.0)
            };

            // Add to output (additive mixing)
            let out_idx = frame * 2;
            if out_idx + 1 < output.len() {
                output[out_idx] += l * gain;
                output[out_idx + 1] += r * gain;
            }

            rendered += 1;

            // Advance position
            self.position += rate * self.direction;

            // Handle loop / end-of-sample
            match loop_mode {
                LoopMode::None => {
                    if self.position >= sample_frames as f64 {
                        // End of sample — start release if still playing
                        if self.state == VoiceState::Playing {
                            self.envelope.note_off();
                            self.state = VoiceState::Releasing;
                        }
                        // Clamp position to end
                        self.position = (sample_frames - 1) as f64;
                    }
                }
                LoopMode::Forward => {
                    if self.position >= loop_end as f64 {
                        // Wrap back to loop start
                        let overshoot = self.position - loop_end as f64;
                        let loop_len = (loop_end - loop_start).max(1) as f64;
                        self.position = loop_start as f64 + (overshoot % loop_len);
                    }
                }
                LoopMode::PingPong => {
                    if self.direction > 0.0 && self.position >= loop_end as f64 {
                        // Reverse direction at loop end
                        self.direction = -1.0;
                        let overshoot = self.position - loop_end as f64;
                        self.position = loop_end as f64 - overshoot;
                    } else if self.direction < 0.0 && self.position <= loop_start as f64 {
                        // Forward again at loop start
                        self.direction = 1.0;
                        let undershoot = loop_start as f64 - self.position;
                        self.position = loop_start as f64 + undershoot;
                    }
                }
            }
        }

        rendered
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sine_sample(frames: usize, freq: f32, sr: u32) -> SampleData {
        let mut data = Vec::with_capacity(frames * 2);
        for i in 0..frames {
            let t = i as f32 / sr as f32;
            let s = (freq * 2.0 * std::f32::consts::PI * t).sin() * 0.8;
            data.push(s); // L
            data.push(s); // R
        }
        SampleData::from_raw(data, 2, sr, "sine".to_string())
    }

    #[test]
    fn test_voice_lifecycle() {
        let mut voice = SampleVoice::new(44100.0);
        assert_eq!(voice.state(), VoiceState::Idle);
        assert!(!voice.is_active());

        let sample = make_sine_sample(4410, 440.0, 44100);
        voice.note_on(sample, 60, 0.8, 44100, 0);
        assert_eq!(voice.state(), VoiceState::Playing);
        assert!(voice.is_active());

        voice.note_off();
        assert_eq!(voice.state(), VoiceState::Releasing);
        assert!(voice.is_active());

        voice.kill();
        assert_eq!(voice.state(), VoiceState::Idle);
        assert!(!voice.is_active());
    }

    #[test]
    fn test_voice_renders_audio() {
        let mut voice = SampleVoice::new(44100.0);
        voice.set_adsr(0.001, 0.01, 1.0, 0.01);

        let sample = make_sine_sample(4410, 440.0, 44100); // 100ms of 440Hz
        voice.note_on(sample, 60, 1.0, 44100, 0);

        // Render 512 frames
        let mut buf = vec![0.0f32; 512 * 2];
        let rendered = voice.render(&mut buf, 512);
        assert_eq!(rendered, 512);

        // Should have non-zero output
        let max = buf.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.01, "Voice should produce output, got max={}", max);
    }

    #[test]
    fn test_voice_pitch_shift() {
        let mut voice = SampleVoice::new(44100.0);
        voice.set_adsr(0.0, 0.0, 1.0, 0.5);

        // 1 second of 440Hz at 44100
        let sample = make_sine_sample(44100, 440.0, 44100);
        // Play at C5 (note 72) = octave up from C4 (root 60) → rate = 2.0
        voice.note_on(sample, 72, 1.0, 44100, 0);

        // After 22050 frames at rate 2.0, position should be ~44100 (end of sample)
        let mut buf = vec![0.0f32; 22050 * 2];
        voice.render(&mut buf, 22050);

        // Voice should still be active (ADSR sustain), but near end
        // The position should have advanced by 22050 * 2.0 = 44100
    }

    #[test]
    fn test_voice_forward_loop() {
        let mut voice = SampleVoice::new(44100.0);
        voice.set_adsr(0.0, 0.0, 1.0, 0.5);
        voice.set_loop(LoopMode::Forward, 100, 200);

        let sample = make_sine_sample(1000, 440.0, 44100);
        voice.note_on(sample, 60, 1.0, 44100, 0);

        // Render enough frames to loop multiple times
        let mut buf = vec![0.0f32; 1000 * 2];
        let rendered = voice.render(&mut buf, 1000);
        assert_eq!(rendered, 1000);

        // Voice should still be active (looping)
        assert!(voice.is_active());
    }

    #[test]
    fn test_voice_velocity_affects_volume() {
        let sample = make_sine_sample(4410, 440.0, 44100);

        // Full velocity
        let mut voice_loud = SampleVoice::new(44100.0);
        voice_loud.set_adsr(0.0, 0.0, 1.0, 0.5);
        voice_loud.note_on(sample.clone(), 60, 1.0, 44100, 0);
        let mut buf_loud = vec![0.0f32; 256 * 2];
        voice_loud.render(&mut buf_loud, 256);
        let max_loud = buf_loud.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        // Half velocity
        let mut voice_quiet = SampleVoice::new(44100.0);
        voice_quiet.set_adsr(0.0, 0.0, 1.0, 0.5);
        voice_quiet.note_on(sample, 60, 0.5, 44100, 0);
        let mut buf_quiet = vec![0.0f32; 256 * 2];
        voice_quiet.render(&mut buf_quiet, 256);
        let max_quiet = buf_quiet.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        // Loud should be roughly 2× quiet
        assert!(max_loud > max_quiet * 1.5,
            "Loud ({}) should be > 1.5× quiet ({})", max_loud, max_quiet);
    }
}
