# Session v0.0.20.200 — Note Expressions: Lane UX (Badges + Context Menu + Value Snap)

**Datum:** 2026-03-03  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Direktive:** Nichts kaputt machen (lane-only, opt-in)

## Ziel
Die Expression-Lane soll sich „lebendig“ und produktiv anfühlen:
- Segment-Handles/Badges (L/S) als sichtbare Affordance
- Context-Menu statt zwingender Hotkeys
- Value-Snapping per Param (Alt=free)

## Änderungen (safe)
### 1) Segment UI affordances
- Pro Segment (zwischen zwei Punkten) wird ein kleines Badge gezeichnet:
  - **L** = linear
  - **S** = smooth
- Hover-Highlight über Segment/Badge.
- **Left-Click Badge** toggelt Segment-Typ (linear ↔ smooth).

### 2) Context Menu (RMB)
- **RMB Segment/Badge**: Toggle / Set Linear / Set Smooth / Insert Point
- **RMB leerer Bereich**: Quantize Selected / Thin Selected / Clear Selection (nur aktiv, wenn Selection existiert)
- **RMB Punkt**: Quick-Delete bleibt; **Ctrl+RMB** öffnet Point-Menu (Delete Point)

### 3) Value Snapping (Alt=free)
- Standard ON in der Lane (Preference):
  - `ui/pianoroll_expr_value_snap` (default True)
- Step sizes:
  - normalized params: 0.01
  - micropitch: 0.05 semitones
- ALT halten: kein Snapping (frei)

### 4) UI Toggle
- Im Piano-Roll Header: **V-Snap** Toggle.

## Betroffene Dateien
- `pydaw/ui/note_expression_lane.py`
- `pydaw/ui/pianoroll_editor.py`
- `pydaw/core/settings.py`
- `PROJECT_DOCS/plans/NOTE_EXPRESSIONS.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Test-Checkliste
1. Piano-Roll: Expr aktivieren → Lane zeigt V-Snap Status.
2. Punkte setzen/draggen: Werte snappen (Alt=free).
3. Segmente: Badges sichtbar, Left-Click toggelt.
4. RMB Segment: Menü erscheint, setzt/toggelt Segment, Insert Point funktioniert.
5. RMB Punkt: Quick delete; Ctrl+RMB öffnet Menü.
6. Undo/Redo: Änderungen kommen als 1 Commit pro Geste / pro Menu-Aktion.

