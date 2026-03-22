# CHANGELOG v0.0.20.426 — Bounce in Place: VST2/VST3 Offline Rendering Fix

**Datum:** 2026-03-12  
**Entwickler:** Claude Opus 4.6

## Fixes

### Bounce in Place für VST2/VST3-Instrument-Tracks
- **Problem:** "Bounce in Place" auf VST2-Instrument-Tracks (Dexed, Helm, etc.) erzeugte eine stille WAV-Datei — kein hörbares Audio im resultierenden Clip.
- **Ursache:** `_render_track_subset_offline()` kannte nur interne Engines (Sampler, DrumMachine, Aeterna). VST2/VST3-Instrumente hatten keinen Offline-Rendering-Pfad.
- **Fix:** Drei Änderungen in `pydaw/services/project_service.py`:
  1. `_create_vst_instrument_engine_offline()`: Erstellt temporäre VST-Engine aus Track-FX-Chain mit restored State
  2. `_render_vst_notes_offline()`: Rendert MIDI mit korrektem note_on/note_off-Scheduling + Release-Tail
  3. `_render_track_subset_offline()`: Fallback auf VST-Engine wenn keine interne Engine verfügbar

### Betrifft alle Bounce-Varianten
- ✅ Bounce in Place (mit Dialog)
- ✅ Bounce in Place + Quelle stummschalten (Schnellzugriff)
- ✅ Bounce in Place (Dry) — ohne FX

## Geänderte Dateien
- `pydaw/services/project_service.py` (3 neue/modifizierte Methoden)

## Nichts kaputt gemacht
- Kein Eingriff in Audio-Engine oder Real-Time-Pfad
- Kein Eingriff in UI-Code
- Interne Engines (Sampler, Drum, Aeterna) unverändert
- VST2/VST3-Host-Code unverändert
