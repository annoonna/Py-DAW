// ==========================================================================
// DSP Math Utilities — Fundamental audio math functions
// ==========================================================================
// v0.0.20.667 — Phase R1C
// Zero-alloc, inline, audio-thread safe.
// ==========================================================================

use std::f32::consts::PI;

/// Convert decibels to linear amplitude.
#[inline]
pub fn db_to_linear(db: f32) -> f32 {
    10.0f32.powf(db / 20.0)
}

/// Convert linear amplitude to decibels.
/// Returns -infinity for zero/negative input.
#[inline]
pub fn linear_to_db(linear: f32) -> f32 {
    if linear <= 0.0 {
        -f32::INFINITY
    } else {
        20.0 * linear.log10()
    }
}

/// Convert MIDI note number to frequency in Hz.
/// A4 (note 69) = 440 Hz.
#[inline]
pub fn midi_to_freq(note: f32) -> f32 {
    440.0 * 2.0f32.powf((note - 69.0) / 12.0)
}

/// Convert frequency in Hz to MIDI note number.
#[inline]
pub fn freq_to_midi(freq: f32) -> f32 {
    if freq <= 0.0 {
        return 0.0;
    }
    69.0 + 12.0 * (freq / 440.0).log2()
}

/// Clamp a value to [min, max].
#[inline]
pub fn clamp(val: f32, min: f32, max: f32) -> f32 {
    val.clamp(min, max)
}

/// Fast tanh approximation (Pade approximant — good for saturation).
/// Clamped to [-1, 1] since the Padé form diverges for |x| > ~3.
#[inline]
pub fn fast_tanh(x: f32) -> f32 {
    let x2 = x * x;
    let result = x * (27.0 + x2) / (27.0 + 9.0 * x2);
    result.clamp(-1.0, 1.0)
}

/// Soft-clip a sample to [-1, 1] range using tanh saturation.
#[inline]
pub fn soft_clip(sample: f32) -> f32 {
    fast_tanh(sample)
}

/// Hard-clip a sample to [-limit, limit].
#[inline]
pub fn hard_clip(sample: f32, limit: f32) -> f32 {
    sample.clamp(-limit, limit)
}

/// Linear interpolation between a and b.
#[inline]
pub fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Equal-power crossfade gains for position t (0.0 = full A, 1.0 = full B).
#[inline]
pub fn equal_power_crossfade(t: f32) -> (f32, f32) {
    let angle = t * PI * 0.5;
    (angle.cos(), angle.sin())
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_db_conversions() {
        assert!((db_to_linear(0.0) - 1.0).abs() < 1e-6);
        assert!((db_to_linear(-6.0) - 0.5012).abs() < 0.01);
        assert!((db_to_linear(-20.0) - 0.1).abs() < 0.001);
        assert!((linear_to_db(1.0)).abs() < 1e-6);
        assert!((linear_to_db(0.5) - (-6.02)).abs() < 0.1);
    }

    #[test]
    fn test_midi_freq() {
        assert!((midi_to_freq(69.0) - 440.0).abs() < 0.01);
        assert!((midi_to_freq(60.0) - 261.63).abs() < 0.1);
        assert!((midi_to_freq(57.0) - 220.0).abs() < 0.1);
        assert!((freq_to_midi(440.0) - 69.0).abs() < 0.01);
    }

    #[test]
    fn test_fast_tanh() {
        assert!((fast_tanh(0.0)).abs() < 1e-6);
        assert!(fast_tanh(5.0) > 0.95);
        assert!(fast_tanh(-5.0) < -0.95);
    }

    #[test]
    fn test_lerp() {
        assert!((lerp(0.0, 1.0, 0.5) - 0.5).abs() < 1e-6);
        assert!((lerp(10.0, 20.0, 0.25) - 12.5).abs() < 1e-6);
    }
}
