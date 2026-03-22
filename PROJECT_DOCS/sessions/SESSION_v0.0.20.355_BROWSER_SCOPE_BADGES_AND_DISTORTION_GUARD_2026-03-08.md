# Session v0.0.20.355 — Browser Scope-Badges + Distortion Automation Guard

Datum: 2026-03-08
Bearbeitung: GPT-5

## Aufgabe
- Kleine **Scope-Badges direkt im Browser/Add-Flow** ergänzen, damit vor dem Hinzufügen klar bleibt, dass Browser-Add weiter nur auf die **aktive Spur** zielt.
- Den gemeldeten Qt-Fehler im **DistortionFxWidget** defensiv absichern, ohne Audio-Core, Mixer oder Routing anzufassen.

## Umsetzung
- `pydaw/ui/device_panel.py` erhielt `browser_add_scope(...)`, das kurze Badge-Texte + Tooltips für den aktuellen Add-Zielkontext liefert.
- `pydaw/ui/main_window.py` reicht diese Scope-Info jetzt an den Browser weiter.
- `pydaw/ui/device_browser.py` aktualisiert Scope-Badges jetzt beim Spurwechsel und Tabwechsel.
- `pydaw/ui/instrument_browser.py`, `pydaw/ui/effects_browser.py` und `pydaw/ui/device_quicklist_tab.py` zeigen jetzt kleine Scope-Badges direkt bei den Add-Buttons an.
- `pydaw/ui/fx_device_widgets.py` bekam einen defensiven Guard für `DistortionFxWidget._on_automation_changed(...)`, inklusive Disconnect beim Destroy, damit keine Qt-Wrapper nach dem Löschen mehr benutzt werden.

## Sicherheit
- Kein Routing-, DSP-, Playback- oder Mixer-Umbau.
- Keine Änderung am eigentlichen Zielverhalten von normalem Browser-Add.
- Nur UI-Klarheit + defensiver Qt-Lifetime-Guard.

## Prüfung
- `python3 -m py_compile pydaw/ui/device_panel.py pydaw/ui/device_browser.py pydaw/ui/instrument_browser.py pydaw/ui/effects_browser.py pydaw/ui/device_quicklist_tab.py pydaw/ui/main_window.py pydaw/ui/fx_device_widgets.py`

## Ergebnis
- Vor dem Hinzufügen ist jetzt sichtbarer, dass Browser-Add / Doppelklick / Drag&Drop weiter auf die **aktive Spur** gehen.
- Die Verwechslungsgefahr zwischen **aktiver Spur** und **ganzer Gruppe** wurde im Browser weiter reduziert.
- Der gemeldete Distortion-Automation-Fehler mit gelöschten QSlider-Objekten wird defensiv abgefangen.
