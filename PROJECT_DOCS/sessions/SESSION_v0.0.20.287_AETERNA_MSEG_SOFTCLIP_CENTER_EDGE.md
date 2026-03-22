# Session v0.0.20.287 — AETERNA MSEG Soft-Clip/Drive + Center/Edge Tools

## Datum
2026-03-06

## Scope
Nur lokaler AETERNA-MSEG-Ausbau. Keine Änderungen an Arranger, Audio Editor, Clip Launcher, Mixer oder globalem Playback-Core.

## Umgesetzt
- Soft-Clip/Drive für lokale MSEG-Kurven
- Center Flatten für kontrolliertes Abflachen um die Kurvenmitte
- Edge Boost für stärkere Ausprägung an den Kurvenrändern
- Persistenz der neuen UI-Auswahlwerte pro Track

## Geänderte Dateien
- `pydaw/plugins/aeterna/aeterna_engine.py`
- `pydaw/plugins/aeterna/aeterna_widget.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Verifikation
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- direkter Engine-Smoke-Test für `softclip_drive_mseg()`, `center_flatten_mseg()`, `edge_boost_mseg()` und `undo_mseg()`
