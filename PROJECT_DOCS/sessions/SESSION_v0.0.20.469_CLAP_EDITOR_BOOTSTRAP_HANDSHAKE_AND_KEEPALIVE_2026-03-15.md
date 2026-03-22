# Session Log — v0.0.20.469

**Datum:** 2026-03-15
**Entwickler:** OpenAI GPT-5.4 Thinking
**Dauer:** ~20 min
**Version:** 0.0.20.468 → 0.0.20.469

## Task

**CLAP native GUI weiter isoliert härten** — speziell den Surge-XT-Fall, bei dem `create_gui()` erfolgreich meldet, das Editorfenster aber lokal weiter leer bleibt. Ziel: nur den Editor-Bootstrap anfassen, kein Risiko für DSP/Audio.

## Problem-Analyse

1. Der bisherige Host begann das CLAP-Main-Thread-Pumping erst *nachdem* `create_gui()` vollständig zurückkam.
2. Einige CLAP-GUIs bootstrapen ihren nativen Child jedoch asynchron und fordern bereits während `create()` / `set_parent()` / `show()` weitere Main-Thread-Arbeit an.
3. Wenn diese Callback-Phase zu spät bedient wird, kann der Container formal korrekt geöffnet sein, visuell aber leer bleiben.
4. Zusätzlich stoppte der Widget-Timer nach der Prime-Phase komplett, sodass spätere `request_callback()`-Bursts bei offenem Editor verloren gehen konnten.

## Fix

1. **Stufenweiser Main-Thread-Handshake im Host**
   - `_ClapPlugin.create_gui()` pumpt jetzt direkt nach `create()`, direkt nach `set_parent()` und direkt nach `show()` jeweils kurze `on_main_thread()`-Bursts.
   - Das ist bewusst nur GUI-/Lifecycle-seitig und greift nicht in die Audioverarbeitung ein.

2. **Sehr leichter Keepalive solange der Editor offen ist**
   - Nach der schnellen Prime-Phase läuft `_editor_pump` jetzt mit 120 ms weiter, statt vollständig zu stoppen.
   - Dadurch bleiben späte GUI-Callbacks bedienbar, ohne die normale Spur-/Arranger-Performance zu belasten, solange der Editor geschlossen ist.

## Betroffene Dateien

- `pydaw/audio/clap_host.py`
- `pydaw/ui/fx_device_widgets.py`

## Validierung

- `python -m py_compile pydaw/audio/clap_host.py pydaw/ui/fx_device_widgets.py`

## Hinweis

- Der Patch ist weiterhin bewusst klein und editor-seitig isoliert.
- Eine echte Laufzeitprüfung gegen dein lokales Surge-XT/XWayland-Setup ist weiterhin erforderlich.
