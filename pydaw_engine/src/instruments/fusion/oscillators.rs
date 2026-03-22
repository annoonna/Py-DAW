// ==========================================================================
// Fusion Oscillators — Semi-modular synth waveforms
// ==========================================================================
// v0.0.20.693 — Phase R10A
//
// Oscillator types matching the Python Fusion engine:
//   - Sine (with skew + fold waveshaping)
//   - Triangle (with skew + fold)
//   - Pulse (variable PWM, PolyBLEP)
//   - Saw (PolyBLEP)
//   - Phase1 (Phase distortion)
//   - Swarm (detuned cluster)
//   - Bite (Bitcrushed oscillator)
//
// All oscillators share the FusionOsc enum for zero-cost dispatch.
//
// Rules:
//   ✅ render_sample() is #[inline] and zero-alloc
//   ✅ All state in fixed-size structs
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::f32::consts::PI;

const TWO_PI: f32 = 2.0 * PI;

// ---------------------------------------------------------------------------
// PolyBLEP (shared)
// ---------------------------------------------------------------------------

#[inline]
fn polyblep(t: f32, dt: f32) -> f32 {
    let dt = dt.max(1e-6);
    if t < dt {
        let x = t / dt;
        x + x - x * x - 1.0
    } else if t > 1.0 - dt {
        let x = (t - 1.0) / dt;
        x * x + x + x + 1.0
    } else {
        0.0
    }
}

// ---------------------------------------------------------------------------
// Oscillator Type Enum
// ---------------------------------------------------------------------------

/// Available Fusion oscillator types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FusionOscType {
    Sine,
    Triangle,
    Pulse,
    Saw,
    Phase1,
    Swarm,
    Bite,
}

impl FusionOscType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "sine" | "Sine" => Self::Sine,
            "triangle" | "Triangle" | "tri" => Self::Triangle,
            "pulse" | "Pulse" | "square" => Self::Pulse,
            "saw" | "Saw" => Self::Saw,
            "phase-1" | "phase1" | "Phase1" => Self::Phase1,
            "swarm" | "Swarm" => Self::Swarm,
            "bite" | "Bite" => Self::Bite,
            _ => Self::Sine,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Sine => "sine",
            Self::Triangle => "triangle",
            Self::Pulse => "pulse",
            Self::Saw => "saw",
            Self::Phase1 => "phase-1",
            Self::Swarm => "swarm",
            Self::Bite => "bite",
        }
    }
}

// ---------------------------------------------------------------------------
// Oscillator Parameters (shared across voice)
// ---------------------------------------------------------------------------

/// Shared oscillator parameters.
#[derive(Debug, Clone)]
pub struct FusionOscParams {
    pub osc_type: FusionOscType,
    /// Semitone offset (-7..+7).
    pub pitch_st: f32,
    /// Octave shift (-2..+3).
    pub octave_shift: i8,
    /// Pulse width (0.01–0.99, for Pulse type).
    pub pulse_width: f32,
    /// Skew (-1..+1, for Sine/Triangle waveshaping).
    pub skew: f32,
    /// Fold amount (0..1, wavefold distortion).
    pub fold: f32,
    /// Phase modulation depth (0..1, from sub-osc).
    pub phase_mod: f32,
    /// Swarm detune (0..1).
    pub swarm_detune: f32,
    /// Swarm voice count (2–8).
    pub swarm_voices: u8,
    /// Bite bit depth (1–16).
    pub bite_bits: u8,
    /// Bite sample rate reduction (1–64).
    pub bite_downsample: u8,
    /// Phase1 distortion amount (0..1).
    pub phase1_amount: f32,
}

impl Default for FusionOscParams {
    fn default() -> Self {
        Self {
            osc_type: FusionOscType::Sine,
            pitch_st: 0.0,
            octave_shift: 0,
            pulse_width: 0.5,
            skew: 0.0,
            fold: 0.0,
            phase_mod: 0.0,
            swarm_detune: 0.2,
            swarm_voices: 4,
            bite_bits: 8,
            bite_downsample: 1,
            phase1_amount: 0.5,
        }
    }
}

impl FusionOscParams {
    /// Calculate effective frequency with pitch offset and octave.
    #[inline]
    pub fn calc_freq(&self, base_freq: f32) -> f32 {
        let oct = 2.0f32.powi(self.octave_shift as i32);
        let st = 2.0f32.powf(self.pitch_st / 12.0);
        base_freq * oct * st
    }
}

// ---------------------------------------------------------------------------
// Oscillator State — per-voice, pre-allocated
// ---------------------------------------------------------------------------

/// Maximum swarm voices.
const MAX_SWARM: usize = 8;

/// Per-voice oscillator state.
pub struct FusionOscState {
    /// Main phase (0..1).
    phase: f32,
    /// Swarm voice phases.
    swarm_phases: [f32; MAX_SWARM],
    /// Bite: held sample value.
    bite_held: f32,
    /// Bite: sample counter for downsampling.
    bite_counter: u8,
}

impl FusionOscState {
    pub fn new() -> Self {
        Self {
            phase: 0.0,
            swarm_phases: [0.0; MAX_SWARM],
            bite_held: 0.0,
            bite_counter: 0,
        }
    }

    pub fn reset(&mut self) {
        self.phase = 0.0;
        self.swarm_phases = [0.0; MAX_SWARM];
        self.bite_held = 0.0;
        self.bite_counter = 0;
    }

    /// Render one sample.
    #[inline]
    pub fn render_sample(
        &mut self,
        freq: f32,
        sr: f32,
        params: &FusionOscParams,
        phase_mod: f32,
    ) -> f32 {
        let dt = freq / sr;

        let sample = match params.osc_type {
            FusionOscType::Sine => self.render_sine(dt, params, phase_mod),
            FusionOscType::Triangle => self.render_triangle(dt, params, phase_mod),
            FusionOscType::Pulse => self.render_pulse(dt, params, phase_mod),
            FusionOscType::Saw => self.render_saw(dt, params, phase_mod),
            FusionOscType::Phase1 => self.render_phase1(dt, params, phase_mod),
            FusionOscType::Swarm => self.render_swarm(dt, sr, freq, params),
            FusionOscType::Bite => self.render_bite(dt, params, phase_mod),
        };

        sample
    }

    // --- Sine ---
    #[inline]
    fn render_sine(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        let mut val = (p * TWO_PI).sin();

        // Skew: asymmetric phase distortion
        if params.skew.abs() > 0.001 {
            let sp = if p < 0.5 {
                let denom = 1.0 - params.skew * 0.49;
                if denom.abs() > 1e-9 { (p / denom) * 0.5 } else { p }
            } else {
                let denom = 1.0 + params.skew * 0.49;
                if denom.abs() > 1e-9 { 0.5 + ((p - 0.5) / denom) * 0.5 } else { p }
            };
            val = (sp * TWO_PI).sin();
        }

        // Fold
        if params.fold > 0.001 {
            val *= 1.0 + params.fold * 4.0;
            // Wavefold: reflect at ±1
            while val > 1.0 || val < -1.0 {
                if val > 1.0 { val = 2.0 - val; }
                if val < -1.0 { val = -2.0 - val; }
            }
        }

        val
    }

    // --- Triangle ---
    #[inline]
    fn render_triangle(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        let mut val = if p < 0.5 { 4.0 * p - 1.0 } else { 3.0 - 4.0 * p };

        // Skew via tanh saturation
        if params.skew.abs() > 0.001 {
            let factor = 1.0 + params.skew.abs() * 2.0;
            val = (val * factor).tanh() / factor.tanh();
        }

        // Fold
        if params.fold > 0.001 {
            val *= 1.0 + params.fold * 4.0;
            while val > 1.0 || val < -1.0 {
                if val > 1.0 { val = 2.0 - val; }
                if val < -1.0 { val = -2.0 - val; }
            }
        }

        val
    }

    // --- Pulse (PolyBLEP) ---
    #[inline]
    fn render_pulse(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        let w = params.pulse_width.clamp(0.01, 0.99);
        let mut val = if p < w { 1.0 } else { -1.0 };

        // PolyBLEP at rising edge
        val += polyblep(p, dt);
        // PolyBLEP at falling edge
        val -= polyblep((p - w + 1.0).rem_euclid(1.0), dt);

        val
    }

    // --- Saw (PolyBLEP) ---
    #[inline]
    fn render_saw(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        let mut val = 2.0 * p - 1.0;
        val -= polyblep(p, dt);

        val
    }

    // --- Phase1 (Phase Distortion) ---
    #[inline]
    fn render_phase1(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        let amt = params.phase1_amount;
        // Phase distortion: warp the phase before feeding to sine
        let warped = if p < 0.5 {
            let stretch = 1.0 + amt * 1.5;
            (p * stretch).min(0.5)
        } else {
            let compress = 1.0 - amt * 0.45;
            0.5 + ((p - 0.5) / compress.max(0.1)).min(0.5)
        };

        (warped * TWO_PI).sin()
    }

    // --- Swarm (detuned cluster) ---
    #[inline]
    fn render_swarm(&mut self, _dt: f32, sr: f32, base_freq: f32, params: &FusionOscParams) -> f32 {
        let n = (params.swarm_voices as usize).clamp(2, MAX_SWARM);
        let max_cents = params.swarm_detune * 50.0; // 0..50 cents
        let mut sum = 0.0f32;

        for i in 0..n {
            let pos = if n > 1 {
                (i as f32 / (n as f32 - 1.0)) * 2.0 - 1.0
            } else {
                0.0
            };
            let cents = pos * max_cents;
            let ratio = 2.0f32.powf(cents / 1200.0);
            let v_dt = (base_freq * ratio) / sr;

            self.swarm_phases[i] = (self.swarm_phases[i] + v_dt).rem_euclid(1.0);

            // Each swarm voice is a simple saw
            let p = self.swarm_phases[i];
            let mut val = 2.0 * p - 1.0;
            val -= polyblep(p, v_dt);
            sum += val;
        }

        sum / (n as f32).sqrt()
    }

    // --- Bite (Bitcrushed) ---
    #[inline]
    fn render_bite(&mut self, dt: f32, params: &FusionOscParams, phase_mod: f32) -> f32 {
        let p = (self.phase + phase_mod * params.phase_mod).rem_euclid(1.0);
        self.phase = (self.phase + dt).rem_euclid(1.0);

        // Downsample: only update held value every N samples
        self.bite_counter += 1;
        if self.bite_counter >= params.bite_downsample {
            self.bite_counter = 0;

            // Generate saw as base
            let raw = 2.0 * p - 1.0;

            // Bit reduction
            let bits = params.bite_bits.clamp(1, 16) as f32;
            let levels = 2.0f32.powf(bits);
            self.bite_held = ((raw * 0.5 + 0.5) * levels).floor() / levels * 2.0 - 1.0;
        }

        self.bite_held
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const SR: f32 = 44100.0;

    #[test]
    fn test_osc_type_parse() {
        assert_eq!(FusionOscType::from_str("sine"), FusionOscType::Sine);
        assert_eq!(FusionOscType::from_str("saw"), FusionOscType::Saw);
        assert_eq!(FusionOscType::from_str("pulse"), FusionOscType::Pulse);
        assert_eq!(FusionOscType::from_str("phase-1"), FusionOscType::Phase1);
        assert_eq!(FusionOscType::from_str("swarm"), FusionOscType::Swarm);
        assert_eq!(FusionOscType::from_str("bite"), FusionOscType::Bite);
        assert_eq!(FusionOscType::from_str("unknown"), FusionOscType::Sine);
    }

    #[test]
    fn test_all_types_produce_audio() {
        let types = [
            FusionOscType::Sine, FusionOscType::Triangle, FusionOscType::Pulse,
            FusionOscType::Saw, FusionOscType::Phase1, FusionOscType::Swarm,
            FusionOscType::Bite,
        ];

        for osc_type in &types {
            let mut state = FusionOscState::new();
            let mut params = FusionOscParams::default();
            params.osc_type = *osc_type;

            let mut max_abs = 0.0f32;
            for _ in 0..512 {
                let s = state.render_sample(440.0, SR, &params, 0.0);
                max_abs = max_abs.max(s.abs());
            }
            assert!(max_abs > 0.1, "{:?} should produce audio: max={}", osc_type, max_abs);
        }
    }

    #[test]
    fn test_sine_at_zero() {
        let mut state = FusionOscState::new();
        let params = FusionOscParams::default();
        let s = state.render_sample(440.0, SR, &params, 0.0);
        assert!(s.abs() < 0.1, "Sine at phase 0 should be near 0: {}", s);
    }

    #[test]
    fn test_pulse_width() {
        let mut state = FusionOscState::new();
        let mut params = FusionOscParams::default();
        params.osc_type = FusionOscType::Pulse;
        params.pulse_width = 0.25;

        let mut pos_count = 0;
        let mut neg_count = 0;
        for _ in 0..1000 {
            let s = state.render_sample(440.0, SR, &params, 0.0);
            if s > 0.0 { pos_count += 1; } else { neg_count += 1; }
        }
        // With 25% width, positive should be roughly 25% of samples
        let ratio = pos_count as f32 / (pos_count + neg_count) as f32;
        assert!(ratio < 0.4, "25% pulse width ratio should be < 0.4: {}", ratio);
    }

    #[test]
    fn test_calc_freq() {
        let mut params = FusionOscParams::default();
        // No offset
        assert!((params.calc_freq(440.0) - 440.0).abs() < 0.01);

        // Octave up
        params.octave_shift = 1;
        assert!((params.calc_freq(440.0) - 880.0).abs() < 0.01);

        // +7 semitones
        params.octave_shift = 0;
        params.pitch_st = 7.0;
        let expected = 440.0 * 2.0f32.powf(7.0 / 12.0);
        assert!((params.calc_freq(440.0) - expected).abs() < 1.0);
    }

    #[test]
    fn test_fold_limits_output() {
        let mut state = FusionOscState::new();
        let mut params = FusionOscParams::default();
        params.fold = 1.0; // maximum fold

        for _ in 0..256 {
            let s = state.render_sample(440.0, SR, &params, 0.0);
            assert!(s >= -1.01 && s <= 1.01, "Fold should keep output in range: {}", s);
        }
    }

    #[test]
    fn test_swarm_wider_than_single() {
        let mut state_single = FusionOscState::new();
        let mut state_swarm = FusionOscState::new();
        let params_single = FusionOscParams { osc_type: FusionOscType::Saw, ..Default::default() };
        let mut params_swarm = FusionOscParams { osc_type: FusionOscType::Swarm, ..Default::default() };
        params_swarm.swarm_detune = 0.8;

        let mut diff = 0.0f32;
        for _ in 0..512 {
            let s1 = state_single.render_sample(440.0, SR, &params_single, 0.0);
            let s2 = state_swarm.render_sample(440.0, SR, &params_swarm, 0.0);
            diff += (s1 - s2).abs();
        }
        assert!(diff > 1.0, "Swarm should differ from single saw: diff={}", diff);
    }

    #[test]
    fn test_bite_quantized() {
        let mut state = FusionOscState::new();
        let mut params = FusionOscParams::default();
        params.osc_type = FusionOscType::Bite;
        params.bite_bits = 2; // very low bit depth

        let mut values = std::collections::HashSet::new();
        for _ in 0..512 {
            let s = state.render_sample(440.0, SR, &params, 0.0);
            values.insert((s * 1000.0) as i32);
        }
        // 2-bit = 4 levels, quantized output should have few unique values
        assert!(values.len() < 20, "2-bit should have few unique values: {}", values.len());
    }
}
