# CHANGELOG v0.0.20.78 — Multi-Project Tabs Polish

**Datum:** 2026-02-15
**Entwickler:** Claude Opus 4.6

## Neue Features

### Cross-Project Drag&Drop im ArrangerCanvas
- Tracks und Clips können jetzt direkt aus einem anderen Tab in den Arranger gezogen werden
- MIME-Type `application/x-pydaw-cross-project` wird im Canvas akzeptiert
- Tracks: `copy_tracks_between_tabs()` mit Device-Chains, Automationen, Routing
- Clips: `copy_clips_between_tabs()` auf den Track unter dem Cursor
- Neuer `dragMoveEvent` in ArrangerCanvas für sauberes Drag-Tracking

### Tab-Reorder per Drag&Drop
- Tabs in der Projekt-Tab-Leiste können jetzt per Drag&Drop umsortiert werden
- `QTabBar.setMovable(True)` aktiviert native Qt-Drag-Reorder
- `ProjectTabService.move_tab(from, to)` hält den aktiven Index konsistent
- Interne Tab-Liste und active_idx werden korrekt synchronisiert

### Ctrl+Tab / Ctrl+Shift+Tab Tab-Navigation
- **Ctrl+Tab** → nächster Tab (wrapping)
- **Ctrl+Shift+Tab** → vorheriger Tab (wrapping)
- Navigation nur aktiv wenn mehr als 1 Tab offen
- Nutzt Qt QShortcut für globale Shortcuts

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/ui/arranger_canvas.py` | Cross-project drop handler, dragMoveEvent, set_tab_service() |
| `pydaw/ui/project_tab_bar.py` | setMovable(True), tabMoved handler |
| `pydaw/ui/main_window.py` | Ctrl+Tab shortcuts, tab_next/prev, canvas tab_service wiring |
| `pydaw/services/project_tab_service.py` | move_tab() Methode |
| `pydaw/version.py` | → 0.0.20.78 |
| `pydaw/model/project.py` | Version-String → 0.0.20.78 |
| `VERSION` | → 0.0.20.78 |
