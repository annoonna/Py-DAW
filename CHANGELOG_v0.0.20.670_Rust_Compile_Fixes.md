# CHANGELOG v0.0.20.670 — Rust Compile Fixes (7 Errors + 2 Warnings)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration — Compile-Fix nach realem `cargo build`

## Was wurde gemacht

### 7 Compile-Errors behoben

1. **`deesser.rs:67-68`** — `Biquad::new()` ohne Argumente aufgerufen
   - Fix: `Biquad::new(FilterType::BandPass, 6500.0, 2.0, 0.0, sample_rate)`
   - Biquad::new() braucht 5 Parameter (filter_type, freq, q, gain_db, sample_rate)

2. **`stereo_widener.rs:55-58`** — 4× `Biquad::new()` ohne Argumente
   - Fix: LP-Filter mit `FilterType::LowPass, 200.0, 0.707` und HP mit `FilterType::HighPass, 200.0, 0.707`
   - Default-Crossover bei 200Hz (Bass-Mono-Grenzfrequenz)

3. **`engine.rs:90`** — `match cmd` nicht exhaustiv (6 neue IPC Commands fehlten)
   - Fix: Handler für `AddFx`, `RemoveFx`, `SetFxBypass`, `SetFxEnabled`, `ReorderFx`, `SetFxChainMix`
   - Jeder Handler nutzt `graph.find_track_index()` → `graph.get_track_mut()` → `fx_chain.*`

### 2 Warnings behoben

4. **`spectrum_analyzer.rs:134`** — Unused variable `num_bins`
   - Fix: `let _num_bins = ...`

5. **`chain.rs` / `reverb.rs`** — Infinite recursion in `impl_fx_node!` Macro
   - Ursache: `Reverb` hatte kein `set_sample_rate()` — Macro rief sich selbst auf
   - Fix: `Reverb::set_sample_rate()` hinzugefügt (speichert neue SR, ruft reset())

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw_engine/src/fx/deesser.rs` | Biquad::new() mit korrekten 5 Argumenten |
| `pydaw_engine/src/fx/stereo_widener.rs` | 4× Biquad::new() mit LP/HP + Butterworth Q |
| `pydaw_engine/src/fx/reverb.rs` | `set_sample_rate()` Methode hinzugefügt |
| `pydaw_engine/src/fx/spectrum_analyzer.rs` | `_num_bins` statt `num_bins` |
| `pydaw_engine/src/engine.rs` | 6 FX-Chain Command-Handler implementiert |
| `VERSION` | 669 → 670 |
| `pydaw/version.py` | 669 → 670 |

## Erwartetes Ergebnis
```
cargo build --release → 0 errors, 0 warnings
cargo test → alle Tests pass
```
