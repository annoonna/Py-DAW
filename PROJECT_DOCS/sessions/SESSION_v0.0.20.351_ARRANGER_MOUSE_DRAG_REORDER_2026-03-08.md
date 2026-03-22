# Session v0.0.20.351 — Arranger Maus-Drag-Reorder

Datum: 2026-03-08
Bearbeitung: GPT-5

## Aufgabe
Sicheres **Track-Reorder per Maus-Drag** im linken Arranger-Bereich ergänzen, ohne den bestehenden **Cross-Project-Track-Drag** kaputt zu machen.

## Umsetzung
- `ArrangerTrackListWidget` eingeführt, das nur **same-widget Drops** mit einem zusätzlichen internen Reorder-MIME behandelt.
- Bestehendes Cross-Project-MIME bleibt unverändert erhalten.
- `TrackList._start_drag()` erweitert, sodass derselbe Drag sowohl Cross-Project- als auch Local-Reorder-Daten trägt.
- `ProjectService.move_tracks_block()` und `AltProjectService.move_tracks_block()` ergänzt, damit ausgewählte Nicht-Master-Spuren als Block verschoben werden.

## Sicherheit
- Kein Eingriff in Routing, Mixer, DSP, Playback oder Clip-Daten.
- Master bleibt weiterhin am Ende.
- Vorhandene Kontextmenüs und ▲/▼-Buttons bleiben erhalten.

## Prüfung
- `python -m py_compile pydaw/ui/arranger.py pydaw/services/project_service.py pydaw/services/altproject_service.py`

## Ergebnis
Der linke Arranger-Bereich unterstützt jetzt sicheres **Maus-Drag-Reorder** für sichtbare Track-Zeilen.
