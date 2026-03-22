# CHANGELOG v0.0.20.475 — Arranger Leerraum-Preview unter letzter Spur

## Neu

- `pydaw/ui/arranger_canvas.py`: Instrument-Drags zeigen jetzt unterhalb der letzten Spur im freien Arranger-Bereich eine cyanfarbene Linie/Badge wie `Neue Instrument-Spur: Surge XT`.
- `pydaw/ui/arranger_canvas.py`: Preview-Zustände werden jetzt zentral über kleine Helper verwaltet (`_parse_plugin_drag_info`, `_update_plugin_drag_preview`, `_clear_plugin_drag_preview`).

## Sicherheit

- Kein echter Plugin-Drop im Arranger
- Keine Spurerzeugung
- Kein Spur-Morphing
- Kein Routing-/Undo-/Projektformat-Umbau

## Validierung

- `python -m py_compile pydaw/ui/arranger_canvas.py`
