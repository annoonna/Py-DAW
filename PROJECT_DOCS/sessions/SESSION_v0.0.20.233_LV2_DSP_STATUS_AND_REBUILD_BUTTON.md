# SESSION v0.0.20.233 — LV2 DSP Status + Rebuild Button

## Goal
Users reported: **LV2 plugin UI shows controls, but no audible effect** on instrument tracks.

We must keep the system safe (no regressions) and improve diagnosis without changing the audio core.

## Root Cause (most common)
Even if LV2 control UI loads (via python-lilv or lv2info fallback), **the DSP instance might not be compiled into the audio thread**.
Reasons:
- LV2 instantiate fails (missing required features / broken bundle)
- FX maps are stale after project load / changes

Previously this was silent: UI worked, but the user had no clear indicator whether DSP is active.

## Changes (SAFE, UI-only)
- Added a **DSP status line** inside `Lv2AudioFxWidget`:
  - `DSP: ACTIVE` when this device id exists inside `AudioEngine._track_audio_fx_map[track_id].devices`.
  - `DSP: INACTIVE ...` when not present (meaning: no audible effect expected).
- Added a **Rebuild FX** button (visible when LV2 hosting is available and DSP is inactive):
  - Calls `AudioEngine.rebuild_fx_maps(current_project)` and refreshes the status.

No changes to the audio callback pipeline; only diagnostics and a safe rebuild trigger.

## Files changed
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/version.py`
- `PROJECT_DOCS/sessions/LATEST.md`

## Manual Test
1. Add an LV2 plugin from Browser → Plugins.
2. Open its device card.
3. Verify:
   - Status shows `DSP: ACTIVE` when instantiated.
   - If status shows `DSP: INACTIVE`, click **Rebuild FX** and verify it becomes `DSP: ACTIVE` when possible.

## Notes
This does not solve missing LV2 dependencies; the existing availability hint still explains how to install python-lilv.
