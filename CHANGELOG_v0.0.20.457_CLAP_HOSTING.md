# CHANGELOG v0.0.20.457 — CLAP Plugin Hosting (First-Class-Citizen)

**Datum:** 2026-03-15
**Bearbeiter:** Claude Opus 4.6

## Neue Features

### CLAP Plugin Hosting via ctypes (komplett neues Plugin-Format)
- **`pydaw/audio/clap_host.py`** — 830+ Zeilen, kompletter CLAP C-ABI Host
  - Vollständige ctypes-Definitionen aller CLAP-Structs
  - `_ClapPlugin` mit komplettem Lifecycle (load → init → activate → process → destroy)
  - `ClapFx` — Audio-FX kompatibel mit FxChain (`process_inplace`)
  - `ClapInstrumentEngine` — Instrument Pull-Source kompatibel mit AudioEngine
  - `enumerate_clap_plugins()` für Multi-Plugin .clap Dateien
  - `describe_controls()` für Parameter-Discovery
  - Keinerlei externe Abhängigkeiten (nur stdlib + numpy)

### Plugin Scanner: CLAP Support
- Standard-Suchpfade für Linux, macOS, Windows
- `CLAP_PATH` Umgebungsvariable
- `scan_clap()` mit Multi-Plugin-Bundle-Enumeration
- `scan_all()` enthält jetzt 6 Formate

### FX Chain: ext.clap: Branch
- Instrument-Erkennung + Pull-Source Routing
- RT-Param-Ensure für CLAP Parameter

### Plugin Browser: CLAP Tab
- Eigener Tab mit Favoriten, Drag&Drop, Suche
- Status-Hints bei Scan und Insert

### Device Panel: CLAP Metadata
- `__ext_ref`, `__ext_path`, `__ext_plugin_name` Normalisierung

### ClapAudioFxWidget
- Slider + SpinBox für alle CLAP Parameter
- RT-Param-Sync + Project-Persistenz

### Audio Engine: CLAP Instrument Engines
- `ClapInstrumentEngine` in Phase 1/2/3 des Instrument-Creation-Flow
