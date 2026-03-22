# SESSION v0.0.20.272 — AETERNA Web Overlay Preview

**Datum:** 2026-03-06  
**Autor:** GPT-5.4 Thinking

## Ziel
Nächster sicherer AETERNA-Schritt: Web A / Web B als Overlay in der großen lokalen Modulations-Preview darstellen, ohne Arranger, Mixer, Audio-Editor, Clip-Launcher oder globalen Audio-Core zu verändern.

## Umgesetzt
- `aeterna_engine.py`
  - neue Helper-Methode `get_web_overlay_data(slot, points)` ergänzt
  - liefert Slot-Konfiguration (`source`, `target`, `amount`) plus lokal berechnete Overlay-Kurve
- `aeterna_widget.py`
  - große Preview zeigt optional **Web A** und **Web B** als gestrichelte Overlay-Kurven
  - neue Toggle-Checkboxen: `Overlay Web A`, `Overlay Web B`
  - Legende im Panel zeigt `SOURCE → TARGET (AMOUNT%)`
  - Overlay-Sichtbarkeit wird im Instrument-State gespeichert und wiederhergestellt

## Sicherheitsrahmen
- Nur AETERNA-Dateien geändert
- Keine Änderungen an Arranger / Clip Launcher / Audio Editor / Mixer / globalem Playback
- Keine Änderung am Projektformat außerhalb des lokalen AETERNA-Instrument-States

## Prüfung
- `py_compile` der geänderten AETERNA-Dateien
- Smoke-Test für `get_web_overlay_data(1|2)` inkl. Amount/Target/Source-Rückgabe
- ZIP neu gebaut als `Py_DAW_v0_0_20_272_TEAM_READY.zip`
