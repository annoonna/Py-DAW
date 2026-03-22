# v0.0.20.367 — VST3 Startup: Cache-Freshness-Guard + Probe-Timeout

## Probleme (gemeldet)

1. **Langer Startup** — Terminal braucht sehr lange bis die DAW aufgebaut ist.
2. **VST3 nicht im Device sichtbar** — nach dem langen Start sind die Plugins nicht
   sofort im Browser vorhanden bzw. das Device zeigt keine VST3-Parameter.

## Ursachen

### Problem 1: Startup-Scan instanziiert `lsp-plugins.vst3` bei jedem Start

`PluginsBrowserWidget.__init__()` rief bisher **immer** `rescan(async_=True)` auf,
auch wenn ein frischer Cache existierte.  Der asynchrone Scan in einem `QThread` rief
`probe_multi_plugin_names()` → `pedalboard.load_plugin("/usr/lib/vst3/lsp-plugins.vst3", "")`
auf.  Die LSP-Plugin-Suite enthält 100+ DSP-Plugins und initialisiert beim Laden
thread-basierte Engine-Pools.  Im GDB-Trace erzeugt das **Hunderte kurzlebiger
Thread-Paare** (`[New Thread … exited]`) – deutlich sichtbar zwischen dem ersten
`[MainWindow._on_project_opened]` und dem zweiten VST3-Load.  Das verursacht CPU-
Contention und verlängert den Start spürbar.

### Problem 2: Kein Cache → leerer Plugin-Browser

Beim allerersten Start (kein Cache) oder nach Cache-Ablauf lädt der Browser zunächst
leer, der async Scan dauert wegen LSP-Probe ~10–30 s, und erst danach erscheinen die
Plugins im `🔌 Plugins`-Tab.  Nutzer sehen einen leeren Tab und denken, VST3 sei
kaputt.

## Fixes

### `pydaw/services/plugin_scanner.py`

- Neue Funktion **`cache_is_fresh(max_age_seconds=3600*4)`**: liest den `ts`-Timestamp
  aus dem JSON-Cache und gibt `True` zurück, wenn der Cache jünger als der Schwellwert
  ist (Standard: 4 Stunden).  Robustes Exception-Handling.

### `pydaw/ui/plugins_browser.py`

- `PluginsBrowserWidget.__init__()`: ruft `rescan(async_=True)` jetzt **nur** auf, wenn
  kein Cache vorliegt (`self._data` leer) **oder** der Cache älter als 4 h ist.
  Bei frischem Cache wird stattdessen eine informative Statuszeile angezeigt:
  `"Cache geladen: N Plugins. Klicke 'Rescan' um den Plugin-Scan zu aktualisieren."`
  Der Nutzer kann jederzeit über den **Rescan**-Button einen vollständigen Scan anstoßen.

### `pydaw/audio/vst3_host.py`

- `probe_multi_plugin_names()`: läuft jetzt mit einem **15-Sekunden-Timeout** in einem
  `ThreadPoolExecutor`.  Hängt ein Plugin-Binary beim Probe, wird nach 15 s abgebrochen
  und eine Warnmeldung nach `stderr` geschrieben – der Rest des Scans läuft weiter.
  Verhindert potentielle Hang-Situationen bei unbekannten VST3-Bundles.

## Nicht verändert

- Kein DSP-Core, kein Transport, kein Mixer, kein Routing.
- Kein Verhalten beim expliziten Rescan (bleibt vollständig wie bisher).
- Kein Verhalten beim Laden aus dem Projekt (VST3 laden aus gespeichertem Zustand).
- Kein Verhalten beim Drag&Drop vom Browser in den Device-Panel.
- Die LSP-Multi-Plugin-Expansion bleibt aktiv – sie greift nur nicht mehr beim
  Kaltstart, wenn ein frischer Cache vorhanden ist.

## Ergebnis

| Situation | Vorher | Nachher |
|-----------|--------|---------|
| Kaltstart, kein Cache | Async-Scan mit LSP-Probe (~30 s Last) | Async-Scan mit LSP-Probe + 15 s Timeout |
| Warmstart (Cache < 4 h) | Async-Scan **immer** | Cache direkt anzeigen, **kein Scan** |
| Warmstart (Cache > 4 h) | Async-Scan | Async-Scan (wie bisher) |
| Expliziter Rescan-Klick | Vollscan | Vollscan (unverändert) |
| Plugin hängt im Probe | Ewiges Warten | Abbruch nach 15 s, Warnung |
