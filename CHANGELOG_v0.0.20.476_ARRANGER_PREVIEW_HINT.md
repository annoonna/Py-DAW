# CHANGELOG v0.0.20.476 — Arranger Preview-Hinweis am Cursor / in Statusleiste

## Neu

- `pydaw/ui/arranger_canvas.py`: Plugin-Hover-Preview zeigt jetzt zusätzlich einen klaren Hinweis `… · Nur Preview — SmartDrop folgt später`.
- `pydaw/ui/arranger_canvas.py`: Der Hinweis wird best-effort als Tooltip in Cursor-Nähe angezeigt und parallel über die bestehende Statusleiste gemeldet.
- `pydaw/ui/arranger_canvas.py`: Beim Verlassen des Preview-Modus wird der Hinweis wieder sauber entfernt.

## Sicherheit

- Kein echter Plugin-Drop im Arranger
- Keine Spurerzeugung
- Kein Spur-Morphing
- Kein Routing-/Undo-/Projektformat-Umbau

## Validierung

- `python -m py_compile pydaw/ui/arranger_canvas.py`
