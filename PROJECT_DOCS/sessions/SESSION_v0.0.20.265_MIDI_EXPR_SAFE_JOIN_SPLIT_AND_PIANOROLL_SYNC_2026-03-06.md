# Session v0.0.20.265 — Safe MIDI Expression Preserve + PianoRoll Sync Fix

## Anlass
User reported three linked problems:
- confusion/mismatch around clip position vs PianoRoll/editor playback line
- note-expression target reacts late in UI / zoom lane feels stale
- consolidate/join/split MIDI paths can lose drawn micropitch / note-expression data

## Umsetzung
1. Fixed PianoRoll clip meta lookup (`id` instead of wrong `clip_id`) so local playhead/clip geometry stay aligned with the selected clip.
2. Added a tiny UI-only target poll in `NoteExpressionLane` so focus/selection/hover changes repaint quickly, also for the zoom dialog.
3. Replaced bare-note reconstruction in MIDI join/split paths with deep-copy based note preservation.
   This keeps expressions, expression curve types and notation metadata.

## Safety
- No DSP/audio-engine changes.
- No changes to FX automation logic.
- No change to note-expression evaluation math.
