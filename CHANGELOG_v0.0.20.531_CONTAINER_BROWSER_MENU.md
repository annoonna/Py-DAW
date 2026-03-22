# CHANGELOG v0.0.20.531 — Device-Container Phase 2: Browser/Menü/DnD-Integration

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (Phase 2 — UI-Integration)

---

## Änderungen

### 3 Wege Container hinzuzufügen:

1. **Effects Browser (Audio-FX Tab)** — 📦 FX Layer und 📦 Chain als erste Einträge (cyan). Doppelklick oder "Add" fügt Container auf aktive Spur ein.

2. **Rechtsklick auf Device-Chain** — Kontextmenü mit 📦 Container-Sektion und 🎚️ Audio-FX-Sektion. Schnellster Weg.

3. **Drag&Drop** — Container aus Browser auf die Device-Chain ziehen. Drop-Indicator zeigt Einfügeposition in der Audio-FX-Zone.

### Automatisches Container-Routing

`add_audio_fx_to_track()` erkennt jetzt Container-Plugin-IDs und delegiert automatisch an `add_fx_layer_to_track()` / `add_chain_container_to_track()`. Damit funktionieren alle bestehenden Codepfade (Browser-Add, Group-Batch-Add, SmartDrop) automatisch mit Containern.

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/ui/effects_browser.py` | Container-Einträge im Audio-FX Tab, Container-Routing in _add_audio_selected() |
| `pydaw/ui/device_panel.py` | contextMenuEvent auf Chain-Fläche, _show_chain_context_menu(), DnD-Accept für container kind, Container-Guard in add_audio_fx_to_track() |

---

## Nichts kaputt gemacht ✅

- Bestehende Audio-FX Browser-Einträge unverändert
- Bestehende DnD-Pfade (Note-FX, Audio-FX, Instrument) unverändert
- DevicePanel Card-Rendering unverändert
- Audio-Engine unberührt
