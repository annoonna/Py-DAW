# CHANGELOG v0.0.20.652 — Preset Browser & Plugin State Management

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP4, Phase 4B + 4C

## Was wurde gemacht

### AP4 Phase 4B — Preset-Browser (komplett)
- **PresetBrowserService** (`pydaw/services/preset_browser_service.py`):
  - Unified Preset-Backend für alle Plugin-Typen (VST3/CLAP/LV2/Built-in)
  - Preset-Scan: User-Presets aus `~/.config/ChronoScaleStudio/presets/<plugin>/`
  - Factory-Preset-Scan: Rekursiv in VST3-Standard-Verzeichnissen
  - Preset Save/Load/Delete/Rename mit sicheren Dateinamen
  - Kategorie-System: All / Factory / User / Favorites
  - Favorites-Persistenz in JSON (`preset_favorites.json`)
  - A/B Vergleich: Zwei Slots mit State-Blob-Snapshots, sofortiger Wechsel
  - Filter/Suche über Name und Tags
- **PresetBrowserWidget** (`pydaw/ui/preset_browser_widget.py`):
  - Kompaktes, wiederverwendbares QWidget für alle Device-Typen
  - Preset-Dropdown mit Kategorie-Filter und Volltextsuche
  - Prev/Next-Navigation (◀ ▶) für schnelles Durchschalten
  - Favorit-Toggle (⭐/☆) pro Preset
  - A/B-Button mit visueller Zustandsanzeige (grün=A, rot=B)
  - Save/Delete/Rename über Menü
  - "Preset-Ordner öffnen" Aktion (xdg-open)
- **VST3-Integration**: PresetBrowserWidget in `Vst3AudioFxWidget._build()` eingebettet
  - `_get_state_b64_for_preset()`: Live-Plugin-State oder Projekt-Fallback
  - `_set_state_b64_from_preset()`: State auf Live-Plugin + Projekt-Daten anwenden
  - `_on_preset_browser_loaded()`: UI-Feedback + Slider-Sync nach Preset-Wechsel
  - Automatische Undo-Push bei Preset-Wechsel (Zustand vorher gesichert)

### AP4 Phase 4C — Plugin-State Management (komplett)
- **PluginStateManager** (in `preset_browser_service.py`):
  - Undo/Redo-Stack pro Device-Instanz (max. 30 Einträge)
  - State-Snapshots als Base64-Blob + Parameter-Dict
  - Auto-Save-Interval (5s) — pushed automatisch bei Parameter-Änderungen
  - `push_undo()` / `undo()` / `redo()` / `can_undo()` / `can_redo()`
  - `clear_device()` für Cleanup bei Device-Entfernung
- **Undo/Redo-Buttons** im PresetBrowserWidget (↩ / ↪)
  - Enabled/Disabled-State wird automatisch per Timer aktualisiert
  - Snapshots werden bei Preset-Wechsel und Parameter-Änderungen gepusht
- **Auto-State auf Projekt-Save**: Bestehendes `embed_project_state_blobs()` bleibt aktiv (VST3 + CLAP)

### Bestehende Funktionalität: NICHT geändert
- CLAP-Widget behält sein eigenes Preset-System (v0.0.20.569 — unverändert)
- Keine Audio-Engine-Änderungen
- Keine Project-Model-Änderungen
- Kein bestehendes Feature gebrochen

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw/services/preset_browser_service.py` | **NEU** — PresetBrowserService + PluginStateManager |
| `pydaw/ui/preset_browser_widget.py` | **NEU** — PresetBrowserWidget (QWidget) |
| `pydaw/ui/fx_device_widgets.py` | PresetBrowserWidget in Vst3AudioFxWidget integriert, Preset-Callbacks + Undo-Notify |
| `VERSION` | 0.0.20.651 → 0.0.20.652 |
| `pydaw/version.py` | Version-String aktualisiert |

## Was als nächstes zu tun ist
- AP7 Phase 7A: Advanced Sampler (Multi-Sample Mapping, Round-Robin, etc.)
- AP10 Phase 10C: DAWproject Roundtrip

## Bekannte Probleme / Offene Fragen
- Factory-Preset-Scan für CLAP-Plugins noch nicht implementiert (CLAP hat keinen Standard-Preset-Pfad)
- LV2-Preset-Scan nutzt noch nicht den bestehenden lilv-basierten Scanner
- "Responsive Verdichtung für kleine Fensterbreiten" (UI-Hotfix) noch offen
