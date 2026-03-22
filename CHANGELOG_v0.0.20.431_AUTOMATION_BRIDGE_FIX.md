# CHANGELOG v0.0.20.431 — Automation Bridge Fix (MIDI Record → Lane → Playback)

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Kritischer Bug-Fix: MIDI-aufgezeichnete Automation war unsichtbar + nie abgespielt

### Das Problem (vor diesem Fix)

Py_DAW hatte **zwei getrennte Automation-Datenspeicher** die nie synchronisiert wurden:

1. **Legacy-Store** (`project.automation_lanes[track_id][param]`): 
   - Hier schrieb `MidiMappingService._write_automation_point()` rein
   - `AutomationPlaybackService` las hieraus — **ABER mit Format-Bug** (erwartete `dict` mit `"points"` Key, bekam aber eine flat `list`)

2. **Neuer Store** (`AutomationManager._lanes[parameter_id]`):
   - Hier schrieb der `EnhancedAutomationEditor` (UI-Zeichnen) rein
   - `AutomationManager.tick()` las hieraus für Playback

**Ergebnis**: 
- ❌ UI-gezeichnete Automation wurde nie abgespielt (da Playback nur Legacy las)
- ❌ MIDI-aufgezeichnete Automation war in der UI unsichtbar (da UI nur neuen Store las)
- ❌ Legacy-Playback-Pfad crashte still wegen Format-Mismatch

### Die Lösung (Best Practice wie Bitwig/Ableton)

**Ein einheitlicher Datenpfad**: MIDI CC → MidiMappingService → **AutomationManager** (primär) + Legacy (Compat)

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/services/midi_mapping_service.py` | `set_automation_manager()` + `_write_automation_point()` schreibt jetzt in BEIDE Stores |
| `pydaw/services/midi_mapping_service.py` | Write-Mode für Volume/Pan/Device-Params aktiviert |
| `pydaw/services/container.py` | AutomationManager wird an MidiMappingService übergeben |
| `pydaw/services/automation_playback.py` | Format-Bug gefixt: flat list UND dict mit "points" Key werden unterstützt |
| `pydaw/ui/automation_editor.py` | `lane_data_changed` Signal verbunden → Editor repaint bei MIDI-Recording |
| `pydaw/ui/automation_editor.py` | MIDI-recorded Lanes erscheinen in der Parameter-Dropdown-Liste (📈 Icon) |

### Best Practice Analyse (Bitwig / Ableton / Cubase)

Alle großen DAWs haben **einen einzigen Automation-Store** pro Parameter:
- **Ableton**: Breakpoint-Array pro Parameter, Automation Arm global + per Track
- **Bitwig**: AutomatableParameter → Timeline-Envelope, Multi-Lane-Stacking inline
- **Cubase**: Read/Write/Touch/Latch/Cross-Over Modi, Virgin Territory

Py_DAW folgt jetzt dem Bitwig-Muster:
1. ✅ MidiMappingService → AutomationManager._lanes (einheitlicher Store)
2. ✅ AutomationManager.tick() spielt alle Lanes ab (bei "read" Mode)
3. ✅ EnhancedAutomationEditor zeigt MIDI-recorded Punkte live an
4. 🔜 Multi-Lane-Stacking (nächster Schritt)
5. 🔜 Touch/Latch Modi (nächster Schritt)

### Risikobewertung

- **Risiko**: Sehr niedrig — nur additive Bridges, keine bestehende Logik geändert
- **Rückwärtskompatibel**: Legacy-Store wird WEITERHIN geschrieben
- **Kein Audio-Thread-Eingriff**: Alle Änderungen sind GUI-Thread-seitig
