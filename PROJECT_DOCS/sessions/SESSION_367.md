# Session 367 — VST3 Startup Cache-Guard + Probe-Timeout

**Datum**: 2026-03-09  
**Entwickler**: Claude Sonnet 4.6  
**Version**: 0.0.20.366 → 0.0.20.367

## Problem

Der DAW-Start hängt 10–60 Sekunden, weil bei jedem Start ein vollständiger
VST3-Scan ausgelöst wird. Das LSP-Plugins-Bundle (`lsp-plugins.vst3`) enthält
100+ DSP-Plugins und initialisiert beim `pedalboard.load_plugin()`-Probe
interne Thread-Pools (~360 kurzlebige Threads, im GDB-Trace sichtbar).

Zusätzlich: kein Timeout im Probe → hängendes VST3-Binary blockiert
den gesamten Scan für immer.

## Root Cause

`PluginsBrowserWidget.__init__()` rief immer `rescan(async_=True)` auf —
auch wenn ein frischer Cache unter `~/.cache/ChronoScaleStudio/plugin_cache.json`
existierte. Das `save_cache()` schreibt zwar bereits einen `ts`-Timestamp,
aber dieser wurde nie ausgewertet.

## Fixes

### Fix 1: `pydaw/services/plugin_scanner.py`
Neue Funktion `cache_is_fresh(max_age_seconds=3600*4)`:
- Liest `ts` aus dem Cache-JSON
- Gibt `True` zurück wenn Cache jünger als der Schwellwert
- Exception-sicher (gibt `False` bei Fehler)

### Fix 2: `pydaw/ui/plugins_browser.py`
`__init__()` prüft jetzt vor dem Scan:
```python
if not self._data or not plugin_scanner.cache_is_fresh(max_age_seconds=3600 * 4):
    self.rescan(async_=True)
else:
    self._set_status(f"Cache geladen: {total} Plugins. ...")
```
Warmer Start: kein Scan, sofortige Anzeige aus Cache.

### Fix 3: `pydaw/audio/vst3_host.py`
`probe_multi_plugin_names()` läuft jetzt in `ThreadPoolExecutor` mit 15s-Timeout:
- `TimeoutError` → Warning auf stderr, gibt `[]` zurück
- Rest des Scans läuft ungestört weiter

## Ergebnis

| Situation | Vorher | Nachher |
|-----------|--------|---------|
| Warmer Start (Cache < 4h) | Async-Scan → ~30s Hänger | Sofort aus Cache |
| Kalter Start | Async-Scan + LSP blockiert | Async-Scan + 15s Timeout |
| Explicit Rescan | Vollscan | Vollscan (unverändert) |
| Plugin hängt | Infinite wait | Abbruch nach 15s |

## Nicht geändert

- DSP-Core, Transport, Mixer, Routing
- Verhalten beim Laden aus gespeichertem Projekt
- Explicit Rescan-Button

## Geänderte Dateien

- `pydaw/services/plugin_scanner.py` — `cache_is_fresh()` hinzugefügt
- `pydaw/ui/plugins_browser.py` — bedingter Startup-Scan
- `pydaw/audio/vst3_host.py` — 15s-Timeout in `probe_multi_plugin_names()`
- `VERSION` — 0.0.20.366 → 0.0.20.367
