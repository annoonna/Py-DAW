# CHANGELOG v0.0.20.149 — Clip Launcher Bitwig Grid (2026-02-28)

## UI / Clip Launcher
- Grid-Orientierung auf Bitwig/Ableton-Style umgestellt:
  - Scenes als Spalten, Tracks als Zeilen
- Track-Header im Grid (Name + M/S/R)
- Slot-Zellen: Clip-Farb-Tint basierend auf `clip.launcher_color`
- ZELLE Inspector: Clip-Name-Zeile mit optionalem ▶ Preview

## Technisches
- Slot-Key-Format unverändert (`scene:<idx>:track:<track_id>`), daher keine Projektmigration nötig.
- Änderungen sind UI-first / safe, keine Audio-Engine-Änderung.

Geänderte Dateien:
- pydaw/ui/clip_launcher.py
- pydaw/ui/clip_launcher_inspector.py
- pydaw/version.py
