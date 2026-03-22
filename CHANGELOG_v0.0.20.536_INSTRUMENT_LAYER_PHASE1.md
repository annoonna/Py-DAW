# CHANGELOG v0.0.20.536 — Instrument-Layer (Stack) Phase 1

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (Phase 1 von 3)

---

## Was ist neu?

Instrument Layer (Stack) — Bitwigs Sound-Design-Kern für Multi-Instrument-Stacks.

### Phase 1 (diese Version):
- **Datenmodell** — Projekt-JSON speichert Layer mit `instrument`, `instrument_name`, `volume`, `enabled`, `devices[]`
- **UI-Widget** — Violettes Farbschema (🎹 #ce93d8), expandierbare Layer mit Instrument-Picker
- **Audio-Engine** — Erkennt `chrono.container.instrument_layer` als parallelen FxLayerContainer
- **Integration** — Browser, Rechtsklick-Menü, DnD, auto-Routing in add_audio_fx_to_track()

### Phase 2 (nächste Version):
- Multi-Instrument-Engine-Creation pro Layer
- MIDI-Dispatch an alle Layer gleichzeitig

### Phase 3 (danach):
- Velocity-Split / Key-Range pro Layer

## Layer-Datenformat
```json
{
  "plugin_id": "chrono.container.instrument_layer",
  "layers": [
    {
      "name": "Layer 1",
      "instrument": "chrono.aeterna",
      "instrument_name": "AETERNA Synthesizer",
      "volume": 1.0,
      "enabled": true,
      "devices": [...]
    }
  ]
}
```

## Geänderte Dateien
- `pydaw/ui/fx_device_widgets.py` (+300 Zeilen)
- `pydaw/audio/fx_chain.py` (+15 Zeilen)
- `pydaw/ui/device_panel.py` (+55 Zeilen)
- `pydaw/ui/fx_specs.py` (+15 Zeilen)

## Nichts kaputt gemacht ✅
