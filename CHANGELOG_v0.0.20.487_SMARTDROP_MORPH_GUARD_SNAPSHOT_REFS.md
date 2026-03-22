# Changelog v0.0.20.487 — SmartDrop Morph Guard Snapshot Reference Preview

**Datum:** 2026-03-16

## Gemacht

- `pydaw/services/smartdrop_morph_guard.py` baut jetzt zusaetzlich deterministische Preview-Referenzen fuer alle geplanten Snapshots auf (`snapshot_refs`, `snapshot_ref_map`, `snapshot_ref_summary`).
- `pydaw/ui/main_window.py` zeigt diese vorbereiteten Snapshot-Referenzen im Guard-Dialog als eigenen Abschnitt an.

## Safety

- Kein echtes Audio->Instrument-Morphing
- Kein Routing-Umbau
- Keine Projektmutation

## Naechster Schritt

- Echte Snapshot-Objekte spaeter an dieselben Referenz-Keys haengen, sobald die atomare Apply-Phase freigeschaltet wird.
