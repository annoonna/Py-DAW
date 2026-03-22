# CHANGELOG v0.0.20.713 — P7C LV2 Host Scaffolding + Cargo.toml P7 Prep

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** P7C (LV2 Rust Host) + P7 Infrastruktur

## Was wurde gemacht

### P7C — LV2 Plugin Host in Rust (Scaffolding) ✅
- **lv2_host.rs** (NEU, 440 Zeilen): Vollständige FFI-Architektur
  - `Lv2PluginInfo`: URI, Name, Author, Ports, Features, Bundle Path
  - `Lv2PortKind`: AudioInput/Output, ControlInput/Output, AtomInput/Output, CV
  - `Lv2PortInfo`: Index, Symbol, Name, Default/Min/Max, Flags
  - `Lv2Instance`: Full AudioPlugin impl (initialize, start/stop, control ports)
  - `UridMap`: Thread-safe URI↔Integer Map mit 12 pre-registered LV2 URIs
  - Scanner: `scan_lv2_plugins()` + `lv2_search_paths()` (Linux standard dirs)
  - Bundle Probing: manifest.ttl check
  - All FFI callsites mit `// TODO (P7C FFI):` markiert für einfaches Auffinden
- **main.rs**: `mod lv2_host;` hinzugefügt

### Cargo.toml — P7 Dependency Preparation
- libloading, clap-sys, pkg-config als kommentierte Dependencies
- Nächster Kollege: uncomment + `cargo build` → sofort nutzbar

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/lv2_host.rs | **NEU** — LV2 Host FFI Scaffolding |
| pydaw_engine/src/main.rs | `mod lv2_host;` |
| pydaw_engine/Cargo.toml | P7 dependency comments |

## Statistik
- 59 Rust-Dateien, 24.437 Zeilen (+545 vs v712)
- 303 Python-Dateien, alle kompilieren fehlerfrei
- Smoke Test: ✅ ALL CHECKS PASSED
