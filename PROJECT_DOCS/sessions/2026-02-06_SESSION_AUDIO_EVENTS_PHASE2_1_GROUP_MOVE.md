# Session Log — 2026-02-06 — v0.0.19.7.51

## Ziel
Phase 2.1 des Audio Clip Editors:
- AudioEvents als interaktive Blöcke im Editor
- Multi-Selection + Group-Move (Pro-DAW-Style)
- Context Menu Aktionen (Quantize/Consolidate) scharf schalten

## Umsetzung
### AudioEventEditor (UI)
- Event-Rendering als `EventBlockItem` (QGraphicsRectItem), selektierbar.
- Group-Drag:
  - Drag startet auf einem Block (Arrow-Tool).
  - Alle selektierten Events bewegen sich gemeinsam.
  - Snap auf Projekt-Raster; **Shift hält Snap aus**.
  - Clamping an Clip-Start/-Ende.
- Pan: Middle-Mouse Drag.

### ProjectService (Logik)
- `move_audio_events(...)` verschiebt Events gruppiert und clamped.
- `quantize_audio_events(...)` quantisiert Event-Starts auf `snap_division`.
- `consolidate_audio_events(...)` merged nur contiguous + source-aligned.

## Dateien
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/services/project_service.py`
- `pydaw/version.py`, `pydaw/model/project.py`, `VERSION`

## Hinweise / Nächste Schritte
- Phase 2.2 (optional): Collision Handling (Overlaps vermeiden) + Slip-Editing.
- Reverse: aktuell TODO (Flag + non-destructive Render Pipeline).
