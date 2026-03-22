# SESSION v0.0.20.176 (2026-03-01)

## Ziel
Phase 1 "Micro-Controls" im Arranger erweitern – **Clip Gain/Pan direkt am Clip** (Cubase/Bitwig-Style), ohne bestehende Workflows zu verändern.

## Was gemacht wurde (safe, nichts kaputt)
- ✅ **Arranger Audio-Clip: Gain-Mini-Handle** (Button "G")
  - Drag **vertikal** = Clip-Gain (dB-mapped, non-destructive)
  - **SHIFT** während Drag = Quick-Pan-Modus (horizontal)
- ✅ **Arranger Audio-Clip: Pan-Mini-Handle** (Button "P")
  - Drag **horizontal** = Clip-Pan
  - **SHIFT** = Fine-Mode (langsamer)
- ✅ **Statusbar Feedback** über `status_message` (Gain dB / Pan L/R %)
- ✅ **Cursor-UX**: Gain = SizeVerCursor, Pan/Fade = SizeHorCursor

## Technisch
- Clip-Parameter werden ausschließlich via `ProjectService.update_audio_clip_params()` gesetzt.
- Änderungen sind rein additiv im UI, keine Shortcut-/Menu-Regression.

## Geänderte Dateien
- `pydaw/ui/arranger_canvas.py`
- `VERSION`, `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`, `DONE.md`, `LATEST.md`
