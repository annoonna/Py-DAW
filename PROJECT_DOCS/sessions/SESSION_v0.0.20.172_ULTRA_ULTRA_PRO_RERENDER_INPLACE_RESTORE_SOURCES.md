# Session: v0.0.20.172 — Ultra-Ultra-Pro: Re-render IN PLACE + Restore Sources (Non-Destructive)

## Ziel
- **Re-render in place**: konsolidierte Clips anhand `render_meta` neu rendern, aber **Clip-ID bleibt gleich** (Arranger-Placement + Clip-Launcher Slots bleiben stabil).
- **Restore Sources (in place)**: Original-Events/Source-File in den Clip zurückholen, ebenfalls **ohne Clip-ID-Wechsel**.
- Alles **safe**: bestehende Ctrl+J Workflows unverändert.

## Implementiert
### 1) ProjectService: `rerender_clip_in_place_from_meta()`
- Rendert über vorhandenes `render_meta` (source_clip_id + event_ids + flags).
- Erzeugt intern einen TEMP-Clip via `bounce_consolidate_audio_events_to_new_clip(..., select_new_clip=False)`.
- Swapped nur Content-Felder (source_path/media_id/offset/length/audio_events) in den bestehenden Clip.
- TEMP-Clip wird aus `project.clips` entfernt (Audiofile bleibt im media/ dir → non-destructive).
- `render_meta.badges += ["RERENDER_INPLACE"]`, `active_state="rendered"`.

### 2) ProjectService: `restore_sources_in_place_from_meta()`
- Stellt `clip.source_path` auf Source zurück und rekonstruiert `audio_events` aus `render_meta.sources.events`.
- Start-Positions werden **relativ zu `base_start_beats`** zurückgerechnet → Timing stimmt.
- Speichert den aktuellen gerenderten Zustand (falls noch nicht vorhanden) in `render_meta["rendered_state"]`.
- `render_meta.badges += ["RESTORED"]`, `active_state="sources"`.

### 3) UI
- **AudioEventEditor Kontextmenü** (bei render_meta):
  - Re-render (from sources)
  - **Re-render (in place)**
  - **Restore Sources (in place)**
  - Back to Sources
- **Arranger Canvas Kontextmenü**: gleiche Ultra-Pro Einträge.
- Zusätzlich: Arranger Canvas hatte zuvor Ultra-Pro Actions im Menü, aber ohne Handler → jetzt korrekt verdrahtet.

## Safety / Nicht kaputt
- Ctrl+J Default (bar-anchored) bleibt unverändert.
- Keine destruktiven Deletes von Source-Clips oder Audiofiles.
- Clip-ID bleibt stabil bei in-place Varianten → keine Slot/Placement-Regressions.

## Geänderte Dateien
- `pydaw/services/project_service.py`
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/ui/arranger_canvas.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`

