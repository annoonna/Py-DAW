// ==========================================================================
// Tremolo — Amplitude modulation effect
// ==========================================================================
// v0.0.20.669 — Phase R3A
//
// Reference: pydaw/audio/creative_fx.py TremoloFx
//
// Architecture: LFO modulates amplitude. Supports stereo offset for
// auto-pan effect (offset = 0.5 → full auto-pan). Multiple LFO shapes.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::lfo::{Lfo, LfoShape};

/// Tremolo parameters.
#[derive(Debug, Clone, Copy)]
pub struct TremoloParams {
    /// LFO rate in Hz (0.1 – 20.0)
    pub rate_hz: f32,
    /// Modulation depth (0.0 – 1.0, 1.0 = full modulation)
    pub depth: f32,
    /// LFO shape
    pub shape: LfoShape,
    /// Stereo phase offset (0.0 – 0.5, 0.5 = auto-pan)
    pub stereo_offset: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for TremoloParams {
    fn default() -> Self {
        Self {
            rate_hz: 4.0,
            depth: 0.7,
            shape: LfoShape::Sine,
            stereo_offset: 0.0,
            mix: 1.0,
        }
    }
}

/// Stereo Tremolo effect.
pub struct Tremolo {
    params: TremoloParams,
    sample_rate: f32,
    lfo_l: Lfo,
    lfo_r: Lfo,
}

impl Tremolo {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: TremoloParams::default(),
            sample_rate,
            lfo_l: Lfo::new(4.0, LfoShape::Sine, sample_rate),
            lfo_r: Lfo::new(4.0, LfoShape::Sine, sample_rate),
        }
    }

    pub fn set_params(&mut self, params: TremoloParams) {
        self.params = params;
        let rate = params.rate_hz.clamp(0.1, 20.0);
        self.lfo_l.set_rate(rate);
        self.lfo_l.set_shape(params.shape);
        self.lfo_r.set_rate(rate);
        self.lfo_r.set_shape(params.shape);
        // Set stereo offset phase
        self.lfo_r.set_phase(params.stereo_offset.clamp(0.0, 0.5));
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        self.lfo_l.set_sample_rate(sr);
        self.lfo_r.set_sample_rate(sr);
    }

    pub fn reset(&mut self) {
        self.lfo_l.reset();
        self.lfo_r.reset();
        self.lfo_r.set_phase(self.params.stereo_offset.clamp(0.0, 0.5));
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        let depth = self.params.depth.clamp(0.0, 1.0);

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            // LFO values (-1..+1) → gain (1-depth .. 1)
            let mod_l = self.lfo_l.process();
            let mod_r = self.lfo_r.process();

            let gain_l = 1.0 - depth * (1.0 - (mod_l + 1.0) * 0.5);
            let gain_r = 1.0 - depth * (1.0 - (mod_r + 1.0) * 0.5);

            // Mix: dry * (1 - mix) + modulated * mix
            buffer.data[idx] = in_l * (1.0 - mix) + in_l * gain_l * mix;
            buffer.data[idx + 1] = in_r * (1.0 - mix) + in_r * gain_r * mix;
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
    fn test_tremolo_modulates_amplitude() {
        let mut trem = Tremolo::new(44100.0);
        trem.set_params(TremoloParams {
            rate_hz: 4.0,
            depth: 1.0,
            shape: LfoShape::Sine,
            stereo_offset: 0.0,
            mix: 1.0,
        });

        // Constant signal
        let mut buf = AudioBuffer::new(44100, 2); // 1 second
        for i in 0..44100 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = 0.5;
        }
        trem.process(&mut buf);

        // Find min and max in output
        let mut min_val = f32::MAX;
        let mut max_val = f32::MIN;
        for i in 0..44100 {
            let s = buf.data[i * 2];
            min_val = min_val.min(s);
            max_val = max_val.max(s);
        }

        // With depth=1.0, should go from ~0 to ~0.5
        assert!(min_val < 0.05, "Tremolo min should be near 0, got {}", min_val);
        assert!(max_val > 0.45, "Tremolo max should be near 0.5, got {}", max_val);
    }

    #[test]
    fn test_tremolo_autopan() {
        let mut trem = Tremolo::new(44100.0);
        trem.set_params(TremoloParams {
            rate_hz: 2.0,
            depth: 1.0,
            shape: LfoShape::Sine,
            stereo_offset: 0.5, // Full auto-pan
            mix: 1.0,
        });

        let mut buf = AudioBuffer::new(4410, 2); // 0.1s
        for i in 0..4410 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = 0.5;
        }
        trem.process(&mut buf);

        // L and R should differ due to stereo offset
        let mut diff_found = false;
        for i in 100..4410 {
            let diff = (buf.data[i * 2] - buf.data[i * 2 + 1]).abs();
            if diff > 0.05 {
                diff_found = true;
                break;
            }
        }
        assert!(diff_found, "Auto-pan should create L/R differences");
    }

    #[test]
    fn test_tremolo_zero_depth() {
        let mut trem = Tremolo::new(44100.0);
        trem.set_params(TremoloParams { depth: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        trem.process(&mut buf);

        // No modulation → passthrough
        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }
}
