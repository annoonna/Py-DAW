# v0.0.20.505 — SmartDrop: Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends

- `pydaw/services/smartdrop_morph_guard.py`: Die vorhandenen Runtime-State-Registry-Backends werden jetzt an konkrete, read-only `runtime_snapshot_state_registry_backend_adapters` / `runtime_snapshot_state_registry_backend_adapter_summary` gekoppelt. Jeder Adapter-Eintrag traegt eigenen `adapter_key`, `backend_store_adapter_key` und `registry_slot_backend_key`.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_registry_backend_adapter_calls` / `state_registry_backend_adapter_summary` und nutzt die neuen `capture_adapter_preview()` / `restore_adapter_preview()` / `rollback_adapter_preview()`-Pfade direkt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt die neue Ebene **Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends** sichtbar an und fuehrt die neuen Adapter-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

