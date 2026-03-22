# CHANGELOG v0.0.20.638 — Punch Crossfade + Pre-Roll Auto-Seek

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2C — Punch In/Out (Abschluss)

## Was wurde gemacht

### 1. AudioConfig Singleton (pydaw/core/audio_config.py) — NEU
- Neue Klasse `AudioConfig` als zentrale Audio-Konfiguration
- `punch_crossfade_ms`: Konfigurierbar 0–100ms, Default 10ms
- `set_punch_crossfade_ms()`: Setter mit Clamping
- `crossfade_samples(sample_rate)`: Konvertierung ms → Samples
- Module-Level Singleton `audio_config` für direkten Import
- Vorbereitet für späteres Preferences-UI

### 2. Punch Crossfade in RecordingService
- `_apply_punch_crossfade(audio_data)`: Linearer Fade-In am Start + Fade-Out am Ende
- Liest Crossfade-Länge aus `AudioConfig` (Fallback: 10ms hardcoded)
- Stereo-aware: Broadcast über Kanäle via numpy newaxis
- Sicherheit: Wenn Audio kürzer als 2× fade_samples → halbe Fade-Länge
- Aufgerufen in `_save_wav_for_track()` nur wenn `_punch_enabled`

### 3. Pre-Roll Auto-Seek (Pro Tools/Logic Standard)
- Bei Record + Punch: Playhead wird automatisch auf `punch_in - pre_roll` geseekt
- Nutzt `TransportService.get_punch_play_start_beat()` für korrekte Beat-Berechnung
- Seek passiert vor `start_recording()`, damit Pre-Roll-Audio korrekt gestreamt wird

### 4. SettingsKeys + Container Wiring
- Neuer Key `audio/punch_crossfade_ms` in SettingsKeys
- ServiceContainer: Lädt gespeicherten Crossfade-Wert beim Start
- Bereit für Preferences-Dialog: `set_value(keys.punch_crossfade_ms, wert)` → persistent

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/core/audio_config.py | **NEU** — AudioConfig Singleton |
| pydaw/core/settings.py | Neuer Key `punch_crossfade_ms` |
| pydaw/services/recording_service.py | `_apply_punch_crossfade()`, Aufruf in `_save_wav_for_track()` |
| pydaw/ui/main_window.py | Pre-Roll Auto-Seek vor Record-Start |
| pydaw/services/container.py | AudioConfig aus Settings laden |
| pydaw/version.py | → 0.0.20.638 |
| VERSION | → 0.0.20.638 |

## AP2 Phase 2C — KOMPLETT ✅
Alle 4 Tasks abgeschlossen:
1. ✅ Punch-Region im Arranger (v0.0.20.637)
2. ✅ Automatisches Punch In/Out (v0.0.20.637)
3. ✅ Pre-/Post-Roll Einstellungen (v0.0.20.637 + Auto-Seek v0.0.20.638)
4. ✅ Crossfade an Punch-Grenzen (v0.0.20.638)

## Was als nächstes zu tun ist
- **AP2 Phase 2D — Comping / Take-Lanes**: Loop-Recording, Take-Lanes, Comp-Tool, Flatten
