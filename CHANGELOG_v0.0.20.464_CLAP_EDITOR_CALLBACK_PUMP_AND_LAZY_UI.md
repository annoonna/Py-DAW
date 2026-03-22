# Changelog v0.0.20.464 — CLAP Editor Callback Pump + Lazy Parameter UI

## Fixes
- CLAP Host-Callbacks werden jetzt pro Plugin-Instanz zugeordnet
- `request_callback()`/`on_main_thread()` wird nach Editor-Erstellung wirklich gepumpt
- CLAP-Resize-Wünsche können ins Qt-Editorfenster übernommen werden
- Große CLAP-Parameterlisten werden lazy aufgebaut statt alles sofort zu rendern
- CLAP-Widget versucht zuerst Runtime-Metadaten aus der laufenden Engine zu nutzen

## Betroffene Dateien
- `pydaw/audio/clap_host.py`
- `pydaw/ui/fx_device_widgets.py`
