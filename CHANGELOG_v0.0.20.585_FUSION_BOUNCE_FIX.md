# CHANGELOG v0.0.20.585 — Fusion Bounce-in-Place Fix

**Datum:** 2026-03-18
**Entwickler:** Claude Opus 4.6
**Typ:** CRITICAL BUG FIX
**Oberste Direktive:** Nichts kaputt machen ✅

## Problem
- Fusion-Tracks erzeugen beim Bounce in Place nur Stille (0-Peak WAV)
- MIDI-Clips sind vorhanden, werden aber nicht gerendert
- Betrifft nur Fusion — andere Instrumente (Aeterna, Bach Orgel, SF2) bouncen korrekt

## Root Cause
`_render_track_subset_offline()` hat eine if/elif-Kette für bekannte Plugin-Typen.
Der Fusion-Block (`chrono.fusion`) war bereits vorhanden, aber:

**`track.plugin_type` war auf dem Track-Objekt leer (`""` oder `None`)**,
weil ältere Projekte oder bestimmte UI-Pfade den `plugin_type` nicht korrekt
setzen. Dadurch matchte keiner der Zweige → `engine = None` → VST-Fallback
findet auch nichts → **STILLE**.

## Fixes (1 Datei: `pydaw/services/project_service.py`)

### Fix A: Auto-Detection aus `instrument_state` (Zeile ~4668)
Wenn `plugin_type` leer ist aber `instrument_state` einen bekannten Key hat
(z.B. `'fusion'`, `'aeterna'`, `'bach_orgel'`), wird `plugin_type` automatisch
auf den korrekten Wert gesetzt.

### Fix B: Fallback Engine-Erstellung (Zeile ~4817)
Zweiter Fallback nach dem try/except-Block: prüft `instrument_state`-Keys
und erstellt die passende Engine direkt (inkl. komplettem Fusion State-Restore).

### Fix C: Verbesserte Diagnostik
`[BOUNCE]`-Log zeigt jetzt `instrument_state_keys`, damit bei zukünftigen
Problemen sofort sichtbar ist welcher Zustand vorliegt.

## Nicht angefasst
- FusionEngine, FusionWidget, Audio-Engine, andere Instrumente
- Knob-Skalierung (`_fusion_knob_to_engine_value`) war bereits korrekt
- Offline-Render-Pipeline (`_render_vst_notes_offline`) war bereits korrekt
