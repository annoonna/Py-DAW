# Session v0.0.20.42 — Live MIDI→Sampler Playback

## Summary
Made MIDI notes from Piano Roll trigger the Pro Audio Sampler during arrangement
playback. Previously, instrument tracks without SF2 were silently skipped.
Also fixed auto-sampler creation and added Pro-DAW-Style sample start position.

## Changes
1. **Real-time MIDI→Sampler**: PreparedMidiEvent scheduling in arrangement renderer
2. **Empty instrument tracks**: Removed auto-sampler creation on track select
3. **Sample start position**: Position slider now controls where notes begin in sample

## Testing
1. Create instrument track → Device panel shows empty (no auto-sampler)
2. Add Pro Audio Sampler via Browser → Instruments
3. Load a sample, set Position slider to middle
4. Draw MIDI notes in Piano Roll
5. Press Play → Notes should trigger sampler at the set position
6. Audio should be audible through VU meters and speakers

## Version
0.0.20.42
