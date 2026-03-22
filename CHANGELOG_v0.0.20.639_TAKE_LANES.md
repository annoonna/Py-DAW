# CHANGELOG v0.0.20.639 — Comping / Take-Lanes (AP2 Phase 2D)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2D — Comping / Take-Lanes

## Was wurde gemacht

### 1. Datenmodell (pydaw/model/project.py)
- `CompRegion` Dataclass: start_beat, end_beat, source_clip_id, crossfade_beats
- `Clip`: Neue Felder `take_group_id`, `take_index`, `is_comp_active`
- `Track`: Neue Felder `take_lanes_visible`, `take_lanes_height`
- Alle Felder backward-kompatibel (Defaults für bestehende Projekte)

### 2. TakeService (pydaw/services/take_service.py) — NEU
- `create_take_group()` — erzeugt neue Take-Gruppen-ID
- `get_takes_for_group()` — alle Takes einer Gruppe, sortiert nach take_index
- `get_take_groups_for_track()` — alle Take-Gruppen eines Tracks
- `get_active_take()` / `set_active_take()` — aktiven Take verwalten
- `add_take_to_group()` — Take hinzufügen (optional als aktiv)
- `delete_take()` — Take löschen (aktiviert vorherigen Take falls nötig)
- `rename_take()` — Take umbenennen
- `flatten_take_group()` — nur aktiven Take behalten, Rest löschen
- `toggle_take_lanes()` — Take-Lanes ein/ausblenden
- `has_takes()` — prüft ob Track Takes hat

### 3. Loop-Recording (pydaw/services/recording_service.py)
- `set_loop_recording()` / `is_loop_recording()` — Loop-Recording Modus
- `set_take_service()` — TakeService verdrahten
- `set_on_take_created()` — Callback für Take-Erstellung
- `on_loop_boundary()` — bei jedem Loop-Wrap:
  - Speichert aktuelle Frames als WAV (pro Track)
  - Erzeugt Take-Gruppe (erster Pass) oder fügt Take hinzu
  - Feuert Callback für Clip-Erstellung + Take-Metadaten
  - Leert Frame-Buffer für nächsten Pass
- `_generate_take_path()` — eindeutige WAV-Pfade pro Take

### 4. TransportService — Loop-Boundary Signal
- Neues Signal `loop_boundary_reached` — feuert bei jedem Loop-Wrap
- In `_tick()`: emit nach Playhead-Reset auf loop_start

### 5. Arranger Canvas — Take-Lane Visualisierung + Kontextmenü
- `_take_service` Referenz für Kontextmenü-Zugriff
- Take-Lanes werden visuell unter dem Haupttrack gerendert:
  - Inaktive Takes als gedimmte rote Clips (opacity 0.5)
  - Label "Take N" pro Lane
  - Nur sichtbar wenn `track.take_lanes_visible = True`
- Kontextmenü-Erweiterung bei Clips mit take_group_id:
  - "Diesen Take aktivieren" → set_active_take()
  - "Take-Lanes ein/ausblenden" → toggle_take_lanes()
  - "Flatten" → flatten_take_group()
  - "Diesen Take löschen" → delete_take()

### 6. MainWindow — Verdrahtung
- `loop_boundary_reached` → `_on_loop_boundary_reached()` → RecordingService
- `_setup_loop_recording_for_record_start()` — aktiviert Loop-Recording automatisch wenn Transport Loop aktiv
- Take-Erstellungs-Callback: importiert WAV, setzt Take-Metadaten, zeigt Take-Lanes
- TakeService → Arranger Canvas verdrahtet

### 7. ServiceContainer — TakeService
- Import + Initialisierung + Wiring in Container

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/model/project.py | CompRegion, Clip take_*, Track take_lanes_* |
| pydaw/services/take_service.py | **NEU** — kompletter TakeService |
| pydaw/services/recording_service.py | Loop-Recording, on_loop_boundary() |
| pydaw/services/transport_service.py | loop_boundary_reached Signal |
| pydaw/ui/arranger_canvas.py | Take-Lane Rendering + Kontextmenü |
| pydaw/ui/main_window.py | Loop-Recording Setup, Verdrahtung |
| pydaw/services/container.py | TakeService Integration |
| pydaw/version.py | → 0.0.20.639 |
| VERSION | → 0.0.20.639 |

## Was als nächstes zu tun ist
- **Comp-Tool**: Bereiche aus verschiedenen Takes per Klick/Drag auswählen (CompRegion-basiert)
- Dann weiter mit **AP5 (Routing)** oder **AP3 (Warp)** gemäß Roadmap-Priorität
