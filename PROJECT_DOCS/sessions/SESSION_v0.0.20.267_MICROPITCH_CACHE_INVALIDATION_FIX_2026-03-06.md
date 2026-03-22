# Session v0.0.20.267

Issue: Micropitch became audible only after moving the note.

Root cause:
- arranger/audio MIDI content hashes did not include micropitch expression payload
- moving a note changed start/pitch and forced a rerender, but pure micropitch edits did not

Fix:
- include micropitch + expression curve types in MIDI content hashes
- harden GainFxWidget automation callback against deleted Qt widgets
