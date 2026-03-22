# Session — v0.0.20.315 — AETERNA Hörhinweise an Vorschlägen

Datum: 2026-03-07

## Ziel
Die lokalen Formel-/Preset-Empfehlungen in AETERNA um kleine musikalische Hörhinweise ergänzen, ohne Eingriff in DAW-Core oder globale Systeme.

## Umgesetzt
- nur `pydaw/plugins/aeterna/aeterna_widget.py` angepasst
- neue lokale Ableitung für kompakte Hörhinweise ergänzt, z. B.:
  - sakral
  - klar
  - getragen
  - belebt
  - kristallin
  - dunkel
- Formel-Onboarding-Buttons zeigen jetzt im Tooltip zusätzlich ein kleines Hörbild
- Preset→Formel-Hinweiszeile hat jetzt eine eigene Hörhinweis-Zeile
- Preset-Kurzliste zeigt pro sichtbarem Preset eine knappe musikalische Einordnung
- keine Änderung an Preset-/Projektstruktur nötig; Save/Load bleibt kompatibel, da die Hörhinweise rein lokal abgeleitet werden

## Sicherheit
- kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core
- keine Änderung an Audio-Engine, globalem Automationssystem oder Projektmodell
- keine neuen globalen Zustände; nur lokale UI-Ableitung im AETERNA-Widget
