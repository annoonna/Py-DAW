# Changelog v0.0.20.151 — Clip Launcher Queued-State Indicator

## Added
- Queued/Armed UI indicator for quantized clip launches (yellow dashed border + triangle outline).
- LauncherService pending launch visibility for UI: `pending_changed` signal + `pending_snapshot()`.
- Optional scene header queued styling (dashed yellow border).

## Notes
- UI-only change: does not alter launch timing or playback logic.
- Playing highlight (green/theme highlight) has priority over queued indicator.
