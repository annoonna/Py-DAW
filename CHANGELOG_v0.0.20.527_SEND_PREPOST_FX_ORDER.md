# CHANGELOG v0.0.20.527 — Send Pre/Post Toggle + FX-Spuren vor Master (Bitwig-Style)

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (2 kleine Punkte)

---

## Änderungen

### 1. Send Pre/Post Toggle im Mixer (Rechtsklick)

**Problem:** Send-Knobs waren nur per Amount steuerbar, Pre/Post-Fader konnte nicht umgeschaltet werden.

**Lösung:**
- Rechtsklick auf jeden Send-Knob öffnet Kontextmenü:
  - 🔵 "Auf Pre-Fader umschalten" / 🟡 "Auf Post-Fader umschalten"
  - Schnellwahl: 50% / 100%
  - ❌ "Send entfernen"
- Neue `toggle_send_pre_fader()` Methode in `ProjectService`
- Farbe wechselt sofort: gelb = Post-Fader, blau = Pre-Fader (Bitwig-Style)
- Audio-Engine empfängt neuen `pre_fader`-Status automatisch via `rebuild_fx_maps()`

**Dateien:**
- `pydaw/ui/mixer.py`: `_on_send_context_menu()`, `customContextMenuRequested` auf QDial
- `pydaw/services/project_service.py`: `toggle_send_pre_fader()`

### 2. FX-Spuren immer direkt vor Master positioniert

**Problem:** FX-Spuren (Return-Tracks) konnten überall zwischen regulären Spuren stehen.

**Lösung:**
- `_rebuild_track_order()` in ProjectService sortiert jetzt automatisch:
  1. Reguläre Spuren (audio, instrument, bus, group) — in ihrer relativen Reihenfolge
  2. FX-Spuren (kind="fx") — gesammelt am Ende
  3. Master-Track — ganz am Schluss
- Gilt bei jedem Track-Add, Track-Move, Track-Reorder

**Datei:**
- `pydaw/services/project_service.py`: `_rebuild_track_order()`

---

## Nichts kaputt gemacht ✅

- Bestehende Send-Knob-Funktionalität (Drehen = Amount ändern) unverändert
- Alle bestehenden Track-Operationen (Add, Remove, Move, Group) funktionieren weiterhin
- Audio-Engine Send-Bus-Routing unverändert (liest pre_fader bereits korrekt)
- Projekt-Format unverändert (pre_fader war bereits im Send-Dict)
- Alle anderen Mixer-Features (VU, Fader, Pan, Mute/Solo) unberührt
