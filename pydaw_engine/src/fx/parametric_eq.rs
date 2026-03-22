// ==========================================================================
// Parametric EQ — 8-Band EQ using Biquad filters from dsp/
// ==========================================================================
// v0.0.20.667 — Phase R2A
//
// Reference: pydaw/audio/builtin_fx.py ParametricEqFx (8-Band Biquad DF2T)
//
// Each band is an independent StereoBiquad. Bands are processed serially.
// Zero allocations in process(). All buffers pre-sized.
// ==========================================================================

use crate::audio_graph::AudioBuffer;
use crate::dsp::biquad::{FilterType, StereoBiquad};

/// Maximum number of EQ bands.
pub const MAX_BANDS: usize = 8;

/// Parameters for a single EQ band.
#[derive(Debug, Clone, Copy)]
pub struct EqBandParams {
    pub enabled: bool,
    pub filter_type: FilterType,
    pub frequency: f32,
    pub gain_db: f32,
    pub q: f32,
}

impl Default for EqBandParams {
    fn default() -> Self {
        Self {
            enabled: false,
            filter_type: FilterType::PeakEQ,
            frequency: 1000.0,
            gain_db: 0.0,
            q: 0.707,
        }
    }
}

/// 8-Band Parametric EQ.
pub struct ParametricEq {
    bands: [StereoBiquad; MAX_BANDS],
    params: [EqBandParams; MAX_BANDS],
    sample_rate: f32,
}

impl ParametricEq {
    pub fn new(sample_rate: f32) -> Self {
        let default_params = EqBandParams::default();
        let default_biquad = StereoBiquad::new(
            FilterType::PeakEQ, 1000.0, 0.707, 0.0, sample_rate,
        );
        Self {
            bands: [
                default_biquad.clone(), default_biquad.clone(),
                default_biquad.clone(), default_biquad.clone(),
                default_biquad.clone(), default_biquad.clone(),
                default_biquad.clone(), default_biquad.clone(),
            ],
            params: [default_params; MAX_BANDS],
            sample_rate,
        }
    }

    /// Set parameters for a single band (0–7).
    pub fn set_band(&mut self, index: usize, params: EqBandParams) {
        if index >= MAX_BANDS { return; }
        self.params[index] = params;
        if params.enabled {
            self.bands[index].set_params(
                params.filter_type, params.frequency, params.q,
                params.gain_db, self.sample_rate,
            );
        }
    }

    /// Set sample rate (recalculates all band coefficients).
    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        for i in 0..MAX_BANDS {
            if self.params[i].enabled {
                let p = &self.params[i];
                self.bands[i].set_params(p.filter_type, p.frequency, p.q, p.gain_db, sr);
            }
        }
    }

    /// Reset all filter states (call on transport stop/seek).
    pub fn reset(&mut self) {
        for band in &mut self.bands {
            band.reset();
        }
    }

    /// Process a stereo AudioBuffer in-place. **AUDIO THREAD**.
    #[inline]
    pub fn process(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        for i in 0..MAX_BANDS {
            if self.params[i].enabled {
                self.bands[i].process_stereo(&mut buffer.data, frames);
            }
        }
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    #[test]
    fn test_eq_passthrough_when_disabled() {
        let mut eq = ParametricEq::new(44100.0);
        // All bands disabled → passthrough
        let mut buf = AudioBuffer::new(128, 2);
        for i in 0..128 {
            buf.data[i * 2] = (i as f32 / 128.0).sin();
            buf.data[i * 2 + 1] = (i as f32 / 128.0).cos();
        }
        let original = buf.data.clone();
        eq.process(&mut buf);
        assert_eq!(buf.data, original);
    }

    #[test]
    fn test_eq_band_modifies_signal() {
        let mut eq = ParametricEq::new(44100.0);
        eq.set_band(0, EqBandParams {
            enabled: true,
            filter_type: FilterType::LowPass,
            frequency: 500.0,
            gain_db: 0.0,
            q: 0.707,
        });

        let mut buf = AudioBuffer::new(512, 2);
        // Fill with 5kHz sine (should be attenuated by 500Hz LP)
        let freq = 5000.0;
        let sr = 44100.0;
        for i in 0..512 {
            let s = (2.0 * PI * freq * i as f32 / sr).sin() * 0.5;
            buf.data[i * 2] = s;
            buf.data[i * 2 + 1] = s;
        }

        eq.process(&mut buf);

        // Check last 256 frames — should be heavily attenuated
        let mut peak = 0.0f32;
        for i in 256..512 {
            peak = peak.max(buf.data[i * 2].abs());
        }
        assert!(peak < 0.15, "5kHz through 500Hz LP peak = {} (expected < 0.15)", peak);
    }
}
