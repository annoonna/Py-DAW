# CHANGELOG v0.0.20.644 — Mega-Session: 7+ Phasen komplett

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspakete:** AP8 8C, AP6 6A+6C, AP9 9A+9B+9C, AP10 10A+10B, AP3 3C

## Erledigte Phasen

### AP8 Phase 8C — Utility FX (5/5) → AP8 KOMPLETT
- GateFx: Noise Gate + Sidechain + Hold
- DeEsserFx: Bandpass-Detektion + Listen-Mode
- StereoWidenerFx: Mid/Side + Width 0-2
- UtilityFx: Gain/Pan/Phase/Mono/DC/Swap
- SpectrumAnalyzerFx: FFT + Peak Hold + API

### AP6 Phase 6A — MIDI Effects Chain (8/8)
- Note Echo (delay+transpose), Velocity Curve (6 Typen)
- 16 Chord-Typen, Drop-2/3/Open/Spread Voicings
- Enhanced Random (+timing/length), 13 Factory MIDI FX Presets

### AP6 Phase 6C — Groove Templates (5/5)
- 12 Factory Grooves (Swing/MPC/808/Drummer)
- Extract/Apply/Humanize

### AP9 Phase 9A/9B/9C — Automation komplett → AP9 KOMPLETT
- Plugin-Parameter Discovery + Arm/Disarm
- Relative/Trim Automation Modes
- Snapshot + Clip-Copy + LOG/EXP/S_CURVE CurveTypes

### AP10 Phase 10A+10B — Export (10A komplett, 10B 3/4)
- WAV/FLAC/MP3/OGG + Dither + Normalize + Progress
- Stem Export + BPM Naming

### AP3 Phase 3C Task 3 — Tempo-Automation
- TempoMap Modell + beat↔time Konvertierung

## Neue Dateien
| Datei | Zeilen | Beschreibung |
|---|---|---|
| pydaw/audio/utility_fx.py | ~490 | 5 Utility FX |
| pydaw/audio/midi_fx_presets.py | ~280 | Preset Manager + 13 Presets |
| pydaw/audio/groove_templates.py | ~350 | 12 Grooves + API |
| pydaw/services/plugin_param_discovery.py | ~320 | Param Discovery |
| pydaw/services/audio_export_service.py | ~380 | Export Engine |
| pydaw/model/tempo_map.py | ~260 | TempoMap |

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/audio/fx_chain.py | +5 Utility FX registriert |
| pydaw/audio/note_fx_chain.py | +Note Echo, Vel Curve, 16 Chords, +Random features |
| pydaw/audio/automatable_parameter.py | +Relative/Trim, +LOG/EXP/S_CURVE, +Snapshot, +Clip-Copy |
| pydaw/ui/fx_specs.py | +7 neue FX Specs |
| pydaw/ui/audio_export_dialog.py | Echter Export statt Placeholder |
