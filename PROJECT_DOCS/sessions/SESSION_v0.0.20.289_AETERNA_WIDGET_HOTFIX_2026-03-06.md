# SESSION v0.0.20.289 — AETERNA Widget Hotfix

## Scope
Local AETERNA widget hotfix only. No Arranger, Clip Launcher, Audio Editor, Mixer or playback-core changes.

## Fixed
- duplicate insertion of the modulation toolbar layout
- duplicate creation of `_ModPreviewWidget`
- invalid grid stretch handling replaced with safe `setColumnStretch`
- shortened preview hint text for readability

## Verification
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py`

## Notes
This is a pure safety/hotfix build responding to a visible instrument/UI error.
