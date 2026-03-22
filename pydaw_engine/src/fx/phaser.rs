// ==========================================================================
// Phaser — N-stage allpass phaser with LFO sweep and feedback
// ==========================================================================
// v0.0.20.669 — Phase R3A
//
// Reference: pydaw/audio/creative_fx.py PhaserFx
//
// Architecture: Chain of 2–12 first-order allpass filters whose cutoff
// frequency is swept by an LFO. The notches created by allpass phase
// cancellation produce the classic phaser sound.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::lfo::{Lfo, LfoShape};

/// Maximum number of allpass stages.
const MAX_STAGES: usize = 12;

/// Phaser parameters.
#[derive(Debug, Clone, Copy)]
pub struct PhaserParams {
    /// LFO rate in Hz (0.01 – 10.0)
    pub rate_hz: f32,
    /// LFO depth (0.0 – 1.0) — controls sweep range
    pub depth: f32,
    /// Number of allpass stages (2 – 12, even numbers sound best)
    pub stages: u8,
    /// Feedback amount (-0.95 – 0.95, negative = inverted)
    pub feedback: f32,
    /// Center frequency of sweep in Hz (100 – 8000)
    pub center_freq: f32,
    /// Dry/wet mix (0.0 – 1.0)
    pub mix: f32,
}

impl Default for PhaserParams {
    fn default() -> Self {
        Self {
            rate_hz: 0.5,
            depth: 0.7,
            stages: 6,
            feedback: 0.5,
            center_freq: 1000.0,
            mix: 0.5,
        }
    }
}

/// First-order allpass filter for phaser stage.
/// Transfer function: H(z) = (a + z^-1) / (1 + a * z^-1)
/// where a = (1 - tan(pi*fc/fs)) / (1 + tan(pi*fc/fs))
struct AllpassStage {
    a: f32,
    z1: f32,
}

impl AllpassStage {
    fn new() -> Self {
        Self { a: 0.0, z1: 0.0 }
    }

    /// Set the allpass coefficient from cutoff frequency.
    #[inline]
    fn set_freq(&mut self, freq: f32, sample_rate: f32) {
        let w = std::f32::consts::PI * freq / sample_rate;
        let t = w.tan();
        self.a = (1.0 - t) / (1.0 + t);
    }

    /// Process one sample through the allpass.
    #[inline]
    fn process(&mut self, input: f32) -> f32 {
        let output = self.a * input + self.z1;
        self.z1 = input - self.a * output;
        output
    }

    fn clear(&mut self) {
        self.z1 = 0.0;
    }
}

/// Stereo Phaser effect.
pub struct Phaser {
    params: PhaserParams,
    sample_rate: f32,
    stages_l: [AllpassStage; MAX_STAGES],
    stages_r: [AllpassStage; MAX_STAGES],
    lfo: Lfo,
    feedback_l: f32,
    feedback_r: f32,
}

impl Phaser {
    pub fn new(sample_rate: f32) -> Self {
        Self {
            params: PhaserParams::default(),
            sample_rate,
            stages_l: std::array::from_fn(|_| AllpassStage::new()),
            stages_r: std::array::from_fn(|_| AllpassStage::new()),
            lfo: Lfo::new(0.5, LfoShape::Sine, sample_rate),
            feedback_l: 0.0,
            feedback_r: 0.0,
        }
    }

    pub fn set_params(&mut self, params: PhaserParams) {
        self.params = params;
        self.lfo.set_rate(params.rate_hz.clamp(0.01, 10.0));
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        self.lfo.set_sample_rate(sr);
    }

    pub fn reset(&mut self) {
        for s in &mut self.stages_l { s.clear(); }
        for s in &mut self.stages_r { s.clear(); }
        self.lfo.reset();
        self.feedback_l = 0.0;
        self.feedback_r = 0.0;
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let mix = self.params.mix.clamp(0.0, 1.0);
        let dry = 1.0 - mix;
        let depth = self.params.depth.clamp(0.0, 1.0);
        let feedback = self.params.feedback.clamp(-0.95, 0.95);
        let stages = (self.params.stages as usize).clamp(2, MAX_STAGES);
        let center = self.params.center_freq.clamp(100.0, 8000.0);
        let sr = self.sample_rate;
        let nyquist = sr * 0.499;

        // Sweep range: center / range_factor .. center * range_factor
        let range_factor = 4.0f32; // 2 octaves each direction

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            // LFO modulation → frequency sweep
            let mod_val = self.lfo.process(); // -1..+1
            let sweep = depth * mod_val; // -depth..+depth

            // Exponential frequency sweep around center
            let freq = (center * range_factor.powf(sweep)).clamp(20.0, nyquist);

            // Update allpass coefficients for all active stages
            for i in 0..stages {
                // Slightly detune each stage for richer sound
                let stage_freq = (freq * (1.0 + 0.03 * i as f32)).min(nyquist);
                self.stages_l[i].set_freq(stage_freq, sr);
                self.stages_r[i].set_freq(stage_freq, sr);
            }

            // Process through allpass chain
            let mut wet_l = in_l + self.feedback_l * feedback;
            let mut wet_r = in_r + self.feedback_r * feedback;

            for i in 0..stages {
                wet_l = self.stages_l[i].process(wet_l);
                wet_r = self.stages_r[i].process(wet_r);
            }

            self.feedback_l = wet_l;
            self.feedback_r = wet_r;

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
    fn test_phaser_produces_output() {
        let mut phaser = Phaser::new(44100.0);
        phaser.set_params(PhaserParams {
            rate_hz: 1.0,
            depth: 0.8,
            stages: 6,
            feedback: 0.5,
            center_freq: 1000.0,
            mix: 1.0,
        });

        let mut buf = AudioBuffer::new(1024, 2);
        for i in 0..1024 {
            let t = i as f32 / 44100.0;
            let s = (440.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }
        phaser.process(&mut buf);

        let max_val = buf.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max_val > 0.01, "Phaser should produce output, got max={}", max_val);
    }

    #[test]
    fn test_phaser_dry_passthrough() {
        let mut phaser = Phaser::new(44100.0);
        phaser.set_params(PhaserParams { mix: 0.0, ..Default::default() });

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        phaser.process(&mut buf);

        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }

    #[test]
    fn test_allpass_stage_unity_gain() {
        // Allpass filter should have unity magnitude (only changes phase)
        let mut stage = AllpassStage::new();
        stage.set_freq(1000.0, 44100.0);

        let mut energy_in = 0.0f64;
        let mut energy_out = 0.0f64;
        for i in 0..4096 {
            let t = i as f32 / 44100.0;
            let s = (1000.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            energy_in += (s as f64) * (s as f64);
            let out = stage.process(s);
            energy_out += (out as f64) * (out as f64);
        }
        let ratio = energy_out / energy_in.max(1e-20);
        assert!((ratio - 1.0).abs() < 0.05, "Allpass should have unity gain, ratio={}", ratio);
    }
}
