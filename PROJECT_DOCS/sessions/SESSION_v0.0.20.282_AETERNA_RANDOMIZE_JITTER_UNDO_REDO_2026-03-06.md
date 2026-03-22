# Session v0.0.20.282 — AETERNA Randomize/Jitter + Undo/Redo light

**Date:** 2026-03-06  
**Author:** GPT-5.4 Thinking

## Goal
Add the next safe local AETERNA-MSEG step: bounded Randomize/Jitter plus a light Undo/Redo history, without touching the DAW core or other instruments.

## Implemented

- Added bounded local `randomize_mseg()` in `aeterna_engine.py`.
- Added bounded local `jitter_mseg()` with point-order protection.
- Added local MSEG history helpers, `undo_mseg()`, `redo_mseg()`, and small history status reporting.
- Updated AETERNA widget toolbar with `Randomize`, `Jitter`, `Undo`, and `Redo`.
- Added per-track persistence for Randomize/Jitter UI amount selectors.
- Improved drag handling to snapshot history once before point movement.

## Safety

- Only AETERNA files changed.
- No Arranger / Clip Launcher / Audio Editor / Mixer / playback core changes.

## Validation

- `python -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Direct engine smoke tests for:
  - `randomize_mseg()`
  - `jitter_mseg()`
  - `undo_mseg()`
  - `redo_mseg()`
