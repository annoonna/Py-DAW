# CHANGELOG v0.0.20.658 — DAWproject Roundtrip (AP10 Phase 10C)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP10, Phase 10C — DAWproject Roundtrip

## Was wurde gemacht

### 1. Plugin-Mapping (dawproject_plugin_map.py) — NEU
- Bidirektionale Mapping-Schicht: Py_DAW plugin_id ↔ DAWproject deviceID
- Vollständiges Internal-Mapping: 28 Einträge (Instrumente + FX + Note-FX)
- VST3/CLAP/LV2/LADSPA Format-Inferenz aus Plugin-ID Prefix
- Well-Known-Plugins Datenbank (Serum, Diva, Zebra2, Surge XT, Vital, etc.)
- `resolve_plugin_identity()` API für Best-Effort Lookup aus beliebigem Identifier

### 2. Vollständiger DAWproject Export (Exporter erweitert)
- **Send-Export**: Track.sends → `<Sends>/<Send destination= volume= preFader=>`
- **Plugin-Mapping Integration**: Alle Plugin deviceIDs werden via Plugin-Map auf
  DAWproject-spec-konforme IDs gemappt (z.B. `drum_machine` → `device:ChronoScaleStudio/ProDrumMachine`)
- FX-Chain Devices ebenfalls mit Mapping versehen

### 3. Vollständiger DAWproject Import (Importer komplett neu geschrieben)
- **Automation-Import**: `<AutomationLanes>` → `automation_manager_lanes` inkl. Bezier-Curves
- **Plugin-State Import**: Base64-State-Blobs aus `<State>` Elementen + Archive-Dateien
- **Send-Import**: `<Sends>` → `Track.sends` mit korrektem ID-Remapping
- **Group-Hierarchie**: `groupId`/`groupName` → `track_group_id`/`track_group_name`
- **Clip Extensions**: Gain, Pan, Pitch, Stretch, Muted, Reversed, ClipAutomation
- **Per-Note Expressions**: `<NoteExpressions>/<Expression>` → `MidiNote.expressions`
- **Device Chain Import**: Instrument + Note-FX + Audio-FX Chains komplett
- **Track-ID Remapping**: Alte IDs werden korrekt auf neue gemappt (für Sends + Groups)
- **pydawKind Roundtrip**: ChronoScaleStudio-eigene Track-Types bleiben erhalten

### 4. Roundtrip-Test Framework (dawproject_roundtrip_test.py) — NEU
- `run_roundtrip_test(project)` → Export → Import → Vergleich
- Vergleicht: Transport, Tracks, Clips, MIDI-Noten, Automation, Sends
- `RoundtripReport` mit Severity-Stufen (error/warning/info)
- Toleranzbasierter Float-Vergleich für Volume/Pan/Timing
- Übersichtliches `report.summary()` Text-Format

### 5. Projekt-Versionierung (project_version_service.py) — NEU
- `ProjectVersionService` mit Git-like Snapshots
- Auto-Snapshots auf Save (konfigurierbares Intervall, Default 5min)
- Manuelle benannte Snapshots (wie Git Tags)
- SHA-256 Content-Hashing zur Duplikat-Erkennung
- Manifest-basierter Index mit Metadaten
- `diff_snapshots()` — Vergleich beliebiger Snapshots (Tracks, Clips, Automation, Media)
- `restore_snapshot()` — Pre-Restore Backup + Wiederherstellung
- Auto-Pruning (max 50 Auto-Snapshots)
- Disk-Usage Reporting

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/fileio/dawproject_plugin_map.py | **NEU** — Plugin-Mapping VST3/CLAP/LV2 ↔ DAWproject |
| pydaw/fileio/dawproject_importer.py | **KOMPLETT NEU** — Automation, Plugins, Sends, Groups, Extensions |
| pydaw/fileio/dawproject_exporter.py | Erweitert: Send-Export, Plugin-Mapping Integration |
| pydaw/fileio/dawproject_roundtrip_test.py | **NEU** — Export → Import → Vergleich Framework |
| pydaw/services/project_version_service.py | **NEU** — Git-like Snapshots, Diff, Auto-Backup |
| pydaw/fileio/__init__.py | Neue Exports: Importer, PluginMap, RoundtripTest |
| VERSION | 0.0.20.657 → 0.0.20.658 |
| pydaw/version.py | 0.0.20.657 → 0.0.20.658 |

## Was als nächstes zu tun ist
- **AP10 Phase 10D** — Cloud & Collaboration (Git-basiertes Backup, Projekt-Sharing)
- **AP1 Phase 1C** — Rust Plugin-Hosting (VST3/CLAP in Rust via vst3-sys/clack-host)
- **AP1 Phase 1D** — Schrittweise Rust-Migration

## Bekannte Probleme / Offene Fragen
- Roundtrip-Test vergleicht Automation nur auf Punkt-Zähler-Ebene (keine ID-genaue Zuordnung
  wegen Remapping — das ist im DAWproject-Format systembedingt)
- Audio-Datei Roundtrip erfordert include_media=True und echte Audio-Dateien im Projekt
- Well-Known-Plugins DB enthält bisher nur 7 gängige Plugins — erweiterbar

### 6. Projekt-Sharing Service (project_sharing_service.py) — NEU
- `ProjectShareExporter` erstellt self-contained .pydaw-share Pakete
- Sammelt + embeddet alle Audio-Dateien (mit Duplikat-Vermeidung)
- README.txt Generator mit Projekt-Statistiken
- `ShareMetadata` mit Tags, Duration, Content-Hash
- `ProjectShareImporter` mit Replace- und Merge-Modus
- `preview_shared_project()` für UI-Vorschau ohne Import
- Konfigurierbar: Media ein/ausschließen, persönliche Daten entfernen

### 7. Collaborative Editing Foundation (project_merge_service.py) — NEU
- `ProjectMergeEngine` — 3-Way Merge (Base + Ours + Theirs)
- Automatischer Merge für nicht-konfligierende Änderungen
- Konflikt-Erkennung für überlappende Modifikationen
- 3 Strategien: ours-wins, theirs-wins, manual
- Merge für: Transport, Tracks, Clips, MIDI Notes, Automation, Media
- `merge_from_snapshots()` Integration mit ProjectVersionService
- `MergeResult.summary()` Übersicht

### 8. UI Responsive Toolbar (toolbar.py + main_window.py)
- ToolBarPanel passt sich an Fensterbreite an:
  - < 500px: Loop + Follow + Python-Logo ausgeblendet
  - < 700px: Loop + Python-Logo ausgeblendet
  - < 900px: nur Loop-Felder ausgeblendet
- MainWindow: Tools-Toolbar bei < 600px komplett ausgeblendet
