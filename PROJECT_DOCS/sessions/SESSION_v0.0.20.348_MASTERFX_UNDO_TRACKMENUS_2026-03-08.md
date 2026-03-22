# Session v0.0.20.348 — Master-FX hörbar / globales Undo / Track-Menüs repariert

## Kontext
User meldete in v0.0.20.347 mehrere direkte UX-/Funktionsprobleme:
- Master-FX lassen sich zwar setzen, sind aber nicht hörbar.
- Ctrl+Z funktioniert projektweit nicht zuverlässig.
- Track-/Gruppen-Kontextmenüs sind unvollständig oder fehlerhaft.
- Gruppenkopf ist noch nicht einklappbar.
- Track-Umbenennen / Löschen im Menü war defekt.

## Umsetzung
- AudioEngine/HybridEngine so erweitert, dass der **Master-Track-Audio-FX-Chain** im Summenpfad wirklich verarbeitet wird.
- ProjectService um einen **coalesced Snapshot-Undo-Fallback** erweitert.
- Globale **Undo/Redo-Shortcuts** zusätzlich per `QShortcut` als ApplicationShortcut verdrahtet.
- Arranger TrackList erweitert:
  - neues **"Neue Spur hinzufügen"**-Untermenü
  - **Gruppenkopf einklappbar**
  - **Umbenennen** jetzt per sicherem Dialog
  - **Track löschen** repariert
  - leere TrackList-Rechtsklickfläche öffnet ebenfalls Add-Track-Menü
- DevicePanel-Master-Placeholder textlich klarer als **Master Bus** markiert.

## Geänderte Dateien
- `pydaw/audio/audio_engine.py`
- `pydaw/audio/hybrid_engine.py`
- `pydaw/services/project_service.py`
- `pydaw/commands/project_snapshot_edit.py`
- `pydaw/commands/__init__.py`
- `pydaw/ui/actions.py`
- `pydaw/ui/main_window.py`
- `pydaw/ui/arranger.py`
- `pydaw/ui/device_panel.py`
- `pydaw/model/project.py`
- `VERSION`
- Progress-/Latest-/Changelog-Dateien

## Validierung
- `python3 -m py_compile` für alle geänderten Python-Dateien erfolgreich.
- Kein Eingriff in Routing-Core oder Bus-Architektur.

## Nächste sichere Schritte
- Fold-State von Gruppen projektseitig persistieren.
- Snapshot-Undo-Labels bei größeren UI-Aktionen gezielt benennen.
