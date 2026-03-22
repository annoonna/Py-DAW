# Session v0.0.20.260 — FX Automation RT Mirror Fix

## Kontext
User-Report: Bei Pro Drum Machine Slot-FX und auch im normalen Device-Panel bewegen sich automatisierte FX-Parameter hörbar nicht zuverlässig, obwohl man beim manuellen Anfassen der Slider sofort einen Klangunterschied hört.
Oberste Direktive: **nichts kaputt machen**.

## Analyse
- FX-Parameter verwenden im bestehenden System oft direkt ihren RT-Key als `parameter_id` (`afx:...`, `afxchain:...`).
- Die Audio-Wirkung hing bisher implizit daran, dass ein verbundenes Widget den Qt-Signalpfad bedient und `rt_params.set_param(...)` ausführt.
- Ist das Widget nicht aktiv/rechtzeitig verbunden oder wird der Signalpfad nicht getroffen, bleibt Audio trocken, obwohl die Lane im Manager korrekt läuft.

## Umsetzung (SAFE)
1. `AutomationManager(rt_params=...)` eingeführt.
2. Neuer interner Helfer `_mirror_to_rt_store(parameter_id, value)`.
3. In `tick()` werden Lane-Werte weiter normal an Parameter/Widgets verteilt **und zusätzlich** direkt in den RT-Store gespiegelt — aber nur für:
   - `afx:...`
   - `afxchain:...`
4. In `clear_automation_values()` wird der effektive Basiswert ebenfalls in den RT-Store zurückgespiegelt.
5. Service-Container übergibt den bestehenden `rt_params` beim Erzeugen des Managers.

## Ergebnis
- FX-Automation hat jetzt einen robusten Audio-Pfad auch ohne UI-Abhängigkeit.
- Sichtbare Widget-Synchronisation bleibt unverändert über `parameter_changed` erhalten.
- Keine Core-DSP-/Hosting-Änderung, daher safe Scope.

## Geänderte Dateien
- `pydaw/audio/automatable_parameter.py`
- `pydaw/services/container.py`
- `VERSION`
- `pydaw/version.py`
