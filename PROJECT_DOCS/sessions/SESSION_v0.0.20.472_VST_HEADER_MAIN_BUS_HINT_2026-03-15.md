# Session v0.0.20.472 — VST Header Main-Bus Hint

**Datum:** 2026-03-15
**Entwickler:** OpenAI GPT-5.4 Thinking
**Ausgangsversion:** 0.0.20.471
**Zielversion:** 0.0.20.472

## Übernommener Task

- Sichtbare Main-Bus-Zeile (`1→1`, `1→2`, `2→2`) im externen VST-Header ergänzen, möglichst klein und ohne DSP-/Routing-Risiko.

## Umsetzung

1. `Vst3AudioFxWidget` um `_lbl_bus_hint` ergänzt.
2. Runtime-Lookup vereinheitlicht: Widget liest die bereits laufende `Vst3Fx`- oder `Vst3InstrumentEngine`-Instanz.
3. `Vst3Fx` und `Vst3InstrumentEngine` um `get_main_bus_layout()` ergänzt, damit das Widget die Information ohne zusätzliche Plugin-Instanz anzeigen kann.
4. Anzeige wird beim Param-Load/Refresh aktualisiert und bleibt rein UI-seitig.

## Geänderte Dateien

- `pydaw/ui/fx_device_widgets.py`
- `pydaw/audio/vst3_host.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/sessions/SESSION_v0.0.20.472_VST_HEADER_MAIN_BUS_HINT_2026-03-15.md`
- `VERSION`
- `CHANGELOG_v0.0.20.472_VST_HEADER_MAIN_BUS_HINT.md`

## Validierung

```bash
python -m py_compile pydaw/audio/vst3_host.py pydaw/ui/fx_device_widgets.py
```

## Risikoabschätzung

- Niedrig: nur zusätzliche UI-/Diagnoseanzeige.
- Kein Eingriff in Audio-Callback, DSP oder Projektformat.
