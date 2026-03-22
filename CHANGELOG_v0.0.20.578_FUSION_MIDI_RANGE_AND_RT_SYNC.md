# Changelog v0.0.20.578 — Fusion MIDI/Range/Realtime-Safety Hotfix

## Fixes

- `CompactKnob` unterstuetzt jetzt echte Wertebereiche (`setRange/minimum/maximum`) statt still immer 0..100 zu bleiben.
- Fusion-Widget nutzt diese Bereiche jetzt korrekt fuer Pitch, Pan, Mode, Voices, Damping usw.
- Dynamische Fusion-Extra-Knobs werden nach OSC/FLT/ENV-Wechsel wieder sauber an Automation und MIDI Learn gebunden.
- Alte MIDI-CC-Listener dynamischer Fusion-Knobs werden beim Rebuild entfernt.
- Fusion-Engine mutiert aktive Voices nicht mehr direkt aus dem GUI/MIDI-Thread; Parameter werden am sicheren Pull-Rand synchronisiert.

## Wirkung

- Weniger Hangs/Abstuerze bei Fusion waehrend laufendem Audio
- MIDI-CC auf Fusion-Parametern arbeitet sauberer und mit korrekten Zielbereichen
- Fusion ist damit deutlich naeher an der Verdrahtung/Stabilitaet der anderen Instrumente
