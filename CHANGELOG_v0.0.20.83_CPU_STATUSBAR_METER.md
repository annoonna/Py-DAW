# CHANGELOG v0.0.20.83 — Optional: CPU Anzeige (Statusbar)

## Added
- Ansicht → **CPU Anzeige** (Ctrl+Shift+U)
- Statusbar-Label "CPU: xx%" (opt-in, Default OFF)

## Implementation notes
- Ultra-low overhead Sampling ohne psutil:
  - `time.process_time()` deltas / `time.perf_counter()` deltas
  - normalisiert auf `os.cpu_count()`
- Läuft ausschließlich im GUI-Thread via QTimer (1000ms)

## Files
- `pydaw/ui/perf_monitor.py` (neu)
- `pydaw/ui/main_window.py`
- `pydaw/ui/actions.py`
- `pydaw/core/settings.py`
