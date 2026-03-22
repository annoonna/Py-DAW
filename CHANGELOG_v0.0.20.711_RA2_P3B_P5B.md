# CHANGELOG v0.0.20.711 — RA2 Instrument Sync + P3B/P5B Editor Scaffolding

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** RA2 (Extended Sample Sync), P3B (VST2 Editor), P5B (CLAP GUI)

## Was wurde gemacht

### RA2 Extended — Instrument Sample Sync (Python-Seite) ✅
- **rust_sample_sync.py**: 4 neue Sync-Methoden + `sync_all_instruments()`
  - `sync_drum_pads()`: DrumMachine Pad-Samples → Rust (pro Pad ein LoadAudioClip)
  - `sync_multisample_zones()`: MultiSample Zonen → Rust (LoadAudioClip + MapSampleZone IPC)
  - `sync_sf2()`: SoundFont-Pfad → Rust (LoadSF2 IPC, Rust lädt von Disk)
  - `sync_wavetable()`: Wavetable-Frames → Rust (LoadWavetable IPC, Base64-Concat aller Frames)
  - `sync_all_instruments()`: Scannt alle Tracks und synct automatisch nach Typ

### P3B — VST2 Editor im Worker (X11) ✅
- **vst2_worker.py**: `_vst2_show_editor()` + `_vst2_hide_editor()` Funktionen
  - libX11 via ctypes laden, XOpenDisplay, XCreateSimpleWindow
  - effEditGetRect (Opcode 13) für Fenstergröße
  - effEditOpen (Opcode 14) mit X11 Window Handle
  - effEditClose (Opcode 15) + XDestroyWindow cleanup
  - show_editor/hide_editor IPC Commands im Worker verdrahtet

### P5B — CLAP GUI im Worker (X11 Scaffolding) ✅
- **clap_worker.py**: Enhanced show_editor mit Dual-Strategie
  - Method 1: show_editor() High-Level Wrapper (wenn vorhanden)
  - Method 2: _clap_gui_create() mit X11 Window (wenn Methode existiert)
  - _clap_gui_destroy() bei hide_editor
  - editor_shown Event via IPC an Main-Prozess

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/rust_sample_sync.py | 4 neue Sync-Methoden + sync_all_instruments() |
| pydaw/plugin_workers/vst2_worker.py | VST2 Editor X11 Scaffolding (P3B) |
| pydaw/plugin_workers/clap_worker.py | CLAP GUI X11 Scaffolding (P5B) |
| pydaw_engine/src/engine.rs | (v710: apply_project_sync) |

## Was als nächstes zu tun ist
- `cargo build --release` + Live-Test
- P7 (OPTIONAL): Rust Native Plugin Hosting
- RA5: A/B Bounce Vergleich (benötigt Live-Projekt)
