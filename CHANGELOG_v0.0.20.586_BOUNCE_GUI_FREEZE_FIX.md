# CHANGELOG v0.0.20.586 — Bounce GUI-Freeze Fix

**Datum:** 2026-03-18
**Entwickler:** Claude Opus 4.6
**Typ:** PERFORMANCE FIX
**Oberste Direktive:** Nichts kaputt machen ✅

## Problem
- "main.py antwortet nicht" Dialog erscheint beim Bounce in Place
- GUI friert komplett ein während Offline-Rendering
- Besonders schlimm bei langen Clips (64 Beats = ~1547 Blöcke)

## Root Cause
`_render_vst_notes_offline()` und `_render_engine_notes_offline()` laufen
synchron im GUI-Thread. Jeder FusionEngine.pull(1024) Block ist reines
Python-DSP und dauert ~20-50ms. Bei 1547 Blöcken = ~30-60 Sekunden
ohne Qt Event-Loop-Pump.

Der bestehende processEvents-Aufruf alle 50 Blöcke war zu selten —
50 × ~30ms = ~1.5 Sekunden zwischen Pumps, aber Qt/OS zeigt "nicht
antwortend" nach ~200-500ms.

## Fix
- `_render_vst_notes_offline`: processEvents alle 8 Blöcke (statt 50)
  → ~170ms Audio / ~240ms Wallclock zwischen Pumps
- `_render_engine_notes_offline`: processEvents alle 8 Blöcke hinzugefügt
  (fehlte komplett!)
- `_render_tracks_selection_to_wav`: processEvents vor WAV-Write

## Geänderte Dateien
- `pydaw/services/project_service.py` (3 Stellen)

## Nicht angefasst
- FusionEngine, Audio-Engine, UI-Komponenten
- Render-Logik/-Qualität unverändert
