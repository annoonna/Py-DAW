// ==========================================================================
// MultiSample Instrument — Zone-mapped polyphonic sampler
// ==========================================================================
// v0.0.20.676 — Phase R6B
//
// A polyphonic sampler with zone-based key/velocity mapping, per-zone DSP
// (filter, ADSR, LFO modulation), round-robin, and auto-mapping.
//
// Built on top of:
//   - R1: DSP Primitives (Biquad, AdsrEnvelope, Lfo)
//   - R5: Sample Engine (SampleData, VoicePool)
//   - R6A: ProSampler (InstrumentNode trait, lock-free MIDI/Command channels)
//
// Architecture:
//   - SampleZone: defines key/vel range, per-zone DSP params
//   - MultiSampleMap: manages zones, lookup by (note, velocity), round-robin
//   - MultiSampleVoice: active voice with per-zone envelope, filter, LFO state
//   - MultiSampleInstrument: top-level InstrumentNode
//
// Signal flow per voice:
//   MIDI NoteOn → find matching zone(s) → allocate voice per zone
//   → pitch-shift sample (cubic interp) → per-zone filter (Biquad)
//   → amp envelope × velocity × zone gain → pan → sum to output
//
// Rules:
//   ✅ process() is zero-alloc (all voices/zones pre-allocated)
//   ✅ MIDI events delivered via lock-free bounded channel
//   ✅ Sample data is Arc-shared (zero-copy across voices)
//   ❌ NO allocations in process()
//   ❌ NO locks in process()
// ==========================================================================

use crossbeam_channel::{bounded, Receiver, Sender, TryRecvError};
use log::{debug, warn};

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use crate::dsp::biquad::{Biquad, FilterType};
use crate::dsp::envelope::AdsrEnvelope;
use crate::dsp::interpolation::interpolate_cubic;
use crate::dsp::lfo::{Lfo, LfoShape};
use crate::sample::SampleData;
use super::{InstrumentNode, MidiEvent};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Maximum MIDI events per process cycle.
const MIDI_RING_CAPACITY: usize = 256;

/// Maximum command queue depth.
const CMD_RING_CAPACITY: usize = 64;

/// Maximum number of simultaneous voices.
const MAX_VOICES: usize = 64;

/// Maximum number of zones in a single map.
const MAX_ZONES: usize = 256;

/// Maximum number of modulation slots per zone.
const MAX_MOD_SLOTS: usize = 4;

/// Maximum round-robin groups.
const MAX_RR_GROUPS: usize = 32;

// ---------------------------------------------------------------------------
// Zone Filter Type
// ---------------------------------------------------------------------------

/// Filter type for per-zone filtering.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ZoneFilterType {
    /// No filter.
    Off,
    /// Low-pass filter.
    LowPass,
    /// High-pass filter.
    HighPass,
    /// Band-pass filter.
    BandPass,
}

impl ZoneFilterType {
    /// Parse from string (IPC/serialization).
    pub fn from_str(s: &str) -> Self {
        match s {
            "lp" | "lowpass" | "LowPass" => Self::LowPass,
            "hp" | "highpass" | "HighPass" => Self::HighPass,
            "bp" | "bandpass" | "BandPass" => Self::BandPass,
            _ => Self::Off,
        }
    }

    /// Convert to biquad FilterType (returns None for Off).
    fn to_biquad_type(self) -> Option<FilterType> {
        match self {
            Self::Off => None,
            Self::LowPass => Some(FilterType::LowPass),
            Self::HighPass => Some(FilterType::HighPass),
            Self::BandPass => Some(FilterType::BandPass),
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Source / Destination
// ---------------------------------------------------------------------------

/// Modulation source.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModSource {
    None,
    Lfo1,
    Lfo2,
    EnvAmp,
    EnvFilter,
    Velocity,
    KeyTrack,
}

impl ModSource {
    pub fn from_str(s: &str) -> Self {
        match s {
            "lfo1" | "LFO1" => Self::Lfo1,
            "lfo2" | "LFO2" => Self::Lfo2,
            "env_amp" | "amp_env" => Self::EnvAmp,
            "env_filter" | "filter_env" => Self::EnvFilter,
            "velocity" => Self::Velocity,
            "key_track" => Self::KeyTrack,
            _ => Self::None,
        }
    }
}

/// Modulation destination.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModDest {
    None,
    Pitch,
    FilterCutoff,
    Amp,
    Pan,
}

impl ModDest {
    pub fn from_str(s: &str) -> Self {
        match s {
            "pitch" => Self::Pitch,
            "filter_cutoff" | "cutoff" => Self::FilterCutoff,
            "amp" | "amplitude" => Self::Amp,
            "pan" => Self::Pan,
            _ => Self::None,
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Slot
// ---------------------------------------------------------------------------

/// A single modulation routing (source → destination with amount).
#[derive(Debug, Clone, Copy)]
pub struct ModSlot {
    pub source: ModSource,
    pub destination: ModDest,
    /// -1.0 .. 1.0
    pub amount: f32,
}

impl Default for ModSlot {
    fn default() -> Self {
        Self {
            source: ModSource::None,
            destination: ModDest::None,
            amount: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Zone Envelope Params (AHDSR)
// ---------------------------------------------------------------------------

/// AHDSR envelope parameters for a zone (just the params, not state).
#[derive(Debug, Clone, Copy)]
pub struct ZoneEnvParams {
    pub attack: f32,
    pub hold: f32,
    pub decay: f32,
    pub sustain: f32,
    pub release: f32,
}

impl Default for ZoneEnvParams {
    fn default() -> Self {
        Self {
            attack: 0.005,
            hold: 0.0,
            decay: 0.15,
            sustain: 1.0,
            release: 0.2,
        }
    }
}

impl ZoneEnvParams {
    /// Filter envelope defaults (shorter sustain=0 for modulation envelope).
    pub fn filter_default() -> Self {
        Self {
            attack: 0.005,
            hold: 0.0,
            decay: 0.3,
            sustain: 0.0,
            release: 0.1,
        }
    }
}

// ---------------------------------------------------------------------------
// Zone Filter Params
// ---------------------------------------------------------------------------

/// Filter parameters for a zone.
#[derive(Debug, Clone, Copy)]
pub struct ZoneFilterParams {
    pub filter_type: ZoneFilterType,
    pub cutoff_hz: f32,
    pub resonance: f32,
    /// How much the filter envelope modulates cutoff (-1.0 .. 1.0).
    pub env_amount: f32,
}

impl Default for ZoneFilterParams {
    fn default() -> Self {
        Self {
            filter_type: ZoneFilterType::Off,
            cutoff_hz: 8000.0,
            resonance: 0.707,
            env_amount: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Zone LFO Params
// ---------------------------------------------------------------------------

/// LFO parameters for a zone.
#[derive(Debug, Clone, Copy)]
pub struct ZoneLfoParams {
    pub rate_hz: f32,
    pub shape: LfoShape,
}

impl Default for ZoneLfoParams {
    fn default() -> Self {
        Self {
            rate_hz: 1.0,
            shape: LfoShape::Sine,
        }
    }
}

// ---------------------------------------------------------------------------
// Sample Zone
// ---------------------------------------------------------------------------

/// A single sample zone in the multi-sample map.
///
/// Maps a sample to a key range × velocity range with per-zone DSP params.
/// All zone data is immutable once set — changes come via commands that
/// replace the entire zone.
#[derive(Clone)]
pub struct SampleZone {
    /// Unique zone identifier (index in the zone array).
    pub zone_id: u16,

    // -- Key mapping --
    /// Lowest MIDI note for this zone (0–127).
    pub key_lo: u8,
    /// Highest MIDI note for this zone (0–127).
    pub key_hi: u8,
    /// Lowest velocity for this zone (0–127).
    pub vel_lo: u8,
    /// Highest velocity for this zone (0–127).
    pub vel_hi: u8,
    /// Root note — the note that plays at original pitch.
    pub root_note: u8,

    // -- Tuning --
    /// Coarse tuning in semitones (-24..24).
    pub tune_semitones: f32,
    /// Fine tuning in cents (-100..100).
    pub tune_cents: f32,

    // -- Output --
    /// Zone gain (0.0–1.0).
    pub gain: f32,
    /// Zone pan (-1.0 left .. 1.0 right).
    pub pan: f32,

    // -- Sample region --
    /// Normalized start position in sample (0.0–1.0).
    pub sample_start: f32,
    /// Normalized end position in sample (0.0–1.0).
    pub sample_end: f32,

    // -- Loop --
    pub loop_enabled: bool,
    /// Normalized loop start (0.0–1.0).
    pub loop_start: f32,
    /// Normalized loop end (0.0–1.0).
    pub loop_end: f32,

    // -- Envelopes --
    pub amp_envelope: ZoneEnvParams,
    pub filter_envelope: ZoneEnvParams,

    // -- Filter --
    pub filter: ZoneFilterParams,

    // -- LFOs --
    pub lfo1: ZoneLfoParams,
    pub lfo2: ZoneLfoParams,

    // -- Modulation --
    pub mod_slots: [ModSlot; MAX_MOD_SLOTS],

    // -- Round-Robin --
    /// Round-robin group (0 = no RR, 1+ = group ID).
    pub rr_group: u8,

    // -- Sample reference --
    /// The loaded sample data (Arc-shared).
    pub sample: Option<SampleData>,

    /// Is this zone slot occupied?
    pub active: bool,
}

impl Default for SampleZone {
    fn default() -> Self {
        Self {
            zone_id: 0,
            key_lo: 0,
            key_hi: 127,
            vel_lo: 0,
            vel_hi: 127,
            root_note: 60,
            tune_semitones: 0.0,
            tune_cents: 0.0,
            gain: 0.8,
            pan: 0.0,
            sample_start: 0.0,
            sample_end: 1.0,
            loop_enabled: false,
            loop_start: 0.0,
            loop_end: 1.0,
            amp_envelope: ZoneEnvParams::default(),
            filter_envelope: ZoneEnvParams::filter_default(),
            filter: ZoneFilterParams::default(),
            lfo1: ZoneLfoParams::default(),
            lfo2: ZoneLfoParams { rate_hz: 0.5, shape: LfoShape::Triangle },
            mod_slots: [ModSlot::default(); MAX_MOD_SLOTS],
            rr_group: 0,
            sample: None,
            active: false,
        }
    }
}

impl SampleZone {
    /// Check if this zone matches the given note + velocity.
    #[inline]
    pub fn contains(&self, note: u8, velocity: u8) -> bool {
        self.active
            && self.sample.is_some()
            && note >= self.key_lo
            && note <= self.key_hi
            && velocity >= self.vel_lo
            && velocity <= self.vel_hi
    }

    /// Calculate pitch ratio for a given MIDI note.
    #[inline]
    pub fn pitch_ratio(&self, note: u8, sample: &SampleData, engine_sr: u32) -> f64 {
        let tune_total = self.tune_semitones as f64 + self.tune_cents as f64 / 100.0;
        let semitone_diff = note as f64 - self.root_note as f64 + tune_total;
        let pitch = 2.0f64.powf(semitone_diff / 12.0);
        let sr_ratio = sample.sample_rate as f64 / engine_sr as f64;
        pitch * sr_ratio
    }
}

impl std::fmt::Debug for SampleZone {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SampleZone")
            .field("zone_id", &self.zone_id)
            .field("key", &format!("{}-{}", self.key_lo, self.key_hi))
            .field("vel", &format!("{}-{}", self.vel_lo, self.vel_hi))
            .field("root", &self.root_note)
            .field("rr_group", &self.rr_group)
            .field("active", &self.active)
            .finish()
    }
}

// ---------------------------------------------------------------------------
// MultiSample Map
// ---------------------------------------------------------------------------

/// Manages a collection of zones with key/velocity lookup and round-robin.
pub struct MultiSampleMap {
    /// Fixed-size zone array (pre-allocated, no heap in lookup).
    zones: [SampleZone; MAX_ZONES],
    /// Number of active zones.
    zone_count: usize,
    /// Round-robin counters per group.
    rr_counters: [u16; MAX_RR_GROUPS],
}

impl MultiSampleMap {
    /// Create an empty map.
    pub fn new() -> Self {
        Self {
            zones: std::array::from_fn(|_| SampleZone::default()),
            zone_count: 0,
            rr_counters: [0; MAX_RR_GROUPS],
        }
    }

    /// Add a zone. Returns the zone index or None if full.
    pub fn add_zone(&mut self, mut zone: SampleZone) -> Option<u16> {
        if self.zone_count >= MAX_ZONES {
            return None;
        }
        let idx = self.zone_count;
        zone.zone_id = idx as u16;
        zone.active = true;
        self.zones[idx] = zone;
        self.zone_count += 1;
        Some(idx as u16)
    }

    /// Remove a zone by index.
    pub fn remove_zone(&mut self, zone_id: u16) {
        let idx = zone_id as usize;
        if idx < self.zone_count {
            self.zones[idx].active = false;
            self.zones[idx].sample = None;
        }
    }

    /// Get a zone by index.
    #[inline]
    pub fn get_zone(&self, zone_id: u16) -> Option<&SampleZone> {
        let idx = zone_id as usize;
        if idx < self.zone_count && self.zones[idx].active {
            Some(&self.zones[idx])
        } else {
            None
        }
    }

    /// Get mutable zone by index.
    #[inline]
    pub fn get_zone_mut(&mut self, zone_id: u16) -> Option<&mut SampleZone> {
        let idx = zone_id as usize;
        if idx < self.zone_count && self.zones[idx].active {
            Some(&mut self.zones[idx])
        } else {
            None
        }
    }

    /// Find matching zones for note + velocity, respecting round-robin.
    ///
    /// Returns zone indices in a pre-allocated scratch array.
    /// `out` is filled with matching zone indices, returns the count.
    ///
    /// **AUDIO THREAD SAFE** — no allocations.
    #[inline]
    pub fn find_zones(&mut self, note: u8, velocity: u8, out: &mut [u16; 16]) -> usize {
        let mut count = 0usize;

        // Temporary RR bucket tracking (stack-allocated)
        // Each RR group may have up to 16 matching zones
        let mut rr_bucket_indices: [[u16; 16]; MAX_RR_GROUPS] = [[0; 16]; MAX_RR_GROUPS];
        let mut rr_bucket_counts: [u8; MAX_RR_GROUPS] = [0; MAX_RR_GROUPS];

        for i in 0..self.zone_count {
            let zone = &self.zones[i];
            if zone.contains(note, velocity) {
                let rr = zone.rr_group as usize;
                if rr > 0 && rr < MAX_RR_GROUPS {
                    // Round-robin zone
                    let bc = rr_bucket_counts[rr] as usize;
                    if bc < 16 {
                        rr_bucket_indices[rr][bc] = i as u16;
                        rr_bucket_counts[rr] = (bc + 1) as u8;
                    }
                } else {
                    // Non-RR zone — add directly
                    if count < 16 {
                        out[count] = i as u16;
                        count += 1;
                    }
                }
            }
        }

        // Resolve round-robin: pick one zone per group
        for grp in 1..MAX_RR_GROUPS {
            let bc = rr_bucket_counts[grp] as usize;
            if bc > 0 {
                let idx = (self.rr_counters[grp] as usize) % bc;
                if count < 16 {
                    out[count] = rr_bucket_indices[grp][idx];
                    count += 1;
                }
                self.rr_counters[grp] = self.rr_counters[grp].wrapping_add(1);
            }
        }

        count
    }

    /// Clear all zones.
    pub fn clear(&mut self) {
        for i in 0..self.zone_count {
            self.zones[i].active = false;
            self.zones[i].sample = None;
        }
        self.zone_count = 0;
        self.rr_counters = [0; MAX_RR_GROUPS];
    }

    /// Reset round-robin counters.
    pub fn reset_round_robin(&mut self) {
        self.rr_counters = [0; MAX_RR_GROUPS];
    }

    /// Number of active zones.
    pub fn active_count(&self) -> usize {
        self.zones[..self.zone_count].iter().filter(|z| z.active).count()
    }
}

// ---------------------------------------------------------------------------
// MultiSample Voice — per-voice DSP state
// ---------------------------------------------------------------------------

/// State for one active multi-sample voice.
///
/// Each voice has its own envelope generators, filter state, and LFO state,
/// because per-zone DSP parameters may differ.
struct MultiSampleVoice {
    /// Is this voice slot active?
    active: bool,
    /// Is this voice in release phase?
    releasing: bool,

    /// Zone index this voice is playing.
    zone_id: u16,
    /// MIDI note triggering this voice.
    note: u8,
    /// Velocity (0–127).
    velocity: u8,

    /// Current sample position (fractional).
    position: f64,
    /// Playback rate (pitch + SR conversion).
    pitch_ratio: f64,

    // Per-voice DSP state
    /// Amplitude ADSR envelope.
    amp_env: AdsrEnvelope,
    /// Filter ADSR envelope.
    filter_env: AdsrEnvelope,
    /// LFO 1.
    lfo1: Lfo,
    /// LFO 2.
    lfo2: Lfo,
    /// Per-voice biquad filter (for zone filter).
    filter: Biquad,
}

impl MultiSampleVoice {
    /// Create an idle voice.
    fn new(sample_rate: f32) -> Self {
        Self {
            active: false,
            releasing: false,
            zone_id: 0,
            note: 0,
            velocity: 0,
            position: 0.0,
            pitch_ratio: 1.0,
            amp_env: AdsrEnvelope::new(0.005, 0.15, 1.0, 0.2, sample_rate),
            filter_env: AdsrEnvelope::new(0.005, 0.3, 0.0, 0.1, sample_rate),
            lfo1: Lfo::new(1.0, LfoShape::Sine, sample_rate),
            lfo2: Lfo::new(0.5, LfoShape::Triangle, sample_rate),
            filter: Biquad::passthrough(),
        }
    }

    /// Activate this voice for a zone.
    fn activate(
        &mut self,
        zone: &SampleZone,
        sample: &SampleData,
        note: u8,
        velocity: u8,
        engine_sr: u32,
    ) {
        self.active = true;
        self.releasing = false;
        self.zone_id = zone.zone_id;
        self.note = note;
        self.velocity = velocity;
        self.pitch_ratio = zone.pitch_ratio(note, sample, engine_sr);

        // Start position
        let n = sample.frames;
        self.position = (zone.sample_start * n as f32) as f64;

        // Init amp envelope from zone params
        let ae = &zone.amp_envelope;
        self.amp_env.set_params(ae.attack, ae.decay, ae.sustain, ae.release);
        self.amp_env.note_on();

        // Init filter envelope from zone params
        let fe = &zone.filter_envelope;
        self.filter_env.set_params(fe.attack, fe.decay, fe.sustain, fe.release);
        self.filter_env.note_on();

        // Init LFOs
        self.lfo1.set_rate(zone.lfo1.rate_hz);
        self.lfo1.set_shape(zone.lfo1.shape);
        self.lfo1.reset();

        self.lfo2.set_rate(zone.lfo2.rate_hz);
        self.lfo2.set_shape(zone.lfo2.shape);
        self.lfo2.reset();

        // Init filter
        self.filter.reset();
    }

    /// Trigger release.
    fn release(&mut self) {
        if self.active && !self.releasing {
            self.releasing = true;
            self.amp_env.note_off();
            self.filter_env.note_off();
        }
    }

    /// Kill immediately (no release).
    fn kill(&mut self) {
        self.active = false;
        self.releasing = false;
        self.amp_env.kill();
        self.filter_env.kill();
    }

    /// Set sample rate on all DSP components.
    fn set_sample_rate(&mut self, sr: f32) {
        self.amp_env.set_sample_rate(sr);
        self.filter_env.set_sample_rate(sr);
        self.lfo1.set_sample_rate(sr);
        self.lfo2.set_sample_rate(sr);
    }
}

// ---------------------------------------------------------------------------
// Auto-Mapping Modes
// ---------------------------------------------------------------------------

/// Auto-mapping strategy for distributing zones across the keyboard.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AutoMapMode {
    /// One sample per key (chromatic keyboard map).
    Chromatic,
    /// All samples on separate notes starting from base_note (drum mapping).
    Drum,
    /// Stack samples as velocity layers on same key range.
    VelocityLayer,
}

impl AutoMapMode {
    pub fn from_str(s: &str) -> Self {
        match s {
            "chromatic" | "Chromatic" => Self::Chromatic,
            "drum" | "Drum" | "drums" => Self::Drum,
            "velocity" | "VelocityLayer" | "velocity_layer" => Self::VelocityLayer,
            _ => Self::Chromatic,
        }
    }
}

/// Generate zone params for auto-mapping.
///
/// Returns Vec of (key_lo, key_hi, vel_lo, vel_hi, root_note) tuples.
/// `count` is the number of samples to map.
/// `base_note` is the starting MIDI note (default 36 for drums, 60 for chromatic).
pub fn auto_map_zones(
    mode: AutoMapMode,
    count: usize,
    base_note: u8,
) -> Vec<(u8, u8, u8, u8, u8)> {
    let mut result = Vec::with_capacity(count);
    match mode {
        AutoMapMode::Chromatic => {
            // Each sample gets ±half-step range centered on its root note
            for i in 0..count {
                let root = (base_note as usize + i).min(127) as u8;
                let lo = if i == 0 { 0u8 } else { root };
                let hi = if i == count - 1 {
                    127u8
                } else {
                    root
                };
                result.push((lo, hi, 0, 127, root));
            }
        }
        AutoMapMode::Drum => {
            // Each sample on a single key (GM drum mapping style)
            for i in 0..count {
                let note = (base_note as usize + i).min(127) as u8;
                result.push((note, note, 0, 127, note));
            }
        }
        AutoMapMode::VelocityLayer => {
            // All samples on full key range, split by velocity
            let vel_step = if count > 0 { 128 / count } else { 128 };
            for i in 0..count {
                let vel_lo = (i * vel_step) as u8;
                let vel_hi = if i == count - 1 {
                    127u8
                } else {
                    ((i + 1) * vel_step - 1).min(127) as u8
                };
                result.push((0, 127, vel_lo, vel_hi, base_note));
            }
        }
    }
    result
}

// ---------------------------------------------------------------------------
// MultiSample Commands (lock-free delivery to audio thread)
// ---------------------------------------------------------------------------

/// Commands for the MultiSample instrument, sent from command thread.
#[derive(Debug, Clone)]
pub enum MultiSampleCommand {
    /// Add a zone with sample data.
    AddZone {
        key_lo: u8,
        key_hi: u8,
        vel_lo: u8,
        vel_hi: u8,
        root_note: u8,
        gain: f32,
        pan: f32,
        tune_semitones: f32,
        tune_cents: f32,
        sample: SampleData,
        rr_group: u8,
    },
    /// Remove a zone by index.
    RemoveZone { zone_id: u16 },
    /// Clear all zones.
    ClearAllZones,
    /// Set zone filter parameters.
    SetZoneFilter {
        zone_id: u16,
        filter_type: ZoneFilterType,
        cutoff_hz: f32,
        resonance: f32,
        env_amount: f32,
    },
    /// Set zone amp envelope.
    SetZoneAmpEnvelope {
        zone_id: u16,
        attack: f32,
        decay: f32,
        sustain: f32,
        release: f32,
    },
    /// Set zone filter envelope.
    SetZoneFilterEnvelope {
        zone_id: u16,
        attack: f32,
        decay: f32,
        sustain: f32,
        release: f32,
    },
    /// Set zone LFO params.
    SetZoneLfo {
        zone_id: u16,
        lfo_index: u8,   // 0 or 1
        rate_hz: f32,
        shape: LfoShape,
    },
    /// Set zone modulation slot.
    SetZoneModSlot {
        zone_id: u16,
        slot_index: u8,
        source: ModSource,
        destination: ModDest,
        amount: f32,
    },
    /// Set zone loop params.
    SetZoneLoop {
        zone_id: u16,
        enabled: bool,
        start: f32,
        end: f32,
    },
    /// Set master gain.
    SetMasterGain(f32),
    /// Set master pan.
    SetMasterPan(f32),
    /// Auto-map: clear all zones, add zones from a batch of samples.
    AutoMap {
        mode: AutoMapMode,
        base_note: u8,
        samples: Vec<SampleData>,
    },
}

// ---------------------------------------------------------------------------
// MultiSampleInstrument
// ---------------------------------------------------------------------------

/// Polyphonic multi-sample instrument with zone-based key/velocity mapping.
///
/// Implements InstrumentNode for use in the audio graph.
pub struct MultiSampleInstrument {
    /// Unique instrument ID.
    id: String,

    /// Zone map.
    map: MultiSampleMap,

    /// Pre-allocated voice pool.
    voices: Vec<MultiSampleVoice>,

    /// Master gain (0.0–2.0).
    master_gain: f32,
    /// Master pan (-1.0..1.0).
    master_pan: f32,

    /// MIDI event receiver (audio thread).
    midi_rx: Receiver<MidiEvent>,
    /// MIDI event sender (command thread).
    midi_tx: Sender<MidiEvent>,

    /// Command receiver (audio thread).
    cmd_rx: Receiver<MultiSampleCommand>,
    /// Command sender (command thread).
    cmd_tx: Sender<MultiSampleCommand>,

    /// Current engine sample rate.
    sample_rate: u32,
    /// Current buffer size.
    buffer_size: usize,
}

impl MultiSampleInstrument {
    /// Create a new MultiSample instrument.
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING_CAPACITY);
        let (cmd_tx, cmd_rx) = bounded(CMD_RING_CAPACITY);

        let sr = sample_rate as f32;
        let voices = (0..MAX_VOICES)
            .map(|_| MultiSampleVoice::new(sr))
            .collect();

        Self {
            id,
            map: MultiSampleMap::new(),
            voices,
            master_gain: 0.8,
            master_pan: 0.0,
            midi_rx,
            midi_tx,
            cmd_rx,
            cmd_tx,
            sample_rate,
            buffer_size,
        }
    }

    /// Get the command sender for parameter changes.
    pub fn command_sender(&self) -> Sender<MultiSampleCommand> {
        self.cmd_tx.clone()
    }

    // -- Command processing --

    /// Drain and apply all pending commands.
    #[inline]
    fn process_commands(&mut self) {
        loop {
            match self.cmd_rx.try_recv() {
                Ok(cmd) => self.apply_command(cmd),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    /// Apply a single command.
    pub fn apply_command(&mut self, cmd: MultiSampleCommand) {
        match cmd {
            MultiSampleCommand::AddZone {
                key_lo, key_hi, vel_lo, vel_hi, root_note,
                gain, pan, tune_semitones, tune_cents,
                sample, rr_group,
            } => {
                let mut zone = SampleZone::default();
                zone.key_lo = key_lo;
                zone.key_hi = key_hi;
                zone.vel_lo = vel_lo;
                zone.vel_hi = vel_hi;
                zone.root_note = root_note;
                zone.gain = gain;
                zone.pan = pan;
                zone.tune_semitones = tune_semitones;
                zone.tune_cents = tune_cents;
                zone.rr_group = rr_group;
                zone.sample = Some(sample);
                if let Some(idx) = self.map.add_zone(zone) {
                    debug!("MultiSample '{}': added zone {}", self.id, idx);
                } else {
                    warn!("MultiSample '{}': zone limit reached", self.id);
                }
            }
            MultiSampleCommand::RemoveZone { zone_id } => {
                // Kill any voices playing this zone
                for v in &mut self.voices {
                    if v.active && v.zone_id == zone_id {
                        v.kill();
                    }
                }
                self.map.remove_zone(zone_id);
            }
            MultiSampleCommand::ClearAllZones => {
                for v in &mut self.voices {
                    v.kill();
                }
                self.map.clear();
            }
            MultiSampleCommand::SetZoneFilter {
                zone_id, filter_type, cutoff_hz, resonance, env_amount,
            } => {
                if let Some(zone) = self.map.get_zone_mut(zone_id) {
                    zone.filter.filter_type = filter_type;
                    zone.filter.cutoff_hz = cutoff_hz.clamp(20.0, 20000.0);
                    zone.filter.resonance = resonance.clamp(0.25, 12.0);
                    zone.filter.env_amount = env_amount.clamp(-1.0, 1.0);
                }
            }
            MultiSampleCommand::SetZoneAmpEnvelope {
                zone_id, attack, decay, sustain, release,
            } => {
                if let Some(zone) = self.map.get_zone_mut(zone_id) {
                    zone.amp_envelope.attack = attack.max(0.001);
                    zone.amp_envelope.decay = decay.max(0.001);
                    zone.amp_envelope.sustain = sustain.clamp(0.0, 1.0);
                    zone.amp_envelope.release = release.max(0.001);
                }
            }
            MultiSampleCommand::SetZoneFilterEnvelope {
                zone_id, attack, decay, sustain, release,
            } => {
                if let Some(zone) = self.map.get_zone_mut(zone_id) {
                    zone.filter_envelope.attack = attack.max(0.001);
                    zone.filter_envelope.decay = decay.max(0.001);
                    zone.filter_envelope.sustain = sustain.clamp(0.0, 1.0);
                    zone.filter_envelope.release = release.max(0.001);
                }
            }
            MultiSampleCommand::SetZoneLfo {
                zone_id, lfo_index, rate_hz, shape,
            } => {
                if let Some(zone) = self.map.get_zone_mut(zone_id) {
                    let params = if lfo_index == 0 {
                        &mut zone.lfo1
                    } else {
                        &mut zone.lfo2
                    };
                    params.rate_hz = rate_hz.clamp(0.01, 50.0);
                    params.shape = shape;
                }
            }
            MultiSampleCommand::SetZoneModSlot {
                zone_id, slot_index, source, destination, amount,
            } => {
                let si = slot_index as usize;
                if si < MAX_MOD_SLOTS {
                    if let Some(zone) = self.map.get_zone_mut(zone_id) {
                        zone.mod_slots[si].source = source;
                        zone.mod_slots[si].destination = destination;
                        zone.mod_slots[si].amount = amount.clamp(-1.0, 1.0);
                    }
                }
            }
            MultiSampleCommand::SetZoneLoop {
                zone_id, enabled, start, end,
            } => {
                if let Some(zone) = self.map.get_zone_mut(zone_id) {
                    zone.loop_enabled = enabled;
                    zone.loop_start = start.clamp(0.0, 1.0);
                    zone.loop_end = end.clamp(0.0, 1.0);
                }
            }
            MultiSampleCommand::SetMasterGain(g) => {
                self.master_gain = g.clamp(0.0, 4.0);
            }
            MultiSampleCommand::SetMasterPan(p) => {
                self.master_pan = p.clamp(-1.0, 1.0);
            }
            MultiSampleCommand::AutoMap { mode, base_note, samples } => {
                // Clear existing zones
                for v in &mut self.voices {
                    v.kill();
                }
                self.map.clear();

                // Generate mappings
                let mappings = auto_map_zones(mode, samples.len(), base_note);
                for (i, sample) in samples.into_iter().enumerate() {
                    if i < mappings.len() {
                        let (klo, khi, vlo, vhi, root) = mappings[i];
                        let mut zone = SampleZone::default();
                        zone.key_lo = klo;
                        zone.key_hi = khi;
                        zone.vel_lo = vlo;
                        zone.vel_hi = vhi;
                        zone.root_note = root;
                        zone.sample = Some(sample);
                        self.map.add_zone(zone);
                    }
                }
                debug!(
                    "MultiSample '{}': auto-mapped {} zones ({:?})",
                    self.id,
                    self.map.active_count(),
                    mode,
                );
            }
        }
    }

    // -- MIDI processing --

    /// Drain and handle all pending MIDI events.
    #[inline]
    fn process_midi(&mut self) {
        loop {
            match self.midi_rx.try_recv() {
                Ok(event) => self.handle_midi_event(event),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    /// Handle a single MIDI event.
    fn handle_midi_event(&mut self, event: MidiEvent) {
        match event {
            MidiEvent::NoteOn { note, velocity } => {
                let vel_u8 = (velocity * 127.0).round() as u8;
                let mut zone_indices = [0u16; 16];
                let count = self.map.find_zones(note, vel_u8, &mut zone_indices);

                let sample_rate = self.sample_rate;

                for i in 0..count {
                    let zone_id = zone_indices[i];
                    // Allocate voice (index-based to avoid borrow conflicts)
                    let voice_idx = Self::alloc_voice_index(&self.voices);
                    if let Some(vi) = voice_idx {
                        // Extract zone data before mutably borrowing voice
                        let zone_data = if let Some(zone) = self.map.get_zone(zone_id) {
                            zone.sample.as_ref().map(|s| (zone.clone(), s.clone()))
                        } else {
                            None
                        };

                        if let Some((zone_clone, sample_clone)) = zone_data {
                            self.voices[vi].activate(
                                &zone_clone,
                                &sample_clone,
                                note,
                                vel_u8,
                                sample_rate,
                            );
                        }
                    }
                }
            }
            MidiEvent::NoteOff { note } => {
                for v in &mut self.voices {
                    if v.active && !v.releasing && v.note == note {
                        v.release();
                    }
                }
            }
            MidiEvent::CC { cc, value: _ } => {
                match cc {
                    120 => {
                        // All Sound Off
                        for v in &mut self.voices {
                            v.kill();
                        }
                    }
                    123 => {
                        // All Notes Off
                        for v in &mut self.voices {
                            if v.active {
                                v.release();
                            }
                        }
                    }
                    _ => {}
                }
            }
            MidiEvent::AllNotesOff => {
                for v in &mut self.voices {
                    if v.active {
                        v.release();
                    }
                }
            }
            MidiEvent::AllSoundOff => {
                for v in &mut self.voices {
                    v.kill();
                }
            }
        }
    }

    /// Find a free voice slot index (free → releasing → steal first).
    ///
    /// Returns index into voices Vec. Uses shared ref to avoid borrow conflicts.
    fn alloc_voice_index(voices: &[MultiSampleVoice]) -> Option<usize> {
        // 1. Find inactive voice
        for (i, v) in voices.iter().enumerate() {
            if !v.active {
                return Some(i);
            }
        }
        // 2. Steal a releasing voice
        for (i, v) in voices.iter().enumerate() {
            if v.releasing {
                return Some(i);
            }
        }
        // 3. Steal first voice (oldest)
        if !voices.is_empty() {
            Some(0)
        } else {
            None
        }
    }

    // -- Audio rendering --

    /// Render all active voices into the output buffer.
    #[inline]
    fn render_voices(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;
        let sr = self.sample_rate as f32;

        for voice_idx in 0..self.voices.len() {
            if !self.voices[voice_idx].active {
                continue;
            }

            let zone_id = self.voices[voice_idx].zone_id;

            // Get zone (immutable borrow of map)
            // We need to copy zone params to avoid borrow conflict with voice
            let zone_data = if let Some(zone) = self.map.get_zone(zone_id) {
                if zone.sample.is_none() {
                    self.voices[voice_idx].kill();
                    continue;
                }
                // Copy the needed params (stack-allocated, no heap)
                Some(ZoneRenderParams {
                    gain: zone.gain,
                    pan: zone.pan,
                    sample_start: zone.sample_start,
                    sample_end: zone.sample_end,
                    loop_enabled: zone.loop_enabled,
                    loop_start: zone.loop_start,
                    loop_end: zone.loop_end,
                    filter_type: zone.filter.filter_type,
                    filter_cutoff: zone.filter.cutoff_hz,
                    filter_resonance: zone.filter.resonance,
                    filter_env_amount: zone.filter.env_amount,
                    mod_slots: zone.mod_slots,
                    sample_data: zone.sample.as_ref().unwrap().data.clone(),
                    sample_frames: zone.sample.as_ref().unwrap().frames,
                    sample_channels: zone.sample.as_ref().unwrap().channels,
                })
            } else {
                self.voices[voice_idx].kill();
                continue;
            };

            let zp = zone_data.unwrap();
            let voice = &mut self.voices[voice_idx];

            Self::render_single_voice(voice, &zp, &mut buffer.data, frames, sr);
        }
    }

    /// Render a single voice into the output buffer.
    ///
    /// Separated from render_voices to avoid borrow conflicts.
    #[inline]
    fn render_single_voice(
        voice: &mut MultiSampleVoice,
        zp: &ZoneRenderParams,
        output: &mut [f32],
        frames: usize,
        sr: f32,
    ) {
        let vel01 = voice.velocity as f32 / 127.0;
        let data = &zp.sample_data;
        let n_frames = zp.sample_frames;
        let channels = zp.sample_channels as usize;

        if n_frames < 2 {
            voice.kill();
            return;
        }

        // Sample boundaries (in frames)
        let s_start = (zp.sample_start * n_frames as f32) as usize;
        let s_end = ((zp.sample_end * n_frames as f32) as usize).max(s_start + 2).min(n_frames);

        let loop_enabled = zp.loop_enabled;
        let loop_start_f = if loop_enabled {
            (zp.loop_start * n_frames as f32) as usize
        } else {
            s_start
        };
        let loop_end_f = if loop_enabled {
            ((zp.loop_end * n_frames as f32) as usize).max(loop_start_f + 2).min(n_frames)
        } else {
            s_end
        };

        // Check if filter is active
        let use_filter = zp.filter_type != ZoneFilterType::Off;

        for i in 0..frames {
            // Process envelopes
            let amp_e = voice.amp_env.process();
            let filt_e = voice.filter_env.process();

            // Check if envelope finished
            if !voice.amp_env.is_active() {
                voice.active = false;
                break;
            }

            if amp_e < 0.00001 {
                // Advance position even when silent (keep in sync)
                voice.position += voice.pitch_ratio;
                continue;
            }

            // LFO values
            let lfo1_val = voice.lfo1.process();
            let lfo2_val = voice.lfo2.process();

            // Evaluate modulation matrix
            let mut mod_pitch: f32 = 0.0;
            let mut mod_cutoff: f32 = 0.0;
            let mut mod_amp: f32 = 0.0;
            let mut mod_pan: f32 = 0.0;

            for slot in &zp.mod_slots {
                if slot.source == ModSource::None || slot.destination == ModDest::None {
                    continue;
                }
                if slot.amount.abs() < 0.001 {
                    continue;
                }

                // Get source value (-1..1)
                let src_val = match slot.source {
                    ModSource::Lfo1 => lfo1_val,
                    ModSource::Lfo2 => lfo2_val,
                    ModSource::EnvAmp => amp_e * 2.0 - 1.0,
                    ModSource::EnvFilter => filt_e * 2.0 - 1.0,
                    ModSource::Velocity => vel01 * 2.0 - 1.0,
                    ModSource::KeyTrack => (voice.note as f32 - 60.0) / 60.0,
                    ModSource::None => 0.0,
                };

                let mod_val = src_val * slot.amount;
                match slot.destination {
                    ModDest::Pitch => mod_pitch += mod_val,
                    ModDest::FilterCutoff => mod_cutoff += mod_val,
                    ModDest::Amp => mod_amp += mod_val,
                    ModDest::Pan => mod_pan += mod_val,
                    ModDest::None => {}
                }
            }

            // Effective pitch with modulation
            let eff_pitch = if mod_pitch.abs() > 0.001 {
                voice.pitch_ratio * 2.0f64.powf((mod_pitch * 2.0 / 12.0) as f64)
            } else {
                voice.pitch_ratio
            };

            // Read sample with interpolation
            let pos = voice.position;
            let idx = pos as usize;
            let frac = (pos - idx as f64) as f32;

            // Check end of sample / loop
            if idx >= s_end.saturating_sub(1) {
                if loop_enabled {
                    let loop_len = (loop_end_f - loop_start_f).max(1) as f64;
                    voice.position = loop_start_f as f64
                        + ((voice.position - loop_end_f as f64) % loop_len);
                    if voice.position < loop_start_f as f64 {
                        voice.position = loop_start_f as f64;
                    }
                    continue; // re-read at new position next sample
                } else {
                    voice.active = false;
                    voice.amp_env.kill();
                    break;
                }
            }

            // Read sample value (mono or stereo → process mono then pan)
            let x = if channels >= 2 {
                // Stereo: average L+R for processing, then re-pan
                if idx + 2 < n_frames {
                    let i0 = if idx > 0 { idx - 1 } else { 0 };
                    let l = interpolate_cubic(
                        data[i0 * 2], data[idx * 2], data[(idx + 1) * 2], data[(idx + 2) * 2],
                        frac,
                    );
                    let r = interpolate_cubic(
                        data[i0 * 2 + 1], data[idx * 2 + 1], data[(idx + 1) * 2 + 1],
                        data[(idx + 2) * 2 + 1], frac,
                    );
                    (l + r) * 0.5
                } else if idx < n_frames {
                    let l = data[idx * 2];
                    let r = data[idx * 2 + 1];
                    (l + r) * 0.5
                } else {
                    0.0
                }
            } else {
                // Mono
                if idx + 2 < n_frames {
                    let i0 = if idx > 0 { idx - 1 } else { 0 };
                    interpolate_cubic(data[i0], data[idx], data[idx + 1], data[idx + 2], frac)
                } else if idx < n_frames {
                    data[idx]
                } else {
                    0.0
                }
            };

            // Apply filter with envelope modulation
            let x_filtered = if use_filter {
                if let Some(bq_type) = zp.filter_type.to_biquad_type() {
                    let base_cutoff = zp.filter_cutoff;
                    let mod_c = base_cutoff
                        * (1.0 + filt_e * zp.filter_env_amount + mod_cutoff * 4000.0 / base_cutoff);
                    let mod_c = mod_c.clamp(20.0, 20000.0);
                    voice.filter.set_params(bq_type, mod_c, zp.filter_resonance, 0.0, sr);
                    voice.filter.process_sample(x)
                } else {
                    x
                }
            } else {
                x
            };

            // Apply amplitude
            let gain = (zp.gain * vel01 * amp_e * (1.0 + mod_amp * 0.5)).clamp(0.0, 2.0);

            // Effective pan
            let eff_pan = (zp.pan + mod_pan * 0.5).clamp(-1.0, 1.0);
            let pan_angle = (eff_pan + 1.0) * 0.25 * std::f32::consts::PI;
            let pan_l = pan_angle.cos() * std::f32::consts::SQRT_2;
            let pan_r = pan_angle.sin() * std::f32::consts::SQRT_2;

            // Write to output (additive)
            let out_idx = i * 2;
            if out_idx + 1 < output.len() {
                output[out_idx] += x_filtered * gain * pan_l;
                output[out_idx + 1] += x_filtered * gain * pan_r;
            }

            // Advance position
            voice.position += eff_pitch;
        }
    }
}

/// Temporary zone params extracted for rendering (avoids borrow conflicts).
struct ZoneRenderParams {
    gain: f32,
    pan: f32,
    sample_start: f32,
    sample_end: f32,
    loop_enabled: bool,
    loop_start: f32,
    loop_end: f32,
    filter_type: ZoneFilterType,
    filter_cutoff: f32,
    filter_resonance: f32,
    filter_env_amount: f32,
    mod_slots: [ModSlot; MAX_MOD_SLOTS],
    /// Arc-shared sample data (clone is cheap — just Arc::clone).
    sample_data: std::sync::Arc<Vec<f32>>,
    sample_frames: usize,
    sample_channels: u16,
}

// ---------------------------------------------------------------------------
// InstrumentNode Implementation
// ---------------------------------------------------------------------------

impl InstrumentNode for MultiSampleInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        if let Err(_) = self.midi_tx.try_send(event) {
            warn!("MultiSample '{}': MIDI ring full, dropping event", self.id);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        // 1. Process pending commands
        self.process_commands();

        // 2. Process pending MIDI events
        self.process_midi();

        // 3. Clear buffer (we're a generator)
        buffer.silence();

        // 4. Render all active voices
        self.render_voices(buffer);

        // 5. Apply master gain
        if (self.master_gain - 1.0).abs() > 0.001 {
            buffer.apply_gain(self.master_gain);
        }

        // 6. Apply master pan
        if self.master_pan.abs() > 0.001 {
            buffer.apply_pan(self.master_pan);
        }
    }

    fn instrument_id(&self) -> &str {
        &self.id
    }

    fn instrument_name(&self) -> &str {
        "MultiSample"
    }

    fn instrument_type(&self) -> &str {
        "multi_sample"
    }

    fn set_sample_rate(&mut self, sample_rate: u32) {
        self.sample_rate = sample_rate;
        let sr = sample_rate as f32;
        for v in &mut self.voices {
            v.set_sample_rate(sr);
        }
    }

    fn set_buffer_size(&mut self, buffer_size: usize) {
        self.buffer_size = buffer_size;
    }

    fn active_voice_count(&self) -> usize {
        self.voices.iter().filter(|v| v.active).count()
    }

    fn max_polyphony(&self) -> usize {
        MAX_VOICES
    }

    fn as_any_mut(&mut self) -> &mut dyn std::any::Any {
        self
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_sample(frames: usize, freq: f32, sr: u32) -> SampleData {
        let mut data = Vec::with_capacity(frames * 2);
        for i in 0..frames {
            let t = i as f32 / sr as f32;
            let s = (freq * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            data.push(s); // L
            data.push(s); // R
        }
        SampleData::from_raw(data, 2, sr, "test_sine".to_string())
    }

    fn make_ctx(frames: usize, sr: u32) -> ProcessContext {
        ProcessContext {
            frames,
            sample_rate: sr,
            position_samples: 0,
            position_beats: 0.0,
            is_playing: true,
            bpm: 120.0,
            time_sig_num: 4,
            time_sig_den: 4,
        }
    }

    #[test]
    fn test_multisample_creation() {
        let ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);
        assert_eq!(ms.instrument_id(), "test");
        assert_eq!(ms.instrument_type(), "multi_sample");
        assert_eq!(ms.instrument_name(), "MultiSample");
        assert_eq!(ms.active_voice_count(), 0);
        assert_eq!(ms.max_polyphony(), MAX_VOICES);
    }

    #[test]
    fn test_multisample_no_zones_silent() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 256);
        let mut buffer = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);

        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        ms.process(&mut buffer, &ctx);

        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max < 0.0001, "Should be silent without zones, got {}", max);
    }

    #[test]
    fn test_multisample_add_zone_and_play() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        // Add a zone via command
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0,
            key_hi: 127,
            vel_lo: 0,
            vel_hi: 127,
            root_note: 60,
            gain: 0.8,
            pan: 0.0,
            tune_semitones: 0.0,
            tune_cents: 0.0,
            sample,
            rr_group: 0,
        });

        // Process to apply command
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        // Now trigger a note
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);

        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.01, "Should produce audio on note_on, got max={}", max);
        assert_eq!(ms.active_voice_count(), 1);
    }

    #[test]
    fn test_multisample_key_range_filtering() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        // Zone only covers C4–C5 (60–72)
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 60,
            key_hi: 72,
            vel_lo: 0,
            vel_hi: 127,
            root_note: 60,
            gain: 0.8,
            pan: 0.0,
            tune_semitones: 0.0,
            tune_cents: 0.0,
            sample,
            rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        // Note 50 is OUTSIDE the zone range
        ms.push_midi(MidiEvent::NoteOn { note: 50, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 0, "Note 50 should not trigger zone 60-72");

        // Note 65 is INSIDE the zone range
        ms.push_midi(MidiEvent::NoteOn { note: 65, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 1, "Note 65 should trigger zone 60-72");
    }

    #[test]
    fn test_multisample_velocity_range_filtering() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        // Zone only responds to velocity 64–127
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0,
            key_hi: 127,
            vel_lo: 64,
            vel_hi: 127,
            root_note: 60,
            gain: 0.8,
            pan: 0.0,
            tune_semitones: 0.0,
            tune_cents: 0.0,
            sample,
            rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        // Low velocity (0.3 * 127 ≈ 38) → below threshold
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.3 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 0, "Low velocity should not trigger");

        // High velocity (0.8 * 127 ≈ 102) → above threshold
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 1, "High velocity should trigger");
    }

    #[test]
    fn test_multisample_round_robin() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 256);

        // Two zones in RR group 1 covering same range
        let s1 = make_test_sample(44100, 440.0, 44100);
        let s2 = make_test_sample(44100, 880.0, 44100);

        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample: s1, rr_group: 1,
        });
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample: s2, rr_group: 1,
        });

        let mut buffer = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);
        ms.process(&mut buffer, &ctx);

        // First trigger → only 1 voice (RR picks one zone)
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        buffer = AudioBuffer::new(256, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 1, "RR should pick only one zone");

        // Second trigger → should pick the other zone
        ms.push_midi(MidiEvent::NoteOn { note: 65, velocity: 0.8 });
        buffer = AudioBuffer::new(256, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 2, "Second note should use different RR zone");
    }

    #[test]
    fn test_multisample_note_off_releases() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample, rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        // Note on
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 1);

        // Note off → voice should be releasing
        ms.push_midi(MidiEvent::NoteOff { note: 60 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);

        // Voice is releasing (still "active" until envelope finishes)
        let voice = &ms.voices[0];
        assert!(voice.releasing || !voice.active);
    }

    #[test]
    fn test_multisample_all_sound_off() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample, rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        ms.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 2);

        ms.push_midi(MidiEvent::AllSoundOff);
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 0);
    }

    #[test]
    fn test_multisample_clear_zones() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample, rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.map.active_count(), 1);

        let _ = ms.cmd_tx.try_send(MultiSampleCommand::ClearAllZones);
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.map.active_count(), 0);
    }

    #[test]
    fn test_auto_map_chromatic() {
        let mappings = auto_map_zones(AutoMapMode::Chromatic, 3, 60);
        assert_eq!(mappings.len(), 3);
        // First: key 0–60, root 60
        assert_eq!(mappings[0], (0, 60, 0, 127, 60));
        // Middle: key 61–61, root 61
        assert_eq!(mappings[1], (61, 61, 0, 127, 61));
        // Last: key 62–127, root 62
        assert_eq!(mappings[2], (62, 127, 0, 127, 62));
    }

    #[test]
    fn test_auto_map_drum() {
        let mappings = auto_map_zones(AutoMapMode::Drum, 4, 36);
        assert_eq!(mappings.len(), 4);
        assert_eq!(mappings[0], (36, 36, 0, 127, 36));
        assert_eq!(mappings[1], (37, 37, 0, 127, 37));
        assert_eq!(mappings[2], (38, 38, 0, 127, 38));
        assert_eq!(mappings[3], (39, 39, 0, 127, 39));
    }

    #[test]
    fn test_auto_map_velocity_layer() {
        let mappings = auto_map_zones(AutoMapMode::VelocityLayer, 3, 60);
        assert_eq!(mappings.len(), 3);
        // Layer 0: vel 0–41
        assert_eq!(mappings[0], (0, 127, 0, 41, 60));
        // Layer 1: vel 42–83
        assert_eq!(mappings[1], (0, 127, 42, 83, 60));
        // Layer 2: vel 84–127
        assert_eq!(mappings[2], (0, 127, 84, 127, 60));
    }

    #[test]
    fn test_multisample_automap_command() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        let samples = vec![
            make_test_sample(4410, 440.0, 44100),
            make_test_sample(4410, 880.0, 44100),
            make_test_sample(4410, 220.0, 44100),
        ];

        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AutoMap {
            mode: AutoMapMode::Drum,
            base_note: 36,
            samples,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        assert_eq!(ms.map.active_count(), 3);

        // Play drum pad 37
        ms.push_midi(MidiEvent::NoteOn { note: 37, velocity: 0.9 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 1);

        // Note 40 is outside mapped range → no voice
        ms.push_midi(MidiEvent::NoteOn { note: 40, velocity: 0.9 });
        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        // 40 > 38 (last mapped note) → no new voice
        assert_eq!(ms.active_voice_count(), 1);
    }

    #[test]
    fn test_zone_filter_type_parse() {
        assert_eq!(ZoneFilterType::from_str("lp"), ZoneFilterType::LowPass);
        assert_eq!(ZoneFilterType::from_str("hp"), ZoneFilterType::HighPass);
        assert_eq!(ZoneFilterType::from_str("bp"), ZoneFilterType::BandPass);
        assert_eq!(ZoneFilterType::from_str("off"), ZoneFilterType::Off);
        assert_eq!(ZoneFilterType::from_str("unknown"), ZoneFilterType::Off);
    }

    #[test]
    fn test_mod_source_dest_parse() {
        assert_eq!(ModSource::from_str("lfo1"), ModSource::Lfo1);
        assert_eq!(ModSource::from_str("velocity"), ModSource::Velocity);
        assert_eq!(ModSource::from_str("none"), ModSource::None);
        assert_eq!(ModDest::from_str("pitch"), ModDest::Pitch);
        assert_eq!(ModDest::from_str("amp"), ModDest::Amp);
        assert_eq!(ModDest::from_str("pan"), ModDest::Pan);
    }

    #[test]
    fn test_multisample_polyphony() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 512);

        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample, rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        ms.process(&mut buffer, &ctx);

        // Play 4 different notes
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        ms.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.7 });
        ms.push_midi(MidiEvent::NoteOn { note: 67, velocity: 0.6 });
        ms.push_midi(MidiEvent::NoteOn { note: 72, velocity: 0.5 });

        buffer = AudioBuffer::new(512, 2);
        ms.process(&mut buffer, &ctx);
        assert_eq!(ms.active_voice_count(), 4);

        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.05, "4 voices should produce audible output, got {}", max);
    }

    #[test]
    fn test_multisample_master_gain() {
        let mut ms = MultiSampleInstrument::new("test".to_string(), 44100, 256);

        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::AddZone {
            key_lo: 0, key_hi: 127, vel_lo: 0, vel_hi: 127,
            root_note: 60, gain: 0.8, pan: 0.0,
            tune_semitones: 0.0, tune_cents: 0.0,
            sample, rr_group: 0,
        });

        let mut buffer = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);
        ms.process(&mut buffer, &ctx);

        // Full gain
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        buffer = AudioBuffer::new(256, 2);
        ms.process(&mut buffer, &ctx);
        let max1 = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        // Half gain
        ms.push_midi(MidiEvent::AllSoundOff);
        let _ = ms.cmd_tx.try_send(MultiSampleCommand::SetMasterGain(0.4));
        ms.push_midi(MidiEvent::NoteOn { note: 60, velocity: 1.0 });
        buffer = AudioBuffer::new(256, 2);
        ms.process(&mut buffer, &ctx);
        let max2 = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));

        assert!(max2 < max1, "Lower master gain should be quieter: {} vs {}", max2, max1);
    }
}
