# Session Log — v0.0.20.690

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R8B+R8C+R8D — AETERNA komplett
**Aufgabe:** Voice+Filter, Modulation Matrix, State/Presets, Python AETERNA Bugfixes

## Was wurde erledigt

### Phase R8B — Voice + Filter (v686–v689)
- `voice.rs` (~600 Z.): AeternaVoice = Osc + Stereo Biquad + AEG/FEG + Glide + VoiceModState
- AeternaVoicePool: 32 Voices pre-allokiert, Oldest/Quietest/SameNote Stealing
- AeternaVoiceParams: 27 Parameter
- AeternaInstrument implements InstrumentNode, Factory Registration

### Phase R8C — Modulation Matrix (v690)
- `modulation.rs` (~470 Z.): ModMatrix mit 8 Slots
- 8 Sources: LFO1, LFO2, AEG, FEG, Velocity, Aftertouch, ModWheel, Off
- 7 Destinations: Pitch (±24st), FilterCutoff, FilterResonance, Amp, Pan, Shape, FmAmount
- Per-voice LFOs synced to note-on, bipolar/unipolar mode
- VoiceModState mit 2 LFOs pro Voice
- Voice render_sample() integriert ModOutput für alle Destinations
- 12 Unit-Tests in modulation.rs

### Phase R8D — Parameter Sync + Presets (v690)
- AeternaCommand Enum: 31 Varianten (inkl. SetModSlot, SetLfoRate, SetLfoShape)
- CC1 (ModWheel) → mod_matrix.mod_wheel
- save_state() → Vec<(String, f64)> für Projekt-Serialisierung
- load_param(key, value) für State-Restore
- 5 Factory Presets: Init, Warm Pad, Pluck Lead, Fat Bass, Bright Keys
- preset_names() API

### Bugfixes
- **v687**: Rust unused import `MAX_UNISON` entfernt (0 Warnings)
- **v688**: ProcessContext in Tests mit allen 8 Feldern via `make_ctx()`
- **v689**: Python AETERNA `note_off(pitch)` per-Note statt alle Voices
- **v689**: Python AETERNA `trigger_note()` nutzt normalen AEG-Release statt 35ms Gate

## Geänderte Dateien
- pydaw_engine/src/instruments/aeterna/modulation.rs (**NEU**, ~470 Z.)
- pydaw_engine/src/instruments/aeterna/voice.rs (R8B+R8C Integration, ~600 Z.)
- pydaw_engine/src/instruments/aeterna/mod.rs (R8C+R8D, ~550 Z.)
- pydaw_engine/src/instruments/mod.rs (Factory Registration)
- pydaw/plugins/aeterna/aeterna_engine.py (note_off + trigger_note Fixes)
- VERSION, pydaw/version.py (685 → 690)

## Nächste Schritte
- Phase R9A — Wavetable Engine (WavetableBank, Frame-Interpolation, Anti-Aliasing)
- Phase R9B — Unison Engine (Classic/Supersaw/Hyper modes)
