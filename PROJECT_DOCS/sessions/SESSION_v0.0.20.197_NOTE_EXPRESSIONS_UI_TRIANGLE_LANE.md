# Session: v0.0.20.197 — Note Expressions UI (Triangle + Lane + Smooth Micropitch)

**Datum:** 2026-03-03  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Oberste Direktive:** nichts kaputt machen ✅

## Ziel

Die Note‑Expressions Foundation aus v0.0.20.196 soll „lebendig“ werden:

- Overlay/Param‑Auswahl in der Piano‑Roll (UI)
- Expression‑Triangle Interaktion (Click‑Menu + Alt‑Drag Morph)
- Expression‑Lanes unter der Piano‑Roll (expand/collapse) + Editing
- Smooth Micropitch Rendering (Bezier)

Alles **opt‑in** und ohne bestehende Note‑Edit‑Tools (Move/Resize/Knife) zu brechen.

## Änderungen

### 1) PianoRoll Header: Expr Toggle + Param Combo

- `Expr` Toggle aktiviert/deaktiviert Note Expressions.
- Param Combo (velocity/chance/timbre/pressure/gain/pan/micropitch) setzt `active_param`.
- Persistiert in QSettings:
  - `ui/pianoroll_note_expressions_enabled`
  - `ui/pianoroll_note_expressions_param`

### 2) Triangle Interaction Model (Canvas)

- Hover über Note: Triangle erscheint dezent.
- Klick auf Triangle: Quick‑Menu zur Paramwahl.
- **Alt+Drag** auf Triangle: **Time‑Morph** (skaliert normalized `t`), Commit bei Release.
- Doppelklick Note: Focus‑Mode (andere Noten gedimmt); ESC beendet Focus.

### 3) Expression Lane Widget

- Neues Widget `NoteExpressionLane` unter der Piano‑Roll.
- Target‑Note Priorität: **Focus > Single Selection > Hover**.
- Draw‑Editing (Linksklick+Ziehen) fügt sparse Punkte ein / ersetzt nahe Punkte.
- Undo/Redo: Snapshot bei Press, Commit bei Release.

### 4) Smooth Micropitch Rendering

- `note_expression_engine.py`: Micropitch wird als **cubic Bezier** (Catmull‑Rom → `cubicTo`) gezeichnet.
- Hintergrunddaten bleiben sparse JSON‑Punkte; nur Darstellung wird smooth.

## Betroffene Dateien

- `pydaw/ui/pianoroll_editor.py`
- `pydaw/ui/pianoroll_canvas.py`
- `pydaw/ui/note_expression_engine.py`
- `pydaw/ui/note_expression_lane.py` (neu)
- `PROJECT_DOCS/plans/NOTE_EXPRESSIONS.md`
- `PROJECT_DOCS/progress/TODO.md`
- `VERSION`, `pydaw/version.py`

## Test‑Checkliste (manuell)

1. Piano‑Roll öffnen → **Expr** ist default OFF.
2. Expr ON → Triangle erscheint beim Hover.
3. Triangle Click → Paramwahl; Combo/Overlay aktualisiert.
4. Alt+Drag Triangle → Curve time‑morph; Release → Undo/Redo funktioniert.
5. Doppelklick Note → Focus; ESC beendet.
6. Lane: Note auswählen/hovern → Kurve sichtbar; Linksklick+Ziehen → Punkte/Curve werden erstellt.

## Nächste Schritte

- Lane expand/collapse UI polish (kleiner Arrow / Height Presets)
- Optional: Curve‑Types (Step/Smooth) + Point‑Delete
- Optional: In‑Note Pen‑Mode (separates Tool), ohne Move/Resize zu stören
