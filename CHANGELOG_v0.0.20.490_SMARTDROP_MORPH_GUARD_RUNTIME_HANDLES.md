# v0.0.20.490 — SmartDrop Morph Guard Runtime Snapshot Handles

## Neu

- `pydaw/services/smartdrop_morph_guard.py` erzeugt jetzt `runtime_snapshot_handles` und `runtime_snapshot_handle_summary`.
- Jeder benoetigte Snapshot-Typ bekommt einen deterministischen Handle-Deskriptor mit `handle_key`, `handle_kind`, `owner_scope`, `owner_ids`, `capture_state` und `capture_stub`.
- `pydaw/ui/main_window.py` zeigt einen neuen Detailabschnitt **Runtime-Snapshot-Handle-Vorschau**.
- Apply-Readiness bewertet jetzt auch die vorverdrahtete Handle-Ebene.

## Sicherheit

- Weiterhin **kein** echtes Audio→Instrument-Morphing.
- Weiterhin **kein** Routing-Umbau.
- Weiterhin **keine** Projektmutation.
