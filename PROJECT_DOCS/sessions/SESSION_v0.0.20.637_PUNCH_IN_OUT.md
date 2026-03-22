# Session Log — v0.0.20.637

**Datum:** 2026-03-19
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2C — Punch In/Out
**Aufgabe:** Punch-Region im Arranger, automatisches Punch In/Out, Pre-/Post-Roll

## Was wurde erledigt

### 1. TransportService — Punch State + Boundary Detection
- `punch_enabled`, `punch_in_beat`, `punch_out_beat`, `pre_roll_bars`, `post_roll_bars`
- Signale: `punch_changed`, `punch_triggered`
- Automatische Boundary-Detection im `_tick()` mit Debounce
- Auto-Stop nach Post-Roll
- Helper: `get_punch_play_start_beat()`, `get_punch_post_stop_beat()`

### 2. Project Model — 5 neue persistierte Felder
- `punch_enabled`, `punch_in_beat`, `punch_out_beat`, `pre_roll_bars`, `post_roll_bars`
- Backward-kompatibel: Defaults für alte Projekte

### 3. Transport Panel — Punch UI
- Punch Checkbox, Pre-Roll SpinBox (0-8 Bars), Post-Roll SpinBox (0-8 Bars)
- Setter-Methoden mit blockSignals

### 4. Arranger Canvas — Visuelle Punch-Region
- Rotes Overlay (alpha 25), durchgehende rote Marker-Linien
- Dreieckige Ruler-Marker, "PUNCH" Label
- Draggable Handles (In/Out), Hover-Cursor
- Kontextmenü: Toggle, "Punch = Loop", "Punch In hier"

### 5. RecordingService — Punch-Aware Recording
- `set_punch()`, `on_punch_triggered()`, `_should_capture_frames()`
- JACK + sounddevice Callbacks: Punch-Guard integriert
- Clip-Start-Beat = punch_in_beat bei Punch-Modus
- Auto-Stop bei Punch-Out

### 6. MainWindow — Komplett verdrahtet
- Arranger ↔ Transport ↔ Recording: alle Signalpfade
- Punch-Sync bei Record-Start
- Punch-State-Restore bei Projekt-Öffnung

## Geänderte Dateien
- pydaw/services/transport_service.py
- pydaw/model/project.py
- pydaw/ui/transport.py
- pydaw/ui/arranger_canvas.py
- pydaw/services/recording_service.py
- pydaw/ui/main_window.py
- pydaw/version.py
- VERSION
- PROJECT_DOCS/ROADMAP_MASTER_PLAN.md (Phase 2C: 3/4 Tasks abgehakt)
- PROJECT_DOCS/progress/TODO.md
- PROJECT_DOCS/progress/DONE.md

## Nächste Schritte
- **Crossfade an Punch-Grenzen** (letzter Task Phase 2C): 5-50ms Crossfade am In/Out-Punkt
- **AP2 Phase 2D — Comping / Take-Lanes**: Loop-Recording, Take-Lanes, Comp-Tool, Flatten
- Optional: Pre-Roll Auto-Seek (Playhead automatisch auf punch_in - pre_roll setzen)

## Offene Fragen an den Auftraggeber
- Crossfade-Länge: Feste 10ms oder konfigurierbar (5-50ms)?
- Soll Pre-Roll den Playhead automatisch an die Startposition (punch_in - pre_roll) seeken?
