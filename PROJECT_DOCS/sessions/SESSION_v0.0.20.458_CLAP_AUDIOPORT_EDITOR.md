# 📝 SESSION LOG: v0.0.20.458 — CLAP Audio-Port-Bridging + Editor GUI + Bugfixes

**Datum:** 2026-03-15
**Bearbeiter:** Claude Opus 4.6
**Oberste Direktive:** Nichts kaputt machen ✅

## Bug-Report-Analyse (Screenshots + GDB-Log)

### Problem 1: DISTRHO assertion `"in == DISTRHO_PLUGIN_NUM_INPUTS" v1 2, v2 1`
**Ursache:** CycleShifter.clap (DISTRHO-Plugin) erwartet **1 Mono-Input**, unser Host gab immer **2 Stereo-Channels**. CLAP-Plugins deklarieren ihre Audio-Port-Konfiguration via `clap.audio-ports` Extension.
**Fix:** Audio-Ports Extension abfragen: `_n_in_channels` und `_n_out_channels` getrennt. Buffer-Setup nach Port-Query. Mono↔Stereo Bridging in `process_inplace()` (Stereo→Mono: average, Mono→Stereo: duplicate).

### Problem 2: Kein nativer Plugin-Editor
**Ursache:** CLAP-Plugins wie glBars haben eine native GUI via `clap.gui` Extension (X11/Cocoa/Win32), die wir nicht abgefragt haben.
**Fix:** GUI Extension abfragen, `has_gui()`, `create_gui(parent_id)`, `destroy_gui()` in `_ClapPlugin`. `ClapAudioFxWidget` hat jetzt einen `🎛 Editor` Button der ein eigenständiges Fenster mit embedded Plugin-GUI öffnet.

### Problem 3: lsp-plugins.clap "0 Parameter"
**Ursache:** Multi-Plugin-Bundle ohne Sub-Plugin-ID Selektion. enumerate_clap_plugins kann bei großen Bundles scheitern. Wenn nur der Bundle-Pfad ohne `::plugin_id` übergeben wird, findet der Host den richtigen Sub-Plugin nicht.
**Status:** Bekannt, wird in nächster Version mit Sub-Plugin-Selector-Dialog gelöst.

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/clap_host.py` | +Audio-Ports Extension, +GUI Extension, +Mono/Stereo Bridging, +Editor-Lifecycle |
| `pydaw/ui/fx_device_widgets.py` | +Editor-Button, +GUI-Embedding, +closeEvent Cleanup |
| `pydaw/audio/audio_engine.py` | Fix: _is_clap nur für .clap-Dateien (nicht alle :: Refs) |
| `pydaw/version.py` | → `0.0.20.458` |

## Nichts kaputt gemacht ✅
- VST3 Surge XT + VST2 Helm funktionieren weiterhin korrekt (bestätigt im GDB-Log)
- Alle bestehenden Plugin-Formate unverändert
- Alle Dateien kompilieren fehlerfrei
