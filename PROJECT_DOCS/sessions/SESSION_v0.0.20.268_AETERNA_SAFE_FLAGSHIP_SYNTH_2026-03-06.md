# Session v0.0.20.268 — AETERNA Safe Flagship Synth

**Datum:** 2026-03-06  
**Bearbeiter:** GPT-5.4 Thinking

## Ziel
User-Wunsch: Neues internes Instrument **AETERNA – The Morphogenetic Engine** bauen und direkt neben die vorhandenen Instrumente im Browser setzen, ohne bestehende DAW-Funktionalität zu beschädigen.

## Safe-Umfang dieser Session
- Neuer Instrument-Eintrag im Browser/Registry-System
- Neue selbständige Engine `pydaw/plugins/aeterna/aeterna_engine.py`
- Neues Widget `pydaw/plugins/aeterna/aeterna_widget.py`
- SamplerRegistry + Pull-Source Integration wie bei bestehenden Instrumenten
- Track-lokale Persistenz + Basis-Automation für die wichtigsten Makro-Parameter

## Umsetzung
1. **Neue Plugin-Familie `pydaw/plugins/aeterna/`**
   - `AeternaEngine`: vektorisiertes NumPy-Instrument mit vier sicheren Modi
     - `formula`
     - `spectral`
     - `terrain`
     - `chaos`
   - Formel-Auswertung über AST-Whitelist (nur erlaubte Funktionen/Operatoren)
   - Fallback auf sichere Sinus-Ausgabe bei ungültiger Formel

2. **Neue UI `AeternaWidget`**
   - Presets: Kathedrale, Schloss, Terrain, Chaos, Orgel der Zukunft
   - Formel-Eingabe + Random-Math-Button
   - Makro-Knobs: Morph, Chaos, Drift, Tone, Release, Gain, Space, Motion, Cathedral
   - Statusanzeige `FORMULA OK` / `FORMULA FALLBACK`

3. **DAW-Integration**
   - Instrument-Browser zeigt jetzt `AETERNA` als viertes internes Instrument
   - `set_track_context()` registriert AETERNA sauber im SamplerRegistry-System
   - eigener Pull-Source-Name für Mixer/Fader/VU-Kompatibilität
   - Persistenz in `track.instrument_state['aeterna']`
   - Automation-Parameter IDs im Stil `trk:<id>:aeterna:<param>`

## Warum das safe ist
- Keine Änderungen an bestehender Audio-Core-Architektur
- Kein Umbau an Sampler, Drum Machine oder Bachs Orgel
- Keine neuen Threads, keine Prozess-Spawns, keine Fremdlibs
- Formel-System absichtlich sandboxed + mit Fallback abgesichert
- Große/risikoreiche Wunsch-Features bewusst **noch nicht** in den Core gedrückt

## Verifikation
- `python3 -m py_compile` auf neue Plugin-Dateien + Registry erfolgreich
- `AeternaEngine` separat per Importlib geladen und Audio-Blocks erzeugt
- Formel-Fallback bei ungültigen Ausdrücken geprüft

## Nächste sinnvolle Schritte
- Optional: Arbeitsmappe/README um Mini-Hilfe für AETERNA ergänzen
- Optional: zusätzliche Automationsziele für Preset/Mode/Formula-Morph
- Optional: Phase 2 mit MSEG/Web/Granular/Physical-Modelling, aber separat und vorsichtig
