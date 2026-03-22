# CHANGELOG v0.0.20.718 — P7 IPC Integration + Warning Fixes

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox Phase P7 — IPC Integration

## Was wurde gemacht

### Rust: Plugin-Hosting komplett verdrahtet (engine.rs)
- `ScanPlugins` Command → ruft alle 3 Scanner auf (VST3/CLAP/LV2)
- `LoadPlugin` Handler → instanziiert echte Vst3Instance/ClapInstance/Lv2Instance
- `UnloadPlugin` → Plugin aus Slot entfernen
- `SetPluginParam` → Parameter an geladenes Plugin weiterleiten
- `SavePluginState` → State als Base64 zurücksenden
- `LoadPluginState` → State aus Base64 laden
- **Ersetzt den alten Stub** ("Plugin commands not yet implemented")

### Rust: TrackNode Plugin-Slots (audio_graph.rs)
- Neues Feld `plugin_slots: Vec<PluginSlot>` auf TrackNode
- Signal-Flow: Instrument → External Plugins → Built-in FX Chain → Volume/Pan
- Slots werden dynamisch bei LoadPlugin erstellt

### Rust: IPC-Protokoll erweitert (ipc.rs)
- `ScanPlugins` Command (neu)
- `LoadPlugin.plugin_id` Feld (neu, #[serde(default)] für Backward-Compat)
- `PluginScanResult` Event mit `Vec<ScannedPlugin>`
- `PluginLoaded` Event (Name, Format, Param-Count, Latency)
- `ScannedPlugin` Struct (einheitliches Format für VST3/CLAP/LV2)

### Rust: Base64 Encode (clip_renderer.rs)
- `base64_encode()` Funktion für State-Blob Serialisierung
- Matching-Funktion zur bestehenden `base64_decode()`

### Rust: Warning-Fixes (v717 → v718)
- `vst3_host.rs`: unused `warn` import entfernt
- `lv2_host.rs`: unused `PathBuf`, `Symbol`, `debug` imports entfernt
- `lv2_host.rs`: `is_output` → `_is_output` (unused variable)

### Python: Bridge-Methoden (rust_engine_bridge.py)
- `scan_plugins()` → sendet ScanPlugins Command
- `load_plugin(track_id, slot, path, format, plugin_id)`
- `unload_plugin(track_id, slot)`
- `set_plugin_param(track_id, slot, param_index, value)`
- `save_plugin_state(track_id, slot)`
- `load_plugin_state(track_id, slot, state_b64)`
- Qt Signals: `plugin_scan_result`, `plugin_loaded`
- Event-Dispatch für PluginScanResult + PluginLoaded

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw_engine/src/engine.rs` | Plugin-Command Handler (ScanPlugins, Load/Unload/Param/State) |
| `pydaw_engine/src/audio_graph.rs` | plugin_slots Feld + Signal-Flow Integration |
| `pydaw_engine/src/ipc.rs` | ScanPlugins, PluginScanResult, PluginLoaded, ScannedPlugin |
| `pydaw_engine/src/clip_renderer.rs` | base64_encode() Funktion |
| `pydaw_engine/src/vst3_host.rs` | Warning-Fix (unused import) |
| `pydaw_engine/src/lv2_host.rs` | Warning-Fixes (3 unused imports + 1 variable) |
| `pydaw/services/rust_engine_bridge.py` | 6 Plugin-Methoden + 2 Signals + 2 Event-Handler |
| `VERSION` | 0.0.20.718 |
| `pydaw/version.py` | __version__ aktualisiert |

## Nächste Schritte
- `cargo build --release` auf Zielmaschine
- Test: `USE_RUST_ENGINE=1 python3 main.py` → `bridge.scan_plugins()`
- Test: `bridge.load_plugin("track_0", 0, "/path/to/plugin.vst3", "vst3")`
- GUI-Integration: Plugin-Browser zeigt Rust-Scanner Ergebnisse
