# v0.0.20.588 — Clip Launcher: launcher_only Flag (Bitwig-Style Separation)

**Date:** 2026-03-18
**Author:** Claude Opus 4.6
**Priority:** HIGH — UX Bug (Launcher clips appeared in Arranger)

## Problem

MIDI/Audio clips created in the Clip Launcher appeared in the Arranger timeline,
which is wrong. In Bitwig Studio, Clip Launcher clips live ONLY in the launcher
until the user explicitly drags them into the Arranger.

## Root Cause

The `_create_launcher_midi_clip()` and `_create_launcher_audio_clip()` methods
did not set `clip.launcher_only = True` on newly created clips. The field already
existed in the Clip model (line 164) and the Arranger UI already filtered it
(line 874: `_arranger_clips()`), but the audio renderer (`arrangement_renderer.py`)
did NOT filter it — causing launcher-only clips to also play during arranger playback.

## Fix (3 files)

| File | Change |
|------|--------|
| `pydaw/ui/clip_launcher.py` | Set `launcher_only = True` on clips created via `_create_launcher_midi_clip()` and `_create_launcher_audio_clip()` |
| `pydaw/audio/arrangement_renderer.py` | Skip `launcher_only` clips in `prepare_clips()` loop (audio playback) |
| `VERSION` | 0.0.20.587 → 0.0.20.588 |

## Safety

- Arranger UI already filtered `launcher_only` via `_arranger_clips()` — no change needed
- Clip model + serialization already supports `launcher_only: bool = False` — no schema change
- arrangement_renderer.py: single `if getattr(clip, 'launcher_only', False): continue` guard
- ClipLauncherPlaybackService handles launcher-only clips independently (no conflict)
