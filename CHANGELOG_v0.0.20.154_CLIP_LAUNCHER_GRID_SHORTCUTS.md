# Py_DAW v0.0.20.154 – Clip Launcher Grid: DAW Shortcuts + Ctrl-Drag Duplicate

## Highlights
- **Grid-Shortcuts** direkt im Clip Launcher:
  - Ctrl+C / Ctrl+X / Ctrl+V
  - Delete / Backspace
  - Ctrl+D (Duplicate nach rechts)
  - Esc (Deselect)
- **Ctrl+Drag** zwischen Slots erzeugt **eine echte Clip-Kopie** (nicht nur Slot-Link).

## Technisch
- UI-only Slot-Selection (subtile Markierung in Slot-Zelle)
- ProjectService neu: `clone_clip_for_launcher()` (deep copy inkl. Audio/MIDI Inhalte + Launcher-Properties)

## Sicherheit
- Keine Änderungen an Audio-Engine / DSP
- Bestehende Alt+Drag Funktion bleibt erhalten
