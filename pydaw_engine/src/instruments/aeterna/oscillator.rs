// ==========================================================================
// AETERNA Oscillator — Anti-aliased waveforms with FM, Sub-Osc, Unison
// ==========================================================================
// v0.0.20.683 — Phase R8A
//
// Core oscillator primitives for the AETERNA synthesizer:
//   - Sine, Saw, Square, Triangle, Noise (White, Pink)
//   - PolyBLEP anti-aliasing for Saw and Square
//   - Wave morphing: Sine ↔ Triangle ↔ Saw ↔ Square (continuous)
//   - Phase Modulation / FM synthesis
//   - Sub-Oscillator (1 or 2 octaves down)
//   - Unison Engine (1–16 voices, detune, stereo spread)
//
// Rules:
//   ✅ All functions are #[inline] and zero-alloc
//   ✅ State is pre-allocated in OscillatorState
//   ❌ NO allocations in process methods
//   ❌ NO locks or panics
// ==========================================================================

use std::f32::consts::PI;

const TWO_PI: f32 = 2.0 * PI;

// ---------------------------------------------------------------------------
// Waveform Type
// ---------------------------------------------------------------------------

/// Available oscillator waveforms.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Waveform {
    Sine,
    Saw,
    Square,
    Triangle,
    WhiteNoise,
    PinkNoise,
}

impl Waveform {
    pub fn from_str(s: &str) -> Self {
        match s {
            "saw" | "Saw" => Self::Saw,
            "square" | "Square" | "pulse" => Self::Square,
            "triangle" | "Triangle" | "tri" => Self::Triangle,
            "white_noise" | "WhiteNoise" | "noise" => Self::WhiteNoise,
            "pink_noise" | "PinkNoise" | "pink" => Self::PinkNoise,
            _ => Self::Sine,
        }
    }
}

// ---------------------------------------------------------------------------
// PolyBLEP — band-limited step function for anti-aliasing
// ---------------------------------------------------------------------------

/// PolyBLEP correction for discontinuities in Saw/Square waves.
///
/// `t` = normalized phase position (0.0–1.0)
/// `dt` = phase increment per sample (freq / sr)
///
/// Smooths the discontinuity at phase wrap-around, reducing aliasing
/// without the cost of wavetable lookup or oversampling.
#[inline]
pub fn polyblep(t: f32, dt: f32) -> f32 {
    let dt = dt.max(1e-6);
    if t < dt {
        // Rising edge
        let x = t / dt;
        x + x - x * x - 1.0
    } else if t > 1.0 - dt {
        // Falling edge
        let x = (t - 1.0) / dt;
        x * x + x + x + 1.0
    } else {
        0.0
    }
}

// ---------------------------------------------------------------------------
// Single-sample waveform generators
// ---------------------------------------------------------------------------

/// Generate one sample of a sine wave.
#[inline]
pub fn gen_sine(phase: f32) -> f32 {
    phase.sin()
}

/// Generate one sample of a naive (aliased) saw wave.
#[inline]
pub fn gen_saw_naive(phase: f32) -> f32 {
    let t = (phase / TWO_PI).rem_euclid(1.0);
    2.0 * t - 1.0
}

/// Generate one sample of an anti-aliased saw wave (PolyBLEP).
#[inline]
pub fn gen_saw_polyblep(phase: f32, dt: f32) -> f32 {
    let t = (phase / TWO_PI).rem_euclid(1.0);
    let mut y = 2.0 * t - 1.0;
    y -= polyblep(t, dt);
    y
}

/// Generate one sample of a naive square wave.
#[inline]
pub fn gen_square_naive(phase: f32, duty: f32) -> f32 {
    let t = (phase / TWO_PI).rem_euclid(1.0);
    if t < duty { 1.0 } else { -1.0 }
}

/// Generate one sample of an anti-aliased square wave (PolyBLEP).
#[inline]
pub fn gen_square_polyblep(phase: f32, dt: f32, duty: f32) -> f32 {
    let t = (phase / TWO_PI).rem_euclid(1.0);
    let duty = duty.clamp(0.05, 0.95);
    let mut y = if t < duty { 1.0 } else { -1.0 };
    y += polyblep(t, dt);
    y -= polyblep((t - duty).rem_euclid(1.0), dt);
    y
}

/// Generate one sample of a triangle wave.
#[inline]
pub fn gen_triangle(phase: f32) -> f32 {
    let t = (phase / TWO_PI).rem_euclid(1.0);
    if t < 0.5 {
        4.0 * t - 1.0
    } else {
        3.0 - 4.0 * t
    }
}

// ---------------------------------------------------------------------------
// Noise generators (stateful)
// ---------------------------------------------------------------------------

/// Simple white noise LCG (no alloc, deterministic enough for audio).
#[inline]
pub fn white_noise(seed: &mut u32) -> f32 {
    // LCG: x = (x * 1103515245 + 12345) & 0x7FFFFFFF
    *seed = seed.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFFFFFF;
    (*seed as f32 / 0x40000000 as f32) - 1.0
}

/// Pink noise approximation (Paul Kellet's method, 3-tap).
///
/// State: `[b0, b1, b2]` — persistent between calls.
#[inline]
pub fn pink_noise(seed: &mut u32, state: &mut [f32; 3]) -> f32 {
    let w = white_noise(seed);
    state[0] = 0.99765 * state[0] + w * 0.0990460;
    state[1] = 0.96300 * state[1] + w * 0.2965164;
    state[2] = 0.57000 * state[2] + w * 1.0526913;
    let pink = state[0] + state[1] + state[2] + w * 0.1848;
    pink * 0.22 // normalize to ~[-1, 1]
}

// ---------------------------------------------------------------------------
// Wave morphing (continuous Sine ↔ Triangle ↔ Saw ↔ Square)
// ---------------------------------------------------------------------------

/// Morph between waveforms continuously.
///
/// `shape` 0.0–1.0:
///   0.00 = Sine
///   0.33 = Triangle
///   0.67 = Saw
///   1.00 = Square
///
/// Uses PolyBLEP for Saw and Square regions.
#[inline]
pub fn gen_morphed(phase: f32, dt: f32, shape: f32) -> f32 {
    let shape = shape.clamp(0.0, 1.0);
    let sine = gen_sine(phase);
    let tri = gen_triangle(phase);

    if shape < 1.0 / 3.0 {
        // Sine → Triangle
        let frac = shape * 3.0;
        sine * (1.0 - frac) + tri * frac
    } else if shape < 2.0 / 3.0 {
        // Triangle → Saw
        let frac = (shape - 1.0 / 3.0) * 3.0;
        let saw = gen_saw_polyblep(phase, dt);
        tri * (1.0 - frac) + saw * frac
    } else {
        // Saw → Square
        let frac = (shape - 2.0 / 3.0) * 3.0;
        let saw = gen_saw_polyblep(phase, dt);
        let sq = gen_square_polyblep(phase, dt, 0.5);
        saw * (1.0 - frac) + sq * frac
    }
}

// ---------------------------------------------------------------------------
// OscillatorState — per-voice oscillator state
// ---------------------------------------------------------------------------

/// Maximum unison voices.
pub const MAX_UNISON: usize = 16;

/// Per-voice oscillator state. Pre-allocated, reused across notes.
pub struct OscillatorState {
    /// Current phase (radians, wraps at 2π).
    pub phase: f32,
    /// Sub-oscillator phase.
    pub sub_phase: f32,
    /// FM modulator phase.
    pub fm_phase: f32,

    /// Noise seed (LCG state).
    pub noise_seed: u32,
    /// Pink noise filter state.
    pub pink_state: [f32; 3],

    // Unison state
    /// Unison voice phases.
    pub unison_phases: [f32; MAX_UNISON],
    /// Pre-computed unison detune ratios (multiplier on frequency).
    pub unison_detune: [f32; MAX_UNISON],
    /// Pre-computed unison stereo pan per voice (-1..1).
    pub unison_pan: [f32; MAX_UNISON],
    /// Number of active unison voices (1 = no unison).
    pub unison_count: u8,
}

impl OscillatorState {
    /// Create a new oscillator state with randomized phase.
    pub fn new() -> Self {
        Self {
            phase: 0.0,
            sub_phase: 0.0,
            fm_phase: 0.0,
            noise_seed: 0x12345678,
            pink_state: [0.0; 3],
            unison_phases: [0.0; MAX_UNISON],
            unison_detune: [1.0; MAX_UNISON],
            unison_pan: [0.0; MAX_UNISON],
            unison_count: 1,
        }
    }

    /// Reset phases for a new note.
    pub fn reset(&mut self, randomize_phase: bool) {
        if randomize_phase {
            // Deterministic pseudo-random start phase per voice
            let seed = self.noise_seed;
            self.phase = ((seed & 0xFFFF) as f32 / 65536.0) * TWO_PI;
            for i in 0..MAX_UNISON {
                let s = seed.wrapping_mul((i as u32).wrapping_add(7));
                self.unison_phases[i] = ((s & 0xFFFF) as f32 / 65536.0) * TWO_PI;
            }
        } else {
            self.phase = 0.0;
            for p in &mut self.unison_phases {
                *p = 0.0;
            }
        }
        self.sub_phase = 0.0;
        self.fm_phase = 0.0;
        self.pink_state = [0.0; 3];
    }

    /// Configure unison: set voice count, detune amount, stereo spread.
    ///
    /// - `voices`: 1–16 (1 = no unison)
    /// - `detune_cents`: total detune spread in cents (e.g., 20 = ±10 cents)
    /// - `spread`: stereo spread 0.0–1.0 (0 = mono, 1 = full L-R)
    pub fn set_unison(&mut self, voices: u8, detune_cents: f32, spread: f32) {
        let n = (voices as usize).clamp(1, MAX_UNISON);
        self.unison_count = n as u8;

        if n == 1 {
            self.unison_detune[0] = 1.0;
            self.unison_pan[0] = 0.0;
            return;
        }

        let spread = spread.clamp(0.0, 1.0);
        let half_detune = detune_cents * 0.5;

        for i in 0..n {
            // Detune: spread evenly from -half to +half cents
            let t = if n > 1 {
                (i as f32 / (n as f32 - 1.0)) * 2.0 - 1.0 // -1..+1
            } else {
                0.0
            };
            let cents = t * half_detune;
            self.unison_detune[i] = 2.0f32.powf(cents / 1200.0);

            // Pan: spread evenly across stereo field
            self.unison_pan[i] = t * spread;
        }
    }

    /// Generate one sample from the oscillator.
    ///
    /// Returns `(left, right)` for stereo output (unison with spread).
    ///
    /// - `freq`: base frequency in Hz
    /// - `sr`: sample rate
    /// - `waveform`: waveform type
    /// - `shape`: morph parameter (0.0–1.0, for Waveform::Sine with morphing)
    /// - `fm_amount`: FM modulation depth (0.0 = off, 1.0 = ±1 octave)
    /// - `fm_ratio`: FM modulator frequency ratio (e.g., 2.0 = 2× carrier)
    /// - `sub_level`: sub-oscillator level (0.0–1.0)
    /// - `sub_octave`: sub-oscillator octave down (1 or 2)
    #[inline]
    pub fn process(
        &mut self,
        freq: f32,
        sr: f32,
        waveform: Waveform,
        _shape: f32,
        fm_amount: f32,
        fm_ratio: f32,
        sub_level: f32,
        sub_octave: u8,
    ) -> (f32, f32) {
        let dt = freq / sr;
        let phase_inc = freq * TWO_PI / sr;

        let n = self.unison_count as usize;
        let mut sum_l: f32 = 0.0;
        let mut sum_r: f32 = 0.0;

        // FM modulator (shared across unison voices)
        let fm_mod = if fm_amount > 0.001 {
            let fm_freq = freq * fm_ratio;
            self.fm_phase += fm_freq * TWO_PI / sr;
            if self.fm_phase > TWO_PI { self.fm_phase -= TWO_PI; }
            self.fm_phase.sin() * fm_amount * PI // ±π radians modulation
        } else {
            0.0
        };

        for i in 0..n {
            let detune = self.unison_detune[i];
            let pan = self.unison_pan[i];
            let voice_inc = phase_inc * detune;
            let voice_dt = dt * detune;

            // Advance phase
            self.unison_phases[i] += voice_inc;
            if self.unison_phases[i] > TWO_PI {
                self.unison_phases[i] -= TWO_PI;
            }

            // Apply FM modulation to phase
            let modulated_phase = self.unison_phases[i] + fm_mod;

            // Generate sample based on waveform
            let sample = match waveform {
                Waveform::Sine => gen_sine(modulated_phase),
                Waveform::Saw => gen_saw_polyblep(modulated_phase, voice_dt),
                Waveform::Square => gen_square_polyblep(modulated_phase, voice_dt, 0.5),
                Waveform::Triangle => gen_triangle(modulated_phase),
                Waveform::WhiteNoise => white_noise(&mut self.noise_seed),
                Waveform::PinkNoise => pink_noise(&mut self.noise_seed, &mut self.pink_state),
            };

            // Equal-power pan for unison spread
            let pan_angle = (pan + 1.0) * 0.25 * PI;
            let pan_l = pan_angle.cos();
            let pan_r = pan_angle.sin();

            let gain = 1.0 / (n as f32).sqrt(); // normalize unison level
            sum_l += sample * gain * pan_l;
            sum_r += sample * gain * pan_r;
        }

        // Also update main phase (for non-unison compatibility)
        self.phase += phase_inc;
        if self.phase > TWO_PI { self.phase -= TWO_PI; }

        // Sub-oscillator (always sine, 1 or 2 octaves down)
        if sub_level > 0.001 {
            let sub_div = if sub_octave >= 2 { 4.0 } else { 2.0 };
            self.sub_phase += (freq / sub_div) * TWO_PI / sr;
            if self.sub_phase > TWO_PI { self.sub_phase -= TWO_PI; }
            let sub = self.sub_phase.sin() * sub_level;
            sum_l += sub;
            sum_r += sub;
        }

        (sum_l, sum_r)
    }

    /// Generate one morphed sample (Sine↔Tri↔Saw↔Square blend).
    ///
    /// Convenience wrapper around `gen_morphed` with unison.
    #[inline]
    pub fn process_morphed(
        &mut self,
        freq: f32,
        sr: f32,
        shape: f32,
        fm_amount: f32,
        fm_ratio: f32,
        sub_level: f32,
        sub_octave: u8,
    ) -> (f32, f32) {
        let dt = freq / sr;
        let phase_inc = freq * TWO_PI / sr;
        let n = self.unison_count as usize;
        let mut sum_l: f32 = 0.0;
        let mut sum_r: f32 = 0.0;

        // FM
        let fm_mod = if fm_amount > 0.001 {
            self.fm_phase += freq * fm_ratio * TWO_PI / sr;
            if self.fm_phase > TWO_PI { self.fm_phase -= TWO_PI; }
            self.fm_phase.sin() * fm_amount * PI
        } else {
            0.0
        };

        for i in 0..n {
            let detune = self.unison_detune[i];
            let pan = self.unison_pan[i];
            let voice_dt = dt * detune;

            self.unison_phases[i] += phase_inc * detune;
            if self.unison_phases[i] > TWO_PI { self.unison_phases[i] -= TWO_PI; }

            let modulated_phase = self.unison_phases[i] + fm_mod;
            let sample = gen_morphed(modulated_phase, voice_dt, shape);

            let pan_angle = (pan + 1.0) * 0.25 * PI;
            let gain = 1.0 / (n as f32).sqrt();
            sum_l += sample * gain * pan_angle.cos();
            sum_r += sample * gain * pan_angle.sin();
        }

        self.phase += phase_inc;
        if self.phase > TWO_PI { self.phase -= TWO_PI; }

        if sub_level > 0.001 {
            let sub_div = if sub_octave >= 2 { 4.0 } else { 2.0 };
            self.sub_phase += (freq / sub_div) * TWO_PI / sr;
            if self.sub_phase > TWO_PI { self.sub_phase -= TWO_PI; }
            let sub = self.sub_phase.sin() * sub_level;
            sum_l += sub;
            sum_r += sub;
        }

        (sum_l, sum_r)
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sine_zero_at_zero() {
        assert!((gen_sine(0.0)).abs() < 0.001);
    }

    #[test]
    fn test_sine_peak() {
        let peak = gen_sine(PI / 2.0);
        assert!((peak - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_saw_range() {
        for i in 0..100 {
            let phase = (i as f32 / 100.0) * TWO_PI;
            let s = gen_saw_polyblep(phase, 0.01);
            assert!(s >= -1.5 && s <= 1.5, "Saw out of range at phase {}: {}", phase, s);
        }
    }

    #[test]
    fn test_square_duty() {
        // At duty=0.5, should be +1 in first half, -1 in second
        let s1 = gen_square_polyblep(0.1, 0.01, 0.5);
        let s2 = gen_square_polyblep(PI + 0.1, 0.01, 0.5);
        assert!(s1 > 0.5, "Square first half should be positive: {}", s1);
        assert!(s2 < -0.5, "Square second half should be negative: {}", s2);
    }

    #[test]
    fn test_triangle_range() {
        for i in 0..100 {
            let phase = (i as f32 / 100.0) * TWO_PI;
            let s = gen_triangle(phase);
            assert!(s >= -1.01 && s <= 1.01, "Triangle out of range: {}", s);
        }
    }

    #[test]
    fn test_triangle_symmetry() {
        // Triangle at 0 should be -1, at π/2 should be ~0, at π should be 1
        let t0 = gen_triangle(0.0);
        let t1 = gen_triangle(PI * 0.5);
        let t2 = gen_triangle(PI);
        assert!((t0 - (-1.0)).abs() < 0.01, "Triangle(0) = {}", t0);
        assert!(t1.abs() < 0.01, "Triangle(π/2) = {}", t1);
        assert!((t2 - 1.0).abs() < 0.01, "Triangle(π) = {}", t2);
    }

    #[test]
    fn test_white_noise_range() {
        let mut seed = 42u32;
        for _ in 0..1000 {
            let s = white_noise(&mut seed);
            assert!(s >= -1.5 && s <= 1.5, "Noise out of range: {}", s);
        }
    }

    #[test]
    fn test_pink_noise_nonzero() {
        let mut seed = 42u32;
        let mut state = [0.0f32; 3];
        let mut sum = 0.0f32;
        for _ in 0..1000 {
            sum += pink_noise(&mut seed, &mut state).abs();
        }
        assert!(sum > 1.0, "Pink noise should produce nonzero output");
    }

    #[test]
    fn test_morph_sine_at_zero() {
        let s = gen_morphed(PI / 2.0, 0.01, 0.0); // shape=0 → sine
        let expected = gen_sine(PI / 2.0);
        assert!((s - expected).abs() < 0.01, "Morph at 0 should be sine: {} vs {}", s, expected);
    }

    #[test]
    fn test_morph_square_at_one() {
        let s = gen_morphed(0.5, 0.01, 1.0); // shape=1 → square
        let expected = gen_square_polyblep(0.5, 0.01, 0.5);
        assert!((s - expected).abs() < 0.01, "Morph at 1 should be square: {} vs {}", s, expected);
    }

    #[test]
    fn test_oscillator_state_process_sine() {
        let mut osc = OscillatorState::new();
        let sr = 44100.0;
        let freq = 440.0;

        // Generate 100 samples of sine
        let mut max_l = 0.0f32;
        for _ in 0..100 {
            let (l, r) = osc.process(freq, sr, Waveform::Sine, 0.0, 0.0, 1.0, 0.0, 1);
            max_l = max_l.max(l.abs());
            assert!((l - r).abs() < 0.001, "Mono sine should be equal L/R");
        }
        assert!(max_l > 0.1, "Should produce audible output: {}", max_l);
    }

    #[test]
    fn test_unison_stereo_spread() {
        let mut osc = OscillatorState::new();
        osc.set_unison(4, 20.0, 1.0); // 4 voices, 20 cents detune, full spread

        let sr = 44100.0;
        let freq = 440.0;
        let mut diff_sum = 0.0f32;

        for _ in 0..512 {
            let (l, r) = osc.process(freq, sr, Waveform::Saw, 0.0, 0.0, 1.0, 0.0, 1);
            diff_sum += (l - r).abs();
        }

        assert!(diff_sum > 1.0, "Unison with spread should have L≠R: diff_sum={}", diff_sum);
    }

    #[test]
    fn test_unison_mono_when_spread_zero() {
        let mut osc = OscillatorState::new();
        osc.set_unison(4, 20.0, 0.0); // 4 voices, detune, NO spread

        let sr = 44100.0;
        let freq = 440.0;

        for _ in 0..100 {
            let (l, r) = osc.process(freq, sr, Waveform::Sine, 0.0, 0.0, 1.0, 0.0, 1);
            assert!((l - r).abs() < 0.01, "No spread should be mono: L={} R={}", l, r);
        }
    }

    #[test]
    fn test_fm_modulation_changes_output() {
        let mut osc_no_fm = OscillatorState::new();
        let mut osc_fm = OscillatorState::new();

        let sr = 44100.0;
        let freq = 440.0;
        let mut diff = 0.0f32;

        for _ in 0..512 {
            let (l1, _) = osc_no_fm.process(freq, sr, Waveform::Sine, 0.0, 0.0, 1.0, 0.0, 1);
            let (l2, _) = osc_fm.process(freq, sr, Waveform::Sine, 0.0, 0.5, 2.0, 0.0, 1);
            diff += (l1 - l2).abs();
        }

        assert!(diff > 1.0, "FM should change the output: diff={}", diff);
    }

    #[test]
    fn test_sub_oscillator() {
        let mut osc_no_sub = OscillatorState::new();
        let mut osc_sub = OscillatorState::new();

        let sr = 44100.0;
        let freq = 440.0;
        let mut diff = 0.0f32;

        for _ in 0..512 {
            let (l1, _) = osc_no_sub.process(freq, sr, Waveform::Sine, 0.0, 0.0, 1.0, 0.0, 1);
            let (l2, _) = osc_sub.process(freq, sr, Waveform::Sine, 0.0, 0.0, 1.0, 0.5, 1);
            diff += (l1 - l2).abs();
        }

        assert!(diff > 1.0, "Sub-osc should add bass: diff={}", diff);
    }

    #[test]
    fn test_waveform_parse() {
        assert_eq!(Waveform::from_str("sine"), Waveform::Sine);
        assert_eq!(Waveform::from_str("saw"), Waveform::Saw);
        assert_eq!(Waveform::from_str("square"), Waveform::Square);
        assert_eq!(Waveform::from_str("triangle"), Waveform::Triangle);
        assert_eq!(Waveform::from_str("noise"), Waveform::WhiteNoise);
        assert_eq!(Waveform::from_str("pink"), Waveform::PinkNoise);
    }

    #[test]
    fn test_polyblep_correction() {
        // PolyBLEP should be zero far from edges
        assert!((polyblep(0.5, 0.01)).abs() < 0.001);
        // Non-zero near edges
        assert!((polyblep(0.005, 0.01)).abs() > 0.01);
        assert!((polyblep(0.995, 0.01)).abs() > 0.01);
    }

    #[test]
    fn test_morphed_process() {
        let mut osc = OscillatorState::new();
        let sr = 44100.0;
        let freq = 440.0;
        let mut max_l = 0.0f32;

        for _ in 0..512 {
            let (l, _) = osc.process_morphed(freq, sr, 0.5, 0.0, 1.0, 0.0, 1);
            max_l = max_l.max(l.abs());
        }
        assert!(max_l > 0.1, "Morphed process should produce audio: {}", max_l);
    }
}
