# CHANGELOG v0.0.20.502 — SmartDrop: Runtime-State-Stores / Capture-Handles

- `pydaw/services/smartdrop_morph_guard.py`: Neue read-only `runtime_snapshot_state_stores` / `runtime_snapshot_state_store_summary` hinter den vorhandenen Runtime-State-Slots.
- `pydaw/services/smartdrop_morph_guard.py`: Neue Store-Klassen pro Snapshot-Familie mit stabilen `capture_handle_key` / `restore_handle_key` / `rollback_handle_key`-Referenzen.
- `pydaw/services/smartdrop_morph_guard.py`: Der Dry-Run fuehrt jetzt `state_store_calls` / `state_store_summary` und die neuen `capture_store_preview()` / `restore_store_preview()` / `rollback_store_preview()`-Pfade.
- `pydaw/ui/main_window.py`: Guard-Dialog zeigt jetzt sowohl die Slot-Ebene als auch die neue Store-/Capture-Handle-Ebene sichtbar an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
