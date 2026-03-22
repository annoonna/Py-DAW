# Session v0.0.20.218 — Slot-FX Drag&Drop Fix + Preset Meta + Whole-Card Reorder + Note-FX Drop

Date: 2026-03-04

## Goal
User reported: Drag&Drop from Effects Browser onto the Slot-FX rack does not work (especially when dropping over the scrollable card area).
Also requested: reorder by dragging the whole card + preset names/tags.
Additionally: Note-FX and Audio-FX should both be usable like Bitwig (Note-FX before instrument, Audio-FX after).

## Changes (safe, UI-only / model-only)
- SlotFxInlineRack:
  - QScrollArea viewport now forwards DragEnter/DragMove/Drop/DragLeave via eventFilter
  - Drop index uses global cursor position to remain stable across viewport events
  - Drop inserts at cursor position (not only append)
  - Preset save prompts for name + tags; stores meta in JSON
  - Preset load displays meta name/tags if present
  - Accepts Note-FX drops and forwards to callback (adds to Track.note_fx_chain)

- SlotFxDeviceCard:
  - Whole-card drag reordering (not only ≡ handle), while protecting interactive controls

- DrumMachineWidget:
  - Added _add_note_fx_to_track() helper (writes Track.note_fx_chain safely and emits ProjectService.project_updated)
  - SlotFxInlineRack constructed with note_fx_cb bound to _add_note_fx_to_track

## Files
- pydaw/plugins/drum_machine/drum_widget.py
- VERSION
- pydaw/version.py

## Test
- Drag Audio-FX from Browser onto Slot-FX rack (including over the scroll card list): should insert and never fail.
- Drag Note-FX from Browser onto Slot-FX rack: should add to Track.note_fx_chain and show status message.
- Reorder: drag whole card (background) without using the ≡ handle.
- Preset save/load: prompts for name/tags; load shows meta in status.
