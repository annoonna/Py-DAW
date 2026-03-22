# CHANGELOG v0.0.20.707 — Rust Project Sync (RA1)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust Audio Pipeline, Phase RA1

## Was wurde gemacht

### RA1 — Project State Sync (Python → Rust)
- `pydaw/services/rust_project_sync.py` (**NEU**):
  - `serialize_project_sync(project)`: Konvertiert Python Project → Rust ProjectSync dict
    - Tracks: ID, Index, Kind, Volume, Pan, Mute, Solo, Group-Routing
    - Clips: Position, Länge, Kind, Gain, Offset (Launcher-only + muted gefiltert)
    - MIDI-Noten: Pitch, Velocity, Start, Länge (aus project.midi_notes)
    - Automation: Breakpoints pro Track/Parameter (aus automation_manager_lanes)
    - Transport: BPM, Time Signature, Loop-Region, Sample Rate
  - `RustProjectSyncer` Klasse:
    - `sync()` → Serialisiert + sendet SyncProject IPC-Command
    - `on_play()` → sync() + bridge.play()
    - `on_stop()` → bridge.stop()
    - `on_seek(beat)` → bridge.seek()
    - `on_tempo_changed(bpm)` → bridge.set_tempo()
    - `on_loop_changed(enabled, start, end)` → bridge.set_loop()
    - `on_track_param_changed(idx, param, val)` → bridge.set_track_param()

### JSON-Format
- Matches Rust `audio_bridge::ProjectSync` struct exakt
- Compact JSON (separators=(",",":")) für minimale IPC-Latenz
- sync_seq Counter für Delta-Detection

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/rust_project_sync.py | **NEU**: Serializer + Syncer |
| VERSION | 0.0.20.707 |
| pydaw/version.py | 0.0.20.707 |

## Was als nächstes zu tun ist
- RA1 Rust-seitig: AudioGraph Rebuild aus ProjectSync (Tracks, Clips, MIDI)
- RA2: Sample-Daten an Rust senden (WAV Base64)
- RA3: Rust übernimmt Audio-Device
