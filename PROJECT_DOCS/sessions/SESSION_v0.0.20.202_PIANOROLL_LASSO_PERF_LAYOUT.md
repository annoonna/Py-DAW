# Session v0.0.20.202 — PianoRoll: Lasso-Fix, Performance, Layout (Safe)

Datum: 2026-03-03

## Ziel
- Piano-Roll muss wieder **flüssig bedienbar** sein: Notes direkt greifen/ziehen, Multi-Select per Lasso.
- UI darf nicht träge wirken (Repaints reduzieren).
- Expression Lane darf **keinen Platz klauen**, wenn Expressions OFF.

## Änderungen
### 1) PianoRollCanvas: Lasso Selection für Noten repariert
- Drag auf leerer Fläche erzeugt Selection-Rect.
- Release selektiert Notes per `QRectF.intersects()`.
- Shift+Lasso additiv.

### 2) Performance: Background/Grid Cache (QPixmap)
- Hintergrund + Pitch-/Beat-Grid wird gecached.
- Repaint bei Drag/Move zeichnet nur Notes/Overlays.

### 3) Performance: Note-Glow nur noch für selektierte Notes
- Unselektierte Notes ohne mehrfaches Glow-FillPath.

### 4) Layout: Expression Lane kollabiert wirklich bei OFF
- Lane-Row Mindesthöhe wird dynamisch 0/120 gesetzt.
- Kein FixedHeight-Spacer mehr, der leere Fläche produziert.

### 5) Layout: Ghost Layers Panel bleibt kompakt
- MaxHeight reduziert + Stretch so, dass PianoRoll den Platz behält.

## Dateien
- `pydaw/ui/pianoroll_canvas.py`
- `pydaw/ui/pianoroll_editor.py`
- `VERSION`, `pydaw/version.py`

## Tests (manuell)
- Notes greifen/ziehen ohne „falsche Note selektiert“
- Lasso: mehrere Notes selektieren, danach gruppiert verschieben
- Expressions OFF: Lane-Bereich verschwindet (kein leerer Block)
- Dragging fühlt sich deutlich flüssiger an
