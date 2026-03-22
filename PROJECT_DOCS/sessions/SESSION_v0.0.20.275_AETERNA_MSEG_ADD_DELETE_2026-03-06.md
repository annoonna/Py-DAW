# SESSION v0.0.20.275 — AETERNA MSEG Punkte hinzufügen/löschen

Datum: 2026-03-06

## Gemacht

- Große lokale AETERNA-MSEG-Preview um Doppelklick zum Hinzufügen neuer Punkte erweitert.
- Löschen selektierter Zwischenpunkte via Rechtsklick sowie Entf/Backspace ergänzt.
- Endpunkte absichtlich geschützt gelassen, damit die Kurve immer stabil von 0.0 bis 1.0 bleibt.
- Selektierten Punkt sichtbar hervorgehoben und Hinttext mit Punktindex/X/Y ergänzt.

## Sicherheit

- Nur `pydaw/plugins/aeterna/aeterna_widget.py` geändert.
- Keine Änderungen am globalen Audio-Core, Arranger, Clip Launcher, Audio Editor oder Mixer.

## Nächster sinnvoller Schritt

- Einfache Segmentformen (`linear` / `smooth`) nur lokal innerhalb von AETERNA.
