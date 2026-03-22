# Session Log — 2026-02-06 — v0.0.19.7.49

## Ziel
Clip-Launcher (Pro-DAW-Style):
- Doppelklick auf Slot öffnet einen Editor:
  - MIDI → Piano Roll / Notation
  - Audio → neuer AudioEventEditor

## Architektur (Low-Risk / Modular)
- **Single Source of Truth**: Project-Model `Clip` (Dataclass) in `pydaw/model/project.py`
- UI (Launcher + Editor) aktualisiert sich ausschließlich über `ProjectService.project_updated`
- Editor kennt den Launcher nicht; Kommunikation nur über Clip-ID + ProjectService (loose coupling)

## Änderungen (Kurz)
### UI
- `pydaw/ui/clip_launcher.py`
  - `clip_edit_requested(clip_id)` Signal
  - `SlotWaveButton.mouseDoubleClickEvent` emittiert Signal

- `pydaw/ui/main_window.py`
  - `_on_clip_edit_requested(clip_id)` öffnet passenden Editor im Editor-Dock

- `pydaw/ui/editor_tabs.py`
  - Tab **Audio** hinzugefügt, integriert `AudioEventEditor`

### AudioEventEditor (neu)
- `pydaw/ui/audio_editor/audio_event_editor.py`
  - Toolbar + Tool-Switch (Arrow/Knife/Eraser/Time)
  - Beat/Grid im Hintergrund (QGraphicsScene.drawBackground)
  - Waveform (best-effort) als QGraphicsPathItem (downsampled)
  - Loop-Overlay mit zwei draggable Edges → schreibt `loop_start_beats/loop_end_beats`
  - Knife Tool → schreibt Slice-Marker in `audio_slices`
  - Context-Menü (Stub) vorbereitet

### Model / Service
- `pydaw/model/project.py`
  - `Clip` erweitert um Audio-Parameter + Loop + Slices

- `pydaw/services/project_service.py`
  - API für Audio-Editor: update params / loop / slices

## Quick Test
1) Projekt starten
2) Clip in Clip-Launcher Slot ziehen (Audio)
3) **Doppelklick** auf Slot → Editor Dock → Tab **Audio**
4) Knife Tool auswählen → Klick in Waveform → Slice-Line erscheint
5) Loop: Tool "Time" auswählen → Drag im Editor → Loop-Region erscheint

## Nächste Schritte (Phase 2)
- Loop/Slices in Launcher-Playback nutzen (LauncherService → AudioEngine Pull Sources)
- Split at Playhead (Context) wirklich umsetzen (Slice-Marker am Transport-Beat)
- Eraser Tool: Slice entfernen (nearest)
- Gain/Pan/Pitch UI-Controls (Regler) → ProjectService.update_audio_clip_params

