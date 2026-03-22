# CHANGELOG v0.0.20.358 — DAWproject Exporter Scaffold

## Neu
- Neuer sicherer `pydaw/fileio/dawproject_exporter.py` als entkoppelter **Snapshot-Exporter** für `.dawproject`.
- Temp-File-First Pipeline: **Staging → XML/ZIP → Validierung → atomarer Move**.
- Audio-Referenzen werden aus `Project.media` und Audio-Clips gesammelt und unter `audio/` in die ZIP geschrieben.
- `automation_manager_lanes` werden exportseitig pro Track in eine XML-Struktur gemappt.
- Instrument-/Device-Zustände werden konservativ als **Base64-State-Blobs** im XML eingebettet.
- Optionaler **QRunnable** für non-blocking UI-Integration ergänzt.

## Dokumentation
- Neues Architekturpapier: `PROJECT_DOCS/plans/DAWPROJECT_EXPORT_ARCHITECTURE.md`

## Bewusst nicht angefasst
- Kein Eingriff in **Audio-Engine**, **Transport**, **Arranger-Playback**, **Mixer**, **Undo/Redo-Core** oder laufende DSP-Pfade.
- Noch kein Menü-Hook im MainWindow, damit die Änderung vollständig risikoarm im FileIO-Bereich bleibt.
