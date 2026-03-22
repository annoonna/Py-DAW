# CHANGELOG v0.0.20.630 — Rust Audio-Engine Phase 1A (Skeleton + IPC Bridge)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP 1 (Rust/C++ Audio-Core), Phase 1A

## Was wurde gemacht

### Rust Audio-Engine (`pydaw_engine/`)
- **Cargo-Projekt** mit allen Dependencies: `cpal` (Audio I/O), `crossbeam` (Lock-Free), `rmp-serde` (MessagePack), `tokio`, `atomic_float`, `parking_lot`
- **IPC-Protokoll** (`ipc.rs`): Vollständige Command/Event-Definitionen mit serde-Serialisierung
  - Commands: Play, Stop, Pause, Seek, SetTempo, SetTimeSignature, SetLoop, AddTrack, RemoveTrack, SetTrackParam, SetGroupRouting, Configure, LoadAudioClip, SetArrangement, LoadPlugin, MidiNoteOn/Off/CC, Ping, Shutdown
  - Events: PlayheadPosition, TransportState, MeterLevels, MasterMeterLevel, Pong, Error, PluginCrash, PluginState, Ready, ShuttingDown
  - Frame-Format: `[u32 LE Länge][MessagePack Payload]`
- **Audio-Graph** (`audio_graph.rs`): Vollständiger Echtzeit-Audiograph
  - `AudioBuffer`: Stereo-Buffer mit mix/gain/pan/peak/rms Operationen
  - `TrackNode`: Atomare Parameter (Volume/Pan/Mute/Solo), pre-allokierte Buffer
  - `AudioGraph`: Topologische Sortierung, Group-Bus-Routing, Solo-Logik, Soft-Limiter
  - Keine Heap-Allokationen im `process()` Hot Path
- **Transport** (`transport.rs`): Lock-free Playback-Steuerung
  - Atomare BPM/Position/Loop-Parameter (Audio-Thread-sicher)
  - Beat↔Sample Konvertierung, Loop-Wraparound
- **Plugin Host** (`plugin_host.rs`): Trait-Definition + Sine-PoC
  - `AudioPlugin` Trait: process, set_parameter, save/load_state, latency
  - `SineGenerator`: 440Hz Proof-of-Concept (Phase 1A Demo)
  - `PluginSlot`: Slot-Management für Track-Plugin-Chains
- **Engine** (`engine.rs`): Koordiniert Graph, Transport, IPC
  - Command-Queue-Drain (max 64/callback, starvation-sicher)
  - Metering-Events ~30Hz
  - XRun-Counter
- **Main** (`main.rs`): Entry Point mit cpal Audio-Stream + Unix Socket Server
  - CLI-Argumente: `--socket`, `--sr`, `--buf`
  - IPC Reader/Writer Threads
  - PoC Setup: Sine-Generator auf Track 1 → Master

### Python Bridge (`pydaw/services/rust_engine_bridge.py`)
- **Singleton** `RustEngineBridge` Klasse
- Subprocess-Management (Start, Monitor, Health-Check, Shutdown)
- Unix Domain Socket IPC (MessagePack + JSON-Fallback)
- Frame-Encoding/Decoding (length-prefixed)
- Typed Convenience-Methoden: `play()`, `stop()`, `seek()`, `set_tempo()`, etc.
- PyQt6-Signale für GUI-Integration: playhead, meters, transport, errors
- Feature-Flag: `USE_RUST_ENGINE=1` (Default: Python-Engine)
- Engine-Binary Auto-Discovery (PATH, env, known locations)
- Background Reader-Thread für Events
- Health-Check Timer (5s Ping-Interval)

### Dokumentation
- `pydaw_engine/README.md`: Build-Anleitung, Architektur, Troubleshooting
- `pydaw_engine/test_bridge.py`: Manueller + automatischer IPC Test-Client

## Geänderte / Neue Dateien

| Datei | Änderung |
|---|---|
| `pydaw_engine/Cargo.toml` | NEU: Rust-Projekt mit Dependencies |
| `pydaw_engine/src/main.rs` | NEU: Entry Point, Audio-Stream, IPC Server |
| `pydaw_engine/src/ipc.rs` | NEU: Command/Event IPC-Protokoll |
| `pydaw_engine/src/audio_graph.rs` | NEU: Echtzeit Audio-Graph |
| `pydaw_engine/src/transport.rs` | NEU: Lock-free Transport |
| `pydaw_engine/src/plugin_host.rs` | NEU: Plugin Trait + Sine PoC |
| `pydaw_engine/src/engine.rs` | NEU: Engine-Koordination |
| `pydaw_engine/README.md` | NEU: Build & Setup Doku |
| `pydaw_engine/test_bridge.py` | NEU: IPC Test-Client |
| `pydaw/services/rust_engine_bridge.py` | NEU: Python↔Rust Bridge |
| `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` | Phase 1A abgehakt |
| `VERSION` | 0.0.20.629 → 0.0.20.630 |

## Was als nächstes zu tun ist
- **Phase 1B — Audio-Graph in Rust** (nächster Kollege):
  - `AudioNode` Trait erweitern: Audio-Clip Rendering
  - Arrangement-State in Rust laden
  - ALSA/PipeWire Backend via cpal testen (ggf. JACK-Backend)
  - Lock-Free Parameter-Updates testen
  - Metering: Peak/RMS korrekt pro Track → Python via IPC
- **Erstmal:** `cargo build --release` auf Zielmaschine ausführen und PoC testen

## Bekannte Einschränkungen
- Rust-Compilation nicht in CI-Umgebung möglich (kein rustc) — muss auf Zielmaschine gebaut werden
- Phase 1A ist Skeleton — kein Audio-Clip-Rendering, kein Plugin-Hosting, kein MIDI
- Sine-PoC schreibt statisch in den Buffer (nicht per-Callback-Regenerierung im AudioGraph)
- Single-Client: Nur eine Python-Verbindung gleichzeitig
- `engine.rs` nutzt `Mutex` für `AudioGraph` — in Phase 1B auf Lock-Free umstellen
