# Changelog v0.0.20.150 — Clip Launcher Play-State Indicator

## Added
- Clip Launcher Slot-Zellen zeigen jetzt einen **Play-State Indicator** (UI-only):
  - Highlight-Rahmen (Theme Highlight)
  - kleines ▶ Symbol oben links

## Changed
- ClipLauncherPlaybackService:
  - `active_slots_changed` Signal + `active_slots()` Snapshot
  - emit nach Launch/Stop
- ProjectService:
  - `cliplauncher_active_slots_changed` Signal (UI)
  - `cliplauncher_active_slots()` helper
  - forward connect zum Playback-Signal

## Fixed
- Scene Launch im Playback-Service nutzt jetzt konsistent `scene:<idx>:track:<id>`

## Notes
- Keine Änderung am Projektformat.
- Keine Audio-Engine Umbauten (safe).
