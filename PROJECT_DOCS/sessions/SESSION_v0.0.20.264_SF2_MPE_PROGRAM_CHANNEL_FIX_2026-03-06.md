# Session v0.0.20.264 — SF2 MPE Program Channel Fix

## Task
Fix regression where SF2 micropitch/MPE no longer worked reliably, without breaking the new visible FX automation slider behavior.

## Root Cause
Deep analysis of the current ZIP showed that SF2 MIDI rendering selected the bank/preset only on channel 0, while micropitch/MPE notes were emitted on channels 1..15 for per-note pitchwheel.
That means pitched notes could render on channels that never received the intended SF2 program selection.

## Safe Fix
- Bank/program init on channels 0..15
- Render hash bump to invalidate stale cache WAVs

## Validation
- `python3 -m py_compile pydaw/audio/midi_render.py`
