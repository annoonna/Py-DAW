# SESSION v0.0.20.291 — AETERNA Phase 3a: lokale State-/Preset-/Automation-Konsolidierung

## Ziel
AETERNA strukturell sauberer machen, ohne noch mehr Feature-Komplexität in die UI zu drücken und ohne den bestehenden DAW-Core anzufassen.

## Umgesetzt
- Engine-State um Schema-Version und Engine-Snapshot erweitert.
- Kompakte `get_state_summary()`-Hilfe in der Engine ergänzt.
- Widget-Persistenz auf konsolidierte Combo-State-Spezifikationen umgestellt.
- Kompakte Phase-3a-Infofläche für State/Preset/Automation im Widget ergänzt.
- Automation-Targets werden jetzt zentral beschrieben und für Persistenz/Anzeige wiederverwendet.

## Sicherheit
- Nur AETERNA lokal geändert.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, globalem Projektmodell oder Playback-Core.

## Checks
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Engine-Smoke-Test für `export_state()`, `import_state()`, `export_preset_snapshot()`, `get_state_summary()`
