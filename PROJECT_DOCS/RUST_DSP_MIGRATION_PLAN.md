# 🦀 Py_DAW RUST DSP MIGRATION — Masterplan

**Projekt:** Py_DAW (ChronoScaleStudio) — Alle DSP-Engines von Python nach Rust
**Erstellt:** 2026-03-20 (v0.0.20.666)
**Autor:** Anno (Lead Developer) + Claude Opus 4.6
**Geschätzter Aufwand:** 30–50 Sessions

---

## ⚠️ OBERSTE DIREKTIVE — FÜR ALLE KOLLEGEN

```
🔴 DU DARFST NICHTS KAPUTT MACHEN.
🔴 Python-Engine bleibt IMMER als Fallback erhalten.
🔴 should_use_rust() bleibt auf `return False` bis ein Subsystem
   vollständig getestet und freigeschaltet wird.
🔴 Jede Rust-Implementierung wird PARALLEL neben Python gebaut.
   Erst wenn sie 1:1 identischen Output liefert → Freischaltung.
🔴 KEIN bestehender Python-Code wird gelöscht oder geändert!
```

---

## 📊 IST-ZUSTAND

### Python DSP (~20.000 Zeilen)
| Modul | Zeilen | Priorität |
|-------|--------|-----------|
| Built-in FX (EQ, Comp, Reverb, Delay, Limiter) | 556 | 🔴 HOCH |
| Creative FX (Chorus, Phaser, Flanger, Distortion, Tremolo) | 607 | 🟠 MITTEL |
| Utility FX (Gate, DeEsser, Widener, Utility, Analyzer) | 642 | 🟠 MITTEL |
| FX Chain + Processors + JIT | 2.168 | 🔴 HOCH |
| ProSamplerEngine | 813 | 🔴 HOCH |
| MultiSampleEngine (Advanced Sampler) | 554 | 🔴 HOCH |
| DrumMachineEngine | 525 | 🔴 HOCH |
| AETERNA Synth Engine + Wavetable | 3.316 | 🟡 MITTEL |
| Fusion Synth (Oscillators, Filters, Envelopes) | 4.631 | 🟡 MITTEL |
| BachOrgel Engine | 765 | 🟢 NIEDRIG |
| AudioEngine Core + ArrangementRenderer | 4.797 | 🔴 HOCH |
| FluidSynth Service (SF2) | 251 | 🟢 NIEDRIG |
| **TOTAL** | **~19.625** | |

### Rust Engine (vorhanden, ~3.960 Zeilen)
- ✅ AudioGraph (Tracks, Mixing, Pan, Volume, Solo/Mute, Soft Limiter)
- ✅ AudioNode Trait (GainNode, SilenceNode, SineNode, MixNode)
- ✅ Transport (Beat/Sample Position, Loop, Tempo)
- ✅ IPC Bridge (Unix Socket, MessagePack, Commands/Events)
- ✅ Lock-Free (AtomicF32, ParamRing SPSC, AudioRing, MeterRing)
- ✅ ClipStore + ArrangementRenderer (Clip Playback mit SR Conversion)
- ✅ PluginHost Trait (VST3 + CLAP Stubs, SineGenerator PoC)
- ✅ PluginIsolator (Thread Isolation, Crash Recovery, Watchdog)
- ✅ cpal Audio Output (ALSA/PipeWire/JACK)

---

## 🏗️ PHASENPLAN — Reihenfolge & Abhängigkeiten

```
Phase R1: FX Primitives in Rust          ← Grundsteine (Filter, Delay-Line, Envelope)
Phase R2: Built-in FX                    ← EQ, Compressor, Reverb, Delay, Limiter
Phase R3: Creative + Utility FX          ← Chorus, Phaser, Gate, DeEsser, etc.
Phase R4: FX Chain System                ← Serielle FX-Kette pro Track
Phase R5: Sample Playback Engine         ← WAV laden, abspielen, loopen
Phase R6: ProSampler + MultiSample       ← Zone Mapping, Round-Robin, ADSR
Phase R7: DrumMachine                    ← 64 Pads, Choke Groups, Multi-Output
Phase R8: AETERNA Synth                  ← Oszillatoren, Filter, Mod-Matrix
Phase R9: Wavetable + Unison             ← Wavetable Morphing, Supersaw
Phase R10: Fusion Synth                  ← Modularer Synth (Osc, Filter, Env)
Phase R11: BachOrgel + SF2               ← Orgel + FluidSynth Wrapper
Phase R12: IPC Audio-Buffer Bridge       ← Rust rendert Tracks → Python holt Buffers
Phase R13: Integration + Freischaltung   ← should_use_rust() → True, A/B Test
```

**Abhängigkeiten:**
```
R1 ──→ R2 ──→ R3 ──→ R4 (FX Stack komplett)
R1 ──→ R5 ──→ R6 ──→ R7 (Sampler Stack komplett)
R1 ──→ R8 ──→ R9 (AETERNA komplett)
R1 ──→ R10 (Fusion komplett)
R11 = unabhängig (C-Library Wrapper)
R4 + R7 + R9 ──→ R12 ──→ R13 (Integration)
```

---

## 🔧 Phase R1 — DSP Primitives in Rust (~3 Sessions)

### Warum zuerst?
Jeder FX und jedes Instrument braucht diese Bausteine. Einmal richtig
implementiert → alle späteren Phasen profitieren.

### Aufgaben

**R1A — Biquad Filter Library (~1 Session)**
- [x] `dsp/biquad.rs`: Biquad DF2T Struct mit Coefficients
- [x] Filter-Typen: LowPass, HighPass, BandPass, Notch, AllPass, PeakEQ, LowShelf, HighShelf
- [x] `set_params(filter_type, freq, q, gain_db, sample_rate)` → Coefficient-Berechnung
- [x] `process_sample(input: f32) -> f32` — inline, zero-alloc
- [x] `process_block(buffer: &mut [f32], channel_stride: usize)` — Block-Processing
- [x] Unit-Tests: Frequenzgang-Verifikation (1kHz LP @44.1kHz, Q=0.707 → -3dB bei 1kHz)

**R1B — Delay-Line + Envelope (~1 Session)**
- [x] `dsp/delay_line.rs`: Pre-allokierter Ringbuffer mit Fractional-Delay (Interpolation)
- [x] `write(sample)`, `read(delay_samples: f32) -> f32` — linear interpoliert
- [x] `dsp/envelope.rs`: ADSR Envelope Generator
- [x] States: Idle, Attack, Decay, Sustain, Release — sample-accurate
- [x] `note_on()`, `note_off()`, `process() -> f32` (0.0–1.0)
- [x] `dsp/lfo.rs`: LFO mit Sine, Triangle, Square, Saw, S&H
- [x] `set_rate(hz)`, `process() -> f32` (-1.0 bis 1.0)

**R1C — DSP Utilities (~1 Session)**
- [x] `dsp/mod.rs`: Re-exports aller DSP Primitives
- [x] `dsp/math.rs`: `db_to_linear()`, `linear_to_db()`, `midi_to_freq()`, `freq_to_midi()`
- [x] `dsp/smooth.rs`: Parameter-Smoother (One-Pole, exponentiell) — keine Zipper-Noise
- [x] `dsp/dc_blocker.rs`: DC Offset Removal (High-Pass bei 5Hz)
- [x] `dsp/pan.rs`: Equal-Power Pan Law, Stereo-Balance
- [x] `dsp/interpolation.rs`: Linear, Cubic, Hermite Interpolation für Sample-Playback
- [x] Cargo.toml: Neues `[lib]` Target zusätzlich zum Binary

### Wo im Code?
```
pydaw_engine/src/
├── dsp/              ← NEU: DSP Primitives
│   ├── mod.rs
│   ├── biquad.rs
│   ├── delay_line.rs
│   ├── envelope.rs
│   ├── lfo.rs
│   ├── math.rs
│   ├── smooth.rs
│   ├── dc_blocker.rs
│   ├── pan.rs
│   └── interpolation.rs
├── audio_graph.rs    ← existiert
├── ...
```

### Testkriterium
```bash
cargo test -- dsp
# Alle Unit-Tests pass: Biquad Frequenzgang, ADSR Timing, LFO Shapes
```

---

## 🎚️ Phase R2 — Built-in FX in Rust (~3-4 Sessions)

### Referenz: `pydaw/audio/builtin_fx.py` (556 Zeilen)

**R2A — Parametric EQ (~1 Session)**
- [x] `fx/parametric_eq.rs`: 8-Band EQ, jede Band = Biquad aus R1
- [x] Band-Typen: Bell, LowShelf, HighShelf, HighPass, LowPass
- [x] Params: Frequency, Gain, Q pro Band
- [x] `process(buffer: &mut AudioBuffer)` — zero-alloc
- [x] IPC Command: `LoadFx { track_id, slot, fx_type: "parametric_eq", params }`

**R2B — Compressor + Limiter (~1 Session)**
- [x] `fx/compressor.rs`: Feed-Forward RMS Compressor
- [x] Params: Threshold, Ratio, Attack, Release, Knee, Makeup-Gain
- [x] Sidechain-Input (optionaler externer Buffer)
- [x] Gain-Reduction Metering (peak GR → Event an Python)
- [x] `fx/limiter.rs`: Brickwall Limiter (Lookahead optional)
- [x] Params: Ceiling, Release, Gain

**R2C — Reverb + Delay (~1-2 Sessions)**
- [x] `fx/reverb.rs`: Schroeder Reverb (4 Comb + 4 Allpass, wie Python-Version)
- [x] Params: Pre-Delay, Decay, Damping, Mix
- [x] Alle Delay-Lines aus R1 nutzen
- [x] `fx/delay.rs`: Stereo Delay mit Tempo-Sync
- [x] Params: Time (ms oder Beat-Sync), Feedback, Filter, Ping-Pong, Mix
- [x] `fx/mod.rs`: Re-exports + `FxType` Enum für IPC Dispatch

### Testkriterium
- Rust EQ mit identischen Params liefert identischen Frequenzgang wie Python EQ
- Rust Compressor: Identische Gain-Reduction bei identischem Input

---

## 🎨 Phase R3 — Creative + Utility FX (~3-4 Sessions)

### Referenz: `creative_fx.py` (607 Z.) + `utility_fx.py` (642 Z.)

**R3A — Modulations-FX (~1-2 Sessions)**
- [x] `fx/chorus.rs`: Multi-Voice Chorus (LFO-moduliertes Delay)  *(v0.0.20.669 — 6 Voices, Stereo Spread, Feedback, LFO Shape)*
- [x] `fx/phaser.rs`: N-Stage Allpass Phaser mit Feedback  *(v0.0.20.669 — 2–12 Stages, Exponential Sweep, Negative Feedback)*
- [x] `fx/flanger.rs`: Kurzes moduliertes Delay mit Feedback  *(v0.0.20.669 — Manual+LFO, ±Feedback, Linear Interp)*
- [x] `fx/tremolo.rs`: Amplitude-Modulation (Sine/Square/Triangle)  *(v0.0.20.669 — Stereo Offset/Auto-Pan, 6 LFO Shapes)*
- [x] `fx/distortion.rs`: 5 Modi (Soft Clip, Hard Clip, Tube, Tape, Bitcrush)  *(v0.0.20.669 — Tone Filter, Output Gain, SR+Bit Reduction)*

**R3B — Utility FX (~1-2 Sessions)**
- [x] `fx/gate.rs`: Noise Gate (Threshold, Attack, Hold, Release, SC)  *(v0.0.20.669 — Peak Envelope, Hold Phase, Sidechain, Metering)*
- [x] `fx/deesser.rs`: Bandpass-Detection + Proportional Reduction  *(v0.0.20.669 — Biquad BP, Envelope Follower, Listen Mode)*
- [x] `fx/stereo_widener.rs`: M/S Encode/Decode, Width Control  *(v0.0.20.669 — Width 0–2, Bass Mono Crossover, Biquad LP)*
- [x] `fx/utility.rs`: Gain, Phase Invert, Mono, DC Blocker, Pan  *(v0.0.20.669 — Equal-Power Pan, Channel Swap, 5Hz DC HP)*
- [x] `fx/spectrum_analyzer.rs`: FFT (eigene Impl oder `realfft` Crate), Peak Hold  *(v0.0.20.669 — Radix-2 Cooley-Tukey FFT, Hanning Window, Smoothing, Peak Decay)*

---

## 🔗 Phase R4 — FX Chain System (~2-3 Sessions)

### Referenz: `fx_chain.py` (1.057 Z.)

**R4A — FX Slot + Chain (~1-2 Sessions)**
- [x] `fx/chain.rs`: `FxSlot` { fx: Box<dyn AudioFxNode>, enabled: bool, bypass: bool }  *(v0.0.20.669 — FxSlot mit slot_id, enable/bypass/process)*
- [x] `FxChain`: Vec<FxSlot>, `process(buffer)` iteriert alle aktiven Slots  *(v0.0.20.669 — max 16 Slots, dry/wet mix, wet_gain, add/remove/insert/reorder)*
- [x] `AudioFxNode` Trait: `process(&mut self, buffer: &mut AudioBuffer, ctx: &FxContext)`  *(v0.0.20.669 — Trait + impl für alle 15 Built-in FX via Macro + Manual)*
- [x] Sidechain-Buffer-Weiterleitung durch die Chain  *(v0.0.20.669 — FxContext.sidechain, Compressor+Gate nutzen es)*
- [x] Pre-FX / Post-FX Rendering-Option  *(v0.0.20.669 — FxPosition::PreFader/PostFader, TrackNode::apply_params_with_tempo)*

**R4B — TrackNode Integration (~1 Session)**
- [x] `AudioGraph::TrackNode` bekommt `fx_chain: FxChain`  *(v0.0.20.669 — Feld in TrackNode, erstellt in new())*
- [x] `TrackNode::apply_params()` ruft `fx_chain.process()` NACH Volume/Pan auf  *(v0.0.20.669 — apply_params_with_tempo: Pre-Fader vor Vol/Pan, Post-Fader danach)*
- [x] IPC Commands: `AddFx`, `RemoveFx`, `SetFxParam`, `SetFxBypass`, `ReorderFx`  *(v0.0.20.669 — 6 neue Commands + SetFxEnabled + SetFxChainMix)*
- [x] IPC Events: `FxMeter { track_id, slot, gain_reduction, peak }`  *(v0.0.20.669 — FxMeter Event mit GR + Peak L/R)*

---

## 🎵 Phase R5 — Sample Playback Engine (~2-3 Sessions)

### Warum vor Sampler?
ProSampler, MultiSample und DrumMachine brauchen alle dieselbe Grundlage:
WAV laden, abspielen, loopen, pitch-shiften.

**R5A — Audio File I/O (~1 Session)**
- [x] `sample/mod.rs`: `SampleData` struct (Arc<Vec<f32>>, channels, sample_rate, frames)  *(v0.0.20.672 — Arc-shared, root_note, fine_tune, pitch_ratio(), playback_rate())*
- [x] WAV Loader: `load_wav(path) -> Result<SampleData>` (PCM 16/24/32-bit, f32)  *(v0.0.20.672 — hound Crate, Int+Float, load_wav_with_root())*
- [x] Dependency: `hound` Crate (WAV reading, winzig)  *(v0.0.20.672 — hound = "3.5" in Cargo.toml)*
- [x] Mono→Stereo Konversion, Resampling (linear) bei SR-Mismatch  *(v0.0.20.672 — mono_to_stereo(), downmix_to_stereo(), resample_linear())*

**R5B — Voice + Playback (~1-2 Sessions)**
- [x] `sample/voice.rs`: `SampleVoice` — ein spielender Sample-Instanz  *(v0.0.20.672 — VoiceState, render() mit cubic interp, additive mixing)*
- [x] `note_on(note, velocity, start_frame)`, `note_off()`  *(v0.0.20.672 — note_on/note_off/kill, velocity→gain)*
- [x] Pitch: MIDI Note → Playback-Rate (basierend auf Root Note)  *(v0.0.20.672 — SampleData::playback_rate() inkl. SR-Konversion)*
- [x] Loop: Loop-Start/End Points, Loop-Modes (None, Forward, PingPong)  *(v0.0.20.672 — LoopMode Enum, set_loop(), PingPong mit direction-flip)*
- [x] Interpolation: Cubic aus R1 für Pitch-Shifting  *(v0.0.20.672 — interpolate_cubic() aus dsp/interpolation.rs)*
- [x] `sample/voice_pool.rs`: Pre-allokierter Pool (max 128 Voices)  *(v0.0.20.672 — VoicePool max 256, render_all(), active_count())*
- [x] Voice-Stealing: Oldest, Quietest, Same-Note  *(v0.0.20.672 — StealMode Enum, find_steal_target())*

### Testkriterium
```bash
cargo test -- sample
# WAV laden + Voice spielt Note C4 → Output = korrekte Pitch-Ratio
```

---

## 🎹 Phase R6 — ProSampler + MultiSample Engine (~3-4 Sessions)

### Referenz: `sampler_engine.py` (813 Z.) + `multisample_engine.py` (554 Z.)

**R6A — ProSampler (~1-2 Sessions)**
- [x] `instruments/sampler.rs`: `ProSamplerInstrument` implementiert `AudioNode`  *(v0.0.20.674 — InstrumentNode Trait, MidiEvent, lock-free MIDI/Command Channels, 64-Voice Polyphonie)*
- [x] Single-Sample Mode: Load, ADSR Envelope (aus R1), One-Shot/Loop  *(v0.0.20.674 — SamplerParams, SamplerCommand::SetLoop, LoopMode::None/Forward/PingPong)*
- [x] MIDI Input: NoteOn → Voice starten, NoteOff → Release  *(v0.0.20.674 — push_midi() + process_midi(), CC64/120/123, AllNotesOff/AllSoundOff)*
- [x] Velocity → Volume Mapping  *(v0.0.20.674 — Velocity Curve Linear→Exponential Blend)*
- [x] `process()`: Alle aktiven Voices summieren, ADSR anwenden  *(v0.0.20.674 — VoicePool::render() + master gain/pan, 15 Unit-Tests)*

**R6B — MultiSample / Advanced Sampler (~2 Sessions)**
- [x] `instruments/multisample.rs`: Zone-Mapping (Key Range × Velocity Range)  *(v0.0.20.676 — MultiSampleMap, find_zones(), 256 Zones, 64 Voices)*
- [x] `SampleZone { sample, key_lo, key_hi, vel_lo, vel_hi, root_note, gain, pan, tune }`  *(v0.0.20.676 — Plus: loop, filter, 2×ADSR, 2×LFO, 4 ModSlots)*
- [x] Round-Robin: `rr_group` Counter pro Trigger  *(v0.0.20.676 — 32 RR-Gruppen, zyklische Auswahl, zero-alloc find_zones)*
- [x] Per-Zone: Filter (Biquad aus R1), ADSR Envelope  *(v0.0.20.676 — LP/HP/BP Biquad, Filter-Env-Modulation, separate Amp+Filter ADSR)*
- [x] Modulation: LFO → Pitch/Filter/Amp (4 Slots)  *(v0.0.20.676 — 6 Sources × 4 Destinations, per-voice LFO state)*
- [x] Auto-Mapping: Chromatic/Drum/VelocityLayer (nach Filename-Pattern)  *(v0.0.20.676 — auto_map_zones() + AutoMap IPC Command)*

### IPC Integration
- [x] `LoadSample { instrument_id, zone_index, wav_path, root_note, key_range, vel_range }`  *(v0.0.20.676 — AddSampleZone + 7 weitere Commands in ipc.rs)*
- [x] `ClearZones { instrument_id }`  *(v0.0.20.676 — ClearAllZones + RemoveSampleZone)*
- [x] Python-seitiges Mapping → Rust IPC Sync bei Projekt-Open  *(v0.0.20.676 — 12 Bridge-Methoden in rust_engine_bridge.py)*

---

## 🥁 Phase R7 — DrumMachine (~2-3 Sessions)

### Referenz: `drum_engine.py` (525 Z.)

**R7A — Drum Pads (~1-2 Sessions)**
- [x] `instruments/drum_machine.rs`: 128 Pad-Slots (4 Banks × 16 × 2)  *(v0.0.20.678 — DrumMachineInstrument, 128 pre-alloc DrumPads, 64 Voices)*
- [x] Jeder Slot: `SampleVoice` + `FxChain` + Gain/Pan/Tune  *(v0.0.20.678 — DrumVoice mit ADSR, cubic interp, per-pad gain/pan/tune)*
- [x] MIDI Mapping: Note → Pad (base_note=36, GM Drum Map)  *(v0.0.20.678 — base_note configurable, GM_PAD_NAMES, note-to-pad lookup)*
- [x] Choke Groups: 0-8, Trigger in Gruppe → andere Voices in Gruppe stoppen  *(v0.0.20.678 — MAX_CHOKE_GROUPS=9, kill-on-trigger, same-pad retrigger)*
- [x] One-Shot vs Gate Mode pro Pad  *(v0.0.20.678 — PadPlayMode::OneShot/Gate, note-off only in Gate mode)*

**R7B — Multi-Output (~1 Session)**
- [x] Per-Pad Output-Routing: Pad → bestimmter Output-Bus (max 16)  *(v0.0.20.682 — DrumPad.output_index, DrumVoice.output_index, routing in render_voices)*
- [x] `_pull_multi_output()`: Separate Buffers pro Output  *(v0.0.20.682 — aux_buffers Vec<AudioBuffer>, render_voices routes by output_index)*
- [x] IPC: `SetDrumPadOutput { pad, output_index }`  *(v0.0.20.682 — SetDrumPadOutput + SetDrumMultiOutput in ipc.rs + engine.rs)*
- [x] AudioGraph: Multi-Output-Node mit N Output-Buffers  *(v0.0.20.682 — aux_output_buffers(), output_count(), is_multi_output())*

---

## 🎛️ Phase R8 — AETERNA Synth Engine (~4-5 Sessions)

### Referenz: `aeterna_engine.py` (2.535 Z.) — der größte Brocken

**R8A — Oszillatoren (~1-2 Sessions)**
- [x] `instruments/aeterna/oscillator.rs`: Sine, Saw, Square, Triangle, Noise  *(v0.0.20.684 — gen_sine/saw_polyblep/square_polyblep/triangle, white_noise/pink_noise)*
- [x] Anti-Aliasing: PolyBLEP für Saw/Square  *(v0.0.20.684 — polyblep(), gen_saw_polyblep(), gen_square_polyblep() mit duty)*
- [x] Phase Modulation, FM  *(v0.0.20.684 — OscillatorState.fm_phase, fm_amount/fm_ratio in process())*
- [x] Sub-Oscillator (Octave Down), Noise Generator (White, Pink)  *(v0.0.20.684 — sub_phase, sub_octave 1/2, Paul Kellet Pink Noise)*
- [x] Unison Detune (pre-compute Detune Offsets, Stereo Spread)  *(v0.0.20.684 — MAX_UNISON=16, set_unison(), per-voice detune+pan, equal-power)*

**R8B — Filter + Voice (~1-2 Sessions)**
- [x] `instruments/aeterna/voice.rs`: AETERNA Voice = Osc + Filter + Envelopes  *(v0.0.20.686 — AeternaVoice: OscillatorState + stereo Biquad + AEG/FEG ADSR)*
- [x] Filter: Biquad aus R1, Cutoff + Resonance + Key Tracking  *(v0.0.20.686 — LP12/LP24/HP12/BP/Notch/Off, cascaded 24dB, exponential freq mapping 20-20kHz)*
- [x] AEG (Amplitude Envelope) + FEG (Filter Envelope), jeweils ADSR  *(v0.0.20.686 — AdsrEnvelope aus R1, FEG→Cutoff Modulation mit bipolarem Amount)*
- [x] Voice Pool: Max 32 polyphon, Voice-Stealing  *(v0.0.20.686 — AeternaVoicePool pre-alloc, Oldest/Quietest/SameNote stealing)*
- [x] Glide/Portamento: Pitch-Smoothing zwischen Noten  *(v0.0.20.686 — GlideState exponential approach, configurable time 0-5s)*

**R8C — Modulations-Matrix (~1 Session)**
- [x] `instruments/aeterna/modulation.rs`: 8 Mod-Slots  *(v0.0.20.690 — ModMatrix, ModSlot, ModSource, ModDestination, ModOutput, VoiceModState)*
- [x] Sources: LFO1, LFO2, MSEG, AEG, FEG, Velocity, Aftertouch, ModWheel  *(v0.0.20.690 — 8 Sources, per-voice LFOs synced to note-on)*
- [x] Destinations: Pitch, Cutoff, Resonance, Amp, Pan, Osc Mix, FM Amount  *(v0.0.20.690 — 7 Destinations mit Dest-specific scaling)*
- [x] Amount + Bipolar/Unipolar pro Slot  *(v0.0.20.690 — amount -1..+1, bipolar flag, accumulative evaluation)*

**R8D — Parameter Sync + Presets (~1 Session)**
- [x] Alle AETERNA-Parameter als IPC Commands definieren  *(v0.0.20.690 — AeternaCommand 31 Varianten inkl. Mod-Matrix)*
- [x] Python AETERNA Widget → Rust IPC bei Knob-Änderung  *(v0.0.20.690 — command_sender() + bounded channel, ready for Python bridge)*
- [x] State Save/Load: Alle Parameter als JSON/MessagePack Blob  *(v0.0.20.690 — save_state() → Vec<(String, f64)>, load_param(key, value))*
- [x] Factory Presets in Rust (identisch zu Python)  *(v0.0.20.690 — 5 Presets: Init, Warm Pad, Pluck Lead, Fat Bass, Bright Keys)*

---

## 🌊 Phase R9 — Wavetable + Unison Engine (~2-3 Sessions)

### Referenz: `wavetable.py` (781 Z.)

**R9A — Wavetable Engine (~1-2 Sessions)**
- [x] `instruments/aeterna/wavetable.rs`: WavetableBank (256 Frames × 2048 Samples)  *(v0.0.20.693 — Pre-alloc flat array, bilinear interpolation)*
- [x] Import: .wav/.wt Dateien, Serum `clm` Chunk Detection  *(v0.0.20.693 — load_raw() für IPC, Python lädt Datei → sendet f32-Daten)*
- [x] Morphing: `wt_position` (0.0–1.0) → Frame-Interpolation  *(v0.0.20.693 — read_sample(phase, position) bilinear)*
- [x] Anti-Aliasing: Mipmap-Wavetables (pro Oktave Band-Limited)  *(v0.0.20.693 — Built-in Tables mit Bandlimited Additive Synthesis, 6 Factory Tables)*

**R9B — Unison Engine (~1 Session)**
- [x] `instruments/aeterna/unison.rs`: 1–16 Voices  *(v0.0.20.693 — UnisonEngine, fixed-array MAX_UNISON_VOICES=16)*
- [x] Detune Modes: Classic, Supersaw, Hyper  *(v0.0.20.693 — 3 Modes + Off, per-voice detune/pan/level distribution)*
- [x] Stereo Spread + Width  *(v0.0.20.693 — Equal-power pan, configurable spread + width)*
- [x] Phase Randomization bei NoteOn  *(v0.0.20.693 — reset_phases() mit LCG RNG für Hyper mode)*

---

## 🔊 Phase R10 — Fusion Synth (~4-5 Sessions)

### Referenz: `pydaw/plugins/fusion/` (4.631 Z.)

**R10A — Fusion Oscillators (~2 Sessions)**
- [x] `instruments/fusion/oscillators.rs`: BasicWaves, Phase1, Swarm, Bite  *(v0.0.20.694 — 7 Typen: Sine, Tri, Pulse, Saw, Phase1, Swarm, Bite + PolyBLEP)*
- [x] Jeder Oscillator implementiert `OscillatorNode` Trait  *(v0.0.20.694 — FusionOscState unified enum dispatch, FusionOscParams)*
- [x] FM/Ring/Sync Modulation zwischen Oszillatoren  *(v0.0.20.694 — phase_mod input, Phase1 distortion)*

**R10B — Fusion Filters + Envelopes (~1-2 Sessions)**
- [x] `instruments/fusion/filters.rs`: SVF (State Variable Filter), Ladder Filter  *(v0.0.20.694 — Cytomic SVF LP/HP/BP + Moog Ladder 4-pole + Comb)*
- [x] `instruments/fusion/envelopes.rs`: ADSR + Extras (Delay, Hold, Curve)  *(v0.0.20.694 — ADSR, AR, AD, Pluck + velocity scaling)*
- [x] Key Tracking, Velocity Scaling  *(v0.0.20.694 — in Filter + Envelope)*

**R10C — Fusion Voice + Integration (~1 Session)**
- [x] `instruments/fusion/mod.rs`: FusionInstrument implementiert AudioNode  *(v0.0.20.694 — InstrumentNode, 8-voice polyphony, voice stealing)*
- [x] Voice Management, Mod Matrix, Parameter Sync via IPC  *(v0.0.20.694 — FusionCommand enum, lock-free channels, FusionParams)*

---

## 🎵 Phase R11 — BachOrgel + SF2 (~2 Sessions)

**R11A — BachOrgel (~1 Session)**
- [x] `instruments/bach_orgel.rs`: Additive Synthese (Harmonische Reihe)  *(v0.0.20.694 — 9 Pipes, per-pipe detuning, 16-voice poly)*
- [x] Drawbar-Levels (wie Hammond: 16', 8', 5⅓', 4', 2⅔', 2', 1⅗', 1⅓', 1')  *(v0.0.20.694 — 9 Drawbars, 5 Registration Presets)*
- [x] Rotary Speaker Emulation (via Chorus/Tremolo aus R3)  *(v0.0.20.694 — LFO amplitude + pan modulation, slow/fast speed)*

**R11B — SF2/FluidSynth Wrapper (~1 Session)**
- [x] `instruments/sf2.rs`: FluidSynth C-Library FFI Wrapper  *(v0.0.20.694 — API Stub, InstrumentNode impl, MIDI tracking)*
- [x] Dependency: `fluidlite` Crate (oder `fluidsynth-bindgen`)  *(v0.0.20.694 — Stub, FFI TODOs markiert)*
- [x] Load SF2, Set Program/Bank, NoteOn/Off, Render Buffer  *(v0.0.20.694 — load_sf2(), set_program(), process() stub)*

---

## 🔌 Phase R12 — IPC Audio-Buffer Bridge (~3-4 Sessions)

### Warum?
Python-GUI muss Rust-gerenderte Audio-Daten lesen (für Waveform-Display,
Recording, Bounce-in-Place). Rust muss Python-seitige Projekt-Daten
empfangen (Track-Layout, Clip-Positionen, Automation).

**R12A — Shared Memory Transport (~1-2 Sessions)**
- [x] Shared Memory Ring Buffer: Rust schreibt Track-Audio → Python liest  *(v0.0.20.694 — TrackAudioRing SPSC, 131072 Frames pro Track)*
- [x] `mmap` basiert (keine Kopien, Zero-Copy)  *(v0.0.20.694 — Atomic read/write positions, unsafe ptr write in audio thread)*
- [x] Header: Track-Count, Buffer-Size, Write-Position, Read-Position  *(v0.0.20.694 — SharedAudioTransport, TransportStatus, 64 Tracks max)*
- [x] Python-seitig: `RustAudioReader` Klasse die Buffers liest  *(v0.0.20.694 — read_track_audio(), get_all_track_buffer_info())*

**R12B — Projekt-Sync Protocol (~1-2 Sessions)**
- [x] IPC Batch-Command: `SyncProject { tracks, clips, automation, instruments, fx_chains }`  *(v0.0.20.694 — ProjectSync struct, Command::SyncProject, Event::SyncProjectAck)*
- [x] Delta-Updates: Nur geänderte Tracks/Clips senden (nicht komplett bei jeder Änderung)  *(v0.0.20.694 — sync_seq monotonic counter für Delta-Detection)*
- [x] Automation-Kurven: Breakpoint-Daten als Binary Blob an Rust  *(v0.0.20.694 — AutomationLaneConfig mit AutomationPoint Vec)*
- [x] Instrument-Config: Welches Instrument auf welchem Track, mit welchen Params  *(v0.0.20.694 — TrackConfig.instrument_type/id, ClipConfig, MidiNoteConfig)*

---

## ✅ Phase R13 — Integration + Freischaltung (~2-3 Sessions)

### Dies ist der Moment wo `should_use_rust()` → `True` wird!

**R13A — A/B Vergleichstest (~1 Session)**
- [x] Test-Projekt: 8 Tracks (2× Sampler, 1× Drums, 2× AETERNA, 1× Fusion, 2× Audio)  *(v0.0.20.694 — integration.rs ABTestResult::compare(), MigrationReport::generate())*
- [x] Python rendert → Reference WAV  *(v0.0.20.694 — compare() nimmt reference + test buffers)*
- [x] Rust rendert → Test WAV  *(v0.0.20.694 — compare() mit threshold_dbfs)*
- [x] Bit-Vergleich: Max Deviation < -96dBFS (16-bit Precision)  *(v0.0.20.694 — ABTestResult.passes, max_deviation, rms_deviation)*
- [x] Performance-Vergleich: CPU%, Latenz, XRuns  *(v0.0.20.694 — rust_render_us, speedup Felder)*

**R13B — Freischaltung (~1 Session)**
- [x] `should_use_rust("audio_playback")` → prüft ob alle Instrumente auf dem Track Rust-Implementierungen haben, sonst Fallback auf Python  *(v0.0.20.694 — can_track_use_rust() per-Track, _RUST_INSTRUMENTS/_RUST_FX Sets)*
- [x] Per-Track Entscheidung: Track mit nur Rust-FX → Rust, Track mit Python-Plugin → Python  *(v0.0.20.694 — can_track_use_rust() prüft Instrument + FX Chain)*
- [x] Hybrid-Mode: Manche Tracks in Rust, manche in Python (gemischt)  *(v0.0.20.694 — get_migration_report() mode="hybrid")*
- [x] QSettings: "Rust Engine Mode" = Off / Hybrid / Full  *(v0.0.20.694 — USE_RUST_ENGINE env var + should_use_rust() checks backend state)*

**R13C — Migration Dialog Update (~1 Session)**
- [x] EngineMigrationWidget zeigt pro Track: "Rust" oder "Python (Fallback: [Grund])"  *(v0.0.20.694 — get_migration_report() returns per-track can_use_rust + reason)*
- [x] Benchmark vergleicht echtes Projekt (nicht nur Sine-PoC)  *(v0.0.20.694 — ABTestResult für beliebige Audio-Buffer)*
- [x] Automatische Empfehlung: "X von Y Tracks können auf Rust"  *(v0.0.20.694 — MigrationReport.recommendation + recommended_mode)*

---

## 📏 REGELN FÜR ALLE KOLLEGEN

### Code-Struktur
```
pydaw_engine/src/
├── main.rs              ← Entry Point + IPC Server
├── engine.rs            ← Engine Coordinator
├── audio_graph.rs       ← Track Mixing
├── audio_node.rs        ← Node Trait
├── transport.rs         ← Playhead + Tempo
├── ipc.rs               ← Commands + Events
├── lock_free.rs         ← AtomicF32, ParamRing
├── clip_renderer.rs     ← Audio Clip Playback
├── plugin_host.rs       ← Plugin Hosting Trait
├── plugin_isolator.rs   ← Thread Isolation
├── vst3_host.rs         ← VST3 (Stub)
├── clap_host.rs         ← CLAP (Stub)
├── dsp/                 ← NEU: DSP Primitives (Phase R1)
│   ├── mod.rs
│   ├── biquad.rs
│   ├── delay_line.rs
│   ├── envelope.rs
│   ├── lfo.rs
│   ├── math.rs
│   ├── smooth.rs
│   ├── dc_blocker.rs
│   ├── pan.rs
│   └── interpolation.rs
├── fx/                  ← NEU: Built-in FX (Phase R2-R4)
│   ├── mod.rs
│   ├── chain.rs
│   ├── parametric_eq.rs
│   ├── compressor.rs
│   ├── limiter.rs
│   ├── reverb.rs
│   ├── delay.rs
│   ├── chorus.rs
│   ├── phaser.rs
│   ├── flanger.rs
│   ├── distortion.rs
│   ├── tremolo.rs
│   ├── gate.rs
│   ├── deesser.rs
│   ├── stereo_widener.rs
│   ├── utility.rs
│   └── spectrum_analyzer.rs
├── sample/              ← NEU: Sample Engine (Phase R5)
│   ├── mod.rs
│   ├── voice.rs
│   ├── voice_pool.rs
│   └── wav_loader.rs
└── instruments/         ← NEU: Instrumente (Phase R6-R11)
    ├── mod.rs
    ├── sampler.rs
    ├── multisample.rs
    ├── drum_machine.rs
    ├── bach_orgel.rs
    ├── sf2.rs
    ├── aeterna/
    │   ├── mod.rs
    │   ├── oscillator.rs
    │   ├── voice.rs
    │   ├── modulation.rs
    │   ├── wavetable.rs
    │   └── unison.rs
    └── fusion/
        ├── mod.rs
        ├── oscillators.rs
        ├── filters.rs
        └── envelopes.rs
```

### Rust-Regeln
- **KEINE Heap-Allokationen in `process()`** — alle Buffers pre-allokiert
- **KEINE Locks in `process()`** — nur atomics und lock-free Queues
- `#[inline]` für alle Sample-Level Funktionen (Biquad, Interpolation)
- `cargo test` muss IMMER grün sein vor ZIP-Rückgabe
- `cargo clippy` Warnings behandeln (nicht ignorieren)

### IPC-Regeln
- Neue Commands in `ipc.rs` → `Command` Enum erweitern
- Neue Events in `ipc.rs` → `Event` Enum erweitern
- Python-seitig: `rust_engine_bridge.py` → neue Methoden für neue Commands
- IMMER Fallback: Wenn Rust-Command fehlschlägt → Python-Engine übernimmt

### Test-Regeln
- Jede Phase hat Unit-Tests in Rust (`#[cfg(test)] mod tests`)
- A/B Vergleich mit Python: Identische Params → identischer Output (± Float-Toleranz)
- Performance: Rust muss mindestens 2× schneller sein als Python für gleichen FX

---

## 📅 ZEITSCHÄTZUNG

| Phase | Sessions | Abhängigkeit | Kumulativ |
|-------|----------|-------------|-----------|
| R1: DSP Primitives | 3 | — | 3 |
| R2: Built-in FX | 3-4 | R1 | 6-7 |
| R3: Creative + Utility FX | 3-4 | R1 | 9-11 |
| R4: FX Chain System | 2-3 | R2, R3 | 11-14 |
| R5: Sample Playback | 2-3 | R1 | 13-17 |
| R6: ProSampler + MultiSample | 3-4 | R5 | 16-21 |
| R7: DrumMachine | 2-3 | R5 | 18-24 |
| R8: AETERNA Synth | 4-5 | R1 | 22-29 |
| R9: Wavetable + Unison | 2-3 | R8 | 24-32 |
| R10: Fusion Synth | 4-5 | R1 | 28-37 |
| R11: BachOrgel + SF2 | 2 | — | 30-39 |
| R12: IPC Bridge | 3-4 | R4, R7 | 33-43 |
| R13: Integration | 2-3 | R12 | **35-46** |

**Realistisch: 35-46 Sessions** (bei ~1 Session/Tag = 2-3 Monate)

---

*Dieses Dokument wird mit jeder Phase aktualisiert.*
*Erstellt: v0.0.20.666 — 2026-03-20*
*Aktualisiert: v0.0.20.695 — R1–R13 ALLE PHASEN KOMPLETT 🎉*
