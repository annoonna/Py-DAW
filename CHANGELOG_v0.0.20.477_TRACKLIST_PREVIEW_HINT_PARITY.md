# v0.0.20.477 — TrackList Preview-Hinweis Parität

## Was wurde gemacht?

- `pydaw/ui/arranger.py`: Die Arranger-TrackList baut jetzt beim Plugin-Hover denselben reinen Preview-Text wie der ArrangerCanvas auf (`Instrument/Note-FX/Effekt → Preview ...`).
- `pydaw/ui/arranger.py`: Der Hinweis wird links zusätzlich als best-effort Tooltip in Cursor-Nähe sowie über `status_message` in die bestehende Statusleiste gespiegelt.
- `pydaw/ui/arranger.py`: Beim Drag-Leave/Drop werden Preview-Hinweis und Tooltip wieder sauber entfernt; der normale Standard-Tooltip der TrackList wird danach wiederhergestellt.

## Safety

- Kein echter Plugin-Drop
- Keine neue Spur
- Kein Spur-Morphing
- Kein Routing-/Undo-/Projektformat-Umbau
