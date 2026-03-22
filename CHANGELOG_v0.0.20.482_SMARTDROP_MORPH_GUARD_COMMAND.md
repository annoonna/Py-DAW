# v0.0.20.482 — SmartDrop Morphing-Guard-Command vorbereitet

## Neu

- Neues Modul `pydaw/services/smartdrop_morph_guard.py` baut einen nicht-mutierenden Audio→Instrument-Morphing-Plan mit `preview / validate / apply`-Schema.
- `ProjectService` kapselt diesen Plan jetzt über eigene Guard-Methoden.
- `MainWindow` besitzt einen zentralen Guard-Handler für geblockte Instrument→Audio-Drops.
- ArrangerCanvas und TrackList leiten geblockte Instrument→Audio-Fälle an den Guard weiter.
- `smartdrop_rules.py` bezieht die Audio-Spur-Preview aus demselben Guard-Plan.

## Sicherheit

- Weiterhin **kein** echtes Audio→Instrument-Morphing
- Weiterhin **kein** Routing-Umbau
- Weiterhin **keine** Projektmutation im Guard-Apply-Hook
