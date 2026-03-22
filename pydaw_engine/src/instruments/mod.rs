// ==========================================================================
// Instruments Module — MIDI-driven audio generators
// ==========================================================================
// v0.0.20.674 — Phase R6A
//
// Every instrument implements the InstrumentNode trait, which extends
// AudioNode with MIDI input capabilities.
//
// Currently implemented:
//   - ProSamplerInstrument (Phase R6A): Single-sample polyphonic sampler
//   - MultiSampleInstrument (Phase R6B): Zone-mapped multi-sample with per-zone DSP
//   - DrumMachineInstrument (Phase R7A): 128-pad drum machine with choke groups
//   - AeternaInstrument (Phase R8B): Subtractive synth with PolyBLEP osc, filter, AEG/FEG, voice pool, glide
//   - FusionInstrument (Phase R10C): Semi-modular synth with swappable OSC/FLT/ENV types
//   - BachOrgelInstrument (Phase R11A): Additive organ with 9 drawbars, rotary speaker
//   - Sf2Instrument (Phase R11B): SoundFont 2 stub (FluidSynth FFI pending)
//
// Rules:
//   ✅ All instruments implement AudioNode (pluggable into AudioGraph)
//   ✅ MIDI events are queued lock-free, consumed in process()
//   ✅ Voice management is pre-allocated (no heap in audio thread)
//   ❌ NO allocations in process()
//   ❌ NO locks in process()
// ==========================================================================

pub mod sampler;
pub mod multisample;
pub mod drum_machine;
pub mod aeterna;
pub mod fusion;
pub mod bach_orgel;
pub mod sf2;

// Re-exports
pub use sampler::ProSamplerInstrument;
pub use multisample::MultiSampleInstrument;
pub use drum_machine::DrumMachineInstrument;
pub use aeterna::AeternaInstrument;
pub use fusion::FusionInstrument;
pub use bach_orgel::BachOrgelInstrument;
pub use sf2::Sf2Instrument;

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;

use std::any::Any;

// ---------------------------------------------------------------------------
// MIDI Event — lightweight, copy-able, for lock-free queuing
// ---------------------------------------------------------------------------

/// A MIDI event to be processed by an instrument.
#[derive(Debug, Clone, Copy)]
pub enum MidiEvent {
    /// Note on: note number, velocity (0.0–1.0).
    NoteOn { note: u8, velocity: f32 },
    /// Note off: note number.
    NoteOff { note: u8 },
    /// Control change: controller number, value (0.0–1.0).
    CC { cc: u8, value: f32 },
    /// All notes off (panic).
    AllNotesOff,
    /// All sound off (immediate kill).
    AllSoundOff,
}

// ---------------------------------------------------------------------------
// InstrumentNode Trait
// ---------------------------------------------------------------------------

/// Trait for MIDI-driven audio generators.
///
/// Extends the audio processing concept with MIDI input.
/// Instruments receive MIDI events via `push_midi()` (from command thread)
/// and consume them in `process()` (on audio thread).
///
/// The separation allows lock-free MIDI delivery:
///   1. Command thread calls `push_midi(event)` → queues event
///   2. Audio thread calls `process()` → drains queue, generates audio
pub trait InstrumentNode: Send {
    /// Queue a MIDI event for processing in the next audio callback.
    ///
    /// **COMMAND THREAD** — may allocate if ring buffer needs to grow,
    /// but the fixed-size ring should handle normal loads without alloc.
    fn push_midi(&mut self, event: MidiEvent);

    /// Process one buffer of audio, consuming any queued MIDI events.
    ///
    /// `buffer` is pre-zeroed for generators. Output is written into buffer.
    ///
    /// **AUDIO THREAD** — no allocations, no locks, no panics.
    fn process(&mut self, buffer: &mut AudioBuffer, ctx: &ProcessContext);

    /// Get the instrument's unique identifier.
    fn instrument_id(&self) -> &str;

    /// Get the instrument's display name.
    fn instrument_name(&self) -> &str;

    /// Get the instrument type string (for IPC/serialization).
    fn instrument_type(&self) -> &str;

    /// Set sample rate (called when audio config changes).
    fn set_sample_rate(&mut self, sample_rate: u32);

    /// Set maximum buffer size (called when audio config changes).
    fn set_buffer_size(&mut self, buffer_size: usize);

    /// Get the number of active voices.
    fn active_voice_count(&self) -> usize;

    /// Get the maximum polyphony.
    fn max_polyphony(&self) -> usize;

    /// Downcast to concrete type for type-specific operations.
    fn as_any_mut(&mut self) -> &mut dyn Any;
}

// ---------------------------------------------------------------------------
// Instrument Type Registry
// ---------------------------------------------------------------------------

/// Known instrument types for IPC dispatch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InstrumentType {
    ProSampler,
    MultiSample,
    DrumMachine,
    Aeterna,
    Fusion,
    BachOrgel,
    Sf2,
}

impl InstrumentType {
    /// Parse instrument type from string (IPC command).
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            // Standard names + Python chrono.* plugin_type names
            "pro_sampler" | "sampler" | "ProSampler"
                | "chrono.pro_audio_sampler" | "chrono.sampler" => Some(Self::ProSampler),
            "multi_sample" | "multisample" | "MultiSample"
                | "chrono.multisample" => Some(Self::MultiSample),
            "drum_machine" | "DrumMachine"
                | "chrono.pro_drum_machine" | "chrono.drum_machine" => Some(Self::DrumMachine),
            "aeterna" | "Aeterna" | "AETERNA"
                | "chrono.aeterna" => Some(Self::Aeterna),
            "fusion" | "Fusion"
                | "chrono.fusion" => Some(Self::Fusion),
            "bach_orgel" | "BachOrgel"
                | "chrono.bach_orgel" => Some(Self::BachOrgel),
            "sf2" | "SF2" | "soundfont" => Some(Self::Sf2),
            _ => None,
        }
    }

    /// Create an instrument instance from type.
    /// Returns a boxed InstrumentNode ready for use.
    pub fn create(&self, id: String, sample_rate: u32, buffer_size: usize) -> Option<Box<dyn InstrumentNode>> {
        match self {
            Self::ProSampler => {
                Some(Box::new(ProSamplerInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::MultiSample => {
                Some(Box::new(MultiSampleInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::DrumMachine => {
                Some(Box::new(DrumMachineInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::Aeterna => {
                Some(Box::new(AeternaInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::Fusion => {
                Some(Box::new(FusionInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::BachOrgel => {
                Some(Box::new(BachOrgelInstrument::new(id, sample_rate, buffer_size)))
            }
            Self::Sf2 => {
                Some(Box::new(Sf2Instrument::new(id, sample_rate, buffer_size)))
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

    #[test]
    fn test_instrument_type_from_str() {
        assert_eq!(InstrumentType::from_str("pro_sampler"), Some(InstrumentType::ProSampler));
        assert_eq!(InstrumentType::from_str("sampler"), Some(InstrumentType::ProSampler));
        assert_eq!(InstrumentType::from_str("drum_machine"), Some(InstrumentType::DrumMachine));
        assert_eq!(InstrumentType::from_str("aeterna"), Some(InstrumentType::Aeterna));
        assert_eq!(InstrumentType::from_str("unknown"), None);
    }

    #[test]
    fn test_instrument_type_create() {
        let inst = InstrumentType::ProSampler.create("test_sampler".to_string(), 44100, 512);
        assert!(inst.is_some());
        let inst = inst.unwrap();
        assert_eq!(inst.instrument_type(), "pro_sampler");
        assert_eq!(inst.instrument_id(), "test_sampler");
    }

    #[test]
    fn test_instrument_type_create_multisample() {
        let inst = InstrumentType::MultiSample.create("test_ms".to_string(), 44100, 512);
        assert!(inst.is_some());
        let inst = inst.unwrap();
        assert_eq!(inst.instrument_type(), "multi_sample");
        assert_eq!(inst.instrument_id(), "test_ms");
        assert_eq!(inst.instrument_name(), "MultiSample");
    }

    #[test]
    fn test_instrument_type_create_drum_machine() {
        let inst = InstrumentType::DrumMachine.create("test_dm".to_string(), 44100, 512);
        assert!(inst.is_some());
        let inst = inst.unwrap();
        assert_eq!(inst.instrument_type(), "drum_machine");
        assert_eq!(inst.instrument_id(), "test_dm");
        assert_eq!(inst.instrument_name(), "DrumMachine");
    }

    #[test]
    fn test_instrument_type_create_aeterna() {
        let inst = InstrumentType::Aeterna.create("test_ae".to_string(), 44100, 512);
        assert!(inst.is_some());
        let inst = inst.unwrap();
        assert_eq!(inst.instrument_type(), "aeterna");
        assert_eq!(inst.instrument_id(), "test_ae");
        assert_eq!(inst.instrument_name(), "AETERNA");
        assert_eq!(inst.max_polyphony(), 32);
    }

    #[test]
    fn test_instrument_type_create_fusion() {
        let inst = InstrumentType::Fusion.create("test_fu".to_string(), 44100, 512);
        assert!(inst.is_some());
        let inst = inst.unwrap();
        assert_eq!(inst.instrument_type(), "fusion");
        assert_eq!(inst.instrument_id(), "test_fu");
        assert_eq!(inst.instrument_name(), "Fusion");
        assert_eq!(inst.max_polyphony(), 8);
    }

    #[test]
    fn test_midi_event_is_copy() {
        let evt = MidiEvent::NoteOn { note: 60, velocity: 0.8 };
        let _copy = evt; // MidiEvent is Copy
        let _copy2 = evt; // Can copy again
    }
}
