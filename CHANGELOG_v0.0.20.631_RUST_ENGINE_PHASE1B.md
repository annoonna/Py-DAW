# CHANGELOG v0.0.20.631 — Rust Audio-Engine Phase 1B (AudioNode + ClipRenderer + Lock-Free)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP 1 (Rust/C++ Audio-Core), Phase 1B

## Was wurde gemacht

### AudioNode Trait (`src/audio_node.rs`)
- **`AudioNode` Trait** mit `process()`, `node_id()`, `node_name()`, `latency_samples()`, `tail_samples()`, `prepare()`, `release()`
- **`ProcessContext`** Struct: frames, sample_rate, position, bpm, time_sig — wird jedem Node pro Cycle übergeben
- **Built-in Nodes:**
  - `GainNode` — einfache Lautstärke-Steuerung
  - `SilenceNode` — Stille-Generator (Placeholder)
  - `SineNode` — Sine-Wave mit Frequency/Amplitude (PoC, transport-aware: Stille wenn nicht playing)
  - `MixNode` — Summen-Bus (Marker-Node für Topologie)

### Lock-Free Ring Buffers (`src/lock_free.rs`)
- **`ParamRing`** — SPSC Lock-Free Ring (4096 Entries)
  - `push(param_id, value)` vom GUI-Thread (wait-free)
  - `drain(callback)` vom Audio-Thread (lock-free)
  - Overflow: älteste Werte werden überschrieben
  - Encoding: param_id = (track_index << 16) | param_type
- **`AudioRing`** — Stereo Audio-Ring für Input-Monitoring / Bounce
  - Power-of-2 Kapazität, lock-free write/read
- **`MeterRing`** — Triple-Buffer für Meter-Daten (Audio → GUI)
  - `write_track()` + `commit()` vom Audio-Thread
  - `read_all()` vom GUI-Thread (immer konsistenter Snapshot)

### Clip Renderer (`src/clip_renderer.rs`)
- **`AudioClipData`** — Audio-Daten mit base64 Import, stereo frame access
  - `from_base64()` für IPC (LoadAudioClip Command)
  - `get_stereo_frame()` inline, mono→stereo Duplikation
- **`ClipStore`** — RwLock<HashMap> für Thread-sichere Clip-Verwaltung
  - `insert()`, `remove()`, `get()` — IPC schreibt, Audio liest
- **`PlacedClip`** — Clip-Platzierung mit beat→sample Konvertierung
  - `from_ipc()` konvertiert ArrangementClip → PlacedClip
- **`ArrangementSnapshot`** — Immutable, atomic swappable
  - Clips sortiert nach start_sample (binary search ready)
  - Pre-computed `clips_by_track` Index für O(1) Track-Lookup
- **`ArrangementRenderer`** — Rendert Clips in Track-Buffers
  - `render_track()` — per-Track mit Sample-Rate Konvertierung (Linear Interpolation)
  - `render_all_tracks()` — iteriert alle Tracks mit Clips
  - Additive Mischung (mehrere Clips pro Track)
  - Gain-Multiplikator pro Clip

### Engine Integration (`src/engine.rs`)
- **ParamRing** integriert: `drain()` am Anfang jedes Audio-Callbacks
- **ClipStore + ArrangementRenderer** integriert in EngineState
- **LoadAudioClip** Command: base64 decode → ClipStore
- **SetArrangement** Command: beat→sample Konvertierung → ArrangementSnapshot
- **process_audio()** erweitert: drain params → render clips → process graph → output

### Python Bridge Erweiterungen (`pydaw/services/rust_engine_bridge.py`)
- `load_audio_clip()` — Raw f32 LE PCM Bytes laden
- `load_audio_clip_from_numpy()` — numpy Array direkt laden
- `set_arrangement()` — Clip-Positionen setzen (beat-basiert)
- `set_track_param_ring()` — Parameter via Ring-Encoding

### Architektur-Dokument
- `PROJECT_DOCS/features/RUST_ENGINE_ARCHITECTURE.md` — Vollständige Design-Doku

## Geänderte / Neue Dateien

| Datei | Änderung |
|---|---|
| `pydaw_engine/src/audio_node.rs` | NEU: AudioNode Trait + Built-in Nodes |
| `pydaw_engine/src/lock_free.rs` | NEU: ParamRing, AudioRing, MeterRing |
| `pydaw_engine/src/clip_renderer.rs` | NEU: ClipStore, ArrangementRenderer |
| `pydaw_engine/src/engine.rs` | Erweitert: ParamRing, ClipStore, Renderer |
| `pydaw_engine/src/main.rs` | Module registriert, PoC aktualisiert |
| `pydaw_engine/src/audio_graph.rs` | buffer_size() Getter |
| `pydaw/services/rust_engine_bridge.py` | Audio-Clip + Arrangement Methoden |
| `PROJECT_DOCS/features/RUST_ENGINE_ARCHITECTURE.md` | NEU: Design-Doku |
| `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` | Phase 1B abgehakt |
| `VERSION` | 0.0.20.630 → 0.0.20.631 |

## Was als nächstes zu tun ist
- **`cargo build --release`** auf Zielmaschine (Rust muss installiert sein)
- **Phase 1C — Plugin-Hosting in Rust**: VST3 via vst3-sys, CLAP via clack-host
- **Phase 1D — Migration**: Feature-Flag, Fallback, Performance-Vergleich

## Bekannte Einschränkungen
- `AudioGraph` nutzt noch `Mutex` — in Produktion durch atomaren Referenz-Swap ersetzen
- `clip_renderer.rs` nutzt `vec![]` in `render_all_tracks()` — Scratch-Buffer pre-allokieren
- Base64-Decoder ist minimalistisch (kein Padding-Validation)
- Kein MIDI-Dispatch in Rust (bleibt vorerst in Python)
