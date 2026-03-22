# Session: Notation Grid + Y-Zoom + Scale Badge (12 Dots)

**Datum:** 2026-02-03  
**Version:** v0.0.19.5.1.32  
**Developer:** GPT-5.2

## Ziel
Notation-Editor soll DAW-typisch bedienbar sein (horizontal scroll/zoom), zusätzlich:
- **kontrastreicheres Grid** (Bars/Beats/Subbeats)
- **mehr vertikaler Platz**, Notes dürfen nicht „verschwinden“
- **Scale-Hints im UI** wie eine Pro-DAW: dunkles Badge + **12 chromatische Dots** + **Root markiert**

## Umsetzung

### 1) Scroll / Zoom (NotationView)
- **Wheel:** horizontal scroll (Timeline)
- **Shift + Wheel:** vertical scroll
- **Ctrl + Wheel:** X-Zoom (pixels/beat)
- **Ctrl + Shift + Wheel:** Y-Zoom (View-Transform)
- **Ctrl + 0:** Reset X+Y Zoom

### 2) Grid Lines stärker
- In `NotationView.drawBackground()`:
  - Subbeat (1/16) sehr hell
  - Beat moderat
  - Bar (4/4) stärker (breiter)

### 3) Notes verschwinden nicht mehr
- `_NoteItem.boundingRect()` korrekt aus StaffRenderer-Referenz berechnet (Bottom-Line + Halfsteps).
- `sceneRect` wird nach Refresh auf **itemsBoundingRect + Padding** gesetzt → genug Höhe/Scrollbereich.

### 4) Scale Badge 12 Dots + Root
- `ScaleMenuButton` rendert eigenes Badge:
  - dunkles Pill-Background
  - Label
  - **12 Dots** (Pitch Classes)
  - Root dot: Outline + slightly larger
  - In-Scale dots: cyan (wenn Scale enabled)

## Geänderte Dateien
- `pydaw/ui/notation/notation_view.py`
- `pydaw/ui/scale_menu_button.py`

## Nächster sinnvoller Schritt
- Notation: echtes „Scale Hints“ pro Pitch/Zeile (mehr Pro-DAW-like) *optional*
- Notation: Feinschliff Farben/Theming (Dark Theme)
