# Session Log — v0.0.20.7 — Preview-Cache (LRU)

**Datum:** 2026-02-07  
**Assignee:** GPT-5.2  
**Ziel:** Wiederholtes Vorhören im Sample-Browser sofort starten (ohne Re-Render), GUI bleibt flüssig.

## Änderungen
### ✅ PreviewCache (LRU)
- Neues Modul: `pydaw/audio/preview_cache.py`
- In-Memory LRU mit Byte-Limit (default 256 MB)
- Cache-Key enthält:
  - absoluter Pfad
  - file mtime + size (Invalidate wenn Sample geändert)
  - Mode (raw/sync), Loop, Projekt-BPM, Beats/Bar, BPM-Hint, SR

### ✅ SampleBrowser nutzt Cache
- `pydaw/ui/sample_browser.py`
  - Cache-Hit: Buffer wird sofort in PreviewPlayer geladen und gestartet
  - Cache-Store: Render-Ergebnis wird in LRU gespeichert (optional zusätzlich unter finalem BPM-Hint Key)

## Testplan
1) Browser öffnen → Sample anklicken
2) Sync + Loop → Preview → erster Lauf rendert (…Rendering)
3) Stop → Preview erneut → sollte sofort starten (kein Rendering)
4) Projekt-BPM ändern → Cache-Key ändert sich → erneutes Render erwartbar

## Next (AVAILABLE)
- Disk-Cache optional (persistenter Preview-Cache)
- Arranger: Clip-PreRender/Caching für lange Sessions (CPU-Spikes vermeiden)
- Echt gapless Loop (Crossfade-Wrap im Ringbuffer)
