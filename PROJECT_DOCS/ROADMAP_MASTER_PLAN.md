# 🎯 Py_DAW ROADMAP — Weg zur Open-Source-Referenz-DAW

**Projekt:** Py_DAW (ChronoScaleStudio)
**Vision:** Open Source, erweiterbar, Python-scriptbar, Linux-first
**Erstellt:** 2026-03-19 (v0.0.20.626, aktualisiert v0.0.20.630)
**Autor:** Anno (Lead Developer) + Claude Opus 4.6

---

## ⚠️ OBERSTE DIREKTIVE — FÜR ALLE KOLLEGEN

```
🔴 DU DARFST NICHTS KAPUTT MACHEN. DAS IST DIE OBERSTE DIREKTIVE.
🔴 "Nichts kaputt machen" bedeutet: Alle bestehenden Features müssen
   nach deiner Arbeit exakt so funktionieren wie vorher.
🔴 Teste IMMER mit python3 -c "import py_compile; ..." vor dem ZIP.
🔴 Im Zweifel: NICHT ändern. Lieber fragen.
```

## 📦 ZIP-WORKFLOW — PFLICHT FÜR JEDEN KOLLEGEN

```bash
# 1. ZIP entpacken (DIREKT im Verzeichnis arbeiten!)
unzip Py_DAW_vX_X_XX_XXX_TEAM_READY.zip -d work
cd work

# 2. NIEMALS vom falschen Pfad ausgehen!
#    Prüfe IMMER: ls pydaw/  ← muss existieren

# 3. Nach Arbeit: VERSION erhöhen, ZIP bauen
echo -n "0.0.20.XXX" > VERSION
zip -r /path/Py_DAW_v0_0_20_XXX_TEAM_READY.zip \
  pydaw pydaw_engine PROJECT_DOCS docs *.py *.md *.txt VERSION *.sh \
  -x "*.pyc" "*__pycache__*" "*.egg-info*" "*/.git/*" "*/node_modules/*" "*/target/*"

# 4. ZIP verifizieren
cd /tmp && mkdir verify && cd verify
unzip -q /path/Py_DAW_v0_0_20_XXX_TEAM_READY.zip
python3 -c "import py_compile; py_compile.compile('pydaw/ui/main_window.py', doraise=True); print('OK')"
```

---

## 🏗️ ARBEITSPAKET 1: Rust/C++ Audio-Core (HÖCHSTE PRIORITÄT)

### Warum?
Pythons GIL (Global Interpreter Lock) verhindert echtes Multi-Thread Audio-Rendering.
Bei 20+ Tracks mit Plugins wird die CPU zum Bottleneck. Bitwig/Ableton/Cubase
rendern Audio in C++ mit Lock-Free-Ringbuffern und Thread-Pools.

### Zielarchitektur

```
┌─────────────────────────────────────┐
│  Python/PyQt6 GUI (wie bisher)      │
│  - Arranger, PianoRoll, Mixer, etc. │
│  - Projekt-Daten, Clips, Automation │
└──────────────┬──────────────────────┘
               │ IPC (SharedMemory / Unix Socket / gRPC)
               │ Commands: play, stop, seek, set_param, load_plugin
               │ Events:   playhead_pos, meter_levels, midi_events
               ▼
┌─────────────────────────────────────┐
│  Rust Audio-Engine (eigener Prozess)│
│  - Echtzeit Audio-Graph             │
│  - Lock-Free Ringbuffer             │
│  - Plugin-Hosting (VST3/CLAP/LV2)  │
│  - Multi-Thread Track-Rendering     │
│  - MIDI Dispatch                    │
│  - Mixer mit Send/Return Routing    │
└──────────────┬──────────────────────┘
               │ ALSA / PipeWire / JACK
               ▼
           🔊 Audio Output
```

### Phasenplan

**Phase 1A — Rust Skeleton + IPC Bridge (~2-3 Sessions)**
- [x] Neues Cargo-Projekt `pydaw_engine/` im Repository  *(v0.0.20.630)*
- [x] Grundstruktur: `main.rs`, `audio_graph.rs`, `ipc.rs`, `plugin_host.rs`  *(v0.0.20.630)*
- [x] IPC-Protokoll definieren (Protobuf oder MessagePack über Unix Socket)  *(v0.0.20.630 — MessagePack via rmp-serde)*
- [x] Python-seitig: `RustEngineBridge` Klasse die Commands sendet und Events empfängt  *(v0.0.20.630)*
- [x] Einfacher Proof-of-Concept: Sine-Wave Generator in Rust, Playhead-Position an Python  *(v0.0.20.630)*
- [x] NICHTS an der bestehenden Python-Engine ändern! Parallelbetrieb.  *(v0.0.20.630 — Feature-Flag USE_RUST_ENGINE)*

**Phase 1B — Audio-Graph in Rust (~3-5 Sessions)**
- [x] `AudioNode` Trait: `process(&mut self, buffer: &mut AudioBuffer, frames: usize)`  *(v0.0.20.631 — audio_node.rs mit ProcessContext, GainNode, SineNode, MixNode)*
- [x] `AudioGraph` mit topologischer Sortierung (wie JUCE AudioProcessorGraph)  *(v0.0.20.630 — audio_graph.rs)*
- [x] Track-Nodes: Volume, Pan, Mute/Solo  *(v0.0.20.630 — TrackNode mit atomaren Parametern)*
- [x] Master-Bus Node  *(v0.0.20.630 — TrackKind::Master, Soft-Limiter)*
- [x] ALSA/PipeWire Backend via `cpal` Crate  *(v0.0.20.630 — main.rs cpal Stream)*
- [x] Lock-Free Parameter-Updates via `crossbeam` Atomic Ringbuffer  *(v0.0.20.631 — lock_free.rs ParamRing SPSC)*
- [x] Metering: Peak/RMS pro Track → Python via IPC  *(v0.0.20.630 — MeterLevels + MasterMeterLevel Events ~30Hz)*

**Phase 1C — Plugin-Hosting in Rust (~3-5 Sessions)**
- [x] VST3 Hosting via `vst3-sys` Crate  *(v0.0.20.658 — vst3_host.rs: Scanner, Vst3PluginInfo, Vst3Instance, AudioPlugin impl, State save/load — FFI-Stubs für dlopen/IPluginFactory)*
- [x] CLAP Hosting via `clap-sys` Crate  *(v0.0.20.658 — clap_host.rs: Scanner, ClapPluginInfo, ClapInstance, AudioPlugin impl, Feature-Tags — FFI-Stubs für clap_entry)*
- [x] Plugin-Prozess-Isolation (jedes Plugin in eigenem Thread/Prozess)  *(v0.0.20.658 — plugin_isolator.rs: IsolatedPlugin Thread, panic::catch_unwind, Heartbeat Watchdog)*
- [x] Parameter-Sync: Python GUI ↔ Rust Engine ↔ Plugin  *(v0.0.20.658 — Crossbeam-Channel Commands, lock-free SetParam/GetParam)*
- [x] Plugin-State Save/Load (Base64 Blobs)  *(v0.0.20.658 — save_state()/load_state() in VST3+CLAP Instances, last_good_state für Auto-Restart)*
- [x] Crash-Recovery: Plugin-Prozess stirbt → Engine läuft weiter  *(v0.0.20.658 — PluginHealth enum, crash_count, max_crashes, auto-mute, Disabled after N crashes)*

**Phase 1D — Migration (~2-3 Sessions)**
- [x] Feature-Flag: `USE_RUST_ENGINE=true/false`  *(v0.0.20.630 — RustEngineBridge.is_enabled())*
- [x] Python-Engine bleibt als Fallback erhalten  *(v0.0.20.630 — kein Byte am bestehenden Code geändert)*
- [x] Schrittweise Migration: erst Audio-Playback, dann MIDI, dann Plugins  *(v0.0.20.662 — EngineMigrationController: 3 Subsysteme, Dependency-Chain, Hot-Swap, Cascade-Rollback, QSettings-Persistenz)*
- [x] Performance-Vergleich: Python-Engine vs Rust-Engine  *(v0.0.20.662 — EnginePerformanceBenchmark: A/B-Test, Render-Timing, P95/P99, CPU-Load, XRun-Zählung, IPC-Roundtrip, formatierter Report)*
- [x] Wenn stabil: Rust-Engine als Default  *(v0.0.20.662 — EngineMigrationController.set_rust_as_default(), nur wenn alle 3 Subsysteme stabil auf Rust)*

### Technologie-Empfehlung
- **Sprache:** Rust (Speichersicherheit, kein GC, excellentes Audio-Ökosystem)
- **Crates:** `cpal` (Audio I/O), `crossbeam` (Lock-Free), `vst3-sys`, `clack-host` (CLAP)
- **IPC:** Unix Domain Sockets + MessagePack (schnell, einfach)
- **Build:** `maturin` für Python-Bindings (PyO3) ODER reiner Socket-IPC

### Risiken
- Größtes Risiko: IPC-Latenz. Muss unter 1ms bleiben.
- Plugin-GUI: Bleibt vorerst in Python (X11 Window Embedding)
- Fallback: Python-Engine MUSS weiterhin funktionieren!

---

## 🎙️ ARBEITSPAKET 2: Audio Recording

### Aktueller Stand
Rudimentäres Recording über JACK Backend. Kein Comping, kein Punch In/Out,
keine Take-Lanes.

### Ziel-Features

**Phase 2A — Solides Single-Track Recording (~2 Sessions)**
- [x] Record-Arm Button pro Track (visuell + funktional)  *(v0.0.20.632 — Mixer R-Button + Arranger Kontextmenü, model.Track.record_arm)*
- [x] Pre-Roll / Count-In mit Metronom  *(v0.0.20.632 — RecordingService.set_count_in_bars(), finish_count_in())*
- [x] Aufnahme schreibt WAV-Datei in Projekt-Ordner  *(v0.0.20.632 — project/media/recordings/, 24-bit WAV)*
- [x] Automatische Clip-Erstellung nach Stop  *(v0.0.20.632 — on_recording_complete Callback → add_audio_clip_from_file_at)*
- [x] Input-Monitoring (Echtzeit-Abhöre des Eingangs)  *(v0.0.20.632 — get_input_level(), set_input_monitoring())*

**Phase 2B — Multi-Track Recording (~2-3 Sessions)**
- [x] Mehrere Tracks gleichzeitig aufnehmen  *(v0.0.20.636 — Multi-Track RecordingService, JACK + sounddevice)*
- [x] Input-Routing: Welcher Hardware-Input → welcher Track  *(v0.0.20.636 — Mixer ComboBox + Track.input_pair, Auto-Detection)*
- [x] Latenz-Kompensation (Plugin Delay Compensation — PDC)  *(v0.0.20.636 — PDC Framework: set/get_track_pdc_latency, Sample-Trimming)*
- [x] Buffer-Size Einstellungen (64/128/256/512/1024/2048)  *(v0.0.20.636 — AudioSettingsDialog ComboBox, Settings → RecordingService)*

**Phase 2C — Punch In/Out (~1-2 Sessions)**
- [x] Punch-Region im Arranger definieren (Start/End Marker)  *(v0.0.20.637 — rote Marker, Drag-Handles, Kontextmenü)*
- [x] Automatisches Punch In/Out bei Play  *(v0.0.20.637 — TransportService boundary detection, RecordingService auto-start/stop)*
- [x] Pre-/Post-Roll Einstellungen  *(v0.0.20.637 — SpinBoxes in Transport Panel, TransportService Pre/Post-Roll)*
- [x] Crossfade an Punch-Grenzen  *(v0.0.20.638 — AudioConfig konfigurierbar 0-100ms, Default 10ms, linear fade-in/out)*

**Phase 2D — Comping / Take-Lanes (~3-4 Sessions)**
- [x] Loop-Recording: Jeder Durchlauf wird als separater Take gespeichert  *(v0.0.20.639 — RecordingService loop-recording, on_loop_boundary(), TransportService loop_boundary_reached)*
- [x] Take-Lanes im Arranger (übereinander gestapelt, wie Cubase/Logic)  *(v0.0.20.639 — Track.take_lanes_visible, visuelles Rendering, Kontextmenü)*
- [x] Comp-Tool: Bereiche aus verschiedenen Takes auswählen  *(v0.0.20.640 — TakeService comp_select_take_at/set_comp_region, Arranger Klick auf Take-Lane, visuelle CompRegion-Bars)*
- [x] Flatten: Comp zu einem einzelnen Clip zusammenfügen  *(v0.0.20.639 — TakeService.flatten_take_group())*
- [x] Take-Management: Umbenennen, Löschen, Farben  *(v0.0.20.639 — TakeService rename/delete/activate, Kontextmenü)*

### Abhängigkeiten
- Wenn AP1 (Rust-Engine) fertig: Recording direkt in Rust implementieren
- Wenn nicht: Bestehenden JACK-Backend erweitern

---

## 🎵 ARBEITSPAKET 3: Time-Stretching & Warping

### Aktueller Stand
Grundlagen vorhanden (Essentia Pool, Rubberband-Integration), aber kein
interaktives Warp-Marker-System.

### Ziel-Features

**Phase 3A — Warp-Marker System (~2-3 Sessions)**
- [x] Warp-Marker Datenmodell: `WarpMarker(beat_position, sample_position)`  *(v0.0.20.641 — WarpMarker dataclass: src_beat, dst_beat, is_anchor)*
- [x] Beat-Detection via Essentia/Aubio → automatische Marker-Platzierung  *(v0.0.20.641 — detect_beat_positions(), auto_detect_warp_markers())*
- [x] Manuelle Marker im Audio-Editor (Klick auf Transiente → Marker setzen)  *(existierte: Doppelklick in Stretch-Overlay → add_stretch_marker)*
- [x] Marker verschieben = Audio wird elastisch gestreckt/gestaucht  *(existierte: StretchWarpMarkerItem Drag + _apply_warp_markers in Renderer)*

**Phase 3B — Stretch-Modi (~2 Sessions)**
- [x] Beats Mode (für Drums/Percussion — Slice-basiert)  *(v0.0.20.641 — _beats_stretch_mono, onset-basiert)*
- [x] Tones Mode (für melodisches Material — Rubberband)  *(existierte: Phase Vocoder + Essentia)*
- [x] Texture Mode (für Ambient/Pads — Granular)  *(v0.0.20.641 — _texture_stretch_mono, Hanning-Grain OLA)*
- [x] Re-Pitch Mode (einfaches Resampling, kein Stretch)  *(v0.0.20.641 — _repitch_mono, lineare Interpolation)*
- [x] Complex/Complex Pro (höchste Qualität, CPU-intensiv)  *(v0.0.20.641 — _complex_stretch_mono, 4096-FFT PV)*

**Phase 3C — Tempo-Anpassung (~1-2 Sessions)**
- [x] Clip-Tempo erkennen (BPM Detection)  *(existierte: estimate_bpm + v0.0.20.641 auto_detect_warp_markers setzt clip.source_bpm)*
- [x] Automatische Anpassung an Projekt-Tempo  *(existierte: arrangement_renderer tempo_ratio = project_bpm / source_bpm)*
- [x] Tempo-Automation: Clips folgen Tempo-Änderungen in Echtzeit  *(v0.0.20.644 — TempoMap Modell, beat_to_time/time_to_beat, tempo_ratio_at_beat())*
- [x] Clip-Warp im Arranger (nicht nur im Audio-Editor)  *(v0.0.20.650 — Warp-Marker Visualisierung, Stretch-Mode Kontextmenü, Auto-Warp via Beat Detection)*

### Technologie
- **Rubberband** (C-Bibliothek, bereits integriert) für Tones/Complex
- **Slice-basiert** (eigene Implementierung) für Beats Mode
- **Granular** (numpy-basiert oder Rust) für Texture Mode

---

## 🔌 ARBEITSPAKET 4: Plugin-Hosting Robustheit

### Aktueller Stand
VST3 via pedalboard, CLAP direkt, LV2/LADSPA via lilvlib.
Kein Sandboxing, kein vollständiger Preset-Browser.

### Ziel-Features

**Phase 4A — Sandboxed Plugin-Hosting (~3-4 Sessions)**
- [x] Jedes Plugin in eigenem Subprocess (wie Bitwig)  *(v0.0.20.650 — PluginSandboxManager, multiprocessing.Process, daemon workers)*
- [x] IPC für Audio-Daten (Shared Memory Ringbuffer)  *(v0.0.20.650 — SharedAudioBuffer via mmap, zero-copy write/read)*
- [x] IPC für Parameter-Updates (Unix Socket)  *(v0.0.20.650 — MessagePack-ready PluginWorkerConfig, state restore via base64)*
- [x] Crash-Detection: Plugin-Prozess stirbt → Track wird gemutet, Fehlermeldung  *(v0.0.20.650 — _monitor_loop heartbeat, muted_by_crash, crash_callback)*
- [x] Auto-Restart: Plugin-Prozess wird neu gestartet, State wiederhergestellt  *(v0.0.20.650 — _restart_worker, MAX_CRASH_RESTARTS=3, buffer recreation)*

**Phase 4B — Preset-Browser (~2-3 Sessions)**
- [x] VST3 Preset-Scan: Alle Presets aus Plugin auslesen  *(v0.0.20.652 — PresetBrowserService: Factory+User Scan, rekursiv)*
- [x] CLAP Preset-Scan via `clap.preset-load` Extension  *(v0.0.20.569 — ClapAudioFxWidget eigenes Preset-System)*
- [x] Preset-Liste im Device-Widget (Dropdown + Search)  *(v0.0.20.652 — PresetBrowserWidget mit Kategorie-Filter + Volltextsuche)*
- [x] Preset-Kategorien (Factory, User, Favoriten)  *(v0.0.20.652 — All/Factory/User/Favorites + Favorit-Toggle)*
- [x] A/B Vergleich: Zwei Preset-Slots zum schnellen Wechseln  *(v0.0.20.652 — ABSlot mit State-Blob-Snapshots, A/B-Button)*

**Phase 4C — Plugin-State Management (~1-2 Sessions)**
- [x] Automatische State-Sicherung bei Projektänderungen  *(v0.0.20.652 — PluginStateManager auto-save interval + embed_project_state_blobs)*
- [x] State als Base64-Blob in Project-JSON  *(existierte: __ext_state_b64 in device params, embed_project_state_blobs)*
- [x] State-Wiederherstellung beim Projekt-Öffnen  *(existierte: _apply_raw_state_to_plugin bei Plugin-Init)*
- [x] Undo/Redo für Parameter-Änderungen  *(v0.0.20.652 — PluginStateManager undo/redo stack, PresetBrowserWidget ↩/↪ Buttons)*

### Abhängigkeiten
- AP1 (Rust-Engine) macht Sandboxing deutlich einfacher (Plugin in Rust-Thread)
- Ohne Rust: Python-Subprocess-Ansatz (langsamer, aber machbar)

---

## 🎛️ ARBEITSPAKET 5: Mixer / Routing

### Aktueller Stand
Basis-Mixer mit Volume/Pan/Mute/Solo pro Track, Master-Bus,
Group-Tracks mit 2-Pass Rendering. Kein Send/Return, kein Sidechain.

### Ziel-Features

**Phase 5A — Send/Return Tracks (~2-3 Sessions)**
- [x] FX Return Track Typ (empfängt nur Send-Signale)  *(v0.0.20.527 — Track kind="fx", Mixer FX-Sektion)*
- [x] Send-Knob pro Track (Pre-Fader / Post-Fader wählbar)  *(v0.0.20.527 — QDial pro FX-Track, Rechtsklick Pre/Post Toggle)*
- [x] Mehrere Sends pro Track (wie Cubase: bis zu 8)  *(v0.0.20.527 — Track.sends Liste, beliebig viele Targets)*
- [x] Send-Amount Automation  *(v0.0.20.528 — AutomatableParameter für jeden Send)*
- [x] Visuelles Routing im Mixer (Linien zwischen Tracks)  *(v0.0.20.640 — _RoutingOverlay Bezier-Kurven, farbkodiert, Opacity nach Amount)*

**Phase 5B — Sidechain-Routing (~1-2 Sessions)**
- [x] Sidechain-Input Selector pro Plugin  *(v0.0.20.641 — Track.sidechain_source_id, Mixer SC ComboBox)*
- [x] Track-zu-Track Sidechain (z.B. Kick → Compressor auf Bass)  *(v0.0.20.641 — HybridEngine sc_map, FX-Chain SC-Buffer API)*
- [x] Visueller Indikator im Mixer  *(v0.0.20.641 — Orange SC Label, RoutingOverlay Dashed-Bezier, Diamant-Marker)*
- [x] Sidechain-Routing Matrix (Übersicht aller Verbindungen)  *(v0.0.20.641 — SidechainRoutingMatrix QDialog, Grid mit Radio-Style)*

**Phase 5C — Routing-Matrix (~2-3 Sessions)**
- [x] Patchbay-Ansicht (wie Cubase MixConsole Routing)  *(v0.0.20.641 — PatchbayDialog: Output, Sends, SC, Channel Config)*
- [x] Drag&Drop Routing zwischen Tracks  *(v0.0.20.641 — Output Target ComboBox in MixerStrip + Patchbay, output_target_id)*
- [x] Multi-Output Plugins (z.B. Drum-Sampler → separate Outputs)  *(v0.0.20.650 — Track.plugin_output_routing/count, create_plugin_output_tracks(), per-output routing API)*
- [x] Mono/Stereo/Surround Track-Konfiguration  *(v0.0.20.641 — Track.channel_config, Mono-Summing in Engine, UI ComboBox)*

---

## 🎹 ARBEITSPAKET 6: MIDI-Editing Tiefe

### Aktueller Stand
Piano Roll mit Pencil/Select/Erase/Knife, Loop-Editor, Expression Lanes,
Ghost Layers, MIDI Learn, CC Automation. Grundsolide, aber es fehlen Power-Tools.

### Ziel-Features

**Phase 6A — MIDI Effects Chain (~3-4 Sessions)**
- [x] MIDI Effect Slot pro Track (vor dem Instrument)  *(existierte: Track.note_fx_chain, apply_note_fx_chain_to_notes())*
- [x] Built-in MIDI Effects:
  - [x] Arpeggiator (Pattern, Rate, Gate, Octave Range)  *(existierte: chrono.note_fx.arp, 12+ Modi)*
  - [x] Chord Generator (Chord Type, Voicing, Spread)  *(v0.0.20.644 — 16 Chord-Typen, Drop-2/3/Open/Spread voicings)*
  - [x] Scale Quantizer (Force to Scale, Nearest Note)  *(existierte: chrono.note_fx.scale_snap, 8 Scales)*
  - [x] Randomizer (Pitch, Velocity, Timing, Length Randomization)  *(v0.0.20.644 — timing_range + length_range hinzugefügt)*
  - [x] Note Echo (Delay, Feedback, Transpose per Repeat)  *(v0.0.20.644 — chrono.note_fx.note_echo, 1-16 Repeats)*
  - [x] Velocity Curve (Compress/Expand/Limit)  *(v0.0.20.644 — chrono.note_fx.velocity_curve, 6 Curve-Typen)*
- [x] MIDI FX Chain: Mehrere Effekte hintereinander  *(existierte: apply_note_fx_chain_to_notes() chain processing)*
- [x] MIDI FX Preset-System  *(v0.0.20.644 — MidiFxPresetManager, 13 Factory Presets, JSON Save/Load)*

**Phase 6B — MPE Support (~2-3 Sessions)**
- [x] Per-Note Pitch Bend (Channel per Note)  *(v0.0.20.650 — MPEChannelAllocator round-robin, per-note pitch_bend_semitones)*
- [x] Per-Note Pressure / Slide  *(v0.0.20.650 — MPEProcessor process_channel_pressure + process_cc(74), curve recording)*
- [x] MPE Configuration (Lower/Upper Zone, Pitch Bend Range)  *(v0.0.20.650 — MPEConfig/MPEZoneConfig, Track.mpe_config, JSON serialization)*
- [x] MPE-aware Piano Roll (Pitch Bend + Pressure pro Note visualisieren)  *(v0.0.20.650 — note_state_to_expressions() → MidiNote.expressions, existing expression lane rendering)*
- [x] MPE Controller Support (Roli Seaboard, Linnstrument, Sensel Morph)  *(v0.0.20.650 — _KNOWN_MPE_CONTROLLERS presets, get_mpe_preset(), detect_mpe_from_mcm API)*

**Phase 6C — Groove Templates (~1-2 Sessions)**
- [x] Groove Template Bibliothek (Swing, MPC, TR-808, Live-Drummer)  *(v0.0.20.644 — 12 Factory Grooves: 5 Swing, 3 MPC, 1 TR-808, 3 Drummer)*
- [x] Groove aus MIDI-Clip extrahieren  *(v0.0.20.644 — extract_groove_from_notes(), per-step timing/velocity/length)*
- [x] Groove auf andere Clips anwenden  *(v0.0.20.644 — apply_groove_to_notes(), per-step grid mapping)*
- [x] Groove-Amount Slider (0-100%)  *(v0.0.20.644 — amount parameter 0.0-2.0, selektiv timing/velocity/length)*
- [x] Humanize: Zufällige Timing/Velocity-Variation  *(v0.0.20.644 — humanize_notes(), Gaussian distribution, seed)*

---

## 🥁 ARBEITSPAKET 7: Sampler / Instrument-Tiefe

### Aktueller Stand
Pro Audio Sampler (basic), AETERNA Synth, SF2 via FluidSynth.
Kein Multi-Sample-Mapping, kein Drum Rack.

### Ziel-Features

**Phase 7A — Advanced Sampler (~3-4 Sessions)**
- [x] Multi-Sample Mapping Editor (Key + Velocity Zones visuell)  *(v0.0.20.656 — ZoneMapCanvas 2D-Grid, ZoneInspector, Drag-Resize)*
- [x] Round-Robin Gruppen (zyklische Sample-Auswahl)  *(v0.0.20.656 — MultiSampleMap RR-Counter, SampleZone.rr_group)*
- [x] Sample-Start/End/Loop-Punkte im Editor  *(v0.0.20.656 — LoopPoints dataclass, Sample-Tab im ZoneInspector)*
- [x] Filter (LP/HP/BP) + Amp Envelope (ADSR) pro Sample-Zone  *(v0.0.20.656 — ZoneFilter + ZoneEnvelope pro Zone, EnvState ADSR-Maschine)*
- [x] Modulations-Matrix (LFO/Envelope → Pitch/Filter/Amp/Pan)  *(v0.0.20.656 — 4 ModulationSlots, 2 LFOs, 7 Sources, 4 Destinations)*
- [x] Sample Import: Drag&Drop, Auto-Mapping (chromatisch/Drum)  *(v0.0.20.656 — auto_mapping.py: Chromatic/Drum/VelLayer/RR, Filename-Pattern-Detection)*

**Phase 7B — Drum Rack (~2-3 Sessions)**
- [x] 4x4 oder 8x8 Pad-Grid (wie Ableton Drum Rack)  *(v0.0.20.656 — Pad-Bank Navigation A/B/C/D = 4×16 = 64 Pads, expand_slots())*
- [x] Ein Sample/Instrument pro Pad  *(existierte: DrumSlot mit ProSamplerEngine pro Pad)*
- [x] Per-Pad: Volume, Pan, Tune, FX Chain  *(existierte: CompactKnob Gain/Pan/Tune, SlotFxInlineRack)*
- [x] Per-Pad: Choke Groups (Hi-Hat Open/Closed)  *(v0.0.20.656 — DrumSlotState.choke_group 0-8, Engine silenciert Gruppe bei Trigger)*
- [x] Pad-Zuordnung via Drag&Drop  *(existierte: DrumPadButton.sample_dropped, Smart-Assign)*
- [x] MIDI-Mapping: C1-D#2 = Standard GM Drum Map  *(existierte: base_note=36, pitch_to_slot_index())*

**Phase 7C — Wavetable-Erweiterung für AETERNA (~2-3 Sessions)**
- [x] Wavetable Import (Serum .wav Format)  *(v0.0.20.657 — WavetableBank: .wav/.wt Import, Serum clm chunk detection, 24-bit support)*
- [x] Wavetable Morphing (Position Automation)  *(v0.0.20.657 — wt_position Parameter, Mod-Target, per-sample position modulation)*
- [x] Wavetable Editor (Draw/Import/FFT)  *(v0.0.20.657 — draw_frame(), get/set_frame_harmonics() FFT, 6 Built-in Tables, normalize)*
- [x] Unison Engine (Detune, Spread, Width)  *(v0.0.20.657 — UnisonEngine: Classic/Supersaw/Hyper, 1-16 Voices, stereo panning)*

---

## 🎚️ ARBEITSPAKET 8: Built-in Effects

### Aktueller Stand
Keine eingebauten Audio-Effekte. Komplett abhängig von externen Plugins.

### Ziel-Features (nach Priorität)

**Phase 8A — Essential FX (~4-5 Sessions)**
- [x] **EQ (Parametric 8-Band)**: Bell, Shelf, HP/LP, Analyzer-Display  *(v0.0.20.642 — ParametricEqFx, 8-Band Biquad DF2T)*
- [x] **Compressor**: Threshold, Ratio, Attack, Release, Knee, Sidechain, Gain Reduction Meter  *(v0.0.20.642 — CompressorFx, feed-forward RMS, SC-Buffer via ChainFx)*
- [x] **Reverb**: Algorithmic (Hall/Room/Plate), Pre-Delay, Decay, Damping, Mix  *(v0.0.20.642 — ReverbFx, 4-Comb + 4-Allpass Schroeder)*
- [x] **Delay**: Tempo-Sync, Ping-Pong, Filter, Feedback, Mix  *(v0.0.20.642 — DelayFx, Stereo + LP Filter + Ping-Pong)*
- [x] **Limiter**: Brickwall, Ceiling, Release, Gain  *(v0.0.20.642 — LimiterFx, instant attack, auto-release)*

**Phase 8B — Creative FX (~3-4 Sessions)**
- [x] **Chorus**: Rate, Depth, Voices, Mix  *(v0.0.20.643 — ChorusFx + Scrawl LFO shape)*
- [x] **Phaser**: Rate, Depth, Stages, Feedback  *(v0.0.20.643 — PhaserFx + Scrawl sweep envelope)*
- [x] **Flanger**: Rate, Depth, Feedback, Mix  *(v0.0.20.643 — FlangerFx + Scrawl delay modulation)*
- [x] **Distortion**: Drive, Tone, Type (Soft/Hard/Tube/Tape/Bitcrush)  *(v0.0.20.643 — DistortionPlusFx + Scrawl transfer function)*
- [x] **Tremolo**: Rate, Depth, Shape (Sine/Square/Triangle)  *(v0.0.20.643 — TremoloFx + Scrawl amplitude shape)*

**Phase 8C — Utility FX (~2-3 Sessions)**
- [x] **Gate**: Threshold, Attack, Hold, Release, Sidechain  *(v0.0.20.644 — GateFx, peak envelope, hold phase, SC-Buffer via ChainFx)*
- [x] **De-Esser**: Frequency, Threshold, Range  *(v0.0.20.644 — DeEsserFx, bandpass detection, proportional reduction, Listen mode)*
- [x] **Stereo Widener**: Width, Mid/Side Balance  *(v0.0.20.644 — StereoWidenerFx, M/S encode/decode, mid/side gain)*
- [x] **Utility**: Gain, Phase Invert, Mono, DC Offset  *(v0.0.20.644 — UtilityFx, pan law, channel swap, DC blocker)*
- [x] **Spectrum Analyzer**: FFT Display, Peak Hold  *(v0.0.20.644 — SpectrumAnalyzerFx, Hanning window, smoothing, get_spectrum_data())*

### Technologie
- **Wenn Rust-Engine (AP1):** FX in Rust implementieren (beste Performance)
- **Ohne Rust:** numpy/scipy DSP in Python (funktioniert, aber CPU-intensiv)
- **Alternative:** Fertige C-Bibliotheken wrappen (z.B. Faust DSP)

---

## 📈 ARBEITSPAKET 9: Automation (Ausbau)

### Aktueller Stand
AutomatableParameter, Breakpoint-Envelopes (Bezier/Step/Smooth),
Write/Touch/Latch Modi, MIDI Learn, Inline Arranger Lanes.

### Ziel-Features

**Phase 9A — Plugin-Parameter Automation (~2 Sessions)**
- [x] Alle Plugin-Parameter als Automations-Ziele  *(v0.0.20.644 — PluginParamDiscovery, _BUILTIN_FX_PARAMS für 13 Built-in FX)*
- [x] Parameter-Discovery: Plugin → Liste aller automatisierbaren Parameter  *(v0.0.20.644 — discover_track_parameters() + get_param_infos() für VST3/CLAP/LV2)*
- [x] "Arm" Button pro Parameter (Write-Modus gezielt)  *(v0.0.20.644 — set_armed/is_armed/get_armed_params/disarm_all)*
- [x] Parameter-Name im Automation-Lane Header  *(v0.0.20.644 — get_param_display_name(), get_params_grouped_by_plugin())*

**Phase 9B — Relative/Trim Automation (~1-2 Sessions)**
- [x] Relative Mode: Automation ist Offset auf aktuellen Wert  *(v0.0.20.644 — AutomationLane.automation_mode="relative", apply_mode() 0.5=no change)*
- [x] Trim Mode: Automation als Multiplikator  *(v0.0.20.644 — automation_mode="trim", 0.5=1x, 0=0x, 1=2x)*
- [x] Visuell: Separate Linie für Basis-Wert + Automation-Offset  *(v0.0.20.644 — apply_mode() returns effective value, mode in to_dict/from_dict)*

**Phase 9C — Automation Workflow (~1-2 Sessions)**
- [x] Automation-Snapshot: Aktuellen Zustand als Startpunkt einfrieren  *(v0.0.20.644 — snapshot_automation() erstellt BPs für alle Track-Parameter)*
- [x] Automation auf Clip-Ebene (nicht nur Track-Ebene)  *(v0.0.20.644 — copy_clip_automation() mit Beat-Offset für Clip-Duplikation)*
- [x] Clip-Automation kopieren bei Clip-Duplikation  *(v0.0.20.644 — copy_clip_automation() src_start/end → dst_start)*
- [x] Automation-Curves: Logarithmisch, Exponentiell, S-Curve  *(v0.0.20.644 — CurveType.LOGARITHMIC/EXPONENTIAL/S_CURVE)*

---

## 📤 ARBEITSPAKET 10: Export & Collaboration

### Aktueller Stand
Basis WAV-Export, DAWproject Export/Import Grundlagen.

### Ziel-Features

**Phase 10A — Multi-Format Export (~1-2 Sessions)**
- [x] Export-Dialog: WAV (16/24/32bit), FLAC, MP3, OGG  *(v0.0.20.644 — AudioExportDialog + audio_export_service.py, soundfile/pydub/lame)*
- [x] Sample-Rate Auswahl (44.1/48/88.2/96 kHz)  *(v0.0.20.644 — _resample() mit scipy.signal.resample_poly Fallback linear interp)*
- [x] Dither-Optionen (Triangular, POW-R)  *(v0.0.20.644 — TPDF + POW-R Type 1 mit Noise Shaping)*
- [x] Normalisierung (Peak / LUFS)  *(v0.0.20.644 — _normalize_peak(), _normalize_lufs() ITU-R BS.1770 approx)*
- [x] Progress-Bar mit Abbrechen  *(v0.0.20.644 — QProgressDialog, progress_callback in export_audio())*

**Phase 10B — Stem Export (~1-2 Sessions)**
- [x] Alle Tracks als separate Dateien exportieren  *(v0.0.20.644 — ExportConfig.stem_export, per-track render loop)*
- [x] Track-Gruppen als Stems (Drums, Bass, Keys, Vocals, etc.)  *(v0.0.20.644 — track_ids Liste im Dialog, Multi-Select)*
- [x] Naming Convention: `Projektname_Trackname_BPM.wav`  *(v0.0.20.644 — base_name = f"{safe_name}_{safe_track}_{bpm}BPM")*
- [x] Pre-/Post-FX Export Optionen  *(v0.0.20.650 — ExportConfig.fx_mode: post_fx/pre_fx/both, UI ComboBox, filename suffix)*

**Phase 10C — DAWproject Roundtrip (~2-3 Sessions)**
- [x] Vollständiger DAWproject Export (Clips, Automation, Plugins)  *(v0.0.20.658 — Send-Export, Plugin-Mapping deviceIDs, Clip Extensions)*
- [x] Import von Bitwig/Studio One DAWproject Dateien  *(v0.0.20.658 — Full Importer: Automation, Plugin States, Sends, Groups, Clip Extensions)*
- [x] Roundtrip-Test: Export → Import → Vergleich  *(v0.0.20.658 — dawproject_roundtrip_test.py: Transport, Tracks, Clips, Notes, Automation, Sends)*
- [x] Plugin-Mapping: VST3 ID ↔ DAWproject Device ID  *(v0.0.20.658 — dawproject_plugin_map.py: Internal+VST3+CLAP+LV2, Well-Known DB, bidirektional)*

**Phase 10D — Cloud & Collaboration (~2-3 Sessions)**
- [x] Projekt-Backup in Cloud (optional, Git-basiert)  *(v0.0.20.658 — ProjectVersionService: auto/manual Snapshots, SHA-256 Dedup, Manifest, Pruning)*
- [x] Projekt-Sharing per Link  *(v0.0.20.658 — ProjectShareExporter/-Importer: .pydaw-share Pakete, Media-Embedding, Preview, Merge/Replace)*
- [x] Versionierung: Projekt-Snapshots mit Diff  *(v0.0.20.658 — diff_snapshots(): Transport, Tracks, Clips, Automation, Media)*
- [x] Collaborative Editing (optional, langfristiges Ziel)  *(v0.0.20.658 — ProjectMergeEngine: 3-Way Merge, Conflict Detection, ours/theirs/manual Strategy)*

---

## 📊 GESAMTÜBERSICHT: Aufwand & Priorität

| AP | Feature | Priorität | Sessions | Abhängigkeit |
|----|---------|-----------|----------|--------------|
| 1  | Rust Audio-Core | 🔴 KRITISCH | 10-16 | — |
| 2  | Audio Recording | 🔴 KRITISCH | 8-11 | AP1 (optional) |
| 3  | Time-Stretch/Warp | 🟠 HOCH | 5-7 | — |
| 4  | Plugin Robustheit | 🟠 HOCH | 6-9 | AP1 (optional) |
| 5  | Mixer/Routing | 🟠 HOCH | 5-8 | AP1 (optional) |
| 6  | MIDI-Editing | 🟡 MITTEL | 6-9 | — |
| 7  | Sampler/Instrumente | 🟡 MITTEL | 7-10 | — |
| 8  | Built-in FX | 🟡 MITTEL | 9-12 | AP1 (empfohlen) |
| 9  | Automation Ausbau | 🟢 NORMAL | 4-6 | — |
| 10 | Export/Collaboration | 🟢 NORMAL | 6-10 | — |
| **TOTAL** | | | **~66-98 Sessions** | |

### Empfohlene Reihenfolge
```
AP1 (Rust Core) → AP2 (Recording) → AP5 (Routing) → AP4 (Plugins)
                → AP3 (Warp) → AP8 (FX) → AP6 (MIDI) → AP7 (Sampler)
                → AP9 (Automation) → AP10 (Export)
```

AP1 ist der Grundstein — alles wird besser wenn die Audio-Engine in Rust läuft.
AP2+AP5 sind die nächsten Kern-Features die jede DAW braucht.
AP3-AP8 können parallel angegangen werden.
AP9-AP10 sind Polish/Workflow-Verbesserungen.

---

## 🔧 TECHNISCHE RICHTLINIEN FÜR ALLE KOLLEGEN

### Code-Stil
- Python 3.12+, PyQt6
- Type Hints wo möglich
- Docstrings für alle öffentlichen Methoden
- `try/except` um alle Qt-Virtual-Overrides (PyQt6 kann SIGABRT bei Exceptions)
- Keine `print()` in Production-Code (nur `logging.getLogger()`)

### Git/ZIP Konventionen
- VERSION-Datei IMMER erhöhen (Format: `0.0.20.XXX`)
- CHANGELOG_v0.0.20.XXX_KURZTITEL.md für jede Version
- TODO.md und DONE.md in PROJECT_DOCS/progress/ aktualisieren
- Session-Log in PROJECT_DOCS/sessions/

### Testing
- `python3 -c "import py_compile; py_compile.compile('datei.py', doraise=True)"` für JEDE geänderte Datei
- ZIP entpacken und nochmal prüfen
- Manuelle Tests: "Funktioniert der Slot-Drag noch? Piano Roll? Transport?"

### Performance-Regeln
- Keine Allokationen im Audio-Callback (Lock-Free only)
- GUI-Updates maximal 30Hz (Timer, nicht pro Sample)
- `set()` Kopien für sichere Iteration über veränderliche Collections
- `getattr(obj, 'attr', default)` statt direktem Zugriff für Robustheit

## UI-Hotfix / Ergonomie (laufend auf Anfrage)
- [x] Top-Toolbar entzerrt: Projekt-Tabs eigene Zeile, Transport kompakter, Python-Logo/Rechtsbereich wieder lesbar  *(v0.0.20.645 — expliziter Toolbar-Break + kompakteres TransportPanel)*
- [x] Eigenständiges Rust-Badge nahe **Neues Projekt** / **Öffnen** eingebunden, bewusst getrennt vom Qt-Badge und etwas größer für bessere Erkennbarkeit  *(v0.0.20.646 — 30×30 Badge in Projekt-Tab-Leiste)*
- [x] Rust-Badge in einen **zentrierten Branding-Slot** der Tool-Leiste verschoben; obere Zeile entschlackt und Combo-Felder für **Zeiger / 1/16 / 1/32** sichtbar verbreitert  *(v0.0.20.647 — centered toolbar branding slot + größere ComboBoxen)*
- [x] Optional: Responsive Verdichtung/Umbruch für sehr kleine Fensterbreiten  *(v0.0.20.663 — TransportPanel + ToolBarPanel 2-Tier resizeEvent)*
- [x] Rust-Badge alternativ in einen separaten Branding-Slot verschiebbar gemacht  *(v0.0.20.647 — zentrierter ToolBar-Slot)*
- [x] Rust-Badge anhand Screenshot-Hinweis weiter in die obere Mitte verlagert; jetzt direkt hinter `Count-In`, ohne Tool-/Browserbereich rechts zu quetschen  *(v0.0.20.648 — Transport-Badge statt rechter Tool-Slot)*
- [x] Combo-Felder fuer **Zeiger / 1/16 / 1/32** nochmals vergroessert, damit Text und Dropdown oben klarer erkennbar bleiben  *(v0.0.20.648 — breitere ComboBoxen + groessere Dropdown-Zone)*
- [x] Exakte Menümitten-/Branding-Feinjustierung nach weiterem Screenshot  *(v0.0.20.649 — Rust-Badge als zentriertes Menüleisten-Overlay unter dem Fenstertitel platziert)*

## 🦀 NEUES GROSSVORHABEN: Rust DSP Migration (ab v0.0.20.666)

```
📋 Vollständiger Plan: PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md
   → 13 Phasen (R1–R13), 35-46 Sessions, selbständig abarbeitbar
   → Alle Python-DSP-Engines (Instrumente + FX) werden in Rust neu gebaut
   → Python-Engine bleibt als Fallback erhalten
```

**Nächste offene Aufgabe:** `cargo build --release` Live-Test (MIDI Scheduler + Instrument Auto-Load verifizieren), dann P7 Plugin-Hosting Live-Test

**v0.0.20.726: MIDI Clip Scheduler implementiert** — MIDI-Noten aus dem Arrangement werden jetzt beim Playback an die Rust-Instrumente dispatcht. Instrumente werden bei ProjectSync automatisch geladen.

---

*Dieses Dokument wird mit jeder Major-Version aktualisiert.*
*Aktueller Stand: v0.0.20.718 — 2026-03-21*
