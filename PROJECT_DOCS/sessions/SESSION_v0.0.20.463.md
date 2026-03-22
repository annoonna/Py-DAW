# Session Log — v0.0.20.463

**Datum:** 2026-03-15
**Entwickler:** Claude Opus 4.6
**Dauer:** ~10 min
**Version:** 0.0.20.462 → 0.0.20.463

## Task

**CLAP Editor: Pin/Roll Fix** — Custom-Titelleiste (📌 Pin, 🔺/🔻 Roll, ✕ Close, Draggable)
funktionierte nicht korrekt für CLAP-Plugin-Editoren.

## Problem-Analyse (aus Screenshots)

1. Surge XT CLAP → Parameter werden geladen, aber Editor-GUI hat kaputten Pin
2. MVerb CLAP → Editor-Button vorhanden, aber Pin/Roll nicht funktional
3. Nekobi CLAP → Nur Parameter-Slider, kein Editor (korrekt, hat keine GUI)

## Root Cause

- **Pin:** `setWindowFlags()` auf X11 = Re-Parenting = embedded Plugin-Window wird zerstört
- **Roll:** `sizeHint()` liefert nach `hide()` falsche Werte → Fenster hat nach Ausrollen falsche Größe

## Fix

1. `_toggle_editor_pin()` — `x11_set_above(wid, enabled)` statt `setWindowFlags()`
2. `_toggle_editor_roll()` — `_saved_gui_width`/`_saved_gui_height` vor dem Rollen speichern

## Nächste Schritte (für nächsten Kollegen)

- [ ] CLAP State Save/Load (Plugin-State in Projekt persistieren)
- [ ] CLAP Multi-Plugin-Bundle Selector (z.B. lsp-plugins.clap)
- [ ] CLAP Preset Browser
