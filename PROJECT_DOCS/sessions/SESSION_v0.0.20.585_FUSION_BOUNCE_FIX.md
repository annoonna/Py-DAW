# Session Log — v0.0.20.585 Fusion Bounce-in-Place Fix

**Datum:** 2026-03-18
**Entwickler:** Claude Opus 4.6
**Vorgänger:** v0.0.20.584

## Auftrag
Fusion-Bounce erzeugt Stille — kein Audio im Bounce-Clip.

## Analyse
1. Bounce-Pipeline verfolgt: `arranger_canvas.py` → `bounce_selected_clips_to_new_audio_track()`
   → `_render_tracks_selection_to_wav()` → `_render_track_subset_offline()` → Engine-Erstellung
2. Engine-Erstellung hat elif-Kette: sampler, drum_machine, aeterna, bach_orgel, fusion
3. Fusion-Block (chrono.fusion) war bereits vorhanden, ABER:
4. `track.plugin_type` war leer → kein Branch matchte → engine=None → STILLE
5. Root cause: plugin_type wird nicht in allen Fällen korrekt auf dem Track gesetzt

## Fix
- Auto-Detection: wenn `plugin_type` leer und `instrument_state` hat Key 'fusion' → setze `plugin_type='chrono.fusion'`
- Fallback: zweiter Check nach try/except erstellt Engine direkt aus instrument_state
- Diagnostik: instrument_state_keys wird im Log ausgegeben

## Geänderte Dateien
- `pydaw/services/project_service.py` (3 Stellen)

## Test-Empfehlung
1. Fusion-Track mit MIDI-Clip erstellen
2. Rechtsklick → "Bounce in Place (Dry)"
3. Neuer Audio-Clip sollte Waveform zeigen (nicht Stille)
4. Terminal prüfen auf: `[BOUNCE] Auto-detected plugin_type='chrono.fusion' from instrument_state key 'fusion'`
