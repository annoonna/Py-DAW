# CHANGELOG v0.0.20.642 — Stretch-Modi + Warp-Marker Komplett (AP3 Phase 3A+3B)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP3 Phase 3B — Stretch-Modi (aufbauend auf v641: AP5 5B+5C + AP3 3A)

## Was wurde gemacht

### AP3 Phase 3B — Stretch-Modi: KOMPLETT ✅ (5/5 Tasks)

1. **Tones Mode** (default): Phase Vocoder + Essentia Fallback — existierte bereits
2. **Beats Mode**: `_beats_stretch_mono()` — Slice-basiert an Onsets, Crossfade, Repositionierung
3. **Texture Mode**: `_texture_stretch_mono()` — Granular OLA mit Hanning-Grains + Jitter
4. **Re-Pitch Mode**: `_repitch_mono()` — Lineare Interpolation (Varispeed, ändert Pitch!)
5. **Complex Mode**: `_complex_stretch_mono()` — PV mit 4096-FFT / 256-Hop (höchste Qualität)

### Dispatch-API
- `time_stretch_mono_mode(x, rate, mode, sr, onsets)` — Mono-Dispatch
- `time_stretch_stereo_mode(data, rate, mode, sr, onsets)` — Stereo-Dispatch
- `STRETCH_MODES` Konstante: ("tones", "beats", "texture", "repitch", "complex")

### Clip-Model
- `Clip.stretch_mode` (str, default "tones") — Stretch-Algorithmus pro Clip

### Arrangement Renderer Integration
- Beide Stretch-Call-Sites (Audio + MIDI) nutzen jetzt `time_stretch_stereo_mode`
- Fallback auf `time_stretch_stereo` wenn Mode = "tones"

### Audio Editor UI
- Stretch Mode ComboBox: Tones / Beats / Texture / Re-Pitch / Complex
- Tooltip mit Beschreibung jedes Modus
- Sync bei Clip-Load, Handler setzt clip.stretch_mode

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/model/project.py | Clip.stretch_mode |
| pydaw/audio/time_stretch.py | 5 Stretch-Algorithmen + Dispatch-API |
| pydaw/audio/arrangement_renderer.py | Import + Nutzung von time_stretch_stereo_mode |
| pydaw/ui/audio_editor/audio_event_editor.py | Mode ComboBox + Handler + Sync |
| pydaw/version.py, VERSION | 0.0.20.642 |

## Was als nächstes zu tun ist
- AP3 Phase 3C Tasks 3-4 (Tempo-Automation, Arranger-Warp)
- AP4 Phase 4A — Sandboxed Plugin-Hosting
- AP8 Phase 8A — Essential FX

## Bekannte Probleme
- Beats Mode Auto-Onset ist einfach (Energie-basiert). Qualität verbessert sich mit Essentia-Onsets.
- Texture Mode Jitter ist deterministic (seed=42) für Reproduzierbarkeit.
