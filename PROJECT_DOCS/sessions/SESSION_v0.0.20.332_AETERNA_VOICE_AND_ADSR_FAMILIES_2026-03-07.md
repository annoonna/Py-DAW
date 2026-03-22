# SESSION v0.0.20.332 — AETERNA Voice Family + AEG/FEG ADSR

Datum: 2026-03-07
Bearbeiter: GPT-5

## Ziel
Einen größeren, aber weiterhin sicheren AETERNA-Familien-Block umsetzen: **Voice** (Pan/Glide/Retrig/Stereo-Spread) plus **AEG/FEG ADSR**.

## Umsetzung
- Nur lokal in `pydaw/plugins/aeterna/aeterna_engine.py` und `pydaw/plugins/aeterna/aeterna_widget.py` gearbeitet.
- Neue Engine-Parameter ergänzt:
  - `pan`, `glide`, `stereo_spread`, `retrigger`
  - `aeg_attack`, `aeg_decay`, `aeg_sustain`, `aeg_release`
  - `feg_attack`, `feg_decay`, `feg_sustain`, `feg_release`, `feg_amount`
- AETERNA-Engine lokal erweitert:
  - sanfte Glide-/Portamento-Annäherung
  - Retrig-Schalter (Phase reset vs. Flow)
  - neue ADSR-Hüllkurvenhelfer
  - AEG für Amplitudenverlauf
  - FEG für Filterverlauf
- AETERNA-Widget lokal erweitert:
  - neue Voice- und Envelope-Sektionen im Synth Panel
  - neue Knobs + Retrig-Checkbox
  - lokale Statuskarten/Hinweise aktualisiert
  - neue kontinuierliche Parameter als Automation-ready markiert
- Zusätzlich fehlende lokale LFO-/MSEG-Helfer in der AETERNA-Engine ergänzt, damit der reine Engine-Pull-Pfad ohne GUI wieder sauber ausführbar ist.

## Sicherheit / Grenzen
- Kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalen Playback-Core.
- `Retrig` bleibt bewusst lokaler Schalter.
- `Filter Type` bleibt lokaler Combo-Parameter statt riskanter Enum-Automation.

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py pydaw/version.py`
- Reiner Engine-Smoketest ohne PyQt6 per `importlib` ausgeführt: `note_on()` / `pull()` / `note_off()` laufen mit den neuen Parametern.

## Nächste sichere Schritte
- **Unison/Sub/Noise** als nächster gebündelter AETERNA-Familienblock
- danach **Pitch/Shape/Pulse Width**
- danach **Drive/Feedback**
