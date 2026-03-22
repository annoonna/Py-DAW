# CHANGELOG v0.0.20.534 — Keyboard Shortcuts für Layout-Presets + Container-Device Reorder

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Typ:** 2 kleine Features

---

## 1. Keyboard Shortcuts für Layout-Presets

| Shortcut | Layout |
|----------|--------|
| Ctrl+Alt+1 | Ein Bildschirm (Groß) |
| Ctrl+Alt+2 | Ein Bildschirm (Klein) |
| Ctrl+Alt+3 | Tablet |
| Ctrl+Alt+4 | Zwei Bildschirme (Studio) |
| Ctrl+Alt+5 | Zwei Bildschirme (Arranger/Mixer) |
| Ctrl+Alt+6 | Zwei Bildschirme (Hauptbildschirm/Detail) |
| Ctrl+Alt+7 | Zwei Bildschirme (Studio/Touch) |
| Ctrl+Alt+8 | Drei Bildschirme |

Shortcuts werden im Menü als Hints angezeigt.

## 2. Container-Device Reorder (▲/▼)

- FX Layer: ▲/▼ pro Device innerhalb jedes Layers
- Chain: ▲/▼ pro Device innerhalb der Sub-Chain
- Nur sichtbar wo Move möglich ist
- Sofortiges UI-Rebuild nach Swap

## Geänderte Dateien

- `pydaw/ui/main_window.py` (+15 Zeilen)
- `pydaw/ui/fx_device_widgets.py` (+50 Zeilen)

## Nichts kaputt gemacht ✅
