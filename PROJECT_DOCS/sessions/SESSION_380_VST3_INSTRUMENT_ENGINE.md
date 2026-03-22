# Session v0.0.20.380 — VST3 Instrument Engine (MIDI→Audio Host)

**Datum:** 2026-03-11
**Autor:** Claude Opus 4.6
**Oberste Direktive:** Nichts kaputt machen ✅

## Problem

Surge XT (und andere VST3-Instrumente) bleiben stumm, obwohl sie als Device
in der Audio-FX-Chain sichtbar sind und MIDI-Clips auf der Spur liegen.

### Root Cause

Py_DAW v0.0.20.379 kennt nur **einen** VST3-Hosting-Pfad: `Vst3Fx` (Audio-FX).
Dieser ruft `plugin.process(audio_buffer, ...)` auf — ein FX-Modus.

VST3-Instrumente erwarten aber **MIDI→Audio Rendering**:
`plugin.process(midi_messages, duration, sample_rate, ...)`.

Die MIDI-Events aus PianoRoll/Notation werden über `SamplerRegistry` nur an
interne Engines (Sampler, BachOrgel, AETERNA, DrumMachine) dispatcht.
Externe VST-Instrumente sind dort nicht registriert → kein MIDI → kein Sound.

## Lösung (5 Dateien geändert)

### 1. `pydaw/audio/vst3_host.py`
- **`is_vst_instrument(path, plugin_name)`** — prüft `plugin.is_instrument`
- **`Vst3InstrumentEngine`** (neue Klasse):
  - `note_on(pitch, velocity, ...)` → akkumuliert MIDI-Bytes
  - `note_off(pitch)` → polyphones Note-Off (Surge XT = polyphon!)
  - `all_notes_off()` → Panic (CC#123)
  - `pull(frames, sr)` → ruft `plugin.process(midi_msgs, duration, sr, ...)` auf
  - RT-Param-Sync wie Vst3Fx (raw_value, nicht setattr)
  - State-Blob Restore beim Laden

### 2. `pydaw/audio/fx_chain.py`
- `ChainFx.instrument_device_specs` — Liste für erkannte Instrumente
- `_compile_devices()`: prüft `is_vst_instrument()` für ext.vst3/ext.vst2
  - Instrument → Skip FX-Chain, Spec in `instrument_device_specs` speichern
  - Effekt → wie bisher als `Vst3Fx` kompilieren

### 3. `pydaw/plugins/sampler/sampler_registry.py`
- `note_off(track_id, pitch=-1)` — optionaler `pitch` Parameter
  - `pitch >= 0`: polyphones Note-Off (VST-Instrumente)
  - `pitch < 0`: generisches Note-Off (Legacy-Engines)

### 4. `pydaw/audio/hybrid_engine.py`
- Sounddevice-Callback: `note_off(track_id, pitch=evt.pitch)`
- JACK-Callback: `note_off(track_id, pitch=evt.pitch)`

### 5. `pydaw/audio/audio_engine.py`
- `_vst_instrument_engines: Dict[str, Vst3InstrumentEngine]`
- `_create_vst_instrument_engines(fx_map, sr)`:
  - Iteriert alle ChainFx, findet `instrument_device_specs`
  - Erstellt `Vst3InstrumentEngine` pro Track
  - Registriert in `SamplerRegistry` (MIDI-Routing)
  - Registriert als Pull-Source mit `_pydaw_track_id` (Audio-Output)
  - Clean-up alter Engines bei Rebuild

## Signalfluss nach dem Patch

```
PianoRoll/Notation → MIDI-Events (ArrangementState)
       ↓
HybridAudioCallback.get_pending_midi_events()
       ↓
SamplerRegistry.note_on(track_id, pitch, velocity)
       ↓                                    ↓
  interne Engines                 Vst3InstrumentEngine
  (Sampler, AETERNA, ...)         .note_on() → akkumuliert MIDI
       ↓                                    ↓
  .pull(frames, sr)              .pull(frames, sr)
  → numpy (frames, 2)           → plugin.process(midi_msgs, duration, sr)
       ↓                         → numpy (frames, 2)
       ↓                                    ↓
  Track Audio-FX Chain ─────────────────────┘
       ↓
  Vol/Pan/Mute/Solo
       ↓
  Group Bus → Master
```

## Was NICHT geändert wurde (Safe)

- Kein Eingriff in bestehende interne Engines (Sampler, AETERNA, BachOrgel, DrumMachine)
- Kein Eingriff in ArrangementState / MIDI-Event-System
- Kein Eingriff in FX-Processing-Pfad (nur Skip bei Instrument-Erkennung)
- Kein Eingriff in Transport / Playhead
- Audio-FX-Chain nach dem Instrument funktioniert weiter (Reverb, Delay, etc.)
- Legacy-Engines note_off() ohne pitch funktioniert weiter (TypeError-Fallback)

## Test-Anleitung

1. Surge XT auf eine Instrument-Spur laden
2. MIDI-Noten im PianoRoll setzen
3. Play drücken → Surge XT sollte jetzt hörbar sein
4. In der Konsole: `[VST3-INST] INSTRUMENT detected: ...` + `Registered pull source`
5. Audio-FX nach Surge (z.B. Reverb) sollten weiterhin funktionieren
