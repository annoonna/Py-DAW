use serde::{Deserialize, Serialize};

// ============================================================================
// IPC Protocol for Py_DAW Audio Engine
// ============================================================================
//
// Transport: Unix Domain Socket (stream mode)
// Encoding:  MessagePack (rmp-serde)
// Framing:   [u32 LE length][msgpack payload]
//
// Direction:
//   Command  = Python GUI  →  Rust Engine
//   Event    = Rust Engine  →  Python GUI
//
// Design rules:
//   - No heap allocations in audio thread — commands are queued, events are pooled
//   - All parameter IDs are u32 (same as RTParamStore keys in Python)
//   - Track indices are u16 (max 65535 tracks, plenty)
//   - Sample positions are i64 (signed, for pre-roll)
// ============================================================================

// ---------------------------------------------------------------------------
// Commands: Python → Rust
// ---------------------------------------------------------------------------

/// Top-level command envelope sent from Python to Rust.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "cmd")]
pub enum Command {
    // -- Transport --------------------------------------------------------
    /// Start playback from current position.
    Play,

    /// Stop playback (reset to last play-start position).
    Stop,

    /// Pause playback (keep current position).
    Pause,

    /// Seek to a specific beat position.
    Seek { beat: f64 },

    /// Set tempo in BPM.
    SetTempo { bpm: f64 },

    /// Set time signature (numerator, denominator).
    SetTimeSignature { numerator: u8, denominator: u8 },

    /// Enable/disable loop region.
    SetLoop {
        enabled: bool,
        start_beat: f64,
        end_beat: f64,
    },

    // -- Audio Graph -------------------------------------------------------
    /// Add a track node to the audio graph.
    AddTrack {
        track_id: String,
        track_index: u16,
        /// "audio", "instrument", "group", "master", "fx_return"
        kind: String,
    },

    /// Remove a track node from the audio graph.
    RemoveTrack { track_id: String },

    /// Set track parameter (volume, pan, mute, solo).
    SetTrackParam {
        track_index: u16,
        param: TrackParam,
        value: f64,
    },

    /// Set master bus parameter.
    SetMasterParam { param: TrackParam, value: f64 },

    /// Configure group bus routing: child track → group track.
    SetGroupRouting {
        child_track_index: u16,
        group_track_index: Option<u16>,
    },

    // -- Audio Data --------------------------------------------------------
    /// Load audio data for a clip (base64-encoded f32 interleaved PCM).
    LoadAudioClip {
        clip_id: String,
        /// Channels (1=mono, 2=stereo)
        channels: u8,
        sample_rate: u32,
        /// Base64-encoded f32 LE samples
        audio_b64: String,
    },

    /// Set the arrangement state (which clips play where).
    SetArrangement { clips: Vec<ArrangementClip> },

    // -- Plugin Hosting ---------------------------------------------------
    /// Scan all installed plugins (VST3 + CLAP + LV2).
    /// Results come back as PluginScanResult event.
    ScanPlugins,

    /// Load a plugin on a track.
    LoadPlugin {
        track_id: String,
        slot_index: u8,
        plugin_path: String,
        /// "vst3", "clap", "lv2"
        plugin_format: String,
        /// VST3: hex class_id. CLAP: plugin_id string. LV2: plugin URI.
        /// Empty string = load first/only plugin in the bundle.
        #[serde(default)]
        plugin_id: String,
    },

    /// Unload a plugin from a track slot.
    UnloadPlugin { track_id: String, slot_index: u8 },

    /// Set a plugin parameter.
    SetPluginParam {
        track_id: String,
        slot_index: u8,
        param_index: u32,
        value: f64,
    },

    /// Save plugin state (request state blob back as Event).
    SavePluginState { track_id: String, slot_index: u8 },

    /// Load plugin state from blob.
    LoadPluginState {
        track_id: String,
        slot_index: u8,
        /// Base64-encoded state blob
        state_b64: String,
    },

    // -- Built-in FX Chain (Phase R4) -------------------------------------
    /// Add a built-in FX to a track's FX chain.
    AddFx {
        track_id: String,
        /// FX type name (e.g. "compressor", "reverb", "chorus")
        fx_type: String,
        /// Slot identifier (e.g. "afx_001")
        slot_id: String,
        /// Insert position (None = append)
        position: Option<u8>,
    },

    /// Remove a built-in FX from a track's FX chain.
    RemoveFx {
        track_id: String,
        /// Slot index in chain
        slot_index: u8,
    },

    /// Set bypass state for a built-in FX slot.
    SetFxBypass {
        track_id: String,
        slot_index: u8,
        bypass: bool,
    },

    /// Enable/disable a built-in FX slot.
    SetFxEnabled {
        track_id: String,
        slot_index: u8,
        enabled: bool,
    },

    /// Reorder FX in a track's chain.
    ReorderFx {
        track_id: String,
        from_index: u8,
        to_index: u8,
    },

    /// Set dry/wet mix for a track's FX chain.
    SetFxChainMix {
        track_id: String,
        mix: f64,
    },

    // -- MIDI --------------------------------------------------------------
    /// Send MIDI note-on to a track's instrument.
    MidiNoteOn {
        track_id: String,
        channel: u8,
        note: u8,
        velocity: f32,
    },

    /// Send MIDI note-off.
    MidiNoteOff {
        track_id: String,
        channel: u8,
        note: u8,
    },

    /// Send MIDI CC.
    MidiCC {
        track_id: String,
        channel: u8,
        cc: u8,
        value: f32,
    },

    // -- Instruments (Phase R6) -----------------------------------------------
    /// Load an instrument on a track.
    LoadInstrument {
        track_id: String,
        /// Instrument type: "pro_sampler", "drum_machine", "aeterna", etc.
        instrument_type: String,
        /// Optional instrument ID (auto-generated if empty).
        instrument_id: String,
    },

    /// Unload an instrument from a track.
    UnloadInstrument {
        track_id: String,
    },

    /// Load a sample into a sampler instrument.
    LoadSample {
        track_id: String,
        /// WAV file path.
        wav_path: String,
        /// Root note (MIDI note number, 60 = C4).
        root_note: u8,
        /// Fine tune in cents (-100 to +100).
        fine_tune: i8,
    },

    /// Clear the sample from a sampler instrument.
    ClearSample {
        track_id: String,
    },

    /// Set an instrument parameter.
    SetInstrumentParam {
        track_id: String,
        /// Parameter name (e.g., "attack", "gain", "loop_mode").
        param_name: String,
        /// Parameter value (interpretation depends on param_name).
        value: f64,
    },

    // -- MultiSample Instruments (Phase R6B) ---------------------------------
    /// Add a sample zone to a multi-sample instrument.
    AddSampleZone {
        track_id: String,
        /// WAV file path.
        wav_path: String,
        root_note: u8,
        key_lo: u8,
        key_hi: u8,
        vel_lo: u8,
        vel_hi: u8,
        /// Zone gain (0.0–1.0).
        gain: f64,
        /// Zone pan (-1.0..1.0).
        pan: f64,
        /// Tuning in semitones.
        tune_semitones: f64,
        /// Tuning in cents.
        tune_cents: f64,
        /// Round-robin group (0 = none).
        rr_group: u8,
    },

    /// Remove a zone from a multi-sample instrument.
    RemoveSampleZone {
        track_id: String,
        zone_id: u16,
    },

    /// Clear all zones from a multi-sample instrument.
    ClearAllZones {
        track_id: String,
    },

    /// Set zone filter parameters.
    SetZoneFilter {
        track_id: String,
        zone_id: u16,
        /// "off", "lp", "hp", "bp"
        filter_type: String,
        cutoff_hz: f64,
        resonance: f64,
        env_amount: f64,
    },

    /// Set zone envelope (amp or filter).
    SetZoneEnvelope {
        track_id: String,
        zone_id: u16,
        /// "amp" or "filter"
        env_type: String,
        attack: f64,
        decay: f64,
        sustain: f64,
        release: f64,
    },

    /// Set zone LFO parameters.
    SetZoneLfo {
        track_id: String,
        zone_id: u16,
        /// 0 or 1
        lfo_index: u8,
        rate_hz: f64,
        /// "sine", "triangle", "square", "saw", "sample_hold"
        shape: String,
    },

    /// Set zone modulation slot.
    SetZoneModSlot {
        track_id: String,
        zone_id: u16,
        slot_index: u8,
        source: String,
        destination: String,
        amount: f64,
    },

    /// Auto-map samples to zones (chromatic, drum, velocity_layer).
    AutoMapZones {
        track_id: String,
        /// "chromatic", "drum", "velocity_layer"
        mode: String,
        base_note: u8,
        /// List of WAV file paths.
        wav_paths: Vec<String>,
    },

    // -- DrumMachine Instruments (Phase R7A) --------------------------------
    /// Load a sample onto a drum pad.
    LoadDrumPadSample {
        track_id: String,
        pad_index: u8,
        wav_path: String,
    },

    /// Clear a drum pad.
    ClearDrumPad {
        track_id: String,
        pad_index: u8,
    },

    /// Set drum pad parameters.
    SetDrumPadParam {
        track_id: String,
        pad_index: u8,
        /// "gain", "pan", "tune", "choke", "play_mode", "attack", "decay", "sustain", "release"
        param_name: String,
        value: f64,
    },

    /// Clear all drum pads.
    ClearAllDrumPads {
        track_id: String,
    },

    /// Set drum machine base note.
    SetDrumBaseNote {
        track_id: String,
        base_note: u8,
    },

    /// Set drum pad output routing (multi-output).
    SetDrumPadOutput {
        track_id: String,
        pad_index: u8,
        /// Output bus index (0=main, 1-15=aux).
        output_index: u8,
    },

    /// Enable/disable drum machine multi-output.
    SetDrumMultiOutput {
        track_id: String,
        enabled: bool,
        /// Number of output buses (1-16).
        output_count: u8,
    },

    // -- Engine Lifecycle --------------------------------------------------
    /// Configure audio backend (sample rate, buffer size, device).
    Configure {
        sample_rate: u32,
        buffer_size: u32,
        /// Device name or empty for default.
        device: String,
    },

    // -- v0.0.20.711: Extended Instrument Data (RA2) ----------------------

    /// Load a SoundFont from disk (Rust reads the .sf2 directly).
    LoadSF2 {
        track_id: String,
        /// Absolute path to the .sf2 file.
        sf2_path: String,
        /// MIDI bank number.
        bank: u16,
        /// MIDI program number.
        preset: u16,
    },

    /// Load wavetable frame data (all frames concatenated as f32 LE Base64).
    LoadWavetable {
        track_id: String,
        /// Human-readable table name.
        table_name: String,
        /// Samples per frame (e.g., 2048).
        frame_size: u32,
        /// Number of frames in the table.
        num_frames: u32,
        /// Base64-encoded f32 LE data (frame_size * num_frames floats).
        data_b64: String,
    },

    /// Map a pre-loaded audio clip (from ClipStore) to a sample zone.
    /// Used by Python sync_multisample_zones() which sends audio first
    /// via LoadAudioClip, then maps via this command.
    MapSampleZone {
        track_id: String,
        /// Clip ID in ClipStore (matches the LoadAudioClip clip_id).
        clip_id: String,
        key_lo: u8,
        key_hi: u8,
        vel_lo: u8,
        vel_hi: u8,
        root_key: u8,
        rr_group: u8,
    },

    /// Request engine status/health.
    Ping { seq: u64 },

    // -- Project Sync (Phase R12B) ----------------------------------------
    /// Full project state sync in one batch.
    /// Replaces multiple individual commands for initial setup.
    SyncProject {
        /// Serialized ProjectSync as JSON string.
        /// Parsed on the engine side into audio_bridge::ProjectSync.
        project_json: String,
    },

    /// Graceful shutdown.
    Shutdown,
}

/// Track parameter types (matches Python TRACK_VOL/PAN/MUTE/SOLO).
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum TrackParam {
    Volume,
    Pan,
    Mute,
    Solo,
}

/// Description of where a clip is placed in the arrangement.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArrangementClip {
    pub clip_id: String,
    pub track_index: u16,
    pub start_beat: f64,
    pub end_beat: f64,
    pub offset_samples: i64,
    pub gain: f32,
}

// ---------------------------------------------------------------------------
// Events: Rust → Python
// ---------------------------------------------------------------------------

/// Top-level event envelope sent from Rust to Python.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "evt")]
pub enum Event {
    // -- Transport ---------------------------------------------------------
    /// Playhead position update (~30Hz for GUI).
    PlayheadPosition {
        beat: f64,
        sample_position: i64,
        is_playing: bool,
    },

    /// Transport state changed.
    TransportState {
        is_playing: bool,
        beat: f64,
    },

    // -- Metering ----------------------------------------------------------
    /// Per-track peak/RMS levels (sent ~30Hz).
    MeterLevels { levels: Vec<TrackMeterLevel> },

    /// Master bus levels.
    MasterMeterLevel {
        peak_l: f32,
        peak_r: f32,
        rms_l: f32,
        rms_r: f32,
    },

    // -- Engine Status -----------------------------------------------------
    /// Response to Ping.
    Pong {
        seq: u64,
        /// Engine CPU load (0.0 - 1.0, actual process_audio time / budget).
        cpu_load: f32,
        /// Audio buffer underruns since start.
        xrun_count: u32,
        /// Last process_audio render time in microseconds.
        render_time_us: u32,
    },

    /// Engine error (non-fatal, logged).
    Error {
        code: u32,
        message: String,
    },

    /// Plugin crashed — track is muted.
    PluginCrash {
        track_id: String,
        slot_index: u8,
        message: String,
    },

    /// FX chain metering data (gain reduction, peak per slot).
    FxMeter {
        track_id: String,
        slot_index: u8,
        /// Current gain reduction in dB (negative = reducing).
        gain_reduction_db: f32,
        /// Peak level after this FX slot.
        peak_l: f32,
        peak_r: f32,
    },

    /// Plugin state blob (response to SavePluginState).
    PluginState {
        track_id: String,
        slot_index: u8,
        /// Base64-encoded state blob.
        state_b64: String,
    },

    /// Plugin scan results (response to ScanPlugins).
    PluginScanResult {
        /// List of discovered plugins.
        plugins: Vec<ScannedPlugin>,
        /// Total scan time in milliseconds.
        scan_time_ms: u64,
        /// Errors encountered during scanning.
        errors: Vec<String>,
    },

    /// Plugin loaded successfully on a track.
    PluginLoaded {
        track_id: String,
        slot_index: u8,
        plugin_name: String,
        plugin_format: String,
        param_count: u32,
        latency_samples: u32,
    },

    /// Engine is ready (sent after Configure).
    Ready {
        sample_rate: u32,
        buffer_size: u32,
        device_name: String,
    },

    /// Project sync acknowledged (Phase R12B).
    SyncProjectAck {
        /// Sequence number echoed back.
        sync_seq: u64,
        /// Number of tracks configured.
        track_count: u16,
        /// Number of clips loaded.
        clip_count: u16,
    },

    /// Engine is shutting down.
    ShuttingDown,
}

/// Per-track meter data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackMeterLevel {
    pub track_index: u16,
    pub peak_l: f32,
    pub peak_r: f32,
    pub rms_l: f32,
    pub rms_r: f32,
}

/// Discovered plugin info (from ScanPlugins).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScannedPlugin {
    /// "vst3", "clap", "lv2"
    pub format: String,
    /// Plugin name.
    pub name: String,
    /// Vendor/author name.
    pub vendor: String,
    /// Unique ID: VST3 = hex class_id, CLAP = reverse-domain, LV2 = URI.
    pub plugin_id: String,
    /// File path (VST3 bundle, .clap file) or empty for LV2.
    pub path: String,
    /// Category or feature tags.
    pub category: String,
    /// Number of audio inputs.
    pub audio_inputs: u32,
    /// Number of audio outputs.
    pub audio_outputs: u32,
}
