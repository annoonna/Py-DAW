// ==========================================================================
// Parameter Smoother — One-pole exponential smoothing
// ==========================================================================
// v0.0.20.667 — Phase R1C
//
// Prevents "zipper noise" when automating parameters (volume, pan, freq).
// One-pole filter: output = target + (output - target) * coeff
// ==========================================================================

/// One-pole parameter smoother for audio-rate parameter interpolation.
///
/// When a parameter changes (e.g., fader moved), the output glides
/// smoothly to the target over `smooth_time_ms` milliseconds.
/// This eliminates clicks/zipper noise from sudden value changes.
pub struct ParamSmoother {
    current: f32,
    target: f32,
    coeff: f32,
    sample_rate: f32,
    smooth_ms: f32,
}

impl ParamSmoother {
    /// Create a new smoother.
    ///
    /// - `initial`: Starting value
    /// - `smooth_ms`: Smoothing time in milliseconds (5–50ms typical)
    /// - `sample_rate`: Audio sample rate
    pub fn new(initial: f32, smooth_ms: f32, sample_rate: f32) -> Self {
        let mut s = Self {
            current: initial,
            target: initial,
            coeff: 0.0,
            sample_rate,
            smooth_ms,
        };
        s.recalc_coeff();
        s
    }

    fn recalc_coeff(&mut self) {
        let samples = (self.smooth_ms * 0.001 * self.sample_rate).max(1.0);
        self.coeff = (-1.0 / samples).exp();
    }

    /// Set a new target value. The output will glide towards it.
    #[inline]
    pub fn set_target(&mut self, target: f32) {
        self.target = target;
    }

    /// Set the value immediately (no smoothing — use for initialization).
    pub fn set_immediate(&mut self, value: f32) {
        self.current = value;
        self.target = value;
    }

    /// Set smoothing time in milliseconds.
    pub fn set_smooth_time(&mut self, ms: f32) {
        self.smooth_ms = ms.max(0.1);
        self.recalc_coeff();
    }

    /// Set sample rate.
    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        self.sample_rate = sample_rate;
        self.recalc_coeff();
    }

    /// Process one sample — returns the smoothed value.
    ///
    /// **AUDIO THREAD** — inline, zero-alloc.
    #[inline]
    pub fn process(&mut self) -> f32 {
        self.current = self.target + (self.current - self.target) * self.coeff;
        self.current
    }

    /// Check if the smoother has reached its target (within epsilon).
    #[inline]
    pub fn is_settled(&self) -> bool {
        (self.current - self.target).abs() < 1e-6
    }

    /// Get the current smoothed value without advancing.
    #[inline]
    pub fn current(&self) -> f32 {
        self.current
    }

    /// Get the target value.
    #[inline]
    pub fn target(&self) -> f32 {
        self.target
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_immediate() {
        let mut s = ParamSmoother::new(0.0, 10.0, 44100.0);
        s.set_immediate(1.0);
        assert!((s.process() - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_converges() {
        let mut s = ParamSmoother::new(0.0, 10.0, 44100.0);
        s.set_target(1.0);
        // After enough samples, should be close to target
        for _ in 0..4000 {
            s.process();
        }
        assert!(
            (s.current() - 1.0).abs() < 0.02,
            "After 4000 samples, should be near 1.0, got {}",
            s.current()
        );
    }

    #[test]
    fn test_settled() {
        let mut s = ParamSmoother::new(1.0, 5.0, 44100.0);
        s.set_target(1.0);
        s.process();
        assert!(s.is_settled());
    }
}
