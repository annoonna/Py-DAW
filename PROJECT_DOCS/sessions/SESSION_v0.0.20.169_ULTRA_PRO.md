# SESSION v0.0.20.169 — Ultra-Pro + Consolidate Fix

Datum: 2026-03-01

## Kontext
User-Report: Im Clip-Arranger Audio-Editor funktionierte "Consolidate" (Ctrl+J / Kontextmenü) nach den Pro-Erweiterungen nicht mehr zuverlässig.

## Änderungen
1) **Bounce erlaubt Single-Selection** (wie in DAWs üblich)
- `bounce_consolidate_audio_events_to_new_clip()` akzeptiert nun >=1 Event statt >=2.

2) **Ultra-Pro: Render-History nutzbar**
- `rerender_clip_from_meta()` erzeugt einen neu gerenderten Clip anhand der gespeicherten `render_meta` (mode/handles/tail/normalize) und ersetzt optional Launcher-Slots, die auf den alten Clip zeigen.
- `back_to_sources_from_meta()` springt zum Source-Clip und triggert eine one-shot Selektion der ursprünglichen Events.

3) **UI Integration**
- Audio-Editor Kontextmenü zeigt Ultra-Pro Actions nur, wenn Meta vorhanden ist.
- Arranger Kontextmenü zeigt Ultra-Pro Actions ebenfalls.

## Testplan
- Clip-Editor: Multi-Event Auswahl → Ctrl+J (bar-anchored) funktioniert.
- Clip-Editor: **1 Event auswählen** → Ctrl+J erzeugt konsolidierten Clip.
- Auf einem konsolidierten Clip: Kontextmenü → **Re-render (from sources)** → neuer Clip entsteht, Launcher-Slot wird ersetzt.
- Kontextmenü → **Back to Sources** → Source-Clip öffnet sich, Events sind selektiert.
