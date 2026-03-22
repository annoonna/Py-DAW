# Session v0.0.20.577 — Fusion Synthesizer Performance Fix

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Task:** Fusion Performance-Probleme + GUI-Freeze beheben
**Priorität:** CRITICAL — App hing ("main.py antwortet nicht")

---

## Problem-Analyse

Fusion Synthesizer war unspielbar:
1. **GUI-Freeze** ("main.py antwortet nicht") — Screenshot zeigt den Dialog
2. **Sound-Stottern** — Audio-Callback konnte Buffer nicht in Echtzeit füllen
3. **CPU-Überlastung** bei Knob-Drehen — GUI und Audio blockierten sich gegenseitig

### Root Causes

1. **Lock-Contention**: `pull()` hielt `threading.Lock()` für die GESAMTE Audio-Berechnung.
   GUI-Thread (`set_param()` bei Knob-Drehen) musste warten → GUI friert ein.

2. **Per-Sample Python-Loops**: Alle DSP-Komponenten hatten `for i in range(frames):`
   mit `self._attribute` Zugriffen pro Sample (Python dict-Lookup = ~100ns × 48000/sec = 5ms/sec pro Attribut)

3. **Keine Vectorisierung**: Statt numpy-Arrays wurden Samples einzeln berechnet.

---

## Lösung (13 Dateien geändert)

### Phase A — Lock-Free Pull (GUI-Freeze Fix)

**`fusion_engine.py`**:
- `pull()` snaphottet aktive Voices + Parameter unter Lock (< 1µs)
- Audio-Rendering ohne Lock → GUI kann jederzeit Parameter ändern
- Voice-Rendering mit try/except pro Voice (keine Crash-Propagation)

### Phase B — Vectorized DSP

**Sine/Triangle Oszillatoren** (`basic_waves.py`):
- Phase-Akkumulation: `np.arange(frames) * dt` statt per-sample Loop
- Plain Sine (kein Skew/Fold): komplett vectorized mit `np.sin()` → **~10x schneller**
- Triangle: vectorized mit `np.where()` + `np.tanh()` für Skew

**Scrawl/Wavetable Oszillatoren** (`scrawl.py`, `wavetable.py`):
- Table-Lookup vectorized: Index-Arrays mit `np.intp`, Frac mit `np.floor()`
- Wavetable Unison: Inner-Loop pro Voice vectorized statt per-sample `_read_table()`

**Swarm Oszillator** (`swarm.py`):
- Sine-Modus: komplett vectorized (N×frames numpy ops)
- Saw-Modus: Local variable caching + inline PolyBLEP

**Noise Generator** (`fusion_engine.py`):
- White Noise: `np.random.randn(frames)` statt per-sample `np.random.randn()`
- Pink/Brown: Pre-generate white buffer, local variable caching

### Phase C — Local Variable Caching (alle DSP-Loops)

**SVF Filter** (`svf.py`):
- Mode-spezifische Inner-Loops (LP/HP/BP separate Schleifen)
- Drive-Branch vor Loop gehoistet (keine per-sample Prüfung)
- Alle Koeffizienten als Locals → ~12 weniger dict-Lookups/Sample

**Ladder Filter** (`ladder.py`):
- `math.tanh` als Local `_tanh` gecached
- Drive-Branch vor Loop gehoistet

**Comb Filter** (`ladder.py`):
- Pre-computed `(1.0 - delay_frac)`, Local caching

**ADSR Envelope** (`adsr.py`):
- Fast-Path: OFF → `np.zeros()`, SUSTAIN → `np.full()`
- Inline Stage-Transitions (kein `_setup_stage()` Methodenaufruf)
- Alle Instance-Vars als Locals

**AR/AD/Pluck Envelopes** (`extras.py`):
- Gleiche Optimierungen: Fast-Path OFF/SUSTAIN, pre-computed Rates, Locals

**Phase1/Union/Bite Oszillatoren**:
- Inline PolyBLEP (keine Funktionsaufruf-Overhead)
- Alle Parameter als Locals gecached
- Mode-spezifische Loops (kein Branching pro Sample)

**Voice.render** (`voice.py`):
- `np.multiply(filtered, aeg_buf, out=filtered)` statt Allocation
- `feg_buf.sum() / n` statt `np.mean()` Overhead

---

## Test-Ergebnis (Container-Umgebung, langsamer als native)

| Komponente          | Zeit (100×1024 Frames) | Real-Time Faktor |
|---------------------|----------------------:|----------------:|
| Sine                | 205ms                 | 10.4x RT        |
| Triangle            | 129ms                 | 16.5x RT        |
| Pulse               | 152ms                 | 14.1x RT        |
| Saw                 | 145ms                 | 14.8x RT        |
| Scrawl              | 132ms                 | 16.2x RT        |
| Wavetable           | 136ms                 | 15.7x RT        |
| Phase-1             | 180ms                 | 11.9x RT        |
| Bite                | 155ms                 | 13.7x RT        |
| Union               | 247ms                 | 8.6x RT         |
| Swarm (8 voices)    | 360ms                 | 5.9x RT         |
| SVF Filter          | 143ms                 | 14.9x RT        |
| Ladder Filter       | 114ms                 | 18.8x RT        |
| **8-Voice Polyphony** | **1006ms**          | **2.1x RT**     |

Auf Apple M4 native: erwartete ~5-8x dieser Werte → **8-Voice Polyphonie ~10-17x RT**.

---

## Geänderte Dateien (13)

1. `pydaw/plugins/fusion/fusion_engine.py` — Lock-free pull, vectorized noise/HP
2. `pydaw/plugins/fusion/voice.py` — Optimized render
3. `pydaw/plugins/fusion/oscillators/basic_waves.py` — Vectorized Sine/Tri/Pulse/Saw
4. `pydaw/plugins/fusion/oscillators/scrawl.py` — Vectorized table lookup
5. `pydaw/plugins/fusion/oscillators/wavetable.py` — Vectorized single+unison render
6. `pydaw/plugins/fusion/oscillators/union.py` — Local cache + inline PolyBLEP
7. `pydaw/plugins/fusion/oscillators/phase1.py` — Local cache + inline distortion
8. `pydaw/plugins/fusion/oscillators/swarm.py` — Vectorized sine path
9. `pydaw/plugins/fusion/oscillators/bite.py` — Mode-split loops + local cache
10. `pydaw/plugins/fusion/filters/svf.py` — Mode-split loops + local cache
11. `pydaw/plugins/fusion/filters/ladder.py` — Local cache + drive hoisting
12. `pydaw/plugins/fusion/envelopes/adsr.py` — Fast-path + inline transitions
13. `pydaw/plugins/fusion/envelopes/extras.py` — Fast-path + pre-computed rates

## Nichts kaputt gemacht ✅

- Alle 10 Oszillatoren produzieren Sound ✓
- Alle 3 Filter funktionieren ✓
- Alle 4 Envelope-Typen funktionieren ✓
- 8-Voice Polyphonie stabil ✓
- Widget-Interface unverändert (keine UI-Änderungen)
- SamplerRegistry-Kompatibilität beibehalten ✓
- State Persistence unverändert ✓
