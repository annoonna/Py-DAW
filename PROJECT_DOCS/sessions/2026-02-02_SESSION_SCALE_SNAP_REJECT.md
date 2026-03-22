# Session Log – 2026-02-02 – Scale Lock: Snap + Reject

Version: **v0.0.19.5.1.17**

## Ziel
"Scale Lock" soll in **Piano Roll** und **Notation** zwei Modi unterstützen:

1. **Snap**: außerhalb liegende Noten werden automatisch auf den nächsten erlaubten Ton "gesnappt".
2. **Reject**: außerhalb liegende Noten werden **nicht gesetzt**.

## Umsetzung
- Neue gemeinsame Helper:
  - `pydaw/music/scales.py` (JSON laden, Pitch-Classes berechnen, Snap/Reject anwenden)
- UI:
  - `pydaw/ui/scale_menu_button.py` als minimaler Pro-DAW-Style Button
    - Enable/Disable Scale Lock
    - Root Note
    - Skala (kategorisiert)
    - Mode: **Snap / Reject**
- Enforcement:
  - Piano Roll: `pydaw/ui/pianoroll_canvas.py` (Note-Input)
  - Notation: `pydaw/ui/notation/tools.py` (DrawTool Note-Input)

## Hinweise
- Modus wirkt aktuell auf **Note-Input** (zeichnen). Editing/Move-Quantize nach Skala folgt später.
- Wenn "Reject" aktiv ist, wird eine kurze Statusmeldung angezeigt (out of scale).

## Nächste Schritte
- Skala auch beim **Note-Move/Drag** (optional per Setting) anwenden.
- "Scale Lock" UI in Notation/PianoRoll optisch näher an Pro-DAW (Cyan Pill, Icon, Search).