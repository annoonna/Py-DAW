# CHANGELOG v0.0.20.155 — Audio Editor: Arranger-Parity

**Datum:** 2026-02-28
**Typ:** Feature (UI-Enhancement)
**Risiko:** Niedrig (keine Engine-Änderungen, nur UI)

## Neue Features

### Ruler (AudioEditorRuler)
- Click-to-Seek: Klick auf Ruler setzt Playhead + Cursor
- Drag-to-Seek: LMB gedrückt halten = Playhead folgt Maus
- Ctrl+Wheel: Horizontaler Zoom
- Doppelklick: Zoom-to-Fit
- Playhead-Anzeige: Rote Linie + Dreieck-Marker
- Loop-Region: Grüne Shading mit "LOOP" Label
- Cursor-Linie: Blaue gestrichelte Linie (Paste-Position)

### Kontextmenü
- Copy (Ctrl+C), Cut (Ctrl+X), Paste (Ctrl+V)
- Delete (Del), Select All (Ctrl+A), Duplicate (Ctrl+D)

### Ctrl+Drag Copy
- Events per Ctrl+Maus auf andere Bar-Positionen kopieren
- 4px Threshold vor Duplikation (verhindert versehentliche Kopien)

### API
- `set_playhead_beat(beat)`: Playhead setzen (lightweight)
- `set_cursor_beat(beat)`: Cursor setzen (Paste-Ziel)

## Geänderte Datei
- `pydaw/ui/audio_editor/audio_event_editor.py` (+310 Zeilen)
