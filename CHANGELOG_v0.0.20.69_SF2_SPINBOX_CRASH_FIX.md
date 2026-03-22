# CHANGELOG v0.0.20.69 — SF2 Bank/Preset SpinBox Crash Fix

## Fix
- **SF2 Anchor**: Bank/Preset QSpinBox klickte manchmal sofort die App weg (**SIGSEGV**).
- Ursache: synchrones `project_updated` → DevicePanel rendert neu und zerstört SpinBox während Qt im `stepBy()` steckt.
- Lösung: SF2-Apply wird mit `QTimer.singleShot(0, ...)` deferred (pending/coalesced), so dass das Re-Render erst nach dem Event erfolgt.

## Dateien
- `pydaw/ui/device_panel.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- Doku: `PROJECT_DOCS/progress/*`

