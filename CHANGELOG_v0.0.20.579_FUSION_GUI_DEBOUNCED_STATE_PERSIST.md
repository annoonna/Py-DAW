# Changelog v0.0.20.579 — Fusion GUI Hotfix: debounced State Persist

## Fix

- Fusion schreibt den kompletten Instrument-State bei schnellen Knob-/MIDI-Updates nicht mehr bei jedem Tick sofort ins Projekt.
- Ein Fusion-only `QTimer` coalesct die Persistenz jetzt auf einen einzelnen Write nach kurzer Ruhezeit.
- Engine-Parameter reagieren weiterhin sofort; nur der teure Projekt-/UI-Update-Pfad wurde entschärft.
- `shutdown()` flusht einen offenen Persist-Timer sicher, damit keine letzten Änderungen verloren gehen.

## Wirkung

- Weniger GUI-Freeze bei Fusion unter MIDI-CC-Last
- Kein Eingriff in Bach Orgel oder andere Instrumente
