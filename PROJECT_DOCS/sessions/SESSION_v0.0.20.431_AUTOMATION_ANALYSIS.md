# Session v0.0.20.431 — Automation Deep Analysis & Critical Bridge Fix

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## 🔍 TIEFENANALYSE: Warum Automation aktuell nicht funktioniert

### Das Kernproblem: ZWEI getrennte Datenspeicher

Py_DAW hat **zwei komplett getrennte Automation-Systeme**, die nie synchronisiert werden:

| System | Wo gespeichert | Format | Wer schreibt | Wer liest |
|--------|---------------|--------|-------------|-----------|
| **Legacy** | `project.automation_lanes[track_id][param]` | `[{beat, value}, ...]` flat list | `MidiMappingService._write_automation_point()` | `AutomationPlaybackService` (ABER mit Format-Bug!) |
| **Neu (v0.0.20.89)** | `AutomationManager._lanes[parameter_id]` | `AutomationLane` mit `BreakPoint`-Objekten | `EnhancedAutomationEditor` (UI-Zeichnen) | `AutomationManager.tick()` |

**→ Wenn du in der Automation Lane zeichnest**, landen die Punkte in `AutomationManager._lanes` — der Playback-Code `AutomationPlaybackService` schaut aber in `project.automation_lanes` (Legacy). **Ergebnis: Gezeichnete Automation wird nie abgespielt.**

**→ Wenn du einen MIDI-Controller bewegst** (im Write-Mode), schreibt `MidiMappingService._write_automation_point()` in `project.automation_lanes` (Legacy) — aber die `EnhancedAutomationEditor` UI liest aus `AutomationManager._lanes`. **Ergebnis: MIDI-aufgezeichnete Automation erscheint nie in der UI.**

### Format-Bug im Legacy-Pfad

Selbst INNERHALB des Legacy-Pfads gibt es einen Fehler:

```python
# MidiMappingService SCHREIBT:
tlanes[param] = [{beat: ..., value: ...}, ...]  # FLAT LIST

# AutomationPlaybackService LIEST:
lane = tlanes.get(param)       # → flat list
points = lane.get("points")    # → AttributeError! List hat kein .get()
```

Die `AutomationPlaybackService._on_playhead()` erwartet `dict` mit `"points"` Key, bekommt aber eine `list`. Dadurch crasht der Lookup still (try/except) und die Automation wird ignoriert.

---

## 📊 Wie andere DAWs es machen (Best Practice)

### Ableton Live
- **Single Automation Store**: Alle Automation (gezeichnet, aufgenommen, MIDI) landet im selben Breakpoint-Array pro Parameter pro Clip/Arrangement
- **Automation Arm**: Globaler "Automation Arm" Button + per-Track überschreibbar
- **Write Recording**: Transport Play + Arm aktiv + Parameter bewegt → Punkte werden in Echtzeit geschrieben
- **Touch vs Latch**: Touch = nur solange der Regler berührt wird; Latch = schreibt weiter bis Stop
- **Multi-Lane**: Jeder Track kann BELIEBIG viele Automation-Lanes zeigen (aufklappbar unter dem Clip-Bereich)
- **Inline im Arranger**: Lanes sind TEIL des Arrangeurs, nicht ein separates Panel

### Bitwig Studio
- **Unified Store**: AutomatableParameter-Klasse mit internem Timeline-Envelope
- **Per-Parameter Automation Lanes**: Jeder Parameter hat seine eigene Lane, die inline unter dem Track erscheint
- **MIDI CC Mapping → Automation Recording**: CC-Wert wird durch den AutomatableParameter geroutet → wenn Armed, wird ein Breakpoint geschrieben
- **Multi-Lane Stacking**: Mehrere Lanes pro Track gleichzeitig sichtbar, mit "+" Button für weitere
- **Bezier Curves**: Freie Kurvenformen zwischen Breakpoints

### Cubase
- **Read/Write/Touch/Latch/Cross-Over**: 5 Automation-Modi
- **Virgin Territory**: Bereiche ohne Punkte behalten den manuellen Wert
- **Global Write Enable**: In der Toolbar + per Track/Channel
- **Controller Lane im Key Editor**: Für MIDI CC direkt sichtbar im Piano Roll

### Gemeinsamer Nenner (Best Practice):
1. **EIN Datenspeicher** für alle Automation-Quellen
2. **Bridge**: MIDI CC → AutomatableParameter → AutomationLane (immer derselbe Pfad)
3. **Transport-gekoppelt**: Write = Recording passiert NUR bei Play + Arm
4. **Multi-Lane**: Mehrere Parameter gleichzeitig sichtbar
5. **Inline im Arranger**: Automation-Lanes als erweiterte Track-Zeilen

---

## 🔧 IMPLEMENTIERUNGSPLAN (Nichts kaputt machen!)

### Fix 1: Bridge — MidiMappingService schreibt in AutomationManager (KRITISCH)
**Risiko**: Sehr niedrig — addiert nur eine Brücke, ändert nichts am bestehenden Pfad

```
MidiMappingService._write_automation_point()
  ├── BISHER: project.automation_lanes[track_id][param] = [...] (Legacy, broken)
  └── NEU:    AutomationManager.get_or_create_lane(pid).add_point(BreakPoint)
              + Legacy-Store AUCH updaten (für Abwärtskompatibilität)
```

### Fix 2: AutomationManager.tick() auch von MidiMappingService-Punkten speisen
Bereits gelöst durch Fix 1 — wenn die Punkte im richtigen Store landen, funktioniert tick().

### Fix 3: AutomationPlaybackService Legacy-Format-Bug fixen
```python
# VORHER (broken):
points = lane.get("points")  # fails on flat list

# NACHHER (safe):
if isinstance(lane, list):
    points = lane
elif isinstance(lane, dict):
    points = lane.get("points", [])
```

### Fix 4: Multi-Lane-Sichtbarkeit
- Neues Widget `MultiLaneStack` im Arranger
- Zeigt N Automation-Lanes übereinander (wie Bitwig)
- "+" Button zum Hinzufügen weiterer Parameter-Lanes
- Jede Lane unabhängig editierbar

### Fix 5: Transport-gekoppeltes Write-Recording
- `automation_mode == "write"` + `transport.playing == True` → schreibe Breakpoints
- Wenn Transport stoppt → write-mode automatisch → read

---

## 📁 Betroffene Dateien

| Datei | Änderung | Risiko |
|-------|----------|--------|
| `services/midi_mapping_service.py` | Bridge zu AutomationManager | Niedrig |
| `services/automation_playback.py` | Format-Bug fix | Niedrig |
| `services/container.py` | AutomationManager-Referenz an MidiMappingService | Niedrig |
| `ui/automation_editor.py` | Multi-Lane Stack | Mittel (nur UI) |
| `audio/automatable_parameter.py` | Keine Änderung nötig | - |

---
