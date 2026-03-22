// ==========================================================================
// Flanger — Short modulated delay with feedback
// ==========================================================================
// v0.0.20.669 — Phase R3A
//
// Reference: pydaw/audio/creative_fx.py FlangerFx
//
// Architecture: Very short delay (0.1–10ms) modulated by LFO, with
// high feedback for comb-filter resonances. Classic jet/whoosh effect.
// Distinct from chorus: shorter delay, higher feedback, single voice.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::delay_line::DelayLine;
use crate::dsp::lfo::{Lfo, LfoShape};

/// Maximum delay in seconds (10ms).
const MAX_DELAY_S: f32 = 0.010;

/// Flanger parameters.
#[derive(Debug, Clone, Copy)]
pub struct FlangerParams {
    /// LFO rate in Hz (0.01 – 5.0)
    pub rate_hz: f32,
    /// Modulation depth in ms (0.1 – 8.0)
    pub depth_ms: f32,
    /// Feedback amount (-0.95 – 0.95, negative = inverted for different tone)
    pub feedback: f32,
    /// Manual delay offset in ms (0.1 – 5.0)
    pub manual_ms: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for FlangerParams {
    fn default() -> Self {
        Self {
            rate_hz: 0.3,
            depth_ms: 3.0,
            feedback: 0.6,
            manual_ms: 1.0,
            mix: 0.5,
        }
    }
}

/// Stereo Flanger effect.
pub struct Flanger {
    params: FlangerParams,
    sample_rate: f32,
    delay_l: DelayLine,
    delay_r: DelayLine,
    lfo: Lfo,
}

impl Flanger {
    pub fn new(sample_rate: f32) -> Self {
        let max_samples = (MAX_DELAY_S * sample_rate) as usize + 64;
        Self {
            params: FlangerParams::default(),
            sample_rate,
            delay_l: DelayLine::new(max_samples),
            delay_r: DelayLine::new(max_samples),
            lfo: Lfo::new(0.3, LfoShape::Sine, sample_rate),
        }
    }

    pub fn set_params(&mut self, params: FlangerParams) {
        self.params = params;
        self.lfo.set_rate(params.rate_hz.clamp(0.01, 5.0));
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        self.lfo.set_sample_rate(sr);
    }

    pub fn reset(&mut self) {
        self.delay_l.clear();
        self.delay_r.clear();
        self.lfo.reset();
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        let dry = 1.0 - mix;
        let depth_samples = self.params.depth_ms.clamp(0.1, 8.0) * 0.001 * self.sample_rate;
        let manual_samples = self.params.manual_ms.clamp(0.1, 5.0) * 0.001 * self.sample_rate;
        let feedback = self.params.feedback.clamp(-0.95, 0.95);
        let max_delay = (MAX_DELAY_S * self.sample_rate) - 2.0;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            // LFO modulation (unipolar 0..1 for delay)
            let mod_val = self.lfo.process_unipolar(); // 0..+1

            // Delay time = manual offset + LFO * depth
            let delay = (manual_samples + mod_val * depth_samples).clamp(1.0, max_delay);

            // Read with linear interpolation for smooth sweep
            let wet_l = self.delay_l.read_linear(delay);
            let wet_r = self.delay_r.read_linear(delay);

            // Write with feedback
            self.delay_l.write(in_l + wet_l * feedback);
            self.delay_r.write(in_r + wet_r * feedback);

            buffer.data[idx] = in_l * dry + wet_l * mix;
            buffer.data[idx + 1] = in_r * dry + wet_r * mix;
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
    fn test_flanger_produces_output() {
        let mut flanger = Flanger::new(44100.0);
        flanger.set_params(FlangerParams {
            rate_hz: 0.5,
            depth_ms: 3.0,
            feedback: 0.7,
            manual_ms: 1.0,
            mix: 1.0,
        });

        let mut buf = AudioBuffer::new(512, 2);
        for i in 0..512 {
            let t = i as f32 / 44100.0;
            let s = (440.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        flanger.process(&mut buf);

        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val > 0.01, "Flanger should produce output, got max={}", max_val);
    }

    #[test]
    fn test_flanger_dry_passthrough() {
        let mut flanger = Flanger::new(44100.0);
        flanger.set_params(FlangerParams { mix: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        flanger.process(&mut buf);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }

    #[test]
    fn test_flanger_negative_feedback() {
        // Negative feedback should produce different harmonic content (odd harmonics)
        let mut flanger = Flanger::new(44100.0);
        flanger.set_params(FlangerParams {
            feedback: -0.8,
            mix: 0.5,
            ..Default::default()
        });

        let mut buf = AudioBuffer::new(256, 2);
        for i in 0..256 {
            let t = i as f32 / 44100.0;
            buf.data[i * 2] = (440.0 * 2.0 * std::f32::consts::PI * t).sin();
            buf.data[i * 2 + 1] = buf.data[i * 2];
        }
        flanger.process(&mut buf);

        // Just verify it doesn't explode
        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val < 5.0, "Flanger should stay bounded, got max={}", max_val);
    }
}
