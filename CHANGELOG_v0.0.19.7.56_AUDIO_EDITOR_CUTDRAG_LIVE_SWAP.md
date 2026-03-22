# Changelog v0.0.19.7.56 — AudioEventEditor Cut+Drag + Live Playback Swap

**Datum:** 2026-02-06

## Fixes
- Fix: `AudioEditorView.mousePressEvent` hatte einen fehlenden Zeilenumbruch (SyntaxError) und konnte den Start abbrechen.

## AudioEventEditor
- Knife Cut+Drag:
  - View emittiert `request_slice_drag(at_beats, press_scene_x)` bei Linksklick.
  - Während des Ziehens kommen `knife_drag_update(scene_x, modifiers_int)` Events.
  - Beim Loslassen kommt `knife_drag_end()` und das Group-Move wird committed.
- Selection-Policy nach Split: Es wird nur die rechte(n) Hälfte(n) selektiert (R-Regel).
- Kontextmenü „Split at Playhead“ nutzt dieselbe R-Regel.

## ClipLauncher Playback
- Live-Edit Support: Bei `project_updated` wird eine neue Voice-Map vorbereitet.
- Swap wird block-genau im Audio-Pull ausgeführt und mit kurzem Crossfade (default: 96 Frames) geblendet, um Klicks zu vermeiden.

## Geänderte Dateien
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/services/cliplauncher_playback.py`
- `VERSION`, `pydaw/version.py`, `CHANGELOG.md`
