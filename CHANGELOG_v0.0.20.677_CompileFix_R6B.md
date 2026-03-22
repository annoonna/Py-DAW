# CHANGELOG v0.0.20.677 — Fix: Rust Compile Errors (R6B + Engine)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Fix: 6 Compile-Errors aus v0.0.20.676

## Was wurde gemacht

### 1. Fix: Borrow-Checker-Fehler in `multisample.rs` (5 Errors)

**Problem:** `alloc_voice(&mut self)` returnierte `&mut MultiSampleVoice`, was `self` mutabel
borgte. Danach war Zugriff auf `self.map`, `self.sample_rate` und weitere `self.voices`-Iterationen
unmöglich (Rust Borrow Rules: nur ein `&mut` zur Zeit).

**Fix:** `alloc_voice()` durch `alloc_voice_index(voices: &[MultiSampleVoice]) -> Option<usize>`
ersetzt. Diese Funktion nimmt nur einen Shared-Ref auf den Voice-Slice (kein `&mut self`).
In `handle_midi_event()` wird jetzt:
1. Voice-Index via `alloc_voice_index(&self.voices)` ermittelt
2. Zone-Daten aus `self.map` gelesen und geklont
3. Erst dann `self.voices[idx]` mutabel zugegriffen → kein Borrow-Konflikt

### 2. Fix: Non-exhaustive match in `engine.rs` (1 Error E0004)

**Problem:** 8 neue IPC Commands (AddSampleZone, RemoveSampleZone, etc.) waren in `ipc.rs`
definiert, aber `engine.rs::handle_command()` hatte keine match-Arms dafür.

**Fix:** Vollständige Command-Dispatch-Implementierung für alle 8 MultiSample-Commands:
- `AddSampleZone`: WAV laden → downcast zu MultiSampleInstrument → apply_command
- `RemoveSampleZone`, `ClearAllZones`: Direkt an MultiSampleInstrument weiterleiten
- `SetZoneFilter`, `SetZoneEnvelope`, `SetZoneLfo`, `SetZoneModSlot`: Parameter-Dispatch
- `AutoMapZones`: Batch-WAV-Load + AutoMap-Command

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/instruments/multisample.rs | alloc_voice → alloc_voice_index (Borrow-Fix) |
| pydaw_engine/src/engine.rs | 8 neue match-Arms für MultiSample-Commands |
| VERSION, pydaw/version.py | 676 → 677 |

## Erwartetes Ergebnis
```
cargo build --release → 0 errors, 0 warnings
cargo test → alle Tests pass
```
