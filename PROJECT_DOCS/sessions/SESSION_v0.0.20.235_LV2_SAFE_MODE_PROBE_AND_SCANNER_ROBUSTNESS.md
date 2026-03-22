# SESSION v0.0.20.235 — LV2 Safe Mode (Crash Guard) + robust LV2 scanner fallback

## Goal
User report (gdb): LV2 Plugins can crash the whole DAW with **SIGBUS / SIGSEGV** during
instantiate/run (native .so), e.g.:
- `/usr/lib/lv2/sapistaEQv2.lv2/eq10qm.so` → SIGBUS inside `lilv_plugin_instantiate()`
- `/usr/lib/lv2/gx_mbdistortion.lv2/...` → SIGSEGV in audio thread

Additional log noise:
- `attempt to map invalid URI '/usr/lib/lv2/delay-swh.lv2'` → indicates that some
  plugin entries were stored as bundle paths instead of real LV2 URIs.

We must keep the system **SAFE** and avoid breaking non-LV2 FX.

## Root Cause
1) **Native LV2 binaries are not memory safe** for the host. A crash in the plugin
   kills the whole Python process. Python cannot catch SIGSEGV/SIGBUS.

2) Our LV2 filesystem scanner used a heuristic manifest parser. When it failed,
   it stored the **bundle directory path** as `plugin_id`. Passing that path into
   lilv as a URI produces `invalid URI` errors and makes LV2 hosting fail.

## Fix (SAFE)
### A) LV2 Safe Mode (subprocess probe)
- Added a subprocess probe that instantiates + connects ports + runs a tiny block
  **outside** the DAW process.
- If the probe crashes/fails/timeouts, the plugin is **blocked** and will not be
  instantiated in-process.
- Results are cached in `~/.cache/ChronoScaleStudio/lv2_probe_cache.json`.
- Users can override (unsafe) via env var: `PYDAW_LV2_UNSAFE=1`.

### B) UI: show BLOCKED reason
- LV2 device widget shows a clear status when the plugin is blocked by Safe Mode:
  - `DSP: BLOCKED (Safe Mode) — …`
  - Controls remain visible (UI still usable), but live DSP is prevented.

### C) LV2 scanner robustness
- Improved LV2 TTL parsing:
  - Recognizes `a lv2:Plugin` *and* `rdf:type lv2:Plugin`.
  - If manifest yields no plugin URIs, scans additional `.ttl` files inside the
    bundle (limited count) to avoid falling back to bundle-path plugin IDs.

### D) Compatibility: resolve bundle-path IDs
- `lv2_host.WorldCache.plugin_by_uri()` now accepts bundle directory paths as a
  best-effort compatibility layer for old caches/projects.

## Files changed
- `pydaw/audio/lv2_host.py`
  - Safe Mode cache + subprocess probe integration
  - Bundle-path compatibility
- `pydaw/tools/lv2_probe.py` (+ `pydaw/tools/__init__.py`)
  - Subprocess probe entry point
- `pydaw/ui/fx_device_widgets.py`
  - Show Safe Mode BLOCKED status in hint + DSP label
- `pydaw/services/plugin_scanner.py`
  - More robust LV2 bundle parsing
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/progress/TODO.md`, `PROJECT_DOCS/progress/DONE.md`, `PROJECT_DOCS/sessions/LATEST.md`

## Manual Test
1) Start Py_DAW.
2) Add a known-stable LV2 (e.g. simple SWH delay):
   - Expected: Probe caches `ok`, DSP becomes ACTIVE, effect audible.
3) Add a known-crashy LV2:
   - Expected: No DAW crash.
   - LV2 device shows `BLOCKED (Safe Mode)` with the reason.
4) Plugins → Rescan:
   - Expected: LV2 entries show URI-based IDs (no `/usr/lib/lv2/...` as plugin_id).

## Notes
This is a **crash guard**, not a full LV2 sandbox/bridge for realtime audio.
True isolation for arbitrary LV2 DSP would require out-of-process audio bridging.
