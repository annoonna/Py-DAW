# Session Log — v0.0.20.716

**Datum:** 2026-03-21
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox P7A, P7B, P7C
**Aufgabe:** Rust Native Plugin Hosting — Stubs durch echte FFI Implementierungen ersetzen

## Was wurde erledigt

### P7A — VST3 Host (vst3_host.rs, 780 Zeilen)
- Komplett neu geschrieben mit Raw COM vtables + libloading
- Kein vst3-sys/vst3-com Crate nötig — eigene struct Definitionen
- Scanner: dlopen .vst3 Bundles → GetPluginFactory → PClassInfo enumerate
- Instance: createInstance(IComponent) → QI(IAudioProcessor) → QI(IEditController)
- Separate Controller Support (getControllerClassId → eigene Instanz)
- Setup: initialize → setupProcessing → activateBus → setActive → setProcessing
- Process: Deinterleave AudioBuffer → ProcessData → IAudioProcessor::process → Reinterleave
- Parameter Discovery: IEditController::getParameterCount/Info/Normalized
- Latency + Tail Samples via IAudioProcessor vtable

### P7B — CLAP Host (clap_host.rs, 782 Zeilen)
- Komplett neu geschrieben mit Raw C API Structs + libloading
- ClapHost struct mit allen Callbacks (get_extension, request_restart/process/callback)
- Scanner: dlopen → clap_entry.init() → get_factory → get_plugin_count/descriptor
- Instance: create_plugin → init → activate → start_processing
- Process: ClapAudioBuffer + ClapProcess + Empty Event Lists
- Params Extension: count, get_info, get_value, flush
- State Extension: save/load stream stubs (TODO: ClapI/OStream impl)
- Feature-Tag Parsing für is_instrument()/is_effect()

### P7C — LV2 Host (lv2_host.rs, 660 Zeilen)
- Komplett neu geschrieben mit dynamischem lilv FFI
- liblilv-0.so wird zur Runtime via libloading geladen (OnceLock Singleton)
- Graceful Degradation: kein lilv → leere Ergebnisse, kein Crash
- 20+ lilv Funktionspointer via macro sicher geladen
- Scanner: world_new → load_all → iterate plugins → Port-Analyse
- Port Types: Audio, Control, Atom mit Direction (Input/Output)
- Instance: instantiate → connect_port → activate → run
- Control Ports: HashMap<u32, f32>, connect_port zeigt auf unsere Values
- Parameter: control input ports als sequentieller param_map

### Infrastruktur
- Cargo.toml: `libloading = "0.8"` als einzige neue Dependency
- Alte Stub-Kommentare (vst3-com, clap-sys, pkg-config) entfernt
- Alle 3 Hosts implementieren AudioPlugin Trait identisch

## Geänderte Dateien
- `pydaw_engine/src/vst3_host.rs` — 780 Zeilen (komplett neu)
- `pydaw_engine/src/clap_host.rs` — 782 Zeilen (komplett neu)
- `pydaw_engine/src/lv2_host.rs` — 660 Zeilen (komplett neu)
- `pydaw_engine/Cargo.toml` — libloading dependency
- `VERSION` — 0.0.20.716
- `pydaw/version.py` — __version__ aktualisiert
- `PROJECT_DOCS/PLUGIN_SANDBOX_ROADMAP.md` — P7A/B/C abgehakt
- `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` — Nächste Aufgabe aktualisiert
- `PROJECT_DOCS/progress/TODO.md` — v716 Einträge
- `PROJECT_DOCS/progress/DONE.md` — v716 Einträge

## Architektur-Entscheidungen
1. **libloading statt vst3-sys/clap-sys**: Volle Kontrolle über vtable Layouts,
   keine Dependency auf halb-maintained Crates, identische Strategie für alle 3 Formate
2. **Raw COM Structs**: Die VST3 COM ABI ist stabil und dokumentiert.
   Unsere eigenen struct-Definitionen sind leichtgewichtiger als vst3-com.
3. **Dynamic lilv**: Statt build.rs/pkg-config laden wir liblilv zur Runtime.
   Wenn nicht installiert → LV2 deaktiviert, alles andere funktioniert.
4. **Pre-allokierte Deinterleave-Buffers**: Vermeidet Heap-Allokation im Audio-Thread.
   resize() nur wenn Block-Size sich ändert.

## Nächste Schritte
1. `cargo build --release` — Kompilierbarkeit auf Zielmaschine prüfen
2. VST3 IBStream/MemoryStream für State Save/Load
3. CLAP MIDI Event Injection (clap_event_note in clap_input_events)
4. LV2 Atom Port MIDI + LV2 State Interface
5. Live-Test mit echten Plugins (Surge XT CLAP, Vital VST3, Calf LV2)
6. Integration mit engine.rs: LoadPlugin Command → passenden Host instanziieren

## Offene Fragen an den Auftraggeber
- Keine — P7 ist als OPTIONAL markiert, der Core-Pfad läuft weiter über Python-Sandbox
