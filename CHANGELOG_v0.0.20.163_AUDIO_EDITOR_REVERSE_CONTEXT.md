# Changelog v0.0.20.163 — Audio Editor: Reverse nur auf selektierte/geklickte Events

**Datum:** 2026-03-01

## Fix

- **Reverse im Audio Editor** wirkt jetzt nur noch auf die aktuelle Auswahl (oder das geklickte Event).
- **Kein Global-Toggle mehr:** Wenn nichts selektiert ist, wird nicht mehr „alle Events im Clip“ umgekehrt.
- **DAW-Style:** Rechtsklick auf ein nicht selektiertes Event selektiert automatisch dieses Event vor dem Öffnen des Kontextmenüs.
- Menüpunkt **Reverse** ist disabled, wenn wirklich keine Auswahl existiert.

## Dateien

- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`
