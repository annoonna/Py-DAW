# CHANGELOG v0.0.20.660 — patchelf + Start-Skript venv Fix

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6

## Was wurde gemacht

### patchelf in alle Build-Dateien integriert
- `requirements.txt`: `patchelf>=0.17; platform_system=="Linux"`
- `install.py`: `pip install patchelf` Schritt
- `setup_all.py`: Install, --check, run_checks

### Start-Skripte: venv-Suche erweitert
- `start_daw.sh` + `start_dawGDB.sh`: Suchen jetzt in 3 Orten:
  1. `$VIRTUAL_ENV` (bereits aktiviertes venv — höchste Priorität)
  2. `$DIR/myenv/` (lokales venv im Projektordner)
  3. `$HOME/myenv/` (globales venv im Home-Verzeichnis)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| requirements.txt | patchelf hinzugefügt |
| install.py | pip install patchelf |
| setup_all.py | patchelf install + check |
| start_daw.sh | ~/myenv Fallback-Pfad |
| start_dawGDB.sh | ~/myenv Fallback-Pfad |
| VERSION | 0.0.20.659 → 0.0.20.660 |
| pydaw/version.py | 0.0.20.659 → 0.0.20.660 |
