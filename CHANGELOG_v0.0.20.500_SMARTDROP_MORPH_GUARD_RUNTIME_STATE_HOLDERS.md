## v0.0.20.500 — SmartDrop: Separate Runtime-State-Halter (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden separaten Runtime-State-Container werden jetzt an konkrete, read-only `runtime_snapshot_state_holders` / `runtime_snapshot_state_holder_summary` gekoppelt. Jeder Halter traegt eigenen `holder_key`, Holder-Klasse, separate Holder-Payload und Payload-Digest.
- Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_holder_calls` / `state_holder_summary` und ruft `capture_holder_preview()` / `restore_holder_preview()` / `rollback_holder_preview()` ueber die neuen Halter auf.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt als **Separate Runtime-State-Halter** an und fuehrt die neuen Holder-Dispatch-Infos im Dry-Run-Block mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

