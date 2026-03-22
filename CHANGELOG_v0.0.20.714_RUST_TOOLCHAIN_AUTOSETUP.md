# CHANGELOG v0.0.20.714 — Rust Toolchain Auto-Setup für Endanwender

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Developer Experience — Rust-Installation für normale Anwender

## Problem
Nach `rustup`-Installation ist `cargo` nicht im PATH der aktuellen Shell.
Anwender müssen manuell `source ~/.cargo/env` ausführen — das ist unzumutbar.
Außerdem fehlen System-Pakete (`libasound2-dev`, `pkg-config`) die für
`cargo build` nötig sind — der Build schlägt ohne Fehlererklärung fehl.

## Lösung

### start_daw.sh — Komplett überarbeitet ✅
- Sourct `~/.cargo/env` automatisch beim Start
- Fügt `~/.cargo/bin` zum PATH hinzu (Fallback)
- Erkennt Rust-Installation und zeigt Version an
- Fragt interaktiv ob Rust-Engine gebaut werden soll (wenn cargo da aber Binary fehlt)
- Prüft ALSA Dev-Headers vor Build-Versuch
- Zeigt klare Fehlermeldungen mit Lösungshinweisen

### setup_all.py — 3 neue Hilfsfunktionen ✅
- `_source_cargo_env()`: Setzt PATH + CARGO_HOME + RUSTUP_HOME in der Python-Session
  - Wird aufgerufen von: check_rust(), install_rust(), build_rust_engine()
  - Löst das "cargo not found after install" Problem komplett
- `_install_rust_system_deps()`: Auto-installiert via apt:
  - `libasound2-dev` (ALSA Headers für cpal Crate)
  - `pkg-config` (für viele Rust Crates)
  - `build-essential` (gcc/make für native compilation)
  - `curl` (für rustup download)
- `install_rust()` ruft jetzt `_install_rust_system_deps()` VOR rustup auf

### install.py — Bessere Hinweise ✅
- End-Message zeigt `./start_daw.sh` als empfohlenen Startbefehl
- Klarer Hinweis auf `python3 setup_all.py --with-rust` für Rust-Engine

### Cargo.toml — P7 Dependencies vorbereitet ✅
- `libloading`, `clap-sys`, `pkg-config` als kommentierte Dependencies

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| start_daw.sh | Komplett neu: cargo env, auto-build, Status |
| setup_all.py | _source_cargo_env, _install_rust_system_deps, check_rust fix |
| install.py | Bessere End-Messages |
| pydaw_engine/Cargo.toml | P7 dep comments |

## Anwender-Workflow jetzt (One-Command-Setup):
```bash
# Erstmalig:
python3 setup_all.py --with-rust
# → Installiert venv, Python deps, Rust, System deps, baut Engine

# Danach immer:
./start_daw.sh
# → Aktiviert venv, findet cargo, fragt ob Build nötig, startet DAW
```
