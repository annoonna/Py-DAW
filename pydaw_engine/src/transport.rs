use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

// ============================================================================
// Transport — Playback timing and position tracking
// ============================================================================

/// Real-time transport state. All fields are atomic for lock-free access
/// from both the audio thread and the IPC command handler.
pub struct Transport {
    /// Whether playback is active.
    pub playing: AtomicBool,

    /// Current position in samples (atomic u64, monotonically increasing).
    /// Reinterpret as i64 for negative pre-roll positions.
    position_samples: AtomicU64,

    /// Tempo in BPM (stored as u64 bits of f64).
    bpm_bits: AtomicU64,

    /// Sample rate.
    sample_rate_bits: AtomicU64,

    /// Time signature numerator.
    pub time_sig_num: std::sync::atomic::AtomicU8,
    /// Time signature denominator.
    pub time_sig_den: std::sync::atomic::AtomicU8,

    /// Loop enabled.
    pub loop_enabled: AtomicBool,
    /// Loop start in samples.
    loop_start_bits: AtomicU64,
    /// Loop end in samples.
    loop_end_bits: AtomicU64,
}

impl Transport {
    pub fn new(sample_rate: u32, bpm: f64) -> Self {
        Self {
            playing: AtomicBool::new(false),
            position_samples: AtomicU64::new(0),
            bpm_bits: AtomicU64::new(bpm.to_bits()),
            sample_rate_bits: AtomicU64::new((sample_rate as f64).to_bits()),
            time_sig_num: std::sync::atomic::AtomicU8::new(4),
            time_sig_den: std::sync::atomic::AtomicU8::new(4),
            loop_enabled: AtomicBool::new(false),
            loop_start_bits: AtomicU64::new(0u64.to_be()),
            loop_end_bits: AtomicU64::new(0u64.to_be()),
        }
    }

    // -- Getters (lock-free, audio-thread safe) ----------------------------

    pub fn bpm(&self) -> f64 {
        f64::from_bits(self.bpm_bits.load(Ordering::Relaxed))
    }

    pub fn sample_rate(&self) -> f64 {
        f64::from_bits(self.sample_rate_bits.load(Ordering::Relaxed))
    }

    pub fn position_samples(&self) -> i64 {
        self.position_samples.load(Ordering::Relaxed) as i64
    }

    pub fn position_beats(&self) -> f64 {
        let samples = self.position_samples() as f64;
        let sr = self.sample_rate();
        let bpm = self.bpm();
        if sr <= 0.0 || bpm <= 0.0 {
            return 0.0;
        }
        samples * bpm / (sr * 60.0)
    }

    pub fn loop_start_samples(&self) -> i64 {
        i64::from_be_bytes(self.loop_start_bits.load(Ordering::Relaxed).to_be_bytes())
    }

    pub fn loop_end_samples(&self) -> i64 {
        i64::from_be_bytes(self.loop_end_bits.load(Ordering::Relaxed).to_be_bytes())
    }

    // -- Setters (called from command handler, NOT audio thread) -----------

    pub fn set_bpm(&self, bpm: f64) {
        self.bpm_bits
            .store(bpm.clamp(20.0, 999.0).to_bits(), Ordering::Relaxed);
    }

    pub fn set_sample_rate(&self, sr: u32) {
        self.sample_rate_bits
            .store((sr as f64).to_bits(), Ordering::Relaxed);
    }

    pub fn set_time_signature(&self, num: u8, den: u8) {
        self.time_sig_num.store(num, Ordering::Relaxed);
        self.time_sig_den.store(den, Ordering::Relaxed);
    }

    pub fn set_loop(&self, enabled: bool, start_beat: f64, end_beat: f64) {
        let sr = self.sample_rate();
        let bpm = self.bpm();
        if sr > 0.0 && bpm > 0.0 {
            let start_samples = (start_beat * sr * 60.0 / bpm) as i64;
            let end_samples = (end_beat * sr * 60.0 / bpm) as i64;
            self.loop_start_bits.store(
                u64::from_be_bytes(start_samples.to_be_bytes()),
                Ordering::Relaxed,
            );
            self.loop_end_bits.store(
                u64::from_be_bytes(end_samples.to_be_bytes()),
                Ordering::Relaxed,
            );
        }
        self.loop_enabled.store(enabled, Ordering::Release);
    }

    // -- Audio thread operations -------------------------------------------

    /// Advance the playhead by `frames` samples.
    /// Handles loop wraparound. Called from the audio callback.
    pub fn advance(&self, frames: usize) {
        if !self.playing.load(Ordering::Relaxed) {
            return;
        }

        let current = self.position_samples() ;
        let mut new_pos = current + frames as i64;

        // Loop wraparound
        if self.loop_enabled.load(Ordering::Relaxed) {
            let loop_end = self.loop_end_samples();
            let loop_start = self.loop_start_samples();
            if loop_end > loop_start && new_pos >= loop_end {
                new_pos = loop_start + (new_pos - loop_end);
            }
        }

        self.position_samples
            .store(new_pos as u64, Ordering::Relaxed);
    }

    /// Seek to a beat position.
    pub fn seek_to_beat(&self, beat: f64) {
        let sr = self.sample_rate();
        let bpm = self.bpm();
        if sr > 0.0 && bpm > 0.0 {
            let samples = (beat * sr * 60.0 / bpm) as i64;
            self.position_samples
                .store(samples.max(0) as u64, Ordering::Relaxed);
        }
    }

    /// Seek to a sample position.
    pub fn seek_to_sample(&self, sample: i64) {
        self.position_samples
            .store(sample.max(0) as u64, Ordering::Relaxed);
    }

    /// Convert beat position to sample position.
    pub fn beat_to_samples(&self, beat: f64) -> i64 {
        let sr = self.sample_rate();
        let bpm = self.bpm();
        if sr <= 0.0 || bpm <= 0.0 {
            return 0;
        }
        (beat * sr * 60.0 / bpm) as i64
    }
}
