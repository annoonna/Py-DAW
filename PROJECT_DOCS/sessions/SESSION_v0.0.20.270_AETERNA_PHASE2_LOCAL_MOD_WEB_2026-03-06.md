# SESSION v0.0.20.270 — AETERNA Phase 2 Local Mod Web (2026-03-06)

## Ziel
AETERNA sicher weiter ausbauen, aber ausschließlich lokal im Instrument. Keine Änderungen an Arranger, Clip-Launcher, Audio-Editor, Mixer oder globalem Audio-Core.

## Umgesetzt
- Lokales Modulations-Fundament in `pydaw/plugins/aeterna/aeterna_engine.py` ergänzt:
  - 2 Mod-Slots (`Web A`, `Web B`)
  - Quellen: `off`, `lfo1`, `lfo2`, `mseg`, `chaos`
  - Ziele: `morph`, `chaos`, `drift`, `motion`, `tone`, `space`, `cathedral`
- Neue sichere Mod-Quellen:
  - `LFO1`: weicher Sinus
  - `LFO2`: langsamer Triangle
  - `MSEG`: mehrstufige Loop-Hüllkurve pro Voice
  - `Chaos`: logistischer Drift als bipolare Modulationsquelle
- Modulationswerte werden ausschließlich innerhalb von AETERNA pro Voice berechnet und auf die lokale Klangformung angewendet.
- UI in `pydaw/plugins/aeterna/aeterna_widget.py` erweitert:
  - neuer Bereich **THE WEB (LOCAL SAFE)**
  - Knobs für `LFO1 Rate`, `LFO2 Rate`, `MSEG Rate`, `Web A`, `Web B`
  - Source/Target-Combos für beide Mod-Slots
  - lokale Hilfe für die Modulationsquellen
- Persistenz erweitert:
  - Combo-Auswahl und neue Knobs werden im Track-`instrument_state['aeterna']` gespeichert und wiederhergestellt.
- Zusätzlicher Preset-Startpunkt: `Web Chapel`.

## Safety
- Keine Änderungen außerhalb des AETERNA-Pakets plus Dokumentation/Versionierung.
- Projektformat bleibt kompatibel: neue Keys sind rein optional.
- Kein Eingriff in globale Automation-Architektur; nur zusätzliche AETERNA-Knobs wurden lokal angebunden.

## Checks
- `python -m py_compile pydaw/plugins/aeterna/aeterna_engine.py pydaw/plugins/aeterna/aeterna_widget.py`
- Engine-Smoke-Test per direktem Modulimport:
  - Presets `Kathedrale`, `Schloss`, `Terrain`, `Chaos`, `Web Chapel` rendern Audio
  - State Export/Import mit neuen String-Parametern getestet
  - Formel-Fallback bei ungültiger Formel weiterhin stabil

## Nächster safe Schritt
- kleine visuelle Modulations-Preview / MSEG-Zeichenanzeige im AETERNA-Widget
- optionale weitere AETERNA-only Automation-Expose für Source/Target-Presets
