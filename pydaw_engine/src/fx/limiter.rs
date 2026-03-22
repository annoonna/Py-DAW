// ==========================================================================
// Limiter — Brickwall limiter with auto-release
// ==========================================================================
// v0.0.20.667 — Phase R2B
//
// Reference: pydaw/audio/builtin_fx.py LimiterFx
// Instant attack, configurable release, ceiling control.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::math::db_to_linear;

/// Brickwall Limiter.
pub struct Limiter {
    ceiling_linear: f32,
    gain_db: f32,
    release_coeff: f32,
    envelope: f32,
    sample_rate: f32,
}

impl Limiter {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            ceiling_linear: db_to_linear(-0.3), // -0.3 dBFS default
            gain_db: 0.0,
            release_coeff: (-1.0 / (0.1 * sample_rate)).exp(), // 100ms release
            envelope: 0.0,
            sample_rate,
        }
    }

    /// Set ceiling in dB (e.g., -0.3 dBFS).
    pub fn set_ceiling(&mut self, ceiling_db: f32) {
        self.ceiling_linear = db_to_linear(ceiling_db.min(0.0));
    }

    /// Set input gain in dB.
    pub fn set_gain(&mut self, gain_db: f32) {
        self.gain_db = gain_db;
    }

    /// Set release time in ms.
    pub fn set_release(&mut self, release_ms: f32) {
        let release_s = (release_ms * 0.001).max(0.001);
        self.release_coeff = (-1.0 / (release_s * self.sample_rate)).exp();
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    pub fn reset(&mut self) {
        self.envelope = 0.0;
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let input_gain = db_to_linear(self.gain_db);
        let ceiling = self.ceiling_linear;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            // Apply input gain
            buffer.data[idx] *= input_gain;
            buffer.data[idx + 1] *= input_gain;

            // Peak detection (instant attack)
            let peak = buffer.data[idx].abs().max(buffer.data[idx + 1].abs());

            // Envelope follower: instant attack, smooth release
            if peak > self.envelope {
                self.envelope = peak; // instant attack
            } else {
                self.envelope = peak + self.release_coeff * (self.envelope - peak);
            }

            // Gain computation
            let gain = if self.envelope > ceiling {
                ceiling / self.envelope
            } else {
                1.0
            };

            buffer.data[idx] *= gain;
            buffer.data[idx + 1] *= gain;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_limiter_clamps() {
        let mut lim = Limiter::new(44100.0);
        lim.set_ceiling(-0.0); // 0 dBFS = 1.0 linear

        let mut buf = AudioBuffer::new(1024, 2);
        for i in 0..1024 {
            buf.data[i * 2] = 2.0;    // way above ceiling
            buf.data[i * 2 + 1] = 2.0;
        }
        lim.process(&mut buf);

        for i in 0..1024 {
            assert!(buf.data[i * 2].abs() <= 1.01,
                "Sample {} = {} (should be ≤ 1.0)", i, buf.data[i * 2]);
        }
    }

    #[test]
    fn test_limiter_passes_quiet() {
        let mut lim = Limiter::new(44100.0);
        lim.set_ceiling(-0.3);

        let mut buf = AudioBuffer::new(512, 2);
        for i in 0..512 {
            buf.data[i * 2] = 0.1;
            buf.data[i * 2 + 1] = 0.1;
        }
        lim.process(&mut buf);

        let last = buf.data[buf.data.len() - 2];
        assert!((last - 0.1).abs() < 0.01, "Quiet signal should pass: {}", last);
    }
}
