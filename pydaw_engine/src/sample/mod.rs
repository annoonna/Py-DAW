// ==========================================================================
// Sample Module — Audio sample loading, storage, and playback primitives
// ==========================================================================
// v0.0.20.671 — Phase R5
//
// Foundation for ProSampler, MultiSample, and DrumMachine instruments.
// All sample data is stored as Arc<Vec<f32>> for zero-copy sharing
// across voices and threads.
//
// Rules:
//   ✅ SampleData is immutable after creation (Arc-shared)
//   ✅ WAV loading happens on non-audio thread
//   ✅ Voice playback is zero-alloc (pre-allocated buffers)
//   ❌ NO allocations during audio processing
// ==========================================================================

pub mod voice;
pub mod voice_pool;

use std::sync::Arc;

// Re-exports
pub use voice::{SampleVoice, LoopMode, VoiceState};
#[allow(unused_imports)]
pub use voice_pool::{VoicePool, StealMode};

// ---------------------------------------------------------------------------
// SampleData — Immutable audio sample in memory
// ---------------------------------------------------------------------------

/// Immutable audio sample data, shared via Arc across voices.
///
/// Audio is stored as interleaved f32 (always stereo after loading).
/// Original file metadata is preserved for pitch calculation.
#[derive(Clone)]
pub struct SampleData {
    /// Interleaved stereo f32 samples [L0, R0, L1, R1, ...]
    pub data: Arc<Vec<f32>>,
    /// Number of channels (always 2 after loading — mono is converted)
    pub channels: u16,
    /// Original sample rate of the file
    pub sample_rate: u32,
    /// Number of frames (samples per channel)
    pub frames: usize,
    /// Root note (MIDI note number, default 60 = C4)
    pub root_note: u8,
    /// Fine tune in cents (-100 to +100)
    pub fine_tune: i8,
    /// Optional sample name
    pub name: String,
}

impl std::fmt::Debug for SampleData {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SampleData")
            .field("name", &self.name)
            .field("channels", &self.channels)
            .field("sample_rate", &self.sample_rate)
            .field("frames", &self.frames)
            .field("root_note", &self.root_note)
            .field("fine_tune", &self.fine_tune)
            .finish()
    }
}

impl SampleData {
    /// Create SampleData from raw interleaved stereo f32 data.
    pub fn from_raw(
        data: Vec<f32>,
        channels: u16,
        sample_rate: u32,
        name: String,
    ) -> Self {
        let frames = if channels > 0 { data.len() / channels as usize } else { 0 };
        Self {
            data: Arc::new(data),
            channels,
            sample_rate,
            frames,
            root_note: 60, // C4
            fine_tune: 0,
            name,
        }
    }

    /// Load a WAV file from disk.
    ///
    /// Supports PCM 8/16/24/32-bit integer and 32-bit float.
    /// Mono files are automatically converted to stereo.
    /// NOT audio-thread safe — call from loading thread only.
    pub fn load_wav(path: &str) -> Result<Self, String> {
        let reader = hound::WavReader::open(path)
            .map_err(|e| format!("Failed to open WAV '{}': {}", path, e))?;

        let spec = reader.spec();
        let channels = spec.channels;
        let sample_rate = spec.sample_rate;

        // Read all samples as f32
        let raw_samples: Vec<f32> = match spec.sample_format {
            hound::SampleFormat::Int => {
                let bits = spec.bits_per_sample;
                let max_val = (1u32 << (bits - 1)) as f32;
                reader
                    .into_samples::<i32>()
                    .filter_map(|s| s.ok())
                    .map(|s| s as f32 / max_val)
                    .collect()
            }
            hound::SampleFormat::Float => {
                reader
                    .into_samples::<f32>()
                    .filter_map(|s| s.ok())
                    .collect()
            }
        };

        if raw_samples.is_empty() {
            return Err(format!("WAV '{}' is empty", path));
        }

        let frames = raw_samples.len() / channels as usize;

        // Convert to stereo interleaved if mono
        let stereo_data = if channels == 1 {
            mono_to_stereo(&raw_samples)
        } else if channels == 2 {
            raw_samples
        } else {
            // Downmix multi-channel to stereo
            downmix_to_stereo(&raw_samples, channels as usize)
        };

        // Extract filename for name
        let name = path
            .rsplit('/')
            .next()
            .unwrap_or(path)
            .rsplit('\\')
            .next()
            .unwrap_or(path)
            .to_string();

        Ok(Self {
            data: Arc::new(stereo_data),
            channels: 2,
            sample_rate,
            frames,
            root_note: 60,
            fine_tune: 0,
            name,
        })
    }

    /// Load WAV with a specific root note.
    pub fn load_wav_with_root(path: &str, root_note: u8) -> Result<Self, String> {
        let mut sample = Self::load_wav(path)?;
        sample.root_note = root_note;
        Ok(sample)
    }

    /// Get a sample at a specific frame and channel (0=L, 1=R).
    /// Returns 0.0 for out-of-bounds access.
    #[inline]
    pub fn get_sample(&self, frame: usize, channel: usize) -> f32 {
        let idx = frame * self.channels as usize + channel;
        if idx < self.data.len() {
            self.data[idx]
        } else {
            0.0
        }
    }

    /// Get stereo frame (L, R) at a specific frame index.
    #[inline]
    pub fn get_frame(&self, frame: usize) -> (f32, f32) {
        let idx = frame * 2;
        if idx + 1 < self.data.len() {
            (self.data[idx], self.data[idx + 1])
        } else {
            (0.0, 0.0)
        }
    }

    /// Duration in seconds.
    pub fn duration_secs(&self) -> f64 {
        if self.sample_rate > 0 {
            self.frames as f64 / self.sample_rate as f64
        } else {
            0.0
        }
    }

    /// Calculate playback rate for a given MIDI note.
    /// Rate 1.0 = original pitch (root_note), 2.0 = one octave up, etc.
    #[inline]
    pub fn pitch_ratio(&self, midi_note: u8) -> f64 {
        let semitone_diff = midi_note as f64 - self.root_note as f64
            + self.fine_tune as f64 / 100.0;
        2.0f64.powf(semitone_diff / 12.0)
    }

    /// Calculate playback rate including sample-rate conversion.
    /// Use this when the engine SR differs from the file SR.
    #[inline]
    pub fn playback_rate(&self, midi_note: u8, engine_sr: u32) -> f64 {
        let pitch = self.pitch_ratio(midi_note);
        let sr_ratio = self.sample_rate as f64 / engine_sr as f64;
        pitch * sr_ratio
    }
}

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

/// Convert mono samples to interleaved stereo (duplicate L→R).
fn mono_to_stereo(mono: &[f32]) -> Vec<f32> {
    let mut stereo = Vec::with_capacity(mono.len() * 2);
    for &s in mono {
        stereo.push(s);
        stereo.push(s);
    }
    stereo
}

/// Downmix N-channel audio to stereo.
fn downmix_to_stereo(data: &[f32], channels: usize) -> Vec<f32> {
    if channels == 0 { return Vec::new(); }
    let frames = data.len() / channels;
    let mut stereo = Vec::with_capacity(frames * 2);
    for frame in 0..frames {
        let base = frame * channels;
        let l = data[base]; // First channel → L
        let r = if channels > 1 { data[base + 1] } else { l }; // Second → R
        stereo.push(l);
        stereo.push(r);
    }
    stereo
}

/// Resample audio data from source SR to target SR using linear interpolation.
/// Input/output are interleaved stereo.
pub fn resample_linear(data: &[f32], src_sr: u32, dst_sr: u32) -> Vec<f32> {
    if src_sr == dst_sr || data.len() < 4 {
        return data.to_vec();
    }
    let src_frames = data.len() / 2;
    let ratio = dst_sr as f64 / src_sr as f64;
    let dst_frames = (src_frames as f64 * ratio).ceil() as usize;
    let mut output = Vec::with_capacity(dst_frames * 2);

    for i in 0..dst_frames {
        let src_pos = i as f64 / ratio;
        let idx = src_pos as usize;
        let frac = (src_pos - idx as f64) as f32;

        let idx0 = idx.min(src_frames - 1);
        let idx1 = (idx + 1).min(src_frames - 1);

        let l = data[idx0 * 2] + (data[idx1 * 2] - data[idx0 * 2]) * frac;
        let r = data[idx0 * 2 + 1] + (data[idx1 * 2 + 1] - data[idx0 * 2 + 1]) * frac;

        output.push(l);
        output.push(r);
    }
    output
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sample_data_from_raw() {
        let data = vec![0.1, -0.1, 0.2, -0.2, 0.3, -0.3];
        let sd = SampleData::from_raw(data, 2, 44100, "test".to_string());
        assert_eq!(sd.frames, 3);
        assert_eq!(sd.channels, 2);
        assert_eq!(sd.sample_rate, 44100);
        assert!((sd.get_sample(0, 0) - 0.1).abs() < 1e-6);
        assert!((sd.get_sample(0, 1) - (-0.1)).abs() < 1e-6);
        assert!((sd.get_sample(2, 0) - 0.3).abs() < 1e-6);
    }

    #[test]
    fn test_get_frame() {
        let data = vec![0.5, -0.5, 0.8, -0.8];
        let sd = SampleData::from_raw(data, 2, 44100, "test".to_string());
        let (l, r) = sd.get_frame(1);
        assert!((l - 0.8).abs() < 1e-6);
        assert!((r - (-0.8)).abs() < 1e-6);
        // Out of bounds
        let (l, r) = sd.get_frame(999);
        assert_eq!(l, 0.0);
        assert_eq!(r, 0.0);
    }

    #[test]
    fn test_mono_to_stereo() {
        let mono = vec![0.1, 0.2, 0.3];
        let stereo = mono_to_stereo(&mono);
        assert_eq!(stereo.len(), 6);
        assert!((stereo[0] - 0.1).abs() < 1e-6); // L
        assert!((stereo[1] - 0.1).abs() < 1e-6); // R (same as L)
        assert!((stereo[4] - 0.3).abs() < 1e-6);
    }

    #[test]
    fn test_pitch_ratio() {
        let sd = SampleData::from_raw(vec![0.0; 4], 2, 44100, "t".to_string());
        // Same note = 1.0
        assert!((sd.pitch_ratio(60) - 1.0).abs() < 1e-6);
        // Octave up = 2.0
        assert!((sd.pitch_ratio(72) - 2.0).abs() < 0.001);
        // Octave down = 0.5
        assert!((sd.pitch_ratio(48) - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_playback_rate_sr_conversion() {
        let mut sd = SampleData::from_raw(vec![0.0; 4], 2, 44100, "t".to_string());
        sd.root_note = 60;
        // Same note, same SR
        assert!((sd.playback_rate(60, 44100) - 1.0).abs() < 1e-6);
        // Same note, engine at 48000 but sample at 44100
        let rate = sd.playback_rate(60, 48000);
        let expected = 44100.0 / 48000.0;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_resample_linear_identity() {
        let data = vec![0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4];
        let out = resample_linear(&data, 44100, 44100);
        assert_eq!(out.len(), data.len());
        for (a, b) in out.iter().zip(data.iter()) {
            assert!((a - b).abs() < 1e-6);
        }
    }

    #[test]
    fn test_resample_linear_upsample() {
        // 2 frames at 22050 → ~4 frames at 44100
        let data = vec![0.0, 0.0, 1.0, 1.0];
        let out = resample_linear(&data, 22050, 44100);
        assert!(out.len() >= 6); // at least 3 frames
        // First frame should be 0.0
        assert!(out[0].abs() < 0.01);
        // Last frame should be near 1.0
        assert!(out[out.len() - 2] > 0.5);
    }

    #[test]
    fn test_duration() {
        let sd = SampleData::from_raw(vec![0.0; 88200], 2, 44100, "t".to_string());
        assert!((sd.duration_secs() - 1.0).abs() < 0.001);
    }
}
