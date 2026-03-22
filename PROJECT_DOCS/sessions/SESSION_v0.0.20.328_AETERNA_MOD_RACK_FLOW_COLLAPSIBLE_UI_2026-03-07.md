# Session v0.0.20.328 — AETERNA Mod Rack / Flow + Collapsible UI

## Summary
AETERNA wurde lokal um ein sicheres Mod-Rack mit Drag-&-Drop-Zuweisung erweitert. Zusätzlich wurden die großen Instrument-Bereiche einklappbar gemacht, damit das Widget kompakter und lesbarer bleibt.

## Änderungen
1. **Lokales MOD RACK / FLOW**
   - neue Drag-Quellen: LFO1, LFO2, MSEG, Chaos, ENV, VEL
   - Drop auf stabile Ziele weist die Quelle einem der realen Slots Web A/B zu
   - Hilfen: Auto/Slot A/Slot B, Swap A/B, Clear A, Clear B
2. **Collapsible Sections**
   - alle großen AETERNA-Sektionen nutzen jetzt Dreiecks-Header zum Ein-/Ausklappen
   - Composer / Mod-Preview / Phase 3A SAFE standardmäßig kompakter
3. **Kleine echte Engine-Erweiterung**
   - AETERNA Engine unterstützt jetzt ENV und VEL als Mod-Quellen in den zwei vorhandenen Mod-Slots
4. **Signalfluss / Formelhilfe**
   - neue Signalfluss-Karte im Widget
   - zusätzliche nicht nur phasengetriebene Formel-Snippets

## Geänderte Dateien
- pydaw/plugins/aeterna/aeterna_widget.py
- pydaw/plugins/aeterna/aeterna_engine.py
- VERSION
- pydaw/version.py
- PROJECT_DOCS/progress/TODO.md
- PROJECT_DOCS/progress/DONE.md
- PROJECT_DOCS/sessions/LATEST.md

## Sicherheit / Grenzen
- kein Eingriff in Playback-Core, Arranger-Core, Mixer-Engine, Transport
- keine globale neue Synth-Architektur
- neue Bedienung bleibt auf stabile lokale AETERNA-Ziele begrenzt

## Tests
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py pydaw/plugins/aeterna/aeterna_engine.py pydaw/version.py`

## Version
0.0.20.328
