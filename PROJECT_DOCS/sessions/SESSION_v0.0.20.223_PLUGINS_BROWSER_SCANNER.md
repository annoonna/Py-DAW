# SESSION v0.0.20.223 — Plugins Browser: LV2/LADSPA/DSSI/VST Scanner (UI-only)

**Date:** 2026-03-04
**Assignee:** GPT-5.2 Thinking (ChatGPT)
**Scope:** Replace "Plugins" tab placeholder with a real external plugin list, without touching audio engine.

## User Request
- "LV2 Plugins dssi ladspa und vst plugins sind momentan nur platz halter" → bitte ändern.
- Oberste Direktive: **nichts kaputt machen**.

## Safety Strategy
- **No hosting / no loading** of external plugins.
- Only implement a **filesystem scanner + UI list**.
- Add caching + rescan to avoid slow start.

## Implemented
### 1) New scanner service
- **File:** `pydaw/services/plugin_scanner.py`
- Scans:
  - **LV2**: finds `.lv2` bundles; best-effort parses `manifest.ttl` for URI + `doap:name`/`rdfs:label`.
  - **LADSPA/DSSI**: shared objects by filename (`.so`/`.dll`/`.dylib`).
  - **VST2**: Linux/Win files; macOS `.vst` bundles.
  - **VST3**: `.vst3` bundles or files.
- Cache:
  - `~/.cache/ChronoScaleStudio/plugin_cache.json`

### 2) New Plugins Browser UI
- **File:** `pydaw/ui/plugins_browser.py`
- Features:
  - Tabs: LV2 / LADSPA / DSSI / VST2 / VST3
  - Search + "Only Favorites"
  - ⭐ Favorites (stored in existing `device_prefs.json` under keys: `ext_lv2`, `ext_ladspa`, ...)
  - Context menu: copy ID/path, open folder
  - Rescan (async QThread worker)

### 3) Paths dialog (optional overrides)
- **File:** `pydaw/ui/plugin_paths_dialog.py`
- QSettings keys:
  - `plugins/paths/<kind>` → QStringList
- If set (non-empty), overrides platform defaults for that plugin kind.

### 4) Integrated into main Browser
- **File:** `pydaw/ui/device_browser.py`
- Replaced placeholder with `PluginsBrowserWidget()`.

## Version bump
- `VERSION`: `0.0.20.223`
- `pydaw/version.py`: `__version__ = '0.0.20.223'`

## Notes / Next Steps (separate task)
- Real external plugin **hosting** (LV2/DSSI/LADSPA/VST) requires a dedicated, careful audio-thread integration.
- This session intentionally stops at listing + metadata to keep the system stable.
