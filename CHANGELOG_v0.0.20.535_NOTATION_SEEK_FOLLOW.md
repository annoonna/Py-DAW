# CHANGELOG v0.0.20.535 — Notation: Playhead Click-to-Seek + Follow Playhead

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Typ:** 2 kleine Features

---

## 1. Playhead Click-to-Seek

Klick ins Zeitlineal (obere 24px der Notation-Ansicht) setzt den Transport-Playhead auf die angeklickte Beat-Position — genau wie im Arranger.

## 2. Follow Playhead (Auto-Scroll)

Neuer "▶ Follow" Toggle-Button in der Notation-Toolbar:
- Blau hinterlegt wenn aktiv
- Notation scrollt automatisch mit dem Playhead
- Bei 80% des sichtbaren Bereichs → Sprung so dass Playhead bei 20% steht
- Identisches Verhalten wie der Follow-Button im Arranger (Bitwig-Stil)

## Geänderte Datei

- `pydaw/ui/notation/notation_view.py` (+45 Zeilen)

## Nichts kaputt gemacht ✅
- Bestehende Notation-Eingabe (Draw/Select/Erase) unverändert
- Playhead-Rendering unverändert
- Ruler-Rendering unverändert
- Transport-Wiring unverändert (additiv erweitert)
