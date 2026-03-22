# SESSION — v0.0.20.311 — AETERNA Web-Template Intensity Safe

Datum: 2026-03-07
Bearbeiter: GPT-5

## Ziel
Kleiner sicherer lokaler AETERNA-Schritt: Web-A/Web-B-Startvorlagen um eine Intensitätsstufe ergänzen, ohne globale Risiken.

## Umsetzung
- Neue lokale Intensitätsauswahl im Widget: **Sanft / Mittel / Präsent**
- Intensität skaliert nur lokale AETERNA-Werte für:
  - `mod1_amount`
  - `mod2_amount`
  - `lfo1_rate`
  - `lfo2_rate`
  - `mseg_rate`
- Neue Hilfsfunktionen zur intensitätsabhängigen Konfiguration der bestehenden Web-Vorlagen.
- Web-Vorlagen-Karte zeigt jetzt zusätzlich die aktive Intensität.
- Neue UI-State-Persistenz für `web_template_intensity`, damit die Einstellung beim Projekt-Speichern/Laden erhalten bleibt.

## Risikoabschätzung
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` angepasst.
- Keine Änderungen an Playback-Core, Arranger, Clip Launcher, Audio Editor, Mixer oder Transport.
- Keine neuen globalen Automationsziele oder Engine-Wege eingeführt.

## Ergebnis
AETERNA hat jetzt lokal besser dosierbare Web-Startvorlagen, die sich sicher speichern und wieder laden lassen.
