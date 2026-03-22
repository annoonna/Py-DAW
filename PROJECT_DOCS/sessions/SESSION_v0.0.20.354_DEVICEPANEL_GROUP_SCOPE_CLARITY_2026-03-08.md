# Session v0.0.20.354 — DevicePanel Gruppen-/Spur-Zieltrennung klarer

Datum: 2026-03-08
Bearbeitung: GPT-5

## Aufgabe
- Die Zieltrennung zwischen **aktiver Spur** und **Gruppe** im DevicePanel klarer und unmissverständlicher machen.
- Keine Änderung an Routing, Audio-Core, Mixer oder Playback vornehmen.

## Umsetzung
- `pydaw/ui/device_panel.py` erhielt eine zusätzliche **Aktive Spur-Ziel**-Hinweisbox.
- Diese Box zeigt jetzt klar an, dass die **sichtbare Device-Kette unten nur der aktiven Spur** gehört.
- Für Gruppenspuren wird zusätzlich erklärt, dass **NOTE→Gruppe** und **AUDIO→Gruppe** die einzigen sicheren Gruppen-Aktionen in dieser Ansicht sind.
- Die bestehende Gruppenleiste wurde sprachlich auf **Gruppen-Aktionen** umgestellt und nennt ausdrücklich, dass noch **kein gemeinsamer Bus** vorhanden ist.
- Die beiden Gruppenbuttons wurden sprechender benannt: **NOTE→Gruppe** / **AUDIO→Gruppe**.

## Sicherheit
- Kein Eingriff in Routing, Mixer, DSP, Playback oder Audio-Core.
- Kein Umbau am tatsächlichen FX-Zielverhalten.
- Nur DevicePanel-UI, Labels und Hinweistexte wurden erweitert.

## Prüfung
- `python3 -m py_compile pydaw/ui/device_panel.py pydaw/version.py`

## Ergebnis
- Es ist jetzt klarer erkennbar, welche Devices zur **aktiven Spur** gehören.
- Gruppen-Aktionen sind sichtbarer von Einzelspur-Aktionen getrennt.
- Die bisherige Verwechslungsgefahr zwischen **Kick-FX** und **Gruppen-FX** wurde UI-seitig deutlich reduziert.
