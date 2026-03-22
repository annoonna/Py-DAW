# CHANGELOG v0.0.20.634 — Rust Build Fix (Arc Ownership + Warnings)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6

## Was wurde gemacht

### Rust Kompilier-Fehler behoben (`pydaw_engine/src/main.rs`)
- **`error[E0382]: borrow of moved value: engine_for_audio`**
  - Ursache: In Rust darf ein `Arc` nicht in zwei `move`-Closures gleichzeitig verschoben werden
  - Fix: Separater `Arc::clone()` für jeden Closure:
    - `engine_ref` → Audio-Callback (process_audio)
    - `engine_err` → Error-Callback (record_xrun)
    - `engine_for_audio` → while-Loop (running check)

### Warnings behoben
- **`unused import: SineGenerator`** in `engine.rs` → Import entfernt
- **`unused variable: buffer`** in `audio_node.rs` MixNode → `_buffer`

## Erklärung für Rust-Einsteiger

In Rust hat jeder Wert genau **einen Besitzer** (Ownership). Wenn ein Wert
in einen `move`-Closure geht, gehört er ab dann dem Closure — man kann ihn
nicht nochmal woanders benutzen. Die Lösung: `Arc::clone()` erstellt einen
neuen "Zeiger" auf dieselben Daten. Jeder Closure bekommt seinen eigenen
Zeiger, aber alle zeigen auf die gleiche Engine.

```rust
// VORHER (Fehler — engine_for_audio wird zweimal "verschoben"):
let engine_ref = Arc::clone(&engine_for_audio);
move |data| { engine_ref.process_audio(...); }     // OK
move |err|  { engine_for_audio.record_xrun(); }    // FEHLER: schon verschoben!
while engine_for_audio.running...                   // FEHLER: schon verschoben!

// NACHHER (korrekt — jeder bekommt seinen eigenen Clone):
let engine_ref = Arc::clone(&engine_for_audio);     // Clone 1 → Audio
let engine_err = Arc::clone(&engine_for_audio);     // Clone 2 → Error
move |data| { engine_ref.process_audio(...); }      // OK
move |err|  { engine_err.record_xrun(); }           // OK
while engine_for_audio.running...                   // OK (Original noch da)
```

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw_engine/src/main.rs` | Arc Clone Fix (1 Fehler) |
| `pydaw_engine/src/engine.rs` | Unused Import entfernt (1 Warning) |
| `pydaw_engine/src/audio_node.rs` | Unused Variable gefixt (1 Warning) |
| `VERSION` | 0.0.20.633 → 0.0.20.634 |
