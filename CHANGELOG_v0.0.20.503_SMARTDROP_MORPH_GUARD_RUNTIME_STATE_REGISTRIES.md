# CHANGELOG v0.0.20.503 — SmartDrop Morph Guard Runtime-State-Registries

- `pydaw/services/smartdrop_morph_guard.py` koppelt Runtime-State-Stores jetzt an konkrete read-only **Runtime-State-Registries / Handle-Speicher** pro Snapshot-Familie.
- Neue Plan-Felder: `runtime_snapshot_state_registries`, `runtime_snapshot_state_registry_summary`.
- Der Dry-Run fuehrt jetzt zusaetzlich `state_registry_calls` und `state_registry_summary` und nutzt `capture_registry_preview()` / `restore_registry_preview()` / `rollback_registry_preview()` read-only.
- `pydaw/ui/main_window.py` zeigt die neue Ebene **Runtime-State-Registries / Handle-Speicher** sichtbar im Guard-Dialog und fuehrt die Registry-Infos auch im Dry-Run-Block.
- Weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
