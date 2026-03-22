# Session: v0.0.20.426 — Bounce in Place: VST2/VST3 Offline Rendering

**Datum:** 2026-03-12
**Entwickler:** Claude Opus 4.6
**Aufgabe:** Bounce in Place erzeugt kein Audio-Sample für VST2-Instrument-Tracks

## Problem

Beim "Bounce in Place" von MIDI-Clips auf VST2-Instrument-Tracks (z.B. Dexed, Helm) wurde
zwar eine neue Audio-Spur mit Clip erstellt, aber die generierte WAV-Datei enthielt nur Stille.
Das Gleiche galt für "Bounce in Place + Quelle stummschalten" und "Bounce in Place (Dry)".

## Ursache

`_render_track_subset_offline()` in `project_service.py` unterstützte nur interne Engines:
- `sampler` → ProSamplerEngine
- `drum_machine` → DrumMachineEngine
- `aeterna` → AeternaEngine

Für VST2/VST3-Instrumente (die über `audio_fx_chain` als `ext.vst2:`/`ext.vst3:` gehosted werden)
gab es keinen Offline-Rendering-Pfad. Die Variable `engine` blieb `None`, und es wurde ein
leerer numpy-Buffer (`np.zeros`) als WAV geschrieben.

## Lösung

### 1. `_create_vst_instrument_engine_offline(track, sr)` (neue Methode)
- Scannt `track.audio_fx_chain` → `devices` nach `ext.vst2:`/`ext.vst3:` Plugins
- Prüft ob das Plugin ein Instrument ist (`__ext_is_instrument` oder `is_vst_instrument()`)
- Erstellt temporäre `Vst2InstrumentEngine` / `Vst3InstrumentEngine` Instanz
- Stellt Plugin-State wieder her via `__ext_state_b64` (Base64-Chunk)
- Nutzt einen Offline-RTParamStore (keine Live-Audio-Engine nötig)

### 2. `_render_vst_notes_offline(engine, notes, bpm, clip_len, sr)` (neue Methode)
- Schedult MIDI note_on UND note_off Events explizit (VST-Engines haben kein `trigger_note()`)
- Events sortiert: Frame-Position, note_off vor note_on bei gleicher Position
- Block-basiertes Rendering über `engine.pull(frames, sr)`
- 1-Sekunde Release-Tail nach `all_notes_off()` für natürliche Ausklingphase

### 3. Modifikation von `_render_track_subset_offline()`
- Nach internem Engine-Versuch (sampler/drum/aeterna): Fallback auf VST-Engine
- Erkennung über `hasattr(engine, 'trigger_note')` → VST vs. Internal
- VST-Engine wird nach Rendering sauber mit `shutdown()` beendet

## Geänderte Dateien

- `pydaw/services/project_service.py`
  - Neue Methode: `_create_vst_instrument_engine_offline()`
  - Neue Methode: `_render_vst_notes_offline()`
  - Modifiziert: `_render_track_subset_offline()` — VST-Instrument-Fallback

## Nicht verändert

- Audio-Engine (kein Eingriff in Real-Time-Pfad)
- UI-Code (Bounce-Dialog, Arranger-Kontext-Menü)
- VST2/VST3-Host-Code
- Alle anderen Module

## Test-Szenario

1. MIDI-Clips auf VST2-Track (z.B. Dexed) selektieren
2. Rechtsklick → "Bounce in Place + Quelle stummschalten"
3. ✅ Neue Audio-Spur mit hörbarem Audio-Clip wird erstellt
4. ✅ Quell-MIDI-Clips werden stummgeschaltet
5. ✅ Waveform im Editor sichtbar (nicht mehr leer/MUTED)
