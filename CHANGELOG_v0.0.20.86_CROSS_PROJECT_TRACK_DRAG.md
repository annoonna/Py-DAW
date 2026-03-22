# CHANGELOG v0.0.20.86 — Cross-Project Track Drag&Drop

**Datum:** 2026-02-15
**Entwickler:** Claude Opus 4.6
**Version:** 0.0.20.86

## Feature: Cross-Project Track Drag aus TrackList

### Problem
Die TrackList (linke Seite im Arranger) hatte keinen Drag-Support. Man konnte
Spuren nicht per Drag&Drop aus einem Projekt-Tab in einen anderen ziehen. Die
Drop-Seite (ArrangerCanvas) war bereits implementiert (v0.0.20.78), aber es
fehlte die **Drag-Initiierung**.

### Lösung

**1. TrackList Drag-Support (`pydaw/ui/arranger.py`):**
- `QListWidget` mit `setDragEnabled(True)` + `DragOnly` Mode
- `ExtendedSelection` für Multi-Track Drag (Ctrl+Klick / Shift+Klick)
- Custom `startDrag()` Override: erstellt `application/x-pydaw-cross-project`
  MIME-Payload mit Track-IDs, Tab-Index, und Flags
- `set_tab_service()` Methode für Tab-Index-Erkennung

**2. ArrangerView Forwarding (`pydaw/ui/arranger.py`):**
- Neues `set_tab_service()` auf ArrangerView-Ebene → leitet an Canvas + TrackList

**3. UI-Refresh nach Drop (`pydaw/ui/arranger_canvas.py`):**
- Nach `copy_tracks_between_tabs()` wird jetzt `project_updated.emit()` aufgerufen
- Dadurch refreshen TrackList, Mixer, DevicePanel, etc. automatisch

**4. MainWindow Wiring (`pydaw/ui/main_window.py`):**
- `set_tab_service` wird jetzt über `ArrangerView` statt direkt auf Canvas aufgerufen

### Workflow
1. Öffne zwei Projekte in Tabs (Ctrl+T / Ctrl+Shift+O)
2. Wechsle zum Quell-Tab
3. Wähle eine oder mehrere Spuren in der TrackList (links)
4. Ziehe per Drag auf den Arranger des Ziel-Tabs
5. Spuren werden mit allen Clips, Device-Chains, MIDI-Notes und Automationen kopiert

### Geänderte Dateien
- `pydaw/ui/arranger.py` — TrackList Drag + ArrangerView.set_tab_service()
- `pydaw/ui/arranger_canvas.py` — project_updated.emit() nach Cross-Project Drop
- `pydaw/ui/main_window.py` — Tab-Service Wiring über ArrangerView
- `pydaw/version.py`, `VERSION`, `pydaw/model/project.py` — Version → 0.0.20.86
