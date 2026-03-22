# CHANGELOG v0.0.20.665 — Engine Migration Dialog Wiring

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP1 — Rust Audio-Core (UI-Verdrahtung)

## Was wurde gemacht

### Engine Migration Dialog: Fehlender Slot `_on_engine_migration_dialog` implementiert

**Problem:** Der Menüeintrag `Audio → Engine Migration (Rust ↔ Python)…` existierte
seit v662, aber die zugehörige Methode `_on_engine_migration_dialog` fehlte in
`MainWindow`. Der Klick wurde stillschweigend vom try/except geschluckt — der
Dialog öffnete sich nie.

**Fix:** `_on_engine_migration_dialog()` in `MainWindow` implementiert:
- Importiert `EngineMigrationDialog` aus `engine_migration_settings.py`
- Öffnet den Dialog modal (`dlg.exec()`)
- Fehler werden in der Statusbar angezeigt
- Pfad: **Menüleiste → Audio → Engine Migration (Rust ↔ Python)…**

### Dialog-Features (bereits in v662 implementiert, jetzt erreichbar):
- 3 Subsystem-Toggles: Audio Playback, MIDI Dispatch, Plugin Hosting
- Rust Binary Verfügbarkeits-Anzeige
- "Alle → Rust" / "Alle → Python" Quick-Actions
- Performance-Benchmark Runner mit Live-Progress
- "Rust als Standard" Checkbox

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/ui/main_window.py | +12 Zeilen: `_on_engine_migration_dialog()` Methode |
| VERSION | 664 → 665 |
| pydaw/version.py | 664 → 665 |

## Bekannte Probleme
- Keine
