# CHANGELOG v0.0.20.712 — Rust IPC Commands + Engine Handlers (RA2 Rust-Side)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** RA2 Rust-seitig (LoadSF2, LoadWavetable, MapSampleZone)

## Was wurde gemacht

### Rust IPC — 3 neue Commands ✅
- **ipc.rs**: `LoadSF2 { track_id, sf2_path, bank, preset }`
  - SoundFont-Pfad an Rust (Rust lädt direkt von Disk)
- **ipc.rs**: `LoadWavetable { track_id, table_name, frame_size, num_frames, data_b64 }`
  - Wavetable-Frames als Base64-f32 LE concat
- **ipc.rs**: `MapSampleZone { track_id, clip_id, key_lo, key_hi, vel_lo, vel_hi, root_key, rr_group }`
  - Bindet pre-loaded Clips aus ClipStore an Multisample-Zonen

### Rust Engine — 3 neue Command Handler ✅
- **engine.rs**: `Command::LoadSF2` → Log + Platzhalter für FluidSynth FFI (R11B)
- **engine.rs**: `Command::LoadWavetable` → Base64 Decode, Größenvalidierung, Platzhalter für R9
- **engine.rs**: `Command::MapSampleZone` → ClipStore Lookup, Platzhalter für R6B Zone-Mapping

### Rust Infra
- **clip_renderer.rs**: `base64_decode()` von `fn` auf `pub fn` (für Wiederverwendung in engine.rs)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/ipc.rs | 3 neue Commands (LoadSF2, LoadWavetable, MapSampleZone) |
| pydaw_engine/src/engine.rs | 3 neue Handler + apply_project_sync RA1 Fix |
| pydaw_engine/src/clip_renderer.rs | base64_decode → pub fn |

## Was als nächstes zu tun ist
- `cargo build --release` → kompilieren und testen
- P7 (OPTIONAL): Rust Native Plugin Hosting (vst3-sys, clack-host)
- RA5: A/B Bounce Test (braucht Live-Projekt)
