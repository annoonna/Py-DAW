// ==========================================================================
// Utility — Gain, Phase Invert, Mono, DC Blocker, Pan
// ==========================================================================
// v0.0.20.669 — Phase R3B
//
// Reference: pydaw/audio/utility_fx.py UtilityFx
//
// Swiss-army-knife channel utility. Every DAW needs this as a basic
// building block. All processing is sample-level, zero-alloc.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::math::db_to_linear;

/// Utility parameters.
#[derive(Debug, Clone, Copy)]
pub struct UtilityParams {
    /// Gain in dB (-96 to +24)
    pub gain_db: f32,
    /// Pan position (-1.0 = full left, 0.0 = center, +1.0 = full right)
    pub pan: f32,
    /// Invert phase of left channel
    pub phase_invert_l: bool,
    /// Invert phase of right channel
    pub phase_invert_r: bool,
    /// Sum to mono
    pub mono: bool,
    /// Enable DC blocking filter
    pub dc_block: bool,
    /// Swap L/R channels
    pub channel_swap: bool,
}

impl Default for UtilityParams {
    fn default() -> Self {
        Self {
            gain_db: 0.0,
            pan: 0.0,
            phase_invert_l: false,
            phase_invert_r: false,
            mono: false,
            dc_block: true,
            channel_swap: false,
        }
    }
}

/// Channel Utility effect.
pub struct Utility {
    params: UtilityParams,
    sample_rate: f32,
    // DC blocker state (1-pole HP at ~5Hz)
    dc_x_l: f32,
    dc_y_l: f32,
    dc_x_r: f32,
    dc_y_r: f32,
}

impl Utility {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: UtilityParams::default(),
            sample_rate,
            dc_x_l: 0.0,
            dc_y_l: 0.0,
            dc_x_r: 0.0,
            dc_y_r: 0.0,
        }
    }

    pub fn set_params(&mut self, params: UtilityParams) {
        self.params = params;
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    pub fn reset(&mut self) {
        self.dc_x_l = 0.0;
        self.dc_y_l = 0.0;
        self.dc_x_r = 0.0;
        self.dc_y_r = 0.0;
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let gain_lin = if self.params.gain_db > -95.0 {
            db_to_linear(self.params.gain_db.clamp(-96.0, 24.0))
        } else {
            0.0
        };

        // Constant-power pan law
        let pan = self.params.pan.clamp(-1.0, 1.0);
        let pan_angle = (pan + 1.0) * 0.25 * std::f32::consts::FRAC_PI_2 * 2.0;
        let pan_l = pan_angle.cos();
        let pan_r = pan_angle.sin();

        let phase_l = if self.params.phase_invert_l { -1.0f32 } else { 1.0 };
        let phase_r = if self.params.phase_invert_r { -1.0f32 } else { 1.0 };
        let mono = self.params.mono;
        let dc_block = self.params.dc_block;
        let swap = self.params.channel_swap;

        // DC blocker coefficient (~5Hz HP)
        let dc_coeff = (1.0 - 2.0 * std::f32::consts::PI * 5.0 / self.sample_rate.max(1.0))
            .clamp(0.9, 0.9999);

        let mut dx_l = self.dc_x_l;
        let mut dy_l = self.dc_y_l;
        let mut dx_r = self.dc_x_r;
        let mut dy_r = self.dc_y_r;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let mut l = buffer.data[idx];
            let mut r = buffer.data[idx + 1];

            // Channel swap
            if swap {
                std::mem::swap(&mut l, &mut r);
            }

            // Mono sum
            if mono {
                let m = (l + r) * 0.5;
                l = m;
                r = m;
            }

            // Phase invert
            l *= phase_l;
            r *= phase_r;

            // Gain + pan
            l = l * gain_lin * pan_l;
            r = r * gain_lin * pan_r;

            // DC blocking filter (1-pole HP)
            if dc_block {
                let new_dy_l = l - dx_l + dc_coeff * dy_l;
                dx_l = l;
                l = new_dy_l;
                dy_l = new_dy_l;

                let new_dy_r = r - dx_r + dc_coeff * dy_r;
                dx_r = r;
                r = new_dy_r;
                dy_r = new_dy_r;
            }

            buffer.data[idx] = l;
            buffer.data[idx + 1] = r;
        }

        self.dc_x_l = dx_l;
        self.dc_y_l = dy_l;
        self.dc_x_r = dx_r;
        self.dc_y_r = dy_r;
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unity_passthrough() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams {
            gain_db: 0.0,
            pan: 0.0,
            dc_block: false,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        util.process(&mut buf);

        // Should be approximately passthrough (constant-power pan at center ≈ 0.707)
        // At center pan: L = input * cos(π/4) ≈ input * 0.707
        let expected_l = 0.42 * (std::f32::consts::FRAC_PI_4).cos();
        assert!((buf.data[254] - expected_l).abs() < 0.01,
            "Expected ~{}, got {}", expected_l, buf.data[254]);
    }

    #[test]
    fn test_mute_at_minus_96() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams { gain_db: -96.0, dc_block: false, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = 0.5;
        }
        util.process(&mut buf);

        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val < 0.001, "At -96dB signal should be nearly silent, got max={}", max_val);
    }

    #[test]
    fn test_mono_sum() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams { mono: true, dc_block: false, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.6;
            buf.data[i * 2 + 1] = -0.2;
        }
        util.process(&mut buf);

        // After mono sum, L and R should be equal
        for i in 0..128 {
            let diff = (buf.data[i * 2] - buf.data[i * 2 + 1]).abs();
            assert!(diff < 0.01, "Mono should make L=R, diff={}", diff);
        }
    }

    #[test]
    fn test_phase_invert() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams {
            phase_invert_l: true,
            phase_invert_r: false,
            dc_block: false,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(64, 2);
        for i in 0..64 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = 0.5;
        }
        util.process(&mut buf);

        // L should be inverted, R should stay positive (both scaled by pan law)
        assert!(buf.data[0] < 0.0, "Left should be inverted");
        assert!(buf.data[1] > 0.0, "Right should not be inverted");
    }

    #[test]
    fn test_channel_swap() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams {
            channel_swap: true,
            dc_block: false,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(64, 2);
        for i in 0..64 {
            buf.data[i * 2] = 0.9;      // L
            buf.data[i * 2 + 1] = -0.1; // R
        }
        util.process(&mut buf);

        // After swap, what was R should be on L side and vice versa
        // (scaled by pan law, but the relative relationship changes)
        // The original L (0.9) goes to R position and R (-0.1) goes to L
        // This is hard to test exactly due to pan law, but L should be < R in magnitude
        // since original R was -0.1 (small) and original L was 0.9 (large)
        assert!(buf.data[0].abs() < buf.data[1].abs(),
            "After swap, L should be smaller: L={}, R={}", buf.data[0], buf.data[1]);
    }

    #[test]
    fn test_dc_blocker() {
        let mut util = Utility::new(44100.0);
        util.set_params(UtilityParams { dc_block: true, ..Default::default() });

        // Signal with DC offset
        let mut buf = AudioBuffer::new(44100, 2); // 1 second
        for i in 0..44100 {
            buf.data[i * 2] = 0.5; // pure DC
            buf.data[i * 2 + 1] = 0.5;
        }
        util.process(&mut buf);

        // After 1 second, DC should be mostly removed
        let last_l = buf.data[44098].abs();
        assert!(last_l < 0.05, "DC blocker should remove DC, got {}", last_l);
    }
}
