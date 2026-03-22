# CHANGELOG v0.0.20.675 — Rust Compile Fixes (R6A)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Fix: 1 Error + 1 Warning aus cargo build (Phase R6A)

## Was wurde gemacht

1. **error[E0277]: SampleData doesn't implement Debug** (sample/mod.rs)
   - Ursache: `SamplerCommand::LoadSample(SampleData)` braucht `#[derive(Debug)]` → aber SampleData hatte nur `#[derive(Clone)]`
   - Fix: Manuelles `impl Debug for SampleData` das nur Metadaten zeigt (nicht tausende Samples ausgeben)

2. **warning: unused variable `ctx`** (instruments/sampler.rs:436)
   - Fix: `ctx` → `_ctx` im `process()` Parameter

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/sample/mod.rs | `impl Debug for SampleData` (zeigt nur name/channels/sr/frames/root/tune) |
| pydaw_engine/src/instruments/sampler.rs | `ctx` → `_ctx` in process() Signatur |
| VERSION | 674 → 675 |
| pydaw/version.py | 674 → 675 |

## Erwartetes Ergebnis
```
cargo build --release → 0 errors, 0 warnings
cargo test → 105+ passed, 0 failed
```

## Was als nächstes zu tun ist
- Phase R6B — MultiSample / Advanced Sampler
