# CHANGELOG v0.0.20.708 — Rust Sample Sync (RA2)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust Audio Pipeline, Phase RA2

## Was wurde gemacht

### RA2 — Sample Data Transfer (Python → Rust)
- `pydaw/services/rust_sample_sync.py` (**NEU**):
  - RustSampleSyncer: Scannt Projekt-Clips, lädt WAV/FLAC/OGG, sendet Base64
  - _load_audio_file(): soundfile → scipy.io.wavfile Fallback
  - Chunked Transfer: _send_chunked() für Dateien >50 MB
  - Change-Detection: _file_hash() (path+mtime+size), _sent_hashes Cache
  - sync_clip(): Einzelclip senden
  - SetArrangement: Clip-Platzierungen (track_index, start/end_beat, gain)
- RustProjectSyncer.on_play() synct jetzt automatisch: Project + Samples + Play

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/rust_sample_sync.py | **NEU** |
| pydaw/services/rust_project_sync.py | Sample-Sync Lazy-Init + on_play Integration |
| VERSION | 0.0.20.708 |
| pydaw/version.py | 0.0.20.708 |
