# Session v0.0.20.286 — AETERNA MSEG Fine Tools

Datum: 2026-03-06

## Gemacht
- Range Clamp für lokale MSEG-Kurven ergänzt.
- Deadband für lokale MSEG-Kurven ergänzt.
- Micro-Smooth für lokale MSEG-Kurven ergänzt.
- Lokale Toolbar-Controls für Tilt/Skew/Copy/Paste/Slots im AETERNA-Widget sichtbar gemacht und mit Persistenz verdrahtet.

## Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_engine.py` und `pydaw/plugins/aeterna/aeterna_widget.py` geändert.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer oder globalem Playback-Core.

## Checks
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Engine-Smoke-Test für `range_clamp_mseg()`, `deadband_mseg()`, `micro_smooth_mseg()`
