# CHANGELOG v0.0.20.364 — VST3 Browser Multi-Plugin Bundle Fix

**Session:** GPT-5 — 2026-03-09
**Basierend auf:** v0.0.20.363

## Problem

Einige VST3-Bundles wurden im Browser nur als Datei dargestellt, obwohl sie intern viele einzelne Plugins enthalten.
Bei `lsp-plugins.vst3` verlangte `pedalboard` deshalb später einen zusätzlichen `plugin_name`, wodurch Parameter-Discovery und Live-Hosting scheiterten.

## Lösung

- Multi-Plugin-Bundles werden jetzt bei verfügbarem `pedalboard` in einzelne Browser-Einträge aufgelöst
- Die exakte Auswahl wird via `__ext_plugin_name` vom Browser bis zum Host durchgereicht
- `describe_controls()` und `Vst3Fx` laden dadurch das korrekte Sub-Plugin statt nur den Bundle-Pfad
- `pedalboard` ist jetzt fest in `install.py` und `requirements.txt` verankert

## Geänderte Dateien

- `pydaw/audio/vst3_host.py`
- `pydaw/services/plugin_scanner.py`
- `pydaw/ui/plugins_browser.py`
- `pydaw/audio/fx_chain.py`
- `pydaw/ui/fx_device_widgets.py`
- `install.py`
- `requirements.txt`

## Sicherheit

- Kein Eingriff in Arranger, Transport, Routing oder DSP-Architektur
- Alte einfache Pfad-Referenzen bleiben kompatibel
- Ohne `pedalboard` bleibt das Verhalten safe/no-crash
