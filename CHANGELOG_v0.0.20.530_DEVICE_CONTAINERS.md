# CHANGELOG v0.0.20.530 — Device-Container Phase 1: FX Layer + Chain (Bitwig Sound-Design-Kern)

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Major Feature (Phase 1)

---

## Was ist ein Device-Container?

In Bitwig Studio ist der Sound-Design-Kern das **Container-System**:
- **FX Layer** — Audio wird in N parallele Pfade gesplittet, jeder Pfad hat seine eigene FX-Chain, die Ergebnisse werden summiert. Ideal für Parallel-Compression, Multi-Band-Processing, kreative Layering.
- **Chain** — Mehrere FX in Serie, zusammengeklappt in eine einzige Card. Für Organisation, Preset-Management, und verschachtelte Effektketten.

Ab v530 hat Py_DAW beides — als erste Phase mit Audio-Engine + UI-Widgets + programmatischer API.

## Architektur-Entscheidung

**Additiv, nichts geändert:** Container sind normale Einträge in `audio_fx_chain.devices[]`. Von außen sieht `ChainFx.process_inplace()` sie als gewöhnliche `AudioFxBase`-Devices. Intern verarbeiten sie Audio parallel (FxLayer) oder als Sub-Chain (ChainContainer). Unbegrenzt verschachtelbar.

## Änderungen

### Audio-Engine (`pydaw/audio/fx_chain.py`)

**FxLayerContainer:**
- Datenformat: `{"plugin_id": "chrono.container.fx_layer", "layers": [{"name": "Layer 1", "volume": 1.0, "devices": [...]}]}`
- Jeder Layer ist intern ein eigenes `ChainFx`
- Processing: Input kopiert → pro Layer verarbeitet → summiert → normalisiert (÷N) → Mix-Blend
- Pre-allokierte Scratch-Buffers für RT-Safety
- Max 8 Layer

**ChainContainerFx:**
- Datenformat: `{"plugin_id": "chrono.container.chain", "devices": [...]}`
- Intern ein `ChainFx` mit eigenem Dry/Wet-Mix
- Wenn Mix < 100%: Dry-Buffer gesichert, Inner-Chain verarbeitet, Blend

**Integration:**
- `_compile_devices()` erkennt Container **vor** allen anderen Plugin-Typen (VST, LV2, etc.)
- `ensure_track_fx_params()` registriert `layer_mix` und `chain_mix` RT-Keys

### UI-Widgets (`pydaw/ui/fx_device_widgets.py`)

**_FxLayerContainerWidget (⧉ Cyan):**
- Layer-Liste mit Statusanzeige (●/○), Device-Count, Volume
- Mix-Slider (0-100%)
- "+ Layer"-Button (max 8)

**_ChainContainerWidget (⟐ Orange):**
- Device-Summary-Liste mit Nummerierung
- Mix-Slider (0-100%)

### DevicePanel API (`pydaw/ui/device_panel.py`)

- `add_fx_layer_to_track(track_id, num_layers=2)` — erstellt FX Layer mit N leeren Layers
- `add_chain_container_to_track(track_id)` — erstellt leere Chain
- `add_device_to_container(track_id, container_device_id, plugin_id, layer_index=0)` — fügt Device in Container ein

### Katalog (`pydaw/ui/fx_specs.py`)

- `get_containers()` liefert FX Layer + Chain Einträge

---

## Nichts kaputt gemacht ✅

- Bestehende serielle FX-Chain-Verarbeitung unverändert
- Alle Plugin-Typen (VST2/3, LV2, LADSPA, DSSI, CLAP, interne FX) unberührt
- DevicePanel Card-Rendering für bestehende Devices unverändert
- Audio-Engine Callback-Pfad unverändert (Container sind normale AudioFxBase)
- Projekt-Format abwärtskompatibel (Container sind reguläre devices[]-Einträge)

## Phase 2 (nächste Session)

- Browser/Menü-Integration (Container per Rechtsklick hinzufügen)
- Drag&Drop von Devices in Container-Layer
- Layer-Expand (Klick öffnet Sub-Chain zum Editieren)
- Instrument-Layer (Stack) als eigener Container-Typ
