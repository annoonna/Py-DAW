# CHANGELOG v0.0.20.68 — Sampler/Drum Playback Fix (Real-Time MIDI Scheduling)

**Datum:** 2026-02-13

## Problem
In **v0.0.20.67** waren **Pro Audio Sampler** und **Pro Drum Machine** im Arrangement stumm: Noten in PianoRoll/Notation, Transport läuft, aber kein Audio. **SF2** (offline MIDI→WAV) funktionierte weiterhin.

## Architektur (relevant)
- **SF2**: MIDI-Clips werden offline gerendert (MIDI→Audio) und als `PreparedClip` in den Arrange-Render-Pfad eingespeist.
- **Sampler/Drum**: Realtime-Pfad über Hybrid-Callback:
  1) `arrangement_renderer.prepare_clips(...)` erzeugt zusätzlich eine Liste `PreparedMidiEvent(sample_pos, is_note_on, pitch, velocity, track_id)`.
  2) `TrackRenderState.get_pending_midi_events(...)` liefert Events blockweise.
  3) `HybridAudioCallback` dispatcht diese Events an die `SamplerRegistry` (`note_on/note_off`).
  4) Danach werden die Realtime-Quellen (`pull_sources`) gezogen und pro Track gemischt.

## Ursache
In `pydaw/audio/arrangement_renderer.py` wurde im **non-SF2 Instrument** Branch (LIVE MIDI PATH) versehentlich ein veraltetes Event-Schema verwendet. Das führte zu einer Exception in `prepare_clips(...)`.

Folge: Der Hybrid-Pfad wurde von `audio_engine.py` verworfen und es wurde auf den Legacy-Mix-Fallback gewechselt. Der Legacy-Fallback rendert SF2, aber **nicht** die Realtime-Instrumente (Sampler/Drum) → Stille.

## Fix
- Live-MIDI Events werden wieder korrekt als `PreparedMidiEvent(sample_pos, is_note_on, pitch, velocity, track_id)` erzeugt.
- NOTE-FX Chain Anwendung bleibt erhalten (wird vor dem Scheduling auf die Note-Liste angewandt).
- Audio Settings: Sample-Rate Presets ergänzt (inkl. **44100 Hz**) für klare UX.

## Geänderte Dateien
- `pydaw/audio/arrangement_renderer.py`
- `pydaw/ui/audio_settings_dialog.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/progress/DONE.md`, `PROJECT_DOCS/progress/LATEST.md`, `PROJECT_DOCS/progress/sessions/SESSION_v0.0.20.68_2026-02-13.md`

## Test
1) Neuer Instrument Track
2) Device: **Pro Audio Sampler** oder **Pro Drum Machine**
3) Sample laden
4) Notes setzen
5) Play → **Audio hörbar**
6) Test mit 44100 und 48000 in den Audio Settings
