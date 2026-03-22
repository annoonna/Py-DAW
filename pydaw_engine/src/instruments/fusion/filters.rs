// ==========================================================================
// Fusion Filters — SVF, Ladder, Comb
// ==========================================================================
// v0.0.20.693 — Phase R10B
//
// State Variable Filter: Cytomic/Simper trapezoidal integration.
//   Zero-delay feedback, stable at all resonance, self-oscillation.
//   Modes: LP, HP, BP.
//
// Ladder Filter: Huovilainen nonlinear 4-pole (24 dB/oct).
//   Moog-style transistor ladder model with drive/saturation.
//
// Comb Filter: Simple feedforward/feedback comb for flanging/Karplus-Strong.
//
// Rules:
//   ✅ process_sample() is #[inline] and zero-alloc
//   ✅ All state in fixed-size structs
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::f32::consts::PI;

// ---------------------------------------------------------------------------
// Filter Type Enum
// ---------------------------------------------------------------------------

/// Available Fusion filter types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FusionFilterType {
    Svf,
    Ladder,
    Comb,
    Off,
}

impl FusionFilterType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "svf" | "SVF" => Self::Svf,
            "ladder" | "Ladder" | "Low-pass LD" => Self::Ladder,
            "comb" | "Comb" => Self::Comb,
            "off" | "Off" | "none" => Self::Off,
            _ => Self::Svf,
        }
    }
}

/// SVF filter mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SvfMode {
    LowPass,
    HighPass,
    BandPass,
}

// ---------------------------------------------------------------------------
// Filter Parameters (shared)
// ---------------------------------------------------------------------------

/// Shared filter parameters.
#[derive(Debug, Clone)]
pub struct FusionFilterParams {
    pub filter_type: FusionFilterType,
    pub svf_mode: SvfMode,
    /// Cutoff frequency in Hz (20–20000).
    pub cutoff: f32,
    /// Resonance (0–1).
    pub resonance: f32,
    /// Key tracking (0–1).
    pub key_track: f32,
    /// Envelope modulation amount (-1..+1).
    pub env_amount: f32,
    /// Drive (0–1, for Ladder saturation).
    pub drive: f32,
    /// Resonance limit (0–1).
    pub res_limit: f32,
}

impl Default for FusionFilterParams {
    fn default() -> Self {
        Self {
            filter_type: FusionFilterType::Svf,
            svf_mode: SvfMode::LowPass,
            cutoff: 8000.0,
            resonance: 0.0,
            key_track: 0.0,
            env_amount: 0.5,
            drive: 0.0,
            res_limit: 1.0,
        }
    }
}

// ---------------------------------------------------------------------------
// SVF State
// ---------------------------------------------------------------------------

/// Cytomic/Simper Trapezoidal SVF state.
struct SvfState {
    ic1eq: f32,
    ic2eq: f32,
}

impl SvfState {
    fn new() -> Self {
        Self { ic1eq: 0.0, ic2eq: 0.0 }
    }

    fn reset(&mut self) {
        self.ic1eq = 0.0;
        self.ic2eq = 0.0;
    }
}

// ---------------------------------------------------------------------------
// Ladder State
// ---------------------------------------------------------------------------

/// Huovilainen 4-pole ladder filter state.
struct LadderState {
    s: [f32; 4],
}

impl LadderState {
    fn new() -> Self {
        Self { s: [0.0; 4] }
    }

    fn reset(&mut self) {
        self.s = [0.0; 4];
    }
}

// ---------------------------------------------------------------------------
// Comb State
// ---------------------------------------------------------------------------

/// Simple comb filter with pre-allocated delay buffer.
const COMB_MAX_DELAY: usize = 4096;

struct CombState {
    buffer: [f32; COMB_MAX_DELAY],
    write_pos: usize,
}

impl CombState {
    fn new() -> Self {
        Self {
            buffer: [0.0; COMB_MAX_DELAY],
            write_pos: 0,
        }
    }

    fn reset(&mut self) {
        self.buffer = [0.0; COMB_MAX_DELAY];
        self.write_pos = 0;
    }
}

// ---------------------------------------------------------------------------
// Fusion Filter — unified filter with all types
// ---------------------------------------------------------------------------

/// Unified Fusion filter (SVF + Ladder + Comb).
pub struct FusionFilter {
    svf: SvfState,
    ladder: LadderState,
    comb: CombState,
}

impl FusionFilter {
    pub fn new() -> Self {
        Self {
            svf: SvfState::new(),
            ladder: LadderState::new(),
            comb: CombState::new(),
        }
    }

    pub fn reset(&mut self) {
        self.svf.reset();
        self.ladder.reset();
        self.comb.reset();
    }

    /// Process one sample through the configured filter.
    #[inline]
    pub fn process_sample(
        &mut self,
        input: f32,
        params: &FusionFilterParams,
        cutoff_mod: f32,
        note_hz: f32,
        sample_rate: f32,
    ) -> f32 {
        match params.filter_type {
            FusionFilterType::Off => input,
            FusionFilterType::Svf => self.process_svf(input, params, cutoff_mod, note_hz, sample_rate),
            FusionFilterType::Ladder => self.process_ladder(input, params, cutoff_mod, note_hz, sample_rate),
            FusionFilterType::Comb => self.process_comb(input, params, note_hz, sample_rate),
        }
    }

    // --- SVF (Cytomic Trapezoidal — Andrew Simper 2013) ---
    #[inline]
    fn process_svf(
        &mut self,
        input: f32,
        params: &FusionFilterParams,
        cutoff_mod: f32,
        note_hz: f32,
        sr: f32,
    ) -> f32 {
        let mut fc = params.cutoff;

        // Key tracking
        if params.key_track > 0.0 {
            let kt_st = 12.0 * (note_hz.max(20.0) / 261.6).log2();
            fc *= 2.0f32.powf(kt_st * params.key_track / 12.0);
        }

        // Envelope modulation
        fc += cutoff_mod * params.env_amount * 10000.0;
        fc = fc.clamp(20.0, sr * 0.49);

        // Simper trapezoidal coefficients
        let g = (PI * fc / sr).tan();
        let k = 2.0 - 2.0 * params.resonance * params.res_limit;

        let a1 = 1.0 / (1.0 + g * (g + k));
        let a2 = g * a1;
        let a3 = g * a2;

        let s = &mut self.svf;

        let v3 = input - s.ic2eq;
        let v1 = a1 * s.ic1eq + a2 * v3;
        let v2 = s.ic2eq + a2 * s.ic1eq + a3 * v3;

        s.ic1eq = 2.0 * v1 - s.ic1eq;
        s.ic2eq = 2.0 * v2 - s.ic2eq;

        match params.svf_mode {
            SvfMode::LowPass => v2,
            SvfMode::HighPass => input - k * v1 - v2,
            SvfMode::BandPass => v1,
        }
    }

    // --- Ladder (Huovilainen 4-pole) ---
    #[inline]
    fn process_ladder(
        &mut self,
        input: f32,
        params: &FusionFilterParams,
        cutoff_mod: f32,
        note_hz: f32,
        sr: f32,
    ) -> f32 {
        let mut fc = params.cutoff;

        if params.key_track > 0.0 {
            let kt_st = 12.0 * (note_hz.max(20.0) / 261.6).log2();
            fc *= 2.0f32.powf(kt_st * params.key_track / 12.0);
        }
        fc += cutoff_mod * params.env_amount * 10000.0;
        fc = fc.clamp(20.0, sr * 0.49);

        let k = params.resonance * 4.0 * params.res_limit;
        let g = 1.0 - (-2.0 * PI * fc / sr).exp();
        let drive = 1.0 + params.drive * 8.0;

        let s = &mut self.ladder.s;

        let x = if drive > 1.01 {
            (input * drive).tanh()
        } else {
            input
        };

        let u = x - k * s[3];
        s[0] += g * (u.tanh() - s[0].tanh());
        s[1] += g * (s[0].tanh() - s[1].tanh());
        s[2] += g * (s[1].tanh() - s[2].tanh());
        s[3] += g * (s[2].tanh() - s[3].tanh());

        s[3]
    }

    // --- Comb ---
    #[inline]
    fn process_comb(
        &mut self,
        input: f32,
        params: &FusionFilterParams,
        note_hz: f32,
        sr: f32,
    ) -> f32 {
        // Delay time based on note frequency (for pitch-tracking comb)
        let delay_samples = (sr / note_hz.max(20.0)) as usize;
        let delay_samples = delay_samples.clamp(1, COMB_MAX_DELAY - 1);

        let c = &mut self.comb;
        let read_pos = (c.write_pos + COMB_MAX_DELAY - delay_samples) % COMB_MAX_DELAY;
        let delayed = c.buffer[read_pos];

        let feedback = params.resonance * 0.95; // limit to prevent blowup
        let output = input + delayed * feedback;

        c.buffer[c.write_pos] = output;
        c.write_pos = (c.write_pos + 1) % COMB_MAX_DELAY;

        output
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
    fn test_filter_type_parse() {
        assert_eq!(FusionFilterType::from_str("svf"), FusionFilterType::Svf);
        assert_eq!(FusionFilterType::from_str("ladder"), FusionFilterType::Ladder);
        assert_eq!(FusionFilterType::from_str("comb"), FusionFilterType::Comb);
        assert_eq!(FusionFilterType::from_str("off"), FusionFilterType::Off);
    }

    #[test]
    fn test_svf_lowpass_attenuates_highs() {
        let mut flt = FusionFilter::new();
        let mut params = FusionFilterParams::default();
        params.cutoff = 200.0; // very low cutoff
        params.svf_mode = SvfMode::LowPass;

        // Feed a 5kHz signal
        let freq = 5000.0;
        let mut input_energy = 0.0f32;
        let mut output_energy = 0.0f32;
        for i in 0..1024 {
            let input = (i as f32 / SR * freq * 2.0 * PI).sin();
            let output = flt.process_sample(input, &params, 0.0, 440.0, SR);
            input_energy += input * input;
            output_energy += output * output;
        }

        assert!(output_energy < input_energy * 0.1,
            "LP200 should attenuate 5kHz: in={} out={}", input_energy, output_energy);
    }

    #[test]
    fn test_svf_passes_low_freq() {
        let mut flt = FusionFilter::new();
        let mut params = FusionFilterParams::default();
        params.cutoff = 10000.0;
        params.svf_mode = SvfMode::LowPass;

        // Feed a 100Hz signal (well below cutoff)
        let freq = 100.0;
        let mut input_energy = 0.0f32;
        let mut output_energy = 0.0f32;
        for i in 0..2048 {
            let input = (i as f32 / SR * freq * 2.0 * PI).sin();
            let output = flt.process_sample(input, &params, 0.0, 440.0, SR);
            input_energy += input * input;
            output_energy += output * output;
        }

        // Should pass through mostly unchanged (within 3dB)
        let ratio = output_energy / input_energy.max(0.001);
        assert!(ratio > 0.5, "LP10k should pass 100Hz: ratio={}", ratio);
    }

    #[test]
    fn test_ladder_self_oscillation() {
        let mut flt = FusionFilter::new();
        let mut params = FusionFilterParams::default();
        params.filter_type = FusionFilterType::Ladder;
        params.cutoff = 1000.0;
        params.resonance = 1.0; // max resonance
        params.res_limit = 1.0;

        // Kick with impulse burst to excite self-oscillation
        for _ in 0..16 {
            let _ = flt.process_sample(0.5, &params, 0.0, 440.0, SR);
        }

        // Feed silence — should self-oscillate at cutoff frequency
        let mut max_abs = 0.0f32;
        for _ in 0..8192 {
            let out = flt.process_sample(0.0, &params, 0.0, 440.0, SR);
            max_abs = max_abs.max(out.abs());
        }
        assert!(max_abs > 0.001, "Ladder at max Q should self-oscillate: max={}", max_abs);
    }

    #[test]
    fn test_comb_produces_output() {
        let mut flt = FusionFilter::new();
        let mut params = FusionFilterParams::default();
        params.filter_type = FusionFilterType::Comb;
        params.resonance = 0.5;

        let mut max_abs = 0.0f32;
        for i in 0..512 {
            let input = if i < 10 { 1.0 } else { 0.0 }; // impulse
            let out = flt.process_sample(input, &params, 0.0, 440.0, SR);
            max_abs = max_abs.max(out.abs());
        }
        assert!(max_abs > 0.1, "Comb should produce output from impulse: max={}", max_abs);
    }

    #[test]
    fn test_off_passthrough() {
        let mut flt = FusionFilter::new();
        let params = FusionFilterParams { filter_type: FusionFilterType::Off, ..Default::default() };

        for i in 0..100 {
            let input = (i as f32 * 0.1).sin();
            let output = flt.process_sample(input, &params, 0.0, 440.0, SR);
            assert!((input - output).abs() < 0.001, "Off should passthrough");
        }
    }

    #[test]
    fn test_reset_clears_state() {
        let mut flt = FusionFilter::new();
        let params = FusionFilterParams::default();

        // Process some audio
        for i in 0..100 {
            flt.process_sample((i as f32 * 0.5).sin(), &params, 0.0, 440.0, SR);
        }

        // Reset
        flt.reset();

        // First sample after reset should be near zero for near-zero input
        let out = flt.process_sample(0.001, &params, 0.0, 440.0, SR);
        assert!(out.abs() < 0.1, "After reset, output should be small: {}", out);
    }
}
