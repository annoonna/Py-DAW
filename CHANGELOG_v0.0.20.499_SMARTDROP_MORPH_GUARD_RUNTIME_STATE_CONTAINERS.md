## v0.0.20.499 — SmartDrop: Separate Runtime-State-Container (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden Runtime-Zustandstraeger werden jetzt an konkrete, read-only `runtime_snapshot_state_containers` / `runtime_snapshot_state_container_summary` gekoppelt. Jeder Container traegt eigenen `container_key`, Container-Klasse, separate Container-Payload und Payload-Digest.
- Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_container_calls` / `state_container_summary` und ruft `capture_container_preview()` / `restore_container_preview()` / `rollback_container_preview()` ueber die neuen Container auf.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt als **Separate Runtime-State-Container** an und fuehrt die neuen Container-Dispatch-Infos im Dry-Run-Block mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

