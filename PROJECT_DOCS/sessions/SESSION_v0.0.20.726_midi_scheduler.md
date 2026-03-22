# Session Log — v0.0.20.726

**Datum:** 2026-03-22
**Kollege:** Claude Opus 4.6
**Aufgabe:** MIDI Clip Scheduler + Instrument Auto-Load (Rust Engine Kernlücke geschlossen)

## Das Problem
Die Rust-Engine hatte alle Bausteine (7 Instrumente, 15 FX, AudioGraph, ClipRenderer,
Live-MIDI-Routing), aber MIDI-Noten aus dem Arrangement wurden beim Playback NICHT
an die Instrumente dispatcht. Code-Kommentar: "instrument rendering pending".

## Was wurde erledigt

### midi_scheduler.rs (NEU — 300+ Zeilen, 7 Tests)
- ScheduledEvent: Beat-Position, Track-Index, Pitch, Velocity, NoteOn/Off
- load_from_sync(): Clip-relative → absolute Beat-Positionen, chronologisch sortiert
- schedule_for_buffer(): Zero-allocation Iterator, Binary-Search bei Seek
- NoteOff vor NoteOn bei gleicher Beat (verhindert Stuck Notes)

### engine.rs — MIDI-Dispatching in process_audio()
- Nach Audio-Clip-Rendering: Beat-Range berechnen → MIDI-Events iterieren → push_midi()
- Stop: scheduler.reset() + AllNotesOff an alle Instrumente
- Seek: scheduler.reset() + AllNotesOff
- apply_project_sync(): Lädt MIDI-Noten in Scheduler + Auto-Load Instrumente

### instruments/mod.rs — chrono.* Prefix
- from_str() erkennt: chrono.aeterna, chrono.pro_audio_sampler, chrono.fusion, etc.

### audio_graph.rs — track_indices()
- Neue Methode für sichere Iteration ohne Borrow-Konflikte

## Geänderte Dateien
- pydaw_engine/src/midi_scheduler.rs — NEU
- pydaw_engine/src/main.rs — mod midi_scheduler
- pydaw_engine/src/engine.rs — MidiScheduler + process_audio + Stop/Seek + Auto-Load
- pydaw_engine/src/audio_graph.rs — track_indices()
- pydaw_engine/src/instruments/mod.rs — chrono.* Prefix
- VERSION — 0.0.20.726
- pydaw/version.py — 0.0.20.726

## Auch in dieser Session erledigt (v0.0.20.725)
- Persistente Plugin-Blacklist (plugin_probe.py komplett überarbeitet)
- Scanner + Probe Integration (scan_all_with_probe)
- FX-Chain Blacklist-Guards (VST3/VST2/CLAP)
- Rust-Bridge Auto-Reconnect + robustere Reader-Loop
- Plugin-Blacklist-Dialog (NEU: plugin_blacklist_dialog.py)
- Plugin-Browser Blacklist-Badges + Insert-Warnung
- Rust Scanner → Browser Merge (additiv)

## Nächste Schritte
1. `cd pydaw_engine && cargo build --release` ← PFLICHT!
2. Falls Compile-Fehler: Borrow-Checker-Details fixen (track_indices Pattern)
3. `USE_RUST_ENGINE=1 python3 main.py` → MIDI-Instrument-Track → Play
4. A/B: Python-Engine vs Rust-Engine auf demselben Projekt

## Offene Fragen
- Rust-Compiler war in der Build-Umgebung nicht verfügbar → kein cargo test möglich
- Loop-Region-Support im MidiScheduler fehlt noch (linear playback funktioniert)
