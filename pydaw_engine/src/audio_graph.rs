use std::collections::HashMap;

use crate::ipc::TrackParam;

// ============================================================================
// Audio Graph — Real-time audio processing graph
// ============================================================================
//
// Design principles:
//   - No heap allocations in process() — all buffers pre-allocated
//   - Lock-free parameter updates via atomic floats
//   - Topological sort computed on graph change, cached for process()
//   - Compatible with future multi-threaded rendering (parallel independent paths)
// ============================================================================

/// Stereo audio buffer (interleaved f32).
#[derive(Clone)]
pub struct AudioBuffer {
    /// Interleaved L/R samples: [L0, R0, L1, R1, ...]
    pub data: Vec<f32>,
    /// Number of frames (samples per channel).
    pub frames: usize,
    /// Number of channels (always 2 for now).
    pub channels: usize,
}

impl AudioBuffer {
    pub fn new(frames: usize, channels: usize) -> Self {
        Self {
            data: vec![0.0; frames * channels],
            frames,
            channels,
        }
    }

    pub fn silence(&mut self) {
        self.data.fill(0.0);
    }

    /// Mix `other` into `self` (additive).
    pub fn mix_from(&mut self, other: &AudioBuffer) {
        debug_assert_eq!(self.data.len(), other.data.len());
        for (dst, src) in self.data.iter_mut().zip(other.data.iter()) {
            *dst += *src;
        }
    }

    /// Apply gain to all samples.
    pub fn apply_gain(&mut self, gain: f32) {
        for s in self.data.iter_mut() {
            *s *= gain;
        }
    }

    /// Apply stereo pan (equal-power pan law).
    pub fn apply_pan(&mut self, pan: f32) {
        let pan = pan.clamp(-1.0, 1.0);
        let x = (pan + 1.0) * 0.5;
        let gain_l = (x * std::f32::consts::FRAC_PI_2).cos();
        let gain_r = (x * std::f32::consts::FRAC_PI_2).sin();
        for frame in 0..self.frames {
            let idx = frame * self.channels;
            self.data[idx] *= gain_l;
            if self.channels > 1 {
                self.data[idx + 1] *= gain_r;
            }
        }
    }

    /// Get peak levels (L, R).
    pub fn peak_levels(&self) -> (f32, f32) {
        let mut peak_l: f32 = 0.0;
        let mut peak_r: f32 = 0.0;
        for frame in 0..self.frames {
            let idx = frame * self.channels;
            peak_l = peak_l.max(self.data[idx].abs());
            if self.channels > 1 {
                peak_r = peak_r.max(self.data[idx + 1].abs());
            }
        }
        (peak_l, peak_r)
    }

    /// Get RMS levels (L, R).
    pub fn rms_levels(&self) -> (f32, f32) {
        if self.frames == 0 {
            return (0.0, 0.0);
        }
        let mut sum_l: f64 = 0.0;
        let mut sum_r: f64 = 0.0;
        for frame in 0..self.frames {
            let idx = frame * self.channels;
            let l = self.data[idx] as f64;
            sum_l += l * l;
            if self.channels > 1 {
                let r = self.data[idx + 1] as f64;
                sum_r += r * r;
            }
        }
        let n = self.frames as f64;
        ((sum_l / n).sqrt() as f32, (sum_r / n).sqrt() as f32)
    }
}

// ---------------------------------------------------------------------------
// Track Node
// ---------------------------------------------------------------------------

/// A track node in the audio graph.
pub struct TrackNode {
    pub track_id: String,
    pub track_index: u16,
    pub kind: TrackKind,

    // Parameters (updated lock-free from command queue)
    pub volume: crate::lock_free::AtomicF32,
    pub pan: crate::lock_free::AtomicF32,
    pub mute: std::sync::atomic::AtomicBool,
    pub solo: std::sync::atomic::AtomicBool,

    // Pre-allocated output buffer (reused each process cycle)
    pub output_buffer: AudioBuffer,

    // Group routing: if Some, output goes to this group track index
    pub group_target: Option<u16>,

    // FX chain (Phase R4A) — serial effects chain per track
    pub fx_chain: crate::fx::chain::FxChain,

    // Instrument (Phase R6A) — MIDI-driven audio generator
    pub instrument: Option<Box<dyn crate::instruments::InstrumentNode>>,

    // External plugin slots (Phase P7) — VST3/CLAP/LV2 inserts
    // Processed AFTER instrument, BEFORE built-in FX chain.
    pub plugin_slots: Vec<crate::plugin_host::PluginSlot>,
}

/// Track type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrackKind {
    Audio,
    Instrument,
    Group,
    FxReturn,
    Master,
}

impl TrackKind {
    pub fn from_str(s: &str) -> Self {
        match s {
            "audio" => Self::Audio,
            "instrument" => Self::Instrument,
            "group" => Self::Group,
            "fx_return" => Self::FxReturn,
            "master" => Self::Master,
            _ => Self::Audio,
        }
    }
}

impl TrackNode {
    pub fn new(track_id: String, track_index: u16, kind: TrackKind, buffer_size: usize) -> Self {
        Self {
            track_id,
            track_index,
            kind,
            volume: crate::lock_free::AtomicF32::new(1.0),
            pan: crate::lock_free::AtomicF32::new(0.0),
            mute: std::sync::atomic::AtomicBool::new(false),
            solo: std::sync::atomic::AtomicBool::new(false),
            output_buffer: AudioBuffer::new(buffer_size, 2),
            group_target: None,
            fx_chain: crate::fx::chain::FxChain::new(buffer_size),
            instrument: None,
            plugin_slots: Vec::new(),
        }
    }

    /// Apply track parameters (volume, pan, mute) to the output buffer.
    /// Called after audio data has been written into `output_buffer`.
    ///
    /// Signal flow:
    ///   1. Pre-fader FX chain (if position == PreFader)
    ///   2. Volume + Pan
    ///   3. Post-fader FX chain (if position == PostFader)
    pub fn apply_params(&mut self) {
        self.apply_params_with_tempo(44100.0, 120.0);
    }

    /// Apply track parameters with sample rate and tempo context.
    pub fn apply_params_with_tempo(&mut self, sample_rate: f32, tempo_bpm: f64) {
        use std::sync::atomic::Ordering::Relaxed;

        if self.mute.load(Relaxed) {
            self.output_buffer.silence();
            return;
        }

        // External plugin slots (P7) — VST3/CLAP/LV2 inserts
        // Processed AFTER instrument, BEFORE built-in FX chain.
        for slot in &mut self.plugin_slots {
            slot.process(&mut self.output_buffer, sample_rate as u32);
        }

        // Pre-fader FX
        if self.fx_chain.position == crate::fx::chain::FxPosition::PreFader {
            self.fx_chain.process(&mut self.output_buffer, sample_rate, tempo_bpm);
        }

        let vol = self.volume.load(Relaxed);
        let pan = self.pan.load(Relaxed);

        self.output_buffer.apply_gain(vol);
        self.output_buffer.apply_pan(pan);

        // Post-fader FX
        if self.fx_chain.position == crate::fx::chain::FxPosition::PostFader {
            self.fx_chain.process(&mut self.output_buffer, sample_rate, tempo_bpm);
        }
    }

    /// Set a parameter from a Command.
    pub fn set_param(&self, param: TrackParam, value: f64) {
        use std::sync::atomic::Ordering::Relaxed;
        match param {
            TrackParam::Volume => self.volume.store(value as f32, Relaxed),
            TrackParam::Pan => self.pan.store(value as f32, Relaxed),
            TrackParam::Mute => self.mute.store(value > 0.5, Relaxed),
            TrackParam::Solo => self.solo.store(value > 0.5, Relaxed),
        }
    }
}

// ---------------------------------------------------------------------------
// Audio Graph
// ---------------------------------------------------------------------------

/// The real-time audio graph.
///
/// Holds all track nodes and computes the processing order via topological sort.
/// The `process()` method is called from the audio callback — NO allocations allowed.
pub struct AudioGraph {
    /// All track nodes, keyed by track_index.
    tracks: HashMap<u16, TrackNode>,

    /// Processing order (topologically sorted track indices).
    /// Regular tracks first, then group tracks, then master.
    process_order: Vec<u16>,

    /// Master track index (always last in process order).
    master_index: Option<u16>,

    /// Scratch buffer for mixing group inputs.
    group_mix_buf: AudioBuffer,

    /// Master output buffer (final output to audio device).
    master_output: AudioBuffer,

    /// Buffer size in frames.
    buffer_size: usize,

    /// Sample rate.
    pub sample_rate: u32,

    /// Current tempo in BPM (for tempo-synced FX like Delay).
    pub tempo_bpm: f64,

    /// Whether any track has solo enabled (cached).
    any_solo: bool,
}

impl AudioGraph {
    pub fn new(buffer_size: usize, sample_rate: u32) -> Self {
        Self {
            tracks: HashMap::new(),
            process_order: Vec::new(),
            master_index: None,
            group_mix_buf: AudioBuffer::new(buffer_size, 2),
            master_output: AudioBuffer::new(buffer_size, 2),
            buffer_size,
            sample_rate,
            tempo_bpm: 120.0,
            any_solo: false,
        }
    }

    /// Get the buffer size in frames.
    pub fn buffer_size(&self) -> usize {
        self.buffer_size
    }

    /// Get the master track index (if any).
    pub fn master_index(&self) -> Option<u16> {
        self.master_index
    }

    /// Add a track. Rebuilds the processing order.
    pub fn add_track(&mut self, track_id: String, track_index: u16, kind: TrackKind) {
        let node = TrackNode::new(track_id, track_index, kind, self.buffer_size);
        if kind == TrackKind::Master {
            self.master_index = Some(track_index);
        }
        self.tracks.insert(track_index, node);
        self.rebuild_order();
    }

    /// Remove a track. Rebuilds the processing order.
    pub fn remove_track(&mut self, track_id: &str) {
        let idx = self
            .tracks
            .iter()
            .find(|(_, n)| n.track_id == track_id)
            .map(|(&idx, _)| idx);
        if let Some(idx) = idx {
            if self.master_index == Some(idx) {
                self.master_index = None;
            }
            self.tracks.remove(&idx);
            self.rebuild_order();
        }
    }

    /// Set group routing for a track.
    pub fn set_group_routing(&mut self, child_index: u16, group_index: Option<u16>) {
        if let Some(track) = self.tracks.get_mut(&child_index) {
            track.group_target = group_index;
        }
        self.rebuild_order();
    }

    /// Get a track by index (for parameter updates).
    pub fn get_track(&self, index: u16) -> Option<&TrackNode> {
        self.tracks.get(&index)
    }

    /// Rebuild the topological processing order.
    ///
    /// Order: regular tracks → group tracks → master.
    /// Within each tier, order is by track_index (deterministic).
    fn rebuild_order(&mut self) {
        self.process_order.clear();

        let mut regular: Vec<u16> = Vec::new();
        let mut groups: Vec<u16> = Vec::new();

        for (&idx, node) in &self.tracks {
            match node.kind {
                TrackKind::Master => {} // Master is always last
                TrackKind::Group => groups.push(idx),
                _ => regular.push(idx),
            }
        }

        regular.sort();
        groups.sort();

        self.process_order.extend(regular);
        self.process_order.extend(groups);

        if let Some(master) = self.master_index {
            self.process_order.push(master);
        }
    }

    /// Process one audio buffer cycle. Called from the audio callback.
    ///
    /// **NO ALLOCATIONS** — all buffers are pre-allocated.
    ///
    /// Returns a reference to the master output buffer.
    pub fn process(&mut self) -> &AudioBuffer {
        // Update solo state cache
        self.any_solo = self
            .tracks
            .values()
            .any(|t| t.solo.load(std::sync::atomic::Ordering::Relaxed));

        // Clear master output
        self.master_output.silence();

        // Process each track in topological order
        for i in 0..self.process_order.len() {
            let track_idx = self.process_order[i];

            // Skip master — handled separately at the end
            if Some(track_idx) == self.master_index {
                continue;
            }

            // If the track has an instrument, let it generate audio into the buffer
            if let Some(track) = self.tracks.get_mut(&track_idx) {
                if track.instrument.is_some() {
                    // Build ProcessContext for the instrument
                    let ctx = crate::audio_node::ProcessContext {
                        frames: self.buffer_size,
                        sample_rate: self.sample_rate,
                        position_samples: 0, // TODO: from transport
                        position_beats: 0.0, // TODO: from transport
                        is_playing: true,
                        bpm: self.tempo_bpm,
                        time_sig_num: 4,
                        time_sig_den: 4,
                    };
                    // Instrument generates audio into the track's output buffer
                    if let Some(ref mut inst) = track.instrument {
                        inst.process(&mut track.output_buffer, &ctx);
                    }
                }
            }

            // Apply track params (volume, pan, mute, FX chain)
            // Safety: we access tracks mutably but only one at a time
            if let Some(track) = self.tracks.get_mut(&track_idx) {
                track.apply_params_with_tempo(self.sample_rate as f32, self.tempo_bpm);

                // Solo logic: if any track is solo'd, mute non-solo'd tracks
                if self.any_solo
                    && !track.solo.load(std::sync::atomic::Ordering::Relaxed)
                {
                    track.output_buffer.silence();
                }
            }

            // Route output to group or master
            let (group_target, peak_l, peak_r, rms_l, rms_r) = {
                if let Some(track) = self.tracks.get(&track_idx) {
                    let (pl, pr) = track.output_buffer.peak_levels();
                    let (rl, rr) = track.output_buffer.rms_levels();
                    (track.group_target, pl, pr, rl, rr)
                } else {
                    continue;
                }
            };

            // Store meter data (to be sent as Event later)
            let _ = (peak_l, peak_r, rms_l, rms_r); // TODO: write to meter ring

            if let Some(group_idx) = group_target {
                // Mix into group track's output buffer
                if group_idx != track_idx {
                    // We need to borrow two tracks — use unsafe split or copy
                    // For safety, copy via scratch buffer
                    let src_len = if let Some(src) = self.tracks.get(&track_idx) {
                        self.group_mix_buf.data[..src.output_buffer.data.len()]
                            .copy_from_slice(&src.output_buffer.data);
                        src.output_buffer.data.len()
                    } else {
                        0
                    };
                    if src_len > 0 {
                        if let Some(dst) = self.tracks.get_mut(&group_idx) {
                            for (d, s) in dst
                                .output_buffer
                                .data
                                .iter_mut()
                                .zip(self.group_mix_buf.data[..src_len].iter())
                            {
                                *d += *s;
                            }
                        }
                    }
                }
            } else {
                // Mix directly into master output
                if let Some(track) = self.tracks.get(&track_idx) {
                    self.master_output.mix_from(&track.output_buffer);
                }
            }
        }

        // Apply master params
        if let Some(master) = self.master_index.and_then(|idx| self.tracks.get(&idx)) {
            let vol = master.volume.load(std::sync::atomic::Ordering::Relaxed);
            let pan = master.pan.load(std::sync::atomic::Ordering::Relaxed);
            self.master_output.apply_gain(vol);
            self.master_output.apply_pan(pan);
        }

        // Soft limiter (prevent clipping)
        for s in self.master_output.data.iter_mut() {
            if *s > 1.0 {
                *s = 1.0 - (-(*s - 1.0)).exp();  // soft-knee at +0dBFS
            } else if *s < -1.0 {
                *s = -(1.0 - (-(- *s - 1.0)).exp());
            }
        }

        &self.master_output
    }

    /// Get master output peak levels after process().
    pub fn master_peaks(&self) -> (f32, f32) {
        self.master_output.peak_levels()
    }

    /// Get master output RMS levels after process().
    pub fn master_rms(&self) -> (f32, f32) {
        self.master_output.rms_levels()
    }

    /// Get all track meter levels (for Event::MeterLevels).
    pub fn all_track_meters(&self) -> Vec<(u16, f32, f32, f32, f32)> {
        self.tracks
            .values()
            .map(|t| {
                let (pl, pr) = t.output_buffer.peak_levels();
                let (rl, rr) = t.output_buffer.rms_levels();
                (t.track_index, pl, pr, rl, rr)
            })
            .collect()
    }

    /// Resize all buffers (called when buffer_size changes).
    pub fn resize_buffers(&mut self, buffer_size: usize) {
        self.buffer_size = buffer_size;
        self.group_mix_buf = AudioBuffer::new(buffer_size, 2);
        self.master_output = AudioBuffer::new(buffer_size, 2);
        for track in self.tracks.values_mut() {
            track.output_buffer = AudioBuffer::new(buffer_size, 2);
            track.fx_chain.resize_buffers(buffer_size);
        }
    }

    /// Get mutable reference to a track by index (for FX chain management via IPC).
    pub fn get_track_mut(&mut self, track_index: u16) -> Option<&mut TrackNode> {
        self.tracks.get_mut(&track_index)
    }

    /// v0.0.20.725: Get all track indices (for iteration without borrowing tracks).
    pub fn track_indices(&self) -> Vec<u16> {
        self.tracks.keys().copied().collect()
    }

    /// Find track index by track_id string.
    pub fn find_track_index(&self, track_id: &str) -> Option<u16> {
        self.tracks.values()
            .find(|t| t.track_id == track_id)
            .map(|t| t.track_index)
    }

    /// Write audio data into a track's output buffer.
    /// Called by the arrangement renderer before process().
    pub fn write_track_audio(&mut self, track_index: u16, data: &[f32]) {
        if let Some(track) = self.tracks.get_mut(&track_index) {
            let len = data.len().min(track.output_buffer.data.len());
            track.output_buffer.data[..len].copy_from_slice(&data[..len]);
        }
    }

    /// Silence a track's output buffer.
    pub fn silence_track(&mut self, track_index: u16) {
        if let Some(track) = self.tracks.get_mut(&track_index) {
            track.output_buffer.silence();
        }
    }

    /// Silence ALL track output buffers (start of each process cycle).
    pub fn silence_all(&mut self) {
        for track in self.tracks.values_mut() {
            track.output_buffer.silence();
        }
    }
}
