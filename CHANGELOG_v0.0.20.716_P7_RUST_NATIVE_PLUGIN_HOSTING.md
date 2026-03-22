# CHANGELOG v0.0.20.716 — Rust Native Plugin Hosting (P7A/P7B/P7C)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox Phase P7A, P7B, P7C

## Was wurde gemacht

### P7A — VST3 Native Host (780 Zeilen)
- `vst3_host.rs` komplett neu geschrieben mit echtem FFI via `libloading`
- Raw COM vtable Structs: FUnknown, IPluginFactory, IComponent, IAudioProcessor, IEditController
- Scanner: dlopen → GetPluginFactory → PClassInfo Enumeration (x86_64 + aarch64)
- Instance: createInstance → QueryInterface → setupProcessing → setActive
- Audio: Deinterleave → process(ProcessData) → Reinterleave (pre-allokierte Buffers)
- Parameter: discover_parameters() via IEditController, getParamNormalized/setParamNormalized
- Separate Controller Support (IComponent ≠ IEditController, getControllerClassId)
- Latency + Tail Samples Reporting

### P7B — CLAP Native Host (782 Zeilen)
- `clap_host.rs` komplett neu geschrieben mit echtem FFI via `libloading`
- Raw C API Structs: clap_plugin_entry, clap_plugin_factory, clap_plugin, clap_process
- ClapHost struct mit Callback-Stubs (get_extension, request_restart/process/callback)
- Scanner: dlopen → clap_entry.init → get_factory → get_plugin_descriptor
- Instance: create_plugin → init → activate → start_processing
- Audio: ClapAudioBuffer + ClapProcess + empty Input/Output Event Lists
- Extensions: clap_plugin_params (count, get_info, get_value, flush)
- Extensions: clap_plugin_state (save/load stream stubs)
- Feature-Tag Parsing (is_instrument, is_effect)

### P7C — LV2 Native Host (660 Zeilen)
- `lv2_host.rs` komplett neu geschrieben mit dynamischem lilv FFI
- Runtime-Loading: liblilv-0.so via libloading + OnceLock (kein build.rs nötig)
- Graceful Degradation: wenn lilv nicht installiert → leere Scan-Ergebnisse, kein Crash
- LilvApi struct: 20+ Funktionspointer, sicher via macro geladen
- Scanner: lilv_world_load_all → iterate plugins → Port-Analyse (Audio/Control/Atom)
- Instance: instantiate → connect_port → activate → run
- Port-System: PortInfo mit Direction + Type, Control-Ports via HashMap
- Parameter: control input ports als param_map, get/set via f32 values

### Infrastruktur
- `Cargo.toml`: `libloading = "0.8"` als einzige neue Dependency
- Kein vst3-sys, kein clap-sys, kein pkg-config — alles über Raw FFI + libloading
- Alle 3 Hosts implementieren das `AudioPlugin` Trait (process, params, state)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw_engine/src/vst3_host.rs` | Komplett neu: Real VST3 FFI (780 Z.) |
| `pydaw_engine/src/clap_host.rs` | Komplett neu: Real CLAP FFI (782 Z.) |
| `pydaw_engine/src/lv2_host.rs` | Komplett neu: Real LV2/lilv FFI (660 Z.) |
| `pydaw_engine/Cargo.toml` | +libloading, alte Stub-Kommentare entfernt |
| `VERSION` | 0.0.20.716 |
| `pydaw/version.py` | __version__ = "0.0.20.716" |
| `PROJECT_DOCS/PLUGIN_SANDBOX_ROADMAP.md` | P7A/P7B/P7C abgehakt |
| `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` | Nächste Aufgabe aktualisiert |

## Was als nächstes zu tun ist
- `cargo build --release` auf Zielmaschine (libloading muss crates.io erreichen)
- VST3 IBStream Implementierung für State Save/Load (MemoryStream)
- CLAP MIDI Event Injection (clap_event_note + clap_input_events)
- LV2 Atom Port MIDI + LV2 State Interface
- Live-Test mit echten Plugins: `USE_RUST_ENGINE=1 python3 main.py`

## Bekannte Einschränkungen
- VST3 State Save/Load noch nicht implementiert (braucht IBStream/MemoryStream)
- CLAP Parameter-Änderungen: flush() ohne echte Event-Injection
- LV2 Atom Ports (MIDI) noch nicht verbunden
- Kein Rust-Compiler in Container → nicht kompilierbar getestet
- Python-Code: 303 .py Dateien kompilieren fehlerfrei ✅
