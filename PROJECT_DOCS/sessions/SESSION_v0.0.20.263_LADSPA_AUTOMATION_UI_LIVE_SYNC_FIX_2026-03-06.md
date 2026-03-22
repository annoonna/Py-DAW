# Session v0.0.20.263 — LADSPA Automation UI Live Sync Fix

## Context
User confirmed the audio-side FX automation works again, but the visible LADSPA sliders in the Device panel and Pro Drum Machine Slot-FX still do not move.

## Findings
- `LadspaAudioFxWidget` had a live sync timer, but it was never started.
- The correct LADSPA `_on_automation_changed()` implementation existed, but was later overwritten by an unrelated duplicate method block for chain wet/mix.

## Changes
- started the LADSPA UI sync timer after widget build/refresh
- restored the real LADSPA automation-change handler by renaming the accidental duplicate methods
- switched live UI polling to prefer `rt_params.get_smooth()` with fallback to `get_target()`

## Validation
- `python3 -m py_compile pydaw/ui/fx_device_widgets.py`

## Risk
Low. UI-only fix. No audio-engine / host processing logic touched.
