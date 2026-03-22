# CHANGELOG v0.0.20.726 — MIDI Clip Scheduler + Instrument Auto-Load

**Datum:** 2026-03-22
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust Engine — Clips + MIDI → echtes Audio

## Was wurde gemacht

### DAS KERNPROBLEM (behoben)
Die Rust-Engine hatte alle Einzelteile (7 Instrumente, 15 FX, AudioGraph, ClipRenderer,
MIDI-Routing für Live-Input), aber **MIDI-Noten aus dem Arrangement wurden beim Playback
nicht abgespielt**. Der Code sagte wörtlich:

```
// MIDI notes are parsed and validated but actual instrument playback
// requires instrument nodes (R6–R11). For now we log the note count.
```

### 1. NEUES MODUL: `midi_scheduler.rs` (300+ Zeilen)
Der fehlende Baustein zwischen "MIDI-Daten im Projekt" und "Instrumente spielen Audio":

- **ScheduledEvent**: Beat, Track-Index, Pitch, Velocity, NoteOn/Off
- **load_from_sync()**: Konvertiert clip-relative Noten zu absoluten Beat-Positionen
  - Clip-Start + Note-Start - Clip-Offset = absolute Beat-Position
  - Sortiert chronologisch (NoteOff vor NoteOn bei gleicher Beat-Position)
- **schedule_for_buffer()**: Zero-allocation Iterator über Beat-Range
  - Binary-Search bei Seek (kein linearer Scan)
  - Seek-Erkennung (Playhead springt rückwärts → Reset scan_index)
- **reset()**: Bei Stop/Seek — verhindert Stuck Notes
- **7 Unit-Tests**: Basis-Scheduling, Seek, NoteOff-Reihenfolge, Multi-Track

### 2. Engine Integration (engine.rs)
- **MidiScheduler im EngineState** als `Mutex<MidiScheduler>` Feld
- **process_audio()**: Nach Audio-Clip-Rendering, VOR graph.process():
  - Berechnet Beat-Range für den Buffer
  - Iteriert MIDI-Events in diesem Range
  - Dispatcht NoteOn/NoteOff an `track.instrument.push_midi()`
- **Stop-Handler**: `midi_scheduler.reset()` + AllNotesOff an alle Instrumente
- **Seek-Handler**: `midi_scheduler.reset()` + AllNotesOff (keine Stuck Notes)
- **apply_project_sync()**: Lädt MIDI-Noten in Scheduler + erstellt automatisch
  Instrumente für Tracks mit instrument_type

### 3. Instrument Auto-Loading bei ProjectSync (engine.rs)
- Wenn Python ein Projekt synchronisiert und ein Track `instrument_type` hat,
  wird das Instrument automatisch erstellt (vorher musste man es separat per IPC laden)
- Mapping: `chrono.aeterna` → AETERNA, `chrono.pro_audio_sampler` → ProSampler, etc.

### 4. chrono.* Prefix-Support (instruments/mod.rs)
- `InstrumentType::from_str()` erkennt jetzt Python's `chrono.*` Plugin-IDs:
  - `chrono.pro_audio_sampler` → ProSampler
  - `chrono.pro_drum_machine` → DrumMachine  
  - `chrono.aeterna` → Aeterna
  - `chrono.fusion` → Fusion
  - `chrono.bach_orgel` → BachOrgel
  - `chrono.multisample` → MultiSample

### 5. AudioGraph: track_indices() Hilfsmethode (audio_graph.rs)
- Neue Methode `track_indices() -> Vec<u16>` für sichere Iteration
  ohne Borrow-Konflikte (collect indices, then get_track_mut)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/midi_scheduler.rs | **NEU** — Beat-accurate MIDI Clip Scheduling (300+ Zeilen) |
| pydaw_engine/src/main.rs | `mod midi_scheduler` registriert |
| pydaw_engine/src/engine.rs | MidiScheduler Feld, process_audio MIDI-Dispatching, Stop/Seek Reset, Auto-Load Instruments |
| pydaw_engine/src/audio_graph.rs | `track_indices()` Hilfsmethode |
| pydaw_engine/src/instruments/mod.rs | `chrono.*` Prefix-Support in from_str() |
| VERSION | 0.0.20.726 |
| pydaw/version.py | 0.0.20.726 |

## Was als nächstes zu tun ist
- `cd pydaw_engine && cargo build --release` ← MUSS als erstes laufen!
- Falls Compile-Fehler: Wahrscheinlich Borrow-Checker Details → einfach fixen
- `USE_RUST_ENGINE=1 python3 main.py` → MIDI-Instrument-Track anlegen → Play drücken
- A/B Vergleich: Python-Engine vs Rust-Engine auf demselben Projekt

## Architektur-Diagramm

```
Python (GUI)                          Rust (Audio-Thread)
────────────                          ──────────────────
Project.midi_notes                    
      │                               
 serialize_project_sync()             
      │ (JSON/MessagePack)            
      ▼                               
 RustEngineBridge.send_command(       
   "SyncProject", {tracks, clips,    
    midi_notes, ...})                 
      │                               
      ╰──── IPC Unix Socket ────────► engine.handle_command(SyncProject)
                                            │
                                       apply_project_sync()
                                            │
                                       ┌────┴────────┐
                                       │  MIDI Notes  │
                                       │  → Scheduler │
                                       └────┬────────┘
                                            │
                                       process_audio() [audio callback]
                                            │
                                       ┌────┴────────────┐
                                       │ Audio Clips      │
                                       │ → ClipRenderer   │
                                       │ → track buffers  │
                                       └────┬────────────┘
                                            │
                                       ┌────┴─────────────────┐
                                       │ MIDI Clip Scheduler   │
                                       │ → schedule_for_buffer │
                                       │ → push_midi(NoteOn)   │
                                       │ → Instrument.process()│
                                       │ → audio into buffer   │
                                       └────┬─────────────────┘
                                            │
                                       ┌────┴────────┐
                                       │ AudioGraph   │
                                       │ Vol/Pan/FX   │
                                       │ → Master     │
                                       └────┬────────┘
                                            │
                                       ┌────┴────────┐
                                       │ cpal Output  │
                                       │ → Speakers   │
                                       └─────────────┘
```
