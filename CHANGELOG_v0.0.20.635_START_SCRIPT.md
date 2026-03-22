# CHANGELOG v0.0.20.635 — Start-Skript (Ein-Klick DAW-Start)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6

## Was wurde gemacht

### `start_daw.sh` — Ein Befehl startet alles
- Erkennt automatisch ob Rust-Engine gebaut ist → aktiviert sie
- Aktiviert das Python venv automatisch
- Startet die Rust-Engine im Hintergrund (falls vorhanden)
- Wartet bis der Socket bereit ist
- Startet die DAW
- Beim Beenden: räumt Rust-Engine + Socket automatisch auf
- Fallback: Wenn Rust nicht verfügbar → Python-Engine wie gewohnt

## Benutzung

```bash
./start_daw.sh
```

Das war's. Keine Environment-Variablen, kein venv-Aktivieren, kein Nachdenken.
