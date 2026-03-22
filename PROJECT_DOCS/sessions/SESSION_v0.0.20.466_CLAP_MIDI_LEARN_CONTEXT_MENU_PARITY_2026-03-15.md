# Session v0.0.20.466 — CLAP MIDI-Learn / Kontextmenü-Parität

**Datum:** 2026-03-15
**Entwickler:** OpenAI GPT-5.4 Thinking

## Ziel
CLAP-Parameter im Device-Panel an die bestehende Rechtsklick-/Automation-/MIDI-Learn-Logik der anderen externen Plugin-Typen angleichen, ohne die Lazy-UI wieder schwerer zu machen.

## Umsetzung
- `ClapAudioFxWidget` um `_automation_params` ergänzt
- `_param_key(name)` eingeführt
- In `_build_rows()` nun für jede gebaute CLAP-Zeile:
  - `_install_automation_menu()` auf Label/Slider/Spinbox
  - `_register_automatable_param()` beim AutomationManager

## Sicherheits-/Performance-Notiz
Die Änderung ist bewusst lokal gehalten:
- keine Änderungen am Audio-Thread
- keine Änderungen am CLAP-DSP-Host
- keine Vollmaterialisierung aller Parameter
- Registrierung nur für sichtbare bzw. lazy nachgeladene Zeilen

## Geänderte Datei
- `pydaw/ui/fx_device_widgets.py`
