# v0.0.20.372 — VST3 Widget Embedded-State Hint

**Datum**: 2026-03-10
**Bearbeiter**: GPT-5
**Aufgabe**: Kleinen sichtbaren Hinweis im VST2/VST3-Widget ergänzen, ob bereits ein eingebetteter Projekt-State-Blob vorhanden ist
**Ausgangsversion**: 0.0.20.371
**Ergebnisversion**: 0.0.20.372

## Ziel

Nach dem projektseitigen Raw-Blob-Save/Load aus v0.0.20.371 sollte als nächster sicherer Schritt direkt im generischen VST-Widget sichtbar werden, ob für das aktuelle externe Device bereits ein eingebetteter `__ext_state_b64`-Blob vorliegt.

Wichtig dabei:

- rein **UI-seitig** bleiben
- **keinen** Eingriff in Audio-Callback, DSP, Routing oder Host-Lifecycle machen
- nur bestehenden Projekt-Device-State lesen und visualisieren

## Umgesetzte Änderungen

- `pydaw/ui/fx_device_widgets.py`
  - kleinen projektseitigen Lookup-Helfer für das aktuelle VST-Device ergänzt
  - neuen Label-Hinweis `Preset/State: ...` direkt unter der Statuszeile eingebaut
  - bei vorhandenem `__ext_state_b64`-Blob wird jetzt **„eingebettet“** inkl. kompakter Größenanzeige dargestellt
  - ohne Blob wird defensiv angezeigt, dass der Blob erst nach dem Projektspeichern erzeugt wird
  - Hinweis wird beim Widget-Aufbau sowie bei `refresh_from_project()` / `_flush_to_project()` mit aktualisiert

## Sicherheitsprinzip

- Keine Änderung am Audio-Thread
- Kein neuer Plugin-Load
- Kein Zugriff auf `raw_state` der Live-Instanz
- Nur Lesen bereits vorhandener Projekt-`params` plus lokale UI-Anzeige

## Benutzerwirkung

- Externe VST2/VST3-Devices zeigen jetzt direkt sichtbar an, ob ihr eingebetteter Projekt-State vorhanden ist
- Das macht den neuen Save/Load-Pfad aus v0.0.20.371 im Widget nachvollziehbar, ohne weitere technische Schritte zu erzwingen

## Tests

- ✅ `python -m py_compile pydaw/ui/fx_device_widgets.py pydaw/version.py`
- ✅ kleiner PyQt-Offscreen-Smoke-Test mit Mock-Projektdevice für vorhandenen und fehlenden `__ext_state_b64`
- ℹ️ kein echter Plugin-Lade-/DSP-Test nötig, da diese Änderung bewusst nur UI-seitig ist

## Nächste sichere Schritte

- [ ] Optional später einen **expliziten „Preset/State aktualisieren“-Button** im VST3-Widget ergänzen
- [ ] Optional den Hinweis noch als kleine farbige Badge im Device-Kopf verdichten, weiterhin rein UI-seitig
