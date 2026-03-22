# Session v0.0.20.259 — Automation UI Crashfix + Visible Slider Sync

## User report
- Automated sliders/knobs did not visibly move in Device / Pro Drum Machine.
- GDB log showed repeated Qt hardening errors and final SIGABRT.

## Root cause
1. `AudioChainContainerWidget._on_change()` was connected to `QDial.valueChanged(int)` but accepted no value argument.
2. Multiple FX widgets stayed connected to `AutomationManager.parameter_changed` after the Qt widgets were already deleted.
3. Automation callback exceptions prevented reliable visible UI feedback.

## Fix
- `_on_change(self, *_args)` made signal-compatible.
- Added `_disconnect_automation()` and automatic disconnect on widget destruction.
- Added RuntimeError guards in automation callbacks for deleted widgets.
- Pro Drum Machine selected-slot editor knobs now mirror automation values visually.

## Safety
- No audio engine core change.
- No Bach Orgel change.
- No SF2 render change.
- Fix is limited to GUI automation update / widget lifecycle.
