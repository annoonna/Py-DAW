# v0.0.20.263 — LADSPA Automation UI Live Sync Fix

Safe UI fix for LADSPA / Pro-Drum Slot-FX automation visuals.

## User report
Automation is audible again, but the visible LADSPA sliders/spinboxes still do not move during playback.

## Root cause
Two UI-only issues in `LadspaAudioFxWidget` blocked visible movement:

1. The widget created a live UI sync timer but never started it.
2. A later accidental duplicate method definition (`_on_automation_changed`) overwrote the real LADSPA handler with unrelated chain wet/mix code.

Because of that, audio automation could work while the visible controls stayed frozen.

## Safe fix
- Start `self._ui_sync_timer` after `refresh_from_project()` in `LadspaAudioFxWidget`.
- Keep the real LADSPA `_on_automation_changed()` active.
- Rename accidental legacy duplicate chain methods so they no longer override LADSPA behavior.
- UI sync prefers `RTParamStore.get_smooth()` and falls back to `get_target()`.

## Files
- `pydaw/ui/fx_device_widgets.py`
- `VERSION`
- `pydaw/version.py`

## Scope
UI-only. No DSP/host/automation-lane semantics changed.
