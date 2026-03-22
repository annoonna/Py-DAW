// ==========================================================================
// Fusion Envelopes — ADSR, AR, AD, Pluck with velocity scaling
// ==========================================================================
// v0.0.20.693 — Phase R10B
//
// Envelope types for the Fusion synthesizer:
//   - ADSR: Standard Attack-Decay-Sustain-Release
//   - AR: Attack-Release (no sustain, auto-release after attack peak)
//   - AD: Attack-Decay (no sustain, no release — one-shot)
//   - Pluck: Instant attack, exponential decay (Karplus-Strong style)
//
// All envelopes share the FusionEnvelope struct with a type discriminant.
// Velocity scaling is built in: velocity affects peak level.
//
// Rules:
//   ✅ process() is #[inline] and zero-alloc
//   ✅ All state in fixed-size struct
//   ❌ NO allocations in audio thread
// ==========================================================================

// ---------------------------------------------------------------------------
// Envelope Type
// ---------------------------------------------------------------------------

/// Available envelope types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FusionEnvType {
    Adsr,
    Ar,
    Ad,
    Pluck,
}

impl FusionEnvType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "adsr" | "ADSR" => Self::Adsr,
            "ar" | "AR" => Self::Ar,
            "ad" | "AD" => Self::Ad,
            "pluck" | "Pluck" => Self::Pluck,
            _ => Self::Adsr,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Adsr => "adsr",
            Self::Ar => "ar",
            Self::Ad => "ad",
            Self::Pluck => "pluck",
        }
    }
}

// ---------------------------------------------------------------------------
// Envelope State
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum EnvPhase {
    Idle,
    Attack,
    Decay,
    Sustain,
    Release,
}

// ---------------------------------------------------------------------------
// Envelope Parameters
// ---------------------------------------------------------------------------

/// Shared envelope parameters.
#[derive(Debug, Clone)]
pub struct FusionEnvParams {
    pub env_type: FusionEnvType,
    /// Attack time in seconds (0.001–10).
    pub attack: f32,
    /// Decay time in seconds (0.001–10).
    pub decay: f32,
    /// Sustain level (0–1).
    pub sustain: f32,
    /// Release time in seconds (0.001–30).
    pub release: f32,
    /// Velocity sensitivity (0–1). 1.0 = full velocity scaling.
    pub velocity_sens: f32,
    /// Pluck decay time in seconds.
    pub pluck_decay: f32,
}

impl Default for FusionEnvParams {
    fn default() -> Self {
        Self {
            env_type: FusionEnvType::Adsr,
            attack: 0.005,
            decay: 0.2,
            sustain: 0.7,
            release: 0.3,
            velocity_sens: 0.8,
            pluck_decay: 0.5,
        }
    }
}

// ---------------------------------------------------------------------------
// Fusion Envelope
// ---------------------------------------------------------------------------

/// Unified envelope generator for Fusion voices.
pub struct FusionEnvelope {
    phase: EnvPhase,
    output: f32,
    /// Velocity-scaled peak level.
    peak: f32,
    /// Per-sample coefficient for current phase.
    coeff: f32,
    /// Target for current phase.
    target: f32,
    sample_rate: f32,
}

impl FusionEnvelope {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            phase: EnvPhase::Idle,
            output: 0.0,
            peak: 1.0,
            coeff: 0.0,
            target: 0.0,
            sample_rate,
        }
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    /// Trigger the envelope (note-on).
    pub fn gate_on(&mut self, velocity: f32, params: &FusionEnvParams) {
        // Velocity scaling
        self.peak = 1.0 - params.velocity_sens * (1.0 - velocity.clamp(0.0, 1.0));

        match params.env_type {
            FusionEnvType::Adsr | FusionEnvType::Ar => {
                self.phase = EnvPhase::Attack;
                self.target = self.peak * 1.05; // overshoot for exponential
                self.coeff = self.time_to_coeff(params.attack);
            }
            FusionEnvType::Ad => {
                self.phase = EnvPhase::Attack;
                self.target = self.peak * 1.05;
                self.coeff = self.time_to_coeff(params.attack);
            }
            FusionEnvType::Pluck => {
                // Instant attack
                self.output = self.peak;
                self.phase = EnvPhase::Decay;
                self.target = 0.0;
                self.coeff = self.time_to_coeff(params.pluck_decay);
            }
        }
    }

    /// Release the envelope (note-off).
    pub fn gate_off(&mut self, params: &FusionEnvParams) {
        match params.env_type {
            FusionEnvType::Adsr | FusionEnvType::Ar => {
                if self.phase != EnvPhase::Idle {
                    self.phase = EnvPhase::Release;
                    self.target = 0.0;
                    self.coeff = self.time_to_coeff(params.release);
                }
            }
            FusionEnvType::Ad | FusionEnvType::Pluck => {
                // AD and Pluck ignore note-off (one-shot)
            }
        }
    }

    /// Kill immediately.
    pub fn kill(&mut self) {
        self.phase = EnvPhase::Idle;
        self.output = 0.0;
    }

    /// Is the envelope still producing output?
    #[inline]
    pub fn is_active(&self) -> bool {
        self.phase != EnvPhase::Idle
    }

    /// Current output level (0–1).
    #[inline]
    pub fn current(&self) -> f32 {
        self.output
    }

    /// Process one sample. Returns envelope level (0–1).
    #[inline]
    pub fn process(&mut self, params: &FusionEnvParams) -> f32 {
        match self.phase {
            EnvPhase::Idle => {
                return 0.0;
            }
            EnvPhase::Attack => {
                self.output += (self.target - self.output) * self.coeff;
                if self.output >= self.peak * 0.99 {
                    self.output = self.peak;
                    match params.env_type {
                        FusionEnvType::Adsr => {
                            self.phase = EnvPhase::Decay;
                            self.target = params.sustain * self.peak;
                            self.coeff = self.time_to_coeff(params.decay);
                        }
                        FusionEnvType::Ar => {
                            // AR: go directly to release after attack peak
                            self.phase = EnvPhase::Release;
                            self.target = 0.0;
                            self.coeff = self.time_to_coeff(params.release);
                        }
                        FusionEnvType::Ad => {
                            self.phase = EnvPhase::Decay;
                            self.target = 0.0;
                            self.coeff = self.time_to_coeff(params.decay);
                        }
                        FusionEnvType::Pluck => {} // shouldn't happen
                    }
                }
            }
            EnvPhase::Decay => {
                self.output += (self.target - self.output) * self.coeff;
                match params.env_type {
                    FusionEnvType::Adsr => {
                        if (self.output - self.target).abs() < 0.001 {
                            self.output = self.target;
                            self.phase = EnvPhase::Sustain;
                        }
                    }
                    FusionEnvType::Ad | FusionEnvType::Pluck => {
                        if self.output < 0.001 {
                            self.output = 0.0;
                            self.phase = EnvPhase::Idle;
                        }
                    }
                    _ => {}
                }
            }
            EnvPhase::Sustain => {
                // Hold at sustain level until gate_off
                self.output = params.sustain * self.peak;
            }
            EnvPhase::Release => {
                self.output += (0.0 - self.output) * self.coeff;
                if self.output < 0.001 {
                    self.output = 0.0;
                    self.phase = EnvPhase::Idle;
                }
            }
        }

        self.output
    }

    /// Convert time in seconds to one-pole coefficient.
    #[inline]
    fn time_to_coeff(&self, time_sec: f32) -> f32 {
        let samples = (time_sec.max(0.001) * self.sample_rate).max(1.0);
        1.0 - (-5.0 / samples).exp() // ~99.3% in time_sec
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
    fn test_env_type_parse() {
        assert_eq!(FusionEnvType::from_str("adsr"), FusionEnvType::Adsr);
        assert_eq!(FusionEnvType::from_str("ar"), FusionEnvType::Ar);
        assert_eq!(FusionEnvType::from_str("ad"), FusionEnvType::Ad);
        assert_eq!(FusionEnvType::from_str("pluck"), FusionEnvType::Pluck);
    }

    #[test]
    fn test_adsr_lifecycle() {
        let mut env = FusionEnvelope::new(SR);
        let params = FusionEnvParams::default();

        assert!(!env.is_active());

        // Gate on
        env.gate_on(1.0, &params);
        assert!(env.is_active());

        // Attack phase — should ramp up
        let mut max_val = 0.0f32;
        for _ in 0..2000 {
            let v = env.process(&params);
            max_val = max_val.max(v);
        }
        assert!(max_val > 0.5, "Should reach sustain: max={}", max_val);

        // Gate off → release
        env.gate_off(&params);
        for _ in 0..50000 {
            env.process(&params);
            if !env.is_active() { break; }
        }
        assert!(!env.is_active(), "Should reach idle after release");
    }

    #[test]
    fn test_pluck_instant_attack() {
        let mut env = FusionEnvelope::new(SR);
        let mut params = FusionEnvParams::default();
        params.env_type = FusionEnvType::Pluck;
        params.pluck_decay = 0.1;

        env.gate_on(1.0, &params);

        // First sample should be near peak
        let v0 = env.process(&params);
        assert!(v0 > 0.5, "Pluck should start near peak: {}", v0);

        // Should decay to idle
        for _ in 0..20000 {
            env.process(&params);
            if !env.is_active() { break; }
        }
        assert!(!env.is_active(), "Pluck should reach idle");
    }

    #[test]
    fn test_ad_one_shot() {
        let mut env = FusionEnvelope::new(SR);
        let mut params = FusionEnvParams::default();
        params.env_type = FusionEnvType::Ad;
        params.attack = 0.01;
        params.decay = 0.05;

        env.gate_on(1.0, &params);

        // Note off should be ignored (one-shot)
        for _ in 0..500 {
            env.process(&params);
        }
        env.gate_off(&params);
        assert!(env.is_active(), "AD should ignore note-off");

        // Eventually reaches idle
        for _ in 0..50000 {
            env.process(&params);
            if !env.is_active() { break; }
        }
        assert!(!env.is_active(), "AD should eventually reach idle");
    }

    #[test]
    fn test_velocity_scaling() {
        let mut env_loud = FusionEnvelope::new(SR);
        let mut env_soft = FusionEnvelope::new(SR);
        let params = FusionEnvParams::default();

        env_loud.gate_on(1.0, &params);
        env_soft.gate_on(0.2, &params);

        let mut max_loud = 0.0f32;
        let mut max_soft = 0.0f32;
        for _ in 0..2000 {
            max_loud = max_loud.max(env_loud.process(&params));
            max_soft = max_soft.max(env_soft.process(&params));
        }

        assert!(max_loud > max_soft, "Loud should be louder: {} vs {}", max_loud, max_soft);
    }

    #[test]
    fn test_kill_immediate() {
        let mut env = FusionEnvelope::new(SR);
        let params = FusionEnvParams::default();

        env.gate_on(1.0, &params);
        for _ in 0..100 {
            env.process(&params);
        }
        assert!(env.is_active());

        env.kill();
        assert!(!env.is_active());
        assert!(env.current().abs() < 0.001);
    }
}
