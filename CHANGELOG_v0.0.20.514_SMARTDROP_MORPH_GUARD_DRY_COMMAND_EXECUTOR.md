# v0.0.20.514 — SmartDrop Morph Guard: read-only Dry-Command-Executor

- Neuer read-only Guard-Block `runtime_snapshot_dry_command_executor` / `_summary` hinter der Preview-Command-Konstruktion.
- Neuer `ProjectService`-Owner-Pfad `preview_audio_to_instrument_morph_dry_command_executor`.
- `ProjectSnapshotEditCommand.do()/undo()` werden ausschliesslich gegen einen lokalen Recorder-Callback simuliert.
- Guard-Dialog und Apply-Readiness zeigen do/undo-Zaehler, Callback-Trace und Payload-Digests sichtbar an.
- Weiterhin keine Projektmutation, kein Undo-Push und kein echtes Audio->Instrument-Morphing.
