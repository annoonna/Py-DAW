# Changelog v0.0.20.372 — VST3 Widget Embedded-State Hint

## Neu

- Das generische externe **VST2/VST3-Audio-FX-Widget** zeigt jetzt einen kleinen sichtbaren **Preset/State-Hinweis** direkt im Widget an.
- Wenn im Projekt bereits ein eingebetteter `__ext_state_b64`-Blob vorhanden ist, zeigt das Widget **„Preset/State: eingebettet“** inklusive kompakter Größenanzeige.
- Wenn noch kein Blob vorhanden ist, wird defensiv angezeigt, dass der eingebettete State erst nach dem Projektspeichern erzeugt wird.

## Technisch

- Umsetzung bleibt vollständig in `pydaw/ui/fx_device_widgets.py`.
- Kein Eingriff in Audio-Thread, Routing, Mixer oder den VST-Host-Lifecycle.
