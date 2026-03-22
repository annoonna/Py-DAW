# CHANGELOG v0.0.20.433 — CC→Automation Recording für MIDI Learn Fast Path

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Kritischer Bug-Fix: MIDI Learn Knob-Drehungen wurden nie in Automation-Lanes aufgezeichnet

### Das Problem (vor diesem Fix)

Py_DAW hatte **zwei getrennte MIDI-CC-Pfade** die nie verbunden waren:

**Pfad 1 — AutomationManager Fast Path (MIDI Learn via Rechtsklick):**
```
MIDI CC Input
  → AutomationManager.handle_midi_message()
    → _midi_cc_listeners[(ch, cc)] = widget
      → widget.handle_midi_cc(val)
        → Knob dreht sich visuell + Audio-Parameter ändert sich
        → ❌ KEINE Automation-Aufzeichnung!
```

**Pfad 2 — MidiMappingService (separater Mapping-Dialog):**
```
MIDI CC Input
  → MidiMappingService.handle_mido_message()
    → project.midi_mappings[] Lookup
      → _apply_param() → _should_write_automation()
        → ✅ _write_automation_point() bei write/touch/latch
```

**Ergebnis**: Wenn ein User per Rechtsklick → MIDI Learn einen CC an einen Knob mappte
(z.B. CC23 ch0 → Bach Orgel Parameter), bewegte sich der Knob, aber es wurde **nie**
ein Automation-Breakpoint geschrieben — egal welcher Mode (write/touch/latch) aktiv war.

### Die Lösung (v0.0.20.433)

Der AutomationManager Fast Path schreibt jetzt **auch Automation-Breakpoints**, wenn
der Track in write/touch/latch Mode ist.

Neuer Datenfluss:
```
MIDI CC Input
  → AutomationManager.handle_midi_message()
    → widget.handle_midi_cc(val)     ← visuell + audio (wie vorher)
    → _write_cc_automation(widget, val)  ← NEU: Automation-Breakpoint schreiben
      → Prüft widget._pydaw_param_id oder widget._parameter_id
      → Prüft track.automation_mode (write/touch/latch)
      → Schreibt BreakPoint in AutomationManager._lanes (primär)
      → Schreibt in project.automation_lanes (legacy/compat)
      → Emittiert lane_data_changed → UI-Repaint (live Kurven!)
```

### Neues Feature: ● REC Button

Im Automation-Panel (unten) gibt es jetzt einen **● REC Button**:
- Klick → schaltet auf **Touch-Modus** (ideal für Live-Aufnahme)
- Nochmal klicken → zurück auf **Read-Modus**
- Leuchtet **rot** wenn Aufnahme aktiv
- Synchronisiert sich mit dem Mode-Dropdown

### Best Practice Workflow für Automation-Aufnahme

1. **Knob per MIDI Learn mappen**: Rechtsklick auf Knob → MIDI Learn → Controller bewegen
2. **REC aktivieren**: ● REC Button im Automation-Panel drücken (oder Mode → touch/write)
3. **Transport starten**: Play drücken
4. **Controller drehen**: Kurve wird LIVE in die Automation-Lane geschrieben
5. **Ergebnis ansehen**: "Show Automation in Arranger" zeigt die aufgezeichnete Kurve

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/automatable_parameter.py` | `set_transport()` + `set_project()` + `_write_cc_automation()` in AutomationManager |
| `pydaw/services/container.py` | Wiring: transport + project → AutomationManager |
| `pydaw/ui/automation_editor.py` | ● REC Button + `_on_rec_toggled()` + Mode/REC Sync |

## Risikobewertung

- **Kein bestehender Code geändert**: Alle Änderungen sind rein additiv
- **`_write_cc_automation()`**: Wrapped in try/except, scheitert still wenn Referenzen fehlen
- **REC Button**: Reines UI-Feature, delegiert an bestehende `_on_mode_changed()` Logik
- **Kein Audio-Thread-Eingriff**: Alle Änderungen sind GUI-Thread-seitig
- **Backward-compat**: Legacy-Store wird weiterhin parallel geschrieben
