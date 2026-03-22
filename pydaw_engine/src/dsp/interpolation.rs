// ==========================================================================
// DC Blocker — Removes DC offset from audio signal
// ==========================================================================
// v0.0.20.667 — Phase R1C
//
// High-pass filter at ~5Hz. Essential after distortion, waveshaping,
// or any nonlinear processing that can introduce DC offset.
//
// Transfer function: H(z) = (1 - z^-1) / (1 - R * z^-1)
// where R = 1 - (2*PI*fc / sr), fc ≈ 5Hz
// ==========================================================================

/// DC offset removal filter.
pub struct DcBlocker {
    x_prev: f32,
    y_prev: f32,
    r: f32, // pole coefficient (close to 1.0)
}

impl DcBlocker {
    /// Create a new DC blocker.
    ///
    /// - `cutoff_hz`: High-pass cutoff frequency (default 5.0 Hz)
    /// - `sample_rate`: Audio sample rate
    pub fn new(cutoff_hz: f32, sample_rate: f32) -> Self {
        let r = 1.0 - (2.0 * std::f32::consts::PI * cutoff_hz / sample_rate);
        Self {
            x_prev: 0.0,
            y_prev: 0.0,
            r: r.clamp(0.9, 0.9999),
        }
    }

    /// Default DC blocker at 5Hz.
    pub fn default_at(sample_rate: f32) -> Self {
        Self::new(5.0, sample_rate)
    }

    /// Process one sample.
    #[inline]
    pub fn process(&mut self, input: f32) -> f32 {
        self.y_prev = input - self.x_prev + self.r * self.y_prev;
        self.x_prev = input;
        self.y_prev
    }

    /// Reset state.
    pub fn reset(&mut self) {
        self.x_prev = 0.0;
        self.y_prev = 0.0;
    }
}

// ==========================================================================
// Stereo Pan — Equal-power pan law
// ==========================================================================

use std::f32::consts::PI;

/// Calculate equal-power pan gains.
///
/// - `pan`: -1.0 (full left) to 1.0 (full right), 0.0 = center
/// - Returns: (left_gain, right_gain)
///
/// Uses cosine/sine pan law: constant power across the stereo field.
#[inline]
pub fn equal_power_pan(pan: f32) -> (f32, f32) {
    let pan = pan.clamp(-1.0, 1.0);
    let angle = (pan + 1.0) * 0.25 * PI; // 0 to PI/2
    (angle.cos(), angle.sin())
}

/// Calculate linear pan gains (simpler, less accurate).
///
/// - `pan`: -1.0 (full left) to 1.0 (full right)
/// - Returns: (left_gain, right_gain)
#[inline]
pub fn linear_pan(pan: f32) -> (f32, f32) {
    let pan = pan.clamp(-1.0, 1.0);
    let right = (pan + 1.0) * 0.5;
    let left = 1.0 - right;
    (left, right)
}

/// Apply equal-power pan to a stereo buffer in-place.
///
/// `buffer`: interleaved stereo [L0, R0, L1, R1, ...]
/// `pan`: -1.0 to 1.0
/// `frames`: number of frames
#[inline]
pub fn apply_pan_to_buffer(buffer: &mut [f32], pan: f32, frames: usize) {
    let (gl, gr) = equal_power_pan(pan);
    for frame in 0..frames {
        let idx = frame * 2;
        if idx + 1 < buffer.len() {
            buffer[idx] *= gl;
            buffer[idx + 1] *= gr;
        }
    }
}

// ==========================================================================
// Interpolation — For sample-rate conversion and pitch shifting
// ==========================================================================

/// Linear interpolation between two samples.
#[inline]
pub fn interpolate_linear(y0: f32, y1: f32, frac: f32) -> f32 {
    y0 + (y1 - y0) * frac
}

/// Cubic Hermite interpolation (4-point).
///
/// Higher quality than linear — less aliasing for pitch shifting.
/// Requires 4 consecutive sample values: y[-1], y[0], y[1], y[2]
/// and a fractional position `frac` between y[0] and y[1].
#[inline]
pub fn interpolate_cubic(y_m1: f32, y0: f32, y1: f32, y2: f32, frac: f32) -> f32 {
    let c0 = y0;
    let c1 = 0.5 * (y1 - y_m1);
    let c2 = y_m1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2;
    let c3 = 0.5 * (y2 - y_m1) + 1.5 * (y0 - y1);
    ((c3 * frac + c2) * frac + c1) * frac + c0
}

/// Lagrange 4-point interpolation.
///
/// Even higher quality than cubic Hermite, slightly more CPU.
#[inline]
pub fn interpolate_lagrange4(y_m1: f32, y0: f32, y1: f32, y2: f32, frac: f32) -> f32 {
    let d = frac;
    let d2 = d * d;
    let d3 = d2 * d;

    let c0 = y0;
    let c1 = y1 - y_m1 * (1.0 / 3.0) - y0 * 0.5 - y2 * (1.0 / 6.0);
    let c2 = 0.5 * (y_m1 + y1) - y0;
    let c3 = (1.0 / 6.0) * (y2 - y_m1) + 0.5 * (y0 - y1);

    c0 + c1 * d + c2 * d2 + c3 * d3
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dc_blocker_removes_dc() {
        let mut dc = DcBlocker::default_at(44100.0);
        // Feed DC offset of 0.5
        let mut output = 0.0;
        for _ in 0..44100 {
            output = dc.process(0.5);
        }
        // After 1 second, DC should be nearly removed
        assert!(output.abs() < 0.01, "DC output after 1s = {} (expected ~0)", output);
    }

    #[test]
    fn test_dc_blocker_passes_signal() {
        let mut dc = DcBlocker::default_at(44100.0);
        // Feed a 1kHz sine — should pass through nearly unattenuated
        let freq = 1000.0;
        let sr = 44100.0;
        let mut peak = 0.0f32;
        for i in 0..44100 {
            let input = (2.0 * PI * freq * i as f32 / sr).sin();
            let output = dc.process(input);
            if i > 4410 { // skip transient
                peak = peak.max(output.abs());
            }
        }
        assert!(peak > 0.95, "1kHz through DC blocker peak = {} (expected > 0.95)", peak);
    }

    #[test]
    fn test_equal_power_pan() {
        let (l, r) = equal_power_pan(0.0); // center
        assert!((l - r).abs() < 0.01, "Center pan should be equal: L={}, R={}", l, r);
        // Power should be ~1.0: l^2 + r^2 ≈ 1.0
        assert!((l * l + r * r - 1.0).abs() < 0.01);

        let (l, r) = equal_power_pan(-1.0); // full left
        assert!(l > 0.99 && r < 0.01);

        let (l, r) = equal_power_pan(1.0); // full right
        assert!(l < 0.01 && r > 0.99);
    }

    #[test]
    fn test_interpolation_linear() {
        assert!((interpolate_linear(0.0, 1.0, 0.5) - 0.5).abs() < 1e-6);
        assert!((interpolate_linear(0.0, 1.0, 0.0) - 0.0).abs() < 1e-6);
        assert!((interpolate_linear(0.0, 1.0, 1.0) - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_interpolation_cubic_at_endpoints() {
        // At frac=0 should return y0
        let val = interpolate_cubic(0.0, 1.0, 2.0, 3.0, 0.0);
        assert!((val - 1.0).abs() < 1e-6);
    }
}
