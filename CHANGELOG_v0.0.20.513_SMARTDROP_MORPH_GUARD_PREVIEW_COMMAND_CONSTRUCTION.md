# v0.0.20.513 — SmartDrop: read-only Preview-Command-Konstruktion

## Ziel
Die bestehende read-only Before-/After-Snapshot-Command-Factory sollte an eine explizite Preview-Command-Konstruktion gekoppelt werden, ohne `do()` auszufuehren, ohne Undo-Push und ohne Projektmutation.

## Umsetzung
- `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_preview_snapshot_command` ein.
- `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_preview_command_construction` und `_summary` ein.
- `pydaw/ui/main_window.py` zeigt einen neuen Block **Read-only Preview-Command-Konstruktion** inklusive Constructor-Form, Callback, Feldliste und Payload-Digests.

## Sicherheit
- kein echtes Audio->Instrument-Morphing
- kein Commit
- kein Undo-Push
- kein Routing-Umbau
- keine Projektmutation
