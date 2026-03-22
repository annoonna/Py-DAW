// ==========================================================================
// Voice Pool — Pre-allocated pool of SampleVoices with stealing
// ==========================================================================
// v0.0.20.671 — Phase R5B
//
// Manages a fixed-size pool of pre-allocated voices.
// Voice stealing strategies: Oldest, Quietest, SameNote.
//
// Rules:
//   ✅ All voices pre-allocated at creation (no heap allocs during playback)
//   ✅ Voice allocation/stealing is O(N) worst case, N = pool size
//   ✅ render_all() sums all active voices into output buffer
//   ❌ NO allocations in audio thread
// ==========================================================================

use crate::sample::{SampleData, SampleVoice, VoiceState, LoopMode};

/// Voice stealing strategy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StealMode {
    /// Steal the oldest active voice.
    Oldest,
    /// Steal the quietest active voice (lowest envelope level).
    Quietest,
    /// Steal a voice playing the same MIDI note (re-trigger), else oldest.
    SameNote,
}

/// Pre-allocated pool of sample voices.
pub struct VoicePool {
    /// Fixed-size array of voices.
    voices: Vec<SampleVoice>,
    /// Maximum number of voices.
    max_voices: usize,
    /// Stealing strategy when pool is full.
    steal_mode: StealMode,
    /// Global sample counter (for age tracking).
    time_counter: u64,
    /// Current engine sample rate.
    sample_rate: f32,
}

impl VoicePool {
    /// Create a new voice pool with `max_voices` pre-allocated voices.
    pub fn new(max_voices: usize, sample_rate: f32) -> Self {
        let clamped = max_voices.clamp(1, 256);
        let mut voices = Vec::with_capacity(clamped);
        for _ in 0..clamped {
            voices.push(SampleVoice::new(sample_rate));
        }
        Self {
            voices,
            max_voices: clamped,
            steal_mode: StealMode::SameNote,
            sample_rate,
            time_counter: 0,
        }
    }

    /// Set the voice stealing mode.
    pub fn set_steal_mode(&mut self, mode: StealMode) {
        self.steal_mode = mode;
    }

    /// Set sample rate for all voices.
    pub fn set_sample_rate(&mut self, sr: f32) {
        self.sample_rate = sr;
        for voice in &mut self.voices {
            voice.set_sample_rate(sr);
        }
    }

    /// Set ADSR parameters for all voices.
    pub fn set_adsr(&mut self, attack: f32, decay: f32, sustain: f32, release: f32) {
        for voice in &mut self.voices {
            voice.set_adsr(attack, decay, sustain, release);
        }
    }

    /// Set loop parameters for all voices.
    pub fn set_loop(&mut self, mode: LoopMode, start: usize, end: usize) {
        for voice in &mut self.voices {
            voice.set_loop(mode, start, end);
        }
    }

    /// Number of currently active voices.
    pub fn active_count(&self) -> usize {
        self.voices.iter().filter(|v| v.is_active()).count()
    }

    /// Trigger note-on. Allocates or steals a voice.
    ///
    /// Returns the index of the voice that was assigned, or None if failed.
    pub fn note_on(
        &mut self,
        sample: SampleData,
        note: u8,
        velocity: f32,
    ) -> Option<usize> {
        self.time_counter += 1;
        let time = self.time_counter;
        let engine_sr = self.sample_rate as u32;

        // SameNote mode: kill existing voices on the same note first (re-trigger)
        if self.steal_mode == StealMode::SameNote {
            for voice in &mut self.voices {
                if voice.is_active() && voice.note() == note {
                    voice.kill();
                    break; // Kill only one (the first match)
                }
            }
        }

        // Try to find a free (idle) voice
        if let Some(idx) = self.find_free_voice() {
            self.voices[idx].note_on(sample, note, velocity, engine_sr, time);
            return Some(idx);
        }

        // No free voices — steal one
        if let Some(idx) = self.find_steal_target(note) {
            self.voices[idx].kill();
            self.voices[idx].note_on(sample, note, velocity, engine_sr, time);
            return Some(idx);
        }

        None // Should never happen if pool size > 0
    }

    /// Trigger note-off for all voices playing the given note.
    pub fn note_off(&mut self, note: u8) {
        for voice in &mut self.voices {
            if voice.is_active() && voice.note() == note && voice.state() == VoiceState::Playing {
                voice.note_off();
            }
        }
    }

    /// Release all active voices.
    pub fn all_notes_off(&mut self) {
        for voice in &mut self.voices {
            if voice.state() == VoiceState::Playing {
                voice.note_off();
            }
        }
    }

    /// Kill all voices immediately (panic button / transport stop).
    pub fn all_sound_off(&mut self) {
        for voice in &mut self.voices {
            voice.kill();
        }
    }

    /// Render all active voices into the output buffer (additive).
    ///
    /// **AUDIO THREAD** — zero-alloc.
    /// `output` is interleaved stereo, length = frames * 2.
    /// Active voices ADD their output to the buffer.
    #[inline]
    pub fn render(&mut self, output: &mut [f32], frames: usize) {
        for voice in &mut self.voices {
            if voice.is_active() {
                voice.render(output, frames);
            }
        }
    }

    /// Advance the time counter (call once per process block).
    pub fn advance_time(&mut self, frames: usize) {
        self.time_counter += frames as u64;
    }

    // --- Private helpers ---

    /// Find a free (idle) voice. Returns index.
    fn find_free_voice(&self) -> Option<usize> {
        self.voices.iter().position(|v| !v.is_active())
    }

    /// Find the best voice to steal based on the current steal mode.
    fn find_steal_target(&self, note: u8) -> Option<usize> {
        match self.steal_mode {
            StealMode::Oldest => {
                // Steal the voice with the smallest start_time
                self.voices
                    .iter()
                    .enumerate()
                    .filter(|(_, v)| v.is_active())
                    .min_by_key(|(_, v)| v.start_time())
                    .map(|(i, _)| i)
            }
            StealMode::Quietest => {
                // Steal the voice with the lowest current level
                self.voices
                    .iter()
                    .enumerate()
                    .filter(|(_, v)| v.is_active())
                    .min_by(|(_, a), (_, b)| {
                        a.current_level()
                            .partial_cmp(&b.current_level())
                            .unwrap_or(std::cmp::Ordering::Equal)
                    })
                    .map(|(i, _)| i)
            }
            StealMode::SameNote => {
                // Prefer stealing a voice on the same note (re-trigger)
                if let Some(idx) = self.voices.iter().position(|v| {
                    v.is_active() && v.note() == note
                }) {
                    return Some(idx);
                }
                // Fallback: steal oldest
                self.voices
                    .iter()
                    .enumerate()
                    .filter(|(_, v)| v.is_active())
                    .min_by_key(|(_, v)| v.start_time())
                    .map(|(i, _)| i)
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

    fn make_test_sample() -> SampleData {
        let mut data = Vec::with_capacity(8820);
        for i in 0..4410 {
            let t = i as f32 / 44100.0;
            let s = (440.0 * 2.0 * std::f32::consts::PI * t).sin() * 0.5;
            data.push(s);
            data.push(s);
        }
        SampleData::from_raw(data, 2, 44100, "test".to_string())
    }

    #[test]
    fn test_pool_note_on_off() {
        let mut pool = VoicePool::new(8, 44100.0);
        pool.set_adsr(0.001, 0.01, 1.0, 0.05);
        assert_eq!(pool.active_count(), 0);

        let sample = make_test_sample();
        pool.note_on(sample.clone(), 60, 0.8);
        assert_eq!(pool.active_count(), 1);

        pool.note_on(sample.clone(), 64, 0.7);
        assert_eq!(pool.active_count(), 2);

        pool.note_off(60);
        // Still active (releasing)
        assert_eq!(pool.active_count(), 2);

        pool.all_sound_off();
        assert_eq!(pool.active_count(), 0);
    }

    #[test]
    fn test_pool_voice_stealing() {
        // Pool with only 2 voices
        let mut pool = VoicePool::new(2, 44100.0);
        pool.set_adsr(0.0, 0.0, 1.0, 0.5);
        pool.set_steal_mode(StealMode::Oldest);

        let sample = make_test_sample();
        pool.note_on(sample.clone(), 60, 1.0); // Voice 0
        pool.note_on(sample.clone(), 64, 1.0); // Voice 1
        assert_eq!(pool.active_count(), 2);

        // Third note should steal oldest (voice 0, note 60)
        let stolen_idx = pool.note_on(sample.clone(), 67, 1.0);
        assert_eq!(pool.active_count(), 2); // Still 2 (one was stolen)
        assert!(stolen_idx.is_some());
    }

    #[test]
    fn test_pool_same_note_steal() {
        let mut pool = VoicePool::new(4, 44100.0);
        pool.set_adsr(0.0, 0.0, 1.0, 0.5);
        pool.set_steal_mode(StealMode::SameNote);

        let sample = make_test_sample();
        pool.note_on(sample.clone(), 60, 1.0);
        pool.note_on(sample.clone(), 64, 1.0);
        pool.note_on(sample.clone(), 67, 1.0);

        // Re-trigger note 60 — should steal the existing voice on 60
        pool.note_on(sample.clone(), 60, 0.9);
        assert_eq!(pool.active_count(), 3); // NOT 4 (re-triggered same note)
    }

    #[test]
    fn test_pool_render() {
        let mut pool = VoicePool::new(4, 44100.0);
        pool.set_adsr(0.0, 0.0, 1.0, 0.5);

        let sample = make_test_sample();
        pool.note_on(sample.clone(), 60, 1.0);
        pool.note_on(sample.clone(), 64, 0.7);

        let mut buf = vec![0.0f32; 256 * 2];
        pool.render(&mut buf, 256);

        // Should have output from both voices
        let max = buf.iter().fold(0.0f32, |m, &s| m.max(s.abs()));
        assert!(max > 0.01, "Pool should produce output, got max={}", max);
    }

    #[test]
    fn test_pool_all_notes_off() {
        let mut pool = VoicePool::new(4, 44100.0);
        pool.set_adsr(0.0, 0.0, 1.0, 0.1);

        let sample = make_test_sample();
        pool.note_on(sample.clone(), 60, 1.0);
        pool.note_on(sample.clone(), 64, 1.0);
        pool.note_on(sample.clone(), 67, 1.0);

        pool.all_notes_off();

        // All should be releasing, not idle yet
        for voice in &pool.voices {
            if voice.is_active() {
                assert_eq!(voice.state(), VoiceState::Releasing);
            }
        }
    }
}
