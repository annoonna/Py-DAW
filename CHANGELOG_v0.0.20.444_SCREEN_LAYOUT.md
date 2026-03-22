# CHANGELOG v0.0.20.444 — Detachable Panels + Multi-Monitor Layout System

## Neue Dateien
- `pydaw/ui/screen_layout.py` — ScreenLayoutManager + DetachablePanel + 8 Layout-Presets

## Geänderte Dateien
- `pydaw/ui/main_window.py` — Integration: Menu, Panel-Registrierung, Lifecycle-Hooks
- `PROJECT_DOCS/progress/TODO.md` — Neue Einträge
- `PROJECT_DOCS/progress/DONE.md` — Neue Einträge
- `VERSION` — 0.0.20.443 → 0.0.20.444

## Features
- **Detachable Panels:** Editor, Mixer, Device, Browser, Automation können als freie Fenster abgekoppelt werden
- **Bitwig-Style Layout-Presets:** 8 Presets für 1/2/3 Monitore via Ansicht → Bildschirm-Layout
- **Persistenz:** Detach-Status + Geometrie überleben App-Neustart
- **Dynamisches Menü:** Zeigt erkannte Monitore, deaktiviert nicht-verfügbare Presets
- **Re-Dock on Close:** Float-Fenster schließen = automatisches Andocken (kein Widget-Verlust)
