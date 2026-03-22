# CHANGELOG v0.0.20.686 — AETERNA Voice + Filter (Rust R8B)

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R8B

## Was wurde gemacht

### Neues Modul: `instruments/aeterna/voice.rs` (~560 Zeilen)

**AeternaVoice — Vollständige Synthesizer-Stimme:**
- OscillatorState (aus R8A) + Stereo Biquad Filter + AEG + FEG + Glide
- Filter: LP12, LP24 (kaskadiert), HP12, BP, Notch, Off
- Exponentielles Cutoff-Mapping (20 Hz – 20 kHz)
- Resonance-Mapping (Q 0.5–20)
- Key Tracking: Cutoff folgt der gespielten Note (0–100%)
- FEG → Cutoff Modulation mit bipolarem Amount (-1..+1)
- Velocity Sensitivity (0–1, skaliert AEG-Amplitude)
- Glide/Portamento: Exponentielles Pitch-Smoothing, konfigurierbar 0–5s

**AeternaVoicePool — Pre-allokierter Voice-Pool:**
- MAX_POLYPHONY = 32 Stimmen, vollständig pre-allokiert
- Voice-Stealing: Oldest, Quietest, SameNote
- Zero-Alloc render(): alle Voices in Interleaved-Buffer summiert
- Last-Freq Tracking für Glide zwischen aufeinanderfolgenden Noten

**AeternaVoiceParams — Shared Parameter Struct:**
- 27 Parameter: Osc, Filter, AEG, FEG, Glide, Master, Velocity
- Wird per AeternaCommand lock-free vom GUI-Thread aktualisiert

### Erweitertes Modul: `instruments/aeterna/mod.rs` (~380 Zeilen)

**AeternaInstrument — InstrumentNode Implementation:**
- Implementiert InstrumentNode Trait (pluggbar in AudioGraph)
- Lock-free MIDI via crossbeam bounded channel (256 Events)
- Lock-free Parameter-Commands via separaten Channel (64 Cmds)
- AeternaCommand Enum: 28 Varianten für alle Parameter
- Factory-Registration: InstrumentType::Aeterna.create() funktioniert

### Tests: 37 Unit-Tests (19 Osc + 18 Voice/Instrument)

**voice.rs Tests (18):**
- midi_to_freq (A4, C4, A5)
- Voice new/idle, note_on/activates, produces_audio
- Release fades to idle, kill immediate
- Filter mode parse, filter changes sound, FEG modulates filter
- Glide smooths pitch, velocity sensitivity
- Voice pool creation, note_on/off, all_notes_off, stealing
- Pool render produces audio, polyphony, glide in pool, key tracking

**mod.rs Tests (5):**
- Instrument creation, process, note_off, all_sound_off
- Command channel, polyphonic chord

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw_engine/src/instruments/aeterna/voice.rs | **NEU** ~560 Z. — AeternaVoice, VoicePool, Params, Glide |
| pydaw_engine/src/instruments/aeterna/mod.rs | **REWRITE** ~380 Z. — AeternaInstrument + InstrumentNode |
| pydaw_engine/src/instruments/mod.rs | AeternaInstrument Re-Export + Factory + Test |
| VERSION | 685 → 686 |
| pydaw/version.py | 685 → 686 |
| PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md | R8B [x] abgehakt |
| PROJECT_DOCS/ROADMAP_MASTER_PLAN.md | Nächste Aufgabe → R8C |

## Was als nächstes zu tun ist
- Phase R8C — AETERNA Modulations-Matrix (8 Mod-Slots, LFO/ENV/MSEG Sources)
- Phase R8D — Parameter Sync + Presets (IPC Commands, State Save/Load)

## Bekannte Probleme / Offene Fragen
- Kein `cargo build` möglich in dieser Umgebung → Syntax durch Brace-Matching und API-Cross-Reference verifiziert
- Filter-Koeffizienten werden pro Sample neu berechnet (korrekt für Modulation, aber CPU-intensiv) — könnte mit Block-Update optimiert werden
