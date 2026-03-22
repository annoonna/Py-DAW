# Session-Log: v0.0.20.358 — Snapshot-sicherer DAWproject Exporter Scaffold

**Datum**: 2026-03-08
**Bearbeiter**: GPT-5
**Aufgabe**: Sichere DAWproject-Export-Architektur + Python-Skelett implementieren, ohne die Kern-Engine der DAW zu berühren
**Ausgangsversion**: 0.0.20.357
**Ergebnisversion**: 0.0.20.358

## Problem-Beschreibung

Die DAW kann `.dawproject` bereits importieren, aber für den Export fehlte noch ein
sauber entkoppelter Pfad. Das Hauptrisiko wäre gewesen, den Export direkt an die
laufende Session, das UI oder sogar die Engine zu koppeln.

Ziel dieser Session war deshalb **kein riskanter Vollausbau**, sondern eine sichere
Grundlage:
- Snapshot statt Live-Projekt
- Temp-File-First statt direktem Zielschreiben
- XML/ZIP-Aufbau im FileIO-Bereich
- optionaler QRunnable statt UI-Blockade

## Architektur-Entscheidungen

### Warum Snapshot via `to_dict()` / `from_dict()`?
- komplette tiefe Entkopplung von Listen/Dicts/Dataclasses
- keine Seiteneffekte auf laufende UI-/Undo-/Playback-Objekte
- robust gegen spätere Modell-Erweiterungen

### Warum eigener `DawProjectExporter` als Data Mapper?
- FileIO bleibt isoliert
- kein Eingriff in `ProjectService`-Mutationen oder Audio-Callback
- Export-Logik ist testbar und später separat im UI verdrahtbar

### Warum Temp-File-First?
- halbfertige Archive landen nicht am finalen Ziel
- XML/ZIP-Validierung kann vor dem finalen Replace laufen
- sauberer Fehlerpfad ohne Projektkorruption

### Warum vorerst kein MainWindow-Hook?
- oberste Direktive: **nichts kaputt machen**
- so bleibt die Änderung vollständig in `pydaw/fileio/` + Doku
- UI-Integration kann als nächster sicherer Schritt separat erfolgen

## Geänderte Dateien

### Neuer Code
- `pydaw/fileio/dawproject_exporter.py`
  - `DawProjectSnapshotFactory`
  - `DawProjectExportRequest` / `DawProjectExportResult`
  - `DawProjectExporter`
  - `build_dawproject_export_request()`
  - `export_dawproject()`
  - `DawProjectExportRunnable` (optional, PyQt6)

### Doku
- `PROJECT_DOCS/plans/DAWPROJECT_EXPORT_ARCHITECTURE.md`
- `CHANGELOG_v0.0.20.358_DAWPROJECT_EXPORTER_SCAFFOLD.md`

### Versions-/Indexdateien
- `VERSION`
- `pydaw/version.py`
- `pydaw/model/project.py`
- `pydaw/fileio/__init__.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/progress/LATEST.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Export-Datenfluss

1. Live-Project → tiefe Snapshot-Kopie
2. Snapshot → Mapping in `project.xml` / `metadata.xml`
3. Audio-Referenzen → `audio/` im Staging-Ordner
4. Plugin-/Instrument-States → Base64-Blob im XML
5. ZIP bauen → validieren → atomar ins Ziel verschieben

## Was der erste Scaffold bereits kann

- BPM + Taktart exportieren
- Spuren mit Grundparametern (Volume/Pan/Mute/Solo) exportieren
- MIDI-Clips + Noten exportieren
- Audio-Clips mit Referenz auf `audio/...` exportieren
- `automation_manager_lanes` pro Spur in eine erste XML-Struktur mappen
- Instrument-/Device-Zustände konservativ als Base64-XML-Blobs einbetten
- optional per `QRunnable` im Hintergrund starten

## Bewusst NICHT angefasst

- keine Änderung an Audio-Engine / Hybrid-Callback
- keine Änderung an Transport / Playback / Mixer
- kein neuer MainWindow-Menüpfad in dieser Session
- kein riskanter Eingriff in Undo/Redo oder Live-Session-Objekte

## Tests

- ✅ Syntax-Check des neuen Exporter-Moduls bestanden
- ✅ Import des neuen Moduls über `pydaw.fileio` bestanden
- ✅ Smoke-Test: minimales Projekt erfolgreich als `.dawproject` geschrieben
- ✅ ZIP-Validierung: `project.xml` + `metadata.xml` vorhanden und parsebar

## Nächste Schritte

- [ ] Sicheren MainWindow-Menü-Hook `Datei → DAWproject exportieren…` ergänzen
- [ ] ProgressDialog + `QThreadPool` für echten UI-Export ergänzen
- [ ] Roundtrip-Smoke-Test (Export → Import in leeres Projekt) ergänzen
- [ ] Optional später VST3/CLAP-State-Mapping verfeinern, wenn echte Chunk-Daten im Modell vorliegen
