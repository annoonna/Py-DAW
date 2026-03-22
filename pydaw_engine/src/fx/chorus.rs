// ==========================================================================
// Chorus — Multi-voice chorus with LFO-modulated delay
// ==========================================================================
// v0.0.20.669 — Phase R3A
//
// Reference: pydaw/audio/creative_fx.py ChorusFx
//
// Architecture: N voices, each with its own LFO phase offset, modulating a
// short delay line. Stereo spread via alternating L/R voice panning.
// All delay lines pre-allocated — zero alloc in process().
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::delay_line::DelayLine;
use crate::dsp::lfo::{Lfo, LfoShape};

/// Maximum number of chorus voices.
const MAX_VOICES: usize = 6;

/// Maximum delay in seconds (20ms).
const MAX_DELAY_S: f32 = 0.020;

/// Chorus parameters.
#[derive(Debug, Clone, Copy)]
pub struct ChorusParams {
    /// LFO rate in Hz (0.01 – 10.0)
    pub rate_hz: f32,
    /// Modulation depth in ms (0.1 – 15.0)
    pub depth_ms: f32,
    /// Number of voices (1 – 6)
    pub voices: u8,
    /// Feedback amount (0.0 – 0.95)
    pub feedback: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for ChorusParams {
    fn default() -> Self {
        Self {
            rate_hz: 1.5,
            depth_ms: 3.0,
            voices: 3,
            feedback: 0.3,
            mix: 0.5,
        }
    }
}

/// Stereo Chorus effect.
pub struct Chorus {
    params: ChorusParams,
    sample_rate: f32,
    delay_l: DelayLine,
    delay_r: DelayLine,
    lfos: [Lfo; MAX_VOICES],
}

impl Chorus {
    pub fn new(sample_rate: f32) -> Self {
        let max_samples = (MAX_DELAY_S * sample_rate) as usize + 64;
        let mut lfos: [Lfo; MAX_VOICES] = std::array::from_fn(|_| {
            Lfo::new(1.5, LfoShape::Sine, sample_rate)
        });
        // Spread LFO phases evenly across voices
        for (i, lfo) in lfos.iter_mut().enumerate() {
            lfo.set_phase(i as f32 / MAX_VOICES as f32);
        }

        Self {
            params: ChorusParams::default(),
            sample_rate,
            delay_l: DelayLine::new(max_samples),
            delay_r: DelayLine::new(max_samples),
            lfos,
        }
    }

    pub fn set_params(&mut self, params: ChorusParams) {
        self.params = params;
        let rate = params.rate_hz.clamp(0.01, 10.0);
        for lfo in &mut self.lfos {
            lfo.set_rate(rate);
        }
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        for lfo in &mut self.lfos {
            lfo.set_sample_rate(sr);
        }
    }

    pub fn reset(&mut self) {
        self.delay_l.clear();
        self.delay_r.clear();
        for (i, lfo) in self.lfos.iter_mut().enumerate() {
            lfo.reset();
            lfo.set_phase(i as f32 / MAX_VOICES as f32);
        }
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        let dry = 1.0 - mix;
        let depth_samples = (self.params.depth_ms.clamp(0.1, 15.0) * 0.001 * self.sample_rate)
            .max(1.0);
        let feedback = self.params.feedback.clamp(0.0, 0.95);
        let voices = (self.params.voices as usize).clamp(1, MAX_VOICES);
        let voice_gain = 1.0 / voices as f32;
        let max_delay = (MAX_DELAY_S * self.sample_rate) as f32 - 2.0;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            let mut wet_l = 0.0f32;
            let mut wet_r = 0.0f32;

            for v in 0..voices {
                let mod_val = self.lfos[v].process(); // -1..+1
                let delay = ((1.0 + mod_val) * 0.5 * depth_samples).clamp(1.0, max_delay);

                let dl = self.delay_l.read_linear(delay);
                let dr = self.delay_r.read_linear(delay);

                // Alternate voices L/R for stereo spread
                if v % 2 == 0 {
                    wet_l += dl * voice_gain;
                    wet_r += dr * voice_gain * 0.7;
                } else {
                    wet_l += dl * voice_gain * 0.7;
                    wet_r += dr * voice_gain;
                }
            }

            // Write input + feedback into delay
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
    fn test_chorus_produces_output() {
        let mut chorus = Chorus::new(44100.0);
        chorus.set_params(ChorusParams {
            rate_hz: 2.0,
            depth_ms: 5.0,
            voices: 3,
            feedback: 0.3,
            mix: 1.0,
        });

        // Feed some signal
        let mut buf = AudioBuffer::new(512, 2);
        for i in 0..512 {
            let t = i as f32 / 44100.0;
            let s = (440.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        chorus.process(&mut buf);

        // Should have some output
        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val > 0.01, "Chorus should produce output, got max={}", max_val);
    }

    #[test]
    fn test_chorus_dry_passthrough() {
        let mut chorus = Chorus::new(44100.0);
        chorus.set_params(ChorusParams { mix: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        chorus.process(&mut buf);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
        assert!((buf.data[255] - (-0.33)).abs() < 0.01);
    }
}
