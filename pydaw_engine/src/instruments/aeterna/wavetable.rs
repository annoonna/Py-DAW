// ==========================================================================
// AETERNA Wavetable Bank — Frame storage, morphing, built-in tables
// ==========================================================================
// v0.0.20.692 — Phase R9A
//
// A wavetable is a collection of single-cycle waveforms ("frames").
// The `wt_position` parameter (0.0–1.0) crossfades between frames.
//
// Storage: Pre-allocated flat array [MAX_FRAMES × FRAME_SIZE] for zero-alloc.
// Interpolation: Bilinear (linear between adjacent frames + linear within frame).
//
// Built-in tables generated at init:
//   - Basic (Sine→Saw): 16 frames, additive harmonics morphing
//   - Basic (Sine→Square): 16 frames, odd harmonics morphing
//   - PWM (Pulse Width): 16 frames, variable duty cycle
//   - Harmonic Sweep: 16 frames, cumulative harmonics
//   - Formant (Vowels): 16 frames, formant synthesis
//   - Noise Morph: 16 frames, sine → noise blend
//
// Rules:
//   ✅ read_sample() is #[inline] and zero-alloc
//   ✅ All frame data pre-allocated in flat array
//   ❌ NO allocations in audio thread
// ==========================================================================

use std::f32::consts::PI;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Samples per wavetable frame (single cycle).
pub const FRAME_SIZE: usize = 2048;

/// Maximum number of frames in a wavetable.
pub const MAX_FRAMES: usize = 256;

/// Number of frames in built-in tables.
const BUILTIN_FRAMES: usize = 16;

const TWO_PI: f32 = 2.0 * PI;

// ---------------------------------------------------------------------------
// WavetableBank
// ---------------------------------------------------------------------------

/// A wavetable bank: a collection of single-cycle waveforms.
///
/// Frames are stored in a flat pre-allocated array for cache efficiency.
/// Access: `data[frame_index * FRAME_SIZE + sample_index]`
pub struct WavetableBank {
    /// Flat storage: MAX_FRAMES × FRAME_SIZE f32 samples.
    data: Vec<f32>,
    /// Number of active frames (1..MAX_FRAMES).
    num_frames: usize,
    /// Frame size (always FRAME_SIZE for now).
    frame_size: usize,
}

impl WavetableBank {
    /// Create an empty wavetable bank (pre-allocated).
    pub fn new() -> Self {
        Self {
            data: vec![0.0; MAX_FRAMES * FRAME_SIZE],
            num_frames: 0,
            frame_size: FRAME_SIZE,
        }
    }

    /// Create a bank with a built-in wavetable loaded.
    pub fn with_builtin(name: &str) -> Self {
        let mut bank = Self::new();
        bank.load_builtin(name);
        bank
    }

    /// Number of active frames.
    #[inline]
    pub fn num_frames(&self) -> usize {
        self.num_frames
    }

    /// Whether the bank has any frames loaded.
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.num_frames == 0
    }

    /// Load a built-in wavetable by name.
    ///
    /// Returns `true` if the name was recognized and loaded.
    pub fn load_builtin(&mut self, name: &str) -> bool {
        match name {
            "Basic (Sine→Saw)" | "sine_to_saw" | "basic_saw" => {
                self.generate_sine_to_saw();
                true
            }
            "Basic (Sine→Square)" | "sine_to_square" | "basic_square" => {
                self.generate_sine_to_square();
                true
            }
            "PWM (Pulse Width)" | "pwm" => {
                self.generate_pwm();
                true
            }
            "Harmonic Sweep" | "harmonic_sweep" => {
                self.generate_harmonic_sweep();
                true
            }
            "Formant (Vowels)" | "formant" => {
                self.generate_formant();
                true
            }
            "Noise Morph" | "noise_morph" => {
                self.generate_noise_morph();
                true
            }
            _ => false,
        }
    }

    /// List available built-in wavetable names.
    pub fn builtin_names() -> &'static [&'static str] {
        &[
            "Basic (Sine→Saw)",
            "Basic (Sine→Square)",
            "PWM (Pulse Width)",
            "Harmonic Sweep",
            "Formant (Vowels)",
            "Noise Morph",
        ]
    }

    /// Load frames from raw f32 data.
    ///
    /// `raw` must be a flat array of frame_count × frame_size samples.
    /// Used for loading from WAV/WT files (Python loads file, sends data via IPC).
    pub fn load_raw(&mut self, raw: &[f32], frame_count: usize, frame_size: usize) -> bool {
        if frame_count == 0 || frame_size == 0 {
            return false;
        }
        let n = frame_count.min(MAX_FRAMES);
        // Clear
        self.data.fill(0.0);
        self.num_frames = n;
        self.frame_size = frame_size.min(FRAME_SIZE);

        for fi in 0..n {
            let src_off = fi * frame_size;
            let dst_off = fi * FRAME_SIZE;
            let copy_len = frame_size.min(FRAME_SIZE).min(raw.len().saturating_sub(src_off));
            for i in 0..copy_len {
                if src_off + i < raw.len() {
                    self.data[dst_off + i] = raw[src_off + i];
                }
            }
            // If source frame_size < FRAME_SIZE, the rest stays zero (silence padded)
        }
        true
    }

    /// Set a single frame's data.
    pub fn set_frame(&mut self, frame_index: usize, samples: &[f32]) {
        if frame_index >= MAX_FRAMES {
            return;
        }
        let off = frame_index * FRAME_SIZE;
        let n = samples.len().min(FRAME_SIZE);
        for i in 0..n {
            self.data[off + i] = samples[i];
        }
        if frame_index >= self.num_frames {
            self.num_frames = frame_index + 1;
        }
    }

    /// Read a single interpolated sample.
    ///
    /// `phase`: 0.0–1.0 (position within single cycle)
    /// `position`: 0.0–1.0 (crossfade position across frames)
    ///
    /// Uses bilinear interpolation (linear between frames + linear within frame).
    #[inline]
    pub fn read_sample(&self, phase: f32, position: f32) -> f32 {
        let n = self.num_frames;
        if n == 0 {
            return 0.0;
        }

        // Frame interpolation
        let pos = position.clamp(0.0, 1.0) * (n as f32 - 1.0);
        let frame_lo = (pos as usize).min(n - 1);
        let frame_hi = (frame_lo + 1).min(n - 1);
        let frame_frac = pos - frame_lo as f32;

        // Sample interpolation within frame
        let fsize = FRAME_SIZE as f32;
        let sample_pos = phase.rem_euclid(1.0) * fsize;
        let s_lo = (sample_pos as usize) % FRAME_SIZE;
        let s_hi = (s_lo + 1) % FRAME_SIZE;
        let s_frac = sample_pos - sample_pos.floor();

        // Bilinear: interpolate within each frame, then between frames
        let off_lo = frame_lo * FRAME_SIZE;
        let off_hi = frame_hi * FRAME_SIZE;

        let val_lo = self.data[off_lo + s_lo] * (1.0 - s_frac)
            + self.data[off_lo + s_hi] * s_frac;
        let val_hi = self.data[off_hi + s_lo] * (1.0 - s_frac)
            + self.data[off_hi + s_hi] * s_frac;

        val_lo * (1.0 - frame_frac) + val_hi * frame_frac
    }

    // =====================================================================
    // Built-in wavetable generators
    // =====================================================================

    /// Sine → Saw morph (additive harmonics, increasing partials).
    fn generate_sine_to_saw(&mut self) {
        self.num_frames = BUILTIN_FRAMES;
        for fi in 0..BUILTIN_FRAMES {
            let max_harm = 1 + (fi * 31) / (BUILTIN_FRAMES - 1); // 1..32 harmonics
            let off = fi * FRAME_SIZE;
            for i in 0..FRAME_SIZE {
                let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
                let mut val = 0.0f32;
                for h in 1..=max_harm {
                    let sign = if h % 2 == 0 { -1.0 } else { 1.0 };
                    val += sign * (phase * h as f32).sin() / h as f32;
                }
                self.data[off + i] = val * (2.0 / PI); // normalize
            }
        }
    }

    /// Sine → Square morph (odd harmonics only).
    fn generate_sine_to_square(&mut self) {
        self.num_frames = BUILTIN_FRAMES;
        for fi in 0..BUILTIN_FRAMES {
            let max_harm = 1 + (fi * 15) / (BUILTIN_FRAMES - 1); // 1..16 odd harmonics
            let off = fi * FRAME_SIZE;
            for i in 0..FRAME_SIZE {
                let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
                let mut val = 0.0f32;
                for h_idx in 0..max_harm {
                    let h = 2 * h_idx + 1; // odd: 1, 3, 5, 7, ...
                    val += (phase * h as f32).sin() / h as f32;
                }
                self.data[off + i] = val * (4.0 / PI); // normalize
            }
        }
    }

    /// PWM (Pulse Width Modulation) — variable duty cycle.
    fn generate_pwm(&mut self) {
        self.num_frames = BUILTIN_FRAMES;
        for fi in 0..BUILTIN_FRAMES {
            let duty = 0.1 + (fi as f32 / (BUILTIN_FRAMES - 1) as f32) * 0.8; // 0.1..0.9
            let off = fi * FRAME_SIZE;
            for i in 0..FRAME_SIZE {
                let t = i as f32 / FRAME_SIZE as f32;
                self.data[off + i] = if t < duty { 1.0 } else { -1.0 };
            }
        }
    }

    /// Harmonic Sweep — cumulative additive harmonics.
    fn generate_harmonic_sweep(&mut self) {
        self.num_frames = BUILTIN_FRAMES;
        for fi in 0..BUILTIN_FRAMES {
            let n_harm = 1 + (fi * 63) / (BUILTIN_FRAMES - 1); // 1..64
            let off = fi * FRAME_SIZE;
            let mut peak = 0.0f32;
            for i in 0..FRAME_SIZE {
                let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
                let mut val = 0.0f32;
                for h in 1..=n_harm {
                    val += (phase * h as f32).sin() / (1.0 + (h as f32 - 1.0) * 0.5);
                }
                self.data[off + i] = val;
                peak = peak.max(val.abs());
            }
            // Normalize
            if peak > 0.001 {
                let norm = 1.0 / peak;
                for i in 0..FRAME_SIZE {
                    self.data[off + i] *= norm;
                }
            }
        }
    }

    /// Formant (Vowels) — simple formant synthesis.
    fn generate_formant(&mut self) {
        // 5 vowel formant sets (F1, F2 in Hz), interpolated across 16 frames
        const FORMANTS: [(f32, f32); 5] = [
            (730.0, 1090.0),  // A
            (270.0, 2290.0),  // E
            (390.0, 1990.0),  // I
            (570.0, 840.0),   // O
            (440.0, 1020.0),  // U
        ];
        self.num_frames = BUILTIN_FRAMES;
        let base_freq = 1.0 / FRAME_SIZE as f32; // normalized base freq
        for fi in 0..BUILTIN_FRAMES {
            let t = fi as f32 / (BUILTIN_FRAMES - 1) as f32;
            let idx = (t * 4.0).min(3.99);
            let lo = idx as usize;
            let hi = (lo + 1).min(4);
            let frac = idx - lo as f32;
            let f1 = FORMANTS[lo].0 * (1.0 - frac) + FORMANTS[hi].0 * frac;
            let f2 = FORMANTS[lo].1 * (1.0 - frac) + FORMANTS[hi].1 * frac;

            let off = fi * FRAME_SIZE;
            let mut peak = 0.0f32;
            for i in 0..FRAME_SIZE {
                let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
                // Carrier + formant modulation
                let carrier = phase.sin();
                let form1 = (phase * f1 * base_freq * FRAME_SIZE as f32).sin() * 0.4;
                let form2 = (phase * f2 * base_freq * FRAME_SIZE as f32).sin() * 0.25;
                let val = carrier * 0.5 + form1 + form2;
                self.data[off + i] = val;
                peak = peak.max(val.abs());
            }
            if peak > 0.001 {
                let norm = 0.9 / peak;
                for i in 0..FRAME_SIZE {
                    self.data[off + i] *= norm;
                }
            }
        }
    }

    /// Noise Morph — clean sine → noisy.
    fn generate_noise_morph(&mut self) {
        self.num_frames = BUILTIN_FRAMES;
        let mut rng: u32 = 0xDEADBEEF;
        for fi in 0..BUILTIN_FRAMES {
            let noise_amt = fi as f32 / (BUILTIN_FRAMES - 1) as f32;
            let off = fi * FRAME_SIZE;
            for i in 0..FRAME_SIZE {
                let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
                let sine = phase.sin();
                // Simple LCG noise
                rng = rng.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFFFFFF;
                let noise = (rng as f32 / 0x40000000 as f32) - 1.0;
                self.data[off + i] = sine * (1.0 - noise_amt) + noise * noise_amt;
            }
        }
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_bank() {
        let bank = WavetableBank::new();
        assert!(bank.is_empty());
        assert_eq!(bank.num_frames(), 0);
        assert!((bank.read_sample(0.0, 0.0)).abs() < 0.001);
    }

    #[test]
    fn test_load_builtin_sine_to_saw() {
        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");
        assert_eq!(bank.num_frames(), BUILTIN_FRAMES);
        assert!(!bank.is_empty());

        // Position 0 = pure sine → should be near 0 at phase 0
        let s0 = bank.read_sample(0.0, 0.0);
        assert!(s0.abs() < 0.1, "Sine at phase 0 should be near 0: {}", s0);

        // Position 0, phase 0.25 → sine peak
        let s_peak = bank.read_sample(0.25, 0.0);
        assert!(s_peak > 0.3, "Sine peak should be positive: {}", s_peak);
    }

    #[test]
    fn test_load_builtin_square() {
        let bank = WavetableBank::with_builtin("Basic (Sine→Square)");
        assert_eq!(bank.num_frames(), BUILTIN_FRAMES);

        // Last frame should be square-ish (high at 0.25, low at 0.75)
        let high = bank.read_sample(0.25, 1.0);
        let low = bank.read_sample(0.75, 1.0);
        assert!(high > 0.3, "Square high should be positive: {}", high);
        assert!(low < -0.3, "Square low should be negative: {}", low);
    }

    #[test]
    fn test_morphing_changes_sound() {
        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");

        // Sample at same phase, different positions
        let mut diff = 0.0f32;
        for i in 0..100 {
            let phase = i as f32 / 100.0;
            let s_sine = bank.read_sample(phase, 0.0);
            let s_saw = bank.read_sample(phase, 1.0);
            diff += (s_sine - s_saw).abs();
        }
        assert!(diff > 1.0, "Different positions should sound different: diff={}", diff);
    }

    #[test]
    fn test_phase_wrapping() {
        let bank = WavetableBank::with_builtin("Basic (Sine→Saw)");
        // Phase wrapping: 1.25 should equal 0.25
        let s1 = bank.read_sample(0.25, 0.5);
        let s2 = bank.read_sample(1.25, 0.5);
        assert!((s1 - s2).abs() < 0.01, "Phase should wrap: {} vs {}", s1, s2);
    }

    #[test]
    fn test_all_builtins_load() {
        for name in WavetableBank::builtin_names() {
            let bank = WavetableBank::with_builtin(name);
            assert!(!bank.is_empty(), "Builtin '{}' should load", name);
            assert_eq!(bank.num_frames(), BUILTIN_FRAMES);

            // Should produce non-zero audio
            let mut max_val = 0.0f32;
            for i in 0..FRAME_SIZE {
                let phase = i as f32 / FRAME_SIZE as f32;
                let s = bank.read_sample(phase, 0.5);
                max_val = max_val.max(s.abs());
            }
            assert!(max_val > 0.1, "Builtin '{}' should produce audio: max={}", name, max_val);
        }
    }

    #[test]
    fn test_load_raw() {
        let mut bank = WavetableBank::new();
        // Create a simple 2-frame table: silence + sine
        let mut raw = vec![0.0f32; 2 * FRAME_SIZE];
        // Frame 1: sine
        for i in 0..FRAME_SIZE {
            let phase = (i as f32 / FRAME_SIZE as f32) * TWO_PI;
            raw[FRAME_SIZE + i] = phase.sin();
        }
        assert!(bank.load_raw(&raw, 2, FRAME_SIZE));
        assert_eq!(bank.num_frames(), 2);

        // Position 0 = silence
        let s0 = bank.read_sample(0.25, 0.0);
        assert!(s0.abs() < 0.01, "Frame 0 should be silent: {}", s0);

        // Position 1 = sine
        let s1 = bank.read_sample(0.25, 1.0);
        assert!(s1 > 0.5, "Frame 1 should be sine peak: {}", s1);
    }

    #[test]
    fn test_set_frame() {
        let mut bank = WavetableBank::new();
        let mut frame = vec![0.0f32; FRAME_SIZE];
        // DC offset frame
        frame.fill(0.5);
        bank.set_frame(0, &frame);
        assert_eq!(bank.num_frames(), 1);

        let s = bank.read_sample(0.0, 0.0);
        assert!((s - 0.5).abs() < 0.01, "DC frame should read 0.5: {}", s);
    }

    #[test]
    fn test_unknown_builtin() {
        let mut bank = WavetableBank::new();
        assert!(!bank.load_builtin("NonExistent Table"));
        assert!(bank.is_empty());
    }
}
