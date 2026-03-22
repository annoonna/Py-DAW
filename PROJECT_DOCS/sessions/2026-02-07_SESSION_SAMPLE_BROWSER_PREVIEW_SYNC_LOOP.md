# Session Log – 2026-02-07 – v0.0.20.6

## Ziel
Pro-DAW-Style Sample Browser bekommt einen integrierten Preview-Player:
- **Raw** (Originaltempo)
- **Sync** (Beat-matched zum Projekt-BPM, pitch-preserving)
- **Loop** (gapless / click-safe, in Sync auf Bar-Boundary ausgerichtet)
Zusätzlich: **BPM Analyse** beim Anklicken eines Samples (Essentia RhythmExtractor2013).

## Änderungen (Code)
### Browser Preview + BPM
- `pydaw/ui/sample_browser.py`
  - Preview UI (Raw/Sync + Loop + Play/Stop)
  - Background Threads:
    - BPM Analyse (Essentia → Fallback)
    - Render/Time-Stretch für Preview (kein UI-Freezing)
  - Drag&Drop: sendet `application/x-pydaw-audio-bpm` via MimeData (wenn BPM bekannt)

### Neue Audio-Module
- `pydaw/audio/bpm_detect.py` (NEU)
  - Essentia RhythmExtractor2013 (primary)
  - Fallbacks: Dateiname (`120bpm`), Autocorr-Estimator (best-effort)
- `pydaw/audio/preview_player.py` (NEU)
  - Pull-Source PreviewPlayer (buffered) mit optionalem Loop + click-safe boundary fades
  - Start-delay in Samples (quantized Start)

### Wiring / Integration
- `pydaw/ui/device_browser.py` + `pydaw/ui/main_window.py`
  - Browser erhält `audio_engine`, `transport`, `project_service` aus `ServiceContainer`
- `pydaw/ui/arranger_canvas.py` + `pydaw/services/project_service.py`
  - BPM Override beim Drop → AudioClip bekommt verlässliches `source_bpm`
- `pydaw/services/transport_service.py`
  - `bpm_changed` Signal wird in `set_bpm()` emittiert (für Live-UI/Sync)

## Version
- `VERSION` → v0.0.20.6
- `pydaw/version.py` → 0.0.20.6

## Test-Checkliste (manuell)
1) Öffne DAW → rechter Browser → Samples Tab
2) Klick auf ein Sample:
   - BPM erscheint (Essentia/Dateiname)
3) Preview:
   - Raw → Play (Originaltempo)
   - Sync → Play (auf Projekt-BPM gestretcht, Pitch bleibt)
   - Loop aktivieren → Sync Preview sollte sauber in der Bar laufen (kein Knacksen beim Loop)
4) Drag&Drop aus Browser auf Arranger:
   - AudioClip bekommt `source_bpm` (wenn erkannt) und skaliert korrekt mit Projekt-BPM

## Nächste Schritte (AVAILABLE)
- Cache für gestretchte Preview-Buffers (LRU) damit Sync-Preview sofort startet.
- Arranger Playback: real-time/streaming Time-Stretch (nicht nur Render) + Background pre-render per Clip.
- Mixer: Essentia FX-Chain (Limiter/EQ) als optionaler Master/Track Insert (Automation-ready).

