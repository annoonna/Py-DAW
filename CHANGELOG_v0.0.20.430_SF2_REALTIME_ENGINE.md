# CHANGELOG v0.0.20.430 — SF2 Realtime Engine (Live MIDI → SoundFont Audio)

## Datum: 2026-03-12
## Entwickler: Claude Opus 4.6

### 🎯 Hauptänderung
**SF2 SoundFont reagiert jetzt auf Live-MIDI-Keyboard!**

Bisher: SF2 wurde nur offline gerendert (FluidSynth CLI → WAV-Cache).
Jetzt: `FluidSynthRealtimeEngine` als Pull-Source — identisch zu Pro Audio Sampler, AETERNA etc.

### Neue Dateien
- `pydaw/audio/sf2_engine.py` — FluidSynthRealtimeEngine (Realtime Pull-Source)

### Geänderte Dateien
- `pydaw/audio/audio_engine.py` — SF2-Engine-Lifecycle in `rebuild_fx_maps()`
- `pydaw/ui/main_window.py` — Polyphonic note_off Pitch-Forwarding
- `pydaw/ui/device_panel.py` — SF2-Widget Hint-Text Update

### Nicht geändert
- Offline-Rendering (`midi_render.py`) intakt
- Alle anderen Instrument-Engines intakt
- Keine bestehende Funktionalität geändert
