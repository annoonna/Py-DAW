# Session Log — v0.0.20.434 Fix: AFX Automation Recording

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6
**Ausgangspunkt**: v0.0.20.433

## Aufgabe

v433 Fix funktionierte nur für Bach Orgel Instrument-Knobs (trk: Prefix).
Gain, LV2, LADSPA, DSSI, VST2, VST3 — alles wurde nicht aufgezeichnet.
User-Screenshots bestätigen: ● REC aktiv, CC-Messages in Statusbar, aber Lanes leer.

## Root Cause

`_write_cc_automation()` hatte:
```python
if parts[0] != "trk":
    return
```

FX-Parameter nutzen `afx:` und `afxchain:` Prefixe → sofort verworfen.

## Fix

1. **Prefix-Prüfung erweitert**: `prefix in ("trk", "afx", "afxchain")`
2. **Generic CC Re-Registration**: `_install_automation_menu()` re-registriert Widgets aus `_persistent_cc_map`

## Geänderte Dateien

- `pydaw/audio/automatable_parameter.py` — 7 Zeilen geändert
- `pydaw/ui/fx_device_widgets.py` — 15 Zeilen hinzugefügt

## Risiko: MINIMAL
