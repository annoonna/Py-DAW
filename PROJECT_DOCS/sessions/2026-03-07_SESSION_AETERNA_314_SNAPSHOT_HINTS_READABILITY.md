# Session — v0.0.20.314 — AETERNA Snapshot-Hinweise lesbarer

Datum: 2026-03-07

## Ziel
Die lokale Snapshot-Karte in AETERNA kompakter und musikalischer lesbar machen, ohne Eingriff in DAW-Core oder globale Zustände.

## Umgesetzt
- Snapshot-Zeilen zeigen jetzt pro Slot kompakt:
  - Preset
  - musikalische Stimmung (sakral/klar/getragen/belebt/offen)
  - Formelhinweis
  - Web-Vorlage mit Intensität
- leere Slots werden lesbarer als bereit für Klang/Formel/Web markiert
- nur `pydaw/plugins/aeterna/aeterna_widget.py` angepasst

## Sicherheit
- kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core
- keine Änderung an Audio-Engine oder globalem Automationssystem
