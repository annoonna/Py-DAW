# SESSION v0.0.20.97 — 2026-02-17

## Ziel
Der Ruler-Zoom darf nicht nur in der linken Ecke funktionieren.
Er soll sich wie in professionellen DAWs anfühlen (Lupe überall erreichbar, Cursorwechsel zur Lupe, Zoom am Maus-Anker stabil), auch wenn man weit nach rechts gescrollt ist (Bar 29 / 97 / 500 …).

## Umsetzung (1 Task)
### ✅ Arranger-Ruler: „Lupe überall“
- Oberes Lineal-Band ist jetzt ein dedizierter **Zoom-Bereich**.
- Die **Lupe (Icon)** folgt der **Maus-X Position** (nicht mehr fest links).
- Der Mauszeiger wechselt im Zoom-Band zu einer **Lupe** (für Discoverability).
- Beim Zoomen bleibt der **Beat unter dem Cursor stabil** (Scroll-Anker wird nachgeführt).
- **Loop-Editing** bleibt weiterhin nutzbar im **unteren** Bereich des Rulers.

## Geänderte Dateien
- `pydaw/ui/arranger_canvas.py`

## Manuelle Tests (Checkliste)
1) Starten (Linux):
   - empfohlen: `pw-jack python3 main.py`
2) Arranger öffnen und **horizontal** weit nach rechts scrollen (z.B. Bar 97).
3) Maus oben im Lineal bewegen:
   - Cursor wird zur **Lupe**
   - Lupe-Icon erscheint an der Maus-X Position
4) Im oberen Band **ziehen (Drag)**:
   - vertikal ziehen → Zoom in/out
   - Der Beat unter dem Mauszeiger bleibt „am Platz“ (Anchor)
5) Loop testen:
   - Im **unteren** Ruler-Band Loop-Handles/Loop-Bereich bedienen

## Notizen
- Zoom-Band-Höhe bewusst klein gehalten, damit Loop-Handles nicht blockiert werden.
