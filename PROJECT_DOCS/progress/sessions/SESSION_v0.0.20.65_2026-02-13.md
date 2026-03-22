# Session Log — v0.0.20.65 (2026-02-13)

## Context
User reported: **SF2 is audible**, but **Pro Audio Sampler** and **Pro Drum Machine** are silent.

Root cause (MVP):
- Sampler/Drum engines were created with `target_sr=48000` hardcoded.
- The audio engine can run at **44.1kHz** (or any configured SR). In that case, `pull(..., sr=44100)` in the engines rejected SR mismatch and returned `None` → silent output.

## Changes
### 1) AudioEngine helper
- Added `AudioEngine.get_effective_sample_rate()`
  - Uses current running config SR if available, otherwise reads from Settings (default 48k).

### 2) Pro Sampler
- `SamplerWidget` now initializes `ProSamplerEngine(target_sr=<effective_sr>)`.
- `SamplerWidget.shutdown()` now deregisters from `SamplerRegistry` (avoid stale routing).

### 3) Pro Drum Machine
- `DrumMachineWidget` now initializes `DrumMachineEngine(target_sr=<effective_sr>)`.
- Registers the engine into `SamplerRegistry` on `set_track_context()` so PianoRoll/Notation note preview routes correctly.
- Deregisters from `SamplerRegistry` on shutdown.

## Files changed
- `pydaw/audio/audio_engine.py`
- `pydaw/plugins/sampler/sampler_widget.py`
- `pydaw/plugins/drum_machine/drum_widget.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/progress/LATEST.md`, `PROJECT_DOCS/progress/DONE.md`, `PROJECT_DOCS/progress/TODO.md`

## Version
- Bump: `0.0.20.64` → `0.0.20.65`

## Notes
If JACK is enabled via env var but no server is running, you will see:
"JACK client enabled, but JACK server is not reachable".
This does **not** prevent sounddevice playback; it only affects JACK-specific services.
