# SESSION v0.0.20.276 — AETERNA lokale MSEG-Segmentformen

Datum: 2026-03-06
Autor: GPT-5.4 Thinking

## Gemacht

- AETERNA lokal um einfache MSEG-Segmentformen `linear` und `smooth` erweitert.
- Segmentform bleibt strikt im AETERNA-Widget und in der AETERNA-Engine gekapselt.
- Segmentformen werden zusammen mit den MSEG-Punkten exportiert/importiert und pro Track gespeichert.
- Große Modulations-Preview zeigt jetzt Segment-Hinweise und erlaubt die Auswahl der Segmentform über eine lokale ComboBox.
- MSEG-Preview/Modulationsquelle nutzt dieselbe Segmentform-Auswertung wie die Darstellung.

## Sicherheit

- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer oder globalem Audio-/Playback-Core.
- Nur `pydaw/plugins/aeterna/aeterna_engine.py` und `pydaw/plugins/aeterna/aeterna_widget.py` angepasst.

## Checks

- `py_compile` für beide geänderten AETERNA-Dateien erfolgreich.
- Engine-Smoke-Test für Export/Import der Segmentformen und MSEG-Preview erfolgreich.

## Nächster sicherer Schritt

- Optional: kleine Kurven-Bibliothek / Preset-Shapes nur lokal in AETERNA.
