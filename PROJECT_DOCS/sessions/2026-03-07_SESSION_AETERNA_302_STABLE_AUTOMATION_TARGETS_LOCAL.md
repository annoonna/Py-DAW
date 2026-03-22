# SESSION — 2026-03-07 — AETERNA stable automation targets exposed locally

## Ausgangslage
Nach der lokalen Automation-Zielkarte sollte jetzt der nächste sichere Schritt folgen: nur solche AETERNA-Parameter sichtbar und benutzbar machen, die bereits stabil als Automation-Ziele taugen, ohne neue riskante Engine-/Core-Wege zu öffnen.

## Umsetzung
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` lokal erweitert.
- Bestehende stabile AETERNA-Knobs wurden **nicht neu erfunden**, sondern als bereits sichere Ziele explizit gruppiert dargestellt.
- Neue lokale Karte **"Jetzt lokal freigegeben"** ergänzt.
- Gruppen:
  - Direkt auf Knobs
  - Modulations-Rates
  - Depth/Amounts
- Bestehende Knob-Bindings an den AutomationManager bleiben erhalten.
- Tooltips der AETERNA-Knobs weisen jetzt zusätzlich auf **Rechtsklick → Show Automation in Arranger** hin.

## Sicherheit
- Kein Eingriff in globales Automation-Backend.
- Kein neuer Audio- oder Playback-Code.
- Keine Änderung an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Projektformat.
- Nur lokales AETERNA-Widget angepasst.

## Ergebnis
AETERNA zeigt jetzt klar, **welche stabilen Ziele bereits jetzt automatisiert werden können**:
- Morph, Tone, Gain, Release, Space, Motion, Cathedral, Drift
- LFO1 Rate, LFO2 Rate, MSEG Rate
- Chaos, Web A, Web B

## Nächste sichere Schritte
- Formel-Infozeile (geladen / geändert / angewendet)
- eventuell noch kompaktere Automation-ready-Kurzansicht direkt an den Reglern
- kuratierte Formel-Preset-Karte erweitern
