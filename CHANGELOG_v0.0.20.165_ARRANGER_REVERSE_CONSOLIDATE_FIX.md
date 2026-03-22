# Changelog v0.0.20.165 — Arranger Reverse + Consolidate Fixes

## ✅ Fixes

### Arranger: Ctrl+J (Audio) funktioniert jetzt wirklich
- `ArrangerCanvas` delegiert Ctrl+J an den zentralen `ArrangerKeyboardHandler._join_clips()`.
- Damit greifen alle Checks/Implementierungen aus v0.0.20.164 (Audio-Bounce-Consolidate) zuverlässig.

### Arranger Kontextmenü: Multi-Selection bleibt erhalten
- Rechtsklick auf einen **bereits selektierten** Clip behält die Mehrfachauswahl.
- Nur Rechtsklick auf einen **nicht selektierten** Clip setzt die Auswahl auf diesen Clip.

### Audio Editor: Reverse ohne Event-Selektion
- Wenn keine Event-Auswahl existiert (z.B. Rechtsklick im Hintergrund), toggelt „Reverse“ jetzt automatisch den **Clip-Reverse**.
- Per-Event Reverse bleibt unverändert, sobald Events selektiert sind.

## ✨ Features

### Arranger Kontextmenü: Reverse (Clip-Level)
- Audio-Clips können im Arranger per Rechtsklick **Reverse** toggeln.
- Reverse-Zustand ist im Arranger sichtbar (Waveform wird gespiegelt + Overlay/Tag).

### Arranger Kontextmenü: Consolidate (Originale behalten)
- Zusätzlich zu Ctrl+J/Consolidate gibt es einen Menüpunkt **„Consolidate (Originale behalten)“**.
- Erstellt den konsolidierten Clip, lässt aber die Original-Clips stehen.

## Dateien
- `pydaw/ui/arranger_canvas.py`
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
