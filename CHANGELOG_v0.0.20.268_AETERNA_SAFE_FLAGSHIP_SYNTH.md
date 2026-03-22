# v0.0.20.268 — AETERNA Safe Flagship Synth

- Neues internes Instrument **AETERNA** im Instrument-Browser ergänzt.
- Safe, additive Integration: eigener Pull-Source-Synth + SamplerRegistry-Anbindung, keine Core-Engine-Umbauten.
- Modi: `formula`, `spectral`, `terrain`, `chaos`.
- UI: Presets, Formula-Input, Random-Math, Morph/Chaos/Drift/Tone/Release/Gain/Space/Motion/Cathedral.
- Track-lokale Persistenz via `instrument_state['aeterna']`.
- Grundlegende Automation für die AETERNA-Knobs via bestehendem AutomationManager.

Hinweis: Das ist bewusst die **sichere Foundation** für AETERNA. Große Themen wie granulare Engine, 3D-Visualisierung, MSEG-Web oder Physical-Modelling-Kern bleiben als nächste Schritte offen, damit bestehende DAW-Funktionalität nicht gefährdet wird.
