// ==========================================================================
// Stereo Widener — Mid/Side based stereo width control
// ==========================================================================
// v0.0.20.669 — Phase R3B
//
// Reference: pydaw/audio/utility_fx.py StereoWidenerFx
//
// Architecture: M/S (Mid/Side) encoding → adjust M/S balance → decode.
// Width=0 → mono, Width=1 → original, Width=2 → exaggerated stereo.
// Optional bass mono (crossover filter to mono-sum below a frequency).
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::biquad::{Biquad, BiquadCoeffs, FilterType};

/// Stereo Widener parameters.
#[derive(Debug, Clone, Copy)]
pub struct StereoWidenerParams {
    /// Stereo width (0.0 = mono, 1.0 = original, 2.0 = exaggerated)
    pub width: f32,
    /// Bass mono crossover frequency in Hz (0 = off, 20–500 Hz)
    pub bass_mono_freq: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for StereoWidenerParams {
    fn default() -> Self {
        Self {
            width: 1.0,
            bass_mono_freq: 0.0, // off
            mix: 1.0,
        }
    }
}

/// M/S Stereo Widener effect.
pub struct StereoWidener {
    params: StereoWidenerParams,
    sample_rate: f32,
    // Optional LP filters for bass mono
    lp_l: Biquad,
    lp_r: Biquad,
    hp_l: Biquad,
    hp_r: Biquad,
    bass_mono_active: bool,
    last_crossover_freq: f32,
}

impl StereoWidener {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: StereoWidenerParams::default(),
            sample_rate,
            lp_l: Biquad::new(FilterType::LowPass, 200.0, 0.707, 0.0, sample_rate),
            lp_r: Biquad::new(FilterType::LowPass, 200.0, 0.707, 0.0, sample_rate),
            hp_l: Biquad::new(FilterType::HighPass, 200.0, 0.707, 0.0, sample_rate),
            hp_r: Biquad::new(FilterType::HighPass, 200.0, 0.707, 0.0, sample_rate),
            bass_mono_active: false,
            last_crossover_freq: 0.0,
        }
    }

    pub fn set_params(&mut self, params: StereoWidenerParams) {
        let freq_changed = (params.bass_mono_freq - self.params.bass_mono_freq).abs() > 1.0;
        self.params = params;
        self.bass_mono_active = params.bass_mono_freq >= 20.0;
        if freq_changed && self.bass_mono_active {
            self.update_crossover();
        }
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        if self.bass_mono_active {
            self.update_crossover();
        }
    }

    fn update_crossover(&mut self) {
        let freq = self.params.bass_mono_freq.clamp(20.0, 500.0);
        if (freq - self.last_crossover_freq).abs() < 1.0 { return; }
        self.last_crossover_freq = freq;

        let lp_coeffs = BiquadCoeffs::calculate(
            FilterType::LowPass, freq, 0.707, 0.0, self.sample_rate,
        );
        let hp_coeffs = BiquadCoeffs::calculate(
            FilterType::HighPass, freq, 0.707, 0.0, self.sample_rate,
        );
        self.lp_l.set_coeffs(lp_coeffs);
        self.lp_r.set_coeffs(lp_coeffs);
        self.hp_l.set_coeffs(hp_coeffs);
        self.hp_r.set_coeffs(hp_coeffs);
    }

    pub fn reset(&mut self) {
        self.lp_l.reset();
        self.lp_r.reset();
        self.hp_l.reset();
        self.hp_r.reset();
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        if mix < 0.001 { return; }

        let width = self.params.width.clamp(0.0, 2.0);

        // M/S coefficients: mid_gain and side_gain
        // width=0 → mid only (mono), width=1 → original, width=2 → side exaggerated
        let mid_gain = 1.0;
        let side_gain = width;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            let out_l;
            let out_r;

            if self.bass_mono_active {
                // Split into bass (mono) and highs (width-adjusted)
                let bass_l = self.lp_l.process_sample(in_l);
                let bass_r = self.lp_r.process_sample(in_r);
                let high_l = self.hp_l.process_sample(in_l);
                let high_r = self.hp_r.process_sample(in_r);

                // Bass: mono sum
                let bass_mono = (bass_l + bass_r) * 0.5;

                // Highs: M/S width processing
                let mid = (high_l + high_r) * 0.5;
                let side = (high_l - high_r) * 0.5;
                let wide_l = mid * mid_gain + side * side_gain;
                let wide_r = mid * mid_gain - side * side_gain;

                out_l = bass_mono + wide_l;
                out_r = bass_mono + wide_r;
            } else {
                // Simple M/S processing on full signal
                let mid = (in_l + in_r) * 0.5;
                let side = (in_l - in_r) * 0.5;
                out_l = mid * mid_gain + side * side_gain;
                out_r = mid * mid_gain - side * side_gain;
            }

            buffer.data[idx] = in_l * (1.0 - mix) + out_l * mix;
            buffer.data[idx + 1] = in_r * (1.0 - mix) + out_r * mix;
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
    fn test_mono_width_zero() {
        let mut w = StereoWidener::new(44100.0);
        w.set_params(StereoWidenerParams { width: 0.0, bass_mono_freq: 0.0, mix: 1.0 });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.5;     // L
            buf.data[i * 2 + 1] = -0.3; // R (different)
        }
        w.process(&mut buf);

        // Width=0 → L and R should be identical (mono)
        for i in 0..128 {
            let diff = (buf.data[i * 2] - buf.data[i * 2 + 1]).abs();
            assert!(diff < 0.01, "Width=0 should produce mono, frame {} diff={}", i, diff);
        }
    }

    #[test]
    fn test_original_width_one() {
        let mut w = StereoWidener::new(44100.0);
        w.set_params(StereoWidenerParams { width: 1.0, bass_mono_freq: 0.0, mix: 1.0 });

        let mut buf = AudioBuffer::new(128, 2);
        let orig_l = 0.5f32;
        let orig_r = -0.3f32;
        for i in 0..128 {
            buf.data[i * 2] = orig_l;
            buf.data[i * 2 + 1] = orig_r;
        }
        w.process(&mut buf);

        // Width=1 → should be approximately original
        assert!((buf.data[254] - orig_l).abs() < 0.01);
        assert!((buf.data[255] - orig_r).abs() < 0.01);
    }

    #[test]
    fn test_wider_increases_stereo() {
        let mut w = StereoWidener::new(44100.0);
        w.set_params(StereoWidenerParams { width: 2.0, bass_mono_freq: 0.0, mix: 1.0 });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = -0.3;
        }
        w.process(&mut buf);

        // Width=2 → difference between L and R should be larger than original
        let orig_diff = (0.5f32 - (-0.3f32)).abs(); // 0.8
        let new_diff = (buf.data[254] - buf.data[255]).abs();
        assert!(new_diff > orig_diff, "Width=2 should increase stereo: orig_diff={}, new_diff={}", orig_diff, new_diff);
    }

    #[test]
    fn test_bass_mono() {
        let mut w = StereoWidener::new(44100.0);
        w.set_params(StereoWidenerParams {
            width: 2.0,
            bass_mono_freq: 200.0, // Mono below 200Hz
            mix: 1.0,
        });

        // Low frequency signal with stereo content
        let mut buf = AudioBuffer::new(4096, 2);
        for i in 0..4096 {
            let t = i as f32 / 44100.0;
            buf.data[i * 2] = (100.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2 + 1] = (100.0 * 2.0 * std::f32::consts::PI * t + 1.0).sin() * 0.5;
        }
        w.process(&mut buf);

        // Low freq L and R should converge toward each other (bass mono)
        // Check the last portion (after filter settles)
        let mut diff_sum = 0.0f32;
        for i in 2048..4096 {
            diff_sum += (buf.data[i * 2] - buf.data[i * 2 + 1]).abs();
        }
        let avg_diff = diff_sum / 2048.0;
        assert!(avg_diff < 0.2, "Bass mono should reduce low freq stereo diff, avg={}", avg_diff);
    }
}
