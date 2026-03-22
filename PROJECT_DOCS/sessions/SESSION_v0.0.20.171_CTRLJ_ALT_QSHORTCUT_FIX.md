# SESSION v0.0.20.171 — Ctrl+J Varianten Fix (Alt-Mod) + PyQt6 QShortcut Import

## Summary
Fixes two regressions that broke Ctrl+J variants in the Audio-Editor and prevented startup in some PyQt6 builds.

## Changes
- **Audio Editor:** `alt` modifier was missing in `handle_key_event()` → caused NameError and status "Zusammenführen fehlgeschlagen" for Ctrl+J variants.
- **PyQt6 Import:** `QShortcut` imported from `QtWidgets` caused ImportError → moved to `PyQt6.QtGui`.

## Files
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`

## Notes
No behavior changes to Consolidate modes. Ctrl+J remains bar-anchored default.
