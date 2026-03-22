# CHANGELOG v0.0.20.463 — CLAP Editor: Pin/Roll + GUI-Finder + WA_NativeWindow Fix

**Datum:** 2026-03-15
**Autor:** Claude Opus 4.6
**Task:** Fix 3: CLAP Editor mit 📌 Pin + 🔺 Roll (wie VST2 Dexed Editor)

## Problem

CLAP-Plugin-Editoren (Surge XT, 3 Band EQ, etc.) zeigten keinen Editor-Button
bzw. das Öffnen funktionierte nicht. Drei Root-Causes:

### Root Cause 1: `_find_live_clap_plugin()` findet Instrumente nicht
CLAP-Instrumente (z.B. Surge XT als Instrument) werden als `ClapInstrumentEngine`
in `audio_engine._vst_instrument_engines[track_id]` gespeichert, NICHT im FxChain.
Die Suchfunktion schaute nur im FxChain → Plugin nie gefunden → Editor-Button bleibt unsichtbar.

### Root Cause 2: `_editor_gui_container` hat kein `WA_NativeWindow`
Ohne `WA_NativeWindow` gibt `winId()` keinen echten X11-Window-Handle zurück.
`create_gui()` bekommt Handle 0 → CLAP-Plugin kann nicht embedden → Editor leer.

### Root Cause 3: `ClapInstrumentEngine` hatte kein `has_gui()`/`get_plugin()`
Die Instrument-Klasse hatte die GUI-Accessor-Methoden noch nicht.

### Bonus: Pin nutzte `setWindowFlags()` statt `x11_set_above()`
Re-Parenting zerstört embedded Plugin-GUI auf X11.

## Lösung

1. **`_find_live_clap_plugin()`** — Sucht jetzt BEIDE Pfade:
   - FX chain devices (`_track_audio_fx_map → devices[]`)
   - Instrument engines (`_vst_instrument_engines[track_id]`)
   - Debug-Output auf stderr für Troubleshooting

2. **`WA_NativeWindow`** auf `_editor_gui_container` gesetzt
   - Echte X11-Window-ID für Plugin-Embedding
   - Kleines Delay (50ms) für X-Server-Sync

3. **`ClapInstrumentEngine`** — `has_gui()` + `get_plugin()` hinzugefügt

4. **`_check_gui_support()`** — Retry-Logik (bis 5x mit steigendem Delay)
   - Audio Engine braucht Zeit zum Laden → erste Prüfung scheitert oft

5. **Pin** → `x11_set_above()` statt `setWindowFlags()`
6. **Roll** → Originalgröße wird gespeichert/wiederhergestellt

## Geänderte Dateien

- `pydaw/ui/fx_device_widgets.py` — `ClapAudioFxWidget` (5 Methoden geändert)
- `pydaw/audio/clap_host.py` — `ClapInstrumentEngine` (+2 Methoden)

## Nichts kaputt gemacht ✅

- VST2/VST3 Editor-Code komplett unberührt
- Nur additive Änderungen an bestehenden CLAP-Klassen
- Syntax-Check bestanden
