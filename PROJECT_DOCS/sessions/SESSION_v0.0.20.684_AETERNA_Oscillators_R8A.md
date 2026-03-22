# Session Log — v0.0.20.684

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R8A — AETERNA Oszillatoren
**Aufgabe:** PolyBLEP Oszillatoren, FM, Sub-Osc, Unison Engine

## Was wurde erledigt

### Neues Modul: `instruments/aeterna/oscillator.rs` (~480 Zeilen)

**Waveforms (alle PolyBLEP anti-aliased wo nötig):**
- `gen_sine(phase)` — Sine
- `gen_saw_polyblep(phase, dt)` — Anti-aliased Saw (PolyBLEP)
- `gen_square_polyblep(phase, dt, duty)` — Anti-aliased Square mit variabler Pulsbreite
- `gen_triangle(phase)` — Triangle
- `white_noise(seed)` — LCG White Noise
- `pink_noise(seed, state)` — Paul Kellet 3-Tap Pink Noise

**Wave Morphing:**
- `gen_morphed(phase, dt, shape)` — Continuous blend: Sine(0) ↔ Triangle(0.33) ↔ Saw(0.67) ↔ Square(1.0)
- `process_morphed()` — Unison-fähige Version

**FM Synthesis:**
- Shared FM modulator across unison voices
- `fm_amount` (0–1 = ±π rad modulation), `fm_ratio` (Freq-Ratio zum Carrier)

**Sub-Oscillator:**
- Sine, 1 oder 2 Oktaven runter, eigene Phase
- Additiv gemischt mit `sub_level` (0–1)

**Unison Engine (1–16 Voices):**
- `set_unison(voices, detune_cents, spread)` — Pre-computed Offsets
- Per-Voice: Detune-Ratio (Cents→Ratio), Stereo Pan (equal-power)
- Level-Normalisierung: `1/√N` für konstante Lautstärke
- Phase Randomization bei `reset(randomize_phase=true)`

**19 Unit-Tests:**
- Sine zero/peak, Saw range, Square duty, Triangle range/symmetry
- White/Pink noise range/nonzero, Morph endpoints
- Oscillator process (sine, morphed), Unison stereo/mono
- FM modulation effect, Sub-oscillator effect
- Waveform parsing, PolyBLEP correction

### Module-Registrierung
- `instruments/aeterna/mod.rs` — Re-Exports aller public API
- `instruments/mod.rs` — `pub mod aeterna` registriert

## Geänderte Dateien
- pydaw_engine/src/instruments/aeterna/oscillator.rs (**NEU**, ~480 Z.)
- pydaw_engine/src/instruments/aeterna/mod.rs (**NEU**)
- pydaw_engine/src/instruments/mod.rs (aeterna registriert)
- VERSION, pydaw/version.py (683 → 684)

## Nächste Schritte
- Phase R8B — AETERNA Voice + Filter (Biquad, AEG/FEG ADSR, Voice Pool, Glide)
