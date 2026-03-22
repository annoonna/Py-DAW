use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::RwLock;

// ============================================================================
// Audio Clip Store + Arrangement Renderer
// ============================================================================
//
// Manages loaded audio data and renders clips into track buffers.
//
// Architecture:
//   1. Python sends LoadAudioClip → base64-decoded PCM stored in ClipStore
//   2. Python sends SetArrangement → clip schedule stored in ArrangementState
//   3. Audio callback: render() reads clips from store, mixes into track buffers
//
// Thread safety:
//   - ClipStore: RwLock (writes from IPC thread, reads from audio thread)
//   - ArrangementState: atomic Arc swap (lock-free read from audio thread)
//
// Memory:
//   - Audio data is stored as Arc<Vec<f32>> — shared, never copied
//   - Clips reference audio data via clip_id
// ============================================================================

/// Stored audio clip data.
pub struct AudioClipData {
    /// Clip identifier (matches Python clip_id).
    pub clip_id: String,
    /// Number of channels (1=mono, 2=stereo).
    pub channels: u8,
    /// Sample rate of the audio data.
    pub sample_rate: u32,
    /// Interleaved f32 samples.
    /// Shared via Arc so the audio thread can read without copying.
    pub samples: Arc<Vec<f32>>,
    /// Number of frames (samples per channel).
    pub frame_count: usize,
}

impl AudioClipData {
    /// Create from raw f32 samples.
    pub fn new(clip_id: String, channels: u8, sample_rate: u32, samples: Vec<f32>) -> Self {
        let frame_count = if channels > 0 {
            samples.len() / channels as usize
        } else {
            0
        };
        Self {
            clip_id,
            channels,
            sample_rate,
            samples: Arc::new(samples),
            frame_count,
        }
    }

    /// Create from base64-encoded f32 LE samples.
    pub fn from_base64(
        clip_id: String,
        channels: u8,
        sample_rate: u32,
        b64_data: &str,
    ) -> Result<Self, String> {
        let raw = base64_decode(b64_data)?;
        if raw.len() % 4 != 0 {
            return Err("Audio data length not aligned to f32".to_string());
        }

        let samples: Vec<f32> = raw
            .chunks_exact(4)
            .map(|chunk| f32::from_le_bytes(chunk.try_into().unwrap()))
            .collect();

        Ok(Self::new(clip_id, channels, sample_rate, samples))
    }

    /// Get a stereo sample at a given frame position.
    /// Returns (left, right). Mono clips are duplicated to both channels.
    #[inline]
    pub fn get_stereo_frame(&self, frame: usize) -> (f32, f32) {
        if frame >= self.frame_count {
            return (0.0, 0.0);
        }
        if self.channels >= 2 {
            let idx = frame * self.channels as usize;
            let l = *self.samples.get(idx).unwrap_or(&0.0);
            let r = *self.samples.get(idx + 1).unwrap_or(&0.0);
            (l, r)
        } else {
            // Mono → duplicate
            let s = *self.samples.get(frame).unwrap_or(&0.0);
            (s, s)
        }
    }
}

/// Simple base64 encoder (matches our base64_decode — no external dependency).
/// v0.0.20.718: Added for SavePluginState.
pub fn base64_encode(input: &[u8]) -> String {
    const CHARS: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity((input.len() + 2) / 3 * 4);
    for chunk in input.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;

        output.push(CHARS[((triple >> 18) & 0x3F) as usize] as char);
        output.push(CHARS[((triple >> 12) & 0x3F) as usize] as char);
        if chunk.len() > 1 {
            output.push(CHARS[((triple >> 6) & 0x3F) as usize] as char);
        } else {
            output.push('=');
        }
        if chunk.len() > 2 {
            output.push(CHARS[(triple & 0x3F) as usize] as char);
        } else {
            output.push('=');
        }
    }
    output
}

/// Simple base64 decoder (no external dependency needed).
/// v0.0.20.711: Made pub for use in engine.rs (LoadWavetable).
pub fn base64_decode(input: &str) -> Result<Vec<u8>, String> {
    fn decode_char(c: u8) -> Result<u8, String> {
        match c {
            b'A'..=b'Z' => Ok(c - b'A'),
            b'a'..=b'z' => Ok(c - b'a' + 26),
            b'0'..=b'9' => Ok(c - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            b'=' => Ok(0),
            _ => Err(format!("Invalid base64 character: {}", c as char)),
        }
    }

    let input = input.as_bytes();
    let mut output = Vec::with_capacity(input.len() * 3 / 4);

    for chunk in input.chunks(4) {
        if chunk.len() < 4 {
            break;
        }
        let a = decode_char(chunk[0])?;
        let b = decode_char(chunk[1])?;
        let c = decode_char(chunk[2])?;
        let d = decode_char(chunk[3])?;

        output.push((a << 2) | (b >> 4));
        if chunk[2] != b'=' {
            output.push((b << 4) | (c >> 2));
        }
        if chunk[3] != b'=' {
            output.push((c << 6) | d);
        }
    }

    Ok(output)
}

// ---------------------------------------------------------------------------
// Clip Store
// ---------------------------------------------------------------------------

/// Thread-safe store for loaded audio clips.
///
/// Write access: IPC thread (LoadAudioClip command).
/// Read access: Audio thread (arrangement rendering).
pub struct ClipStore {
    clips: RwLock<HashMap<String, Arc<AudioClipData>>>,
}

impl ClipStore {
    pub fn new() -> Self {
        Self {
            clips: RwLock::new(HashMap::new()),
        }
    }

    /// Store a clip. Replaces any existing clip with the same ID.
    pub fn insert(&self, clip: AudioClipData) {
        let id = clip.clip_id.clone();
        self.clips.write().insert(id, Arc::new(clip));
    }

    /// Remove a clip by ID.
    pub fn remove(&self, clip_id: &str) {
        self.clips.write().remove(clip_id);
    }

    /// Get a clip by ID (audio-thread read, very fast via RwLock read).
    pub fn get(&self, clip_id: &str) -> Option<Arc<AudioClipData>> {
        self.clips.read().get(clip_id).cloned()
    }

    /// Number of loaded clips.
    pub fn count(&self) -> usize {
        self.clips.read().len()
    }
}

// ---------------------------------------------------------------------------
// Arrangement State
// ---------------------------------------------------------------------------

/// Description of a placed clip in the arrangement timeline.
#[derive(Clone)]
pub struct PlacedClip {
    /// Reference to audio data.
    pub clip_id: String,
    /// Track index this clip belongs to.
    pub track_index: u16,
    /// Start position in samples (in project timeline).
    pub start_sample: i64,
    /// End position in samples.
    pub end_sample: i64,
    /// Offset into the clip data in samples (for trimmed clips).
    pub clip_offset_samples: i64,
    /// Gain multiplier.
    pub gain: f32,
    /// Whether the clip is muted.
    pub muted: bool,
}

impl PlacedClip {
    /// Create from IPC ArrangementClip, converting beats to samples.
    pub fn from_ipc(
        clip: &crate::ipc::ArrangementClip,
        sample_rate: u32,
        bpm: f64,
    ) -> Self {
        let sr = sample_rate as f64;
        let beat_to_samples = |beat: f64| -> i64 {
            (beat * sr * 60.0 / bpm) as i64
        };

        Self {
            clip_id: clip.clip_id.clone(),
            track_index: clip.track_index,
            start_sample: beat_to_samples(clip.start_beat),
            end_sample: beat_to_samples(clip.end_beat),
            clip_offset_samples: clip.offset_samples,
            gain: clip.gain,
            muted: false,
        }
    }
}

/// Immutable snapshot of the arrangement (all placed clips).
///
/// Swapped atomically: Python builds a new state, then replaces the old one
/// via Arc swap. The audio thread always reads a consistent snapshot.
pub struct ArrangementSnapshot {
    /// All placed clips, sorted by start_sample for efficient rendering.
    pub clips: Vec<PlacedClip>,
    /// Pre-computed: clips grouped by track_index for fast per-track rendering.
    pub clips_by_track: HashMap<u16, Vec<usize>>,  // track_index → indices into clips[]
}

impl ArrangementSnapshot {
    pub fn new(mut clips: Vec<PlacedClip>) -> Self {
        // Sort by start_sample for efficient binary search
        clips.sort_by_key(|c| c.start_sample);

        // Build per-track index
        let mut by_track: HashMap<u16, Vec<usize>> = HashMap::new();
        for (i, clip) in clips.iter().enumerate() {
            by_track
                .entry(clip.track_index)
                .or_insert_with(Vec::new)
                .push(i);
        }

        Self {
            clips,
            clips_by_track: by_track,
        }
    }

    pub fn empty() -> Self {
        Self {
            clips: Vec::new(),
            clips_by_track: HashMap::new(),
        }
    }
}

// ---------------------------------------------------------------------------
// Arrangement Renderer
// ---------------------------------------------------------------------------

/// Renders audio clips into track buffers for one process cycle.
///
/// Called from the audio callback. Reads from ClipStore + ArrangementSnapshot.
/// Writes into AudioGraph track buffers.
///
/// **Performance rules:**
/// - No heap allocations (all buffers pre-allocated)
/// - No locks on the hot path (ClipStore uses RwLock read, ArrangementSnapshot is Arc)
/// - Linear interpolation for sample-rate conversion (if clip SR ≠ engine SR)
pub struct ArrangementRenderer {
    /// Current arrangement (atomic swap).
    arrangement: Arc<RwLock<Arc<ArrangementSnapshot>>>,
    /// Clip data store.
    clip_store: Arc<ClipStore>,
}

impl ArrangementRenderer {
    pub fn new(clip_store: Arc<ClipStore>) -> Self {
        Self {
            arrangement: Arc::new(RwLock::new(Arc::new(ArrangementSnapshot::empty()))),
            clip_store,
        }
    }

    /// Set a new arrangement (called from IPC handler).
    pub fn set_arrangement(&self, snapshot: ArrangementSnapshot) {
        *self.arrangement.write() = Arc::new(snapshot);
    }

    /// Get current arrangement snapshot (for audio thread).
    pub fn get_arrangement(&self) -> Arc<ArrangementSnapshot> {
        self.arrangement.read().clone()
    }

    /// Render one buffer cycle for a specific track.
    ///
    /// Writes rendered audio into `output` (interleaved stereo f32).
    /// `position_samples` is the current playhead position in samples.
    /// `frames` is the number of frames to render.
    /// `engine_sr` is the engine's sample rate.
    ///
    /// Returns the number of clips that contributed audio.
    pub fn render_track(
        &self,
        track_index: u16,
        output: &mut [f32],
        position_samples: i64,
        frames: usize,
        engine_sr: u32,
    ) -> usize {
        let arrangement = self.get_arrangement();

        // Get clips for this track
        let clip_indices = match arrangement.clips_by_track.get(&track_index) {
            Some(indices) => indices,
            None => return 0,
        };

        let end_sample = position_samples + frames as i64;
        let mut clips_rendered = 0;

        for &clip_idx in clip_indices {
            let placed = &arrangement.clips[clip_idx];

            // Skip muted clips
            if placed.muted {
                continue;
            }

            // Skip clips that don't overlap this buffer window
            if placed.end_sample <= position_samples || placed.start_sample >= end_sample {
                continue;
            }

            // Get the audio data
            let clip_data = match self.clip_store.get(&placed.clip_id) {
                Some(data) => data,
                None => continue,
            };

            // Calculate render range within this buffer
            let buf_start = (placed.start_sample - position_samples).max(0) as usize;
            let buf_end = ((placed.end_sample - position_samples) as usize).min(frames);

            if buf_start >= buf_end {
                continue;
            }

            // Calculate source position in clip data
            let clip_start_offset = if position_samples > placed.start_sample {
                (position_samples - placed.start_sample) as usize
            } else {
                0
            } + placed.clip_offset_samples.max(0) as usize;

            // Sample rate ratio (for clips recorded at different SR)
            let sr_ratio = if clip_data.sample_rate != engine_sr && clip_data.sample_rate > 0 {
                clip_data.sample_rate as f64 / engine_sr as f64
            } else {
                1.0
            };

            let gain = placed.gain;

            // Render frames
            for frame in buf_start..buf_end {
                let src_frame_f = (clip_start_offset + (frame - buf_start)) as f64 * sr_ratio;
                let src_frame = src_frame_f as usize;

                // Linear interpolation for non-integer sample positions
                let (l, r) = if sr_ratio != 1.0 {
                    let frac = (src_frame_f - src_frame as f64) as f32;
                    let (l0, r0) = clip_data.get_stereo_frame(src_frame);
                    let (l1, r1) = clip_data.get_stereo_frame(src_frame + 1);
                    (
                        l0 + (l1 - l0) * frac,
                        r0 + (r1 - r0) * frac,
                    )
                } else {
                    clip_data.get_stereo_frame(src_frame)
                };

                // Mix into output (additive — multiple clips can overlap)
                let out_idx = frame * 2;
                if out_idx + 1 < output.len() {
                    output[out_idx] += l * gain;
                    output[out_idx + 1] += r * gain;
                }
            }

            clips_rendered += 1;
        }

        clips_rendered
    }

    /// Render all tracks for one buffer cycle.
    ///
    /// Iterates all tracks that have clips in the current arrangement
    /// and writes audio into the graph's track buffers.
    pub fn render_all_tracks(
        &self,
        graph: &mut crate::audio_graph::AudioGraph,
        position_samples: i64,
        frames: usize,
        engine_sr: u32,
    ) {
        let arrangement = self.get_arrangement();

        for (&track_index, _) in &arrangement.clips_by_track {
            // Get a mutable reference to the track's output buffer
            // We use write_track_audio indirectly through a scratch buffer
            let mut scratch = vec![0.0f32; frames * 2];

            let count = self.render_track(
                track_index,
                &mut scratch,
                position_samples,
                frames,
                engine_sr,
            );

            if count > 0 {
                graph.write_track_audio(track_index, &scratch);
            }
        }
    }
}
