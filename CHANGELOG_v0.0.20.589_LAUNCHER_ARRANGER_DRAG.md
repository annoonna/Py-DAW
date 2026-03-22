# v0.0.20.589 — Clip Launcher → Arranger Drag&Drop (Bitwig-Style)

**Date:** 2026-03-18
**Author:** Claude Opus 4.6
**Priority:** HIGH — Core UX (Bitwig workflow completion)

## Problem

Launcher clips had `launcher_only=True` (v588) so they didn't appear in the Arranger.
But there was no way to bring them INTO the Arranger — the Bitwig workflow requires
dragging clips from Launcher to Arranger.

Also, drag from launcher slots required Alt+Drag or Ctrl+Drag. In Bitwig, a plain
drag (no modifier) starts the drag operation.

## Fix

### 1. Plain Drag from Slot Buttons (clip_launcher.py)
- Removed Alt/Ctrl modifier requirement from `SlotButton.mouseMoveEvent()`
- Any click+drag on a filled slot now initiates DnD (8px manhattan threshold)
- Ctrl+Drag still marks as "duplicate" for slot-to-slot copy

### 2. Arranger Accepts Launcher Clips (arranger_canvas.py)
- `dropEvent()`: When a dropped clip_id is not found in `_arranger_clips()`,
  now falls back to searching ALL clips. If the clip is `launcher_only=True`,
  it's accepted as a launcher→arranger drag.
- The drop DUPLICATES the clip (original stays in launcher) and sets
  `launcher_only=False` on the duplicate → appears in Arranger.
- Position and track assignment work as with any internal clip drag.

### 3. Ghost Preview for Launcher Drags (arranger_canvas.py)
- `dragEnterEvent()`: Detects launcher_only clips and shows a ghost preview
  with clip label + icon (🎵 for MIDI, 🔊 for Audio).

## Files Changed

| File | Change |
|------|--------|
| `pydaw/ui/clip_launcher.py` | Plain drag (no modifier) for launcher slots |
| `pydaw/ui/arranger_canvas.py` | Accept + duplicate launcher_only clips on drop, ghost preview |
| `VERSION` | 0.0.20.588 → 0.0.20.589 |

## Bitwig Behavior Now Complete

1. Create clip in Launcher (double-click or right-click) → `launcher_only=True`
2. Clip visible ONLY in Clip Launcher, NOT in Arranger
3. Drag clip from Launcher → Arranger: creates a COPY in the Arranger
4. Original stays in Launcher for re-use
5. Arranger copy has `launcher_only=False` → normal arranger clip
