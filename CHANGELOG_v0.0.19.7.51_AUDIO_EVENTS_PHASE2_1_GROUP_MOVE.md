# v0.0.19.7.51 – Audio Events (Phase 2.1)

## Fokus: Pro-DAW-Style Audio-Event-Blöcke (Selection + Group-Move)

### Neu
- AudioEventEditor: **AudioEvents werden als selektierbare Blöcke** dargestellt (QGraphicsRectItem).
- **Group-Move (Multi-Selection):** Ziehen eines Blocks verschiebt **alle selektierten** Events gemeinsam.
  - **Shift gedrückt halten** deaktiviert Snap beim Drag.
  - Clamping: Events können nicht über 0..Clip-Länge hinaus geschoben werden.
- Middle-Mouse-Pan im Editor (wie in vielen DAWs): Scrollen/Drag ohne Tool-Wechsel.

### Kontext-Menü (Editor)
- **Consolidate**: Selektierte Events werden zusammengeführt, **wenn** sie zeitlich *und* im Source-Offset lückenlos aneinander liegen.
- **Quantize (Events)**: Quantisiert Start-Positionen der selektierten Events auf das Projekt-Snap-Raster.

### Service/Model
- ProjectService:
  - `move_audio_events(clip_id, event_ids, delta_beats)`
  - `quantize_audio_events(clip_id, event_ids, division=None)`
  - `consolidate_audio_events(clip_id, event_ids)`

### Fixes
- Stabilisierung des AudioEventEditor: Event-Render/Selection/Drag ist vollständig signal-safe.

### Dateien
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/services/project_service.py`
- `pydaw/model/project.py` (Version-Bump)
- `pydaw/version.py`
- `VERSION`
