# v0.0.20.492 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Instanz-Vorschau

## Was wurde umgesetzt?

- Der zentrale Morphing-Guard baut jetzt zusaetzlich `runtime_snapshot_instances` und `runtime_snapshot_instance_summary` auf.
- Die vorhandenen Runtime-Capture-Objekte werden dabei in konkrete, weiterhin read-only Snapshot-Instanzen mit stabilem `snapshot_instance_key`, `snapshot_payload` und `payload_digest` materialisiert.
- Der Guard-Dialog zeigt diese neue Ebene als **Runtime-Snapshot-Instanz-Vorschau** an.
- Nebenbei wurde ein kleiner Safety-Hotfix in `pydaw/services/project_service.py` eingebaut: die Guard-Funktionen werden jetzt explizit importiert, damit der gemeinsame Preview/Validate/Apply-Pfad nicht an fehlenden Symbolen haengt.

## Sicherheit

- weiterhin **kein** echtes Audio->Instrument-Morphing
- weiterhin **kein** Routing-Umbau
- weiterhin **keine** Projektmutation
