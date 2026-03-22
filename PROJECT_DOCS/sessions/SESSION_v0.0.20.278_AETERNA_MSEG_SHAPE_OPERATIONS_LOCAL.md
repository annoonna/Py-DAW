# SESSION v0.0.20.278 — AETERNA lokale MSEG-Shape-Operationen

Datum: 2026-03-06
Autor: GPT-5.4 Thinking

## Gemacht

- Große AETERNA-MSEG-Preview um lokale Shape-Werkzeuge `Invert`, `Mirror` und `Normalize` erweitert.
- Engine-Helfer für die drei Operationen ergänzt.
- Widget-Toolbar um drei sichere Buttons erweitert.
- Hinttext auf die neuen lokalen Werkzeuge angepasst.

## Sicherheit

- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer oder globalem Audio-/Playback-Core.
- Änderungen beschränken sich auf `pydaw/plugins/aeterna/aeterna_engine.py` und `pydaw/plugins/aeterna/aeterna_widget.py`.

## Tests

- `python -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Direkter Engine-Smoke-Test für `invert_mseg()`, `mirror_mseg()` und `normalize_mseg()`.
