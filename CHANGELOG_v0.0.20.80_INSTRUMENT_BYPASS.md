# CHANGELOG v0.0.20.80 — Instrument Power/Bypass

**Datum:** 2026-02-15
**Entwickler:** Claude Opus 4.6

## Neues Feature: Instrument Power/Bypass

Jedes Instrument (SF2, Pro Audio Sampler, Pro Drum Machine) hat jetzt einen **Power-Button** in der Device-Card-Titelleiste. Damit kann das Instrument **bypassed** (deaktiviert) werden:

### Was passiert bei Bypass (Power OFF)?
- ❌ Keine MIDI-Events werden an das Instrument dispatched
- ❌ Kein SF2-Rendering (FluidSynth) findet statt
- ❌ Pull-Sources (Sampler/Drum Machine) erzeugen kein Audio
- ✅ Track bleibt sichtbar im Mixer / Arranger
- ✅ Audio-FX Chain bleibt intakt (greift nur nicht, weil kein Input-Signal)
- ✅ Zustand wird im Projekt gespeichert (`Track.instrument_enabled`)

### Unterschied zu Track-Mute
- **Track-Mute**: Audio wird erzeugt, aber in der Mix-Phase stummgeschaltet
- **Instrument Bypass**: Audio wird gar nicht erst erzeugt → **CPU-sparender**

### Geänderte Dateien
| Datei | Änderung |
|-------|----------|
| `pydaw/model/project.py` | `Track.instrument_enabled: bool = True` |
| `pydaw/ui/device_panel.py` | Power-Button + `_set_instrument_enabled()` |
| `pydaw/audio/arrangement_renderer.py` | Bypass-Check bei MIDI-Clip-Verarbeitung |
| `pydaw/audio/hybrid_engine.py` | `_bypassed_track_ids` + Checks (JACK + sounddevice) |
| `pydaw/audio/audio_engine.py` | Bypass-Set Verdrahtung bei Playback-Start |
