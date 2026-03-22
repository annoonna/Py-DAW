# Session — v0.0.20.298 — AETERNA Formula Startcard / Onboarding

## Ziel
Den nächsten sicheren lokalen Schritt in AETERNA umsetzen: eine kleine Formel-Startkarte / Onboarding-Hilfe direkt im Widget, ohne DAW-Core-Eingriff.

## Analyse
- Vorheriger sicherer Stand: v0.0.20.297 mit mehrzeiligem Formel-Editor und lokalen Preset-Metadaten.
- Der passende offene TODO-Block war die Formel-Startkarte direkt im AETERNA-Widget.
- Umsetzung sollte nur UI-lokal im Formelbereich stattfinden.

## Umsetzung
- Im AETERNA-Formelbereich eine lokale Startkarte ergänzt.
- Vier sichere Beispiel-Presets ergänzt:
  - Warm Start
  - Sakral
  - Chaos
  - Glitch
- Klick auf ein Beispiel schreibt die Formel lokal in das mehrzeilige Feld.
- Klang-Änderung erfolgt weiterhin erst über den vorhandenen Button "Formel anwenden".
- Keine Änderungen an Engine-Core, globalem Automationssystem, Arranger oder Playback.

## Geänderte Datei
- `pydaw/plugins/aeterna/aeterna_widget.py`

## Sicherheit
- Nur AETERNA-Widget geändert.
- Keine Änderungen an globalem DAW-Core.
- Datei mit `python3 -m py_compile` geprüft.

## Nächste sichere Schritte
- Formel-Makro-Slots noch klarer gruppieren.
- Optionale lokale Tags/Favorit für Preset-Metadaten.
- Kleine Infozeile, ob ein Startbeispiel nur vorgeladen oder schon angewendet wurde.
