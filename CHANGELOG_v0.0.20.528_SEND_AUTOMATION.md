# CHANGELOG v0.0.20.528 — Send-Automation (Send-Amount als automatierbarer Parameter)

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (mittel)

---

## Änderungen

### Send-Amount ist jetzt vollständig automatisierbar

**Vorher:** Send-Knobs konnten nur manuell gedreht werden. Kein Weg, Send-Levels über die Zeit zu animieren.

**Nachher:** Send-Amounts verhalten sich jetzt genau wie Volume und Pan — sie sind vollständig automatisierbar:
- Automation-Lanes können im Arranger gezeichnet werden (Pencil-Tool)
- MIDI CC-Controller können per MIDI Learn auf Sends gemappt und aufgenommen werden
- Touch/Latch/Write Automation-Modi funktionieren
- Send-Knobs bewegen sich bei Playback mit der Automation-Kurve
- Douglas-Peucker Auto-Thinning nach Recording

### Technische Details

**Parameter-ID Format:** `trk:{track_id}:send:{fx_track_id}`
- Passt in die bestehende `trk:` Prefix-Familie
- Wird von `_write_cc_automation()` korrekt geparst (track_id an Position [1])
- Serialisiert über `AutomationManager.export_lanes()` ins Projekt-JSON

**Datenfluss:**

```
Zeichnen/CC-Aufnahme → AutomationManager._lanes["trk:X:send:Y"]
                                    ↓
Transport tick → AutomationManager.tick(beat) → interpolate → parameter_changed signal
                                    ↓
MixerStrip._on_send_automation_changed() → knob.setValue() (blockSignals)
                                    ↓
AutomationPlaybackService._on_playhead() → _interp(send-lanes) → apply_automation_value()
                                    ↓
ProjectService.apply_automation_value("send:fx_id") → track.sends[].amount = value
                                    ↓
_emit_updated() → AudioEngine.rebuild_fx_maps() → HybridAudioCallback._send_bus_map
```

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/ui/mixer.py` | `_register_send_automation()`, `_on_send_automation_changed()`, "📈 Automation im Arranger zeigen" im Kontextmenü |
| `pydaw/services/project_service.py` | `apply_automation_value()` erweitert: `send:{fx_track_id}` Branch |
| `pydaw/services/automation_playback.py` | Dynamische Send-Lane-Erkennung in `_on_playhead()` |

---

## Nichts kaputt gemacht ✅

- Volume/Pan-Automation unverändert (gleicher `_targets`-Loop wie vorher)
- Manuelles Send-Knob-Drehen funktioniert weiterhin (valueChanged Pfad)
- Pre/Post Toggle (v527) unverändert
- Audio-Engine Send-Bus-Routing unverändert (empfängt neue Werte über bestehenden `_emit_updated()` → `rebuild_fx_maps()` Pfad)
- Projekt-Format abwärtskompatibel (Send-Lanes sind reguläre AutomationManager-Lanes)
- Alle Plugin-Widgets (VST, CLAP, LV2 etc.) unberührt
