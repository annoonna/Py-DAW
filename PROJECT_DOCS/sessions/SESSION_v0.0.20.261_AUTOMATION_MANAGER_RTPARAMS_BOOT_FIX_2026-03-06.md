# Session v0.0.20.261 — AutomationManager RTParamStore Boot Fix

Date: 2026-03-06
Author: GPT-5.4 Thinking

## Context
User reported immediate startup failure after updating to `v0.0.20.260`:

```text
NameError: name 'rt_params' is not defined
```

Crash location:
- `pydaw/services/container.py`
- `ServiceContainer.create_default()`

## Root Cause
The new `AutomationManager(rt_params=rt_params)` wiring referenced `rt_params`
before the variable had been created.

## Safe Fix
- Read `rt_params` from `audio_engine.rt_params`
- Create `AutomationManager` only after that binding exists
- Keep all other automation behavior untouched

## Files changed
- `pydaw/services/container.py`
- `VERSION`
- `pydaw/version.py`
- `CHANGELOG_v0.0.20.261_AUTOMATION_MANAGER_RTPARAMS_BOOT_FIX.md`

## Validation
- `python3 -m py_compile pydaw/services/container.py pydaw/audio/automatable_parameter.py`

## Notes
This is a boot/wiring hotfix only. It does not change project data, device state,
or automation curve semantics.
