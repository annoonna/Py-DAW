## v0.0.20.493 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Objekt-Bindung (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bisherigen Runtime-Snapshot-Instanzen werden jetzt an konkrete, read-only Snapshot-Objektbindungen gekoppelt (`runtime_snapshot_objects`, `runtime_snapshot_object_summary`) — inklusive stabiler `snapshot_object_key`-Schluessel, Objektklasse sowie Capture-/Restore-Methoden.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt diese neue Ebene jetzt explizit als **Runtime-Snapshot-Objekt-Bindung** an und bindet die Objekt-Zusammenfassung bereits in den Infotext ein.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

