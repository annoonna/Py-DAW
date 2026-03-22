# SESSION v0.0.20.234 — LV2 Instantiate Compat Fix + Better Error Reporting

## Goal
User report: **LV2 Devices show UI controls, but DSP stays INACTIVE** and even the Plugins-Browser "Offline Render" fails with:

- "LV2 Plugin konnte nicht instanziiert werden"

We must keep the system safe and avoid breaking non-LV2 FX.

## Root Cause
Different python-lilv builds expose different instantiation APIs:
- `plugin.instantiate(sr)`
- `plugin.instantiate(sr, features)`
- `lilv.Instance(plugin, sr, features)`

Our host called only `plugin.instantiate(sr)`.
On systems where the binding requires a `features` argument, this raises a `TypeError` (caught and swallowed), resulting in:
- LV2 DSP object not compiled into the audio thread (`DSP: INACTIVE`)
- Offline render failing with the generic message

## Fix (SAFE, compatibility-only)
- Added a version-tolerant instantiation helper `_try_instantiate_plugin()` that tries:
  - `plugin.instantiate(sr, [])`
  - `plugin.instantiate(sr, None)`
  - `plugin.instantiate(sr)`
  - and fallbacks via `lilv.Instance(...)` when available
- Added `_get_required_features()` (best-effort) so failures can show which LV2 features are required.
- `Lv2Fx` now stores a short `_err` string when instantiation fails.
- `offline_process_wav()` returns that `_err` string so the user sees *why* instantiation failed (instead of a generic message).

## Files changed
- `pydaw/audio/lv2_host.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/progress/TODO.md`, `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Manual Test
1. Plugins → LV2 → pick a simple SWH plugin (e.g. delay-swh)
2. Use context menu: "Offline: Render WAV through LV2…"
3. Expected:
   - Either render succeeds (OK)
   - Or the warning shows an informative reason (TypeError signature / required features list)
4. Add the same LV2 plugin to a track FX chain and verify:
   - Device shows `DSP: ACTIVE` once instantiated

## Notes
This does **not** add support for complex LV2 required features (URID map/options/etc.).
It only ensures we call the binding correctly and surface clear diagnostics.
