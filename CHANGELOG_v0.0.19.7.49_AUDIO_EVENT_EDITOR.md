# Changelog — v0.0.19.7.49

## Fokus
Clip Launcher — Doppelklick öffnet dedizierten Editor (Pro-DAW-Workflow):
- MIDI → Piano Roll / Notation
- Audio → neuer **AudioEventEditor**

## Implementiert (MVP / Phase 1)
### Clip Launcher
- `pydaw/ui/clip_launcher.py`
  - `clip_edit_requested(clip_id)` Signal
  - `SlotWaveButton.mouseDoubleClickEvent` emittiert das Signal bei Doppelklick

### MainWindow
- `pydaw/ui/main_window.py`
  - `_on_clip_edit_requested(clip_id)` öffnet den passenden Editor im Editor-Dock

### Editor Dock
- `pydaw/ui/editor_tabs.py`
  - neuer Tab **Audio**
  - Integration `AudioEventEditor`

### AudioEventEditor (neu)
- `pydaw/ui/audio_editor/audio_event_editor.py`
  - Toolbar: Werkzeug (Arrow/Knife/Eraser/Time)
  - Funktions-Buttons (Toggle-Buttons): Audio Events, Comping, Stretch, Onsets, Gain, Pan, Pitch, Formant
  - Zoom: Ctrl+Mausrad (horizontal)
  - Grid: Beat/Bar Hintergrund (QGraphicsScene.drawBackground)
  - Loop-Region: Overlay + zwei draggable Edges (Start/End) → schreibt in Projekt-Modell
  - Knife Tool: Klick setzt **non-destructive Slice-Marker** (beats) → schreibt in Projekt-Modell
  - Context-Menü (Stub): Split at Playhead, Consolidate, Reverse, Quantize, Transpose

### Model / Data
- `pydaw/model/project.py`
  - Clip erweitert um Audio-Parameter: gain/pan/pitch/formant/stretch + loop_start/loop_end + audio_slices + onsets

- `pydaw/services/project_service.py`
  - `update_audio_clip_params(...)`
  - `set_audio_clip_loop(...)`
  - `add_audio_slice(...)`
  - `remove_audio_slice_near(...)`

## Nicht enthalten (kommt als Phase 2)
- echte Engine-Integration: Loop/Slices wirken auf Playback im Launcher/Arrangement
- Comping/Stretch/Onsets echte Algorithmen
- Transpose/Pitch-Menü: echte DSP-Operationen
- Vollständige Pro-DAW-Context-Actions (Consolidate/Reverse non-destructive)

