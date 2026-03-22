# SESSION v0.0.20.271 — AETERNA Large Mod Preview (2026-03-06)

## Ziel
AETERNA lokal und sicher erweitern: größere Read-only Modulations-Preview direkt im Widget, ohne Eingriff in globalen DAW-Core, andere Instrumente oder Playback-Routing.

## Gemacht
- `pydaw/plugins/aeterna/aeterna_widget.py`
  - neues großes Preview-Panel `GROSSE MODULATIONS-PREVIEW`
  - Umschaltung zwischen `MSEG`, `LFO1`, `LFO2`, `Chaos`
  - Grid, Kurvenanzeige und laufende Phase-Markierung
  - Ansicht wird im Instrument-State mitgespeichert
- `pydaw/plugins/aeterna/aeterna_engine.py`
  - neue sichere Preview-Funktion `get_mod_preview_data(...)` für lokale UI-Darstellung
- `VERSION`, `pydaw/version.py`, `PROJECT_DOCS/sessions/LATEST.md`
  - auf `0.0.20.271` synchronisiert

## Safety
- keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer oder Hybrid-/Playback-Core
- nur AETERNA-Plugin-Dateien + Metadaten angepasst
- Preview ist bewusst Read-only und UI-lokal

## Tests
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py pydaw/plugins/aeterna/aeterna_engine.py`
- Engine-Smoke-Test für `get_mod_preview_data()` mit `mseg`, `lfo1`, `lfo2`, `chaos`, `off`

## Nächste sichere Schritte
- optionale Overlay-Darstellung von Web A / Web B auf der großen Preview
- optionale Punkt-/Segmentbearbeitung weiter nur lokal in AETERNA
