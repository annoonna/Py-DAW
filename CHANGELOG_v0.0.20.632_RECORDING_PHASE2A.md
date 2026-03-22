# CHANGELOG v0.0.20.632 — Audio Recording Phase 2A (Single-Track Recording)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP 2 (Audio Recording), Phase 2A

## Was wurde gemacht

### RecordingService Rewrite (`pydaw/services/recording_service.py`)
- **Backend Auto-Detection**: JACK > PipeWire > sounddevice (Fallback)
- **Record-Arm Management**: `arm_track()`, `disarm_track()` mit Input-Pair
- **Pre-Roll / Count-In**: `set_count_in_bars()`, `finish_count_in()` — Frames während Count-In werden verworfen
- **Project-Ordner WAV-Schreibung**: `set_project_media_path()` → `project/media/recordings/rec_TRACKNAME_TIMESTAMP.wav`
- **24-Bit WAV Support**: `set_bit_depth(24)` — 16/24/32-bit konfigurierbar
- **Auto Clip-Erstellung**: `set_on_recording_complete(callback)` — Callback wird nach Stop mit (wav_path, track_id, start_beat) aufgerufen
- **Input Monitoring**: `set_input_monitoring()`, `get_input_level()` für VU-Meter
- **JACK Input-Pair Routing**: Stereo-Pair Offset bei Auto-Connect
- **Sauberes Cleanup**: `_stop_streams()` schließt alle aktiven Backends

### Mixer Record-Arm Button (`pydaw/ui/mixer.py`)
- **"R" Button** im Channel Strip (neben M/S) — rot wenn armed
- **Visual Feedback**: `border-left: 3px solid #e33` auf dem Strip
- **Model-Sync**: `refresh_from_model()` liest `track.record_arm`
- **Handler**: `_on_rec_arm()` setzt `track.record_arm` direkt

### MainWindow Recording Modernisierung (`pydaw/ui/main_window.py`)
- **Neuer `_on_record_toggled()`**: Nutzt RecordingService statt direkt JACK
- **`_on_record_toggled_legacy()`**: Alter JACK-only Code als Fallback erhalten
- **Auto Clip-Import**: `add_audio_clip_from_file_at()` Callback
- **Backend-Anzeige**: StatusBar zeigt welches Backend benutzt wird

### Rust Engine Fixes
- **SetMasterParam**: Korrekter Handler (war Placeholder)
- **AudioGraph.master_index()**: Getter hinzugefügt

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw/services/recording_service.py` | REWRITE: Vollständiger AP2 Phase 2A Service |
| `pydaw/ui/mixer.py` | Record-Arm "R" Button + Handler |
| `pydaw/ui/main_window.py` | RecordingService Integration + Legacy Fallback |
| `pydaw_engine/src/engine.rs` | SetMasterParam Fix |
| `pydaw_engine/src/audio_graph.rs` | master_index() Getter |
| `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` | Phase 2A abgehakt |
| `VERSION` | 0.0.20.631 → 0.0.20.632 |

## Was als nächstes zu tun ist
- **AP2 Phase 2B — Multi-Track Recording**: Mehrere Tracks gleichzeitig, PDC
- **AP2 Phase 2C — Punch In/Out**: Region im Arranger, Crossfade
- **AP5 — Mixer/Routing**: Send/Return, Sidechain
