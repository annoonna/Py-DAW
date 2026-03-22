# Session Log: v0.0.20.133 — Audio Editor Pro Upgrade (Bitwig/Ableton Parity)

**Date:** 2026-02-27
**Assignee:** Claude Opus 4.6 (Anthropic)
**Task:** Audio Editor komplett Bitwig/Ableton-fertig machen

## Zusammenfassung

Komplettes Upgrade des Audio-Editors auf professionelles DAW-Niveau.
Alle Änderungen sind **nicht-destruktiv** und **rückwärtskompatibel** (neue Felder defaulten auf 0.0).

## Änderungen

### 1. Model (pydaw/model/project.py)
- **+2 Felder** auf Clip-Dataclass:
  - `fade_in_beats: float = 0.0` — Fade-In Länge in Beats
  - `fade_out_beats: float = 0.0` — Fade-Out Länge in Beats
- Version: 0.0.20.132 → 0.0.20.133

### 2. ProjectService (pydaw/services/project_service.py)
- **`update_audio_clip_params()`**: +2 neue Parameter (`fade_in_beats`, `fade_out_beats`)
- **NEU `normalize_audio_clip(clip_id)`**: Echte Peak-Analyse mit soundfile/numpy, berechnet optimalen Gain für 0 dBFS
- **NEU `detect_onsets(clip_id)`**: Energiebasierte Transient-Erkennung (10ms Hop, adaptive Schwelle, 50ms Mindestabstand)
- **NEU `add_onset_at(clip_id, at_beats)`**: Einzelnen Onset-Marker setzen
- **NEU `clear_onsets(clip_id)`**: Alle Onset-Marker löschen
- **NEU `find_zero_crossings(clip_id, near_beats)`**: Nächste Nulldurchgänge für Click-freie Schnitte finden
- **NEU `slice_at_onsets(clip_id)`**: Audio-Events an allen erkannten Onsets splitten

### 3. AudioEventEditor (pydaw/ui/audio_editor/audio_event_editor.py)
**+464 Zeilen** (1675 → 2139)

#### Neue visuelle Features:
- **Fade-Overlays**: Dreieckige dunkle Overlays für Fade In (links, orange) und Fade Out (rechts, blau)
- **Fade-Handles**: Ziehbare Dreiecke an Fade-Grenzen (Bitwig-Style), Live-Update beim Ziehen
- **Reverse Waveform**: Gespiegelte Audio-Darstellung wenn `clip.reversed=True`, plus oranger Tint
- **Mute Overlay**: Halbtransparentes schwarzes Overlay + "MUTED" Label wenn `clip.muted=True`

#### Erweitertes Kontextmenü:
- **Fades Untermenü**: Fade In/Out Presets (1/16, 1/8, 1/4, 1 Bar), Clear Fades
- **Gain Untermenü**: +3/-3/+6/-6 dB, Reset (0 dB)
- **Transpose Untermenü**: +1/-1 Semitone, +12/-12 (Oktave)
- **Onsets Untermenü**: Auto-Detect, Add at Playhead, Slice at Onsets, Clear
- **Snap to Zero-Crossing** Aktion

#### Verbesserte Aktionen:
- **Normalize**: Echte Peak-Analyse statt einfacher gain=1.0
- **Auto-Detect Onsets**: Energiebasierte Transient-Erkennung, automatische Onset-Anzeige
- **Slice at Onsets**: Events an allen Onsets aufteilen

## Erhaltene Funktionalität ✅
- Arrow/Knife/Eraser/Time Tools: Unverändert
- Audio Events (non-destructive): Unverändert
- Loop Region: Unverändert
- Group Drag/Move: Unverändert
- Split/Consolidate/Quantize: Unverändert
- Param Controls (Gain/Pan/Pitch/Formant/Stretch): Unverändert
- Projektmodell-Kompatibilität: Rückwärtskompatibel

## Dateien geändert
- `pydaw/model/project.py`: +2 Felder, Version-Bump
- `pydaw/services/project_service.py`: +2 Params, +6 neue Methoden (~200 Zeilen)
- `pydaw/ui/audio_editor/audio_event_editor.py`: +464 Zeilen (Overlays, Handles, Menü, Aktionen)
- `pydaw/version.py`: 0.0.20.132 → 0.0.20.133
- `VERSION`: 0.0.20.132 → 0.0.20.133

## Backup
- `pydaw/ui/audio_editor/audio_event_editor.py.bak`: Original v0.0.20.132

## Nächste Schritte für Kollegen
- [ ] Runtime-Testing aller neuen Features
- [ ] Fade-Rendering in Audio Engine (Fade-Kurven beim Playback anwenden)
- [ ] Comping Implementation (Phase 4)
- [ ] Undo/Redo für Fade/Onset/Trim Operationen
- [ ] Keyboard Shortcuts für häufige Aktionen
