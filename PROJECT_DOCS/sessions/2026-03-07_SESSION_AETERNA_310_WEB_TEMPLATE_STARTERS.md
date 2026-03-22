# SESSION — v0.0.20.310 — AETERNA Web-A/Web-B-Startvorlagen

Datum: 2026-03-07

## Ziel
Nur lokal in AETERNA kleine sichere Web-A/Web-B-Startvorlagen ergänzen, damit der Nutzer schnell musikalische Grundbewegungen laden kann, ohne den DAW-Core anzufassen.

## Umgesetzt
- Neue lokale Vorlagen: **Langsam**, **Lebendig**, **Organisch**, **Sakral**.
- Vorlagen setzen nur sichere lokale Werte für:
  - Web A/B Quelle
  - Web A/B Ziel
  - Web A/B Amount
  - LFO1 Rate
  - LFO2 Rate
  - MSEG Rate
- Neue kompakte Karte im Widget zeigt aktive Vorlage und aktuelle Web-A/B-Kombination.
- Bei manueller Abweichung wird die Ansicht lokal als **Eigen** markiert.

## Sicherheit
- Keine Änderung an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.
- Keine neuen globalen Automationsziele.
- Keine Engine-/DSP-Umbauten außerhalb von AETERNA.
