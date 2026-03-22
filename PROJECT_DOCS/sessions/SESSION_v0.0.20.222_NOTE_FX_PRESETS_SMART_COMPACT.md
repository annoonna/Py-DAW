# Session v0.0.20.222 — NOTE‑FX Presets + Smart Compact UI

## Goal
User requested (strict directive: **do not break anything**):
- NOTE‑FX **Presets per Track** (Save/Load like Slot‑FX)
- NOTE‑FX **per-card collapsible** with **smart default** (only one expanded)
- Overall **more compact** (less scrolling; Ableton/Bitwig-like density)

## Changes (UI-only, safe)
### Pro Drum Machine — NOTE‑FX strip
- Added **Preset** menu to NOTE‑FX strip:
  - Save Preset… (asks name + tags)
  - Load Preset… (validates known NOTE‑FX, regenerates IDs, keeps dict refs stable)
  - Clear Note‑FX
- Added **smart expand** behavior:
  - Only **one** NOTE‑FX card expanded at a time
  - Newly added NOTE‑FX auto-expands + strip auto-opens
  - If exactly one NOTE‑FX exists, it auto-expands (otherwise compact)
- Reduced UI density (margins/spacing + scroll height) to reduce scrolling.

### Pro Drum Machine — Slot‑FX inline rack compact
- Slot‑FX rack is now **collapsed by default** (auto-expands on drag enter).
- Reduced scroll heights + spacing.
- CHAIN container dials are **smaller** inside the inline rack (UI-only).

## Files changed
- `pydaw/plugins/drum_machine/drum_widget.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/sessions/LATEST.md`

## Notes
- No audio engine/DSP/core refactors.
- Presets stored under `~/.cache/ChronoScaleStudio/note_fx_presets/`.
