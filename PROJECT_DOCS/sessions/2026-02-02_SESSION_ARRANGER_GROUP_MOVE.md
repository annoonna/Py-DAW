# Session 2026-02-02 — Arranger: Lasso + Group-Move (Multi-Clip Drag)

## Ziel
- Wenn mehrere Clips per Lasso/Mehrfachauswahl markiert sind, sollen sie **gemeinsam** verschoben werden, sobald man einen der markierten Clips zieht.
- Snap soll DAW-typisch funktionieren: **Anker-Clip** snapped, alle anderen behalten ihren relativen Abstand.

## Umsetzung
- ArrangerCanvas: neue Struktur `_DragMoveMulti`.
- MousePress: Wenn auf markierten Clip geklickt wird und `len(selected) > 1`, startet Multi-Drag (Anchor = geklickter Clip).
- MouseMove: berechnet Delta in Beats über Anchor, wendet es auf alle selektierten Clips an.
- Optionales Track-Move: vertikales Drag erzeugt `track_index_delta` und verschiebt alle Clips entsprechend (geclamped).
- MouseRelease: reset der Multi-Drag-State.

## Ergebnis
- Lasso/Mehrfachauswahl + Drag bewegt alle markierten Clips gemeinsam.
- Keine Syntax/Indentation-Regression.

## Dateien
- `pydaw/ui/arranger_canvas.py`

