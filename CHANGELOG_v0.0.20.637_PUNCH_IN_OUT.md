# CHANGELOG v0.0.20.637 — Punch In/Out (AP2 Phase 2C)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2C — Punch In/Out

## Was wurde gemacht

### 1. TransportService — Punch State + Signale
- Neue Felder: `punch_enabled`, `punch_in_beat`, `punch_out_beat`, `pre_roll_bars`, `post_roll_bars`
- Signal `punch_changed(bool, float, float)` — UI-Sync bei Punch-Änderungen
- Signal `punch_triggered(str)` — feuert "in"/"out" wenn Playhead Punch-Grenzen kreuzt
- Methoden: `set_punch()`, `set_punch_region()`, `set_pre_roll_bars()`, `set_post_roll_bars()`
- Helper: `get_punch_play_start_beat()`, `get_punch_post_stop_beat()` für Pre/Post-Roll Berechnung
- Automatische Punch-Boundary-Detection im `_tick()` Timer mit Debounce-Flags
- Auto-Stop nach Post-Roll Ende

### 2. Project Model — Persistierung
- Neue Felder im `Project` Dataclass: `punch_enabled`, `punch_in_beat`, `punch_out_beat`, `pre_roll_bars`, `post_roll_bars`
- `from_dict()` / `to_dict()` (via asdict) — backward-kompatibel (Default-Werte für alte Projekte)

### 3. Transport Panel — UI-Widgets
- `chk_punch` Checkbox: "Punch" Toggle mit Tooltip
- `spin_pre_roll` SpinBox: Pre-Roll 0-8 Bars
- `spin_post_roll` SpinBox: Post-Roll 0-8 Bars
- Signale: `punch_toggled`, `pre_roll_changed`, `post_roll_changed`
- Setter: `set_punch()`, `set_pre_roll()`, `set_post_roll()` (blockSignals-safe)

### 4. Arranger Canvas — Visuelle Punch-Region
- Punch-Region als rot-getönte Overlay-Zone im Arranger (subtil, 25 alpha)
- Rote Punch-Marker-Linien (durchgehend von Ruler bis unten)
- Dreieckige Marker am Ruler-Top für Punch In/Out
- "PUNCH" Label im Ruler
- Draggable Punch-Handles im Ruler (gleich wie Loop-Handles, aber rot)
- Hit-Test `_hit_punch_handle()` für In/Out Marker
- Kontextmenü:
  - "Punch aktivieren/deaktivieren" Toggle
  - "Punch = Loop Region übernehmen" (kopiert Loop → Punch)
  - "Punch In hier setzen" (setzt Punch-In an Klickposition)
- Signal `punch_region_committed(bool, float, float)`

### 5. RecordingService — Punch-Aware Recording
- Neue Felder: `_punch_enabled`, `_punch_in_beat`, `_punch_out_beat`, `_punch_recording_active`
- `set_punch(enabled, in_beat, out_beat)` — konfiguriert Punch-Modus
- `on_punch_triggered(boundary)` — von TransportService aufgerufen:
  - "in": Aktiviert Frame-Capture, löscht Pre-Roll-Audio, setzt Start-Beat auf punch_in
  - "out": Stoppt Frame-Capture, ruft `stop_recording()` auf
- `_should_capture_frames()` — zentrale Guard-Methode für alle Audio-Callbacks
- JACK Callback: Punch-Guard integriert (kein Frame-Append außerhalb Punch-Region)
- sounddevice Callback: Punch-Guard integriert
- `start_recording()`: Clip-Start-Beat = `punch_in_beat` statt Playhead-Position
- `stop_recording()`: Reset `_punch_recording_active`

### 6. MainWindow — Vollständige Verdrahtung
- Arranger → Transport: `punch_region_committed` → `set_punch_region()` + `set_punch()`
- Transport Panel → Service: `punch_toggled` → `set_punch()`, Pre/Post-Roll → `set_pre/post_roll_bars()`
- TransportService → UI: `punch_changed` → Arranger + Panel sync, `punch_triggered` → RecordingService
- Punch-State-Sync bei Recording-Start: `rec.set_punch()` vor `start_recording()`
- Punch-State-Restore bei Projekt-Öffnung (Tab-Switch)
- Auto-Uncheck Record-Button bei Punch-Out

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/transport_service.py | Punch state, signals, boundary detection |
| pydaw/model/project.py | 5 neue Felder + from_dict Erweiterung |
| pydaw/ui/transport.py | Punch checkbox, Pre/Post-Roll SpinBoxes |
| pydaw/ui/arranger_canvas.py | Punch-Region visuell, Drag-Handles, Kontextmenü |
| pydaw/services/recording_service.py | Punch-aware Callbacks, set_punch(), on_punch_triggered() |
| pydaw/ui/main_window.py | Signal-Verdrahtung, Handler, Projekt-Restore |
| pydaw/version.py | → 0.0.20.637 |
| VERSION | → 0.0.20.637 |

## Was als nächstes zu tun ist
- **AP2 Phase 2C — Crossfade an Punch-Grenzen**: Kurzer Crossfade (5-50ms) am Punch-In/Out-Punkt um Clicks zu vermeiden
- **AP2 Phase 2D — Comping / Take-Lanes**: Loop-Recording, Take-Lanes, Comp-Tool, Flatten

## Bekannte Probleme / Offene Fragen
- Crossfade an Punch-Grenzen fehlt noch (letzter Task von Phase 2C)
- Pre-Roll Playhead-Seek: Aktuell startet Play an aktueller Position; für perfekten Pre-Roll müsste der Playhead automatisch auf `get_punch_play_start_beat()` gesetzt werden bei Record+Punch
