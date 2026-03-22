# CHANGELOG v0.0.20.577 — Fusion Synthesizer Performance Fix

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6

## CRITICAL FIX: GUI-Freeze + Audio-Stottern

### Problem
- App hängt bei "main.py antwortet nicht" wenn Fusion-Knobs gedreht werden
- Sound stottert und bricht ab bei Polyphonie
- CPU-Last steigt auf >24% für einen einzelnen Synthesizer

### Root Cause
1. `threading.Lock()` in `pull()` blockiert GUI-Thread während gesamter Audio-Berechnung
2. Alle DSP in reinen Python `for i in range(frames)` Schleifen mit `self._attribute` Zugriffen
3. Kein numpy-Vectorisierung für Oszillatoren, Filter, Envelopes

### Fix (13 Dateien)

**fusion_engine.py**: Lock-free Pull — Snapshot unter Lock, Render ohne Lock
**basic_waves.py**: Vectorized Sine/Triangle mit numpy
**scrawl.py**: Vectorized Table-Lookup
**wavetable.py**: Vectorized single+unison Render
**svf.py**: Mode-split Inner-Loops, Local caching
**ladder.py**: tanh als Local, Drive-Branch hoisting
**adsr.py**: Fast-path OFF/SUSTAIN, inline Stage-Transitions
**extras.py**: Pre-computed Rates, Local caching
**voice.py**: In-place multiply, optimized FEG mean
**union.py, phase1.py, swarm.py, bite.py**: Local cache + inline PolyBLEP
