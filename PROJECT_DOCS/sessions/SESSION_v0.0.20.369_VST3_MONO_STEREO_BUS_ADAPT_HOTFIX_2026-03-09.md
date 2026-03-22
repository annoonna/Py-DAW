# v0.0.20.369 — VST3 Mono/Stereo Bus-Adapt Hotfix

**Datum**: 2026-03-09
**Bearbeiter**: GPT-5
**Aufgabe**: Sicheren Bridge-Fix für Mono-VSTs im weiterhin stereo-internen Audio-FX-Pfad ergänzen
**Ausgangsversion**: 0.0.20.368
**Ergebnisversion**: 0.0.20.369

## Ziel

Externe VST3/VST2-FX wurden seit v0.0.20.363 live gehostet, aber der Bridge-Pfad reichte immer starr ein `2 x frames`-Signal an `pedalboard` weiter.
Bei Mono-Plugins wie **LSP Autogain Mono** führte das im Playback zu wiederholten Fehlern wie:

- `Plugin 'Autogain Mono' does not support 2-channel output`
- `Main bus currently expects 1 input channels and 1 output channels`

Die Anforderung dieses Schritts war deshalb ganz bewusst:

- **kein** Umbau des internen Stereo-FX-/Mixer-Pfads
- **nur** die externe VST-Bridge robuster machen
- Mono- und gemischte Main-Bus-Layouts sicher adaptieren

## Umgesetzte Änderungen

- `pydaw/audio/vst3_host.py`
  - Kanal-Layout-Helfer für externe Plugins ergänzt
  - sichere Bridge zwischen Host-Stereo und Plugin-Main-Bus ergänzt
  - Fehlertext-Parser für `expects 1 input channels and 1 output channels` ergänzt
  - Layout wird nach erster Erkennung gecached, damit kein Log-Spam pro Audio-Block entsteht

## Sicherheitsprinzip

- Interner Host-/Track-FX-Pfad bleibt weiterhin **Stereo**
- Anpassung erfolgt nur direkt vor bzw. nach `plugin.process(...)`
- Kein Eingriff in Arranger, Automation-System, Routing, Mixer oder Projektformat

## Benutzerwirkung

- **Autogain Mono**, **Filter Mono** und ähnliche Mono-FX lassen sich jetzt im Audio-FX-Bereich benutzen, ohne dass sie sofort in Dauerfehler laufen
- Mono-Output wird wieder hörbar auf beide Host-Kanäle geschrieben
- Die Fehlermeldung wiederholt sich nicht mehr jede Callback-Runde

## Tests

- ✅ `python -m py_compile pydaw/audio/vst3_host.py`
- ✅ Smoke-Test mit Mock-Plugin für **2→1→1**-Fallback (Stereo Host → Mono Plugin → Mono zurück auf Stereo Host)
- ✅ Smoke-Test mit Mock-Plugin für **2→1→2**-Fallback

## Nächste sichere Schritte

- [ ] Optional die erkannte **Main-Bus-Anzahl** im externen VST-Header sichtbar machen
- [ ] Optional kleinen Diagnose-Hinweis ergänzen, wenn ein Plugin mehr als 2 Hauptkanäle erwartet

