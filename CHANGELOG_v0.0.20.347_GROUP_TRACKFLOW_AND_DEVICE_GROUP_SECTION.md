# Changelog v0.0.20.347 — Arranger Track-/Gruppen-Flow + DevicePanel Gruppen-Sektion

## Neu
- Clip-Auswahl im Arranger zieht jetzt die zugehörige Spur-Auswahl mit.
- Rechtsklick-Menü direkt auf Track-/Instrument-Zeilen im Arranger.
- Gruppierte Tracks werden als sichtbare Gruppen-Sektion mit Gruppenkopf und eingerückten Mitgliedern dargestellt.
- DevicePanel zeigt für gruppierte Spuren eine Gruppen-Sektion mit Mitgliederliste sowie Batch-Aktionen:
  - `N→G` = NOTE-FX auf alle Instrument-Mitglieder der Gruppe
  - `A→G` = AUDIO-FX auf alle Tracks der Gruppe

## Technisch
- `pydaw/ui/arranger.py`
  - Kontextmenüs für Track- und Gruppenkopf-Zeilen
  - Auswahlhelfer für Track-/Gruppen-Selektion
  - Gruppenkopf-Rendering im Trackbereich
- `pydaw/ui/main_window.py`
  - Spur-Auswahl und Clip-Auswahl besser synchronisiert
- `pydaw/ui/device_panel.py`
  - Gruppen-Strip im Header
  - sichere Batch-FX-Anwendung auf Gruppen
  - `defer_*` Flags für gruppierte FX-Anwendungen
- `pydaw/model/project.py`
  - Default-Projektversion auf `0.0.20.347` angehoben

## Bewusst nicht enthalten
- kein echter Audio-Gruppenbus
- kein Routing-/Mixer-/Playback-Core-Umbau
- keine Änderungen am Audio-Thread
