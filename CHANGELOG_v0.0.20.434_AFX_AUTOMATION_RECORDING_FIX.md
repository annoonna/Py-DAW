# CHANGELOG v0.0.20.434 — Fix: CC→Automation für ALLE Plugin-Typen

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Direktive**: Nichts kaputt machen!

---

## Bug-Fix: Automation-Recording funktionierte NUR für instrument-Knobs, nicht für FX-Parameter

### Das Problem

In v0.0.20.433 wurde `_write_cc_automation()` eingeführt, aber die Parameter-ID-Parsing
war zu restriktiv:

```python
# ALT (v433) — NUR trk: akzeptiert:
parts = param_id.split(":", 2)
if len(parts) < 3 or parts[0] != "trk":
    return  # ← VERWIRFT alle afx: und afxchain: IDs!
```

Alle FX-Parameter verwenden aber **andere Prefixe**:

| Plugin-Typ | Parameter-ID Format | Ergebnis v433 |
|-----------|---------------------|---------------|
| Gain | `afx:{tid}:{did}:gain` | ❌ Verworfen |
| LV2 | `afx:{tid}:{did}:lv2:{sym}` | ❌ Verworfen |
| LADSPA | `afx:{tid}:{did}:ladspa:{port}` | ❌ Verworfen |
| DSSI | `afx:{tid}:{did}:dssi:{param}` | ❌ Verworfen |
| VST2 | `afx:{tid}:{did}:vst2:{param}` | ❌ Verworfen |
| VST3 | `afx:{tid}:{did}:vst3:{param}` | ❌ Verworfen |
| Chain Wet/Mix | `afxchain:{tid}:wet_gain` | ❌ Verworfen |
| Bach Orgel | `trk:{tid}:bach_orgel:cut` | ✅ Funktioniert |

### Die Lösung (v434)

```python
# NEU — Akzeptiert alle bekannten Prefixe:
parts = param_id.split(":", 2)
if len(parts) < 2:
    return
prefix = parts[0]
if prefix not in ("trk", "afx", "afxchain"):
    return
track_id = parts[1]  # Track-ID ist IMMER an Position [1]
```

### Bonus: Generic CC Re-Registration

Problem: Wenn `project_updated` feuert, zerstört DevicePanel die alten Widgets und
erstellt neue. Die neuen Slider/Knobs haben keine `_pydaw_param_id` mehr und CC-Mappings
gehen verloren.

Lösung: `_install_automation_menu()` prüft jetzt bei Widget-Erstellung ob ein
`_persistent_cc_map` Eintrag existiert und re-registriert automatisch.

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/automatable_parameter.py` | `_write_cc_automation()`: afx/afxchain/trk Prefix-Support |
| `pydaw/ui/fx_device_widgets.py` | `_install_automation_menu()`: Generic CC Re-Registration aus `_persistent_cc_map` |

## Risikobewertung

- **Minimaler Eingriff**: 7 Zeilen in automatable_parameter.py geändert, 15 Zeilen in fx_device_widgets.py hinzugefügt
- **Kein bestehender Code verändert**: Nur die Prefix-Prüfung erweitert
- **Kein Audio-Thread-Eingriff**
