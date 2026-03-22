# Session Log — Knife: Snap + Selection-Regeln

**Date:** 2026-02-06  
**Version bump:** v0.0.19.7.52 → v0.0.19.7.53  
**Scope:** Audio Clip Editor (AudioEventEditor)

## Ziel
User-Request: **"Knife: Snap + Selection-Regeln rein"**

- Knife soll **auf Grid snappen** (Pro-DAW-like)
- Knife soll **Selection-Regeln** beachten:
  - Wenn selektierte Events existieren und den Cut-Punkt enthalten → **nur selektierte** Events schneiden
  - Sonst → **Event unter Cursor/Playhead** schneiden

## Änderungen
### UI / Interaktion
- `AudioEditorView`:
  - Snap-to-grid im Knife-Tool implementiert
  - **Shift** deaktiviert Snap (freies Schneiden)
  - Snap-Quantum kommt vom Projekt (Snap-Division)

### Daten/Service
- `ProjectService`:
  - neue API `split_audio_events_at(clip_id, at_beats, event_ids=None)`
    - `event_ids=None`: legacy Verhalten (erstes Event, das `at_beats` enthält)
    - `event_ids=[...]`: splitte **alle** selektierten Events, die `at_beats` enthalten
    - Rückgabe: Liste der neuen Event-IDs (für Selection-Update)
  - `split_audio_event()` bleibt als Wrapper erhalten (Backward compatible)

### Editor-Controller
- `AudioEventEditor`:
  - `_knife_target_event_ids(...)` implementiert (Selection-Regeln)
  - Bei Split: Auto-Refresh unterdrückt, danach Refresh mit neuer Selection
  - Kontext-Menü **Split at Playhead** nutzt dieselben Regeln

## Files geändert
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/services/project_service.py`
- `VERSION`
- `pydaw/version.py`

## Quick Test Checklist
- [ ] Audio-Clip im Launcher öffnen
- [ ] Knife-Tool wählen
- [ ] Klick → Cut sitzt auf Grid
- [ ] Shift+Klick → Cut ohne Snap
- [ ] Event selektieren, Cut innerhalb → nur dieses Event wird geschnitten
- [ ] Selection vorhanden, Cut außerhalb → Event unter Cursor wird geschnitten
- [ ] Context Menu: Split at Playhead → gleiche Regeln

