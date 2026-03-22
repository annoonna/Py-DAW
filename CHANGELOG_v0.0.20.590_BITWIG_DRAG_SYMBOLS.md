# v0.0.20.590 — Clip Launcher: Bitwig-Style Drag + Symbols

**Date:** 2026-03-18
**Author:** Claude Opus 4.6

## Fixes

### 1. Plain Drag without modifier (Bitwig-style)
- `SlotButton.mouseMoveEvent`: Call `self.setDown(False)` before `QDrag.exec()` to release
  QPushButton pressed state. Without this, QPushButton held the mouse grab and prevented
  the drag cursor from appearing.

### 2. Bitwig-style slot symbols
- **▶ Play button**: Moved from top-right to LEFT-CENTER of clip slot (matching Bitwig position).
  Larger triangle, subtle background, hover feedback.
- **● Record indicator**: Red circle in top-right of slot when track is record-armed.
- **■ Stop button per track**: New button in track header row (next to M/S/R).
  Stops all playing clips on that track. `_stop_track_clips()` uses `active_slots()` + `stop_slot()`.
- **R button styling**: Red color when checked (record-armed).

### 3. Layout adjustment
- Label and waveform/pianoroll shifted right by 28px to not overlap with play button.

## Files Changed

| File | Change |
|------|--------|
| `pydaw/ui/clip_launcher.py` | setDown(False) fix, play button repositioned, record indicator, stop button per track, layout offset |
| `VERSION` | 0.0.20.589 → 0.0.20.590 |
