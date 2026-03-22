// ==========================================================================
// Biquad Filter — Direct Form II Transposed
// ==========================================================================
// v0.0.20.667 — Phase R1A
//
// The workhorse filter for all EQ, compressor sidechains, crossovers, etc.
// Implements all standard filter types with coefficient calculation from
// the Audio EQ Cookbook (Robert Bristow-Johnson).
//
// Rules:
//   ✅ Zero heap allocations in process()
//   ✅ All state in fixed-size struct
//   ✅ #[inline] on hot-path functions
//   ❌ NO allocations, locks, or panics in audio thread
// ==========================================================================

use std::f32::consts::PI;

/// Filter type selector.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FilterType {
    LowPass,
    HighPass,
    BandPass,
    Notch,
    AllPass,
    PeakEQ,
    LowShelf,
    HighShelf,
}

/// Biquad filter coefficients (normalized: a0 = 1.0).
#[derive(Debug, Clone, Copy)]
pub struct BiquadCoeffs {
    pub b0: f32,
    pub b1: f32,
    pub b2: f32,
    pub a1: f32,
    pub a2: f32,
}

impl Default for BiquadCoeffs {
    fn default() -> Self {
        // Passthrough (unity gain, no filtering)
        Self {
            b0: 1.0,
            b1: 0.0,
            b2: 0.0,
            a1: 0.0,
            a2: 0.0,
        }
    }
}

impl BiquadCoeffs {
    /// Calculate coefficients for the given filter type.
    ///
    /// Based on the Audio EQ Cookbook by Robert Bristow-Johnson.
    ///
    /// - `freq`: Center/cutoff frequency in Hz
    /// - `q`: Quality factor (0.1 – 30.0, typical 0.707 for Butterworth)
    /// - `gain_db`: Gain in dB (only used for PeakEQ, LowShelf, HighShelf)
    /// - `sample_rate`: Sample rate in Hz
    pub fn calculate(
        filter_type: FilterType,
        freq: f32,
        q: f32,
        gain_db: f32,
        sample_rate: f32,
    ) -> Self {
        // Clamp frequency to valid range (avoid NaN from bad input)
        let freq = freq.clamp(1.0, sample_rate * 0.499);
        let q = q.max(0.01);

        let w0 = 2.0 * PI * freq / sample_rate;
        let cos_w0 = w0.cos();
        let sin_w0 = w0.sin();
        let alpha = sin_w0 / (2.0 * q);

        let a = if gain_db != 0.0 {
            10.0f32.powf(gain_db / 40.0) // sqrt of linear gain
        } else {
            1.0
        };

        let (b0, b1, b2, a0, a1, a2) = match filter_type {
            FilterType::LowPass => {
                let b1 = 1.0 - cos_w0;
                let b0 = b1 / 2.0;
                let b2 = b0;
                let a0 = 1.0 + alpha;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::HighPass => {
                let b1 = -(1.0 + cos_w0);
                let b0 = -b1 / 2.0;
                let b2 = b0;
                let a0 = 1.0 + alpha;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::BandPass => {
                let b0 = alpha;
                let b1 = 0.0;
                let b2 = -alpha;
                let a0 = 1.0 + alpha;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::Notch => {
                let b0 = 1.0;
                let b1 = -2.0 * cos_w0;
                let b2 = 1.0;
                let a0 = 1.0 + alpha;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::AllPass => {
                let b0 = 1.0 - alpha;
                let b1 = -2.0 * cos_w0;
                let b2 = 1.0 + alpha;
                let a0 = 1.0 + alpha;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::PeakEQ => {
                let b0 = 1.0 + alpha * a;
                let b1 = -2.0 * cos_w0;
                let b2 = 1.0 - alpha * a;
                let a0 = 1.0 + alpha / a;
                let a1 = -2.0 * cos_w0;
                let a2 = 1.0 - alpha / a;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::LowShelf => {
                let two_sqrt_a_alpha = 2.0 * a.sqrt() * alpha;
                let b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha);
                let b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0);
                let b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha);
                let a0 = (a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha;
                let a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0);
                let a2 = (a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha;
                (b0, b1, b2, a0, a1, a2)
            }

            FilterType::HighShelf => {
                let two_sqrt_a_alpha = 2.0 * a.sqrt() * alpha;
                let b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha);
                let b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0);
                let b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha);
                let a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha;
                let a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0);
                let a2 = (a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha;
                (b0, b1, b2, a0, a1, a2)
            }
        };

        // Normalize by a0
        let inv_a0 = 1.0 / a0;
        Self {
            b0: b0 * inv_a0,
            b1: b1 * inv_a0,
            b2: b2 * inv_a0,
            a1: a1 * inv_a0,
            a2: a2 * inv_a0,
        }
    }
}

/// A single-channel Biquad filter (Direct Form II Transposed).
///
/// DF2T has the best numerical properties for floating-point audio:
/// fewer rounding errors than DF1 or DF2 at low frequencies.
#[derive(Debug, Clone)]
pub struct Biquad {
    coeffs: BiquadCoeffs,
    /// State variables (z^-1 delay elements).
    z1: f32,
    z2: f32,
}

impl Default for Biquad {
    fn default() -> Self {
        Self {
            coeffs: BiquadCoeffs::default(),
            z1: 0.0,
            z2: 0.0,
        }
    }
}

impl Biquad {
    /// Create a new biquad filter with the given type and parameters.
    pub fn new(filter_type: FilterType, freq: f32, q: f32, gain_db: f32, sample_rate: f32) -> Self {
        Self {
            coeffs: BiquadCoeffs::calculate(filter_type, freq, q, gain_db, sample_rate),
            z1: 0.0,
            z2: 0.0,
        }
    }

    /// Create a passthrough (unity gain) filter.
    pub fn passthrough() -> Self {
        Self::default()
    }

    /// Update filter parameters. Call from the parameter update thread,
    /// NOT from the audio callback (coefficients are not atomic).
    /// For zipper-free updates, use a parameter smoother on freq/q/gain
    /// and call this at a reduced rate (e.g., every 32 samples).
    pub fn set_params(
        &mut self,
        filter_type: FilterType,
        freq: f32,
        q: f32,
        gain_db: f32,
        sample_rate: f32,
    ) {
        self.coeffs = BiquadCoeffs::calculate(filter_type, freq, q, gain_db, sample_rate);
    }

    /// Set coefficients directly (for pre-computed coefficient sets).
    pub fn set_coeffs(&mut self, coeffs: BiquadCoeffs) {
        self.coeffs = coeffs;
    }

    /// Reset filter state (clear delay elements). Call on note-on or
    /// when the filter is re-initialized to prevent clicks.
    pub fn reset(&mut self) {
        self.z1 = 0.0;
        self.z2 = 0.0;
    }

    /// Process a single sample. **AUDIO THREAD** — inline, zero-alloc.
    ///
    /// Direct Form II Transposed:
    ///   y[n] = b0*x[n] + z1
    ///   z1   = b1*x[n] - a1*y[n] + z2
    ///   z2   = b2*x[n] - a2*y[n]
    #[inline]
    pub fn process_sample(&mut self, input: f32) -> f32 {
        let output = self.coeffs.b0 * input + self.z1;
        self.z1 = self.coeffs.b1 * input - self.coeffs.a1 * output + self.z2;
        self.z2 = self.coeffs.b2 * input - self.coeffs.a2 * output;
        output
    }

    /// Process a block of interleaved samples for one channel.
    ///
    /// `buffer`: interleaved audio data (e.g., [L0, R0, L1, R1, ...])
    /// `channel`: which channel to process (0 = left, 1 = right)
    /// `channels`: total number of channels (stride)
    /// `frames`: number of frames to process
    ///
    /// Processes in-place. **AUDIO THREAD** — zero-alloc.
    #[inline]
    pub fn process_block(
        &mut self,
        buffer: &mut [f32],
        channel: usize,
        channels: usize,
        frames: usize,
    ) {
        for frame in 0..frames {
            let idx = frame * channels + channel;
            if idx < buffer.len() {
                buffer[idx] = self.process_sample(buffer[idx]);
            }
        }
    }
}

/// Stereo biquad filter (two independent channels, same coefficients).
#[derive(Debug, Clone)]
pub struct StereoBiquad {
    left: Biquad,
    right: Biquad,
}

impl StereoBiquad {
    pub fn new(filter_type: FilterType, freq: f32, q: f32, gain_db: f32, sample_rate: f32) -> Self {
        let coeffs = BiquadCoeffs::calculate(filter_type, freq, q, gain_db, sample_rate);
        Self {
            left: Biquad { coeffs, z1: 0.0, z2: 0.0 },
            right: Biquad { coeffs, z1: 0.0, z2: 0.0 },
        }
    }

    pub fn set_params(
        &mut self,
        filter_type: FilterType,
        freq: f32,
        q: f32,
        gain_db: f32,
        sample_rate: f32,
    ) {
        let coeffs = BiquadCoeffs::calculate(filter_type, freq, q, gain_db, sample_rate);
        self.left.coeffs = coeffs;
        self.right.coeffs = coeffs;
    }

    pub fn reset(&mut self) {
        self.left.reset();
        self.right.reset();
    }

    /// Process interleaved stereo buffer in-place.
    #[inline]
    pub fn process_stereo(&mut self, buffer: &mut [f32], frames: usize) {
        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 < buffer.len() {
                buffer[idx] = self.left.process_sample(buffer[idx]);
                buffer[idx + 1] = self.right.process_sample(buffer[idx + 1]);
            }
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
    fn test_passthrough() {
        let mut f = Biquad::passthrough();
        assert!((f.process_sample(1.0) - 1.0).abs() < 1e-6);
        assert!((f.process_sample(0.5) - 0.5).abs() < 1e-6);
        assert!((f.process_sample(-0.3) - (-0.3)).abs() < 1e-6);
    }

    #[test]
    fn test_lowpass_attenuates_high_freq() {
        // 1kHz lowpass at 44100Hz — a 10kHz sine should be attenuated
        let mut f = Biquad::new(FilterType::LowPass, 1000.0, 0.707, 0.0, 44100.0);
        let sr = 44100.0;
        let freq = 10000.0;

        // Run 1000 samples of 10kHz sine through the filter
        let mut peak_out: f32 = 0.0;
        for i in 0..1000 {
            let input = (2.0 * PI * freq * i as f32 / sr).sin();
            let output = f.process_sample(input);
            if i > 100 {
                // Skip transient
                peak_out = peak_out.max(output.abs());
            }
        }
        // 10kHz should be significantly attenuated by 1kHz LP
        assert!(peak_out < 0.15, "10kHz peak through 1kHz LP = {} (expected < 0.15)", peak_out);
    }

    #[test]
    fn test_lowpass_passes_low_freq() {
        // 1kHz lowpass — a 100Hz sine should pass through nearly unattenuated
        let mut f = Biquad::new(FilterType::LowPass, 1000.0, 0.707, 0.0, 44100.0);
        let sr = 44100.0;
        let freq = 100.0;

        let mut peak_out: f32 = 0.0;
        for i in 0..4000 {
            let input = (2.0 * PI * freq * i as f32 / sr).sin();
            let output = f.process_sample(input);
            if i > 500 {
                peak_out = peak_out.max(output.abs());
            }
        }
        // 100Hz should pass through a 1kHz LP at roughly unity
        assert!(peak_out > 0.9, "100Hz peak through 1kHz LP = {} (expected > 0.9)", peak_out);
    }

    #[test]
    fn test_highpass_attenuates_low_freq() {
        let mut f = Biquad::new(FilterType::HighPass, 5000.0, 0.707, 0.0, 44100.0);
        let sr = 44100.0;
        let freq = 100.0;

        let mut peak_out: f32 = 0.0;
        for i in 0..4000 {
            let input = (2.0 * PI * freq * i as f32 / sr).sin();
            let output = f.process_sample(input);
            if i > 500 {
                peak_out = peak_out.max(output.abs());
            }
        }
        assert!(peak_out < 0.05, "100Hz through 5kHz HP = {} (expected < 0.05)", peak_out);
    }

    #[test]
    fn test_peak_eq_boost() {
        // +12dB bell at 1kHz — 1kHz sine should be louder
        let mut f = Biquad::new(FilterType::PeakEQ, 1000.0, 1.0, 12.0, 44100.0);
        let sr = 44100.0;
        let freq = 1000.0;

        let mut peak_out: f32 = 0.0;
        for i in 0..4000 {
            let input = (2.0 * PI * freq * i as f32 / sr).sin() * 0.25;
            let output = f.process_sample(input);
            if i > 500 {
                peak_out = peak_out.max(output.abs());
            }
        }
        // +12dB ≈ 4x linear, input peak = 0.25 → output should be ~1.0
        assert!(peak_out > 0.8, "1kHz through +12dB EQ at 1kHz = {} (expected > 0.8)", peak_out);
    }

    #[test]
    fn test_stereo_biquad() {
        let mut f = StereoBiquad::new(FilterType::LowPass, 1000.0, 0.707, 0.0, 44100.0);
        let mut buffer = vec![0.5, -0.3, 0.7, 0.1]; // 2 frames, stereo
        f.process_stereo(&mut buffer, 2);
        // Just verify it doesn't crash and produces different output
        assert!((buffer[0] - 0.5).abs() > 0.001 || (buffer[2] - 0.7).abs() > 0.001);
    }

    #[test]
    fn test_reset_clears_state() {
        let mut f = Biquad::new(FilterType::LowPass, 1000.0, 0.707, 0.0, 44100.0);
        // Process some samples
        for _ in 0..100 {
            f.process_sample(1.0);
        }
        assert!(f.z1.abs() > 0.0 || f.z2.abs() > 0.0);
        f.reset();
        assert_eq!(f.z1, 0.0);
        assert_eq!(f.z2, 0.0);
    }
}
