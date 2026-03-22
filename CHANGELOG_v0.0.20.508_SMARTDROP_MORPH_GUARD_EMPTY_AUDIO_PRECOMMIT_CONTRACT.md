# CHANGELOG v0.0.20.508 — SmartDrop Morph Guard Empty Audio Pre-Commit Contract

## Neu
- `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_precommit_contract` und `runtime_snapshot_precommit_contract_summary` ein.
- Fuer die leere Audio-Spur gibt es jetzt eine eigene read-only Commit-/Rollback-Sequenz hinter Minimalfall, Apply-Runner und Dry-Run.
- `pydaw/ui/main_window.py` zeigt dafuer einen neuen Detailblock im Guard-Dialog an.

## Sicherheit
- Weiterhin **kein** echtes Audio->Instrument-Morphing
- Weiterhin **kein** Commit
- Weiterhin **kein** Routing-Umbau
- Weiterhin **keine** Projektmutation
