## v0.0.20.512 — SmartDrop Morph Guard Before-/After-Snapshot-Command-Factory / materialisierte Payloads

- Hinter der vorhandenen read-only `ProjectSnapshotEditCommand`-/Undo-Huelle haengt jetzt ein eigener `runtime_snapshot_command_factory_payloads`-Block.
- Die neue read-only Before-/After-Snapshot-Factory fuehrt Factory-Preview, Before-/After-Payload-Materialisierung, Restore-Callback und Payload-Paritaet sichtbar mit.
- `ProjectService` materialisiert Before-/After-Snapshots dafuer nur in-memory und liefert Digests, Byte-Groessen und Top-Level-Key-Metadaten an den Guard zurueck.
- Guard-Dialog und Apply-Readiness zeigen jetzt den neuen Block **Read-only Before-/After-Snapshot-Command-Factory** sichtbar an.
- Safety first: weiterhin kein Commit, kein Undo-Push, kein Routing-Umbau und keine Projektmutation.

