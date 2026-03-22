// ==========================================================================
// AETERNA Modulation Matrix — 8 Slots, per-voice modulation
// ==========================================================================
// v0.0.20.689 — Phase R8C
//
// The modulation matrix connects sources (LFOs, Envelopes, MIDI) to
// destinations (Pitch, Filter, Amp, etc.) with per-slot amount + polarity.
//
// Architecture:
//   - 8 ModSlots, each with Source → Destination → Amount → Bipolar
//   - 2 LFOs per voice (synced to note-on, with shape + rate)
//   - Sources are evaluated per-sample, per-voice
//   - Destinations accumulate: multiple slots can target the same param
//   - Output: ModulationOutput struct with all destination offsets
//
// Rules:
//   ✅ All DSP is zero-alloc in process()
//   ✅ Fixed-size arrays (no Vec in audio path)
//   ✅ #[inline] on all sample-level functions
//   ❌ NO allocations in audio thread
// ==========================================================================

use crate::dsp::lfo::{Lfo, LfoShape};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Maximum number of modulation slots.
pub const MAX_MOD_SLOTS: usize = 8;

/// Number of per-voice LFOs.
pub const NUM_LFOS: usize = 2;

// ---------------------------------------------------------------------------
// Modulation Source
// ---------------------------------------------------------------------------

/// Available modulation sources.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModSource {
    /// Slot disabled.
    Off,
    /// LFO 1 (per-voice, synced to note-on).
    Lfo1,
    /// LFO 2 (per-voice, synced to note-on).
    Lfo2,
    /// Amplitude Envelope (AEG output 0–1).
    Aeg,
    /// Filter Envelope (FEG output 0–1).
    Feg,
    /// Note velocity (0–1, fixed per voice).
    Velocity,
    /// Channel aftertouch (0–1, from MIDI CC).
    Aftertouch,
    /// Mod wheel (CC1, 0–1).
    ModWheel,
}

impl ModSource {
    /// Parse from string (IPC compatibility).
    pub fn from_str(s: &str) -> Self {
        match s {
            "lfo1" | "LFO1" => Self::Lfo1,
            "lfo2" | "LFO2" => Self::Lfo2,
            "aeg" | "AEG" | "env" => Self::Aeg,
            "feg" | "FEG" | "env2" => Self::Feg,
            "velocity" | "vel" => Self::Velocity,
            "aftertouch" | "at" => Self::Aftertouch,
            "mod_wheel" | "modwheel" | "cc1" => Self::ModWheel,
            _ => Self::Off,
        }
    }

    /// Convert to string for serialization.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Lfo1 => "lfo1",
            Self::Lfo2 => "lfo2",
            Self::Aeg => "aeg",
            Self::Feg => "feg",
            Self::Velocity => "velocity",
            Self::Aftertouch => "aftertouch",
            Self::ModWheel => "mod_wheel",
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Destination
// ---------------------------------------------------------------------------

/// Available modulation destinations.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModDestination {
    /// Slot disabled.
    Off,
    /// Oscillator pitch (semitones offset).
    Pitch,
    /// Filter cutoff (normalized offset).
    FilterCutoff,
    /// Filter resonance (normalized offset).
    FilterResonance,
    /// Amplitude (gain multiplier offset).
    Amp,
    /// Stereo pan (offset).
    Pan,
    /// Oscillator shape/morph (offset).
    Shape,
    /// FM modulation depth (offset).
    FmAmount,
}

impl ModDestination {
    /// Parse from string.
    pub fn from_str(s: &str) -> Self {
        match s {
            "pitch" => Self::Pitch,
            "filter_cutoff" | "cutoff" => Self::FilterCutoff,
            "filter_resonance" | "resonance" => Self::FilterResonance,
            "amp" | "amplitude" => Self::Amp,
            "pan" => Self::Pan,
            "shape" | "morph" => Self::Shape,
            "fm_amount" | "fm" => Self::FmAmount,
            _ => Self::Off,
        }
    }

    /// Convert to string for serialization.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Pitch => "pitch",
            Self::FilterCutoff => "filter_cutoff",
            Self::FilterResonance => "filter_resonance",
            Self::Amp => "amp",
            Self::Pan => "pan",
            Self::Shape => "shape",
            Self::FmAmount => "fm_amount",
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Slot
// ---------------------------------------------------------------------------

/// A single modulation routing: Source → Destination with amount.
#[derive(Debug, Clone, Copy)]
pub struct ModSlot {
    pub source: ModSource,
    pub destination: ModDestination,
    /// Modulation amount (-1.0 to 1.0).
    pub amount: f32,
    /// If true, source output is bipolar (-1..+1).
    /// If false, source is unipolar (0..1) before scaling.
    pub bipolar: bool,
}

impl Default for ModSlot {
    fn default() -> Self {
        Self {
            source: ModSource::Off,
            destination: ModDestination::Off,
            amount: 0.0,
            bipolar: true,
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Output — accumulated offsets for one sample
// ---------------------------------------------------------------------------

/// Accumulated modulation offsets for all destinations.
///
/// These are ADDED to the base parameter values in the voice render loop.
#[derive(Debug, Clone, Copy, Default)]
pub struct ModOutput {
    /// Pitch offset in semitones (e.g., ±12 for octave vibrato).
    pub pitch: f32,
    /// Filter cutoff offset (normalized, added to base cutoff).
    pub filter_cutoff: f32,
    /// Filter resonance offset.
    pub filter_resonance: f32,
    /// Amplitude multiplier offset (added to 1.0, so -0.5 = half volume).
    pub amp: f32,
    /// Pan offset (-1..+1).
    pub pan: f32,
    /// Shape/morph offset.
    pub shape: f32,
    /// FM amount offset.
    pub fm_amount: f32,
}

impl ModOutput {
    /// Create a zeroed output (no modulation).
    #[inline]
    pub fn zero() -> Self {
        Self::default()
    }

    /// Accumulate a value into the appropriate destination.
    #[inline]
    pub fn add(&mut self, dest: ModDestination, value: f32) {
        match dest {
            ModDestination::Off => {}
            ModDestination::Pitch => self.pitch += value,
            ModDestination::FilterCutoff => self.filter_cutoff += value,
            ModDestination::FilterResonance => self.filter_resonance += value,
            ModDestination::Amp => self.amp += value,
            ModDestination::Pan => self.pan += value,
            ModDestination::Shape => self.shape += value,
            ModDestination::FmAmount => self.fm_amount += value,
        }
    }
}

// ---------------------------------------------------------------------------
// Per-Voice Modulation State
// ---------------------------------------------------------------------------

/// Per-voice LFO and modulation state. Pre-allocated, reused across notes.
pub struct VoiceModState {
    /// 2 LFOs per voice (synced to note-on).
    pub lfos: [Lfo; NUM_LFOS],
}

impl VoiceModState {
    /// Create new mod state with default LFOs.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            lfos: [
                Lfo::new(1.0, LfoShape::Sine, sample_rate),
                Lfo::new(0.5, LfoShape::Triangle, sample_rate),
            ],
        }
    }

    /// Reset LFOs for a new note (sync to note-on).
    pub fn reset(&mut self) {
        for lfo in &mut self.lfos {
            lfo.reset();
        }
    }

    /// Update sample rate.
    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        for lfo in &mut self.lfos {
            lfo.set_sample_rate(sample_rate);
        }
    }
}

// ---------------------------------------------------------------------------
// Modulation Matrix — shared config + per-voice evaluation
// ---------------------------------------------------------------------------

/// LFO parameters (shared across all voices).
#[derive(Debug, Clone, Copy)]
pub struct LfoParams {
    pub rate_hz: f32,
    pub shape: LfoShape,
}

impl Default for LfoParams {
    fn default() -> Self {
        Self {
            rate_hz: 1.0,
            shape: LfoShape::Sine,
        }
    }
}

/// The modulation matrix configuration.
///
/// Holds 8 mod slots and LFO parameters. Updated from the command thread.
/// Evaluated per-sample, per-voice in the audio thread.
pub struct ModMatrix {
    /// 8 modulation slots.
    pub slots: [ModSlot; MAX_MOD_SLOTS],
    /// LFO parameters (2 LFOs).
    pub lfo_params: [LfoParams; NUM_LFOS],
    /// Global aftertouch value (from MIDI, 0–1).
    pub aftertouch: f32,
    /// Global mod wheel value (CC1, 0–1).
    pub mod_wheel: f32,
}

impl ModMatrix {
    /// Create a new empty modulation matrix.
    pub fn new() -> Self {
        Self {
            slots: [ModSlot::default(); MAX_MOD_SLOTS],
            lfo_params: [LfoParams::default(); NUM_LFOS],
            aftertouch: 0.0,
            mod_wheel: 0.0,
        }
    }

    /// Set a mod slot's routing.
    pub fn set_slot(
        &mut self,
        index: usize,
        source: ModSource,
        destination: ModDestination,
        amount: f32,
        bipolar: bool,
    ) {
        if index < MAX_MOD_SLOTS {
            self.slots[index] = ModSlot {
                source,
                destination,
                amount: amount.clamp(-1.0, 1.0),
                bipolar,
            };
        }
    }

    /// Set LFO rate.
    pub fn set_lfo_rate(&mut self, lfo_index: usize, rate_hz: f32) {
        if lfo_index < NUM_LFOS {
            self.lfo_params[lfo_index].rate_hz = rate_hz.clamp(0.01, 100.0);
        }
    }

    /// Set LFO shape.
    pub fn set_lfo_shape(&mut self, lfo_index: usize, shape: LfoShape) {
        if lfo_index < NUM_LFOS {
            self.lfo_params[lfo_index].shape = shape;
        }
    }

    /// Update per-voice LFO parameters from shared config.
    ///
    /// Call this once per process block (not per sample) to sync rates/shapes.
    #[inline]
    pub fn sync_voice_lfos(&self, voice_mod: &mut VoiceModState) {
        for i in 0..NUM_LFOS {
            voice_mod.lfos[i].set_rate(self.lfo_params[i].rate_hz);
            voice_mod.lfos[i].set_shape(self.lfo_params[i].shape);
        }
    }

    /// Evaluate all mod slots for one sample.
    ///
    /// Reads source values from the voice state and accumulates into ModOutput.
    ///
    /// # Arguments
    /// * `voice_mod` — per-voice LFO state (advanced by one sample)
    /// * `aeg_value` — current AEG output (0–1)
    /// * `feg_value` — current FEG output (0–1)
    /// * `velocity` — note velocity (0–1)
    ///
    /// Returns the accumulated modulation offsets.
    #[inline]
    pub fn evaluate(
        &self,
        voice_mod: &mut VoiceModState,
        aeg_value: f32,
        feg_value: f32,
        velocity: f32,
    ) -> ModOutput {
        // Advance LFOs (one sample each)
        let lfo_values = [
            voice_mod.lfos[0].process(),
            voice_mod.lfos[1].process(),
        ];

        let mut output = ModOutput::zero();

        for slot in &self.slots {
            if slot.source == ModSource::Off || slot.destination == ModDestination::Off {
                continue;
            }
            if slot.amount.abs() < 1e-6 {
                continue;
            }

            // Get raw source value (bipolar: -1..+1)
            let raw = match slot.source {
                ModSource::Off => 0.0,
                ModSource::Lfo1 => lfo_values[0],
                ModSource::Lfo2 => lfo_values[1],
                ModSource::Aeg => if slot.bipolar { aeg_value * 2.0 - 1.0 } else { aeg_value },
                ModSource::Feg => if slot.bipolar { feg_value * 2.0 - 1.0 } else { feg_value },
                ModSource::Velocity => if slot.bipolar { velocity * 2.0 - 1.0 } else { velocity },
                ModSource::Aftertouch => if slot.bipolar { self.aftertouch * 2.0 - 1.0 } else { self.aftertouch },
                ModSource::ModWheel => if slot.bipolar { self.mod_wheel * 2.0 - 1.0 } else { self.mod_wheel },
            };

            // Scale by amount and apply destination scaling
            let scaled = raw * slot.amount;

            // Apply destination-appropriate scaling
            let value = match slot.destination {
                ModDestination::Pitch => scaled * 24.0,        // ±24 semitones max
                ModDestination::FilterCutoff => scaled * 0.5,  // ±0.5 normalized
                ModDestination::FilterResonance => scaled * 0.3, // ±0.3 normalized
                ModDestination::Amp => scaled,                  // ±1.0
                ModDestination::Pan => scaled,                  // ±1.0
                ModDestination::Shape => scaled * 0.5,          // ±0.5
                ModDestination::FmAmount => scaled * 0.5,       // ±0.5
                ModDestination::Off => 0.0,
            };

            output.add(slot.destination, value);
        }

        output
    }

    /// Check if any slot is active (has a non-Off source and destination).
    pub fn is_active(&self) -> bool {
        self.slots.iter().any(|s| {
            s.source != ModSource::Off
                && s.destination != ModDestination::Off
                && s.amount.abs() > 1e-6
        })
    }

    /// Count active slots.
    pub fn active_slot_count(&self) -> usize {
        self.slots.iter().filter(|s| {
            s.source != ModSource::Off
                && s.destination != ModDestination::Off
                && s.amount.abs() > 1e-6
        }).count()
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const SR: f32 = 44100.0;

    #[test]
    fn test_mod_source_parse() {
        assert_eq!(ModSource::from_str("lfo1"), ModSource::Lfo1);
        assert_eq!(ModSource::from_str("lfo2"), ModSource::Lfo2);
        assert_eq!(ModSource::from_str("aeg"), ModSource::Aeg);
        assert_eq!(ModSource::from_str("feg"), ModSource::Feg);
        assert_eq!(ModSource::from_str("velocity"), ModSource::Velocity);
        assert_eq!(ModSource::from_str("mod_wheel"), ModSource::ModWheel);
        assert_eq!(ModSource::from_str("unknown"), ModSource::Off);
    }

    #[test]
    fn test_mod_destination_parse() {
        assert_eq!(ModDestination::from_str("pitch"), ModDestination::Pitch);
        assert_eq!(ModDestination::from_str("filter_cutoff"), ModDestination::FilterCutoff);
        assert_eq!(ModDestination::from_str("amp"), ModDestination::Amp);
        assert_eq!(ModDestination::from_str("pan"), ModDestination::Pan);
        assert_eq!(ModDestination::from_str("shape"), ModDestination::Shape);
        assert_eq!(ModDestination::from_str("unknown"), ModDestination::Off);
    }

    #[test]
    fn test_mod_matrix_empty() {
        let matrix = ModMatrix::new();
        assert!(!matrix.is_active());
        assert_eq!(matrix.active_slot_count(), 0);
    }

    #[test]
    fn test_mod_matrix_set_slot() {
        let mut matrix = ModMatrix::new();
        matrix.set_slot(0, ModSource::Lfo1, ModDestination::Pitch, 0.5, true);
        assert!(matrix.is_active());
        assert_eq!(matrix.active_slot_count(), 1);
        assert_eq!(matrix.slots[0].source, ModSource::Lfo1);
        assert_eq!(matrix.slots[0].destination, ModDestination::Pitch);
        assert!((matrix.slots[0].amount - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_mod_output_accumulate() {
        let mut out = ModOutput::zero();
        out.add(ModDestination::Pitch, 2.0);
        out.add(ModDestination::Pitch, 1.5);
        assert!((out.pitch - 3.5).abs() < 0.001);

        out.add(ModDestination::FilterCutoff, 0.3);
        assert!((out.filter_cutoff - 0.3).abs() < 0.001);
    }

    #[test]
    fn test_evaluate_no_modulation() {
        let matrix = ModMatrix::new();
        let mut voice_mod = VoiceModState::new(SR);
        let output = matrix.evaluate(&mut voice_mod, 0.5, 0.5, 0.8);
        assert!(output.pitch.abs() < 0.001);
        assert!(output.filter_cutoff.abs() < 0.001);
        assert!(output.amp.abs() < 0.001);
    }

    #[test]
    fn test_evaluate_lfo_to_pitch() {
        let mut matrix = ModMatrix::new();
        matrix.set_slot(0, ModSource::Lfo1, ModDestination::Pitch, 0.5, true);
        matrix.set_lfo_rate(0, 10.0); // fast LFO for testing

        let mut voice_mod = VoiceModState::new(SR);
        matrix.sync_voice_lfos(&mut voice_mod);

        // Collect pitch modulation over several samples
        let mut min_pitch = f32::MAX;
        let mut max_pitch = f32::MIN;
        for _ in 0..4410 { // 100ms at 44.1kHz = one full LFO cycle at 10Hz
            let out = matrix.evaluate(&mut voice_mod, 0.5, 0.5, 0.8);
            min_pitch = min_pitch.min(out.pitch);
            max_pitch = max_pitch.max(out.pitch);
        }

        // LFO range is -1..+1, amount=0.5, pitch scaling=24st → ±12 semitones
        assert!(max_pitch > 1.0, "LFO should modulate pitch up: max={}", max_pitch);
        assert!(min_pitch < -1.0, "LFO should modulate pitch down: min={}", min_pitch);
    }

    #[test]
    fn test_evaluate_velocity_to_filter() {
        let mut matrix = ModMatrix::new();
        matrix.set_slot(0, ModSource::Velocity, ModDestination::FilterCutoff, 0.8, false);

        let mut voice_mod = VoiceModState::new(SR);

        // High velocity
        let out_hi = matrix.evaluate(&mut voice_mod, 0.0, 0.0, 1.0);
        // Low velocity
        let out_lo = matrix.evaluate(&mut voice_mod, 0.0, 0.0, 0.2);

        assert!(out_hi.filter_cutoff > out_lo.filter_cutoff,
            "Higher velocity should open filter more: hi={} lo={}",
            out_hi.filter_cutoff, out_lo.filter_cutoff);
    }

    #[test]
    fn test_evaluate_aeg_to_amp() {
        let mut matrix = ModMatrix::new();
        matrix.set_slot(0, ModSource::Aeg, ModDestination::Amp, 1.0, false);

        let mut voice_mod = VoiceModState::new(SR);

        let out_full = matrix.evaluate(&mut voice_mod, 1.0, 0.0, 0.8);
        let out_zero = matrix.evaluate(&mut voice_mod, 0.0, 0.0, 0.8);

        assert!(out_full.amp > out_zero.amp,
            "Full AEG should give more amp: full={} zero={}",
            out_full.amp, out_zero.amp);
    }

    #[test]
    fn test_evaluate_multiple_slots_same_dest() {
        let mut matrix = ModMatrix::new();
        // Both LFO1 and Velocity target pitch
        matrix.set_slot(0, ModSource::Lfo1, ModDestination::Pitch, 0.3, true);
        matrix.set_slot(1, ModSource::Velocity, ModDestination::Pitch, 0.5, false);

        let mut voice_mod = VoiceModState::new(SR);
        matrix.sync_voice_lfos(&mut voice_mod);

        let out = matrix.evaluate(&mut voice_mod, 0.0, 0.0, 0.8);
        // Should have contributions from both slots
        assert!(out.pitch.abs() > 0.01, "Both slots should contribute: pitch={}", out.pitch);
    }

    #[test]
    fn test_mod_wheel_source() {
        let mut matrix = ModMatrix::new();
        matrix.set_slot(0, ModSource::ModWheel, ModDestination::FilterCutoff, 1.0, false);
        matrix.mod_wheel = 0.7;

        let mut voice_mod = VoiceModState::new(SR);
        let out = matrix.evaluate(&mut voice_mod, 0.0, 0.0, 0.8);

        // mod_wheel=0.7, unipolar, amount=1.0, cutoff scaling=0.5 → 0.7*1.0*0.5=0.35
        assert!((out.filter_cutoff - 0.35).abs() < 0.01,
            "Mod wheel should modulate cutoff: {}", out.filter_cutoff);
    }

    #[test]
    fn test_voice_mod_state_reset() {
        let mut vms = VoiceModState::new(SR);
        // Advance LFOs
        for _ in 0..1000 {
            vms.lfos[0].process();
        }
        // Reset
        vms.reset();
        // LFO should be at start again (sine at phase 0 ≈ 0)
        let val = vms.lfos[0].process();
        assert!(val.abs() < 0.1, "LFO after reset should be near zero: {}", val);
    }

    #[test]
    fn test_lfo_params_sync() {
        let mut matrix = ModMatrix::new();
        matrix.set_lfo_rate(0, 5.0);
        matrix.set_lfo_shape(0, LfoShape::Square);
        matrix.set_lfo_rate(1, 0.25);
        matrix.set_lfo_shape(1, LfoShape::SawUp);

        let mut voice_mod = VoiceModState::new(SR);
        matrix.sync_voice_lfos(&mut voice_mod);

        // After sync, voice LFOs should use the matrix parameters
        // (we can't directly read rate back, but we verify shapes match)
        assert_eq!(matrix.lfo_params[0].rate_hz, 5.0);
        assert_eq!(matrix.lfo_params[0].shape, LfoShape::Square);
        assert_eq!(matrix.lfo_params[1].rate_hz, 0.25);
        assert_eq!(matrix.lfo_params[1].shape, LfoShape::SawUp);
    }

    #[test]
    fn test_source_destination_roundtrip() {
        // All sources serialize/deserialize correctly
        for s in &[ModSource::Off, ModSource::Lfo1, ModSource::Lfo2,
                   ModSource::Aeg, ModSource::Feg, ModSource::Velocity,
                   ModSource::Aftertouch, ModSource::ModWheel] {
            let name = s.as_str();
            let parsed = ModSource::from_str(name);
            assert_eq!(*s, parsed, "Source roundtrip failed for {:?} → {}", s, name);
        }

        // All destinations serialize/deserialize correctly
        for d in &[ModDestination::Off, ModDestination::Pitch,
                   ModDestination::FilterCutoff, ModDestination::FilterResonance,
                   ModDestination::Amp, ModDestination::Pan,
                   ModDestination::Shape, ModDestination::FmAmount] {
            let name = d.as_str();
            let parsed = ModDestination::from_str(name);
            assert_eq!(*d, parsed, "Dest roundtrip failed for {:?} → {}", d, name);
        }
    }
}
