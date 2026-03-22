// ==========================================================================
// Compressor — Feed-forward RMS compressor with sidechain
// ==========================================================================
// v0.0.20.667 — Phase R2B
//
// Reference: pydaw/audio/builtin_fx.py CompressorFx
//
// Architecture: Feed-forward design (detector on input, not output).
// RMS envelope for smooth detection, log-domain gain computation.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::math::{db_to_linear, linear_to_db};

/// Compressor parameters.
#[derive(Debug, Clone, Copy)]
pub struct CompressorParams {
    pub threshold_db: f32,  // -60 to 0 dB
    pub ratio: f32,         // 1.0 (no compression) to 20.0+
    pub attack_ms: f32,     // 0.1 to 200 ms
    pub release_ms: f32,    // 10 to 2000 ms
    pub knee_db: f32,       // 0 (hard) to 12 dB (soft)
    pub makeup_db: f32,     // 0 to 30 dB
}

impl Default for CompressorParams {
    fn default() -> Self {
        Self {
            threshold_db: -18.0,
            ratio: 4.0,
            attack_ms: 10.0,
            release_ms: 100.0,
            knee_db: 3.0,
            makeup_db: 0.0,
        }
    }
}

/// Feed-forward RMS Compressor.
pub struct Compressor {
    params: CompressorParams,
    sample_rate: f32,
    // Envelope follower state
    env_db: f32,
    attack_coeff: f32,
    release_coeff: f32,
    // Metering
    gain_reduction_db: f32,
}

impl Compressor {
    pub fn new(sample_rate: f32) -> Self {
        let mut c = Self {
            params: CompressorParams::default(),
            sample_rate,
            env_db: -96.0,
            attack_coeff: 0.0,
            release_coeff: 0.0,
            gain_reduction_db: 0.0,
        };
        c.recalc_coeffs();
        c
    }

    pub fn set_params(&mut self, params: CompressorParams) {
        self.params = params;
        self.recalc_coeffs();
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        self.recalc_coeffs();
    }

    fn recalc_coeffs(&mut self) {
        let attack_s = (self.params.attack_ms * 0.001).max(0.0001);
        let release_s = (self.params.release_ms * 0.001).max(0.001);
        self.attack_coeff = (-1.0 / (attack_s * self.sample_rate)).exp();
        self.release_coeff = (-1.0 / (release_s * self.sample_rate)).exp();
    }

    pub fn reset(&mut self) {
        self.env_db = -96.0;
        self.gain_reduction_db = 0.0;
    }

    /// Get current gain reduction in dB (for metering).
    pub fn gain_reduction_db(&self) -> f32 {
        self.gain_reduction_db
    }

    /// Compute gain in dB for a given input level in dB (with soft knee).
    #[inline]
    fn compute_gain_db(&self, input_db: f32) -> f32 {
        let thresh = self.params.threshold_db;
        let ratio = self.params.ratio;
        let knee = self.params.knee_db;

        if knee <= 0.0 {
            // Hard knee
            if input_db <= thresh {
                0.0
            } else {
                (thresh + (input_db - thresh) / ratio) - input_db
            }
        } else {
            // Soft knee
            let half_knee = knee * 0.5;
            let lower = thresh - half_knee;
            let upper = thresh + half_knee;

            if input_db <= lower {
                0.0
            } else if input_db >= upper {
                (thresh + (input_db - thresh) / ratio) - input_db
            } else {
                // Quadratic interpolation in the knee region
                let x = input_db - lower;
                let gain_at_upper = (thresh + (upper - thresh) / ratio) - upper;
                gain_at_upper * x * x / (2.0 * knee * knee)
            }
        }
    }

    /// Process stereo AudioBuffer in-place. **AUDIO THREAD**.
    ///
    /// `sidechain`: Optional external sidechain buffer. If None, uses input signal.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer, sidechain: Option<&AudioBuffer>) {
        let frames = buffer.frames;
        let makeup_linear = db_to_linear(self.params.makeup_db);
        let mut peak_gr: f32 = 0.0;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            // Detector: use sidechain if available, otherwise input
            let (det_l, det_r) = if let Some(sc) = sidechain {
                if idx + 1 < sc.data.len() {
                    (sc.data[idx], sc.data[idx + 1])
                } else {
                    (buffer.data[idx], buffer.data[idx + 1])
                }
            } else {
                (buffer.data[idx], buffer.data[idx + 1])
            };

            // RMS of stereo detector
            let rms_sq = (det_l * det_l + det_r * det_r) * 0.5;
            let input_db = if rms_sq > 1e-12 {
                linear_to_db(rms_sq.sqrt())
            } else {
                -96.0
            };

            // Envelope follower (ballistics)
            let coeff = if input_db > self.env_db {
                self.attack_coeff
            } else {
                self.release_coeff
            };
            self.env_db = input_db + coeff * (self.env_db - input_db);

            // Gain computation
            let gr_db = self.compute_gain_db(self.env_db);
            let gain = db_to_linear(gr_db) * makeup_linear;

            // Apply gain
            buffer.data[idx] *= gain;
            buffer.data[idx + 1] *= gain;

            peak_gr = peak_gr.min(gr_db);
        }

        self.gain_reduction_db = peak_gr;
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_no_compression_below_threshold() {
        let mut comp = Compressor::new(44100.0);
        comp.set_params(CompressorParams {
            threshold_db: -10.0,
            ratio: 4.0,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(512, 2);
        // Fill with very quiet signal (-40 dBFS)
        let level = db_to_linear(-40.0);
        for i in 0..512 {
            buf.data[i * 2] = level;
            buf.data[i * 2 + 1] = level;
        }
        let original_peak = level;
        comp.process(&mut buf, None);

        // Should be mostly unchanged (+ makeup if any)
        let output_peak = buf.data[buf.data.len() - 2].abs();
        assert!(
            (output_peak - original_peak).abs() < 0.01,
            "Below threshold: input={}, output={}", original_peak, output_peak
        );
    }

    #[test]
    fn test_compression_above_threshold() {
        let mut comp = Compressor::new(44100.0);
        comp.set_params(CompressorParams {
            threshold_db: -20.0,
            ratio: 10.0,
            attack_ms: 0.1,
            release_ms: 50.0,
            knee_db: 0.0,
            makeup_db: 0.0,
        });

        let mut buf = AudioBuffer::new(4096, 2);
        // Fill with loud signal (-6 dBFS)
        let level = db_to_linear(-6.0);
        for i in 0..4096 {
            buf.data[i * 2] = level;
            buf.data[i * 2 + 1] = level;
        }

        comp.process(&mut buf, None);

        // Output should be reduced
        let output = buf.data[buf.data.len() - 2].abs();
        assert!(
            output < level * 0.7,
            "Above threshold: input={}, output={} (expected reduction)", level, output
        );
    }

    #[test]
    fn test_gain_reduction_meter() {
        let mut comp = Compressor::new(44100.0);
        comp.set_params(CompressorParams {
            threshold_db: -20.0,
            ratio: 8.0,
            attack_ms: 0.1,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(4096, 2);
        let level = db_to_linear(-6.0);
        for i in 0..4096 {
            buf.data[i * 2] = level;
            buf.data[i * 2 + 1] = level;
        }
        comp.process(&mut buf, None);

        assert!(comp.gain_reduction_db() < -1.0,
            "GR should be negative: {}", comp.gain_reduction_db());
    }
}
