// ==========================================================================
// DeEsser — Frequency-selective compressor for sibilance control
// ==========================================================================
// v0.0.20.669 — Phase R3B
//
// Reference: pydaw/audio/utility_fx.py DeEsserFx
//
// Architecture: Biquad bandpass isolates sibilance band → envelope follower
// detects level → proportional gain reduction on full signal when band
// exceeds threshold. Listen mode solos the detection band.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::biquad::{Biquad, BiquadCoeffs, FilterType};
use crate::dsp::math::db_to_linear;

/// DeEsser parameters.
#[derive(Debug, Clone, Copy)]
pub struct DeEsserParams {
    /// Center frequency of detection band in Hz (2000 – 16000)
    pub frequency: f32,
    /// Detection threshold in dB (-40 to 0)
    pub threshold_db: f32,
    /// Maximum reduction amount in dB (0 – 24)
    pub range_db: f32,
    /// Detector attack in ms (0.01 – 10)
    pub attack_ms: f32,
    /// Detector release in ms (10 – 200)
    pub release_ms: f32,
    /// Solo detection band (for tuning)
    pub listen: bool,
}

impl Default for DeEsserParams {
    fn default() -> Self {
        Self {
            frequency: 6500.0,
            threshold_db: -20.0,
            range_db: 6.0,
            attack_ms: 0.1,
            release_ms: 50.0,
            listen: false,
        }
    }
}

/// Frequency-selective DeEsser.
pub struct DeEsser {
    params: DeEsserParams,
    sample_rate: f32,
    // Detection bandpass filters (stereo)
    bp_l: Biquad,
    bp_r: Biquad,
    // Envelope follower state
    env: f32,
    // Current gain reduction in dB (for metering)
    gain_reduction_db: f32,
    // Last params used for coefficient calculation
    last_freq: f32,
}

impl DeEsser {
    pub fn new(sample_rate: f32) -> Self {
        let mut de = Self {
            params: DeEsserParams::default(),
            sample_rate,
            bp_l: Biquad::new(FilterType::BandPass, 6500.0, 2.0, 0.0, sample_rate),
            bp_r: Biquad::new(FilterType::BandPass, 6500.0, 2.0, 0.0, sample_rate),
            env: 0.0,
            gain_reduction_db: 0.0,
            last_freq: 0.0,
        };
        de.update_filter();
        de
    }

    pub fn set_params(&mut self, params: DeEsserParams) {
        let freq_changed = (params.frequency - self.params.frequency).abs() > 1.0;
        self.params = params;
        if freq_changed {
            self.update_filter();
        }
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        self.update_filter();
    }

    fn update_filter(&mut self) {
        let freq = self.params.frequency.clamp(2000.0, 16000.0);
        if (freq - self.last_freq).abs() < 1.0 { return; }
        self.last_freq = freq;
        let coeffs = BiquadCoeffs::calculate(
            FilterType::BandPass,
            freq,
            2.0, // Q=2 for focused detection band
            0.0,
            self.sample_rate,
        );
        self.bp_l.set_coeffs(coeffs);
        self.bp_r.set_coeffs(coeffs);
    }

    pub fn reset(&mut self) {
        self.bp_l.reset();
        self.bp_r.reset();
        self.env = 0.0;
        self.gain_reduction_db = 0.0;
    }

    /// Get current gain reduction in dB (for metering).
    pub fn gain_reduction_db(&self) -> f32 {
        self.gain_reduction_db
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let threshold_lin = db_to_linear(self.params.threshold_db.clamp(-40.0, 0.0));
        let max_reduction_lin = db_to_linear(-self.params.range_db.clamp(0.0, 24.0));
        let attack_coeff = (-1.0 / (self.sample_rate * self.params.attack_ms.max(0.01) * 0.001)).exp();
        let release_coeff = (-1.0 / (self.sample_rate * self.params.release_ms.max(10.0) * 0.001)).exp();
        let listen = self.params.listen;

        let mut env = self.env;
        let mut peak_gr = 0.0f32;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            // Filter detection band
            let bp_l = self.bp_l.process_sample(in_l);
            let bp_r = self.bp_r.process_sample(in_r);

            // Listen mode: output only the detection band
            if listen {
                buffer.data[idx] = bp_l;
                buffer.data[idx + 1] = bp_r;
                continue;
            }

            // Envelope follower on detection band
            let det_level = bp_l.abs().max(bp_r.abs());
            if det_level > env {
                env = (1.0 - attack_coeff) * det_level + attack_coeff * env;
            } else {
                env = (1.0 - release_coeff) * det_level + release_coeff * env;
            }

            // Compute gain reduction
            let gain = if env > threshold_lin {
                // Proportional reduction: how far above threshold → more reduction
                let excess_ratio = env / threshold_lin.max(1e-10);
                let reduction = (1.0 / excess_ratio).max(max_reduction_lin);
                reduction
            } else {
                1.0
            };

            peak_gr = peak_gr.min(gain);

            buffer.data[idx] = in_l * gain;
            buffer.data[idx + 1] = in_r * gain;
        }

        self.env = env;
        // Store gain reduction in dB for metering
        if peak_gr > 0.0 && peak_gr < 1.0 {
            self.gain_reduction_db = 20.0 * peak_gr.log10();
        } else {
            self.gain_reduction_db = 0.0;
        }
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deesser_reduces_sibilance() {
        let mut de = DeEsser::new(44100.0);
        de.set_params(DeEsserParams {
            frequency: 6000.0,
            threshold_db: -30.0,
            range_db: 12.0,
            attack_ms: 0.1,
            release_ms: 20.0,
            listen: false,
        });

        // Create a signal with strong sibilance frequency
        let mut buf = AudioBuffer::new(4096, 2);
        for i in 0..4096 {
            let t = i as f32 / 44100.0;
            let sibilance = (6000.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2] = sibilance;
            buf.data[i * 2 + 1] = sibilance;
        }

        // Measure energy before
        let energy_before: f32 = buf.data.iter().map(|s| s * s).sum();

        de.process(&mut buf);

        // Measure energy after
        let energy_after: f32 = buf.data.iter().map(|s| s * s).sum();

        // Should be reduced
        assert!(
            energy_after < energy_before * 0.8,
            "DeEsser should reduce sibilance energy: before={}, after={}",
            energy_before, energy_after
        );
    }

    #[test]
    fn test_deesser_passes_low_freq() {
        let mut de = DeEsser::new(44100.0);
        de.set_params(DeEsserParams {
            frequency: 8000.0,
            threshold_db: -20.0,
            range_db: 12.0,
            ..Default::default()
        });

        // Low frequency signal (well below detection band)
        let mut buf = AudioBuffer::new(4096, 2);
        for i in 0..4096 {
            let t = i as f32 / 44100.0;
            let low = (200.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.3;
            buf.data[i * 2] = low;
            buf.data[i * 2 + 1] = low;
        }

        let energy_before: f32 = buf.data.iter().map(|s| s * s).sum();
        de.process(&mut buf);
        let energy_after: f32 = buf.data.iter().map(|s| s * s).sum();

        // Should pass through mostly unchanged
        let ratio = energy_after / energy_before.max(1e-10);
        assert!(ratio > 0.9, "DeEsser should not reduce low freq: ratio={}", ratio);
    }

    #[test]
    fn test_deesser_listen_mode() {
        let mut de = DeEsser::new(44100.0);
        de.set_params(DeEsserParams {
            frequency: 6000.0,
            listen: true,
            ..Default::default()
        });

        // Broadband signal
        let mut buf = AudioBuffer::new(2048, 2);
        for i in 0..2048 {
            let t = i as f32 / 44100.0;
            buf.data[i * 2] = (200.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.3
                + (6000.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.3;
            buf.data[i * 2 + 1] = buf.data[i * 2];
        }
        de.process(&mut buf);

        // In listen mode, only the bandpassed signal should come through
        // Just verify it produces some output
        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val > 0.01, "Listen mode should produce output");
    }
}
