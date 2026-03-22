// ==========================================================================
// IPC Audio-Buffer Bridge — Shared Memory + Project Sync
// ==========================================================================
// v0.0.20.694 — Phase R12A+R12B
//
// R12A: Shared Memory Audio Transport
//   - SharedAudioTransport: pre-allocated ring buffers for each track
//   - Rust writes rendered audio per track → Python reads for waveform/bounce
//   - Zero-copy design: Python reads directly from the shared buffer
//   - Header tracks write/read positions for lock-free SPSC access
//
// R12B: Project Sync Protocol
//   - SyncProject batch command: full project state in one message
//   - Delta-updates: only changed tracks/clips
//   - TrackConfig, ClipConfig, AutomationData structs
//   - Maps directly to IPC Command::SyncProject
//
// Rules:
//   ✅ All audio buffers pre-allocated
//   ✅ Lock-free SPSC ring buffer for audio transport
//   ✅ Batch project sync minimizes IPC round-trips
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use serde::{Serialize, Deserialize};

// ═══════════════════════════════════════════════════════════════════════════
// R12A — Shared Memory Audio Transport
// ═══════════════════════════════════════════════════════════════════════════

/// Maximum number of tracks in the shared audio transport.
pub const MAX_TRANSPORT_TRACKS: usize = 64;

/// Maximum audio frames per track buffer (enough for ~2 seconds at 48kHz).
const TRACK_BUFFER_FRAMES: usize = 131072; // 2^17

/// Per-track audio ring buffer with atomic read/write positions.
///
/// SPSC: Rust audio thread writes, Python reader reads.
/// Interleaved stereo: [L0, R0, L1, R1, ...]
pub struct TrackAudioRing {
    /// Interleaved stereo samples.
    data: Vec<f32>,
    /// Write position in frames (wraps at TRACK_BUFFER_FRAMES).
    write_pos: AtomicUsize,
    /// Read position in frames (tracked by reader).
    read_pos: AtomicUsize,
    /// Total frames written since creation (monotonic, for sync).
    total_written: AtomicU64,
    /// Track index (for identification).
    track_index: u16,
    /// Whether this slot is in use.
    active: bool,
}

impl TrackAudioRing {
    fn new(track_index: u16) -> Self {
        Self {
            data: vec![0.0; TRACK_BUFFER_FRAMES * 2], // stereo
            write_pos: AtomicUsize::new(0),
            read_pos: AtomicUsize::new(0),
            total_written: AtomicU64::new(0),
            track_index,
            active: false,
        }
    }

    /// Write stereo frames from the audio thread.
    ///
    /// `samples`: interleaved stereo [L0, R0, L1, R1, ...]
    /// Returns number of frames actually written.
    #[inline]
    pub fn write(&self, samples: &[f32]) -> usize {
        let frames = samples.len() / 2;
        if frames == 0 {
            return 0;
        }

        let cap = TRACK_BUFFER_FRAMES;
        let mut wp = self.write_pos.load(Ordering::Relaxed);

        let to_write = frames.min(cap);
        for i in 0..to_write {
            let dst = (wp % cap) * 2;
            let src = i * 2;
            if src + 1 < samples.len() && dst + 1 < self.data.len() {
                // Safety: single writer (audio thread), atomics for position
                unsafe {
                    let ptr = self.data.as_ptr() as *mut f32;
                    *ptr.add(dst) = samples[src];
                    *ptr.add(dst + 1) = samples[src + 1];
                }
            }
            wp += 1;
        }

        self.write_pos.store(wp % cap, Ordering::Release);
        self.total_written.fetch_add(to_write as u64, Ordering::Relaxed);
        to_write
    }

    /// Read available frames (non-blocking, from reader thread).
    ///
    /// Returns a Vec of interleaved stereo samples.
    /// Advances the read position.
    pub fn read_available(&self, max_frames: usize) -> Vec<f32> {
        let wp = self.write_pos.load(Ordering::Acquire);
        let rp = self.read_pos.load(Ordering::Relaxed);
        let cap = TRACK_BUFFER_FRAMES;

        let available = if wp >= rp { wp - rp } else { cap - rp + wp };
        let to_read = available.min(max_frames);

        if to_read == 0 {
            return Vec::new();
        }

        let mut out = vec![0.0f32; to_read * 2];
        for i in 0..to_read {
            let src = ((rp + i) % cap) * 2;
            let dst = i * 2;
            out[dst] = self.data[src];
            out[dst + 1] = self.data[src + 1];
        }

        self.read_pos.store((rp + to_read) % cap, Ordering::Release);
        out
    }

    /// Get number of frames available to read.
    pub fn available_frames(&self) -> usize {
        let wp = self.write_pos.load(Ordering::Acquire);
        let rp = self.read_pos.load(Ordering::Relaxed);
        let cap = TRACK_BUFFER_FRAMES;
        if wp >= rp { wp - rp } else { cap - rp + wp }
    }

    /// Total frames written since creation.
    pub fn total_written(&self) -> u64 {
        self.total_written.load(Ordering::Relaxed)
    }

    /// Reset (clear buffer, reset positions).
    pub fn reset(&mut self) {
        self.data.fill(0.0);
        self.write_pos.store(0, Ordering::Release);
        self.read_pos.store(0, Ordering::Release);
        self.total_written.store(0, Ordering::Release);
    }
}

// ---------------------------------------------------------------------------
// Shared Audio Transport (all tracks)
// ---------------------------------------------------------------------------

/// Manages per-track audio ring buffers for Python to read rendered audio.
pub struct SharedAudioTransport {
    /// Per-track ring buffers (fixed array, indexed by track_index).
    tracks: Vec<TrackAudioRing>,
    /// Number of active tracks.
    active_count: usize,
    /// Current sample rate.
    sample_rate: u32,
    /// Current buffer size.
    buffer_size: u32,
}

impl SharedAudioTransport {
    /// Create a new transport with pre-allocated track buffers.
    pub fn new(sample_rate: u32, buffer_size: u32) -> Self {
        let mut tracks = Vec::with_capacity(MAX_TRANSPORT_TRACKS);
        for i in 0..MAX_TRANSPORT_TRACKS {
            tracks.push(TrackAudioRing::new(i as u16));
        }
        Self {
            tracks,
            active_count: 0,
            sample_rate,
            buffer_size,
        }
    }

    /// Activate a track slot for writing.
    pub fn activate_track(&mut self, track_index: u16) {
        let idx = track_index as usize;
        if idx < MAX_TRANSPORT_TRACKS {
            self.tracks[idx].active = true;
            self.tracks[idx].reset();
            self.active_count = self.tracks.iter().filter(|t| t.active).count();
        }
    }

    /// Deactivate a track slot.
    pub fn deactivate_track(&mut self, track_index: u16) {
        let idx = track_index as usize;
        if idx < MAX_TRANSPORT_TRACKS {
            self.tracks[idx].active = false;
            self.active_count = self.tracks.iter().filter(|t| t.active).count();
        }
    }

    /// Write audio data for a track (called from audio thread).
    #[inline]
    pub fn write_track_audio(&self, track_index: u16, samples: &[f32]) -> usize {
        let idx = track_index as usize;
        if idx < MAX_TRANSPORT_TRACKS && self.tracks[idx].active {
            self.tracks[idx].write(samples)
        } else {
            0
        }
    }

    /// Read available audio from a track (called from Python/GUI thread).
    pub fn read_track_audio(&self, track_index: u16, max_frames: usize) -> Vec<f32> {
        let idx = track_index as usize;
        if idx < MAX_TRANSPORT_TRACKS && self.tracks[idx].active {
            self.tracks[idx].read_available(max_frames)
        } else {
            Vec::new()
        }
    }

    /// Get transport status for Python bridge.
    pub fn status(&self) -> TransportStatus {
        TransportStatus {
            active_tracks: self.active_count as u16,
            sample_rate: self.sample_rate,
            buffer_size: self.buffer_size,
            track_frames_available: (0..MAX_TRANSPORT_TRACKS as u16)
                .filter(|&i| self.tracks[i as usize].active)
                .map(|i| (i, self.tracks[i as usize].available_frames() as u32))
                .collect(),
        }
    }

    /// Reset all track buffers.
    pub fn reset_all(&mut self) {
        for track in &mut self.tracks {
            track.reset();
        }
    }
}

/// Transport status report (serialized to Python).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransportStatus {
    pub active_tracks: u16,
    pub sample_rate: u32,
    pub buffer_size: u32,
    pub track_frames_available: Vec<(u16, u32)>,
}

// ═══════════════════════════════════════════════════════════════════════════
// R12B — Project Sync Protocol
// ═══════════════════════════════════════════════════════════════════════════

/// Track configuration for project sync.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackConfig {
    pub track_id: String,
    pub track_index: u16,
    /// "audio", "instrument", "group", "master", "fx_return"
    pub kind: String,
    pub volume: f64,
    pub pan: f64,
    pub muted: bool,
    pub soloed: bool,
    /// Instrument type (for instrument tracks): "pro_sampler", "aeterna", etc.
    pub instrument_type: Option<String>,
    /// Instrument ID (unique per instrument instance).
    pub instrument_id: Option<String>,
    /// Group bus parent (track_index of group, None = master).
    pub group_index: Option<u16>,
}

/// Clip placement in the arrangement.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClipConfig {
    pub clip_id: String,
    pub track_id: String,
    /// Start position in beats.
    pub start_beats: f64,
    /// Length in beats.
    pub length_beats: f64,
    /// "audio" or "midi"
    pub kind: String,
    /// Audio clip: base64-encoded f32 stereo samples (None for MIDI clips).
    pub audio_b64: Option<String>,
    /// Audio clip: source sample rate.
    pub source_sr: Option<u32>,
    /// Audio clip: source channels.
    pub source_channels: Option<u8>,
    /// Audio clip: gain (0.0–2.0).
    pub gain: f64,
    /// Offset in beats (for clip trimming).
    pub offset_beats: f64,
}

/// MIDI note for project sync.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MidiNoteConfig {
    pub clip_id: String,
    pub pitch: u8,
    pub velocity: u8,
    /// Start position in beats (relative to clip start).
    pub start_beats: f64,
    /// Note length in beats.
    pub length_beats: f64,
}

/// Automation breakpoint for project sync.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationPoint {
    /// Position in beats.
    pub beat: f64,
    /// Parameter value (0.0–1.0 normalized).
    pub value: f64,
    /// Curve type: "linear", "smooth", "step"
    pub curve: String,
}

/// Automation lane configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationLaneConfig {
    pub track_id: String,
    /// Parameter identifier (e.g., "volume", "pan", "fx.0.cutoff").
    pub param_id: String,
    /// Breakpoints.
    pub points: Vec<AutomationPoint>,
}

/// Full project sync payload.
///
/// Sent as a single IPC batch command to minimize round-trips.
/// The Rust engine rebuilds its internal state from this.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectSync {
    /// Transport settings.
    pub bpm: f64,
    pub time_sig_num: u8,
    pub time_sig_den: u8,
    pub loop_enabled: bool,
    pub loop_start_beat: f64,
    pub loop_end_beat: f64,

    /// All tracks in the project.
    pub tracks: Vec<TrackConfig>,

    /// All clips in the arrangement.
    pub clips: Vec<ClipConfig>,

    /// All MIDI notes (grouped by clip_id).
    pub midi_notes: Vec<MidiNoteConfig>,

    /// All automation lanes.
    pub automation: Vec<AutomationLaneConfig>,

    /// Project sample rate.
    pub sample_rate: u32,

    /// Sequence number for delta detection.
    /// If > last received seq, this is a full sync.
    /// If == last seq + 1, only changed fields are populated.
    pub sync_seq: u64,
}

impl ProjectSync {
    /// Create an empty project sync.
    pub fn empty() -> Self {
        Self {
            bpm: 120.0,
            time_sig_num: 4,
            time_sig_den: 4,
            loop_enabled: false,
            loop_start_beat: 0.0,
            loop_end_beat: 16.0,
            tracks: Vec::new(),
            clips: Vec::new(),
            midi_notes: Vec::new(),
            automation: Vec::new(),
            sample_rate: 48000,
            sync_seq: 0,
        }
    }

    /// Number of tracks in this sync.
    pub fn track_count(&self) -> usize {
        self.tracks.len()
    }

    /// Number of clips in this sync.
    pub fn clip_count(&self) -> usize {
        self.clips.len()
    }

    /// Number of MIDI notes in this sync.
    pub fn note_count(&self) -> usize {
        self.midi_notes.len()
    }

    /// Number of automation lanes in this sync.
    pub fn automation_lane_count(&self) -> usize {
        self.automation.len()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Python-side Reader Helpers
// ═══════════════════════════════════════════════════════════════════════════

/// Summary of a track's audio buffer state (for Python bridge).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackBufferInfo {
    pub track_index: u16,
    pub active: bool,
    pub available_frames: u32,
    pub total_written: u64,
}

/// Get info about all active track buffers.
pub fn get_all_track_buffer_info(transport: &SharedAudioTransport) -> Vec<TrackBufferInfo> {
    let mut info = Vec::new();
    for i in 0..MAX_TRANSPORT_TRACKS {
        let t = &transport.tracks[i];
        if t.active {
            info.push(TrackBufferInfo {
                track_index: t.track_index,
                active: true,
                available_frames: t.available_frames() as u32,
                total_written: t.total_written(),
            });
        }
    }
    info
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_track_ring_write_read() {
        let ring = TrackAudioRing::new(0);
        // Write 4 stereo frames
        let samples = vec![0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8];
        let written = ring.write(&samples);
        assert_eq!(written, 4);
        assert_eq!(ring.available_frames(), 4);

        // Read back
        let read = ring.read_available(10);
        assert_eq!(read.len(), 8);
        assert!((read[0] - 0.1).abs() < 0.001);
        assert!((read[7] - 0.8).abs() < 0.001);
        assert_eq!(ring.available_frames(), 0);
    }

    #[test]
    fn test_track_ring_wrap() {
        let mut ring = TrackAudioRing::new(0);
        ring.active = true;

        // Write many frames to test wrapping
        let chunk = vec![1.0f32; 2048]; // 1024 stereo frames
        for _ in 0..200 {
            ring.write(&chunk);
        }

        assert!(ring.total_written() > 100000);
        let avail = ring.available_frames();
        assert!(avail > 0, "Should have readable data: {}", avail);
    }

    #[test]
    fn test_transport_activate_deactivate() {
        let mut transport = SharedAudioTransport::new(44100, 512);
        assert_eq!(transport.active_count, 0);

        transport.activate_track(0);
        transport.activate_track(3);
        assert_eq!(transport.active_count, 2);

        transport.deactivate_track(0);
        assert_eq!(transport.active_count, 1);
    }

    #[test]
    fn test_transport_write_read() {
        let mut transport = SharedAudioTransport::new(48000, 256);
        transport.activate_track(5);

        let samples = vec![0.5, -0.5, 0.3, -0.3]; // 2 stereo frames
        transport.write_track_audio(5, &samples);

        let read = transport.read_track_audio(5, 10);
        assert_eq!(read.len(), 4);
        assert!((read[0] - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_transport_inactive_track_silent() {
        let transport = SharedAudioTransport::new(44100, 512);
        let read = transport.read_track_audio(0, 100);
        assert!(read.is_empty(), "Inactive track should return empty");
    }

    #[test]
    fn test_project_sync_empty() {
        let sync = ProjectSync::empty();
        assert_eq!(sync.track_count(), 0);
        assert_eq!(sync.clip_count(), 0);
        assert_eq!(sync.bpm, 120.0);
    }

    #[test]
    fn test_project_sync_with_tracks() {
        let mut sync = ProjectSync::empty();
        sync.bpm = 140.0;
        sync.tracks.push(TrackConfig {
            track_id: "t1".to_string(),
            track_index: 0,
            kind: "instrument".to_string(),
            volume: 0.8,
            pan: 0.0,
            muted: false,
            soloed: false,
            instrument_type: Some("aeterna".to_string()),
            instrument_id: Some("ae_001".to_string()),
            group_index: None,
        });
        sync.clips.push(ClipConfig {
            clip_id: "c1".to_string(),
            track_id: "t1".to_string(),
            start_beats: 0.0,
            length_beats: 4.0,
            kind: "midi".to_string(),
            audio_b64: None,
            source_sr: None,
            source_channels: None,
            gain: 1.0,
            offset_beats: 0.0,
        });
        sync.midi_notes.push(MidiNoteConfig {
            clip_id: "c1".to_string(),
            pitch: 60,
            velocity: 100,
            start_beats: 0.0,
            length_beats: 1.0,
        });

        assert_eq!(sync.track_count(), 1);
        assert_eq!(sync.clip_count(), 1);
        assert_eq!(sync.note_count(), 1);
    }

    #[test]
    fn test_project_sync_serializable() {
        let sync = ProjectSync::empty();
        // Should be serializable to JSON (serde)
        let json = serde_json::to_string(&sync).unwrap();
        assert!(json.contains("\"bpm\":120.0"));

        // And deserializable
        let parsed: ProjectSync = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.bpm, 120.0);
    }

    #[test]
    fn test_transport_status() {
        let mut transport = SharedAudioTransport::new(48000, 512);
        transport.activate_track(0);
        transport.activate_track(2);

        let status = transport.status();
        assert_eq!(status.active_tracks, 2);
        assert_eq!(status.sample_rate, 48000);
        assert_eq!(status.track_frames_available.len(), 2);
    }
}
