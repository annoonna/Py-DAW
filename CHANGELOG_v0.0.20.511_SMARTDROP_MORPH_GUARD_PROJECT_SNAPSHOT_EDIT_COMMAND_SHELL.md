# CHANGELOG v0.0.20.511 — SmartDrop read-only ProjectSnapshotEditCommand / Undo-Huelle

## Neu
- `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_command_undo_shell` und `runtime_snapshot_command_undo_shell_summary` ein.
- Hinter Mutation-Gate und Transaction-Capsule werden jetzt Command-Preview, Command-/Undo-Huelle, Snapshot-Capture-/Restore und Undo-Stack-Push read-only sichtbar vorverdrahtet.
- `pydaw/services/project_service.py` exponiert dafuer `preview_audio_to_instrument_morph_project_snapshot_edit_command` und `preview_audio_to_instrument_morph_command_undo_shell`.
- `pydaw/ui/main_window.py` zeigt einen neuen Detailblock **Read-only ProjectSnapshotEditCommand / Undo-Huelle** und fuehrt die neue Summary in Infotext und Apply-Readiness.

## Sicherheit
- weiterhin **kein** echtes Audio->Instrument-Morphing
- weiterhin **kein** Commit
- weiterhin **kein** Routing-Umbau
- weiterhin **keine** Projektmutation

## Validierung
- `python3 -m py_compile pydaw/services/smartdrop_morph_guard.py pydaw/services/project_service.py pydaw/ui/main_window.py`
- `python3 -m compileall -q pydaw`
- Mock-Sanity-Run fuer leere Audio-Spur und FX-blockierten Fall
