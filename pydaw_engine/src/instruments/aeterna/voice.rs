// ==========================================================================
// AETERNA Voice — Oscillator + Filter + Envelopes + Voice Pool + Glide
// ==========================================================================
// v0.0.20.685 — Phase R8B
//
// Each AeternaVoice contains:
//   - OscillatorState (from R8A): PolyBLEP osc with FM, Sub, Unison
//   - Stereo Biquad Filter (from R1): LP/HP/BP/Notch + Key Tracking
//   - AEG: Amplitude Envelope (ADSR)
//   - FEG: Filter Envelope (ADSR) → modulates filter cutoff
//   - Glide/Portamento: Exponential pitch smoothing between notes
//
// AeternaVoicePool:
//   - Pre-allocated array of MAX_POLYPHONY voices (32)
//   - Voice stealing: Oldest, Quietest, SameNote
//   - Zero-alloc render: all buffers pre-allocated
//
// Rules:
//   ✅ All DSP is zero-alloc in process/render
//   ✅ Voice pool is fully pre-allocated
//   ✅ #[inline] on all sample-level functions
//   ❌ NO allocations in audio thread
//   ❌ NO locks or panics
// ==========================================================================

use crate::dsp::biquad::{Biquad, FilterType};
use crate::dsp::envelope::{AdsrEnvelope, EnvState};
use super::oscillator::{OscillatorState, Waveform};
use super::modulation::{ModMatrix, ModOutput, VoiceModState};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Maximum polyphony for AETERNA.
pub const MAX_POLYPHONY: usize = 32;

/// Minimum frequency (Hz) for filter cutoff.
const FILTER_FREQ_MIN: f32 = 20.0;

/// Maximum frequency (Hz) for filter cutoff.
const FILTER_FREQ_MAX: f32 = 20000.0;

/// Default filter cutoff (normalized 0–1, maps to FILTER_FREQ_MIN..FILTER_FREQ_MAX).
const DEFAULT_CUTOFF: f32 = 0.68;

/// Default filter resonance (0–1).
const DEFAULT_RESONANCE: f32 = 0.18;

// ---------------------------------------------------------------------------
// AETERNA Filter Type
// ---------------------------------------------------------------------------

/// Filter mode for AETERNA voices.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AeternaFilterMode {
    /// Low-pass 12 dB/oct (1× Biquad).
    Lp12,
    /// Low-pass 24 dB/oct (2× cascaded Biquad).
    Lp24,
    /// High-pass 12 dB/oct.
    Hp12,
    /// Band-pass.
    Bp,
    /// Notch (band-reject).
    Notch,
    /// Filter bypassed.
    Off,
}

impl AeternaFilterMode {
    /// Parse from string (Python compatibility).
    pub fn from_str(s: &str) -> Self {
        match s {
            "LP 24" | "lp24" | "LP24" => Self::Lp24,
            "LP 12" | "lp12" | "LP12" => Self::Lp12,
            "HP 12" | "hp12" | "HP12" => Self::Hp12,
            "BP" | "bp" | "BandPass" => Self::Bp,
            "Notch" | "notch" => Self::Notch,
            "Off" | "off" | "none" => Self::Off,
            _ => Self::Lp24,
        }
    }

    /// Convert to R1 Biquad FilterType.
    fn to_biquad_type(self) -> FilterType {
        match self {
            Self::Lp24 | Self::Lp12 => FilterType::LowPass,
            Self::Hp12 => FilterType::HighPass,
            Self::Bp => FilterType::BandPass,
            Self::Notch => FilterType::Notch,
            Self::Off => FilterType::LowPass, // unused when off
        }
    }

    /// Whether this mode uses a second cascaded biquad (24 dB/oct).
    fn is_cascaded(self) -> bool {
        matches!(self, Self::Lp24)
    }
}

// ---------------------------------------------------------------------------
// Voice Steal Mode
// ---------------------------------------------------------------------------

/// Strategy for stealing voices when pool is full.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceStealMode {
    /// Steal the oldest voice.
    Oldest,
    /// Steal the quietest voice (lowest AEG level).
    Quietest,
    /// Steal the voice playing the same note (retrigger).
    SameNote,
}

// ---------------------------------------------------------------------------
// AETERNA Voice Parameters (shared across all voices)
// ---------------------------------------------------------------------------

/// Shared parameters for all AETERNA voices.
///
/// Updated from the command thread, read by the audio thread.
/// No locking needed — single writer, single reader, and f32/u8 writes are atomic on all targets.
#[derive(Debug, Clone)]
pub struct AeternaVoiceParams {
    // --- Oscillator ---
    pub waveform: Waveform,
    /// Morph shape (0.0–1.0): Sine ↔ Tri ↔ Saw ↔ Square.
    pub shape: f32,
    /// FM modulation depth (0.0–1.0).
    pub fm_amount: f32,
    /// FM modulator frequency ratio.
    pub fm_ratio: f32,
    /// Sub-oscillator level (0.0–1.0).
    pub sub_level: f32,
    /// Sub-oscillator octave down (1 or 2).
    pub sub_octave: u8,
    /// Unison voice count (1–16).
    pub unison_voices: u8,
    /// Unison detune in cents.
    pub unison_detune: f32,
    /// Unison stereo spread (0.0–1.0).
    pub unison_spread: f32,

    // --- Filter ---
    pub filter_mode: AeternaFilterMode,
    /// Normalized cutoff (0.0–1.0 → 20 Hz – 20 kHz exponential).
    pub filter_cutoff: f32,
    /// Resonance (0.0–1.0 → Q 0.5 – 20).
    pub filter_resonance: f32,
    /// Key tracking amount (0.0–1.0). 1.0 = cutoff follows pitch 1:1.
    pub filter_key_track: f32,

    // --- AEG (Amplitude Envelope) ---
    pub aeg_attack: f32,
    pub aeg_decay: f32,
    pub aeg_sustain: f32,
    pub aeg_release: f32,

    // --- FEG (Filter Envelope) ---
    pub feg_attack: f32,
    pub feg_decay: f32,
    pub feg_sustain: f32,
    pub feg_release: f32,
    /// FEG modulation amount (-1.0 to 1.0). Positive = open filter, negative = close.
    pub feg_amount: f32,

    // --- Glide / Portamento ---
    /// Glide time in seconds (0.0 = off).
    pub glide_time: f32,

    // --- Master ---
    pub master_gain: f32,
    pub master_pan: f32,

    // --- Velocity ---
    /// Velocity sensitivity (0.0 = ignore velocity, 1.0 = full).
    pub velocity_sensitivity: f32,
}

impl Default for AeternaVoiceParams {
    fn default() -> Self {
        Self {
            waveform: Waveform::Saw,
            shape: 0.0,
            fm_amount: 0.0,
            fm_ratio: 2.0,
            sub_level: 0.0,
            sub_octave: 1,
            unison_voices: 1,
            unison_detune: 15.0,
            unison_spread: 0.7,

            filter_mode: AeternaFilterMode::Lp24,
            filter_cutoff: DEFAULT_CUTOFF,
            filter_resonance: DEFAULT_RESONANCE,
            filter_key_track: 0.0,

            aeg_attack: 0.005,
            aeg_decay: 0.2,
            aeg_sustain: 0.7,
            aeg_release: 0.3,

            feg_attack: 0.01,
            feg_decay: 0.3,
            feg_sustain: 0.3,
            feg_release: 0.4,
            feg_amount: 0.0,

            glide_time: 0.0,

            master_gain: 0.7,
            master_pan: 0.0,

            velocity_sensitivity: 0.8,
        }
    }
}

// ---------------------------------------------------------------------------
// Glide State — exponential pitch smoothing
// ---------------------------------------------------------------------------

/// Per-voice glide state for portamento.
struct GlideState {
    /// Current frequency (smoothed).
    current_freq: f32,
    /// Target frequency.
    target_freq: f32,
    /// Smoothing coefficient per sample (0–1, higher = faster).
    coeff: f32,
    /// Whether glide is active (freq != target).
    active: bool,
}

impl GlideState {
    fn new() -> Self {
        Self {
            current_freq: 440.0,
            target_freq: 440.0,
            coeff: 1.0, // instant
            active: false,
        }
    }

    /// Start a glide from current frequency to new target.
    fn start(&mut self, target_freq: f32, glide_time_sec: f32, sample_rate: f32) {
        self.target_freq = target_freq;
        if glide_time_sec < 0.001 || (self.current_freq - target_freq).abs() < 0.01 {
            // No glide needed
            self.current_freq = target_freq;
            self.active = false;
            self.coeff = 1.0;
        } else {
            self.active = true;
            // Exponential approach: reach ~99.3% in glide_time
            let samples = (glide_time_sec * sample_rate).max(1.0);
            self.coeff = 1.0 - (-5.0 / samples).exp();
        }
    }

    /// Start fresh (no previous note to glide from).
    fn set_immediate(&mut self, freq: f32) {
        self.current_freq = freq;
        self.target_freq = freq;
        self.active = false;
    }

    /// Advance one sample. Returns the current (smoothed) frequency.
    #[inline]
    fn process(&mut self) -> f32 {
        if self.active {
            self.current_freq += (self.target_freq - self.current_freq) * self.coeff;
            if (self.current_freq - self.target_freq).abs() < 0.01 {
                self.current_freq = self.target_freq;
                self.active = false;
            }
        }
        self.current_freq
    }
}

// ---------------------------------------------------------------------------
// AETERNA Voice — one playing note
// ---------------------------------------------------------------------------

/// A single AETERNA voice: oscillator + filter + envelopes + glide.
pub struct AeternaVoice {
    // --- Identity ---
    /// MIDI note number (0–127).
    note: u8,
    /// Velocity (0.0–1.0).
    velocity: f32,
    /// Base frequency (Hz) for this note.
    base_freq: f32,
    /// Whether the voice is active (producing audio).
    active: bool,
    /// Age in samples (for voice stealing).
    age: u64,
    /// Sequence number (for oldest-first stealing).
    seq: u64,

    // --- Oscillator ---
    osc: OscillatorState,

    // --- Filter (stereo: L + R Biquad, optionally cascaded for 24dB) ---
    filter_l1: Biquad,
    filter_r1: Biquad,
    filter_l2: Biquad,   // second stage for LP24
    filter_r2: Biquad,

    // --- Envelopes ---
    /// Amplitude Envelope Generator.
    aeg: AdsrEnvelope,
    /// Filter Envelope Generator.
    feg: AdsrEnvelope,

    // --- Modulation (R8C) ---
    /// Per-voice modulation state (LFOs synced to note-on).
    mod_state: VoiceModState,

    // --- Glide ---
    glide: GlideState,
}

impl AeternaVoice {
    /// Create a new idle voice with default state.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            note: 0,
            velocity: 0.0,
            base_freq: 440.0,
            active: false,
            age: 0,
            seq: 0,

            osc: OscillatorState::new(),

            filter_l1: Biquad::passthrough(),
            filter_r1: Biquad::passthrough(),
            filter_l2: Biquad::passthrough(),
            filter_r2: Biquad::passthrough(),

            aeg: AdsrEnvelope::new(0.005, 0.2, 0.7, 0.3, sample_rate),
            feg: AdsrEnvelope::new(0.01, 0.3, 0.3, 0.4, sample_rate),

            mod_state: VoiceModState::new(sample_rate),

            glide: GlideState::new(),
        }
    }

    /// Trigger a note on this voice.
    pub fn note_on(
        &mut self,
        note: u8,
        velocity: f32,
        freq: f32,
        params: &AeternaVoiceParams,
        sample_rate: f32,
        seq: u64,
        prev_freq: Option<f32>,
    ) {
        self.note = note;
        self.velocity = velocity;
        self.base_freq = freq;
        self.active = true;
        self.age = 0;
        self.seq = seq;

        // Oscillator reset
        self.osc.reset(true); // randomize phase for analog feel
        self.osc.set_unison(params.unison_voices, params.unison_detune, params.unison_spread);

        // Filter reset
        self.filter_l1.reset();
        self.filter_r1.reset();
        self.filter_l2.reset();
        self.filter_r2.reset();

        // Modulation reset (LFOs sync to note-on)
        self.mod_state.reset();

        // AEG
        self.aeg.set_params(params.aeg_attack, params.aeg_decay, params.aeg_sustain, params.aeg_release);
        self.aeg.set_sample_rate(sample_rate);
        self.aeg.note_on();

        // FEG
        self.feg.set_params(params.feg_attack, params.feg_decay, params.feg_sustain, params.feg_release);
        self.feg.set_sample_rate(sample_rate);
        self.feg.note_on();

        // Glide
        if let Some(pf) = prev_freq {
            if params.glide_time > 0.001 {
                self.glide.current_freq = pf;
                self.glide.start(freq, params.glide_time, sample_rate);
            } else {
                self.glide.set_immediate(freq);
            }
        } else {
            self.glide.set_immediate(freq);
        }
    }

    /// Trigger note off (enter release phase).
    pub fn note_off(&mut self) {
        self.aeg.note_off();
        self.feg.note_off();
    }

    /// Kill voice immediately (no release).
    pub fn kill(&mut self) {
        self.aeg.kill();
        self.feg.kill();
        self.active = false;
    }

    /// Check if voice is still producing audio.
    #[inline]
    pub fn is_active(&self) -> bool {
        self.active
    }

    /// Get the MIDI note this voice is playing.
    #[inline]
    pub fn note(&self) -> u8 {
        self.note
    }

    /// Get the current AEG level (for quietest-voice stealing).
    #[inline]
    pub fn aeg_level(&self) -> f32 {
        self.aeg.current()
    }

    /// Get age in samples.
    #[inline]
    pub fn age(&self) -> u64 {
        self.age
    }

    /// Get sequence number.
    #[inline]
    pub fn seq(&self) -> u64 {
        self.seq
    }

    /// Get the current (possibly gliding) frequency.
    #[inline]
    pub fn current_freq(&self) -> f32 {
        self.glide.current_freq
    }

    /// Render one sample of this voice.
    ///
    /// Returns `(left, right)` stereo pair, already scaled by AEG and velocity.
    /// Returns `(0.0, 0.0)` and sets `active = false` if voice has finished.
    #[inline]
    pub fn render_sample(&mut self, params: &AeternaVoiceParams, sample_rate: f32, mod_matrix: &ModMatrix) -> (f32, f32) {
        if !self.active {
            return (0.0, 0.0);
        }

        // Advance AEG
        let aeg_val = self.aeg.process();
        if self.aeg.state() == EnvState::Idle && self.age > 0 {
            self.active = false;
            return (0.0, 0.0);
        }

        // Advance FEG
        let feg_val = self.feg.process();

        // Evaluate modulation matrix (advances LFOs, reads envelopes)
        let modulation = mod_matrix.evaluate(
            &mut self.mod_state,
            aeg_val,
            feg_val,
            self.velocity,
        );

        // Glide
        let base_freq = self.glide.process();

        // Apply pitch modulation (semitones → frequency ratio)
        let freq = if modulation.pitch.abs() > 0.001 {
            base_freq * 2.0f32.powf(modulation.pitch / 12.0)
        } else {
            base_freq
        };

        // Velocity scaling
        let vel_gain = 1.0 - params.velocity_sensitivity * (1.0 - self.velocity);

        // Effective shape and FM with modulation offsets
        let eff_shape = (params.shape + modulation.shape).clamp(0.0, 1.0);
        let eff_fm = (params.fm_amount + modulation.fm_amount).clamp(0.0, 1.0);

        // --- Generate oscillator output ---
        let (raw_l, raw_r) = if eff_shape > 0.001 {
            self.osc.process_morphed(
                freq, sample_rate, eff_shape,
                eff_fm, params.fm_ratio,
                params.sub_level, params.sub_octave,
            )
        } else {
            self.osc.process(
                freq, sample_rate, params.waveform, 0.0,
                eff_fm, params.fm_ratio,
                params.sub_level, params.sub_octave,
            )
        };

        // --- Apply filter (with modulation offsets for cutoff/resonance) ---
        let (filt_l, filt_r) = if params.filter_mode == AeternaFilterMode::Off {
            (raw_l, raw_r)
        } else {
            self.apply_filter(raw_l, raw_r, params, feg_val, sample_rate, &modulation)
        };

        // --- Apply AEG, velocity, and amp modulation ---
        let amp = aeg_val * vel_gain * (1.0 + modulation.amp).max(0.0);
        self.age += 1;

        // Apply pan modulation
        let (out_l, out_r) = if modulation.pan.abs() > 0.001 {
            let pan = modulation.pan.clamp(-1.0, 1.0);
            let pan_angle = (pan + 1.0) * 0.25 * std::f32::consts::PI;
            (filt_l * amp * pan_angle.cos(), filt_r * amp * pan_angle.sin())
        } else {
            (filt_l * amp, filt_r * amp)
        };

        (out_l, out_r)
    }

    /// Apply the filter to one sample pair.
    #[inline]
    fn apply_filter(
        &mut self,
        left: f32,
        right: f32,
        params: &AeternaVoiceParams,
        feg_val: f32,
        sample_rate: f32,
        modulation: &ModOutput,
    ) -> (f32, f32) {
        // Calculate effective cutoff with FEG modulation, key tracking, and mod matrix
        let base_cutoff = params.filter_cutoff;

        // FEG modulation
        let feg_offset = params.feg_amount * (feg_val * 2.0 - 1.0) * 0.4;

        // Key tracking
        let key_offset = if params.filter_key_track > 0.001 {
            let semitones_from_c3 = (self.note as f32 - 60.0) / 120.0;
            semitones_from_c3 * params.filter_key_track
        } else {
            0.0
        };

        // Mod matrix cutoff offset
        let mod_cutoff_offset = modulation.filter_cutoff;
        let mod_resonance_offset = modulation.filter_resonance;

        let effective_cutoff = (base_cutoff + feg_offset + key_offset + mod_cutoff_offset).clamp(0.0, 1.0);
        let effective_resonance = (params.filter_resonance + mod_resonance_offset).clamp(0.0, 1.0);

        // Map normalized cutoff (0–1) to frequency (20–20000 Hz, exponential)
        let cutoff_hz = FILTER_FREQ_MIN * (FILTER_FREQ_MAX / FILTER_FREQ_MIN).powf(effective_cutoff);
        let cutoff_hz = cutoff_hz.min(sample_rate * 0.45); // Nyquist guard

        // Map resonance (0–1) to Q (0.5–20)
        let q = 0.5 + effective_resonance * 19.5;

        // Update filter coefficients
        let ftype = params.filter_mode.to_biquad_type();
        self.filter_l1.set_params(ftype, cutoff_hz, q, 0.0, sample_rate);
        self.filter_r1.set_params(ftype, cutoff_hz, q, 0.0, sample_rate);

        let out_l = self.filter_l1.process_sample(left);
        let out_r = self.filter_r1.process_sample(right);

        if params.filter_mode.is_cascaded() {
            // Second stage for 24 dB/oct
            self.filter_l2.set_params(ftype, cutoff_hz, q * 0.7, 0.0, sample_rate);
            self.filter_r2.set_params(ftype, cutoff_hz, q * 0.7, 0.0, sample_rate);
            let out_l2 = self.filter_l2.process_sample(out_l);
            let out_r2 = self.filter_r2.process_sample(out_r);
            (out_l2, out_r2)
        } else {
            (out_l, out_r)
        }
    }
}

// ---------------------------------------------------------------------------
// AETERNA Voice Pool — pre-allocated, voice stealing
// ---------------------------------------------------------------------------

/// Pre-allocated pool of AETERNA voices.
pub struct AeternaVoicePool {
    voices: Vec<AeternaVoice>,
    /// Global sequence counter for voice ordering.
    seq_counter: u64,
    /// Current voice steal mode.
    steal_mode: VoiceStealMode,
    /// Last played frequency (for glide).
    last_freq: Option<f32>,
}

impl AeternaVoicePool {
    /// Create a new voice pool with `max_voices` pre-allocated voices.
    pub fn new(max_voices: usize, sample_rate: f32) -> Self {
        let n = max_voices.min(MAX_POLYPHONY);
        let mut voices = Vec::with_capacity(n);
        for _ in 0..n {
            voices.push(AeternaVoice::new(sample_rate));
        }
        Self {
            voices,
            seq_counter: 0,
            steal_mode: VoiceStealMode::Oldest,
            last_freq: None,
        }
    }

    /// Set the voice stealing strategy.
    pub fn set_steal_mode(&mut self, mode: VoiceStealMode) {
        self.steal_mode = mode;
    }

    /// Get the number of currently active voices.
    pub fn active_count(&self) -> usize {
        self.voices.iter().filter(|v| v.is_active()).count()
    }

    /// Get maximum polyphony.
    pub fn max_polyphony(&self) -> usize {
        self.voices.len()
    }

    /// Trigger a note on. Allocates a voice (or steals one if pool is full).
    pub fn note_on(
        &mut self,
        note: u8,
        velocity: f32,
        params: &AeternaVoiceParams,
        sample_rate: f32,
    ) {
        self.seq_counter += 1;
        let seq = self.seq_counter;
        let freq = midi_to_freq(note);
        let prev_freq = self.last_freq;

        // Find a free voice or steal one
        let idx = self.find_free_or_steal(note);

        if let Some(voice) = self.voices.get_mut(idx) {
            voice.note_on(note, velocity, freq, params, sample_rate, seq, prev_freq);
        }

        self.last_freq = Some(freq);
    }

    /// Release all voices playing the given note.
    pub fn note_off(&mut self, note: u8) {
        for voice in &mut self.voices {
            if voice.is_active() && voice.note() == note && voice.aeg.state() != EnvState::Release {
                voice.note_off();
            }
        }
    }

    /// Release all voices (all notes off).
    pub fn all_notes_off(&mut self) {
        for voice in &mut self.voices {
            if voice.is_active() {
                voice.note_off();
            }
        }
    }

    /// Kill all voices immediately (all sound off).
    pub fn all_sound_off(&mut self) {
        for voice in &mut self.voices {
            voice.kill();
        }
        self.last_freq = None;
    }

    /// Render all active voices into the given buffer (additive).
    ///
    /// Buffer is NOT cleared — caller must zero it if needed.
    /// This is designed for additive mixing into a shared buffer.
    pub fn render(
        &mut self,
        buffer: &mut [f32],
        frames: usize,
        channels: usize,
        params: &AeternaVoiceParams,
        sample_rate: f32,
        mod_matrix: &ModMatrix,
    ) {
        for voice in &mut self.voices {
            if !voice.is_active() {
                continue;
            }
            // Sync LFO rates/shapes from shared matrix config (once per buffer)
            mod_matrix.sync_voice_lfos(&mut voice.mod_state);

            for frame in 0..frames {
                let (l, r) = voice.render_sample(params, sample_rate, mod_matrix);
                let idx = frame * channels;
                if idx < buffer.len() {
                    buffer[idx] += l;
                    if channels > 1 && idx + 1 < buffer.len() {
                        buffer[idx + 1] += r;
                    }
                }
            }
        }
    }

    /// Update sample rate for all voices.
    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        for voice in &mut self.voices {
            voice.aeg.set_sample_rate(sample_rate);
            voice.feg.set_sample_rate(sample_rate);
            voice.mod_state.set_sample_rate(sample_rate);
        }
    }

    /// Find a free voice slot, or steal one based on the current strategy.
    fn find_free_or_steal(&self, note: u8) -> usize {
        // 1. Try to find an idle voice
        for (i, voice) in self.voices.iter().enumerate() {
            if !voice.is_active() {
                return i;
            }
        }

        // 2. If SameNote mode, steal the voice playing the same note
        if self.steal_mode == VoiceStealMode::SameNote {
            for (i, voice) in self.voices.iter().enumerate() {
                if voice.note() == note {
                    return i;
                }
            }
        }

        // 3. Steal based on strategy
        match self.steal_mode {
            VoiceStealMode::Oldest | VoiceStealMode::SameNote => {
                // Find voice with lowest sequence number (oldest)
                let mut oldest_idx = 0;
                let mut oldest_seq = u64::MAX;
                for (i, voice) in self.voices.iter().enumerate() {
                    if voice.seq() < oldest_seq {
                        oldest_seq = voice.seq();
                        oldest_idx = i;
                    }
                }
                oldest_idx
            }
            VoiceStealMode::Quietest => {
                // Find voice with lowest AEG level
                let mut quietest_idx = 0;
                let mut quietest_level = f32::MAX;
                for (i, voice) in self.voices.iter().enumerate() {
                    let level = voice.aeg_level();
                    if level < quietest_level {
                        quietest_level = level;
                        quietest_idx = i;
                    }
                }
                quietest_idx
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/// Convert MIDI note number to frequency (A4 = 440 Hz).
#[inline]
pub fn midi_to_freq(note: u8) -> f32 {
    440.0 * 2.0f32.powf((note as f32 - 69.0) / 12.0)
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const SR: f32 = 44100.0;

    /// Empty mod matrix for tests that don't need modulation.
    fn mm() -> ModMatrix { ModMatrix::new() }

    #[test]
    fn test_midi_to_freq() {
        let f = midi_to_freq(69);
        assert!((f - 440.0).abs() < 0.01, "A4 should be 440 Hz: {}", f);

        let f_c4 = midi_to_freq(60);
        assert!((f_c4 - 261.63).abs() < 1.0, "C4 should be ~261.63 Hz: {}", f_c4);

        let f_a5 = midi_to_freq(81);
        assert!((f_a5 - 880.0).abs() < 1.0, "A5 should be 880 Hz: {}", f_a5);
    }

    #[test]
    fn test_voice_new_is_idle() {
        let voice = AeternaVoice::new(SR);
        assert!(!voice.is_active());
    }

    #[test]
    fn test_voice_note_on_activates() {
        let mut voice = AeternaVoice::new(SR);
        let params = AeternaVoiceParams::default();
        voice.note_on(60, 0.8, 261.63, &params, SR, 1, None);
        assert!(voice.is_active());
        assert_eq!(voice.note(), 60);
    }

    #[test]
    fn test_voice_produces_audio() {
        let mut voice = AeternaVoice::new(SR);
        let params = AeternaVoiceParams::default();
        let mm = mm();
        voice.note_on(69, 1.0, 440.0, &params, SR, 1, None);

        let mut max_abs = 0.0f32;
        for _ in 0..512 {
            let (l, r) = voice.render_sample(&params, SR, &mm);
            max_abs = max_abs.max(l.abs()).max(r.abs());
        }
        assert!(max_abs > 0.01, "Voice should produce audio: max={}", max_abs);
    }

    #[test]
    fn test_voice_release_fades_to_idle() {
        let mut voice = AeternaVoice::new(SR);
        let mut params = AeternaVoiceParams::default();
        let mm = mm();
        params.aeg_attack = 0.001;
        params.aeg_decay = 0.01;
        params.aeg_sustain = 0.5;
        params.aeg_release = 0.01;
        voice.note_on(60, 1.0, 261.63, &params, SR, 1, None);

        for _ in 0..2000 {
            voice.render_sample(&params, SR, &mm);
        }
        assert!(voice.is_active());

        voice.note_off();

        for _ in 0..5000 {
            voice.render_sample(&params, SR, &mm);
            if !voice.is_active() {
                break;
            }
        }
        assert!(!voice.is_active(), "Voice should become idle after release");
    }

    #[test]
    fn test_voice_kill_immediate() {
        let mut voice = AeternaVoice::new(SR);
        let params = AeternaVoiceParams::default();
        voice.note_on(60, 1.0, 261.63, &params, SR, 1, None);
        assert!(voice.is_active());
        voice.kill();
        assert!(!voice.is_active());
    }

    #[test]
    fn test_filter_mode_parse() {
        assert_eq!(AeternaFilterMode::from_str("LP 24"), AeternaFilterMode::Lp24);
        assert_eq!(AeternaFilterMode::from_str("LP 12"), AeternaFilterMode::Lp12);
        assert_eq!(AeternaFilterMode::from_str("HP 12"), AeternaFilterMode::Hp12);
        assert_eq!(AeternaFilterMode::from_str("BP"), AeternaFilterMode::Bp);
        assert_eq!(AeternaFilterMode::from_str("Notch"), AeternaFilterMode::Notch);
        assert_eq!(AeternaFilterMode::from_str("Off"), AeternaFilterMode::Off);
        assert_eq!(AeternaFilterMode::from_str("unknown"), AeternaFilterMode::Lp24);
    }

    #[test]
    fn test_filter_changes_sound() {
        let mut voice_no_filter = AeternaVoice::new(SR);
        let mut voice_with_filter = AeternaVoice::new(SR);
        let mm = mm();

        let mut params_off = AeternaVoiceParams::default();
        params_off.waveform = Waveform::Saw;
        params_off.filter_mode = AeternaFilterMode::Off;

        let mut params_lp = AeternaVoiceParams::default();
        params_lp.waveform = Waveform::Saw;
        params_lp.filter_mode = AeternaFilterMode::Lp24;
        params_lp.filter_cutoff = 0.3;

        voice_no_filter.note_on(60, 1.0, 261.63, &params_off, SR, 1, None);
        voice_with_filter.note_on(60, 1.0, 261.63, &params_lp, SR, 1, None);

        let mut diff = 0.0f32;
        for _ in 0..512 {
            let (l1, _) = voice_no_filter.render_sample(&params_off, SR, &mm);
            let (l2, _) = voice_with_filter.render_sample(&params_lp, SR, &mm);
            diff += (l1 - l2).abs();
        }

        assert!(diff > 1.0, "LP filter should change the sound: diff={}", diff);
    }

    #[test]
    fn test_feg_modulates_filter() {
        let mut voice1 = AeternaVoice::new(SR);
        let mut voice2 = AeternaVoice::new(SR);
        let mm = mm();

        let mut params_no_feg = AeternaVoiceParams::default();
        params_no_feg.waveform = Waveform::Saw;
        params_no_feg.filter_mode = AeternaFilterMode::Lp24;
        params_no_feg.filter_cutoff = 0.3;
        params_no_feg.feg_amount = 0.0;

        let mut params_feg = params_no_feg.clone();
        params_feg.feg_amount = 0.8;
        params_feg.feg_attack = 0.001;
        params_feg.feg_decay = 0.5;

        voice1.note_on(60, 1.0, 261.63, &params_no_feg, SR, 1, None);
        voice2.note_on(60, 1.0, 261.63, &params_feg, SR, 1, None);

        let mut diff = 0.0f32;
        for _ in 0..512 {
            let (l1, _) = voice1.render_sample(&params_no_feg, SR, &mm);
            let (l2, _) = voice2.render_sample(&params_feg, SR, &mm);
            diff += (l1 - l2).abs();
        }

        assert!(diff > 0.5, "FEG should modulate the filter: diff={}", diff);
    }

    #[test]
    fn test_glide_smooths_pitch() {
        let mut glide = GlideState::new();
        glide.set_immediate(220.0);
        glide.start(440.0, 0.01, SR);

        let f1 = glide.process();
        assert!(f1 < 300.0, "Glide start should be near 220: {}", f1);

        for _ in 0..2000 {
            glide.process();
        }
        let f_end = glide.process();
        assert!((f_end - 440.0).abs() < 1.0, "Glide end should be near 440: {}", f_end);
    }

    #[test]
    fn test_voice_pool_creation() {
        let pool = AeternaVoicePool::new(32, SR);
        assert_eq!(pool.max_polyphony(), 32);
        assert_eq!(pool.active_count(), 0);
    }

    #[test]
    fn test_voice_pool_note_on_off() {
        let mut pool = AeternaVoicePool::new(32, SR);
        let params = AeternaVoiceParams::default();

        pool.note_on(60, 0.8, &params, SR);
        assert_eq!(pool.active_count(), 1);

        pool.note_on(64, 0.8, &params, SR);
        assert_eq!(pool.active_count(), 2);

        pool.note_off(60);
        assert_eq!(pool.active_count(), 2);
    }

    #[test]
    fn test_voice_pool_all_notes_off() {
        let mut pool = AeternaVoicePool::new(8, SR);
        let params = AeternaVoiceParams::default();

        for note in 60..68 {
            pool.note_on(note, 0.8, &params, SR);
        }
        assert_eq!(pool.active_count(), 8);

        pool.all_notes_off();
        assert_eq!(pool.active_count(), 8);

        pool.all_sound_off();
        assert_eq!(pool.active_count(), 0);
    }

    #[test]
    fn test_voice_pool_stealing() {
        let mut pool = AeternaVoicePool::new(4, SR);
        let params = AeternaVoiceParams::default();

        for note in 60..64 {
            pool.note_on(note, 0.8, &params, SR);
        }
        assert_eq!(pool.active_count(), 4);

        pool.note_on(65, 0.8, &params, SR);
        assert_eq!(pool.active_count(), 4);
    }

    #[test]
    fn test_voice_pool_render_produces_audio() {
        let mut pool = AeternaVoicePool::new(8, SR);
        let params = AeternaVoiceParams::default();
        let mm = mm();

        pool.note_on(69, 1.0, &params, SR);

        let frames = 256;
        let channels = 2;
        let mut buffer = vec![0.0f32; frames * channels];
        pool.render(&mut buffer, frames, channels, &params, SR, &mm);

        let max_abs: f32 = buffer.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max_abs > 0.01, "Pool render should produce audio: max={}", max_abs);
    }

    #[test]
    fn test_voice_pool_polyphony() {
        let mut pool = AeternaVoicePool::new(8, SR);
        let params = AeternaVoiceParams::default();
        let mm = mm();

        pool.note_on(60, 0.8, &params, SR);
        pool.note_on(64, 0.8, &params, SR);
        pool.note_on(67, 0.8, &params, SR);
        assert_eq!(pool.active_count(), 3);

        let frames = 128;
        let channels = 2;
        let mut buffer = vec![0.0f32; frames * channels];
        pool.render(&mut buffer, frames, channels, &params, SR, &mm);

        let max_abs: f32 = buffer.iter().map(|s| s.abs()).fold(0.0, f32::max);
        assert!(max_abs > 0.01, "Chord should produce audio: max={}", max_abs);
    }

    #[test]
    fn test_velocity_sensitivity() {
        let mut voice_loud = AeternaVoice::new(SR);
        let mut voice_soft = AeternaVoice::new(SR);
        let mm = mm();

        let params = AeternaVoiceParams::default();

        voice_loud.note_on(60, 1.0, 261.63, &params, SR, 1, None);
        voice_soft.note_on(60, 0.2, 261.63, &params, SR, 2, None);

        let mut sum_loud = 0.0f32;
        let mut sum_soft = 0.0f32;
        for _ in 0..256 {
            let (l1, _) = voice_loud.render_sample(&params, SR, &mm);
            let (l2, _) = voice_soft.render_sample(&params, SR, &mm);
            sum_loud += l1.abs();
            sum_soft += l2.abs();
        }

        assert!(sum_loud > sum_soft * 1.5, "Loud should be louder: {} vs {}", sum_loud, sum_soft);
    }

    #[test]
    fn test_glide_in_voice_pool() {
        let mut pool = AeternaVoicePool::new(8, SR);
        let mut params = AeternaVoiceParams::default();
        params.glide_time = 0.05;

        pool.note_on(60, 0.8, &params, SR);
        assert!(pool.last_freq.is_some());

        pool.note_on(72, 0.8, &params, SR);

        let active_voices: Vec<&AeternaVoice> = pool.voices.iter()
            .filter(|v| v.is_active())
            .collect();
        assert_eq!(active_voices.len(), 2);
    }

    #[test]
    fn test_key_tracking() {
        let mut voice_low = AeternaVoice::new(SR);
        let mut voice_high = AeternaVoice::new(SR);
        let mm = mm();

        let mut params = AeternaVoiceParams::default();
        params.waveform = Waveform::Saw;
        params.filter_mode = AeternaFilterMode::Lp24;
        params.filter_cutoff = 0.3;
        params.filter_key_track = 1.0;

        voice_low.note_on(36, 1.0, midi_to_freq(36), &params, SR, 1, None);
        voice_high.note_on(84, 1.0, midi_to_freq(84), &params, SR, 2, None);

        let mut energy_low = 0.0f32;
        let mut energy_high = 0.0f32;
        for _ in 0..512 {
            let (l1, _) = voice_low.render_sample(&params, SR, &mm);
            let (l2, _) = voice_high.render_sample(&params, SR, &mm);
            energy_low += l1.abs();
            energy_high += l2.abs();
        }

        assert!(energy_low > 0.1, "Low note should produce audio: {}", energy_low);
        assert!(energy_high > 0.1, "High note should produce audio: {}", energy_high);
    }
}
