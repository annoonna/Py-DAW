# Session Log — v0.0.20.636

**Datum:** 2026-03-19
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2B — Multi-Track Recording
**Aufgabe:** Mehrere Tracks gleichzeitig aufnehmen, Input-Routing, Buffer-Size, PDC

## Was wurde erledigt

### 1. RecordingService → Multi-Track (recording_service.py)
- `TrackRecordingState` Dataclass für per-Track State (frames, path, input_pair)
- `_armed_tracks: Dict[str, TrackRecordingState]` ersetzt Single-Track-Feld
- `arm_track()` / `disarm_track()` unterstützen jetzt N Tracks gleichzeitig
- `start_recording()` erzeugt pro armed Track einen eigenen Frame-Buffer
- `stop_recording()` speichert pro Track eine separate WAV + feuert Callback
- JACK Backend: Separate Portpaare pro Input-Pair, Demux im Process-Callback
- sounddevice: Multi-Channel InputStream, Demux auf Track-Buffers im Callback
- Volle Backward-Kompatibilität: Single-Track-API (track_id, input_pair) funktioniert weiterhin

### 2. Input-Routing UI (mixer.py)
- `cmb_input` ComboBox im MixerStrip: "In 1/2", "In 3/4", etc.
- `_populate_input_routing()` fragt RecordingService nach verfügbaren Inputs
- `_on_input_pair_changed()` setzt `Track.input_pair` im Model
- `refresh_from_model()` synct ComboBox ← Track.input_pair

### 3. Buffer-Size Settings (audio_settings_dialog.py)
- `spin_buf` SpinBox → `cmb_buf` ComboBox (64/128/256/512/1024/2048/4096)
- Latenz-Anzeige in ms pro Eintrag ("512 (10.7 ms @ 48kHz)")
- Load/Save via SettingsKeys, Accept() persistiert als integer

### 4. PDC Framework (recording_service.py)
- `set_track_pdc_latency(track_id, latency_samples)` — pro Track
- `get_track_pdc_latency()`, `get_max_pdc_latency()`
- Bei WAV-Save: PDC-Samples werden am Anfang getrimmt
- Bei Clip-Erstellung: start_beat wird um PDC-Beats korrigiert

### 5. MainWindow Multi-Track (main_window.py)
- Recording Toggle sammelt ALLE armed Tracks (nicht nur den ersten)
- `rec.disarm_track(None)` + loop `rec.arm_track()` pro armed Track
- Status-Anzeige: "Recording: 3 Track(s), jack, Buffer 512"

### 6. Container Wiring (container.py)
- Buffer-Size aus Settings → RecordingService bei Init

## Geänderte Dateien
- pydaw/services/recording_service.py (komplett überarbeitet)
- pydaw/ui/mixer.py (Input ComboBox + _populate_input_routing)
- pydaw/ui/main_window.py (Multi-Track Recording Toggle)
- pydaw/ui/audio_settings_dialog.py (Buffer ComboBox)
- pydaw/services/container.py (Buffer-Size Wiring)
- pydaw/version.py
- VERSION
- PROJECT_DOCS/ROADMAP_MASTER_PLAN.md (Phase 2B abgehakt)

## Nächste Schritte
- **AP2 Phase 2C — Punch In/Out**: Region im Arranger, Crossfade
- **AP2 Phase 2D — Comping / Take-Lanes**: Loop-Recording, Comp-Tool
- Optional: PDC Auto-Read aus Plugin FX-Chains

## Offene Fragen an den Auftraggeber
- Soll PDC automatisch aus FX-Chain Plugins gelesen werden? (benötigt Plugin-API Extension)
- Priorisierung: Phase 2C (Punch) oder Phase 2D (Comping) als nächstes?
