# Session Log — v0.0.20.433 CC→Automation Recording

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Ausgangspunkt**: v0.0.20.432

## Aufgabe

User konnte MIDI-Controller-Knobs/Slider per MIDI Learn mappen (CC23 ch0 → Bach Orgel Parameter), 
aber beim Drehen der physischen Regler wurde NIE eine Automation-Kurve aufgezeichnet — obwohl 
write/touch/latch Modi existieren.

## Tiefenanalyse

### Root Cause: Zwei getrennte MIDI-CC-Pfade

1. **AutomationManager Fast Path** (MIDI Learn via Rechtsklick auf Knob):
   - CC → `handle_midi_message()` → `_midi_cc_listeners` → `widget.handle_midi_cc(val)`
   - Bewegt Knob visuell + ändert Audio-Parameter
   - **Schreibt KEINE Automation-Breakpoints**

2. **MidiMappingService** (separater Mapping-Dialog mit `project.midi_mappings`):
   - CC → `handle_mido_message()` → `_apply_param()` → `_write_automation_point()`
   - Schreibt Automation bei write/touch/latch
   - **Weiß nichts vom Fast Path Mapping**

### Warum zwei Pfade?
- Fast Path (v0.0.20.397-399): Für sofortige, low-latency Knob-Updates
- MidiMappingService (v0.0.20.397): Für persistente, projektweite Mappings
- Die Automation-Write-Fähigkeit wurde nur in den MidiMappingService eingebaut (v0.0.20.431-432)

## Lösung

### 1. `_write_cc_automation()` in AutomationManager
- Nach Widget-Dispatch → prüft `_pydaw_param_id` oder `_parameter_id`
- Parsed `track_id` aus `parameter_id` (Format: `trk:{tid}:{param}`)
- Prüft `track.automation_mode` 
- Schreibt BreakPoint in `AutomationManager._lanes` (primär) + legacy Store
- Emittiert `lane_data_changed` für Live-UI-Repaint

### 2. Transport+Project References
- `AutomationManager.set_transport(transport)` für `current_beat`
- `AutomationManager.set_project(project)` für `track.automation_mode`
- Gewired in `container.py`

### 3. ● REC Button im Automation-Panel
- Toggle: Touch-Modus ↔ Read-Modus
- Leuchtet rot bei aktiver Aufnahme
- Synchronisiert mit Mode-Dropdown

## Geänderte Dateien

- `pydaw/audio/automatable_parameter.py` — 3 neue Methoden, ~80 Zeilen
- `pydaw/services/container.py` — 6 Zeilen (Wiring)
- `pydaw/ui/automation_editor.py` — REC Button + Handler, ~30 Zeilen

## Risiko: MINIMAL
- Alle Änderungen additiv
- Kein bestehender Code modifiziert
- Kein Audio-Thread-Eingriff
- Try/except wrapped
