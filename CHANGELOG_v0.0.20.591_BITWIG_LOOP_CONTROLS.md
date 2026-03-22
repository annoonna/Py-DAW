# v0.0.20.591 — Clip Launcher: Bitwig-Style Loop Controls

**Date:** 2026-03-18
**Author:** Claude Opus 4.6

## Problem

MIDI clips in the Clip Launcher could not be looped with custom length.
The "Länge" spinbox in the inspector was writing to `length_beats` (clip total
length) instead of `loop_end_beats` (loop region end). Users couldn't control
loop start or loop region length independently.

## Fix: Bitwig-Style Loop Region Controls

### Inspector (`clip_launcher_inspector.py`)
- **Loop Start spinbox**: new editable spinbox for `loop_start_beats` (was: static label)
- **Loop Länge spinbox**: now controls `loop_end_beats = loop_start + val` (was: writing `length_beats`)
- **Clip Länge spinbox**: new separate control for `length_beats` (total clip length)
- **Enable/Disable**: Loop Start + Loop Länge spinboxes grey out when Loop checkbox is off
- **Orange styling**: Loop controls use Bitwig-orange color

### Bitwig Behavior Now Correct:
1. Check "Loop" → enables loop with full clip length as default
2. Adjust "Loop Start" → moves loop region start within the clip
3. Adjust "Loop Länge" → controls how long the loop region is (e.g. 2 beats = short loop)
4. Adjust "Länge" → changes total clip length (independent of loop)
5. Playback loops within [loop_start, loop_start + loop_length] region

## Files Changed

| File | Change |
|------|--------|
| `pydaw/ui/clip_launcher_inspector.py` | Loop Start spinbox, Loop Länge → loop_end_beats, Clip Länge spinbox, enable/disable |
| `VERSION` | 0.0.20.590 → 0.0.20.591 |
