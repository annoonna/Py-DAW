# CHANGELOG v0.0.20.710 — P2B Param Sync + RA1 Rust AudioGraph Rebuild

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** P2B (VST GUI Integration) + RA1 (Rust-seitig AudioGraph)

## Was wurde gemacht

### P2B — VST3 Editor Param Polling in Worker ✅
- **vst3_worker.py**: Param-Poller-Thread aus `vst_gui_process.py` integriert
  - ~12Hz Polling wenn Editor offen, sendet `param_changed` Events via IPC
  - Preset-Switch Detection (Batch >10 Änderungen → State-Blob senden)
  - State-Hash-Check alle ~640ms als Backup-Detection
  - Thread startet bei `show_editor`, stoppt bei `hide_editor`
- **sandbox_process_manager.py**: `param_changed` Callback API
  - `set_param_changed_callback(cb)` → `cb(track_id, slot_id, param_id, value)`
  - Event-Handler für `param_changed` Events verdrahtet

### RA1 — Rust-seitig: AudioGraph Rebuild aus ProjectSync ✅
- **engine.rs**: `apply_project_sync()` Methode (110 Zeilen)
  - Transport: BPM, Time-Sig, Loop-Region aus Sync setzen
  - Tracks: AudioGraph-Tracks erstellen mit richtigen Parametern (Volume/Pan/Mute/Solo)
  - Group Routing: Kind-Tracks an Group-Bus-Tracks binden
  - Audio Clips: Base64 → ClipStore (PCM f32 Samples)
  - ArrangementSnapshot: Clip-Platzierungen mit Beat→Sample Konvertierung
  - MIDI Notes: Empfangen und geloggt (Instrument-Rendering via R6-R11)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/plugin_workers/vst3_worker.py | Param-Poller Thread (P2B) |
| pydaw/services/sandbox_process_manager.py | param_changed callback (P2B) |
| pydaw_engine/src/engine.rs | apply_project_sync() (RA1 Rust) |

## Was als nächstes zu tun ist
- `cargo build --release` → Rust Binary kompilieren und testen
- Live-Test: USE_RUST_ENGINE=1 python3 main.py
- P7 (OPTIONAL): Rust Native Plugin Hosting
