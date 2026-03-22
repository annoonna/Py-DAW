# CHANGELOG v0.0.20.679 — Fix: Benchmark misst jetzt echte Rust-Render-Zeit

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Fix: Performance-Benchmark (Apples-to-Oranges Vergleich)

## Root Cause Analyse

Der Benchmark zeigte "Rust 60× langsamer als Python" — das war **falsch**.

### Das Problem:

| Benchmark | Python | Rust |
|---|---|---|
| Audio | Misst numpy-Mixing (~198µs) | Misst `ping() + time.sleep(11610µs)` ← **SLEEP!** |
| MIDI | Misst dict-Routing im RAM (~5µs) | Misst 32× einzelne IPC-Socket-Roundtrips (~5000µs) |

Die "11862µs Rust-Render-Zeit" war fast exakt `512/44100 * 1e6 = 11610µs`
— das ist die **Sleep-Duration**, nicht die Render-Zeit der Rust-Engine!

### Die echte Rust-Performance war immer da:
- IPC Roundtrip: ~1464µs (davon ~1000µs = sleep(0.001))
- Echte Render-Zeit: unsichtbar, weil `cpu_load: 0.0 // TODO: measure`

## Was wurde gefixt

### 1. Rust Engine: Echte Render-Zeitmessung (`engine.rs`)
- `process_audio()` umklammert mit `Instant::now()` + `elapsed().as_micros()`
- Neue Felder: `last_render_us: AtomicU32`, `budget_us: AtomicU32`
- `Pong` Handler: `cpu_load = last_render_us / budget_us` (echte Last)
- Neues Feld `render_time_us` im Pong-Event

### 2. Pong-Event erweitert (`ipc.rs`)
- Neues Feld: `render_time_us: u32` — echte process_audio()-Dauer in Mikrosekunden

### 3. Python Bridge (`rust_engine_bridge.py`)
- Pong-Handler speichert `_last_render_time_us` und `_last_cpu_load`
- Init-Felder für neue Metriken

### 4. Benchmark (`engine_benchmark.py`)
- **`_bench_rust_audio()`**: Liest jetzt `bridge._last_render_time_us` aus Pong-Events
  statt `ping() + time.sleep()` zu messen. Warmup-Phase (100ms). Poll-Intervall angepasst.
- **`_bench_rust_midi()`**: Berechnet jetzt Per-Event-Kosten (total_us / event_count)
  für fairen Vergleich mit Python (das auch pro Buffer/Batch misst).

## Erwartete Benchmark-Ergebnisse nach dem Fix

| | Python | Rust (erwartet) |
|---|---|---|
| Audio (8 Tracks, Sine Mix) | ~200µs | ~10–50µs (lockfreie Graph-Verarbeitung) |
| MIDI (32 Events) | ~5µs (in-process) | ~5–20µs/Event (IPC overhead) |

MIDI wird per-IPC-Call immer langsamer sein als in-process Python (Natur der Sache
bei Unix Socket + MessagePack). Audio-Rendering sollte Rust deutlich schneller sein
sobald echte DSP-Last (Plugins, FX) dazukommt.

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/engine.rs | Instant-Timing in process_audio, Pong mit render_time_us |
| pydaw_engine/src/ipc.rs | Pong-Event + render_time_us Feld |
| pydaw/services/rust_engine_bridge.py | Pong-Handler speichert render_time_us |
| pydaw/services/engine_benchmark.py | Audio + MIDI Benchmark komplett umgeschrieben |
| VERSION, pydaw/version.py | 678 → 679 |
