# Changelog v0.0.20.164 — Consolidate/Bounce: Audio (Arranger + Clip Editor)

## Neu

### Arranger: Ctrl+J für Audio-Clips
- Audio-Clips können jetzt wie MIDI zu **einem** durchgehenden Clip-Block konsolidiert werden.
- Technisch: Offline-Bounce → neue WAV in `media/` + neuer Audio-Clip, Originale werden gelöscht.
- Grid-Snap: nutzt aktuelles Arranger-Grid (wenn verfügbar).
- Anti-Fade-Schutz: interne Clip-Fades werden beim Render ignoriert, damit keine ungewollten Fades „eingebacken“ werden.

### Clip-Arranger / Audio Editor: Consolidate/Ctrl+J für AudioEvents
- Consolidate erzeugt jetzt einen **durchgehenden Audio-Block** (Bounce).
- Ergebnis: neuer Audio-Clip mit **1 AudioEvent** (Start 0, Länge = Auswahl), neue WAV in `media/`.
- Baked: clip gain/pan + pitch/stretch (varispeed preview quality) + per-event reverse.
- Safe: Source-Clip bleibt erhalten; Clip-Launcher Slots können automatisch auf den neuen Clip umgebogen werden.
- Zusatz: **Shift+Ctrl+J** bleibt als non-destructive „Join to new Clip“ (Events bleiben separat).

## Geändert
- `pydaw/services/project_service.py`
- `pydaw/ui/arranger_keyboard.py`
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
