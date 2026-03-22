// ==========================================================================
// Reverb — Schroeder reverb (4 Comb + 4 Allpass)
// ==========================================================================
// v0.0.20.667 — Phase R2C
//
// Reference: pydaw/audio/builtin_fx.py ReverbFx
// Classic Schroeder/Freeverb topology. Pre-delay via DelayLine.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::delay_line::DelayLine;

/// Comb filter (feedback delay with damping).
struct CombFilter {
    delay: DelayLine,
    feedback: f32,
    damp1: f32,
    damp2: f32,
    filter_state: f32,
    delay_samples: usize,
}

impl CombFilter {
    fn new(delay_samples: usize) -> Self {
        Self {
            delay: DelayLine::new(delay_samples + 64),
            feedback: 0.5,
            damp1: 0.5,
            damp2: 0.5,
            filter_state: 0.0,
            delay_samples,
        }
    }

    fn set_feedback(&mut self, feedback: f32) {
        self.feedback = feedback;
    }

    fn set_damping(&mut self, damping: f32) {
        self.damp1 = damping;
        self.damp2 = 1.0 - damping;
    }

    #[inline]
    fn process(&mut self, input: f32) -> f32 {
        let delayed = self.delay.read(self.delay_samples);
        self.filter_state = delayed * self.damp2 + self.filter_state * self.damp1;
        self.delay.write(input + self.filter_state * self.feedback);
        delayed
    }

    fn clear(&mut self) {
        self.delay.clear();
        self.filter_state = 0.0;
    }
}

/// Allpass filter (diffusion).
struct AllpassFilter {
    delay: DelayLine,
    feedback: f32,
    delay_samples: usize,
}

impl AllpassFilter {
    fn new(delay_samples: usize) -> Self {
        Self {
            delay: DelayLine::new(delay_samples + 16),
            feedback: 0.5,
            delay_samples,
        }
    }

    #[inline]
    fn process(&mut self, input: f32) -> f32 {
        let delayed = self.delay.read(self.delay_samples);
        let output = -input + delayed;
        self.delay.write(input + delayed * self.feedback);
        output
    }

    fn clear(&mut self) {
        self.delay.clear();
    }
}

// Freeverb tuning constants (in samples at 44100Hz, scaled to actual SR)
const COMB_TUNINGS: [usize; 4] = [1116, 1188, 1277, 1356];
const ALLPASS_TUNINGS: [usize; 4] = [556, 441, 341, 225];

/// Schroeder Reverb (stereo).
pub struct Reverb {
    combs_l: [CombFilter; 4],
    combs_r: [CombFilter; 4],
    allpasses_l: [AllpassFilter; 4],
    allpasses_r: [AllpassFilter; 4],
    pre_delay: DelayLine,
    pre_delay_samples: usize,
    mix: f32,
    decay: f32,
    damping: f32,
    sample_rate: f32,
}

impl Reverb {
    pub fn new(sample_rate: f32) -> Self {
        let scale = sample_rate / 44100.0;
        let s = |base: usize| -> usize { (base as f32 * scale) as usize };
        // Stereo spread: offset right channel by ~23 samples
        let spread: usize = (23.0 * scale) as usize;

        let mut rev = Self {
            combs_l: [
                CombFilter::new(s(COMB_TUNINGS[0])),
                CombFilter::new(s(COMB_TUNINGS[1])),
                CombFilter::new(s(COMB_TUNINGS[2])),
                CombFilter::new(s(COMB_TUNINGS[3])),
            ],
            combs_r: [
                CombFilter::new(s(COMB_TUNINGS[0]) + spread),
                CombFilter::new(s(COMB_TUNINGS[1]) + spread),
                CombFilter::new(s(COMB_TUNINGS[2]) + spread),
                CombFilter::new(s(COMB_TUNINGS[3]) + spread),
            ],
            allpasses_l: [
                AllpassFilter::new(s(ALLPASS_TUNINGS[0])),
                AllpassFilter::new(s(ALLPASS_TUNINGS[1])),
                AllpassFilter::new(s(ALLPASS_TUNINGS[2])),
                AllpassFilter::new(s(ALLPASS_TUNINGS[3])),
            ],
            allpasses_r: [
                AllpassFilter::new(s(ALLPASS_TUNINGS[0]) + spread),
                AllpassFilter::new(s(ALLPASS_TUNINGS[1]) + spread),
                AllpassFilter::new(s(ALLPASS_TUNINGS[2]) + spread),
                AllpassFilter::new(s(ALLPASS_TUNINGS[3]) + spread),
            ],
            pre_delay: DelayLine::new((sample_rate * 0.25) as usize), // max 250ms
            pre_delay_samples: 0,
            mix: 0.3,
            decay: 0.7,
            damping: 0.5,
            sample_rate,
        };
        rev.update_params();
        rev
    }

    /// Set reverb parameters.
    pub fn set_params(&mut self, decay: f32, damping: f32, pre_delay_ms: f32, mix: f32) {
        self.decay = decay.clamp(0.0, 1.0);
        self.damping = damping.clamp(0.0, 1.0);
        self.pre_delay_samples = ((pre_delay_ms * 0.001 * self.sample_rate) as usize)
            .min(self.pre_delay.max_delay());
        self.mix = mix.clamp(0.0, 1.0);
        self.update_params();
    }

    fn update_params(&mut self) {
        let feedback = self.decay * 0.9 + 0.1; // map 0..1 → 0.1..1.0
        for comb in self.combs_l.iter_mut().chain(self.combs_r.iter_mut()) {
            comb.set_feedback(feedback);
            comb.set_damping(self.damping);
        }
    }

    pub fn reset(&mut self) {
        for c in self.combs_l.iter_mut().chain(self.combs_r.iter_mut()) { c.clear(); }
        for a in self.allpasses_l.iter_mut().chain(self.allpasses_r.iter_mut()) { a.clear(); }
        self.pre_delay.clear();
    }

    /// Update sample rate. Resets state (comb tunings are fixed at creation).
    pub fn set_sample_rate(&mut self, sr: f32) {
        if (sr - self.sample_rate).abs() > 1.0 {
            self.sample_rate = sr;
            // Comb/allpass tunings were computed at creation for the original SR.
            // A full rebuild would be ideal, but for now just reset state.
            self.reset();
        }
    }

    /// Process stereo buffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let wet = self.mix;
        let dry = 1.0 - self.mix;

        for frame in 0..frames {
            let idx = frame * 2;
            if idx + 1 >= buffer.data.len() { break; }

            let in_l = buffer.data[idx];
            let in_r = buffer.data[idx + 1];

            // Pre-delay (mono sum)
            let mono = (in_l + in_r) * 0.5;
            self.pre_delay.write(mono);
            let pre = self.pre_delay.read(self.pre_delay_samples);

            // Parallel comb filters
            let mut wet_l = 0.0f32;
            let mut wet_r = 0.0f32;
            for comb in &mut self.combs_l { wet_l += comb.process(pre); }
            for comb in &mut self.combs_r { wet_r += comb.process(pre); }

            // Series allpass filters
            for ap in &mut self.allpasses_l { wet_l = ap.process(wet_l); }
            for ap in &mut self.allpasses_r { wet_r = ap.process(wet_r); }

            // Wet/dry mix
            buffer.data[idx] = in_l * dry + wet_l * wet;
            buffer.data[idx + 1] = in_r * dry + wet_r * wet;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_reverb_produces_tail() {
        let mut rev = Reverb::new(44100.0);
        rev.set_params(0.8, 0.3, 0.0, 1.0); // full wet, long decay

        // Feed an impulse
        let mut buf = AudioBuffer::new(64, 2);
        buf.data[0] = 1.0;
        buf.data[1] = 1.0;
        rev.process(&mut buf);

        // Process more silence — reverb tail should still produce output
        let mut buf2 = AudioBuffer::new(4096, 2);
        rev.process(&mut buf2);

        let mut has_output = false;
        for &s in &buf2.data {
            if s.abs() > 0.001 {
                has_output = true;
                break;
            }
        }
        assert!(has_output, "Reverb should produce a tail after impulse");
    }

    #[test]
    fn test_reverb_dry_passthrough() {
        let mut rev = Reverb::new(44100.0);
        rev.set_params(0.5, 0.5, 0.0, 0.0); // full dry

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.42;
            buf.data[i * 2 + 1] = -0.33;
        }
        rev.process(&mut buf);

        // Should be nearly identical to input (dry=1.0, wet=0.0)
        assert!((buf.data[254] - 0.42).abs() < 0.01);
    }
}
