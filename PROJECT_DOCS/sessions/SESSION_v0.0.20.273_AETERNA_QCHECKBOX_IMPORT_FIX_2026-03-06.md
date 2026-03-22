# SESSION v0.0.20.273 — AETERNA QCheckBox Import Fix

**Datum:** 2026-03-06  
**Autor:** GPT-5.4 Thinking

## Ziel
Den gemeldeten AETERNA-Device-Fehler `name 'QCheckBox' is not defined` sicher beheben, ohne andere DAW-Bereiche anzufassen.

## Umgesetzt
- `pydaw/plugins/aeterna/aeterna_widget.py`
  - fehlenden PyQt6-Widget-Import `QCheckBox` ergänzt

## Sicherheitsrahmen
- Nur eine lokale Importzeile in AETERNA geändert
- Keine Änderungen an Audio-Core, Arranger, Clip Launcher, Audio Editor, Mixer oder anderen Instrumenten

## Prüfung
- `py_compile` für `pydaw/plugins/aeterna/aeterna_widget.py`
- gezielte Suche nach der Fehlerstelle bestätigt
- ZIP neu gebaut als `Py_DAW_v0_0_20_273_TEAM_READY.zip`
