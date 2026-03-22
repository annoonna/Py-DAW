# SESSION v0.0.20.68 — 2026-02-13

## Kontext
User-Report: **v0.0.20.67** spielt bei **Pro Audio Sampler / Pro Drum Machine** keinen Ton mehr im Arrangement (Noten in PianoRoll/Notation), **SF2 funktioniert** weiterhin.

## Diagnose
- Realtime-Instrumente (Sampler/Drum) laufen über den **Hybrid-Callback**.
- In `pydaw/audio/audio_engine.py` wird bei Fehlern im Hybrid-Pfad automatisch auf Legacy-Fallback gewechselt.
- In `pydaw/audio/arrangement_renderer.py` wurde im non-SF2 Instrument-Branch (LIVE MIDI PATH) ein falsches Event-Format verwendet.
  Dadurch konnte `prepare_clips(...)` fehlschlagen → Hybrid-Path wird verworfen → Legacy rendert nur Audio+SF2 → Sampler/Drum bleiben stumm.

## Fix
1) `pydaw/audio/arrangement_renderer.py`
   - Live-MIDI Events wieder korrekt als
     `PreparedMidiEvent(sample_pos, is_note_on, pitch, velocity, track_id)` erzeugt.
   - NOTE-FX Chain wird weiterhin auf die Note-Liste angewandt.
   - Scheduling nutzt `beats_to_samples(...)` für samplegenaue Dispatch-Events.

2) `pydaw/ui/audio_settings_dialog.py`
   - Sample-Rate Preset Dropdown ergänzt (44100/48000/88200/96000/192000) + weiterhin frei editierbare Spinbox.

3) Versionierung & Doku
   - `VERSION`, `pydaw/version.py`, `pydaw/model/project.py` → **0.0.20.68**
   - `PROJECT_DOCS/progress/DONE.md` + `LATEST.md` aktualisiert.

## Quick Test Checklist
- Neuer Instrument Track
- Device: Pro Audio Sampler
- Sample laden
- Notes in PianoRoll setzen
- Play → **Audio hörbar**
- Repeat für Pro Drum Machine
- Test mit 44100 und 48000 (Audio Settings) → **beides ok**
