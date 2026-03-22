# Changelog v0.0.20.157 — Clip Launcher Slot UX + Audio Editor Loop-Tiling

**Datum:** 2026-02-28

## Clip Launcher (Bitwig/Ableton UX)

- **Single-Click auf Slot:** jetzt *nur* Auswahl + Editor-Fokus (kein Auto-Launch/Transport-Start).
- **In-Slot ▶-Button (Hotzone oben rechts):** startet Launch des Clips.
- **Safety:** ▶-Klick unterdrückt das normale QPushButton.clicked, um Doppelaktionen zu verhindern.

## Audio Editor

- **Waveform-Background tiled jetzt die Clip-Loop-Region** (loop_start_beats / loop_end_beats) über die Clip-Länge.
  Dadurch sieht man bei kurzen Samples die Wiederholung wie in Bitwig/Ableton.

## Geänderte Dateien

- `pydaw/ui/clip_launcher.py`
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
