# SESSION v0.0.20.214 — Waveform Region Drag Handles (Start/End)

**Datum:** 2026-03-04  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Scope:** UI-only, safe / keine DAW-Core Änderungen

## Ziel
User-Request: **Start/End als Drag-Handles direkt im Waveform** (Bitwig/Ableton-Style), ohne andere Systeme anzufassen.

## Umsetzung (safe)
- `WaveformStrip` erhält eine minimale Hit-Test + Drag-Logik für die **Region**:
  - Hover nahe Start/End-Linie ⇒ Cursor ↔ (`SizeHorCursor`)
  - Drag am Handle ⇒ normierte Position (0..1) ⇒ `engine.set_region_norm(start=..., end=...)`
- Handles werden im Strip gerendert als kleine Caps über den Region-Linien.

## Safety
- Wenn `engine` fehlt oder `set_region_norm` nicht existiert ⇒ **no-op** (keine Exceptions nach außen).
- Keine Änderungen an Audio-Engine / Project-Format.

## Dateien
- `pydaw/plugins/sampler/ui_widgets.py`
- `VERSION`, `pydaw/version.py`

## Test-Checkliste
1) Pro Audio Sampler → Sample laden → Start/End Marker sichtbar.
2) Maus nahe Marker → Cursor ↔.
3) Drag Start/End → Region verschiebt sich hörbar (One-Shot/Preview) und visuell.
4) Drum Machine Slot Editor Waveform → gleiche Interaktion.

