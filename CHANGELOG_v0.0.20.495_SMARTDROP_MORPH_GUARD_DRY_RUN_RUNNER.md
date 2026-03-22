# CHANGELOG — v0.0.20.495

## SmartDrop: Morphing-Guard Dry-Run Runner

- Snapshot-Bundle an einen read-only Dry-Run-/Transaktions-Runner gekoppelt.
- Neuer Dry-Run-Report mit `runner_key`, `capture_sequence`, `restore_sequence`, `rollback_sequence`, `rehearsed_steps` und `phase_results`.
- Guard-Dialog erweitert um einen sichtbaren Abschnitt fuer die neue Dry-Run-Ebene.
- Apply-Readiness um den Check `transaction_dry_run` erweitert.

Weiterhin bewusst sicher:
- kein echtes Audio->Instrument-Morphing
- kein Routing-Umbau
- keine Projektmutation
