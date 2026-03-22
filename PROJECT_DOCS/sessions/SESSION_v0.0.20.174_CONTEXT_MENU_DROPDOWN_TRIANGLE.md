# Session: v0.0.20.174 — Kontextmenü-Pro + Clip-Dropdown-Dreieck (Arranger/Editor/Launcher)

## Ziel
1) **Re-render-Einträge** müssen im Kontextmenü **sichtbar** sein:
- Arranger Clip Rechtsklick
- Audio-Editor Rechtsklick
- Clip-Launcher Slot Rechtsklick

2) **Cubase-inspiriertes Mini-Dreieck** am Clip im Arranger:
- kleines ▾ erscheint bei Hover oder Selektion
- Klick öffnet das gleiche Clip-Kontextmenü (ohne Rechtsklick nötig)

## Implementiert (safe)
### 1) Kontextmenü: Render/Restore immer discoverable
- In **Arranger** und **Audio-Editor** werden die Render/Restore Actions jetzt immer angezeigt.
- Wenn der Clip keine `render_meta.sources` hat, werden Restore/Toggle/Rebuild ausgegraut.
- **"Re-render (in place)" bleibt aktiv** und kann jetzt auch bei normalen Audio-Clips den **Initial-Render** auslösen.

### 2) ProjectService: Initial-Render über `rerender_clip_in_place_from_meta()`
- `rerender_clip_in_place_from_meta()` akzeptiert jetzt auch Audio-Clips ohne `render_meta`:
  - leitet `audio_events` ab (voller Clip als 1 Event, falls nötig)
  - rendert non-destructive über den existierenden Bounce-Path
- Wichtig: Beim **allerersten Render** wird `rendered_state` **nicht** aus dem Quellzustand befüllt,
  damit `restore_sources_in_place_from_meta()` später korrekt den tatsächlichen Render-State snapshotten kann.

### 3) Arranger Clip ▾ Dropdown-Button
- `ArrangerCanvas` trackt `_hover_clip_id`
- Im `paintEvent()` wird ein kleiner ▾ Button am Clip (top-right) gezeichnet, bei:
  - Hover **oder**
  - Selektion
- In `mousePressEvent()` wird ein Klick auf den ▾ Button als ContextMenu-Event weitergeleitet → identisches Menü.

## Dateien
- `pydaw/services/project_service.py`
- `pydaw/ui/arranger_canvas.py`
- `pydaw/ui/audio_editor/audio_event_editor.py`
- `pydaw/ui/clip_launcher.py`

## Test-Checkliste
- Arranger: Audio-Clip rechtsklick → „Re-render (in place)“ immer sichtbar.
- Arranger: Clip hover → ▾ erscheint; Klick → Kontextmenü.
- Audio-Editor: rechtsklick → Render/Restore Gruppe sichtbar.
- Clip-Launcher: Slot rechtsklick → Render/Restore Gruppe sichtbar.
- Normaler Audio-Clip (ohne CONSOL): „Re-render (in place)“ → erzeugt Render-State, danach Toggle/Restore nutzbar.

