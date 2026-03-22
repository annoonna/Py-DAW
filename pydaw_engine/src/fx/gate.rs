// ==========================================================================
// Gate — Noise gate with threshold, attack, hold, release
// ==========================================================================
// v0.0.20.669 — Phase R3B
//
// Reference: pydaw/audio/utility_fx.py GateFx
//
// Architecture: Peak envelope follower → gate logic with hold phase →
// smoothed gain transitions. Optional sidechain input buffer.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::math::db_to_linear;

/// Gate parameters.
#[derive(Debug, Clone, Copy)]
pub struct GateParams {
    /// Gate threshold in dB (-80 to 0)
    pub threshold_db: f32,
    /// Attack time in ms (0.01 – 50)
    pub attack_ms: f32,
    /// Hold time in ms (0 – 500)
    pub hold_ms: f32,
    /// Release time in ms (1 – 2000)
    pub release_ms: f32,
    /// Attenuation when closed in dB (-80 to -1)
    pub range_db: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for GateParams {
    fn default() -> Self {
        Self {
            threshold_db: -40.0,
            attack_ms: 0.5,
            hold_ms: 50.0,
            release_ms: 100.0,
            range_db: -80.0,
            mix: 1.0,
        }
    }
}

/// Noise Gate effect.
pub struct Gate {
    params: GateParams,
    sample_rate: f32,
    env: f32,           // envelope follower state
    gate_gain: f32,     // current gate gain (0..1)
    hold_counter: usize, // samples remaining in hold phase
}

impl Gate {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: GateParams::default(),
            sample_rate,
            env: 0.0,
            gate_gain: 0.0,
            hold_counter: 0,
        }
    }

    pub fn set_params(&mut self, params: GateParams) {
        self.params = params;
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    pub fn reset(&mut self) {
        self.env = 0.0;
        self.gate_gain = 0.0;
        self.hold_counter = 0;
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    ///
    /// `sidechain`: Optional external sidechain buffer for detection.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        self.process_with_sidechain(buffer, None);
    }

    /// Process with optional external sidechain buffer.
    #[inline]
    pub fn process_with_sidechain(
        &mut self,
        buffer: &mut AudioBuffer,
        sidechain: Option<&AudioBuffer>,
    ) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        if mix < 0.001 { return; }

        let threshold_lin = db_to_linear(self.params.threshold_db.clamp(-80.0, 0.0));
        let range_lin = db_to_linear(self.params.range_db.clamp(-80.0, -1.0));
        let attack_ms = self.params.attack_ms.max(0.01);
        let release_ms = self.params.release_ms.max(1.0);
        let attack_coeff = (-1.0 / (self.sample_rate * attack_ms * 0.001)).exp();
        let release_coeff = (-1.0 / (self.sample_rate * release_ms * 0.001)).exp();
        let hold_samps = (self.params.hold_ms.max(0.0) * 0.001 * self.sample_rate) as usize;

        let mut env = self.env;
        let mut gate_gain = self.gate_gain;
        let mut hold_counter = self.hold_counter;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            // Detect level from sidechain or main input
            let level = if let Some(sc) = sidechain {
                let sc_idx = frame * 2;
                if sc_idx + 1 < sc.data.len() {
                    sc.data[sc_idx].abs().max(sc.data[sc_idx + 1].abs())
                } else {
                    buffer.data[idx].abs().max(buffer.data[idx + 1].abs())
                }
            } else {
                buffer.data[idx].abs().max(buffer.data[idx + 1].abs())
            };

            // Peak envelope follower
            if level > env {
                env = level;
            } else {
                env = release_coeff * env + (1.0 - release_coeff) * level;
            }

            // Gate logic
            let target = if env >= threshold_lin {
                hold_counter = hold_samps;
                1.0
            } else if hold_counter > 0 {
                hold_counter -= 1;
                1.0
            } else {
                range_lin
            };

            // Smooth gain transitions
            if target > gate_gain {
                gate_gain = (1.0 - attack_coeff) * target + attack_coeff * gate_gain;
            } else {
                gate_gain = (1.0 - release_coeff) * target + release_coeff * gate_gain;
            }

            // Apply
            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];
            let gated_l = in_l * gate_gain;
            let gated_r = in_r * gate_gain;
            buffer.data[idx] = in_l * (1.0 - mix) + gated_l * mix;
            buffer.data[idx + 1] = in_r * (1.0 - mix) + gated_r * mix;
        }

        self.env = env;
        self.gate_gain = gate_gain;
        self.hold_counter = hold_counter;
    }

    /// Get current gate gain for metering (0.0 = fully closed, 1.0 = open).
    pub fn current_gain(&self) -> f32 {
        self.gate_gain
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gate_silence_below_threshold() {
        let mut gate = Gate::new(44100.0);
        gate.set_params(GateParams {
            threshold_db: -20.0,
            range_db: -80.0,
            attack_ms: 0.01,
            hold_ms: 0.0,
            release_ms: 1.0,
            mix: 1.0,
        });

        // Process some silence first to let gate close
        let mut buf = AudioBuffer::new(4096, 2);
        gate.process(&mut buf);

        // Now process quiet signal (below threshold)
        let mut buf = AudioBuffer::new(512, 2);
        for i in 0..512 {
            buf.data[i * 2] = 0.01; // -40 dB
            buf.data[i * 2 + 1] = 0.01;
        }
        gate.process(&mut buf);

        // Output should be heavily attenuated
        let max_out = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_out < 0.05, "Gate should attenuate below threshold, got max={}", max_out);
    }

    #[test]
    fn test_gate_passes_above_threshold() {
        let mut gate = Gate::new(44100.0);
        gate.set_params(GateParams {
            threshold_db: -40.0,
            range_db: -80.0,
            attack_ms: 0.01,
            hold_ms: 10.0,
            release_ms: 10.0,
            mix: 1.0,
        });

        // Loud signal (well above -40dB threshold)
        let mut buf = AudioBuffer::new(2048, 2);
        for i in 0..2048 {
            buf.data[i * 2] = 0.5; // ~ -6 dB
            buf.data[i * 2 + 1] = 0.5;
        }
        gate.process(&mut buf);

        // After attack, output should be close to input
        let last_l = buf.data[2046];
        assert!(last_l > 0.4, "Gate should pass signal above threshold, got {}", last_l);
    }

    #[test]
    fn test_gate_dry_passthrough() {
        let mut gate = Gate::new(44100.0);
        gate.set_params(GateParams { mix: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        gate.process(&mut buf);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }
}
