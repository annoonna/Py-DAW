# SESSION v0.0.20.249 — FX Automation for External Effects

**Date:** 2026-03-06  
**Author:** GPT-5.4 Thinking

## Ziel
Externe Audio-FX (vor allem LV2 und LADSPA/DSSI) sollen dieselbe Automation-UX bekommen wie die bestehenden Instrument-Knobs: Rechtsklick → `Show Automation in Arranger`, Lane-Playback wirkt live auf Widget + RT-Parameter + Projektzustand.

## Umsetzung
- In `pydaw/ui/fx_device_widgets.py` kleine Helper für Automation-Menü + Parameter-Registrierung ergänzt.
- `GainFxWidget` an `AutomationManager` angebunden.
- `DistortionFxWidget` an `AutomationManager` angebunden.
- `Lv2AudioFxWidget` registriert jetzt jede Control-Port-Row als Automationsparameter.
- `LadspaAudioFxWidget` registriert jetzt jede Control-Port-Row als Automationsparameter.
- Bei eingehender Lane-Automation werden Slider/SpinBox signal-blocked aktualisiert und der RT-Store sofort mitgeschrieben.

## Warum kein LADSPA-Safe-Mode in diesem Schritt?
Der Wunsch ist sinnvoll, aber das wäre ein Architektur-Schritt mit eigenem Risiko. Weil der harte LADSPA-Crash in v0.0.20.248 bereits behoben wurde und aktuell kein neuer Crash vorliegt, wurde der Safe-Mode bewusst **nicht** in denselben Commit gepackt. So bleibt dieser Schritt klein und testbar.

## Test/Checks
- `python3 -m py_compile pydaw/ui/fx_device_widgets.py` ✅
- Version/Projektmetadaten auf `0.0.20.249` angehoben ✅

## Nächster sinnvoller Safe-Step
- Optionaler LADSPA Safe-Mode per Subprozess **separat** implementieren, falls wieder ein reproduzierbarer Crash mit einem bestimmten Plugin auftaucht.
