# Session Log – Notation Scroll + Zoom

**Datum:** 2026-02-02  
**Autor:** GPT-5.2  
**Ziel:** Notation-Editor: Timeline-Scroll/Zoom fixen (Noten wandern nach rechts → bisher nicht erreichbar).

## Problem
- Im Notation-Tab konnte man die Timeline nicht ergonomisch bedienen:
  - Kein DAW-typisches Scrollen mit Mausrad
  - Kein Zoom (Zeitachse)
  - Bei sehr langen Clips/Noten weit rechts war die Szene praktisch „zu kurz“ (Notes außerhalb des SceneRect → nicht erreichbar)

## Lösung (implementiert)
### 1) DAW-Style Scroll/Zoom
- **Mausrad** scrollt horizontal (Timeline)
- **Ctrl + Mausrad** zoomt die Zeitachse (px/Beat)
- **Ctrl + 0 / +/-**: Reset/Zoom per Tastatur

### 2) Szene wächst mit Clip-Länge (ohne harte 256-Beat-Klemme)
- SceneRect wird anhand von `max_end` (letztes Note-Ende) erweitert.
- Nur ein sehr großer Hard-Cap bleibt als Schutz gegen Ausreißer (Performance).

## Betroffene Dateien
- `pydaw/ui/notation/notation_view.py`

## Hinweise / Nächste Schritte
- Optional: Toolbar-Buttons für Zoom In/Out/Reset (wenn gewünscht).
- Optional: Auto-Follow Playhead (wie Piano Roll) – **nur** wenn stabil implementiert.

