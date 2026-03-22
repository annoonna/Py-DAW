# v0.0.20.587 — Clip Launcher: MIDI Real-Time Playback + Creation (Bitwig/Ableton-Grade)

**Date:** 2026-03-18
**Author:** Claude Opus 4.6
**Priority:** HIGH — Core Feature Gap (MIDI clips non-functional in Clip Launcher)

## Problem

MIDI clips in the Clip Launcher were **completely non-functional** for all non-SF2 instruments:
- Pro Audio Sampler, Fusion, VST3, CLAP, Drum Machine: NO sound when launching MIDI clips
- Root cause: `_render_midi_clip_to_wav()` only worked for SF2 (FluidSynth offline render)
- No way to **create** MIDI clips directly in the Clip Launcher (only audio clips existed)
- No **visual feedback** for MIDI clips in slot buttons (only audio waveforms rendered)

## Solution: 3-Layer Architecture Fix

### 1. Real-Time MIDI Dispatch via SamplerRegistry (cliplauncher_playback.py)

**New architecture for MIDI clip playback:**
- SF2 instruments: continue using offline WAV render (cached, high quality)
- ALL other instruments (Sampler, Fusion, VST3, CLAP, Drum Machine):
  → Real-time MIDI dispatch via SamplerRegistry `note_on()`/`note_off()`
  → Same path as arranger playback (PreparedMidiEvent), but from Clip Launcher

**Key implementation details:**
- `_MidiNoteEvent` dataclass: lightweight MIDI note storage (no allocation on hot path)
- `_Voice.is_midi_realtime` flag: routes MIDI voices to dispatch instead of audio mix
- `_Voice.midi_notes`: pre-sorted note list for O(n) scheduling
- `_dispatch_midi_for_voice()`: loop-aware note scheduler with:
  - Correct note_on/note_off at loop wrap boundaries
  - Polyphonic tracking (active notes set per track)
  - Mute/Solo awareness via RT params
  - Clean all_notes_off on stop/loop-wrap (no hanging notes)
- Auto-detect plugin type from `instrument_state` keys (same logic as Bounce)

### 2. MIDI Clip Creation in Clip Launcher UI (clip_launcher.py)

**Bitwig/Ableton-style direct clip creation:**
- Right-click empty slot → "MIDI-Clip erstellen" / "Audio-Clip erstellen"
- Double-click empty slot → auto-creates MIDI clip (instrument track) or Audio clip
- Track type auto-detection: instrument tracks get MIDI, audio tracks get Audio
- 4-bar default length (matches Bitwig default)
- Immediate assignment to slot + editor activation

### 3. Mini Piano-Roll Visualization for MIDI Slots (clip_launcher.py)

**Bitwig-style note preview in slot buttons:**
- `_draw_midi_pianoroll()`: renders note bars with:
  - Pitch → vertical position (auto-scaled to note range, min 12 semitones)
  - Time → horizontal position (beat-mapped within clip length)
  - Velocity → opacity (40..230 alpha, higher velocity = brighter)
  - Per-clip color tinting (12-color palette matching Bitwig launcher)
  - Rounded note bars with minimum visible width (1.5px)
- Empty MIDI clips show "♪ MIDI" placeholder

## Files Changed

| File | Change |
|------|--------|
| `pydaw/services/cliplauncher_playback.py` | Real-time MIDI dispatch, _MidiNoteEvent, _extract_midi_notes, _dispatch_midi_for_voice, _stop_midi_voice, _all_midi_notes_off, enhanced stop_all/stop_slot |
| `pydaw/ui/clip_launcher.py` | _draw_midi_pianoroll, _create_launcher_midi_clip, _create_launcher_audio_clip, empty-slot double-click creation, context menu MIDI/Audio creation |
| `VERSION` | 0.0.20.586 → 0.0.20.587 |

## Safety

- **Nichts kaputt gemacht:** All existing audio clip playback paths unchanged
- SF2 MIDI render path preserved as-is
- All new code wrapped in try/except (no Qt fatal SIGABRT)
- MIDI note tracking with proper cleanup on stop/loop-wrap/panic
- No changes to arranger, piano roll, notation, mixer, or any other subsystem
