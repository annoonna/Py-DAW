# CHANGELOG v0.0.20.14 — Hybrid Engine Phase 2

**Datum:** 2026-02-08 | **Autor:** Claude Opus 4.6 | **Basis:** v0.0.20.13

## Neue Features

### 1. Per-Track Volume/Pan/Mute/Solo via ParamRingBuffer
- `TrackParamState`: Pre-allokierter Cache (128 Tracks), zero-alloc
- `drain_into()`: Track-Params → TrackParamState, Master → Iterator
- IIR Smoothing + Solo-Logik (any_solo Flag)

### 2. JACK Integration via HybridAudioCallback
- `render_for_jack()` als Primary in AudioEngine JACK-Pfad
- Preview + Arrangement Playback, DSP-Engine als Fallback

### 3. WaveformGLRenderer als ArrangerCanvas Overlay
- `ArrangerGLOverlay`: OpenGL über ArrangerCanvas (mouse pass-through)
- 60fps Viewport-Sync, QPainter Fallback

### 4. Essentia Worker Pool mit Prio-Queue
- 4 Priority-Level (CRITICAL/HIGH/NORMAL/LOW)
- LRU Cache (256 MB), Dedup, Generation-based Cancellation

### 5. SharedMemory Backing für Ring Buffer
- `ParamRingBuffer(shm_name="...")` + `AudioRingBuffer(shm_name="...")`
- Multi-Process Ready, graceful Fallback

### 6. Hybrid als Default für sounddevice Arrangement
- HybridAudioCallback als Primary sounddevice Callback
- Legacy als automatischer Fallback

## Dateien
| Datei | Status |
|-------|--------|
| `pydaw/audio/ring_buffer.py` | GEÄNDERT (+TrackParamState, +SharedMemory) |
| `pydaw/audio/hybrid_engine.py` | GEÄNDERT (+per-track, +JACK, +read_track_peak) |
| `pydaw/audio/audio_engine.py` | GEÄNDERT (import fix) |
| `pydaw/audio/essentia_pool.py` | **NEU** |
| `pydaw/ui/arranger_gl_overlay.py` | **NEU** |

## Tests: 🎉 ALLE BESTANDEN
