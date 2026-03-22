# v0.0.20.498 — SmartDrop: Morphing-Guard State-Carriers

- `pydaw/services/smartdrop_morph_guard.py` koppelt die vorhandenen Runtime-Stubs jetzt an konkrete read-only Zustandstraeger / State-Carrier-Klassen.
- Der Dry-Run nutzt diese State-Carrier direkt fuer `capture_state_preview()` / `restore_state_preview()` / `rollback_state_preview()` und liefert zusaetzlich `state_carrier_calls` sowie `state_carrier_summary`.
- `pydaw/ui/main_window.py` zeigt die neue Ebene als **Runtime-Zustandstraeger / State-Carrier** im Guard-Dialog an und fuehrt die Carrier-Infos auch im Dry-Run-Block mit.
- Weiterhin bewusst sicher: kein Commit, kein Routing-Umbau, keine Projektmutation.
