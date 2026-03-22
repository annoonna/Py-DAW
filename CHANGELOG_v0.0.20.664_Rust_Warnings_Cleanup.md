# CHANGELOG v0.0.20.664 — Rust Engine Warnings Cleanup

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP1 — Rust Audio-Core (Post-Build Cleanup)

## Was wurde gemacht

### Rust Engine: 61 Compiler-Warnings beseitigt

Nach erfolgreichem `cargo build --release` (0 Errors, 61 Warnings) wurden alle
Warnings systematisch behoben:

1. **`#![allow(dead_code)]` Crate-weit** (main.rs)
   - Eliminiert ~49 dead_code Warnings von Stub-Modulen (Phase 1C FFI nicht aktiv)
   - VST3/CLAP Host, Plugin Isolator, Audio Nodes — alles absichtlich vorbereiteter Code

2. **12 Unused-Import-Fixes** (die `cargo fix` Suggestions):
   - `vst3_host.rs`: Entfernt `c_void`, `CStr`, `OsStr`, `Arc`, `RwLock`, `error`, `warn`
   - `clap_host.rs`: Entfernt `error`, `warn`
   - `plugin_isolator.rs`: Entfernt `TrySendError`, `Instant`
   - `clip_renderer.rs`: Entfernt `use std::convert::TryInto` (Rust 2021 Prelude)

3. **Unused Constant entfernt**:
   - `clip_renderer.rs`: `TABLE` Konstante in `base64_decode()` war definiert aber nie referenziert

### Ergebnis
- **Vorher:** 0 errors, 61 warnings (12 suggestions)
- **Nachher:** 0 errors, 0 warnings erwartet

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw_engine/src/main.rs | `#![allow(dead_code)]` hinzugefügt |
| pydaw_engine/src/vst3_host.rs | 7 unused imports entfernt |
| pydaw_engine/src/clap_host.rs | 2 unused imports entfernt |
| pydaw_engine/src/plugin_isolator.rs | 2 unused imports entfernt |
| pydaw_engine/src/clip_renderer.rs | TryInto import + TABLE const entfernt |
| VERSION | 663 → 664 |
| pydaw/version.py | 663 → 664 |

## Was als nächstes zu tun ist
- `cd pydaw_engine && cargo build --release` → 0 warnings bestätigen
- Optional: `cargo clippy` für weitergehende Rust-Lint-Empfehlungen
- EngineMigrationDialog öffnen → "Alle → Rust" → Benchmark laufen lassen

## Bekannte Probleme
- Keine — rein kosmetische Änderungen, keine Verhaltensänderung
