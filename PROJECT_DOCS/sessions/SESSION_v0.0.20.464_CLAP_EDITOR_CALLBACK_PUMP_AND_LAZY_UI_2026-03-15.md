# Session v0.0.20.464 — CLAP Editor Callback Pump + Lazy Parameter UI

**Datum:** 2026-03-15
**Entwickler:** OpenAI GPT-5.4 Thinking

## Ziel
Leeres CLAP-Editorfenster (Surge XT) und träge UI bei großen CLAP-Parameterlisten beheben, ohne bestehende VST/LV2/SF2-Pfade anzufassen.

## Gemacht
- `pydaw/audio/clap_host.py`
  - Host-Callback-Routing pro `_ClapPlugin` eingeführt
  - `request_callback()` / GUI-Resize werden jetzt gemerkt statt verloren
  - `pump_main_thread()` ergänzt
- `pydaw/ui/fx_device_widgets.py`
  - CLAP-Parameter kommen bevorzugt aus Runtime-Instanz
  - Lazy-Build: erster Batch sofort, Rest on-demand
  - Suchfeld + „Mehr Parameter laden“
  - Editor pumpt CLAP-Main-Thread nach `create_gui()` und übernimmt Resize-Wünsche

## Warum sicher
- Kein Eingriff in Routing, MIDI-Dispatch oder Render-Reihenfolge
- Keine Änderung an VST2/VST3/LV2/SF2 Codepfaden
- Änderungen sind lokal auf CLAP Host + CLAP Widget begrenzt

## Validierung
- `python -m py_compile pydaw/audio/clap_host.py pydaw/ui/fx_device_widgets.py` ✅

## Hinweis für den nächsten Kollegen
Falls einzelne CLAP-GUIs weiterhin nur teilweise zeichnen, als Nächstes `clap.gui`-Resize-Hints/Scale noch feiner an Qt spiegeln — aber erst nach Test mit der jetzigen Pump-Lösung.
