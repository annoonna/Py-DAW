# Session v0.0.20.217 — Pro Drum Machine: Slot‑FX Reorder (Drag) + Presets + QScrollArea Fix

**Datum:** 2026-03-04 12:16  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Oberste Direktive:** Nichts kaputt machen (safe UI‑only)

## Problem
- Pro Drum Machine zeigte: `Instrument error: name 'QScrollArea' is not defined`
- User‑Wunsch: 
  - Drag&Drop Reorder innerhalb des Slot‑FX Racks (statt nur ▲▼)
  - Presets pro Slot‑FX Chain (Save/Load)

## Fixes / Features (safe)
### 1) QScrollArea Fix
- `QScrollArea` korrekt aus `PyQt6.QtWidgets` importiert.
- Keine Logikänderung, nur Import‑Fehler behoben.

### 2) Reorder per Drag (internal move)
- Jede Slot‑FX Karte hat jetzt einen **Drag‑Handle (≡)**.
- Drag innerhalb des Racks → Drop bestimmt Insert‑Index → Geräte‑Liste wird neu sortiert.
- Up/Down Buttons bleiben als Fallback bestehen.

### 3) Presets pro Slot‑FX Chain (Save/Load/Clear)
- Menü **Preset** im Slot‑FX Rack:
  - **Save Preset…** → JSON
  - **Load Preset…** → JSON (validiert; unbekannte FX werden übersprungen)
  - **Clear Slot FX**

**Speicherort Default:** `~/.cache/ChronoScaleStudio/slot_fx_presets/`

## Betroffene Dateien
- `pydaw/plugins/drum_machine/drum_widget.py`
- `pydaw/version.py`
- `VERSION`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Test
1) Pro Drum Machine öffnen → darf nicht mehr “Instrument error … QScrollArea” zeigen.  
2) Im Slot‑FX Rack 3+ FX hinzufügen → mit **≡** umsortieren.  
3) Preset speichern → Chain löschen → Preset laden → Chain wieder da.

