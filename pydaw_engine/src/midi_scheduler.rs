// ==========================================================================
// MIDI Clip Scheduler — Beat-accurate MIDI dispatching during playback
// ==========================================================================
// v0.0.20.725 — THE MISSING PIECE
//
// This module bridges the gap between:
//   - MIDI notes stored in the arrangement (from ProjectSync)
//   - InstrumentNode::push_midi() on the audio thread
//
// During playback, process_audio() calls schedule_for_buffer() which:
//   1. Calculates the beat range for the current buffer
//   2. Finds NoteOn events in that range → push_midi(NoteOn)
//   3. Finds NoteOff events (note_start + note_length) → push_midi(NoteOff)
//
// Architecture:
//   ProjectSync ──→ MidiScheduler::load_from_sync()
//                     ↓ (sorted event list per track)
//   process_audio ──→ MidiScheduler::schedule_for_buffer()
//                     ↓
//                   track.instrument.push_midi(NoteOn/NoteOff)
//
// Rules:
//   ✅ NO allocations in schedule_for_buffer() (pre-sorted, index scan)
//   ✅ Lock-free: owned by engine, called only from audio thread
//   ✅ Handles loop regions correctly
//   ❌ Does NOT handle tempo automation (assumes constant BPM per buffer)
// ==========================================================================

use crate::audio_bridge::{MidiNoteConfig, ClipConfig};

/// A pre-computed, time-sorted MIDI event for the scheduler.
#[derive(Debug, Clone, Copy)]
pub struct ScheduledEvent {
    /// Absolute beat position of this event.
    pub beat: f64,
    /// Track index (matches AudioGraph track index).
    pub track_index: u16,
    /// MIDI note number (0–127).
    pub pitch: u8,
    /// Velocity (0.0–1.0). 0.0 = NoteOff.
    pub velocity: f32,
    /// True = NoteOn, False = NoteOff.
    pub is_note_on: bool,
}

/// MIDI Clip Scheduler — holds all arrangement MIDI events, sorted by beat.
///
/// Call `load_from_sync()` when the project changes.
/// Call `schedule_for_buffer()` from the audio callback.
pub struct MidiScheduler {
    /// All events sorted by beat position (ascending).
    events: Vec<ScheduledEvent>,
    /// Current scan index (advances as playback progresses).
    /// Reset to 0 on seek or loop.
    scan_index: usize,
    /// Last processed beat position (for seek detection).
    last_beat: f64,
    /// Total number of events.
    event_count: usize,
}

impl MidiScheduler {
    /// Create an empty scheduler.
    pub fn new() -> Self {
        Self {
            events: Vec::new(),
            scan_index: 0,
            last_beat: -1.0,
            event_count: 0,
        }
    }

    /// Load MIDI events from a ProjectSync.
    ///
    /// Converts relative (per-clip) MIDI note positions to absolute beat positions
    /// and sorts all events chronologically.
    ///
    /// This is called from the command thread (NOT audio thread) so allocations are OK.
    pub fn load_from_sync(
        &mut self,
        clips: &[ClipConfig],
        midi_notes: &[MidiNoteConfig],
        tracks: &[crate::audio_bridge::TrackConfig],
    ) {
        self.events.clear();
        self.scan_index = 0;
        self.last_beat = -1.0;

        // Build clip_id → (track_id, clip_start_beats, clip_offset_beats) map
        let mut clip_map: std::collections::HashMap<&str, (&str, f64, f64)> =
            std::collections::HashMap::new();
        for clip in clips {
            if clip.kind == "midi" {
                clip_map.insert(
                    &clip.clip_id,
                    (&clip.track_id, clip.start_beats, clip.offset_beats),
                );
            }
        }

        // Build track_id → track_index map
        let mut track_idx_map: std::collections::HashMap<&str, u16> =
            std::collections::HashMap::new();
        for tc in tracks {
            track_idx_map.insert(&tc.track_id, tc.track_index);
        }

        // Convert MIDI notes to absolute-beat ScheduledEvents
        for note in midi_notes {
            let (track_id, clip_start, clip_offset) = match clip_map.get(note.clip_id.as_str()) {
                Some(v) => *v,
                None => continue, // Note belongs to unknown clip — skip
            };
            let track_index = match track_idx_map.get(track_id) {
                Some(&idx) => idx,
                None => continue, // Unknown track — skip
            };

            // Absolute beat = clip_start + note_start_in_clip - clip_offset
            let abs_start = clip_start + note.start_beats - clip_offset;
            let abs_end = abs_start + note.length_beats;

            // Velocity: u8 (0–127) → f32 (0.0–1.0)
            let velocity = note.velocity as f32 / 127.0;

            // NoteOn event
            self.events.push(ScheduledEvent {
                beat: abs_start,
                track_index,
                pitch: note.pitch,
                velocity,
                is_note_on: true,
            });

            // NoteOff event
            self.events.push(ScheduledEvent {
                beat: abs_end,
                track_index,
                pitch: note.pitch,
                velocity: 0.0,
                is_note_on: false,
            });
        }

        // Sort by beat position (stable sort preserves NoteOff before NoteOn at same beat)
        self.events.sort_by(|a, b| {
            a.beat.partial_cmp(&b.beat).unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| {
                    // NoteOff before NoteOn at same beat (avoid stuck notes)
                    a.is_note_on.cmp(&b.is_note_on)
                })
        });

        self.event_count = self.events.len();
        if self.event_count > 0 {
            log::info!(
                "MidiScheduler: loaded {} events ({} notes) across {} MIDI clips",
                self.event_count,
                midi_notes.len(),
                clip_map.len(),
            );
        }
    }

    /// Schedule MIDI events for one audio buffer.
    ///
    /// Called from `process_audio()` on the AUDIO THREAD.
    /// NO allocations, NO locks.
    ///
    /// Returns an iterator of events that fall within [beat_start, beat_end).
    /// The caller is responsible for dispatching them to the correct track instruments.
    ///
    /// Arguments:
    ///   - beat_start: Start beat of this buffer
    ///   - beat_end: End beat of this buffer (exclusive)
    ///   - is_playing: Skip scheduling if not playing
    pub fn schedule_for_buffer(
        &mut self,
        beat_start: f64,
        beat_end: f64,
        is_playing: bool,
    ) -> MidiBufferIter<'_> {
        if !is_playing || self.event_count == 0 {
            return MidiBufferIter {
                events: &self.events,
                start: 0,
                end: 0,
            };
        }

        // Detect seek (playhead jumped backward or forward significantly)
        if beat_start < self.last_beat - 0.01 {
            // Seek backward (or loop restart) — reset scan index
            self.scan_index = 0;
            // Binary search to find start position
            self.scan_index = self.events
                .partition_point(|e| e.beat < beat_start);
        } else if beat_start > self.last_beat + 1.0 {
            // Forward seek — binary search
            self.scan_index = self.events
                .partition_point(|e| e.beat < beat_start);
        }

        self.last_beat = beat_end;

        // Scan forward from current position to find events in [beat_start, beat_end)
        let _start_idx = self.scan_index;

        // Advance scan_index past events before beat_start
        while self.scan_index < self.event_count
            && self.events[self.scan_index].beat < beat_start
        {
            self.scan_index += 1;
        }

        let range_start = self.scan_index;

        // Find end of range (first event at or past beat_end)
        let mut range_end = range_start;
        while range_end < self.event_count
            && self.events[range_end].beat < beat_end
        {
            range_end += 1;
        }

        // Advance scan_index to end of range for next call
        self.scan_index = range_end;

        MidiBufferIter {
            events: &self.events,
            start: range_start,
            end: range_end,
        }
    }

    /// Reset playback position (on seek, stop, or loop).
    pub fn reset(&mut self) {
        self.scan_index = 0;
        self.last_beat = -1.0;
    }

    /// Number of loaded events.
    pub fn event_count(&self) -> usize {
        self.event_count
    }

    /// Clear all events.
    pub fn clear(&mut self) {
        self.events.clear();
        self.event_count = 0;
        self.scan_index = 0;
        self.last_beat = -1.0;
    }
}

/// Zero-allocation iterator over events in a beat range.
pub struct MidiBufferIter<'a> {
    events: &'a [ScheduledEvent],
    start: usize,
    end: usize,
}

impl<'a> Iterator for MidiBufferIter<'a> {
    type Item = &'a ScheduledEvent;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        if self.start < self.end {
            let evt = &self.events[self.start];
            self.start += 1;
            Some(evt)
        } else {
            None
        }
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        let len = self.end - self.start;
        (len, Some(len))
    }
}

// ==========================================================================
// Tests
// ==========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio_bridge::{ClipConfig, MidiNoteConfig, TrackConfig};

    fn make_track(id: &str, idx: u16) -> TrackConfig {
        TrackConfig {
            track_id: id.to_string(),
            track_index: idx,
            kind: "instrument".to_string(),
            volume: 1.0,
            pan: 0.0,
            muted: false,
            soloed: false,
            instrument_type: None,
            instrument_id: None,
            group_index: None,
        }
    }

    fn make_clip(clip_id: &str, track_id: &str, start: f64, len: f64) -> ClipConfig {
        ClipConfig {
            clip_id: clip_id.to_string(),
            track_id: track_id.to_string(),
            start_beats: start,
            length_beats: len,
            kind: "midi".to_string(),
            audio_b64: None,
            source_sr: None,
            source_channels: None,
            gain: 1.0,
            offset_beats: 0.0,
        }
    }

    fn make_note(clip_id: &str, pitch: u8, vel: u8, start: f64, len: f64) -> MidiNoteConfig {
        MidiNoteConfig {
            clip_id: clip_id.to_string(),
            pitch,
            velocity: vel,
            start_beats: start,
            length_beats: len,
        }
    }

    #[test]
    fn test_empty_scheduler() {
        let mut sched = MidiScheduler::new();
        let iter = sched.schedule_for_buffer(0.0, 1.0, true);
        assert_eq!(iter.count(), 0);
    }

    #[test]
    fn test_basic_note_scheduling() {
        let mut sched = MidiScheduler::new();

        let tracks = vec![make_track("t1", 0)];
        let clips = vec![make_clip("c1", "t1", 0.0, 4.0)];
        // Note at beat 1.0, length 0.5
        let notes = vec![make_note("c1", 60, 100, 1.0, 0.5)];

        sched.load_from_sync(&clips, &notes, &tracks);
        assert_eq!(sched.event_count(), 2); // NoteOn + NoteOff

        // Buffer 0.0–1.0: no notes start here
        let events: Vec<_> = sched.schedule_for_buffer(0.0, 1.0, true).collect();
        assert_eq!(events.len(), 0);

        // Buffer 1.0–2.0: NoteOn at 1.0 + NoteOff at 1.5
        let events: Vec<_> = sched.schedule_for_buffer(1.0, 2.0, true).collect();
        assert_eq!(events.len(), 2);
        assert!(events[0].is_note_on);
        assert_eq!(events[0].pitch, 60);
        assert!(!events[1].is_note_on);
        assert_eq!(events[1].pitch, 60);
    }

    #[test]
    fn test_seek_backward_resets() {
        let mut sched = MidiScheduler::new();

        let tracks = vec![make_track("t1", 0)];
        let clips = vec![make_clip("c1", "t1", 0.0, 8.0)];
        let notes = vec![
            make_note("c1", 60, 100, 1.0, 0.5),
            make_note("c1", 64, 80, 3.0, 0.5),
        ];

        sched.load_from_sync(&clips, &notes, &tracks);

        // Play forward past both notes
        let _ = sched.schedule_for_buffer(0.0, 4.0, true);

        // Seek back to 0
        let events: Vec<_> = sched.schedule_for_buffer(0.0, 2.0, true).collect();
        // Should find note at beat 1.0 again
        assert!(events.iter().any(|e| e.pitch == 60 && e.is_note_on));
    }

    #[test]
    fn test_noteoff_before_noteon_at_same_beat() {
        let mut sched = MidiScheduler::new();

        let tracks = vec![make_track("t1", 0)];
        let clips = vec![make_clip("c1", "t1", 0.0, 4.0)];
        // Two notes: first ends at beat 2.0, second starts at beat 2.0
        let notes = vec![
            make_note("c1", 60, 100, 1.0, 1.0), // ends at 2.0
            make_note("c1", 64, 100, 2.0, 1.0), // starts at 2.0
        ];

        sched.load_from_sync(&clips, &notes, &tracks);

        let events: Vec<_> = sched.schedule_for_buffer(1.5, 2.5, true).collect();
        // At beat 2.0: NoteOff(60) should come before NoteOn(64)
        let at_2: Vec<_> = events.iter().filter(|e| (e.beat - 2.0).abs() < 0.001).collect();
        assert_eq!(at_2.len(), 2);
        assert!(!at_2[0].is_note_on); // NoteOff first
        assert!(at_2[1].is_note_on);  // NoteOn second
    }

    #[test]
    fn test_not_playing_returns_empty() {
        let mut sched = MidiScheduler::new();

        let tracks = vec![make_track("t1", 0)];
        let clips = vec![make_clip("c1", "t1", 0.0, 4.0)];
        let notes = vec![make_note("c1", 60, 100, 0.0, 1.0)];

        sched.load_from_sync(&clips, &notes, &tracks);

        let events: Vec<_> = sched.schedule_for_buffer(0.0, 1.0, false).collect();
        assert_eq!(events.len(), 0);
    }

    #[test]
    fn test_multi_track() {
        let mut sched = MidiScheduler::new();

        let tracks = vec![
            make_track("bass", 0),
            make_track("drums", 1),
        ];
        let clips = vec![
            make_clip("c_bass", "bass", 0.0, 4.0),
            make_clip("c_drums", "drums", 0.0, 4.0),
        ];
        let notes = vec![
            make_note("c_bass", 36, 100, 0.0, 1.0),  // bass note
            make_note("c_drums", 42, 80, 0.0, 0.25),  // hi-hat
            make_note("c_drums", 36, 120, 0.0, 0.5),  // kick
        ];

        sched.load_from_sync(&clips, &notes, &tracks);
        assert_eq!(sched.event_count(), 6); // 3 NoteOn + 3 NoteOff

        let events: Vec<_> = sched.schedule_for_buffer(0.0, 0.5, true).collect();
        // All NoteOns at beat 0 + hi-hat NoteOff at 0.25
        let note_ons: Vec<_> = events.iter().filter(|e| e.is_note_on).collect();
        assert_eq!(note_ons.len(), 3);
        // Track 0 (bass) and track 1 (drums) both have notes
        assert!(note_ons.iter().any(|e| e.track_index == 0));
        assert!(note_ons.iter().any(|e| e.track_index == 1));
    }
}
