# CHANGELOG v0.0.20.529 — Send MIDI Learn (CC-Controller auf Send-Knobs)

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (klein)

---

## Änderung

### MIDI Learn für Send-Knobs

**Vorher:** Send-Knobs konnten nur mit der Maus bedient werden. MIDI-Controller hatten keinen Zugang zu Sends.

**Nachher:** Jeder Send-Knob unterstützt jetzt MIDI Learn — genau wie alle anderen Parameter in Py_DAW:
- Rechtsklick → "🎛 MIDI Learn" → nächsten CC drehen → Knob reagiert ab sofort
- Roter Border als visuelles Feedback im Learn-Mode
- CC-Mapping überlebt Widget-Rebuild (persistent registry)
- Menü zeigt aktive CC-Nummer: "🎛 MIDI Learn (CC 7)"
- "🚫 MIDI Learn zurücksetzen" entfernt Mapping komplett
- CC-Änderungen schreiben Automation-Breakpoints wenn Track-Mode = write/touch/latch

**Datenfluss:**
```
MIDI CC → AutomationManager.handle_midi_message()
           → cc_listeners[(ch, cc)] = send_knob
           → knob.setValue(scaled_value)
           → _write_cc_automation(knob, val)  [weil _pydaw_param_id gesetzt]
           → AutomationLane.points.append(BreakPoint)
```

---

## Geänderte Datei

- `pydaw/ui/mixer.py` (+55 Zeilen): `_start_send_midi_learn()`, `_reset_send_midi_learn()`, `_pydaw_param_id` Tag, CC re-registration in `_register_send_automation()`, erweiterte Kontextmenü-Einträge

## Nichts kaputt gemacht ✅

- Bestehende MIDI Learn für alle anderen Widgets (Instruments, FX) unverändert
- Send-Knob-Mausbedienung unverändert
- Pre/Post Toggle unverändert
- Send-Automation (v528) unverändert
- Audio-Engine unberührt
