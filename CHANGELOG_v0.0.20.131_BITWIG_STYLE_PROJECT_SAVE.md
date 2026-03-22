# CHANGELOG v0.0.20.131 — Bitwig/Ableton-Style Projekt-Speicherung

## 🔴 CRITICAL FIX: Sampler/Instrumente werden beim Laden wiederhergestellt

### Problem
Beim Speichern und Wiederladen gingen ALLE Sampler-Samples, DrumMachine-Samples
und SF2-Instrumente verloren.

### Root Cause
1. `ProjectService.import_audio_to_project()` existierte nicht → Samples nie importiert
2. `_package_project_media()` ignorierte `track.instrument_state` → Pfade nie relativiert
3. `_resolve_project_paths_after_load()` ignorierte `track.instrument_state` → Pfade nie aufgelöst

### Fix (Bitwig/Ableton-Style)
- **Neue Methode `import_audio_to_project()`** auf ProjectService: 
  Samples werden beim Laden in den Sampler/DrumMachine automatisch nach `<project>/media/` kopiert
- **Save**: Alle Assets (Samples, SF2, Instrument-States) werden in `media/` gepackt, 
  Pfade werden relativ gespeichert → Projektordner ist portabel
- **Load**: Alle relativen Pfade werden zurück in absolute Pfade aufgelöst
- **Rückwärtskompatibel**: Alte Projekte laden weiterhin korrekt

### Geänderte Dateien
- `pydaw/services/project_service.py`
- `pydaw/fileio/file_manager.py`
- `pydaw/version.py`, `VERSION`, `pydaw/model/project.py`
