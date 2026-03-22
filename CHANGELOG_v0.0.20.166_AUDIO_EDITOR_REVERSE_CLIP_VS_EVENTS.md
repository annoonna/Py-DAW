# Changelog v0.0.20.166 — Audio Editor Reverse: Clip vs Events

## ✨ Feature / Fix

- **Audio Editor Kontextmenü:** Reverse ist jetzt **klar getrennt**:
  - **Reverse** = **Clip-Level Reverse** (`clip.reversed`) (checkable)
    - wirkt auf Playback + Editor Visual + **Arranger Visual**
  - **Reverse (Events)** = **Per-Event Reverse** (nur selektierte AudioEvents)
    - Workflow: z.B. 3 von 9 Hits reverse, ohne die anderen zu beeinflussen

## Dateien
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
