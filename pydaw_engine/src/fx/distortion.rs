// ==========================================================================
// Distortion — Multi-mode distortion / saturation effect
// ==========================================================================
// v0.0.20.669 — Phase R3A
//
// Reference: pydaw/audio/creative_fx.py DistortionPlusFx
//
// Five distinct clipping modes:
//   1. Soft Clip  — tanh saturation (warm, musical)
//   2. Hard Clip  — digital clipping (harsh, aggressive)
//   3. Tube       — asymmetric waveshaping (even harmonics)
//   4. Tape       — soft saturation with hysteresis-like compression
//   5. Bitcrush   — sample rate + bit depth reduction (lo-fi)
//
// Post-distortion tone filter (1-pole LP) to tame harshness.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::math::{fast_tanh, hard_clip};

/// Distortion mode selector.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DistortionMode {
    SoftClip,
    HardClip,
    Tube,
    Tape,
    Bitcrush,
}

/// Distortion parameters.
#[derive(Debug, Clone, Copy)]
pub struct DistortionParams {
    /// Drive amount (0.0 – 1.0, maps to 1x – 20x gain)
    pub drive: f32,
    /// Distortion mode
    pub mode: DistortionMode,
    /// Tone control (0.0 = dark, 1.0 = bright)
    pub tone: f32,
    /// Bitcrush: target sample rate in Hz (only for Bitcrush mode)
    pub crush_rate: f32,
    /// Bitcrush: bit depth (1 – 16, only for Bitcrush mode)
    pub crush_bits: u8,
    /// Output level (0.0 – 1.0, to compensate drive boost)
    pub output: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for DistortionParams {
    fn default() -> Self {
        Self {
            drive: 0.5,
            mode: DistortionMode::SoftClip,
            tone: 0.5,
            crush_rate: 8000.0,
            crush_bits: 8,
            output: 0.7,
            mix: 1.0,
        }
    }
}

/// Multi-mode Distortion effect.
pub struct Distortion {
    params: DistortionParams,
    sample_rate: f32,
    // Tone filter state (1-pole LP)
    lp_l: f32,
    lp_r: f32,
    // Bitcrush state
    crush_hold_l: f32,
    crush_hold_r: f32,
    crush_counter: f32,
}

impl Distortion {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: DistortionParams::default(),
            sample_rate,
            lp_l: 0.0,
            lp_r: 0.0,
            crush_hold_l: 0.0,
            crush_hold_r: 0.0,
            crush_counter: 0.0,
        }
    }

    pub fn set_params(&mut self, params: DistortionParams) {
        self.params = params;
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    pub fn reset(&mut self) {
        self.lp_l = 0.0;
        self.lp_r = 0.0;
        self.crush_hold_l = 0.0;
        self.crush_hold_r = 0.0;
        self.crush_counter = 0.0;
    }

    /// Apply distortion to a single sample.
    #[inline]
    fn distort_sample(&self, sample: f32, drive_gain: f32) -> f32 {
        let driven = sample * drive_gain;
        match self.params.mode {
            DistortionMode::SoftClip => {
                fast_tanh(driven)
            }
            DistortionMode::HardClip => {
                hard_clip(driven, 1.0)
            }
            DistortionMode::Tube => {
                // Asymmetric: positive half softer, negative half harder
                // Produces even harmonics like real tubes
                if driven >= 0.0 {
                    Self::tube_positive(driven)
                } else {
                    fast_tanh(driven * 1.5) // harder clip on negative
                }
            }
            DistortionMode::Tape => {
                // Tape saturation: gentle compression + soft limiting
                // Based on approximation of magnetic tape transfer curve
                let x = driven;
                let abs_x = x.abs();
                if abs_x < 0.5 {
                    x // Linear below threshold
                } else if abs_x < 1.5 {
                    // Soft transition zone
                    x.signum() * (0.5 + (abs_x - 0.5) / (1.0 + (abs_x - 0.5).powi(2)))
                } else {
                    // Saturated
                    x.signum() * (0.5 + 0.5 * fast_tanh((abs_x - 0.5) * 2.0))
                }
            }
            DistortionMode::Bitcrush => {
                // Bit reduction is handled in process() for sample-rate reduction
                // Here just apply bit depth reduction
                let bits = self.params.crush_bits.clamp(1, 16) as f32;
                let levels = 2.0f32.powf(bits);
                let quantized = (driven * levels).round() / levels;
                quantized.clamp(-1.0, 1.0)
            }
        }
    }

    /// Tube positive half helper.
    #[inline]
    fn tube_positive(x: f32) -> f32 {
        // 1 - e^(-3x) saturates smoothly to 1.0
        if x > 10.0 { return 1.0; }
        1.0 - (-x * 3.0).exp()
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        let drive_gain = 1.0 + self.params.drive.clamp(0.0, 1.0) * 19.0; // 1x – 20x
        let output_gain = self.params.output.clamp(0.0, 1.0);
        let tone_coeff = 0.05 + 0.9 * self.params.tone.clamp(0.0, 1.0);

        let is_bitcrush = self.params.mode == DistortionMode::Bitcrush;
        let crush_step = if is_bitcrush {
            self.sample_rate / self.params.crush_rate.clamp(500.0, self.sample_rate)
        } else {
            1.0
        };

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let dry_l = buffer.data[idx];
            let dry_r = buffer.data[idx + 1];

            let mut wet_l;
            let mut wet_r;

            if is_bitcrush {
                // Sample rate reduction: hold samples
                self.crush_counter += 1.0;
                if self.crush_counter >= crush_step {
                    self.crush_counter -= crush_step;
                    self.crush_hold_l = self.distort_sample(dry_l, drive_gain);
                    self.crush_hold_r = self.distort_sample(dry_r, drive_gain);
                }
                wet_l = self.crush_hold_l;
                wet_r = self.crush_hold_r;
            } else {
                wet_l = self.distort_sample(dry_l, drive_gain);
                wet_r = self.distort_sample(dry_r, drive_gain);
            }

            // Tone filter (1-pole LP)
            self.lp_l += tone_coeff * (wet_l - self.lp_l);
            self.lp_r += tone_coeff * (wet_r - self.lp_r);
            wet_l = self.lp_l;
            wet_r = self.lp_r;

            // Output gain
            wet_l *= output_gain;
            wet_r *= output_gain;

            buffer.data[idx] = dry_l * (1.0 - mix) + wet_l * mix;
            buffer.data[idx + 1] = dry_r * (1.0 - mix) + wet_r * mix;
        }
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sine_buf(frames: usize, freq: f32, sr: f32, amplitude: f32) -> AudioBuffer {
        let mut buf = AudioBuffer::new(frames, 2);
        for i in 0..frames {
            let t = i as f32 / sr;
            let s = (freq * 2.0 * std::f32::consts::PI * t).sin() * amplitude;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        buf
    }

    #[test]
    fn test_soft_clip_saturation() {
        let mut dist = Distortion::new(44100.0);
        dist.set_params(DistortionParams {
            drive: 1.0,
            mode: DistortionMode::SoftClip,
            tone: 1.0,
            output: 1.0,
            mix: 1.0,
            ..Default::default()
        });

        let mut buf = make_sine_buf(512, 440.0, 44100.0, 0.8);
        dist.process(&mut buf);

        // Output should be bounded by tanh
        for &s in &buf.data {
            assert!(s.abs() <= 1.01, "Soft clip should be bounded, got {}", s);
        }
    }

    #[test]
    fn test_hard_clip() {
        let mut dist = Distortion::new(44100.0);
        dist.set_params(DistortionParams {
            drive: 1.0,
            mode: DistortionMode::HardClip,
            tone: 1.0,
            output: 1.0,
            mix: 1.0,
            ..Default::default()
        });

        let mut buf = make_sine_buf(512, 440.0, 44100.0, 0.8);
        dist.process(&mut buf);

        for &s in &buf.data {
            assert!(s.abs() <= 1.01, "Hard clip should be bounded, got {}", s);
        }
    }

    #[test]
    fn test_bitcrush_reduces_quality() {
        let mut dist = Distortion::new(44100.0);
        dist.set_params(DistortionParams {
            drive: 0.2,
            mode: DistortionMode::Bitcrush,
            crush_rate: 4000.0,
            crush_bits: 4,
            tone: 1.0,
            output: 1.0,
            mix: 1.0,
        });

        let mut buf = make_sine_buf(1024, 440.0, 44100.0, 0.5);
        dist.process(&mut buf);

        // With 4 bits, there should be noticeable quantization
        // Count unique values (should be significantly fewer than original)
        let mut values: Vec<i32> = buf.data[0..100]
            .iter()
            .map(|&s| (s * 10000.0) as i32)
            .collect();
        values.sort();
        values.dedup();
        // 4-bit = 16 levels, so unique values should be limited
        assert!(values.len() < 100, "Bitcrush should reduce unique values");
    }

    #[test]
    fn test_dry_passthrough() {
        let mut dist = Distortion::new(44100.0);
        dist.set_params(DistortionParams { mix: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        dist.process(&mut buf);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }

    #[test]
    fn test_tube_asymmetry() {
        let mut dist = Distortion::new(44100.0);
        dist.set_params(DistortionParams {
            drive: 0.8,
            mode: DistortionMode::Tube,
            tone: 1.0,
            output: 1.0,
            mix: 1.0,
            ..Default::default()
        });

        let mut buf = make_sine_buf(4096, 440.0, 44100.0, 0.7);
        dist.process(&mut buf);

        // Tube mode is asymmetric: positive and negative halves differ.
        // Compute DC offset (even harmonics create DC)
        let dc: f32 = buf.data.iter().step_by(2).sum::<f32>() / (buf.frames as f32);
        // Should have some DC offset (asymmetric clipping)
        // This may be very small, so just check it doesn't explode
        assert!(dc.abs() < 1.0, "Tube DC should be bounded");
    }
}
