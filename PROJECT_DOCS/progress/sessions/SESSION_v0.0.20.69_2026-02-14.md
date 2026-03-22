# SESSION v0.0.20.69 — 2026-02-14

## Kontext
User report: **SIGSEGV** beim Klick auf SF2 *Bank* / *Preset* SpinBox im DevicePanel.
GDB Backtrace zeigt Crash in `QAbstractSpinBox::stepBy()` → `QWidget::style()`.

## Task
Hotfix: **SF2 Bank/Preset SpinBox SIGSEGV** eliminieren (Qt Re-Entrancy / sofortiges Re-Render).

## Root Cause
`ProjectService.set_track_soundfont()` emittiert `project_updated` **synchron**.
Das DevicePanel rendert daraufhin sofort neu und zerstört die SF2-Widgets,
während Qt noch im Mouse-Event des SpinBox steckt (stepBy) → invalid state → SIGSEGV.

## Fix
- SF2-Apply wird **deferred** (`QTimer.singleShot(0, ...)`) auf den nächsten Event-Loop Tick.
- Änderungen werden **coalesced** (Pending-Flag), damit mehrere valueChanged Events nicht spammen.
- Redundantes `_emit_project_updated()` aus dem SF2-Widget entfernt (Service emit reicht).

## Geänderte Files
- `pydaw/ui/device_panel.py`
- `VERSION`
- `pydaw/version.py`
- `pydaw/model/project.py`
- `PROJECT_DOCS/progress/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Testplan
1) Start:
   - `pw-jack python3 main.py` (oder normal, je nach Setup)
2) DevicePanel → Instrument → **SF2**:
   - SF2 laden (plus Button)
   - Mehrfach Bank/Preset mit Pfeilen klicken (schnell)
   - Erwartung: **kein Crash**, UI bleibt stabil
3) Optional:
   - Während Playback Bank/Preset ändern → danach Stop/Play für sofortigen Wechsel.

## Offene Themen / Next
- Projekt-Laden: Media/Samples werden nicht zuverlässig wiederhergestellt (User report: `media/` leer).
  → Nächster Task: Path-Resolve & Media-Pool rehydrate beim Open/Save prüfen.

