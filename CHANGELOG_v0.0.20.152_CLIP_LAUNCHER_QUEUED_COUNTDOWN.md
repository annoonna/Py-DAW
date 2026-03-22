# Changelog v0.0.20.152 — Clip Launcher Queued Countdown

## Added
- Bitwig/Ableton-style queued countdown in Clip Launcher slots:
  - Shows *when* a quantized launch will fire (e.g. `0.5 Bar` / `0.2 Beat`).
  - Rendered in the slot title row (right side), in the same yellow accent as the queued dashed border.
- Scene header queued countdown (right-aligned label).

## Implementation Notes
- UI-only feature: transport/launch timing logic is unchanged.
- Uses LauncherService `pending_snapshot()` metadata (`at_beat`, `quantize`) + TransportService `current_beat`.
- A lightweight QTimer (60ms) repaints the Clip Launcher only while pending launches exist.

## Files
- `pydaw/services/launcher_service.py`
- `pydaw/ui/clip_launcher.py`
