# Session: SF2 Realtime Engine — Live MIDI Keyboard → SoundFont Audio
**Version:** v0.0.20.430
**Datum:** 2026-03-12
**Entwickler:** Claude Opus 4.6

## Problem
SF2-Tracks reagierten nicht auf Live-MIDI-Keyboard. Alle anderen Instrumente (VST2, VST3, DSSI, LADSPA, LV2, Pro Audio Sampler, Pro Drum Machine, AETERNA, Bach Orgel) funktionierten korrekt.

## Root Cause Analyse

### Architektur-Problem
SF2 war das **einzige Instrument ohne Realtime-Engine**:
- SF2: MIDI → FluidSynth CLI → WAV-Cache → Audio-Mix (nur offline/Playback)
- Alle anderen: MIDI → SamplerRegistry → Engine.note_on() → Pull-Source → Audio-Mix (realtime)

### Signal-Fluss bei Live-MIDI
```
MIDI Keyboard → MidiManager.live_note_on
                    ↓
MainWindow._on_live_note_on_route_to_sampler
                    ↓
SamplerRegistry.note_on(track_id, pitch, vel)
                    ↓
              ❌ Kein Engine für SF2-Track registriert
                    ↓
              _route_live_note_to_vst() → auch nichts
                    ↓
              "Kein Sound" StatusBar-Meldung
```

### Best Practice (Bitwig/Ableton/Cubase)
SoundFont-Instrumente haben immer eine Realtime-Synth-Engine:
- MIDI Input → Synth → Audio Buffer → Mixer
- Kein Unterschied zwischen Live-Play und Playback

## Lösung

### 1. `FluidSynthRealtimeEngine` (NEU: `pydaw/audio/sf2_engine.py`)
- Wraps `pyfluidsynth.Synth` als Pull-Source
- `pull(frames, sr)` → `synth.get_samples()` → float32 stereo numpy array
- `note_on(pitch, vel)` / `note_off(pitch=...)` / `all_notes_off()`
- Thread-safe via Lock (GUI-Thread note_on, Audio-Thread pull)
- Polyphonic: tracked active pitches für pitch-spezifisches note_off
- `trigger_note()` für One-Shot-Preview (Timer-basiert)
- `set_program(bank, preset)` für Runtime-Wechsel
- Clean shutdown mit SoundFont-Unload

### 2. `AudioEngine._create_sf2_instrument_engines()` (NEU in `audio_engine.py`)
- Scannt Project-Tracks nach `plugin_type == "sf2"`
- Erstellt/reused FluidSynthRealtimeEngine pro SF2-Track
- Registriert Engine in SamplerRegistry (MIDI-Dispatch)
- Registriert Pull-Source mit `_pydaw_track_id` Tag (Track-Mixer: Vol/Pan/Mute/Solo/VU)
- Aufgerufen von `rebuild_fx_maps()` (gleicher Lifecycle wie VST-Engines)
- Shutdown alter Engines wenn Track entfernt/geändert

### 3. Polyphonic note_off Fix (`main_window.py`)
- `_on_live_note_off_route_to_sampler()` gibt jetzt `pitch` an SamplerRegistry.note_off() weiter
- Vorher: `note_off(track_id)` ohne pitch → released ALLE Noten
- Nachher: `note_off(track_id, pitch=pitch)` → released nur die losgelassene Taste

### 4. UI-Hint Update (`device_panel.py`)
- Altes Label: "SF2 wird beim Playback gerendert"
- Neues Label: "SF2 SoundFont — Live-MIDI + Playback"

## Geänderte Dateien
| Datei | Änderung |
|-------|----------|
| `pydaw/audio/sf2_engine.py` | **NEU** — FluidSynthRealtimeEngine |
| `pydaw/audio/audio_engine.py` | `_sf2_instrument_engines` Dict + `_create_sf2_instrument_engines()` + Aufruf in `rebuild_fx_maps()` |
| `pydaw/ui/main_window.py` | Polyphonic pitch in `note_off()` Dispatch |
| `pydaw/ui/device_panel.py` | UI-Hint Text Update |

## Nicht geändert (Offline-Rendering intakt)
- `pydaw/audio/midi_render.py` — SF2 WAV-Cache für Playback unverändert
- `pydaw/services/fluidsynth_service.py` — Legacy-Service unverändert
- Alle anderen Instrument-Engines — nicht berührt

## Test-Anleitung
1. SF2 SoundFont auf Instrument-Track laden
2. MIDI-Keyboard anschließen (Record-Button im Piano Roll drücken)
3. Tasten spielen → Sofort Sound hören
4. Stderr prüfen: `[SF2-RT] Engine created: track=... ✓`
5. Playback starten → SF2-Clips werden weiterhin korrekt gerendert
6. Andere Instrumente testen → Nichts kaputt
