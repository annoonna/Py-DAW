# CHANGELOG v0.0.20.435 — Fix: Automation Playback dB→Linear RT-Store Overwrite

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Kritischer Audio-Bug: Gain-Automation machte Sound extrem laut statt leise

### Das Problem

Die aufgezeichnete Gain-Automation wurde korrekt gespeichert (CC/127 → normalized 0-1).
Beim Playback wurde sie auch korrekt denormalisiert (-60 bis +24 dB).

**ABER**: In `AutomationManager.tick()` liefen zwei RT-Store-Writes nacheinander:

```
1. param.set_automation_value(-18 dB)
   → Signal: parameter_changed
     → Gain-Widget._on_automation_changed(-18 dB)
       → _apply_rt(-18 dB)
         → 10^(-18/20) = 0.126 LINEAR
           → rt.set_param("afx:...:gain", 0.126) ✅ RICHTIG!

2. _mirror_to_rt_store("afx:...:gain", -18.0)  
   → rt.set_param("afx:...:gain", -18.0) ❌ ÜBERSCHREIBT!
```

Schritt 2 überschrieb den korrekten linearen Wert (0.126) mit dem rohen dB-Wert (-18.0).
Der Audio-Thread interpretierte -18.0 als linearen Gain-Multiplikator → **EXTREM LAUT**.

### Die Lösung

```python
# tick() — nur Mirror wenn KEIN Widget-Listener existiert:
if not param._listeners:
    self._mirror_to_rt_store(pid, actual)
```

Wenn ein Widget aktiv ist (z.B. Gain-Slider), hat der Parameter Listeners.
Das Widget übernimmt die korrekte Konvertierung (dB→linear, etc.) über die Signal-Kette.
`_mirror_to_rt_store` wird nur noch für "verwaiste" Parameter ohne aktive Widgets aufgerufen.

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/automatable_parameter.py` | `tick()` + `clear_automation_values()`: Guard `if not param._listeners` |

## Risikobewertung

- **2 Zeilen geändert**: Minimal-invasiv
- **Bestehende Widget-Pfade unverändert**: Signal-Kette funktioniert wie vorher
- **Nur _mirror_to_rt_store übersprungen**: Verwaiste Params werden weiterhin gesynced
