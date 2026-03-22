# CHANGELOG v0.0.20.532 — Device-Container Phase 3: Layer-Expand + Device-Management

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (Phase 3 — Container-Interaktion)

---

## Was ist neu?

Container sind jetzt **voll interaktiv** — nicht nur Anzeige, sondern komplettes Device-Management direkt im Container-Widget.

### FX Layer Container (⧉ Cyan)

- **▶/▼ Klick-Expand pro Layer** — Layer-Header klicken klappt die Devices auf/zu
- **Per-Layer Volume** — 50px Mini-Slider pro Layer (0-100%)
- **Layer Ein/Aus** — ●/○ Toggle-Button
- **Layer Entfernen** — × Button (korrektes Index-Shifting)
- **Device Ein/Aus** — ⏻ Toggle pro Device im Layer
- **Device Entfernen** — × Button pro Device
- **"+ FX → Layer N"** — Popup-Menü mit allen 17 Built-in Audio-FX, fügt in den spezifischen Layer ein

### Chain Container (⟐ Orange)

- **Device Ein/Aus** — ⏻ Toggle pro Device
- **Device Entfernen** — × Button pro Device
- **"+ FX → Chain"** — Popup-Menü mit allen 17 Built-in Audio-FX

### Geänderte Datei

- `pydaw/ui/fx_device_widgets.py` — Komplett überarbeitete Container-Widgets + `_clear_layout()` Helper

## Nichts kaputt gemacht ✅

- Audio-Engine Container-Processing (v530) unverändert
- Browser/Menü/DnD-Integration (v531) unverändert
- Alle bestehenden Device-Widgets unberührt
- Projekt-Format unverändert (gleiche JSON-Struktur)
