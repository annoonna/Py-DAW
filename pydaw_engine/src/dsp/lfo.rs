// ==========================================================================
// LFO — Low Frequency Oscillator for modulation
// ==========================================================================
// v0.0.20.667 — Phase R1B
//
// Used by: Chorus, Phaser, Tremolo, AETERNA Mod-Matrix, Fusion
// Shapes: Sine, Triangle, Square, Saw Up, Saw Down, Sample & Hold
// ==========================================================================

use std::f32::consts::PI;

/// LFO waveform shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LfoShape {
    Sine,
    Triangle,
    Square,
    SawUp,
    SawDown,
    SampleAndHold,
}

/// Low Frequency Oscillator.
///
/// Output range: -1.0 to 1.0 (bipolar) or 0.0 to 1.0 (unipolar via `process_unipolar()`).
/// Phase-synced, sample-accurate.
pub struct Lfo {
    phase: f32,        // 0.0 – 1.0
    phase_inc: f32,    // per-sample phase increment
    shape: LfoShape,
    sample_rate: f32,
    rate_hz: f32,
    /// Sample & Hold: held value until next S&H trigger
    sh_value: f32,
    /// Simple RNG state for S&H
    rng_state: u32,
}

impl Lfo {
    /// Create a new LFO.
    ///
    /// - `rate_hz`: Frequency in Hz (0.01 – 100.0 typical)
    /// - `shape`: Waveform shape
    /// - `sample_rate`: Audio sample rate
    pub fn new(rate_hz: f32, shape: LfoShape, sample_rate: f32) -> Self {
        Self {
            phase: 0.0,
            phase_inc: rate_hz / sample_rate,
            shape,
            sample_rate,
            rate_hz,
            sh_value: 0.0,
            rng_state: 0x12345678,
        }
    }

    /// Set the LFO rate in Hz.
    pub fn set_rate(&mut self, rate_hz: f32) {
        self.rate_hz = rate_hz.max(0.001);
        self.phase_inc = self.rate_hz / self.sample_rate;
    }

    /// Set the LFO shape.
    pub fn set_shape(&mut self, shape: LfoShape) {
        self.shape = shape;
    }

    /// Set sample rate (on audio config change).
    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        self.sample_rate = sample_rate;
        self.phase_inc = self.rate_hz / self.sample_rate;
    }

    /// Reset phase to 0 (call on note-on for synced LFO).
    pub fn reset(&mut self) {
        self.phase = 0.0;
    }

    /// Set phase directly (for phase offset between LFO instances).
    pub fn set_phase(&mut self, phase: f32) {
        self.phase = phase.rem_euclid(1.0);
    }

    /// Process one sample and return bipolar output (-1.0 to 1.0).
    ///
    /// **AUDIO THREAD** — inline, zero-alloc.
    #[inline]
    pub fn process(&mut self) -> f32 {
        let value = self.compute_shape(self.phase);

        // Advance phase
        self.phase += self.phase_inc;
        if self.phase >= 1.0 {
            self.phase -= 1.0;
            // S&H: latch new random value at phase wrap
            if self.shape == LfoShape::SampleAndHold {
                self.sh_value = self.next_random();
            }
        }

        value
    }

    /// Process one sample, unipolar output (0.0 to 1.0).
    #[inline]
    pub fn process_unipolar(&mut self) -> f32 {
        (self.process() + 1.0) * 0.5
    }

    /// Compute the shape value at a given phase (0.0 – 1.0).
    #[inline]
    fn compute_shape(&self, phase: f32) -> f32 {
        match self.shape {
            LfoShape::Sine => (phase * 2.0 * PI).sin(),

            LfoShape::Triangle => {
                if phase < 0.25 {
                    phase * 4.0
                } else if phase < 0.75 {
                    2.0 - phase * 4.0
                } else {
                    phase * 4.0 - 4.0
                }
            }

            LfoShape::Square => {
                if phase < 0.5 { 1.0 } else { -1.0 }
            }

            LfoShape::SawUp => phase * 2.0 - 1.0,

            LfoShape::SawDown => 1.0 - phase * 2.0,

            LfoShape::SampleAndHold => self.sh_value,
        }
    }

    /// Simple xorshift RNG for S&H (-1.0 to 1.0).
    #[inline]
    fn next_random(&mut self) -> f32 {
        self.rng_state ^= self.rng_state << 13;
        self.rng_state ^= self.rng_state >> 17;
        self.rng_state ^= self.rng_state << 5;
        // Convert to -1.0..1.0
        (self.rng_state as f32 / u32::MAX as f32) * 2.0 - 1.0
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sine_range() {
        let mut lfo = Lfo::new(1.0, LfoShape::Sine, 1000.0);
        let mut min_val = f32::MAX;
        let mut max_val = f32::MIN;
        for _ in 0..1000 {
            let v = lfo.process();
            min_val = min_val.min(v);
            max_val = max_val.max(v);
        }
        assert!(min_val >= -1.01 && max_val <= 1.01);
        assert!(min_val < -0.9);
        assert!(max_val > 0.9);
    }

    #[test]
    fn test_triangle_range() {
        let mut lfo = Lfo::new(1.0, LfoShape::Triangle, 1000.0);
        for _ in 0..1000 {
            let v = lfo.process();
            assert!(v >= -1.01 && v <= 1.01, "Triangle out of range: {}", v);
        }
    }

    #[test]
    fn test_square_values() {
        let mut lfo = Lfo::new(1.0, LfoShape::Square, 100.0);
        // First half should be +1, second half -1
        let v0 = lfo.process();
        assert!((v0 - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_unipolar() {
        let mut lfo = Lfo::new(1.0, LfoShape::Sine, 1000.0);
        for _ in 0..1000 {
            let v = lfo.process_unipolar();
            assert!(v >= -0.01 && v <= 1.01, "Unipolar out of range: {}", v);
        }
    }
}
