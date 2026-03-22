# Session Log — 2026-03-07 — AETERNA 301 Automation-Zielkarte

## Ziel
Nur lokal in AETERNA eine kompakte, klar benannte Übersicht später sinnvoller Automationsziele ergänzen, ohne Core-Eingriff.

## Umsetzung
- Phase-3-Bereich um eine lokale **Automation-Zielkarte** erweitert.
- Ziele lesbar gruppiert: **Klang**, **Raum/Bewegung**, **Modulation**, **Web**.
- Sicherheits-Hinweis ergänzt: für spätere Automation sind stabile **Knobs**, **Rates** und **Amounts** gedacht, nicht flüchtige UI-Zustände oder rohe interne Phasenwerte.
- Bestehende Gruppenlabels nutzen jetzt lesbarere Namen statt roher Parameter-Keys.

## Betroffene Dateien
- `pydaw/plugins/aeterna/aeterna_widget.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Risiko
Sehr gering. Nur AETERNA-Widget/UI geändert, keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.
