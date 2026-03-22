# SESSION v0.0.20.186 — Hotfix: PyQt6 Slot-Safety (signal.connect wrapper) gegen SIGABRT

**Datum:** 2026-03-01  
**Assignee:** GPT-5.2 Thinking (ChatGPT)

## Problem
Auf manchen Linux/Wayland/Qt6 Setups beendet PyQt6 den Prozess hart mit **SIGABRT**, wenn eine Python-Exception aus einem Slot (Signal-Callback) entkommt.
Typisches Terminal-Muster:
- `qt.qpa.wayland.textinput ...`
- `Unhandled Python exception`
- danach `SIGABRT` (qFatal)

Die bisherige Hardening-Schicht (v0.0.20.185) hat *Qt-virtual Methods* abgesichert (paintEvent/eventFilter/…); der Crash kam aber weiterhin über **Signal/Slot**.

## Lösung (safe, additiv, nichts kaputt)
### 1) PyQt6 signal.connect global defensiv
- Neu: `pydaw/ui/qt_hardening.py` erweitert um `harden_signal_slots()`.
- Monkey-Patch von `PyQt6.QtCore.pyqtBoundSignal.connect`:
  - Wenn ein **Python-callable Slot** verbunden wird → wird er in einen try/except Wrapper gepackt.
  - Exceptions werden **geschluckt & geloggt** (statt qFatal).
  - Signal-to-signal Verbindungen bleiben unberührt.

### 2) Aktivierung beim Start
- `pydaw/app.py`: ruft `harden_signal_slots()` vor UI-Erzeugung auf.

## Environment Switches
- `PYDAW_SAFE_SIGNAL_CONNECT=0` → deaktiviert Slot-Wrapping
- `PYDAW_HARDEN_QT=0` → deaktiviert Virtual-Method-Hardening (v0.0.20.185)

## Betroffene Dateien
- `pydaw/ui/qt_hardening.py`
- `pydaw/app.py`
- `VERSION`, `pydaw/version.py`

## Testplan
1) Start:
   - `gdb -batch -ex "run" -ex "bt" --args python3 main.py`
2) Erwartung:
   - kein `Unhandled Python exception` + SIGABRT mehr
3) Falls Exception passiert:
   - sie steht jetzt im Log: `~/.cache/ChronoScaleStudio/pydaw.log` unter
     `Qt hardening: swallowed exception in slot ...`

