# SESSION v0.0.20.327 — Bounce/Freeze-Dialoge + Freeze-Marker + AETERNA Math-Familien

Datum: 2026-03-07
Autor: GPT-5

## Ziel
Nur den kleinsten sicheren Ausbau für die neue Bounce/Freeze-Stufe und AETERNA lokal umsetzen, ohne Playback/Core anzufassen.

## Umgesetzt
- Neue UI-Dialoge für Bounce/Freeze-Optionen ergänzt (`pydaw/ui/bounce_freeze_dialog.py`).
- Arranger-Kontextmenü für **Bounce in Place** auf Dialog-Variante erweitert.
- Track-Kontextmenü für **Spur einfrieren / bouncen** und **Gruppe einfrieren / bouncen** auf Dialog-Variante erweitert.
- Sichtbare Freeze-Marker in der **TrackList** ergänzt: **❄ PROXY** und **❄ SRC** inklusive Tooltip.
- Zwei lokale Laufzeitfehler in `ProjectService` behoben (robustere Clip-/Track-Bounce-Label-Namen).
- AETERNA lokal um zusätzliche Math-/Random-Formelideen erweitert:
  - tent lattice
  - pink bloom
  - lorenz breath
  - sample hold veil
  - harmonic lattice
  - modal drift

## Nicht angefasst
- Playback-Core
- Mixer-Engine
- Transport
- Clip Launcher
- globale Audio-Architektur

## Prüfung
- `python3 -m py_compile pydaw/ui/bounce_freeze_dialog.py pydaw/ui/track_list.py pydaw/ui/arranger_canvas.py pydaw/services/project_service.py pydaw/plugins/aeterna/aeterna_widget.py pydaw/version.py`

## Ergebnis
Sicherer Workflow-Komfort für Bounce/Freeze ist jetzt sichtbarer und kontrollierbarer, und AETERNA hat lokal deutlich breitere mathematische Startideen bekommen — ohne Core-Umbau.
