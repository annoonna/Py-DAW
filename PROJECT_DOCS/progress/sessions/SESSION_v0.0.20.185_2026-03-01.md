# SESSION v0.0.20.185 (2026-03-01)

## Context
User reported reproducible Linux/Wayland startup aborts:
- terminal shows `qt.qpa.wayland.textinput ...` and then
- `Unhandled Python exception` followed by SIGABRT

This is a known failure mode where PyQt6/SIP terminates the process if a Python
exception escapes a Qt *virtual method* implemented in Python (paintEvent,
eventFilter, mouse handlers, etc.).

## Work done (safe, additive)
1) Added **Qt hardening layer**:
- `pydaw/ui/qt_hardening.py` wraps common Qt virtuals for classes in `pydaw.ui.*`.
- Exceptions are swallowed and logged (default: once per class+method to avoid spam).
- Can be disabled via `PYDAW_HARDEN_QT=0`.

2) Enabled hardening at startup:
- `pydaw/app.py` calls `harden_qt_virtuals()` right after creating QApplication and before creating UI widgets.

3) Defensive TrackList drag override:
- `pydaw/ui/arranger.py` now sets `startDrag` only if `_start_drag` exists/callable.

## Files changed
- `pydaw/ui/qt_hardening.py` (new)
- `pydaw/app.py`
- `pydaw/ui/arranger.py`
- `VERSION`, `pydaw/version.py`

## Notes
If the UI still behaves oddly, check the logfile:
`~/.cache/ChronoScaleStudio/pydaw.log`

Look for lines starting with:
`Qt hardening: swallowed exception in ...`

Those log entries identify the exact widget/method that threw, so we can fix the underlying bug without relying on hardening.
