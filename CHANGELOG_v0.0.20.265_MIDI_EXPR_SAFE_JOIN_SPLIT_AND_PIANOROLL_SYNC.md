# v0.0.20.265 — Safe MIDI Expression Preserve + PianoRoll Sync Fix

## Safe fixes

- PianoRoll local clip playhead/geometry now read clip metadata by `clip.id` again.
- Note Expression Lane now refreshes quickly when note focus/selection/hover changes,
  including the detached zoom window.
- MIDI clip join/split paths now preserve per-note metadata instead of rebuilding bare notes.
  This keeps note expressions (including micropitch), curve types, tie/accidental data intact.

## Files
- `pydaw/ui/pianoroll_canvas.py`
- `pydaw/ui/note_expression_lane.py`
- `pydaw/services/project_service.py`
- `pydaw/services/altproject_service.py`
- `pydaw/ui/arranger_keyboard.py`
