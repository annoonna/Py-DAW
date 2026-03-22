// ==========================================================================
// Spectrum Analyzer — FFT analysis with peak hold (pass-through)
// ==========================================================================
// v0.0.20.669 — Phase R3B
//
// Reference: pydaw/audio/utility_fx.py SpectrumAnalyzerFx
//
// This is a PASS-THROUGH effect — it does NOT modify audio.
// It accumulates samples, computes magnitude spectrum via radix-2 FFT,
// and stores results for GUI polling (~30Hz).
//
// Includes: Hanning window, magnitude in dB, spectral smoothing, peak hold.
// Uses a simple in-place radix-2 Cooley-Tukey FFT (no external crate).
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use std::f32::consts::PI;

/// Maximum FFT size.
const MAX_FFT_SIZE: usize = 4096;

/// Spectrum Analyzer parameters.
#[derive(Debug, Clone, Copy)]
pub struct SpectrumAnalyzerParams {
    /// FFT window size (512, 1024, 2048, 4096)
    pub fft_size: usize,
    /// Peak hold decay time in seconds (0 – 10)
    pub peak_hold_s: f32,
    /// Spectral smoothing factor (0.0 – 0.95)
    pub smoothing: f32,
}

impl Default for SpectrumAnalyzerParams {
    fn default() -> Self {
        Self {
            fft_size: 2048,
            peak_hold_s: 2.0,
            smoothing: 0.7,
        }
    }
}

/// Spectrum data for GUI retrieval.
#[derive(Debug, Clone)]
pub struct SpectrumData {
    /// Magnitude in dB per frequency bin
    pub magnitudes: Vec<f32>,
    /// Peak hold in dB per frequency bin
    pub peaks: Vec<f32>,
    /// FFT size used
    pub fft_size: usize,
    /// Sample rate
    pub sample_rate: f32,
    /// Number of frequency bins
    pub num_bins: usize,
}

/// FFT-based Spectrum Analyzer (pass-through).
pub struct SpectrumAnalyzer {
    params: SpectrumAnalyzerParams,
    sample_rate: f32,
    // Accumulation buffer
    acc_buf: Vec<f32>,
    acc_pos: usize,
    // Hanning window (precomputed)
    window: Vec<f32>,
    // Spectrum data
    magnitude_db: Vec<f32>,
    peak_db: Vec<f32>,
    smoothed_db: Vec<f32>,
    // FFT scratch buffers (pre-allocated)
    fft_real: Vec<f32>,
    fft_imag: Vec<f32>,
}

impl SpectrumAnalyzer {
    pub fn new(sample_rate: f32) -> Self {
        let fft_size = 2048;
        let num_bins = fft_size / 2 + 1;
        let mut sa = Self {
            params: SpectrumAnalyzerParams::default(),
            sample_rate,
            acc_buf: vec![0.0; fft_size],
            acc_pos: 0,
            window: vec![0.0; fft_size],
            magnitude_db: vec![-120.0; num_bins],
            peak_db: vec![-120.0; num_bins],
            smoothed_db: vec![-120.0; num_bins],
            fft_real: vec![0.0; fft_size],
            fft_imag: vec![0.0; fft_size],
        };
        sa.build_window(fft_size);
        sa
    }

    pub fn set_params(&mut self, params: SpectrumAnalyzerParams) {
        let fft_size = match params.fft_size {
            512 | 1024 | 2048 | 4096 => params.fft_size,
            _ => 2048,
        };
        if fft_size != self.params.fft_size {
            self.resize(fft_size);
        }
        self.params = SpectrumAnalyzerParams { fft_size, ..params };
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    fn resize(&mut self, fft_size: usize) {
        let num_bins = fft_size / 2 + 1;
        self.acc_buf.resize(fft_size, 0.0);
        self.acc_buf.fill(0.0);
        self.acc_pos = 0;
        self.fft_real.resize(fft_size, 0.0);
        self.fft_imag.resize(fft_size, 0.0);
        self.magnitude_db.resize(num_bins, -120.0);
        self.peak_db.resize(num_bins, -120.0);
        self.smoothed_db.resize(num_bins, -120.0);
        self.build_window(fft_size);
    }

    fn build_window(&mut self, fft_size: usize) {
        self.window.resize(fft_size, 0.0);
        for i in 0..fft_size {
            self.window[i] = 0.5 * (1.0 - (2.0 * PI * i as f32 / fft_size as f32).cos());
        }
    }

    pub fn reset(&mut self) {
        self.acc_buf.fill(0.0);
        self.acc_pos = 0;
        let _num_bins = self.params.fft_size / 2 + 1;
        self.magnitude_db.iter_mut().for_each(|v| *v = -120.0);
        self.peak_db.iter_mut().for_each(|v| *v = -120.0);
        self.smoothed_db.iter_mut().for_each(|v| *v = -120.0);
    }

    /// Get current spectrum data for GUI display.
    pub fn get_spectrum_data(&self) -> SpectrumData {
        let fft_size = self.params.fft_size;
        let num_bins = fft_size / 2 + 1;
        SpectrumData {
            magnitudes: self.magnitude_db[..num_bins].to_vec(),
            peaks: self.peak_db[..num_bins].to_vec(),
            fft_size,
            sample_rate: self.sample_rate,
            num_bins,
        }
    }

    /// Process stereo buffer — PASS-THROUGH (no audio modification). **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let fft_size = self.params.fft_size;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            // Accumulate mono-sum
            let mono = (buffer.data[idx] + buffer.data[idx + 1]) * 0.5;
            self.acc_buf[self.acc_pos] = mono;
            self.acc_pos += 1;

            // When buffer full, compute FFT
            if self.acc_pos >= fft_size {
                self.acc_pos = 0;
                self.compute_fft(frames);
            }
        }
        // Audio buffer is NOT modified — this is a pass-through effect
    }

    fn compute_fft(&mut self, block_frames: usize) {
        let fft_size = self.params.fft_size;
        let num_bins = fft_size / 2 + 1;
        let smoothing = self.params.smoothing.clamp(0.0, 0.95);
        let peak_hold_s = self.params.peak_hold_s.max(0.0);

        // Apply window and copy to FFT buffers
        for i in 0..fft_size {
            self.fft_real[i] = self.acc_buf[i] * self.window[i];
            self.fft_imag[i] = 0.0;
        }

        // In-place radix-2 FFT
        Self::fft_in_place(&mut self.fft_real, &mut self.fft_imag, fft_size);

        // Compute magnitudes and update spectrum data
        let decay_per_block = if peak_hold_s > 0.01 && block_frames > 0 {
            let blocks_per_sec = self.sample_rate / block_frames.max(1) as f32;
            60.0 / (peak_hold_s * blocks_per_sec).max(1.0)
        } else {
            120.0 // instant decay
        };

        for i in 0..num_bins.min(self.magnitude_db.len()) {
            let re = self.fft_real[i];
            let im = self.fft_imag[i];
            let mag = (re * re + im * im).sqrt() / fft_size as f32;
            let db = if mag > 1e-10 { 20.0 * mag.log10() } else { -120.0 };

            // Smoothing
            self.smoothed_db[i] = smoothing * self.smoothed_db[i] + (1.0 - smoothing) * db;
            self.magnitude_db[i] = self.smoothed_db[i];

            // Peak hold
            if db > self.peak_db[i] {
                self.peak_db[i] = db;
            } else {
                self.peak_db[i] = (self.peak_db[i] - decay_per_block).max(-120.0);
            }
        }
    }

    /// In-place radix-2 Cooley-Tukey FFT.
    ///
    /// `real` and `imag` are both of length `n` (must be power of 2).
    fn fft_in_place(real: &mut [f32], imag: &mut [f32], n: usize) {
        // Bit-reversal permutation
        let mut j = 0usize;
        for i in 0..n {
            if i < j {
                real.swap(i, j);
                imag.swap(i, j);
            }
            let mut m = n >> 1;
            while m >= 1 && j >= m {
                j -= m;
                m >>= 1;
            }
            j += m;
        }

        // Butterfly stages
        let mut stage_len = 2;
        while stage_len <= n {
            let half = stage_len / 2;
            let angle_step = -2.0 * PI / stage_len as f32;

            let mut k = 0;
            while k < n {
                let mut w_re = 1.0f32;
                let mut w_im = 0.0f32;
                let cos_step = (angle_step).cos();
                let sin_step = (angle_step).sin();

                for j_inner in 0..half {
                    let even = k + j_inner;
                    let odd = even + half;

                    let tre = w_re * real[odd] - w_im * imag[odd];
                    let tim = w_re * imag[odd] + w_im * real[odd];

                    real[odd] = real[even] - tre;
                    imag[odd] = imag[even] - tim;
                    real[even] += tre;
                    imag[even] += tim;

                    // Rotate twiddle factor
                    let new_w_re = w_re * cos_step - w_im * sin_step;
                    let new_w_im = w_re * sin_step + w_im * cos_step;
                    w_re = new_w_re;
                    w_im = new_w_im;
                }
                k += stage_len;
            }
            stage_len <<= 1;
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
        let mut sa = SpectrumAnalyzer::new(44100.0);

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        let orig_l = buf.data[254];
        let orig_r = buf.data[255];
        sa.process(&mut buf);

        // Must not modify audio
        assert!((buf.data[254] - orig_l).abs() < 1e-6, "Analyzer must not modify audio");
        assert!((buf.data[255] - orig_r).abs() < 1e-6);
    }

    #[test]
    fn test_fft_detects_frequency() {
        let sr = 44100.0;
        let mut sa = SpectrumAnalyzer::new(sr);
        sa.set_params(SpectrumAnalyzerParams {
            fft_size: 2048,
            peak_hold_s: 1.0,
            smoothing: 0.0, // no smoothing for clear test
        });

        // Generate a 1kHz tone for enough samples to trigger FFT
        let mut buf = AudioBuffer::new(2048, 2);
        for i in 0..2048 {
            let t = i as f32 / sr;
            let s = (1000.0 * 2.0 * PI * t).sin() * 0.8;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        sa.process(&mut buf);

        let data = sa.get_spectrum_data();
        assert_eq!(data.num_bins, 1025);
        assert_eq!(data.fft_size, 2048);

        // Find the bin with highest magnitude
        let mut max_bin = 0;
        let mut max_db = -200.0f32;
        for (i, &db) in data.magnitudes.iter().enumerate() {
            if db > max_db {
                max_db = db;
                max_bin = i;
            }
        }

        // Expected bin for 1kHz: bin = freq * fft_size / sr = 1000 * 2048 / 44100 ≈ 46
        let expected_bin = (1000.0 * 2048.0 / sr).round() as usize;
        assert!(
            (max_bin as i32 - expected_bin as i32).unsigned_abs() <= 2,
            "Peak should be near bin {}, got bin {} (max_db={})",
            expected_bin, max_bin, max_db
        );
    }

    #[test]
    fn test_fft_basic_correctness() {
        // Test FFT with a known signal: DC + 1 cycle sine
        let n = 8;
        let mut real = vec![0.0f32; n];
        let mut imag = vec![0.0f32; n];

        // 1 cycle of cosine in 8 samples → should peak at bin 1
        for i in 0..n {
            real[i] = (2.0 * PI * i as f32 / n as f32).cos();
        }

        SpectrumAnalyzer::fft_in_place(&mut real, &mut imag, n);

        // Bin 1 should have magnitude n/2 = 4 for a cosine
        let mag_bin1 = (real[1] * real[1] + imag[1] * imag[1]).sqrt();
        assert!(
            (mag_bin1 - 4.0).abs() < 0.1,
            "FFT bin 1 should be ~4.0 for cosine, got {}",
            mag_bin1
        );
    }

    #[test]
    fn test_resize_fft() {
        let mut sa = SpectrumAnalyzer::new(44100.0);
        sa.set_params(SpectrumAnalyzerParams {
            fft_size: 4096,
            ..Default::default()
        });
        let data = sa.get_spectrum_data();
        assert_eq!(data.fft_size, 4096);
        assert_eq!(data.num_bins, 2049);
    }
}
