# v0.0.20.251 — Pro Drum LADSPA Slot-FX Rebuild Loop Fix

## Fix
- Fixed a Pro Drum Slot-FX UI rebuild loop caused by `SlotFxDeviceCard` emitting `toggled()` during construction.
- `btn_power.setChecked()` is now wrapped with `QSignalBlocker` during initial card setup.

## Why this mattered
- Rebuilding the inline Slot-FX rack recreated device cards.
- Card construction re-emitted the power toggle signal.
- That triggered another Slot-FX rebuild, which rebuilt the UI again.
- For LADSPA this caused repeated re-instantiation, UI lockups, and the Drum Machine Slot-FX area collapsing/hanging.

## Safe scope
- UI-only initialization fix
- No core audio routing changes
- No LADSPA ABI changes
- No automation model changes
