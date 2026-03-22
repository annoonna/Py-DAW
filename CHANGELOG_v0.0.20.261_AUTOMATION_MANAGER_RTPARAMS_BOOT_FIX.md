# v0.0.20.261 — AutomationManager RTParamStore Boot Fix

## Problem
In `v0.0.20.260` the service container created `AutomationManager(rt_params=rt_params)`
before `rt_params` had been defined. This caused an immediate startup crash:

- `NameError: name 'rt_params' is not defined`

## Safe Fix
- `rt_params` is now taken directly from `audio_engine.rt_params` before creating the
  `AutomationManager`.
- No behavioral change to the automation logic itself.
- This is a startup wiring hotfix only.

## Files
- `pydaw/services/container.py`
- `VERSION`
- `pydaw/version.py`
