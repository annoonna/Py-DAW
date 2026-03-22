# v0.0.20.589 — Clip Launcher → Arranger Drag&Drop (Bitwig-Style Promotion)

**Date:** 2026-03-18
**Author:** Claude Opus 4.6

## Problem

Launcher-only clips could not be dragged into the Arranger. The Arranger's
`dropEvent` searched only `_arranger_clips()` which filters `launcher_only=True`,
so the drop was silently ignored.

## Fix

`arranger_canvas.py` `dropEvent`: If the clip-id is not found in `_arranger_clips()`,
fall back to searching ALL clips. If the source is `launcher_only`, accept the drop,
duplicate the clip, and set `launcher_only=False` on the duplicate (promoting it to
an arranger clip). The original launcher clip remains untouched.

**Bitwig behavior now complete:**
1. Create clip in Launcher → `launcher_only=True` → not in Arranger
2. Alt/Ctrl+Drag from Launcher slot → drop on Arranger → duplicate with `launcher_only=False`
3. Original stays in Launcher, copy lives in Arranger at drop position

## Files Changed

| File | Change |
|------|--------|
| `pydaw/ui/arranger_canvas.py` | `dropEvent`: fall-through to all clips for launcher_only promotion |
| `VERSION` | 0.0.20.588 → 0.0.20.589 |
