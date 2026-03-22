## v0.0.20.496 — SmartDrop: Morphing-Guard Safe-Runner Dispatch (2026-03-16)

- Der read-only Dry-Run-/Transaktions-Runner dispatcht Capture-/Restore-Phasen jetzt ueber konkrete Snapshot-Preview-Funktionen pro Typ, statt nur ueber generische Platzhaltertexte.
- Der Dry-Run-Bericht fuehrt zusaetzlich `capture_method_calls`, `restore_method_calls` und `runner_dispatch_summary`, damit die spaeteren Safe-Runner-Einstiegspunkte schon sichtbar fest verdrahtet sind.
- `pydaw/ui/main_window.py` zeigt diese neue Dispatch-Ebene direkt im bestehenden Block **Read-only Dry-Run / Transaktions-Runner** an.

