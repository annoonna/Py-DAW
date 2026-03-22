// ============================================================================
// Plugin Host — Stub for Phase 1C
// ============================================================================
//
// This module will host VST3 and CLAP plugins in future phases.
// For Phase 1A, it provides the trait interfaces and a passthrough stub.
//
// Future crates: vst3-sys, clack-host (CLAP)
// ============================================================================

use crate::audio_graph::AudioBuffer;

/// Plugin processing trait.
///
/// Each hosted plugin implements this trait. The audio graph calls `process()`
/// in the audio thread — NO allocations, NO locks.
pub trait AudioPlugin: Send {
    /// Process audio in-place.
    ///
    /// `input` and `output` may alias (in-place processing).
    /// `frames` is the number of audio frames to process.
    fn process(&mut self, buffer: &mut AudioBuffer, sample_rate: u32);

    /// Get the plugin's unique identifier.
    fn id(&self) -> &str;

    /// Get the plugin's display name.
    fn name(&self) -> &str;

    /// Set a parameter value (called from command queue, NOT audio thread).
    fn set_parameter(&mut self, index: u32, value: f64);

    /// Get a parameter value.
    fn get_parameter(&self, index: u32) -> f64;

    /// Get number of parameters.
    fn parameter_count(&self) -> u32;

    /// Get parameter name by index.
    fn parameter_name(&self, index: u32) -> String;

    /// Save state as binary blob.
    fn save_state(&self) -> Vec<u8>;

    /// Load state from binary blob.
    fn load_state(&mut self, data: &[u8]) -> Result<(), String>;

    /// Get tail length in samples (for reverb/delay tails).
    fn tail_samples(&self) -> u64 {
        0
    }

    /// Get latency in samples (for Plugin Delay Compensation).
    fn latency_samples(&self) -> u32 {
        0
    }
}

// ---------------------------------------------------------------------------
// Sine Wave Generator — Phase 1A Proof of Concept
// ---------------------------------------------------------------------------

/// Simple sine wave generator for testing the audio graph.
///
/// This is used as the Phase 1A proof-of-concept: a Rust-native "plugin"
/// that generates audio, proving the engine→device→output pipeline works.
pub struct SineGenerator {
    phase: f64,
    frequency: f64,
    amplitude: f64,
    sample_rate: f64,
}

impl SineGenerator {
    pub fn new(frequency: f64, amplitude: f64) -> Self {
        Self {
            phase: 0.0,
            frequency,
            amplitude,
            sample_rate: 44100.0,
        }
    }

    /// Generate sine wave into a buffer.
    pub fn generate(&mut self, buffer: &mut AudioBuffer, sample_rate: u32) {
        self.sample_rate = sample_rate as f64;
        let phase_inc = self.frequency / self.sample_rate;

        for frame in 0..buffer.frames {
            let sample = (self.phase * 2.0 * std::f64::consts::PI).sin() * self.amplitude;
            let s = sample as f32;

            let idx = frame * buffer.channels;
            buffer.data[idx] = s;       // Left
            if buffer.channels > 1 {
                buffer.data[idx + 1] = s; // Right
            }

            self.phase += phase_inc;
            if self.phase >= 1.0 {
                self.phase -= 1.0;
            }
        }
    }
}

impl AudioPlugin for SineGenerator {
    fn process(&mut self, buffer: &mut AudioBuffer, sample_rate: u32) {
        self.generate(buffer, sample_rate);
    }

    fn id(&self) -> &str {
        "pydaw.sine_generator"
    }

    fn name(&self) -> &str {
        "Sine Generator (PoC)"
    }

    fn set_parameter(&mut self, index: u32, value: f64) {
        match index {
            0 => self.frequency = value.clamp(20.0, 20000.0),
            1 => self.amplitude = value.clamp(0.0, 1.0),
            _ => {}
        }
    }

    fn get_parameter(&self, index: u32) -> f64 {
        match index {
            0 => self.frequency,
            1 => self.amplitude,
            _ => 0.0,
        }
    }

    fn parameter_count(&self) -> u32 {
        2
    }

    fn parameter_name(&self, index: u32) -> String {
        match index {
            0 => "Frequency".to_string(),
            1 => "Amplitude".to_string(),
            _ => String::new(),
        }
    }

    fn save_state(&self) -> Vec<u8> {
        let state = format!("{},{}", self.frequency, self.amplitude);
        state.into_bytes()
    }

    fn load_state(&mut self, data: &[u8]) -> Result<(), String> {
        let s = std::str::from_utf8(data).map_err(|e| e.to_string())?;
        let parts: Vec<&str> = s.split(',').collect();
        if parts.len() >= 2 {
            self.frequency = parts[0].parse().map_err(|e: std::num::ParseFloatError| e.to_string())?;
            self.amplitude = parts[1].parse().map_err(|e: std::num::ParseFloatError| e.to_string())?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Plugin Slot — manages one plugin instance on a track
// ---------------------------------------------------------------------------

/// A plugin slot on a track. Holds the plugin instance and metadata.
pub struct PluginSlot {
    pub slot_index: u8,
    pub plugin: Option<Box<dyn AudioPlugin>>,
    pub enabled: bool,
}

impl PluginSlot {
    pub fn new(slot_index: u8) -> Self {
        Self {
            slot_index,
            plugin: None,
            enabled: true,
        }
    }

    /// Process audio through this slot (if a plugin is loaded and enabled).
    pub fn process(&mut self, buffer: &mut AudioBuffer, sample_rate: u32) {
        if !self.enabled {
            return;
        }
        if let Some(ref mut plugin) = self.plugin {
            plugin.process(buffer, sample_rate);
        }
    }
}
