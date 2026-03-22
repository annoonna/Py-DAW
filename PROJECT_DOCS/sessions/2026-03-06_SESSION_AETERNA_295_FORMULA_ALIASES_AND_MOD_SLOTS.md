# Session 2026-03-06 — AETERNA v0.0.20.295

## Aufgabe
Lokale sichere AETERNA-Formel-Aliase ergänzen und die aktuell verwendeten Formelquellen im Widget sichtbar machen.

## Umgesetzt
- `$VEL`, `$NOTE`, `$T_REM`, `$T_REMAINING`, `$GLITCH` werden vor der sicheren AST-Auswertung intern normalisiert.
- `rand(t)` und `random()` stehen als lokale deterministische Formelquelle zur Verfügung.
- Formelbereich zeigt jetzt **Aktive Formelquellen** und **Alias-Ansicht**.

## Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_engine.py` und `pydaw/plugins/aeterna/aeterna_widget.py` geändert.
- Kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalen Playback-Core.
