# CHANGELOG v0.0.20.466 — CLAP MIDI-Learn / Kontextmenü-Parität

## Fix
- CLAP-Parameterzeilen unterstützen jetzt denselben Rechtsklick-Workflow wie LV2/LADSPA/DSSI/VST:
  - Show Automation in Arranger
  - MIDI Learn
  - Reset to Default
- AutomationManager-Registrierung für CLAP erfolgt pro gebauter Lazy-UI-Zeile.

## Performance
- Kein zusätzlicher Vollscan
- Keine neue Vollmaterialisierung großer CLAP-Plugins
- Keine Änderungen an DSP/Audio-Thread

## Datei
- `pydaw/ui/fx_device_widgets.py`
