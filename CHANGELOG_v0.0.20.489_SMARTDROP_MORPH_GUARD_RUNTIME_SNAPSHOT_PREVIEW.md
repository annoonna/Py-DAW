# Changelog v0.0.20.489 — SmartDrop Morph Guard Runtime Snapshot Preview

## Neu

- `pydaw/services/smartdrop_morph_guard.py` baut jetzt zusaetzlich `runtime_snapshot_preview` und `runtime_snapshot_summary` auf.
- Die bestehenden Snapshot-Referenzen werden erstmals direkt gegen den aktuellen Zielspur-/Routing-/Clip-/Chain-Zustand aufgeloest, weiterhin komplett read-only.
- `pydaw/ui/main_window.py` zeigt diese Daten im Guard-Dialog jetzt als **Aktuelle Runtime-Snapshot-Vorschau** an.

## Safety

- weiterhin **kein** echtes Audio->Instrument-Morphing
- weiterhin **kein** Routing-Umbau
- weiterhin **keine** Projektmutation
