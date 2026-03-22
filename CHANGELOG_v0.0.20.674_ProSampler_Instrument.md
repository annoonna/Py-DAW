# CHANGELOG v0.0.20.674 — ProSampler Instrument (Phase R6A)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R6A — ProSampler Instrument

## Was wurde gemacht

### Neues Instrument-System (instruments/ Modul)
- `InstrumentNode` Trait: push_midi(), process(), as_any_mut() für sicheres Downcasting
- `MidiEvent` Enum: NoteOn, NoteOff, CC, AllNotesOff, AllSoundOff (Copy, lock-free tauglich)
- `InstrumentType` Registry mit from_str() + create() Factory für alle geplanten Instrumente

### ProSamplerInstrument (instruments/sampler.rs, ~760 Zeilen)
- Polyphoner Single-Sample-Sampler auf Basis R5 VoicePool (max 64 Voices)
- ADSR Envelope (aus R1), One-Shot/Loop Playback, Velocity→Volume Mapping
- Lock-free MIDI-Input via crossbeam_channel (256 Events bounded Ring)
- Lock-free Parameter-Commands: SetAdsr, SetGain, SetPan, SetLoop, SetStealMode, SetRootNote, SetFineTune, SetVelocityCurve
- Velocity Curve: Linear (0.0) bis Exponential (1.0) Blend
- CC-Handling: CC64 Sustain, CC120 All Sound Off, CC123 All Notes Off
- 15 Unit-Tests

### AudioGraph Integration
- TrackNode um `instrument: Option<Box<dyn InstrumentNode>>` Feld erweitert
- Instrument-Processing VOR Track-Params (Volume/Pan/FX) in der Process-Schleife
- ProcessContext wird für jedes Instrument gebaut

### Engine MIDI-Routing
- MidiNoteOn/Off/CC → Instrument auf dem Track geroutet (war vorher Stub)
- 5 neue Instrument-Commands: LoadInstrument, UnloadInstrument, LoadSample, ClearSample, SetInstrumentParam
- Typ-sicheres Downcasting via as_any_mut() für ProSampler-spezifische Operationen

### IPC Protocol
- 5 neue Commands in ipc.rs: LoadInstrument, UnloadInstrument, LoadSample, ClearSample, SetInstrumentParam

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/instruments/mod.rs | **NEU**: InstrumentNode Trait, MidiEvent, InstrumentType Registry |
| pydaw_engine/src/instruments/sampler.rs | **NEU**: ProSamplerInstrument (~760 Zeilen) |
| pydaw_engine/src/main.rs | `mod instruments;` hinzugefügt |
| pydaw_engine/src/audio_graph.rs | TrackNode.instrument Feld, Instrument-Processing in process() |
| pydaw_engine/src/engine.rs | MIDI-Routing, 5 Instrument-Command-Handler |
| pydaw_engine/src/ipc.rs | 5 neue IPC Commands |
| VERSION | 673 → 674 |
| pydaw/version.py | 673 → 674 |

## Was als nächstes zu tun ist
- Phase R6B — MultiSample / Advanced Sampler: Zone-Mapping, Round-Robin, Per-Zone Filter, Modulation
- Der nächste Kollege sollte als ERSTES `cargo build && cargo test` ausführen

## Bekannte Probleme / Offene Fragen
- cargo build/test konnten im Container NICHT ausgeführt werden (Rust-Toolchain nicht installiert, Netzwerk eingeschränkt)
- Code ist syntaktisch konsistent geprüft (Cross-Reference aller Typen, Trait-Methoden, Importe)
- AudioGraph::process() übergibt noch statische Transport-Daten (position_samples=0) an Instrumente — muss in R12 mit echtem Transport-State verbunden werden
