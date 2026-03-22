# Session v0.0.20.336 — AETERNA Layer-Toggles + Mod-Badges/Mini-Meter

Datum: 2026-03-07

## Ziel
- Nur lokal in AETERNA arbeiten.
- Irreführende Layer-Vorschau im Synth Panel bereinigen.
- Familienkarten um klarere Aktiv-/Modulationshinweise ergänzen.

## Umsetzung
- Die bisherigen Checkboxen für **Unison / Sub / Noise** im unteren Layer-/Preview-Bereich wurden in echte Schnellschalter verdrahtet.
- Schalter setzen lokal die realen Layer-Level **Unison Mix / Sub Level / Noise Level** auf 0 bzw. auf den zuletzt sinnvollen Wert zurück.
- Familienkarten zeigen jetzt pro Familie kompakte **Mini-Meter** und **aktive Mod-Ziel-Badges** für Web A/B.
- Alles bleibt auf `pydaw/plugins/aeterna/aeterna_widget.py` begrenzt.

## Sicherheit
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.
- Keine Änderung an der globalen Projektstruktur.

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py pydaw/plugins/aeterna/aeterna_engine.py pydaw/version.py`
