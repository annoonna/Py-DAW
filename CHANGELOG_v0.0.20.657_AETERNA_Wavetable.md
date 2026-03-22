# CHANGELOG v0.0.20.657 — AETERNA Wavetable Engine

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP7, Phase 7C — Wavetable-Erweiterung für AETERNA

## Was wurde gemacht

### Neues Modul: `pydaw/plugins/aeterna/wavetable.py`
- **WavetableBank** — Thread-safe Wavetable-Speicher mit Import/Export/Draw/FFT
  - Serum-kompatibel: .wav Import mit clm-Chunk-Erkennung, 24-bit Support
  - Surge-Format: .wt Import (raw float32 Frames)
  - 6 Built-in Wavetables: Basic Sine→Saw, Sine→Square, PWM, Formant Vowels, Noise Morph, Harmonic Sweep
  - Frame Drawing: `draw_frame()` zum manuellen Zeichnen einzelner Frames
  - FFT Editor: `get_frame_harmonics()` / `set_frame_from_harmonics()` für additive Synthese
  - Vectorisierte Block-Reads: `read_block()` und `read_block_modulated()` für Audio-Thread
  - State-Serialisierung: Base64-Blob Export/Import für Projekt-Speicherung
  - Max 256 Frames, Auto-Detection Frame Size (256/512/1024/2048)

- **UnisonEngine** — Wavetable-aware Unison mit 4 Modi
  - Off: Single Voice
  - Classic: gleichmäßiges Detune, gleiche Lautstärke
  - Supersaw: breiteres Detune, leichter Level-Taper an den Rändern
  - Hyper: extremes Detune mit zufälligen Phase-Offsets
  - 1-16 Voices, Stereo-Panning pro Voice, sqrt(n) Normalisierung

### Engine-Integration: `aeterna_engine.py`
- Neuer Oszillator-Modus `"wavetable"` in `_render_voice()`
- Wavetable-Position als Modulationsziel (`wt_position` in MOD_TARGET_KEYS)
- Per-Sample Position-Modulation via `read_block_modulated()`
- Motion-Animation: subtile Position-Sweep über motion Parameter
- 3 neue Presets: "Wavetable Pad", "Wavetable Lead", "Wavetable Choir"
- State Schema Version 11→12
- Wavetable-State in `export_state()`/`import_state()` integriert
- `apply_preset()` lädt automatisch Built-in Tables für WT-Presets
- Automation-Gruppe "Wavetable" mit wt_position, detune, spread, width
- Neue API: `load_wavetable_file()`, `load_wavetable_builtin()`, `get_wavetable_info()`, `draw_wavetable_frame()`, `get_wavetable_frame_harmonics()`, `set_wavetable_frame_harmonics()`, `sync_wavetable_unison()`

### Widget-Integration: `aeterna_widget.py`
- Neue WAVETABLE UI-Sektion (auto-hide wenn Mode ≠ wavetable)
- Built-in Table Dropdown + Import-Button (.wav/.wt)
- Waveform-Preview Widget (`_WavetablePreviewWidget`) mit Echtzeit-Anzeige
- Position-Slider (0..1, 1000 Stufen)
- Unison-Controls: Mode ComboBox, Voices SpinBox, Detune/Spread/Width Slider
- Normalize-Button
- Frame-Info Label
- Mode ComboBox um "wavetable" erweitert
- GUI-Sync bei State-Restore

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `pydaw/plugins/aeterna/wavetable.py` | **NEU** — WavetableBank, UnisonEngine, 6 Built-in Tables |
| `pydaw/plugins/aeterna/aeterna_engine.py` | Wavetable-Modus, 3 Presets, State, API, Schema v12 |
| `pydaw/plugins/aeterna/aeterna_widget.py` | WAVETABLE Sektion, Preview, Controls, Handlers |
| `pydaw/plugins/aeterna/__init__.py` | Exports erweitert |
| `VERSION` | 0.0.20.657 |
| `pydaw/version.py` | __version__ aktualisiert |

## Was als nächstes zu tun ist
- **AP10 Phase 10C — DAWproject Roundtrip**: Export/Import mit Plugins
- **AP1 Phase 1C — Rust Plugin-Hosting**: VST3/CLAP in Rust
- **AP1 Phase 1D — Migration**: Schrittweise Migration auf Rust-Engine

## Bekannte Probleme / Offene Fragen
- Keine — Phase 7C ist vollständig implementiert
- Wavetable Draw-Editor (graphisches Zeichnen in UI) könnte als zukünftige Verfeinerung ein Canvas-Widget bekommen
