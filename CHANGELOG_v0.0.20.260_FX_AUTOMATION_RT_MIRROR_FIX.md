# v0.0.20.260 — FX Automation RT Mirror Fix

## Problem
FX-Automation war in manchen Situationen sichtbar im Arranger, wirkte aber hörbar nicht zuverlässig auf Audio-FX.
Das betraf besonders Parameter, deren `parameter_id` direkt ein `RTParamStore`-Key ist (`afx:...`, `afxchain:...`).
Bisher verließ sich der Audiopfad darauf, dass ein passendes Widget aktiv ist und den Qt-Signalpfad bis zum `rt_params.set_param(...)` bedient.

## Fix (SAFE)
- `AutomationManager` kann jetzt optional den `RTParamStore` direkt kennen.
- Während `tick()` werden aktive Automationwerte zusätzlich direkt in den RT-Store gespiegelt, **aber nur** für bekannte FX-RT-Keys:
  - `afx:...`
  - `afxchain:...`
- `clear_automation_values()` spiegelt beim Stoppen wieder den effektiven Basiswert zurück.
- Container/Services verdrahten den bestehenden `rt_params` sicher in den `AutomationManager`.

## Warum das safe ist
- Keine Änderung an DSP-Algorithmen
- Keine Änderung an Plugin-ABI / Hosting
- Keine Änderung an Projektformat oder Lane-Daten
- Nur zusätzlicher, defensiver Write-Pfad für bereits etablierte RT-Keys

## Betroffene Dateien
- `pydaw/audio/automatable_parameter.py`
- `pydaw/services/container.py`
- `VERSION`
- `pydaw/version.py`
