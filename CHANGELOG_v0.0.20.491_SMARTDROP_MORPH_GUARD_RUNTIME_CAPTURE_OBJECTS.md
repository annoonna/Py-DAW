# v0.0.20.491 — SmartDrop Morph Guard Runtime Capture Objects

## Neu

- `pydaw/services/smartdrop_morph_guard.py` erzeugt jetzt `runtime_snapshot_captures` und `runtime_snapshot_capture_summary`.
- Jeder vorbereitete Runtime-Handle kann jetzt in ein deterministisches Capture-Objekt mit `capture_key`, `capture_object_kind`, `payload_preview` und `payload_entry_count` ueberfuehrt werden.
- `pydaw/ui/main_window.py` zeigt einen neuen Detailabschnitt **Runtime-Capture-Objekt-Vorschau**.
- Apply-Readiness bewertet jetzt auch die vorbereitete Capture-Objekt-Ebene.

## Sicherheit

- Weiterhin **kein** echtes Audio→Instrument-Morphing.
- Weiterhin **kein** Routing-Umbau.
- Weiterhin **keine** Projektmutation.
