# v0.0.20.506 — SmartDrop: Read-only Snapshot-Transaktions-Dispatch / Apply-Runner

- `pydaw/services/smartdrop_morph_guard.py`: Hinter den vorhandenen Runtime-State-Registry-Backend-Adaptern gibt es jetzt einen eigenen, read-only `runtime_snapshot_apply_runner` / `runtime_snapshot_apply_runner_summary`.
- Der neue Runner dispatcht Adapter-, Backend-Store-Adapter- und Registry-Slot-Backend-Pfade sichtbar read-only, weiterhin ohne Commit und ohne Projektmutation.
- `pydaw/ui/main_window.py`: Der Guard-Dialog zeigt jetzt den Block **Read-only Snapshot-Transaktions-Dispatch / Apply-Runner** inklusive Sequenzen, Dispatch-Summaries und Beispiel-Phasen.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau, **kein** Commit und **keine** Projektmutation.
