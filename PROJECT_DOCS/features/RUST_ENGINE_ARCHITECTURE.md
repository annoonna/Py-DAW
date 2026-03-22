# Rust Audio Engine — Architektur-Design

**Version:** v0.0.20.631
**Status:** Phase 1A ✅ | Phase 1B ✅ (Skeleton) | Phase 1C ⬜ | Phase 1D ⬜

## Übersicht

```
┌──────────────────────────────────────────────────────────────┐
│  Python/PyQt6 GUI                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  RustEngineBridge (Singleton)                         │   │
│  │  ├─ send_command()    → Unix Socket →                 │   │
│  │  ├─ _reader_thread    ← Unix Socket ←                 │   │
│  │  ├─ PyQt6 Signals: playhead, meters, transport        │   │
│  │  └─ Feature-Flag: USE_RUST_ENGINE=1                   │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬──────────────────────────────────┘
                            │ Unix Domain Socket
                            │ Frame: [u32 LE len][MessagePack]
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Rust Audio Engine (eigener Prozess)                         │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  IPC Server  │  │  EngineState  │  │  Audio Thread    │   │
│  │  (reader/    │──│  ├ Transport  │──│  (cpal callback) │   │
│  │   writer)    │  │  ├ AudioGraph │  │  ├ drain cmds    │   │
│  └─────────────┘  │  ├ ClipStore  │  │  ├ render clips   │   │
│                    │  ├ Renderer   │  │  ├ process graph  │   │
│                    │  └ ParamRing  │  │  └ output to dev  │   │
│                    └──────────────┘  └──────────────────┘   │
│                                              │               │
│                                     ALSA / PipeWire / JACK   │
└──────────────────────────────────────────────────────────────┘
```

## Dateistruktur

```
pydaw_engine/
├── Cargo.toml              ← Dependencies, Build-Config
├── README.md               ← Build & Setup Anleitung
├── test_bridge.py          ← IPC Test-Client
└── src/
    ├── main.rs             ← Entry Point, cpal Stream, IPC Server
    ├── engine.rs           ← EngineState: koordiniert alles
    ├── audio_graph.rs      ← AudioGraph, TrackNode, AudioBuffer
    ├── audio_node.rs       ← AudioNode Trait, GainNode, SineNode
    ├── clip_renderer.rs    ← ClipStore, ArrangementRenderer
    ├── ipc.rs              ← Command/Event Protokoll (serde)
    ├── lock_free.rs        ← ParamRing, AudioRing, MeterRing
    ├── plugin_host.rs      ← AudioPlugin Trait, PluginSlot
    └── transport.rs        ← Atomare Transport-Steuerung
```

## Thread-Modell

| Thread | Aufgabe | Regeln |
|--------|---------|--------|
| **Audio** (cpal) | process_audio() | KEINE Allokationen, KEINE Locks, KEINE Syscalls |
| **IPC Reader** | Commands lesen | Darf in Command-Queue schreiben (crossbeam) |
| **IPC Writer** | Events senden | Liest aus Event-Queue (crossbeam) |
| **Main** | Startup, Socket | Wartet auf Client-Verbindung |

## Lock-Free Design

```
GUI Thread (Python)
    │
    ├── send_command() → crossbeam channel → Audio Thread
    │                                         ↓
    │                                    drain_commands()
    │
    ├── ParamRing.push(id, val) ──────→ ParamRing.drain()
    │   (lock-free SPSC)                (audio callback)
    │
    └── ← Event channel ← MeterLevels, PlayheadPosition
```

### Warum crossbeam + ParamRing?

- **crossbeam channel**: Für seltene strukturierte Commands (Play, AddTrack, LoadClip)
- **ParamRing**: Für hochfrequente Parameter-Updates (Fader, Knobs bei 8Hz+)
  - SPSC (Single Producer, Single Consumer)
  - Keine Locks, keine Syscalls
  - Overflow: älteste Werte gehen verloren (neuer Wert überschreibt)

## IPC-Protokoll

### Frame-Format
```
[4 Bytes: u32 LE Payload-Länge][N Bytes: MessagePack Payload]
```

### Commands (Python → Rust)
| Command | Felder | Beschreibung |
|---------|--------|--------------|
| Play | — | Playback starten |
| Stop | — | Stopp + Reset |
| Pause | — | Pause (Position behalten) |
| Seek | beat: f64 | Zu Beat-Position springen |
| SetTempo | bpm: f64 | Tempo setzen |
| AddTrack | track_id, track_index, kind | Track hinzufügen |
| SetTrackParam | track_index, param, value | Vol/Pan/Mute/Solo |
| LoadAudioClip | clip_id, channels, sr, b64 | Audio-Daten laden |
| SetArrangement | clips[] | Clip-Positionen setzen |
| Ping | seq | Health-Check |
| Shutdown | — | Beenden |

### Events (Rust → Python)
| Event | Felder | Frequenz |
|-------|--------|----------|
| PlayheadPosition | beat, sample_pos, playing | ~30Hz |
| MasterMeterLevel | peak_l/r, rms_l/r | ~30Hz |
| MeterLevels | levels[] | ~30Hz |
| TransportState | playing, beat | Bei Änderung |
| Ready | sr, buf, device | Nach Configure |
| Pong | seq, cpu_load, xruns | Auf Ping |
| Error | code, message | Bei Fehler |

## Audio-Graph Architektur

```
Track 1 (Instrument) ──┐
Track 2 (Audio) ────────┤── Group A ──┐
Track 3 (Audio) ────────┘             │
                                      ├── Master Bus → Soft Limiter → Output
Track 4 (Instrument) ─────────────────┘
Track 5 (FX Return) ─────────────────────────────────┘
```

### Topologische Sortierung
1. Reguläre Tracks (Audio, Instrument, FX Return)
2. Group Tracks
3. Master Bus (immer zuletzt)

### Pro Track:
- Pre-allokierter AudioBuffer (Stereo, frames × 2)
- Atomare Parameter: Volume, Pan, Mute, Solo
- Optional: Group-Routing → anderer Track statt Master

## Clip Rendering

```
ClipStore (RwLock<HashMap<String, Arc<AudioClipData>>>)
    │
    │ get(clip_id) → Arc<AudioClipData>  (lock-free read)
    │
ArrangementRenderer
    │
    │ ArrangementSnapshot (Arc, atomic swap)
    │   └─ clips_by_track: HashMap<u16, Vec<PlacedClip>>
    │
    └─ render_track(track_idx, output, position, frames, sr)
        ├─ Binary search: welche Clips überlappen diesen Buffer?
        ├─ Sample-Rate Konvertierung (linear interpolation)
        ├─ Gain-Multiplikator pro Clip
        └─ Additive Mischung (mehrere Clips pro Track)
```

## Nächste Schritte

### Phase 1C — Plugin-Hosting
- VST3 via `vst3-sys` Crate
- CLAP via `clack-host` Crate
- Plugin in eigenem Thread (Crash-Isolation)

### Phase 1D — Migration
- Feature-Flag `USE_RUST_ENGINE=1` schaltet um
- Python-Engine bleibt als Fallback
- Schrittweise: erst Playback, dann MIDI, dann Plugins
