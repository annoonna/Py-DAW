# CHANGELOG v0.0.20.432 — Multi-Lane Stacking + Touch/Latch Automation Modi

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Neue Features

### 1. Multi-Lane Stacking (Bitwig-Style)

Das Automation-Panel unten zeigt jetzt **mehrere Lanes gleichzeitig**:

```
[Track: Instrument Track]     ┌──────────────────────────────────────┐
[Mode: touch ▼]               │ [Volume ▼]   [linear ▼]   🗑   ×    │
[⋯]                           │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░ │
[+ Lane]                      ├──────────────────────────────────────┤
                              │ [Cutoff ▼]   [bezier ▼]   🗑   ×    │
                              │ ░░████████████░░░░░░░░░░░░░░░░░░░░░ │
                              └──────────────────────────────────────┘
```

- **"+ Lane" Button**: Fügt neue Lane hinzu (bis zu 8 gleichzeitig)
- **"×" Button**: Entfernt eine Lane (mindestens 1 bleibt immer)
- **Jede Lane unabhängig**: Eigener Parameter, eigene Curve-Auswahl
- **"Show Automation in Arranger"**: Öffnet automatisch eine neue Lane

### 2. Touch/Latch Automation Modi

| Modus | Verhalten |
|-------|-----------|
| **off** | Keine Automation |
| **read** | Automation abspielen |
| **write** | Immer aufzeichnen (überschreibt alles) |
| **touch** | Aufzeichnen nur solange Controller bewegt wird. 500ms nach letztem CC → Stop |
| **latch** | Aufzeichnen ab erstem CC. Hält den letzten Wert bis Transport-Stop |

**Touch** ist der natürlichste Modus für Live-Aufnahmen: Drehe einen Knob, die Automation wird aufgezeichnet. Lass los, die Aufnahme stoppt.

**Latch** ist für Fade-Ins/Fade-Outs: Stelle einen Wert ein, und dieser Wert wird konstant geschrieben bis du den Transport stoppst.

### 3. Playback für Touch/Latch

`AutomationPlaybackService` liest jetzt Automation nicht nur bei "read", sondern auch bei "touch" und "latch" Modus. So hörst du bestehende Automation auch während Touch/Latch-Aufnahme.

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/ui/automation_editor.py` | `_LaneStrip` Klasse + Multi-Lane `EnhancedAutomationLanePanel` |
| `pydaw/services/midi_mapping_service.py` | Touch/Latch Timer + `_should_write_automation()` |
| `pydaw/services/automation_playback.py` | Mode-Check erweitert: read + touch + latch |
| `pydaw/ui/automation_lanes.py` | Touch/Latch in Legacy-Panel ComboBox |

## Risikobewertung

- **Multi-Lane**: Additive UI-Erweiterung. Backward-Compat durch `self.editor`/`self.cmb_param` Aliase
- **Touch/Latch**: Additive Logik in MidiMappingService. Keine bestehenden Pfade geändert
- **Kein Audio-Thread-Eingriff**: Alle Änderungen sind GUI-Thread-seitig
