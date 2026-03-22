use std::sync::Arc;

use crossbeam_channel::{Receiver, Sender};
use log::{error, info, warn};
use parking_lot::Mutex;

use crate::audio_graph::AudioGraph;
use crate::clip_renderer::{ArrangementRenderer, ArrangementSnapshot, AudioClipData, ClipStore, PlacedClip};
use crate::ipc::{Command, Event, TrackMeterLevel};
use crate::lock_free::ParamRing;
use crate::transport::Transport;

// ============================================================================
// Engine — The core audio engine coordinator
// ============================================================================
//
// Ownership model:
//   - Engine owns AudioGraph + Transport + ClipStore + ArrangementRenderer
//   - Audio callback borrows via Arc (lock-free reads)
//   - IPC handler sends Commands via crossbeam channel
//   - ParamRing: GUI writes, Audio thread drains (lock-free SPSC)
//
// Thread model:
//   - Main thread: IPC server
//   - Audio thread: cpal callback → drain params → render clips → process graph → output
//   - GUI thread: Python (separate process, connected via IPC)
// ============================================================================

/// Shared engine state, accessible from both IPC handler and audio callback.
pub struct EngineState {
    pub graph: Mutex<AudioGraph>,
    pub transport: Arc<Transport>,
    pub command_rx: Receiver<Command>,
    pub event_tx: Sender<Event>,
    pub running: std::sync::atomic::AtomicBool,

    /// Lock-free parameter ring (GUI → Audio thread).
    pub param_ring: Arc<ParamRing>,

    /// Audio clip data store (RwLock-protected, shared with renderer).
    pub clip_store: Arc<ClipStore>,

    /// Arrangement renderer (reads clips, writes into track buffers).
    pub renderer: ArrangementRenderer,

    /// v0.0.20.725: Beat-accurate MIDI clip scheduler.
    /// Dispatches NoteOn/NoteOff from arrangement MIDI clips to instruments.
    pub midi_scheduler: Mutex<crate::midi_scheduler::MidiScheduler>,

    /// Meter update counter — only send meter events every N process cycles (~30Hz).
    meter_counter: std::sync::atomic::AtomicU32,
    /// XRun counter.
    xrun_count: std::sync::atomic::AtomicU32,
    /// Last process_audio render time in microseconds (for Pong cpu_load).
    last_render_us: std::sync::atomic::AtomicU32,
    /// Buffer budget in microseconds (sample_rate / buffer_size based).
    budget_us: std::sync::atomic::AtomicU32,
}

impl EngineState {
    pub fn new(
        sample_rate: u32,
        buffer_size: u32,
        bpm: f64,
        command_rx: Receiver<Command>,
        event_tx: Sender<Event>,
    ) -> Self {
        let clip_store = Arc::new(ClipStore::new());
        let renderer = ArrangementRenderer::new(Arc::clone(&clip_store));
        Self {
            graph: Mutex::new(AudioGraph::new(buffer_size as usize, sample_rate)),
            transport: Arc::new(Transport::new(sample_rate, bpm)),
            command_rx,
            event_tx,
            running: std::sync::atomic::AtomicBool::new(true),
            param_ring: Arc::new(ParamRing::new()),
            clip_store,
            renderer,
            midi_scheduler: Mutex::new(crate::midi_scheduler::MidiScheduler::new()),
            meter_counter: std::sync::atomic::AtomicU32::new(0),
            xrun_count: std::sync::atomic::AtomicU32::new(0),
            last_render_us: std::sync::atomic::AtomicU32::new(0),
            budget_us: std::sync::atomic::AtomicU32::new(
                ((buffer_size as f64 / sample_rate as f64) * 1_000_000.0) as u32
            ),
        }
    }

    /// Process all pending commands from the IPC queue.
    /// Called at the start of each audio callback — MUST be fast.
    pub fn drain_commands(&self) {
        // Drain up to 64 commands per callback to prevent starvation
        for _ in 0..64 {
            match self.command_rx.try_recv() {
                Ok(cmd) => self.handle_command(cmd),
                Err(_) => break,
            }
        }
    }

    /// Handle a single command.
    fn handle_command(&self, cmd: Command) {
        match cmd {
            Command::Play => {
                self.transport.playing.store(true, std::sync::atomic::Ordering::Release);
                let _ = self.event_tx.try_send(Event::TransportState {
                    is_playing: true,
                    beat: self.transport.position_beats(),
                });
            }
            Command::Stop => {
                self.transport.playing.store(false, std::sync::atomic::Ordering::Release);
                self.transport.seek_to_sample(0);
                // v0.0.20.725: Reset MIDI scheduler + send AllNotesOff to prevent stuck notes
                self.midi_scheduler.lock().reset();
                {
                    let mut graph = self.graph.lock();
                    let indices = graph.track_indices();
                    for idx in indices {
                        if let Some(track) = graph.get_track_mut(idx) {
                            if let Some(ref mut inst) = track.instrument {
                                inst.push_midi(crate::instruments::MidiEvent::AllNotesOff);
                            }
                        }
                    }
                }
                let _ = self.event_tx.try_send(Event::TransportState {
                    is_playing: false,
                    beat: 0.0,
                });
            }
            Command::Pause => {
                self.transport.playing.store(false, std::sync::atomic::Ordering::Release);
                let _ = self.event_tx.try_send(Event::TransportState {
                    is_playing: false,
                    beat: self.transport.position_beats(),
                });
            }
            Command::Seek { beat } => {
                self.transport.seek_to_beat(beat);
                // v0.0.20.725: Reset scheduler scan position + kill lingering notes
                self.midi_scheduler.lock().reset();
                {
                    let mut graph = self.graph.lock();
                    let indices = graph.track_indices();
                    for idx in indices {
                        if let Some(track) = graph.get_track_mut(idx) {
                            if let Some(ref mut inst) = track.instrument {
                                inst.push_midi(crate::instruments::MidiEvent::AllNotesOff);
                            }
                        }
                    }
                }
            }
            Command::SetTempo { bpm } => {
                self.transport.set_bpm(bpm);
            }
            Command::SetTimeSignature {
                numerator,
                denominator,
            } => {
                self.transport.set_time_signature(numerator, denominator);
            }
            Command::SetLoop {
                enabled,
                start_beat,
                end_beat,
            } => {
                self.transport.set_loop(enabled, start_beat, end_beat);
            }
            Command::AddTrack {
                track_id,
                track_index,
                kind,
            } => {
                let tk = crate::audio_graph::TrackKind::from_str(&kind);
                let mut graph = self.graph.lock();
                graph.add_track(track_id, track_index, tk);
            }
            Command::RemoveTrack { track_id } => {
                let mut graph = self.graph.lock();
                graph.remove_track(&track_id);
            }
            Command::SetTrackParam {
                track_index,
                param,
                value,
            } => {
                let graph = self.graph.lock();
                if let Some(track) = graph.get_track(track_index) {
                    track.set_param(param, value);
                }
            }
            Command::SetMasterParam { param, value } => {
                let graph = self.graph.lock();
                if let Some(master_idx) = graph.master_index() {
                    if let Some(track) = graph.get_track(master_idx) {
                        track.set_param(param, value);
                    }
                }
            }
            Command::SetGroupRouting {
                child_track_index,
                group_track_index,
            } => {
                let mut graph = self.graph.lock();
                graph.set_group_routing(child_track_index, group_track_index);
            }
            Command::Configure {
                sample_rate,
                buffer_size,
                device,
            } => {
                info!(
                    "Configure: sr={}, buf={}, dev='{}'",
                    sample_rate, buffer_size, device
                );
                self.transport.set_sample_rate(sample_rate);
                let mut graph = self.graph.lock();
                graph.sample_rate = sample_rate;
                graph.resize_buffers(buffer_size as usize);
                let _ = self.event_tx.try_send(Event::Ready {
                    sample_rate,
                    buffer_size,
                    device_name: device,
                });
            }

            // -- v0.0.20.711: RA2 Extended Instrument Data ----------------

            Command::LoadSF2 {
                track_id,
                sf2_path,
                bank,
                preset,
            } => {
                // SF2 loading requires FluidSynth FFI (R11B).
                // For now: store the path and program info for when
                // the FluidSynth integration is ready.
                info!(
                    "LoadSF2: track={}, path={}, bank={}, preset={}",
                    track_id, sf2_path, bank, preset
                );
                // TODO (R11B): fluidsynth::load_soundfont(&sf2_path)
                // TODO: fluidsynth::program_select(bank, preset)
                let _ = self.event_tx.try_send(Event::Error {
                    code: 100,
                    message: format!(
                        "LoadSF2 received but FluidSynth FFI not yet implemented (track={})",
                        track_id
                    ),
                });
            }

            Command::LoadWavetable {
                track_id,
                table_name,
                frame_size,
                num_frames,
                data_b64,
            } => {
                // Decode wavetable frames from Base64.
                // Store in the instrument node for the AETERNA synth.
                info!(
                    "LoadWavetable: track={}, table='{}', {}×{} frames",
                    track_id, table_name, num_frames, frame_size
                );
                match crate::clip_renderer::base64_decode(&data_b64) {
                    Ok(raw) => {
                        let expected = (frame_size * num_frames * 4) as usize; // f32 = 4 bytes
                        if raw.len() >= expected {
                            info!(
                                "LoadWavetable: decoded {} bytes (expected {})",
                                raw.len(),
                                expected
                            );
                            // TODO (R9): Store in AeternaInstrument wavetable bank
                        } else {
                            warn!(
                                "LoadWavetable: short data ({} < {})",
                                raw.len(),
                                expected
                            );
                        }
                    }
                    Err(e) => {
                        warn!("LoadWavetable: base64 decode error: {}", e);
                    }
                }
            }

            Command::MapSampleZone {
                track_id,
                clip_id,
                key_lo,
                key_hi,
                vel_lo,
                vel_hi,
                root_key,
                rr_group,
            } => {
                // Map a pre-loaded clip (already in ClipStore via LoadAudioClip)
                // to a sample zone on a multi-sample instrument.
                info!(
                    "MapSampleZone: track={}, clip={}, keys={}-{}, vel={}-{}, root={}, rr={}",
                    track_id, clip_id, key_lo, key_hi, vel_lo, vel_hi, root_key, rr_group
                );
                // Verify clip exists in ClipStore
                if self.clip_store.get(&clip_id).is_some() {
                    info!("MapSampleZone: clip '{}' found in ClipStore", clip_id);
                    // TODO (R6B): Add zone to MultiSampleInstrument on track
                } else {
                    warn!(
                        "MapSampleZone: clip '{}' not found in ClipStore — \
                         send LoadAudioClip first!",
                        clip_id
                    );
                }
            }
            Command::Ping { seq } => {
                let render_us = self.last_render_us.load(std::sync::atomic::Ordering::Relaxed);
                let budget = self.budget_us.load(std::sync::atomic::Ordering::Relaxed);
                let cpu_load = if budget > 0 {
                    render_us as f32 / budget as f32
                } else {
                    0.0
                };
                let _ = self.event_tx.try_send(Event::Pong {
                    seq,
                    cpu_load,
                    xrun_count: self
                        .xrun_count
                        .load(std::sync::atomic::Ordering::Relaxed),
                    render_time_us: render_us,
                });
            }
            Command::Shutdown => {
                info!("Shutdown command received");
                self.running
                    .store(false, std::sync::atomic::Ordering::Release);
                let _ = self.event_tx.try_send(Event::ShuttingDown);
            }
            // -- Audio Data (Phase 1B) ------------------------------------
            Command::LoadAudioClip {
                clip_id,
                channels,
                sample_rate,
                audio_b64,
            } => {
                match AudioClipData::from_base64(clip_id.clone(), channels, sample_rate, &audio_b64)
                {
                    Ok(clip) => {
                        info!(
                            "Loaded audio clip '{}': {}ch, {}Hz, {} frames",
                            clip_id, channels, sample_rate, clip.frame_count
                        );
                        self.clip_store.insert(clip);
                    }
                    Err(e) => {
                        error!("Failed to decode audio clip '{}': {}", clip_id, e);
                        let _ = self.event_tx.try_send(Event::Error {
                            code: 100,
                            message: format!("LoadAudioClip failed: {}", e),
                        });
                    }
                }
            }
            Command::SetArrangement { clips } => {
                let bpm = self.transport.bpm();
                let sr = self.transport.sample_rate() as u32;
                let placed: Vec<PlacedClip> = clips
                    .iter()
                    .map(|c| PlacedClip::from_ipc(c, sr, bpm))
                    .collect();
                let snapshot = ArrangementSnapshot::new(placed);
                info!(
                    "Arrangement updated: {} clips on {} tracks",
                    snapshot.clips.len(),
                    snapshot.clips_by_track.len()
                );
                self.renderer.set_arrangement(snapshot);
            }
            // -- External Plugin Hosting (Phase P7) ----------------------------
            Command::ScanPlugins => {
                info!("ScanPlugins: scanning VST3 + CLAP + LV2...");
                let mut all_plugins: Vec<crate::ipc::ScannedPlugin> = Vec::new();
                let mut all_errors: Vec<String> = Vec::new();
                let scan_start = std::time::Instant::now();

                // VST3
                let vst3 = crate::vst3_host::scan_vst3_plugins();
                for p in &vst3.plugins {
                    all_plugins.push(crate::ipc::ScannedPlugin {
                        format: "vst3".to_string(),
                        name: p.name.clone(),
                        vendor: p.vendor.clone(),
                        plugin_id: p.class_id.clone(),
                        path: p.bundle_path.to_string_lossy().to_string(),
                        category: p.category.clone(),
                        audio_inputs: p.audio_inputs,
                        audio_outputs: p.audio_outputs,
                    });
                }
                all_errors.extend(vst3.errors);

                // CLAP
                let clap = crate::clap_host::scan_clap_plugins();
                for p in &clap.plugins {
                    all_plugins.push(crate::ipc::ScannedPlugin {
                        format: "clap".to_string(),
                        name: p.name.clone(),
                        vendor: p.vendor.clone(),
                        plugin_id: p.plugin_id.clone(),
                        path: p.file_path.to_string_lossy().to_string(),
                        category: p.features.join(", "),
                        audio_inputs: 1,
                        audio_outputs: 1,
                    });
                }
                all_errors.extend(clap.errors);

                // LV2
                let lv2 = crate::lv2_host::scan_lv2_plugins();
                for p in &lv2.plugins {
                    all_plugins.push(crate::ipc::ScannedPlugin {
                        format: "lv2".to_string(),
                        name: p.name.clone(),
                        vendor: p.author.clone(),
                        plugin_id: p.uri.clone(),
                        path: String::new(),
                        category: String::new(),
                        audio_inputs: p.audio_inputs,
                        audio_outputs: p.audio_outputs,
                    });
                }
                all_errors.extend(lv2.errors);

                let scan_ms = scan_start.elapsed().as_millis() as u64;
                info!(
                    "ScanPlugins complete: {} VST3, {} CLAP, {} LV2 ({} total) in {}ms",
                    vst3.plugins.len(), clap.plugins.len(), lv2.plugins.len(),
                    all_plugins.len(), scan_ms
                );
                let _ = self.event_tx.try_send(Event::PluginScanResult {
                    plugins: all_plugins,
                    scan_time_ms: scan_ms,
                    errors: all_errors,
                });
            }

            Command::LoadPlugin {
                track_id, slot_index, plugin_path, plugin_format, plugin_id,
            } => {
                let mut graph = self.graph.lock();
                let sr = graph.sample_rate as f64;
                let bs = graph.buffer_size() as u32;

                let result: Result<Box<dyn crate::plugin_host::AudioPlugin>, String> = match plugin_format.as_str() {
                    "vst3" => {
                        let cid = if plugin_id.is_empty() { None } else { Some(plugin_id.as_str()) };
                        crate::vst3_host::load_vst3(
                            std::path::Path::new(&plugin_path), cid, sr, bs,
                        ).map(|i| Box::new(i) as Box<dyn crate::plugin_host::AudioPlugin>)
                    }
                    "clap" => {
                        crate::clap_host::load_clap(
                            std::path::Path::new(&plugin_path), &plugin_id, sr, bs,
                        ).map(|i| Box::new(i) as Box<dyn crate::plugin_host::AudioPlugin>)
                    }
                    "lv2" => {
                        crate::lv2_host::Lv2Instance::load(&plugin_id, sr, bs)
                            .map(|i| Box::new(i) as Box<dyn crate::plugin_host::AudioPlugin>)
                    }
                    _ => Err(format!("Unknown plugin format: {}", plugin_format)),
                };

                match result {
                    Ok(plugin) => {
                        let pname = plugin.name().to_string();
                        let pcount = plugin.parameter_count();
                        let latency = plugin.latency_samples();

                        if let Some(idx) = graph.find_track_index(&track_id) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                // Ensure we have enough slots
                                while track.plugin_slots.len() <= slot_index as usize {
                                    let si = track.plugin_slots.len() as u8;
                                    track.plugin_slots.push(
                                        crate::plugin_host::PluginSlot::new(si)
                                    );
                                }
                                track.plugin_slots[slot_index as usize].plugin = Some(plugin);
                                track.plugin_slots[slot_index as usize].enabled = true;

                                info!(
                                    "Loaded {} plugin '{}' on track '{}' slot {} ({} params, {} lat)",
                                    plugin_format, pname, track_id, slot_index, pcount, latency
                                );
                                let _ = self.event_tx.try_send(Event::PluginLoaded {
                                    track_id, slot_index,
                                    plugin_name: pname,
                                    plugin_format,
                                    param_count: pcount,
                                    latency_samples: latency,
                                });
                            }
                        } else {
                            warn!("LoadPlugin: track '{}' not found", track_id);
                        }
                    }
                    Err(e) => {
                        error!("LoadPlugin failed ({}): {}", plugin_format, e);
                        let _ = self.event_tx.try_send(Event::Error {
                            code: 200,
                            message: format!("LoadPlugin failed: {}", e),
                        });
                    }
                }
            }

            Command::UnloadPlugin { track_id, slot_index } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(slot) = track.plugin_slots.get_mut(slot_index as usize) {
                            if let Some(ref plugin) = slot.plugin {
                                info!("Unloading plugin '{}' from track '{}' slot {}",
                                      plugin.name(), track_id, slot_index);
                            }
                            slot.plugin = None;
                            slot.enabled = false;
                        }
                    }
                }
            }

            Command::SetPluginParam { track_id, slot_index, param_index, value } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(slot) = track.plugin_slots.get_mut(slot_index as usize) {
                            if let Some(ref mut plugin) = slot.plugin {
                                plugin.set_parameter(param_index, value);
                            }
                        }
                    }
                }
            }

            Command::SavePluginState { track_id, slot_index } => {
                let graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track(idx) {
                        if let Some(slot) = track.plugin_slots.get(slot_index as usize) {
                            if let Some(ref plugin) = slot.plugin {
                                let state = plugin.save_state();
                                let encoded = crate::clip_renderer::base64_encode(&state);
                                let _ = self.event_tx.try_send(Event::PluginState {
                                    track_id,
                                    slot_index,
                                    state_b64: encoded,
                                });
                            }
                        }
                    }
                }
            }

            Command::LoadPluginState { track_id, slot_index, state_b64 } => {
                match crate::clip_renderer::base64_decode(&state_b64) {
                    Ok(data) => {
                        let mut graph = self.graph.lock();
                        if let Some(idx) = graph.find_track_index(&track_id) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                if let Some(slot) = track.plugin_slots.get_mut(slot_index as usize) {
                                    if let Some(ref mut plugin) = slot.plugin {
                                        if let Err(e) = plugin.load_state(&data) {
                                            warn!("LoadPluginState: {}", e);
                                        } else {
                                            info!("Loaded plugin state on track '{}' slot {}",
                                                  track_id, slot_index);
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!("LoadPluginState: base64 decode error: {}", e);
                    }
                }
            }
            Command::MidiNoteOn { track_id, note, velocity, .. } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            inst.push_midi(crate::instruments::MidiEvent::NoteOn { note, velocity });
                        }
                    }
                }
            }
            Command::MidiNoteOff { track_id, note, .. } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            inst.push_midi(crate::instruments::MidiEvent::NoteOff { note });
                        }
                    }
                }
            }
            Command::MidiCC { track_id, cc, value, .. } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            inst.push_midi(crate::instruments::MidiEvent::CC { cc, value });
                        }
                    }
                }
            }
            // -- Instruments (Phase R6) ----------------------------------------
            Command::LoadInstrument { track_id, instrument_type, instrument_id } => {
                let mut graph = self.graph.lock();
                let sr = graph.sample_rate;
                let buf_size = graph.buffer_size();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    let inst_id = if instrument_id.is_empty() {
                        format!("inst_{}", track_id)
                    } else {
                        instrument_id.clone()
                    };
                    if let Some(itype) = crate::instruments::InstrumentType::from_str(&instrument_type) {
                        if let Some(inst) = itype.create(inst_id.clone(), sr, buf_size) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                track.instrument = Some(inst);
                                info!("Loaded instrument '{}' (type={}) on track '{}'", inst_id, instrument_type, track_id);
                            }
                        } else {
                            warn!("Failed to create instrument type '{}'", instrument_type);
                        }
                    } else {
                        warn!("Unknown instrument type: '{}'", instrument_type);
                    }
                }
            }
            Command::UnloadInstrument { track_id } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if track.instrument.is_some() {
                            track.instrument = None;
                            info!("Unloaded instrument from track '{}'", track_id);
                        }
                    }
                }
            }
            Command::LoadSample { track_id, wav_path, root_note, fine_tune } => {
                // Load sample data on this thread (non-audio-safe, but command thread is OK)
                match crate::sample::SampleData::load_wav(&wav_path) {
                    Ok(mut sample_data) => {
                        sample_data.root_note = root_note;
                        sample_data.fine_tune = fine_tune;
                        let mut graph = self.graph.lock();
                        if let Some(idx) = graph.find_track_index(&track_id) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                if let Some(ref mut inst) = track.instrument {
                                    // Send sample via command channel for audio-thread-safe delivery
                                    // For ProSampler, we downcast or use InstrumentNode trait
                                    // Simple approach: push_midi is for MIDI, we need a different path
                                    // For now, set directly (we hold the mutex, audio thread is blocked)
                                    // This is safe because the mutex serializes access
                                    use crate::instruments::sampler::ProSamplerInstrument;
                                    // Use the command sender
                                    let any = inst.as_any_mut();
                                    if let Some(sampler) = any.downcast_mut::<ProSamplerInstrument>() {
                                        sampler.set_sample(sample_data);
                                        info!("Loaded sample '{}' (root={}, tune={}) on track '{}'",
                                              wav_path, root_note, fine_tune, track_id);
                                    } else {
                                        warn!("Track '{}' instrument is not a ProSampler", track_id);
                                    }
                                } else {
                                    warn!("Track '{}' has no instrument loaded", track_id);
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load sample '{}': {}", wav_path, e);
                    }
                }
            }
            Command::ClearSample { track_id } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            // Send AllSoundOff + clear
                            inst.push_midi(crate::instruments::MidiEvent::AllSoundOff);
                            info!("Cleared sample on track '{}'", track_id);
                        }
                    }
                }
            }
            Command::SetInstrumentParam { track_id, param_name, value } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::sampler::{ProSamplerInstrument, SamplerCommand};
                            let any = inst.as_any_mut();
                            if let Some(sampler) = any.downcast_mut::<ProSamplerInstrument>() {
                                let cmd = match param_name.as_str() {
                                    "attack" => Some(SamplerCommand::SetAdsr {
                                        attack: value as f32,
                                        decay: sampler.params.decay,
                                        sustain: sampler.params.sustain,
                                        release: sampler.params.release,
                                    }),
                                    "decay" => Some(SamplerCommand::SetAdsr {
                                        attack: sampler.params.attack,
                                        decay: value as f32,
                                        sustain: sampler.params.sustain,
                                        release: sampler.params.release,
                                    }),
                                    "sustain" => Some(SamplerCommand::SetAdsr {
                                        attack: sampler.params.attack,
                                        decay: sampler.params.decay,
                                        sustain: value as f32,
                                        release: sampler.params.release,
                                    }),
                                    "release" => Some(SamplerCommand::SetAdsr {
                                        attack: sampler.params.attack,
                                        decay: sampler.params.decay,
                                        sustain: sampler.params.sustain,
                                        release: value as f32,
                                    }),
                                    "gain" => Some(SamplerCommand::SetGain(value as f32)),
                                    "pan" => Some(SamplerCommand::SetPan(value as f32)),
                                    "velocity_curve" => Some(SamplerCommand::SetVelocityCurve(value as f32)),
                                    _ => {
                                        warn!("Unknown sampler param: '{}'", param_name);
                                        None
                                    }
                                };
                                if let Some(cmd) = cmd {
                                    sampler.apply_command(cmd);
                                }
                            }
                        }
                    }
                }
            }
            // -- Built-in FX Chain (Phase R4) ---------------------------------
            Command::AddFx {
                track_id,
                fx_type,
                slot_id,
                position,
            } => {
                let mut graph = self.graph.lock();
                let sr = graph.sample_rate as f32;
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(fx) = crate::fx::chain::create_fx(&fx_type, sr) {
                        if let Some(track) = graph.get_track_mut(idx) {
                            if let Some(pos) = position {
                                track.fx_chain.insert_fx(pos as usize, fx, slot_id.clone());
                            } else {
                                track.fx_chain.add_fx(fx, slot_id.clone());
                            }
                            info!("Added FX '{}' (type={}) to track '{}'", slot_id, fx_type, track_id);
                        }
                    } else {
                        warn!("Unknown FX type '{}' for AddFx", fx_type);
                    }
                }
            }
            Command::RemoveFx {
                track_id,
                slot_index,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        track.fx_chain.remove_fx(slot_index as usize);
                    }
                }
            }
            Command::SetFxBypass {
                track_id,
                slot_index,
                bypass,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        track.fx_chain.set_bypass(slot_index as usize, bypass);
                    }
                }
            }
            Command::SetFxEnabled {
                track_id,
                slot_index,
                enabled,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        track.fx_chain.set_enabled(slot_index as usize, enabled);
                    }
                }
            }
            Command::ReorderFx {
                track_id,
                from_index,
                to_index,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        track.fx_chain.reorder(from_index as usize, to_index as usize);
                    }
                }
            }
            Command::SetFxChainMix {
                track_id,
                mix,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        track.fx_chain.set_mix(mix as f32);
                    }
                }
            }

            // -- MultiSample Instrument (Phase R6B) ---------------------------
            Command::AddSampleZone {
                track_id, wav_path, root_note, key_lo, key_hi,
                vel_lo, vel_hi, gain, pan, tune_semitones, tune_cents, rr_group,
            } => {
                match crate::sample::SampleData::load_wav(&wav_path) {
                    Ok(mut sample_data) => {
                        sample_data.root_note = root_note;
                        let mut graph = self.graph.lock();
                        if let Some(idx) = graph.find_track_index(&track_id) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                if let Some(ref mut inst) = track.instrument {
                                    use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand};
                                    let any = inst.as_any_mut();
                                    if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                        ms.apply_command(MultiSampleCommand::AddZone {
                                            key_lo, key_hi, vel_lo, vel_hi, root_note,
                                            gain: gain as f32, pan: pan as f32,
                                            tune_semitones: tune_semitones as f32,
                                            tune_cents: tune_cents as f32,
                                            sample: sample_data, rr_group,
                                        });
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load sample zone '{}': {}", wav_path, e);
                    }
                }
            }
            Command::RemoveSampleZone { track_id, zone_id } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand};
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                ms.apply_command(MultiSampleCommand::RemoveZone { zone_id });
                            }
                        }
                    }
                }
            }
            Command::ClearAllZones { track_id } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand};
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                ms.apply_command(MultiSampleCommand::ClearAllZones);
                            }
                        }
                    }
                }
            }
            Command::SetZoneFilter {
                track_id, zone_id, filter_type, cutoff_hz, resonance, env_amount,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand, ZoneFilterType};
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                ms.apply_command(MultiSampleCommand::SetZoneFilter {
                                    zone_id,
                                    filter_type: ZoneFilterType::from_str(&filter_type),
                                    cutoff_hz: cutoff_hz as f32,
                                    resonance: resonance as f32,
                                    env_amount: env_amount as f32,
                                });
                            }
                        }
                    }
                }
            }
            Command::SetZoneEnvelope {
                track_id, zone_id, env_type, attack, decay, sustain, release,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand};
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                if env_type == "filter" {
                                    ms.apply_command(MultiSampleCommand::SetZoneFilterEnvelope {
                                        zone_id,
                                        attack: attack as f32,
                                        decay: decay as f32,
                                        sustain: sustain as f32,
                                        release: release as f32,
                                    });
                                } else {
                                    ms.apply_command(MultiSampleCommand::SetZoneAmpEnvelope {
                                        zone_id,
                                        attack: attack as f32,
                                        decay: decay as f32,
                                        sustain: sustain as f32,
                                        release: release as f32,
                                    });
                                }
                            }
                        }
                    }
                }
            }
            Command::SetZoneLfo {
                track_id, zone_id, lfo_index, rate_hz, shape,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand};
                            use crate::dsp::lfo::LfoShape;
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                let lfo_shape = match shape.as_str() {
                                    "triangle" => LfoShape::Triangle,
                                    "square" => LfoShape::Square,
                                    "saw" => LfoShape::SawUp,
                                    "sample_hold" => LfoShape::SampleAndHold,
                                    _ => LfoShape::Sine,
                                };
                                ms.apply_command(MultiSampleCommand::SetZoneLfo {
                                    zone_id, lfo_index, rate_hz: rate_hz as f32, shape: lfo_shape,
                                });
                            }
                        }
                    }
                }
            }
            Command::SetZoneModSlot {
                track_id, zone_id, slot_index, source, destination, amount,
            } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand, ModSource, ModDest};
                            let any = inst.as_any_mut();
                            if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                ms.apply_command(MultiSampleCommand::SetZoneModSlot {
                                    zone_id, slot_index,
                                    source: ModSource::from_str(&source),
                                    destination: ModDest::from_str(&destination),
                                    amount: amount as f32,
                                });
                            }
                        }
                    }
                }
            }
            Command::AutoMapZones {
                track_id, mode, base_note, wav_paths,
            } => {
                // Load all samples on command thread
                let mut samples = Vec::new();
                for path in &wav_paths {
                    match crate::sample::SampleData::load_wav(path) {
                        Ok(s) => samples.push(s),
                        Err(e) => {
                            warn!("AutoMap: failed to load '{}': {}", path, e);
                        }
                    }
                }
                if !samples.is_empty() {
                    let mut graph = self.graph.lock();
                    if let Some(idx) = graph.find_track_index(&track_id) {
                        if let Some(track) = graph.get_track_mut(idx) {
                            if let Some(ref mut inst) = track.instrument {
                                use crate::instruments::multisample::{MultiSampleInstrument, MultiSampleCommand, AutoMapMode};
                                let any = inst.as_any_mut();
                                if let Some(ms) = any.downcast_mut::<MultiSampleInstrument>() {
                                    ms.apply_command(MultiSampleCommand::AutoMap {
                                        mode: AutoMapMode::from_str(&mode),
                                        base_note,
                                        samples,
                                    });
                                }
                            }
                        }
                    }
                }
            }

            // -- DrumMachine Instrument (Phase R7A) ----------------------------
            Command::LoadDrumPadSample { track_id, pad_index, wav_path } => {
                match crate::sample::SampleData::load_wav(&wav_path) {
                    Ok(sample_data) => {
                        let mut graph = self.graph.lock();
                        if let Some(idx) = graph.find_track_index(&track_id) {
                            if let Some(track) = graph.get_track_mut(idx) {
                                if let Some(ref mut inst) = track.instrument {
                                    use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                                    let any = inst.as_any_mut();
                                    if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                        dm.apply_command(DrumMachineCommand::LoadPadSample {
                                            pad_index, sample: sample_data,
                                        });
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load drum sample '{}': {}", wav_path, e);
                    }
                }
            }
            Command::ClearDrumPad { track_id, pad_index } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                dm.apply_command(DrumMachineCommand::ClearPad { pad_index });
                            }
                        }
                    }
                }
            }
            Command::SetDrumPadParam { track_id, pad_index, param_name, value } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand, PadPlayMode};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                let cmd = match param_name.as_str() {
                                    "gain" => Some(DrumMachineCommand::SetPadGain { pad_index, gain: value as f32 }),
                                    "pan" => Some(DrumMachineCommand::SetPadPan { pad_index, pan: value as f32 }),
                                    "tune" => Some(DrumMachineCommand::SetPadTune { pad_index, semitones: value as f32 }),
                                    "choke" => Some(DrumMachineCommand::SetPadChoke { pad_index, group: value as u8 }),
                                    "play_mode" => Some(DrumMachineCommand::SetPadPlayMode {
                                        pad_index,
                                        mode: if value > 0.5 { PadPlayMode::Gate } else { PadPlayMode::OneShot },
                                    }),
                                    _ => {
                                        warn!("Unknown drum pad param: '{}'", param_name);
                                        None
                                    }
                                };
                                if let Some(c) = cmd {
                                    dm.apply_command(c);
                                }
                            }
                        }
                    }
                }
            }
            Command::ClearAllDrumPads { track_id } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                dm.apply_command(DrumMachineCommand::ClearAllPads);
                            }
                        }
                    }
                }
            }
            Command::SetDrumBaseNote { track_id, base_note } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                dm.apply_command(DrumMachineCommand::SetBaseNote(base_note));
                            }
                        }
                    }
                }
            }
            Command::SetDrumPadOutput { track_id, pad_index, output_index } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                dm.apply_command(DrumMachineCommand::SetPadOutput { pad_index, output_index });
                            }
                        }
                    }
                }
            }
            Command::SetDrumMultiOutput { track_id, enabled, output_count } => {
                let mut graph = self.graph.lock();
                if let Some(idx) = graph.find_track_index(&track_id) {
                    if let Some(track) = graph.get_track_mut(idx) {
                        if let Some(ref mut inst) = track.instrument {
                            use crate::instruments::drum_machine::{DrumMachineInstrument, DrumMachineCommand};
                            let any = inst.as_any_mut();
                            if let Some(dm) = any.downcast_mut::<DrumMachineInstrument>() {
                                dm.apply_command(DrumMachineCommand::SetMultiOutput { enabled, output_count });
                            }
                        }
                    }
                }
            }

            // -- Project Sync (Phase R12B + RA1 v710) --------------------------
            Command::SyncProject { project_json } => {
                match serde_json::from_str::<crate::audio_bridge::ProjectSync>(&project_json) {
                    Ok(sync) => {
                        info!(
                            "SyncProject received: seq={}, {} tracks, {} clips, {} notes",
                            sync.sync_seq, sync.track_count(), sync.clip_count(), sync.note_count()
                        );

                        // RA1 v0.0.20.710: Actually rebuild the AudioGraph
                        self.apply_project_sync(&sync);

                        let _ = self.event_tx.try_send(Event::SyncProjectAck {
                            sync_seq: sync.sync_seq,
                            track_count: sync.track_count() as u16,
                            clip_count: sync.clip_count() as u16,
                        });
                    }
                    Err(e) => {
                        error!("SyncProject JSON parse error: {}", e);
                        let _ = self.event_tx.try_send(Event::Error {
                            code: 200,
                            message: format!("SyncProject parse failed: {}", e),
                        });
                    }
                }
            }
        }
    }

    /// RA1 v0.0.20.710: Rebuild the entire audio engine state from ProjectSync.
    ///
    /// 1. Rebuilds AudioGraph tracks (clears old, creates new with correct params)
    /// 2. Loads audio clips into ClipStore from base64 data
    /// 3. Builds ArrangementSnapshot (clip placements)
    /// 4. Updates transport (BPM, time sig, loop region)
    /// 5. MIDI notes are stored but require instrument nodes for playback
    fn apply_project_sync(&self, sync: &crate::audio_bridge::ProjectSync) {
        use crate::audio_graph::TrackKind;

        let sr = sync.sample_rate;
        let bpm = sync.bpm;

        // --- 1. Update transport ---
        {
            self.transport.set_bpm(bpm);
            self.transport.set_time_signature(sync.time_sig_num, sync.time_sig_den);
            self.transport.set_loop(
                sync.loop_enabled,
                sync.loop_start_beat,
                sync.loop_end_beat,
            );
        }

        // --- 2. Rebuild AudioGraph tracks ---
        {
            let mut graph = self.graph.lock();

            // Add tracks that don't exist yet, update params for existing
            for tc in &sync.tracks {
                let tk = TrackKind::from_str(&tc.kind);
                let idx = tc.track_index;

                // Check if track exists
                if graph.get_track(idx).is_none() {
                    graph.add_track(tc.track_id.clone(), idx, tk);
                    info!("RA1: Added track {} (idx={}, kind={})", tc.track_id, idx, tc.kind);
                }

                // Apply parameters via TrackNode.set_param
                {
                    use crate::ipc::TrackParam;
                    if let Some(tn) = graph.get_track(idx) {
                        tn.set_param(TrackParam::Volume, tc.volume);
                        tn.set_param(TrackParam::Pan, tc.pan);
                        tn.set_param(TrackParam::Mute, if tc.muted { 1.0 } else { 0.0 });
                        tn.set_param(TrackParam::Solo, if tc.soloed { 1.0 } else { 0.0 });
                    }
                }

                // Group routing
                if let Some(gi) = tc.group_index {
                    graph.set_group_routing(idx, Some(gi));
                }
            }

            info!("RA1: AudioGraph rebuilt with {} tracks", sync.tracks.len());
        }

        // --- 3. Load audio clips into ClipStore ---
        {
            let mut loaded = 0u32;
            for cc in &sync.clips {
                if cc.kind == "audio" {
                    if let Some(ref b64) = cc.audio_b64 {
                        if !b64.is_empty() {
                            let clip_sr = cc.source_sr.unwrap_or(sr);
                            let clip_ch = cc.source_channels.unwrap_or(2);
                            match crate::clip_renderer::AudioClipData::from_base64(
                                cc.clip_id.clone(),
                                clip_ch,
                                clip_sr,
                                b64,
                            ) {
                                Ok(clip_data) => {
                                    self.clip_store.insert(clip_data);
                                    loaded += 1;
                                }
                                Err(e) => {
                                    warn!("RA1: Failed to decode clip {}: {}", cc.clip_id, e);
                                }
                            }
                        }
                    }
                }
            }
            if loaded > 0 {
                info!("RA1: Loaded {} audio clips into ClipStore", loaded);
            }
        }

        // --- 4. Build ArrangementSnapshot from clips ---
        {
            use crate::clip_renderer::{PlacedClip, ArrangementSnapshot};

            let sr_f = sr as f64;
            let beat_to_samples = |beat: f64| -> i64 {
                (beat * sr_f * 60.0 / bpm) as i64
            };

            let mut placed: Vec<PlacedClip> = Vec::new();
            for cc in &sync.clips {
                // Find track_index from track_id
                let track_index = sync.tracks.iter()
                    .find(|t| t.track_id == cc.track_id)
                    .map(|t| t.track_index)
                    .unwrap_or(0);

                let start = beat_to_samples(cc.start_beats);
                let end = beat_to_samples(cc.start_beats + cc.length_beats);
                let offset = beat_to_samples(cc.offset_beats);

                placed.push(PlacedClip {
                    clip_id: cc.clip_id.clone(),
                    track_index,
                    start_sample: start,
                    end_sample: end,
                    clip_offset_samples: offset,
                    gain: cc.gain as f32,
                    muted: false,
                });
            }

            let snapshot = ArrangementSnapshot::new(placed);
            self.renderer.set_arrangement(snapshot);
            info!("RA1: ArrangementSnapshot set with {} clips", sync.clips.len());
        }

        // --- 5. Load MIDI notes into scheduler (v0.0.20.725) ---
        // This is THE crucial step: MIDI notes from the arrangement get loaded
        // into the MidiScheduler which will dispatch NoteOn/NoteOff events
        // to the correct instrument nodes during process_audio().
        {
            let mut sched = self.midi_scheduler.lock();
            sched.load_from_sync(&sync.clips, &sync.midi_notes, &sync.tracks);
            if sched.event_count() > 0 {
                info!("RA1: MidiScheduler loaded {} events from {} MIDI notes",
                      sched.event_count(), sync.midi_notes.len());
            }
        }

        // --- 6. Load instruments for tracks that have instrument_type ---
        for tc in &sync.tracks {
            if let Some(ref itype_str) = tc.instrument_type {
                if itype_str.is_empty() {
                    continue;
                }
                let inst_id = tc.instrument_id.clone().unwrap_or_default();
                let inst_id = if inst_id.is_empty() {
                    format!("inst_{}", tc.track_id)
                } else {
                    inst_id
                };
                if let Some(itype) = crate::instruments::InstrumentType::from_str(itype_str) {
                    let mut graph = self.graph.lock();
                    let buf_size = graph.buffer_size();
                    if let Some(track) = graph.get_track_mut(tc.track_index) {
                        // Only create if not already loaded
                        if track.instrument.is_none() {
                            if let Some(inst) = itype.create(inst_id.clone(), sr, buf_size) {
                                track.instrument = Some(inst);
                                info!("RA1: Loaded instrument '{}' (type={}) on track '{}'",
                                      inst_id, itype_str, tc.track_id);
                            }
                        }
                    }
                }
            }
        }

        info!("RA1: ProjectSync applied (seq={}, bpm={}, {} tracks, {} clips)",
              sync.sync_seq, bpm, sync.tracks.len(), sync.clips.len());
    }

    /// Called from the audio callback. Processes the graph and returns output.
    /// The output samples should be written to the audio device.
    pub fn process_audio(&self, output: &mut [f32], frames: usize, channels: usize) {
        let t_start = std::time::Instant::now();

        // 1. Drain pending commands
        self.drain_commands();

        // 2. Drain lock-free parameter ring (GUI → audio thread)
        {
            let graph = self.graph.lock();
            self.param_ring.drain(|param_id, value| {
                // Decode param_id: high 16 bits = track_index, low 16 bits = param type
                let track_idx = (param_id >> 16) as u16;
                let param_type = (param_id & 0xFFFF) as u16;
                if let Some(track) = graph.get_track(track_idx) {
                    match param_type {
                        0 => track.set_param(crate::ipc::TrackParam::Volume, value),
                        1 => track.set_param(crate::ipc::TrackParam::Pan, value),
                        2 => track.set_param(crate::ipc::TrackParam::Mute, value),
                        3 => track.set_param(crate::ipc::TrackParam::Solo, value),
                        _ => {}
                    }
                }
            });
        }

        // 3. Render arrangement clips + MIDI into track buffers
        {
            let mut graph = self.graph.lock();
            graph.silence_all();

            let is_playing = self.transport.playing.load(std::sync::atomic::Ordering::Relaxed);

            // Phase 1B: Render audio clips from ArrangementRenderer
            let position = self.transport.position_samples();
            let sr = graph.sample_rate;
            if is_playing {
                self.renderer.render_all_tracks(&mut graph, position, frames, sr);
            }

            // v0.0.20.725: Dispatch MIDI notes from arrangement clips to instruments.
            // This is the bridge between "MIDI data in project" and "instrument audio output".
            if is_playing {
                let bpm = graph.tempo_bpm as f64;
                let sr_f = sr as f64;
                let beat_start = self.transport.position_beats();
                let beats_per_buffer = if bpm > 0.0 && sr_f > 0.0 {
                    (frames as f64 / sr_f) * (bpm / 60.0)
                } else {
                    0.0
                };
                let beat_end = beat_start + beats_per_buffer;

                let mut sched = self.midi_scheduler.lock();
                for evt in sched.schedule_for_buffer(beat_start, beat_end, true) {
                    if let Some(track) = graph.get_track_mut(evt.track_index) {
                        if let Some(ref mut inst) = track.instrument {
                            if evt.is_note_on {
                                inst.push_midi(crate::instruments::MidiEvent::NoteOn {
                                    note: evt.pitch,
                                    velocity: evt.velocity,
                                });
                            } else {
                                inst.push_midi(crate::instruments::MidiEvent::NoteOff {
                                    note: evt.pitch,
                                });
                            }
                        }
                    }
                }
            }

            // 4. Process the audio graph (instruments + FX + volume/pan/mute/solo → master)
            let master_buf = graph.process();

            // 5. Copy master output to device buffer
            let copy_len = (frames * channels).min(output.len()).min(master_buf.data.len());
            output[..copy_len].copy_from_slice(&master_buf.data[..copy_len]);

            // Zero any remaining output samples
            if copy_len < output.len() {
                output[copy_len..].fill(0.0);
            }

            // 4. Send meter levels (~30Hz)
            let counter = self
                .meter_counter
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            let sr = self.transport.sample_rate() as u32;
            let meter_interval = if sr > 0 { sr / (frames as u32 * 30).max(1) } else { 50 };

            if counter % meter_interval.max(1) == 0 {
                // Master meters
                let (pl, pr) = master_buf.peak_levels();
                let (rl, rr) = master_buf.rms_levels();
                let _ = self.event_tx.try_send(Event::MasterMeterLevel {
                    peak_l: pl,
                    peak_r: pr,
                    rms_l: rl,
                    rms_r: rr,
                });

                // Track meters
                let track_meters: Vec<TrackMeterLevel> = graph
                    .all_track_meters()
                    .into_iter()
                    .map(|(idx, pl, pr, rl, rr)| TrackMeterLevel {
                        track_index: idx,
                        peak_l: pl,
                        peak_r: pr,
                        rms_l: rl,
                        rms_r: rr,
                    })
                    .collect();

                if !track_meters.is_empty() {
                    let _ = self.event_tx.try_send(Event::MeterLevels {
                        levels: track_meters,
                    });
                }
            }
        }

        // 5. Advance transport
        self.transport.advance(frames);

        // 6. Send playhead position (~30Hz, reuse meter counter)
        let counter = self
            .meter_counter
            .load(std::sync::atomic::Ordering::Relaxed);
        let sr = self.transport.sample_rate() as u32;
        let meter_interval = if sr > 0 {
            sr / (frames as u32 * 30).max(1)
        } else {
            50
        };
        if counter % meter_interval.max(1) == 0 {
            let _ = self.event_tx.try_send(Event::PlayheadPosition {
                beat: self.transport.position_beats(),
                sample_position: self.transport.position_samples(),
                is_playing: self
                    .transport
                    .playing
                    .load(std::sync::atomic::Ordering::Relaxed),
            });
        }

        // 7. Store render time for Pong cpu_load reporting
        let elapsed_us = t_start.elapsed().as_micros() as u32;
        self.last_render_us.store(elapsed_us, std::sync::atomic::Ordering::Relaxed);
    }

    /// Record an xrun.
    pub fn record_xrun(&self) {
        self.xrun_count
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    }
}
