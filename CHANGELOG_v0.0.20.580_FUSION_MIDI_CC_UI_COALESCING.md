# Changelog v0.0.20.580 — Fusion MIDI-CC UI Coalescing (~60 Hz)

## Fix

- Fusion-Knobs puffern eingehende MIDI-CC-Werte jetzt lokal im `FusionWidget` und flushen sie ueber einen Fusion-only `QTimer` mit 16 ms Intervall.
- Pro Knob wird nur noch der letzte CC-Wert pro UI-Frame angewendet statt jeder einzelne Roh-Tick.
- Dynamische OSC/FLT/ENV-Extra-Knobs droppen beim Rebuild offene Queue-Eintraege alter Widgets.
- `shutdown()` flusht ausstehende CC-Werte vor dem restlichen Cleanup.

## Wirkung

- Weniger GUI-Freeze bei Fusion unter MIDI-CC-Last
- Kein Eingriff in Bach Orgel oder andere Instrumente
