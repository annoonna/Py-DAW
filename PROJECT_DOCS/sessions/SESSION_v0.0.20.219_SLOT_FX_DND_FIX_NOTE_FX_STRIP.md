# Session v0.0.20.219 — Slot-FX DnD Fix + Note-FX Strip (UI-only)

## Goal
User reported that dragging FX from the Browser into the Pro Drum Machine Slot‑FX rack did not work: no cyan insert indicator and the FX was inserted into the Track Device chain instead.
Also Note‑FX drops were not applied.

## What was changed (SAFE)
### 1) DevicePanel drop-filter opt-out (UI-only)
- `DevicePanel` installs a drop-forward filter on *all* instrument child widgets.
- This was hijacking drops from internal racks.
- Added an opt-out: widgets with dynamic property `pydaw_exclusive_drop_target=True` are ignored by the drop-forward filter.

Files:
- `pydaw/ui/device_panel.py`

### 2) Slot-FX Rack is now an exclusive drop target
- `SlotFxInlineRack` sets `pydaw_exclusive_drop_target=True`.
- Added a visible cyan insert line indicator (like DevicePanel).

Files:
- `pydaw/plugins/drum_machine/drum_widget.py`

### 3) Compact, collapsible Note‑FX strip (Track-level)
- Added `NoteFxInlineStrip` inside `Pro Drum Machine` UI.
- Collapsed by default (triangle), minimal footprint.
- Supports drag&drop of Note‑FX from Browser into the strip, with cyan insert line.
- Allows enable/bypass, up/down, remove.

Files:
- `pydaw/plugins/drum_machine/drum_widget.py`

## Safety notes
- No audio engine refactors.
- Only UI + project model dicts (`Track.note_fx_chain`, `slot.state.audio_fx_chain`).
- All handlers are try/except wrapped to prevent Qt aborts.

## Manual test checklist
1) Open Pro Drum Machine.
2) Browser → Audio‑FX: drag `Gain` onto Slot‑FX rack → should show cyan line and insert into slot chain.
3) Browser → Note‑FX: drag `Transpose` onto Note‑FX strip header/body → should insert and show in list.
4) Confirm DevicePanel normal drag&drop still works outside these internal racks.
