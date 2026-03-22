# Session v0.0.20.280 — AETERNA MSEG Snap/Quantize/Smooth

## Ziel
Den lokalen AETERNA-MSEG-Editor in einem sicheren Schritt erweitern: Snap/Quantize, kleine Kurven-Glättung und bestehende Stretch/Compress-Verdrahtung vollständig lokal fertigstellen.

## Umgesetzt
- Lokales **Snap X** für MSEG-Punkte mit Grid-Auswahl (4/8/16/32)
- Lokales **Quantize Y** mit Stufen-Auswahl (3/5/9/17)
- Lokales **Smooth** für MSEG-Kurven (ein sicherer Glättungsdurchlauf)
- Bereits sichtbare **Stretch/Compress**-Buttons jetzt vollständig im Handler verdrahtet
- Snap/Quantize-Auswahl wird pro Track-State mitgespeichert

## Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_engine.py` geändert
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` geändert
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer oder globalem Audio-/Playback-Core

## Tests
- `python -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Direkter Engine-Smoke-Test für:
  - `stretch_mseg()`
  - `compress_mseg()`
  - `snap_mseg_x()`
  - `quantize_mseg_y()`
  - `smooth_mseg()`
