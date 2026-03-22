# Session Log — 2026-02-07

## Titel
ArrangerRenderCache (Shared) + Tempo-Sync Cache Reuse (sounddevice + JACK)

## Kontext
- Preview-Browser (Raw/Sync/Loop) + PreviewCache laufen stabil (v0.0.20.7)
- Nächster Schritt: Arrangement-Playback muss **Tempo-Sync** nutzen, ohne dass beim Play/Stop oder bei BPM-Wechsel ständig neu gestretcht wird.
- Zusätzlich: JACK-Backend und sounddevice-Backend sollen **die gleiche Vorbereitung** nutzen.

## Umsetzung
### 1) Neuer Cache-Layer
- `pydaw/audio/arranger_cache.py`
  - `ArrangerRenderCache`: 2 LRU-Caches (byte-budgeted)
    - decoded/resampled buffers
    - stretched buffers (rate+sr keyed)
  - Keys enthalten `mtime/size` → automatische Invalidation
  - Optionaler Disk-Cache (OFF per default)

### 2) JACK Prepare nutzt Cache
- `prepare_clips(project, sr, cache=...)` unterstützt optionalen Cache
- `AudioEngine.start_arrangement_playback()` übergibt `self._arranger_cache` an `prepare_clips`.

### 3) sounddevice Arranger nutzt Cache
- `AudioEngine.start_arrangement_playback()` übergibt `arranger_cache_ref` in die Thread-Config.
- `_EngineThread._run_sounddevice_arrangement()`
  - decode/resample via cache
  - time-stretch via cache (`get_stretched`) → Reuse across Play/Stop

### 4) Offset-Mapping unter Stretch
- Offset-Sekunden werden auf stretched-time abgebildet:
  - `offset_sample = (offset_s * sr) / rate`

## Dateien
- `pydaw/audio/arranger_cache.py` (NEU)
- `pydaw/audio/arrangement_renderer.py`
- `pydaw/audio/audio_engine.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Nächster Schritt (Vorschlag)
- Arranger-Editor: BPM-Feld Änderung → optional "Pre-Warm" der Stretch-Caches für sichtbare Clips
- Disk-Cache default optional in Settings
- Bar-accurate Loop für Arranger (Clip-Level)
