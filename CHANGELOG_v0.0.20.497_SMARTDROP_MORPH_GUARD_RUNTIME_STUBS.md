## v0.0.20.497 — SmartDrop: Morphing-Guard Runtime-Stubs / Klassenkopplung (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden Runtime-Snapshot-Objektbindungen werden jetzt an konkrete read-only Runtime-Stub-Klassen gekoppelt (`runtime_snapshot_stubs`, `runtime_snapshot_stub_summary`).
- Der Dry-Run / Safe-Runner ruft Capture-/Restore-/Rollback-Previews nun ueber diese konkreten Stub-Klassen (`*.capture_preview()` / `*.restore_preview()` / `*.rollback_preview()`) auf statt nur ueber lose Methodennamen.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt als **Runtime-Snapshot-Stubs / Klassenkopplung** an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
