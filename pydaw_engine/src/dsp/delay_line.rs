// ==========================================================================
// Delay Line — Pre-allocated ring buffer with fractional delay
// ==========================================================================
// v0.0.20.667 — Phase R1B
//
// Used by: Reverb (comb filters), Delay FX, Chorus, Flanger, Phaser
// All memory pre-allocated at creation — zero alloc in process().
// ==========================================================================

/// Fixed-capacity delay line with linear-interpolated fractional reads.
///
/// Memory is pre-allocated to `max_delay_samples` at construction.
/// All operations are O(1) and allocation-free.
pub struct DelayLine {
    buffer: Vec<f32>,
    write_pos: usize,
    mask: usize,
}

impl DelayLine {
    /// Create a new delay line. Capacity is rounded up to next power of 2.
    pub fn new(max_delay_samples: usize) -> Self {
        let capacity = max_delay_samples.max(4).next_power_of_two();
        Self {
            buffer: vec![0.0; capacity],
            write_pos: 0,
            mask: capacity - 1,
        }
    }

    /// Write a sample into the delay line and advance the write pointer.
    #[inline]
    pub fn write(&mut self, sample: f32) {
        self.buffer[self.write_pos & self.mask] = sample;
        self.write_pos = self.write_pos.wrapping_add(1);
    }

    /// Read a sample from the delay line at an integer delay (in samples).
    /// `delay` = 0 means the most recently written sample.
    #[inline]
    pub fn read(&self, delay: usize) -> f32 {
        let idx = self.write_pos.wrapping_sub(1).wrapping_sub(delay) & self.mask;
        self.buffer[idx]
    }

    /// Read with fractional delay using linear interpolation.
    ///
    /// `delay_samples` can be fractional (e.g., 10.3 samples).
    /// This is essential for pitch-shifting, chorus LFO modulation, etc.
    #[inline]
    pub fn read_linear(&self, delay_samples: f32) -> f32 {
        let delay_int = delay_samples as usize;
        let frac = delay_samples - delay_int as f32;
        let s0 = self.read(delay_int);
        let s1 = self.read(delay_int + 1);
        s0 + (s1 - s0) * frac
    }

    /// Read with fractional delay using cubic (Hermite) interpolation.
    /// Higher quality than linear — less aliasing for pitch shifting.
    #[inline]
    pub fn read_cubic(&self, delay_samples: f32) -> f32 {
        let delay_int = delay_samples as usize;
        let frac = delay_samples - delay_int as f32;

        let y_m1 = self.read(delay_int + 2); // oldest
        let y0 = self.read(delay_int + 1);
        let y1 = self.read(delay_int);
        let y2 = if delay_int > 0 { self.read(delay_int - 1) } else { y1 };

        // Hermite interpolation
        let c0 = y0;
        let c1 = 0.5 * (y1 - y_m1);
        let c2 = y_m1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2;
        let c3 = 0.5 * (y2 - y_m1) + 1.5 * (y0 - y1);

        ((c3 * frac + c2) * frac + c1) * frac + c0
    }

    /// Clear the entire delay buffer (silence).
    pub fn clear(&mut self) {
        self.buffer.fill(0.0);
    }

    /// Get the maximum delay in samples.
    pub fn max_delay(&self) -> usize {
        self.mask // capacity - 1
    }

    /// Write a sample without advancing the pointer (for manual control).
    #[inline]
    pub fn write_at(&mut self, offset: usize, sample: f32) {
        let idx = self.write_pos.wrapping_add(offset) & self.mask;
        self.buffer[idx] = sample;
    }

    /// Advance write pointer without writing (for manual control).
    #[inline]
    pub fn advance(&mut self) {
        self.write_pos = self.write_pos.wrapping_add(1);
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_delay() {
        let mut dl = DelayLine::new(16);
        dl.write(1.0);
        dl.write(2.0);
        dl.write(3.0);
        assert!((dl.read(0) - 3.0).abs() < 1e-6);
        assert!((dl.read(1) - 2.0).abs() < 1e-6);
        assert!((dl.read(2) - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_fractional_delay() {
        let mut dl = DelayLine::new(16);
        dl.write(0.0);
        dl.write(1.0);
        // Linear interp between delay=0 (1.0) and delay=1 (0.0) at t=0.5
        let val = dl.read_linear(0.5);
        assert!((val - 0.5).abs() < 1e-6, "Expected 0.5, got {}", val);
    }

    #[test]
    fn test_clear() {
        let mut dl = DelayLine::new(16);
        dl.write(42.0);
        dl.clear();
        assert!((dl.read(0)).abs() < 1e-6);
    }

    #[test]
    fn test_wraparound() {
        let mut dl = DelayLine::new(4); // capacity = 4 (next power of 2)
        for i in 0..20 {
            dl.write(i as f32);
        }
        assert!((dl.read(0) - 19.0).abs() < 1e-6);
        assert!((dl.read(1) - 18.0).abs() < 1e-6);
    }
}
