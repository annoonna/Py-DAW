# SESSION v0.0.20.186 (2026-03-01)

## Fokus
Stabilität unter Wayland/PyQt6: **Signal/Slot Exceptions dürfen niemals SIGABRT auslösen**.

## Änderungen
- `pydaw/ui/qt_hardening.py`
  - Neu: `harden_signal_slots()` monkey-patcht `PyQt6.QtCore.pyqtBoundSignal.connect`.
  - Python-Slots werden defensiv in try/except Wrapper gepackt → Exceptions werden geloggt statt qFatal.
  - signal-to-signal connect bleibt unberührt.
- `pydaw/app.py`
  - Aktiviert `harden_signal_slots()` beim Start (vor UI-Konstruktion).
- Version bump: `0.0.20.186`

## Toggle
- `PYDAW_SAFE_SIGNAL_CONNECT=0` → Slot-Wrapping aus

## Test
- Start via `gdb -batch -ex "run" -ex "bt" --args python3 main.py`
- Erwartung: kein `Unhandled Python exception` + SIGABRT.
- Wenn eine Exception passiert: `~/.cache/ChronoScaleStudio/pydaw.log` enthält `Qt hardening: swallowed exception in slot ...`
