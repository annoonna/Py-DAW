# SESSION v0.0.20.334 — AETERNA Pitch/Shape/Pulse Width + Drive/Feedback

Datum: 2026-03-07
Modul: AETERNA (lokal)
Version: 0.0.20.334

## Ziel
Den nächsten größeren, aber weiterhin sicheren AETERNA-Familienblock in einem Rutsch umsetzen: **Pitch / Shape / Pulse Width** sowie **Drive / Feedback**, ohne Arranger, Playback-Core, Mixer, Transport oder andere Instrumente anzufassen.

## Umgesetzt
- AETERNA-Engine lokal um neue kontinuierliche Parameter erweitert:
  - `pitch`
  - `shape`
  - `pulse_width`
  - `drive`
  - `feedback`
- Neue Parameter in den lokalen AETERNA-State, Init-Patch, Automation-Gruppen und Mod-Targets aufgenommen.
- DSP lokal erweitert:
  - Pitch als musikalische globale Tonhöhenverschiebung im AETERNA-Kern
  - Shape als zusätzliche Wellenform-Morphing-Ebene
  - Pulse Width als Pulsbreitensteuerung des Rechteckanteils
  - Drive als zusätzliche Sättigungsstufe
  - Feedback als kontrollierte interne Rückkopplung pro Stimme
- AETERNA-Widget lokal erweitert:
  - neue Familienkarten im **AETERNA SYNTH PANEL**
  - neue Knobs für Pitch / Shape / PW / Drive / Feedback
  - neue Zusammenfassungen/Statuskarten
  - Automation-Schnellzugriff um die neuen stabilen Ziele erweitert
- Randomize und lokale Snapshot-/Save-Load-Pfade mitgezogen.

## Sicherheit / Nicht angefasst
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.
- Keine Änderungen an anderen Instrumenten.
- Keine globale Audioarchitektur geändert.

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py`
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py`
- `python3 -m py_compile pydaw/version.py`
- zusätzlicher lokaler Engine-Smoketest ohne GUI über direkten Datei-Import:
  - `note_on()`
  - `pull()`
  - `note_off()`

## Ergebnis
AETERNA hat jetzt die nächsten zwei größeren Klangfamilien in einem kontrollierten Schritt bekommen. Der Ausbau bleibt lokal, testbar und kompatibel zur bestehenden DAW-Struktur.
