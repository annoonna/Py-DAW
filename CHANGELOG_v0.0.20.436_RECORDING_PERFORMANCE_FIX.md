# CHANGELOG v0.0.20.436 — Performance Fix: Automation Recording Audio-Stutter

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Kritischer Performance-Bug: Sound stotterte und hing während Automation-Recording

### Root Cause: 3 teure Operationen pro CC-Message (30-120x/Sek)

| Operation | Kosten | Aufrufe/Sek | Ergebnis |
|-----------|--------|-------------|----------|
| `sort_points()` | O(n log n) | 30-120 | Wachsende Liste wird ständig re-sortiert |
| `lane_data_changed.emit()` | QPainter repaint | 30-120 | 30-120 Repaints/s auf GUI-Thread |
| Legacy dict write + sort | O(n) copy + O(n log n) sort | 30-120 | Doppelte Arbeit für Backward-Compat |

Der GUI-Thread war so beschäftigt mit Sortieren und Neuzeichnen, dass der Audio-Callback
nicht mehr rechtzeitig bedient wurde → **Audio-Stutter**.

### Die Lösung

| Fix | Vorher | Nachher |
|-----|--------|---------|
| `sort_points()` | Jeden CC | ENTFERNT (beats monoton steigend) |
| `lane_data_changed` | Jeden CC (30-120 Hz) | Throttled auf 8 Hz (dirty-set + Timer) |
| Legacy store write | Jeden CC | ENTFERNT (deferred to save) |
| Gesamt pro CC | O(n log n) + Repaint | O(1) append |

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/automatable_parameter.py` | `_write_cc_automation()` + `_flush_cc_ui()` |
| `pydaw/services/midi_mapping_service.py` | `_write_automation_point()` |

### Risikobewertung

- **sort_points() Entfernung**: Sicher, weil beat monoton steigend. Sort bei Save.
- **Throttled emit**: 8 Hz ist smooth genug für visuelles Feedback, blockiert nicht Audio.
- **Legacy store skip**: Primary store (AutomationManager) bleibt aktuell. Legacy bei Save.
