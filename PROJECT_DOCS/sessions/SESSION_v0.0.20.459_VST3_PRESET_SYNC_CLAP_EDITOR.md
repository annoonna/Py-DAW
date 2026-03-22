# 📝 SESSION LOG: v0.0.20.459 — VST3 Preset-Sync + CLAP Host-Extension Fix

**Datum:** 2026-03-15
**Bearbeiter:** Claude Opus 4.6
**Oberste Direktive:** Nichts kaputt machen ✅

## Hauptproblem: "Warum klingt jedes Preset von Surge XT gleich?"

### Root Cause
Der VST3 Editor läuft als separater QProcess (`vst_gui_process.py`), der eine **eigene pedalboard Plugin-Instanz** lädt. Wenn man im Surge XT Patch Browser ein Preset wählt, ändert sich nur die Editor-Instanz — die Audio-Engine-Instanz (die den Sound produziert) bleibt unverändert auf "Init Saw".

### Fix: State-Blob-Tracking + Transfer
1. **`_ParamPoller` in `vst_gui_process.py`** — Tracked jetzt alle ~500ms den `raw_state` Blob-Hash. Bei Änderung (= Preset-Wechsel) wird der volle State als Base64 via `{"event": "state", "blob": "..."}` an den Host gesendet.
2. **`Vst3AudioFxWidget._on_editor_stdout()`** — Neuer `"state"` Event-Handler empfängt den Blob.
3. **`_apply_state_blob_from_editor()`** — Neue Methode: Findet die live Audio-Engine Plugin-Instanz (Instrument ODER FX) und wendet den State-Blob via `setattr(plugin, "raw_state", raw)` an. Surge XT klingt jetzt sofort anders wenn man ein Preset wählt.

## Zweites Problem: `hostGui != nullptr` DISTRHO assertion

### Root Cause (aus v458)
Das `clap_host_t` Struct fehlte die `get_extension` Callback-Funktion. DISTRHO-Plugins rufen `host->get_extension("clap.gui")` auf und erwarten einen Pointer auf `clap_host_gui_t` zurück.

### Fix
- `clap_host_t` hat jetzt `get_extension` Feld (korrekte Position per CLAP-Spec)
- `_host_get_extension()` Callback erkennt `"clap.gui"` und gibt `_host_gui_ext` zurück
- `clap_host_gui_t` Struct mit allen 5 Callbacks (resize_hints_changed, request_resize, request_show, request_hide, closed)

## CLAP Editor mit Pin 📌 + Roll 🔺

ClapAudioFxWidget Editor-Fenster hat jetzt:
- Custom Titelleiste (FramelessWindowHint)
- 📌 Pin Button (WindowStaysOnTopHint toggle)
- 🔺/🔻 Roll Button (GUI container hide/show)
- ✕ Close Button
- Draggable Titelleiste (mousePressEvent/mouseMoveEvent)
- Plugin-GUI in separatem Container embedded

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/vst_gui_process.py` | _ParamPoller: State-Blob-Tracking + "state" Event |
| `pydaw/ui/fx_device_widgets.py` | Vst3AudioFxWidget: "state" handler + _apply_state_blob_from_editor() |
| `pydaw/audio/clap_host.py` | clap_host_t: +get_extension, +clap_host_gui_t, +_host_gui_ext |
| `pydaw/ui/fx_device_widgets.py` | ClapAudioFxWidget: Editor mit Pin/Roll/Close Titelleiste |
| `pydaw/version.py` | → `0.0.20.459` |

## Nichts kaputt gemacht ✅
- Alle Dateien kompilieren fehlerfrei
- VST2/VST3/LV2/LADSPA/DSSI unverändert
- CLAP additiv
