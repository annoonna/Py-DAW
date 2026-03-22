# v0.0.20.259 — Automation UI Crashfix + Visible Slider Sync

- Fixed Qt/PyQt crash caused by stale `parameter_changed` connections on deleted FX widgets.
- Fixed `AudioChainContainerWidget._on_change()` signal signature for `QDial.valueChanged(int)`.
- Added safe automation disconnect on widget destruction for chain and LADSPA FX widgets.
- Added safe RuntimeError guards for automation callbacks on already deleted widgets.
- Pro Drum Machine editor knobs now visibly follow automation for the currently selected slot.
