from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject


def _interp(points: List[Dict[str, Any]], beat: float) -> Optional[float]:
    """Linear interpolation over automation points.

    Points are expected to be dicts with keys: "beat" (float) and "value" (float).
    Returns None if points is empty.
    """
    if not points:
        return None
    pts = sorted(
        (
            (float(p.get("beat", 0.0)), float(p.get("value", 0.0)))
            for p in points
            if p is not None
        ),
        key=lambda x: x[0],
    )
    if not pts:
        return None

    # Clamp before first / after last.
    if beat <= pts[0][0]:
        return pts[0][1]
    if beat >= pts[-1][0]:
        return pts[-1][1]

    # Find segment.
    for i in range(len(pts) - 1):
        b0, v0 = pts[i]
        b1, v1 = pts[i + 1]
        if b0 <= beat <= b1:
            if b1 == b0:
                return v1
            t = (beat - b0) / (b1 - b0)
            return v0 + t * (v1 - v0)
    return pts[-1][1]


@dataclass
class AutomationTargets:
    """Mapping from automation param -> setter conversion."""

    param: str
    # If True, lane values are [0..1] but track expects [-1..1].
    map_01_to_minus1_1: bool = False


class AutomationPlaybackService(QObject):
    """Applies automation lanes to track parameters during playback.

    This is intentionally conservative: it only runs when the transport is
    currently playing AND the track automation_mode is "read".
    """

    def __init__(self, project, transport) -> None:
        super().__init__()
        self.project = project
        self.transport = transport

        self._enabled = True
        self._targets = [
            AutomationTargets("volume", map_01_to_minus1_1=False),
            AutomationTargets("pan", map_01_to_minus1_1=True),
        ]

        self.transport.playhead_changed.connect(self._on_playhead)

        # TransportService exposes `playing_changed` (bool) in this code line.
        # Older revisions used `playing_state_changed`. Support both to avoid
        # hard crashes during early development.
        if hasattr(self.transport, "playing_changed"):
            self.transport.playing_changed.connect(self._on_playing)
        elif hasattr(self.transport, "playing_state_changed"):
            self.transport.playing_state_changed.connect(self._on_playing)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def _on_playing(self, is_playing: bool) -> None:
        # No-op for now; keep hook for future (arming, caching etc.).
        _ = is_playing

    def _on_playhead(self, beat: float) -> None:
        if not self._enabled:
            return
        if not getattr(self.transport, "playing", False):
            return
        proj = getattr(self.project, "project", None)
        if proj is None:
            return
        lanes = getattr(proj, "automation_lanes", None)
        if not isinstance(lanes, dict):
            return

        # Apply automation for each track.
        for track in getattr(proj, "tracks", []):
            # v0.0.20.432: Read automation for read, touch, and latch modes
            # (touch/latch = read + conditional write, but always read back)
            mode = getattr(track, "automation_mode", "off")
            if mode not in ("read", "touch", "latch"):
                continue
            tid = getattr(track, "id", "")
            if not tid:
                continue
            tlanes = lanes.get(tid) or {}
            if not isinstance(tlanes, dict):
                continue
            for tgt in self._targets:
                lane = tlanes.get(tgt.param)
                if not lane:
                    continue
                # v0.0.20.431: Handle BOTH legacy formats:
                # - flat list: [{beat, value}, ...]  (from MidiMappingService._write_automation_point)
                # - dict with points key: {points: [{beat, value}, ...]}  (from older import)
                points = None
                if isinstance(lane, list):
                    points = lane
                elif isinstance(lane, dict):
                    points = lane.get("points")
                if not isinstance(points, list) or not points:
                    continue
                v = _interp(points, float(beat))
                if v is None:
                    continue

                # Convert as needed.
                value = float(v)
                if tgt.map_01_to_minus1_1:
                    value = max(0.0, min(1.0, value)) * 2.0 - 1.0
                else:
                    value = max(0.0, min(1.0, value))

                # Apply without creating new automation points.
                try:
                    self.project.apply_automation_value(tid, tgt.param, value)
                except Exception:
                    # Keep playback robust: automation must never crash the UI.
                    continue

            # v0.0.20.528: Send automation — dynamic lanes with key "send:{fx_track_id}"
            for lane_key, lane in tlanes.items():
                if not isinstance(lane_key, str) or not lane_key.startswith("send:"):
                    continue
                points = None
                if isinstance(lane, list):
                    points = lane
                elif isinstance(lane, dict):
                    points = lane.get("points")
                if not isinstance(points, list) or not points:
                    continue
                v = _interp(points, float(beat))
                if v is None:
                    continue
                value = float(max(0.0, min(1.0, v)))
                try:
                    self.project.apply_automation_value(tid, lane_key, value)
                except Exception:
                    continue
