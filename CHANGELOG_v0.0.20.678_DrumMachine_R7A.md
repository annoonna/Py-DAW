# CHANGELOG v0.0.20.678 — Phase R7A: DrumMachine Instrument

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R7A

## Was wurde gemacht

### Neues Rust-Modul: `instruments/drum_machine.rs` (~620 Zeilen)
- **DrumPad**: 128 pre-allokierte Pad-Slots mit Sample, Gain, Pan, Tune, Choke Group, Play Mode, ADSR
- **DrumVoice**: 64-Voice Pool mit per-voice ADSR, cubic Interpolation, equal-power Pan
- **DrumMachineInstrument**: InstrumentNode-Implementierung mit lock-free MIDI/Command Channels
- **Choke Groups**: 0-8, Trigger in Gruppe → alle anderen Voices in der Gruppe werden gekillt
- **Retrigger**: Same-Pad-Retrigger killt alte Voice, startet neue
- **Play Modes**: OneShot (play to end, ignore note-off) vs Gate (release on note-off)
- **GM Drum Map**: 16 Standard-Namen (Kick, Snare, CHat, OHat, ...), base_note=36
- **12 Unit-Tests**: Creation, Names, Silence, Load+Trigger, Note-Below-Base, Choke Groups, Retrigger, Multi-Pad, AllSoundOff, Gate Mode, ClearAll, PlayMode Parse

### IPC Commands (`ipc.rs`)
5 neue Commands: LoadDrumPadSample, ClearDrumPad, SetDrumPadParam, ClearAllDrumPads, SetDrumBaseNote

### Engine Dispatch (`engine.rs`)
Vollständige match-Arms für alle 5 DrumMachine-Commands mit downcast_mut Pattern

### Python Bridge (`rust_engine_bridge.py`)
5 neue Methoden: load_drum_pad_sample, clear_drum_pad, set_drum_pad_param, clear_all_drum_pads, set_drum_base_note

### instruments/mod.rs
DrumMachine registriert + Factory + Test

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/instruments/drum_machine.rs | **NEU** (~620 Zeilen) |
| pydaw_engine/src/instruments/mod.rs | DrumMachine registriert, Factory, Test |
| pydaw_engine/src/ipc.rs | 5 neue IPC Commands |
| pydaw_engine/src/engine.rs | 5 neue match-Arms |
| pydaw/services/rust_engine_bridge.py | 5 neue Bridge-Methoden |
| VERSION, pydaw/version.py | 677 → 678 |

## Was als nächstes zu tun ist
- Phase R7B — Multi-Output: Per-Pad Output-Routing, Separate Buffers pro Output
- Phase R8A — AETERNA Synth: Oszillatoren (Sine, Saw, Square, Triangle, Noise)
