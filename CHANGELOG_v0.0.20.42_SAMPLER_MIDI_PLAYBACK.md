# Changelog v0.0.20.42 — Live MIDI→Sampler Playback + Pro-DAW-Style Device Flow

## Priority 1: MIDI Notes Now Trigger Sampler During Playback

### Problem
Drawing notes in the Piano Roll on instrument tracks with the Pro Audio Sampler
produced no sound during arrangement playback. The MIDI rendering path required
a SoundFont (SF2) file and used FluidSynth for offline rendering — sampler-based
tracks were silently skipped.

### Root Cause
`prepare_clips()` in `arrangement_renderer.py` had a hard `if not sf2: continue`
that skipped ALL MIDI clips on tracks without SF2, with no fallback to the
sampler engine.

### Solution: Real-Time MIDI Event Scheduling
Instead of pre-rendering MIDI through FluidSynth, instrument tracks with a
sampler now receive **real-time MIDI events** during playback:

1. **`arrangement_renderer.py`**: New `PreparedMidiEvent` dataclass. `prepare_clips()`
   now creates `note_on`/`note_off` events for MIDI clips on instrument tracks
   without SF2, converting beat positions to absolute sample positions.

2. **`ArrangementState`**: Stores sorted MIDI events with a scan cursor.
   `get_pending_midi_events(frames)` returns events in the current audio block.

3. **`hybrid_engine.py`**: Both sounddevice and JACK paths process MIDI events
   BEFORE pull sources, triggering `sampler_registry.note_on()/note_off()`.
   This ensures the sampler receives notes before its `pull()` generates audio.

4. **`audio_engine.py`**: Sampler registry is wired from `main_window.py` →
   `AudioEngine._sampler_registry` → config → `HybridAudioCallback._sampler_registry`.

### Data Flow (New)
```
Piano Roll Notes → PreparedMidiEvent list (sorted by sample_pos)
                            ↓
Audio Callback Block → ArrangementState.get_pending_midi_events(frames)
                            ↓
                   SamplerRegistry.note_on(track_id, pitch, velocity)
                            ↓
                   ProSamplerEngine.trigger_note() → starts playing
                            ↓
                   ProSamplerEngine.pull(frames) → audio output
                            ↓
                   Mixed into master output via pull_sources
```

## Priority 2: Instrument Tracks Start Empty (Ableton/Pro-DAW Behavior)

### Problem
Every time an instrument track was selected, a Pro Audio Sampler was automatically
created — even for new empty tracks.

### Fix
Removed auto-creation in `main_window.py._on_track_selected()`. Instrument tracks
now start empty. Users add instruments explicitly via Browser → Instruments → 
'Add to Device'. The sampler registry registration is triggered when adding via browser.

## Bonus: Pro-DAW-Style Sample Start Position

### Problem
The Position slider in the sampler set the playback cursor directly, but
`trigger_note()` always reset position to 0.0 — notes always started from the
beginning regardless of Position slider setting.

### Fix
- New `start_position` field in `EngineState` (normalized 0.0–1.0)
- Position slider sets `start_position` instead of raw position
- `trigger_note()` uses `start_position` to compute starting sample index
- `toggle_play()` (PLAY button) also uses `start_position`
- Notes now play from the position set in the sampler UI

## Files Changed
- `pydaw/audio/arrangement_renderer.py` — PreparedMidiEvent, updated prepare_clips()
- `pydaw/audio/hybrid_engine.py` — MIDI event processing in both render paths
- `pydaw/audio/audio_engine.py` — sampler_registry wiring
- `pydaw/plugins/sampler/sampler_engine.py` — start_position support
- `pydaw/plugins/sampler/sampler_widget.py` — Position slider → start_position
- `pydaw/ui/main_window.py` — removed auto-sampler, registry on browser add
- `pydaw/version.py` / `VERSION` → 0.0.20.42
