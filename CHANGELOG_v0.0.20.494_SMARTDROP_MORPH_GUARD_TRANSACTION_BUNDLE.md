# Changelog v0.0.20.494 — SmartDrop: Morphing-Guard mit Snapshot-Bundle / Transaktions-Container

**Datum:** 2026-03-16

## Neu

- `pydaw/services/smartdrop_morph_guard.py` baut jetzt aus den vorhandenen Runtime-Snapshot-Objektbindungen ein stabiles, read-only **Snapshot-Bundle / einen Transaktions-Container** auf (`runtime_snapshot_bundle`, `runtime_snapshot_bundle_summary`).
- Der Container fuehrt `bundle_key`, `transaction_container_kind`, Objektzaehler, benoetigte Snapshot-Typen, `commit_stub`, `rollback_stub`, Capture-/Restore-Methoden, Rollback-Slots und Payload-Digests zentral zusammen.
- Die Apply-Readiness enthaelt jetzt zusaetzlich einen Check fuer das vorbereitete Snapshot-Bundle.
- `pydaw/ui/main_window.py` zeigt die neue Container-Ebene jetzt sichtbar im bestehenden Morphing-Guard-Dialog an.

## Sicherheit

- Weiterhin **kein** echtes Audio->Instrument-Morphing
- Weiterhin **kein** Routing-Umbau
- Weiterhin **keine** Projektmutation

## Validierung

- `python -m py_compile pydaw/services/smartdrop_morph_guard.py pydaw/ui/main_window.py`
- Guard-Sanity-Run ueber `build_audio_to_instrument_morph_plan(...)`
