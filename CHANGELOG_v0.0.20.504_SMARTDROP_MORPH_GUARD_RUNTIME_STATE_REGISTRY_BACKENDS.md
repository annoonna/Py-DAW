# v0.0.20.504 — SmartDrop: Runtime-State-Registry-Backends / Handle-Register / Registry-Slots

- `pydaw/services/smartdrop_morph_guard.py`: Die vorhandenen Runtime-State-Registries werden jetzt an konkrete, read-only `runtime_snapshot_state_registry_backends` / `runtime_snapshot_state_registry_backend_summary` gekoppelt. Jeder Backend-Eintrag traegt eigenen `backend_key`, `handle_register_key` und `registry_slot_key`.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_registry_backend_calls` / `state_registry_backend_summary` und nutzt die neuen `capture_backend_preview()` / `restore_backend_preview()` / `rollback_backend_preview()`-Pfade direkt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt die neue Ebene **Runtime-State-Registry-Backends / Handle-Register / Registry-Slots** sichtbar an und fuehrt die neuen Backend-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
