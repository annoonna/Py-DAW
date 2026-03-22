# Changelog — v0.0.20.24 (StretchPool Prewarm FULL)

## Highlights
- PrewarmService nutzt jetzt den EssentiaWorkerPool für asynchrones Time-Stretching (Jobs queued, kein blockierender Stretch im Prewarm-Thread)
- ArrangerRenderCache kann durch Pool-Ergebnisse befüllt werden (peek/put + stabiler cache_key)
- EssentiaWorkerPool-Dedup unterstützt jetzt mehrere Callbacks pro cache_key

## Geänderte Dateien
- pydaw/audio/arranger_cache.py
- pydaw/audio/essentia_pool.py
- pydaw/services/prewarm_service.py
- VERSION
- pydaw/version.py
- PROJECT_DOCS/progress/TODO.md
- PROJECT_DOCS/progress/DONE.md
- PROJECT_DOCS/sessions/LATEST.md
- PROJECT_DOCS/sessions/2026-02-08_SESSION_PREWARM_STRETCHPOOL_FULL_v0.0.20.24.md
