// ==========================================================================
// DrumMachine Instrument — Pad-based sampler with choke groups
// ==========================================================================
// v0.0.20.677 — Phase R7A
//
// A drum machine with 128 pad slots mapped to MIDI notes.
// Each pad has its own sample, gain, pan, tune, choke group, and play mode.
//
// Built on top of:
//   - R1: DSP Primitives (AdsrEnvelope, interpolation)
//   - R5: Sample Engine (SampleData, SampleVoice)
//   - R6A: InstrumentNode trait, lock-free channels
//
// Architecture:
//   - DrumPad: per-pad config (sample, gain, pan, tune, choke, mode)
//   - DrumVoice: active voice playing a pad's sample
//   - DrumMachineInstrument: top-level InstrumentNode, 128 pads, 64 voices
//
// Signal flow:
//   MIDI NoteOn(N) → pad = pads[N - base_note]
//   → choke: kill voices in same choke group
//   → allocate voice → play sample at pitch + tune
//   → voice envelope × velocity × pad gain → pad pan → sum to output
//
// Rules:
//   ✅ process() is zero-alloc (all pads/voices pre-allocated)
//   ✅ MIDI events delivered via lock-free bounded channel
//   ✅ Sample data is Arc-shared (zero-copy)
//   ❌ NO allocations in process()
//   ❌ NO locks in process()
// ==========================================================================

use crossbeam_channel::{bounded, Receiver, Sender, TryRecvError};
use log::{debug, warn};

use crate::audio_graph::AudioBuffer;
use crate::audio_node::ProcessContext;
use crate::dsp::envelope::AdsrEnvelope;
use crate::dsp::interpolation::interpolate_cubic;
use crate::sample::SampleData;
use super::{InstrumentNode, MidiEvent};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIDI_RING_CAPACITY: usize = 256;
const CMD_RING_CAPACITY: usize = 64;

/// Maximum pad slots (4 banks × 16 pads × 2).
const MAX_PADS: usize = 128;

/// Maximum simultaneous voices.
const MAX_VOICES: usize = 64;

/// Maximum choke groups (0 = none, 1–8 = groups).
const MAX_CHOKE_GROUPS: usize = 9;

/// Default base MIDI note (GM Drum Map: bass drum = 36).
const DEFAULT_BASE_NOTE: u8 = 36;

/// Default pad names (first 16 — GM standard).
const GM_PAD_NAMES: [&str; 16] = [
    "Kick", "Snare", "CHat", "OHat",
    "Clap", "Tom1", "Perc", "Rim",
    "Tom2", "Tom3", "Ride", "Crash",
    "Pad13", "Pad14", "Pad15", "Pad16",
];

// ---------------------------------------------------------------------------
// Play Mode
// ---------------------------------------------------------------------------

/// How a drum pad plays its sample.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PadPlayMode {
    /// One-shot: play to end, ignore note-off.
    OneShot,
    /// Gate: play while note held, release on note-off.
    Gate,
}

impl PadPlayMode {
    pub fn from_str(s: &str) -> Self {
        match s {
            "gate" | "Gate" => Self::Gate,
            _ => Self::OneShot,
        }
    }
}

// ---------------------------------------------------------------------------
// Drum Pad
// ---------------------------------------------------------------------------

/// A single drum pad slot.
#[derive(Clone)]
pub struct DrumPad {
    /// Pad index (0–127).
    pub index: u8,
    /// Pad name (for display).
    pub name: [u8; 16],
    pub name_len: u8,

    /// Loaded sample (Arc-shared, cheap to clone).
    pub sample: Option<SampleData>,

    /// Pad gain (0.0–2.0, default 0.8).
    pub gain: f32,
    /// Pad pan (-1.0 left .. 1.0 right).
    pub pan: f32,
    /// Tune offset in semitones (-24..24).
    pub tune_semitones: f32,

    /// Choke group (0 = none, 1–8 = mutual exclusion).
    pub choke_group: u8,
    /// Play mode (one-shot or gate).
    pub play_mode: PadPlayMode,

    /// Output bus index (0 = main, 1–15 = auxiliary outputs).
    pub output_index: u8,

    /// Is this pad active (has sample)?
    pub active: bool,

    /// ADSR envelope params for this pad.
    pub attack: f32,
    pub decay: f32,
    pub sustain: f32,
    pub release: f32,
}

impl DrumPad {
    fn new(index: u8) -> Self {
        let mut name = [0u8; 16];
        let nm = if (index as usize) < GM_PAD_NAMES.len() {
            GM_PAD_NAMES[index as usize]
        } else {
            "Pad"
        };
        let bytes = nm.as_bytes();
        let len = bytes.len().min(16);
        name[..len].copy_from_slice(&bytes[..len]);

        Self {
            index,
            name,
            name_len: len as u8,
            sample: None,
            gain: 0.8,
            pan: 0.0,
            tune_semitones: 0.0,
            choke_group: 0,
            play_mode: PadPlayMode::OneShot,
            output_index: 0,
            active: false,
            attack: 0.001,
            decay: 0.0,
            sustain: 1.0,
            release: 0.05,
        }
    }

    /// Get the name as a string.
    pub fn name_str(&self) -> &str {
        std::str::from_utf8(&self.name[..self.name_len as usize]).unwrap_or("Pad")
    }
}

// ---------------------------------------------------------------------------
// Drum Voice — active playing instance
// ---------------------------------------------------------------------------

/// A voice playing a drum pad's sample.
struct DrumVoice {
    /// Is this voice active?
    active: bool,
    /// Which pad triggered this voice.
    pad_index: u8,
    /// MIDI note that triggered this voice.
    note: u8,
    /// Choke group (cached from pad at trigger time).
    choke_group: u8,
    /// Is this a gate voice (releases on note-off)?
    is_gate: bool,
    /// Output bus index (cached from pad at trigger time, 0=main, 1-15=aux).
    output_index: u8,

    /// Current sample position (fractional).
    position: f64,
    /// Playback rate (pitch + SR conversion + tune).
    playback_rate: f64,

    /// ADSR amplitude envelope.
    envelope: AdsrEnvelope,
    /// Velocity gain (0.0–1.0).
    velocity_gain: f32,
    /// Pad gain (cached at trigger time).
    pad_gain: f32,
    /// Pad pan (cached at trigger time).
    pad_pan: f32,

    /// Reference to sample data (Arc-shared).
    sample: Option<SampleData>,
}

impl DrumVoice {
    fn new(sample_rate: f32) -> Self {
        Self {
            active: false,
            pad_index: 0,
            note: 0,
            choke_group: 0,
            is_gate: false,
            output_index: 0,
            position: 0.0,
            playback_rate: 1.0,
            envelope: AdsrEnvelope::new(0.001, 0.0, 1.0, 0.05, sample_rate),
            velocity_gain: 1.0,
            pad_gain: 0.8,
            pad_pan: 0.0,
            sample: None,
        }
    }

    /// Trigger this voice to play a pad.
    fn trigger(
        &mut self,
        pad: &DrumPad,
        sample: &SampleData,
        note: u8,
        velocity: f32,
        engine_sr: u32,
    ) {
        self.active = true;
        self.pad_index = pad.index;
        self.note = note;
        self.choke_group = pad.choke_group;
        self.is_gate = pad.play_mode == PadPlayMode::Gate;
        self.output_index = pad.output_index;
        self.velocity_gain = velocity.clamp(0.0, 1.0);
        self.pad_gain = pad.gain;
        self.pad_pan = pad.pan;
        self.position = 0.0;

        // Calculate playback rate with tune offset
        let tune = pad.tune_semitones as f64;
        let pitch = 2.0f64.powf(tune / 12.0);
        let sr_ratio = sample.sample_rate as f64 / engine_sr as f64;
        self.playback_rate = pitch * sr_ratio;

        // Set envelope
        self.envelope.set_params(pad.attack, pad.decay, pad.sustain, pad.release);
        self.envelope.note_on();

        self.sample = Some(sample.clone());
    }

    /// Release (for gate mode).
    fn release(&mut self) {
        if self.active {
            self.envelope.note_off();
        }
    }

    /// Kill immediately.
    fn kill(&mut self) {
        self.active = false;
        self.envelope.kill();
        self.sample = None;
    }

    fn set_sample_rate(&mut self, sr: f32) {
        self.envelope.set_sample_rate(sr);
    }

    /// Render this voice into a stereo buffer (additive).
    /// Returns number of frames rendered.
    #[inline]
    fn render(&mut self, output: &mut [f32], frames: usize) -> usize {
        if !self.active {
            return 0;
        }

        let sample = match &self.sample {
            Some(s) => s,
            None => {
                self.active = false;
                return 0;
            }
        };

        let sample_frames = sample.frames;
        if sample_frames == 0 {
            self.active = false;
            return 0;
        }

        let data = &sample.data;
        let vel = self.velocity_gain;
        let pg = self.pad_gain;
        let rate = self.playback_rate;

        // Pre-compute pan
        let pan_angle = (self.pad_pan + 1.0) * 0.25 * std::f32::consts::PI;
        let pan_l = pan_angle.cos() * std::f32::consts::SQRT_2;
        let pan_r = pan_angle.sin() * std::f32::consts::SQRT_2;

        let mut rendered = 0;

        for frame in 0..frames {
            let env = self.envelope.process();

            if !self.envelope.is_active() {
                self.active = false;
                self.sample = None;
                break;
            }

            let gain = env * vel * pg;

            // Read sample with cubic interpolation
            let pos = self.position;
            let idx = pos as usize;
            let frac = (pos - idx as f64) as f32;

            let (l, r) = if idx + 2 < sample_frames {
                let i0 = if idx > 0 { idx - 1 } else { 0 };
                let i1 = idx;
                let i2 = idx + 1;
                let i3 = idx + 2;
                let l = interpolate_cubic(
                    data[i0 * 2], data[i1 * 2], data[i2 * 2], data[i3 * 2], frac,
                );
                let r = interpolate_cubic(
                    data[i0 * 2 + 1], data[i1 * 2 + 1], data[i2 * 2 + 1], data[i3 * 2 + 1], frac,
                );
                (l, r)
            } else if idx < sample_frames {
                let (l0, r0) = (data[idx * 2], data[idx * 2 + 1]);
                if idx + 1 < sample_frames {
                    let (l1, r1) = (data[(idx + 1) * 2], data[(idx + 1) * 2 + 1]);
                    (l0 + (l1 - l0) * frac, r0 + (r1 - r0) * frac)
                } else {
                    (l0, r0)
                }
            } else {
                (0.0, 0.0)
            };

            // Write with pan (additive)
            let out_idx = frame * 2;
            if out_idx + 1 < output.len() {
                output[out_idx] += l * gain * pan_l;
                output[out_idx + 1] += r * gain * pan_r;
            }

            rendered += 1;

            // Advance position
            self.position += rate;

            // End of sample — for one-shot, start release
            if self.position >= sample_frames as f64 {
                if !self.is_gate {
                    // One-shot: start release at end of sample
                    self.envelope.note_off();
                }
                // Clamp to end
                self.position = (sample_frames - 1) as f64;
            }
        }

        rendered
    }
}

// ---------------------------------------------------------------------------
// DrumMachine Commands
// ---------------------------------------------------------------------------

/// Commands sent from command thread to audio thread.
#[derive(Debug, Clone)]
pub enum DrumMachineCommand {
    /// Load a sample onto a pad.
    LoadPadSample { pad_index: u8, sample: SampleData },
    /// Clear a pad's sample.
    ClearPad { pad_index: u8 },
    /// Set pad gain.
    SetPadGain { pad_index: u8, gain: f32 },
    /// Set pad pan.
    SetPadPan { pad_index: u8, pan: f32 },
    /// Set pad tune (semitones).
    SetPadTune { pad_index: u8, semitones: f32 },
    /// Set pad choke group (0=none, 1–8).
    SetPadChoke { pad_index: u8, group: u8 },
    /// Set pad play mode.
    SetPadPlayMode { pad_index: u8, mode: PadPlayMode },
    /// Set pad ADSR envelope.
    SetPadEnvelope { pad_index: u8, attack: f32, decay: f32, sustain: f32, release: f32 },
    /// Set pad name.
    SetPadName { pad_index: u8, name: [u8; 16], name_len: u8 },
    /// Set pad output bus (0=main, 1–15=aux).
    SetPadOutput { pad_index: u8, output_index: u8 },
    /// Enable/disable multi-output mode.
    SetMultiOutput { enabled: bool, output_count: u8 },
    /// Set base note (default 36).
    SetBaseNote(u8),
    /// Set master gain.
    SetMasterGain(f32),
    /// Set master pan.
    SetMasterPan(f32),
    /// Clear all pads.
    ClearAllPads,
}

// ---------------------------------------------------------------------------
// DrumMachineInstrument
// ---------------------------------------------------------------------------

/// 128-pad drum machine with choke groups and per-pad DSP.
pub struct DrumMachineInstrument {
    /// Unique instrument ID.
    id: String,

    /// Pad slots (pre-allocated, 128).
    pads: Vec<DrumPad>,

    /// Pre-allocated voice pool.
    voices: Vec<DrumVoice>,

    /// Base MIDI note (pad 0 = this note).
    base_note: u8,

    /// Master gain.
    master_gain: f32,
    /// Master pan.
    master_pan: f32,

    /// Multi-output enabled (voices route to auxiliary buffers by pad.output_index).
    multi_output_enabled: bool,
    /// Number of output buses (1 = stereo only, 2–16 = main + aux).
    output_count: u8,
    /// Auxiliary output buffers (pre-allocated, index 1..output_count-1).
    /// Index 0 is the main buffer (the InstrumentNode output_buffer).
    aux_buffers: Vec<AudioBuffer>,

    /// MIDI receiver (audio thread).
    midi_rx: Receiver<MidiEvent>,
    /// MIDI sender (command thread).
    midi_tx: Sender<MidiEvent>,

    /// Command receiver (audio thread).
    cmd_rx: Receiver<DrumMachineCommand>,
    /// Command sender (command thread).
    cmd_tx: Sender<DrumMachineCommand>,

    /// Engine sample rate.
    sample_rate: u32,
    /// Buffer size.
    buffer_size: usize,
}

impl DrumMachineInstrument {
    /// Create a new DrumMachine instrument.
    pub fn new(id: String, sample_rate: u32, buffer_size: usize) -> Self {
        let (midi_tx, midi_rx) = bounded(MIDI_RING_CAPACITY);
        let (cmd_tx, cmd_rx) = bounded(CMD_RING_CAPACITY);

        let sr = sample_rate as f32;
        let pads: Vec<DrumPad> = (0..MAX_PADS as u8).map(DrumPad::new).collect();
        let voices: Vec<DrumVoice> = (0..MAX_VOICES).map(|_| DrumVoice::new(sr)).collect();

        Self {
            id,
            pads,
            voices,
            base_note: DEFAULT_BASE_NOTE,
            master_gain: 0.8,
            master_pan: 0.0,
            multi_output_enabled: false,
            output_count: 1,
            aux_buffers: Vec::new(),
            midi_rx,
            midi_tx,
            cmd_rx,
            cmd_tx,
            sample_rate,
            buffer_size,
        }
    }

    /// Get the command sender.
    pub fn command_sender(&self) -> Sender<DrumMachineCommand> {
        self.cmd_tx.clone()
    }

    // -- Command processing --

    #[inline]
    fn process_commands(&mut self) {
        loop {
            match self.cmd_rx.try_recv() {
                Ok(cmd) => self.apply_command(cmd),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    /// Apply a single command.
    pub fn apply_command(&mut self, cmd: DrumMachineCommand) {
        match cmd {
            DrumMachineCommand::LoadPadSample { pad_index, sample } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].sample = Some(sample);
                    self.pads[pi].active = true;
                    debug!("DrumMachine '{}': loaded sample on pad {}", self.id, pad_index);
                }
            }
            DrumMachineCommand::ClearPad { pad_index } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    // Kill any voices playing this pad
                    for v in &mut self.voices {
                        if v.active && v.pad_index == pad_index {
                            v.kill();
                        }
                    }
                    self.pads[pi].sample = None;
                    self.pads[pi].active = false;
                }
            }
            DrumMachineCommand::SetPadGain { pad_index, gain } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].gain = gain.clamp(0.0, 2.0);
                }
            }
            DrumMachineCommand::SetPadPan { pad_index, pan } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].pan = pan.clamp(-1.0, 1.0);
                }
            }
            DrumMachineCommand::SetPadTune { pad_index, semitones } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].tune_semitones = semitones.clamp(-24.0, 24.0);
                }
            }
            DrumMachineCommand::SetPadChoke { pad_index, group } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].choke_group = group.min((MAX_CHOKE_GROUPS - 1) as u8);
                }
            }
            DrumMachineCommand::SetPadPlayMode { pad_index, mode } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].play_mode = mode;
                }
            }
            DrumMachineCommand::SetPadEnvelope { pad_index, attack, decay, sustain, release } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].attack = attack.max(0.0001);
                    self.pads[pi].decay = decay.max(0.0);
                    self.pads[pi].sustain = sustain.clamp(0.0, 1.0);
                    self.pads[pi].release = release.max(0.001);
                }
            }
            DrumMachineCommand::SetPadName { pad_index, name, name_len } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].name = name;
                    self.pads[pi].name_len = name_len.min(16);
                }
            }
            DrumMachineCommand::SetPadOutput { pad_index, output_index } => {
                let pi = pad_index as usize;
                if pi < self.pads.len() {
                    self.pads[pi].output_index = output_index.min(15);
                }
            }
            DrumMachineCommand::SetMultiOutput { enabled, output_count } => {
                let oc = (output_count as usize).clamp(1, 16);
                self.multi_output_enabled = enabled;
                self.output_count = oc as u8;
                // Pre-allocate aux buffers (index 1..oc-1, index 0 = main buffer)
                let buf_size = self.buffer_size;
                self.aux_buffers.clear();
                if enabled && oc > 1 {
                    for _ in 1..oc {
                        self.aux_buffers.push(AudioBuffer::new(buf_size, 2));
                    }
                }
                debug!("DrumMachine '{}': multi-output {} (outputs={})",
                       self.id, if enabled { "ON" } else { "OFF" }, oc);
            }
            DrumMachineCommand::SetBaseNote(note) => {
                self.base_note = note.min(127);
            }
            DrumMachineCommand::SetMasterGain(g) => {
                self.master_gain = g.clamp(0.0, 4.0);
            }
            DrumMachineCommand::SetMasterPan(p) => {
                self.master_pan = p.clamp(-1.0, 1.0);
            }
            DrumMachineCommand::ClearAllPads => {
                for v in &mut self.voices {
                    v.kill();
                }
                for p in &mut self.pads {
                    p.sample = None;
                    p.active = false;
                }
            }
        }
    }

    // -- MIDI processing --

    #[inline]
    fn process_midi(&mut self) {
        loop {
            match self.midi_rx.try_recv() {
                Ok(event) => self.handle_midi_event(event),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => break,
            }
        }
    }

    fn handle_midi_event(&mut self, event: MidiEvent) {
        match event {
            MidiEvent::NoteOn { note, velocity } => {
                // Map note to pad index
                if note < self.base_note {
                    return;
                }
                let pad_idx = (note - self.base_note) as usize;
                if pad_idx >= self.pads.len() || !self.pads[pad_idx].active {
                    return;
                }

                let pad = &self.pads[pad_idx];
                let sample = match &pad.sample {
                    Some(s) => s.clone(),
                    None => return,
                };
                let choke = pad.choke_group;
                let pad_clone = pad.clone();
                let sample_rate = self.sample_rate;

                // Choke: kill all voices in same choke group (if group > 0)
                if choke > 0 {
                    for v in &mut self.voices {
                        if v.active && v.choke_group == choke {
                            v.kill();
                        }
                    }
                }

                // Also kill any existing voice on same pad (retrigger)
                for v in &mut self.voices {
                    if v.active && v.pad_index == pad_idx as u8 {
                        v.kill();
                    }
                }

                // Allocate voice
                if let Some(vi) = Self::alloc_voice_index(&self.voices) {
                    self.voices[vi].trigger(
                        &pad_clone,
                        &sample,
                        note,
                        velocity,
                        sample_rate,
                    );
                }
            }
            MidiEvent::NoteOff { note } => {
                // Only affects gate-mode voices
                for v in &mut self.voices {
                    if v.active && v.note == note && v.is_gate {
                        v.release();
                    }
                }
            }
            MidiEvent::CC { cc, .. } => {
                match cc {
                    120 => {
                        for v in &mut self.voices { v.kill(); }
                    }
                    123 => {
                        for v in &mut self.voices {
                            if v.active { v.release(); }
                        }
                    }
                    _ => {}
                }
            }
            MidiEvent::AllNotesOff => {
                for v in &mut self.voices {
                    if v.active { v.release(); }
                }
            }
            MidiEvent::AllSoundOff => {
                for v in &mut self.voices { v.kill(); }
            }
        }
    }

    /// Find free voice slot index.
    fn alloc_voice_index(voices: &[DrumVoice]) -> Option<usize> {
        // 1. Inactive
        for (i, v) in voices.iter().enumerate() {
            if !v.active { return Some(i); }
        }
        // 2. Steal first (oldest)
        if !voices.is_empty() { Some(0) } else { None }
    }

    // -- Rendering --

    #[inline]
    fn render_voices(&mut self, buffer: &mut AudioBuffer) {
        let frames = buffer.frames;

        // Silence aux buffers if multi-output
        if self.multi_output_enabled {
            for ab in &mut self.aux_buffers {
                ab.silence();
            }
        }

        for voice in &mut self.voices {
            if !voice.active {
                continue;
            }

            let out_idx = voice.output_index as usize;

            if self.multi_output_enabled && out_idx > 0 && out_idx <= self.aux_buffers.len() {
                // Route to auxiliary buffer
                let ab = &mut self.aux_buffers[out_idx - 1];
                voice.render(&mut ab.data, frames);
            } else {
                // Route to main buffer (output 0 or multi-output disabled)
                voice.render(&mut buffer.data, frames);
            }
        }
    }

    /// Get a reference to the auxiliary output buffers (for multi-output routing).
    ///
    /// Returns empty slice if multi-output is disabled.
    /// Index 0 = aux output 1, index 1 = aux output 2, etc.
    /// (Main output is the instrument's own buffer, not in this list.)
    pub fn aux_output_buffers(&self) -> &[AudioBuffer] {
        &self.aux_buffers
    }

    /// Get the number of output buses (1 = stereo, 2+ = multi-output).
    pub fn output_count(&self) -> u8 {
        self.output_count
    }

    /// Is multi-output enabled?
    pub fn is_multi_output(&self) -> bool {
        self.multi_output_enabled
    }
}

// ---------------------------------------------------------------------------
// InstrumentNode Implementation
// ---------------------------------------------------------------------------

impl InstrumentNode for DrumMachineInstrument {
    fn push_midi(&mut self, event: MidiEvent) {
        if let Err(_) = self.midi_tx.try_send(event) {
            warn!("DrumMachine '{}': MIDI ring full", self.id);
        }
    }

    fn process(&mut self, buffer: &mut AudioBuffer, _ctx: &ProcessContext) {
        self.process_commands();
        self.process_midi();
        buffer.silence();
        self.render_voices(buffer);

        if (self.master_gain - 1.0).abs() > 0.001 {
            buffer.apply_gain(self.master_gain);
        }
        if self.master_pan.abs() > 0.001 {
            buffer.apply_pan(self.master_pan);
        }
    }

    fn instrument_id(&self) -> &str { &self.id }
    fn instrument_name(&self) -> &str { "DrumMachine" }
    fn instrument_type(&self) -> &str { "drum_machine" }

    fn set_sample_rate(&mut self, sample_rate: u32) {
        self.sample_rate = sample_rate;
        let sr = sample_rate as f32;
        for v in &mut self.voices { v.set_sample_rate(sr); }
    }

    fn set_buffer_size(&mut self, buffer_size: usize) {
        self.buffer_size = buffer_size;
    }

    fn active_voice_count(&self) -> usize {
        self.voices.iter().filter(|v| v.active).count()
    }

    fn max_polyphony(&self) -> usize { MAX_VOICES }

    fn as_any_mut(&mut self) -> &mut dyn std::any::Any { self }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_sample(frames: usize, freq: f32, sr: u32) -> SampleData {
        let mut data = Vec::with_capacity(frames * 2);
        for i in 0..frames {
            let t = i as f32 / sr as f32;
            let s = (freq * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            data.push(s);
            data.push(s);
        }
        SampleData::from_raw(data, 2, sr, "test_drum".to_string())
    }

    fn make_ctx(frames: usize, sr: u32) -> ProcessContext {
        ProcessContext {
            frames, sample_rate: sr, position_samples: 0,
            position_beats: 0.0, is_playing: true, bpm: 120.0,
            time_sig_num: 4, time_sig_den: 4,
        }
    }

    #[test]
    fn test_drum_creation() {
        let dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        assert_eq!(dm.instrument_id(), "test");
        assert_eq!(dm.instrument_type(), "drum_machine");
        assert_eq!(dm.instrument_name(), "DrumMachine");
        assert_eq!(dm.active_voice_count(), 0);
        assert_eq!(dm.pads.len(), MAX_PADS);
        assert_eq!(dm.base_note, DEFAULT_BASE_NOTE);
    }

    #[test]
    fn test_drum_pad_names() {
        let dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        assert_eq!(dm.pads[0].name_str(), "Kick");
        assert_eq!(dm.pads[1].name_str(), "Snare");
        assert_eq!(dm.pads[3].name_str(), "OHat");
    }

    #[test]
    fn test_drum_no_sample_silent() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 256);
        let mut buffer = AudioBuffer::new(256, 2);
        let ctx = make_ctx(256, 44100);

        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 });
        dm.process(&mut buffer, &ctx);

        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max < 0.0001, "Should be silent without samples");
    }

    #[test]
    fn test_drum_load_and_trigger() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);

        // Load on pad 0 (note 36)
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample {
            pad_index: 0, sample,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        // Trigger note 36 (pad 0)
        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.9 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);

        let max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.01, "Should produce audio, got {}", max);
        assert_eq!(dm.active_voice_count(), 1);
    }

    #[test]
    fn test_drum_note_below_base_ignored() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        // Note 35 < base_note 36 → ignored
        dm.push_midi(MidiEvent::NoteOn { note: 35, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 0);
    }

    #[test]
    fn test_drum_choke_group() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);

        // Load two pads in same choke group (e.g., HH open + closed)
        let s1 = make_test_sample(44100, 440.0, 44100);
        let s2 = make_test_sample(44100, 880.0, 44100);

        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample: s1 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadChoke { pad_index: 0, group: 1 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 1, sample: s2 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadChoke { pad_index: 1, group: 1 });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx); // apply commands

        // Play pad 0
        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1);

        // Play pad 1 → should choke pad 0 (same group)
        dm.push_midi(MidiEvent::NoteOn { note: 37, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1, "Choke should kill pad 0 voice");
    }

    #[test]
    fn test_drum_retrigger_same_pad() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        // Play same pad twice → retrigger (kill old, start new)
        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1);

        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.9 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1, "Retrigger should reuse, not stack");
    }

    #[test]
    fn test_drum_multiple_pads() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);

        for i in 0..4u8 {
            let s = make_test_sample(44100, 440.0 * (i as f32 + 1.0), 44100);
            let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: i, sample: s });
        }

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        // Play 4 different pads
        for i in 0..4u8 {
            dm.push_midi(MidiEvent::NoteOn { note: 36 + i, velocity: 0.8 });
        }
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 4);
    }

    #[test]
    fn test_drum_all_sound_off() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 1.0 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1);

        dm.push_midi(MidiEvent::AllSoundOff);
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 0);
    }

    #[test]
    fn test_drum_gate_mode_note_off() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadPlayMode {
            pad_index: 0, mode: PadPlayMode::Gate,
        });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert_eq!(dm.active_voice_count(), 1);

        // Note off should trigger release for gate mode
        dm.push_midi(MidiEvent::NoteOff { note: 36 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        // Voice is releasing (still "active" until envelope finishes)
        // After enough buffers it will become inactive
    }

    #[test]
    fn test_drum_clear_all() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);
        let sample = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);
        assert!(dm.pads[0].active);

        let _ = dm.cmd_tx.try_send(DrumMachineCommand::ClearAllPads);
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);
        assert!(!dm.pads[0].active);
    }

    #[test]
    fn test_drum_play_mode_parse() {
        assert_eq!(PadPlayMode::from_str("one_shot"), PadPlayMode::OneShot);
        assert_eq!(PadPlayMode::from_str("gate"), PadPlayMode::Gate);
        assert_eq!(PadPlayMode::from_str("Gate"), PadPlayMode::Gate);
        assert_eq!(PadPlayMode::from_str("unknown"), PadPlayMode::OneShot);
    }

    #[test]
    fn test_drum_multi_output_enable() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);

        assert!(!dm.is_multi_output());
        assert_eq!(dm.output_count(), 1);
        assert_eq!(dm.aux_output_buffers().len(), 0);

        // Enable 4 outputs
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetMultiOutput {
            enabled: true, output_count: 4,
        });
        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        assert!(dm.is_multi_output());
        assert_eq!(dm.output_count(), 4);
        assert_eq!(dm.aux_output_buffers().len(), 3); // outputs 1,2,3
    }

    #[test]
    fn test_drum_multi_output_routing() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);

        // Load pads on slot 0 (output 0=main) and slot 1 (output 1=aux)
        let s0 = make_test_sample(44100, 440.0, 44100);
        let s1 = make_test_sample(44100, 880.0, 44100);

        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample: s0 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadOutput { pad_index: 0, output_index: 0 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 1, sample: s1 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadOutput { pad_index: 1, output_index: 1 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetMultiOutput { enabled: true, output_count: 4 });

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx); // apply commands

        // Trigger both pads
        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 }); // pad 0 → main
        dm.push_midi(MidiEvent::NoteOn { note: 37, velocity: 0.8 }); // pad 1 → aux 1

        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);

        assert_eq!(dm.active_voice_count(), 2);

        // Main buffer should have audio from pad 0
        let main_max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(main_max > 0.01, "Main buffer should have pad 0 audio, got {}", main_max);

        // Aux buffer 0 (output_index 1) should have audio from pad 1
        let aux = &dm.aux_output_buffers()[0]; // index 0 = output 1
        let aux_max = aux.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(aux_max > 0.01, "Aux buffer 1 should have pad 1 audio, got {}", aux_max);

        // Aux buffer 1 (output_index 2) should be silent
        let aux2 = &dm.aux_output_buffers()[1];
        let aux2_max = aux2.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(aux2_max < 0.001, "Aux buffer 2 should be silent, got {}", aux2_max);
    }

    #[test]
    fn test_drum_multi_output_disabled_all_to_main() {
        let mut dm = DrumMachineInstrument::new("test".to_string(), 44100, 512);

        let s0 = make_test_sample(44100, 440.0, 44100);
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::LoadPadSample { pad_index: 0, sample: s0 });
        let _ = dm.cmd_tx.try_send(DrumMachineCommand::SetPadOutput { pad_index: 0, output_index: 2 });
        // Multi-output NOT enabled → should go to main regardless

        let mut buffer = AudioBuffer::new(512, 2);
        let ctx = make_ctx(512, 44100);
        dm.process(&mut buffer, &ctx);

        dm.push_midi(MidiEvent::NoteOn { note: 36, velocity: 0.8 });
        buffer = AudioBuffer::new(512, 2);
        dm.process(&mut buffer, &ctx);

        let main_max = buffer.data.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(main_max > 0.01, "With multi-output OFF, all goes to main");
    }
}
