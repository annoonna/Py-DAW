# SESSION v0.0.20.224 — Plugins: Insert into Device-Chain (Placeholder, UI-only)

**Date:** 2026-03-04
**Assignee:** GPT-5.2 Thinking (ChatGPT)
**Scope:** Make Plugins Browser entries behave like browser items (Add/Drag into device chain) WITHOUT implementing plugin hosting.

## User Request
- "ich kann keine plug ins laden warum das es geht nicht ins device???"
- Oberste Direktive: **nichts kaputt machen**.

## Safety Strategy
- No external plugin hosting / DSP integration.
- Insert creates a normal **Audio-FX device entry** that the engine will ignore (unknown plugin id).
- Changes are UI/model only, fully backwards compatible.

## Implemented
### 1) Plugins Browser: Add + DnD uses existing device mime
- **File:** `pydaw/ui/plugins_browser.py`
- Drag payload now uses `application/x-pydaw-plugin` with:
  - `kind = audio_fx`
  - `plugin_id = ext.<kind>:<ext_id>`
  - `name = <Plugin Name>`
  - `params = {__ext_kind,__ext_id,__ext_path}`
- Added:
  - Button **"Add to Device"**
  - Double-click inserts
  - Context menu: **"Add to Device (Placeholder)"**

### 2) DevicePanel: accept optional name/params
- **File:** `pydaw/ui/device_panel.py`
- `add_audio_fx_to_track(..., name='', params=None)` and `add_note_fx_to_track(..., name='', params=None)`
  - merges `params` into defaults
  - stores `name` into device header title
- Drop handler forwards `name/params` when present.

### 3) Wiring
- **File:** `pydaw/ui/device_browser.py` → passes `on_add_audio_fx` into `PluginsBrowserWidget`.
- **File:** `pydaw/ui/main_window.py` → callbacks accept optional `name/params` (old call sites still OK).

## Result
- External plugins appear in the **Audio-FX chain** as a device card (placeholder).
- No audio processing yet (expected); this is a safe UX step.

## Version bump
- `VERSION`: `0.0.20.224`
- `pydaw/version.py`: `__version__ = '0.0.20.224'`
