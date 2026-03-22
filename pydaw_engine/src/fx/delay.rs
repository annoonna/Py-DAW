// ==========================================================================
// Delay — Stereo delay with feedback, filter, ping-pong
// ==========================================================================
// v0.0.20.667 — Phase R2C
//
// Reference: pydaw/audio/builtin_fx.py DelayFx
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::biquad::{Biquad, FilterType};
use crate::dsp::delay_line::DelayLine;

/// Stereo Delay FX.
pub struct Delay {
    delay_l: DelayLine,
    delay_r: DelayLine,
    filter_l: Biquad,
    filter_r: Biquad,
    delay_samples_l: f32,
    delay_samples_r: f32,
    feedback: f32,
    mix: f32,
    ping_pong: bool,
    filter_freq: f32,
    sample_rate: f32,
}

impl Delay {
    pub fn new(sample_rate: f32) -> Self {
        let max_delay = (sample_rate * 4.0) as usize; // max 4 seconds
        Self {
            delay_l: DelayLine::new(max_delay),
            delay_r: DelayLine::new(max_delay),
            filter_l: Biquad::new(FilterType::LowPass, 8000.0, 0.707, 0.0, sample_rate),
            filter_r: Biquad::new(FilterType::LowPass, 8000.0, 0.707, 0.0, sample_rate),
            delay_samples_l: sample_rate * 0.375, // default 375ms (dotted 8th at 120BPM)
            delay_samples_r: sample_rate * 0.375,
            feedback: 0.35,
            mix: 0.3,
            ping_pong: false,
            filter_freq: 8000.0,
            sample_rate,
        }
    }

    /// Set delay time in milliseconds (both channels).
    pub fn set_time_ms(&mut self, ms: f32) {
        let samples = (ms * 0.001 * self.sample_rate).max(1.0);
        self.delay_samples_l = samples;
        self.delay_samples_r = samples;
    }

    /// Set delay time from tempo sync (beat fraction at given BPM).
    /// `beat_fraction`: 0.25 = 1/16th, 0.5 = 1/8th, 1.0 = quarter, etc.
    pub fn set_time_sync(&mut self, beat_fraction: f32, bpm: f32) {
        let beat_sec = 60.0 / bpm.max(20.0);
        let ms = beat_fraction * beat_sec * 1000.0;
        self.set_time_ms(ms);
    }

    pub fn set_feedback(&mut self, feedback: f32) {
        self.feedback = feedback.clamp(0.0, 0.95);
    }

    pub fn set_mix(&mut self, mix: f32) {
        self.mix = mix.clamp(0.0, 1.0);
    }

    pub fn set_ping_pong(&mut self, enabled: bool) {
        self.ping_pong = enabled;
    }

    pub fn set_filter_freq(&mut self, freq: f32) {
        self.filter_freq = freq.clamp(200.0, 18000.0);
        self.filter_l.set_params(FilterType::LowPass, self.filter_freq, 0.707, 0.0, self.sample_rate);
        self.filter_r.set_params(FilterType::LowPass, self.filter_freq, 0.707, 0.0, self.sample_rate);
    }

    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
    }

    pub fn reset(&mut self) {
        self.delay_l.clear();
        self.delay_r.clear();
        self.filter_l.reset();
        self.filter_r.reset();
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

            // Read from delay lines
            let tap_l = self.delay_l.read_linear(self.delay_samples_l);
            let tap_r = self.delay_r.read_linear(self.delay_samples_r);

            // Apply feedback filter
            let filt_l = self.filter_l.process_sample(tap_l);
            let filt_r = self.filter_r.process_sample(tap_r);

            // Write to delay lines (with feedback)
            if self.ping_pong {
                // Ping-pong: L feeds R, R feeds L
                self.delay_l.write(in_l + filt_r * self.feedback);
                self.delay_r.write(in_r + filt_l * self.feedback);
            } else {
                self.delay_l.write(in_l + filt_l * self.feedback);
                self.delay_r.write(in_r + filt_r * self.feedback);
            }

            // Mix
            buffer.data[idx] = in_l * dry + tap_l * wet;
            buffer.data[idx + 1] = in_r * dry + tap_r * wet;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_delay_echo() {
        let mut delay = Delay::new(44100.0);
        delay.set_time_ms(100.0); // 100ms = 4410 samples
        delay.set_feedback(0.0);
        delay.set_mix(1.0); // full wet

        // Feed impulse then silence in one big buffer
        let total_frames = 8820; // 200ms — enough for the echo to appear
        let mut buf = AudioBuffer::new(total_frames, 2);
        buf.data[0] = 1.0;
        buf.data[1] = 1.0;
        delay.process(&mut buf);

        // Echo should appear around frame 4410 (±2 for rounding)
        let expected = 4410usize;
        let mut found_echo = false;
        for frame in (expected.saturating_sub(4))..=(expected + 4).min(total_frames - 1) {
            let val = buf.data[frame * 2].abs();
            if val > 0.3 {
                found_echo = true;
                break;
            }
        }
        assert!(found_echo, "Echo should appear around frame {} of {} total", expected, total_frames);
    }

    #[test]
    fn test_delay_dry() {
        let mut delay = Delay::new(44100.0);
        delay.set_mix(0.0); // full dry

        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = 0.5;
            buf.data[i * 2 + 1] = -0.3;
        }
        delay.process(&mut buf);

        assert!((buf.data[254] - 0.5).abs() < 0.01);
    }
}
