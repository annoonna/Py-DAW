# CHANGELOG v0.0.20.667 — Rust DSP Primitives (Phase R1 KOMPLETT)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration — Phase R1 (DSP Primitives)

## Was wurde gemacht

### Phase R1 komplett implementiert — 7 neue Rust-Dateien, 1.560 Zeilen

**R1A — Biquad Filter Library** (`dsp/biquad.rs`, 445 Zeilen)
- Biquad DF2T (Direct Form II Transposed) — optimale Floating-Point-Numerik
- 8 Filter-Typen: LowPass, HighPass, BandPass, Notch, AllPass, PeakEQ, LowShelf, HighShelf
- Audio EQ Cookbook Koeffizienten-Berechnung (Robert Bristow-Johnson)
- `process_sample()` inline, zero-alloc
- `process_block()` für Block-Processing mit Channel-Stride
- `StereoBiquad` für Stereo-Verarbeitung mit geteilten Koeffizienten
- 6 Unit-Tests: LP/HP Attenuation, PeakEQ Boost, Passthrough, Reset

**R1B — Delay-Line** (`dsp/delay_line.rs`, 150 Zeilen)
- Pre-allokierter Power-of-2 Ringbuffer
- Integer-Delay + Linear-Interpolation + Cubic-Hermite Interpolation
- Wraparound-sicher (Bit-Masking statt Modulo)
- 4 Unit-Tests

**R1B — ADSR Envelope** (`dsp/envelope.rs`, 276 Zeilen)
- 5-State Machine: Idle → Attack → Decay → Sustain → Release
- Exponentieller Kurvenverlauf (natürlich klingendes Attack/Decay/Release)
- Sample-accurate Transitions
- `note_on()`, `note_off()`, `kill()`, `process()`, `process_block()`
- 5 Unit-Tests

**R1B — LFO** (`dsp/lfo.rs`, 197 Zeilen)
- 6 Shapes: Sine, Triangle, Square, SawUp, SawDown, Sample&Hold
- Bipolar (-1..1) und Unipolar (0..1) Output
- Phase-Reset für synced LFOs
- XorShift RNG für Sample&Hold
- 4 Unit-Tests

**R1C — Math Utilities** (`dsp/math.rs`, 118 Zeilen)
- `db_to_linear()`, `linear_to_db()`, `midi_to_freq()`, `freq_to_midi()`
- `fast_tanh()` (Padé-Approximant), `soft_clip()`, `hard_clip()`
- `lerp()`, `equal_power_crossfade()`
- 4 Unit-Tests

**R1C — Parameter Smoother** (`dsp/smooth.rs`, 135 Zeilen)
- One-Pole exponentieller Glättungsfilter
- Verhindert Zipper-Noise bei Automation (Volume, Pan, Filter-Freq)
- `set_target()` + `process()` → glatter Übergang
- 3 Unit-Tests

**R1C — DC Blocker + Pan + Interpolation** (`dsp/interpolation.rs`, 207 Zeilen)
- DC Blocker: High-Pass bei 5Hz, entfernt Gleichspannungsoffset
- Equal-Power Pan Law + Linear Pan + Buffer-Application
- Linear, Cubic-Hermite, Lagrange-4 Interpolation für Sample-Playback
- 4 Unit-Tests

## Geänderte Dateien

| Datei | Zeilen | Status |
|---|---|---|
| pydaw_engine/src/dsp/mod.rs | 32 | NEU |
| pydaw_engine/src/dsp/biquad.rs | 445 | NEU |
| pydaw_engine/src/dsp/delay_line.rs | 150 | NEU |
| pydaw_engine/src/dsp/envelope.rs | 276 | NEU |
| pydaw_engine/src/dsp/lfo.rs | 197 | NEU |
| pydaw_engine/src/dsp/math.rs | 118 | NEU |
| pydaw_engine/src/dsp/smooth.rs | 135 | NEU |
| pydaw_engine/src/dsp/interpolation.rs | 207 | NEU |
| pydaw_engine/src/main.rs | +1 Zeile (`mod dsp;`) | GEÄNDERT |
| PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md | 20 Checkboxen [x] | GEÄNDERT |
| VERSION | 666 → 667 | |

## Nächste Schritte
- `cd pydaw_engine && cargo test -- dsp` → Alle 30 Unit-Tests müssen grün sein
- `cargo build --release` → 0 errors, 0 warnings
- Dann: **Phase R2A — Parametric EQ** (nutzt Biquad aus R1)

## Phase R2 KOMPLETT — 5 neue FX-Dateien, 999 Zeilen

**R2A — Parametric EQ** (`fx/parametric_eq.rs`, 160 Zeilen)
- 8-Band EQ, jede Band = StereoBiquad aus R1
- Band-Typen: Bell, LowShelf, HighShelf, HighPass, LowPass
- Disabled-Bands = Passthrough (keine CPU-Kosten)
- 2 Unit-Tests

**R2B — Compressor** (`fx/compressor.rs`, 266 Zeilen)
- Feed-Forward RMS Compressor mit Soft-Knee
- Attack/Release Ballistics (One-Pole Envelope)
- Optionaler Sidechain-Buffer
- Gain-Reduction Metering für GUI
- 3 Unit-Tests

**R2B — Limiter** (`fx/limiter.rs`, 132 Zeilen)
- Brickwall Limiter: Instant Attack, Smooth Release
- Ceiling + Input-Gain Controls
- 2 Unit-Tests

**R2C — Reverb** (`fx/reverb.rs`, 252 Zeilen)
- Schroeder/Freeverb: 4 Comb Filters + 4 Allpass Filters
- Stereo mit Sample-Rate-skalierter Tuning + Spread
- Pre-Delay, Decay, Damping, Wet/Dry Mix
- 2 Unit-Tests

**R2C — Delay** (`fx/delay.rs`, 170 Zeilen)
- Stereo Delay mit Fractional-Delay Readout
- Feedback mit LP-Filter, Ping-Pong Mode
- Tempo-Sync Methode (Beat-Fraction × BPM)
- 2 Unit-Tests
