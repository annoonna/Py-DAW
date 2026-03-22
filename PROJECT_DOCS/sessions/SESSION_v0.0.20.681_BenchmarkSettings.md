# Session Log — v0.0.20.681

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Fix: Benchmark benutzt jetzt echte Audio-Einstellungen
**Aufgabe:** Benchmark soll SR/Buffer aus QSettings lesen statt hardcoded 44100/512

## Was wurde erledigt

### Problem
Der Benchmark benutzte hardcoded `sample_rate=44100, buffer_size=512` —
aber die echten Audio-Einstellungen des Users sind `48000 Hz / 2048 Buffer`.
Das verfälscht Budget-Berechnung und Realtime-Ratio.

### Fix: `engine_benchmark.py`
- `run_benchmark()`: Defaults geändert auf `sample_rate=0, buffer_size=0` (Sentinel)
- Neue Methode `_read_audio_settings()`: Liest `audio/sample_rate` und
  `audio/buffer_size` aus QSettings (via `pydaw.core.settings_store.get_value`)
- Fallback: 48000/512 wenn QSettings nicht verfügbar
- Sanity-Clamp: SR 8000–192000, Buffer 32–8192

### Ergebnis
Der Benchmark-Header zeigt jetzt die echten Settings:
```
Tracks: 8 | Buffer: 2048 | SR: 48000 Hz | Duration: 3.0s
Budget per buffer: 42667 µs    ← statt vorher 11610 µs
```

## Geänderte Dateien
- pydaw/services/engine_benchmark.py (auto-detect + _read_audio_settings)
- VERSION, pydaw/version.py (680 → 681)

## Nächste Schritte
- Phase R7B — DrumMachine Multi-Output
