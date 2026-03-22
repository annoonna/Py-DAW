# CHANGELOG v0.0.20.244 — LADSPA Live-Hosting + Parameter-UI

**Datum:** 2026-03-05
**Bearbeiter:** Claude Opus (Anthropic)

## Feature: LADSPA Audio-FX Hosting

PyDAW kann jetzt **187+ LADSPA Plugins** live als Audio-Effekte nutzen
(vorher nur "no UI yet" Platzhalter).

### Neue Datei: `pydaw/audio/ladspa_host.py`
- Komplettes LADSPA C-API Hosting via Python `ctypes`
- Parst `LADSPA_Descriptor` struct direkt aus .so Dateien
- Control-Port Defaults aus LADSPA Hints (BOUNDED, LOGARITHMIC, etc.)
- Stereo/Mono Audio I/O mit automatischem Up/Downmix
- RT-Parameter Integration (gleicher Mechanismus wie LV2)
- Multi-Plugin .so Support (z.B. `adsr_1653.so` → Plugin mit ID 1653)
- Sauberes Cleanup (deactivate + cleanup bei GC)

### Geänderte Dateien
- `pydaw/audio/fx_chain.py` — `ext.ladspa:` und `ext.dssi:` in ChainFx
- `pydaw/ui/fx_device_widgets.py` — `LadspaAudioFxWidget` (Slider + SpinBox)
- `VERSION` → 0.0.20.244

### Wie nutzen
1. Browser → Plugins Tab → LADSPA
2. Plugin auswählen → "Add to Device"
3. Device Panel zeigt jetzt alle Parameter mit Slidern
4. DSP: ACTIVE wenn Audio-Engine das Plugin verarbeitet

### Einschränkungen (MVP)
- Kein LADSPA-spezifisches Preset-System
- Keine DSSI-GUI-Einbettung (Parameter-UI funktioniert aber)
- INPLACE_BROKEN Property wird nicht gesondert behandelt (selten)
