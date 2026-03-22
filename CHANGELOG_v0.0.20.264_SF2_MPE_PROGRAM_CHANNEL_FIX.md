# v0.0.20.264 — SF2 MPE Program Channel Fix

Safe hotfix for SF2 micropitch/MPE playback without touching the working FX automation path.

## Problem
In SF2 rendering, bank/program selection was only sent on MIDI channel 0.
Micropitch/MPE notes were routed to channels 1..15 for per-note pitchwheel, so those notes could play with the wrong/default patch.
This made SF2 micropitch appear broken or inconsistent.

Additionally, already rendered stale cache WAVs could survive across code updates.

## Fix
- Initialize SF2 bank/program on all 16 MIDI channels before rendering.
- Add a render-format tag to the MIDI content hash so old broken SF2 cache files are invalidated automatically.

## Files
- `pydaw/audio/midi_render.py`
