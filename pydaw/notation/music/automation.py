
# ChronoScaleStudio – Automation (z.B. Lautstärke)
# Punkte in Beats, lineare Interpolation.

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class AutomationPoint:
    beat: float
    value: float   # 0.0–1.0


class AutomationLane:
    def __init__(self, name: str, default: float = 1.0):
        self.name = str(name)
        self.default = float(default)
        self.points: List[AutomationPoint] = []

    def set_points(self, points: List[Tuple[float, float]]):
        self.points = [AutomationPoint(float(b), float(v)) for b, v in points]
        self.points.sort(key=lambda p: p.beat)

    def get_points(self) -> List[AutomationPoint]:
        return list(self.points)

    def value_at(self, beat: float) -> float:
        beat = float(beat)
        if not self.points:
            return self.default

        pts = self.points
        if beat <= pts[0].beat:
            return pts[0].value
        if beat >= pts[-1].beat:
            return pts[-1].value

        # lineare Interpolation
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if a.beat <= beat <= b.beat:
                if b.beat == a.beat:
                    return b.value
                t = (beat - a.beat) / (b.beat - a.beat)
                return a.value + t * (b.value - a.value)

        return self.default

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "default": float(self.default),
            "points": [{"beat": float(p.beat), "value": float(p.value)} for p in self.points],
        }

    @staticmethod
    def from_dict(data: dict) -> "AutomationLane":
        lane = AutomationLane(name=str(data.get("name", "automation")), default=float(data.get("default", 1.0)))
        pts = []
        for p in data.get("points", []) or []:
            try:
                pts.append((float(p.get("beat", 0.0)), float(p.get("value", 1.0))))
            except Exception:
                pass
        lane.set_points(pts)
        return lane
