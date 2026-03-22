# SESSION v0.0.20.274 — AETERNA Local MSEG Points

Datum: 2026-03-06
Autor: GPT-5.4 Thinking

## Ziel
Nächsten sicheren lokalen AETERNA-Schritt umsetzen: editierbare MSEG-Punkte direkt in der großen Modulations-Preview, ohne Arranger, Mixer, Audio Editor, Clip Launcher oder globalen Playback-Core anzufassen.

## Gemacht
- `pydaw/plugins/aeterna/aeterna_engine.py` erweitert um:
  - `DEFAULT_MSEG_POINTS`
  - `get_mseg_points()` / `set_mseg_points()` / `reset_mseg_points()`
  - sicheren Export/Import der MSEG-Punkte im Instrument-State
  - Nutzung der gespeicherten Punkte im internen MSEG-Modulationspfad
- `pydaw/plugins/aeterna/aeterna_widget.py` erweitert um:
  - lokale Punkt-Hitboxen in der großen Modulations-Preview
  - Drag-Bearbeitung der MSEG-Punkte im MSEG-Modus
  - `MSEG Reset`-Button
  - Persistenz-Hook beim Bearbeiten

## Sicherheit
- Nur AETERNA-Dateien geändert
- Keine Änderungen an globalem Audio-Core, Projekt-Service, Arranger, Clip Launcher, Audio Editor oder Mixer
- Endpunkte der MSEG bleiben sicher auf x=0.0 und x=1.0 fixiert
- Mittlere Punkte bleiben horizontal zwischen Nachbarn geklemmt

## Checks
- AST/Syntax-Parse erfolgreich für:
  - `pydaw/plugins/aeterna/aeterna_widget.py`
  - `pydaw/plugins/aeterna/aeterna_engine.py`
- Engine-Smoke-Test erfolgreich:
  - `set_mseg_points(...)`
  - `get_mseg_points()`
  - `get_mod_preview_data("mseg")`
  - Export/Import der Punkte über `export_state()` / `import_state()`

## Nächster sicherer Schritt
- Lokale MSEG-Punkte hinzufügen/löschen
- oder einfache Segmentformen/Interpolation nur innerhalb von AETERNA
