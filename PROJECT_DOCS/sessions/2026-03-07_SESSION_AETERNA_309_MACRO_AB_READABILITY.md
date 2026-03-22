# Session Log — 2026-03-07 — AETERNA 309 Macro-A/B-Feinsteuerung lesbarer

## Ziel
Lokale Macro-A/B-Feinsteuerung in AETERNA lesbarer machen, ohne DAW-Core-Eingriff.

## Umsetzung
- Im Bereich **THE WEB (LOCAL SAFE)** eine kompakte lokale Karte ergänzt.
- Karte zeigt für **Web A** und **Web B** jeweils:
  - Quelle
  - Ziel
  - Amount
  - kurze Einordnung der Modulationsidee
- Aktualisierung hängt nur an lokalen Combo-/Knob-Änderungen in AETERNA.

## Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` angepasst.
- Keine Änderungen an Audio-Engine, Playback-Core, Arranger, Clip Launcher, Audio Editor oder Mixer.

## Ergebnis
- Makro A/B ist im Widget deutlich leichter lesbar.
- Nutzer sehen jetzt schneller, welche Source→Target→Amount-Kombination aktiv ist und wofür sie musikalisch taugt.
