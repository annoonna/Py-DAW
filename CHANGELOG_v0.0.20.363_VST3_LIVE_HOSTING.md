# CHANGELOG v0.0.20.363 — VST3/VST2 Live Hosting via pedalboard

**Session:** Claude Sonnet 4.6 — 2026-03-09
**Basierend auf:** v0.0.20.362

## Problem

VST3 und VST2 Plugins wurden im Browser angezeigt und konnten dem Device hinzugefügt werden,
aber die Status-Meldung lautete immer:

```
"Added to Device: ZamAutoSat — Placeholder (Hosting noch nicht implementiert)"
```

Im Device-Panel stand "(no UI yet)" und das Plugin wurde beim Audio-Rendering ignoriert.

## Lösung

### `pedalboard` (Spotify) als VST3/VST2 Host

`pedalboard` ist bereits installiert (v0.9.22) und bietet:
- `pedalboard.load_plugin(path)` — lädt VST3/VST2 Plugins
- `plugin.parameters` — Dict aller Parameter mit min/max/default
- `plugin.process(audio, sample_rate)` — echtes Audio-Processing

### Neue/geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/vst3_host.py` | **NEU** — VST3 Host via pedalboard |
| `pydaw/audio/fx_chain.py` | `ext.vst3:` / `ext.vst2:` Branch hinzugefügt |
| `pydaw/ui/fx_device_widgets.py` | `Vst3AudioFxWidget` Klasse + Dispatch |
| `pydaw/ui/plugins_browser.py` | Status-Meldung auf "VST3 live OK" aktualisiert |

### vst3_host.py — Kernfunktionen

- `is_available()` → True wenn pedalboard importierbar
- `availability_hint()` → Versions-String für Status-Bar
- `describe_controls(path)` → Liste von `Vst3ParamInfo` (name, min, max, default, units)
- `Vst3Fx.process_inplace(buf, frames, sr)` — kompatibel mit FxChain-Interface
  - buf shape: (frames, 2) stereo float32
  - Liest Parameter aus RTParamStore
  - Setzt sie auf Plugin vor jedem Block
  - Ruft `plugin.process()` auf, schreibt zurück

### Vst3AudioFxWidget

- Header: "VST3" / "VST2" Label + Plugin-Dateiname
- Alle Parameter als Slider + SpinBox (oder Checkbox für Booleans)
- Live-Sync alle 60ms vom RTParamStore
- Persistenz in Project-JSON
- Automation-Kontextmenü

## Sicherheit

- Alle Exceptions gecatcht, `_ok=False` → no-op bei Fehler
- Keine Änderungen an Audio-Engine, Hybrid-Engine oder Transport
- Neue Datei (`vst3_host.py`) kann nicht bestehende Funktionalität brechen
- VST3-Branch in fx_chain.py ist ein `elif` hinter LADSPA — keine Interferenz
