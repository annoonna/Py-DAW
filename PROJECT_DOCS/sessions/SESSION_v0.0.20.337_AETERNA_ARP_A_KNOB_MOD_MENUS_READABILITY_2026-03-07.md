# SESSION — v0.0.20.337 — AETERNA Arp A + Per-Knob Mod-Menüs + Readability

Datum: 2026-03-07

## Ziel
Einen größeren, aber weiterhin sicheren AETERNA-Block umsetzen: lokaler Arpeggiator, echte per-Knob Modulator-Menüs und bessere Lesbarkeit — ohne DAW-Core-Umbau.

## Umgesetzt
- AETERNA **Arp A (LOCAL SAFE)** als Clip-Arpeggiator ergänzt
- Pattern, Rate, Straight/Dotted/Triplets, Root/Chord, Shuffle und 16 Step-Editoren ergänzt
- pro Step: Transpose / Skip / Velocity / Gate 0–400%
- MIDI-Erzeugung: neuer Clip oder aktiven Clip überschreiben
- Rechtsklick-Menü auf allen AETERNA-Knobs erweitert: Show Automation in Arranger + Add Modulator
- lokale per-Knob Mod-Profile ergänzt
- AETERNA-Readability verbessert (größere Fonts / Controls / Signalfluss-Lesbarkeit)

## Nicht angefasst
- Arranger
- Clip Launcher
- Audio Editor
- Mixer
- Transport
- Playback-Core
- andere Instrumente

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py pydaw/plugins/aeterna/aeterna_engine.py pydaw/version.py`

## Hinweise
- Arp A ist bewusst **Clip-basiert** und lokal sicher.
- Per-Knob-Mod-Profile merken den Zielzustand je Knob, während die reale aktive Modulation weiterhin über die vorhandenen Web-Slots A/B läuft.
