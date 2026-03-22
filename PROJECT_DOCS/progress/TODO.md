## v0.0.20.726 — 🎵 MIDI Clip Scheduler + Instrument Auto-Load (Rust)

- [x] (Claude Opus 4.6, 2026-03-22): **midi_scheduler.rs** — NEU: Beat-accurate MIDI Clip Scheduling (300+ Zeilen, 7 Tests)
- [x] (Claude Opus 4.6, 2026-03-22): **engine.rs** — process_audio() MIDI-Dispatching: NoteOn/NoteOff an Instrumente
- [x] (Claude Opus 4.6, 2026-03-22): **engine.rs** — Stop/Seek: Scheduler reset + AllNotesOff (keine Stuck Notes)
- [x] (Claude Opus 4.6, 2026-03-22): **engine.rs** — apply_project_sync(): Auto-Load Instruments + Scheduler
- [x] (Claude Opus 4.6, 2026-03-22): **instruments/mod.rs** — chrono.* Prefix-Support (chrono.aeterna → Aeterna etc.)
- [x] (Claude Opus 4.6, 2026-03-22): **audio_graph.rs** — track_indices() für sichere Iteration
- [ ] AVAILABLE: `cargo build --release` + Live-Test mit MIDI-Instrumenten
- [ ] AVAILABLE: A/B Vergleich: Python vs Rust auf echtem Projekt
- [ ] AVAILABLE: Loop-Region Support im MidiScheduler

## v0.0.20.725 — 💀 Persistent Plugin Blacklist + Stability Hardening

- [x] (Claude Opus 4.6, 2026-03-22): **Persistent Blacklist** — plugin_probe.py: BlacklistEntry, JSON on disk, user-override, batch-probe
- [x] (Claude Opus 4.6, 2026-03-22): **Scanner Integration** — scan_all_with_probe(): excludiert blacklisted Plugins beim Scan
- [x] (Claude Opus 4.6, 2026-03-22): **Deferred Retry CLAP** — _retry_failed_vst_instruments: CLAP + Blacklist-Check
- [x] (Claude Opus 4.6, 2026-03-22): **Rust-Bridge Reconnect** — Auto-Reconnect + robustere Reader-Loop
- [x] (Claude Opus 4.6, 2026-03-22): **Blacklist-Dialog** — UI: 💀 Plugin-Blacklist… im Sandbox-Menü
- [x] (Claude Opus 4.6, 2026-03-22): **Fork-Probe Scanner** — _expand_multi_vst_plugins: Blacklist + fork vor pedalboard
- [x] (Claude Opus 4.6, 2026-03-22): **Browser Badges** — 💀 + dimming + Insert-Warnung
- [x] (Claude Opus 4.6, 2026-03-22): **FX-Chain Guards** — VST3/VST2/CLAP Blacklist-Prüfung in _compile_devices()
- [x] (Claude Opus 4.6, 2026-03-22): **Rust Scanner Merge** — Browser triggert ScanPlugins + mergt Ergebnisse additiv
- [ ] AVAILABLE: `cargo build --release` + Live-Test mit echten Plugins
- [ ] AVAILABLE: GUI-Integration: Plugin-Browser zeigt Rust-Scanner-Ergebnisse
- [ ] AVAILABLE: VST3 IBStream für echtes State Save/Load
- [ ] AVAILABLE: CLAP MIDI Event Injection (clap_event_note)

## v0.0.20.718 — 🔌 P7 IPC Integration (Plugin Hosting verdrahtet)

- [x] (Claude Opus 4.6, 2026-03-21): **P7** — engine.rs: ScanPlugins → 3 Scanner → PluginScanResult Event
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — engine.rs: LoadPlugin → echte Vst3/Clap/Lv2 Instanziierung
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — engine.rs: Unload/SetParam/SaveState/LoadState Handler
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — audio_graph.rs: TrackNode.plugin_slots + Signal-Flow
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — ipc.rs: ScanPlugins, PluginScanResult, PluginLoaded, ScannedPlugin
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — clip_renderer.rs: base64_encode()
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — rust_engine_bridge.py: 6 Methoden + 2 Signals + 2 Event-Handler
- [x] (Claude Opus 4.6, 2026-03-21): **Fix** — 5 Compiler-Warnings behoben (0 warnings, 0 errors, 286 tests)
- [ ] AVAILABLE: `cargo build --release` + Live-Test mit echten Plugins
- [ ] AVAILABLE: GUI-Integration: Plugin-Browser zeigt Rust-Scanner Ergebnisse
- [ ] AVAILABLE: VST3 IBStream für echtes State Save/Load
- [ ] AVAILABLE: CLAP MIDI Event Injection (clap_event_note)

## v0.0.20.716 — 🦀 P7A/P7B/P7C Rust Native Plugin Hosting (Real FFI)

- [x] (Claude Opus 4.6, 2026-03-21): **P7A** — vst3_host.rs: Real COM FFI via libloading (780 Z.)
- [x] (Claude Opus 4.6, 2026-03-21): **P7B** — clap_host.rs: Real CLAP C FFI via libloading (782 Z.)
- [x] (Claude Opus 4.6, 2026-03-21): **P7C** — lv2_host.rs: Real lilv FFI via libloading+OnceLock (660 Z.)
- [x] (Claude Opus 4.6, 2026-03-21): **Infra** — Cargo.toml: libloading=0.8, Stub-Kommentare entfernt
- [ ] AVAILABLE: `cargo build --release` kompilieren + testen
- [ ] AVAILABLE: VST3 IBStream (MemoryStream) für State Save/Load
- [ ] AVAILABLE: CLAP MIDI Event Injection (clap_event_note)
- [ ] AVAILABLE: LV2 Atom Port MIDI + LV2 State Interface
- [ ] AVAILABLE: Live-Test mit echten Plugins (Surge XT, Vital, Calf, etc.)

## v0.0.20.714 — 🔧 Rust Toolchain Auto-Setup für Endanwender

- [x] (Claude Opus 4.6, 2026-03-21): **DX** — start_daw.sh: cargo env auto-source, Build-Prompt, ALSA-Check
- [x] (Claude Opus 4.6, 2026-03-21): **DX** — setup_all.py: _source_cargo_env, _install_rust_system_deps, check_rust fix
- [x] (Claude Opus 4.6, 2026-03-21): **DX** — install.py: Bessere Hinweise (start_daw.sh, --with-rust)
- [ ] AVAILABLE: `python3 setup_all.py --with-rust` auf Zielmaschine testen
- [ ] AVAILABLE: P7A-C — Rust Native Plugin Hosting (vst3-sys, clap-sys)

## v0.0.20.713 — 🦀 P7C LV2 Host Scaffolding + Cargo.toml P7 Prep

- [x] (Claude Opus 4.6, 2026-03-21): **P7C** — lv2_host.rs (440 Zeilen): Lv2Instance, UridMap, Scanner, Ports
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — Cargo.toml Dependencies vorbereitet (libloading, clap-sys, pkg-config)
- [ ] AVAILABLE: `cargo build --release` → kompilieren + testen
- [ ] AVAILABLE: P7A — VST3 FFI (vst3-sys COM Bindings)
- [ ] AVAILABLE: P7B — CLAP FFI (clap-sys Bindings)

## v0.0.20.712 — 🦀 Rust IPC Commands + Engine Handlers (RA2 Rust-Side)

- [x] (Claude Opus 4.6, 2026-03-21): **RA2 Rust** — LoadSF2/LoadWavetable/MapSampleZone IPC Commands
- [x] (Claude Opus 4.6, 2026-03-21): **RA2 Rust** — 3 Engine Handler + base64_decode pub
- [ ] AVAILABLE: `cargo build --release` + Live-Test
- [ ] AVAILABLE: P7 (OPTIONAL) — Rust Native Plugin Hosting

## v0.0.20.711 — 🎵🖥️ RA2 Instrument Sync + P3B/P5B Editor Scaffolding

- [x] (Claude Opus 4.6, 2026-03-21): **RA2** — sync_drum_pads, sync_multisample_zones, sync_sf2, sync_wavetable
- [x] (Claude Opus 4.6, 2026-03-21): **P3B** — VST2 Editor via effEditOpen + X11 im Worker
- [x] (Claude Opus 4.6, 2026-03-21): **P5B** — CLAP GUI via clap_plugin_gui + X11 im Worker
- [ ] AVAILABLE: `cargo build --release` + Live-Test
- [ ] AVAILABLE: P7 (OPTIONAL) — Rust Native Plugin Hosting

## v0.0.20.710 — 🔧🦀 P2B Param Sync + RA1 Rust AudioGraph Rebuild

- [x] (Claude Opus 4.6, 2026-03-21): **P2B** — vst_gui_process.py Param-Poller in VST3 Worker integriert
- [x] (Claude Opus 4.6, 2026-03-21): **P2B** — param_changed Callback in SandboxProcessManager
- [x] (Claude Opus 4.6, 2026-03-21): **RA1 Rust** — apply_project_sync() in engine.rs (Tracks+Clips+Transport)
- [ ] AVAILABLE: `cargo build --release` + Live-Test
- [ ] AVAILABLE: P7 (OPTIONAL) — Rust Native Plugin Hosting

## v0.0.20.709 — 🛡️🔌 Plugin Sandbox Overrides + Latency PDC

- [x] (Claude Opus 4.6, 2026-03-21): **P6C** — Pro-Plugin Sandbox Override (Rechtsklick → In Sandbox / Ohne Sandbox)
- [x] (Claude Opus 4.6, 2026-03-21): **P2C** — Plugin Latency Report via IPC (get_latency in allen Workern)
- [x] (Claude Opus 4.6, 2026-03-21): **P4A** — Worker-eigene URID Map (frische lilv.World im Subprocess)
- [x] (Claude Opus 4.6, 2026-03-21): **RA4** — Hybrid Mode PDC (compute_hybrid_pdc, Rust↔Python sync)
- [ ] AVAILABLE: P7 (OPTIONAL) — Rust Native Plugin Hosting (vst3-sys, clack-host)
- [ ] AVAILABLE: Live-Test mit `USE_RUST_ENGINE=1 python3 main.py`
- [ ] AVAILABLE: A/B Bounce-Vergleich Python vs Rust

## v0.0.20.708 — 🎵🔌🔀✅ Rust Pipeline RA2+RA3+RA4+RA5

- [x] (Claude Opus 4.6, 2026-03-21): **RA2** — rust_sample_sync.py: WAV→Base64, Chunking, Cache, SetArrangement
- [x] (Claude Opus 4.6, 2026-03-21): **RA3** — rust_audio_takeover.py: Python→Rust Engine Handoff, Event Wiring, Fallback
- [x] (Claude Opus 4.6, 2026-03-21): **RA4** — rust_hybrid_engine.py: Per-Track Backend-Zuweisung, Hybrid Mix
- [x] (Claude Opus 4.6, 2026-03-21): **RA5** — EngineMode Enum (Python/Hybrid/Rust), QSettings, Auto-Downgrade, A/B Test API
- [ ] AVAILABLE: Praxistest mit `cargo build --release` + echtem Projekt
- [ ] AVAILABLE: P7 (OPTIONAL) — Rust Native Plugin Hosting

## v0.0.20.707 — 🦀 Rust Project Sync (RA1 Python-Seite)

- [x] (Claude Opus 4.6, 2026-03-21): **RA1** — rust_project_sync.py: serialize_project_sync + RustProjectSyncer
- [x] (Claude Opus 4.6, 2026-03-21): **RA1** — on_play/stop/seek/tempo/loop/track_param Methoden
- [ ] NEXT: RA1 Rust-seitig: AudioGraph Rebuild aus ProjectSync
- [ ] AVAILABLE: RA2 — Sample-Daten an Rust (WAV Base64)
- [ ] AVAILABLE: RA3 — Rust übernimmt Audio-Device

## v0.0.20.706 — 🔌 Format-Worker komplett (P3/P4/P5)

- [x] (Claude Opus 4.6, 2026-03-21): **P3** — vst2_worker.py: FX+Instrument, MIDI, State
- [x] (Claude Opus 4.6, 2026-03-21): **P4** — lv2_ladspa_worker.py: LV2+LADSPA, State/Snapshot
- [x] (Claude Opus 4.6, 2026-03-21): **P5** — clap_worker.py: FX+Instrument, MIDI, Editor
- [x] (Claude Opus 4.6, 2026-03-21): **Routing** — 5-Format auto-dispatch in SandboxProcessManager
- [ ] NEXT: Rust Audio Pipeline RA1 oder P7 Rust Native Hosting (optional)
- [ ] AVAILABLE: Praxistest: Plugin Sandbox mit echten VST3/CLAP Plugins

## v0.0.20.705 — 🎸 VST3 Sandbox Worker (P2A/P2B/P2C)

- [x] (Claude Opus 4.6, 2026-03-21): **P2A** — vst3_worker.py: Audio-Loop, Params, State, CLI
- [x] (Claude Opus 4.6, 2026-03-21): **P2B** — ShowEditor/HideEditor IPC + Worker-GUI
- [x] (Claude Opus 4.6, 2026-03-21): **P2C** — MIDI IPC, Instrument-Mode, SandboxedFx.pull()
- [ ] NEXT: Phase P3A — VST2 Worker Process (ctypes im Subprocess)
- [ ] AVAILABLE: Phase P4A — LV2 Worker (lilv im Subprocess)
- [ ] AVAILABLE: Phase P5A — CLAP Worker (ctypes im Subprocess)

## v0.0.20.704 — 🛡️ Crash Recovery UI (P6 komplett)

- [x] (Claude Opus 4.6, 2026-03-21): **P6A** — Mixer CrashIndicatorBadge + roter Rand + set_sandbox_state()
- [x] (Claude Opus 4.6, 2026-03-21): **P6B** — CrashLog verdrahtet, factory_restart(), CrashLogDialog
- [x] (Claude Opus 4.6, 2026-03-21): **P6C** — Audio→Plugin Sandbox Untermenü, SandboxStatusDialog
- [x] (Claude Opus 4.6, 2026-03-21): **P1C Rest** — AudioSettingsDialog Sandbox-Toggle
- [ ] NEXT: Phase P2A — VST3 Worker Process (pedalboard im Subprocess)
- [ ] AVAILABLE: Phase P2B — VST3 GUI im Worker-Prozess
- [ ] AVAILABLE: Phase P2C — VST3 Instrument Sandbox

## v0.0.20.695 — 🎉 RUST DSP MIGRATION R1–R13 KOMPLETT

- [x] (Claude Opus 4.6, 2026-03-21): **R8** — AETERNA komplett (Osc+Voice+Filter+Mod+Presets)
- [x] (Claude Opus 4.6, 2026-03-21): **R9** — Wavetable + Unison Engine
- [x] (Claude Opus 4.6, 2026-03-21): **R10** — Fusion Synth komplett (Osc+Filter+Env+Voice)
- [x] (Claude Opus 4.6, 2026-03-21): **R11** — BachOrgel + SF2 Stub
- [x] (Claude Opus 4.6, 2026-03-21): **R12** — IPC Audio Bridge + Project Sync
- [x] (Claude Opus 4.6, 2026-03-21): **R13** — Integration + A/B Test + Migration Report
- [ ] NEXT: Live-Test mit USE_RUST_ENGINE=1, A/B Vergleich, Performance-Messung

## v0.0.20.694 — Phase R9+R10: Wavetable+Unison+Fusion (Rust)

- [x] (Claude Opus 4.6, 2026-03-21): **R9A+B** — wavetable.rs + unison.rs
- [x] (Claude Opus 4.6, 2026-03-21): **R10A** — fusion/oscillators.rs (7 Typen, PolyBLEP)
- [x] (Claude Opus 4.6, 2026-03-21): **R10B** — fusion/filters.rs (SVF+Ladder+Comb) + envelopes.rs (ADSR+AR+AD+Pluck)
- [x] (Claude Opus 4.6, 2026-03-21): **R10C** — fusion/mod.rs (FusionInstrument, 8-voice, Factory)
- [ ] AVAILABLE: **R11A — BachOrgel** — Additive Synthese, 9 Drawbars, Rotary Speaker
- [ ] AVAILABLE: **R11B — SF2 Wrapper** — FluidSynth FFI, Load/Program/Render

## v0.0.20.693 — Phase R9: Wavetable + Unison Engine (Rust)

- [x] (Claude Opus 4.6, 2026-03-21): **R9A** — wavetable.rs, WavetableBank, 6 Built-in Tables, bilinear interpolation
- [x] (Claude Opus 4.6, 2026-03-21): **R9B** — unison.rs, UnisonEngine, Classic/Supersaw/Hyper, 16 Voices
- [x] (Claude Opus 4.6, 2026-03-21): **Revert** — Python AETERNA note_off/trigger_note zurück auf Original
- [ ] AVAILABLE: **R10A — Fusion Oscillators** — BasicWaves, Swarm, Scrawl, Wavetable
- [ ] AVAILABLE: **R10B — Fusion Filters + Envelopes** — SVF, Ladder, ADSR+

## v0.0.20.690 — Phase R8 komplett: AETERNA Voice+Filter+Modulation+Presets (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R8B** — voice.rs, AeternaVoicePool, AeternaInstrument InstrumentNode
- [x] (Claude Opus 4.6, 2026-03-20): **R8C** — modulation.rs, 8 Mod-Slots, LFO/ENV/MIDI Sources, 7 Destinations
- [x] (Claude Opus 4.6, 2026-03-20): **R8D** — State Save/Load, 5 Factory Presets, 31 IPC Commands
- [x] (Claude Opus 4.6, 2026-03-20): **Bugfix** — Python AETERNA note_off per-Pitch, trigger_note AEG Release
- [ ] AVAILABLE: **R9A — Wavetable Engine** — WavetableBank, Frame-Interpolation, Mipmap Anti-Aliasing
- [ ] AVAILABLE: **R9B — Unison Engine** — Classic/Supersaw/Hyper, Phase Randomization

## v0.0.20.686 — Phase R8B: AETERNA Voice + Filter (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R8B — voice.rs** — AeternaVoice = Osc + Filter + AEG/FEG + Glide
- [x] (Claude Opus 4.6, 2026-03-20): **R8B — Biquad Filter** — LP12/LP24/HP12/BP/Notch/Off, Key Tracking, FEG→Cutoff
- [x] (Claude Opus 4.6, 2026-03-20): **R8B — Voice Pool** — 32 Voices pre-allokiert, Oldest/Quietest/SameNote Stealing
- [x] (Claude Opus 4.6, 2026-03-20): **R8B — Glide/Portamento** — Exponentielles Pitch-Smoothing 0-5s
- [x] (Claude Opus 4.6, 2026-03-20): **R8B — AeternaInstrument** — InstrumentNode Trait, Factory, Command Channel
- [ ] AVAILABLE: **R8C — Modulations-Matrix** — 8 Mod-Slots, LFO/ENV/MSEG Sources → Pitch/Cutoff/Res/Amp/Pan
- [ ] AVAILABLE: **R8D — Parameter Sync + Presets** — IPC Commands, State Save/Load, Factory Presets

## v0.0.20.684 — Phase R8A: AETERNA Oszillatoren (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R8A — oscillator.rs** — Sine, Saw, Square, Triangle, White/Pink Noise, PolyBLEP AA
- [x] (Claude Opus 4.6, 2026-03-20): **R8A — FM Synthesis** — Phase Modulation mit fm_amount/fm_ratio
- [x] (Claude Opus 4.6, 2026-03-20): **R8A — Sub-Oscillator** — 1/2 Oktaven runter, Sine
- [x] (Claude Opus 4.6, 2026-03-20): **R8A — Unison Engine** — 1–16 Voices, Detune (Cents), Stereo Spread, equal-power pan
- [x] (Claude Opus 4.6, 2026-03-20): **R8A — Wave Morphing** — Continuous Sine↔Tri↔Saw↔Square (gen_morphed + process_morphed)
- [x] (Claude Opus 4.6, 2026-03-20): **R8A — 19 Unit-Tests** — Waveforms, range, symmetry, noise, morph, unison, FM, sub, polyblep
- [ ] AVAILABLE: **Phase R8B — AETERNA Voice + Filter** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.682 — Phase R7B: DrumMachine Multi-Output (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R7B — Per-Pad Output-Routing** — output_index auf DrumPad + DrumVoice, render_voices routet nach Index
- [x] (Claude Opus 4.6, 2026-03-20): **R7B — Aux Buffers** — Vec<AudioBuffer> pre-allokiert, aux_output_buffers() API
- [x] (Claude Opus 4.6, 2026-03-20): **R7B — IPC + Engine** — SetDrumPadOutput, SetDrumMultiOutput + 2 match-Arms + 2 Bridge-Methoden
- [x] (Claude Opus 4.6, 2026-03-20): **R7B — 4 neue Tests** — enable, routing, silence-check, disabled-fallback
- [ ] AVAILABLE: **Phase R8A — AETERNA Synth Oszillatoren** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.679 — Fix: Benchmark misst echte Rust-Render-Zeit

- [x] (Claude Opus 4.6, 2026-03-20): **Fix: engine.rs** — Instant::now() Timing um process_audio, Pong mit cpu_load+render_time_us
- [x] (Claude Opus 4.6, 2026-03-20): **Fix: ipc.rs** — Pong-Event render_time_us Feld
- [x] (Claude Opus 4.6, 2026-03-20): **Fix: Benchmark** — _bench_rust_audio liest render_time_us statt sleep(), _bench_rust_midi per-event-cost
- [x] (Claude Opus 4.6, 2026-03-20): **Fix: Bridge** — speichert _last_render_time_us aus Pong
- [ ] AVAILABLE: **Phase R7B — DrumMachine Multi-Output** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.678 — Phase R7A: DrumMachine Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R7A — DrumMachineInstrument** — 128 Pads, 64 Voices, Choke Groups, OneShot/Gate, GM Map (~620 Zeilen)
- [x] (Claude Opus 4.6, 2026-03-20): **R7A — IPC + Engine Dispatch** — 5 Commands + 5 match-Arms
- [x] (Claude Opus 4.6, 2026-03-20): **R7A — Python Bridge** — 5 neue Methoden
- [x] (Claude Opus 4.6, 2026-03-20): **R7A — 12 Unit-Tests** — Choke, Retrigger, Gate, MultiPad, etc.
- [ ] AVAILABLE: **Phase R7B — DrumMachine Multi-Output** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.677 — Fix: Rust Compile Errors (R6B + Engine)

- [x] (Claude Opus 4.6, 2026-03-20): **Fix: 5× Borrow-Checker** — alloc_voice → alloc_voice_index (index-basiert statt &mut self)
- [x] (Claude Opus 4.6, 2026-03-20): **Fix: E0004 non-exhaustive** — 8 neue match-Arms in engine.rs für MultiSample-Commands
- [ ] AVAILABLE: **Phase R7A — DrumMachine Drum Pads** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.676 — Phase R6B: MultiSample Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R6B — MultiSampleInstrument** — Zone-mapped polyphonic sampler (~1050 Zeilen Rust)
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — SampleZone + MultiSampleMap** — 256 Zones, Key/Vel-Range, RR-Groups, Per-Zone DSP
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — Per-Zone DSP** — Biquad Filter, Amp+Filter ADSR, 2×LFO, 4 Mod-Slots
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — Auto-Mapping** — Chromatic/Drum/VelocityLayer Modi
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — IPC Commands** — 8 neue Commands in ipc.rs
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — Python Bridge** — 12 neue Methoden in rust_engine_bridge.py
- [x] (Claude Opus 4.6, 2026-03-20): **R6B — 18 Unit-Tests** — Zone-Filtering, RR, Polyphonie, AutoMap, Parsing
- [ ] AVAILABLE: **Phase R7A — DrumMachine Drum Pads** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.675 — Rust Compile Fixes (R6A)

- [x] (Claude Opus 4.6, 2026-03-20): **Fix: SampleData Debug** — impl Debug manuell (nur Metadaten, nicht Samples)
- [x] (Claude Opus 4.6, 2026-03-20): **Fix: unused variable ctx** — _ctx in ProSampler process()
- [ ] AVAILABLE: **Phase R6B — MultiSample / Advanced Sampler** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.674 — Phase R6A: ProSampler Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R6A — InstrumentNode Trait** — push_midi(), process(), as_any_mut(), MidiEvent Enum, InstrumentType Registry
- [x] (Claude Opus 4.6, 2026-03-20): **R6A — ProSamplerInstrument** — 64-Voice Polyphonie, ADSR, One-Shot/Loop, Velocity Curve, lock-free MIDI/Command Channels
- [x] (Claude Opus 4.6, 2026-03-20): **R6A — AudioGraph Integration** — TrackNode.instrument Feld, Instrument-Processing in Graph-Loop
- [x] (Claude Opus 4.6, 2026-03-20): **R6A — Engine MIDI-Routing** — NoteOn/Off/CC → Instrument, 5 neue IPC Commands
- [ ] AVAILABLE: **Phase R6B — MultiSample / Advanced Sampler** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.672 — Phase R5: Sample Playback Engine (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R5A — SampleData** — Arc-shared, WAV Loader (hound), Mono→Stereo, Resample, pitch_ratio
- [x] (Claude Opus 4.6, 2026-03-20): **R5B — SampleVoice** — note_on/off, ADSR, Cubic Interp, Forward/PingPong Loop, Velocity
- [x] (Claude Opus 4.6, 2026-03-20): **R5B — VoicePool** — Pre-allokiert (max 256), Oldest/Quietest/SameNote Stealing, render_all
- [x] (Claude Opus 4.6, 2026-03-20): **R6A erledigt** — ProSampler Instrument (siehe v0.0.20.674)

## v0.0.20.671 — 3 Test-Fixes (87/87 Tests grün)

## v0.0.20.669 — Phase R3 + R4: Creative/Utility FX + FX Chain (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R3A — Chorus** — 6 Voices, LFO-moduliert, Stereo Spread, Feedback
- [x] (Claude Opus 4.6, 2026-03-20): **R3A — Phaser** — 2–12 Allpass Stages, Exp. Sweep, ±Feedback
- [x] (Claude Opus 4.6, 2026-03-20): **R3A — Flanger** — Short Delay, Manual+LFO, ±Feedback
- [x] (Claude Opus 4.6, 2026-03-20): **R3A — Tremolo** — 6 LFO Shapes, Stereo Offset/Auto-Pan
- [x] (Claude Opus 4.6, 2026-03-20): **R3A — Distortion** — 5 Modi (Soft/Hard/Tube/Tape/Bitcrush), Tube Bug-Fix
- [x] (Claude Opus 4.6, 2026-03-20): **R3B — Gate** — Peak Envelope, Hold, Sidechain, Metering
- [x] (Claude Opus 4.6, 2026-03-20): **R3B — DeEsser** — Biquad BP Detection, Proportional Reduction
- [x] (Claude Opus 4.6, 2026-03-20): **R3B — Stereo Widener** — M/S, Width 0–2, Bass Mono Crossover
- [x] (Claude Opus 4.6, 2026-03-20): **R3B — Utility** — Gain, Pan, Phase Invert, Mono, DC Block
- [x] (Claude Opus 4.6, 2026-03-20): **R3B — Spectrum Analyzer** — Radix-2 FFT, Hanning, Peak Hold
- [x] (Claude Opus 4.6, 2026-03-20): **R4A — FX Chain** — AudioFxNode Trait, FxSlot, FxChain, Factory (15 FX)
- [x] (Claude Opus 4.6, 2026-03-20): **R4B — TrackNode Integration** — FxChain in AudioGraph, Pre/Post-Fader, IPC Commands/Events
- [ ] AVAILABLE: **Phase R5A — Sample Playback WAV Loader** → siehe RUST_DSP_MIGRATION_PLAN.md
- [ ] AVAILABLE: **Phase R5B — Voice + Playback Engine** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.667 — Rust DSP Primitives (Phase R1 KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **Phase R1A — Biquad Filter** — 8 Typen, DF2T, Stereo, 6 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **Phase R1B — Delay-Line + ADSR + LFO** — Ringbuffer, Envelope, 6 Shapes
- [x] (Claude Opus 4.6, 2026-03-20): **Phase R1C — Math + Smoother + DC/Pan/Interp** — Utilities komplett
- [ ] AVAILABLE: **Phase R2A — Parametric EQ** → siehe RUST_DSP_MIGRATION_PLAN.md
- [ ] AVAILABLE: **Phase R2B — Compressor + Limiter** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.666 — CRITICAL: GUI Freeze + Silent Playback Fix

- [x] (Claude Opus 4.6, 2026-03-20): **Safety Gate** — `should_use_rust()` → False, Python-Engine als einziger Audio-Pfad
- [x] (Claude Opus 4.6, 2026-03-20): **Error-Flood-Schutz** — `_shutting_down` Flag, RuntimeError Guard in RustEngineBridge
- [x] (Claude Opus 4.6, 2026-03-20): **Graceful Disconnect** — sauberer Shutdown ohne Error-Logging
- [x] (Claude Opus 4.6, 2026-03-20): **Rust DSP Migration Plan erstellt** — 13 Phasen, 35-46 Sessions, PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md
- [ ] AVAILABLE: **Phase R1A — Biquad Filter Library** → siehe RUST_DSP_MIGRATION_PLAN.md
- [ ] AVAILABLE: **Phase R1B — Delay-Line + Envelope** → siehe RUST_DSP_MIGRATION_PLAN.md
- [ ] AVAILABLE: **Phase R1C — DSP Utilities** → siehe RUST_DSP_MIGRATION_PLAN.md

## v0.0.20.665 — Engine Migration Dialog Wiring

- [x] (Claude Opus 4.6, 2026-03-20): **Engine Migration Dialog** — fehlenden Slot `_on_engine_migration_dialog` in MainWindow implementiert

## v0.0.20.664 — Rust Engine Warnings Cleanup

- [x] (Claude Opus 4.6, 2026-03-20): **Rust Engine 61 Warnings beseitigt** — dead_code allow, 12 unused imports, TABLE const

## v0.0.20.663 — Responsive UI + Bug-Fix (ROADMAP KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **Bug-Fix scale_ai.py** — SCALES Import korrigiert, Backward-Compat-Alias
- [x] (Claude Opus 4.6, 2026-03-20): **Responsive Verdichtung TransportPanel** — 2-Tier resizeEvent, Pre/Post/Count-In + Punch/TS/Loop/Metro
- [x] (Claude Opus 4.6, 2026-03-20): **Responsive Verdichtung ToolBarPanel** — 2-Tier resizeEvent, Loop-Range + Follow/Loop
- [x] DONE: **Rust Warnings Cleanup** → erledigt in v0.0.20.664

## v0.0.20.662 — Engine Migration Controller (AP1 Phase 1D KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **EngineMigrationController** — 3 Subsysteme, Dependency-Chain, Hot-Swap, Cascade-Rollback, QSettings
- [x] (Claude Opus 4.6, 2026-03-20): **EnginePerformanceBenchmark** — A/B-Test Python vs Rust, Render-Timing, P95/P99, CPU-Load, XRuns
- [x] (Claude Opus 4.6, 2026-03-20): **Rust-Engine als Default** — set_rust_as_default(), nur wenn alle Subsysteme stabil
- [x] (Claude Opus 4.6, 2026-03-20): **AudioEngine Rust-Delegation** — start_arrangement_playback → Rust Bridge, Auto-Fallback
- [x] (Claude Opus 4.6, 2026-03-20): **EngineMigrationWidget** — Settings-UI, Benchmark-Runner, Quick-Actions
- [x] DONE: **UI Hotfix: Responsive Verdichtung** → erledigt in v0.0.20.663
- [ ] AVAILABLE: **Rust Binary kompilieren + Integrations-Test** (cargo build --release, Echtzeit-IPC-Test)

## v0.0.20.658 — DAWproject Roundtrip (AP10 Phase 10C)

- [x] (Claude Opus 4.6, 2026-03-20): **Plugin-Mapping** — dawproject_plugin_map.py: 28 Internal + VST3/CLAP/LV2, Well-Known DB, bidirektional
- [x] (Claude Opus 4.6, 2026-03-20): **Vollständiger Export** — Send-Export, Plugin-Mapping deviceIDs, FX-Chain Mapping
- [x] (Claude Opus 4.6, 2026-03-20): **Vollständiger Import** — Automation, Plugin States, Sends, Groups, Clip Extensions, Per-Note Expressions
- [x] (Claude Opus 4.6, 2026-03-20): **Roundtrip-Test** — Export→Import→Vergleich: Transport, Tracks, Clips, Notes, Automation, Sends
- [x] (Claude Opus 4.6, 2026-03-20): **Projekt-Versionierung** — ProjectVersionService: auto/manual Snapshots, SHA-256 Dedup, Manifest, Pruning
- [x] (Claude Opus 4.6, 2026-03-20): **Snapshot-Diff** — diff_snapshots(): Transport, Tracks, Clips, Automation, Media Vergleich
- [ ] AVAILABLE: **AP10 Phase 10D (Rest)** — Projekt-Sharing per Link, Collaborative Editing
- [ ] AVAILABLE: **AP1 Phase 1C — Rust Plugin-Hosting** (VST3/CLAP in Rust)
- [ ] AVAILABLE: **AP1 Phase 1D — Rust Migration** (Schrittweise Migration)

## v0.0.20.657 — AETERNA Wavetable Engine (AP7 Phase 7C)

- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Import** — WavetableBank: .wav/.wt, Serum clm-Chunk, 24-bit, Auto-Detection
- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Morphing** — wt_position Mod-Target, per-sample Position-Modulation, 3 Presets
- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Editor** — draw_frame(), FFT harmonics, 6 Built-in Tables, normalize
- [x] (Claude Opus 4.6, 2026-03-20): **Unison Engine** — Classic/Supersaw/Hyper, 1-16 Voices, Detune/Spread/Width
- [x] DONE: **AP10 Phase 10C — DAWproject Roundtrip** (Export/Import mit Plugins)
- [ ] AVAILABLE: **AP1 Phase 1C — Rust Plugin-Hosting** (VST3/CLAP in Rust)
- [ ] AVAILABLE: **AP1 Phase 1D — Rust Migration** (Schrittweise Migration)

## v0.0.20.656 — Advanced Multi-Sample Sampler + Drum Rack (AP7 Phase 7A+7B)

- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Sample Mapping Editor** — ZoneMapCanvas 2D Key×Velocity Grid, ZoneInspector 5-Tab, Drag-Resize
- [x] (Claude Opus 4.6, 2026-03-20): **Round-Robin Gruppen** — MultiSampleMap RR-Counter, SampleZone.rr_group
- [x] (Claude Opus 4.6, 2026-03-20): **Sample-Start/End/Loop-Punkte** — LoopPoints dataclass, Sample-Tab im Inspector
- [x] (Claude Opus 4.6, 2026-03-20): **Filter + ADSR pro Zone** — ZoneFilter LP/HP/BP, ZoneEnvelope ADSR, EnvState Maschine
- [x] (Claude Opus 4.6, 2026-03-20): **Modulations-Matrix** — 4 Slots, 2 LFOs (5 Shapes), 7 Sources, 4 Destinations
- [x] (Claude Opus 4.6, 2026-03-20): **Auto-Mapping + Drag&Drop** — Chromatic/Drum/VelLayer/RR, Filename-Pattern-Detection
- [x] (Claude Opus 4.6, 2026-03-20): **Drum Rack Choke Groups** — DrumSlotState.choke_group 0-8, Engine silenciert Gruppe
- [x] (Claude Opus 4.6, 2026-03-20): **Drum Rack Pad-Bank Navigation** — A/B/C/D Banks, expand_slots(), Bank-aware UI
- [ ] AVAILABLE: **AP7 Phase 7C — Wavetable-Erweiterung AETERNA** (Import, Morphing, Editor, Unison)
- [ ] AVAILABLE: **AP10 Phase 10C — DAWproject Roundtrip**
- [ ] AVAILABLE: **AP1 Phase 1C — Rust Plugin-Hosting** (VST3/CLAP in Rust)

## v0.0.20.655 — Mixer Multi-Output UI + Collapse/Expand

- [x] (Claude Opus 4.6, 2026-03-20): **Mixer-Kontextmenü: Multi-Output** — Rechtsklick → 16 Child-Tracks erstellen, plugin_output_routing automatisch
- [x] (Claude Opus 4.6, 2026-03-20): **Collapse/Expand** — Pad-Kanäle ein-/ausblenden im Mixer, State überlebt Refresh
- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Output Deaktivierung** — Child-Tracks löschen, Reset auf Stereo
- [ ] AVAILABLE: **AP7 Phase 7A — Advanced Sampler** (Multi-Sample Mapping, Round-Robin)
- [ ] AVAILABLE: **AP10 Phase 10C — DAWproject Roundtrip**

## v0.0.20.654 — Drum Machine Multi-Output Engine

- [x] (Claude Opus 4.6, 2026-03-20): **DrumMachineEngine Multi-Output** — set_multi_output(), _pull_multi_output(), _slot_output_map, Zero-Alloc Buffer
- [x] (Claude Opus 4.6, 2026-03-20): **DrumMachineWidget Wiring** — Auto-Enable Multi-Output aus Track.plugin_output_count, _pydaw_output_count Tagging
- [x] (Claude Opus 4.6, 2026-03-20): **Fehlende Methoden** — set_fx_context() + rebuild_all_slot_fx() hinzugefügt
- [ ] AVAILABLE: **Mixer-UI: "Create Multi-Output Tracks" Button** — erstellt 16 Child-Tracks automatisch
- [ ] AVAILABLE: **AP7 Phase 7A — Advanced Sampler** (Multi-Sample Mapping, Round-Robin)

## v0.0.20.653 — CLAP Unified Presets + Multi-Output Wiring

- [x] (Claude Opus 4.6, 2026-03-20): **CLAP Unified PresetBrowserWidget** — Alten Preset-Timer entfernt, Undo-Notify integriert
- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Output Wiring in HybridAudioCallback** — _plugin_output_map, _mix_source_to_track(), Split-Routing in render_for_jack, AudioEngine rebuild
- [ ] AVAILABLE: **AP7 Phase 7A — Advanced Sampler** (Multi-Sample Mapping, Round-Robin, Multi-Output pull())
- [ ] AVAILABLE: **AP10 Phase 10C — DAWproject Roundtrip**

## v0.0.20.652 — Preset Browser & Plugin State Management

- [x] (Claude Opus 4.6, 2026-03-20): **AP4 Phase 4B — Preset-Browser** — PresetBrowserService, PresetBrowserWidget, VST3 Integration
- [x] (Claude Opus 4.6, 2026-03-20): **AP4 Phase 4C — Plugin-State Management** — PluginStateManager, Undo/Redo, Auto-Save
- [ ] AVAILABLE: **AP7 Phase 7A — Advanced Sampler** (Multi-Sample Mapping, Round-Robin, etc.)
- [ ] AVAILABLE: **AP10 Phase 10C — DAWproject Roundtrip**
- [ ] AVAILABLE: **AP1 Phase 1C — Rust Plugin-Hosting** (VST3/CLAP in Rust)

## v0.0.20.651 — Statusleisten-Tech-Signatur

- [x] (GPT-5.4 Thinking, 2026-03-20): **Qt/Python/Rust als gemeinsames Tech-Cluster gruppiert** — Alle drei Logos sitzen jetzt zusammen unten rechts in der Statusleiste statt über die UI verteilt.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Top-/Bottom-Bar beruhigt** — Python aus der oberen Tool-Leiste, Rust aus der Menümitte und Qt aus der linken Bottom-Nav entfernt.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Größe als Referenz beibehalten** — Einheitliche Signatur-Größe auf Basis des gewünschten Rust-Badges.
- [ ] AVAILABLE: **Optional UI-Feinschliff** — Statusleisten-Tech-Signatur bei Bedarf nur noch pixelgenau per Screenshot trimmen.
- [ ] AVAILABLE: **AP4 Phase 4B — Preset-Browser** (VST3/CLAP Preset-Scan, UI)

## v0.0.20.650 — Multi-Feature: Warp/Sandbox/MPE/MultiOut/Export

- [x] (Claude Opus 4.6, 2026-03-20): **AP3 3C: Clip-Warp im Arranger** — Warp-Marker Visualisierung, Stretch-Mode Kontextmenü, Auto-Warp
- [x] (Claude Opus 4.6, 2026-03-20): **AP4 4A: Sandboxed Plugin-Hosting** — PluginSandboxManager, SharedAudioBuffer, Crash-Detection, Auto-Restart
- [x] (Claude Opus 4.6, 2026-03-20): **AP5 5C: Multi-Output Plugins** — plugin_output_routing, create_plugin_output_tracks()
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 6B: MPE Support** — MPEProcessor, Channel-Allocator, Zone Config, Controller Presets
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 10B: Pre-/Post-FX Export** — fx_mode in ExportConfig, UI ComboBox
- [ ] AVAILABLE: **AP4 Phase 4B — Preset-Browser** (VST3/CLAP Preset-Scan, UI)
- [ ] AVAILABLE: **AP4 Phase 4C — Plugin-State Management** (Auto-Save, Undo/Redo)
- [ ] AVAILABLE: **AP10 Phase 10C — DAWproject Roundtrip**
- [ ] AVAILABLE: **AP7 Phase 7A — Advanced Sampler**

## v0.0.20.649 — Menümitte-Rust-Badge

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge exakt in die obere Menümitte gesetzt** — Badge sitzt jetzt als zentriertes Menüleisten-Overlay unter dem Fenstertitel statt rechts neben `1/16` oder hinter `Count-In`.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Transport-Leiste wieder freigeräumt** — Das Transport-Badge wurde entfernt, damit Transport/Snap/Browser oben nicht erneut gequetscht werden.
- [ ] AVAILABLE: **Responsive Verdichtung/Umbruch für sehr kleine Fensterbreiten**
- [ ] AVAILABLE: **AP3 Phase 3C Task 4 — Clip-Warp im Arranger**

## v0.0.20.648 — Rust-Badge in Topbar-Mitte + Snap-Lesbarkeit

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge naeher an die Topbar-Mitte verschoben** — Branding-Badge sitzt jetzt direkt hinter `Count-In` statt rechts neben `1/16`.
- [x] (GPT-5.4 Thinking, 2026-03-20): **`Zeiger` / `1/16` / `1/32` besser lesbar gemacht** — ComboBoxen breiter, Schrift und Dropdown-Zone groesser.
- [ ] AVAILABLE: **Screenshot-Feinjustierung** — Rust-Badge bei Bedarf noch pixelgenau nach dem naechsten Screenshot trimmen.
- [ ] AVAILABLE: **AP3 Phase 3C Task 4 — Clip-Warp im Arranger**

## v0.0.20.647 — Centered Rust Badge + Grid Visibility

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge zentriert** — eigenes Branding-Element jetzt mittig in der Tool-Leiste statt rechts in der Projekt-Tab-Leiste.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Topbar besser lesbar** — „Zeiger“, „1/16“ und „1/32“ durch breitere ComboBoxen und größere Dropdown-Fläche klarer erkennbar.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Rechte Symbolik ruhiger** — Python-Badge etwas größer, obere Leiste optisch entlastet.
- [ ] AVAILABLE: **AP3 Phase 3C Task 4 — Clip-Warp im Arranger**
- [ ] AVAILABLE: **Optional UI-Feinschliff** — Exakte Menümitten-/Badge-Feinjustierung anhand weiterer Screenshots
- [ ] AVAILABLE: **Optional UI-Feinschliff** — Responsive Verdichtung für sehr kleine Fensterbreiten

## v0.0.20.646 — Rust Logo Badge

- [x] (GPT-5.4 Thinking, 2026-03-20): **Eigenständiges Rust-Badge integriert** — eigenes Paint-Widget nahe Neues Projekt/Öffnen, bewusst ohne Vererbung vom Qt-Badge.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Erkennbarkeit erhöht** — Badge auf 30×30 px in leicht höherer Projekt-Tab-Leiste gesetzt.
- [ ] AVAILABLE: **AP3 Phase 3C Task 4 — Clip-Warp im Arranger**
- [ ] AVAILABLE: **Optional UI-Feinschliff** — Responsive Verdichtung für sehr kleine Fensterbreiten
- [ ] AVAILABLE: **Optional Branding-Feinschliff** — Rust-Badge alternativ in separaten Branding-Slot verschiebbar machen

## v0.0.20.645 — Toolbar Readability Hotfix

- [x] (GPT-5.2 Thinking, 2026-03-20): **Projekt-Tab-Leiste entzerrt** — Tabs liegen jetzt in einer eigenen Toolbar-Zeile statt Transport + Tools zusammenzuquetschen.
- [x] (GPT-5.2 Thinking, 2026-03-20): **Transport kompakter gemacht** — Kleinere Buttons/Felder, Pre/Post/Count-In ohne breite "Bars"-Suffixe.
- [x] (GPT-5.2 Thinking, 2026-03-20): **Rechter Kopfbereich lesbar gehalten** — Tool-Leiste und Python-Logo bekommen wieder Platz.
- [ ] AVAILABLE: **AP3 Phase 3C Task 4 — Clip-Warp im Arranger**
- [ ] AVAILABLE: **Optional UI-Feinschliff** — Responsive Verdichtung für sehr kleine Fensterbreiten

## v0.0.20.644 — Mega-Session: 7 Phasen komplett (AP8 8C + AP6 6A/6C + AP9 9A/9B/9C + AP10 10A/10B + AP3 3C)

- [x] (Claude Opus 4.6, 2026-03-20): **AP8 Phase 8C** — 5 Utility FX (Gate/De-Esser/Stereo Widener/Utility/Spectrum Analyzer) → **AP8 KOMPLETT**
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 Phase 6A** — MIDI Effects Chain: Note Echo, Velocity Curve, 16 Chord-Typen, Voicings, 13 Presets
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 Phase 6C** — Groove Templates: 12 Factory Grooves, Extract/Apply/Humanize
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9A** — Plugin-Parameter Discovery + Arm/Disarm + 13 Built-in FX Param Maps
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9B** — Relative/Trim Automation: AutomationLane.automation_mode, apply_mode()
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9C** — Automation Workflow: Snapshot, Clip-Copy, LOG/EXP/S_CURVE CurveTypes → **AP9 KOMPLETT**
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 Phase 10A** — Multi-Format Export: WAV/FLAC/MP3/OGG, Dither TPDF/POW-R, LUFS/Peak Normalize
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 Phase 10B** — Stem Export: per-Track Rendering, BPM Naming Convention (3/4 Tasks)
- [x] (Claude Opus 4.6, 2026-03-20): **AP3 Phase 3C Task 3** — Tempo-Automation: TempoMap, beat_to_time/time_to_beat, tempo_ratio_at_beat
- [ ] AVAILABLE: **AP6 Phase 6B — MPE Support** — Per-Note Pitch Bend, MPE Piano Roll
- [ ] AVAILABLE: **AP3 Phase 3C Task 4** — Clip-Warp im Arranger
- [ ] AVAILABLE: **AP10 Phase 10B Task 4** — Pre/Post-FX Export Optionen
- [ ] AVAILABLE: **AP10 Phase 10C** — DAWproject Roundtrip
- [ ] AVAILABLE: **AP1 Phase 1C** — Plugin-Hosting in Rust

## v0.0.20.643 — Creative FX + Scrawl + KI + UI Fix (AP8 8B ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP8 Phase 8B** — 5 Creative FX mit Scrawl-Zeichenfläche + KI Curve Generator
- [x] (Claude Opus 4.6, 2026-03-19): **Chorus/Phaser/Flanger/Distortion+/Tremolo** — Alle mit zeichenbarer Kurve
- [x] (Claude Opus 4.6, 2026-03-19): **KI Generate** — ki_generate_curve() erzeugt musikalisch sinnvolle Scrawl-Kurven
- [x] (Claude Opus 4.6, 2026-03-19): **UI Fix** — DevicePanel 9 Buttons → 2 Dropdown-Menüs (View + Zone)
- [ ] AVAILABLE: **AP8 Phase 8C — Utility FX** — Gate, De-Esser, Stereo Widener, Spectrum Analyzer
- [ ] AVAILABLE: **AP3 Phase 3C Tasks 3-4** — Tempo-Automation, Arranger-Warp
- [ ] AVAILABLE: **AP4 Phase 4A — Sandboxed Plugin-Hosting**

## v0.0.20.642 — Stretch-Modi + Essential FX (AP3 3B ✅ + AP8 8A ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP3 Phase 3B** — 5 Stretch-Modi (Beats/Texture/Re-Pitch/Complex + Tones existierte)
- [x] (Claude Opus 4.6, 2026-03-19): **Stretch Dispatch** — time_stretch_mono_mode/stereo_mode + Renderer Integration
- [x] (Claude Opus 4.6, 2026-03-19): **Audio Editor** — Stretch Mode ComboBox (5 Modi) + Handler
- [x] (Claude Opus 4.6, 2026-03-19): **AP8 Phase 8A** — 5 Essential FX DSP (EQ/Compressor/Reverb/Delay/Limiter)
- [x] (Claude Opus 4.6, 2026-03-19): **builtin_fx.py** — 5 professionelle DSP-Klassen, registriert in fx_chain
- [x] (Claude Opus 4.6, 2026-03-19): **FX Specs** — Proper defaults für alle 5 Essential FX
- [ ] AVAILABLE: **AP3 Phase 3C Tasks 3-4** — Tempo-Automation, Arranger-Warp
- [ ] AVAILABLE: **AP8 Phase 8B — Creative FX** — Chorus, Phaser, Flanger, Distortion+, Tremolo
- [ ] AVAILABLE: **AP4 Phase 4A — Sandboxed Plugin-Hosting**

## v0.0.20.641 — Sidechain + Routing + Warp (AP5 5B ✅ + 5C 3/4 + AP3 3A ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP5 Phase 5B** — Sidechain-Routing KOMPLETT (SC Model/Engine/FX/UI/Matrix)
- [x] (Claude Opus 4.6, 2026-03-19): **AP5 Phase 5C** — Patchbay Dialog, Output-Routing, Mono/Stereo Config
- [x] (Claude Opus 4.6, 2026-03-19): **AP3 Phase 3A** — WarpMarker Dataclass, detect_beat_positions(), auto_detect_warp_markers()
- [x] (Claude Opus 4.6, 2026-03-19): **Audio Editor** — Warp Markers Kontextmenü (Auto-Detect + Clear)
- [ ] AVAILABLE: **AP3 Phase 3B — Stretch-Modi** — Beats/Tones/Texture/Re-Pitch/Complex
- [ ] AVAILABLE: **AP5 Phase 5C Task 3 — Multi-Output Plugins** — benötigt AP4
- [ ] AVAILABLE: **AP4 Phase 4A — Sandboxed Plugin-Hosting** — Subprocess, Crash-Detection

## v0.0.20.640 — Comp-Tool + Routing Overlay (AP2 KOMPLETT ✅ / AP5 Phase 5A KOMPLETT ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **Comp-Methoden** — set_comp_region mit Split/Trim, get_active_clip_at_beat, comp_select_take_at
- [x] (Claude Opus 4.6, 2026-03-19): **Comp Interaktion** — Klick auf Take-Lane → comp_select_take_at, Status-Message
- [x] (Claude Opus 4.6, 2026-03-19): **Comp Visualisierung** — Farbige 4px-Bars am Track-Top, 5 Farben pro Clip
- [x] (Claude Opus 4.6, 2026-03-19): **Mixer Routing-Linien** — _RoutingOverlay Bezier-Kurven, farbkodiert, Opacity nach Amount
- [ ] AVAILABLE: **AP5 Phase 5B — Sidechain-Routing** — Sidechain-Input Selector, Track-zu-Track, Matrix
- [ ] AVAILABLE: **AP3 Phase 3A — Warp-Marker System** — Beat-Detection, manuelle Marker, elastisches Stretching

## v0.0.20.639 — Comping / Take-Lanes (AP2 Phase 2D)

- [x] (Claude Opus 4.6, 2026-03-19): **Datenmodell** — CompRegion, Clip.take_group_id/take_index/is_comp_active, Track.take_lanes_visible
- [x] (Claude Opus 4.6, 2026-03-19): **TakeService** — Komplett: create/get/set/add/delete/rename/flatten/toggle
- [x] (Claude Opus 4.6, 2026-03-19): **Loop-Recording** — RecordingService on_loop_boundary(), auto WAV pro Pass, Take-Gruppen
- [x] (Claude Opus 4.6, 2026-03-19): **Take-Lanes Arranger** — Visuelle Darstellung inaktiver Takes, Kontextmenü
- [x] (Claude Opus 4.6, 2026-03-19): **Verdrahtung** — MainWindow, Container, Transport loop_boundary_reached
- [ ] AVAILABLE: **Comp-Tool** — Bereiche aus verschiedenen Takes per Klick/Drag auswählen (CompRegion)
- [ ] AVAILABLE: **AP3 Phase 3A — Warp-Marker System** — Beat-Detection, manuelle Marker, elastisches Stretching
- [ ] AVAILABLE: **AP5 Phase 5A — Send/Return Tracks** — FX Return, Send-Knob, Pre/Post-Fader

## v0.0.20.638 — Punch Crossfade + Pre-Roll Auto-Seek (AP2 Phase 2C Abschluss)

- [x] (Claude Opus 4.6, 2026-03-19): **AudioConfig Singleton** — Konfigurierbare Crossfade-Länge 0-100ms, Default 10ms
- [x] (Claude Opus 4.6, 2026-03-19): **Punch Crossfade** — Linearer Fade-In/Out in _save_wav_for_track(), numpy-basiert
- [x] (Claude Opus 4.6, 2026-03-19): **Pre-Roll Auto-Seek** — Playhead → punch_in - pre_roll bei Record+Punch (Pro Tools/Logic Standard)
- [x] (Claude Opus 4.6, 2026-03-19): **Settings Wiring** — punch_crossfade_ms Key, Container lädt aus QSettings
- [ ] AVAILABLE: **AP2 Phase 2D — Comping / Take-Lanes** — Loop-Recording, Take-Lanes, Comp-Tool, Flatten

## v0.0.20.637 — Punch In/Out (AP2 Phase 2C)

- [x] (Claude Opus 4.6, 2026-03-19): **Punch-Region im Arranger** — Rote Marker, Drag-Handles, Kontextmenü, visuelles Overlay
- [x] (Claude Opus 4.6, 2026-03-19): **Automatisches Punch In/Out** — TransportService boundary detection, RecordingService auto-start/stop
- [x] (Claude Opus 4.6, 2026-03-19): **Pre-/Post-Roll** — SpinBoxes im Transport Panel, TransportService Berechnung
- [x] (Claude Opus 4.6, 2026-03-19): **Punch-Persistierung** — Project Model Felder, Restore bei Projekt-Öffnung
- [x] (Claude Opus 4.6, 2026-03-19): **MainWindow Verdrahtung** — Alle Signale Arranger↔Transport↔Recording, Punch-Sync bei Record-Start
- [ ] AVAILABLE: **Crossfade an Punch-Grenzen** — Kurzer Crossfade (5-50ms) am Punch-In/Out-Punkt
- [ ] AVAILABLE: **AP2 Phase 2D — Comping / Take-Lanes** — Loop-Recording, Take-Lanes, Comp-Tool, Flatten

## v0.0.20.636 — Multi-Track Recording (AP2 Phase 2B)

- [x] (Claude Opus 4.6, 2026-03-19): **Multi-Track Recording** — Mehrere armed Tracks gleichzeitig aufnehmen, separate WAV pro Track
- [x] (Claude Opus 4.6, 2026-03-19): **Input-Routing** — ComboBox im Mixer-Strip, Hardware-Input-Detection, Track.input_pair Sync
- [x] (Claude Opus 4.6, 2026-03-19): **Buffer-Size Settings** — ComboBox in AudioSettingsDialog (64-4096), Settings→RecordingService
- [x] (Claude Opus 4.6, 2026-03-19): **PDC Framework** — set/get_track_pdc_latency, Sample-Trimming bei WAV-Save, Beat-Korrektur
- [ ] AVAILABLE: **AP2 Phase 2C — Punch In/Out** — Region im Arranger, automatisches Punch, Crossfade an Grenzen
- [ ] AVAILABLE: **AP2 Phase 2D — Comping / Take-Lanes** — Loop-Recording, Take-Lanes, Comp-Tool, Flatten
- [ ] AVAILABLE: **PDC Auto-Read** — Plugin-Chains müssten get_latency() pro Plugin liefern

## v0.0.20.634 — Rust Build Fix (Arc Ownership + Warnings)

- [x] (Claude Opus 4.6, 2026-03-19): **Arc Clone Fix** — `engine_for_audio` dreifach geklont für drei separate Closures
- [x] (Claude Opus 4.6, 2026-03-19): **2 Warnings gefixt** — unused import + unused variable
- [ ] AVAILABLE: **`cargo build --release` erneut testen** — sollte jetzt fehlerfrei kompilieren

## v0.0.20.633 — Setup-Automatisierung (Alles-Macher Installer)

- [x] (Claude Opus 4.6, 2026-03-19): **setup_all.py** — Ein Befehl für alles: venv, Python-Deps, Audio-Check, optional Rust
- [x] (Claude Opus 4.6, 2026-03-19): **INSTALL.md** — Komplett neu geschrieben mit Schnellstart
- [x] (Claude Opus 4.6, 2026-03-19): **TEAM_SETUP_CHECKLIST.md** — Checkliste für alle Kollegen + Benutzer

## v0.0.20.632 — Audio Recording Phase 2A (Single-Track Recording)

- [x] (Claude Opus 4.6, 2026-03-19): **RecordingService Rewrite** — Backend Auto-Detection, Record-Arm, Count-In, 24-bit WAV, Auto Clip-Erstellung, Input Monitoring
- [x] (Claude Opus 4.6, 2026-03-19): **Mixer Record-Arm "R" Button** — Visuell + funktional, Model-Sync
- [x] (Claude Opus 4.6, 2026-03-19): **MainWindow Recording** — RecordingService statt direkt JACK, Legacy Fallback
- [ ] AVAILABLE: **AP2 Phase 2B — Multi-Track Recording** — Mehrere Tracks gleichzeitig, Input-Routing Matrix, PDC
- [ ] AVAILABLE: **AP2 Phase 2C — Punch In/Out** — Region im Arranger, Crossfade an Grenzen

## v0.0.20.631 — Rust Audio-Engine Phase 1B (AudioNode + ClipRenderer + Lock-Free)

- [x] (Claude Opus 4.6, 2026-03-19): **AudioNode Trait** — ProcessContext, GainNode, SilenceNode, SineNode, MixNode
- [x] (Claude Opus 4.6, 2026-03-19): **Lock-Free Rings** — ParamRing (SPSC 4096), AudioRing, MeterRing (Triple-Buffer)
- [x] (Claude Opus 4.6, 2026-03-19): **Clip Renderer** — ClipStore, ArrangementSnapshot (atomic swap), render_track() mit SR-Konvertierung
- [x] (Claude Opus 4.6, 2026-03-19): **Engine Integration** — ParamRing drain, Clip-Rendering im Audio-Callback, LoadAudioClip/SetArrangement
- [x] (Claude Opus 4.6, 2026-03-19): **Bridge erweitert** — load_audio_clip(), set_arrangement(), load_audio_clip_from_numpy()
- [ ] AVAILABLE: **AP1 Phase 1C — Plugin-Hosting in Rust** — VST3 via vst3-sys, CLAP via clack-host
- [ ] AVAILABLE: **`cargo build --release` auf Zielmaschine** — Testen ob cpal + ALSA/PipeWire funktioniert

## v0.0.20.630 — Rust Audio-Engine Phase 1A (Skeleton + IPC Bridge)

- [x] (Claude Opus 4.6, 2026-03-19): **Cargo-Projekt `pydaw_engine/`** — Vollständiges Rust-Projekt mit main.rs, audio_graph.rs, ipc.rs, plugin_host.rs, transport.rs, engine.rs
- [x] (Claude Opus 4.6, 2026-03-19): **IPC-Protokoll** — MessagePack über Unix Socket, vollständige Command/Event-Definitionen
- [x] (Claude Opus 4.6, 2026-03-19): **Python RustEngineBridge** — Singleton, Subprocess-Mgmt, typed API, PyQt6-Signale, Feature-Flag
- [x] (Claude Opus 4.6, 2026-03-19): **Sine-Wave PoC** — 440Hz Generator in Rust, Playhead + Metering → Python
- [ ] AVAILABLE: **AP1 Phase 1B — Audio-Graph in Rust** — AudioNode Trait, Audio-Clip Rendering, cpal Backend, Lock-Free Params, Metering
- [ ] AVAILABLE: **`cargo build --release` auf Zielmaschine** — Rust muss dort installiert sein

## v0.0.20.617 — Slot-Timer Repaint + Arranger Follow-Grid Fix

- [x] (Claude Opus 4.6, 2026-03-19): **Slot-Timer Repaint Fix** — Timer-Tick ruft `btn.update()` direkt auf aktiven Slot-Buttons auf. Vorher wurden nur Container-Widgets repainted → Countdown-Text blieb bei "0.0 Bar".
- [x] (Claude Opus 4.6, 2026-03-19): **Arranger Follow-Grid Fix** — Nach Follow-Scroll volles `self.update()` statt nur Playhead-Streifen. Grid, Clips und Hintergrund werden jetzt korrekt gezeichnet.
- [ ] AVAILABLE: **Phase F: Alte Direktverdrahtung abbauen** — Fallback-Transport-Connections entfernen wenn stabil getestet.

## v0.0.20.616 — Hotfix: Snapshot transport Attribut-Tippfehler

- [x] (Claude Opus 4.6, 2026-03-19): **self._transport → self.transport** — `get_runtime_snapshot()` las `self._transport.current_beat`, aber das Attribut heißt `self.transport`. try/except verschluckte den AttributeError → `cur_beat` immer 0.

## v0.0.20.615 — Launcher Slot Loop-Position Fix

- [x] (Claude Opus 4.6, 2026-03-19): **Slot Loop-Position zeigt korrekte Zeit** — `_get_loop_position_text()` nutzt jetzt `get_runtime_snapshot()` statt unsicherem `_voices`-Zugriff. Thread-sicher, korrekte Berechnung via `snap.local_beat`.
- [ ] AVAILABLE: **Phase F: Alte Direktverdrahtung abbauen** — Fallback-Transport-Connections entfernen wenn stabil getestet.

## v0.0.20.614 — CRITICAL: Clip Launcher Loop Fix + AudioEditor Adapter

- [x] (Claude Opus 4.6, 2026-03-19): **CRITICAL FIX: Clips loopen nicht** — Root Cause: Default Follow-Action `next_action='Stopp'` + `next_action_count=1` stoppte den Clip nach 1 Durchlauf. Fix: Wenn beide Actions 'Stopp' → return sofort (loop forever). Bitwig/Ableton-Verhalten.
- [x] (Claude Opus 4.6, 2026-03-19): **AudioEditor._local_playhead_beats Adapter-Integration** — `_last_adapter_beat` Instanzvariable, `_on_transport_playhead_changed()` speichert Adapter-Beat, `_local_playhead_beats()` nutzt gespeicherten Beat statt `transport.current_beat`. Fallback beibehalten.
- [x] (Claude Opus 4.6, 2026-03-19): **Launcher-Playhead im Slot-Button** → erledigt in v0.0.20.615.

## v0.0.20.613 — Dual-Clock Phase C live + E (Alle Editoren auf Adapter)

- [x] (Claude Opus 4.6, 2026-03-19): **Feature-Flag aktiviert** — `editor_dual_clock_enabled=True`. Arranger-Modus = Passthrough (identisch), Launcher-Modus = lokaler Slot-Beat.
- [x] (Claude Opus 4.6, 2026-03-19): **PianoRollEditor auf Adapter** — `editor_timeline` Parameter, Adapter-Playhead hat Vorrang, Fallback auf Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **NotationWidget auf Adapter** — `editor_timeline` Parameter, Adapter-Playhead, Click-to-Seek bleibt bei Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **AudioEventEditor auf Adapter** — `editor_timeline` Parameter, Adapter-Playhead, `playing_changed` bleibt bei Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **EditorTabs Durchreichung** — `editor_timeline` an alle 3 Editoren.
- [x] (Claude Opus 4.6, 2026-03-19): **MainWindow Wiring** — `editor_timeline` an EditorTabs übergeben.
- [x] (Claude Opus 4.6, 2026-03-19): **AudioEditor._local_playhead_beats** → erledigt in v0.0.20.614.

## v0.0.20.612 — Dual-Clock Architektur Phase A+B+C+D (Vorbau komplett)

- [x] (Claude Opus 4.6, 2026-03-19): **EditorFocusContext + LauncherSlotRuntimeState** — Neue frozen/mutable Dataclasses in `pydaw/services/editor_focus.py`. Beschreiben vollständig Clip + Quelle + Slot + Runtime-Referenz. Zentrale Formel: `local = loop_start + (global_beat - voice_start_beat) % span`.
- [x] (Claude Opus 4.6, 2026-03-19): **ClipLauncherPlaybackService.get_runtime_snapshot()** — GUI-sicherer Snapshot unter Lock aus `_voices`. Berechnet `local_beat` + `loop_count`. Kein UI-/Audio-Thread-Eingriff.
- [x] (Claude Opus 4.6, 2026-03-19): **EditorTimelineAdapter** — Zentrale Zeitumrechnung für alle Editoren (`pydaw/services/editor_timeline_adapter.py`). Arranger/Launcher-Umrechnung + 30Hz Snapshot-Polling.
- [x] (Claude Opus 4.6, 2026-03-19): **ClipContextService erweitert** — `editor_focus_changed` Signal + `set_editor_focus()` + `build_arranger_focus()` + `build_launcher_focus()` Factories.
- [x] (Claude Opus 4.6, 2026-03-19): **ServiceContainer Wiring** — `editor_timeline` Feld, Erstellung, `clip_context→adapter` Brücke, Shutdown.
- [x] (Claude Opus 4.6, 2026-03-19): **Phase D: Clip Launcher sendet echten Fokus** — `_emit_launcher_focus()` Helper bei Slot-Klick + `_launch()`. `MainWindow._on_clip_activated()` baut Arranger-Fokus (überspringt bei bestehendem Launcher-Fokus).
- [x] (Claude Opus 4.6, 2026-03-19): **Phase C live + Phase E** — Alle Editoren auf Adapter umgehängt → v0.0.20.613.

## v0.0.20.611 — QWERTZ Keyboard Layout Fix

- [x] (Claude Opus 4.6, 2026-03-18): **QWERTZ Auto-Detect** — Y/Z physisch vertauscht auf deutscher Tastatur. Locale-Erkennung via LANG/LC_ALL + locale.getlocale() für de_/at_/ch_/cs_/hu_/hr_/sl_/sk_.
- [x] (Claude Opus 4.6, 2026-03-18): **Overlay QWERTZ** — Zeigt korrekte Buchstaben (Z=G# oben, Y=C-1 unten) + Layout-Name "(QWERTZ)" im Header.
- [x] (Claude Opus 4.6, 2026-03-18): **Deprecated locale.getdefaultlocale** — Durch locale.getlocale() + env-var Fallback ersetzt.

## v0.0.20.610 — Hotfix + Computer Keyboard Overlay

- [x] (Claude Opus 4.6, 2026-03-18): **HOTFIX: UnboundLocalError QAction** — Redundanter `from PyQt6.QtGui import QAction` in try-Block entfernt (shadowed top-level import).
- [x] (Claude Opus 4.6, 2026-03-18): **Computer Keyboard Overlay** — Dezentes semi-transparentes Widget am unteren Rand mit Tastenbelegung, orange Highlight bei Tastendruck, Fade-Out, Slide-In Animation.
- [x] (Claude Opus 4.6, 2026-03-18): **key_pressed/key_released Signale** — ComputerKeyboardMidi emittiert Qt-Key-Codes für Overlay-Highlighting.

## v0.0.20.608 — Bitwig-Style MIDI Input Routing

- [x] (Claude Opus 4.6, 2026-03-18): **Track Model: midi_input Feld** — `midi_input: str = ""` mit Auto-Default (Instrument→"All ins", Audio/FX/Master→"No input").
- [x] (Claude Opus 4.6, 2026-03-18): **ProjectService: Setter + Helper** — `set_track_midi_input()` + `get_track_effective_midi_input()`.
- [x] (Claude Opus 4.6, 2026-03-18): **MidiManager: Source-Port Tagging** — Queue-Items als `(port, msg)` Tuples, `_midi_input_accepts()` Filter pro Track.
- [x] (Claude Opus 4.6, 2026-03-18): **MidiManager: inject_message() API** — Virtuelle MIDI-Quellen (Computer Keyboard, OSC, Track-Routing) einspeisen.
- [x] (Claude Opus 4.6, 2026-03-18): **Arranger UI: MIDI Input Dropdown** — Bitwig-Style Menü mit NOTE INPUTS / Add Controller / TRACKS Kategorien.
- [x] (Claude Opus 4.6, 2026-03-18): **Arranger UI: Output Label** — "→ Master" / "→ Group" pro Track-Row.
- [x] (Claude Opus 4.6, 2026-03-18): **MainWindow Wiring** — `arranger.set_midi_manager(services.midi)`.

## v0.0.20.609 — MIDI Input Routing Complete (5 Features)

- [x] (Claude Opus 4.6, 2026-03-18): **Computer Keyboard MIDI** — QWERTY→MIDI Service mit Bitwig-Layout (A-L=weiß, W/E/T/Y/U=schwarz), Event-Filter, Oktave-Shift (,/.), Ctrl+Shift+K Toggle.
- [x] (Claude Opus 4.6, 2026-03-18): **MIDI Channel Filter** — `midi_channel_filter: int = -1` auf Track, `_midi_channel_accepts()` in MidiManager, Omni/Ch 1-16 QComboBox pro Track.
- [x] (Claude Opus 4.6, 2026-03-18): **Touch Keyboard Widget** — On-Screen Piano (QPainter, 3 Oktaven, Click/Drag, Velocity), QDockWidget, Ctrl+Shift+T Toggle.
- [x] (Claude Opus 4.6, 2026-03-18): **Track-to-Track MIDI** — `forward_track_midi(source_track_id, msg)` API, Routing-Filter für `track:` prefix, ♪ Track-Einträge im Dropdown.
- [x] (Claude Opus 4.6, 2026-03-18): **OSC Input Source** — UDP Server `/note/on`, `/note/off`, `/cc`, Port 9000, graceful fallback.

## v0.0.20.606 — Kompaktes Layout: Slots, Inspector, Piano Roll Scroll

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Slots kompakter** — Grid Column Stretch + MinWidth 60, Track-Header MaxWidth 140, Countdown 56px.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Inspector schmaler** — MaxWidth 260, Default 200 (vorher 320), MinWidth 80.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Piano Roll scrollt zu Bar 1** — set_clip() setzt horizontalScrollBar auf 0.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Right Dock 28%** — resizeDocks begrenzt Browser/Launcher Dock auf ~28% Fensterbreite.

## v0.0.20.605 — ALLE 22 Items FERTIG: Recording, Crossfade, Multi-Drag, MIDI CC, Audio Rec, Morphing

- [x] (Claude Opus 4.6, 2026-03-18): **Overdub vs Replace** — MidiManager prüft launcher_record_mode, Replace löscht überlappende Noten.
- [x] (Claude Opus 4.6, 2026-03-18): **Record Quantize** — Noten beim Recording an Grid gesnapped.
- [x] (Claude Opus 4.6, 2026-03-18): **Crossfade Playback** — Echtes Sample-Level Crossfade bei Legato (_fading_voices + envelope).
- [x] (Claude Opus 4.6, 2026-03-18): **Scene Crossfade** — launch_scene nutzt launcher_scene_crossfade_ms.
- [x] (Claude Opus 4.6, 2026-03-18): **Multi-Slot Drag** — JSON MIME Encoding aller selektierten Clips.
- [x] (Claude Opus 4.6, 2026-03-18): **MIDI CC Dispatch** — Default CC 20-28 + Custom Mapping.
- [x] (Claude Opus 4.6, 2026-03-18): **Audio Recording** — ClipLauncherRecordService: sounddevice InputStream, WAV-Export, Clip-Creation.
- [x] (Claude Opus 4.6, 2026-03-18): **Punch In/Out** — Loop-basierte Region, Aufnahme nur im Punch-Bereich.
- [x] (Claude Opus 4.6, 2026-03-18): **Monitoring** — Input-Passthrough via get_monitor_buffer().
- [x] (Claude Opus 4.6, 2026-03-18): **Morphing** — _morph_variation_notes: Velocity-Blending + Timing-Humanization zwischen Variationen.

## v0.0.20.605 — Verbleibende 10 Items: Recording, Crossfade, Multi-Drag, MIDI CC

- [x] (Claude Opus 4.6, 2026-03-18): **Overdub vs Replace** — MidiManager prüft launcher_record_mode, Replace löscht überlappende Noten.
- [x] (Claude Opus 4.6, 2026-03-18): **Record Quantize** — Noten werden beim Recording an Grid (1/16–1 Bar) gesnapped.
- [x] (Claude Opus 4.6, 2026-03-18): **Crossfade Playback** — Echtes Sample-Level Crossfade bei Legato-Übergang (_fading_voices + fade envelope).
- [x] (Claude Opus 4.6, 2026-03-18): **Scene Crossfade** — launch_scene nutzt launcher_scene_crossfade_ms für sanfte Übergänge.
- [x] (Claude Opus 4.6, 2026-03-18): **Multi-Slot Drag** — Encoding aller selektierten Clips als JSON in MIME data.
- [x] (Claude Opus 4.6, 2026-03-18): **MIDI Controller CC** — Default CC 20-27=Scene 1-8, CC 28=Stop All + Custom Mapping.

## v0.0.20.604 — Verbleibende Features: Szenen-Farbe, Probability, Recording, Variationen, Smart Quantize

- [x] (Claude Opus 4.6, 2026-03-18): **Szenen-Farbe** — Rechtsklick auf Scene → 12-Farben Submenu, persistiert in launcher_scene_colors.
- [x] (Claude Opus 4.6, 2026-03-18): **Follow Action Probability** — Action A/B mit %-Chance (Ableton-Style Dual Actions).
- [x] (Claude Opus 4.6, 2026-03-18): **Recording Modes** — Overdub/Replace + Record Quantize (Off/1-16/1-8/1-4/1-Bar) im Rechtsklick-Menü.
- [x] (Claude Opus 4.6, 2026-03-18): **Clip-Variationen** — "+ Variation hinzufügen" erstellt Alt-Clip, launcher_alt_clips[] gespeichert.
- [x] (Claude Opus 4.6, 2026-03-18): **Random Variation** — Follow Actions wählen bei Launch zufällig aus Main+Variationen.
- [x] (Claude Opus 4.6, 2026-03-18): **Smart Quantize** — KI-Groove-Preservation: 40% Threshold, snapped nur nahe Noten, bewahrt Groove.

## v0.0.20.603 — Phase 5.2 + 5.3 + 6.1 + 6.2: Keyboard, Clip Info, KI Patterns, Scene-Chain

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Keyboard Shortcuts** — 1-8 startet Szenen, Enter startet selektierten Slot, Space togglet Play/Stop.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Clip-Länge Text** — "4 bar" Anzeige unten-rechts im Slot.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **KI MIDI Pattern Generator** — 10 Pattern-Typen (Arpeggio, Akkorde, Bass, Drums, Pentatonisch, Pad) per Rechtsklick-Menü.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Scene-Chain → Arranger** — "→ Arranger" Button überträgt Szenen-Reihenfolge als lineare Clips in den Arranger.

## v0.0.20.602 — Phase 4+5: MIDI Recording Wiring + Slot Zoom + Loop Bar

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **MIDI Recording Wiring** — launch_slot setzt `set_active_clip()` automatisch, MIDI-Manager schreibt in den richtigen Launcher-Clip.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Ctrl+Scroll Slot Zoom** — Slot-Höhe 28–120px einstellbar (Bitwig-Style).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop Region Bar** — Oranges Band am Slot-Boden zeigt Loop-Region innerhalb der Clip-Länge.

## v0.0.20.601 — Phase 3.2 + 3.3: Legato Mode + Launch Modes

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Legato vom Clip** — Neuer Clip startet an der Loop-Position des vorherigen Clips auf derselben Spur (nahtloser Übergang).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Legato vom Projekt** — Neuer Clip startet an der globalen Transport-Position innerhalb seines Loops.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Trigger Mode** — Klick auf ▶ startet, erneuter Klick stoppt (Toggle pro Slot).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Gate Mode** — Clip spielt nur solange der ▶-Button gedrückt ist (mouseUp = Stop).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **One-clip-per-track** — launch_slot stoppt automatisch alle anderen Clips auf derselben Spur.

## v0.0.20.600 — Phase 2.3 + Phase 3.1: Multi-Selektion + Follow Actions

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Ctrl+Click Multi-Selektion** — Toggle einzelner Slots in/aus der Auswahl.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Shift+Click Range-Selektion** — Rechteckige Bereich-Auswahl zwischen Anchor und Ziel.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Follow Actions (Ableton-Style)** — Nach N Loops automatisch nächsten/vorherigen/zufälligen/ersten/letzten Clip triggern. Loop-Counting im Audio-Thread, Action-Dispatch per GUI-Timer (100ms). Alle 13 Inspector-Aktionen unterstützt.

## v0.0.20.599 — Phase 2: Clip Umbenennen + Szenen-Management

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **F2 Rename** — F2 auf selektiertem Slot öffnet Inline-Textfeld zum Umbenennen. Enter bestätigt, Esc bricht ab.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Szene umbenennen** — Rechtsklick auf Scene-Header → "Szene umbenennen" → Inline-Textfeld.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Szene duplizieren** — Rechtsklick → "Szene duplizieren" klont alle Clips in eine neue Szene.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Szene löschen** — Rechtsklick → "Szene löschen" leert alle Slots der Szene.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Scene Names persistent** — `launcher_scene_names` Dict im Project-Model, wird gespeichert/geladen.

## v0.0.20.598 — Clip Launcher: Color Fix + Drop Fix + Masterplan

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Slot-Farbe sichtbar** — Alpha 45→80 (Hintergrund) + 200→255 (Streifen). Farben jetzt deutlich sichtbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Arranger→Launcher Drop** — Arranger-Clips werden beim Drop als launcher_only Kopie erstellt. Kein Auto-Launch mehr (Bitwig-Verhalten).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Ctrl+Drag Fix** — Drop-Handler überarbeitet, zuverlässiges Klonen.
- [x] DONE (Claude Opus 4.6, 2026-03-18): **CLIP_LAUNCHER_MASTERPLAN.md** — Kompletter 6-Phasen-Plan für Bitwig/Ableton Feature-Parity + eigene Innovationen.

## v0.0.20.597 — Fenster-Overflow: setMinimumSize entfernt

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **arranger_canvas** — `setMinimumSize(w,h)` → `resize(w,h)`. Canvas erzwingt nicht mehr das Hauptfenster breiter als der Bildschirm.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **pianoroll_canvas** — Gleicher Fix.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **main_window** — `setMinimumSize(400,300)`, editor/device dock `setMinimumHeight(0)`.

## v0.0.20.596 — Clip Launcher: Farbauswahl Fix + Slot-Hintergrund

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Farbauswahl funktioniert** — Mini-Piano-Roll liest jetzt `launcher_color` statt `color` (Feld existierte nicht).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Bitwig-Style Slot-Hintergrund** — Gefüllte Slots zeigen farbigen Hintergrund + 3px Farbstreifen links (12-Farben-Palette).

## v0.0.20.595 — Clip Launcher: Fenster-Overflow Fix + RT Loop Position

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Fenster-Overflow** — Inspector minWidth 220→120, Track-Header 180→100, Grid-Container+Inner Ignored SizePolicy, horizontaler Scrollbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **RT Loop Position** — Nutzt jetzt `voice.start_beat` aus ClipLauncherPlaybackService für akkurate Position (nicht nur Transport-Beat).

## v0.0.20.594 — Piano Roll: Fenster-Größe Fix + Loop Position im Slot

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Fenster-Overflow** — PianoRollEditor bekommt `SizePolicy.Preferred`, editor_dock minimumHeight 320→200, LayerPanel maxHeight 200→120.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop Position im Slot** — Spielende Clips zeigen jetzt "1.3 Bar" im Slot-Button (oranges Loop-Position-Label).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Timer läuft bei Playback** — Repaint-Timer stoppt nicht mehr wenn keine Queued-Launches da sind, solange Clips spielen.

## v0.0.20.593 — Piano Roll: Loop Playhead Wrap + Checkbox

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Playhead wrapped in Loop** — Rote Linie springt an Loop-End zurück zu Loop-Start (Bitwig-Verhalten).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **✓ Loop Checkbox** — Echte Checkbox statt Toggle-Button (wie im Arranger).

## v0.0.20.592 — Piano Roll: Loop Region Controls (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop L/Bar Spinboxes** im Piano Roll Header — Loop Start + End in Bars einstellbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Rechtsklick-Drag im Ruler** — Loop-Region ziehen (snap-to-bar), genau wie im Arranger.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop-Band Visualisierung** — Oranges Band im Ruler zeigt aktive Loop-Region.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop-Button funktional** — Schaltet Loop ein/aus und zeigt/versteckt Spinboxes.

## v0.0.20.591 — Clip Launcher: Bitwig-Style Loop Controls

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop Start Spinbox** — Editierbarer Loop-Start statt statischem Label.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop Länge → loop_end_beats** — Steuert jetzt die Loop-Region, nicht die Clip-Länge.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Separate Clip-Länge** — Neuer Spinbox für `length_beats` (unabhängig von Loop).
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes.

## v0.0.20.590 — Clip Launcher: Bitwig-Style Drag + Symbols

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Plain Drag Fix** — `setDown(False)` vor QDrag löst QPushButton Grab. Einfaches Ziehen funktioniert jetzt.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **▶ Play-Button** — Links-zentriert im Slot (Bitwig-Position), größeres Dreieck.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **● Record-Indikator** — Roter Kreis oben-rechts bei record-armed Track.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **■ Stop per Track** — Neuer Button im Track-Header, stoppt alle Clips der Spur.
- [ ] AVAILABLE: **Arranger→Launcher Drag** — Arranger-Clip in Launcher-Slot ziehen.
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes (Ableton-style).

## v0.0.20.589 — Clip Launcher → Arranger Drag&Drop

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Launcher→Arranger Drag** — Alt/Ctrl+Drag aus Launcher-Slot in Arranger erstellt eine Kopie mit `launcher_only=False`. Original bleibt im Launcher.
- [ ] AVAILABLE: **Arranger→Launcher Drag** — Arranger-Clip in Launcher-Slot ziehen (setzt `launcher_only=True` auf Kopie).
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes (Ableton-style).

## v0.0.20.589 — Clip Launcher → Arranger Drag&Drop (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Plain Drag** — Launcher-Slots starten DnD ohne Alt/Ctrl-Modifier (Bitwig-Verhalten).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Arranger akzeptiert Launcher-Clips** — Drop dupliziert den Clip und setzt `launcher_only=False` auf der Kopie.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Ghost-Preview** — Launcher→Arranger-Drag zeigt Ghost-Overlay mit Clip-Name und Icon.
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes (Ableton-style).
- [ ] AVAILABLE: **Clip Launcher per-Clip Launch Mode** — Per-clip trigger/toggle/gate override.
- [ ] AVAILABLE: **Clip Launcher Legato Mode** — Seamless handoff between clips on same track.

## v0.0.20.588 — Clip Launcher: launcher_only Flag (Bitwig-Style Separation)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **launcher_only Flag** — Launcher-Clips erscheinen NICHT mehr im Arranger. `clip.launcher_only = True` wird gesetzt bei Clip-Erstellung im Launcher.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **arrangement_renderer Filter** — `prepare_clips()` überspringt `launcher_only` Clips (kein doppeltes Playback).
- [ ] AVAILABLE: **Drag Launcher→Arranger** — Launcher-Clip per Drag&Drop in den Arranger ziehen (setzt `launcher_only=False` + positioniert).
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes (Ableton-style).

## v0.0.20.587 — Clip Launcher: MIDI Real-Time Playback + Creation

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **MIDI Realtime Dispatch** — Non-SF2 instruments (Pro Audio Sampler, Fusion, VST3, CLAP, Drum Machine) now play MIDI clips in Clip Launcher via SamplerRegistry note_on/note_off dispatch.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **MIDI Clip Creation** — Right-click or double-click empty slot creates MIDI/Audio clip directly in Clip Launcher (Bitwig-style).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Mini Piano-Roll** — MIDI clips show note visualization in slot buttons (pitch/time/velocity mapped, per-clip color).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop-aware MIDI** — Correct note_off at loop boundaries, polyphonic tracking, all_notes_off on stop/panic.
- [ ] AVAILABLE: **Clip Launcher MIDI Recording** — Arm slot + record MIDI input into launcher clip.
- [ ] AVAILABLE: **Clip Launcher Follow Actions** — Auto-trigger next clip after current finishes (Ableton-style).
- [ ] AVAILABLE: **Clip Launcher per-Clip Launch Mode** — Per-clip trigger/toggle/gate override.
- [ ] AVAILABLE: **Clip Launcher Legato Mode** — Seamless handoff between clips on same track.

## v0.0.20.586 — Bounce GUI-Freeze Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents alle 8 Blöcke** — `_render_vst_notes_offline` pumpte Qt nur alle 50 Blöcke (~1.5s Wallclock). Jetzt alle 8 Blöcke (~240ms). "main.py antwortet nicht" sollte nicht mehr erscheinen.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents in _render_engine_notes_offline** — fehlte komplett, jetzt alle 8 Blöcke.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents vor WAV-Write** — letzte Event-Loop-Pump bevor die große WAV geschrieben wird.

## v0.0.20.585 — Fusion Bounce in Place Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Fusion Bounce SILENT** — `_render_track_subset_offline()` hatte zwar einen Handler fuer `chrono.fusion`, aber `track.plugin_type` war leer. Neuer Auto-Detect-Mechanismus erkennt den Plugin-Typ aus `instrument_state`-Keys (`'fusion'` → `'chrono.fusion'`).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Fallback Engine-Erstellung** — Zweiter Fallback nach dem try/except erstellt Fusion-Engine direkt aus `instrument_state`, falls Auto-Detection nicht greift.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Bounce-Diagnostik** — `[BOUNCE]`-Log zeigt jetzt `instrument_state_keys` fuer schnelles Debugging.
- [ ] AVAILABLE: **FusionEngine Lock-Granularität** — `_voice_params_dirty` pro Modul statt global.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — LFO → Filter Cutoff / OSC Pitch / Pan etc.
- [ ] AVAILABLE: **Fusion: Unison/Detune auf Engine-Ebene** — Stereo Detune pro Voice.
- [ ] AVAILABLE: **Fusion: Effects Section** — Delay/Reverb/Chorus built-in.

## v0.0.20.584 — GUI Performance Deep-Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Signal-Kaskade eliminiert** — `FusionWidget._persist_instrument_state()` triggerte `project_updated` → 15+ UI-Panels machten Full-Refresh bei jedem Knob-Dreh. `_emit_updated()` entfernt.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Zentraler VU-Meter-Timer** — N per-Strip `QTimer(33ms)` durch einen einzigen `MixerPanel`-Timer ersetzt. Timer stoppt bei unsichtbarem Mixer. Reduktion: N×30fps → 1×30fps.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Transport + GL-Overlay 30fps** — Playhead-Timer und GL-Sync von 16ms auf 33ms reduziert (~60 weniger Callbacks/s).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Arranger Hover-Throttling** — Doppelte `_clip_at_pos()` zu einer verschmolzen, 50ms Throttle. Clip-Iteration: ~1000/s → ~20/s.
- [ ] AVAILABLE: **FusionEngine Lock-Granularität** — `_voice_params_dirty` pro Modul statt global (Low Priority, v577 hat bereits Lock-Free Pull).
- [ ] AVAILABLE: **Fusion: LFO Modulation** — LFO → Filter Cutoff / OSC Pitch / Pan etc.
- [ ] AVAILABLE: **Fusion: Unison/Detune auf Engine-Ebene** — Stereo Detune pro Voice (aktuell nur Swarm/Wavetable-spezifisch).
- [ ] AVAILABLE: **Fusion: Effects Section** — Delay/Reverb/Chorus built-in.

## v0.0.20.583 — Fusion Scrawl Hover-Repaint Hotfix

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Scrawl Hover-Repaint Storm** — `ScrawlCanvas` repainted bisher bei jeder normalen Mausbewegung; plain Hover triggert jetzt keine dauernden Redraws mehr.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Freehand Preview begrenzt** — waehrend des Zeichnens werden freie Maus-Samples lokal begrenzt, damit der Preview-Path nicht ungebremst anwachsen kann.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion-only GUI Safety** — Aenderung sitzt nur in `pydaw/plugins/fusion/scrawl_editor.py`; keine globalen Knob-/MIDI-/Engine-Pfade wurden angefasst.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — LFO → Filter Cutoff / OSC Pitch / Pan etc.
- [ ] AVAILABLE: **Fusion: Unison/Detune auf Engine-Ebene** — Stereo Detune pro Voice (aktuell nur Swarm/Wavetable-spezifisch).
- [ ] AVAILABLE: **Fusion: Effects Section** — Delay/Reverb/Chorus built-in.

## v0.0.20.582 — Fusion Regression Smoke-Test + Snapshot Flush

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Snapshot Flush vor Save/Preset** — `_capture_state_snapshot()` flusht offene Fusion-only MIDI-CC-Queues vor dem JSON-Snapshot, damit coalescte Controller-Werte nicht zwischen Queue und Save verloren gehen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Regression Harness** — `pydaw/tools/fusion_smoke_test.py` deckt queued MIDI-CC Snapshot, Scrawl Recall, Wavetable Recall und kompletten Modulwechsel ab.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Manueller Testplan** — `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md` beschreibt den reproduzierbaren UI/MIDI/State-Recall-Test fuer echte PyQt6/MIDI-Hardware-Umgebungen.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — LFO → Filter Cutoff / OSC Pitch / Pan etc.
- [ ] AVAILABLE: **Fusion: Unison/Detune auf Engine-Ebene** — Stereo Detune pro Voice (aktuell nur Swarm/Wavetable-spezifisch).
- [ ] AVAILABLE: **Fusion: Effects Section** — Delay/Reverb/Chorus built-in.

## v0.0.20.581 — CRITICAL: Fusion Scrawl State Save/Load Fix

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Scrawl State Persistenz** — `scrawl_points`, `scrawl_smooth` und `wt_file_path` werden jetzt mit Projekt/Preset gespeichert.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Persist-Trigger fuer Canvas-Aenderungen** — Scrawl-Zeichnen laeuft jetzt ebenfalls ueber den vorhandenen debounced Persist-Pfad.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Restore/Display-Sync** — gespeicherte Scrawl-Wellen werden beim Laden wieder in Engine/Voices/Editor gespiegelt; kein stiller Fallback mehr auf die Default-Welle.
- [x] FIXED in v0.0.20.582 (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Regression Smoke-Test UI/MIDI/State-Recall** — konsolidiert in `pydaw/tools/fusion_smoke_test.py` + `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md`.

## v0.0.20.580 — CRITICAL: Fusion MIDI-CC UI Coalescing (~60 Hz)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion-only MIDI-CC UI Coalescing** — eingehende CC-Werte werden pro Fusion-Knob gesammelt und nur noch auf einem ~60-Hz-`QTimer` in die Widgets/Engine gedrueckt; `CompactKnob` global bleibt unveraendert.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Cleanup fuer dynamische Extra-Knobs** — beim Rebuild von OSC/FLT/ENV-Extras werden offene coalescte CC-Werte alter Knobs verworfen, damit kein spaeter Write in entfernte Widgets laeuft.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Shutdown-Flush fuer pending CCs** — letzte gepufferte CC-Aenderungen werden vor Pull-Source-/SamplerRegistry-Cleanup angewendet.
- [x] FIXED in v0.0.20.582 (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Regression Smoke-Test UI/MIDI** — reproduzierbarer Testplan/Harness jetzt vorhanden.

## v0.0.20.579 — CRITICAL: Fusion GUI Hotfix (debounced State Persist)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion-only Debounce fuer Project-State Writes** — `FusionWidget` schreibt bei schnellen MIDI-/Knob-Aenderungen den kompletten Instrument-State nicht mehr bei jedem Tick sofort; ein `QTimer` coalesct den Persist-Pfad.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Sicherer Flush beim Shutdown** — offener Persist-Timer wird vor dem Entfernen des Pull-Source sauber ausgeschrieben.
- [x] FIXED in v0.0.20.580 (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion MIDI-CC UI Coalescing (~60 Hz)** — umgesetzt als Fusion-only Queue + 16-ms-Timer.

## v0.0.20.578 — CRITICAL: Fusion MIDI/Range/Realtime-Safety Hotfix

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Knob Range Wiring** — `CompactKnob` unterstuetzt echte Wertebereiche; Fusion reicht Pitch/Pan/Mode/Voices/Damp korrekt durch statt still 0..100 zu erzwingen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Dynamic Knob Rebind** — OSC/FLT/ENV-Extra-Knobs binden nach Rebuild wieder sauber Automation + MIDI Learn; alte CC-Listener werden entfernt.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion RT Param Sync** — `set_param()` schreibt nur noch Shared-State; aktive Voices werden am sicheren Pull-Rand synchronisiert statt mitten im Rendern.
- [x] FIXED in v0.0.20.582 (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Regression Smoke-Test UI/MIDI** — manueller Plan + halbautomatischer Smoke-Test vorhanden.

## v0.0.20.577 — CRITICAL: Fusion Synthesizer Performance Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Lock-Free Pull** — `pull()` snaphottet Voices unter Lock (<1µs), rendert ohne Lock. GUI-Thread kann jederzeit Parameter aendern → kein "main.py antwortet nicht" mehr.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Vectorized Oscillators** — Sine/Triangle nutzen `np.arange`+`np.sin`/`np.where` statt per-sample Loop (~10x schneller). Scrawl/Wavetable nutzen vectorized Table-Lookup mit numpy Index-Arrays.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Optimized Filters** — SVF: Mode-spezifische Inner-Loops (LP/HP/BP separat), Drive-Branch vor Loop gehoistet. Ladder: `math.tanh` als Local gecached. Beide ~30% schneller.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Optimized Envelopes** — ADSR: Fast-Path fuer OFF (`np.zeros`) und SUSTAIN (`np.full`), inline Stage-Transitions. AR/AD/Pluck: pre-computed Rates, Local caching.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Local Variable Caching** — Alle 13 DSP-Dateien: Instance-Vars als Locals, inline PolyBLEP (kein Funktionsaufruf), mode-split Loops.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Vectorized Noise** — White Noise: `np.random.randn(frames)` statt per-sample. Pink/Brown: pre-generate Buffer.
- [ ] AVAILABLE: **Fusion Phase 5: Numpy/Cython DSP** — Weitere Optimierung: SVF/Ladder als C-Extension oder Cython fuer nochmal ~5-10x Speedup.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — LFO → Filter Cutoff / OSC Pitch / Pan etc.
- [ ] AVAILABLE: **Fusion: Unison/Detune auf Engine-Ebene** — Stereo Detune pro Voice (aktuell nur Swarm).
- [ ] AVAILABLE: **Fusion: Effects Section** — Delay/Reverb/Chorus built-in.

## v0.0.20.569 — Session-Finale: Instrument Layer System + Rechtsklick + MIDI Learn komplett

### Erledigte Tasks (v527–v569, 43 Versionen):
- [x] Send/Return System (v527–v529)
- [x] Device-Container: FX Layer, Chain, Instrument Layer (v530–v532)
- [x] CLAP State Save/Load (v533)
- [x] Layout Shortcuts + Container Reorder (v534)
- [x] Notation: Playhead Click-to-Seek + Follow (v535)
- [x] Instrument Layer: Datenmodell + UI + Engine (v536–v540)
- [x] Container Preset Save/Load (v541)
- [x] Built-in Instrument Support in Layern (v542)
- [x] SF2 als Layer-Instrument + Velocity-Crossfade (v543)
- [x] CRITICAL BUGFIX: NotationView __init__ (v544)
- [x] Cursor-Fix: ArrowCursor auf Inner-Widget (v545)
- [x] Instrument Layer UI-Ueberarbeitung (v546–v549)
- [x] Audio-Engine Rebuild bei Layer-Aenderungen (v550–v553)
- [x] Bitwig-Style Layer-Zoom Phase 1+2 (v554–v555)
- [x] CRITICAL: Sound-Pipeline + Stuck Notes (v556–v557)
- [x] Engine-Lookup + Constructor-Fix + FX-Button (v558–v559)
- [x] Rechtsklick-Menue + Visual Polish (v560)
- [x] FX-Chain im Layer-Zoom: Reorder/Enable/Remove (v561)
- [x] FX Layer + Chain Zoom (v562)
- [x] Einheitliche Widget-Groesse (v563)
- [x] ProSampler Import Fix (v564)
- [x] Vollstaendiges FX-Menue alle Formate (v565–v567)
- [x] MIDI Learn + Rechtsklick fuer ALLE Plugins (v568)
- [x] MIDI Learn Persistent CC Mapping fuer Layer-Knobs (v569)
- [x] CLAP State Save/Load (v533)
- [x] Layout Shortcuts + Container Reorder (v534)
- [x] Notation: Playhead Click-to-Seek + Follow (v535)
- [x] Instrument Layer: Datenmodell + UI + Engine (v536–v540)
- [x] Container Preset Save/Load (v541)
- [x] Built-in Instrument Support in Layern (v542)
- [x] SF2 als Layer-Instrument + Velocity-Crossfade (v543)
- [x] CRITICAL BUGFIX: NotationView __init__ (v544)
- [x] Cursor-Fix: ArrowCursor auf Inner-Widget (v545)
- [x] Instrument Layer UI-Ueberarbeitung (v546–v549)
- [x] Instrument-Picker Popup Fix (v550)
- [x] Audio-Engine Rebuild bei Layer-Aenderungen (v551–v552)
- [x] Bitwig-Style Audio-Summierung (v553)
- [x] Bitwig-Style Layer-Zoom Phase 1: Navigation + Rendering (v554)
- [x] Layer-Zoom Phase 2: Externe Plugin-Parameter (v555)
- [x] CRITICAL: Sound-Pipeline Fix (layers_spec Tippfehler) (v556)
- [x] Stuck Notes Fix: Doppeltes MIDI-Routing (v557)
- [x] Engine-Lookup fuer alle Plugin-Formate (v558)
- [x] Constructor-Fix + Engine-Verbindung + FX-Button (v559)
- [x] Rechtsklick-Menue (Automation/MIDI Learn) + Visual Polish (v560)
- [x] FX-Chain im Layer-Zoom: Reorder/Enable/Remove (v561)
- [x] FX Layer + Chain Zoom (v562)
- [x] Einheitliche Widget-Groesse im Layer-Zoom (v563)
- [x] ProSampler Import Fix + SamplerRegistry Schutz (v564)
- [x] Vollstaendiges FX-Menue mit allen Plugin-Formaten (v565)
- [x] SF2-Widget mit Bank/Preset-Selector + FX-Menue ohne Limit (v566)
- [x] Alle 3 Container-FX-Menues mit allen Formaten (v567)
- [x] MIDI Learn + Rechtsklick fuer ALLE Audio-FX + Note-FX Plugins (v568)

### Naechste Tasks (kuenftige Sessions):
- [ ] AVAILABLE: **MIDI Learn fuer Layer-Knobs** — CC-Mapping mit Layer-Kontext.
- [ ] AVAILABLE: **Automation-Lanes fuer Layer-Parameter** — RT-Key-Mapping fuer Layer-Kontext, AutomationPlaybackService Erweiterung.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.
- [ ] AVAILABLE: **CLAP Preset Browser** — Preset-Liste aus CLAP-Plugin.
- [ ] AVAILABLE: **CLAP Note Expressions** — Per-Note Expressions.

## v0.0.20.555 — Bitwig-Style Layer-Zoom Phase 2: Externe Plugin-Parameter

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Externe Plugins im Layer-Zoom** — VST3, CLAP, LV2, VST2 Instrumente bekommen im Layer-Zoom das SELBE Widget wie auf normalen Tracks (Parameter-Sliders, Editor-Button, Sync-Timer). Verwendet `make_audio_fx_widget()` Factory mit virtuellem Device-Dict.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Built-in + External Hybrid** — Built-in Instrumente (AETERNA, BachOrgel, Sampler, Drum) behalten ihre nativen Widgets, externe Plugins gehen durch die universelle Factory.
- [ ] AVAILABLE: **Layer-Zoom Phase 3: FX-Add/Remove im Zoom** — Devices direkt im gezoomten Layer hinzufuegen/entfernen.
- [ ] AVAILABLE: **Layer-Zoom Phase 4: Nested Zoom** — In Container innerhalb von Layern reinzoomen.

## v0.0.20.554 — Bitwig-Style Layer-Zoom (Phase 1)

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Navigation-Stack** — `DevicePanel._nav_stack` speichert Zoom-Kontext (Layer-Index, Device-ID, Track-ID).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Breadcrumb-Leiste** — "← Zurück" Button + Pfadanzeige ("Instrument Layer › Layer 1") erscheint beim Reinzoomen.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **_render_layer_zoom()** — Zeigt das Instrument-Widget des Layers als Device-Card + per-Layer FX-Kette. Built-in Instrumente (AETERNA, BachOrgel, Sampler, Drum) bekommen ihr echtes Widget.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **"🔍 Layer öffnen" Button** — Erscheint pro Layer wenn ein Instrument zugewiesen ist. Löst `zoom_into_layer()` aus.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **zoom_out()** — Navigation zurück, Breadcrumb verschwindet, normaler Track-View wird gerendert.
- [ ] AVAILABLE: **Layer-Zoom Phase 2: Externe Plugin-Parameter** — VST3/CLAP/LV2 Parameter-Widgets im Layer-Zoom.
- [ ] AVAILABLE: **Layer-Zoom Phase 3: FX-Add/Remove im Zoom** — Devices direkt im gezoomten Layer hinzufuegen/entfernen.

## v0.0.20.544 — CRITICAL BUGFIX: NotationView __init__ abgeschnitten

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **NotationView.__init__() war abgeschnitten** — Die Methode `_beats_per_bar()` war versehentlich MITTEN in `__init__()` eingefuegt worden (v0.0.20.538). Dadurch endete `__init__` nach Zeile 605, und alles danach (input_state, tools, layer_manager, ghost_renderer, selection, clipboard, etc.) war unerreichbarer Code innerhalb von `_beats_per_bar()`. App-Start crashte mit `AttributeError: 'NotationView' object has no attribute 'layer_manager'`.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **_beats_per_bar() als eigene Methode** — Korrekt nach `__init__()` platziert, vor dem "View transforms" Abschnitt.

## v0.0.20.543 — SF2 als Layer-Instrument + Velocity-Crossfade

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **SF2 Soundfont als Layer-Instrument** — `chrono.sf2` im Instrument-Picker. Waehlt man SF2, oeffnet sich ein QFileDialog fuer die .sf2 Datei. Pfad wird in `layer["sf2_path"]` gespeichert. Audio-Engine erstellt `FluidSynthRealtimeEngine` mit sf2_path/bank/preset aus Layer-Daten.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Velocity-Crossfade** — Neues 5. Range-Feld `vel_crossfade` (0-64) pro Layer. Bei Crossfade > 0 werden Noten in der Uebergangszone mit linear skalierter Velocity weitergeleitet statt hart abgeschnitten. UI: "Xfade:" SpinBox in der Range-Zeile.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Dispatcher 5-Tupel** — `_InstrumentLayerDispatcher` nutzt `(vel_min, vel_max, key_min, key_max, vel_crossfade)` statt 4-Tupel. Abwaertskompatibel (fehlender 5. Wert = 0).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **get_instruments() erweitert** — "SF2 Soundfont" als 5. Built-in Instrument im Picker.
- [ ] AVAILABLE: **SF2 Bank/Preset-Auswahl im Layer** — Aktuell immer Bank 0 / Preset 0. Picker fuer Bank/Preset aus der SF2-Datei.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.

## v0.0.20.542 — Instrument-Layer: Built-in Instrument Support

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Built-in Instrument Engines in Layern** — AETERNA Synthesizer, Pro Sampler, Pro Drum Machine und Bach Orgel koennen jetzt als Layer-Instrument ausgewaehlt werden. Audio-Engine erstellt pro Layer die passende Built-in Engine (AeternaEngine, ProSamplerEngine, DrumMachineEngine, BachOrgelEngine).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Engine-Interface-Kompatibilitaet** — Built-in Engines bekommen `_ok=True` Tag fuer Reuse-Check. `note_on`/`pull` Interface-Pruefung statt `_ok` Attribut.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Doppel-Append-Schutz** — Nach Built-in Engine-Erstellung wird `engine=None` gesetzt um doppelten Append im generischen Code-Pfad zu verhindern.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.
- [ ] AVAILABLE: **Instrument-Layer: Crossfade zwischen Velocity-Zonen** — Weiche Uebergaenge statt harter Split-Punkte.
- [ ] AVAILABLE: **SF2 als Layer-Instrument** — FluidSynth-Engine als Layer-Option.

## v0.0.20.541 — Container Preset Save/Load

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Container Preset Save** — 💾 Button im Header aller 3 Container-Widgets (FX Layer, Chain, Instrument Layer). Speichert die komplette Container-Konfiguration als JSON-Datei via QFileDialog.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Container Preset Load** — 📂 Button im Header aller 3 Container-Widgets. Lädt ein JSON-Preset und ersetzt die Container-Daten (layers/devices + params). Sofortiger UI-Rebuild.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Preset-Verzeichnis** — `~/.config/ChronoScaleStudio/container_presets/` wird automatisch erstellt.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Hilfsfunktionen** — `_container_presets_dir()`, `_save_container_preset()`, `_load_container_preset()` als wiederverwendbare Funktionen.
- [ ] AVAILABLE: **Instrument-Layer: Built-in Instrument Support** — AETERNA, Pro Sampler etc. als Layer-Instrument.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.

## v0.0.20.540 — Instrument-Layer Phase 3: Velocity-Split / Key-Range

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Dispatcher Velocity/Key Filtering** — `_InstrumentLayerDispatcher.note_on()` filtert jetzt per-Layer nach Velocity-Range (vel_min/vel_max) und Key-Range (key_min/key_max). Noten ausserhalb des Bereichs werden fuer diesen Layer ignoriert. note_off geht immer an alle Layer (keine Stuck Notes).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Range-Extraktion bei Dispatcher-Erstellung** — `_create_vst_instrument_engines()` liest `vel_min`, `vel_max`, `key_min`, `key_max` aus den Layer-Daten und uebergibt sie als `layer_ranges` an den Dispatcher.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **UI: Velocity/Key Range Controls** — Pro expandiertem Layer: 4 QSpinBox-Felder (Vel Min/Max + Key Min/Max, 0-127). Tooltips zeigen MIDI-Notennamen (C4, F#2 etc.).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **_set_layer_range()** — Handler schreibt Range-Werte in Layer-Daten (Projekt-JSON).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **_midi_note_name()** — Hilfsfunktion konvertiert MIDI-Notennummer (0-127) in menschenlesbare Namen (C-2 bis G8).
- [ ] AVAILABLE: **Instrument-Layer: Built-in Instrument Support** — AETERNA, Pro Sampler etc. als Layer-Instrument (aktuell nur ext.vst3/vst2/clap).
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.
- [ ] AVAILABLE: **Instrument-Layer: Crossfade zwischen Velocity-Zonen** — Weiche Uebergaenge statt harter Split-Punkte.

## v0.0.20.539 — Instrument-Layer Phase 2: Multi-Engine + MIDI-Dispatch

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **_InstrumentLayerDispatcher** — Leichtgewichtiger Wrapper der note_on/note_off/all_notes_off an ALLE Layer-Engines gleichzeitig dispatcht. Implementiert das gleiche Interface wie VST3/CLAP InstrumentEngine.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Phase 3b: Instrument Layer Scan** — `_create_vst_instrument_engines()` scannt jetzt Projekt-Tracks nach `chrono.container.instrument_layer` Containern. Fuer jeden Layer mit einem ext.vst3/vst2/clap Instrument wird eine eigene Engine erstellt.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Per-Layer Engine Reuse** — Bestehende Layer-Engines werden wiederverwendet wenn der gleiche Layer-Key existiert (kein Reload bei rebuild_fx_maps).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **SamplerRegistry Dispatcher** — Der Dispatcher wird unter der Track-ID registriert, sodass MIDI-Events an alle Layer-Engines gleichzeitig gehen.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Per-Layer Pull Sources** — Jede Layer-Engine wird als eigene Pull-Source registriert (`vstinst:{tid}:ilayer:{i}`), sodass das Audio jedes Layers in den Mix einfliesst.
- [x] FIXED in v0.0.20.540 (Claude Opus 4.6, 2026-03-17): **Velocity-Split / Key-Range** — Phase 3 komplett: Dispatcher-Filtering + UI-Controls + Range-Persistenz.

## v0.0.20.538 — LV2/CLAP Slider folgt Automation (RT-Sync-Timer)

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **LV2 _ui_sync_timer + _sync_from_rt()** — LV2 Widget hatte keinen Timer erstellt (nur `.start()` Aufruf der silent failt). Jetzt: 60ms QTimer pollt RT-Store, updated Sliders/Spinboxes mit QSignalBlocker.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **CLAP _ui_sync_timer + _sync_from_rt()** — CLAP Widget hatte keinen Sync-Timer. Jetzt: 60ms QTimer pollt RT-Store, updated Sliders/Spinboxes/CheckBoxes mit QSignalBlocker. Gleiche Architektur wie VST3/LADSPA.
- [ ] AVAILABLE: **Instrument-Layer Phase 2: Multi-Instrument Engine** — Audio-Engine erstellt pro Layer eine eigene Instrument-Engine. MIDI wird an alle Layer dispatcht.
- [ ] AVAILABLE: **Instrument-Layer Phase 3: Velocity-Split / Key-Range** — Per-Layer Velocity/Key-Range.

## v0.0.20.537 — Instrument-Layer Picker: Externe Plugins (LV2/VST2/VST3/CLAP/DSSI/LADSPA)

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Instrument-Picker zeigt externe Plugins** — Submenüs pro Format (VST3, CLAP, VST2, LV2, DSSI, LADSPA) mit allen als Instrument markierten Plugins aus dem Plugin-Cache. Gefiltert nach `is_instrument=True`. Max 50 pro Format mit "... und N weitere" Hinweis.
- [ ] AVAILABLE: **Instrument-Layer Phase 2: Multi-Instrument Engine** — Audio-Engine erstellt pro Layer eine eigene Instrument-Engine. MIDI wird an alle Layer dispatcht.
- [ ] AVAILABLE: **Instrument-Layer Phase 3: Velocity-Split / Key-Range** — Per-Layer Velocity/Key-Range.

## v0.0.20.536 — Instrument-Layer (Stack) Phase 1: Datenmodell + UI + Engine-Erkennung

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Instrument Layer Container Widget** — `_InstrumentLayerContainerWidget` mit violettem Farbschema (🎹 #ce93d8). Expandierbare Layer mit Instrument-Badge, Volume-Slider, Enable/Disable, Remove. Per-Layer Instrument-Picker (Popup-Menue mit Built-in Instrumenten). Per-Layer FX Devices mit Enable/Disable/Remove/Reorder (▲/▼).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Audio-Engine Container-Erkennung** — `_compile_devices()` erkennt `chrono.container.instrument_layer` und behandelt es als `FxLayerContainer` (parallele Audio-Verarbeitung pro Layer).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **RT-Key Registrierung** — `ensure_track_fx_params()` registriert `afx:{tid}:{did}:layer_mix` fuer Instrument Layer Container.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **DevicePanel API** — `add_instrument_layer_to_track()` erstellt Container mit N leeren Layern. Container-Routing-Guard in `add_audio_fx_to_track()`. Rechtsklick-Menue zeigt "🎹 Instrument Layer (Stack)".
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **FX-Katalog** — `get_instruments()` in `fx_specs.py` mit Pro Sampler, Pro Drum Machine, AETERNA, Bach Orgel. `get_containers()` erweitert um Instrument Layer Eintrag.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **make_audio_fx_widget Dispatch** — Instrument Layer Plugin-ID an neues Widget delegiert.
- [ ] AVAILABLE: **Instrument-Layer Phase 2: Multi-Instrument Engine** — Audio-Engine erstellt pro Layer eine eigene Instrument-Engine. MIDI wird an alle Layer dispatcht. Pull-Sources pro Layer registriert.
- [ ] AVAILABLE: **Instrument-Layer Phase 3: Velocity-Split / Key-Range** — Per-Layer Velocity-Range (z.B. 0-64 / 65-127) und Key-Range (z.B. C1-B3 / C4-B6) fuer realistische Instrument-Stacks.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Sidechain-Eingang aus einem Send-Signal ableiten.

## v0.0.20.535 — Notation: Playhead Click-to-Seek + Follow Playhead

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Notation Playhead Click-to-Seek** — Klick ins Zeitlineal (obere 24px) setzt den Transport-Playhead auf die angeklickte Beat-Position. Nutzt `transport.seek(beat)` ueber die bestehende TransportService-API.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Notation Follow Playhead** — Neuer "▶ Follow" Toggle-Button in der Toolbar (blau wenn aktiv). Wenn aktiviert, scrollt die Notation automatisch mit dem Playhead: bei 80% des sichtbaren Bereichs springt die View so dass der Playhead bei 20% steht (Bitwig-Stil).
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **NotationView.set_transport()** — Transport-Referenz wird an die View durchgereicht fuer Click-to-Seek.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **NotationView._seek_to_beat()** — Interne Seek-Methode mit Transport-Null-Check.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **NotationView.set_follow_playhead()** — Flag-Setter fuer auto-scroll.
- [x] FIXED in v0.0.20.536 (Claude Opus 4.6, 2026-03-17): **Instrument-Layer Phase 1** — Datenmodell, UI-Widget, Engine-Erkennung, DevicePanel-Integration.

## v0.0.20.534 — Keyboard Shortcuts fuer Layout-Presets + Container-Device Reorder

- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Keyboard Shortcuts fuer Layout-Presets** — Ctrl+Alt+1 bis Ctrl+Alt+8 wenden die 8 Layout-Presets direkt an (Ein Bildschirm Gross/Klein/Tablet, Zwei Bildschirme Studio/Arranger+Mixer/Main+Detail/Studio+Touch, Drei Bildschirme). Shortcut-Hints im Menue sichtbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Container-Device Reorder** — ▲/▼ Buttons pro Device in FX Layer und Chain Containern. Devices koennen innerhalb eines Layers oder einer Chain nach oben/unten verschoben werden. Buttons nur sichtbar wo Move moeglich ist.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **FxLayer _move_device()** — Array-Swap in der Layer-Device-Liste mit sofortigem UI-Rebuild.
- [x] FIXED (Claude Opus 4.6, 2026-03-17): **Chain _move_device()** — Array-Swap in der Chain-Device-Liste mit sofortigem UI-Rebuild.
- [x] FIXED in v0.0.20.535 (Claude Opus 4.6, 2026-03-17): **Notation: Playhead Click-to-Seek + Follow Playhead** — Klick ins Lineal setzt Playhead, Follow-Button fuer Auto-Scroll.

## v0.0.20.533 — CLAP State Save/Load + Browser Icons Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **CLAP Browser Icons** — `scan_clap()` gibt jetzt `is_instrument` aus den CLAP-Features weiter (Linux + macOS). Plugins zeigen 🎹 (Instrument) oder 🔊 (Effect) statt generischem Symbol.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **CLAP State Extension (clap.state)** — Komplette ctypes-Implementation: `clap_istream_t`, `clap_ostream_t`, `clap_plugin_state_t`, Memory-Stream-Klassen (`_MemoryOutputStream`, `_MemoryInputStream`).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_ClapPlugin.get_state()/set_state()/has_state()** — Low-Level State Save/Load ueber die clap.state Extension.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ClapFx State Restore bei Load** — `_load()` liest `__ext_state_b64` aus Projekt-Params und stellt Plugin-State wieder her.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ClapFx.get_state_b64()** — Aktuellen Plugin-State als Base64 fuer Projekt-Persistenz exportieren.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ClapInstrumentEngine State Restore + get_state_b64()** — Gleiche State-Integration fuer CLAP-Instrumente (Surge XT etc.).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **embed_clap_project_state_blobs()** — Scannt alle Tracks, findet laufende CLAP-Instanzen aus der Audio-Engine, speichert deren State als Base64 in die Projekt-JSON.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Project-Save-Hook** — `save_project_as()` und `save_snapshot()` rufen jetzt `embed_clap_project_state_blobs()` auf (analog zu VST3).
- [ ] AVAILABLE: **CLAP Preset Browser** — Preset-Liste aus CLAP Plugin (clap.preset-load Extension).
- [ ] AVAILABLE: **CLAP Note Expressions** — Per-Note Expressions (Tuning, Brightness, Pressure).

## v0.0.20.532 — Device-Container Phase 3: Layer-Expand + Device-Management

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Klick-Expand** — Klick auf Layer-Header (▶/▼) klappt die Layer-Devices auf/zu. Jeder Layer zeigt seine Devices als Mini-Eintraege mit ●/○ Status.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Per-Layer Volume** — Mini-Slider (50px) pro Layer fuer Volume-Kontrolle (0-100%).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Layer Enable/Disable** — ●/○ Toggle pro Layer schaltet den Layer ein/aus.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Layer Remove** — × Button entfernt Layer (mit korrekter Shift der expanded-Indices).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Device Enable/Disable** — ⏻ Toggle pro Device innerhalb eines Layers.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: Device Remove** — × Button entfernt Device aus Layer.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX Layer: "+ FX → Layer N"** — Button pro expandiertem Layer oeffnet Popup-Menue mit allen Built-in Audio-FX. Fuegt neues Device in den spezifischen Layer ein und expandiert ihn automatisch.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Chain: Device Enable/Disable** — ⏻ Toggle pro Device in der Sub-Chain.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Chain: Device Remove** — × Button entfernt Device aus Sub-Chain.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Chain: "+ FX → Chain"** — Button oeffnet Popup-Menue mit allen Built-in Audio-FX. Fuegt neues Device in die Sub-Chain ein.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_clear_layout() Helper** — Rekursive Layout-Bereinigung fuer Widget-Rebuilds.
- [ ] AVAILABLE: **Instrument-Layer (Stack)** — Mehrere Instrumente auf einer Spur stacken (Layer-Split, Velocity-Layer).
- [ ] AVAILABLE: **Container-Device Drag-Reorder** — Devices innerhalb eines Containers per Drag&Drop umsortieren.
- [ ] AVAILABLE: **Container Preset Save/Load** — Container-Konfiguration als Preset speichern und laden.

## v0.0.20.531 — Device-Container Phase 2: Browser/Menue/DnD/Rechtsklick-Integration

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Effects Browser zeigt Container** — Audio-FX Tab zeigt "📦 FX Layer" und "📦 Chain" als erste Eintraege (cyan). Doppelklick/Add fuegt Container auf aktive Spur ein.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Rechtsklick auf Device-Chain-Flaeche** — `_show_chain_context_menu()` mit 📦 Container-Sektion (FX Layer / Chain) und 🎚️ Audio-FX-Sektion. Schnellster Weg einen Container hinzuzufuegen.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Drag&Drop aus Browser** — Container-Eintraege koennen per Drag aus dem Effects Browser auf die Device-Chain gezogen werden. Drop-Indicator zeigt Einfuegeposition in Audio-FX-Zone.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **add_audio_fx_to_track() Container-Routing** — Wenn `plugin_id` ein Container ist, wird automatisch an `add_fx_layer_to_track()` / `add_chain_container_to_track()` delegiert.
- [x] FIXED in v0.0.20.532 (Claude Opus 4.6, 2026-03-16): **Layer-Expand + Device-Management** — Volle Interaktion innerhalb von Containern.

## v0.0.20.530 — Device-Container Phase 1: FX Layer + Chain (Bitwig Sound-Design-Kern)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FxLayerContainer Audio-Engine** — Neues `AudioFxBase`-Device in `fx_chain.py`: N parallele Layer, jeder mit eigener serieller ChainFx. Audio wird gesplittet → pro Layer verarbeitet → summiert (mit Normalisierung). Per-Layer Volume + Container-Mix (RT-animierbar).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ChainContainerFx Audio-Engine** — Serial Sub-Chain als einzelnes Device: kapselt beliebig viele FX in eine Card. Dry/Wet-Mix (RT-animierbar). Unbegrenzt verschachtelbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_compile_devices() erkennt Container** — `chrono.container.fx_layer` und `chrono.container.chain` werden vor allen anderen Plugin-Typen erkannt und kompiliert.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ensure_track_fx_params() fuer Container** — RT-Store-Keys `afx:{tid}:{did}:layer_mix` und `afx:{tid}:{did}:chain_mix` werden registriert.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_FxLayerContainerWidget UI** — Layer-Liste mit Device-Counts, Mix-Slider, "+ Layer"-Button, farbcodierte Statusanzeige (Cyan).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_ChainContainerWidget UI** — Device-Summary-Liste, Mix-Slider, farbcodierte Anzeige (Orange).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **DevicePanel API** — `add_fx_layer_to_track()`, `add_chain_container_to_track()`, `add_device_to_container()` als programmatische Methoden.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Katalog** — `get_containers()` in `fx_specs.py` mit FX Layer + Chain Eintraegen.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **make_audio_fx_widget Dispatch** — Container-Plugin-IDs werden an die neuen Widget-Klassen delegiert.
- [x] FIXED in v0.0.20.531 (Claude Opus 4.6, 2026-03-16): **Browser/Menue/DnD-Integration** — Container im Effects Browser, Rechtsklick-Menue, Drag&Drop und auto-Routing in add_audio_fx_to_track().

## v0.0.20.529 — Send MIDI Learn (CC-Controller auf Send-Knobs)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Send MIDI Learn** — Rechtsklick auf Send-Knob → "🎛 MIDI Learn": naechster CC-Dreh am MIDI-Controller wird dem Send-Knob zugewiesen. Roter Border als visuelles Feedback waehrend Learn-Mode. Nutzt den bestehenden `AutomationManager.handle_midi_message()`-Pfad.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **MIDI Learn Reset** — "🚫 MIDI Learn zurücksetzen" entfernt CC-Mapping aus Live-Listeners und Persistent-Registry.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **CC-Mapping ueberlebt Widget-Rebuild** — `_register_send_automation()` liest `_persistent_cc_map` und re-registriert CC-Mappings auf neue Knob-Instanzen nach Mixer-Refresh.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **_pydaw_param_id auf Send-Knobs** — Jeder QDial traegt jetzt `_pydaw_param_id = "trk:{tid}:send:{fx_id}"`, damit `_write_cc_automation()` Breakpoints fuer Send-Lanes schreiben kann.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Kontextmenue zeigt aktive CC-Nummer** — Wenn ein Mapping existiert, zeigt das Menue "🎛 MIDI Learn (CC 7)" statt nur "🎛 MIDI Learn".
- [x] FIXED in v0.0.20.530 (Claude Opus 4.6, 2026-03-16): **Device-Container (Schritt B) Phase 1** — FX Layer + Chain als Audio-Engine-Devices + UI-Widgets + DevicePanel-API.

## v0.0.20.528 — Send-Automation (Send-Amount als automatierbarer Parameter)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Send-Amount als automatierbarer Parameter** — Jeder Send-Knob im Mixer registriert sich jetzt im AutomationManager (`trk:{track_id}:send:{fx_track_id}`). Automation-Lanes koennen gezeichnet, per MIDI CC aufgenommen und bei Playback abgespielt werden — genau wie Volume/Pan.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **AutomationPlaybackService liest Send-Lanes** — `_on_playhead()` scannt jetzt dynamisch alle Lane-Keys die mit `send:` beginnen und appliziert den interpolierten Wert ueber `apply_automation_value()`.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **apply_automation_value() erweitert** — Neuer `send:{fx_track_id}` Branch: updated Send-Amount in `track.sends[]` in-memory. Auto-creates Send-Eintrag wenn Automation einen noch nicht existierenden Send antreibt.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Send-Knob folgt Automation-Kurve** — `_on_send_automation_changed()` empfaengt `parameter_changed` Signal und bewegt den QDial per `blockSignals()` (kein Feedback-Loop).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Show Automation in Arranger** — Rechtsklick auf Send-Knob hat jetzt "📈 Automation im Arranger zeigen" als ersten Menuepunkt. Emittiert `request_show_automation` Signal → Arranger oeffnet die richtige Lane.
- [x] FIXED in v0.0.20.529 (Claude Opus 4.6, 2026-03-16): **Send-Automation MIDI Learn** — MIDI-Controller direkt auf Send-Knob mappen und Automation aufzeichnen.

## v0.0.20.527 — Send Pre/Post Toggle + FX-Spuren vor Master (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Send Pre/Post Toggle im Mixer (Rechtsklick)** — Rechtsklick auf Send-Knob oeffnet Kontextmenue mit Pre/Post-Umschaltung (🔵 Pre-Fader / 🟡 Post-Fader), Schnellwahl 50%/100%, und Send-Entfernen. Neue `toggle_send_pre_fader()` Methode in ProjectService. Farbe wechselt sofort: gelb=post, blau=pre (Bitwig-Style).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Spuren immer direkt vor Master positioniert** — `_rebuild_track_order()` in ProjectService sortiert jetzt FX-Tracks (`kind="fx"`) automatisch ans Ende, direkt vor den Master-Track. Regulaere Spuren (audio, instrument, bus, group) behalten ihre relative Reihenfolge. Genau wie Bitwig Studio.
- [x] FIXED in v0.0.20.528 (Claude Opus 4.6, 2026-03-16): **Send-Automation** — Send-Amount als automatierbarer Parameter registriert.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Optional einen Sidechain-Eingang aus einem Send-Signal ableiten.
- [ ] AVAILABLE: **Device-Container (Schritt B)** — FX-Layer (parallel), Instrument-Layer (Stack), Chain (seriell als ein Device). Bitwigs Sound-Design-Kern. Grosser Umbau (~500+ Zeilen).

## v0.0.20.526 — Alle Plugin-Typen: Slider folgt Automation-Kurve

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **LV2 Slider folgt Automation** — `Lv2AudioFxWidget._on_automation_param_changed()` + `parameter_changed.connect()`
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **LADSPA/DSSI Slider folgt Automation** — `LadspaAudioFxWidget._on_automation_param_changed()` + `parameter_changed.connect()`
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **CLAP Slider folgt Automation** — `ClapAudioFxWidget._on_automation_param_changed()` + `parameter_changed.connect()`
- Zusammen mit v525 (VST2/VST3) sind jetzt ALLE externen Plugin-Formate abgedeckt: LV2, LADSPA, DSSI, VST2, VST3, CLAP.

## v0.0.20.525 — VST2/VST3 Slider folgt Automation-Kurve

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **VST2/VST3 Schieberegler bewegen sich jetzt mit gezeichneter Automation** — Die Unified VST Widget Klasse hatte keinen `parameter_changed.connect()` Aufruf. Jetzt verbindet `_build()` das Signal und der neue Handler `_on_automation_param_changed()` aktualisiert Slider+Spinbox per QSignalBlocker (kein Feedback-Loop) und pusht den Wert in den RT-Store.
- [ ] AVAILABLE: **LV2/LADSPA/CLAP Slider folgt Automation** — Gleiches Pattern wie VST, fehlt aber noch in den jeweiligen Widget-Klassen.

## v0.0.20.524 — Automation-Migration: Device-ID Mapping fuer VST

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **VST-Automation wird jetzt korrekt migriert** — Root Cause: VST-Parameter-Keys enthalten die Device-ID (`afx:{track}:{device_id}:vst3:Cutoff`). Beim Move/Copy bekommt das Ziel eine NEUE Device-ID, aber die alte blieb im Key → Lane-Widget Mismatch. Fix: Die Migration baut jetzt eine Device-ID-Map aus den audio_fx_chain Eintraegen beider Spuren (matching per plugin_id) und ersetzt sowohl track_id ALS AUCH alle device_ids im Key. Interne Instrumente (Bach Orgel) mit `trk:{tid}:bach_orgel:param` Format funktionieren weiterhin (kein device_id im Key).

## v0.0.20.523 — Automation-Migration Fix: Alle Key-Formate

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Automation-Lanes werden jetzt tatsaechlich migriert** — Root Cause: Die Migration suchte nur nach `trk:{track_id}:` Prefix, aber UI-gezeichnete Automation hat das Format `afx:{track_id}:{device_id}:param` (kein `trk:` Prefix). Deshalb wurden 0 Lanes gefunden. Fix: Matching per `lane.track_id` Attribut UND `source_track_id in pid` Fallback. Dann `pid.replace(source, target)` fuer die Key-Umschreibung. Funktioniert jetzt fuer ALLE drei Formate: UI-drawn (`afx:...`), MIDI-recorded (`trk:...afx:...`), und Track-level (wird korrekt uebersprungen).

## v0.0.20.522 — Automation-Copy bei Ctrl+Drag

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Ctrl+Drag kopiert jetzt auch Automation-Lanes** — `_migrate_automation_for_device_move()` hat neuen Parameter `copy: bool`. Bei `copy=True` werden Lanes per `deepcopy` dupliziert (Original bleibt auf Quellspur). Bei `copy=False` (normaler Move) werden sie verschoben wie bisher. Alle 3 Handler rufen jetzt immer `_migrate_automation_for_device_move(..., copy=is_copy)` auf.

## v0.0.20.521 — Mixer Send-Scroll sichtbar + FX nummeriert

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Duenner sichtbarer Scrollbalken (6px)** — `ScrollBarAsNeeded` statt `AlwaysOff`. Styled: 6px breit, abgerundeter Handle, transparenter Hintergrund.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Knobs nummeriert** — Labels zeigen jetzt `FX1`, `FX2`, `FX3` etc. statt nur `FX`. Tooltip zeigt vollen FX-Spurnamen + Nummer + Prozentwert + Pre/Post-Status.

## v0.0.20.520 — Mixer Send-Knobs Invisible Scroll (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Send-Bereich scrollt unsichtbar per Mausrad** — Die Send-Knobs sitzen jetzt in einer `QScrollArea` mit `ScrollBarAlwaysOff` und fester Hoehe (80px). Bei 3+ FX-Spuren scrollt man einfach mit dem Mausrad — kein Scrollbalken sichtbar, genau wie Bitwig. Fader und VU-Meter bekommen immer genug Platz.

## v0.0.20.519 — Mixer Send-Knobs Compact + Automation folgt Device beim Move

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Mixer Send-Knobs kompakt (Bitwig-Style)** — Send-Knobs sind jetzt 22px kleine Dials in horizontalen Reihen `[Label][Knob]` statt 32px vertikal gestapelt. Gelb=Post-Fader, Blau=Pre-Fader (wie Bitwig). Aktive Sends hell, inaktive gedimmt. Funktioniert jetzt auch bei 6+ FX-Spuren ohne den Strip zu sprengen.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Automation folgt Device beim Cross-Track-Move** — Neue `_migrate_automation_for_device_move()` Methode findet alle Automation-Lanes deren `parameter_id` die Quellspur + Device-ID referenziert, schreibt sie auf die Zielspur um und entfernt die alten Lanes. Wird automatisch bei jedem Cross-Track-Move aufgerufen (Instrument, Audio-FX, Note-FX). Bei Ctrl+Drag (Copy) wird die Automation NICHT migriert (bleibt auf beiden Spuren).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Track-Level-Params bleiben bei der Spur** — Volume/Pan-Automation wird bewusst NICHT mitgenommen, weil sie zur Spur gehoert, nicht zum Device.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Safe bei Konflikten** — Wenn die Zielspur bereits eine Lane fuer denselben Parameter hat, bleibt die alte Lane erhalten (kein Ueberschreiben).
- [ ] AVAILABLE: **Automation-Copy bei Ctrl+Drag** — Optional bei Ctrl+Drag die Lanes duplizieren statt nur auf der Quellspur zu lassen.
- [x] FIXED in v0.0.20.527 (Claude Opus 4.6, 2026-03-16): **Send Pre/Post Toggle im Mixer** — Rechtsklick auf Send-Knob fuer Pre/Post-Umschaltung.

## v0.0.20.518 — Send-FX / Return-Tracks (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Track.sends Feld im Datenmodell** — Jeder Track traegt jetzt eine `sends` Liste mit `{target_track_id, amount, pre_fader}` Eintraegen. Persistiert im Projekt-JSON. Abwaertskompatibel (default=[]).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Track-Typ `kind="fx"`** — Neuer Track-Typ fuer Return/FX-Spuren. Erscheint in allen Add-Track-Menues (Mixer, Arranger-Kontextmenue). FX-Tracks empfangen nur Send-Audio, keine eigenen Clips.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Audio-Engine: Komplettes Send-Bus-Routing** — `HybridAudioCallback` verarbeitet Sends in der richtigen Reihenfolge: FX-Busse nullen → Tracks rendern → Pre-Fader-Sends (nach FX-Chain, vor Vol/Pan) → Post-Fader-Sends (nach Vol/Pan) → FX-Bus-Processing (eigene FX-Chain + Vol/Pan + Metering) → Master-Mix. Folgt exakt dem Group-Bus-Muster aus v357.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **AudioEngine.rebuild_fx_maps() berechnet Send-Bus-Map** — Liest `Track.sends` aus dem Projekt-Snapshot und pusht die Map atomar per `set_send_bus_map()` in den Audio-Callback.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **ProjectService: Send-Management-API** — `add_send()`, `remove_send()`, `set_send_amount()`, `get_fx_tracks()` fuer programmatische Send-Verwaltung.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Mixer UI: Send-Knobs (QDial) pro Strip** — Jeder Mixer-Strip zeigt fuer jede FX-Spur im Projekt einen Drehregler (0-100%). FX- und Master-Strips zeigen keine Send-Knobs. Knobs werden dynamisch bei Projekt-Aenderungen aktualisiert.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Tracks in allen Add-Menues** — Mixer "+ Add" und Arranger-Kontextmenue bieten "FX-Spur (Return) hinzufuegen" an.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **SmartDrop: FX-Tracks als Audio-FX-Ziel** — Audio-FX koennen per Drag auf FX-Tracks gedroppt werden (z.B. Reverb auf Return-Spur).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **FX-Spur Label in SmartDrop/Guard** — `_track_kind_label()` kennt jetzt `"fx"` → `"FX-Spur"`.
- [x] FIXED in v0.0.20.527 (Claude Opus 4.6, 2026-03-16): **Send Pre/Post Toggle im Mixer** — Rechtsklick-Kontextmenue mit Pre/Post-Umschaltung.
- [x] FIXED in v0.0.20.527 (Claude Opus 4.6, 2026-03-16): **FX-Spuren immer direkt vor Master positioniert** — `_rebuild_track_order()` sortiert FX-Tracks automatisch ans Ende.
- [x] FIXED in v0.0.20.528 (Claude Opus 4.6, 2026-03-16): **Send-Automation** — Send-Amount als automatierbarer Parameter registriert.
- [ ] AVAILABLE: **Sidechain-Input von FX-Track** — Optional einen Sidechain-Eingang aus einem Send-Signal ableiten.

## v0.0.20.517 — Ctrl+Drag Copy, Auto Track-Type, Belegte Audio-Spuren Morph

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Ctrl+Drag = Copy statt Move (Bitwig-Style)** — Beim Cross-Track-Drag mit gehaltener Ctrl-Taste wird das Device auf die Zielspur kopiert, ohne es von der Quellspur zu entfernen. Gilt fuer Instrumente, Audio-FX und Note-FX. `_is_ctrl_held()` Helper prueft `QApplication.keyboardModifiers()`.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Automatische Track-Typ-Anpassung nach Instrument-Entfernung** — Wenn ein Instrument per Cross-Track-Move von einer Instrument-Spur entfernt wird und die Quellspur danach kein plugin_type mehr hat, wird `track.kind` automatisch auf `"audio"` zurueckgesetzt.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Belegte Audio-Spuren koennen jetzt zu Instrument-Spuren gemorpht werden** — `can_apply=True` und `apply_mode="audio_to_instrument_with_content"` fuer Audio-Spuren mit Clips und/oder FX-Ketten. Audio-Clips und FX-Kette bleiben komplett erhalten (Bitwig-Style Hybrid-Konvertierung). Bestaetigungsdialog wird nur bei belegten Spuren angezeigt.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Undo funktioniert fuer alle Faelle** — Leere Spuren, belegte Spuren, Cross-Track-Move und Cross-Track-Copy sind alle per Ctrl+Z rueckgaengig machbar (ein einziger Undo-Punkt pro Aktion).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Statusmeldungen zeigen Move/Copy/Morph klar an** — Alle Handler unterscheiden jetzt zwischen "gesetzt", "verschoben", "kopiert" und "gemorpht" in der Statusleiste.
- [ ] AVAILABLE: **Hybrid-Track-Konzept (Audio+MIDI Clips auf selber Spur)** — Bitwig kennt Hybrid-Tracks die sowohl Audio- als auch MIDI-Clips halten koennen. Aktuell ist track.kind entweder audio oder instrument.
- [ ] AVAILABLE: **Send-/Routing-Migration bei Morph** — Bei belegten Audio-Spuren koennten Sends und Bus-Routing optional mitgefuehrt werden.
- [ ] AVAILABLE: **Automation-Migration bei Cross-Track-Move** — Automation-Lanes koennten optional beim Device-Move mitgenommen werden.

## v0.0.20.516 — Cross-Track Device Drag&Drop (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **DeviceCard Drag-Payload angereichert** — `_DeviceCard` traegt jetzt `plugin_type_id`, `plugin_name` und `source_track_id` als Drag-Metadaten. Sowohl Note-FX als auch Audio-FX und Instrument-Cards senden diese Daten beim Drag mit.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Instrument-Anchor-Card ist jetzt draggbar** — Die Instrument-Card (SF2 und Plugin-basiert) bekommt `fx_kind="instrument"`, `device_id`, `plugin_type_id` und `source_track_id`, sodass sie per Drag aus dem DevicePanel auf den Arranger/TrackList gezogen werden kann.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Cross-Track Instrument-Move** — Instrument per Drag von Spur A auf bestehende Instrument-Spur B verschieben: Insert auf Ziel + automatische Entfernung von der Quellspur.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Cross-Track FX-Move** — Audio-FX und Note-FX per Drag von Spur A auf kompatible Spur B verschieben: Insert auf Ziel + automatische Entfernung von der Quellspur.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Cross-Track Instrument auf leere Audio-Spur** — Instrument per Drag auf leere Audio-Spur: v515 Morph-Guard konvertiert die Spur atomar zu Instrument-Spur, fuegt das Instrument ein und entfernt es von der Quellspur.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **`_smartdrop_remove_from_source()` Helper** — Neue zentrale Methode in MainWindow entfernt nach erfolgreichem Cross-Track-Move das Device sicher von der Quellspur (Instrument, Audio-FX oder Note-FX).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Internes Reorder unveraendert** — Das bestehende Drag-Reorder innerhalb derselben Device-Chain bleibt exakt wie bisher funktionsfaehig (gleicher `_INTERNAL_MIME` Pfad).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Alle bestehenden Browser-Drop-Pfade unveraendert** — Browser→Arranger, Browser→TrackList, Browser→DevicePanel funktionieren exakt wie vorher.
- [ ] AVAILABLE: **Ctrl+Drag fuer Copy statt Move** — Optional beim Cross-Track-Drag mit Ctrl-Taste das Device kopieren statt verschieben (Device bleibt auf Quellspur).
- [ ] AVAILABLE: **Cross-Track Instrument auf belegte Audio-Spur** — Audio-Spuren mit Clips/FX bleiben weiterhin vom Morph-Guard blockiert (eigener Bauabschnitt).
- [ ] AVAILABLE: **Automatische Track-Typ-Anpassung nach Instrument-Entfernung** — Wenn die Quellspur nach dem Move kein Instrument mehr hat, optional `kind="audio"` setzen.

## v0.0.20.515 — SmartDrop: Erster ECHTER atomarer Live-Pfad fuer leere Audio-Spur

- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Shadow-Commit-Rehearsal implementiert** — `_build_shadow_commit_rehearsal()` in `pydaw/services/smartdrop_morph_guard.py` simuliert den kompletten Undo-Zyklus (deepcopy Projekt, track.kind aendern, ProjectSnapshotEditCommand konstruieren, do()/undo() gegen lokalen Recorder, Round-Trip-Verifikation) komplett read-only ohne das Live-Projekt zu beruehren.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Erster ECHTER atomarer Live-Pfad fuer den Minimalfall (leere Audio-Spur)** — `apply_audio_to_instrument_morph_plan()` fuehrt jetzt bei `apply_mode="minimal_empty_audio"` die echte Mutation durch: Before-Snapshot erfassen, `set_track_kind("instrument")`, After-Snapshot erfassen, `ProjectSnapshotEditCommand` auf den Undo-Stack pushen. Bei jedem Fehler wird sofort per Snapshot-Restore zurueckgerollt.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **MainWindow fuehrt nach erfolgreichem Morph die Instrument-Einfuegung durch** — `_on_arranger_smartdrop_instrument_morph_guard()` ruft nach `ok=True` die bestehende `device_panel.add_instrument_to_track()` auf, selektiert die Spur, oeffnet das DevicePanel und emittiert UI-Refresh.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Apply-Readiness-Checkliste kennt jetzt Shadow-Rehearsal, Routing-Atomic und Undo-Commit als dynamische Pruefpunkte** — alle drei kippen erst auf `ready` wenn der Minimalfall (leere Audio-Spur + Rehearsal bestanden) vorliegt.
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Guard blockiert weiterhin alle nicht-leeren Audio-Spuren** — Spuren mit Audio-Clips, FX-Ketten oder Note-FX bleiben wie bisher komplett gesperrt (can_apply=False, apply_mode=blocked).
- [x] FIXED (Claude Opus 4.6, 2026-03-16): **Undo/Redo funktioniert** — die gesamte Aenderung (track.kind Audio→Instrument) wird als ein einziger Undo-Punkt gekappselt; Ctrl+Z stellt den Audio-Spur-Zustand komplett wieder her.
- [ ] AVAILABLE: **Volles Audio→Instrument-Morphing fuer belegte Spuren** — Audio-Spuren mit Clips, FX-Ketten, Sends/Routing, Automation etc. sind weiterhin noch ein ganzer zweiter Bauabschnitt.
- [ ] AVAILABLE: **Instrument-Replace auf bestehender Instrument-Spur via Morph-Guard** — optional den Guard-Pfad auch fuer Instrument→Instrument-Wechsel nutzen (aktuell laeuft das ueber den separaten SmartDrop-to-Track-Pfad).

## v0.0.20.514 — SmartDrop: read-only Dry-Command-Executor / do()-undo()-Simulations-Harness

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Preview-Command-Konstruktion ist jetzt an einen expliziten Dry-Command-Executor / do()-undo()-Simulations-Harness gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_dry_command_executor` und `_summary` ein; hinter der Preview-Command-Konstruktion werden jetzt echte `do()`-/`undo()`-Simulation, Recorder-Callback, Payload-Wiederverwendung und Callback-Trace read-only sichtbar.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **ProjectService exponiert jetzt explizite read-only Dry-Command-Executor-Owner-Pfade** — `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_dry_command_executor` ein; die Methode laesst `ProjectSnapshotEditCommand.do()/undo()` nur gegen einen lokalen Recorder-Callback laufen und beruehrt weder Live-Projekt noch Undo-Stack.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog, Statuslabel und Apply-Readiness zeigen den neuen Dry-Command-Executor sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer den read-only Dry-Command-Executor / do()-undo()-Simulations-Harness; die Checkliste kennt jetzt einen eigenen Punkt fuer die Simulations-Harness-Kopplung.
- [x] FIXED in v0.0.20.515 (Claude Opus 4.6, 2026-03-16): **Den read-only Dry-Command-Executor an einen expliziten Shadow-Commit-/Undo-Push-Rehearsal-Pfad gekoppelt UND ersten echten atomaren Live-Pfad fuer leere Audio-Spur freigeschaltet** — Shadow-Rehearsal simuliert do()/undo() komplett; bei bestandenem Rehearsal + leerer Audio-Spur wird der Minimalfall jetzt echt mutierend ausgefuehrt.

## v0.0.20.513 — SmartDrop: read-only Preview-Command-Konstruktion (`ProjectSnapshotEditCommand(before=..., after=..., ...)`)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Before-/After-Snapshot-Command-Factory ist jetzt an eine explizite Preview-Command-Konstruktion (`ProjectSnapshotEditCommand(before=..., after=..., ...)`) gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_preview_command_construction` und `_summary` ein; hinter der Payload-Factory wird jetzt die reale Constructor-Form, Callback-Bindung und Feldliste von `ProjectSnapshotEditCommand` read-only sichtbar, weiterhin ohne `do()`, Undo-Push oder Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **ProjectService exponiert jetzt explizite read-only Preview-Command-Owner-Pfade** — `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_preview_snapshot_command` ein; die Methode konstruiert `ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)` nur in-memory und liefert daraus nur Metadaten fuer den Guard zurueck.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog, Statuslabel und Apply-Readiness zeigen die neue Preview-Command-Konstruktion sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer die read-only Preview-Command-Konstruktion inklusive Constructor-Form, Callback, Feldliste und Payload-Digests; die Checkliste kennt jetzt einen eigenen Punkt fuer die Preview-Command-Kopplung.
- [x] FIXED in v0.0.20.514 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Preview-Command-Konstruktion spaeter an einen expliziten Dry-Command-Executor / do()-undo()-Simulations-Harness gekoppelt** — der neue Simulations-Harness bleibt weiterhin read-only, ohne Undo-Push, ohne echten Commit, ohne Routing-Umbau und ohne Projektmutation.

## v0.0.20.512 — SmartDrop: read-only Before-/After-Snapshot-Command-Factory / materialisierte Payloads

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only ProjectSnapshotEditCommand-/Undo-Huelle ist jetzt an eine explizite Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payloads gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_command_factory_payloads` und `runtime_snapshot_command_factory_payload_summary` ein; hinter der Command-/Undo-Huelle werden jetzt Before-/After-Payload-Materialisierung, Restore-Callback und Payload-Paritaet read-only sichtbar vorverdrahtet.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **ProjectService exponiert jetzt explizite read-only Before-/After-Snapshot-Factory-Owner-Pfade** — `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_before_after_snapshot_command_factory` ein; die Methode materialisiert Before-/After-Snapshot-Payloads bewusst nur in-memory und liefert daraus nur Payload-Metadaten zurueck.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog, Statuslabel und Apply-Readiness zeigen die neue Before-/After-Snapshot-Factory sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer die read-only Before-/After-Snapshot-Command-Factory inklusive Digests, Byte-Groessen und Payload-Paritaet; die Checkliste kennt jetzt einen eigenen Punkt fuer die Payload-Factory-Kopplung.
- [x] FIXED in v0.0.20.513 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Before-/After-Snapshot-Command-Factory spaeter an eine explizite Preview-Command-Konstruktion (`ProjectSnapshotEditCommand(before=..., after=..., ...)`) gekoppelt** — die neue Preview-Command-Konstruktion bleibt weiterhin read-only, ohne `do()`, Undo-Push, Projektmutation und ohne echtes Audio->Instrument-Morphing.

## v0.0.20.511 — SmartDrop: read-only ProjectSnapshotEditCommand / Undo-Huelle

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Mutation-Gate-/Transaction-Capsule ist jetzt an eine explizite atomare ProjectSnapshotEditCommand-/Undo-Huelle gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_command_undo_shell` und `runtime_snapshot_command_undo_shell_summary` ein; hinter Mutation-Gate und Transaction-Capsule werden jetzt Command-Preview, Command-/Undo-Shell, Snapshot-Capture-/Restore und Undo-Push read-only sichtbar vorverdrahtet.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **ProjectService exponiert jetzt explizite read-only ProjectSnapshotEditCommand-/Undo-Owner-Pfade** — `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_project_snapshot_edit_command` und `preview_audio_to_instrument_morph_command_undo_shell` als sichere Owner-Deskriptoren ein; die echte `ProjectSnapshotEditCommand`-Klasse wird nur sichtbar referenziert, weiterhin ohne Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog, Statuslabel und Apply-Readiness zeigen die neue ProjectSnapshotEditCommand-/Undo-Huelle sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer ProjectSnapshotEditCommand / Undo-Huelle; die Checkliste kennt jetzt einen eigenen Punkt fuer die read-only Command-/Undo-Kopplung.
- [x] FIXED in v0.0.20.512 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only ProjectSnapshotEditCommand-/Undo-Huelle spaeter an eine explizite Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payloads gekoppelt** — die neue Factory bleibt weiterhin read-only, ohne Undo-Push, ohne Projektmutation und ohne echtes Audio->Instrument-Morphing.

## v0.0.20.510 — SmartDrop: read-only Mutation-Gate / Transaction-Capsule

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only atomaren Entry-Points sind jetzt an eine explizite Mutation-Gate-/Transaction-Capsule gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_mutation_gate_capsule` und `runtime_snapshot_mutation_gate_capsule_summary` ein; hinter den atomaren Entry-Points werden jetzt Mutation-Gate-, Capsule-, Snapshot-Capture-/Restore- sowie Commit-/Rollback-Kapselschritte read-only sichtbar vorverdrahtet.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **ProjectService exponiert jetzt explizite read-only Mutation-Gate-/Capsule-Owner-Pfade** — `pydaw/services/project_service.py` fuehrt `preview_audio_to_instrument_morph_mutation_gate`, `preview_audio_to_instrument_morph_transaction_capsule`, `preview_audio_to_instrument_morph_capsule_commit` und `preview_audio_to_instrument_morph_capsule_rollback` als sichere Owner-Deskriptoren ein, weiterhin komplett ohne Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog, Statuslabel und Apply-Readiness zeigen die neue Mutation-Gate-/Capsule-Schicht sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer Mutation-Gate / Transaction-Capsule; die Checkliste kennt jetzt einen eigenen Punkt fuer die read-only Capsule-Kopplung.
- [x] FIXED in v0.0.20.511 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only Mutation-Gate-/Transaction-Capsule spaeter an eine explizite atomare Command-/Undo-Huelle (`ProjectSnapshotEditCommand`) gekoppelt** — die neue Command-/Undo-Huelle bleibt weiterhin read-only, ohne Projektmutation und ohne echtes Audio->Instrument-Morphing.

## v0.0.20.509 — SmartDrop: read-only atomare Commit-/Undo-/Routing-Entry-Points

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Der read-only Pre-Commit-Vertrag ist jetzt an echte Owner-/Service-Entry-Points gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_atomic_entrypoints` und `runtime_snapshot_atomic_entrypoints_summary` ein; bei einem echten Runtime-Owner werden `preview_audio_to_instrument_morph`, `validate_audio_to_instrument_morph`, `apply_audio_to_instrument_morph`, `set_track_kind` und `undo_stack.push` read-only in denselben Minimalfall-Vertrag aufgeloest.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Routing-/Undo-/Track-Kind-Snapshot-Entry-Points werden jetzt als eigene atomare Kopplung sichtbar gezaehlt** — der Guard bindet `capture_*` / `restore_*` der vorbereiteten Snapshot-Objekte fuer `routing_state`, `undo_track_state` und `track_kind_state` in denselben Entry-Point-Plan ein, weiterhin ohne Commit und ohne Mutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog und Apply-Readiness zeigen die neue Entry-Point-Kopplung sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer atomare Commit-/Undo-/Routing-Entry-Points; die Checkliste kennt jetzt einen eigenen Punkt fuer die read-only Entry-Point-Kopplung.
- [x] FIXED in v0.0.20.510 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Die read-only atomaren Entry-Points spaeter an eine explizite Mutation-Gate-/Transaction-Capsule gekoppelt** — die neue Capsule bleibt weiterhin read-only, ohne Projektmutation und ohne echtes Audio->Instrument-Morphing.

## v0.0.20.508 — SmartDrop: Leere Audio-Spur read-only Pre-Commit-Vertrag

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Leere Audio-Spur hat jetzt einen eigenen read-only Pre-Commit-Vertrag hinter dem Minimalfall** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_precommit_contract` und `runtime_snapshot_precommit_contract_summary` ein; Undo-, Routing-, Track-Kind- und Instrument-Commit-Reihenfolge werden fuer den spaeteren Minimalfall read-only vorverdrahtet.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Apply-Readiness kennt jetzt den read-only Pre-Commit-Vertrag** — die Checkliste fuehrt einen eigenen Punkt fuer den spaeteren atomaren Minimalfall der leeren Audio-Spur und trennt diesen weiter von echter Mutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt den read-only Pre-Commit-Vertrag sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen neuen Detailblock fuer Commit-/Rollback-Sequenzen, Mutation-Gate und Preview-Phasen ein.
- [x] FIXED in v0.0.20.509 (OpenAI GPT-5.4 Thinking, 2026-03-16): **Den neuen read-only Pre-Commit-Vertrag an echte atomare Commit-/Undo-/Routing-Entry-Points gekoppelt** — die neue Entry-Point-Kopplung bleibt weiterhin read-only, ohne Projektmutation und ohne echtes Audio->Instrument-Morphing.

## v0.0.20.507 — SmartDrop: Erster spaeterer Minimalfall (leere Audio-Spur) read-only vorqualifiziert

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Leere Audio-Spur wird jetzt als erster spaeterer Minimalfall explizit read-only vorqualifiziert** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `first_minimal_case_report` und `first_minimal_case_summary` ein; der Guard erkennt jetzt gezielt die leere Audio-Spur als spaeteren ersten echten Freigabefall, ohne bereits zu committen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Preview-/Status-Texte unterscheiden jetzt leere Audio-Spur vs. belegte Audio-Spur sauberer** — leere Audio-Spuren erhalten eine eigene Minimalfall-Vorschau und eine passendere read-only Statusmeldung; Audio-Spuren mit Clips/FX bleiben wie bisher klar blockiert.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt den spaeteren ersten Minimalfall sichtbar an** — `pydaw/ui/main_window.py` fuehrt einen eigenen Detailblock fuer die read-only Minimalfall-Vorqualifizierung ein und meldet Bundle-/Apply-Runner-/Dry-Run-Bereitschaft getrennt.
- [ ] AVAILABLE: **Ersten echten Minimalfall spaeter nur fuer leere Audio-Spur mutierend freischalten** — erst wenn der atomare Commit-/Routing-/Undo-Pfad wirklich existiert; weiterhin noch keine Projektmutation.

## v0.0.20.506 — SmartDrop: Read-only Snapshot-Transaktions-Dispatch / Apply-Runner

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Backend-Store-Adapter / Registry-Slot-Backends jetzt an einen echten read-only Snapshot-Transaktions-Dispatch / Apply-Runner gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_apply_runner` und `runtime_snapshot_apply_runner_summary` ein; der neue Runner dispatcht Adapter-, Backend-Store-Adapter- und Registry-Slot-Backend-Pfade read-only hinter dem Snapshot-Bundle.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Apply-Readiness kennt jetzt die Apply-Runner-Ebene** — die Checkliste fuehrt einen eigenen Punkt fuer den read-only Snapshot-Transaktions-Dispatch / Apply-Runner und zaehlt dessen Apply-/Restore-/Rollback-Phasen sichtbar mit.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt den Snapshot-Transaktions-Dispatch / Apply-Runner sichtbar an** — `pydaw/ui/main_window.py` fuehrt den neuen Apply-Runner-Block mit Adapter-/Backend-Store-/Registry-Slot-Dispatch-Infos im Detaildialog und in den Summary-Zeilen mit.
- [ ] AVAILABLE: **Ersten echten Minimalfall spaeter nur fuer leere Audio-Spur freischalten** — erst nach echter Snapshot-/Rollback- und Dry-Run-/Apply-Runner-Absicherung.

## v0.0.20.505 — SmartDrop: Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Runtime-State-Registry-Backends jetzt an konkrete read-only Backend-Store-Adapter / Registry-Slot-Backends gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_state_registry_backend_adapters` und `runtime_snapshot_state_registry_backend_adapter_summary` ein; jede Snapshot-Familie traegt jetzt `adapter_key`, `backend_store_adapter_key` und `registry_slot_backend_key`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Dry-Run kennt jetzt die Adapter-Ebene hinter den Registry-Backends** — der Safe-Runner fuehrt `state_registry_backend_adapter_calls` / `state_registry_backend_adapter_summary` und die neuen `capture_adapter_preview()` / `restore_adapter_preview()` / `rollback_adapter_preview()`-Pfade direkt mit.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt Backend-Store-Adapter / Registry-Slot-Backends sichtbar an** — `pydaw/ui/main_window.py` fuehrt die neue read-only Adapter-Ebene im Detailblock und im Dry-Run-Abschnitt auf.
- [ ] AVAILABLE: **Backend-Store-Adapter / Registry-Slot-Backends spaeter an einen echten read-only Snapshot-Transaktions-Dispatch / Apply-Runner koppeln** — weiterhin zunaechst noch ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: **Ersten echten Minimalfall spaeter nur fuer leere Audio-Spur freischalten** — erst nach echter Snapshot-/Rollback- und Dry-Run-Absicherung.

## v0.0.20.504 — SmartDrop: Runtime-State-Registry-Backends / Handle-Register / Registry-Slots

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Runtime-State-Registries jetzt an konkrete read-only Registry-Backends gekoppelt** — `pydaw/services/smartdrop_morph_guard.py` fuehrt `runtime_snapshot_state_registry_backends` und `runtime_snapshot_state_registry_backend_summary` ein; jede Snapshot-Familie traegt jetzt `backend_key`, `handle_register_key` und `registry_slot_key`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Dry-Run kennt jetzt die Backend-Ebene** — der Safe-Runner fuehrt `state_registry_backend_calls` / `state_registry_backend_summary` und die neuen `capture_backend_preview()` / `restore_backend_preview()` / `rollback_backend_preview()`-Pfade direkt mit.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt Registry-Backend-/Handle-Register-/Registry-Slot-Ebene sichtbar an** — `pydaw/ui/main_window.py` fuehrt die neue read-only Ebene im Detailblock und im Dry-Run-Abschnitt auf.
- [ ] AVAILABLE: **Runtime-State-Registry-Backends spaeter an echte Backend-Store-Adapter / Registry-Slot-Backends koppeln** — weiterhin zunaechst noch ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: **Ersten echten Minimalfall spaeter nur fuer leere Audio-Spur freischalten** — erst nach echter Snapshot-/Rollback- und Dry-Run-Absicherung.

## v0.0.20.502 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Die vorhandenen **Runtime-State-Slots / Snapshot-State-Speicher** an konkrete, read-only **Runtime-State-Stores mit Capture-Handles** gekoppelt; der Dry-Run nutzt jetzt eigene Store-Preview-Aufrufe, weiterhin komplett ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: Die neuen Runtime-State-Stores spaeter an **echte Runtime-State-Registries / Snapshot-State-Stores mit separaten Handle-Speichern** koppeln, weiterhin noch ohne Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.

## v0.0.20.501 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Die vorhandenen **Runtime-State-Halter** an konkrete, separate **Runtime-State-Slots / Snapshot-State-Speicher** gekoppelt — weiterhin komplett read-only, ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: Die neuen Runtime-State-Slots spaeter an **echte Runtime-State-Speicherobjekte / Snapshot-State-Stores mit Capture-Handles** koppeln, weiterhin noch ohne Commit.

## v0.0.20.500 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Die vorhandenen **Runtime-State-Container** an konkrete, separate **Runtime-State-Halter** gekoppelt; der Dry-Run nutzt jetzt eigene Holder-Preview-Aufrufe, weiterhin read-only und ohne Commit.
- [ ] AVAILABLE: Die neuen Runtime-State-Halter im naechsten Schritt an **echte Runtime-State-Slots / Snapshot-State-Speicher** weiter anbinden, weiterhin noch ohne Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.

## v0.0.20.499 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Die vorhandenen **Runtime-Zustandstraeger / State-Carrier** an konkrete, separate **Runtime-State-Container** gekoppelt; der Dry-Run nutzt jetzt eigene Container-Preview-Aufrufe, weiterhin read-only und ohne Commit.
- [ ] AVAILABLE: Die neuen Runtime-State-Container im naechsten Schritt an **echte Snapshot-/State-Objektinstanzen mit separaten Runtime-State-Haltern** weiter anbinden, weiterhin noch ohne Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.

## v0.0.20.498 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Den Morphing-Guard um konkrete **Runtime-Zustandstraeger / State-Carrier** erweitert; die vorhandenen Runtime-Stubs sind jetzt an konkrete read-only Capture-/Restore-State-Methoden gekoppelt und der Dry-Run nutzt diese Carrier direkt, weiterhin ohne Commit.
- [ ] AVAILABLE: Die State-Carrier im naechsten Schritt an **echte Snapshot-/State-Objektinstanzen** mit separaten Runtime-State-Containern koppeln, weiterhin noch ohne Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.

## v0.0.20.497 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Die vorbereiteten Runtime-Snapshot-Objektbindungen sind jetzt an **konkrete read-only Runtime-Stubs / Snapshot-Klassen** gekoppelt; der Dry-Run ruft Capture-/Restore-/Rollback-Previews ueber diese Stub-Klassen auf, weiterhin ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: Die neuen Runtime-Stubs als naechsten Schritt an **echte Snapshot-Capture-/Restore-Klassenmethoden mit Zustandstraegern** koppeln, weiterhin noch ohne echten Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.

## v0.0.20.494 — SmartDrop: Morphing-Guard mit Snapshot-Bundle / Transaktions-Container

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard fuehrt die Runtime-Snapshot-Objekte jetzt in ein stabiles Snapshot-Bundle / einen Transaktions-Container zusammen** — `runtime_snapshot_bundle` und `runtime_snapshot_bundle_summary` sammeln die vorhandenen `snapshot_object_key`-Bindungen in einem read-only Container mit `bundle_key`, `commit_stub`, `rollback_stub`, Capture-/Restore-Methoden und Rollback-Slots.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt die neue Bundle-Ebene sichtbar an** — die Sicherheitsvorschau listet jetzt den Snapshot-Container mit Bundle-Key, Objektanzahl, benoetigten Snapshot-Typen sowie Commit-/Rollback-Stubs.
- [ ] AVAILABLE: **Snapshot-Bundle spaeter an echten Dry-Run-/Transaktions-Runner anbinden** — naechster sicherer Schritt: denselben Container an einen read-only Runner koppeln, der die geplanten Capture-/Restore-Schritte einmal komplett durchlaeuft, weiterhin noch ohne echte Projektmutation.

## v0.0.20.493 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Objekt-Bindung

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard bindet Snapshot-Instanzen jetzt an echte Snapshot-Objektklassen** — `runtime_snapshot_objects` und `runtime_snapshot_object_summary` fuehren die vorhandenen `snapshot_instance_key`-Eintraege in konkrete, read-only Objektbindungen mit `snapshot_object_key`, `snapshot_object_class`, `capture_method`, `restore_method` und `rollback_slot` ueber.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt die Snapshot-Objekt-Bindung jetzt explizit an** — `pydaw/ui/main_window.py` ergaenzt einen neuen Abschnitt `Runtime-Snapshot-Objekt-Bindung`, damit spaetere echte Apply-/Rollback-Logik auf sichtbaren Objektbindungen statt nur auf Instanz-Payloads aufsetzen kann.
- [ ] AVAILABLE: **Snapshot-Objekt-Bindungen spaeter in ein echtes Snapshot-Bundle ueberfuehren** — naechster sicherer Schritt: dieselben Objektbindungen in ein gemeinsames Bundle/Transaction-Container-Objekt legen, weiterhin noch ohne Projektmutation.
- [ ] AVAILABLE: **Dry-Run-Transaktion spaeter exakt mit diesen Objektbindungen speisen** — die spaetere atomare Apply-Phase sollte genau dieselben `snapshot_object_key`/`rollback_slot`-Eintraege fuer Undo-/Routing-/Clip-/FX-Rueckbau wiederverwenden.

## v0.0.20.492 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Instanz-Vorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard materialisiert jetzt read-only Snapshot-Instanzen** — `runtime_snapshot_instances` und `runtime_snapshot_instance_summary` ueberfuehren die vorhandenen `capture_key`-Objekte in konkrete, stabile Snapshot-Instanzen mit `snapshot_instance_key`, `snapshot_payload` und `payload_digest`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt die Snapshot-Instanz-Ebene jetzt explizit an** — `pydaw/ui/main_window.py` ergaenzt einen neuen Abschnitt `Runtime-Snapshot-Instanz-Vorschau`, damit die spaetere echte Apply-Phase auf sichtbaren Instanz-Objekten statt nur auf Capture-Objekten aufsetzen kann.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Kleiner Safety-Hotfix im ProjectService** — die zentralen Morphing-Guard-Funktionen werden jetzt explizit importiert, damit `preview/validate/apply_audio_to_instrument_morph(...)` nicht an fehlenden Symbolen haengen.
- [ ] AVAILABLE: **Snapshot-Instanzen spaeter an echte Undo-/Routing-Snapshot-Objekte binden** — naechster sicherer Schritt: dieselben `snapshot_instance_key`-Objekte an echte Snapshot-Objekte/Handles haengen, weiterhin noch ohne echte Projektmutation.
- [ ] AVAILABLE: **Dry-Run-Transaktion spaeter mit denselben Snapshot-Instanzen speisen** — die spaetere atomare Apply-Phase sollte exakt diese materialisierten Instanz-Objekte fuer Undo-/Routing-/Clip-/FX-Rollback wiederverwenden.

## v0.0.20.491 — SmartDrop: Morphing-Guard mit Runtime-Capture-Objekt-Vorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard baut jetzt echte Runtime-Capture-Objekt-Vorschauen** — `runtime_snapshot_captures` und `runtime_snapshot_capture_summary` binden die vorhandenen Handle-Deskriptoren an konkrete, read-only Capture-Objekte mit `capture_key`, `capture_object_kind`, `payload_preview` und `payload_entry_count`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt die Capture-Ebene jetzt explizit an** — `pydaw/ui/main_window.py` ergaenzt einen neuen Abschnitt `Runtime-Capture-Objekt-Vorschau`, damit spaeteres echtes Snapshot-Capturing auf sichtbaren Objekt-Deskriptoren statt nur auf Handles aufsetzen kann.
- [ ] AVAILABLE: **Capture-Objekte spaeter an echte Snapshot-Instanzen binden** — naechster sicherer Schritt: dieselben `capture_key`-Objekte an echte Undo-/Routing-/Clip-/FX-Snapshot-Instanzen haengen, weiterhin zunaechst noch ohne echtes Morphing.
- [ ] AVAILABLE: **Capture-Payload spaeter um tiefere Param-/Device-Details erweitern** — optionale Vertiefung: z. B. mehr Chain-/Clip-Metadaten pro Capture-Objekt sichtbar machen, weiterhin read-only.

## v0.0.20.490 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Handle-Vorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard-Plan baut jetzt konkrete Runtime-Snapshot-Handle-Deskriptoren auf** — `runtime_snapshot_handles` / `runtime_snapshot_handle_summary` verknuepfen Snapshot-Typ, Capture-Key, Scope und aktuelle Runtime-Ziele read-only, weiterhin ohne Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Apply-Readiness bewertet jetzt auch die vorverdrahtete Handle-Ebene** — ein zusaetzlicher Check macht sichtbar, dass die spaetere Snapshot-Erfassung bereits an konkrete Handle-Schluessel andocken kann.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt jetzt eine Runtime-Snapshot-Handle-Vorschau** — neuer Detailabschnitt `Runtime-Snapshot-Handle-Vorschau` plus kurze Handle-Zusammenfassung im Infotext.
- [ ] AVAILABLE: **Dieselben Handle-Deskriptoren spaeter an echte Snapshot-Capture-Objekte binden** — Undo-/Routing-/Clip-/FX-Snapshots koennen danach dieselben `handle_key`-Eintraege uebernehmen, weiterhin zunaechst noch ohne Apply.
- [ ] AVAILABLE: **Handle-Vorschau spaeter um Param-/Reihenfolge-Details vertiefen** — z. B. Audio-FX-Parameter, Device-Reihenfolge oder Clip-IDs noch expliziter pro Handle sichtbar machen, weiterhin read-only.

## v0.0.20.489 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Vorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard-Plan loest Snapshot-Referenzen jetzt gegen echte Laufzeitdaten auf** — `runtime_snapshot_preview` / `runtime_snapshot_summary` spiegeln den aktuellen Zielspur-, Routing-, Clip- und Chain-Zustand read-only, weiterhin ohne Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt jetzt eine aktuelle Runtime-Snapshot-Vorschau** — zusaetzlicher Abschnitt `Aktuelle Runtime-Snapshot-Vorschau`, damit die spaetere Apply-Freigabe nicht nur geplante Referenzen, sondern auch den aktuell aufloesbaren Zustand sieht.
- [ ] AVAILABLE: **Readiness spaeter an echte Runtime-Objekte binden** — der naechste sichere Vorbau waere, diese Runtime-Vorschau in echte Snapshot-Handles/Objekte umzuschalten, weiterhin zunaechst noch ohne Apply.
- [ ] AVAILABLE: **Snapshot-Vorschau spaeter um Param-/Device-Details vertiefen** — optionale kleine Erweiterung: mehr konkrete Chain-/Clip-Details pro Snapshot-Typ sichtbar machen, weiterhin read-only.

## v0.0.20.488 — SmartDrop: Morphing-Guard mit Apply-Readiness-Checkliste

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard-Plan liefert jetzt eine strukturierte Apply-Readiness-Checkliste** — `readiness_checks` und `readiness_summary` bewerten zentral, welche Guard-Bausteine bereits bereit sind und welche fuer echtes Morphing noch fehlen, weiterhin komplett nicht-mutierend.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt diese Apply-Readiness jetzt explizit an** — zusaetzlicher Abschnitt `Apply-Readiness-Checkliste`, damit spaetere echte Snapshot-/Routing-Freigabe auf einer sichtbaren, konsistenten Sicherheitsmatrix aufsetzen kann.
- [ ] AVAILABLE: **Echte Snapshot-Erfassung spaeter an die Readiness-Checks binden** — sobald Undo-/Routing-/Clip-/FX-Snapshots real erzeugt werden, koennen dieselben Check-Eintraege von `pending/blocked` auf echte Laufzeit-States umschalten.
- [ ] AVAILABLE: **Apply-Phase spaeter aus derselben Readiness-Matrix freischalten** — `can_apply` sollte erst dann kippen, wenn die benoetigten Snapshot-/Routing-/Undo-Bedingungen zentral als bereit markiert sind.

## v0.0.20.487 — SmartDrop: Morphing-Guard mit Snapshot-Referenzvorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Morphing-Guard-Plan liefert jetzt geplante Snapshot-Referenzen** — `snapshot_refs`, `snapshot_ref_map` und `snapshot_ref_summary` werden deterministisch aus `transaction_key` + `required_snapshots` aufgebaut, weiterhin komplett nicht-mutierend.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): **Guard-Dialog zeigt diese Snapshot-Referenzen jetzt explizit an** — zusaetzlicher Abschnitt `Geplante Snapshot-Referenzen`, damit die spaetere echte Apply-Phase klar an vorverdrahtete Referenzen andocken kann.
- [ ] AVAILABLE: **Echte Snapshot-IDs spaeter an dieselben Referenzen binden** — sobald Undo-/Routing-/Clip-/FX-Snapshots real erzeugt werden, koennen sie dieselben Keys/Referenzen direkt uebernehmen statt nur Preview-Handles zu zeigen.
- [ ] AVAILABLE: **Apply-Phase spaeter mit echten Snapshot-Objekten fuettern** — dieselbe Struktur kann danach die atomare Ausfuehrung und den Rueckbau zentral speisen.

## v0.0.20.486 — SmartDrop: Morphing-Guard mit atomarer Transaktionsvorschau

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Morphing-Guard-Plan liefert jetzt eine atomare Transaktionsvorschau** — `required_snapshots`, `transaction_steps`, `transaction_key` und `transaction_summary` werden zentral in `pydaw/services/smartdrop_morph_guard.py` aufgebaut, weiterhin komplett nicht-mutierend.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Guard-Dialog zeigt jetzt noetige Snapshots und den geplanten atomaren Ablauf** — `pydaw/ui/main_window.py` verwendet dieselbe Plan-Struktur fuer zusaetzliche Detailabschnitte wie `Noetige Snapshots` und `Geplanter atomarer Ablauf`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Transaktionsvorschau bleibt bewusst read-only** — weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
- [ ] AVAILABLE: **Echte Apply-Phase spaeter an diese Transaktionsvorschau haengen** — sobald Undo-/Routing-Snapshots freigeschaltet werden, sollte dieselbe Struktur die echte atomare Apply-Phase speisen.
- [ ] AVAILABLE: **Guard-Plan spaeter um echte Snapshot-Referenzen erweitern** — konkrete Undo-/Routing-/Clip-/FX-Snapshot-IDs koennen spaeter direkt im Plan landen.


## v0.0.20.485 — SmartDrop: Guard-Dialog mit Risiko-/Rueckbau-Zusammenfassung

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Morphing-Guard-Plan liefert jetzt strukturierte Sicherheitsdaten** — `impact_summary`, `rollback_lines` und `future_apply_steps` werden zentral in `pydaw/services/smartdrop_morph_guard.py` aufgebaut, weiterhin komplett nicht-mutierend.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Guard-Dialog zeigt jetzt Risiko-/Rueckbau-Abschnitte klar getrennt an** — `pydaw/ui/main_window.py` verwendet dieselbe Plan-Struktur fuer `Risiken / Blocker`, `Rueckbau vor echter Freigabe` und `Spaetere atomare Apply-Phase`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Status bleibt weiterhin ehrlich und sicher** — der Dialog bleibt reine Sicherheitsvorschau; es gibt weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.
- [ ] AVAILABLE: **Echte Apply-Phase spaeter an dieselbe Rueckbau-Struktur anbinden** — wenn Undo-/Routing-Snapshots freigeschaltet werden, sollte dieselbe Plan-Struktur direkt die mutierende Apply-Phase speisen.
- [ ] AVAILABLE: **Guard-Plan spaeter um echte Undo-/Routing-Snapshot-IDs erweitern** — sobald es die atomare Apply-Phase gibt, kann der Plan konkrete Rueckbau-Referenzen tragen statt nur textuelle Sicherheitsvorschau.


## v0.0.20.484 — SmartDrop: Guard-Dialog auf spätere Apply-Phase vorbereitet

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Guard-Dialog liefert jetzt ein Ergebnisobjekt statt nur bool** — `shown / accepted / can_apply / requires_confirmation` werden zentral zurückgegeben, damit dieselbe Dialog-Stelle später direkt für echte Bestätigungen nutzbar bleibt.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Spätere Bestätigungsaktion ist bereits vorverdrahtet** — falls `can_apply` später einmal `True` wird, kann derselbe Dialog bereits zwischen `Morphing bestaetigen` und `Abbrechen` unterscheiden, ohne Canvas/TrackList erneut anzufassen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Geblockter Zustand bleibt unverändert sicher** — solange `can_apply=False` bleibt das Verhalten read-only; `apply_audio_to_instrument_morph(...)` wird nicht in eine echte Mutation umgeschaltet.
- [ ] AVAILABLE: **Echte Guard-Apply-Phase spaeter atomar freischalten** — erst danach `apply_audio_to_instrument_morph(...)` wirklich mutierend machen: Undo-Snapshot, Routing-Umbau, Clip-/FX-Rueckbau in einem Schritt.
- [ ] AVAILABLE: **Dialog spaeter um echte Risiko-/Rueckbau-Zusammenfassung erweitern** — sobald die Apply-Phase existiert, kann dieselbe Dialog-Stelle vor dem echten Morphing noch klarer Undo-/Routing-/Clip-Folgen anzeigen.


## v0.0.20.483 — SmartDrop: Guard-Dialog aus Morphing-Plan

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Sicherheitsdialog direkt aus dem Guard-Plan gespeist** — `MainWindow` zeigt bei geblockten `Instrument -> Audio-Spur`-Drops jetzt optional einen Warning-Dialog, wenn `requires_confirmation` im Morphing-Plan gesetzt ist.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Dialog erklaert Track-Zustand und Guard-Gruende** — Summary, `blocked_message` und `blocked_reasons` aus dem bestehenden Plan werden als kurze Sicherheitsvorschau angezeigt; weiterhin ohne Projektmutation.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Statusbar bleibt synchron** — nach dem Dialog bleibt die bestehende Guard-Statusmeldung aktiv, damit auch ohne Detailansicht klar bleibt, dass Morphing weiterhin gesperrt ist.
- [ ] AVAILABLE: **Dialog optional um spaetere echte Bestaetigungsaktion erweitern** — falls das echte Morphing spaeter freigeschaltet wird, kann derselbe Dialog spaeter eine echte Bestaetigungsaktion an `apply_audio_to_instrument_morph(...)` weiterreichen.
- [ ] AVAILABLE: **Echte Guard-Apply-Phase spaeter atomar freischalten** — erst danach `apply_audio_to_instrument_morph(...)` wirklich mutierend machen: Undo-Snapshot, Routing-Umbau, Clip-/FX-Rueckbau in einem Schritt.


## v0.0.20.482 — SmartDrop: Morphing-Guard-Command vorbereitet

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Audio→Instrument-Morphing als separaten Guard-Command vorbereitet** — neues Service-Modul `pydaw/services/smartdrop_morph_guard.py` liefert jetzt einen zentralen, noch nicht mutierenden Morphing-Plan mit `preview / validate / apply`-Schema.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **ProjectService + MainWindow sprechen jetzt denselben Guard-Vertrag** — `ProjectService.preview/validate/apply_audio_to_instrument_morph(...)` und `MainWindow._on_arranger_smartdrop_instrument_morph_guard(...)` bilden jetzt den künftigen zentralen Einstiegspunkt, ohne schon Routing oder Spurtypen umzubauen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Geblockte Instrument→Audio-Drops laufen jetzt über den Guard-Pfad** — ArrangerCanvas und linke TrackList melden diesen Fall jetzt an den neuen Guard, statt nur lokal Text zu bauen; die Apply-Stelle bleibt in dieser Phase bewusst noch blockiert.
- [ ] AVAILABLE: **Optionalen Bestätigungsdialog aus dem Guard-Plan speisen** — falls Audio-Clips/FX auf der Zielspur liegen, als nächstes einen Sicherheitsdialog direkt aus `blocked_reasons` / `requires_confirmation` aufbauen.
- [ ] AVAILABLE: **Echte Guard-Apply-Phase später atomar freischalten** — erst danach `apply_audio_to_instrument_morph(...)` wirklich mutierend machen: Undo-Snapshot, Routing-Umbau, Clip-/FX-Rückbau in einem Schritt.

## v0.0.20.481 — SmartDrop: Zentrale Morphing-Vorprüfung + Block-Hinweis

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Zentrale SmartDrop-Zielbewertung** — ArrangerCanvas und linke TrackList verwenden jetzt dieselben Regeln aus `pydaw/ui/smartdrop_rules.py`, damit Hover-/Preview-Texte für Instrument / Note-FX / Effekt nicht mehr auseinanderlaufen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Instrument→Audio-Spur zeigt jetzt ehrliche Morphing-Vorprüfung** — die Preview nennt jetzt zusätzlich den Audio-Spur-Kontext (z. B. `Audio-Spur · 3 Audio-Clips · 2 FX`) statt nur pauschal `Morphing folgt später`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Geblockter Drop meldet aktiv warum nichts passiert** — wenn ein Instrument wirklich auf eine Audio-Spur oder anderes bewusst gesperrtes Ziel losgelassen wird, erscheint jetzt eine klare Statusmeldung, dass Audio→Instrument-Morphing erst nach atomarem Undo-/Routing-Rückbau freigeschaltet wird.
- [ ] AVAILABLE: **Optionaler Bestätigungsdialog für künftiges Morphing** — falls Audio-Clips/FX auf der Zielspur liegen, später erst eine explizite Sicherheitsbestätigung zeigen, bevor echtes Morphing freigeschaltet wird.

## v0.0.20.480 — SmartDrop: Kompatible FX-Ziele

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Echter FX-SmartDrop auf bestehende kompatible Ziele** — `Note-FX` können jetzt auf bestehende **Instrument-Spuren**, `Audio-FX` auf bestehende **Instrument-/Audio-/Bus-/Gruppen-Spuren** im ArrangerCanvas und in der linken TrackList wirklich gedroppt und zentral eingefügt werden.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **UI-Hinweise kennen jetzt echte FX-Ziele** — Hover-/Tooltip-/Status-Texte unterscheiden jetzt auch für `Note-FX` und `Effekt` zwischen `Einfügen auf ...` und reiner Preview.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Inkompatible Ziele bleiben bewusst geschützt** — `Note-FX` auf Nicht-Instrument-Spuren und alle weiterhin riskanten Morphing-/Routing-Fälle bleiben reine Preview; kein Spur-Morphing, kein Routing-Umbau.
- [ ] AVAILABLE: **Audio-Spur-Morphing weiter separat absichern** — der bestehende Morphing-Hinweis für `Instrument → Audio-Spur` bleibt bewusst rein visuell, bis Routing/Undo dafür getrennt gehärtet sind.
- [ ] AVAILABLE: **SmartDrop-Replace-Pfad für bestehende Instrument-Spuren separat prüfen** — optionaler späterer Schritt: vorhandenes Instrument gezielt ersetzen statt nur sicher einzufügen, weiterhin ohne Audio→MIDI-Morphing.

## v0.0.20.479 — SmartDrop: Bestehende Instrument-Spur

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Echter Instrument-Drop auf bestehende Instrument-Spuren** — ein Instrument kann jetzt auf eine bereits vorhandene Instrument-Spur im ArrangerCanvas oder in der linken TrackList gedroppt und dort zentral eingefügt werden.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **UI-Hinweise kennen jetzt echte Ziele** — Tooltip/Status unterscheiden zwischen `Instrument → Einfügen auf ...` und reiner Preview (`Nur Preview — SmartDrop folgt später`).
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Audio-Spuren bleiben bewusst geschützt** — Instrument-Drops auf Audio-Spuren bleiben weiter reine Preview mit Morphing-Hinweis; kein Audio→MIDI-Umbau in diesem Schritt.
- [ ] AVAILABLE: **SmartDrop für kompatible FX-Ziele** — nächster kleiner echter Schritt: Audio-FX / Note-FX auf vorhandene kompatible Tracks wirklich droppen, weiterhin ohne Spur-Morphing.
- [ ] AVAILABLE: **Audio-Spur-Morphing weiter separat absichern** — der bestehende Morphing-Hinweis bleibt bewusst rein visuell, bis Routing/Undo dafür getrennt gehärtet sind.

## v0.0.20.478 — SmartDrop: Neue Instrument-Spur aus Leerraum-Drop

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Erster echter SmartDrop nur für leere Fläche** — ein Instrument-Drop **unterhalb der letzten Spur** legt jetzt erstmals wirklich eine **neue Instrument-Spur** an, benennt sie nach dem Plugin und fügt das Instrument dort ein.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Bestehende Spuren bleiben unberührt** — weiterhin **kein** Spur-Morphing, **kein** Drop auf bestehende Track-Ziele und **kein** Routing-Umbau vorhandener Audio-Spuren.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Undo-freundlich über bestehenden Projektpfad** — der Schritt läuft zentral über MainWindow/ProjectService/DevicePanel mit bestehender Projekt-Änderungslogik statt über einen neuen Sonderpfad direkt im Canvas.
- [ ] AVAILABLE: **SmartDrop auf bestehende Instrument-Spur** — nächster kleiner Schritt: Instrument auf bestehende Instrument-Spur droppen und dort gezielt einsetzen/ersetzen, weiterhin ohne Audio→MIDI-Morphing.
- [ ] AVAILABLE: **SmartDrop auf Audio-Spur weiterhin nur Preview** — der bestehende Morphing-Hinweis bleibt bewusst rein visuell, bis Routing/Undo dafür separat abgesichert sind.

## v0.0.20.477 — TrackList Preview-Hinweis Parität

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **TrackList Preview-Sprache an ArrangerCanvas angeglichen** — beim Plugin-Hover zeigt die linke Arranger-TrackList jetzt denselben reinen Preview-Text für Instrument / Effekt / Note-FX wie der Canvas, inklusive `… · Nur Preview — SmartDrop folgt später`.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Status-/Tooltip-Hinweis auch links ergänzt** — TrackList meldet den Preview-Hinweis jetzt ebenfalls als best-effort Tooltip in Cursor-Nähe und über die bestehende Statusleiste; beim Drag-Leave/Drop wird der Hinweis sauber zurückgesetzt.
- [ ] AVAILABLE: **Erster echter SmartDrop nur für leere Fläche** — separat und atomar: ausschließlich `Instrument unter letzter Spur -> neue Instrument-Spur anlegen`, mit Undo und ohne Spur-Morphing anderer bestehender Spuren.
- [ ] AVAILABLE: **TrackList Leerraum-/Header-Hover bewusst neutral halten oder separat gestalten** — falls gewünscht, könnte später noch explizit ein neutraler Hinweis für Gruppenkopf / Nicht-Zielbereich ergänzt werden, weiterhin rein visuell.

## v0.0.20.476 — Arranger Preview-Hinweis am Cursor / in Statusleiste

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Plugin-Preview zeigt jetzt einen klaren Zusatzhinweis** — ArrangerCanvas meldet bei Spur- und Leerraum-Preview jetzt `Nur Preview — SmartDrop folgt später` in Tooltip und Statusleiste.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Hint räumt sich sauber wieder weg** — beim Drag-Leave oder Drop werden Preview-Hinweis und Tooltip zurückgesetzt, ohne bestehende Datei-/Clip-/Cross-Project-Drops zu beeinflussen.
- [ ] AVAILABLE: **TrackList Preview-Hinweis angleichen** — optional denselben reinen Preview-Text auch links in der Arranger-TrackList sichtbar machen.
- [ ] AVAILABLE: **Erster echter SmartDrop nur für leere Fläche** — als späterer separater Schritt könnte ausschließlich `Instrument unter letzter Spur -> neue Instrument-Spur anlegen` atomar mit Undo umgesetzt werden.

## v0.0.20.475 — Arranger Leerraum-Preview unter letzter Spur

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Instrument-Hover unter letzter Spur zeigt jetzt eine cyanfarbene Neuspur-Vorschau** — im freien Arranger-Bereich unterhalb der letzten Spur erscheint rein visuell eine Linie/Badge wie `Neue Instrument-Spur: Surge XT`, noch ohne echten Drop oder Spurerzeugung.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Preview-Status im ArrangerCanvas zentralisiert und gehärtet** — Track-Lane-Preview und Leerraum-Preview verwenden jetzt denselben sicheren Parse/Clear/Update-Pfad; weiterhin ohne Routing-, Undo- oder Projektformat-Eingriff.
- [ ] AVAILABLE: **Cursor-/Status-Tooltip für Preview-Modus** — Zusatzhinweis `Nur Preview — SmartDrop folgt später` direkt am Cursor oder in der Statusleiste.
- [ ] AVAILABLE: **Erster echter SmartDrop nur für leere Fläche** — als späterer separater Schritt könnte ausschließlich `Instrument unter letzter Spur -> neue Instrument-Spur anlegen` atomar mit Undo umgesetzt werden.

## v0.0.20.474 — Arranger/TrackList Plugin Hover Preview

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **TrackList Plugin-Hover** — Die Arranger-TrackList reagiert jetzt rein visuell auf Browser-Plugin-Drags (`application/x-pydaw-plugin`) mit einer cyanfarbenen Ziel-Hervorhebung pro Spur. Das gilt für interne Devices und externe Plugins, die ihre Rolle bereits im Payload tragen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **ArrangerCanvas Plugin-Preview** — Beim Hover über eine Spur zeichnet der Arranger jetzt ein cyanfarbenes Lane-Overlay mit Rollenhinweis wie `Instrument → Preview` oder `Effekt → Preview`, noch ohne echtes Drop-Verhalten.
- [ ] AVAILABLE: **Leerraum-Preview unter letzter Spur** — Rein visuelle cyanfarbene Linie/Badge für „Neue Instrument-Spur“, wenn ein Instrument unterhalb der letzten Spur gehovert wird.
- [ ] AVAILABLE: **Cursor-/Status-Tooltip für Preview-Modus** — Zusatzhinweis „Nur Preview — SmartDrop folgt später“ direkt am Cursor oder in der Statusleiste.

## v0.0.20.473 — Plugins Browser Scope-Badge + Rollen-Metadaten

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Plugins-Browser zeigt jetzt ebenfalls eine Scope-Badge** — der Tab kommuniziert das aktive Spur-Ziel jetzt sichtbar wie Instruments / Effects / Favorites / Recents.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Externe Plugin-Payload trägt Instrument-/Effekt-Rolle mit** — `device_kind` und `__ext_is_instrument` werden bei Add / Drag&Drop mitgegeben, ohne den bestehenden sicheren Insert-Pfad umzubauen.
- [ ] AVAILABLE: **Nächster Safe-Schritt für SmartDrop** — Track-/Arranger-Zielseiten können diese Rollen-Metadaten jetzt für reines **Cyan-Hover-Feedback** auswerten, zunächst noch ohne echtes Spur-Morphing oder Routing-Umbau.

## v0.0.20.472 — VST Header Main-Bus Hint (pedalboard/VST-Host sichtbar)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Externe VST2/VST3-Widgets zeigen jetzt die erkannte Main-Bus-Zeile** — `Vst3AudioFxWidget` blendet direkt unter dem Status eine kleine `Main-Bus: 1→1 / 1→2 / 2→2`-Info ein, sobald die laufende Host-Instanz verfügbar ist.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Funktioniert für FX und Instrumente** — die Anzeige liest den Bus sicher aus der bereits laufenden `Vst3Fx`- bzw. `Vst3InstrumentEngine`, ohne zusätzlichen Plugin-Load und ohne Eingriff in DSP/Routing.
- [ ] AVAILABLE: Optional später dieselbe kompakte Bus-Hinweiszeile auch für CLAP-/LV2-Header ergänzen.

## v0.0.20.471 — CLAP Instrument Engine Reuse Fix (Preset/Editor-Stabilität)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Instrument-Engine wird bei harmlosen Rebuilds jetzt korrekt wiederverwendet** — der Reuse-Check vergleicht für CLAP nicht mehr fälschlich `engine.path` mit dem kompletten `path::plugin_id`-Ref, sondern trennt Bundle-Pfad und Sub-Plugin-ID sauber. Dadurch entstehen beim Refresh keine unnötigen zweiten Surge-XT-Instanzen mehr.
- [ ] AVAILABLE: **CLAP Instrument Parameter-/State-Initialisierung weiter härten** — optional projektseitige CLAP-Parameter beim Engine-Start explizit auf die Live-Instanz zurückschreiben, falls einzelne Plugins bei späteren Rebuilds zusätzliche Restore-Hilfe brauchen.

## v0.0.20.470 — CLAP GUI Async-IO Host Support (POSIX-FD + Timer)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Host meldet jetzt `clap.posix-fd-support` und `clap.timer-support`** — der ctypes-Host stellt beide offiziellen GUI-Helfer bereit und speichert FD-/Timer-Registrierungen pro `_ClapPlugin`-Instanz.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Qt-Editor spiegelt registrierte CLAP-FDs und Timer nur solange der Editor offen ist** — `ClapAudioFxWidget` verbindet registrierte GUI-FDs mit `QSocketNotifier` und Timer-IDs mit `QTimer`, inklusive sauberem Aufräumen beim Editor-Schließen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **FD-/Timer-Callbacks triggern wieder Main-Thread-Pumps** — nach `on_fd()`/`on_timer()` werden angeforderte GUI-Callbacks sofort weitergepumpt; das ist der kleinste sichere Schritt für CLAP-GUIs, die ihren X11-/Async-Eventloop über Host-FD/Timer anbinden.
- [ ] AVAILABLE: Surge XT CLAP lokal erneut prüfen. Falls das Fenster immer noch leer bleibt, nächster isolierter Schritt: optionaler Floating-Window-Fallback nur für problematische CLAP-GUIs, ohne DSP-/Routing-Änderungen.

## v0.0.20.469 — CLAP Editor Bootstrap Main-Thread Handshake + Low-Rate Keepalive

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-GUI-Bootstrap jetzt stufenweise auf dem Main Thread gepumpt** — `_ClapPlugin.create_gui()` führt nach `create()`, nach `set_parent()` und nach `show()` jeweils kurze, erzwungene `on_main_thread()`-Bursts aus. Damit werden Plugins abgefangen, die ihren nativen Child während des GUI-Bootstraps asynchron auf dem Main Thread fertigstellen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Editor-Pump bleibt im geöffneten Editor auf sehr langsamer Kadenz aktiv** — nach der schnellen Prime-Phase stoppt der Timer nicht mehr komplett, sondern läuft mit 120 ms weiter. Dadurch gehen späte `request_callback()`-Bursts des Plugins nicht verloren, ohne die generelle UI-/Audio-Performance zu belasten, solange der Editor geschlossen ist.
- [ ] AVAILABLE: Surge XT CLAP lokal erneut gegenprüfen; falls das Fenster weiterhin leer bleibt, nächsten isolierten Schritt als optionalen Floating-/Fallback-Pfad nur für problematische CLAP-GUIs bauen.

## v0.0.20.468 — CLAP Editor Deferred-Mapping + GUI-Visibility/Resize-Handshake

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Editor erst nach echter Qt/X11-Mapping-Phase öffnen** — `ClapAudioFxWidget` zeigt das Editorfenster jetzt zuerst an und ruft `create_gui()` erst in einem deferred Schritt nach `processEvents()` auf. Das entspricht dem bereits bewährten VST2-Flow und reduziert das Risiko, dass `set_parent()` auf einem noch nicht sauber gemappten X11-Child landet.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-GUI-Container mit `WA_DontCreateNativeAncestors` gehärtet** — der native Child-Container verhält sich jetzt näher an den stabilen VST-Editorpfaden und vermeidet unnötige Native-Ancestor-Ketten.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Resize-/Show-/Hide-Wünsche des Plugins sauber in Qt gespiegelt** — Host und Widget können jetzt angeforderte GUI-Größe sowie `request_show`/`request_hide` gezielt übernehmen, ohne dauernd im schnellen Pump-Takt zu laufen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Editor-Pump nach der Startphase entschärft** — Prime-Phase bleibt schnell für den ersten GUI-Aufbau, danach läuft der Timer nur noch gedrosselt weiter, solange der Plugin-Host wirklich Callbacks anfordert.
- [ ] AVAILABLE: CLAP native GUI lokal gegen Surge XT / XWayland gegenprüfen; falls weiterhin leer: optionaler Fallback-Pfad für Plugins, die Child-Embedding verweigern.

## v0.0.20.467 — CLAP Live-Plugin-Cache + Find-Log-Drosselung

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Live-Plugin-Lookup gecacht** — `ClapAudioFxWidget` hält jetzt pro Widget einen Cache auf die bereits gefundene laufende CLAP-Instanz, statt bei jedem Pump-/GUI-/Editor-Zyklus erneut die kompletten Engine-Maps zu durchsuchen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **`[CLAP-FIND]` Log-Spam gedrosselt** — Statusmeldungen werden nur noch bei Zustandswechseln geschrieben; der endlose Wiederholstrom beim geöffneten Editor verschwindet, ohne die Diagnose komplett abzuschalten.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Sicherer Refresh-Pfad bleibt erhalten** — Editor-Pfade dürfen den Cache weiterhin gezielt mit `use_cache=False` neu auflösen, damit Rebuild-/Reopen-Fälle nicht auf einem veralteten Objekt hängen bleiben.
- [ ] AVAILABLE: CLAP native GUI weiter untersuchen (Surge XT Fenster bleibt bei manchen Setups trotz erfolgreichem `create_gui()` leer).

## v0.0.20.466 — CLAP MIDI-Learn / Kontextmenü-Parität

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP-Parameter-Rechtsklick an LV2/LADSPA/DSSI/VST angeglichen** — die materialisierten CLAP-Parameterzeilen haben jetzt ebenfalls **Show Automation in Arranger**, **MIDI Learn**, **Reset to Default** und die bestehende Fast-Path-Verdrahtung.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Ohne zusätzlichen Performance-Druck umgesetzt** — keine neue Vollregistrierung aller 700+ Parameter; Automation/MIDI-Learn wird nur für tatsächlich gebaute Lazy-UI-Zeilen registriert.
- [ ] AVAILABLE: CLAP native GUI weiter untersuchen (Surge XT Fenster bleibt bei manchen Setups trotz erfolgreichem `create_gui()` leer).

## v0.0.20.464 — CLAP Editor Callback Pump + Lazy Parameter UI

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP Editor Main-Thread Callback Pump** — `_ClapPlugin` bekommt jetzt pro Instanz ein eigenes `clap_host_t` mit `host_data`, Host-Callbacks markieren `request_callback()`/GUI-Resize sauber, und `pump_main_thread()` ruft `plugin.on_main_thread()` gezielt nach `create_gui()` auf. Dadurch bleiben GUI-Fenster wie Surge XT nicht mehr auf einem leeren dunklen Container stehen, obwohl `create_gui()` erfolgreich war.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP GUI Resize/Show Requests an UI durchreichen** — Resize-Wünsche aus `clap.gui` werden zwischengespeichert und vom Qt-Editorfenster übernommen; der Editor kann damit nach dem ersten Paint sauber auf die vom Plugin gewünschte Größe einrasten.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **CLAP Parameter-UI performant gemacht** — `ClapAudioFxWidget` zieht Parameter jetzt zuerst aus der bereits laufenden Runtime-Instanz statt per zusätzlichem `describe_controls()`-Plugin-Load, baut initial nur einen kleinen Batch, lädt weitere Parameter on-demand und kann per Suche gezielt weitere Controls materialisieren. Das reduziert die Hänger beim Spurwechsel mit großen CLAPs (z. B. Surge XT mit ~775 Parametern) deutlich.
- [ ] AVAILABLE: **CLAP Multi-Plugin-Bundle Selector im Browser** — Für `.clap` Bundles mit mehreren Sub-Plugins (z. B. LSP) soll der Browser vor dem Einfügen ein Auswahlfenster zeigen, statt still den ersten Treffer zu nehmen.

## v0.0.20.463 — CLAP Editor: GUI-Finder + WA_NativeWindow + Pin/Roll Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-15): **CLAP Editor: Instrument-Finder** — `_find_live_clap_plugin()` sucht jetzt in `_vst_instrument_engines[track_id]` (Instrumente) UND `_track_audio_fx_map` (FX). Vorher wurden CLAP-Instrumente (Surge XT) nie gefunden → Editor-Button blieb unsichtbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **WA_NativeWindow auf GUI-Container** — `_editor_gui_container` bekommt `WA_NativeWindow` Attribut → echte X11-Window-ID für CLAP `create_gui()`. Ohne dies war `winId()` ungültig → Editor leer.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **ClapInstrumentEngine.has_gui()/get_plugin()** — Accessor-Methoden für GUI-Embedding hinzugefügt.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **GUI-Check Retry-Logik** — `_check_gui_support()` versucht bis zu 5x mit steigendem Delay (Audio Engine braucht Zeit zum Laden).
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Pin via x11_set_above()** — Ersetzt `setWindowFlags()` (X11 Re-Parenting zerstört embedded GUI).
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Roll mit gespeicherter Größe** — `_saved_gui_width`/`_saved_gui_height` vor Einrollen gesichert.

## v0.0.20.458 — CLAP Audio-Port-Bridging + Editor GUI

- [x] FIXED (Claude Opus 4.6, 2026-03-15): **CLAP Audio-Ports Extension** — `clap.audio-ports` abfragen für korrekte Kanalzahl. `_n_in_channels`/`_n_out_channels` getrennt. Buffer-Allokation nach Port-Query. Behebt DISTRHO assertion crash.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Mono↔Stereo Bridging** — Stereo→Mono (average L+R) für Mono-Plugins. Mono→Stereo (duplicate) für Mono-Output.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **CLAP GUI Extension** — `clap.gui` abfragen, `has_gui()`, `create_gui(parent_id)`, `destroy_gui()` in _ClapPlugin. Unterstützt X11, Cocoa, Win32.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **🎛 Editor Button** — ClapAudioFxWidget zeigt Editor-Button wenn Plugin GUI unterstützt. Öffnet eigenständiges Fenster mit embedded Plugin-GUI.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **_is_clap Detection Fix** — Nur .clap-Dateien als CLAP erkennen, nicht alle :: Referenzen (VST3 Surge XT Fix).
- [ ] AVAILABLE: **CLAP Multi-Plugin-Bundle Selector** — Dialog für lsp-plugins.clap etc. (wähle Sub-Plugin aus Bundle).
- [ ] AVAILABLE: **CLAP State Save/Load** — Plugin-State persistieren über clap.state Extension.

## v0.0.20.457 — CLAP Plugin Hosting (First-Class-Citizen)

- [x] FIXED (Claude Opus 4.6, 2026-03-15): **CLAP C-ABI Host** — Komplett neues Modul `pydaw/audio/clap_host.py` (~830 Zeilen). Vollständige ctypes-Definitionen aller CLAP-Structs (Entry, Factory, Plugin, Process, AudioBuffer, Events, Params Extension). `_ClapPlugin` mit komplettem Lifecycle. Keinerlei externe Abhängigkeiten.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **ClapFx Audio-FX Wrapper** — Kompatibel mit `fx_chain.py` (`process_inplace`). RT-Param-Sync mit normalized 0..1 → denormalized min..max. Parameter via `clap_event_param_value_t` Events.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **ClapInstrumentEngine Pull-Source** — Kompatibel mit AudioEngine SamplerRegistry (`note_on`, `note_off`, `pull`). Thread-safe pending notes. Returns numpy (frames, 2) float32.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Plugin Scanner: scan_clap()** — Standard-Suchpfade (Linux/macOS/Windows), CLAP_PATH env, Multi-Plugin-Bundle-Enumeration, scan_all() erweitert.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **FX Chain: ext.clap: Branch** — Instrument-Erkennung + Pull-Source Routing + RT-Param-Ensure.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Plugin Browser: CLAP Tab** — Eigener Tab mit Favoriten, Drag&Drop, Suche, Status-Hints.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **ClapAudioFxWidget** — Slider + SpinBox für alle Parameter, RT-Sync, Project-Persistenz.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Audio Engine: CLAP Instruments** — ClapInstrumentEngine in Phase 1/2/3 des Instrument-Creation-Flow.
- [x] FIXED (Claude Opus 4.6, 2026-03-15): **Device Panel: CLAP Metadata** — __ext_ref, __ext_path, __ext_plugin_name Normalisierung.
- [ ] AVAILABLE: **CLAP Native Editor** — GUI-Subprocess für CLAP Plugins (analog zu VST3 `vst_gui_process.py`). CLAP hat dafür die `clap.gui` Extension.
- [ ] AVAILABLE: **CLAP State Save/Load** — Plugin-State als Blob in project JSON sichern (CLAP `clap.state` Extension).
- [ ] AVAILABLE: **CLAP Preset Browser** — Preset-Liste aus CLAP Plugin (CLAP `clap.preset-load` Extension).
- [ ] AVAILABLE: **CLAP Note Expressions** — Per-Note Expressions (Tuning, Brightness, Pressure) über CLAP Event-System.
- [ ] AVAILABLE: **CLAP MIDI CC/Pitchbend Forwarding** — CC-Events und Pitch Bend an CLAP-Instrumente weiterleiten.
- [ ] AVAILABLE: **CLAP Multi-Port Audio** — Mehrere Audio-Ports pro Plugin (z.B. Surround).

## v0.0.20.451 — Klangfarben-Noten + Notennamen + Schlüssel-Dialog Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-14): **Pitch-Class Klangfarben** — Jede Note wird nach Tonhöhe farblich dargestellt: C=Rot, D=Orange, E=Gelb-Grün, F=Grün, G=Türkis, A=Indigo, H=Pink. Chromatische Farbrad-Zuordnung. Velocity moduliert Helligkeit dezent.
- [x] FIXED (Claude Opus 4.6, 2026-03-14): **Notennamen im Notenkopf** — Jede Note zeigt ihren Namen (C, D, E, F, G, A, B, H) zentriert im Notenkopf. 6pt fett, hoher Kontrast. Deutsche Notation (H statt B).
- [x] FIXED (Claude Opus 4.6, 2026-03-14): **Dezenter Glow-Effekt** — Alle Noten haben sanften Glow in ihrer Klangfarbe. Selektierte Noten stärkeren Glow.
- [x] FIXED (Claude Opus 4.6, 2026-03-14): **Schlüssel-Dialog: QComboBox** — Signal-Problem endgültig gelöst durch QComboBox als Hauptnavigation mit Dropdown aller 12 Schlüssel.

## v0.0.20.449 — Notation Editor: Record Button (MIDI Live-Aufnahme)

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Record Button** — Neuer Toggle-Button "Record" in der Notation-Toolbar. Rot hinterlegt wenn aktiv (`#cc3333`). Ausführlicher Tooltip erklärt die Funktion. Gleicher MIDI-Record-Pfad wie im Piano Roll.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **record_toggled Signal** — `NotationWidget.record_toggled(bool)` Signal wird in `main_window.py` an `MidiManager.set_record_enabled` angeschlossen. Beide Editoren (Piano Roll + Notation) teilen den selben Record-Pfad.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Status-Feedback** — "Notation Record: AN/AUS" wird in der Statusleiste angezeigt.

## v0.0.20.448 — Notenschlüssel-System (Clef Dialog + Rendering + Klick-Interaktion)

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **ClefType Enum + ClefInfo Datenmodell** — Neues Modul `pydaw/ui/notation/clef_dialog.py` mit 12 Schlüssel-Typen: Violin (G), Bass (F), Alt (C3), Tenor (C4), Sopran (C1), Mezzosopran (C2), Bariton (C5/F3), plus 8va/8vb Varianten für Violin und Bass. Jeder Typ hat Unicode-Symbol, Referenz-Note (MIDI), Referenz-Linie, Oktav-Shift und ausführlichen deutschen Tooltip.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **ClefDialog** — Visueller Schlüssel-Picker mit ◀/▶ Pfeil-Buttons, Live-Vorschau (Staff + Schlüssel + Referenz-Note), Name + Info-Text, Transpositions-Option ("Tonhöhen beibehalten" / "In richtige Oktave transponieren"). Exakt wie im professionellen Vorbild.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **StaffRenderer.render_clef()** — Zeichnet Schlüssel-Symbol (Unicode) an der korrekten Referenz-Linie. Oktavierungs-Anzeige (8va/8vb) wird automatisch über/unter dem Schlüssel gerendert. Gibt Bounding-Rect zurück für Klick-Detection.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **StaffRenderer.render_time_signature()** — Zeichnet Taktangabe (z.B. 4/4) auf dem Staff, fett, zentriert.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **_StaffBackgroundItem erweitert** — Rendert jetzt Schlüssel + Taktangabe automatisch. Speichert clef_rect für Klick-Erkennung.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Klick auf Schlüssel → Dialog** — `NotationView.mousePressEvent()` prüft ob der Klick im Schlüssel-Bereich liegt und öffnet dann `ClefDialog`. Schlüssel-Wechsel → sofortiges Refresh.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **𝄞 Schlüssel-Button in Toolbar** — Mit vollständigem Tooltip aller 12 Schlüssel-Typen inkl. Referenz-Noten und Linien. "Tipp: Auch direkt auf den Schlüssel klicken!"
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Clef-aware Pitch Mapping** — `_pitch_to_staff_line()` nutzt jetzt `pitch_to_staff_line(pitch, clef_type)` aus clef_dialog.py. Diatonische Distanz relativ zur Schlüssel-Referenz. Fallback auf Treble wenn import fehlschlägt.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **NotationLayout erweitert** — Neue Felder `clef_type`, `time_sig_num`, `time_sig_denom`.
- [ ] AVAILABLE: **Schlüssel-Persistenz** — Gewählten Schlüssel im Projekt-Modell speichern (aktuell nur Laufzeit).
- [ ] AVAILABLE: **Transposition bei Schlüsselwechsel** — Noten tatsächlich transponieren (Dialog-Option ist UI-fertig, Logik folgt).
- [ ] AVAILABLE: **Schlüsselwechsel innerhalb eines Stücks** — Verschiedene Schlüssel an verschiedenen Beat-Positionen.

## v0.0.20.447 — "Rosegarden" Branding entfernt

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Alle "Rosegarden" Referenzen entfernt** — 0 Referenzen im aktiven Python-Code. Ersetzt durch "professionell", "Pro-Style", "ChronoScaleStudio". Betrifft: notation_view.py, notation_palette.py, main_window.py, README_TEAM.md, BRIEF_AN_KOLLEGEN.md, VISION.md, TODO.md.

## v0.0.20.446 — Professionelles Notations-Kontextmenü (umfassend)

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Professionelles Rechtsklick-Menü** — Umfassendes strukturiertes Kontextmenü mit 12 Kategorien, >80 Einträgen, vollständig deutsch beschriftet mit ausführlichen Tooltips. Organisiert nach professionellem Notations-Editor Paletten-Layout.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Intelligenter Rechtsklick-Trigger** — Rechtsklick auf leeren Bereich = Kontextmenü öffnen. Rechtsklick auf Note = Erase (bestehendes Verhalten). Ctrl+Rechtsklick = immer Menü. Nichts kaputt gemacht.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎵 Notenwerte** — Ganze bis 64tel mit Unicode-Symbolen, Punktiert, Doppelt punktiert. Jeder mit ausführlicher Beschreibung.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **⏸ Pausen** — Ganze Pause bis 32tel-Pause, Eingabemodus Pausen (Y) als Toggle.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **♯♭ Vorzeichen** — Kreuz, Be, Auflöser + NEU: Doppelkreuz (𝄪), Doppel-Be (𝄫) mit Erklärung.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎶 Tuplets** — NEU: Triole (3:2), Duole (2:3), Quintole (5:4), Sextole (6:4), Septole (7:4) als notation_marks.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎻 Artikulation** — NEU: Staccato, Akzent, Tenuto, Marcato, Fermata, Staccatissimo, Portato, Downbow, Upbow, Pizzicato (LH), Flageolett. Alle mit ausführlicher Erklärung.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎼 Dynamik** — NEU: ppp bis fff (8 Stufen mit MIDI-Velocity-Mapping), sf/sfz/fp/fz, Crescendo/Decrescendo Hairpins.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎵 Ornamente** — Triller + NEU: Mordent, Pralltriller, Doppelschlag, Gruppetto, Schleifer, Vorschlag, Tremolo, Vibrato, Glissando.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **🎹 Spielanweisungen** — NEU: 8va/8vb/15ma, Pedal/Pedal-Auf, Una Corda/Tre Corde, Atemzeichen, Cäsur, Arco, Pizzicato, Con/Senza Sordino.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **📐 Struktur/Navigation** — NEU: Segno, Coda, D.C., D.S., D.S. al Coda, D.C. al Fine, Fine, Wiederholungszeichen (Anfang/Ende), Volta 1/2.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **⌒∿ Bögen** — Haltebogen, Bindebogen (bestehend), NEU: Phrasierungsbogen.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **ℹ Über-Dialog** — Kompakte Kurzreferenz aller verfügbaren Symbole.
- [ ] AVAILABLE: **Rendering aller neuen Mark-Typen** — Aktuell werden die neuen Marks als notation_marks gespeichert (Datenmodell OK), aber noch nicht alle visuell gerendert. Nächster Schritt: `_render_notation_marks()` erweitern.
- [ ] AVAILABLE: **Professionelles Seitenpalette** — Vertikale Symbolpalette am rechten Rand als vertikale Symbolpalette zusätzlich zum Kontextmenü.

## v0.0.20.445 — Notation Editor: Playhead + Zeitlineal + Zoom Buttons (Arranger-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Playhead (rote Linie)** — `NotationView.drawForeground()` zeichnet eine rote 2px Linie über die gesamte Szene-Höhe. Effizientes Stripe-Update wie im Arranger (nur alte/neue Position invalidiert, kein Full-Repaint).
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Playhead-Dreieck** — Kleines rotes Dreieck-Marker am oberen Lineal-Rand zeigt exakte Playhead-Position (wie Arranger/Bitwig).
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Zeitlineal mit Bar-Labels** — Halbtransparenter Ruler-Streifen (24px) am oberen Szenen-Rand. Zeigt "Bar 1", "Bar 2" usw. mit Trennlinien pro Takt (4/4 MVP). Zeichnet sich nur für sichtbare Bars (Performance).
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Zoom +/− Buttons** — Toolbar-Buttons "+" und "−" (28×28px) mit 1.25× Faktor, plus "⊙" Reset-Button und %-Label. Exakt wie im Arranger-Vorbild.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Zoom-Label** — Zeigt aktuelles Zoom-Level als Prozent an (z.B. "125%"), aktualisiert sich bei Button-Klick und Transport-Tick.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Transport → Notation Playhead Wiring** — `TransportService.playhead_changed` Signal wird in `NotationWidget._on_playhead_changed()` empfangen und an `NotationView.set_playhead_beat()` weitergeleitet.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Mouse-Lupe Zoom** — Ctrl+Mausrad zoomt X-Achse (bereits vorhanden, jetzt konsistent mit den Buttons). Ctrl+Shift+Wheel = Y-Zoom. Shift+Wheel = horizontaler Scroll.
- [ ] AVAILABLE: **Playhead Click-to-Seek** — Klick ins Lineal setzt Playhead (wie im Arranger).
- [ ] AVAILABLE: **Follow Playhead** — Automatischer Scroll wenn Playhead den sichtbaren Bereich verlässt.
- [ ] AVAILABLE: **Zeitlineal: Time-Sig Support** — Statt 4/4 fix die tatsächliche Taktart des Projekts verwenden.

## v0.0.20.444 — Detachable Panels + Bitwig-Style Multi-Monitor Layout System

- [x] FIXED (Claude Opus 4.6, 2026-03-13): **ScreenLayoutManager** — Neues Modul `pydaw/ui/screen_layout.py` mit vollständigem Multi-Monitor-Layout-System. `DetachablePanel` kapselt jedes Widget für Dock↔Float-Toggle. `ScreenLayoutManager` orchestriert alle Panels und wendet Layout-Presets an.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **8 Layout-Presets** — "Ein Bildschirm (Groß)", "Ein Bildschirm (Klein)", "Tablet", "Zwei Bildschirme (Studio)", "Zwei Bildschirme (Arranger/Mixer)", "Zwei Bildschirme (Hauptbildschirm/Detail)", "Zwei Bildschirme (Studio/Touch)", "Drei Bildschirme" — exakt wie im Bitwig-Style Screenshot-Menü.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Ansicht → Bildschirm-Layout Menü** — Neues Untermenü zeigt erkannte Bildschirme, alle Presets (deaktiviert wenn zu wenige Monitore), individuelles Panel-Abkoppeln, und "Alle andocken".
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **5 registrierte Panels** — Editor, Mixer, Device, Browser, Automation als DetachablePanel registriert. Jedes Panel kann einzeln abgekoppelt und frei auf dem Desktop platziert werden.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Persistenz** — Detach-Status und Fenster-Geometrie werden in SettingsStore gespeichert und beim nächsten Start wiederhergestellt. closeEvent speichert + dockt alles sauber an.
- [x] FIXED (Claude Opus 4.6, 2026-03-13): **Safety-First** — Alle Qt-Operationen in try/except. Re-Docking gibt Widgets immer an original Parent/Position zurück. Schließen eines Float-Fensters dockt automatisch an statt zu zerstören.
- [ ] AVAILABLE: **Keyboard Shortcuts für Layout-Presets** — z.B. Ctrl+Alt+1/2/3 für schnellen Layout-Wechsel.
- [ ] AVAILABLE: **Custom Layout speichern** — User-definierte Layouts als benannte Presets speichern.
- [ ] AVAILABLE: **Screen-Change Detection** — Automatische Layout-Anpassung wenn Monitor an-/abgesteckt wird (QScreen::screenAdded/Removed).
- [ ] AVAILABLE: **Arranger als DetachablePanel** — Aktuell bleibt der Arranger immer im Hauptfenster; könnte auch abkoppelbar sein.

## v0.0.20.441 — Auto-Thinning (Douglas-Peucker) + Lane Tools (Pointer/Pencil/Eraser)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Douglas-Peucker Auto-Thinning** — `AutomationLane.thin(epsilon=0.015)` reduziert 500 raw CC-Punkte auf ~30-50 saubere Punkte bei 1.5% max Abweichung. Wird automatisch bei Transport-Stop, Touch-Timeout und Latch-Ende aufgerufen.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Lane-Werkzeuge: ↖ Pointer, ✏ Pencil, ⌫ Eraser** — Tool-Buttons im Lane-Header. Pointer = Standard (auswählen/verschieben). Pencil = Freihand-Zeichnen mit Auto-Thin bei Release. Eraser = Drag-Rechteck löscht alle Punkte darin.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Recorded Lane Tracking** — `_recorded_lane_pids` Set trackt welche Lanes beschrieben wurden. `thin_recorded_lanes()` thinnt nur diese bei Stop.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Visual Feedback** — Pencil: gelbe Preview-Linie während Zeichnen. Eraser: rotes gestricheltes Selektions-Rechteck.

## v0.0.20.439 — Follow Playhead (Bitwig-Style) + Loop Transport-Feld + Automation-Button entfernt

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **▶ Follow Button** — Neuer Toggle in der Toolbar. Arranger scrollt smooth mit dem Playhead. Wenn Playhead 80% des sichtbaren Bereichs erreicht, springt View so dass Playhead bei 20% steht (Bitwig-Stil).
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Loop Start/End Eingabefelder** — Numerische SpinBoxen (Bar-Einheit) + Loop-Checkbox direkt in der Toolbar. Bidirektional mit Transport + Arranger synchronisiert.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Toter Automation-Button entfernt** — Hatte keinen Click-Handler, war rein dekorativ. btn_auto ist jetzt ein Alias auf btn_follow für Backward-Compat.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording.

## v0.0.20.438 — Fix: Drum Machine Knobs + vollständige Analyse aller Plugins

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Pro Drum Machine Engine-Rewire** — Selbes disconnect-Problem wie Sampler. `kn_gain/pan/tune/cut/res` Engine-Connections werden nach `bind_automation` als Failsafe wieder angeschlossen.
- [x] VERIFIED (Claude Opus 4.6, 2026-03-12): **Vollständige Codebase-Analyse** — Nur Sampler + Drum Machine hatten `valueChanged.disconnect()`. AETERNA, VST2, VST3, LV2, LADSPA, DSSI, Bach Orgel haben das Problem NICHT.

## v0.0.20.437 — Fix: Pro Audio Sampler Knobs wieder funktionsfähig

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Direkte Engine-Connections als Failsafe** — `_setup_automation()` trennte die `valueChanged→engine` Verbindungen und ersetzte sie durch die AutomationManager-Kette. Wenn die Signal-Kette nicht durchkam (race condition, None-Param, signal coalescing), waren die Knobs tot. Fix: Engine-Connections werden nach `bind_automation` zusätzlich wieder angeschlossen.

## v0.0.20.436 — Performance Fix: Automation Recording Audio-Stutter beseitigt

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`sort_points()` während Recording entfernt** — Beats sind monoton steigend während Playback, append ist already in-order. Sort passiert erst bei Project-Save. War O(n log n) pro CC-Message → jetzt O(1).
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`lane_data_changed` throttled auf 8 Hz** — Statt emit bei jedem CC (30-120/s → 30-120 Repaints/s) jetzt max 8 Repaints/s über dirty-set + Timer. Vorher blockierte der GUI-Thread den Audio-Callback.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Legacy-Store-Write während Recording entfernt** — `project.automation_lanes` dict wurde auf jedem CC kopiert+sortiert. Deferred to save.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Selbe Fixes in `MidiMappingService._write_automation_point()`** — Beide Recording-Pfade sind jetzt O(1) pro CC.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording.

## v0.0.20.435 — Fix: Automation Playback dB→Linear RT-Store Overwrite Bug

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`tick()` _mirror_to_rt_store überschrieb Gain-Werte** — `_mirror_to_rt_store()` schrieb den rohen dB-Wert (z.B. -18) in den RT-Store, aber der Audio-Thread erwartet LINEAR (z.B. 0.126). Die Widget-Signal-Kette konvertierte korrekt (dB→linear), wurde aber danach von `_mirror_to_rt_store` überschrieben. Fix: `if not param._listeners:` → Mirror nur für Params ohne aktive Widget-Listener.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`clear_automation_values()` gleicher Guard** — Selbe Logik: keine RT-Mirror wenn Widget-Listener existieren.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording.

## v0.0.20.434 — Fix: CC→Automation Recording für ALLE Plugin-Typen (afx:/afxchain: Support)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_write_cc_automation()` akzeptiert jetzt afx: und afxchain: Prefixe** — Vorher wurde nur `trk:` akzeptiert, wodurch Gain, LV2, LADSPA, DSSI, VST2, VST3 Parameter nie aufgezeichnet wurden. Jetzt: `prefix in ("trk", "afx", "afxchain")` → track_id immer an Position [1].
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Generic CC Re-Registration in `_install_automation_menu()`** — Wenn DevicePanel Widgets rebuildet (project_updated), gehen MIDI Learn Mappings verloren. Jetzt: neue Widgets re-registrieren sich aus `_persistent_cc_map` bei Erstellung.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording (Cubase-Style).
- [ ] AVAILABLE: **Global Automation Arm** — Ein globaler "Arm"-Button in der Toolbar + per-Track Arm/Disarm.

## v0.0.20.433 — CC→Automation Recording für MIDI Learn Fast Path + REC Button

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **MIDI Learn Fast Path schreibt jetzt Automation** — `AutomationManager.handle_midi_message()` ruft nach dem Widget-Dispatch `_write_cc_automation()` auf. Prüft `widget._pydaw_param_id` oder `widget._parameter_id`, liest `track.automation_mode`, schreibt BreakPoints bei write/touch/latch.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_write_cc_automation()` Methode** — Neue Methode in AutomationManager: schreibt in BEIDE Stores (AutomationManager._lanes + legacy project.automation_lanes). Emittiert `lane_data_changed` für Live-UI-Repaint.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Transport+Project Referenzen** — `set_transport()` + `set_project()` in AutomationManager; gewired in `container.py`.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **● REC Button** — Neuer Button im Automation-Panel. Toggle: Touch-Modus (Aufnahme) ↔ Read-Modus. Leuchtet rot bei aktiver Aufnahme. Synchronisiert mit Mode-Dropdown.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording (Cubase-Style). Aktuell werden bei 30-120 CC/Sek alle Punkte gespeichert.
- [ ] AVAILABLE: **Global Automation Arm** — Ein globaler "Arm"-Button in der Toolbar + per-Track Arm/Disarm.
- [ ] AVAILABLE: **Inline Automation im Arranger** — Automation-Lanes als erweiterte Track-Zeilen direkt im Arranger statt separatem Panel (wie Bitwig).

## v0.0.20.432 — Multi-Lane Stacking + Touch/Latch Automation Modi

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Multi-Lane Stacking (Bitwig-Style)** — `EnhancedAutomationLanePanel` zeigt jetzt beliebig viele Automation-Lanes gleichzeitig. Jede Lane hat eigenen Parameter-Selector + Curve-Selector + Close-Button. "+" Button zum Hinzufügen, "×" zum Entfernen. Bis zu 8 Lanes gleichzeitig.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_LaneStrip` Widget** — Neue Klasse: mini Header-Bar (Param-Combo + Curve-Combo + Clear + Close) + `EnhancedAutomationEditor`. Jede Strip ist unabhängig editierbar.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Touch Automation-Modus** — Aufzeichnung nur solange der MIDI-Controller bewegt wird. 500ms nach letztem CC-Wert stoppt die Aufzeichnung automatisch.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Latch Automation-Modus** — Aufzeichnung startet beim ersten CC-Wert und hält den letzten Wert bis Transport-Stop. Timer schreibt alle 100ms den gelatchten Wert.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **AutomationPlaybackService liest Touch/Latch** — Automation wird bei `mode in (read, touch, latch)` abgespielt, nicht nur bei "read".
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **"Show Automation" öffnet neue Lane** — Wenn ein Knob per Rechtsklick → "Show Automation in Arranger" angefragt wird und der Parameter noch nicht sichtbar ist, wird automatisch eine neue Lane hinzugefügt.
- [ ] AVAILABLE: **Inline Automation im Arranger** — Automation-Lanes als erweiterte Track-Zeilen direkt im Arranger statt separatem Panel (wie Bitwig).
- [ ] AVAILABLE: **Global Automation Arm** — Ein globaler "Arm"-Button in der Toolbar + per-Track Arm/Disarm.
- [ ] AVAILABLE: **Automation Thinning** — Reduktion der Breakpoint-Dichte nach Recording (Cubase-Style). Aktuell werden bei 30-120 CC/Sek alle Punkte gespeichert.

## v0.0.20.431 — Automation Bridge Fix (MIDI Record → Lane → Playback)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Kritischer Dual-Store-Bug behoben** — MIDI-aufgezeichnete Automation landete im Legacy-Store (`project.automation_lanes`), aber die UI und der Playback lasen aus dem neuen Store (`AutomationManager._lanes`). Jetzt schreibt `_write_automation_point()` in BEIDE Stores.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Legacy-Format-Bug in AutomationPlaybackService** — `_on_playhead()` erwartete `dict` mit `"points"` Key, bekam aber eine flat `list`. Jetzt werden beide Formate unterstützt.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Write-Mode für Volume/Pan/Device-Params** — Bisher wurde Automation nur für generische Params aufgezeichnet. Jetzt zeichnen Volume, Pan und alle Device-Parameter Breakpoints auf wenn `automation_mode == "write"`.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **MIDI-recorded Lanes in UI sichtbar** — `lane_data_changed` Signal repainted den Editor live; MIDI-erzeugte Lanes erscheinen in der Parameter-Dropdown-Liste (📈 Icon).

## v0.0.20.430 — SF2 Realtime Engine (Live MIDI → SoundFont Audio)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **SF2 SoundFont reagiert jetzt auf Live-MIDI-Keyboard** — Bisher wurde SF2 nur offline gerendert (FluidSynth CLI → WAV-Cache). Neue `FluidSynthRealtimeEngine` (Pull-Source) registriert sich in SamplerRegistry + AudioEngine wie alle anderen Instrumente.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_create_sf2_instrument_engines()` in AudioEngine** — Scannt Tracks nach `plugin_type=="sf2"`, erstellt/reused Engines, registriert Pull-Sources mit `_pydaw_track_id` Tag für Track-Mixer (Vol/Pan/Mute/Solo/VU).
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Polyphonic note_off für alle Live-MIDI-Instrumente** — `_on_live_note_off_route_to_sampler()` gibt jetzt `pitch` an `SamplerRegistry.note_off()` weiter. Vorher wurden alle Noten released, jetzt nur die losgelassene Taste.
- [ ] AVAILABLE: **SF2 Multi-Channel Support** — Aktuell nur Channel 0; könnte auf 16 Kanäle erweitert werden für GM/GS drum kits.
- [ ] AVAILABLE: **SF2 Preset-Browser** — Preset-Liste aus SoundFont anzeigen (Bank/Preset mit Namen).

## v0.0.20.429 — Bounce in Place: plugin_type Matching Fix (chrono-Prefix)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **plugin_type `'chrono.pro_drum_machine'` wurde nicht erkannt** — Der Offline-Render-Code prüfte nur `'drum_machine'`, `'sampler'`, `'aeterna'`, aber die Plugin-Registry verwendet `'chrono.pro_drum_machine'`, `'chrono.pro_audio_sampler'`, `'chrono.aeterna'`. Alle Prüfungen erweitert auf `in ('drum_machine', 'chrono.pro_drum_machine')` etc.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Bach-Orgel Fallback** — `'chrono.bach_orgel'` wird jetzt ebenfalls als internes Instrument erkannt.

## v0.0.20.428 — Bounce in Place: Best-Practice Fix (Borrow Running Engine)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Best-Practice Ansatz wie Bitwig/Ableton/Cubase** — Statt eine NEUE VST-Instanz für den Offline-Bounce zu erstellen (was bei vielen Plugins scheitert), wird jetzt die BEREITS LAUFENDE Engine-Instanz aus der Audio-Engine "geborgt". Das Plugin ist schon geladen, initialisiert und produziert garantiert Audio.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_audio_engine_ref` Brücke** — `ServiceContainer` setzt `project._audio_engine_ref = audio_engine`, damit ProjectService auf die laufenden VST-Engines zugreifen kann (`_vst_instrument_engines[track_id]`).
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_borrowed` Flag** — Geborgte Engines werden NICHT mit `shutdown()` beendet (gehören der Audio-Engine). Nach dem Bounce: `all_notes_off()` + Flush-Blocks zum Aufräumen.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Relaxierte `kind=='instrument'` Prüfung** — Die strenge Prüfung `kind == 'instrument'` hat Tracks mit VST-Devices ausgesperrt, wenn `kind` nicht korrekt gesetzt war. Jetzt: `_track_has_vst_device()` prüft sowohl `audio_fx_chain` als auch die laufende Audio-Engine.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Offline-Fallback beibehalten** — Falls keine laufende Engine verfügbar ist (z.B. frisch geladenes Projekt), wird weiterhin eine neue Instanz erstellt (mit Suspend/Resume + Warmup).

## v0.0.20.427 — Bounce in Place: VST Offline Fix #2 (Warmup + Suspend/Resume + Diagnostics)

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **VST2 Suspend/Resume nach State-Restore** — Nach `set_chunk()` brauchen viele VSTs (Dexed, Helm, etc.) einen `effMainsChanged(0)→effMainsChanged(1)→effStartProcess` Zyklus, damit der geladene State aktiv wird. Ohne diesen Schritt bleibt das Plugin im "Schlafmodus".
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **200ms Warmup-Phase** — VST-Plugins werden nach Engine-Erstellung mit ~200ms Leer-Audio "aufgewärmt", damit interne Oszillatoren, Filter und Buffer initialisiert sind bevor MIDI-Noten ankommen.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Relaxierte Instrument-Erkennung** — `__ext_is_instrument` ist oft nicht im gespeicherten Projekt-JSON vorhanden. Jetzt: wenn wir MIDI-Clips bouncen und kein internes Engine (Sampler/Drum/Aeterna) passt, wird jedes `ext.vst` Device als Instrument angenommen.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Umfangreiche Diagnose-Logs** — Jeder Schritt des Offline-Bounce-Prozesses wird nach stderr geloggt: Device-Scan, Engine-Erstellung, MIDI-Events, Peak-Level, WAV-Datei-Analyse. Zeigt `AUDIO OK` oder `SILENT!` an.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Exception-Logging statt stummes Verschlucken** — Alle `except: pass` Blöcke im Bounce-Pfad loggen jetzt Fehler + Traceback nach stderr.

## v0.0.20.426 — Bounce in Place: VST2/VST3 Instrument Offline Rendering Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Bounce in Place erzeugt jetzt Audio für VST2/VST3-Instrument-Tracks** — zuvor wurde eine stille WAV-Datei erstellt, weil `_render_track_subset_offline` nur interne Engines (Sampler, DrumMachine, Aeterna) kannte. Jetzt wird automatisch eine temporäre `Vst2InstrumentEngine` / `Vst3InstrumentEngine` aus dem `audio_fx_chain` des Tracks instanziiert und für Offline-Rendering genutzt.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_create_vst_instrument_engine_offline()`** — neue Methode: scannt `track.audio_fx_chain` nach `ext.vst2:`/`ext.vst3:` Instrument-Devices, erstellt temporäre Engine-Instanz mit restored Plugin-State (`__ext_state_b64`), nutzt Offline-RTParamStore.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **`_render_vst_notes_offline()`** — neue Methode: rendert MIDI-Noten durch VST-Engine mit korrektem note_on/note_off-Scheduling (statt `trigger_note()`). Inklusive 1-Sekunde Release-Tail für natürliche Ausklingphase.
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Bounce in Place + Quelle stummschalten** — funktioniert jetzt korrekt auch für VST2-Instrumente (Dexed, Helm, etc.).
- [x] FIXED (Claude Opus 4.6, 2026-03-12): **Bounce in Place (Dry)** — ebenfalls für VST-Instrumente unterstützt; FX-Chain-Processing wird korrekt angewendet (VST-Instrument wird von ChainFx übersprungen, nur Audio-FX werden verarbeitet).

## v0.0.20.380 — VST3 Instrument Engine (MIDI→Audio Host für Surge XT & Co.)

- [x] FIXED (Claude Opus 4.6, 2026-03-11): **Vst3InstrumentEngine** — neue Klasse in `vst3_host.py` für VST3/VST2-Instrument-Hosting via pedalboard. Empfängt MIDI über SamplerRegistry, rendert Audio via `plugin.process(midi_msgs, duration, sr)`, registriert sich als Pull-Source im Audio-Callback.
- [x] FIXED (Claude Opus 4.6, 2026-03-11): **Instrument-Erkennung in FX-Chain** — `is_vst_instrument()` prüft `plugin.is_instrument`; erkannte Instrumente werden aus der FX-Verarbeitung übersprungen und stattdessen als Pull-Source gehostet.
- [x] FIXED (Claude Opus 4.6, 2026-03-11): **Polyphonic note_off** — `SamplerRegistry.note_off(track_id, pitch)` unterstützt jetzt pitch-spezifisches Note-Off für polyphonische VST-Instrumente (Surge XT).
- [x] FIXED (Claude Opus 4.6, 2026-03-11): **MIDI-Routing in HybridAudioCallback** — beide Callbacks (Sounddevice + JACK) übergeben jetzt `pitch` an `note_off()`.
- [x] FIXED (Claude Opus 4.6, 2026-03-11): **AudioEngine._create_vst_instrument_engines()** — erstellt und registriert Instrument-Engines automatisch bei `rebuild_fx_maps()`.
- [ ] AVAILABLE: **VST3 Instrument Preset Browser** — Preset-Auswahl direkt im Device-Widget für Surge XT.
- [ ] AVAILABLE: **Multi-Instrument pro Track** — aktuell nur 1 VST-Instrument pro Track (wie Ableton); mehrere wäre Ableton-Live-Rack-Style.
- [ ] AVAILABLE: **MIDI CC/Pitchbend Forwarding** — CC-Events und Pitch Bend an VST-Instrumente weiterleiten.

## v0.0.20.375 — Bidirektionale VST Param-Sync + Editor-Fenstertitel

- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Bidirektionale Param-Sync DAW ↔ Editor** — vollständiges JSON-Protokoll über QProcess stdout/stdin:
  - **Editor→DAW** (`vst_gui_process.py` Polling-Thread, 80 ms): Param-Änderungen im nativen Fenster werden via `{"event":"param","name":...,"value":...}` gesendet; `_apply_param_from_editor()` schreibt in RTParamStore + updated Slider mit QSignalBlocker (kein Echo-Loop).
  - **DAW→Editor** (`_send_to_editor()`): Slider/Spinbox/Checkbox-Änderungen senden `{"cmd":"set_param","name":...,"value":...}` zu subprocess stdin; `_StdinReader`-Thread setzt `setattr(plugin, name, value)`.
  - **Initialer Snapshot**: `ready`-Event trägt jetzt `params`-Liste mit allen Anfangswerten; Widget übernimmt sie sofort.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Editor-Fenster-Titel** `"PluginName  [TrackName]  — Py_DAW"` — `_get_track_name()` liest Track.name aus ProjectService; `--title`/`--track` Args übergeben; `show_editor(window_title=...)` mit graceful TypeError-Fallback für ältere pedalboard-Versionen.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): `QProcess.ProcessChannelMode.SeparateChannels` statt MergedChannels — ermöglicht stabiles stdin-Schreiben ohne stdout-Korruption.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): `_get_track_name()` + `_send_to_editor()` als wiederverwendbare Hilfsmethoden in `Vst3AudioFxWidget`.
- [ ] AVAILABLE: Bidirektionale Param-Sync auch für LADSPA- und LV2-Devices.
- [ ] AVAILABLE: Editor-Fenster-Position/Größe persistieren (pro Plugin-Pfad in Projekt-JSON).

## v0.0.20.374 — VST3 Native Editor Subprocess + Param-Source-Hint

- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Nativer VST3/VST2-Editor als Subprocess** (`pydaw/audio/vst_gui_process.py` neu) — isolierter `QProcess` lädt Plugin + ruft `show_editor()` auf. Kein Block des Qt-Main-Thread, Audio-Engine komplett unbeeinflusst. Läuft auf Linux (X11/XWayland), macOS, Windows.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **`🎛 Editor`-Button** im VST-Widget-Header — startet/stoppt den Subprocess. Visuelles Feedback: `⏳ Editor…` beim Starten, `✕ Editor schließen` (grün) wenn aktiv.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Param-Source-Hint** — `_lbl_param_source` zeigt kursiv ⚡ live / ⏳ async / 🔄 main-thread.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **`closeEvent()`** im Widget killt Editor-Subprocess sauber beim Schließen.
- [ ] AVAILABLE: Bidirektionale Param-Sync zwischen Editor-Subprocess und Audio-Engine.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Editor-Fenster-Titel** — `"PluginName  [TrackName]  — Py_DAW"` via `--title` + `--track` Args; `show_editor(window_title=...)` mit graceful TypeError-Fallback.

## v0.0.20.373 — VST3 Widget Main-Thread Reload Hotfix

- [x] FIXED (GPT-5, 2026-03-10): **`QCheckBox`-Import im VST3-Widget ergänzt** — Bool-/Toggle-Parameter können wieder stabil als Checkbox-Zeilen aufgebaut werden.
- [x] FIXED (GPT-5, 2026-03-10): **Async-Fallback macht jetzt einen einmaligen Main-Thread-Retry**, wenn `pedalboard` explizit `must be reloaded on the main thread` meldet.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **Parameter-Quell-Hint** — `_lbl_param_source` zeigt jetzt ⚡ live / ⏳ async / 🔄 main-thread je nach Ladepfad.

## v0.0.20.371 — VST3 Project-State Raw-Blob Save/Load

- [x] FIXED (GPT-5, 2026-03-10): **Projekt-Save bettet jetzt für externe VST2/VST3-Devices einen `raw_state`-Blob als Base64** (`__ext_state_b64`) ins Device-`params` ein — erzeugt aus den aktuell gespeicherten Plugin-Parametern, ohne die laufende DSP-Instanz anzufassen.
- [x] FIXED (GPT-5, 2026-03-10): **`Vst3Fx` stellt den gespeicherten Base64-Blob beim Laden zuerst wieder her** und übernimmt danach wie bisher die explizit gespeicherten Parameterwerte; dadurch bleiben Preset-/State-Daten projektseitig erhalten, ohne den Audio-Callback-Pfad umzubauen.
- [x] FIXED (GPT-5, 2026-03-10): **`Vst3AudioFxWidget` zeigt jetzt direkt im Header einen kleinen Preset-/State-Hinweis**, ob für dieses externe VST2/VST3-Device bereits ein eingebetteter `__ext_state_b64`-Blob im Projekt vorhanden ist, inklusive kompakter Größenanzeige – rein UI-seitig, ohne Audio-/Host-Eingriff.
- [ ] AVAILABLE: Optional später einen **expliziten „Preset/State aktualisieren“-Button** im VST3-Widget ergänzen, falls künftig auch native Plugin-Editoren internen State ändern dürfen.

## v0.0.20.370 — VST3 Widget Runtime-Param-Reuse Hotfix

- [x] FIXED (GPT-5, 2026-03-10): **`Vst3AudioFxWidget` bevorzugt jetzt die bereits laufende DSP-Instanz** — Parameter-Metadaten werden zuerst direkt aus dem kompilierten `Vst3Fx` im `audio_engine._track_audio_fx_map` gelesen, statt denselben Bundle-/Sub-Plugin-Pfad sofort erneut im Worker zu laden.
- [x] FIXED (GPT-5, 2026-03-10): **Kurzer Rebuild-Wartepfad vor Async-Fallback** ergänzt — frisch eingefügte VST3-Devices bekommen ein paar kurze Poll-Versuche auf die Live-Instanz; erst danach startet der bestehende Background-Loader.
- [x] FIXED (GPT-5, 2026-03-10): **`Vst3Fx._load()` extrahiert Parameter jetzt direkt aus der bereits geladenen Plugin-Instanz** — vermeidet unnötigen Doppel-Load desselben VSTs während des FX-Map-Builds.
- [ ] AVAILABLE: Optional im VST-Header einen kleinen Status wie **„Parameter: live“ / „Parameter: fallback“** anzeigen, weiterhin nur UI-seitig.

## v0.0.20.369 — VST3 Mono/Stereo Bus-Adapt Hotfix

- [x] FIXED (GPT-5, 2026-03-09): **`Vst3Fx` passt Hauptbus-Kanalzahlen jetzt sicher an** — Mono-VSTs wie **LSP Autogain Mono / Filter Mono** laufen im weiterhin stereo-internen Track-FX-Pfad, ohne pro Audio-Block denselben `does not support 2-channel output`-Fehler zu werfen.
- [x] FIXED (GPT-5, 2026-03-09): **Eingang/ Ausgang werden jetzt gebrückt statt starr 2→2 erzwungen** — Stereo→Mono wird sauber heruntergemischt, Mono→Stereo wieder dupliziert, 2→1 und 1→2 bleiben damit ebenfalls safe.
- [x] FIXED (GPT-5, 2026-03-09): **Fehlertext-Parser + Layout-Cache** ergänzt — wenn `pedalboard` die Busgröße erst beim `process()` verrät, merkt sich der Host die erkannte 1/1- bzw. 1/2-/2/1-Konfiguration und spammt nicht weiter jede Callback-Runde dieselbe Fehlermeldung.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-15): **Externe VST-Header zeigen jetzt die erkannte Main-Bus-Zeile** (`1→1`, `1→2`, `2→2`) direkt im Widget an — rein UI-seitig, aus der bereits laufenden Host-Instanz gelesen.

## v0.0.20.368 — VST3 Widget Async-Param-Load Fix

- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **Vst3AudioFxWidget: describe_controls async** — Plugin-Parameter-Lade blockierte Qt-Main-Thread (10-60 s Freeze bei "Add to Device"). Neuer _Vst3ParamLoader(QThread) lädt Parameter im Hintergrund, UI zeigt sofort "Lade Plugin-Parameter…" Status.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **_build_rows_from_infos()** — Row-Build-Code aus synchronem Pfad extrahiert, wird jetzt in _on_params_loaded() nach async-Load aufgerufen.

## v0.0.20.367 — VST3 Startup Cache-Guard + Probe-Timeout

- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **Warmer Start ohne Rescan** — `PluginsBrowserWidget.__init__()` ruft `rescan()` nur noch dann auf, wenn kein frischer Cache (< 4h) vorhanden ist. Sonst wird der Cache sofort angezeigt.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`cache_is_fresh(max_age_seconds)`** in `plugin_scanner.py` — prüft `ts`-Feld des Caches, gibt `True` zurück wenn frisch.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`probe_multi_plugin_names()` mit 15-Sekunden-Timeout** — hängendes VST3-Binary wird nach 15s abgebrochen; Warning auf stderr, Scan läuft weiter.
- [ ] AVAILABLE: Optional sichtbare Sub-Plugin-Zeile im Device-Header für externe VSTs.
- [ ] AVAILABLE: Insert-Selbsttest / Diagnose-Toast wenn externes VST nach Insert keine Parameter liefert.
- [ ] AVAILABLE: Lazy "Sub-Plugin wählen…" Dialog für unbekannte Multi-Plugin-Bundles (kein Eager-Scan).
- [ ] AVAILABLE: Scanner-Modus-Schalter (safe/deep) im Plugins-Browser als UI-Option.


## v0.0.20.366 — VST3 Device Exact-Reference Hotfix

- [x] FIXED (GPT-5, 2026-03-09): **Externe VST3/VST2-Devices speichern jetzt immer eine kanonische Komplett-Referenz** (`__ext_ref`) zusätzlich zu Basis-Pfad und optionalem `__ext_plugin_name`.
- [x] FIXED (GPT-5, 2026-03-09): **Browser → DevicePanel → FX-Widget → Live-Host** bevorzugt jetzt diese exakte Referenz; damit gehen Multi-Plugin-Sub-Plugins beim Insert/Rebuild nicht mehr still verloren.
- [x] FIXED (GPT-5, 2026-03-09): **DevicePanel normalisiert VST-Insert-Metadaten** beim Hinzufügen, damit auch gemischte alte/neue Payloads robust im Projekt landen.
- [ ] AVAILABLE: Optional den Device-Header bei externen VSTs zusätzlich um eine **sichtbare Sub-Plugin-Zeile** erweitern (Datei + Sub-Plugin getrennt lesbar).
- [ ] AVAILABLE: Optional einen kleinen **Insert-Selbsttest / Diagnose-Toast** ergänzen, wenn ein externes VST nach dem Insert keine Parameter liefert.

## v0.0.20.365 — VST3 Startup Scan Hang Hotfix

- [x] FIXED (GPT-5, 2026-03-09): **Automatischer VST3-Startscan instanziiert nicht mehr jedes Plugin** per `pedalboard.load_plugin()`; dadurch hängt der Programmstart nicht mehr an problematischen Plugins wie `ZamVerb.vst3`.
- [x] FIXED (GPT-5, 2026-03-09): **Eager Multi-Plugin-Probing** ist jetzt auf bekannte sichere Bundle-Sammlungen wie `lsp-plugins.vst3` begrenzt; normale VST3s werden beim Scan nur als Datei/Bundles gelistet.
- [x] FIXED (GPT-5, 2026-03-09): **Debug-Override** `PYDAW_VST_MULTI_PROBE=1` ergänzt, um das breite Probe-Verhalten bei Bedarf bewusst wieder einzuschalten.
- [ ] AVAILABLE: Optional einen **Lazy „Sub-Plugin wählen…“ Dialog** ergänzen, damit auch unbekannte Multi-Plugin-Bundles ohne Eager-Scan sauber auswählbar bleiben.
- [ ] AVAILABLE: Optional einen kleinen **Scanner-Modus-Schalter** (safe/deep) im Plugins-Browser ergänzen.

## v0.0.20.364 — VST3 Browser Multi-Plugin Bundle Fix

- [x] FIXED (GPT-5, 2026-03-09): **VST3-Browser scannt Multi-Plugin-Bundles** wie `lsp-plugins.vst3` jetzt in einzelne auswählbare Sub-Plugins auf, sobald `pedalboard` verfügbar ist.
- [x] FIXED (GPT-5, 2026-03-09): **Externe VST-Metadaten** tragen jetzt zusätzlich `__ext_plugin_name`, damit Browser, Device-Widget und Live-Host exakt dasselbe Sub-Plugin laden.
- [x] FIXED (GPT-5, 2026-03-09): **`install.py` + `requirements.txt`** ergänzen jetzt `pedalboard`, damit VST2/VST3-Hosting auf frischen Setups nicht nur zufällig lokal funktioniert.
- [x] FIXED (GPT-5, 2026-03-09): Veraltete **Placeholder-Texte** im Plugins-Browser bereinigt; Status/Hinweise sprechen jetzt von echtem Live-Hosting statt Dummy-Verhalten.
- [ ] AVAILABLE: Optional einen kleinen **„Sub-Plugin wählen…“ Fallback-Dialog** ergänzen, falls ein alter Cache-Eintrag noch als Bundle-Datei statt als einzelnes Sub-Plugin angeklickt wird.
- [ ] AVAILABLE: Optional einen kleinen **„Rescan empfohlen“ Hinweis** anzeigen, wenn der VST-Cache noch aus Vor-Multi-Plugin-Zeiten stammt.

## v0.0.20.363 — VST3/VST2 Live Hosting via pedalboard

- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **VST3/VST2 Plugins live gehostet** via `pedalboard` (Spotify). Plugins werden bei Audio-Rendering tatsächlich ausgeführt statt Placeholder.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`pydaw/audio/vst3_host.py`** neu erstellt — `Vst3Fx` mit `process_inplace(buf, frames, sr)` kompatibel zu FxChain. Parameter-Discovery via `describe_controls()`.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`pydaw/audio/fx_chain.py`** — `ext.vst3:` und `ext.vst2:` Branch hinzugefügt (analog zu LADSPA-Branch).
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`Vst3AudioFxWidget`** in `fx_device_widgets.py` — zeigt alle VST3-Parameter als Slider/Spinbox/Checkbox, mit RT-Sync, Persistenz und Automation-Menü.
- [x] FIXED (Claude Sonnet 4.6, 2026-03-09): **`plugins_browser.py`** — Status-Meldung zeigt jetzt "VST3 live OK (pedalboard X.Y.Z)" statt "Placeholder (Hosting noch nicht implementiert)".
- [x] FIXED (Claude Sonnet 4.6, 2026-03-10): **VST3 Native Editor** — `🎛 Editor`-Button in `Vst3AudioFxWidget`; startet `vst_gui_process.py` als isolierten `QProcess`-Subprocess.
- [ ] AVAILABLE: **VST3 Preset-Speicherung** — Plugin-State als Base64-Blob in project JSON sichern.

## v0.0.20.361 — MIDI Content Scaling + Instrument-Browser Doppelklick-Fix

- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Alt + Drag am MIDI-Clip-Rand = Content Scaling** — alle MIDI-Noten proportional zur neuen Cliplänge skaliert (Bitwig-Style).
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Alt + Drag am Audio-Clip-Rand = Audio Stretch** — clip.stretch proportional angepasst.
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Lazy Update Pattern** + **Original-Snapshot** für Rundungssicherheit.
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Neon-Glow-Effekt** (Cyan/Teal) + Skalierungsfaktor-Overlay (🎵 MIDI / 🔊 Audio).
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Alt+Shift+Drag = Free Mode** (pixelgenau, kein Grid-Snap).
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Instrument-Browser Doppelklick** repariert — `_add_instrument_to_device()` war leer.
- [x] FIXED (Claude Opus 4.6, 2026-03-09): **Alt+Drag-auf-Body DnD-Copy entfernt** (kollidierte mit Content Scaling, Ctrl+Drag ist die richtige Copy-Methode).
- [ ] AVAILABLE: **Multi-Clip Content Scaling** — mehrere selektierte MIDI-Clips gleichzeitig skalieren.

## v0.0.20.360 — DAWproject Export Cross-Device Hotfix

- [x] FIXED (GPT-5, 2026-03-08): Kritischen Export-Fehler **`[Errno 18] Ungültiger Link über Gerätegrenzen hinweg`** behoben. Finale `.dawproject`-Datei wird jetzt als **temporäre Schwesterdatei im Zielordner** erzeugt und erst danach per `os.replace()` übernommen. Dadurch funktionieren Exporte auch dann, wenn `/tmp` und Benutzerordner auf unterschiedlichen Dateisystemen liegen.

## v0.0.20.359 — DAWproject Export UI Hook (sichtbar im Datei-Menü)

- [x] FIXED (GPT-5, 2026-03-08): Sicherer Menü-Hook **`Datei → DAWproject exportieren… (.dawproject)`** ergänzt, inklusive Hintergrund-Export via `DawProjectExportRunnable`, Progress-Dialog und Summary-Dialog — ohne Core-/Playback-Eingriff.
- [ ] AVAILABLE: Export-Dialog optional später um sehr kleine **Optionen** ergänzen (z. B. Audio einbetten an/aus, Validierung an/aus), weiterhin nur UI/FileIO.
- [ ] AVAILABLE: Ein kleiner **Roundtrip-Testpfad** `Export → neues leeres Projekt → Import` kann als separater sicherer QA-Schritt ergänzt werden.


## v0.0.20.358 — DAWproject Exporter Scaffold (snapshot-safe, ohne Core-Eingriff)

- [x] FIXED (GPT-5, 2026-03-08): Neuer entkoppelter **`DawProjectExporter`** als reiner **Data Mapper** ergänzt — arbeitet ausschließlich auf einer tief kopierten Snapshot-`Project`-Instanz.
- [x] FIXED (GPT-5, 2026-03-08): Sicherer **Temp-File-First Exportpfad** umgesetzt: Staging-Ordner → `project.xml` / `metadata.xml` / `audio/` → temporäre ZIP → XML/ZIP-Validierung → atomarer Move.
- [x] FIXED (GPT-5, 2026-03-08): **Automation-Lanes**, **Audio-Referenzen** und konservative **Base64-Plugin-State-Blobs** in ein erstes `.dawproject`-Export-Skelett gemappt, ohne Playback-/DSP-Core anzufassen.
- [x] FIXED (GPT-5, 2026-03-08): Optionalen **`DawProjectExportRunnable`** für non-blocking UI-Integration ergänzt, weiterhin ohne MainWindow-Hook.
- [ ] AVAILABLE: Sicheren **MainWindow-Menü-Hook** `Datei → DAWproject exportieren…` ergänzen, ausschließlich auf Basis des neuen Snapshot-Exporters.
- [ ] AVAILABLE: Kleinen **Export-ProgressDialog** mit `QThreadPool` / `DawProjectExportRunnable` ergänzen, ohne Audio-/Transport-Core anzufassen.
- [ ] AVAILABLE: **Roundtrip-Smoke-Test** (Export → Re-Import in leeres Projekt) ergänzen, weiterhin nur im FileIO-/Test-Bereich.

## v0.0.20.357 — Echter Group-Bus mit eigener Device-Chain (Bitwig-Style)

- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Echte Gruppenspur mit kind="group"** erstellt — Group-Track hat eigene `audio_fx_chain` durch die das summierte Audio aller Kindspuren fließt.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Group-Bus-Routing im Audio-Callback**: Kind-Audio → Kind-FX → Kind-Vol/Pan → Group-Buffer → Group-FX → Group-Vol/Pan → Master.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Pull-Sources (Sampler/Drum/SF2)** werden ebenfalls durch den Group-Bus geroutet.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Group-Header-Klick im Arranger** wählt den Group-Track aus → DevicePanel zeigt die Gruppen-Device-Chain.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Effects auf die Gruppe** landen jetzt auf der Gruppen-FX-Chain (nicht mehr auf kick).
- [ ] AVAILABLE: **Group-Fader im Mixer-View** als eigener Bus-Kanal anzeigen.
- [ ] AVAILABLE: **Group Mute/Solo Verhalten** (Bitwig: Group-Mute stummschaltet alle Kinder).
- [ ] AVAILABLE: **Sub-Lanes innerhalb einer eingeklappten Gruppe** statt Überlappung.

## v0.0.20.356 — Kritischer Bugfix: Collapsed-Group Clip-Track-Zuordnung

- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Clip-Track-Korruption bei Drag in eingeklappter Gruppe** behoben. Clips wurden beim horizontalen Drag stillschweigend auf `members[0]` (z.B. kick) umgehängt — damit spielten alle gruppierten Instrumente gleichzeitig.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Single-Clip, Multi-Clip und Copy-Drag** jeweils mit `_is_same_collapsed_group()` Guard geschützt.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Track-Lookup Fallback** für collapsed Groups: Volume-Anzeige für Non-First-Members korrigiert.
- [x] FIXED (Claude Opus 4.6, 2026-03-08): **Spur-Name-Prefix in Clip-Labels** bei eingeklappter Gruppe (🔹kick: ..., 🔹open hi: ...) zur besseren Unterscheidbarkeit.
- [ ] AVAILABLE: **Sub-Lanes innerhalb einer eingeklappten Gruppe** statt Überlappung aller Clips auf einer Zeile.
- [ ] AVAILABLE: **Echte Group-Track / Group-Bus Device-Chain wie in Bitwig** bleibt ein separater Routing-/Mixer-Schritt.

## v0.0.20.355 — Browser Scope-Badges + Distortion Automation Guard

- [x] FIXED (GPT-5, 2026-03-08): Kleine **Scope-Badges direkt im Browser/Add-Flow** ergänzt (Instruments / Effects / Favorites / Recents), damit vor dem Hinzufügen sichtbar ist, dass Browser-Add weiter nur auf die **aktive Spur** zielt.
- [x] FIXED (GPT-5, 2026-03-08): Die Scope-Badges werden jetzt **trackbezogen aktualisiert**, sobald die aktive Spur wechselt.
- [x] FIXED (GPT-5, 2026-03-08): Safe Guard gegen den gemeldeten **DistortionFxWidget Automation-Callback auf gelöschte Slider/Spinboxen** ergänzt.
- [ ] AVAILABLE: Optional die Scope-Badges zusätzlich in **Plugins** und ggf. weiteren Browser-Tabs spiegeln, weiterhin UI-only.
- [ ] AVAILABLE: **Echte Group-Track / Group-Bus Device-Chain wie in Bitwig** bleibt ein separater Routing-/Mixer-Schritt und ist in diesem Safe-Block bewusst noch nicht umgesetzt.

## v0.0.20.354 — DevicePanel Gruppen-/Spur-Zieltrennung klarer

- [x] FIXED (GPT-5, 2026-03-08): DevicePanel zeigt jetzt eine zusätzliche **Aktive Spur-Ziel**-Hinweisbox; sichtbare Device-Kette unten wird klar als **aktive Spur** ausgewiesen, Gruppen-Aktionen separat als **NOTE→Gruppe / AUDIO→Gruppe** erklärt.
- [ ] AVAILABLE: Kleine **Scope-Badge direkt im Browser/Add-Flow** ergänzen, damit schon vor dem Hinzufügen klar ist, ob das Ziel die **aktive Spur** oder die **ganze Gruppe** ist.

## v0.0.20.353 — TrackList Drop-Markierung beim Maus-Reorder

- [x] FIXED (GPT-5, 2026-03-08): **Sichtbare Drop-Markierung in der linken Arranger-TrackList** ergänzt, damit beim Maus-Verschieben klar erkennbar ist, an welcher Position Spur oder Block eingefügt wird.
- [x] FIXED (GPT-5, 2026-03-08): Die Markierung reagiert sicher auf **same-widget Reorder-Drags** und bleibt damit vom bestehenden **Cross-Project-Track-Drag** getrennt.
- [ ] AVAILABLE: Optional die **Drop-Markierung zusätzlich als kleine Ziel-Highlight-Zone** pro Zeile erweitern, weiterhin ohne Routing-/DSP-Eingriff.
- [ ] AVAILABLE: Die **Gruppen-/Track-FX-Zieltrennung** im DevicePanel optional noch deutlicher visualisieren; echter Gruppenbus bleibt weiterhin ein separater Core-Schritt.

## v0.0.20.352 — Gruppenkopf-Mausdrag + Doppelklick-Umbenennen

- [x] FIXED (GPT-5, 2026-03-08): **Gruppenkopf in der Arranger-TrackList per Maus als kompletter Block verschiebbar** gemacht, ohne den bestehenden Cross-Project-Track-Drag anzutasten.
- [x] FIXED (GPT-5, 2026-03-08): **Doppelklick auf Track-/Gruppennamen** öffnet jetzt sicher den bestehenden Umbenennen-Dialog.
- [x] FIXED (GPT-5, 2026-03-08): DevicePanel-Gruppenhinweis klarer gemacht: **normales Add-to-Device wirkt nur auf die aktive Spur**, **N→G / A→G** auf die ganze Gruppe.

## v0.0.20.351 — Arranger Maus-Reorder in TrackList

- [x] FIXED (GPT-5, 2026-03-08): **Maus-Drag-Reorder im linken Arranger-Bereich** ergänzt, inklusive sicherem **Mehrfachauswahl-Blockmove** und ohne den bestehenden **Cross-Project-Track-Drag** zu brechen.
- [ ] AVAILABLE: Optional **Gruppenkopf ebenfalls per Maus als kompletter Block** verschiebbar machen, weiterhin ohne Routing-/DSP-Eingriff.
- [ ] AVAILABLE: Optional eine kleine **Drop-Ziel-Markierung** in der TrackList ergänzen, damit die Einfügeposition beim Maus-Drag noch klarer wird.

## v0.0.20.350 — Arranger Gruppen-Alignment + sichtbare Verschiebe-Pfeile

- [x] FIXED (GPT-5, 2026-03-08): **Ausgeklappte Gruppen im Arranger-Canvas an die linke TrackList angeglichen**: Gruppenkopf und alle Mitgliedsspuren werden jetzt korrekt untereinander gezeigt, statt dass Spuren optisch verschwinden oder zusammenrutschen.
- [x] FIXED (GPT-5, 2026-03-08): Das Gruppen-Alignment gilt jetzt sicher auch für **Audio- und Busspuren** innerhalb derselben Gruppendarstellung.
- [x] FIXED (GPT-5, 2026-03-08): **Sichtbare ▲/▼-Buttons direkt in Track-/Gruppenzeilen** ergänzt, damit das Verschieben nicht nur über Kontextmenü, sondern direkt im Arranger-Header funktioniert.
- [x] FIXED (GPT-5, 2026-03-08): **Gruppenkopf als kompletter Block nach oben/unten verschiebbar** gemacht, ohne Audio-/Routing-Core anzufassen.
- [ ] AVAILABLE: **Track-Reorder per Drag & Drop** separat evaluieren; nur sinnvoll, wenn Cross-Project-Drag dabei sicher erhalten bleibt.
- [ ] AVAILABLE: **Gruppenkopf-Lane im Canvas** optional noch mit kompakterem Titel/Badge visuell verfeinern.
- [ ] AVAILABLE: **Echte Audio-Gruppenbusse** weiterhin strikt getrennt als späteren Routing-/Mixer-Schritt behandeln.

## v0.0.20.349 — Gruppen-Fold-State + Arranger-Gruppen-Lane + Track-Reorder

- [x] FIXED (GPT-5, 2026-03-08): **Gruppen-Einklappstatus projektseitig gespeichert** (`arranger_collapsed_group_ids`), damit Fold-State beim Speichern/Laden erhalten bleibt.
- [x] FIXED (GPT-5, 2026-03-08): **Gruppen im Arranger-Canvas als eine Lane im eingeklappten Zustand** sichtbar gemacht; Clips aller Mitglieder laufen dann sicher auf einer gemeinsamen Gruppen-Lane zusammen.
- [x] FIXED (GPT-5, 2026-03-08): **Spuren im Arranger-Kontextmenü nach oben/unten verschiebbar** gemacht, damit neu angelegte Instrument-/Audio-/Busspuren sauber umsortiert werden können.
- [x] FIXED (GPT-5, 2026-03-08): **Neue Spur direkt in eine bestehende Gruppe einfügen** ergänzt (Gruppenkopf-Menü + Track-Menü „In diese Gruppe hinzufügen“), damit neue Instrumente/Busse nicht mehr nur unterhalb der Gruppe landen.
- [ ] AVAILABLE: **Collapsed Group Lane** optional um kleine kompakte Summen-/Member-Hinweise direkt im Canvas ergänzen, rein visuell.
- [ ] AVAILABLE: **Gruppen-Spur verschieben** optional als kompletter Block (alle Mitglieder zusammen) ergänzen; separat planen, weil das Verhalten klar definiert werden sollte.
- [ ] AVAILABLE: **Echte Audio-Gruppenbusse** weiterhin getrennt als späteren Routing-/Mixer-Schritt behandeln, nicht in diesem UI-safe Block.

## v0.0.20.348 — Master-FX / Global Undo / Arranger-Menü-Hotfixes

- [x] FIXED (GPT-5, 2026-03-08): **Master-Audio-FX hörbar gemacht**: Summen-/Master-FX werden jetzt im Master-Mixpfad wirklich verarbeitet.
- [x] FIXED (GPT-5, 2026-03-08): **Globales Projekt-Undo/Redo** per sicherem Snapshot-Fallback ergänzt, damit viele bislang undo-lose Projektänderungen rückgängig gemacht werden können.
- [x] FIXED (GPT-5, 2026-03-08): **Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y** zusätzlich als globale Application-Shortcuts verdrahtet.
- [x] FIXED (GPT-5, 2026-03-08): **Track-Kontextmenü repariert/erweitert**: **Umbenennen**, **Track löschen**, **Instrument-/Audio-/Bus-Spur hinzufügen**.
- [x] FIXED (GPT-5, 2026-03-08): **Gruppenkopf einklappbar** im Arranger umgesetzt.
- [ ] AVAILABLE: **Gruppen-Einklappstatus projektseitig speichern**, damit Fold-State beim erneuten Laden erhalten bleibt.
- [ ] AVAILABLE: **Undo-Labels** für größere UI-Aktionen gezielter benennen statt generischem Snapshot-Label.
- [ ] AVAILABLE: **Master-DeviceCard** optisch noch klarer als Summenkanal ausweisen (rein UI-seitig).

## v0.0.20.347 — Arranger Track-/Gruppen-Flow + Gruppen-Sektion im DevicePanel

- [x] FIXED (GPT-5, 2026-03-08): **Clip → Track-Auswahl synchronisiert**: wenn im Arranger ein MIDI-/Audio-Clip aktiv ausgewählt wird, wird jetzt auch seine zugehörige Spur im Track-Header mit ausgewählt.
- [x] FIXED (GPT-5, 2026-03-08): **Rechtsklick-Menü direkt auf Track-/Instrument-Zeilen** im Arranger ergänzt, inkl. **Umbenennen**, **Auswahl gruppieren**, **Gruppe umbenennen**, **Gruppe auflösen**, Devices/Browser sowie bestehende Track-Aktionen.
- [x] FIXED (GPT-5, 2026-03-08): **Spurgruppierung visuell als echte Sektion** im Arranger-Trackbereich dargestellt: Gruppenkopf + eingerückte Mitglieder untereinander, ohne Eingriff in Playback-/Mixer-Core.
- [x] FIXED (GPT-5, 2026-03-08): **Gruppen-Sektion im DevicePanel** ergänzt: sichtbare Mitgliederliste plus sichere Batch-Aktionen **N→G** / **A→G**, um NOTE-FX bzw. AUDIO-FX auf alle Tracks der aktuellen Gruppe anzuwenden.
- [ ] AVAILABLE: **Gruppen-Kopf einklappbar** machen (nur UI), damit große Orchester-/Chorgruppen im Arranger kompakter werden.
- [ ] AVAILABLE: **Gruppen-DevicePanel** optional um eine kleine **Bypass-/Mute-Übersicht pro Mitglied** erweitern, weiterhin ohne Engine-/Routing-Umbau.
- [ ] AVAILABLE: **Echte Gruppen-Bus-/Summen-Spur** als späteren Architektur-Schritt separat planen, erst nach expliziter Freigabe, weil das ein Core-/Routing-Thema wäre.

## v0.0.20.338 — AETERNA Live ARP / Readability / Safe Note-FX Bridge

- [x] FIXED (GPT-5, 2026-03-07): **AETERNA Arp A** kann jetzt sicher **Live an/aus** geschaltet werden, indem lokal ein vorhandenes **Track Note-FX Arp** für diese AETERNA-Spur gepflegt wird — ohne Playback-Core-Umbau.
- [x] FIXED (GPT-5, 2026-03-07): Die bereits vorhandenen **16 Step-Daten** von AETERNA Arp A werden jetzt auch für den sicheren **Track Note-FX Arp** genutzt (**Transpose / Skip / Velocity / Gate / Shuffle / Note Type**), damit Live-ARP und ARP→MIDI näher zusammenliegen.
- [x] FIXED (GPT-5, 2026-03-07): **AETERNA-Readability** lokal weiter angehoben: etwas größere Card-/Hint-Schriften sowie klarerer **ARP Live / ARP→MIDI**-Header.
- [ ] AVAILABLE: Lokale **AETERNA-Familienkarten** noch weiter verdichten (z. B. kompakte Mini-Meter oder aktive Mod-Ziel-Badges direkt im Card-Kopf), nur Widget/State.
- [ ] AVAILABLE: Lokale **Signalfluss-Ansicht** noch feiner staffeln (z. B. aktive Slot-Ziele farbig im passenden Ziel-Bucket hervorheben), nur im AETERNA-Widget.

## v0.0.20.335 — Nächster sichere AETERNA-Polish-Block

- [x] FIXED (GPT-5, 2026-03-07): Größeren lokalen **AETERNA-Polish-Block** umgesetzt: stärkere **Farbtrennung**, neue **Familien-Legende**, deutlichere **Familienkarten** und eine kleine **grafische Signalfluss-Ansicht** direkt im Instrument, weiterhin ohne Core-Umbau.
- [x] FIXED (GPT-5, 2026-03-07): Bisher intern schon vorgesehene **Pitch / Shape / Pulse Width**- sowie **Drive / Feedback**-Familien jetzt auch als echte sichtbare **Synth-Panel-Karten mit Knobs** im Widget ergänzt, weiterhin nur lokal in AETERNA.
- [ ] AVAILABLE: Lokale **AETERNA-Familienkarten** noch weiter verdichten (z. B. kompakte Mini-Meter oder aktive Mod-Ziel-Badges direkt im Card-Kopf), nur Widget/State.
- [ ] AVAILABLE: Lokale **Signalfluss-Ansicht** noch feiner staffeln (z. B. aktive Slot-Ziele farbig im passenden Ziel-Bucket hervorheben), nur im AETERNA-Widget.

## v0.0.20.329 — Nächste sichere AETERNA-Mod-Rack-/Synth-Schritte

- [ ] AVAILABLE: Lokale **AETERNA-Targets** optional noch kompakter nach **Klang / Raum / Bewegung** gliedern, weiterhin nur im Widget.
- [x] FIXED (GPT-5, 2026-03-07): Lokales **AETERNA-SYNTH PANEL Stage 1** mit bereits stabilen Parametern aufgebaut und lesbar gruppiert.
- [x] FIXED (GPT-5, 2026-03-07): Lokales **AETERNA-SYNTH PANEL Stage 2** mit echtem **Filter Cutoff / Resonance / Filter Type** ergänzt.
- [x] FIXED (GPT-5, 2026-03-07): Lokales **AETERNA-SYNTH PANEL Stage 3** in sicheren Familien gestartet: zuerst **Voice** (**Pan / Glide / Retrig / Stereo-Spread**) und **AEG/FEG ADSR**.
- [ ] AVAILABLE: Nächste Stage-3-Familien weiterführen: **Unison/Voices/Detune**, **Sub/Sub-Oktave**, **Shape/Pulse Width**, **Noise**, **Drive/Feedback** — nur schrittweise und nie alles auf einmal.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-SYNTH PANEL Stage 3** um die Familie **Unison / Sub / Noise** erweitert: echte Klangparameter, lokale Comboboxen für **Voices**/**Sub-Oktave** sowie stabile Automation-/Mod-Ziele für **Unison Mix / Unison Detune / Sub Level / Noise Level / Noise Color**.
- [ ] AVAILABLE: Nächste Stage-3-Familien weiterführen: **Pitch/Shape/Pulse Width** sowie **Drive/Feedback** — weiterhin nur schrittweise und nur lokal in AETERNA.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA-Mod-Rack zeigt jetzt lokale **Amount-/Polaritätsanzeigen** direkt an den realen Web-A/B-Slots.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA hat jetzt eine kleine lokale **Signalfluss-Linienansicht** für die aktiven Web-A/B-Wege.

## v0.0.20.326 — Nächste sichere Bounce/Freeze- und AETERNA-Schritte

- [ ] AVAILABLE: **Bounce in Place** optional um einen kleinen lokalen Dialog ergänzen (z. B. Quelle stummschalten / Dry / +FX), weiterhin ohne Playback-Core-Umbau.
- [ ] AVAILABLE: **Freeze Track / Group Freeze** optional um einen sichtbaren kleinen Statusmarker im Track-Namen oder Kontextmenü ergänzen, weiterhin projekt-/UI-seitig.
- [ ] AVAILABLE: Lokale **AETERNA Random-Math-/Formel-Familien** weiter ausbauen (z. B. mehr kohärente/noise-/chaos-inspirierte Startideen), weiterhin nur im Widget.
- [x] FIXED (GPT-5, 2026-03-07): Erste sichere **Bounce/Freeze-Workflows** ergänzt: **Bounce in Place → neue Audiospur**, **Spur einfrieren (+FX/Dry)**, **Gruppe einfrieren** bei vorhandener Track-Gruppe sowie **Freeze-Quellen wieder aktivieren** — ohne Playback-Core-Umbau.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA-Formelhilfen und Randomizer lokal um **breitere mathematische Familien** erweitert, damit nicht immer nur reine **phase**-Varianten im Vordergrund stehen.

## v0.0.20.324 — Nächste sichere AETERNA-Performance-Schritte

- [ ] AVAILABLE: Lokale **AETERNA-Ladeprofil-Hinweise** im Widget noch etwas sichtbarer machen (z. B. leichte Ready-/Staged-Init-Hinweise), weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Composer-Phrasenlängen/-Dichten** feiner staffeln, weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Snapshot-/Preset-Schnellaufrufe** optional noch um einen kleinen aktiven Fokusmarker ergänzen, weiterhin nur in AETERNA.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA lädt lokal spürbar sanfter: **Restore-Signale werden gebündelt**, **Komfort-Refreshes gestaffelt nachgezogen** und **Button-Rebinds ohne blindes disconnect()** aktualisiert — weiterhin nur im Widget.

## v0.0.20.321 — Nächste sichere AETERNA-Schritte

- [ ] AVAILABLE: Lokale **Automation-Hinweise** an den bereits sicheren AETERNA-Knobs noch klarer verdichten, weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Snapshot-Karte** optional noch um eine sehr kleine „zuletzt gespeichert/recallt“-Hinweiszeile ergänzen, weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Preset-/Snapshot-Schnellaufrufe** optional noch um kleine Statusfarben oder „aktiv“-Marker verfeinern, weiterhin nur im Widget.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Preset-/Snapshot-Kombis** sind jetzt als kleine **Schnellaufrufe** direkt im AETERNA-Widget sichtbar, inklusive kompakter Buttons und Tooltips für Recall/Load — ohne Core-Eingriff.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **Formel-/Web-Kombitipps** werden jetzt direkt an passenden AETERNA-Presets sichtbarer gezeigt, inklusive Preset-Fokus, Kurzlistenzeile und erweiterten Schnellpreset-Tooltips.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA-Preset-Kurzliste zeigt jetzt lokale **Direktmarker für Kategorie/Charakter** im Schnellbereich.

---

- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt einen lokalen **Automation-Schnellzugriff** für alle stabilen Knobs/Rates/Amounts, inklusive klarerer **musikalischer Tooltip-Hinweise** direkt an den Reglern.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Snapshot-Slots** um kleine **Farbbadges/Statusmarker** erweitert, inklusive klarerem Slot-Tooltip und deaktiviertem Recall für leere Slots.
## v0.0.20.318 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Automation-Ziele** optional noch nach "Sweep / Bewegung / Raum" kompakter gruppieren, weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Preset-Kurzliste** optional um kleine Direktmarker für Kategorie/Charakter ergänzen, weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Snapshot-Karte** optional noch um eine sehr kleine „zuletzt gespeichert/recallt“-Hinweiszeile ergänzen, weiterhin nur im Widget.


- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Presetbibliothek** kompakter nach **Kategorie/Charakter** zusammengefasst, inklusive aktivem Preset-Fokus und kompakter Bibliotheksübersicht direkt im Widget.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Formel-/Preset-Empfehlungen** um kompakte **Hörhinweise** ergänzt.
## v0.0.20.315 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **AETERNA-Presetbibliothek** kompakter nach Charakter/Kategorie zusammenfassen, nur im Widget.
- [ ] AVAILABLE: Lokale **Snapshot-Slots** optional um kleine Farbbadges/kurze Statusmarker ergänzen, weiterhin nur im Widget.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **Automation-ready-Knob-Hinweise** in AETERNA kompakter gemacht, inklusive **Schnellzugriff** auf alle stabilen Automation-Lanes und klarerer Tooltip-Hinweise direkt an den Reglern.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Snapshot-Karte** kompakter und musikalischer lesbar gemacht.
## v0.0.20.314 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Formel-/Preset-Empfehlungen** um kleine Hörhinweise ergänzen (z. B. sakral, klar, getragen), weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **AETERNA-Presetbibliothek** kompakter nach Charakter/Kategorie zusammenfassen, nur im Widget.
- [ ] AVAILABLE: Lokale **Snapshot-Slots** optional um kleine Farbbadges/kurze Statusmarker ergänzen, weiterhin nur im Widget.

- [x] 2026-03-07 AETERNA: Web-Vorlagen Basis-Reset lokal ergänzt, inkl. Save/Load von aktivem Web-Template.
## v0.0.20.311 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Formel-/Preset-Empfehlungen** um kleine Hörhinweise ergänzen (z. B. sakral, klar, getragen), weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **AETERNA-Presetbibliothek** kompakter nach Charakter/Kategorie zusammenfassen, nur im Widget.
- [ ] AVAILABLE: Lokale **Web-Vorlagen** optional um eine kleine klare **„Reset auf Basiswerte“**-Funktion ergänzen, weiterhin nur lokal in AETERNA.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Web-Intensitätsstufen** für AETERNA-Startvorlagen ergänzt (**Sanft / Mittel / Präsent**), inklusive sauberem Save/Load im Instrument-State.

## v0.0.20.309 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **AETERNA-Presetbibliothek** kompakter nach Charakter/Kategorie zusammenfassen, nur im Widget.
- [ ] AVAILABLE: Lokale **Formel-/Preset-Empfehlungen** optional um kleine Hörhinweise ergänzen (z. B. sakral, klar, getragen), weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Web-A/Web-B-Startvorlagen** ergänzen (z. B. langsam/lebendig/organisch), weiterhin nur in AETERNA.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Macro-A/B-Feinsteuerung** in AETERNA lesbarer gemacht, mit klarer Source→Target→Amount-Karte und kompakten Nutzungshinweisen.

## v0.0.20.308 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Macro-A/B-Feinsteuerung** lesbarer machen, weiterhin ohne DAW-Core-Eingriff.
- [ ] AVAILABLE: Lokale **AETERNA-Presetbibliothek** kompakter nach Charakter/Kategorie zusammenfassen, nur im Widget.
- [ ] AVAILABLE: Lokale **Formel-/Preset-Empfehlungen** optional um kleine Hörhinweise ergänzen (z. B. sakral, klar, getragen), weiterhin nur im Widget.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA zeigt jetzt lokal sichtbar, **welche Formelidee zum aktuellen Preset passt**, inklusive Lade-Button und Statuszeile.

## v0.0.20.307 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Formula-/Preset-Verknüpfung** sichtbarer machen (z. B. welches Preset nutzt aktuell welche Formelidee), nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Macro-A/B-Feinsteuerung** lesbarer machen, weiterhin ohne DAW-Core-Eingriff.
- [ ] AVAILABLE: Lokale **Preset-Kurzliste** um kleine Herkunftshinweise ergänzen (z. B. sakral/kristall/drone), weiterhin nur im Widget.

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Preset-Kurzliste** in AETERNA um einen sicheren **Filter** erweitert (Alle / Sakral / Kristall / Drone / Favoriten).

---

## v0.0.20.306 — Nächste sichere AETERNA-Phase-3b-Schritte

- lokale Preset-Kurzliste optional um intelligente Filter (z. B. sakral / kristall / drone) erweitern
- kuratierte Formel-Preset-Karte weiter ausbauen
- weitere vorsichtige Klangverfeinerung nur lokal in AETERNA
- weiterhin keine Core-Eingriffe

## v0.0.20.304 — Nächste sichere AETERNA-Schritte nach Kristall-/Formel-Upgrade
- [ ] AVAILABLE: Lokale **Formel-Preset-Karte** noch kompakter mit kleinen Stil-Hinweisen (z. B. ruhig / sakral / organisch / drone) ergänzen, weiterhin nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **AETERNA-Knob-Hinweise** für langsame Sweeps vs. lebendige Modulation noch klarer ausweisen, ohne Core-Eingriff.
- [ ] AVAILABLE: Optional ein lokales **"Klar/Weich"-Voicing-Preset** für AETERNA ergänzen, weiterhin nur innerhalb des Instruments.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt zusätzliche kuratierte **Formel-Startbeispiele** (**Organisch**, **Drone**), ein lokales **klareres/kristallineres Voicing** und den lokalen Bugfix **`get_formula_status()`** für die Formelstatus-Anzeige.

## v0.0.20.303 — Nächste sichere AETERNA-Schritte nach Formel-Infozeile
- [ ] AVAILABLE: Kuratierte lokale **Formel-Preset-Karte** um weitere musikalische Startbeispiele (z. B. Organisch / Drone) ergänzen, weiterhin nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Automation-ready**-Hinweise direkt an ausgewählten AETERNA-Knobs kompakter machen, ohne Core-Eingriff.
- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt eine lokale **Formel-Infozeile**, die klar zwischen **Beispiel geladen**, **manuell geändert**, **angewendet** und **noch nicht angewendet** unterscheidet.

## v0.0.20.302 — Nächste sichere AETERNA-Schritte nach freigegebenen Automationszielen

- [ ] AVAILABLE: Kleine lokale **Formel-Infozeile** ergänzen, die zeigt, ob ein Startbeispiel nur im Feld steht oder bereits angewendet wurde.
- [ ] AVAILABLE: Lokale **AETERNA-Makros/Knobs** optional um eine noch kompaktere **"Automation-ready"-Kurzansicht** direkt an den Reglern ergänzen, weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Kuratierte lokale **Formel-Preset-Karte** erweitern (z. B. Organisch / Drone), weiterhin nur im AETERNA-Widget.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA zeigt jetzt klar die **bereits lokal freigegebenen stabilen Automationsziele** (Knobs, Rates, Amounts) und erklärt die sichere Nutzung per **Rechtsklick → Show Automation in Arranger**.

---

## v0.0.20.301 — Nächste sichere AETERNA-Schritte nach lokaler Automation-Zielkarte

- [ ] AVAILABLE: Kleine lokale **Formel-Infozeile** ergänzen, die erklärt, ob ein Startbeispiel erst im Feld steht oder schon angewendet wurde.
- [ ] AVAILABLE: Lokale **Formel-Preset-Hinweise** noch deutlicher mit Preset-Metadaten verknüpfen, weiterhin nur im Widget.
- [ ] AVAILABLE: Lokale **Automation-Ziele** optional um kurze Hinweise ergänzen, welche Ziele eher für langsame Sweeps und welche für lebendige Modulation sinnvoll sind.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt eine kompakte lokale **Automation-Zielkarte** mit klar benannten Gruppen und Sicherheits-Hinweis.

---

---

## v0.0.20.300 — Nächste sichere AETERNA-Schritte nach Phase 3a safe

- [ ] AVAILABLE: Lokale **Automation-Ziele** in AETERNA als kompakte, klar benannte Kurzliste/Karte sichtbar machen.
- [ ] AVAILABLE: Kleine lokale **Formel-Infozeile** ergänzen, die erklärt, ob ein Startbeispiel erst im Feld steht oder schon angewendet wurde.
- [ ] AVAILABLE: Lokale **Formel-Preset-Hinweise** noch deutlicher mit Preset-Metadaten verknüpfen, weiterhin nur im Widget.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt eine kompakte lokale **Badge-/Kurzansicht** für Preset-Metadaten direkt im Widget.

---

## v0.0.20.299 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Kleine lokale **Formel-Infozeile** ergänzen, die erklärt, ob ein Startbeispiel erst im Feld steht oder schon angewendet wurde.
- [ ] AVAILABLE: Lokale **Preset-Metadaten** in AETERNA noch klarer zusammenfassen (z. B. Badge-/Kurzansicht), weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Formel-Preset-Hinweise** noch deutlicher mit Preset-Metadaten verknüpfen, weiterhin nur im Widget.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt lokale **Preset-Metadaten mit Tags/Favorit**, weiterhin nur im Widget/State von AETERNA.


---

## v0.0.20.298 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Lokale **Formel-Makro-Slots** noch lesbarer gruppieren (z. B. Sound / Zeit / Chaos), weiterhin nur in AETERNA.
- [ ] AVAILABLE: Lokale **Preset-Metadaten** optional um Tags/Favorit erweitern, weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Kleine lokale **Formel-Infozeile** ergänzen, die erklärt, ob ein Startbeispiel erst im Feld steht oder schon angewendet wurde.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA erhielt eine lokale **Formel-Startkarte / Onboarding-Hilfe** mit sicheren Beispiel-Buttons direkt im Widget.

---

## v0.0.20.297 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Lokale **Formel-Startkarte / Onboarding-Hilfe** ergänzen, nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Formel-Makro-Slots** noch lesbarer gruppieren (z. B. Sound / Zeit / Chaos), weiterhin nur in AETERNA.
- [ ] AVAILABLE: Lokale **Preset-Metadaten** optional um Tags/Favorit erweitern, weiterhin ohne Core-Eingriff.

- [x] FIXED (GPT-5, 2026-03-07): AETERNA Formel-Eingabe wieder nutzbar gemacht (**mehrzeiliges Edit-Feld**) und **lokale Preset-Metadaten** ergänzt.

---

## v0.0.20.295 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Lokale **Formel-Makro-Slots** noch lesbarer gruppieren (z. B. Sound / Zeit / Chaos), weiterhin nur in AETERNA.
- [ ] AVAILABLE: Lokale **Formel-Hilfe** um ein kleines Beispiel-Panel ergänzen, weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Preset-Metadaten** ergänzen (z. B. Snapshot-Info oder kleiner Kommentar), weiterhin ohne Core-Eingriff.

- [x] FIXED (GPT-5, 2026-03-06): AETERNA Phase 3a safe erweitert: **Formel-Aliase** plus **sichtbare Formel-Mod-Slots** im Widget.

---

## v0.0.20.294 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Lokale **Formel-Mod-Slots** lesbar ergänzen (z. B. kleine Liste der aktuell genutzten Formelquellen), weiterhin nur in AETERNA.
- [ ] AVAILABLE: Lokale **Formel-Hilfe** noch klarer machen (z. B. Wrapping-Buttons oder Makro-Snippets), weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Preset-Metadaten** ergänzen (z. B. Snapshot-Info oder kleiner Kommentar), weiterhin ohne Core-Eingriff.

- [x] FIXED (GPT-5, 2026-03-06): AETERNA Phase 3a safe erweitert: **LFO/MSEG/Chaos-Formelhilfen** per **Klick** und **Drag&Drop** direkt in die Formel.


## v0.0.20.293 — Nächste sichere AETERNA-Phase-3a-Schritte

- [ ] AVAILABLE: Lokale **Phase-3a-Ansicht** weiter vereinfachen (z. B. noch klarere Basic/Advanced-Trennung nur in AETERNA).
- [ ] AVAILABLE: Lokale **Preset-Metadaten** ergänzen (z. B. Snapshot-Info oder kleiner Kommentar), weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Automation-Listen** optional noch kompakter machen (z. B. nur lesbare Namen statt Keys), weiterhin nur im AETERNA-Widget.

- [x] FIXED (GPT-5, 2026-03-06): AETERNA Phase 3a safe erweitert: **Preset A/B** plus **klarere Automation-Zielsektionen** im Phase-3a-Bereich.


---

## v0.0.20.305 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Preset-Kurzliste/Favoritenansicht** in AETERNA ergänzen, damit sakrale/kristalline Presets schneller auffindbar sind.
- [ ] AVAILABLE: Lokale **Formula-/Preset-Verknüpfung** sichtbarer machen (z. B. welches Preset nutzt aktuell welche Formelidee), nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Macro-A/B-Feinsteuerung** lesbarer machen, weiterhin ohne DAW-Core-Eingriff.

---

## v0.0.20.310 — Nächste sichere AETERNA-Phase-3b-Schritte

- [ ] AVAILABLE: Lokale **Web-A/Web-B-Feinmischung** um kleine Intensitätsstufen ergänzen (z. B. sanft / mittel / präsent), nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Formel-/Web-Verknüpfung** sichtbarer machen (z. B. welche Web-Vorlage passt zu welcher Formelidee), ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Preset-/Web-Kombis** als kleine Kurztipps ergänzen, weiterhin nur in AETERNA.


## v0.0.20.313 — Nächste sichere AETERNA-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Snapshot-Hinweise** in AETERNA weiter verdichtet: Badges, Tooltips, Recall-Status und neue **„Zuletzt: Store/Recall …“**-Hinweiszeile direkt an der Snapshot-Karte.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **Formel-/Web-Kombitipps** pro Preset ergänzt, damit der passende Startweg direkt sichtbar wird.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **Preset-/Snapshot-Kombis** als kleine Schnellaufrufe direkt im Widget sichtbar gemacht.
---

## v0.0.20.322 — Nächste sichere lokale AETERNA-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokale **Snapshot-Slot-Kurznamen** ergänzt (automatisch aus Preset/Hörbild abgeleitet), weiterhin nur im AETERNA-Widget.
- [ ] AVAILABLE: Lokale **Snapshot-Vergleichshinweise** kompakter machen (z. B. was sich zwischen aktivem Zustand und Recall-Slot grob ändert), ohne Engine-/Core-Eingriff.
- [ ] AVAILABLE: Lokale **Preset-/Snapshot-Schnellaufrufe** optisch feiner staffeln (z. B. aktiver Slot klarer markiert), nur im Widget.

## v0.0.20.323 — Nächste sichere lokale AETERNA-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokalen **AETERNA Composer** mit Dreiecks-Menü ergänzt: mathematischer Weltstil-Mix für **Bass / Melodie / Lead / Pad / Arp** direkt als MIDI-Clip auf der aktuellen AETERNA-Spur, ohne Drum-Logik und ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **AETERNA-Composer-Vergleichshinweise** ergänzen (z. B. aktuelle Stil-Mischung vs. letzter Seed), weiterhin nur im Widget/State.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Composer-Phrasenlängen/-Dichten** feiner gestaffelt: neue lokale Phrasenprofile und Dichteprofile im Widget, weiterhin ohne Core-Eingriff.
- [ ] AVAILABLE: Lokale **Snapshot-Vergleichshinweise** mit Composer-Kontext verbinden (z. B. ob Recall eher Bass/Pad/Lead-lastig ist), weiterhin ohne Engine-/Core-Eingriff.



## v0.0.20.325 — Nächste sichere lokale AETERNA-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokale **AETERNA-Ladezeit sichtbar gemacht** (Build / Restore / staged Refresh) direkt im Widget, ohne globales Profiling.
- [ ] AVAILABLE: Lokale **AETERNA-Composer-Vergleichshinweise** ergänzen (z. B. aktueller Mix vs. letzter Seed), weiterhin nur im Widget/State.
- [ ] AVAILABLE: Lokale **Snapshot-Vergleichshinweise** mit Composer-Kontext verbinden (z. B. Recall eher Bass/Pad/Lead-lastig), weiterhin ohne Engine-/Core-Eingriff.
- [ ] AVAILABLE: Lokale **AETERNA-Ladeprofil-Historie** kompakt ergänzen (z. B. letzter Restore vs. aktueller Restore), weiterhin nur im Widget.


## v0.0.20.327 — Nächste sichere Bounce/Freeze- und AETERNA-Schritte

- [ ] AVAILABLE: Kleinen **Freeze-Status im Arranger-Header** sichtbar machen, weiterhin ohne Playback-Core-Umbau.
- [ ] AVAILABLE: **Bounce/Freeze-Dialog** optional um „Proxy sofort solo/selektieren“ ergänzen, nur UI-seitig.
- [ ] AVAILABLE: AETERNA lokal um noch klarere **Math-/Random-Familien-Kategorien** im Formelbereich ergänzen, weiterhin ohne Engine-Eingriff.

## v0.0.20.330 — Nächste sichere AETERNA-Synth-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokales **AETERNA Synth Panel Stage 1** ergänzt: vorhandene stabile Parameter lesbar gruppiert, Bereichs-Navigation hinzugefügt und sichere UI-Preview für spätere Familien reserviert.
- [x] FIXED (GPT-5, 2026-03-07): Ersten echten **Filter-Block** nur in AETERNA ergänzt (**Cutoff / Resonance / Type**) – mit lokalem UI, Save/Load, stabiler Automation sowie lokalen Mod-Rack-Zielen, weiterhin ohne DAW-Core-Umbau.
- [x] FIXED (GPT-5, 2026-03-07): Größeren **Voice-Block** in AETERNA als zusammenhängende Familie ergänzt (**Pan / Glide / Retrig / Stereo-Spread**), inklusive lokaler UI, Save/Load, stabiler Automation für die kontinuierlichen Parameter und echter Audio-Wirkung innerhalb von AETERNA.
- [x] FIXED (GPT-5, 2026-03-07): Nächste **Envelope-Familie** in AETERNA gebündelt (**AEG ADSR / FEG ADSR** als lokale UI + State + sichere Audio-Wirkung), inklusive Filter-Envelope-Amount.
- [ ] AVAILABLE: Nächsten **Unison/Sub/Noise-Block** als eigene sichere Ausbau-Familie ergänzen, lokal in AETERNA und mit klarer Einklapp-/Signalflussdarstellung.
- [ ] AVAILABLE: Danach einen **Pitch/Shape/Pulse-Width-Block** als eigene sichere Familie ergänzen, lokal in AETERNA und ohne Core-Umbau.
- [ ] AVAILABLE: Anschließend **Drive/Feedback** als separate sichere Klangfamilie ergänzen, lokal in AETERNA und mit klarer Warn-/Stabilitätstrennung.



## v0.0.20.334 — Nächste sichere AETERNA-Synth-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Gebündelten lokalen **Pitch / Shape / Pulse Width**-Block in AETERNA ergänzt — mit echter Klangwirkung, Save/Load, Randomize, stabilen Automation-Zielen und lokalen Mod-Rack-Zielen, ohne Core-Umbau.
- [x] FIXED (GPT-5, 2026-03-07): Gebündelten lokalen **Drive / Feedback**-Block in AETERNA ergänzt — mit echter Audio-Wirkung, Save/Load, Randomize, stabilen Automation-Zielen und lokalen Mod-Rack-Zielen, weiterhin nur in AETERNA.
- [ ] AVAILABLE: Lokale **AETERNA-Unison/Sub/Noise-UX** weiter verdichten (z. B. kleine Voices-/Oktav-Hinweise direkt an den Familienkarten), nur Widget/State.
- [ ] AVAILABLE: Lokale **AETERNA-Mod-Rack-Visualisierung** für die neuen Pitch/Timbre-/Drive-Ziele weiter ausbauen (z. B. stärkere Zielhervorhebung), ohne Core-Eingriff.
- [ ] AVAILABLE: Nächsten sicheren **Feinpolish-Block** für AETERNA angehen (z. B. kompaktere Familienkarten, stärkere Farbtrennung, klarere Signalfluss-Linien), weiterhin lokal im Instrument.


## v0.0.20.336 — Nächste sichere AETERNA-UX-Schritte

- [x] FIXED (GPT-5, 2026-03-07): **Layer-Schnellschalter** im AETERNA Synth Panel repariert: die bisher irreführenden Vorschau-Checkboxen für **Unison / Sub / Noise** schalten jetzt die realen Layer-Level direkt lokal an/aus.
- [x] FIXED (GPT-5, 2026-03-07): **Familienkarten** um lokale **aktive Mod-Ziel-Badges** und kompakte **Mini-Meter** ergänzt, weiterhin nur im AETERNA-Widget.
- [x] FIXED (GPT-5, 2026-03-07): Kleine **Mini-Meter direkt an einzelnen AETERNA-Synth-Knobs** ergänzt, weiterhin nur Widget/State.
- [ ] AVAILABLE: **Layer-Voices/Sub-Oktave** noch direkter in den Familienkarten hervorheben, ohne Engine-Eingriff.


## v0.0.20.337 — Nächste sichere AETERNA-ARP-/Mod-Schritte

- [x] FIXED (GPT-5, 2026-03-07): Lokalen **AETERNA Arp A (LOCAL SAFE)** ergänzt — als **Clip-Arpeggiator** nur für die aktuelle AETERNA-Spur, mit Pattern, Rate, Straight/Dotted/Triplets, 16 Steps sowie pro-Step **Transpose / Skip / Velocity / Gate**.
- [x] FIXED (GPT-5, 2026-03-07): **Per-Knob-Kontextmenü** in AETERNA erweitert: Rechtsklick bietet jetzt **Show Automation in Arranger** und **Add Modulator** (LFO1/LFO2/MSEG/Chaos/ENV/VEL) direkt für den angeklickten Ziel-Knob.
- [x] FIXED (GPT-5, 2026-03-07): Lokale **Knob-Mod-Profilzustände** pro AETERNA-Ziel ergänzt, damit jeder Knob seinen eigenen gespeicherten Mod-Zuweisungszustand behalten kann.
- [x] FIXED (GPT-5, 2026-03-07): **Readability-Polish** lokal in AETERNA verstärkt (größere Karten-/Hint-Schriften, lesbarere Signalfluss-Karte, höhere Controls).
- [ ] AVAILABLE: **Arp B** als zweite lokale AETERNA-Instanz ergänzen (erst nach Praxistest von Arp A).
- [ ] AVAILABLE: **Per-Knob-Mod-Profile** später um frei speicherbare Amount-/Polaritäts-Presets erweitern, weiterhin lokal im Widget/State.
- [x] FIXED (GPT-5, 2026-03-07): Kleine **Knob-Mini-Meter** direkt an wichtigen AETERNA-Synth-Zielen sichtbar gemacht; aktive Mod-Badges werden jetzt pro Knob kompakt angedeutet.


## v0.0.20.340 — Nächste sichere AETERNA-/Qt-Schritte

- [x] FIXED (GPT-5, 2026-03-07): **Layer-Voices/Sub-Oktave** in den AETERNA-Familienkarten deutlicher sichtbar gemacht, weiterhin nur Widget/State.
- [x] FIXED (GPT-5, 2026-03-07): Den **Qt-/Selection-Rekursionspfad** aus dem GDB-Log gezielt lokal entschärft: Refresh-/Signalguards für TrackList, Arranger-TrackList, Automation-Lanes sowie koaleszierter AETERNA-Refresh bei Live-ARP.
- [ ] AVAILABLE: Den **AETERNA-ARP-Live-Pfad** nach Praxistest weiter verhärten (z. B. noch gezieltere Diff-Erkennung der Note-FX-Params), weiterhin ohne Playback-Core-Umbau.
- [ ] AVAILABLE: Die **Layer-/Noise-Familienkarten** zusätzlich um kleine **Mode-/Voices-Badges** verdichten, weiterhin rein lokal im Widget.


## v0.0.20.496 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Der Dry-Run dispatcht jetzt **echte read-only Snapshot-Capture-/Restore-Methodenaufrufe** im Safe-Runner; pro Snapshot-Typ laufen konkrete Preview-Dispatcher und erscheinen als detailreiche `phase_results`, weiterhin ohne Commit und ohne Projektmutation.
- [ ] AVAILABLE: Den Safe-Runner als naechsten Schritt an **echte Snapshot-Klassenmethoden / Runtime-Capture-Stubs** koppeln, weiterhin noch ohne echten Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.


## v0.0.20.503 — Naechster sicherer SmartDrop-Schritt

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-16): Runtime-State-Stores jetzt an konkrete read-only **Runtime-State-Registries / Handle-Speicher** gekoppelt; Dry-Run und Guard-Dialog fuehren die neue Registry-Ebene sichtbar mit, weiterhin ohne Commit.
- [ ] AVAILABLE: Die neuen Runtime-State-Registries als naechsten Schritt an **echte Snapshot-State-Store-Backends / Handle-Register mit separaten Registry-Slots** koppeln, weiterhin noch ohne Commit.
- [ ] AVAILABLE: Erst danach den **ersten echten Minimalfall** `Instrument -> leere Audio-Spur` mit atomarem Undo-/Routing-Pfad freischalten.
