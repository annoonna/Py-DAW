# CHANGELOG v0.0.20.539 — Instrument-Layer Phase 2: Multi-Engine + MIDI-Dispatch

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (Phase 2 — Audio-Engine Integration)

---

## Was ist neu?

Instrument Layer Containers sind jetzt **vollständig funktional**:
MIDI-Noten werden an alle Layer gleichzeitig dispatcht, jeder Layer
spielt seinen eigenen Sound, und alle Layer-Ausgänge fließen in den Mix.

### Datenfluss:

```
MIDI-Keyboard → SamplerRegistry → _InstrumentLayerDispatcher
  → Layer 0 Engine.note_on() → Pull Source 0 → Audio Mix
  → Layer 1 Engine.note_on() → Pull Source 1 → Audio Mix
  → Layer 2 Engine.note_on() → Pull Source 2 → Audio Mix
```

### Architektur:

- **_InstrumentLayerDispatcher**: Leichtgewichtiger Wrapper, implementiert note_on/note_off/all_notes_off und leitet an alle Layer-Engines weiter
- **Phase 3b in _create_vst_instrument_engines()**: Scannt Projekt nach instrument_layer Container, erstellt pro Layer eine VST3/VST2/CLAP Engine
- **Engine-Reuse**: Bei rebuild_fx_maps() werden bestehende Layer-Engines wiederverwendet (kein 2s Surge XT Reload)
- **Per-Layer Pull Sources**: Jeder Layer hat eigene Pull-Source (`vstinst:{tid}:ilayer:{i}`)

### Einschränkungen (Phase 3):
- Aktuell nur externe Plugins (VST3/VST2/CLAP), keine Built-in Instrumente als Layer
- Keine Velocity-Split / Key-Range pro Layer (alle Layer empfangen alle Noten)

## Geänderte Datei
- `pydaw/audio/audio_engine.py` (+120 Zeilen)

## Nichts kaputt gemacht ✅
- Bestehender Einzelinstrument-Pfad komplett unberührt
- Phase 3b wird nur aktiviert wenn instrument_layer Container existieren
- Cleanup (Phase 4) behandelt Layer-Engines korrekt
