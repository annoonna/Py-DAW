# SESSION — v0.0.20.333 — AETERNA Unison / Sub / Noise

Datum: 2026-03-07
Autor: GPT-5

## Ziel
Den nächsten größeren, aber weiterhin sicheren AETERNA-Familienblock umsetzen: **Unison / Sub / Noise**, ausschließlich lokal in AETERNA.

## Umsetzung
- `pydaw/plugins/aeterna/aeterna_engine.py` erweitert um neue lokale Parameter:
  - `unison_mix`
  - `unison_detune`
  - `unison_voices`
  - `sub_level`
  - `sub_octave`
  - `noise_level`
  - `noise_color`
- Neue stabile Mod-/Automation-Ziele ergänzt:
  - `unison_mix`
  - `unison_detune`
  - `sub_level`
  - `noise_level`
  - `noise_color`
- DSP lokal erweitert:
  - leichter Unison-Layer mit 2/4/6 Stimmen
  - Sub-Layer auf -1 / -2 Oktaven
  - farbbares Noise-Layer (dunkel ↔ hell)
- `pydaw/plugins/aeterna/aeterna_widget.py` erweitert um:
  - neue Synth-Panel-Familie **Unison / Sub**
  - neue Synth-Panel-Familie **Noise / Color**
  - neue Comboboxen **Unison Voices** und **Sub Oktave**
  - neue Knobs **Uni Mix / Uni Det / Sub / Noise / Color**
- Save/Load, Snapshot und Randomize lokal mitgezogen.

## Sicherheitsrahmen
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.
- `Unison Voices` und `Sub Oktave` bleiben bewusst lokale Combobox-Parameter statt Timeline-Automation.

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py pydaw/version.py`
- zusätzlicher lokaler Engine-Smoketest ohne GUI:
  - `note_on()`
  - `pull()`
  - `note_off()`

## Nächster sinnvoller sicherer Schritt
Als nächster größerer, aber noch lokaler Familien-Block: **Pitch / Shape / Pulse Width** oder **Drive / Feedback**.
