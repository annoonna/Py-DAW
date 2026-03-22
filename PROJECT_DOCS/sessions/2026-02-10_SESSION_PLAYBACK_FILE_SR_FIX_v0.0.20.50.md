# Session Log — v0.0.20.50 Playback Hotfix (JACK Arrange Preparation)

**Date:** 2026-02-10  
**Developer:** GPT-5.2 Thinking

## Issue

- Playback ist stumm.
- Dialog beim Start:
  `JACK: Arrange-Vorbereitung fehlgeschlagen: cannot access local variable 'file_sr' where it is not associated with a value`

## Cause

In `pydaw/audio/arrangement_renderer.py` wurde beim Laden der gerenderten SF2-WAV aus dem Cache zwar `data` gesetzt, aber `file_sr` nie initialisiert.
Später wird `file_sr` genutzt, um Resampling zu bestimmen -> UnboundLocalError.

## Fix

1. `arrangement_renderer.py`: `file_sr = int(sr)` vor Cache-Abfrage initialisiert.
2. `audio_engine.py`: Wenn Backend auf JACK erzwungen ist, aber `JackClientService.probe_available()` false ist, automatisch auf `sounddevice` wechseln und Hinweis ausgeben.

## Files

- `pydaw/audio/arrangement_renderer.py`
- `pydaw/audio/audio_engine.py`

