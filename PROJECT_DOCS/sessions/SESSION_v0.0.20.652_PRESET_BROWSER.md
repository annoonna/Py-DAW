# Session Log — v0.0.20.652

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** AP4, Phase 4B + 4C
**Aufgabe:** Preset-Browser + Plugin-State Management

## Was wurde erledigt

### AP4 Phase 4B — Preset-Browser (5/5 Tasks ✅)
- **PresetBrowserService** (neues Modul `pydaw/services/preset_browser_service.py`):
  - Unified Backend für VST3/CLAP/LV2/Built-in Presets
  - User-Presets: `~/.config/ChronoScaleStudio/presets/<safe_plugin_id>/`
  - Factory-Preset-Scan: rekursiv in `~/.vst3/presets/`, `/usr/share/vst3/presets/`, Bundle-interne Presets
  - Save/Load/Delete/Rename mit sicheren Dateinamen
  - Kategorie-System: All / Factory / User / Favorites
  - Favorites als JSON persistiert (`preset_favorites.json`)
  - A/B Vergleich: Zwei Slots (A/B) mit State-Blob + Param-Dict Snapshots
  - Filter-API: Suche nach Name + Tags, Kategorie-Filter
- **PresetBrowserWidget** (neues Modul `pydaw/ui/preset_browser_widget.py`):
  - Kompaktes QWidget (2 Zeilen): Kategorie-Combo | Preset-Combo | ◀▶ | ⭐ | A/B
  - Zweite Zeile: Suchfeld | 💾 Save | ⋯ Menü | ↩ Undo | ↪ Redo
  - Prev/Next-Navigation für schnelles Durchschalten
  - Favorit-Toggle mit visueller Anzeige (⭐/☆)
  - A/B-Button mit farbkodiertem State (grün=A, rot=B)
  - Kontextmenü: Löschen, Umbenennen, Ordner öffnen, Aktualisieren
  - Vollständig callback-basiert (get_state, set_state, get_params, set_params)
- **VST3-Integration** in `Vst3AudioFxWidget`:
  - PresetBrowserWidget zwischen State-Hint und Parametersuche eingebaut
  - Callbacks: `_get_state_b64_for_preset()`, `_set_state_b64_from_preset()`, `_get_current_param_values()`
  - Automatischer Undo-Push vor Preset-Wechsel
  - Slider-Sync nach Preset-Laden (via `_sync_from_rt_once()`)

### AP4 Phase 4C — Plugin-State Management (4/4 Tasks ✅)
- **PluginStateManager** (in `preset_browser_service.py`):
  - Undo/Redo-Stack pro Device-Instanz (max 30 Einträge)
  - Snapshots: Base64-Blob + Parameter-Dict + Beschreibung + Timestamp
  - Auto-Save-Interval (5s) — `should_auto_save()` / `mark_auto_saved()`
  - `push_undo()` / `undo()` / `redo()` / `can_undo()` / `can_redo()`
  - `clear_device()` für Cleanup
- Undo/Redo-Buttons im PresetBrowserWidget mit Auto-Refresh (1s Timer)
- `_flush_to_project()` ruft `notify_param_changed()` auf für automatische Undo-Snapshots
- Bestehende State-Embedding-Logik (`embed_project_state_blobs`) unverändert aktiv

## Geänderte Dateien
- `pydaw/services/preset_browser_service.py` — **NEU** (PresetBrowserService + PluginStateManager)
- `pydaw/ui/preset_browser_widget.py` — **NEU** (PresetBrowserWidget)
- `pydaw/ui/fx_device_widgets.py` — PresetBrowserWidget in Vst3AudioFxWidget, Preset-Callbacks, Undo-Notify
- `VERSION` — 0.0.20.652
- `pydaw/version.py` — 0.0.20.652
- `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` — Phase 4B+4C abgehakt
- `PROJECT_DOCS/progress/TODO.md` — v652 Eintrag
- `PROJECT_DOCS/progress/DONE.md` — v652 Eintrag
- `CHANGELOG_v0.0.20.652_PRESET_BROWSER_STATE_MGMT.md` — Changelog

## Nächste Schritte
- **AP7 Phase 7A — Advanced Sampler**: Multi-Sample Mapping Editor, Round-Robin, Sample-Start/End/Loop, Filter + ADSR, Mod-Matrix, Auto-Mapping
- **AP10 Phase 10C — DAWproject Roundtrip**: Vollständiger Export/Import, Plugin-Mapping
- **AP1 Phase 1C — Rust Plugin-Hosting**: VST3/CLAP in Rust (benötigt Rust-Compiler auf Zielsystem)

## Offene Fragen an den Auftraggeber
- Soll das PresetBrowserWidget auch in das CLAP-Widget integriert werden (zusätzlich zum bestehenden Preset-System), oder soll CLAP sein eigenes Preset-UI behalten?
- Soll der Factory-Preset-Scan auch CLAP-Standard-Pfade und LV2-Presets (via lilv) einbeziehen?
