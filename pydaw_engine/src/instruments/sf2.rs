// ==========================================================================
// SF2 Instrument — FluidSynth Wrapper (API Stub)
// ==========================================================================
// v0.0.20.694 — Phase R11B
//
// This module provides the InstrumentNode interface for SF2 (SoundFont)
// playback. The actual audio rendering is delegated to FluidSynth (C lib)
// via FFI, but this stub implements the full API contract so the rest of
// the engine can integrate it.
//
// When fluidlite or fluidsynth-sys is linked, the stub methods will be
// replaced with real FFI calls. Until then, this produces silence but
// correctly handles MIDI events and voice management.
//
// Rules:
//   ✅ API matches InstrumentNode trait
//   ✅ MIDI routing works (note_on/off queued)
//   ✅ Safe to use in AudioGraph (produces silence until FFI linked)
//   ❌ No actual audio until FluidSynth C-library is linked
// ==========================================================================

use crossbeam_channel::{bounded, Receiver, Sender, TrySendError};
use std::any::Any;

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use super::{InstrumentNode, MidiEvent};

const MIDI_RING: usize = 256;

// ---------------------------------------------------------------------------
// SF2 Parameters
// ---------------------------------------------------------------------------

/// SF2 instrument parameters.
pub struct Sf2Params {
    /// Path to the loaded .sf2 file (empty = none).
    pub sf2_path: String,
    /// Bank number (0–128).
    pub bank: u16,
    /// Preset/program number (0–127).
    pub preset: u8,
    /// Master gain (0–2).
    pub gain: f32,
    /// Whether a SF2 file is loaded.
    pub loaded: bool,
}

impl Default for Sf2Params {
    fn default() -> Self {
        Self {
            sf2_path: String::new(),
            bank: 0,
            preset: 0,
            gain: 1.0,
            loaded: false,
        }
    }
}

// ---------------------------------------------------------------------------
// SF2 Instrument
// ---------------------------------------------------------------------------

/// SF2 (SoundFont 2) instrument using FluidSynth.
///
/// Currently a stub that handles MIDI correctly but produces silence.
/// When `fluidlite` crate is linked, this will render real SF2 audio.
pub struct Sf2Instrument {
    id: String,
    sample_rate: u32,
    buffer_size: usize,
    midi_tx: Sender<MidiEvent>,
    midi_rx: Receiver<MidiEvent>,
    params: Sf2Params,
    /// Simulated active note count (for voice count reporting).
    active_notes: u8,
}

impl Sf2Instrument {
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING);
        Self {
            id, sample_rate, buffer_size,
            midi_tx, midi_rx,
            params: Sf2Params::default(),
            active_notes: 0,
        }
    }

    /// Load a SoundFont file.
    ///
    /// Currently a no-op stub. When FluidSynth is linked:
    /// - Calls `fluid_synth_sfload(synth, path, 1)`
    /// - Sets the bank/preset via `fluid_synth_program_select`
    pub fn load_sf2(&mut self, path: &str, bank: u16, preset: u8) -> bool {
        self.params.sf2_path = path.to_string();
        self.params.bank = bank;
        self.params.preset = preset;
        // TODO: actual FluidSynth loading when FFI is available
        // fluid_synth_sfload(self.synth, path, 1);
        // fluid_synth_program_select(self.synth, 0, sfont_id, bank, preset);
        self.params.loaded = false; // stub: always false until FFI
        false
    }

    /// Set bank and preset (program change).
    pub fn set_program(&mut self, bank: u16, preset: u8) {
        self.params.bank = bank;
        self.params.preset = preset;
        // TODO: fluid_synth_program_select when FFI available
    }

    /// Check if a SF2 is loaded and ready.
    pub fn is_loaded(&self) -> bool {
        self.params.loaded
    }
}

impl InstrumentNode for Sf2Instrument {
    fn push_midi(&mut self, event: MidiEvent) {
        if let Err(TrySendError::Full(evt)) = self.midi_tx.try_send(event) {
            let _ = self.midi_rx.try_recv();
            let _ = self.midi_tx.try_send(evt);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        // Drain MIDI events (track active notes for reporting)
        loop {
            match self.midi_rx.try_recv() {
                Ok(evt) => match evt {
                    MidiEvent::NoteOn { note: _, velocity: _ } => {
                        self.active_notes = self.active_notes.saturating_add(1).min(128);
                        // TODO: fluid_synth_noteon(synth, chan, note, vel_int)
                    }
                    MidiEvent::NoteOff { note: _ } => {
                        self.active_notes = self.active_notes.saturating_sub(1);
                        // TODO: fluid_synth_noteoff(synth, chan, note)
                    }
                    MidiEvent::AllNotesOff | MidiEvent::AllSoundOff => {
                        self.active_notes = 0;
                        // TODO: fluid_synth_all_notes_off / all_sounds_off
                    }
                    MidiEvent::CC { cc: _, value: _ } => {
                        // TODO: fluid_synth_cc(synth, chan, cc, val_int)
                    }
                },
                Err(_) => break,
            }
        }

        // Render silence (stub)
        // TODO: fluid_synth_write_float(synth, frames, left, right)
        buffer.silence();
    }

    fn instrument_id(&self) -> &str { &self.id }
    fn instrument_name(&self) -> &str { "SF2" }
    fn instrument_type(&self) -> &str { "sf2" }
    fn set_sample_rate(&mut self, sr: u32) { self.sample_rate = sr; }
    fn set_buffer_size(&mut self, bs: usize) { self.buffer_size = bs; }
    fn active_voice_count(&self) -> usize { self.active_notes as usize }
    fn max_polyphony(&self) -> usize { 128 }
    fn as_any_mut(&mut self) -> &mut dyn Any { self }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_ctx(frames: usize, sr: u32) -> ProcessContext {
        ProcessContext {
            frames, sample_rate: sr, position_samples: 0,
            position_beats: 0.0, is_playing: true, bpm: 120.0,
            time_sig_num: 4, time_sig_den: 4,
        }
    }

    #[test]
    fn test_sf2_creation() {
        let inst = Sf2Instrument::new("sf2_1".to_string(), 44100, 512);
        assert_eq!(inst.instrument_type(), "sf2");
        assert!(!inst.is_loaded());
    }

    #[test]
    fn test_sf2_midi_tracking() {
        let mut inst = Sf2Instrument::new("t".to_string(), 44100, 256);
        let ctx = make_ctx(256, 44100);
        let mut buf = AudioBuffer::new(256, 2);

        inst.push_midi(MidiEvent::NoteOn { note: 60, velocity: 0.8 });
        inst.push_midi(MidiEvent::NoteOn { note: 64, velocity: 0.7 });
        inst.process(&mut buf, &ctx);
        assert_eq!(inst.active_voice_count(), 2);

        inst.push_midi(MidiEvent::NoteOff { note: 60 });
        inst.process(&mut buf, &ctx);
        assert_eq!(inst.active_voice_count(), 1);

        inst.push_midi(MidiEvent::AllSoundOff);
        inst.process(&mut buf, &ctx);
        assert_eq!(inst.active_voice_count(), 0);
    }

    #[test]
    fn test_sf2_load_stub() {
        let mut inst = Sf2Instrument::new("t".to_string(), 44100, 512);
        let loaded = inst.load_sf2("/path/to/gm.sf2", 0, 0);
        assert!(!loaded); // stub always returns false
    }
}
