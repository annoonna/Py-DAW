## v0.0.20.726 — 🎵 MIDI Clip Scheduler + Instrument Auto-Load (Rust)

- [x] (Claude Opus 4.6, 2026-03-22): **midi_scheduler.rs NEU** — Beat-accurate MIDI dispatching (ScheduledEvent, load_from_sync, schedule_for_buffer, 7 Tests)
- [x] (Claude Opus 4.6, 2026-03-22): **engine.rs** — MIDI-Noten aus Arrangement werden beim Playback an Instrumente dispatcht
- [x] (Claude Opus 4.6, 2026-03-22): **engine.rs** — Auto-Load Instrumente bei ProjectSync (chrono.aeterna etc.)
- [x] (Claude Opus 4.6, 2026-03-22): **instruments/mod.rs** — chrono.* Plugin-IDs → InstrumentType Mapping
- [x] (Claude Opus 4.6, 2026-03-22): **audio_graph.rs** — track_indices() Hilfsmethode

## v0.0.20.725 — 💀 Persistent Plugin Blacklist + Stability Hardening

- [x] (Claude Opus 4.6, 2026-03-22): **Persistent Blacklist** — plugin_probe.py komplett überarbeitet: BlacklistEntry, JSON-Disk-Persistenz, Batch-Probe, User-Override
- [x] (Claude Opus 4.6, 2026-03-22): **Scanner Integration** — scan_all_with_probe() excludiert blacklisted Plugins
- [x] (Claude Opus 4.6, 2026-03-22): **Deferred Retry CLAP** — CLAP-Instrumente + Blacklist-Check im Deferred Loading
- [x] (Claude Opus 4.6, 2026-03-22): **Rust-Bridge Reconnect** — Auto-Reconnect bei Engine-Tod + robustere Reader-Loop (5 Retries)
- [x] (Claude Opus 4.6, 2026-03-22): **Blacklist-Dialog** — Neue UI: Blacklist anzeigen/verwalten/entsperren im Sandbox-Menü
- [x] (Claude Opus 4.6, 2026-03-22): **Fork-Probe Scanner** — _expand_multi_vst_plugins: Blacklist + fork-Probe vor pedalboard
- [x] (Claude Opus 4.6, 2026-03-22): **Browser Badges** — 💀 + [BLACKLISTED] + dimming + Insert-Warnung mit User-Override
- [x] (Claude Opus 4.6, 2026-03-22): **FX-Chain Guards** — VST3/VST2/CLAP Blacklist-Prüfung in _compile_devices()
- [x] (Claude Opus 4.6, 2026-03-22): **Rust Scanner Merge** — Browser triggert ScanPlugins, mergt Ergebnisse additiv

## v0.0.20.718 — 🔌 P7 IPC Integration + Warning Fixes

- [x] (Claude Opus 4.6, 2026-03-21): **P7** — engine.rs: ScanPlugins + LoadPlugin + Unload/Param/State Handler
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — audio_graph.rs: TrackNode.plugin_slots, Signal-Flow Integration
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — ipc.rs: ScanPlugins Cmd, PluginScanResult/PluginLoaded Events, ScannedPlugin
- [x] (Claude Opus 4.6, 2026-03-21): **P7** — rust_engine_bridge.py: 6 Methoden, 2 Signals, 2 Event-Dispatcher
- [x] (Claude Opus 4.6, 2026-03-21): **Fix** — 5 Compiler-Warnings behoben (0W/0E/286T)

## v0.0.20.716 — 🦀 P7A/P7B/P7C Rust Native Plugin Hosting (Real FFI)

- [x] (Claude Opus 4.6, 2026-03-21): **P7A** — vst3_host.rs: Real VST3 COM FFI (780 Z.) — Scanner, Instance, Process, Params
- [x] (Claude Opus 4.6, 2026-03-21): **P7B** — clap_host.rs: Real CLAP C FFI (782 Z.) — Scanner, Instance, Process, Params, State Stubs
- [x] (Claude Opus 4.6, 2026-03-21): **P7C** — lv2_host.rs: Real LV2/lilv FFI (660 Z.) — Dynamic Loading, Scanner, Instance, Run, Control Ports
- [x] (Claude Opus 4.6, 2026-03-21): **Infra** — Cargo.toml: libloading=0.8

## v0.0.20.714 — 🔧 Rust Toolchain Auto-Setup

- [x] (Claude Opus 4.6, 2026-03-21): **DX** — start_daw.sh + setup_all.py + install.py Rust-freundlich

## v0.0.20.713 — 🦀 P7C LV2 Host Scaffolding

- [x] (Claude Opus 4.6, 2026-03-21): **P7C** — lv2_host.rs NEU (440 Zeilen, UridMap, Scanner, AudioPlugin impl)

## v0.0.20.712 — 🦀 Rust IPC Commands + Engine Handlers

- [x] (Claude Opus 4.6, 2026-03-21): **RA2 Rust** — 3 IPC Commands + 3 Engine Handler + pub base64_decode

## v0.0.20.711 — 🎵🖥️ RA2 Instrument Sync + P3B/P5B Editor Scaffolding

- [x] (Claude Opus 4.6, 2026-03-21): **RA2** — 4 Instrument-Sync Methoden + sync_all_instruments()
- [x] (Claude Opus 4.6, 2026-03-21): **P3B** — VST2 Editor X11 (effEditOpen/Close, XCreateSimpleWindow)
- [x] (Claude Opus 4.6, 2026-03-21): **P5B** — CLAP GUI X11 Scaffolding (dual strategy)

## v0.0.20.710 — 🔧🦀 P2B Param Sync + RA1 Rust AudioGraph Rebuild

- [x] (Claude Opus 4.6, 2026-03-21): **P2B** — Param-Poller Thread in vst3_worker.py + param_changed Callback
- [x] (Claude Opus 4.6, 2026-03-21): **RA1 Rust** — apply_project_sync() (Tracks, Clips, Transport, Arrangement)

## v0.0.20.709 — 🛡️🔌 Plugin Sandbox Overrides + Latency PDC

- [x] (Claude Opus 4.6, 2026-03-21): **P6C** — sandbox_overrides.py + contextMenuEvent auf _DeviceCard
- [x] (Claude Opus 4.6, 2026-03-21): **P2C** — get_latency IPC in allen 4 Workern + SandboxedFx + ProcessManager
- [x] (Claude Opus 4.6, 2026-03-21): **P4A** — Worker-eigene URID Map (lilv.World reset im Subprocess)
- [x] (Claude Opus 4.6, 2026-03-21): **RA4** — compute_hybrid_pdc() für Rust↔Python Latenz-Synchronisation

## v0.0.20.708 — 🎵🔌🔀✅ Rust Pipeline RA2+RA3+RA4+RA5

- [x] (Claude Opus 4.6, 2026-03-21): **RA2** — rust_sample_sync.py
- [x] (Claude Opus 4.6, 2026-03-21): **RA3** — rust_audio_takeover.py
- [x] (Claude Opus 4.6, 2026-03-21): **RA4** — rust_hybrid_engine.py (Per-Track Rust/Python, Hybrid Mix)
- [x] (Claude Opus 4.6, 2026-03-21): **RA5** — EngineMode (Python/Hybrid/Rust), QSettings, Auto-Downgrade

## v0.0.20.707 — 🦀 Rust Project Sync (RA1 Python-Seite)

- [x] (Claude Opus 4.6, 2026-03-21): **RA1** — rust_project_sync.py (serialize + RustProjectSyncer)
- [x] (Claude Opus 4.6, 2026-03-21): **RA1** — Tracks/Clips/MIDI/Automation/Transport Serialisierung

## v0.0.20.706 — 🔌 Format-Worker komplett (P3/P4/P5)

- [x] (Claude Opus 4.6, 2026-03-21): **P3** — vst2_worker.py (FX+Instrument, MIDI, State)
- [x] (Claude Opus 4.6, 2026-03-21): **P4** — lv2_ladspa_worker.py (LV2 State + LADSPA Param-Snapshot)
- [x] (Claude Opus 4.6, 2026-03-21): **P5** — clap_worker.py (FX+Instrument, MIDI, Editor IPC)
- [x] (Claude Opus 4.6, 2026-03-21): **Routing** — 5-Format auto-dispatch in SandboxProcessManager

## v0.0.20.705 — 🎸 VST3 Sandbox Worker (P2A/P2B/P2C)

- [x] (Claude Opus 4.6, 2026-03-21): **P2A** — vst3_worker.py, Audio-Loop, Params, State, Auto-Routing
- [x] (Claude Opus 4.6, 2026-03-21): **P2B** — ShowEditor/HideEditor IPC, Worker-GUI
- [x] (Claude Opus 4.6, 2026-03-21): **P2C** — MIDI IPC, Instrument-Mode, pull(), SandboxedFx Instrument-API

## v0.0.20.704 — 🛡️ Crash Recovery UI (P6A/P6B/P6C komplett)

- [x] (Claude Opus 4.6, 2026-03-21): **P6A** — Mixer CrashIndicatorBadge, roter Crash-Rand, set_sandbox_state()
- [x] (Claude Opus 4.6, 2026-03-21): **P6B** — CrashLog Wiring, factory_restart(), CrashLogDialog
- [x] (Claude Opus 4.6, 2026-03-21): **P6C** — Audio→Plugin Sandbox Untermenü, SandboxStatusDialog, Restart-All
- [x] (Claude Opus 4.6, 2026-03-21): **P1C** — AudioSettingsDialog Sandbox-Toggle + QSettings

## v0.0.20.695 — 🎉 R1–R13 KOMPLETT (771 KB Rust, 7 Instrumente, 15 FX)

- [x] (Claude Opus 4.6, 2026-03-21): **R11** — bach_orgel.rs (~12 KB) + sf2.rs (~8 KB)
- [x] (Claude Opus 4.6, 2026-03-21): **R12** — audio_bridge.rs (~17 KB) — SharedAudioTransport + ProjectSync
- [x] (Claude Opus 4.6, 2026-03-21): **R13** — integration.rs (~12 KB) — A/B Test + Migration Report
- [x] (Claude Opus 4.6, 2026-03-21): **R13B** — engine_migration.py — can_track_use_rust() + get_migration_report()

## v0.0.20.694 — Phase R9+R10 (Rust)

- [x] (Claude Opus 4.6, 2026-03-21): **wavetable.rs** (~430 Z.) + **unison.rs** (~400 Z.) — R9 komplett
- [x] (Claude Opus 4.6, 2026-03-21): **fusion/oscillators.rs** (~420 Z.) — 7 Osc-Typen, PolyBLEP, Swarm, Bite
- [x] (Claude Opus 4.6, 2026-03-21): **fusion/filters.rs** (~340 Z.) — SVF + Ladder + Comb
- [x] (Claude Opus 4.6, 2026-03-21): **fusion/envelopes.rs** (~310 Z.) — ADSR + AR + AD + Pluck
- [x] (Claude Opus 4.6, 2026-03-21): **fusion/mod.rs** (~500 Z.) — FusionInstrument InstrumentNode

## v0.0.20.693 — Phase R9: Wavetable + Unison (Rust)

- [x] (Claude Opus 4.6, 2026-03-21): **wavetable.rs** (~430 Z.) — WavetableBank 256×2048, bilinear interpolation, 6 Built-in Tables, 8 Tests
- [x] (Claude Opus 4.6, 2026-03-21): **unison.rs** (~400 Z.) — UnisonEngine 16 Voices, Classic/Supersaw/Hyper, stereo spread, 10 Tests

## v0.0.20.690 — Phase R8 komplett: AETERNA (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R8C modulation.rs** (~470 Z.) — ModMatrix 8 Slots, 8 Sources, 7 Destinations, VoiceModState, 12 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **R8D State/Presets** — save_state/load_param, 5 Factory Presets, 31 AeternaCommand variants
- [x] (Claude Opus 4.6, 2026-03-20): **R8C+D voice.rs Integration** — ModMatrix in render_sample, pitch/cutoff/res/amp/pan/shape/fm modulation
- [x] (Claude Opus 4.6, 2026-03-20): **Python Bugfix** — aeterna_engine.py note_off(pitch), trigger_note normal AEG release

## v0.0.20.686 — Phase R8B: AETERNA Voice + Filter (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **aeterna/voice.rs** (~560 Z.) — AeternaVoice, AeternaVoicePool (32), AeternaVoiceParams (27 params), GlideState, 18 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **aeterna/mod.rs** (~380 Z.) — AeternaInstrument InstrumentNode, AeternaCommand (28 variants), Factory registration, 5 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **instruments/mod.rs** — AeternaInstrument Re-Export, InstrumentType::Aeterna.create(), Factory-Test

## v0.0.20.684 — Phase R8A: AETERNA Oszillatoren (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **aeterna/oscillator.rs** (~480 Z.) — 6 Waveforms, PolyBLEP, FM, Sub-Osc, Unison (1–16), Wave Morphing, 19 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **aeterna/mod.rs** — Module + Re-Exports registriert

## v0.0.20.682 — Phase R7B: DrumMachine Multi-Output (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **Per-Pad Output-Routing** — output_index auf Pad+Voice, render_voices routet Voices zu Main/Aux
- [x] (Claude Opus 4.6, 2026-03-20): **Aux Buffers + API** — Pre-allokiert, aux_output_buffers(), is_multi_output(), output_count()
- [x] (Claude Opus 4.6, 2026-03-20): **IPC** — SetDrumPadOutput, SetDrumMultiOutput + Engine-Dispatch + 2 Bridge-Methoden
- [x] (Claude Opus 4.6, 2026-03-20): **4 Tests** — enable/routing/silence/disabled-fallback

## v0.0.20.679 — Fix: Benchmark misst echte Rust-Render-Zeit

- [x] (Claude Opus 4.6, 2026-03-20): **Root Cause:** Benchmark maß `time.sleep(11610µs)` statt Rust-Render-Zeit → "Rust 60× langsamer"
- [x] (Claude Opus 4.6, 2026-03-20): **Engine:** `Instant::now()` Timing in `process_audio()`, Pong mit `render_time_us`
- [x] (Claude Opus 4.6, 2026-03-20): **Benchmark:** Liest jetzt `render_time_us` aus Pong, MIDI per-event statt batch

## v0.0.20.678 — Phase R7A: DrumMachine Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **instruments/drum_machine.rs** — 128 Pads, 64 Voices, Choke Groups (0–8), OneShot/Gate, GM Map, 12 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **IPC + Engine** — 5 Commands + 5 match-Arms + 5 Bridge-Methoden

## v0.0.20.677 — Fix: Rust Compile Errors (R6B + Engine)

- [x] (Claude Opus 4.6, 2026-03-20): **5× Borrow-Checker Fix** — alloc_voice_index() mit &[Voice] statt &mut self
- [x] (Claude Opus 4.6, 2026-03-20): **Engine Dispatch** — 8 match-Arms für MultiSample IPC Commands in engine.rs

## v0.0.20.676 — Phase R6B: MultiSample Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **instruments/multisample.rs** — MultiSampleInstrument (~1050 Zeilen), Zone-Mapping, Per-Zone DSP, 18 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **SampleZone + MultiSampleMap** — 256 Zones, Key/Vel-Range, 32 RR-Gruppen, zero-alloc find_zones
- [x] (Claude Opus 4.6, 2026-03-20): **Per-Zone DSP** — Biquad LP/HP/BP, Amp+Filter ADSR, 2 LFOs, 4 Mod-Slots (6 Sources × 4 Dest)
- [x] (Claude Opus 4.6, 2026-03-20): **Auto-Mapping** — Chromatic/Drum/VelocityLayer, auto_map_zones()
- [x] (Claude Opus 4.6, 2026-03-20): **IPC** — 8 neue Commands (AddSampleZone, SetZoneFilter, SetZoneLfo, etc.)
- [x] (Claude Opus 4.6, 2026-03-20): **Python Bridge** — 12 neue Methoden in rust_engine_bridge.py

## v0.0.20.675 — Rust Compile Fixes (R6A)

- [x] (Claude Opus 4.6, 2026-03-20): **1 Error + 1 Warning behoben** — SampleData Debug impl, unused _ctx

## v0.0.20.674 — Phase R6A: ProSampler Instrument (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **instruments/mod.rs** — InstrumentNode Trait, MidiEvent, InstrumentType Registry
- [x] (Claude Opus 4.6, 2026-03-20): **instruments/sampler.rs** — ProSamplerInstrument (~760 Zeilen), 64-Voice Poly, ADSR, Loop, Velocity Curve, 15 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **AudioGraph** — TrackNode.instrument Feld, Instrument-Processing in process()
- [x] (Claude Opus 4.6, 2026-03-20): **Engine** — MIDI-Routing zu Instrumenten, 5 neue IPC Commands (LoadInstrument, LoadSample, etc.)

## v0.0.20.672 — Phase R5: Sample Playback Engine (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **3 neue Dateien** — sample/mod.rs, voice.rs, voice_pool.rs (~750 Rust-Zeilen)
- [x] (Claude Opus 4.6, 2026-03-20): **R5A:** SampleData, WAV Loader (hound), Mono→Stereo, Resampling, pitch_ratio
- [x] (Claude Opus 4.6, 2026-03-20): **R5B:** SampleVoice (Cubic Interp, ADSR, Loop), VoicePool (Stealing), 13 Tests

## v0.0.20.671 — 3 Test-Fixes (87/87 Tests grün)

- [x] (Claude Opus 4.6, 2026-03-20): **reorder() Off-by-One**, **fast_tanh() clamp**, **dry/wet tolerance**

## v0.0.20.670 — Rust Compile Fixes (7 Errors + 2 Warnings)

- [x] (Claude Opus 4.6, 2026-03-20): **7 Errors + 2 Warnings** — Biquad::new() Args, Engine match exhaustiv, Reverb set_sample_rate, unused var

## v0.0.20.669 — Phase R3 + R4: Creative/Utility FX + FX Chain (Rust)

- [x] (Claude Opus 4.6, 2026-03-20): **R3: 10 FX-Module** — 2.636 Rust-Zeilen, 40 Unit-Tests
- [x] (Claude Opus 4.6, 2026-03-20): **R3A:** Chorus, Phaser, Flanger, Tremolo, Distortion (5 Modi)
- [x] (Claude Opus 4.6, 2026-03-20): **R3B:** Gate, DeEsser, Stereo Widener, Utility, Spectrum Analyzer (FFT)
- [x] (Claude Opus 4.6, 2026-03-20): **Bug-Fix:** Distortion Tube-Modus — tube_positive() korrekt aufgerufen
- [x] (Claude Opus 4.6, 2026-03-20): **R4A:** FX Chain System — AudioFxNode Trait, FxSlot, FxChain, Factory (15 FX), 8 Tests
- [x] (Claude Opus 4.6, 2026-03-20): **R4B:** TrackNode Integration — FxChain in AudioGraph, Pre/Post-Fader, 8 IPC Commands, FxMeter Event

## v0.0.20.667 — Rust DSP Primitives (Phase R1 KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **7 neue Rust-Dateien** — 1.560 Zeilen DSP Code, 30 Unit-Tests
- [x] (Claude Opus 4.6, 2026-03-20): **Biquad, Delay, ADSR, LFO, Math, Smoother, DC/Pan/Interpolation**

## v0.0.20.666 — CRITICAL: GUI Freeze + Silent Playback Fix

- [x] (Claude Opus 4.6, 2026-03-20): **should_use_rust() Safety Gate** — immer False, Rust PoC kann keine Python-Instrumente rendern
- [x] (Claude Opus 4.6, 2026-03-20): **RustEngineBridge Error-Flood-Schutz** — _shutting_down Flag, RuntimeError("deleted") Guard
- [x] (Claude Opus 4.6, 2026-03-20): **Graceful Disconnect** — kein Error-Logging nach gewolltem Shutdown

## v0.0.20.665 — Engine Migration Dialog Wiring

- [x] (Claude Opus 4.6, 2026-03-20): **Fehlender Slot `_on_engine_migration_dialog`** in MainWindow implementiert — Dialog jetzt via Audio-Menü erreichbar

## v0.0.20.664 — Rust Engine Warnings Cleanup

- [x] (Claude Opus 4.6, 2026-03-20): **61 Warnings → 0** — `#![allow(dead_code)]` crate-weit, 12 unused imports entfernt (vst3_host, clap_host, plugin_isolator, clip_renderer), TABLE const entfernt

## v0.0.20.663 — Responsive UI + Bug-Fix (ROADMAP KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **Bug-Fix scale_ai.py** — SCALES Import korrigiert (SCALE_DB.all_scales()), Backward-Compat-Alias in database.py
- [x] (Claude Opus 4.6, 2026-03-20): **Responsive Verdichtung TransportPanel** — 2-Tier resizeEvent: Tier1 <700px (Pre/Post/Count-In), Tier2 <520px (Punch/TS/Loop/Metro)
- [x] (Claude Opus 4.6, 2026-03-20): **Responsive Verdichtung ToolBarPanel** — 2-Tier resizeEvent: Tier1 <480px (Loop-Range), Tier2 <350px (Follow/Loop)
- [x] (Claude Opus 4.6, 2026-03-20): **ROADMAP 100% KOMPLETT** — Alle 10 Arbeitspakete + alle UI-Hotfix-Checkboxen abgehakt

## v0.0.20.662 — Engine Migration Controller (AP1 Phase 1D KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **EngineMigrationController** — 3 Subsysteme (audio_playback, midi_dispatch, plugin_hosting), Dependency-Chain, Hot-Swap, Cascade-Rollback, QSettings-Persistenz
- [x] (Claude Opus 4.6, 2026-03-20): **EnginePerformanceBenchmark** — A/B Python vs Rust, Render-Timing µs, P95/P99, CPU-Load%, XRuns, IPC-Roundtrip, formatierter Report
- [x] (Claude Opus 4.6, 2026-03-20): **Rust-Engine als Default** — set_rust_as_default() nur wenn alle 3 Subsysteme stabil auf Rust
- [x] (Claude Opus 4.6, 2026-03-20): **AudioEngine Rust-Delegation** — _start_rust_arrangement_playback(), Projekt-Sync via IPC, Auto-Fallback
- [x] (Claude Opus 4.6, 2026-03-20): **EngineMigrationWidget** — PyQt6 Settings-Panel, Toggle pro Subsystem, Benchmark-Runner, Quick-Actions

## v0.0.20.658 — DAWproject Roundtrip + Versionierung (AP10 Phase 10C+10D)

- [x] (Claude Opus 4.6, 2026-03-20): **Plugin-Mapping** — dawproject_plugin_map.py: 28 Internal-Mappings + VST3/CLAP/LV2/LADSPA, Well-Known DB, bidirektional
- [x] (Claude Opus 4.6, 2026-03-20): **Vollständiger Export** — Send-Export, Plugin-Mapping deviceIDs (spec-konform), FX-Chain Mapping
- [x] (Claude Opus 4.6, 2026-03-20): **Vollständiger Import** — Automation Lanes, Plugin States (Base64+JSON), Sends, Groups, Clip Extensions, Per-Note Expressions
- [x] (Claude Opus 4.6, 2026-03-20): **Roundtrip-Test** — Export→Import→Vergleich Framework: Transport, Tracks, Clips, Notes, Automation, Sends
- [x] (Claude Opus 4.6, 2026-03-20): **Projekt-Versionierung** — ProjectVersionService: auto/manual Snapshots, SHA-256 Dedup, Manifest, Auto-Pruning
- [x] (Claude Opus 4.6, 2026-03-20): **Snapshot-Diff** — diff_snapshots(): Transport/Tracks/Clips/Automation/Media Vergleich, SnapshotDiff.summary()

## v0.0.20.657 — AETERNA Wavetable Engine (AP7 Phase 7C — KOMPLETT)

- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Import** — WavetableBank: .wav/.wt Import, Serum clm-Chunk-Detection, 24-bit WAV, Auto-Frame-Size
- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Morphing** — wt_position als Mod-Target, per-sample read_block_modulated(), 3 Factory Presets
- [x] (Claude Opus 4.6, 2026-03-20): **Wavetable Editor** — draw_frame(), FFT get/set_frame_harmonics(), 6 Built-in Tables, normalize
- [x] (Claude Opus 4.6, 2026-03-20): **Unison Engine** — UnisonEngine Off/Classic/Supersaw/Hyper, 1-16 Voices, Detune/Spread/Width, sqrt(n) Norm

## v0.0.20.656 — Advanced Multi-Sample Sampler + Drum Rack (AP7 Phase 7A+7B)

- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Sample Mapping Editor** — ZoneMapCanvas 2D Key×Velocity Grid, ZoneInspector 5-Tab, Drag-Resize, Context-Menu
- [x] (Claude Opus 4.6, 2026-03-20): **Polyphoner Multi-Sample Engine** — 32-Voice, per-Voice ADSR/Filter/LFO, Voice-Stealing, Sample-Cache
- [x] (Claude Opus 4.6, 2026-03-20): **Round-Robin Gruppen** — MultiSampleMap RR-Counter, zyklische Auswahl
- [x] (Claude Opus 4.6, 2026-03-20): **Sample-Start/End/Loop-Punkte** — LoopPoints dataclass, Crossfade, Inspector-Tab
- [x] (Claude Opus 4.6, 2026-03-20): **Filter + ADSR pro Zone** — ZoneFilter LP/HP/BP mit Envelope-Modulation, ZoneEnvelope ADSR
- [x] (Claude Opus 4.6, 2026-03-20): **Modulations-Matrix** — 4 Slots × (7 Sources → 4 Destinations), 2 LFOs (5 Shapes)
- [x] (Claude Opus 4.6, 2026-03-20): **Auto-Mapping + Drag&Drop** — Chromatic/Drum/VelLayer/RR, GM-Drum-Keywords, Filename-Pattern
- [x] (Claude Opus 4.6, 2026-03-20): **Drum Rack Choke Groups** — DrumSlotState.choke_group, Engine mutual-exclusion bei Trigger
- [x] (Claude Opus 4.6, 2026-03-20): **Drum Rack Pad-Bank Navigation** — A/B/C/D = 4×16 = 64 Pads, expand_slots(), Bank-aware UI

## v0.0.20.655 — Mixer Multi-Output UI + Collapse/Expand

- [x] (Claude Opus 4.6, 2026-03-20): **Mixer-Kontextmenü Multi-Output** — Rechtsklick auf Drum-Track → 15 Child-Tracks + plugin_output_routing + rebuild_fx_maps
- [x] (Claude Opus 4.6, 2026-03-20): **Collapse/Expand Pad-Kanäle** — _children_collapsed State + _restore_collapse_states nach Refresh
- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Output Deaktivierung** — Child-Tracks löschen + Reset

## v0.0.20.654 — Drum Machine Multi-Output Engine

- [x] (Claude Opus 4.6, 2026-03-20): **DrumMachineEngine Multi-Output** — `_pull_multi_output()` liefert (frames, 32) für 16 Stereo-Outputs, `_slot_output_map`, set_multi_output/set_slot_output API
- [x] (Claude Opus 4.6, 2026-03-20): **DrumMachineWidget Auto-Wiring** — Liest Track.plugin_output_count, aktiviert Multi-Output, taggt Pull-Source
- [x] (Claude Opus 4.6, 2026-03-20): **set_fx_context() + rebuild_all_slot_fx()** — Fehlende Methoden für per-Slot FX-Chains

## v0.0.20.653 — CLAP Unified Presets + Multi-Output Wiring

- [x] (Claude Opus 4.6, 2026-03-20): **CLAP → Unified PresetBrowserWidget** — Alter v569 Timer entfernt, Undo-Notify, konsistentes Look & Feel VST3 ↔ CLAP
- [x] (Claude Opus 4.6, 2026-03-20): **Multi-Output Plugin Wiring** — `_plugin_output_map` + `_mix_source_to_track()` Helper + Split-Routing in `render_for_jack` Step 8 + `AudioEngine.rebuild_fx_maps()` Builder + Pull-Source Tagging

## v0.0.20.652 — Preset Browser & Plugin State Management

- [x] (Claude Opus 4.6, 2026-03-20): **AP4 Phase 4B — Preset-Browser (komplett)** — PresetBrowserService (Scan/Save/Load/Delete/Rename/Favorites/A-B), PresetBrowserWidget (QWidget mit Kategorie-Filter/Suche/Prev-Next/Favorit-Toggle/A-B-Button), VST3-Integration
- [x] (Claude Opus 4.6, 2026-03-20): **AP4 Phase 4C — Plugin-State Management (komplett)** — PluginStateManager (Undo/Redo-Stack/Auto-Save), Undo/Redo-Buttons im PresetBrowserWidget

## v0.0.20.651 — Statusleisten-Tech-Signatur

- [x] (GPT-5.4 Thinking, 2026-03-20): **Qt/Python/Rust Status-Signatur** — drei Logos unten rechts als gemeinsames Tech-Cluster statt verstreut in Menu/Toolbar/Bottom-Nav.
- [x] (GPT-5.4 Thinking, 2026-03-20): **UI beruhigt** — obere Mitte, obere Tool-Leiste und linke Bottom-Nav wieder freigeräumt.

## v0.0.20.650 — Multi-Feature: Warp/Sandbox/MPE/MultiOut/Export

- [x] (Claude Opus 4.6, 2026-03-20): **AP3 3C Task 4: Clip-Warp im Arranger** — Marker-Visualisierung, Stretch-Mode Menü, Auto-Warp
- [x] (Claude Opus 4.6, 2026-03-20): **AP4 4A: Sandboxed Plugin-Hosting (komplett)** — PluginSandboxManager, SharedAudioBuffer, Crash-Detection+Auto-Restart
- [x] (Claude Opus 4.6, 2026-03-20): **AP5 5C: Multi-Output Plugins** — Track.plugin_output_routing, create_plugin_output_tracks()
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 6B: MPE Support (komplett)** — MPEConfig, MPEChannelAllocator, MPEProcessor, Controller-Presets
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 10B Task 4: Pre-/Post-FX Export** — ExportConfig.fx_mode, UI ComboBox, filename suffix

## v0.0.20.649 — Menümitte-Rust-Badge

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge pixelnah an den Screenshot in die Menümitte verschoben**
- [x] (GPT-5.4 Thinking, 2026-03-20): **Transport-Leiste vom Badge befreit**

## v0.0.20.648 — Rust-Badge in Topbar-Mitte + Snap-Lesbarkeit

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge aus dem rechten Toolbereich in die Transport-Mitte verlegt**
- [x] (GPT-5.4 Thinking, 2026-03-20): **Obere Snap-/Werkzeugfelder sichtbar vergroessert**

## v0.0.20.647 — Centered Rust Badge + Grid Visibility

- [x] (GPT-5.4 Thinking, 2026-03-20): **Rust-Badge zentriert** — Branding-Slot in der Tool-Leiste statt rechter Projekt-Tab-Kante.
- [x] (GPT-5.4 Thinking, 2026-03-20): **ComboBox-Lesbarkeit erhöht** — Zeiger/1-16/1-32 in der Topbar klarer sichtbar.
- [x] (GPT-5.4 Thinking, 2026-03-20): **Toolbar entschlackt** — Projekt-Tab-Leiste rechts aufgeräumt, Python-Badge besser erkennbar.

## v0.0.20.646 — Rust Logo Badge

- [x] (GPT-5.4 Thinking, 2026-03-20): **Eigenständiges Rust-Badge** — in die Projekt-Tab-Leiste nahe Neues Projekt/Öffnen integriert, größer und klarer lesbar, ohne Qt-Vererbung.

## v0.0.20.645 — Toolbar Readability Hotfix

- [x] (GPT-5.2 Thinking, 2026-03-20): **Top-Toolbar Readability Hotfix** — Projekt-Tabs eigene Zeile + kompaktere Transport-Leiste + entquetschter rechter Bereich.

## v0.0.20.644 — Mega-Session: AP8 ✅ + AP6 6A/6C ✅ + AP9 ✅ + AP10 10A/10B + AP3 3C

- [x] (Claude Opus 4.6, 2026-03-20): **AP8 Phase 8C KOMPLETT** — 5 Utility FX → **AP8 vollständig abgeschlossen**
- [x] (Claude Opus 4.6, 2026-03-20): **GateFx** — Noise Gate, Hold, Sidechain, Range
- [x] (Claude Opus 4.6, 2026-03-20): **DeEsserFx** — Bandpass-Detektion, Listen-Mode
- [x] (Claude Opus 4.6, 2026-03-20): **StereoWidenerFx** — M/S Width, Mid/Side Gain
- [x] (Claude Opus 4.6, 2026-03-20): **UtilityFx** — Gain/Pan/Phase/Mono/DC/Swap
- [x] (Claude Opus 4.6, 2026-03-20): **SpectrumAnalyzerFx** — FFT + Peak Hold + API
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 Phase 6A** — Note Echo, Velocity Curve, 16 Chord-Typen, Drop-2/3/Open Voicings, 13 MIDI FX Presets
- [x] (Claude Opus 4.6, 2026-03-20): **AP6 Phase 6C** — 12 Factory Grooves, extract/apply/humanize
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9A** — PluginParamDiscovery, 13 FX Param Maps, Arm/Disarm
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9B** — Relative/Trim Automation Modes, apply_mode()
- [x] (Claude Opus 4.6, 2026-03-20): **AP9 Phase 9C** — Snapshot, Clip-Copy, LOG/EXP/S_CURVE → **AP9 vollständig abgeschlossen**
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 Phase 10A** — WAV/FLAC/MP3/OGG Export, TPDF/POW-R Dither, Peak/LUFS Normalize
- [x] (Claude Opus 4.6, 2026-03-20): **AP10 Phase 10B** — Stem Export, per-Track Rendering, BPM Naming (3/4 Tasks)
- [x] (Claude Opus 4.6, 2026-03-20): **AP3 Phase 3C Task 3** — TempoMap, beat↔time Konvertierung, tempo_ratio_at_beat()

## v0.0.20.643 — Creative FX + Scrawl + KI + UI Fix (AP8 8B ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP8 Phase 8B KOMPLETT** — 5 Creative FX mit Scrawl
- [x] (Claude Opus 4.6, 2026-03-19): **ChorusFx** — Scrawl = LFO-Shape, Multi-Voice
- [x] (Claude Opus 4.6, 2026-03-19): **PhaserFx** — Scrawl = Sweep-Envelope, 6-Stage Allpass
- [x] (Claude Opus 4.6, 2026-03-19): **FlangerFx** — Scrawl = Delay-Modulation
- [x] (Claude Opus 4.6, 2026-03-19): **DistortionPlusFx** — Scrawl = Waveshaper-Transferfunktion (1024 LUT)
- [x] (Claude Opus 4.6, 2026-03-19): **TremoloFx** — Scrawl = Amplitude-Shape + Stereo-Offset
- [x] (Claude Opus 4.6, 2026-03-19): **KI Curve Generator** — ki_generate_curve() für alle 5 Effekttypen
- [x] (Claude Opus 4.6, 2026-03-19): **UI Fix** — DevicePanel Dropdown-Menüs (View + Zone)

## v0.0.20.642 — Stretch-Modi + Essential FX (AP3 3B ✅ + AP8 8A ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP3 Phase 3B KOMPLETT** — 5 Stretch-Modi
- [x] (Claude Opus 4.6, 2026-03-19): **AP8 Phase 8A KOMPLETT** — 5 Essential FX DSP
- [x] (Claude Opus 4.6, 2026-03-19): **ParametricEqFx** — 8-Band Biquad DF2T (Bell/Shelf/HP/LP)
- [x] (Claude Opus 4.6, 2026-03-19): **CompressorFx** — Feed-forward RMS + Sidechain-Buffer Support
- [x] (Claude Opus 4.6, 2026-03-19): **ReverbFx** — Schroeder 4-Comb + 4-Allpass + Pre-Delay
- [x] (Claude Opus 4.6, 2026-03-19): **DelayFx** — Stereo + Ping-Pong + LP Filter + Feedback
- [x] (Claude Opus 4.6, 2026-03-19): **LimiterFx** — Brickwall Peak, instant attack, auto-release

## v0.0.20.641 — Sidechain + Routing + Warp (AP5 5B ✅ + 5C 3/4 + AP3 3A ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AP5 Phase 5B KOMPLETT** — Sidechain-Routing (4/4)
- [x] (Claude Opus 4.6, 2026-03-19): **AP5 Phase 5C (3/4)** — Patchbay, Output-Routing, Mono/Stereo
- [x] (Claude Opus 4.6, 2026-03-19): **AP3 Phase 3A KOMPLETT** — Warp-Marker System (4/4)
- [x] (Claude Opus 4.6, 2026-03-19): **WarpMarker Dataclass** — src_beat, dst_beat, is_anchor
- [x] (Claude Opus 4.6, 2026-03-19): **Beat-Detection** — detect_beat_positions (Essentia + Autocorr)
- [x] (Claude Opus 4.6, 2026-03-19): **Auto-Warp Service** — auto_detect_warp_markers + clear_warp_markers
- [x] (Claude Opus 4.6, 2026-03-19): **Audio Editor** — Warp Markers Kontextmenü (Auto-Detect + Clear)

## v0.0.20.640 — Comp-Tool (AP2 Phase 2D KOMPLETT ✅ / AP2 KOMPLETT ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **Comp-Tool** — set_comp_region, Klick auf Take-Lane, visuelle Comp-Bars
- [x] (Claude Opus 4.6, 2026-03-19): **AP2 Phase 2D KOMPLETT** — Alle 5/5 Tasks erledigt
- [x] (Claude Opus 4.6, 2026-03-19): **AP2 KOMPLETT** — Alle 4 Phasen (2A–2D) abgeschlossen

## v0.0.20.639 — Comping / Take-Lanes (AP2 Phase 2D: 4/5 Tasks)

- [x] (Claude Opus 4.6, 2026-03-19): **Loop-Recording** — Jeder Loop-Durchlauf als separater Take
- [x] (Claude Opus 4.6, 2026-03-19): **Take-Lanes im Arranger** — Visuell + Kontextmenü
- [x] (Claude Opus 4.6, 2026-03-19): **Flatten** — TakeService.flatten_take_group()
- [x] (Claude Opus 4.6, 2026-03-19): **Take-Management** — Rename, Delete, Activate, Toggle Lanes

## v0.0.20.638 — Punch Crossfade + Pre-Roll Auto-Seek (AP2 Phase 2C KOMPLETT ✅)

- [x] (Claude Opus 4.6, 2026-03-19): **AudioConfig Singleton** — pydaw/core/audio_config.py
- [x] (Claude Opus 4.6, 2026-03-19): **Punch Crossfade** — Linear fade-in/out, konfigurierbar
- [x] (Claude Opus 4.6, 2026-03-19): **Pre-Roll Auto-Seek** — Industriestandard Workflow
- [x] (Claude Opus 4.6, 2026-03-19): **AP2 Phase 2C KOMPLETT** — Alle 4/4 Tasks erledigt

## v0.0.20.637 — Punch In/Out (AP2 Phase 2C)

- [x] (Claude Opus 4.6, 2026-03-19): **Punch-Region im Arranger** — Rote Marker, Drag-Handles, Kontextmenü
- [x] (Claude Opus 4.6, 2026-03-19): **Automatisches Punch In/Out** — Boundary detection + auto-record
- [x] (Claude Opus 4.6, 2026-03-19): **Pre-/Post-Roll Einstellungen** — Transport Panel SpinBoxes
- [x] (Claude Opus 4.6, 2026-03-19): **Punch-Persistierung** — Project Model + Restore
- [x] (Claude Opus 4.6, 2026-03-19): **MainWindow Verdrahtung** — Komplett: Arranger↔Transport↔Recording

## v0.0.20.636 — Multi-Track Recording (AP2 Phase 2B)

- [x] (Claude Opus 4.6, 2026-03-19): **Multi-Track Recording** — Mehrere armed Tracks gleichzeitig, separate WAV, JACK+sounddevice
- [x] (Claude Opus 4.6, 2026-03-19): **Input-Routing** — Mixer ComboBox, Hardware-Input-Detection, Track.input_pair
- [x] (Claude Opus 4.6, 2026-03-19): **Buffer-Size Settings** — ComboBox 64-4096 in AudioSettingsDialog, Settings→RecordingService
- [x] (Claude Opus 4.6, 2026-03-19): **PDC Framework** — set/get_track_pdc_latency, Sample-Trimming, Beat-Korrektur

## v0.0.20.634 — Rust Build Fix

- [x] (Claude Opus 4.6, 2026-03-19): **Rust kompiliert jetzt** — Arc Ownership Fix + 2 Warnings behoben

## v0.0.20.633 — Setup-Automatisierung

- [x] (Claude Opus 4.6, 2026-03-19): **Komplett-Installer** — setup_all.py, INSTALL.md, TEAM_SETUP_CHECKLIST.md

## v0.0.20.632 — Audio Recording Phase 2A (Single-Track Recording)

- [x] (Claude Opus 4.6, 2026-03-19): **AP2 Phase 2A komplett** — RecordingService Rewrite (JACK/PipeWire/sounddevice), Mixer R-Button, 24-bit WAV in Projekt-Ordner, Auto Clip-Erstellung, Count-In, Input Monitoring.

## v0.0.20.631 — Rust Audio-Engine Phase 1B (AudioNode + ClipRenderer + Lock-Free)

- [x] (Claude Opus 4.6, 2026-03-19): **AP1 Phase 1B komplett** — AudioNode Trait, Lock-Free ParamRing/AudioRing/MeterRing, ClipStore + ArrangementRenderer, Engine-Integration, Python Bridge erweitert, Architektur-Doku.

## v0.0.20.630 — Rust Audio-Engine Phase 1A (Skeleton + IPC Bridge)

- [x] (Claude Opus 4.6, 2026-03-19): **AP1 Phase 1A komplett** — Cargo-Projekt, IPC-Protokoll, AudioGraph, Transport, PluginHost-Trait, SinePoC, Python Bridge, Build-Doku, Test-Script. Bestehende Python-Engine unberührt (Feature-Flag).

## v0.0.20.617 — Slot-Timer Repaint + Arranger Follow-Grid Fix

- [x] (Claude Opus 4.6, 2026-03-19): **Slot-Timer** — Aktive Buttons direkt repainted.
- [x] (Claude Opus 4.6, 2026-03-19): **Follow-Grid** — Volles Repaint nach Scroll.

## v0.0.20.616 — Hotfix: Snapshot transport Tippfehler

- [x] (Claude Opus 4.6, 2026-03-19): **self._transport → self.transport** in get_runtime_snapshot().

## v0.0.20.615 — Launcher Slot Loop-Position Fix

- [x] (Claude Opus 4.6, 2026-03-19): **Slot Loop-Position** zeigt jetzt korrekte Zeit via `get_runtime_snapshot()` statt unsicherem _voices-Zugriff.

## v0.0.20.614 — CRITICAL: Clip Launcher Loop Fix + AudioEditor Adapter

- [x] (Claude Opus 4.6, 2026-03-19): **CRITICAL FIX: Clips loopen nicht** — Default Follow-Action stoppte nach 1 Durchlauf. Fix: Beide Actions='Stopp' → loop forever.
- [x] (Claude Opus 4.6, 2026-03-19): **AudioEditor._local_playhead_beats** nutzt jetzt Adapter-Beat statt `transport.current_beat` direkt. Fallback beibehalten.

## v0.0.20.613 — Dual-Clock Phase C live + E (Alle Editoren auf Adapter)

- [x] (Claude Opus 4.6, 2026-03-19): **Feature-Flag aktiviert** — `editor_dual_clock_enabled=True`, Arranger=Passthrough, Launcher=lokaler Slot-Beat.
- [x] (Claude Opus 4.6, 2026-03-19): **PianoRollEditor auf Adapter** — Adapter-Playhead hat Vorrang, Fallback auf Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **NotationWidget auf Adapter** — Adapter-Playhead, Click-to-Seek bleibt bei Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **AudioEventEditor auf Adapter** — Adapter-Playhead, playing_changed bleibt bei Transport.
- [x] (Claude Opus 4.6, 2026-03-19): **EditorTabs + MainWindow Wiring** — editor_timeline durchgereicht an alle 3 Editoren.

## v0.0.20.612 — Dual-Clock Architektur Phase A+B+C+D (Vorbau komplett)

- [x] (Claude Opus 4.6, 2026-03-19): **EditorFocusContext + LauncherSlotRuntimeState** — Frozen/mutable Dataclasses für Dual-Clock-System.
- [x] (Claude Opus 4.6, 2026-03-19): **get_runtime_snapshot()** — GUI-sicherer Snapshot unter Lock aus ClipLauncherPlaybackService.
- [x] (Claude Opus 4.6, 2026-03-19): **EditorTimelineAdapter** — Zentrale Zeitumrechnung mit Feature-Flag, Snapshot-Polling, Arranger/Launcher-Logik.
- [x] (Claude Opus 4.6, 2026-03-19): **ClipContextService erweitert** — editor_focus_changed Signal + Focus-API + Builder-Factories.
- [x] (Claude Opus 4.6, 2026-03-19): **ServiceContainer Wiring** — editor_timeline Feld, Erstellung, Brücke, Shutdown.
- [x] (Claude Opus 4.6, 2026-03-19): **Phase D: Launcher + Arranger senden echten Fokus** — `_emit_launcher_focus()` bei Slot-Klick/Launch, `_on_clip_activated()` baut Arranger-Fokus.

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

## v0.0.20.592 — Piano Roll: Loop Region Controls (2026-03-18)

- [x] Loop L/Bar Spinboxes, Rechtsklick-Drag Loop im Ruler, oranges Loop-Band, Loop-Button funktional.

## v0.0.20.591 — Clip Launcher: Bitwig-Style Loop Controls (2026-03-18)

- [x] Loop Start/Länge Spinboxes steuern die Loop-Region korrekt (loop_start_beats/loop_end_beats).
- [x] Separate Clip-Länge Spinbox für length_beats.

## v0.0.20.590 — Clip Launcher: Bitwig-Style Drag + Symbols (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Plain Drag** — `setDown(False)` fix, einfaches Ziehen ohne Modifier.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **▶ Play / ● Record / ■ Stop** — Bitwig-Symbole im Clip Launcher.

## v0.0.20.589 — Clip Launcher → Arranger Drag&Drop (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Launcher→Arranger Drag** — Launcher-Clips per Alt/Ctrl+Drag in Arranger ziehbar. Duplikat wird mit `launcher_only=False` promotet.

## v0.0.20.589 — Clip Launcher → Arranger Drag&Drop (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Plain Drag** — Launcher-Slots starten DnD ohne Modifier.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Arranger akzeptiert Launcher-Clips** — Dupliziert + `launcher_only=False`.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Ghost-Preview** — 🎵/🔊 + Clip-Name beim Drag.

## v0.0.20.588 — Clip Launcher: launcher_only Flag (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **launcher_only=True** — Clips im Launcher erscheinen nicht mehr im Arranger (Bitwig-Style).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **arrangement_renderer** — Launcher-only Clips werden auch beim Audio-Playback übersprungen.

## v0.0.20.587 — Clip Launcher: MIDI Real-Time Playback + Creation (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **MIDI Realtime Dispatch** — Non-SF2 instruments now play MIDI clips via SamplerRegistry (Pro Audio Sampler, Fusion, VST3, CLAP, Drum Machine all working).
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **MIDI Clip Creation** — Right-click/double-click empty slot creates MIDI or Audio clip directly in Clip Launcher.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Mini Piano-Roll** — MIDI clips show Bitwig-style note visualization in slot buttons.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Loop-aware MIDI** — Correct note_off at loop boundaries, polyphonic tracking, all_notes_off on stop.

## v0.0.20.586 — Bounce GUI-Freeze Fix (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents 50→8 Blöcke** — Qt Event-Loop wird jetzt alle 8 Blöcke gepumpt statt 50. Verhindert "main.py antwortet nicht" beim Bounce.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents in _render_engine_notes_offline** — fehlte komplett.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **processEvents vor WAV-Write** — letzte Pump vor dem Schreiben.

## v0.0.20.585 — Fusion Bounce-in-Place Fix (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Fusion Bounce SILENT** — `track.plugin_type` war leer obwohl Fusion-State vorhanden. Auto-Detection aus `instrument_state`-Keys (`'fusion'` → `'chrono.fusion'`) und Fallback-Engine-Erstellung eingefügt.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Bounce-Diagnostik verbessert** — `[BOUNCE]`-Log zeigt `instrument_state_keys` für schnelles Debugging.

## v0.0.20.584 — GUI Performance Deep-Fix (2026-03-18)

- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Signal-Kaskade eliminiert** — `FusionWidget._persist_instrument_state()` rief `project_updated.emit()` auf → 15+ UI-Panels machten Full-Refresh pro Knob-Dreh. `_emit_updated()` entfernt; State wird weiterhin korrekt in `trk.instrument_state` gespeichert.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Zentraler VU-Meter-Timer** — N per-Strip `QTimer(33ms)` durch einen `MixerPanel._tick_all_vu_meters()` ersetzt. showEvent/hideEvent steuern Start/Stop. Reduktion: N×30fps → 1×30fps.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Transport + GL-Overlay 30fps** — Timer von 16ms auf 33ms. ~60 weniger Callbacks/s.
- [x] FIXED (Claude Opus 4.6, 2026-03-18): **Arranger Hover-Throttling** — Doppelte `_clip_at_pos()` verschmolzen + 50ms Throttle. Clip-Iteration: ~1000/s → ~20/s.

## v0.0.20.583 — Fusion Scrawl Hover-Repaint Hotfix (2026-03-17)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Scrawl Hover-Repaint Storm** — `ScrawlCanvas` redrawt bei normalem Maus-Hover nicht mehr permanent; Realtime-Redraw bleibt auf echte Zeichenvorgaenge begrenzt.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Freehand Preview Cap** — freie Zeichen-Samples sind jetzt lokal begrenzt, damit ein langes Scribble den Canvas-Paint nicht unnoetig aufblaeht.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — naechster Feature-Schritt, sobald der User-Regressionstest fuer Mouse/UI-Fluidity sauber ist.

## v0.0.20.582 — Fusion Regression Smoke-Test + Snapshot Flush (2026-03-17)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Snapshot Flush vor Save/Preset** — Fusion nutzt jetzt `_capture_state_snapshot()`; offene coalescte MIDI-CC-Werte werden vor dem Snapshot in die Knobs/Engine geschrieben.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Regression Harness** — `pydaw/tools/fusion_smoke_test.py` prueft queued MIDI-CC Snapshot, Scrawl Recall, Wavetable Recall und Modulwechsel.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Manueller Testplan** — `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md` beschreibt die reproduzierbaren UI/MIDI/Recall-Schritte fuer das echte User-Setup.
- [ ] AVAILABLE: **Fusion: LFO Modulation** — naechster Feature-Schritt nach bestandenem Smoke-Test im echten PyQt6-Setup.

## v0.0.20.581 — Fusion Scrawl State Save/Load Fix (2026-03-17)

- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Scrawl State Persistenz** — Projekt-/Preset-State enthaelt jetzt `scrawl_points`, `scrawl_smooth` und optional `wt_file_path` statt nur Modul-Typen + Knob-Werte.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **Scrawl-Editor schreibt jetzt wirklich mit** — gezeichnete Wellen triggern den bestehenden Fusion-only Persist-Timer, damit sie beim Speichern nicht verloren gehen.
- [x] FIXED (OpenAI GPT-5.4 Thinking, 2026-03-17): **State-Recall fuer Editor/Engine/Voices** — Restore spielt den gespeicherten Scrawl-Zustand wieder in Engine, aktive Voices und die Editor-Anzeige ein.
- [x] FIXED in v0.0.20.582 (OpenAI GPT-5.4 Thinking, 2026-03-17): **Fusion Regression Smoke-Test UI/MIDI/State-Recall** — konsolidiert in `pydaw/tools/fusion_smoke_test.py` + `PROJECT_DOCS/testing/FUSION_SMOKE_TEST.md`.

## v0.0.20.580 — Fusion MIDI-CC UI Coalescing (~60 Hz) (2026-03-17)

- `pydaw/plugins/fusion/fusion_widget.py`: Fusion-Knobs queueen eingehende MIDI-CC-Werte jetzt pro Widget und flushen sie ueber einen Fusion-only `QTimer` mit 16 ms Intervall (~60 Hz). Das reduziert Repaints/Engine-Writes bei CC-Flut, ohne `CompactKnob` global zu veraendern.
- `pydaw/plugins/fusion/fusion_widget.py`: dynamische OSC/FLT/ENV-Extra-Knobs droppen beim Rebuild offene gepufferte CC-Werte; `shutdown()` flusht noch ausstehende CCs vor dem restlichen Cleanup.

## v0.0.20.579 — Fusion GUI Hotfix: debounced State Persist (2026-03-17)

- `pydaw/plugins/fusion/fusion_widget.py`: neuer Fusion-only `QTimer` (single-shot, 120 ms) fuer debouncte Projekt-Persistenz. `engine.set_param()` bleibt sofort, aber der teure State-Snapshot + `project_updated` wird bei CC-Flut zusammengefasst.
- `pydaw/plugins/fusion/fusion_widget.py`: `shutdown()` flusht einen evtl. noch aktiven Persist-Timer sicher, bevor Pull-Source/SamplerRegistry entfernt werden.

## v0.0.20.578 — Fusion MIDI/Range/Realtime-Safety Hotfix (2026-03-17)

- `pydaw/plugins/sampler/ui_widgets.py`: `CompactKnob` unterstuetzt jetzt echte Wertebereiche (`setRange()`, `minimum()`, `maximum()`), skaliert MIDI-CC korrekt auf diesen Bereich und zeichnet Arc/Pointer normiert. Default-0..100 bleibt fuer bestehende Widgets kompatibel.
- `pydaw/plugins/fusion/fusion_widget.py`: Fusion setzt echte Knob-Ranges, bindet dynamische OSC/FLT/ENV-Extra-Knobs nach Rebuild wieder an Automation/MIDI Learn, entfernt alte CC-Listener und korrigiert mehrere Skalierungsfaelle (`flt.mode`, `flt.feedback`, `flt.damp_freq`, `osc.unison_*`, `osc.index`, `osc.smooth`, `aeg.loop` usw.).
- `pydaw/plugins/fusion/fusion_engine.py`: Realtime-sichere Param-Synchronisation — GUI/MIDI-Thread aendert nur Shared-State; aktive Voices werden gesammelt unter Lock am Pull-Rand aktualisiert.

## v0.0.20.569 — MIDI Learn Persistent CC Mapping (2026-03-17)

- `pydaw/plugins/sampler/ui_widgets.py`: `CompactKnob._on_midi_learn_cc()` speichert CC-Mapping in `_persistent_cc_map`. `CompactKnob.bind_automation()` stellt Mapping automatisch wieder her (ueberlebt Widget-Rebuild bei Zoom out/in). Context Menu „Mapping entfernen" loescht auch aus persistent map.

## v0.0.20.568 — MIDI Learn + Rechtsklick fuer ALLE Plugins (2026-03-17)

- `pydaw/ui/fx_audio_widgets.py`: `_AudioFxBase._show_param_automation_menu()` erweitert um MIDI Learn (13 Audio-FX: EQ-5, Delay-2, Reverb, Comb, Compressor, Filter+, Distortion+, Dynamics, Flanger, PitchShifter, Tremolo, PeakLimiter, Chorus, XY FX, De-Esser). Neue Methoden: `_start_midi_learn()`, `_remove_midi_mapping()`.
- `pydaw/ui/fx_device_widgets.py`: `_NoteFxBase` erweitert um `_install_param_context_menu()` + `_show_notefx_context_menu()`. 6 Note-FX Widgets (Transpose, VelocityScale, ScaleSnap, Chord, Arp, Random) haben jetzt Rechtsklick mit Show Automation + MIDI Learn + Reset.

## v0.0.20.567 — Alle 3 Container-FX-Menues mit allen Formaten (2026-03-17)

- `pydaw/ui/fx_device_widgets.py`: Neue shared Funktion `_build_container_fx_menu()`. Alle 3 Container-Widgets (_FxLayerContainerWidget, _ChainContainerWidget, _InstrumentLayerContainerWidget) zeigen jetzt VST3/CLAP/VST2/LV2/DSSI/LADSPA im FX-Add-Menue.

## v0.0.20.566 — SF2-Widget + FX-Menue ohne Limit (2026-03-17)

- `pydaw/ui/device_panel.py`: SF2-Widget fuer Layer-Zoom mit Bank/Preset QSpinBox + SF2-Datei-Picker + Live-Engine `set_program()`. FX-Menue-Limit von 80 entfernt, grosse Listen werden in alphabetische 40er-Gruppen aufgeteilt.

## v0.0.20.565 — Vollstaendiges FX-Menue mit allen Plugin-Formaten (2026-03-17)

- `pydaw/ui/device_panel.py`: `_build_full_fx_menu()` erstellt Menue mit Built-in + VST3/CLAP/VST2/LV2/DSSI/LADSPA. `_show_layer_add_fx_menu()` unified fuer alle Container-Typen. `_show_chain_add_fx_menu()` delegiert.

## v0.0.20.564 — ProSampler Import Fix + SamplerRegistry Schutz (2026-03-17)

- `pydaw/ui/device_panel.py`: `ProSamplerWidget` → `SamplerWidget` (Klassenname-Fix). `widget._track_id = track_id` statt Setter (SamplerRegistry-Ueberschreibung verhindert). Widget's eigene Pull-Source wird nach Engine-Swap entfernt.

## v0.0.20.563 — Einheitliche Widget-Groesse im Layer-Zoom (2026-03-17)

- `pydaw/ui/device_panel.py`: Alle Built-in + externe Instrument-Widgets im Layer-Zoom bekommen `Expanding` SizePolicy + `setMinimumWidth(0)` + `setMaximumWidth(16777215)`.

## v0.0.20.562 — FX Layer + Chain Zoom (2026-03-17)

- `pydaw/ui/device_panel.py`: Neue Methoden `zoom_into_fx_layer()`, `zoom_into_chain()`, `_render_fx_layer_zoom()`, `_render_chain_zoom()`. Chain-Management: `_chain_move_fx()`, `_chain_toggle_fx()`, `_chain_remove_fx()`, `_show_chain_add_fx_menu()`. Breadcrumb zeigt alle 3 Container-Typen.
- `pydaw/ui/fx_device_widgets.py`: `_FxLayerContainerWidget._zoom_into_fx_layer()`, `_ChainContainerWidget._zoom_into_chain()` mit Zoom-Buttons in der UI.

## v0.0.20.561 — FX-Chain im Layer-Zoom: Reorder/Enable/Remove (2026-03-17)

- `pydaw/ui/device_panel.py`: FX-Cards im Layer-Zoom haben jetzt on_up/on_down/on_power/on_remove Callbacks. Neue Methoden: `_layer_move_fx()`, `_layer_toggle_fx()`, `_layer_remove_fx()`, `_get_layer_devices_list()`, `_emit_layer_update()`. FX-Cards bekommen Expanding SizePolicy.

## v0.0.20.560 — Rechtsklick-Menue + Visual Polish im Layer-Zoom (2026-03-17)

- `pydaw/ui/device_panel.py`: `_setup_automation()` wird jetzt nach Engine-Verbindung aufgerufen → Rechtsklick auf Knobs zeigt "Show Automation", "MIDI Learn", "Reset to Default".

## v0.0.20.559 — Layer-Zoom: 5 Critical Fixes (2026-03-17)

- `pydaw/ui/device_panel.py`: `_make_layer_instrument_widget()` komplett ueberarbeitet — korrekte Constructor-Args (project_service, audio_engine, automation_manager), Engine-Verbindung zu existierender Layer-Engine statt eigener Kopie, `_restore_instrument_state()` + `_setup_automation()` Aufruf. "+ Audio-FX → Layer" Button mit `_show_layer_add_fx_menu()` + `_add_fx_to_layer()`. Instrument-Card volle Viewport-Breite.

## v0.0.20.558 — Engine-Lookup fuer alle Plugin-Formate (2026-03-17)

- `pydaw/ui/fx_device_widgets.py`: VST3 `_get_runtime_param_infos()`, `_get_runtime_vst_host()`, CLAP `_get_runtime_param_infos()`, `_find_live_clap_plugin()` — alle erweitert um Layer-Engine-Lookup via `inst_engines[device_id]`.
- `pydaw/ui/device_panel.py`: Virtual Device ID = Engine-Key-Format (`tid:ilayer:N`). Editor-Button wieder aktiviert.

## v0.0.20.557 — Stuck Notes Fix (2026-03-17)

- `pydaw/audio/audio_engine.py`: `_InstrumentLayerDispatcher` bekommt `_is_layer_dispatcher` Flag. `note_off()` nutzt `inspect.signature()` fuer robuste Erkennung (0 args vs pitch arg).
- `pydaw/ui/main_window.py`: `_route_live_note_to_vst()` ueberspringt Layer-Dispatcher (SamplerRegistry handled es).

## v0.0.20.556 — CRITICAL: Sound-Pipeline Fix (2026-03-17)

- `pydaw/audio/audio_engine.py`: `layers_spec` → `layers` (NameError tötete die komplette Dispatcher-Erstellung). Instrument-Card MinWidth 600→viewport. `_InstrumentLayerDispatcher` erhaelt `layer_volumes`. Pull-Source als Dispatcher statt per-Layer registriert (Bitwig-Modell).

## v0.0.20.555 — Bitwig-Style Layer-Zoom Phase 2: Externe Plugin-Parameter (2026-03-17)

- `pydaw/ui/device_panel.py`: `_make_layer_instrument_widget()` ueberarbeitet — externe Plugins (ext.vst3/vst2/clap/lv2) gehen jetzt durch `make_audio_fx_widget()` Factory mit virtuellem Device-Dict. Ergebnis: identische Parameter-Slider, Editor-Button und Sync-Timer wie auf normalen Tracks. Built-in Instrumente behalten ihre nativen Widgets.

## v0.0.20.554 — Bitwig-Style Layer-Zoom Phase 1 (2026-03-17)

- `pydaw/ui/device_panel.py`: Navigation-Stack (`_nav_stack`), Breadcrumb-Leiste mit "← Zurueck" Button und Pfadanzeige. `zoom_into_layer()`, `zoom_out()`, `_get_layer_context()`, `_update_breadcrumb()`. `_render_layer_zoom()` rendert Layer-Inhalt: Instrument-Widget als Device-Card + per-Layer FX. `_make_layer_instrument_widget()` erzeugt Built-in Widgets (AETERNA, BachOrgel, Sampler, Drum) oder Info-Widget fuer externe Plugins. `QPushButton` Import hinzugefuegt.
- `pydaw/ui/fx_device_widgets.py`: "🔍 Layer oeffnen" Zoom-Button in `_build_one_layer()`. `_zoom_into_layer()` Methode sucht DevicePanel per Widget-Tree und ruft `zoom_into_layer()` auf.

## v0.0.20.544 — CRITICAL BUGFIX: NotationView __init__ (2026-03-17)

- `pydaw/ui/notation/notation_view.py`: `_beats_per_bar()` war versehentlich mitten in `__init__()` eingefuegt, wodurch `__init__` bei Zeile 605 endete und alles danach (input_state, tools, layer_manager, ghost_renderer, 80+ Zeilen Init-Code) unerreichbar war. Fix: `_beats_per_bar()` als eigene Methode nach `__init__()` platziert. Alle Init-Attribute werden jetzt korrekt gesetzt.

## v0.0.20.543 — SF2 als Layer-Instrument + Velocity-Crossfade (2026-03-17)

- `pydaw/audio/audio_engine.py`: `chrono.sf2` Erkennung in Instrument-Layer-Block — erstellt `FluidSynthRealtimeEngine` mit `sf2_path`/`sf2_bank`/`sf2_preset` aus Layer-Daten. `_InstrumentLayerDispatcher` erweitert auf 5-Tupel `(vel_min, vel_max, key_min, key_max, vel_crossfade)` — Crossfade-Logik in `note_on()`: lineare Velocity-Skalierung in Uebergangszonen. Range-Extraktion liest `vel_crossfade`.
- `pydaw/ui/fx_device_widgets.py`: `_set_layer_instrument()` oeffnet QFileDialog fuer SF2-Dateien wenn `chrono.sf2` gewaehlt. "Xfade:" QSpinBox (0-64) in Range-Zeile pro expandiertem Layer.
- `pydaw/ui/fx_specs.py`: `get_instruments()` erweitert um "SF2 Soundfont".

## v0.0.20.542 — Instrument-Layer: Built-in Instrument Support (2026-03-17)

- `pydaw/audio/audio_engine.py`: Instrument-Layer Engine-Erstellung erweitert um Built-in Instrumente (`chrono.aeterna` → AeternaEngine, `chrono.sampler` → ProSamplerEngine, `chrono.drum_machine` → DrumMachineEngine, `chrono.bach_orgel` → BachOrgelEngine). Interface-Pruefung via `hasattr(engine, "note_on") and hasattr(engine, "pull")` statt `_ok`. Doppel-Append-Schutz via `engine=None` nach Built-in-Block.

## v0.0.20.541 — Container Preset Save/Load (2026-03-17)

- `pydaw/ui/fx_device_widgets.py`: 💾/📂 Buttons im Header aller 3 Container-Widgets (FxLayer, Chain, InstrumentLayer). `_load_preset()` Methode pro Widget (merged layers/devices + params, rebuilt UI). Neue Hilfsfunktionen: `_container_presets_dir()` (Verzeichnis `~/.config/ChronoScaleStudio/container_presets/`), `_save_container_preset()` (JSON-Export via QFileDialog), `_load_container_preset()` (JSON-Import via QFileDialog). `Path` Import hinzugefuegt.

## v0.0.20.540 — Instrument-Layer Phase 3: Velocity-Split / Key-Range (2026-03-17)

- `pydaw/audio/audio_engine.py`: `_InstrumentLayerDispatcher` erweitert mit `layer_ranges` Parameter — `note_on()` filtert per-Layer nach `(vel_min, vel_max, key_min, key_max)`. Range-Extraktion bei Dispatcher-Erstellung aus Layer-Daten.
- `pydaw/ui/fx_device_widgets.py`: 4 QSpinBox-Felder pro expandiertem Layer (Vel Min/Max + Key Min/Max, 0-127). `_set_layer_range()` Handler. `_midi_note_name()` Hilfsfunktion (MIDI-Note → "C4", "F#2" etc.).

## v0.0.20.539 — Instrument-Layer Phase 2: Multi-Engine + MIDI-Dispatch (2026-03-17)

- `pydaw/audio/audio_engine.py` (+120 Zeilen): `_InstrumentLayerDispatcher` Klasse — fans note_on/note_off/all_notes_off an alle Layer-Engines. Phase 3b in `_create_vst_instrument_engines()` — scannt Projekt-Tracks nach `chrono.container.instrument_layer`, erstellt pro Layer eine VST3/VST2/CLAP InstrumentEngine, registriert Dispatcher in SamplerRegistry, registriert per-Layer Pull-Sources. Engine-Reuse fuer bestehende Layer-Keys.

## v0.0.20.538 — LV2/CLAP Slider folgt Automation (2026-03-17)

- `pydaw/ui/fx_device_widgets.py`: LV2 Widget — `_ui_sync_timer` Erstellung (QTimer 60ms) + `_sync_from_rt()` Methode. CLAP Widget — `_ui_sync_timer` Erstellung (QTimer 60ms) + `_sync_from_rt()` Methode + `.start()` nach Build. Beide polled RT-Store mit `get_smooth()`/`get_param()`, updated Sliders/Spinboxes/CheckBoxes mit QSignalBlocker. Jetzt haben alle 5 Plugin-Format-Widgets (AudioChainContainer, LV2, LADSPA, VST3, CLAP) den gleichen RT-Sync-Mechanismus.

## v0.0.20.537 — Instrument-Layer Picker: Externe Plugins (2026-03-17)

- `pydaw/ui/fx_device_widgets.py`: `_show_instrument_picker()` komplett ueberarbeitet — zeigt jetzt Built-in Instrumente UND externe Plugins (VST3, CLAP, VST2, LV2, DSSI, LADSPA) als Submenues. Liest Plugin-Cache via `plugin_scanner.load_cache()`, filtert nach `is_instrument=True`. Format-Labels mit Zaehler, max 50 pro Format.

## v0.0.20.536 — Instrument-Layer (Stack) Phase 1 (2026-03-17)

- `pydaw/ui/fx_device_widgets.py` (+300 Zeilen): `_InstrumentLayerContainerWidget` — violettes Farbschema (#ce93d8), expandierbare Layer mit Instrument-Badge und Picker, Per-Layer Volume/Enable/Remove, Per-Layer FX Devices mit Enable/Disable/Remove/Reorder (▲/▼), Add-FX-Menue pro Layer.
- `pydaw/audio/fx_chain.py`: `_compile_devices()` erkennt `chrono.container.instrument_layer` und erstellt `FxLayerContainer` (parallele Audio-Verarbeitung). `ensure_track_fx_params()` registriert RT-Key `afx:{tid}:{did}:layer_mix`.
- `pydaw/ui/device_panel.py`: `add_instrument_layer_to_track()` API. Container-Routing-Guard fuer instrument_layer. Rechtsklick-Menue mit "🎹 Instrument Layer (Stack)".
- `pydaw/ui/fx_specs.py`: `get_instruments()` mit 4 Built-in Instrumenten. `get_containers()` erweitert um Instrument Layer Eintrag. `make_audio_fx_widget()` Dispatch.

## v0.0.20.535 — Notation: Playhead Click-to-Seek + Follow Playhead (2026-03-17)

- `pydaw/ui/notation/notation_view.py`: Click-to-Seek im Ruler-Bereich — `mousePressEvent()` erkennt Klicks in oberen 24px und ruft `_seek_to_beat()` → `transport.seek()`. Follow-Playhead — `set_playhead_beat()` prueft `_follow_playhead` Flag und scrollt bei 80% auf 20% (Bitwig-Stil). Neue Methoden: `set_transport()`, `_seek_to_beat()`, `set_follow_playhead()`. NotationWidget: "▶ Follow" Toggle-Button (blau wenn aktiv), `_on_follow_toggled()` Handler, `set_transport()` Wiring im Init.

## v0.0.20.534 — Layout Shortcuts + Container Reorder (2026-03-17)

- `pydaw/ui/main_window.py`: QShortcut Ctrl+Alt+1..8 fuer alle 8 Layout-Presets registriert in `_init_screen_layout_manager()`. Shortcut-Hints in `_populate_screen_layout_menu()` Menue-Labels sichtbar.
- `pydaw/ui/fx_device_widgets.py`: ▲/▼ Reorder-Buttons pro Device in `_FxLayerContainerWidget` und `_ChainContainerWidget`. `_move_device()` Methode in beiden Klassen — simpler Array-Swap mit sofortigem `_emit_update()`.

## v0.0.20.533 — CLAP State Save/Load + Browser Icons Fix (2026-03-16)

- `pydaw/audio/clap_host.py` (+200 Zeilen): `CLAP_EXT_STATE`, `clap_istream_t`/`clap_ostream_t`/`clap_plugin_state_t` ctypes-Structs, `_MemoryOutputStream`/`_MemoryInputStream` Memory-Stream-Klassen, `_ClapPlugin.get_state()`/`set_state()`/`has_state()`, State-Extension-Query im Init. `ClapFx._load()` restored State aus `__ext_state_b64`. `ClapFx.get_state_b64()` exportiert State als Base64. `ClapInstrumentEngine` gleiche Integration. `embed_clap_project_state_blobs()` fuer Projekt-Save.
- `pydaw/services/plugin_scanner.py`: `scan_clap()` gibt `is_instrument=bool(d.is_instrument)` an `ExtPlugin` weiter (Linux + macOS). CLAP-Plugins erscheinen jetzt mit 🎹/🔊 Icons im Browser.
- `pydaw/services/project_service.py`: `save_project_as()` und `save_snapshot()` rufen `embed_clap_project_state_blobs()` auf (analog zu VST3).

## v0.0.20.532 — Device-Container Phase 3: Layer-Expand + Device-Management (2026-03-16)

- `pydaw/ui/fx_device_widgets.py`: Komplett ueberarbeitete `_FxLayerContainerWidget` — Klick-Expand pro Layer (▶/▼), Per-Layer Volume-Slider, Enable/Disable/Remove fuer Layers UND Devices, "+ FX → Layer N" Popup-Menue pro Layer, automatisches Expand bei FX-Add. Komplett ueberarbeitete `_ChainContainerWidget` — Device-Liste mit Enable/Disable/Remove Buttons, "+ FX → Chain" Popup-Menue. Neuer `_clear_layout()` Helper fuer rekursive Widget-Bereinigung bei Rebuilds.

## v0.0.20.531 — Device-Container Phase 2: Browser/Menue/DnD-Integration (2026-03-16)

- `pydaw/ui/effects_browser.py`: Container-Eintraege (📦 FX Layer, 📦 Chain) im Audio-FX Tab als erste Eintraege. `_refilter_audio()` zeigt Container mit cyan Farbe. `_add_audio_selected()` erkennt `kind="container"` und routet an Container-Callback oder generischen Add-Pfad.
- `pydaw/ui/device_panel.py`: `_DropForwardHost.contextMenuEvent()` → `_show_chain_context_menu()` mit Container-Sektion und Audio-FX-Sektion. `_forward_drag_event()` akzeptiert `kind="container"`, Drop-Indicator benutzt Audio-FX-Zone. `add_audio_fx_to_track()` hat Container-Routing-Guard (delegiert an `add_fx_layer_to_track()`/`add_chain_container_to_track()`).

## v0.0.20.530 — Device-Container Phase 1: FX Layer + Chain (2026-03-16)

- `pydaw/audio/fx_chain.py` (+220 Zeilen): `FxLayerContainer(AudioFxBase)` — N parallele Layer mit eigenem ChainFx, Summierung mit Normalisierung, per-Layer Volume, Container-Mix ueber RT-Store. `ChainContainerFx(AudioFxBase)` — Serial Sub-Chain als einzelnes Device, Dry/Wet-Mix. `_FxLayer` Dataclass. `_compile_devices()` erkennt `chrono.container.fx_layer` und `chrono.container.chain` vor allen anderen Plugin-Typen. `ensure_track_fx_params()` registriert Container-RT-Keys.
- `pydaw/ui/fx_device_widgets.py` (+180 Zeilen): `_FxLayerContainerWidget` — Layer-Liste, Device-Counts, Mix-Slider, "+Layer"-Button. `_ChainContainerWidget` — Device-Summary, Mix-Slider. `make_audio_fx_widget()` dispatcht Container-Plugin-IDs.
- `pydaw/ui/device_panel.py` (+140 Zeilen): `add_fx_layer_to_track()` — erstellt FX Layer mit N leeren Layers. `add_chain_container_to_track()` — erstellt leere Chain. `add_device_to_container()` — fuegt Device in Container-Layer/Chain ein.
- `pydaw/ui/fx_specs.py` (+10 Zeilen): `get_containers()` Katalog mit FX Layer + Chain.

## v0.0.20.529 — Send MIDI Learn (2026-03-16)

- `pydaw/ui/mixer.py`: "🎛 MIDI Learn" und "🚫 MIDI Learn zurücksetzen" im Send-Knob-Kontextmenue. `_start_send_midi_learn()` setzt `am._midi_learn_knob = knob` mit rotem Border-Feedback. `_reset_send_midi_learn()` entfernt Mapping aus Live-Listeners und Persistent-Registry. `_pydaw_param_id` auf jedem Send-QDial gesetzt fuer CC-Automation-Recording. `_register_send_automation()` re-registriert CC-Mappings aus `_persistent_cc_map` bei Widget-Rebuild. Menue zeigt aktive CC-Nummer wenn gemappt.

## v0.0.20.528 — Send-Automation (2026-03-16)

- `pydaw/ui/mixer.py`: Send-Knobs registrieren sich im AutomationManager (`_register_send_automation()`, param_id `trk:{tid}:send:{fx_id}`). `_on_send_automation_changed()` empfaengt `parameter_changed` Signal und bewegt QDial per `blockSignals()`. Rechtsklick-Menue hat jetzt "📈 Automation im Arranger zeigen" als ersten Eintrag → emittiert `request_show_automation`.
- `pydaw/services/project_service.py`: `apply_automation_value()` erweitert um `send:{fx_track_id}` Branch — updated Send-Amount in `track.sends[]` in-memory, auto-creates Send-Eintrag bei Bedarf.
- `pydaw/services/automation_playback.py`: `_on_playhead()` scannt jetzt dynamisch alle Lane-Keys die mit `send:` beginnen und appliziert interpolierten Wert. Gleicher Legacy-Format-Support (flat list + dict mit points key).

## v0.0.20.527 — Send Pre/Post Toggle + FX-Spuren vor Master (2026-03-16)

- `pydaw/ui/mixer.py`: Rechtsklick-Kontextmenue auf Send-Knobs (`_on_send_context_menu()`): Pre/Post-Fader Toggle (blau/gelb Bitwig-Style), Schnellwahl 50%/100%, Send entfernen. CustomContextMenu-Policy auf QDial gesetzt.
- `pydaw/services/project_service.py`: Neue `toggle_send_pre_fader()` Methode flippt `pre_fader` bool im Send-Dict und emittiert Update. `_rebuild_track_order()` sortiert jetzt FX-Tracks (kind="fx") automatisch ans Ende direkt vor Master — regulaere Spuren behalten ihre relative Reihenfolge.

## v0.0.20.526 — Alle Plugin-Typen: Slider folgt Automation (2026-03-16)

- `pydaw/ui/fx_device_widgets.py`: `_on_automation_param_changed()` + `parameter_changed.connect()` in 3 weiteren Widget-Klassen: Lv2AudioFxWidget (prefix `afx:...:lv2:`), LadspaAudioFxWidget (prefix `afx:...:ladspa:`), ClapAudioFxWidget (prefix `afx:...:clap:`). Jeder Handler prueft Prefix-Match, aktualisiert Slider/Spinbox/Checkbox per QSignalBlocker, pusht Wert in RT-Store. Zusammen mit v525 sind jetzt alle 4 externen Plugin-Formate + interne Plugins komplett abgedeckt.

## v0.0.20.525 — VST2/VST3 Slider folgt Automation-Kurve (2026-03-16)

- `pydaw/ui/fx_device_widgets.py`: `_build()` verbindet `am.parameter_changed.connect(self._on_automation_param_changed)`. Neuer Handler `_on_automation_param_changed(pid, value)` prueft Prefix-Match, aktualisiert Slider/Spinbox/Checkbox per QSignalBlocker, pusht Wert in RT-Store. ~50 Zeilen, nur VST2/VST3 Unified Widget betroffen.

## v0.0.20.524 — Automation-Migration: Device-ID Mapping fuer VST (2026-03-16)

- `pydaw/ui/main_window.py`: `_migrate_automation_for_device_move()` baut jetzt eine `device_id_map` aus Source/Target audio_fx_chain (matched per plugin_id). Key-Replacement: erst track_id, dann alle device_ids aus der Map. Funktioniert fuer alle Formate: VST2/VST3 (`afx:...:device:...`), interne Plugins (`trk:...:bach_orgel:...`), MIDI-recorded (`trk:...:afx:...:device:...`).

## v0.0.20.523 — Automation-Migration Fix: Alle Key-Formate (2026-03-16)

- `pydaw/ui/main_window.py`: `_migrate_automation_for_device_move()` komplett umgeschrieben. Matching per `lane.track_id == source` + `source in pid` statt nur Prefix. Key-Umschreibung per `str.replace(source, target)` statt Prefix-Swap. Volume/Pan Skip per `.endswith()`. Funktioniert fuer UI-drawn, MIDI-recorded und Track-Level Keys.

## v0.0.20.522 — Automation-Copy bei Ctrl+Drag (2026-03-16)

- `pydaw/ui/main_window.py`: `_migrate_automation_for_device_move()` neuer `copy` Parameter. Bei copy=True deepcopy statt pop. 3 Aufrufstellen: Guard aufgespalten — Migration immer (mit copy=is_copy), Removal nur bei Move (not is_copy).

## v0.0.20.521 — Mixer Send-Scroll sichtbar + FX nummeriert (2026-03-16)

- `pydaw/ui/mixer.py`: `ScrollBarAsNeeded` + 6px styled scrollbar. FX-Labels nummeriert (FX1..FXn). Tooltip mit vollem Namen, Nummer, Prozent, Pre/Post.

## v0.0.20.520 — Mixer Send-Knobs Invisible Scroll / Bitwig-Style (2026-03-16)

- `pydaw/ui/mixer.py`: Send-Knobs sitzen jetzt in einer `QScrollArea` (80px fixe Hoehe, `ScrollBarAlwaysOff`, transparent, frameless). Bei mehr als 3 FX-Spuren scrollt man mit dem Mausrad — kein sichtbarer Scrollbalken. Fader/VU behalten immer vollen Platz.

## v0.0.20.519 — Mixer Send-Knobs Compact + Automation folgt Device beim Move (2026-03-16)

- `pydaw/ui/mixer.py`:
  - **Send-Knobs kompakt**: 22px QDial in horizontalen `[Label][Knob]` Reihen statt 32px vertikal gestapelt. Gelb=Post, Blau=Pre (Bitwig). Aktive hell, inaktive gedimmt. QGridLayout durch QVBoxLayout+QHBoxLayout ersetzt.
- `pydaw/ui/main_window.py`:
  - **`_migrate_automation_for_device_move()`**: Neue Methode (~90 Zeilen). Findet Lanes mit `trk:{source}:` Prefix + Device-ID, schreibt `parameter_id` und `track_id` auf Zielspur um, entfernt alte Lanes. Ueberspringt Volume/Pan (gehoeren zur Spur). Safe bei Konflikten (kein Ueberschreiben bestehender Ziel-Lanes).
  - **3 Aufrufstellen**: Instrument-Handler, FX-Handler und Morph-Guard-Handler rufen alle `_migrate_automation_for_device_move()` VOR `_smartdrop_remove_from_source()` auf. Nur bei Move (nicht bei Ctrl+Copy).
- **Schritt C aus dem Dreier-Plan ist damit abgeschlossen.**

## v0.0.20.518 — Send-FX / Return-Tracks / Bitwig-Style (2026-03-16)

- `pydaw/model/project.py`:
  - **`Track.sends`**: Neues Feld `sends: list = field(default_factory=list)`. Jeder Eintrag: `{"target_track_id": "...", "amount": 0.5, "pre_fader": False}`. Persistiert automatisch via dataclass `asdict`/`from_dict`.
  - **`Track.kind`**: Kommentar erweitert um `"fx"` als gueltigem Typ.
- `pydaw/audio/hybrid_engine.py`:
  - **Slots**: `_send_bus_map`, `_fx_track_idxs`, `_send_bus_id_map` als neue RT-sichere Felder.
  - **`set_send_bus_map()`**: Atomarer Swap der Send-Routing-Maps vom Main-Thread.
  - **`_process()`**: FX-Bus-Buffer werden vor dem Render genullt. FX-Tracks im Main-Loop uebersprungen. Pre-Fader-Sends nach FX-Chain/vor Vol/Pan. Post-Fader-Sends nach Vol/Pan. FX-Bus-Processing: eigene FX-Chain + Vol/Pan + Metering → Master. Folgt exakt dem Group-Bus-Muster.
- `pydaw/audio/audio_engine.py`:
  - **`rebuild_fx_maps()`**: Berechnet Send-Bus-Map aus `Track.sends` und `Track.kind=="fx"`. Pusht Map atomar per `hcb.set_send_bus_map()`.
- `pydaw/services/project_service.py`:
  - **`add_send()`**, **`remove_send()`**, **`set_send_amount()`**, **`get_fx_tracks()`**: Neue API fuer Send-Verwaltung.
  - **`add_track()`**: Default-Name fuer `kind="fx"` ist "FX".
- `pydaw/ui/mixer.py`:
  - **Send-Knobs**: `QDial` pro FX-Track im Mixer-Strip (0-100%). Labels mit FX-Track-Name. Dynamisch bei Projekt-Aenderungen aktualisiert. FX/Master-Strips zeigen keine Send-Knobs.
  - **`_rebuild_send_knobs()`**, **`_on_send()`**: Neue Methoden in `_MixerStrip`.
  - **Add-Menu**: "FX-Spur (Return)" als neuer Menuepunkt.
- `pydaw/ui/arranger.py`:
  - **`_build_add_track_menu()`**: "FX-Spur (Return) hinzufuegen" in allen Varianten (nach Spur, in Gruppe, global).
- `pydaw/ui/smartdrop_rules.py`, `pydaw/services/smartdrop_morph_guard.py`:
  - **`_track_kind_label()`**: `"fx"` → `"FX-Spur"`.
  - **`evaluate_plugin_drop_target()`**: `"fx"` als kompatibles Audio-FX-Drop-Ziel.
- `pydaw/ui/main_window.py`:
  - **FX-Handler**: `"fx"` als kompatible Zielspur fuer Audio-FX SmartDrop.
- **9 Dateien geaendert, keine bestehenden Tests oder Pfade gebrochen.**

## v0.0.20.517 — Ctrl+Drag Copy, Auto Track-Type, Belegte Audio-Spuren Morph (2026-03-16)

- `pydaw/ui/main_window.py`:
  - **`_is_ctrl_held()`**: Neuer statischer Helper prueft `QApplication.keyboardModifiers()` auf `ControlModifier`.
  - **`_smartdrop_remove_from_source()`**: Erweitert um Auto Track-Type: nach Instrument-Entfernung von einer Instrument-Spur wird `kind="audio"` gesetzt wenn kein plugin_type mehr vorhanden.
  - **`_on_arranger_smartdrop_instrument_to_track()`**: Prueft jetzt `_is_ctrl_held()` — bei Ctrl wird Device kopiert statt verschoben. Statusmeldung zeigt "kopiert"/"verschoben"/"gesetzt".
  - **`_on_arranger_smartdrop_fx_to_track()`**: Ebenso Ctrl-Copy-Support. Undo-Label und Status passen sich dynamisch an.
  - **`_on_arranger_smartdrop_instrument_morph_guard()`**: Ebenso Ctrl-Copy fuer Cross-Track-Morph auf Audio-Spuren.
- `pydaw/services/smartdrop_morph_guard.py`:
  - **`build_audio_to_instrument_morph_plan()`**: Setzt `can_apply=True` und `apply_mode="audio_to_instrument_with_content"` fuer ALLE Audio-Spuren (nicht nur leere). Belegte Spuren zeigen `requires_confirmation=True` fuer Bestaetigungsdialog.
  - **`apply_audio_to_instrument_morph_plan()`**: Akzeptiert jetzt beide Modi (`minimal_empty_audio` und `audio_to_instrument_with_content`). Die Mutation ist identisch: Before-Snapshot → set_track_kind → After-Snapshot → Undo-Push. Audio-Clips und FX-Kette bleiben komplett erhalten.
  - **`validate_audio_to_instrument_morph_plan()`**: Bewahrt `can_apply=True` fuer beide Modi.
- **Getestet**: Leere Audio-Spur (no dialog), Audio+Clips (dialog→morph→clips erhalten), Audio+FX (dialog→morph→FX erhalten), Undo/Redo korrekt, Instrument-Spur bleibt blockiert.

## v0.0.20.516 — Cross-Track Device Drag&Drop / Bitwig-Style (2026-03-16)

- `pydaw/ui/device_panel.py`:
  - **`_DeviceCard.__init__()`**: 3 neue Parameter: `plugin_type_id`, `plugin_name`, `source_track_id` fuer Cross-Track-Drag-Metadaten. Abwaertskompatibel (alle defaults="").
  - **`_DeviceCard.mouseMoveEvent()`**: Drag-Payload erweitert um `plugin_id`, `name`, `source_track_id`. Drag-Action erlaubt jetzt `MoveAction | CopyAction` statt nur `MoveAction`.
  - **Note-FX Card Creation**: Setzt jetzt `plugin_type_id`, `plugin_name`, `source_track_id` aus dem Device-Dict.
  - **Audio-FX Card Creation**: Ebenso erweitert.
  - **SF2-Instrument-Card**: Bekommt `fx_kind="instrument"`, `device_id=tid`, `plugin_type_id="sf2"`, `source_track_id=tid` — damit erstmals draggbar!
  - **Plugin-Instrument-Card**: Bekommt `fx_kind="instrument"`, `device_id=tid`, `plugin_type_id=plugin_id`, `source_track_id=tid` — erstmals draggbar!
  - Internes Reorder innerhalb derselben Chain bleibt komplett unveraendert (selber `_INTERNAL_MIME` Pfad).
- `pydaw/ui/main_window.py`:
  - **`_smartdrop_remove_from_source()`**: Neue zentrale Helper-Methode. Entfernt nach erfolgreichem Cross-Track-Move das Device von der Quellspur. Kennt instrument, audio_fx, note_fx. Safe: bei Fehler bleibt das Device auf beiden Spuren.
  - **`_on_arranger_smartdrop_instrument_to_track()`**: Erkennt jetzt `source_track_id` im Payload. Bei Cross-Track: Insert auf Ziel + `_smartdrop_remove_from_source()` auf Quellspur. Undo-Label angepasst.
  - **`_on_arranger_smartdrop_fx_to_track()`**: Ebenso erweitert fuer Note-FX und Audio-FX Cross-Track-Moves.
  - **`_on_arranger_smartdrop_instrument_morph_guard()`**: Bei Cross-Track-Morph (Instrument auf leere Audio-Spur) wird nach erfolgreichem Morph + Insert auch `_smartdrop_remove_from_source()` aufgerufen.
- Alle bestehenden Pfade (Browser-Drop, internes Device-Reorder, SmartDrop-Guard fuer belegte Spuren) bleiben exakt unveraendert.
- **BITWIG-PARITÄT erreicht fuer:** Device-Move zwischen Tracks per Drag&Drop (Instrument, Audio-FX, Note-FX).

## v0.0.20.515 — SmartDrop: Erster ECHTER atomarer Live-Pfad fuer leere Audio-Spur (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`:
  - **`_build_shadow_commit_rehearsal()`**: Neue Funktion simuliert den kompletten Undo-Zyklus read-only: deepcopy des Projekts, track.kind-Aenderung auf der Kopie, `ProjectSnapshotEditCommand` mit do()/undo() gegen lokalen Recorder, Round-Trip-Verifikation. Beruehrt das Live-Projekt nie.
  - **`apply_audio_to_instrument_morph_plan()`**: Fuehrt jetzt bei `apply_mode="minimal_empty_audio"` + `can_apply=True` die ECHTE atomare Mutation durch: Before-Snapshot → `set_track_kind("instrument")` → After-Snapshot → Undo-Push. Bei Fehlern sofortiger Rollback per Snapshot-Restore.
  - **`build_audio_to_instrument_morph_plan()`**: Setzt `can_apply=True` und `apply_mode="minimal_empty_audio"` wenn: track_kind==audio, keine Clips, keine FX, keine Note-FX, Shadow-Rehearsal bestanden.
  - **`validate_audio_to_instrument_morph_plan()`**: Bewahrt `can_apply=True` fuer den Minimalfall (vorher wurde can_apply immer auf False gesetzt).
  - **Apply-Readiness**: 3 neue dynamische Checks: `shadow_commit_rehearsal`, `routing_atomic`, `undo_commit` kippen auf `ready` wenn der Minimalfall vorliegt.
- `pydaw/ui/main_window.py`:
  - **`_on_arranger_smartdrop_instrument_morph_guard()`**: Fuehrt nach erfolgreichem Morph (`ok=True, applied=True`) die Instrument-Einfuegung via `device_panel.add_instrument_to_track()` durch, selektiert die Spur, oeffnet das DevicePanel und emittiert UI-Refresh-Signale.
- Guard blockiert weiterhin ALLE nicht-leeren Audio-Spuren (Clips/FX/Note-FX vorhanden → can_apply=False).
- Undo/Redo funktioniert: Die gesamte Aenderung wird als ein einziger Undo-Punkt gekapselt (Ctrl+Z stellt den Audio-Spur-Zustand komplett wieder her).
- **ERSTER ECHTER MUTIERENDER SMARTDROP-PFAD in der gesamten Projektgeschichte!**

## v0.0.20.514 — SmartDrop: read-only Dry-Command-Executor / do()-undo()-Simulations-Harness (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter der bestehenden read-only Preview-Command-Konstruktion haengt jetzt ein eigener `runtime_snapshot_dry_command_executor` / `runtime_snapshot_dry_command_executor_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an eine echte `do()`-/`undo()`-Simulation mit Recorder-Callback, Callback-Trace und Payload-Wiederverwendung.
- `pydaw/services/project_service.py`: Der `ProjectService` exponiert jetzt den sicheren read-only Owner-Deskriptor `preview_audio_to_instrument_morph_dry_command_executor`, der `ProjectSnapshotEditCommand.do()/undo()` nur gegen einen lokalen In-Memory-Recorder laufen laesst und weder Live-Projekt noch Undo-Stack anfasst.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only Dry-Command-Executor / do()-undo()-Simulations-Harness** inklusive do/undo-Zaehlern, Callback-Trace, Callback-Digests und einzelnen Simulations-Schritten sichtbar an; Preview-/Statuslabel und Apply-Readiness fuehren die neue Schicht ebenfalls mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** echter Commit, **kein** Undo-Push, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.513 — SmartDrop: read-only Preview-Command-Konstruktion (`ProjectSnapshotEditCommand(before=..., after=..., ...)`) (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter der vorhandenen read-only Before-/After-Snapshot-Command-Factory haengt jetzt ein eigener `runtime_snapshot_preview_command_construction` / `runtime_snapshot_preview_command_construction_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an die echte Constructor-Form von `ProjectSnapshotEditCommand`, die Callback-Bindung sowie die Feldliste der Dataclass.
- `pydaw/services/project_service.py`: Der `ProjectService` exponiert jetzt den sicheren read-only Owner-Deskriptor `preview_audio_to_instrument_morph_preview_snapshot_command`, der `ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)` nur in-memory konstruiert, aber weder `do()` noch `undo()` ausfuehrt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only Preview-Command-Konstruktion** inklusive Constructor-Form, Callback, Feldliste, Payload-Digests und einzelnen Preview-Schritten sichtbar an; Preview-/Statuslabel und Apply-Readiness fuehren die neue Schicht ebenfalls mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Undo-Push, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.512 — SmartDrop: read-only Before-/After-Snapshot-Command-Factory / materialisierte Payloads (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter der vorhandenen read-only `ProjectSnapshotEditCommand`-/Undo-Huelle haengt jetzt ein eigener `runtime_snapshot_command_factory_payloads` / `runtime_snapshot_command_factory_payload_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an eine explizite Before-/After-Snapshot-Factory, materialisierte Payload-Metadaten, Restore-Callback und Payload-Paritaet.
- `pydaw/services/project_service.py`: Der `ProjectService` exponiert jetzt den sicheren read-only Owner-Deskriptor `preview_audio_to_instrument_morph_before_after_snapshot_command_factory`, der Before-/After-Snapshot-Payloads nur in-memory materialisiert und daraus Digests, Byte-Groessen und Top-Level-Key-Metadaten ableitet.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only Before-/After-Snapshot-Command-Factory** inklusive Payload-Zusammenfassung, Digests, Byte-Groessen, Delta-Kind und einzelnen Factory-Schritten sichtbar an; Preview-/Statuslabel und Apply-Readiness fuehren die neue Schicht ebenfalls mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Routing-Umbau, **kein** Undo-Push und **keine** Projektmutation.

## v0.0.20.511 — SmartDrop: read-only ProjectSnapshotEditCommand / Undo-Huelle (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter Mutation-Gate und Transaction-Capsule haengt jetzt ein eigener `runtime_snapshot_command_undo_shell` / `runtime_snapshot_command_undo_shell_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an `ProjectSnapshotEditCommand`, eine explizite Command-/Undo-Huelle, Projekt-Snapshot-Capture/Restore sowie Undo-Stack-Push.
- `pydaw/services/project_service.py`: Der `ProjectService` exponiert jetzt sichere read-only Owner-Deskriptoren fuer `ProjectSnapshotEditCommand` und die spaetere Command-/Undo-Huelle (`preview_audio_to_instrument_morph_project_snapshot_edit_command`, `preview_audio_to_instrument_morph_command_undo_shell`).
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only ProjectSnapshotEditCommand / Undo-Huelle** inklusive Huelle-Sequenz und Einzelstatus sichtbar an; Preview-/Statuslabel und Apply-Readiness fuehren die neue Schicht ebenfalls mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.510 — SmartDrop: read-only Mutation-Gate / Transaction-Capsule (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter den read-only atomaren Entry-Points haengt jetzt ein eigener `runtime_snapshot_mutation_gate_capsule` / `runtime_snapshot_mutation_gate_capsule_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an explizites Mutation-Gate, Transaction-Capsule, Projekt-Snapshot-Capture/Restore sowie Kapsel-Commit-/Rollback-Stubs.
- `pydaw/services/project_service.py`: Der `ProjectService` exponiert jetzt sichere read-only Owner-Deskriptoren fuer Mutation-Gate und Transaction-Capsule (`preview_audio_to_instrument_morph_mutation_gate`, `preview_audio_to_instrument_morph_transaction_capsule`, `preview_audio_to_instrument_morph_capsule_commit`, `preview_audio_to_instrument_morph_capsule_rollback`).
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only Mutation-Gate / Transaction-Capsule** inklusive Kapsel-Sequenz und Einzelstatus sichtbar an; Preview-/Statuslabel und Apply-Readiness fuehren die neue Schicht ebenfalls mit.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.509 — SmartDrop: read-only atomare Commit-/Undo-/Routing-Entry-Points (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter dem read-only Pre-Commit-Vertrag haengt jetzt ein eigener `runtime_snapshot_atomic_entrypoints` / `runtime_snapshot_atomic_entrypoints_summary`-Block. Er koppelt den spaeteren Minimalfall der leeren Audio-Spur read-only an reale Owner-/Service-Entry-Points (`preview_audio_to_instrument_morph`, `validate_audio_to_instrument_morph`, `apply_audio_to_instrument_morph`, `set_track_kind`, `undo_stack.push`) sowie an Routing-/Undo-/Track-Kind-Snapshot-Entry-Points.
- `pydaw/services/project_service.py`: Die Preview-/Validate-Pfade uebergeben jetzt den echten `ProjectService` als Runtime-Owner in den Guard-Builder, sodass die neue Entry-Point-Kopplung im Hauptpfad wirklich an realen Service-Methoden aufgeloest wird.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only atomare Commit-/Undo-/Routing-Entry-Points** inklusive Owner, Dispatch-Sequenz und einzelnen Entry-Point-Statuszeilen sichtbar an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.508 — SmartDrop: Leere Audio-Spur read-only Pre-Commit-Vertrag (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter der vorhandenen Minimalfall-Vorqualifizierung haengt jetzt ein eigener read-only `runtime_snapshot_precommit_contract` / `runtime_snapshot_precommit_contract_summary`. Der neue Vertrag beschreibt Undo-, Routing-, Track-Kind- und Instrument-Commit-Sequenz fuer die spaetere leere Audio-Spur, bleibt aber vollstaendig preview-only.
- `pydaw/services/smartdrop_morph_guard.py`: Die Apply-Readiness fuehrt jetzt einen eigenen Check **Leere Audio-Spur: read-only Pre-Commit-Vertrag vorbereitet** und trennt damit die neue Vorschau-Ebene sauber von echter Routing-/Undo-Mutation.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Leere Audio-Spur: read-only Pre-Commit-Vertrag** inklusive Commit-/Rollback-Sequenz, Mutation-Gate und Preview-Phasen sichtbar an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Commit, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.507 — SmartDrop: Erster spaeterer Minimalfall (leere Audio-Spur) read-only vorqualifiziert (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard fuehrt jetzt `first_minimal_case_report` / `first_minimal_case_summary` ein. Damit wird eine leere Audio-Spur erstmals explizit als spaeterer erster echter Freigabefall read-only erkannt, ohne Commit, Routing-Umbau oder Projektmutation.
- `pydaw/services/smartdrop_morph_guard.py`: Preview-Label, Status-Text und Apply-Preview unterscheiden jetzt gezielt zwischen leerer Audio-Spur (Minimalfall vorbereitet) und Audio-Spur mit Clips/FX (weiter klar blockiert).
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt einen eigenen Block **Erster spaeterer Minimalfall (leere Audio-Spur)** mit Scope, offenen Punkten sowie Bundle-/Apply-Runner-/Dry-Run-Vorqualifizierung.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau, **kein** Commit und **keine** Projektmutation.

## v0.0.20.506 — SmartDrop: Read-only Snapshot-Transaktions-Dispatch / Apply-Runner (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Hinter den vorhandenen Runtime-State-Registry-Backend-Adaptern haengt jetzt ein eigener, read-only `runtime_snapshot_apply_runner` / `runtime_snapshot_apply_runner_summary`. Der neue Runner dispatcht Snapshot-Adapter, Backend-Store-Adapter und Registry-Slot-Backends als eigene Preview-Phase hinter dem Snapshot-Bundle.
- `pydaw/services/smartdrop_morph_guard.py`: Die Apply-Readiness fuehrt jetzt einen separaten Check fuer den neuen Snapshot-Transaktions-Dispatch / Apply-Runner. Zusaetzlich gibt es eigene Dispatch-Summaries fuer `backend_store_adapter_calls` und `registry_slot_backend_calls`.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt den neuen Block **Read-only Snapshot-Transaktions-Dispatch / Apply-Runner** inklusive Apply-/Restore-/Rollback-Sequenz, Dispatch-Summaries und Beispiel-Phasen sichtbar an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau, **kein** Commit und **keine** Projektmutation.

## v0.0.20.505 — SmartDrop: Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die vorhandenen Runtime-State-Registry-Backends werden jetzt an konkrete, read-only `runtime_snapshot_state_registry_backend_adapters` / `runtime_snapshot_state_registry_backend_adapter_summary` gekoppelt. Jeder Adapter-Eintrag traegt stabilen `adapter_key`, `backend_store_adapter_key` und `registry_slot_backend_key`.
- Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_registry_backend_adapter_calls` / `state_registry_backend_adapter_summary` und nutzt die neuen `capture_adapter_preview()` / `restore_adapter_preview()` / `rollback_adapter_preview()`-Pfade direkt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt die neue Ebene **Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter / Registry-Slot-Backends** sichtbar an und fuehrt die neuen Adapter-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.504 — SmartDrop: Runtime-State-Registry-Backends / Handle-Register / Registry-Slots (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden Runtime-State-Registries werden jetzt an konkrete, read-only `runtime_snapshot_state_registry_backends` / `runtime_snapshot_state_registry_backend_summary` gekoppelt. Jeder Backend-Eintrag traegt `backend_key`, `backend_class`, `handle_register_key`, `handle_register_class`, `registry_slot_key` und `registry_slot_class`.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_registry_backend_calls` / `state_registry_backend_summary` und nutzt die neuen `capture_backend_preview()` / `restore_backend_preview()` / `rollback_backend_preview()`-Pfade direkt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt sichtbar an und fuehrt die neuen Backend-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.502 — SmartDrop: Runtime-State-Stores / Capture-Handles (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die vorhandenen Runtime-State-Slots werden jetzt an konkrete, read-only `runtime_snapshot_state_stores` / `runtime_snapshot_state_store_summary` gekoppelt. Jeder Store traegt eigenen `store_key`, Store-Klasse sowie `capture_handle_key` / `restore_handle_key` / `rollback_handle_key`.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_store_calls` / `state_store_summary` und nutzt die neuen `capture_store_preview()` / `restore_store_preview()` / `rollback_store_preview()`-Pfade direkt.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt jetzt sowohl die bisherige **Runtime-State-Slot**-Ebene als auch die neue **Runtime-State-Stores / Capture-Handles**-Ebene sichtbar an; der Dry-Run-Block fuehrt die neuen Store-Dispatch-Infos ebenfalls mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.500 — SmartDrop: Separate Runtime-State-Halter (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden separaten Runtime-State-Container werden jetzt an konkrete, read-only `runtime_snapshot_state_holders` / `runtime_snapshot_state_holder_summary` gekoppelt. Jeder Halter traegt eigenen `holder_key`, Holder-Klasse, Holder-Payload und Holder-Digest.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_holder_calls` / `state_holder_summary` und ruft `capture_holder_preview()` / `restore_holder_preview()` / `rollback_holder_preview()` ueber die neuen Halter auf.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt als **Separate Runtime-State-Halter** an und fuehrt die neuen Holder-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.499 — SmartDrop: Separate Runtime-State-Container (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Die bestehenden Runtime-Zustandstraeger werden jetzt an konkrete, read-only `runtime_snapshot_state_containers` / `runtime_snapshot_state_container_summary` gekoppelt. Jeder Container traegt eigenen `container_key`, Container-Klasse, Payload-Digest und separate Capture-/Restore-/Rollback-Container-Previews.
- `pydaw/services/smartdrop_morph_guard.py`: Der read-only Dry-Run fuehrt jetzt zusaetzlich `state_container_calls` / `state_container_summary` und nutzt die Container-Previews direkt, weiterhin ohne Commit oder Projektmutation.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Dialog zeigt die neue Ebene jetzt als **Separate Runtime-State-Container** an und fuehrt die neuen Container-Dispatch-Infos im Dry-Run-Block mit auf.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.497 — SmartDrop: Runtime-Stubs / Klassenkopplung (2026-03-16)

- Die vorbereiteten Runtime-Snapshot-Objektbindungen werden jetzt an konkrete read-only Runtime-Stub-Klassen gekoppelt (`runtime_snapshot_stubs`, `runtime_snapshot_stub_summary`).
- Der Safe-Runner instanziiert diese Stub-Klassen und laesst Capture-/Restore-/Rollback-Previews ueber `capture_preview()` / `restore_preview()` / `rollback_preview()` laufen.
- `pydaw/ui/main_window.py` zeigt die neue Ebene im zentralen Morphing-Guard-Dialog sichtbar an.
- Safety first: weiterhin kein echtes Audio->Instrument-Morphing, kein Routing-Umbau und keine Projektmutation.

## v0.0.20.494 — SmartDrop: Morphing-Guard mit Snapshot-Bundle / Transaktions-Container (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `runtime_snapshot_bundle` und `runtime_snapshot_bundle_summary`; die vorhandenen Runtime-Snapshot-Objektbindungen werden damit in einen stabilen, read-only Transaktions-Container mit `bundle_key`, `commit_stub`, `rollback_stub`, Capture-/Restore-Methoden und Rollback-Slots zusammengefuehrt.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt als **Snapshot-Bundle / Transaktions-Container** an und meldet die neue Bundle-Ebene bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.493 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Objekt-Bindung (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `runtime_snapshot_objects` und `runtime_snapshot_object_summary`; die bisherigen Snapshot-Instanzen werden damit an konkrete, read-only Snapshot-Objektbindungen mit `snapshot_object_key`, Objektklasse sowie Capture-/Restore-Methoden gekoppelt.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt als **Runtime-Snapshot-Objekt-Bindung** an und meldet die neue Objekt-Ebene bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.492 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Instanz-Vorschau (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `runtime_snapshot_instances` und `runtime_snapshot_instance_summary`; die vorhandenen Capture-Objekte werden damit in konkrete, read-only Snapshot-Instanzen mit stabilem `snapshot_instance_key`, Payload und `payload_digest` materialisiert.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt als **Runtime-Snapshot-Instanz-Vorschau** an und meldet die neue Instanz-Ebene bereits im Infotext.
- `pydaw/services/project_service.py`: Kleiner Safety-Hotfix — die zentralen Guard-Funktionen werden jetzt explizit importiert, damit Preview/Validate/Apply nicht an fehlenden Symbolen scheitern.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation.

## v0.0.20.491 — SmartDrop: Morphing-Guard mit Runtime-Capture-Objekt-Vorschau (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `runtime_snapshot_captures` und `runtime_snapshot_capture_summary`; die bisherigen Runtime-Handles werden damit in konkrete, read-only Capture-Objekt-Deskriptoren mit Payload-Vorschau ueberfuehrt.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt als **Runtime-Capture-Objekt-Vorschau** an und meldet die vorbereitete Capture-Ebene bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Snapshot-/Capture-Vorschau.

## v0.0.20.489 — SmartDrop: Morphing-Guard mit Runtime-Snapshot-Vorschau (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `runtime_snapshot_preview` und `runtime_snapshot_summary`; die bestehenden Snapshot-Referenzen werden erstmals direkt gegen den aktuellen Track-/Clip-/Chain-Zustand aufgeloest, weiterhin komplett read-only.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt zusaetzlich als **Aktuelle Runtime-Snapshot-Vorschau** an und meldet die aktuelle Aufloesbarkeit bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Laufzeit-Vorschau.

## v0.0.20.488 — SmartDrop: Morphing-Guard mit Apply-Readiness-Checkliste (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `readiness_checks` und `readiness_summary`, damit die spaetere echte Apply-Phase auf einer zentralen Sicherheitsmatrix fuer Snapshot-/Routing-/Undo-Bereitschaft aufbauen kann.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt zusaetzlich als **Apply-Readiness-Checkliste** an und meldet die zusammengefasste Bereitschaft bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Vorschau.

## v0.0.20.487 — SmartDrop: Morphing-Guard mit Snapshot-Referenzvorschau (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `snapshot_refs`, `snapshot_ref_map` und `snapshot_ref_summary`; die Referenzen werden deterministisch aus `transaction_key` und den bereits geplanten Snapshot-Namen aufgebaut.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt zusaetzlich als **Geplante Snapshot-Referenzen** an und meldet die vorbereitete Referenzanzahl bereits im Infotext.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Vorschau.

## v0.0.20.486 — SmartDrop: Morphing-Guard mit atomarer Transaktionsvorschau (2026-03-15)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `required_snapshots`, `transaction_steps`, `transaction_key` und `transaction_summary`, damit die spaetere echte Apply-Phase auf einer klaren atomaren Vorschau aufbauen kann.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt zusaetzlich als **Noetige Snapshots** und **Geplanter atomarer Ablauf** an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Vorschau.

## v0.0.20.485 — SmartDrop: Guard-Dialog mit Risiko-/Rueckbau-Zusammenfassung (2026-03-15)

- `pydaw/services/smartdrop_morph_guard.py`: Der Morphing-Guard-Plan liefert jetzt zusaetzlich `impact_summary`, `rollback_lines` und `future_apply_steps`, damit die spaetere echte Apply-Phase bereits auf einer klareren Sicherheitsstruktur aufbauen kann.
- `pydaw/ui/main_window.py`: Der bestehende Guard-Dialog zeigt diese Struktur jetzt getrennt als **Risiken / Blocker**, **Rueckbau vor echter Freigabe** und **Spaetere atomare Apply-Phase** an.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation; der Schritt bleibt reine Sicherheitsvorschau.

## v0.0.20.484 — SmartDrop: Guard-Dialog auf spätere Apply-Phase vorbereitet (2026-03-15)

- `pydaw/ui/main_window.py`: Der Morphing-Guard-Dialog liefert jetzt ein kleines Ergebnisobjekt (`shown / accepted / can_apply / requires_confirmation`) statt nur `True/False`.
- `pydaw/ui/main_window.py`: Dieselbe Dialog-Stelle ist bereits fuer die spaetere echte Bestaetigung vorbereitet; falls `can_apply` spaeter freigeschaltet wird, kann der Dialog schon jetzt zwischen `Morphing bestaetigen` und `Abbrechen` unterscheiden.
- `pydaw/ui/main_window.py`: Der zentrale Guard-Handler respektiert diese spaetere Struktur bereits, bleibt aktuell aber bewusst nicht-mutierend, weil `can_apply` weiterhin `False` bleibt.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau, **keine** Projektmutation.

## v0.0.20.483 — SmartDrop: Guard-Dialog aus Morphing-Plan (2026-03-15)

- `pydaw/ui/main_window.py`: Geblockte `Instrument -> Audio-Spur`-Drops oeffnen jetzt optional einen read-only Sicherheitsdialog, wenn der Morphing-Guard `requires_confirmation` meldet.
- `pydaw/ui/main_window.py`: Der Dialog zeigt direkt Daten aus dem bestehenden Guard-Plan (`blocked_message`, `summary`, `blocked_reasons`) und bleibt damit konsistent mit Preview/Validate/Apply.
- Safety first: weiterhin **kein** echtes Audio->Instrument-Morphing, **kein** Routing-Umbau, **keine** Projektmutation; der Dialog ist nur eine Sicherheitsvorschau.

## v0.0.20.482 — SmartDrop: Morphing-Guard-Command vorbereitet (2026-03-15)

- `pydaw/services/smartdrop_morph_guard.py`: Neues zentrales Guard-Modul für künftiges **Audio→Instrument-Morphing** mit gemeinsamem `preview / validate / apply`-Schema; in dieser Phase bewusst noch **nicht mutierend**.
- `pydaw/services/project_service.py`: Neue Wrapper `preview_audio_to_instrument_morph(...)`, `validate_audio_to_instrument_morph(...)` und `apply_audio_to_instrument_morph(...)` bündeln den Guard jetzt service-seitig für spätere echte Undo-/Routing-Schritte.
- `pydaw/ui/main_window.py`: MainWindow besitzt jetzt einen eigenen Guard-Einstiegspunkt für geblockte Instrument→Audio-Drops und ruft dafür bereits denselben zukünftigen Apply-Hook auf — aktuell absichtlich nur als blockierte Stub-Anwendung.
- `pydaw/ui/arranger_canvas.py` + `pydaw/ui/arranger.py`: Geblockte Instrument→Audio-Drops werden nicht mehr nur lokal kommentiert, sondern an den neuen zentralen Morphing-Guard weitergereicht.
- `pydaw/ui/smartdrop_rules.py`: Die Audio-Spur-Preview nutzt jetzt denselben Guard-Plan wie ProjectService/MainWindow, damit Summary/Blocked-Message nicht mehr doppelt auseinanderlaufen.
- Safety first: weiterhin **kein** echtes Audio→Instrument-Morphing, **kein** Routing-Umbau, **keine** Projektmutation in der neuen Guard-Apply-Stelle.


## v0.0.20.481 — SmartDrop: Zentrale Morphing-Vorprüfung + Block-Hinweis (2026-03-15)

- `pydaw/ui/smartdrop_rules.py`: Neues zentrales Regelmodul bewertet Plugin-Drop-Ziele gemeinsam für ArrangerCanvas und linke TrackList; inklusive Audio-/MIDI-Clip-Zählung und FX-Ketten-Summary pro Zielspur.
- `pydaw/ui/arranger_canvas.py`: Canvas nutzt jetzt dieselbe Zielbewertung wie die TrackList und zeigt bei Instrument→Audio-Spur eine aussagekräftigere Preview; geblockte Ziele melden beim echten Drop aktiv den Sperrgrund über die Statusleiste.
- `pydaw/ui/arranger.py`: Die linke TrackList verwendet dieselbe zentrale Zielbewertung und meldet geblockte SmartDrop-Versuche jetzt ebenfalls explizit statt still zu ignorieren.
- Safety first: weiterhin **kein** echtes Audio→Instrument-Morphing, **kein** Routing-Umbau und **keine** Projektmutation auf bewusst gesperrten Zielen.

## v0.0.20.480 — SmartDrop: Kompatible FX-Ziele (2026-03-15)

- `pydaw/ui/arranger.py`: Die linke Arranger-TrackList kennt jetzt echte kompatible FX-Ziele und emittiert bei `Note-FX`/`Audio-FX` auf passenden bestehenden Spuren einen zentralen SmartDrop-Request statt nur Preview.
- `pydaw/ui/arranger_canvas.py`: Der ArrangerCanvas behandelt kompatible bestehende FX-Ziele jetzt ebenfalls als echte Drops; `Note-FX` werden nur auf Instrument-Spuren, `Audio-FX` nur auf kompatiblen bestehenden Spuren angenommen.
- `pydaw/ui/main_window.py`: Neues zentrales Handling für FX-SmartDrop nutzt die vorhandenen sicheren DevicePanel-Pfade (`add_note_fx_to_track` / `add_audio_fx_to_track`), selektiert danach die Zielspur und fokussiert das DevicePanel.
- Safety first: weiterhin **kein** Audio→MIDI-Morphing, **kein** Routing-Umbau und **keine** Erweiterung auf inkompatible Ziele.

## v0.0.20.479 — SmartDrop auf bestehende Instrument-Spur (2026-03-15)

- `pydaw/ui/arranger_canvas.py`: Instrument-Drops auf **bestehende Instrument-Spuren** werden jetzt im Canvas wirklich angenommen; Audio-Spuren bleiben bewusst Preview-only.
- `pydaw/ui/arranger.py`: Die linke Arranger-TrackList akzeptiert denselben echten Instrument-Drop ebenfalls und meldet ihn zentral weiter.
- `pydaw/ui/main_window.py`: MainWindow führt den SmartDrop auf bestehende Instrument-Spuren über die vorhandenen DevicePanel-Pfade aus und selektiert danach die Zielspur.
- UX-Härtung: Tooltip-/Status-Texte unterscheiden jetzt sauber zwischen **echter Aktion** (`Instrument → Einfügen auf ...`) und reiner Preview.
- Safety first: weiterhin **kein** Audio→MIDI-Morphing, **kein** SmartDrop auf Audio-Spuren und **kein** Routing-Umbau vorhandener Tracks.

## v0.0.20.478 — SmartDrop: Neue Instrument-Spur aus Leerraum-Drop (2026-03-15)

- `pydaw/ui/arranger_canvas.py`: Plugin-Drops im freien Arranger-Bereich **unterhalb der letzten Spur** werden jetzt erstmals wirklich ausgewertet — aber nur für **Instrumente**.
- `pydaw/ui/arranger_canvas.py`: Der Canvas emittiert dafür einen kleinen zentralen SmartDrop-Request statt selbst Tracks/Devices direkt umzubauen; bestehende Track-Drops bleiben damit getrennt und risikoarm.
- `pydaw/ui/main_window.py`: MainWindow legt bei diesem SmartDrop eine **neue Instrument-Spur** an, benennt sie nach dem Plugin und fügt das Instrument über die vorhandenen DevicePanel-Pfade ein.
- Safety first: weiterhin **kein** Spur-Morphing bestehender Tracks, **kein** echter SmartDrop auf bestehende Spuren, **kein** Routing-Umbau vorhandener Audio-Spuren.

## v0.0.20.477 — TrackList Preview-Hinweis Parität (2026-03-15)

- `pydaw/ui/arranger.py`: Die Arranger-TrackList zeigt beim Plugin-Hover jetzt denselben reinen Preview-Hinweis wie der ArrangerCanvas (`… · Nur Preview — SmartDrop folgt später`).
- `pydaw/ui/arranger.py`: Der Hinweis erscheint links ebenfalls als best-effort Tooltip in Cursor-Nähe und wird zusätzlich über die bestehende `status_message`-Leiste gemeldet.
- `pydaw/ui/arranger.py`: Beim Verlassen des Preview-Modus werden Tooltip/Hint sauber entfernt und der normale Standard-Tooltip der TrackList wiederhergestellt.
- Safety first: weiterhin **kein** echter Plugin-Drop in der TrackList, **keine** neue Spur, **kein** Spur-Morphing, **kein** Routing-/Undo-/Projektformat-Umbau.

## v0.0.20.476 — Arranger Preview-Hinweis am Cursor / in Statusleiste (2026-03-15)

- `pydaw/ui/arranger_canvas.py`: Plugin-Hover-Preview zeigt jetzt zusätzlich einen klaren Hinweis `… · Nur Preview — SmartDrop folgt später` an.
- `pydaw/ui/arranger_canvas.py`: Der Hinweis erscheint als best-effort Tooltip in Cursor-Nähe und wird parallel über die bestehende `status_message`-Leiste gemeldet.
- `pydaw/ui/arranger_canvas.py`: Beim Verlassen des Preview-Modus werden Tooltip/Hint sauber wieder entfernt.
- Safety first: weiterhin **kein** echter Plugin-Drop im Arranger, **keine** neue Spur, **kein** Spur-Morphing, **kein** Routing-/Undo-/Projektformat-Umbau.

## v0.0.20.475 — Arranger Leerraum-Preview unter letzter Spur (2026-03-15)

- `pydaw/ui/arranger_canvas.py`: Instrument-Drags zeigen jetzt im freien Bereich **unterhalb der letzten Spur** eine rein visuelle cyanfarbene Linie/Badge wie `Neue Instrument-Spur: …`.
- `pydaw/ui/arranger_canvas.py`: Track-Lane-Preview und Leerraum-Preview laufen jetzt über einen zentralen Parse/Clear/Update-Pfad (`_parse_plugin_drag_info`, `_update_plugin_drag_preview`, `_clear_plugin_drag_preview`).
- Safety first: weiterhin **kein** echter Plugin-Drop im Arranger, **keine** neue Spur, **kein** Spur-Morphing, **kein** Routing-/Undo-/Projektformat-Umbau.
- Kleiner Härtungseffekt: der ArrangerCanvas enthält keinen fehlerhaften Inline-Preview-Block im Konstruktor mehr; der Preview-Code lebt jetzt nur noch im Paint-/Helper-Pfad.

## v0.0.20.474 — Arranger/TrackList Plugin Hover Preview (2026-03-15)

- `pydaw/ui/arranger.py`: Die Arranger-TrackList wertet Plugin-Drag-Payloads jetzt **rein visuell** aus und markiert die Zielspur mit einem cyanfarbenen Hover-Rahmen.
- `pydaw/ui/arranger_canvas.py`: Der Arranger zeichnet jetzt beim Plugin-Hover ein cyanfarbenes Spur-Overlay mit Rollenhinweis für **Instrument**, **Effekt** oder **Note-FX**.
- Instrument-Hover auf einer Audio-Spur zeigt bewusst nur eine **Preview** („Morphing folgt später“) — also noch **kein** Spur-Umbau, **kein** Routing-Umbau und **kein** neues Drop-Verhalten.
- Risikoarm: bestehende Clip-/Datei-/Cross-Project-Drops bleiben unberührt; Plugin-Drops auf Track/Arranger werden in diesem Schritt weiterhin nur visuell behandelt.

## v0.0.20.473 — Plugins Browser Scope-Badge + Rollen-Metadaten (2026-03-15)

- `pydaw/ui/plugins_browser.py`: Plugins-Browser zeigt jetzt ebenfalls eine **trackbezogene Scope-Badge** im Header, analog zu Instruments / Effects / Favorites / Recents.
- `pydaw/ui/plugins_browser.py`: Externe Plugin-Payloads für **Add** und **Drag&Drop** tragen jetzt zusätzlich die erkannte Rolle **Instrument vs. Effekt** mit (`device_kind`, `__ext_is_instrument`).
- `pydaw/ui/device_browser.py`: Scope-Badge-Refresh berücksichtigt jetzt auch den Plugins-Tab.
- Risikoarm: bestehender Insert-/Drop-Pfad bleibt unverändert; kein Routing-Umbau, kein DSP-Eingriff, kein neues Projektformat.

## v0.0.20.472 — VST Header Main-Bus Hint (2026-03-15)

- `pydaw/ui/fx_device_widgets.py`: `Vst3AudioFxWidget` zeigt jetzt direkt unter dem Status eine kleine Main-Bus-Hinweiszeile wie `Main-Bus: 1→1`, `1→2` oder `2→2`.
- `pydaw/ui/fx_device_widgets.py`: Die Anzeige liest den Bus bevorzugt aus der bereits laufenden Runtime-Host-Instanz (FX oder Instrument) und bleibt dadurch rein UI-seitig — kein zweiter Plugin-Load, kein neuer Rebuild-Pfad.
- `pydaw/audio/vst3_host.py`: `Vst3Fx` und `Vst3InstrumentEngine` stellen dafür einen kleinen `get_main_bus_layout()`-Accessor bereit.
- Risikoarm: keine Änderung an DSP, Audio-Callback oder Routing; nur zusätzliche Diagnose-/Header-Information für externe pedalboard-VSTs.

## v0.0.20.471 — CLAP Instrument Engine Reuse Fix (Preset/Editor-Stabilität) (2026-03-15)

- `pydaw/audio/audio_engine.py`: Der Instrument-Reuse-Pfad behandelt CLAP-Referenzen jetzt korrekt als `bundle_path + plugin_id` statt sie fälschlich mit dem kompletten `path::plugin_id`-String gegen `engine.path` zu vergleichen.
- Ergebnis: bereits laufende CLAP-Instrument-Engines (z. B. Surge XT) werden bei normalen Rebuild-/Refresh-Zyklen wiederverwendet statt neu geladen.
- Risikoarm: kein Eingriff in DSP, kein Routing-Umbau, keine Änderung am Audio-Callback selbst — nur der Engine-Reuse-Check wurde korrigiert.

## v0.0.20.470 — CLAP GUI Async-IO Host Support (POSIX-FD + Timer) (2026-03-15)

- `pydaw/audio/clap_host.py`: Offizielle Host-Erweiterungen für `clap.posix-fd-support` und `clap.timer-support` ergänzt, inklusive ctypes-Structs, Host-Callbacks und pro Plugin gespeicherten FD-/Timer-Registrierungen.
- `pydaw/audio/clap_host.py`: `_ClapPlugin` liest nun optional `clap_plugin_posix_fd_support_t` und `clap_plugin_timer_support_t` aus und bietet `dispatch_gui_fd()` / `dispatch_gui_timer()` für den GUI-Pfad an.
- `pydaw/ui/fx_device_widgets.py`: `ClapAudioFxWidget` synchronisiert registrierte GUI-FDs mit `QSocketNotifier` und Timer mit `QTimer`, aber nur solange das CLAP-Editorfenster wirklich offen ist.
- `pydaw/ui/fx_device_widgets.py`: FD-/Timer-Events pumpen danach wieder gezielt den CLAP-Main-Thread und räumen alle Async-Quellen beim Editor-Schließen sauber weg.
- Risikoarm: keine Änderung an CLAP-DSP, Audio-Callback oder Routing; Fokus ausschließlich auf den nativen Editor-/GUI-Pfad.

## v0.0.20.469 — CLAP Editor Bootstrap Main-Thread Handshake + Low-Rate Keepalive (2026-03-15)

- `pydaw/audio/clap_host.py`: `_ClapPlugin.create_gui()` pumpt jetzt den CLAP-Main-Thread gezielt in drei Phasen (`create` → `set_parent` → `show`), statt erst nach dem kompletten GUI-Aufruf. Das reduziert das Risiko, dass ein Plugin seinen nativen Child asynchron zu spät initialisiert und nur ein leerer Host-Container sichtbar bleibt.
- `pydaw/audio/clap_host.py`: Best-Effort `set_scale(1.0)` ergänzt und Host-Version auf `0.0.20.469` angehoben.
- `pydaw/ui/fx_device_widgets.py`: Der CLAP-Editor-Pump stoppt bei offenem Editor nicht mehr vollständig, sondern läuft nach der Prime-Phase mit 120 ms als sehr leichter Keepalive weiter. Dadurch können spätere `request_callback()`-Signale des Plugins weiterhin abgearbeitet werden.
- Risikoarm: keine Änderung am Audio-Callback, kein Eingriff in CLAP-DSP/Parameter-Events, Änderungen ausschließlich im Editor-Lifecycle solange das Editorfenster offen ist.

## v0.0.20.468 — CLAP Editor Deferred-Mapping + GUI-Visibility/Resize-Handshake (2026-03-15)

- `pydaw/ui/fx_device_widgets.py`: `ClapAudioFxWidget` öffnet den nativen CLAP-Editor jetzt deferred erst nach `show()` + `processEvents()`; `create_gui()` läuft dadurch nicht mehr direkt im Button-Klick auf einem potentiell noch instabilen Child-Handle.
- `pydaw/ui/fx_device_widgets.py`: `_editor_gui_container` nutzt jetzt zusätzlich `WA_DontCreateNativeAncestors`; der Pump-Timer schaltet nach der Prime-Phase automatisch von 16 ms auf einen langsameren Takt zurück.
- `pydaw/ui/fx_device_widgets.py`: GUI-Requests aus dem Host (`request_resize`, `request_show`, `request_hide`) werden an das Qt-Fenster gespiegelt, inklusive optionalem `set_gui_size()` Rückruf an das Plugin.
- `pydaw/audio/clap_host.py`: `_ClapPlugin` merkt sich die letzte GUI-Größe und stellt `take_requested_gui_visibility()` sowie `set_gui_size()` bereit.
- Risikoarm: kein Eingriff in CLAP-DSP, keine Änderung am Audio-Callback, Fokus ausschließlich auf Editor-Lifecycle und GUI-Handshake.

## v0.0.20.467 — CLAP Live-Plugin-Cache + Find-Log-Drosselung (2026-03-15)

- `pydaw/ui/fx_device_widgets.py`: `ClapAudioFxWidget` ergänzt um `_live_plugin_cache`, `_invalidate_live_clap_plugin_cache()` und einen gedrosselten `_find_live_clap_plugin()`-Pfad mit optionalem `use_cache=False` Refresh.
- Editor-Pump und GUI-Check nutzen jetzt bevorzugt den Cache statt pro Timer-Tick erneut `_track_audio_fx_map` / `_vst_instrument_engines` zu durchsuchen.
- `[CLAP-FIND]`-Diagnosen werden nur noch einmal pro Statuswechsel geloggt, damit das Terminal beim offenen CLAP-Editor nicht vollgeschrieben wird.
- Risikoarm: keine Änderung am Audio-Callback, keine Änderung an DSP/CLAP-Events, nur Widget-seitiger Lookup-/Diagnose-Pfad.

## v0.0.20.466 — CLAP MIDI-Learn / Kontextmenü-Parität (2026-03-15)

- `pydaw/ui/fx_device_widgets.py`: `ClapAudioFxWidget` ergänzt um `_automation_params`, `_param_key()` sowie die gleiche `_install_automation_menu()` / `_register_automatable_param()`-Verdrahtung wie bei den externen VST-Widgets.
- CLAP-Slider/Spinbox/Label unterstützen jetzt ebenfalls per Rechtsklick: **Show Automation in Arranger**, **MIDI Learn**, **Reset to Default**.
- Performance-sicher: die Registrierung passiert nur dann, wenn eine CLAP-Zeile durch die Lazy-UI wirklich gebaut wurde; keine zusätzliche Vollmaterialisierung großer Plugins wie Surge XT.

## v0.0.20.464 — CLAP Editor Callback Pump + Lazy Parameter UI

#### 2026-03-15 — Surge-XT-Editor und CLAP-Parameter-UI gehärtet
**Task:** CLAP Editor bleibt leer + Spurwechsel mit großem CLAP zu langsam
**Developer:** OpenAI GPT-5.4 Thinking
**Änderungen:**
- `pydaw/audio/clap_host.py`
  - Pro Plugin-Instanz eigenes `clap_host_t` mit `host_data`-Cookie
  - Host-Callbacks (`request_callback`, `request_resize`, `request_show/hide`) werden dem owning `_ClapPlugin` zugeordnet
  - `pump_main_thread()` + `take_requested_gui_size()` ergänzt
- `pydaw/ui/fx_device_widgets.py`
  - CLAP-Widget lädt Parameter bevorzugt aus der laufenden Audio-Engine
  - Initial nur kleiner Parameter-Batch, weitere Rows per „Mehr Parameter laden“
  - Suchfeld kann gezielt zusätzliche Parameter aufbauen statt immer alle auf einmal zu rendern
  - Editor startet nach `create_gui()` einen kurzen Qt-Pump-Timer für CLAP `on_main_thread()` und übernimmt Resize-Wünsche
**Erfolg:** ✅ Kein Syntaxfehler, keine riskante Audio-Engine-Neuarchitektur, Fokus nur auf CLAP-Editor-Lifecycle und UI-Performance

---

## v0.0.20.463 — CLAP Editor Pin/Roll Fix (x11_set_above)

#### 2026-03-15 — CLAP Editor Custom-Titelleiste repariert
**Task:** CLAP Editor 📌 Pin + 🔺 Roll Fix
**Developer:** Claude Opus 4.6
**Änderungen:**
- Pin: `setWindowFlags()` → `x11_set_above()` (verhindert X11 Re-Parenting / GUI-Zerstörung)
- Roll: Originalgröße wird gespeichert/wiederhergestellt (kein sizeHint-Fallback)
- Tooltips zeigen Pin-Status an
**Dateien:** `pydaw/ui/fx_device_widgets.py`

---

## v0.0.20.457 — CLAP Plugin Hosting (First-Class-Citizen)

#### 2026-03-15 — CLAP Plugin-Standard komplett integriert
**Task:** CLAP Plugin Hosting als vollwertiges Plugin-Format
**Developer:** Claude Opus 4.6
**Dauer:** 1 Session

**Was gemacht:**
- [x] `pydaw/audio/clap_host.py` NEU — ~830 Zeilen, kompletter CLAP C-ABI Host via ctypes
- [x] `pydaw/services/plugin_scanner.py` — CLAP Suchpfade + scan_clap() + scan_all()
- [x] `pydaw/audio/fx_chain.py` — ext.clap: Branch (FX + Instrument)
- [x] `pydaw/ui/plugins_browser.py` — CLAP Tab mit Favoriten, Drag&Drop, Status
- [x] `pydaw/ui/device_panel.py` — CLAP Metadata-Normalisierung
- [x] `pydaw/ui/fx_device_widgets.py` — ClapAudioFxWidget + make_audio_fx_widget Branch
- [x] `pydaw/audio/audio_engine.py` — ClapInstrumentEngine in Phase 1/2/3

**Files:** pydaw/audio/clap_host.py (NEU), pydaw/services/plugin_scanner.py, pydaw/audio/fx_chain.py, pydaw/ui/plugins_browser.py, pydaw/ui/device_panel.py, pydaw/ui/fx_device_widgets.py, pydaw/audio/audio_engine.py
**Erfolg:** ✅ Alle 7 Dateien kompilieren fehlerfrei, nichts kaputt gemacht

## v0.0.20.444 — Detachable Panels + Bitwig-Style Multi-Monitor Layout System

- `pydaw/ui/screen_layout.py`: Neues Modul — `PanelId`, `DetachablePanel`, `_FloatingWindow`, `ScreenLayoutManager`, `LayoutPreset`, `PanelPlacement`, 8 vordefinierte `LAYOUT_PRESETS`.
- `pydaw/ui/main_window.py`: Import `screen_layout`; `_init_screen_layout_manager()` registriert Editor/Mixer/Device/Browser/Automation als DetachablePanel; `_populate_screen_layout_menu()` baut dynamisches Menü; `_apply_screen_layout()`, `_toggle_panel_detach()`, `_dock_all_panels()` Handler; `closeEvent` speichert Layout-State.

## v0.0.20.436 — Performance Fix: Automation Recording Audio-Stutter

- `pydaw/audio/automatable_parameter.py`: sort_points() entfernt, lane_data_changed auf 8 Hz throttled, _flush_cc_ui() Timer.
- `pydaw/services/midi_mapping_service.py`: sort entfernt, emit throttled, legacy store write deferred.

## v0.0.20.435 — Fix: Automation Playback dB→Linear RT-Store Overwrite

- `pydaw/audio/automatable_parameter.py`: `tick()` + `clear_automation_values()`: Guard `if not param._listeners` vor `_mirror_to_rt_store()`.

## v0.0.20.434 — Fix: CC→Automation für ALLE Plugin-Typen

- `pydaw/audio/automatable_parameter.py`: `_write_cc_automation()` akzeptiert jetzt `afx:`, `afxchain:`, `trk:` Prefixe.
- `pydaw/ui/fx_device_widgets.py`: Generic CC Re-Registration in `_install_automation_menu()`.

## v0.0.20.433 — CC→Automation Recording für MIDI Learn Fast Path + REC Button

- `pydaw/audio/automatable_parameter.py`: `set_transport()`, `set_project()`, `_write_cc_automation()` — Fast Path MIDI Learn schreibt jetzt Automation-Breakpoints bei write/touch/latch.
- `pydaw/services/container.py`: Transport + Project Referenzen an AutomationManager übergeben.
- `pydaw/ui/automation_editor.py`: ● REC Button mit Touch/Read Toggle + Mode-Sync.

## v0.0.20.432 — Multi-Lane Stacking + Touch/Latch Automation Modi

- `pydaw/ui/automation_editor.py`: `_LaneStrip` + Multi-Lane `EnhancedAutomationLanePanel` (bis zu 8 gleichzeitig).
- `pydaw/services/midi_mapping_service.py`: Touch/Latch Timer + `_should_write_automation()`.
- `pydaw/services/automation_playback.py`: Mode-Check erweitert: read + touch + latch.

## v0.0.20.429 — Bounce in Place: plugin_type Matching Fix (chrono-Prefix)

- `pydaw/services/project_service.py`: `plugin_type` Matching erweitert: `'sampler'` → `in ('sampler', 'chrono.pro_audio_sampler')`, `'drum_machine'` → `in ('drum_machine', 'chrono.pro_drum_machine')`, `'aeterna'` → `in ('aeterna', 'chrono.aeterna')`, plus `'chrono.bach_orgel'`.

## v0.0.20.428 — Bounce in Place: Best-Practice Fix (Borrow Running Engine)

- `pydaw/services/container.py`: `project._audio_engine_ref = audio_engine` — Brücke zur laufenden Audio-Engine.
- `pydaw/services/project_service.py`: `_track_has_vst_device()` — Prüft ob Track VST-Devices hat.
- `pydaw/services/project_service.py`: `_create_vst_instrument_engine_offline()` — Borgt ZUERST die laufende Engine (Best-Practice), Offline-Fallback nur wenn nötig.
- `pydaw/services/project_service.py`: `_render_track_subset_offline()` — Relaxierte kind-Prüfung + borrowed-Engine Handling.

## v0.0.20.427 — Bounce in Place: VST Offline Fix #2 (Warmup + Suspend/Resume)

- `pydaw/services/project_service.py`: VST2 Suspend/Resume Zyklus nach State-Restore (`effMainsChanged(0)→(1)→effStartProcess`).
- `pydaw/services/project_service.py`: 200ms Warmup-Phase nach Engine-Erstellung (Plugin-Initialisierung).
- `pydaw/services/project_service.py`: Relaxierte Instrument-Erkennung (Fallback: jedes ext.vst = Instrument wenn MIDI-Bounce).
- `pydaw/services/project_service.py`: Umfangreiche stderr-Diagnose-Logs für den gesamten Offline-Bounce-Pfad.
- `pydaw/services/project_service.py`: Exception-Logging statt stummes `except: pass`.

## v0.0.20.426 — Bounce in Place: VST2/VST3 Offline Rendering Fix

- `pydaw/services/project_service.py`: Neue Methode `_create_vst_instrument_engine_offline()` — erstellt temporäre VST2/VST3-Engine aus Track-FX-Chain für Offline-Bounce.
- `pydaw/services/project_service.py`: Neue Methode `_render_vst_notes_offline()` — rendert MIDI-Noten mit korrektem note_on/note_off-Scheduling + Release-Tail durch VST-Engine.
- `pydaw/services/project_service.py`: `_render_track_subset_offline()` hat jetzt VST-Instrument-Fallback wenn keine interne Engine (Sampler/Drum/Aeterna) verfügbar.
- Bounce in Place, Bounce + Mute, Bounce Dry funktionieren jetzt für VST2/VST3-Instrument-Tracks (Dexed, Helm, Surge XT, etc.).

## v0.0.20.373 — VST3 Widget Main-Thread Reload Hotfix

- `pydaw/ui/fx_device_widgets.py` importiert jetzt `QCheckBox`, sodass Bool-Parameter im externen VST3-Widget wieder sauber als Checkboxen aufgebaut werden können.
- Der bestehende Async-Fallback im `Vst3AudioFxWidget` bleibt erhalten, reagiert aber jetzt auf den Spezialfall `must be reloaded on the main thread` mit einem gezielten einmaligen Retry im Qt-Main-Thread.
- Fokus blieb bewusst auf einem kleinen Widget-/Fallback-Hotfix; Audio-Routing, Host-Core, Mixer und Projektformat wurden nicht angefasst.

## v0.0.20.372 — VST3 Widget Embedded-State Hint

- `Vst3AudioFxWidget` zeigt jetzt einen kleinen sichtbaren **Preset/State-Hinweis** direkt im Widget an.
- Das Widget erkennt projektseitig, ob für das aktuelle externe **VST2/VST3-Device** bereits ein eingebetteter `__ext_state_b64`-Blob vorhanden ist.
- Bei vorhandenem Blob wird ein kompakter Hinweis mit grober Größenanzeige angezeigt; ohne Blob erscheint defensiv ein klarer Hinweis, dass der State erst nach dem Speichern erzeugt wird.
- Umsetzung bleibt vollständig **UI-seitig** in `pydaw/ui/fx_device_widgets.py`; kein Eingriff in Audio-Callback, Routing, Mixer oder Plugin-Hosting.


## v0.0.20.371 — VST3 Project-State Raw-Blob Save/Load

- Externe **VST2/VST3-Devices** schreiben beim Projektspeichern jetzt zusätzlich einen **Base64-`raw_state`-Blob** (`__ext_state_b64`) in ihre Device-`params`.
- Der Blob wird **aus den aktuell gespeicherten Projekt-Parametern** auf einer frischen Plugin-Instanz erzeugt; die laufende DSP-Instanz wird dafür bewusst **nicht** direkt angefasst.
- `Vst3Fx` restauriert diesen Blob beim Laden vor der normalen Parameter-Initialisierung, sodass projektseitige Preset-/State-Daten erhalten bleiben.

## v0.0.20.370 — VST3 Widget Runtime-Param-Reuse Hotfix

- `Vst3AudioFxWidget` liest Parameter-Infos jetzt bevorzugt direkt aus der **bereits laufenden VST-DSP-Instanz** im Audio-Engine-FX-Map.
- Dadurch müssen frisch eingefügte Plugins wie **Autogain Mono** oder **GOTT Compressor LeftRight** für die Widget-Parameter nicht mehr sofort erneut in einem Worker-Thread geladen werden.
- Vor dem Async-Fallback wartet das Widget kurz auf den FX-Rebuild; das hält den Insert weiter responsiv, ohne die gerade aktive Live-Instanz aus dem Tritt zu bringen.
- `Vst3Fx` extrahiert Parameter-Metadaten jetzt direkt aus der schon geladenen Plugin-Instanz und macht beim Build keinen unnötigen Zweit-Load mehr.
- Fokus blieb bewusst auf **VST-Widget/Host-Metadaten**; kein Eingriff in Audio-Routing, Mixer, Automation-Architektur oder Projektformat.

## v0.0.20.369 — VST3 Mono/Stereo Bus-Adapt Hotfix

- `pydaw/audio/vst3_host.py` adaptiert externe VST3/VST2-FX jetzt sicher zwischen dem internen **Stereo-Track-Pfad** und dem tatsächlichen **Plugin-Main-Bus**.
- Mono-FX wie **LSP Autogain Mono** oder **Filter Mono** laufen dadurch jetzt ohne dauerhaften `2-channel output`-Fehler im Audio-Callback.
- Stereo→Mono nutzt einen kleinen Downmix an der Bridge; Mono-Outputs werden für den Host wieder sauber auf links/rechts gespiegelt.
- Falls `pedalboard` die Busgrößen nicht vorab verrät, liest der Host die Kanalzahlen einmalig aus der Fehlermeldung, stellt sich darauf um und cached das Layout für die weiteren Blöcke.
- Rein auf den externen VST-Bridge-Pfad begrenzt; kein Umbau an Mixer, Arranger, Routing oder DSP-Grundarchitektur.

## v0.0.20.366 — VST3 Device Exact-Reference Hotfix

- Externe VST3/VST2-Devices tragen jetzt immer eine **kanonische Komplett-Referenz** (`__ext_ref`) zusätzlich zu `__ext_path` und optional `__ext_plugin_name`.
- Browser-Insert und Drag&Drop geben diese exakte Referenz jetzt direkt mit.
- DevicePanel normalisiert die VST-Metadaten beim Hinzufügen, damit auch ältere Payloads oder gemischte Insert-Wege stabil auf dasselbe Sub-Plugin zeigen.
- Audio-FX-Build und VST-Widget bevorzugen jetzt die exakte Referenz statt nur des Basis-Pfads.
- Ziel: **kein stiller Verlust des gewählten Sub-Plugins** mehr beim Insert/Rebuild von Multi-Plugin-Bundles wie `lsp-plugins.vst3`.
- Kein Eingriff in Transport, Routing, Mixer, Automation-Architektur oder DSP-Grundverhalten.

## v0.0.20.365 — VST3 Startup Scan Hang Hotfix

- Kritischen Start-Hänger behoben: Der Plugins-Browser instanziiert beim automatischen Rescan nicht mehr blind jedes VST3 über `pedalboard`.
- Ursache war die neue Multi-Plugin-Erkennung aus v0.0.20.364; Plugins wie `ZamVerb.vst3` konnten dabei schon während des Browser-Scans hängen bleiben.
- Sicherer Hotfix: Eager-Probing nur noch für bekannte sichere Collection-Bundles wie `lsp-plugins.vst3`; normale VST3s bleiben beim Scan rein dateibasiert.
- Debug-Override `PYDAW_VST_MULTI_PROBE=1` ergänzt.
- Keine Änderung an Audio-Engine, Transport, Mixer oder Projektformat.

## v0.0.20.364 — VST3 Browser Multi-Plugin Bundle Fix

- **VST3-Browser** erkennt Mehrfach-Bundles wie `lsp-plugins.vst3` jetzt als mehrere separate Plugin-Einträge statt als eine unklare Datei.
- **`__ext_plugin_name`** wird durch Browser → DevicePanel → Widget → Live-Host durchgereicht, damit genau das ausgewählte Sub-Plugin geladen wird.
- **`pydaw/audio/vst3_host.py`** erhielt sichere Helper für Ref-Aufbau/-Split, Mehrfach-Bundle-Erkennung und exaktes Laden via `plugin_name`.
- **`install.py`** installiert `pedalboard` jetzt explizit; **`requirements.txt`** enthält die Abhängigkeit ebenfalls.
- Veraltete **Placeholder-Labels** im Plugins-Browser wurden auf echtes Live-Hosting / Rescan-Hinweise umgestellt.
- Rein auf Plugin-Discovery/-UI/-Hosting-Metadaten begrenzt; kein Eingriff in Arranger, Transport, Routing oder DSP-Grundarchitektur.

## v0.0.20.361 — MIDI Content Scaling + Instrument-Browser Doppelklick-Fix

- **Alt + Drag am MIDI-Clip-Rand** skaliert alle MIDI-Noten proportional (Bitwig-Style).
- **Alt + Drag am Audio-Clip-Rand** passt `clip.stretch` proportional an.
- **Instrument-Browser Doppelklick** repariert (Methode war leer).
- **Alt+Drag-auf-Body DnD-Copy entfernt** (kollidierte, Ctrl+Drag ist Copy-Methode).
- Neon-Glow-Effekt (🎵/🔊), Lazy Update, Original-Snapshot, Free Mode (Alt+Shift).
- Kein Eingriff in Audio-Engine, Transport, FX-Chain.

## v0.0.20.360 — DAWproject Export Cross-Device Hotfix

- Kritischen Export-Fehler **`[Errno 18] Ungültiger Link über Gerätegrenzen hinweg`** behoben.
- Finale `.dawproject`-Datei wird jetzt als **temporäre Schwesterdatei direkt im Zielordner** geschrieben statt in `/tmp`.
- Atomarer Abschluss via `os.replace()` bleibt erhalten, auch wenn Staging in `/tmp` und Zielordner auf verschiedenen Dateisystemen liegen.
- Zusätzlicher Cleanup für temporäre Zieldateien im Fehlerfall ergänzt.
- Kein Eingriff in Audio-Engine, Routing, Mixer, Transport, Undo/Redo oder Projektmodell.

## v0.0.20.359 — DAWproject Export UI Hook

- Neuer Menüeintrag **Datei → DAWproject exportieren… (.dawproject)** direkt neben dem vorhandenen Import ergänzt.
- Export läuft im Hintergrund über den bereits sicheren **`DawProjectExportRunnable`** auf Basis eines **read-only Snapshots**.
- **QProgressDialog** zeigt den Export-Fortschritt, ohne Audio-Core oder Arranger-Playback anzufassen.
- **QFileDialog** schlägt automatisch einen sinnvollen `.dawproject`-Dateinamen vor.
- Nach Erfolg erscheint ein Summary-Dialog mit Export-Zahlen und optionalen Warnungen.
- Bewusst **kein** Eingriff in Engine, Routing, Mixer, Transport, Undo/Redo oder Projekt-Mutationen.


## v0.0.20.358 — DAWproject Exporter Scaffold (snapshot-safe)

- Neuer sicherer **`pydaw/fileio/dawproject_exporter.py`** ergänzt.
- Export arbeitet bewusst nur auf einer **tief kopierten Snapshot-Instanz** des Projekts und berührt die laufende Session nicht.
- Neue **Temp-File-First Pipeline**: Staging-Ordner, XML-Erzeugung, ZIP-Bau, Validierung, anschließend atomarer Replace auf das Ziel.
- **Audio-Dateien** werden aus `Project.media` und Audio-Clips gesammelt und in `audio/` innerhalb des `.dawproject`-Containers geschrieben.
- **Automation-Lanes** aus `automation_manager_lanes` werden pro Spur in eine konservative XML-Struktur gemappt.
- **Instrument-/Device-Zustände** werden als erste sichere Grundlage als **Base64-XML-State-Blobs** serialisiert.
- Optionaler **`DawProjectExportRunnable`** für non-blocking PyQt6-Integration ergänzt.
- Neue Architektur-Dokumentation mit Datenfluss und Mermaid-Klassendiagramm unter `PROJECT_DOCS/plans/DAWPROJECT_EXPORT_ARCHITECTURE.md`.
- Bewusst **kein** Eingriff in Audio-Engine, Arranger-Playback, Mixer, Transport oder Undo/Redo-Core.


## v0.0.20.357 — Echter Group-Bus mit eigener Device-Chain (Bitwig-Style)

- **Echte Gruppenspur** mit `kind="group"` und eigener `audio_fx_chain` implementiert.
- **Group-Bus-Routing** im Audio-Callback: Kind-Audio wird summiert, durch Gruppen-FX verarbeitet, dann erst in den Master gemischt.
- **Pull-Sources** (Sampler/Drum/SF2) fließen ebenfalls durch den Group-Bus.
- **Group-Header-Klick** wählt den Group-Track aus → DevicePanel zeigt Gruppen-Chain.
- **Effects auf Gruppe** landen auf der Gruppen-FX-Chain, nicht auf der kick-Spur.
- Alte Projekte ohne Group-Tracks → kein Routing → Audio unverändert.
- 8 Dateien geändert: hybrid_engine, audio_engine, project_service (2×), arranger (2×), version, model.

## v0.0.20.356 — Kritischer Bugfix: Collapsed-Group Clip-Track-Zuordnung

- **Clip-Track-Korruption bei Drag in eingeklappter Gruppe** behoben: Clips wurden beim Drag auf `members[0]` umgehängt, sodass alle Instrumente gleichzeitig spielten.
- Neue Helper-Methode `_is_same_collapsed_group()` schützt alle drei Drag-Pfade (Single/Multi/Copy).
- **Track-Lookup Fallback** für collapsed Groups: Volume-Anzeige für Non-First-Members korrigiert.
- **Spur-Name-Prefix** in Clip-Labels bei eingeklappter Gruppe (🔹kick: ..., 🔹open hi: ...) für bessere Unterscheidbarkeit.
- Rein UI/Canvas-Fix, kein Eingriff in Audio-Engine, Routing oder Projektformat.

## v0.0.20.355 — Browser Scope-Badges + Distortion Automation Guard

- Browser/Add-Flow zeigt jetzt kleine **Scope-Badges** direkt neben den Add-Buttons in **Instruments**, **Effects**, **Favorites** und **Recents**.
- Die Badges nennen klar das aktuelle Ziel der normalen Browser-Aktion: **aktive Spur**, nicht die ganze Gruppe.
- Bei Gruppenspuren bleibt damit vor dem Add sichtbarer, dass **normales Add / Doppelklick / Drag&Drop** weiter nur auf die aktive Einzelspur wirkt.
- Die Scope-Badges aktualisieren sich sicher beim Spurwechsel über `DeviceBrowser.set_selected_track(...)`.
- Zusätzlich wurde ein sicherer Guard im **DistortionFxWidget** ergänzt, damit Automation-Callbacks nicht mehr auf bereits gelöschte Qt-Slider/Spinboxen zugreifen.

## v0.0.20.354 — DevicePanel Gruppen-/Spur-Zieltrennung klarer

- DevicePanel erhielt eine zusätzliche **Aktive Spur-Ziel**-Hinweisbox direkt oberhalb der sichtbaren Device-Kette.
- Die Box erklärt jetzt klar, dass die **sichtbare Device-Kette unten nur zur aktiven Spur** gehört.
- Für Gruppenspuren werden **NOTE→Gruppe** und **AUDIO→Gruppe** als getrennte Gruppen-Aktionen klar ausgewiesen.
- Die bisherige Gruppenleiste wurde sprachlich auf **Gruppen-Aktionen** geschärft und nennt ausdrücklich, dass hier noch **kein gemeinsamer Gruppenbus** existiert.
- Umsetzung blieb vollständig **UI-only** in `pydaw/ui/device_panel.py`.

## v0.0.20.353 — TrackList Drop-Markierung beim Maus-Reorder

- Linke Arranger-TrackList zeigt beim lokalen Maus-Reorder jetzt eine **sichtbare cyanfarbene Drop-Markierung** direkt an der Einfügeposition.
- Die Markierung folgt **oben/unten pro Zielzeile** und zeigt auch **Drop am Listenende** korrekt an.
- Die Lösung greift nur bei internem **TrackList-Reorder-MIME**; bestehender **Cross-Project-Track-Drag** bleibt unangetastet.
- Keine Änderung an Routing, Mixer, DSP, Playback oder Projekt-Audiodaten.

## v0.0.20.352 — Gruppenkopf-Mausdrag + Doppelklick-Umbenennen

- Gruppenköpfe lassen sich im linken Arranger jetzt **direkt per Maus-Drag als kompletter Block** verschieben.
- Das nutzt weiterhin den bestehenden sicheren Drag-Weg: **Cross-Project-Track-Drag bleibt erhalten**, lokal kommt nur derselbe Reorder-Mechanismus für Gruppenmitglieder zum Einsatz.
- **Doppelklick auf Track-Namen** öffnet jetzt direkt den sicheren Umbenennen-Dialog; **Doppelklick auf Gruppenkopf** öffnet den Gruppen-Umbenennen-Dialog.
- DevicePanel-Gruppenstreifen zeigt jetzt deutlicher an: **Track-FX = nur aktive Spur**, **N→G / A→G = ganze Gruppe**.

## v0.0.20.351 — Arranger Maus-Reorder in TrackList

- Spuren lassen sich im linken Arranger-Bereich jetzt **mit der Maus neu anordnen**.
- Mehrfachauswahl wird als **zusammenhängender Block** verschoben, statt Spur für Spur.
- Der bestehende **Cross-Project-Track-Drag** bleibt erhalten; lokales Reorder nutzt nur ein zusätzliches internes MIME und greift ausschließlich bei **same-widget Drops**.
- Umsetzung bleibt bewusst **UI-/Projektordnungs-safe**: kein Eingriff in Audio-Routing, Mixer, DSP oder Playback-Core.

## v0.0.20.350 — Arranger Gruppen-Alignment / Move Buttons

- ArrangerCanvas zeigt jetzt **ausgeklappte Gruppen mit Gruppenkopf + allen Mitgliedsspuren** synchron zur linken TrackList.
- Das behebt die sichtbare Fehlzuordnung, bei der in ausgeklappten Gruppen nicht alle Instrument-/Audio-/Busspuren korrekt erschienen.
- Direkt sichtbare **▲/▼-Buttons** in Track-/Gruppenzeilen ergänzt.
- **Gruppen als Block verschiebbar** gemacht.

## v0.0.20.349 — Gruppen-Fold-State + Arranger-Gruppen-Lane + Track-Reorder

- Arranger speichert jetzt den **Gruppen-Einklappstatus** direkt im Projekt (`arranger_collapsed_group_ids`), sodass Gruppen nach dem erneuten Laden in ihrem letzten Fold-Zustand wieder erscheinen.
- Eingeklappte Gruppen werden jetzt nicht nur links in der TrackList, sondern auch **rechts im Arranger-Canvas als eine gemeinsame Spur/Lane** dargestellt; die Clips der Gruppenmitglieder werden sicher auf diese Gruppen-Lane abgebildet.
- Arranger-Track-Menüs können Spuren jetzt **nach oben/unten verschieben**, ohne Master-Position oder Audio-Core anzufassen.
- Über Gruppenkopf- und Track-Menüs lassen sich neue **Instrument-/Audio-/Busspuren direkt in die bestehende Gruppe einfügen**, statt nur unterhalb der Gruppe am Listenende zu landen.
- Umsetzung bleibt bewusst **UI-/Projektmodell-safe**: kein Bus-Routing-Umbau, kein Mixer-Core-Redesign, keine DSP-Änderung.

## v0.0.20.348 — Master-FX hörbar + globales Projekt-Undo + reparierte Track-Menüs

- Master-Audio-FX werden jetzt im Summenpfad wirklich verarbeitet und sind hörbar, ohne Routing-/Bus-Core-Umbau.
- Globaler Projekt-Undo-Fallback ergänzt: modellweite Änderungen mit `project_updated` werden jetzt zusätzlich als sichere Snapshot-Undo-Schritte erfasst.
- Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y als globale Application-Shortcuts verdrahtet, damit Undo/Redo auch bei Fokus in Unterwidgets greift.
- Track-Kontextmenüs im Arranger erweitert/repariert: **Umbenennen**, **Track löschen**, **Instrument-/Audio-/Bus-Spur hinzufügen**.
- Gruppenköpfe im Arranger sind jetzt wirklich **einklappbar** und bieten ein passendes Gruppenmenü.
- Track-Löschen aus dem Kontextmenü ist wieder funktionsfähig; Umbenennen läuft jetzt sicher per Dialog statt instabiler Inline-Editierung.

## v0.0.20.347 — Arranger Track-/Gruppen-Flow + Gruppen-Sektion im DevicePanel

- Arranger-Clipauswahl synchronisiert jetzt sicher die zugehörige Spur mit, sodass beim Klick auf einen MIDI-/Audio-Clip auch die Instrument-/Track-Zeile aktiv wird.
- Direktes Rechtsklick-Menü auf Track-Zeilen im Arranger ergänzt; Gruppierungsfunktionen sind jetzt dort auffindbar statt nur über Tastenkürzel oder den kleinen ▾-Button.
- Gruppierte Spuren werden im Arranger als sichtbare **Gruppen-Sektion** mit Gruppenkopf und eingerückten Mitgliedern dargestellt.
- DevicePanel zeigt für gruppierte Spuren jetzt eine lokale **Gruppen-Sektion** mit Mitgliederliste und sicheren Batch-Aktionen **N→G** / **A→G**, um NOTE-FX oder AUDIO-FX auf die komplette aktive Gruppe anzuwenden.
- Umsetzung bleibt bewusst **UI-/Projektmodell-first**: kein Eingriff in Playback-Core, Mixer-Engine, Transport oder Audio-Routing.

## v0.0.20.339 — AETERNA Knob-Mini-Meter / aktive Mod-Badges direkt an Synth-Knobs

- AETERNA zeigt jetzt kleine **Mini-Meter direkt an wichtigen Synth-Knobs** im lokalen Synth Panel (Filter, Voice, AEG, FEG, Layer, Noise, Timbre, Drive).
- Die Meter nennen kompakt **aktuellen Wert + kleine Balkenanzeige**; darunter erscheinen **aktive Mod-Badges pro Ziel-Knob** wie z. B. **A+20** oder **B−18**, falls Web A/B gerade wirklich auf diesen Knob zielen.
- Die bestehenden **Knob-Tooltips** wurden passend erweitert: neben Automation-Hinweis und gespeichertem Mod-Profil nennen sie jetzt auch **Mini-Meter** und **aktive Mod-Badges**.
- Reiner Widget-/State-Schritt in `aeterna_widget.py`; kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core oder AETERNA-DSP.

## v0.0.20.338 — AETERNA Live ARP via bestehendem Note-FX-Arp

- AETERNA **Arp A** hat jetzt einen sicheren **Live-ARP-ON/OFF**-Weg: Das Widget pflegt lokal auf der aktuellen Spur ein eigenes **Track Note-FX Arp** (markiert als `aeterna_owner=arp_a`) und schaltet dieses per **ARP Live** an/aus.
- Damit bleibt der Eingriff **außerhalb des Playback-Cores** und nutzt die bereits vorhandene projektweite **Note-FX-Kette** statt eines riskanten neuen Echtzeit-Arp-Cores in AETERNA.
- Die AETERNA-Arp-Stepdaten wirken jetzt nicht mehr nur beim **ARP→MIDI**-Weg, sondern auch für den sicheren **Live-ARP**: **Transpose / Skip / Velocity / Gate / Shuffle / Note Type** werden im bestehenden `chrono.note_fx.arp` berücksichtigt.
- AETERNA zeigt den Zustand jetzt klarer als **ARP Live** vs. **ARP→MIDI**; zusätzlich wurden Card-/Hint-Schriften lokal leicht vergrößert, damit die Screens auf kleineren Höhen lesbarer bleiben.
- Weiterhin keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

## v0.0.20.328 — AETERNA Mod Rack / Flow + Collapsible UI

- AETERNA lokal um ein **MOD RACK / FLOW (LOCAL SAFE)** erweitert.
- Neue lokale **Drag-&-Drop-Quellen**: **LFO1**, **LFO2**, **MSEG**, **Chaos**, **ENV**, **VEL**.
- Drop auf stabile Ziele (**Morph, Tone, Gain, Release, Space, Motion, Cathedral, Drift, Chaos**) weist die Quelle sicher einem der realen Slots **Web A/B** zu.
- Zusätzliche lokale Slot-Helfer: **Drop-Slot Auto/A/B**, **Swap A/B**, **Clear A**, **Clear B**.
- Alle großen AETERNA-Bereiche sind jetzt **einklappbar** (Dreiecks-Header), damit das Instrument kompakter bleibt.
- Neue lokale **Signalfluss-Karte** erklärt den AETERNA-Aufbau kompakt.
- Kleine echte Engine-Erweiterung nur innerhalb AETERNA: **ENV**- und **VEL**-Modulationsquellen können jetzt in den beiden Web-Slots genutzt werden.
- Keine Änderungen an Arranger-Core, Playback-Core, Mixer-Engine, Transport oder anderen Instrumenten.

## v0.0.20.324 — AETERNA staged Init / sanfteres Laden

- AETERNA lädt jetzt lokal **sanfter und flüssiger**: beim Restore werden UI-Signale geblockt und Widget-Updates gebündelt, damit nicht dutzende Komfort-Callbacks gleichzeitig im GUI-Thread anlaufen.
- Komfort-/Lesbarkeitsbereiche (**Formel-Info, Web-/Snapshot-Karte, Composer-Zusammenfassung, Preset-Kurzliste, Phase-3a-Summary**) werden jetzt **gestaffelt per Deferred Refresh** aufgebaut, sodass das Grund-Widget früher sichtbar wird.
- Lokale Button-Neubindung für Preset-/Snapshot-Schnellaufrufe auf **gezieltes Rebind statt blindem disconnect()** umgestellt; das vermeidet überflüssige Qt-Hardening-Fehlermeldungen beim Refresh.
- Weiterhin nur **AETERNA-Widget**, kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

## v0.0.20.321 — AETERNA Preset-/Snapshot-Schnellaufrufe lokal

- AETERNA zeigt jetzt kleine lokale **Preset-/Snapshot-Schnellaufrufe** direkt im Widget: gefüllte Snapshot-Slots werden als kompakte Recall-Buttons sichtbar, ergänzt um Preset-Schnellaufrufe aus der bestehenden Kurzliste.
- Die neue Schnellaufruf-Zeile leitet alles rein lokal aus bereits vorhandenen **Snapshot-Daten**, **Preset-Metadaten** und **Formel/Web-Kombitipps** ab; Tooltips nennen kompakt **Hörbild**, **Formel** und **Web-Startweg**.
- Keine neue Engine- oder State-Logik: reiner Widget-/Komfortschritt in AETERNA ohne Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

---

## v0.0.20.320 — AETERNA Formel-/Web-Kombitipps direkt an Presets

- AETERNA zeigt jetzt lokale **Preset→Startweg**-Hinweise direkt im Widget: pro Preset wird ein kompakter Tipp für **Formel + Web-Vorlage/Intensität** sichtbar.
- Die **Preset-Kurzliste** nennt diese Startwege jetzt direkt in der Textzeile; Schnellpreset-Tooltips zeigen zusätzlich **Hörbild**, **Formelidee** und **Web-Startweg** zusammen an.
- Der kompakte **Preset-Fokus** des aktuell gewählten Presets enthält jetzt ebenfalls den lokalen **Startweg**.
- Rein lokale Ableitung aus bereits vorhandenen Preset-Metadaten, Formelideen und Web-Vorlagen; **kein** neuer Core-State und kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

---

## v0.0.20.319 — AETERNA Preset-Kurzliste mit Direktmarkern

- AETERNA-Preset-Kurzliste zeigt jetzt lokale **Direktmarker** für **Kategorie** und **Charakter**.
- Die sichtbaren Kurzlisten-Einträge werden kompakter als Marker dargestellt, z. B. **Sakral • Hell** oder **Ambient • Weich**.
- Tooltips der Schnell-Presets zeigen zusätzlich den Direktmarker neben Hörbild und Presetnamen.
- Der Aktiv-Status der Kurzliste enthält jetzt ebenfalls den aktuellen **Kategorie/Charakter-Marker**.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

---

## v0.0.20.318 — AETERNA Snapshot-Slots mit Farbbadges/Statusmarkern

- AETERNA lokal um kleine **Farbbadges/Statusmarker** direkt an den Snapshot-Slots **A/B/C** erweitert: **leer**, **gefüllt** und **aktiv** werden jetzt sofort sichtbar.
- Zusätzlicher kleiner **Hörbild-Marker** pro Slot (z. B. sakral, klar, getragen, belebt) wird rein lokal aus den bereits vorhandenen Snapshot-Daten abgeleitet.
- **Recall** ist für leere Slots lokal deaktiviert; Tooltips von **Store/Recall** zeigen jetzt kompakt den aktuellen Snapshot-Inhalt an.
- Reiner Widget-/Darstellungsschritt auf Basis vorhandener lokaler Snapshot-Daten; **kein** Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core oder Projektstruktur.

## v0.0.20.317 — AETERNA Preset-Bibliothek kompakt nach Kategorie/Charakter

- AETERNA lokal um eine kompakte **Preset-Bibliotheksansicht** erweitert: sichtbare Zusammenfassung der lokalen Presets nach **Kategorie** und **Charakter** direkt im Widget.
- Neue **Fokuszeile** für das aktive Preset: zeigt **Kategorie / Charakter / Favorit / Tags / Hörbild** kompakt an.
- Die bestehende **Preset-Kurzliste** zeigt jetzt zusätzlich **Kategorie/Charakter** direkt in der Textzeile sowie im Tooltip der Schnellwahl-Buttons.
- Reiner Widget-/Darstellungsschritt auf Basis vorhandener lokaler Preset-Metadaten; **kein** Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core oder Projektstruktur.

## v0.0.20.316 — AETERNA lokaler Automation-Schnellzugriff

- AETERNA lokal um einen **Automation-Schnellzugriff** erweitert: alle bereits stabil freigegebenen Ziele (**Morph, Tone, Gain, Release, Space, Motion, Cathedral, Drift, Chaos, LFO1 Rate, LFO2 Rate, MSEG Rate, Web A, Web B**) können jetzt direkt aus dem Widget in die passende Automation-Lane geöffnet werden.
- Bestehende AETERNA-Knobs zeigen lokal klarere **Automation-ready-Tooltips** mit einer kleinen musikalischen Einordnung (z. B. Sweeps, sakrale Weite, Schwebung, Web-Tiefe).
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core oder Projektstruktur.

- 2026-03-07 v0.0.20.315: AETERNA Formel-/Preset-Vorschläge um lokale Hörhinweise ergänzt (z. B. sakral, klar, getragen, belebt, kristallin, dunkel) – nur im Widget.
- 2026-03-07 v0.0.20.314: AETERNA Snapshot-Karte kompakter und musikalischer lesbar gemacht (Preset, Stimmung, Formelhinweis, Web).
- 2026-03-07 v0.0.20.312: AETERNA Web-Vorlagen um „Basis wiederherstellen“ erweitert; aktive Web-Vorlage und Intensität werden lokal gespeichert/geladen.
## v0.0.20.311 — AETERNA Web-Vorlagen mit Intensitätsstufen

- AETERNA lokal um sichere **Intensitätsstufen** für Web-A/Web-B-Startvorlagen erweitert: **Sanft**, **Mittel**, **Präsent**.
- Intensität skaliert nur lokale **Amount-/Rate-Werte** der Web-Vorlagen und greift nicht in den DAW-Core ein.
- Die gewählte Intensität wird sauber im **Instrument-State** mitgespeichert und beim Projektladen wiederhergestellt.
- Web-Karte zeigt jetzt kompakt: **aktive Vorlage + Intensität + Web A/B**.
- Weiterhin nur **AETERNA-Widget**, kein Eingriff in Arranger, Audio Editor, Clip Launcher, Mixer, Transport oder Playback-Core.

## v0.0.20.309 — AETERNA Macro-A/B-Feinsteuerung lesbarer

- AETERNA lokal um eine kompakte **Macro-A/B-Karte** erweitert.
- Zeigt jetzt lesbar: **Quelle → Ziel → Amount** für **Web A** und **Web B**.
- Zusätzliche Kurz-Hinweise im Widget ordnen die aktuelle Modulationsidee ein, z. B. eher **Sweep**, **gezeichneter Verlauf**, **organische Bewegung** oder **spielabhängige Dynamik**.
- Fokus bleibt lokal auf sicheren Makro-Wege: **Source/Target/Amount** statt roher interner Zustände.
- Weiterhin nur **AETERNA-Widget**, kein Core-Eingriff.

## v0.0.20.308 — AETERNA Formel-/Preset-Verknüpfung sichtbar

- Lokale **Preset→Formel-Hinweiszeile** direkt im AETERNA-Formelbereich ergänzt.
- Zeigt jetzt, welche **Formelidee** zum aktuellen Preset passt (z. B. Sakral, Organisch, Drone, Chaos, Warm Start).
- Zusätzlicher Button **„… laden“**, um die vorgeschlagene Formelidee nur lokal ins Formelfeld zu übernehmen.
- Status unterscheidet: passende Idee bereit / im Feld / angewendet / eigene Formel.
- Weiterhin **nur AETERNA-Widget**, kein Core-Eingriff.

## v0.0.20.307 — AETERNA Preset-Kurzliste mit lokalem Filter

- AETERNA lokal um einen sicheren Filter für die Preset-Kurzliste erweitert: **Alle**, **Sakral**, **Kristall**, **Drone** und **Favoriten**.
- Die vier Schnellwahl-Buttons passen sich jetzt lokal dem gewählten Filter an.
- Hilft beim schnellen Finden von sakralen, gläsernen oder ruhigen Startpresets, ohne Eingriff in den DAW-Core.

## v0.0.20.306 — AETERNA Preset-Kurzliste lokal

- kompakte lokale Preset-Kurzliste direkt im AETERNA-Widget ergänzt
- Schnellwahl-Buttons für: Kristall Bach, Bach Glas, Kathedrale, Celesta Chapel
- lokale Statuszeile zeigt aktives Preset, Favorit und Tag-Vorschau
- nur AETERNA-Widget angepasst, keine Core-Änderungen

## v0.0.20.304
- AETERNA lokal um weitere kuratierte **Formel-Startbeispiele** erweitert: **Organisch** und **Drone**.
- Lokales **AETERNA-Voicing** in der Engine entschärft und verfeinert: weniger chipig/kratzig, mehr klarer, luftiger, orgeliger Grundcharakter.
- Bestehende sakrale/organartige Presets lokal nachgeschärft und neues Preset **Kristall Bach** ergänzt.
- Lokalen Bugfix ergänzt: `AeternaEngine.get_formula_status()` nachgezogen, damit die Formelstatus-Anzeige im Widget keinen AttributeError mehr wirft.
- Weiterhin nur **AETERNA** geändert; keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

## v0.0.20.303
- AETERNA lokal um eine **Formel-Infozeile** erweitert.
- Die Infozeile zeigt jetzt klar: **Beispiel im Feld**, **manuell geändert**, **angewendet** oder **noch nicht angewendet**.
- Der Status bleibt rein lokal im AETERNA-Widget und wird mit dem lokalen Instrument-State mitgespeichert.

## v0.0.20.302

- AETERNA lokal um eine klare **"Jetzt lokal freigegeben"-Karte** für stabile Automationsziele erweitert.
- Freigegeben und sichtbar gruppiert: **Direkt auf Knobs**, **Modulations-Rates** und **Depth/Amounts**.
- Die bereits vorhandene sichere Anbindung an das DAW-Automationssystem wird jetzt im Widget klar erklärt: **Rechtsklick auf einen AETERNA-Knob → Show Automation in Arranger**.
- Knob-Tooltips weisen lokal zusätzlich auf die Automationsnutzung hin.
- Keine Änderungen am globalen DAW-Core, Playback-Core, Arranger, Clip Launcher, Audio Editor, Mixer oder Transport.

---

## v0.0.20.301

- AETERNA lokal um eine kompakte **Automation-Zielkarte** erweitert.
- Spätere sichere Ziele jetzt lesbar gruppiert: **Klang**, **Raum/Bewegung**, **Modulation**, **Web**.
- Zusätzlicher Hinweis im Widget: später vorzugsweise **Knobs/Rates/Amounts** automatisieren, nicht flüchtige UI- oder rohe Phasen-Zustände.
- Keine Änderungen am globalen DAW-Core.

---

## v0.0.20.300 — AETERNA kompakte Badge-/Kurzansicht für Preset-Metadaten

- Lokale **Badge-/Kurzansicht** direkt im AETERNA-Widget ergänzt.
- Zeigt kompakt **Favorit**, **Kategorie**, **Charakter**, **Tags** und eine gekürzte **Notiz** an.
- Badge-Ansicht aktualisiert sich bei Änderungen der lokalen Preset-Metadaten sofort.
- Weiterhin nur **AETERNA** geändert, ohne Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.
---

## v0.0.20.299 — AETERNA lokale Preset-Metadaten mit Tags/Favorit

- Lokale **Preset-Metadaten** in AETERNA um **Tags** und **Favorit** erweitert.
- Tags werden lokal als kurze Liste normalisiert und dedupliziert.
- Favorit-Status läuft lokal in **AETERNA-State** und **Preset-Snapshot** mit.
- Phase-3a-Metadaten-Zeile zeigt jetzt zusätzlich **Favorit** und **Tags** lesbar an.
- State-Schema auf **Version 5**, Preset-Schema auf **Version 3** angehoben.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.
---

## v0.0.20.298 — AETERNA Formel-Startkarte / Onboarding-Hilfe

- Lokale **Formel-Startkarte** direkt im AETERNA-Formelbereich ergänzt.
- Vier sichere lokale **Startbeispiele** eingebaut: **Warm Start**, **Sakral**, **Chaos** und **Glitch**.
- Beispiele schreiben nur das **Formelfeld lokal vor**; der Klang ändert sich weiterhin erst nach **"Formel anwenden"**.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

---

## v0.0.20.297 — AETERNA Formel-Editor-Fix + lokale Preset-Metadaten

- Das AETERNA-Formelfeld ist jetzt wieder **praktisch beschreibbar**: statt einer knappen Ein-Zeile wird ein **mehrzeiliges lokales Edit-Feld** verwendet.
- Token-Einfügen per **Klick** und **Drag&Drop** funktioniert weiter im mehrzeiligen Formelbereich.
- Lokale **Preset-Metadaten** ergänzt: **Kategorie**, **Charakter** und **Notiz** direkt im AETERNA-Widget.
- Preset-Metadaten werden lokal in **AETERNA-State** und **Preset-Snapshot** mitgeführt.
- State-Schema auf **Version 4**, Preset-Schema auf **Version 2** angehoben.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

---

## v0.0.20.295 — AETERNA Formel-Aliase + sichtbare Formel-Mod-Slots

- Lokale sichere Formel-Aliase ergänzt: **$VEL**, **$NOTE**, **$T_REM**, **$T_REMAINING**, **$GLITCH**.
- Sichere lokale Formel-Funktionen ergänzt: **rand(t)** und **random()**.
- Formelbereich zeigt jetzt lesbar die **aktiven Formelquellen** und eine kurze **Alias-Ansicht**.
- UI-State-Schema auf **Version 4** angehoben.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

---


## v0.0.20.293 — AETERNA Phase 3a Preset A/B + lesbare Automation-Zielsektionen

- Lokale **Preset-A/B**-Aktionen ergänzt: **Store A**, **Store B**, **Recall A**, **Recall B**, **Compare A/B**.
- Phase-3a-Bereich zeigt lokale Automation-Ziele jetzt lesbarer in vier Gruppen: **Klang**, **Raum/Bewegung**, **Modulation**, **Web**.
- Preset-A/B-Zustände werden lokal im AETERNA-Instrumentzustand mitgespeichert.
- UI-State-Schema auf **Version 3** angehoben.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

---

## v0.0.20.294 — AETERNA Phase 3a Formel-Modulationshilfen

- Lokales **Formel-Insert-System** ergänzt: **LFO1**, **LFO2**, **MSEG**, **CHAOS**, **ENV** und **VEL** können per **Klick** oder **Drag&Drop** in die Formel eingefügt werden.
- Neue **Quick-Snippets** für typische Modulationsideen direkt im Formelbereich.
- Formel-Engine akzeptiert jetzt zusätzlich die lokalen Formelquellen **lfo1**, **lfo2**, **mseg** und **chaos_src**.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.


---

## v0.0.20.305 — AETERNA Klang-/Preset-Pack safe

- AETERNA lokal um vier neue kuratierte Startpresets erweitert: **Bach Glas**, **Celesta Chapel**, **Choral Crystal** und **Abendmanual**.
- Bestehende sakrale/kristalline Richtung weiter geschärft, weiterhin nur in **AETERNA**.
- Lokale Voicing-Mischung vorsichtig geglättet, damit spektrale/formelbasierte Klänge weniger chipig und klarer/kristalliner wirken.
- Preset-Metadaten für die neuen AETERNA-Presets ergänzt (Kategorie, Charakter, Notiz, Tags/Favorit lokal).
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

---

## v0.0.20.310 — AETERNA Web-A/Web-B-Startvorlagen

- Neue lokale **Web-Startvorlagen** direkt im Bereich **THE WEB (LOCAL SAFE)**: **Langsam**, **Lebendig**, **Organisch**, **Sakral**.
- Vorlagen setzen nur sichere lokale AETERNA-Werte für **mod1/mod2 source**, **target**, **amount** sowie **LFO/MSEG-Rates**.
- Neue kompakte **Web-Vorlagen-Karte** zeigt aktive Vorlage plus Kurzansicht von **Web A** und **Web B**.
- Manuelle Abweichungen werden lokal als **Eigen** erkannt.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.


## v0.0.20.313 — AETERNA lokale Snapshot-Karte

- Neue lokale Snapshot-Karte in AETERNA für **Klang / Formel / Web** mit drei Slots: **A / B / C**.
- Pro Slot gibt es **Store** und **Recall**, nur lokal im AETERNA-Widget.
- Snapshot speichert nur sichere AETERNA-Zustände: Preset, Formel, Web-Template/Intensität, Web A/B, wichtige Klang- und Rate-Knobs.
- Snapshot-Slots werden im **Instrument-State** mit dem Projekt gespeichert und beim Laden wiederhergestellt.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

---

## v0.0.20.322 — AETERNA Snapshot-Last-Action-Hinweis

- Lokale Snapshot-Karte in AETERNA um eine kompakte **„Zuletzt: Store/Recall …“**-Hinweiszeile erweitert.
- Die Zeile zeigt direkt **Aktion**, **Slot**, **Preset**, **Hörbild**, **Formelhinweis** und **Web-Startweg/Intensität**.
- Hinweis bleibt rein lokal im AETERNA-Widget und wird mit dem lokalen Instrument-State im Projekt gespeichert und beim Laden wiederhergestellt.
- Zusätzlich wird die Hinweiszeile bei Snapshot-Store/Recall automatisch mit der bestehenden Snapshot-Karte synchronisiert.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.

## v0.0.20.323 — AETERNA Composer + Snapshot-Slot-Kurznamen

- Lokalen **AETERNA Composer (LOCAL SAFE)** direkt im Widget ergänzt.
- Neuer **Dreiecks-/Menü-Button** erzeugt MIDI-Clips direkt auf der aktuellen **AETERNA-Spur** oder überschreibt den aktiven Clip dieser Spur.
- Breiter lokaler **Weltstil-Katalog** mit freier Eingabe ergänzt; zwei Stile können gemischt werden (**Style A × Style B**).
- Mathematische/deterministische Seed-Logik via Hash/PRNG ergänzt; **Seed**, **Style-Mix**, **Bars**, **Grid**, **Swing**, **Dichte** und **Mix** bleiben lokal im AETERNA-State gespeichert.
- Neue Voice-Schalter nur für **Bass**, **Melodie**, **Lead**, **Pad** und **Arp**; ausdrücklich **keine Drums**.
- Umsetzung nutzt nur bestehende sichere Projekt-APIs für **MIDI-Clip-Erzeugung** und **MIDI-Noten-Schreiben**; kein Eingriff in Playback-Core, Arranger, Clip Launcher, Audio Editor, Mixer oder Transport.
- Lokale **Snapshot-Slot-Kurznamen** ergänzt und zusätzlich in Schnellaufrufen sichtbar gemacht.



## v0.0.20.325 — AETERNA sichtbare Ladezeit + feinere Composer-Profile

- Lokale **Ladeprofil-Anzeige** direkt im AETERNA-Widget ergänzt.
- Sichtbar gemacht werden **Build**, **Restore** und der letzte **staged UI refresh**; alles rein lokal als Widget-/Restore-Messung.
- AETERNA Composer lokal um **Phrasenprofile** erweitert: **Sehr getragen**, **Getragen**, **Ausgewogen**, **Belebt**, **Sehr belebt**.
- AETERNA Composer lokal um **Dichteprofile** erweitert: **Luftig**, **Offen**, **Mittel**, **Dicht**, **Schimmernd**.
- Die neuen Profile wirken nur lokal auf **Notendichte**, **Notenlängen** und **Arp-/Lead-/Pad-Verhalten** für **Bass / Melodie / Lead / Pad / Arp**.
- Neue Composer-Profile werden im lokalen **AETERNA-State** gespeichert und beim Projektladen wiederhergestellt.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder Playback-Core.


## v0.0.20.326 — Bounce in Place / Freeze Track (erste sichere Workflow-Stufe)

- Erste sichere **Bounce-in-Place**-Stufe ergänzt: Im Arranger-Kontextmenü können ausgewählte Clips jetzt auf **eine neue Audiospur** gebounced werden (**+FX**, **Dry**, optional **Quelle stummschalten**).
- Erste sichere **Freeze-Track**-Stufe ergänzt: Im Track-Kontextmenü können Spuren jetzt als **Audio-Proxy** auf eine neue Audiospur gebounced und die Quellspur(en) dabei **stumm/Instrument aus** geschaltet werden.
- Wenn eine Spur bereits zu einer **Track-Gruppe** gehört, ist zusätzlich ein erster **Gruppe einfrieren**-Eintrag im Track-Kontextmenü verfügbar.
- Für Freeze-Proxys gibt es einen ersten **Auftauen-/Reaktivieren**-Weg: **Freeze-Quellen wieder aktivieren** im Track-Kontextmenü der Proxy-Spur.
- Umsetzung bleibt projekt-/UI-seitig: neue Offline-Render-Helfer in `ProjectService`, neue Arranger-/Track-Kontextmenü-Einträge; **kein** Umbau von Arranger-Core, Playback-Core, Mixer oder Transport.
- AETERNA lokal zusätzlich um **breitere mathematische Formel-/Random-Familien** in Hilfe und Randomizer ergänzt (z. B. env/coherent/cloud/logistic/brown-artige Startideen), weiterhin nur im Widget.


## v0.0.20.327 — Bounce/Freeze-Dialoge + sichtbare Freeze-Marker + breitere AETERNA-Math-Familien

- Neue kleine **Bounce/Freeze-Dialoge** für Clip-Bounce, Track-Freeze/Bounce und Group-Freeze ergänzt.
- Dialoge erlauben jetzt lokal/gezielt: **Label**, **+FX/Dry** sowie optional **Quelle stummschalten/deaktivieren**.
- **TrackList** zeigt jetzt sichtbare **Freeze-Marker** für **Proxy-Spuren** und **Freeze-Quellspuren** inklusive Tooltip.
- Laufzeitfehler in der ersten Bounce-Stufe lokal behoben: sichere Label-Verwendung für neu erzeugte Audio-Clips bei Clip-/Track-Bounce.
- AETERNA lokal um weitere **Math-/Random-Familien** in Formelhilfen, Onboarding und Randomizer erweitert (z. B. harmonic lattice, pink bloom, lorenz breath, sample hold veil, tent lattice, modal drift).
- Keine Änderungen an Playback-Core, Mixer-Engine, Transport oder globaler Audio-Architektur.

## v0.0.20.329 — AETERNA Mod-Rack Amount/Polarität + Signalfluss-Karte

- AETERNA **Web A / Web B** lokal um echte **Polaritätsumschaltung (+ / −)** erweitert; bleibt vollständig auf das interne Instrument begrenzt.
- Mod-Rack-Karte zeigt pro Slot jetzt **Amount + Polarität + kleine Balkenanzeige**.
- Neue lokale **Signalfluss-Linienansicht** ergänzt, die aktive Wege wie **Quelle → Web A/B → Ziel** direkt sichtbar macht.
- Polarity bleibt im lokalen AETERNA-State gespeichert und wird beim Projektladen wiederhergestellt.
- Zusätzlich ein sicherer **Stufenplan** für die größere gewünschte AETERNA-Synth-Erweiterung dokumentiert: erst UI-/Stage-Plan, dann Filter, dann weitere Wunschfamilien wie Unison/Sub/Shape/Noise/Glide/Drive — ausdrücklich **nicht alles in einem riskanten Schritt**.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

## v0.0.20.330 — AETERNA Synth Panel Stage 1 (safe UI grouping)

- Neuer lokaler Bereich **AETERNA SYNTH PANEL (STAGE 1 SAFE)** direkt im Widget.
- Vorhandene stabile Parameter werden dort lesbarer gruppiert in **Core Voice**, **Space / Motion** und **Mod / Web**.
- Kleine Navigations-Buttons öffnen direkt die bereits vorhandenen Bereiche **ENGINE**, **MORPHOGENETIC CONTROLS**, **THE WEB** und **MOD RACK / FLOW**.
- Neue kompakte Statuskarten zeigen die aktuellen Werte der bereits vorhandenen stabilen AETERNA-Parameter inklusive **Web A / Web B**-Kurzansicht.
- Zusätzlich wurden bewusst deaktivierte **Preview-/Platzhalterfelder** für spätere sichere Ausbaustufen ergänzt (z. B. **Filter Type**, **Envelope**, **Layer**, **Unison/Sub/Noise**), damit die UI-Richtung klar ist ohne neue Audio-Engine-Risiken.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalem Playback-Core.

## v0.0.20.331 — AETERNA Filter Stage 2 (größerer sicherer Ausbau)

- Echter lokaler **AETERNA-Filterblock** ergänzt: **Cutoff**, **Resonance** und **Type** (**LP 12 / LP 24 / HP 12 / BP / Notch / Comb+**).
- Filter sitzt vollständig **innerhalb von AETERNA**; kein Eingriff in Arranger, Clip Launcher, Audio Editor, Mixer, Transport oder globalen Playback-Core.
- Neue echte Filter-Bedienung im **AETERNA SYNTH PANEL** statt nur Preview-Platzhalter.
- **Filter Cutoff** und **Filter Resonance** sind jetzt als stabile **Automation-Ziele** sichtbar und direkt über die vorhandenen Automation-Wege nutzbar.
- **Web A / Web B** können jetzt lokal auch auf **Filter Cutoff** und **Filter Resonance** zielen.
- Neue Filter-Zustände werden mit dem **AETERNA-State** gespeichert und beim Projektladen wiederhergestellt; Snapshot-/Randomize-Pfade wurden lokal mitgezogen.
- Signalfluss-/Synth-Panel-Hinweise wurden lokal erweitert, damit die größere Ausbau-Richtung sichtbarer wird.



## v0.0.20.332 — AETERNA Voice Family + AEG/FEG ADSR (größerer Familien-Block)

- Größeren lokalen **Voice-Block** in AETERNA ergänzt: **Pan**, **Glide**, **Stereo-Spread** und **Retrig**.
- **Pan / Glide / Stereo-Spread** sind als stabile **Automation-Ziele** und lokale **Mod-Rack-Ziele** innerhalb von AETERNA verfügbar; **Retrig** bleibt in dieser sicheren Stufe als lokaler Schalter umgesetzt.
- Größeren lokalen **Envelope-Block** ergänzt: **AEG ADSR** und **FEG ADSR** inklusive **FEG Amount**.
- AEG steuert jetzt lokal die Amplituden-Hüllkurve, FEG formt lokal den Filterverlauf (Cutoff/Resonance) – alles innerhalb von AETERNA ohne Eingriff in DAW-Core, Arranger, Mixer oder Transport.
- Neue Familien wurden im **AETERNA SYNTH PANEL** sichtbar gruppiert, inklusive Statuskarten, erklärender Hinweise und weiterhin einklappbarer Struktur.
- Save/Load, Snapshot und Randomize lokal mitgezogen; bestehende AETERNA-Zustände bleiben kompatibel durch konservative Defaults.
- Zusätzlich eine kleine lokale Runtime-Lücke in der aktuellen AETERNA-Engine geschlossen: fehlende interne **LFO-/MSEG-Helfer** ergänzt, damit der reine Engine-Pull-Pfad wieder lokal ausführbar ist.

## v0.0.20.333 — AETERNA Unison / Sub / Noise (größerer Familien-Block)

- Größeren lokalen **Layer-Block** in AETERNA ergänzt: **Unison / Sub / Noise**.
- Neue echte Klangparameter: **Unison Mix**, **Unison Detune**, **Sub Level**, **Noise Level**, **Noise Color**.
- Neue lokale Comboboxen: **Unison Voices** (**1 / 2 / 4 / 6**) und **Sub Oktave** (**-1 / -2**).
- Stabile kontinuierliche Ziele **Unison Mix / Unison Detune / Sub Level / Noise Level / Noise Color** sind jetzt im AETERNA-Kontext als Automation-/Mod-Rack-Ziele verfügbar.
- Umsetzung bleibt vollständig lokal in **AETERNA Engine + Widget**; kein Eingriff in Arranger, Mixer, Transport oder globalen Playback-Core.
- Save/Load, Snapshot und Randomize für die neue Familie lokal mitgezogen.
- Engine-Smoketest ohne GUI lief sauber für **note_on() / pull() / note_off()** mit aktivem Unison/Sub/Noise-Block.



## v0.0.20.334 — AETERNA Pitch/Shape/Pulse Width + Drive/Feedback (größerer Familien-Block)

- Größeren lokalen **Pitch/Timbre-Block** in AETERNA ergänzt: **Pitch**, **Shape** und **Pulse Width**.
- **Pitch** wirkt jetzt lokal als musikalische globale Tonhöhen-Verschiebung (zentriert um 50%), bleibt aber vollständig innerhalb von AETERNA.
- **Shape** morpht lokal die Wellenform zwischen eher **sine/triangle** und **saw/square**-artigen Verläufen.
- **Pulse Width** steuert lokal die Pulsbreite des Rechteckanteils und damit den Vokal-/Nasalcharakter.
- Größeren lokalen **Drive/Feedback-Block** ergänzt: **Drive** und **Feedback** mit echter Audio-Wirkung innerhalb von AETERNA.
- **Drive** erweitert lokal die Sättigung/Bissigkeit, **Feedback** fügt kontrollierte interne Rückkopplung hinzu — ohne den DAW-Core, Mixer oder Transport anzutasten.
- Neue kontinuierliche Ziele **Pitch / Shape / Pulse Width / Drive / Feedback** sind jetzt im AETERNA-Kontext als stabile **Automation-** und **Mod-Rack-Ziele** verfügbar.
- Familien wurden direkt im **AETERNA SYNTH PANEL** sichtbar ergänzt, inklusive neuer Statuskarten und erweitertem Automation-Schnellzugriff.
- Save/Load, Snapshot und Randomize lokal mitgezogen; bestehende AETERNA-Zustände bleiben kompatibel durch konservative Defaults.
- Engine-Smoketest ohne GUI lief sauber mit den neuen Familien (**note_on / pull / note_off**).

## v0.0.20.335 — AETERNA Visual Polish + sichtbare Familienkarten

- Größeren lokalen **AETERNA-Polish-Block** umgesetzt: deutlichere **Farbtrennung** zwischen Core, Filter, Voice, AEG, FEG, Layer, Timbre und Drive.
- Neue kleine **Familien-Legende** direkt im **AETERNA SYNTH PANEL**, damit die großen Familien schneller lesbar und farblich unterscheidbar sind.
- Neue kleine **grafische Signalfluss-Ansicht** im Bereich **MOD RACK / FLOW**: Audio-Pfad und Mod-Pfad werden jetzt als lokale Linien-/Kartenübersicht sichtbar dargestellt.
- Bestehende Zusammenfassungs-Karten (**Overview, Core, Space, Mod, Future, Filter, Voice, AEG, FEG, Unison/Sub, Noise/Color**) farblich getönt und klarer getrennt.
- Bisher im State/Update schon angelegte Familien **Pitch / Shape / Pulse Width** sowie **Drive / Feedback** jetzt auch als echte **sichtbare Karten mit Knobs** im **AETERNA SYNTH PANEL** ergänzt.
- Umsetzung bleibt vollständig lokal in **pydaw/plugins/aeterna/aeterna_widget.py**; kein Eingriff in Arranger, Playback-Core, Mixer, Transport oder andere Instrumente.


## v0.0.20.336 — AETERNA Layer-Toggles + Mod-Badges/Mini-Meter

- Irreführende Vorschau-Checkboxen im **AETERNA SYNTH PANEL** für **Unison / Sub / Noise** in echte lokale **Layer-Schnellschalter** umgebaut.
- Die drei Schalter greifen jetzt direkt auf die realen Layer-Level **Unison Mix / Sub Level / Noise Level** zu und schalten diese sicher an/aus, ohne Playback-Core oder andere Instrumente anzufassen.
- Letzter sinnvoller Layer-Wert wird lokal gemerkt, sodass ein erneutes Einschalten nicht hart bei 0 startet.
- **Familienkarten** im Synth-Panel zeigen jetzt zusätzlich kompakte **Mini-Meter** und **aktive Mod-Ziel-Badges** pro Familie (z. B. Web A/B auf Filter-, Voice-, Layer- oder Drive-Ziele).
- Umsetzung bleibt vollständig lokal in `pydaw/plugins/aeterna/aeterna_widget.py`.


## v0.0.20.337 — AETERNA Arp A + Per-Knob Mod-Menüs + Readability

- Lokalen **AETERNA Arp A (LOCAL SAFE)** ergänzt: als **sicherer Clip-Arpeggiator** für die aktuelle AETERNA-Spur, ohne Playback-Core-Umbau.
- Arp A bietet jetzt **Pattern** (u. a. up/down/chords/random/flow/blossom/low&up/hi&down), **Rate** (1/1 bis 1/64), **Straight/Dotted/Triplets** und **16 editierbare Steps**.
- Pro Step vorhanden: **Transpose**, **Skip**, **Velocity** und **Gate Length 0–400%**.
- Lokale **Shuffle**-Option für Arp A ergänzt, inklusive Anzahl der betroffenen Steps.
- Arp A kann direkt als **neuen MIDI-Clip** auf der aktuellen AETERNA-Spur schreiben oder den **aktiven Clip überschreiben**.
- Rechtsklick-Kontextmenü auf **allen AETERNA-Knobs** erweitert: **Show Automation in Arranger** plus **Add Modulator** direkt auf den angeklickten Ziel-Knob.
- Neue lokale **Per-Knob-Mod-Profile** eingeführt: jeder AETERNA-Knob kann seinen eigenen gespeicherten Modulator-Zustand behalten, statt einen gemeinsamen Platzhalterzustand zu teilen.
- Lesbarkeit in AETERNA lokal verbessert: **größere Karten-/Hint-Schriften**, **größere Controls** und **deutlichere Signalfluss-Karten**.
- Umsetzung bleibt vollständig lokal in `pydaw/plugins/aeterna/aeterna_widget.py`; kein Eingriff in Arranger, Mixer, Transport, Audio Editor oder globalen Playback-Core.


## v0.0.20.340 — AETERNA Layer-Visibility + Qt Selection Guard

- **Layer-/Noise-Familienkarten** in AETERNA zeigen jetzt **Unison Voices** und **Sub Oktave** klarer direkt in den Karten und im Preview-Hinweis.
- **AETERNA Live-ARP Refresh** wurde lokal koalesziert, damit Checkbox-Klicks nicht mehrere direkte verschachtelte Refresh-Wellen durch die UI jagen.
- **ARP-Live-Sync** besitzt jetzt einen lokalen **Reentrancy-Guard** und emittiert Projekt-Refresh nur noch bei echten State-Änderungen.
- **TrackList**, **Arranger-TrackList** und **Automation-Lanes** wurden um kleine **Refresh-/Signalguards** ergänzt, damit `QListWidget`-Selektionen während Refresh/Restore nicht rekursiv `setCurrentRow`/`setCurrentItem` auslösen.
- Umsetzung bleibt vollständig lokal in AETERNA/UI; kein Eingriff in Playback-Core, Mixer, Transport oder Arranger-Engine.

## v0.0.20.377 — VST3 Editor Stability Fixes (2026-03-10)

**Bug 1 — `RuntimeError: wrapped C/C++ object of type QPushButton has been deleted`**
- Root cause: `_on_editor_process_finished()` and `_on_editor_process_error()` tried to
  call `btn.setText()` AFTER the widget (and its child QPushButton) was already destroyed
  by Qt — e.g. when the Device panel was closed while an editor was open.
- Fix in `fx_device_widgets.py`: All `btn.setText/setEnabled/setStyleSheet` calls wrapped
  in `try/except RuntimeError`. Same guard added to `_on_editor_stdout` ready-event handler.
  `_on_editor_process_error` now also catches RuntimeError from `_show_editor_error`.

**Bug 2 — `QProcess: Destroyed while process is still running`**
- Root cause: `closeEvent` called `proc.kill()` but did NOT disconnect QProcess signals first.
  After widget deletion, `finished` / `errorOccurred` signals still fired against the dead
  widget, causing the RuntimeError above as a secondary effect.
- Fix: `closeEvent` now disconnects ALL QProcess signals (`readyReadStandardOutput`,
  `finished`, `errorOccurred`) BEFORE terminating, using `terminate()` → `waitForFinished(500)`
  → `kill()` sequence.

**Bug 3 — Native editor param changes not reflected in PyDAW sliders (no movement)**
- Root cause: `_snapshot_params()` in `vst_gui_process.py` used `dir(plugin)` + `getattr()`
  to enumerate numeric attributes — completely bypassing pedalboard's official parameter API.
  This never returned actual plugin parameter values, so the `_ParamPoller` never emitted
  any `param` events.
- Fix: `_snapshot_params()` rewritten to use `plugin.parameters` dict
  (name → `AudioProcessorParameter`) and `param.raw_value` for current value.
  Fallback to `getattr(plugin, name)` only for older pedalboard builds without `raw_value`.

Files changed: `pydaw/audio/vst_gui_process.py`, `pydaw/ui/fx_device_widgets.py`

## v0.0.20.378 — VST3 Sliders + Audio-Params Fix (2026-03-10)

**Bug 1 — Alle VST3-Parameter erscheinen als Checkbox (keine Slider)**
- Root cause: `_extract_param_infos()` in vst3_host.py enthielt eine Heuristik:
  `if not is_bool and mx - mn <= 1.0 and mx == 1.0 and mn == 0.0: is_bool = True`
  Da pedalboard ALLE VST3-Parameter normalisiert auf [0.0, 1.0] meldet (minimum_value=0.0,
  maximum_value=1.0), wurde jeder kontinuierliche Parameter (time_ms, lpf_hz, feedback …)
  fälschlicherweise als Boolean klassifiziert und als Checkbox gerendert.
- Fix: Heuristik entfernt. Nur noch `param.is_boolean` aus pedalboard wird verwendet.

**Bug 2 — VST3-Plugins laden aber wirken sich nicht auf Audio aus**
- Root cause: `_apply_rt_params()` verwendete `setattr(plugin, name, val)` mit dem
  normalisierten 0-1 Wert aus dem RTParamStore. pedalboard's setattr() erwartet aber
  den *physikalischen* Wert (z.B. 500.0 für 500 ms). Das Setzen von 0.5 für "time_ms"
  ergab also 0.5 ms — nahezu Null, weshalb alle Plugins wirkungslos erschienen.
- Fix: `_apply_rt_params()` verwendet jetzt `plugin.parameters[name].raw_value = val`
  (normalisierter 0-1 Setter). Für Boolean-Params weiterhin setattr(plugin, name, True/False).
- Gleiches Fix in `get_current_values()` (raw_value statt getattr) und
  `vst_gui_process.py` `set_param`-Handler.

Files changed: `pydaw/audio/vst3_host.py`, `pydaw/audio/vst_gui_process.py`

## v0.0.20.379 — VST3 Editor In-Process: Echte Meter/Analyser (2026-03-10)

**Problem: Nativer Editor zeigt keine Pegel / Spectrum-Anzeige**
- Root cause: Der bisherige Subprocess-Ansatz lud eine SEPARATE Plugin-Instanz nur
  um die GUI anzuzeigen. Diese Instanz bekam niemals Audio → alle Meter/Analyser
  (Spectrum, VU, Loudness-Graph) zeigten nichts.

**Lösung: In-Process QThread (_VstInProcessEditorThread)**
- Neue Klasse `_VstInProcessEditorThread(QThread)` ruft `show_editor()` direkt auf
  dem Plugin-Objekt der `Vst3Fx`-Instanz auf, die echtes Audio prozessiert.
- Zugriffspfad: `services.audio_engine._track_audio_fx_map[track_id].devices`
  → `Vst3Fx` mit passendem `device_id` → `._plugin` (pedalboard plugin object)
- Selbe Plugin-Instanz = native Editor sieht den echten Audio-Datenstrom → Meter ✓

**Bidirektionale Param-Sync im In-Process-Modus**
- `_editor_poll_timer` (80ms): liest `plugin.parameters[name].raw_value`,
  vergleicht mit RT-Store, ruft `_apply_param_from_editor()` bei Änderungen.

**Fallback**
- `_get_vst3_fx_instance()` gibt None zurück wenn Engine nicht erreichbar →
  automatischer Fallback auf den bisherigen QProcess-Subprocess (unverändert).

**Kein Code gelöscht**: Alle bestehenden Subprocess-Methoden bleiben vollständig
erhalten als Fallback-Pfad.

Files changed: `pydaw/ui/fx_device_widgets.py` (neuer Thread, neue Methoden,
               erweiterter closeEvent)

## v0.0.20.490 — SmartDrop: Morphing-Guard Runtime-Snapshot-Handles (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py` baut jetzt konkrete `runtime_snapshot_handles` samt `handle_key`, `handle_kind`, `owner_scope`, `owner_ids`, `capture_state` und `capture_stub` auf.
- Die Apply-Readiness enthaelt jetzt einen zusaetzlichen Check fuer bereits vorverdrahtete Runtime-Snapshot-Handles.
- `pydaw/ui/main_window.py` zeigt einen neuen Abschnitt **Runtime-Snapshot-Handle-Vorschau** und fuehrt die Handle-Zusammenfassung auch im Guard-Dialog-Infotext.
- Kleiner UI-Hotfix nebenbei: Variablen-Ueberschattung im Guard-Dialog bereinigt, damit `Zielspur:` wieder sicher die eigentliche Spurzusammenfassung anzeigt.



## v0.0.20.495 — SmartDrop: Morphing-Guard Dry-Run Runner (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py` koppelt das Snapshot-Bundle jetzt an einen read-only Dry-Run-/Transaktions-Runner mit `runner_key`, Capture-/Restore-/Rollback-Sequenzen und `phase_results`.
- Die Apply-Readiness enthaelt jetzt einen zusaetzlichen Check fuer den vorbereiteten Dry-Run-Runner.
- `pydaw/ui/main_window.py` zeigt einen neuen Abschnitt **Read-only Dry-Run / Transaktions-Runner** und fuehrt die Dry-Run-Zusammenfassung im Guard-Dialog-Infotext.

## v0.0.20.496 — SmartDrop: Morphing-Guard Safe-Runner Dispatch (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py` dispatcht Capture-/Restore-Phasen jetzt ueber konkrete read-only Preview-Funktionen je Snapshot-Typ (`capture_track_state_snapshot`, `capture_routing_snapshot`, `restore_*` usw.) statt nur ueber generische Platzhaltertexte.
- Der Dry-Run-Bericht enthaelt jetzt zusaetzlich `capture_method_calls`, `restore_method_calls` und `runner_dispatch_summary`, sodass sichtbar ist, welche Safe-Runner-Methoden bereits zentral vorverdrahtet sind.
- `pydaw/ui/main_window.py` zeigt diese neuen Safe-Runner-Dispatch-Infos im bestehenden Block **Read-only Dry-Run / Transaktions-Runner** mit an.



## v0.0.20.498 — SmartDrop: Morphing-Guard State-Carriers (2026-03-16)

- `pydaw/services/smartdrop_morph_guard.py` koppelt Runtime-Stubs jetzt an konkrete read-only Zustandstraeger / State-Carrier mit eigener Payload-Vorschau.
- Der Dry-Run ruft jetzt `capture_state_preview()` / `restore_state_preview()` / `rollback_state_preview()` ueber die Carrier auf und fuehrt `state_carrier_calls` plus `state_carrier_summary` im Plan mit.
- `pydaw/ui/main_window.py` zeigt die neue Ebene als **Runtime-Zustandstraeger / State-Carrier** an und fuehrt die Carrier-Infos auch im Dry-Run-Detailblock.

## v0.0.20.501 — Runtime-State-Slots / Snapshot-State-Speicher

- Runtime-State-Halter wurden an konkrete read-only **Runtime-State-Slots / Snapshot-State-Speicher** gekoppelt.
- Der Safe-Runner nutzt jetzt `capture_slot_preview()` / `restore_slot_preview()` / `rollback_slot_preview()` direkt ueber die neuen Slot-Klassen.
- Der Guard-Dialog zeigt die neue Slot-Ebene sowie die neuen Dry-Run-Dispatch-Infos sichtbar an.

## v0.0.20.503 — Runtime-State-Registries / Handle-Speicher

- Runtime-State-Stores wurden an konkrete read-only **Runtime-State-Registries / Handle-Speicher** gekoppelt.
- Der Safe-Runner nutzt jetzt `capture_registry_preview()` / `restore_registry_preview()` / `rollback_registry_preview()` direkt ueber die neuen Registry-Klassen.
- Der Guard-Dialog zeigt die neue Registry-Ebene sowie die neuen Dry-Run-Dispatch-Infos sichtbar an.
