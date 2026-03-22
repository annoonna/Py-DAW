# Session Log — 2026-02-02

**Version:** v0.0.19.5.1.14
**Topic:** Performance / MIDI Pre-Render Optionen + Scope-Pre-Render

## Ziel
Das "Ready for Bach" Pre-Render soll **konfigurierbar** sein, damit der Workflow stabil bleibt:
- Auto-Pre-Render nach Projekt-Load **an/aus**
- Optionaler Fortschritt bei Auto-Load
- Beim Play: optional **warten bis Pre-Render fertig** (mit/ohne Dialog)
- Zusätzlich: Pre-Render nur für **Auswahl** (Clips) oder **Track**.

## Umsetzung
### 1) Audio-Einstellungen erweitert
Neuer Block: **"Performance (MIDI Pre-Render)"**
- [x] Auto-Pre-Render nach Projekt laden
- [x] Fortschritt beim Auto-Pre-Render anzeigen
- [x] Vor Play auf Pre-Render warten
- [x] Fortschritt vor Play anzeigen

### 2) Scope-Pre-Render
Im Audio-Menü:
- [x] Pre-Render: ausgewählte Clips
- [x] Pre-Render: ausgewählter Track

Intern:
- ProjectService Pre-Render akzeptiert jetzt Filter: `clip_ids` / `track_id`.

### 3) Play-Workflow
Wenn **"Vor Play auf Pre-Render warten"** aktiv ist:
- Play startet **erst nach** abgeschlossenem Pre-Render.
- Dialog optional (wenn deaktiviert: Statusbar-Meldung).

## Geänderte Dateien
- `pydaw/core/settings.py`
- `pydaw/ui/audio_settings_dialog.py`
- `pydaw/ui/actions.py`
- `pydaw/ui/main_window.py`
- `pydaw/services/project_service.py`

## Manual Tests
1) **Audio → Audio-Einstellungen → Performance (MIDI Pre-Render)**
   - Haken setzen/entfernen, OK, neu starten → Settings bleiben.
2) Projekt laden:
   - Auto-Load aktiv: Pre-Render startet (silent oder mit Dialog, je nach Option).
3) Play:
   - Wait-before-Play aktiv: Pre-Render läuft, danach Play.
4) Arranger: Clips markieren → **Audio → Pre-Render: ausgewählte Clips**
5) Track wählen → **Audio → Pre-Render: ausgewählter Track**

