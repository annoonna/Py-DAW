# Session v0.0.20.468 — CLAP Editor Deferred-Mapping + GUI-Visibility/Resize-Handshake

**Datum:** 2026-03-15  
**Entwickler:** OpenAI GPT-5.4 Thinking  
**Version:** 0.0.20.467 → 0.0.20.468

## Ziel

Den CLAP-Editor für problematische Plugins wie Surge XT weiter absichern, ohne Audio-Thread, Routing oder DSP anzufassen.

## Umgesetzte Änderungen

- `ClapAudioFxWidget._toggle_editor()` zeigt das Editorfenster jetzt zuerst an und startet den eigentlichen `create_gui()`-Schritt deferred über `_open_editor_deferred()`.
- Der native CLAP-Container nutzt jetzt zusätzlich `WA_DontCreateNativeAncestors`.
- Der Editor-Pump läuft in einer kurzen Prime-Phase schnell und danach nur noch gedrosselt.
- GUI-Wünsche aus dem Host (`request_resize`, `request_show`, `request_hide`) werden über neue Helper im Host und im Widget ausgewertet.
- `_ClapPlugin` bietet jetzt `take_requested_gui_visibility()` und `set_gui_size()` für einen saubereren GUI-Handshake.

## Warum das sicher ist

- Keine Änderung an CLAP-DSP oder Audio-Callback
- Keine Änderung am MIDI-Routing
- Keine Änderung an Device-Persistenz oder Projektformat
- Fokus nur auf nativen Editor-Lifecycle

## Betroffene Dateien

- `pydaw/ui/fx_device_widgets.py`
- `pydaw/audio/clap_host.py`

## Validierung

- `python -m py_compile pydaw/audio/clap_host.py pydaw/ui/fx_device_widgets.py`

## Offen

- Lokaler Test gegen Surge XT unter deinem X11/XWayland-Setup
- Falls das Fenster weiterhin leer bleibt: optionaler Fallback für Plugins, die Child-Embedding nicht sauber unterstützen
