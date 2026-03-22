# 📝 SESSION LOG: v0.0.20.457 — CLAP Plugin Hosting (First-Class-Citizen)

**Datum:** 2026-03-15
**Bearbeiter:** Claude Opus 4.6
**Oberste Direktive:** Nichts kaputt machen ✅
**Task:** CLAP Plugin-Standard als vollwertiges Plugin-Format integrieren

## Aufgabe: CLAP Plugin Hosting — Komplette Integration

### Motivation
CLAP (CLever Audio Plugin) ist der modernste offene Plugin-Standard:
- **Bessere Performance**: Effizientere Thread-Verteilung (Multithreading)
- **Keine Lizenz-Hürden**: Komplett open-source, volle Kontrolle
- **Saubere C-ABI**: Direkt via ctypes ansprechbar (wie VST2-Host)
- **Modernes Event-System**: Eleganter als VST3 für Parameter + MIDI
- **Zukunftssicher**: Bereits von u-he, Bitwig, Surge XT, REAPER unterstützt

### Neue Datei: `pydaw/audio/clap_host.py` (~830 Zeilen)

**C-ABI Definitionen (ctypes):**
- `clap_plugin_entry_t` — Entry-Point-Struct (.clap → init → get_factory)
- `clap_plugin_factory_t` — Factory für Plugin-Enumeration + Erstellung
- `clap_plugin_t` — Plugin-Struct mit allen Lifecycle-Funktionen
- `clap_process_t` — Process-Struct mit Audio-Buffers + Events
- `clap_audio_buffer_t` — Stereo Audio I/O (float32*)
- `clap_event_note_t` — Note-On/Off Events
- `clap_event_param_value_t` — Parameter-Value Events
- `clap_input_events_t` / `clap_output_events_t` — Event-Listen
- `clap_plugin_params_t` — Params-Extension (count, get_info, get_value)
- `clap_param_info_t` — Parameter-Descriptor (id, name, min/max/default, flags)
- `clap_host_t` — Host-Descriptor mit Callbacks (request_restart/process/callback)

**Low-Level Plugin-Wrapper:**
- `_ClapPlugin` — Vollständiger Lifecycle: dlopen → entry.init → get_factory → create_plugin → plugin.init → activate → start_processing → process → stop → deactivate → destroy → deinit
- Preallocated stereo float32 Buffers (wie VST2-Host)
- `_EventList` — Event-Management mit add_note_on/off, add_param_value

**Public API:**
- `enumerate_clap_plugins(path)` — Multi-Plugin-Enumeration aus .clap Dateien
- `describe_controls(path, plugin_id)` — Temporäres Plugin laden, alle Parameter auslesen
- `is_clap_instrument(path, plugin_id)` — Instrument-Erkennung via Features
- `is_available()` — Immer True (ctypes, keine externen Deps)
- `build_plugin_reference()` / `split_plugin_reference()` — Canonical `path::plugin_id` Refs

**ClapFx (Audio-FX Wrapper):**
- Kompatibel mit `fx_chain.py` (`process_inplace(buf, frames, sr)`)
- RT-Param-Sync: RTParamStore (0..1 normalized) → Plugin (min..max denormalized)
- Parameter via `clap_event_param_value_t` Events (nicht direkt setattr wie VST)
- Same interface: `_ok`, `get_param_infos()`, `shutdown()`, `device_id`, `track_id`

**ClapInstrumentEngine (Pull-Source):**
- Kompatibel mit AudioEngine SamplerRegistry (`note_on`, `note_off`, `pull`)
- Thread-safe pending notes via Lock
- `all_notes_off()` für Transport-Stop
- Returns numpy (frames, 2) float32 wie alle anderen Pull-Sources

### Erweitert: `pydaw/services/plugin_scanner.py`
- **CLAP Suchpfade:**
  - Linux: `/usr/lib/clap/`, `~/.clap/`, `~/.local/lib/clap/`
  - macOS: `/Library/Audio/Plug-Ins/CLAP/`, `~/Library/Audio/Plug-Ins/CLAP/`
  - Windows: `%ProgramFiles%/Common Files/CLAP/`, `%LOCALAPPDATA%/Programs/Common/CLAP/`
- **`CLAP_PATH` Umgebungsvariable** für benutzerdefinierte Suchpfade
- **`scan_clap()`** — Scannt .clap Dateien/Bundles, enumeriert Multi-Plugin-Bundles
- **`scan_all()`** — Enthält jetzt CLAP als 6. Format

### Erweitert: `pydaw/audio/fx_chain.py`
- **`ext.clap:` Branch** in `ChainFx._compile()` — Erstellt `ClapFx` Instanzen
- Instrument-Erkennung → `instrument_device_specs` (wie VST2/VST3)
- **RT-Param-Ensure** in `ensure_track_fx_params()` für CLAP Parameter

### Erweitert: `pydaw/ui/plugins_browser.py`
- **CLAP Tab** in der Plugin-Browser Tab-Leiste
- **`list_clap`** — `_StarDragList("ext_clap", ...)` mit Favoriten, Drag&Drop
- **Scan-Status** zeigt CLAP-Anzahl + Availability-Hint
- **Add-to-Device Status** zeigt "CLAP live OK" bei Insert
- **Reference-Splitting** für `path::plugin_id` Format
- **Extra-Paths** über Settings für CLAP konfigurierbar

### Erweitert: `pydaw/ui/device_panel.py`
- **CLAP Metadata-Normalisierung** bei `add_audio_fx_to_track()`:
  - `__ext_ref` — Canonical Reference (`path::plugin_id`)
  - `__ext_path` — Dateipfad
  - `__ext_plugin_name` — CLAP Plugin-ID

### Erweitert: `pydaw/ui/fx_device_widgets.py`
- **`ClapAudioFxWidget`** (~200 Zeilen) — Vollständiges Parameter-UI:
  - Header mit Plugin-Name
  - ScrollArea mit Slider + SpinBox pro Parameter
  - RT-Param-Sync (Slider → RTParamStore → Audio-Thread)
  - Project-Persistenz (Flush to JSON, Restore from JSON)
  - Tooltips mit Range/Default
- **`make_audio_fx_widget()`** — `ext.clap:` Branch

### Erweitert: `pydaw/audio/audio_engine.py`
- **`ClapInstrumentEngine` Import** in `_create_vst_instrument_engines()`
- **Phase 1** — CLAP instrument specs aus ChainFx (`clap_ref`, `clap_plugin_id`)
- **Phase 2** — Fallback-Scan für `ext.clap:` Devices in Projekt
- **Phase 3** — CLAP Engine-Erstellung mit `split_plugin_reference()`

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/clap_host.py` | **NEU** — ~830 Zeilen, kompletter CLAP ctypes Host |
| `pydaw/services/plugin_scanner.py` | +CLAP Pfade, +scan_clap(), +scan_all() |
| `pydaw/audio/fx_chain.py` | +ext.clap: Branch, +RT-Param-Ensure |
| `pydaw/ui/plugins_browser.py` | +CLAP Tab, Status, Ref-Split, Extra-Paths |
| `pydaw/ui/device_panel.py` | +CLAP Metadata-Normalisierung |
| `pydaw/ui/fx_device_widgets.py` | +ClapAudioFxWidget, +make_audio_fx_widget Branch |
| `pydaw/audio/audio_engine.py` | +ClapInstrumentEngine in Phase 1/2/3 |
| `pydaw/version.py` | → `0.0.20.457` |
| `VERSION` | → `0.0.20.457` |

## Architektur-Übersicht

```
Browser → scan_clap() → CLAP Tab → Doppelklick
    ↓
device_panel.add_audio_fx_to_track("ext.clap:path::plugin_id")
    ↓                                    ↓
fx_chain.py                    ClapAudioFxWidget
  ext.clap: Branch               (Slider/SpinBox UI)
    ↓                                    ↓
ClapFx (process_inplace)         RTParamStore sync
    ↓
_ClapPlugin (ctypes)
  dlopen → clap_entry → factory → create → init → activate → process
```

## Nichts kaputt gemacht ✅
- Alle bestehenden Plugin-Formate (LV2, LADSPA, DSSI, VST2, VST3) unverändert
- Alle 7 geänderten Dateien kompilieren fehlerfrei (py_compile)
- CLAP ist additiv — kein bestehender Code entfernt oder modifiziert
- Safe try/except überall — fehlende CLAP-Plugins = no-op
