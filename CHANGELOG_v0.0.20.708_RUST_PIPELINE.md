# CHANGELOG v0.0.20.708 — Rust Audio Pipeline RA2-RA5

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust Audio Pipeline, Phase RA2+RA3+RA4+RA5

## Was wurde gemacht

### RA2 — Sample Data Transfer
- `rust_sample_sync.py`: RustSampleSyncer — WAV/FLAC→f32 Base64→LoadAudioClip
- Chunked Transfer >50MB, _file_hash Change-Detection Cache
- SetArrangement Clip-Platzierungen, sync_clip() Einzelclip
- on_play() synct automatisch Project + Samples

### RA3 — Audio Device Takeover
- `rust_audio_takeover.py`: RustAudioTakeover
- activate(): Stop Python → Start Rust → Wire Events → Sync
- deactivate(): Stop Rust → Restart Python
- Event Wiring: Playhead/Meters/Transport → Qt Callbacks
- Settings aus QSettings, Fallback bei Rust-Fehler

### RA4 — Hybrid Mode
- `rust_hybrid_engine.py`: RustHybridEngine
- assign_tracks(): Per-Track Rust/Python via can_track_use_rust()
- EngineMode.HYBRID: Rust für Built-in, Python für externe Plugins
- get_track_badge(): "R"/"P" Badge API für Track-Header UI

### RA5 — Full Rust Mode
- EngineMode Enum: Python | Hybrid | Rust
- QSettings: audio/engine_mode persistent
- Auto-Downgrade: Rust→Hybrid wenn Tracks Python brauchen
- run_ab_test() Placeholder für A/B Bounce-Vergleich
- Fallback Chain: Rust→Hybrid→Python bei Fehler

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/rust_sample_sync.py | **NEU**: RA2 Sample Transfer |
| pydaw/services/rust_audio_takeover.py | **NEU**: RA3 Device Takeover |
| pydaw/services/rust_hybrid_engine.py | **NEU**: RA4+RA5 Hybrid+Full Rust |
| pydaw/services/rust_project_sync.py | Sample-Sync Integration |
| pydaw/core/settings.py | audio_engine_mode SettingsKey |
| VERSION | 0.0.20.708 |
| pydaw/version.py | 0.0.20.708 |

## Was als nächstes zu tun ist
1. `cd pydaw_engine && cargo build --release` → Rust Binary kompilieren
2. Live-Test: Py_DAW starten → Audio → Engine Mode → Rust/Hybrid
3. A/B Bounce: Python-Bounce vs Rust-Bounce auf echtem Projekt
4. Optional: P7 Rust Native Plugin Hosting (langfristig)
