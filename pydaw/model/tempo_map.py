# -*- coding: utf-8 -*-
"""Tempo Map — Tempo automation over the timeline (AP3 Phase 3C).

v0.0.20.644: Tempo changes throughout the arrangement.

Stores a series of tempo events (beat → BPM) and provides:
- BPM at any beat position (interpolated or stepped)
- Beat → time (seconds) conversion accounting for tempo changes
- Time → beat conversion
- Integration with arrangement renderer for real-time clip stretching

Data format (stored in Project):
{
    "events": [
        {"beat": 0.0, "bpm": 120.0, "curve": "linear"},
        {"beat": 32.0, "bpm": 140.0, "curve": "step"},
        ...
    ],
    "global_bpm": 120.0  # fallback when no events exist
}
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TempoEvent:
    """A single tempo change point on the timeline."""
    beat: float = 0.0
    bpm: float = 120.0
    curve: str = "step"  # "step" = instant change, "linear" = ramp to next event

    def to_dict(self) -> dict:
        return {"beat": self.beat, "bpm": self.bpm, "curve": self.curve}

    @classmethod
    def from_dict(cls, d: dict) -> "TempoEvent":
        return cls(
            beat=float(d.get("beat", 0.0)),
            bpm=max(10.0, min(999.0, float(d.get("bpm", 120.0)))),
            curve=str(d.get("curve", "step")),
        )


class TempoMap:
    """Timeline tempo map with interpolation and beat↔time conversion.

    Thread-safe for reads (audio thread). Writes only from GUI thread.
    """

    def __init__(self, global_bpm: float = 120.0):
        self._global_bpm = max(10.0, float(global_bpm))
        self._events: List[TempoEvent] = []
        # Pre-computed beat→time lookup (invalidated on change)
        self._time_cache: List[Tuple[float, float]] = []  # (beat, time_seconds)
        self._cache_valid = False

    @property
    def global_bpm(self) -> float:
        return self._global_bpm

    @global_bpm.setter
    def global_bpm(self, bpm: float) -> None:
        self._global_bpm = max(10.0, float(bpm))
        self._cache_valid = False

    @property
    def events(self) -> List[TempoEvent]:
        return list(self._events)

    # --- Event management ---

    def add_event(self, beat: float, bpm: float, curve: str = "step") -> None:
        """Add or update a tempo event at the given beat."""
        bpm = max(10.0, min(999.0, float(bpm)))
        # Check if event already exists at this beat
        for e in self._events:
            if abs(e.beat - beat) < 0.001:
                e.bpm = bpm
                e.curve = curve
                self._cache_valid = False
                return
        self._events.append(TempoEvent(beat=beat, bpm=bpm, curve=curve))
        self._events.sort(key=lambda e: e.beat)
        self._cache_valid = False

    def remove_event(self, beat: float) -> bool:
        """Remove the tempo event nearest to the given beat (within 0.5 beats)."""
        best_idx = -1
        best_dist = 0.5
        for i, e in enumerate(self._events):
            d = abs(e.beat - beat)
            if d < best_dist:
                best_dist = d
                best_idx = i
        if best_idx >= 0:
            self._events.pop(best_idx)
            self._cache_valid = False
            return True
        return False

    def clear_events(self) -> None:
        """Remove all tempo events."""
        self._events.clear()
        self._cache_valid = False

    # --- Tempo query ---

    def bpm_at_beat(self, beat: float) -> float:
        """Get the BPM at a specific beat position.

        For "step" curves: returns the last event's BPM.
        For "linear" curves: linearly interpolates between events.
        """
        if not self._events:
            return self._global_bpm

        # Before first event
        if beat <= self._events[0].beat:
            return self._events[0].bpm

        # Find the segment
        for i in range(len(self._events) - 1):
            e0 = self._events[i]
            e1 = self._events[i + 1]
            if e0.beat <= beat < e1.beat:
                if e0.curve == "linear":
                    # Linearly interpolate BPM
                    span = e1.beat - e0.beat
                    if span > 0:
                        t = (beat - e0.beat) / span
                        return e0.bpm + t * (e1.bpm - e0.bpm)
                return e0.bpm  # step

        # After last event
        return self._events[-1].bpm

    # --- Beat ↔ Time conversion ---

    def beat_to_time(self, beat: float) -> float:
        """Convert a beat position to time in seconds, accounting for tempo changes.

        Uses numerical integration of 1/BPM over the beat range.
        """
        if not self._events:
            return beat * 60.0 / self._global_bpm

        time = 0.0
        current_beat = 0.0

        # Process each segment between tempo events
        all_beats = [e.beat for e in self._events]
        all_bpms = [e.bpm for e in self._events]
        all_curves = [e.curve for e in self._events]

        # Before first event
        if beat <= all_beats[0]:
            bpm0 = all_bpms[0]
            return beat * 60.0 / bpm0

        # Integrate through each segment
        for i in range(len(self._events)):
            seg_start = all_beats[i]
            if i + 1 < len(self._events):
                seg_end = min(beat, all_beats[i + 1])
            else:
                seg_end = beat

            if current_beat >= beat:
                break

            actual_start = max(seg_start, current_beat)
            actual_end = min(seg_end, beat)

            if actual_start >= actual_end:
                current_beat = seg_end
                continue

            duration_beats = actual_end - actual_start

            if all_curves[i] == "linear" and i + 1 < len(self._events):
                # Linear ramp: integrate 60/(BPM(b)) db
                bpm_start = all_bpms[i]
                bpm_end = all_bpms[i + 1]
                seg_span = all_beats[i + 1] - all_beats[i]
                if seg_span > 0 and abs(bpm_end - bpm_start) > 0.01:
                    # For linear BPM ramp: time = 60 * span * ln(bpm_end/bpm_start) / (bpm_end - bpm_start)
                    # Approximate: use midpoint BPM
                    t0 = (actual_start - seg_start) / seg_span
                    t1 = (actual_end - seg_start) / seg_span
                    bpm_a = bpm_start + t0 * (bpm_end - bpm_start)
                    bpm_b = bpm_start + t1 * (bpm_end - bpm_start)
                    avg_bpm = (bpm_a + bpm_b) * 0.5
                    time += duration_beats * 60.0 / max(10.0, avg_bpm)
                else:
                    time += duration_beats * 60.0 / max(10.0, all_bpms[i])
            else:
                # Step: constant BPM
                time += duration_beats * 60.0 / max(10.0, all_bpms[i])

            current_beat = actual_end

        # Any remaining beats after last event
        if current_beat < beat:
            remaining = beat - current_beat
            last_bpm = all_bpms[-1] if all_bpms else self._global_bpm
            time += remaining * 60.0 / max(10.0, last_bpm)

        return time

    def time_to_beat(self, time_seconds: float) -> float:
        """Convert time in seconds to beat position, accounting for tempo changes.

        Uses iterative binary search for accuracy.
        """
        if time_seconds <= 0.0:
            return 0.0

        if not self._events:
            return time_seconds * self._global_bpm / 60.0

        # Binary search: find beat where beat_to_time(beat) ≈ time_seconds
        lo = 0.0
        hi = time_seconds * 300.0 / 60.0  # max 300 BPM estimate
        for _ in range(50):  # converge in ~50 iterations
            mid = (lo + hi) * 0.5
            t = self.beat_to_time(mid)
            if t < time_seconds:
                lo = mid
            else:
                hi = mid
            if abs(t - time_seconds) < 0.0001:  # 0.1ms precision
                break
        return (lo + hi) * 0.5

    def tempo_ratio_at_beat(self, beat: float, project_bpm: float) -> float:
        """Get the tempo ratio at a beat relative to project BPM.

        Used by arrangement renderer for clip time-stretching.
        ratio > 1.0 → tempo is faster than project BPM → clips play faster
        ratio < 1.0 → tempo is slower → clips play slower

        Args:
            beat: Current beat position
            project_bpm: The project's base BPM

        Returns:
            Ratio: current_bpm / project_bpm
        """
        current_bpm = self.bpm_at_beat(beat)
        if project_bpm <= 0:
            return 1.0
        return current_bpm / project_bpm

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            "global_bpm": self._global_bpm,
            "events": [e.to_dict() for e in self._events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TempoMap":
        tm = cls(global_bpm=float(d.get("global_bpm", 120.0)))
        for ed in d.get("events", []):
            if isinstance(ed, dict):
                tm._events.append(TempoEvent.from_dict(ed))
        tm._events.sort(key=lambda e: e.beat)
        return tm

    def __repr__(self) -> str:
        return f"TempoMap(global_bpm={self._global_bpm}, events={len(self._events)})"
