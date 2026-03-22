# Session v0.0.20.253 — Safe MPE-Mode (Note Expressions)

## Ziel
Micropitch/MPE kontrolliert ins Playback bringen, ohne bestehende Audio-/Playback-Pfade kaputt zu machen.

## Entscheidung (safe)
Kein harter Umbau auf vollständiges, kontinuierliches MPE im gesamten Engine-Stack.
Stattdessen ein **eigener MPE-Mode (safe v1)**:
- opt-in per Toggle im Piano-Roll (`MPE`)
- nutzt **note-start Micropitch** als sicheren Startwert
- bestehendes Normal-Playback bleibt unverändert, solange MPE aus ist

## Implementiert
- `audio/note_expr_mpe_mode` als Setting ergänzt
- Piano-Roll: neuer `MPE` Toggle neben Note-Expressions
- `effective_micropitch()` für Playback-Evaluation ergänzt
- Realtime-Playback-Events tragen optional `pitch_offset_semitones`
- SamplerRegistry + interne Instrumente (Sampler / Bachs Orgel / Drum Machine) akzeptieren optionalen Pitch-Offset
- SF2/FluidSynth-Render: Pitchwheel + per-note Channel Routing im MPE-Mode

## Bewusst NICHT in diesem Schritt
- keine volle kontinuierliche Micropitch-Kurvenfahrt während laufender Note für Realtime-Engines
- kein generisches MPE-Voice-Management für alle externen Plugin-Hosts
- kein riskanter Umbau an bestehendem Standard-Playback

## Verifikation
- geänderte Python-Dateien via `python -m py_compile` geprüft
- keine Änderungen an LV2/LADSPA Hosting, Arranger-Mixing, Automation-Core oder Device-DnD
