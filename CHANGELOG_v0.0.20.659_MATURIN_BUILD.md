# CHANGELOG v0.0.20.659 — maturin Build-Tool Integration

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Build-System / Rust-Bridge

## Was wurde gemacht

### maturin in alle Build-Dateien integriert

`maturin` ist das Standard-Tool um Rust-Code als Python-importierbares
Modul zu bauen (PyO3/pyo3-maturin). Es ersetzt den manuellen
`cargo build` + Socket-IPC Ansatz durch ein direkt importierbares
Python-Modul.

**requirements.txt:**
- `maturin>=1.5` als Dependency hinzugefügt

**install.py:**
- `pip install maturin` Schritt nach pedalboard
- Hinweis auf `cd pydaw_engine && maturin develop --release`

**setup_all.py:**
- `pip install maturin` in install_python_deps()
- `maturin develop --release` als zusätzlicher Build-Schritt nach `cargo build`
- maturin in `--check` Modus geprüft
- maturin in `run_checks()` System-Check
- Hinweis in Hilfe und Final-Report

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| requirements.txt | maturin>=1.5 hinzugefügt |
| install.py | pip install maturin + Hinweis |
| setup_all.py | maturin install, build, check, report |
| VERSION | 0.0.20.658 → 0.0.20.659 |
| pydaw/version.py | 0.0.20.658 → 0.0.20.659 |
