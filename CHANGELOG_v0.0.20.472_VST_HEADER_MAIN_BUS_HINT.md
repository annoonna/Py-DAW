# CHANGELOG v0.0.20.472 — VST Header Main-Bus Hint

## Neu

- Externe VST2/VST3-Widgets zeigen jetzt direkt im Header die erkannte Main-Bus-Zeile (`Main-Bus: 1→1`, `1→2`, `2→2`).
- Funktioniert sowohl für klassische FX (`Vst3Fx`) als auch für VST-Instrumente (`Vst3InstrumentEngine`).

## Technisch

- `pydaw/ui/fx_device_widgets.py`: neue kompakte Bus-Hinweiszeile im Widget.
- `pydaw/audio/vst3_host.py`: kleine `get_main_bus_layout()`-Accessor ergänzt.

## Risiko

- Rein UI-seitiger Schritt, keine Änderung an DSP oder Routing.
