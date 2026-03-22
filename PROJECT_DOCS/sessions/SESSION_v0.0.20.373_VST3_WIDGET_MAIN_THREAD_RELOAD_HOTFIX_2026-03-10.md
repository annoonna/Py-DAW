# v0.0.20.373 — VST3 Widget Main-Thread Reload Hotfix

**Datum**: 2026-03-10
**Bearbeiter**: GPT-5
**Ausgangsversion**: 0.0.20.372
**Ergebnisversion**: 0.0.20.373

## Änderung

- `QCheckBox`-Import in `pydaw/ui/fx_device_widgets.py` ergänzt
- bestehender VST3-Async-Fallback bleibt erhalten
- wenn der Worker mit `must be reloaded on the main thread` scheitert, macht das Widget jetzt automatisch einen einmaligen sicheren Main-Thread-Retry

## Warum so klein?

Ziel war bewusst ein minimaler UI-Hotfix ohne Audio-/Routing-/Host-Core-Umbau. Damit bleibt der responsive Insert-Pfad erhalten und nur der bekannte Sonderfall wird gezielt abgefangen.

## Tests

- `python -m py_compile pydaw/ui/fx_device_widgets.py pydaw/audio/vst3_host.py`
