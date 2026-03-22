# Session v0.0.20.279 — AETERNA MSEG Fine Edit + Stretch/Compress

## Ziel
Lokale AETERNA-MSEG-Bearbeitung sinnvoll erweitern, ohne Arranger, Audio-Editor, Clip-Launcher, Mixer oder Playback-Core anzufassen.

## Umgesetzt
- Selektierter MSEG-Punkt kann jetzt über **X/Y-Felder** direkt numerisch gesetzt werden
- **Punkt-Nudges** für X/Y direkt im AETERNA-Widget
- Neue lokale Zeitachsen-Operationen:
  - **Stretch**
  - **Compress**
- Auswahl-Sync zwischen großer Preview und Punkteditor
- Alles bleibt lokal im AETERNA-Track-State gespeichert

## Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_engine.py` geändert
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` geändert
- Keine Core-Änderungen

## Tests
- `python -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Direkter Engine-Smoke-Test für:
  - `stretch_mseg()`
  - `compress_mseg()`
  - Punkt-Update via `set_mseg_points()`
  - `get_mod_preview_data("mseg")`
