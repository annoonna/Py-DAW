# SESSION — v0.0.20.308 — AETERNA Formula/Preset Link

Datum: 2026-03-07

## Ziel
Sichtbar machen, welche Formelidee zum aktuell gewählten AETERNA-Preset passt, ohne den DAW-Core oder die Engine-Architektur anzufassen.

## Umsetzung
- Im Formelbereich wurde eine lokale **Preset→Formel-Hinweiszeile** ergänzt.
- Die Empfehlung wird aus Preset-Name plus lokalen Metadaten (Kategorie, Charakter, Tags, Notiz) abgeleitet.
- Ein Button lädt die vorgeschlagene Formelidee nur ins Formelfeld; Klangänderung bleibt weiterhin erst bei **„Formel anwenden“** aktiv.
- Statuslogik ergänzt: passende Idee bereit / im Feld / angewendet / eigene Formel.

## Risiko
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` geändert.
- Keine Änderungen an Playback, Arranger, Mixer, Transport oder globalem Automationssystem.
