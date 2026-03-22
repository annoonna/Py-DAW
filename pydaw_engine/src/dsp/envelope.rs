// ==========================================================================
// ADSR Envelope Generator — Sample-accurate amplitude shaping
// ==========================================================================
// v0.0.20.667 — Phase R1B
//
// Used by: Every instrument (Sampler, AETERNA, Fusion, DrumMachine)
// States: Idle → Attack → Decay → Sustain → Release → Idle
// All transitions are sample-accurate — no quantization to buffer boundaries.
// ==========================================================================

/// Envelope state machine states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnvState {
    Idle,
    Attack,
    Decay,
    Sustain,
    Release,
}

/// ADSR Envelope Generator.
///
/// Times are in seconds. The envelope runs at sample rate.
/// Output is 0.0–1.0 (linear amplitude).
///
/// Attack shape: exponential approach to 1.0
/// Decay shape: exponential decay to sustain level
/// Release shape: exponential decay to 0.0
#[derive(Debug, Clone)]
pub struct AdsrEnvelope {
    state: EnvState,
    output: f32,
    /// Attack time coefficient (per sample).
    attack_coeff: f32,
    /// Decay time coefficient.
    decay_coeff: f32,
    /// Release time coefficient.
    release_coeff: f32,
    /// Sustain level (0.0 – 1.0).
    sustain: f32,
    /// Target for attack phase (slightly above 1.0 for exponential overshoot).
    attack_target: f32,
    /// Sample rate.
    sample_rate: f32,
    /// Raw parameter values (for recalculation).
    attack_sec: f32,
    decay_sec: f32,
    release_sec: f32,
}

impl AdsrEnvelope {
    /// Create a new ADSR envelope.
    ///
    /// - `attack`: Attack time in seconds (0.001 – 10.0)
    /// - `decay`: Decay time in seconds (0.001 – 10.0)
    /// - `sustain`: Sustain level (0.0 – 1.0)
    /// - `release`: Release time in seconds (0.001 – 10.0)
    /// - `sample_rate`: Sample rate in Hz
    pub fn new(attack: f32, decay: f32, sustain: f32, release: f32, sample_rate: f32) -> Self {
        let mut env = Self {
            state: EnvState::Idle,
            output: 0.0,
            attack_coeff: 0.0,
            decay_coeff: 0.0,
            release_coeff: 0.0,
            sustain: sustain.clamp(0.0, 1.0),
            attack_target: 1.2, // Overshoot for natural exponential curve
            sample_rate,
            attack_sec: attack,
            decay_sec: decay,
            release_sec: release,
        };
        env.recalc_coefficients();
        env
    }

    /// Update envelope parameters (can be called during playback).
    pub fn set_params(&mut self, attack: f32, decay: f32, sustain: f32, release: f32) {
        self.attack_sec = attack;
        self.decay_sec = decay;
        self.sustain = sustain.clamp(0.0, 1.0);
        self.release_sec = release;
        self.recalc_coefficients();
    }

    /// Set sample rate (call on audio config change).
    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        self.sample_rate = sample_rate;
        self.recalc_coefficients();
    }

    fn recalc_coefficients(&mut self) {
        self.attack_coeff = Self::time_to_coeff(self.attack_sec, self.sample_rate);
        self.decay_coeff = Self::time_to_coeff(self.decay_sec, self.sample_rate);
        self.release_coeff = Self::time_to_coeff(self.release_sec, self.sample_rate);
    }

    /// Convert time in seconds to a one-pole coefficient.
    /// Coefficient = exp(-1 / (time * sample_rate))
    #[inline]
    fn time_to_coeff(time_sec: f32, sample_rate: f32) -> f32 {
        let samples = (time_sec.max(0.001) * sample_rate).max(1.0);
        (-1.0 / samples).exp()
    }

    /// Trigger note-on (start Attack phase).
    pub fn note_on(&mut self) {
        self.state = EnvState::Attack;
        // Don't reset output — allows re-trigger without click
    }

    /// Trigger note-off (start Release phase).
    pub fn note_off(&mut self) {
        if self.state != EnvState::Idle {
            self.state = EnvState::Release;
        }
    }

    /// Force the envelope to Idle (immediate stop).
    pub fn kill(&mut self) {
        self.state = EnvState::Idle;
        self.output = 0.0;
    }

    /// Get the current envelope state.
    pub fn state(&self) -> EnvState {
        self.state
    }

    /// Check if the envelope is active (not Idle).
    #[inline]
    pub fn is_active(&self) -> bool {
        self.state != EnvState::Idle
    }

    /// Get the current output value without advancing.
    #[inline]
    pub fn current(&self) -> f32 {
        self.output
    }

    /// Process one sample and return the envelope value (0.0–1.0).
    ///
    /// **AUDIO THREAD** — inline, zero-alloc.
    #[inline]
    pub fn process(&mut self) -> f32 {
        match self.state {
            EnvState::Idle => {
                self.output = 0.0;
            }

            EnvState::Attack => {
                // Exponential approach to attack_target (overshoots 1.0)
                self.output = self.attack_target
                    + (self.output - self.attack_target) * self.attack_coeff;
                if self.output >= 1.0 {
                    self.output = 1.0;
                    self.state = EnvState::Decay;
                }
            }

            EnvState::Decay => {
                // Exponential decay towards sustain level
                self.output =
                    self.sustain + (self.output - self.sustain) * self.decay_coeff;
                // Transition to Sustain when close enough
                if (self.output - self.sustain).abs() < 0.0001 {
                    self.output = self.sustain;
                    self.state = EnvState::Sustain;
                }
            }

            EnvState::Sustain => {
                self.output = self.sustain;
            }

            EnvState::Release => {
                // Exponential decay towards 0.0
                self.output *= self.release_coeff;
                if self.output < 0.0001 {
                    self.output = 0.0;
                    self.state = EnvState::Idle;
                }
            }
        }

        self.output
    }

    /// Process a block of samples, writing envelope values into the output slice.
    /// Useful for applying envelope to an entire buffer in one call.
    #[inline]
    pub fn process_block(&mut self, output: &mut [f32]) {
        for sample in output.iter_mut() {
            *sample = self.process();
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
    fn test_idle_is_zero() {
        let mut env = AdsrEnvelope::new(0.01, 0.1, 0.5, 0.2, 44100.0);
        assert_eq!(env.state(), EnvState::Idle);
        assert_eq!(env.process(), 0.0);
    }

    #[test]
    fn test_attack_reaches_one() {
        let mut env = AdsrEnvelope::new(0.01, 0.1, 0.5, 0.2, 44100.0);
        env.note_on();
        // Run enough samples for 10ms attack
        let mut reached_one = false;
        for _ in 0..2000 {
            let val = env.process();
            if val >= 0.99 {
                reached_one = true;
                break;
            }
        }
        assert!(reached_one, "Attack should reach ~1.0 within 2000 samples at 44100Hz (10ms attack)");
    }

    #[test]
    fn test_decay_reaches_sustain() {
        let mut env = AdsrEnvelope::new(0.001, 0.01, 0.5, 0.2, 44100.0);
        env.note_on();
        // Run through attack + decay
        for _ in 0..10000 {
            env.process();
        }
        let val = env.current();
        assert!(
            (val - 0.5).abs() < 0.05,
            "After attack+decay, should be near sustain (0.5), got {}",
            val
        );
        assert_eq!(env.state(), EnvState::Sustain);
    }

    #[test]
    fn test_release_reaches_zero() {
        let mut env = AdsrEnvelope::new(0.001, 0.01, 0.5, 0.01, 44100.0);
        env.note_on();
        for _ in 0..5000 {
            env.process();
        }
        env.note_off();
        assert_eq!(env.state(), EnvState::Release);

        for _ in 0..5000 {
            env.process();
        }
        assert_eq!(env.state(), EnvState::Idle);
        assert!(env.current() < 0.001);
    }

    #[test]
    fn test_kill_immediate() {
        let mut env = AdsrEnvelope::new(0.1, 0.1, 0.5, 0.1, 44100.0);
        env.note_on();
        for _ in 0..100 {
            env.process();
        }
        env.kill();
        assert_eq!(env.state(), EnvState::Idle);
        assert_eq!(env.current(), 0.0);
    }
}
