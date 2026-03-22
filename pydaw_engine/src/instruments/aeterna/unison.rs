// ==========================================================================
// AETERNA Unison Engine — Multi-voice detune with stereo spread
// ==========================================================================
// v0.0.20.692 — Phase R9B
//
// Renders N unison voices through a WavetableBank with per-voice detune,
// stereo pan, and level. Three modes:
//   - Classic: Even detune spread, equal levels
//   - Supersaw: Wider detune, slight level taper at edges
//   - Hyper: Extreme detune, random phase offsets per voice
//
// Used by AeternaVoice when in wavetable mode: the unison engine replaces
// the OscillatorState's built-in unison for wavetable playback.
//
// Rules:
//   ✅ render_sample() is #[inline] and zero-alloc
//   ✅ All voice state pre-allocated in fixed-size arrays
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::f32::consts::PI;
use super::wavetable::WavetableBank;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Maximum number of unison voices.
pub const MAX_UNISON_VOICES: usize = 16;

// ---------------------------------------------------------------------------
// Unison Mode
// ---------------------------------------------------------------------------

/// Unison detune distribution mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnisonMode {
    /// No unison (single voice).
    Off,
    /// Even detune spread, equal levels.
    Classic,
    /// Wider detune, slight level taper at edges (JP-8000 style).
    Supersaw,
    /// Extreme detune, random phase offsets (dense pad mode).
    Hyper,
}

impl UnisonMode {
    /// Parse from integer (0=Off, 1=Classic, 2=Supersaw, 3=Hyper).
    pub fn from_int(v: u8) -> Self {
        match v {
            1 => Self::Classic,
            2 => Self::Supersaw,
            3 => Self::Hyper,
            _ => Self::Off,
        }
    }

    /// Parse from string.
    pub fn from_str(s: &str) -> Self {
        match s {
            "classic" | "Classic" => Self::Classic,
            "supersaw" | "Supersaw" => Self::Supersaw,
            "hyper" | "Hyper" => Self::Hyper,
            _ => Self::Off,
        }
    }

    /// Convert to string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Classic => "classic",
            Self::Supersaw => "supersaw",
            Self::Hyper => "hyper",
        }
    }
}

// ---------------------------------------------------------------------------
// Per-voice unison state
// ---------------------------------------------------------------------------

/// State for a single unison voice.
#[derive(Debug, Clone, Copy)]
struct UnisonVoice {
    /// Current phase (0.0–1.0, wraps).
    phase: f32,
    /// Detune in cents (pre-computed from mode).
    detune_cents: f32,
    /// Frequency ratio (pre-computed from detune_cents).
    detune_ratio: f32,
    /// Stereo pan (-1.0 left, +1.0 right).
    pan: f32,
    /// Level multiplier (for Supersaw taper).
    level: f32,
}

impl Default for UnisonVoice {
    fn default() -> Self {
        Self {
            phase: 0.0,
            detune_cents: 0.0,
            detune_ratio: 1.0,
            pan: 0.0,
            level: 1.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Unison Engine
// ---------------------------------------------------------------------------

/// Wavetable-aware unison engine.
///
/// Renders 1–16 detuned voices through a WavetableBank, producing
/// stereo output with configurable spread and width.
pub struct UnisonEngine {
    /// Active mode.
    mode: UnisonMode,
    /// Number of active voices (1–16).
    num_voices: usize,
    /// Detune amount (0.0–1.0 → 0–60 cents).
    detune: f32,
    /// Stereo spread (0.0–1.0).
    spread: f32,
    /// Stereo width (0.0–1.0).
    width: f32,
    /// Pre-allocated voice array.
    voices: [UnisonVoice; MAX_UNISON_VOICES],
    /// Simple RNG state for Hyper mode phase randomization.
    rng_state: u32,
}

impl UnisonEngine {
    /// Create a new unison engine (single voice, off).
    pub fn new() -> Self {
        Self {
            mode: UnisonMode::Off,
            num_voices: 1,
            detune: 0.20,
            spread: 0.50,
            width: 0.50,
            voices: [UnisonVoice::default(); MAX_UNISON_VOICES],
            rng_state: 0x12345678,
        }
    }

    /// Configure the unison engine.
    ///
    /// Rebuilds the voice array with new detune/pan distribution.
    pub fn configure(
        &mut self,
        mode: UnisonMode,
        num_voices: usize,
        detune: f32,
        spread: f32,
        width: f32,
    ) {
        self.mode = mode;
        self.num_voices = num_voices.clamp(1, MAX_UNISON_VOICES);
        self.detune = detune.clamp(0.0, 1.0);
        self.spread = spread.clamp(0.0, 1.0);
        self.width = width.clamp(0.0, 1.0);
        self.rebuild_voices();
    }

    /// Set just the mode (convenience).
    pub fn set_mode(&mut self, mode: UnisonMode) {
        self.mode = mode;
        self.rebuild_voices();
    }

    /// Set voice count.
    pub fn set_num_voices(&mut self, n: usize) {
        self.num_voices = n.clamp(1, MAX_UNISON_VOICES);
        self.rebuild_voices();
    }

    /// Set detune amount (0.0–1.0).
    pub fn set_detune(&mut self, detune: f32) {
        self.detune = detune.clamp(0.0, 1.0);
        self.rebuild_voices();
    }

    /// Set stereo spread (0.0–1.0).
    pub fn set_spread(&mut self, spread: f32) {
        self.spread = spread.clamp(0.0, 1.0);
        self.rebuild_voices();
    }

    /// Set stereo width (0.0–1.0).
    pub fn set_width(&mut self, width: f32) {
        self.width = width.clamp(0.0, 1.0);
    }

    /// Get current mode.
    pub fn mode(&self) -> UnisonMode {
        self.mode
    }

    /// Get number of active voices.
    pub fn num_voices(&self) -> usize {
        self.num_voices
    }

    /// Reset all voice phases (call on note-on).
    pub fn reset_phases(&mut self) {
        if self.mode == UnisonMode::Hyper {
            // Hyper: random phase per voice
            for i in 0..self.num_voices {
                self.rng_state = self.rng_state.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFFFFFF;
                self.voices[i].phase = (self.rng_state & 0xFFFF) as f32 / 65536.0;
            }
        } else {
            for v in &mut self.voices {
                v.phase = 0.0;
            }
        }
    }

    /// Render one sample through the wavetable bank.
    ///
    /// Returns `(left, right)` stereo pair.
    ///
    /// `base_freq`: fundamental frequency in Hz
    /// `sample_rate`: audio sample rate
    /// `bank`: wavetable bank to read from
    /// `position`: wavetable position (0.0–1.0)
    #[inline]
    pub fn render_sample(
        &mut self,
        base_freq: f32,
        sample_rate: f32,
        bank: &WavetableBank,
        position: f32,
    ) -> (f32, f32) {
        if bank.is_empty() {
            return (0.0, 0.0);
        }

        let n = self.num_voices;

        if self.mode == UnisonMode::Off || n <= 1 {
            // Single voice — no unison overhead
            let v = &mut self.voices[0];
            let dt = base_freq / sample_rate;
            let sample = bank.read_sample(v.phase, position);
            v.phase = (v.phase + dt).rem_euclid(1.0);
            return (sample, sample);
        }

        let mut sum_l: f32 = 0.0;
        let mut sum_r: f32 = 0.0;
        let width = self.width;

        for i in 0..n {
            let v = &mut self.voices[i];
            let freq = base_freq * v.detune_ratio;
            let dt = freq / sample_rate;

            let sample = bank.read_sample(v.phase, position) * v.level;
            v.phase = (v.phase + dt).rem_euclid(1.0);

            // Equal-power stereo pan
            let pan = v.pan * width;
            let pan_angle = (pan + 1.0) * 0.25 * PI;
            sum_l += sample * pan_angle.cos();
            sum_r += sample * pan_angle.sin();
        }

        // Normalize by sqrt(N) for consistent level
        let norm = 1.0 / (n as f32).sqrt();
        (sum_l * norm, sum_r * norm)
    }

    /// Rebuild voice detune/pan/level arrays from current settings.
    fn rebuild_voices(&mut self) {
        let n = self.num_voices;
        let max_detune_cents = self.detune * 60.0; // 0–60 cents range

        for i in 0..n {
            let v = &mut self.voices[i];

            if n == 1 {
                v.detune_cents = 0.0;
                v.detune_ratio = 1.0;
                v.pan = 0.0;
                v.level = 1.0;
                continue;
            }

            // Position: -1.0 to +1.0 across voice array
            let pos = (i as f32 / (n as f32 - 1.0)) * 2.0 - 1.0;

            match self.mode {
                UnisonMode::Classic => {
                    v.detune_cents = pos * max_detune_cents;
                    v.pan = pos * self.spread;
                    v.level = 1.0;
                }
                UnisonMode::Supersaw => {
                    v.detune_cents = pos * max_detune_cents * 1.3;
                    v.pan = pos * self.spread;
                    v.level = 1.0 - pos.abs() * 0.25; // taper at edges
                }
                UnisonMode::Hyper => {
                    v.detune_cents = pos * max_detune_cents * 1.8;
                    v.pan = pos * self.spread;
                    // Pseudo-random level variation
                    self.rng_state = self.rng_state.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFFFFFF;
                    v.level = 0.8 + (self.rng_state & 0xFF) as f32 / 1280.0; // 0.8–1.0
                }
                UnisonMode::Off => {
                    v.detune_cents = 0.0;
                    v.pan = 0.0;
                    v.level = 1.0;
                }
            }

            // Pre-compute frequency ratio from cents
            v.detune_ratio = 2.0f32.powf(v.detune_cents / 1200.0);
        }
    }

    /// Export state for serialization.
    pub fn export_state(&self) -> (u8, usize, f32, f32, f32) {
        (
            self.mode as u8,
            self.num_voices,
            self.detune,
            self.spread,
            self.width,
        )
    }

    /// Import state from serialized values.
    pub fn import_state(&mut self, mode: u8, num_voices: usize, detune: f32, spread: f32, width: f32) {
        self.configure(
            UnisonMode::from_int(mode),
            num_voices,
            detune,
            spread,
            width,
        );
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const SR: f32 = 44100.0;

    #[test]
    fn test_unison_mode_parse() {
        assert_eq!(UnisonMode::from_int(0), UnisonMode::Off);
        assert_eq!(UnisonMode::from_int(1), UnisonMode::Classic);
        assert_eq!(UnisonMode::from_int(2), UnisonMode::Supersaw);
        assert_eq!(UnisonMode::from_int(3), UnisonMode::Hyper);
        assert_eq!(UnisonMode::from_str("classic"), UnisonMode::Classic);
        assert_eq!(UnisonMode::from_str("unknown"), UnisonMode::Off);
    }

    #[test]
    fn test_unison_mode_roundtrip() {
        for m in &[UnisonMode::Off, UnisonMode::Classic, UnisonMode::Supersaw, UnisonMode::Hyper] {
            let s = m.as_str();
            let parsed = UnisonMode::from_str(s);
            assert_eq!(*m, parsed, "Roundtrip failed for {:?}", m);
        }
    }

    #[test]
    fn test_single_voice_mono() {
        let mut uni = UnisonEngine::new();
        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");

        // Single voice → mono output (L == R)
        let mut diff = 0.0f32;
        for _ in 0..256 {
            let (l, r) = uni.render_sample(440.0, SR, &bank, 0.0);
            diff += (l - r).abs();
        }
        assert!(diff < 0.001, "Single voice should be mono: diff={}", diff);
    }

    #[test]
    fn test_classic_stereo_spread() {
        let mut uni = UnisonEngine::new();
        uni.configure(UnisonMode::Classic, 4, 0.3, 1.0, 1.0);

        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");

        let mut diff = 0.0f32;
        for _ in 0..512 {
            let (l, r) = uni.render_sample(440.0, SR, &bank, 0.5);
            diff += (l - r).abs();
        }
        assert!(diff > 0.1, "Classic unison with spread should have L≠R: diff={}", diff);
    }

    #[test]
    fn test_supersaw_produces_audio() {
        let mut uni = UnisonEngine::new();
        uni.configure(UnisonMode::Supersaw, 7, 0.5, 0.8, 0.7);

        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");

        let mut max_abs = 0.0f32;
        for _ in 0..512 {
            let (l, r) = uni.render_sample(440.0, SR, &bank, 0.8);
            max_abs = max_abs.max(l.abs()).max(r.abs());
        }
        assert!(max_abs > 0.1, "Supersaw should produce audio: max={}", max_abs);
    }

    #[test]
    fn test_hyper_random_phases() {
        let mut uni1 = UnisonEngine::new();
        let mut uni2 = UnisonEngine::new();

        uni1.configure(UnisonMode::Hyper, 8, 0.5, 0.8, 0.7);
        uni2.configure(UnisonMode::Hyper, 8, 0.5, 0.8, 0.7);

        // After reset, hyper voices should have random phases
        uni1.reset_phases();
        uni2.reset_phases();

        // Both engines have same RNG state derivation so phases should differ
        // between voice indices within the same engine
        let phases: Vec<f32> = (0..8).map(|i| uni1.voices[i].phase).collect();
        let unique: std::collections::HashSet<u32> = phases.iter()
            .map(|p| (*p * 10000.0) as u32)
            .collect();
        assert!(unique.len() >= 4, "Hyper should have varied phases: {:?}", phases);
    }

    #[test]
    fn test_empty_bank_silent() {
        let mut uni = UnisonEngine::new();
        uni.configure(UnisonMode::Classic, 4, 0.3, 0.5, 0.5);

        let bank = WavetableBank::new(); // empty

        let (l, r) = uni.render_sample(440.0, SR, &bank, 0.5);
        assert!(l.abs() < 0.001 && r.abs() < 0.001, "Empty bank should be silent");
    }

    #[test]
    fn test_configure_and_state() {
        let mut uni = UnisonEngine::new();
        uni.configure(UnisonMode::Supersaw, 6, 0.4, 0.7, 0.6);

        assert_eq!(uni.mode(), UnisonMode::Supersaw);
        assert_eq!(uni.num_voices(), 6);

        let (mode, nv, det, spr, wid) = uni.export_state();
        assert_eq!(mode, 2); // Supersaw
        assert_eq!(nv, 6);
        assert!((det - 0.4).abs() < 0.001);
        assert!((spr - 0.7).abs() < 0.001);
        assert!((wid - 0.6).abs() < 0.001);
    }

    #[test]
    fn test_import_state() {
        let mut uni = UnisonEngine::new();
        uni.import_state(3, 8, 0.5, 0.9, 0.8);

        assert_eq!(uni.mode(), UnisonMode::Hyper);
        assert_eq!(uni.num_voices(), 8);
    }

    #[test]
    fn test_detune_changes_pitch() {
        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");

        let mut uni_none = UnisonEngine::new();
        uni_none.configure(UnisonMode::Classic, 4, 0.0, 0.0, 0.0); // 0 detune

        let mut uni_detuned = UnisonEngine::new();
        uni_detuned.configure(UnisonMode::Classic, 4, 1.0, 0.0, 0.0); // max detune

        let mut diff = 0.0f32;
        for _ in 0..512 {
            let (l1, _) = uni_none.render_sample(440.0, SR, &bank, 0.5);
            let (l2, _) = uni_detuned.render_sample(440.0, SR, &bank, 0.5);
            diff += (l1 - l2).abs();
        }
        assert!(diff > 0.5, "Detune should change the sound: diff={}", diff);
    }

    #[test]
    fn test_voice_count_clamp() {
        let mut uni = UnisonEngine::new();
        uni.set_num_voices(0); // should clamp to 1
        assert_eq!(uni.num_voices(), 1);
        uni.set_num_voices(100); // should clamp to MAX
        assert_eq!(uni.num_voices(), MAX_UNISON_VOICES);
    }
}
