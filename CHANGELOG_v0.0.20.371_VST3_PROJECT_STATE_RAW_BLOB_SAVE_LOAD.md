# CHANGELOG v0.0.20.371 — VST3 Project-State Raw-Blob Save/Load

## Neu
- Projektdateien betten für externe **VST2/VST3-Devices** jetzt zusätzlich einen Base64-kodierten `raw_state`-Blob in `params["__ext_state_b64"]` ein.
- Der Blob wird aus den aktuell gespeicherten Projektparametern auf einer frischen Plugin-Instanz erzeugt.

## Fix
- `Vst3Fx` restauriert den gespeicherten Blob beim Laden vor der normalen Parameter-Initialisierung, sodass projektseitige Preset-/State-Daten nicht verloren gehen.

## Sicherheit
- Kein direkter Zugriff auf die laufende DSP-Instanz für den Save-Pfad.
- Kein Eingriff in Audio-Routing, Mixer, Transport oder Callback-Logik.
