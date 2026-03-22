# SESSION LOG — Prewarm StretchPool FULL Integration (v0.0.20.24)

Datum: 2026-02-08  
Kollege: Anno (ChatGPT)

## Ziel
Den in v0.0.20.23 vorbereiteten EssentiaWorkerPool/StretchPool nun **wirklich** in den Prewarm-Flow integrieren,
so dass BPM-abhängige Stretches nicht mehr im Prewarm-Thread blockierend berechnet werden, sondern als Jobs queued werden.

## Änderungen (Code)
### 1) ArrangerRenderCache (pydaw/audio/arranger_cache.py)
- Neu:
  - `make_stretched_key(path, sr, rate)` (public Key-Builder inkl. File-Signature)
  - `peek_stretched(path, sr, rate)` (RAM/Disk check ohne Compute)
  - `put_stretched(path, sr, rate, buf)` (Pool kann Ergebnis direkt in Cache schreiben)

### 2) EssentiaWorkerPool (pydaw/audio/essentia_pool.py)
- Dedup-Fall verbessert:
  - Wenn derselbe `cache_key` bereits pending ist, kann jetzt der **zweite** Caller trotzdem einen Callback anhängen
    (Callback-Chaining), statt “still” zu sein.

### 3) PrewarmService (pydaw/services/prewarm_service.py)
- Prewarm-Job:
  - Prüft zuerst `cache.peek_stretched()`
  - Wenn nicht vorhanden und Pool verfügbar:
    - decodiert via `cache.get_decoded()`
    - submitted Stretch-Job in Pool (PRIORITY_HIGH, dedup per cache_key)
    - Callback schreibt Ergebnis via `cache.put_stretched()`
  - Fallback ohne Pool: nutzt weiterhin `cache.get_stretched()`
- BPM-Change Debounce:
  - cancel normal/low pending Stretch-Jobs via `cancel_below_priority(PRIORITY_NORMAL)` (verhindert Backlog bei BPM-Drag)

## Ergebnis
- Prewarm bleibt responsive: Stretches werden parallel/async per Pool queued.
- Cache kann durch Pool-Ergebnisse gefüllt werden (inkl. optionalem Disk-Cache).

## Nächste sinnvolle Schritte
- Optional: `stretches_completed` im Callback zählen (Thread-safe Aggregation) + UI/Status verbessern.
- Optional: “visible range” vs “lookahead” in PRIORITY_HIGH/PRIORITY_NORMAL splitten.
- Optional: Per-Track Rendering aus dem Phase-3-Guide implementieren.

