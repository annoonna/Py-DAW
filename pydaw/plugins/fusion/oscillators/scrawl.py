"""Fusion Oscillator — Scrawl (freely drawable segmented oscillator).

v0.0.20.576: Draw your own waveforms with a pen tool.

The waveform is defined by control points connected by linear or
smooth (cubic) interpolation. The editor widget provides:
  - Click to add/move points
  - Drag to draw freehand
  - Right-click to delete points
  - Preset shapes (Sine, Saw, Square, Triangle, Random)
  - Smooth toggle for cubic interpolation
  - Anti-aliased playback
"""
from __future__ import annotations
import math
import numpy as np
from typing import Optional
from .base import OscillatorBase


class ScrawlOscillator(OscillatorBase):
    """Freely drawable oscillator with segmented waveform."""

    NAME = "Scrawl"
    TABLE_SIZE = 2048  # Internal lookup table resolution

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._smooth = True        # cubic vs linear interpolation
        self._antialiasing = True

        # Control points: list of (x, y) where x=0..1, y=-1..+1
        self._points: list[tuple[float, float]] = []

        # Rendered lookup table (regenerated when points change)
        self._table = np.zeros(self.TABLE_SIZE, dtype=np.float64)

        # Initialize with sine shape
        self.set_shape_sine()

    # ── Parameters ──

    def set_param(self, key: str, value: float) -> None:
        if key == "smooth":
            self._smooth = bool(float(value) > 0.5)
            self._rebuild_table()
        elif key == "antialiasing":
            self._antialiasing = bool(float(value) > 0.5)
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "smooth":
            return 1.0 if self._smooth else 0.0
        if key == "antialiasing":
            return 1.0 if self._antialiasing else 0.0
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["smooth", "antialiasing"]

    # ── Point Editing API ──

    def get_points(self) -> list[tuple[float, float]]:
        """Return current control points (for UI display)."""
        return list(self._points)

    def set_points(self, points: list[tuple[float, float]]) -> None:
        """Set control points and rebuild table."""
        self._points = sorted(points, key=lambda p: p[0])
        # Ensure start (0) and end (1) exist
        if not self._points or self._points[0][0] > 0.01:
            self._points.insert(0, (0.0, self._points[0][1] if self._points else 0.0))
        if self._points[-1][0] < 0.99:
            self._points.append((1.0, self._points[0][1]))  # Loop: end = start
        self._rebuild_table()

    def add_point(self, x: float, y: float) -> None:
        """Add a control point and rebuild."""
        x = max(0.0, min(1.0, float(x)))
        y = max(-1.0, min(1.0, float(y)))
        self._points.append((x, y))
        self._points.sort(key=lambda p: p[0])
        self._rebuild_table()

    def remove_point_near(self, x: float, threshold: float = 0.02) -> bool:
        """Remove point nearest to x (if within threshold). Returns True if removed."""
        if len(self._points) <= 2:
            return False  # Need at least 2 points
        best_idx = -1
        best_dist = float('inf')
        for i, (px, py) in enumerate(self._points):
            d = abs(px - x)
            if d < best_dist and d < threshold:
                # Don't remove first/last anchor
                if i > 0 and i < len(self._points) - 1:
                    best_idx = i
                    best_dist = d
        if best_idx >= 0:
            self._points.pop(best_idx)
            self._rebuild_table()
            return True
        return False

    def set_freehand(self, samples: list[float]) -> None:
        """Set waveform from freehand drawing (evenly spaced Y values -1..+1).

        Converts to control points by downsampling to ~32-64 points.
        """
        if not samples or len(samples) < 2:
            return
        # Downsample to manageable number of points
        n_target = min(64, max(8, len(samples) // 4))
        step = max(1, len(samples) // n_target)
        pts = []
        for i in range(0, len(samples), step):
            x = i / (len(samples) - 1)
            y = max(-1.0, min(1.0, float(samples[i])))
            pts.append((x, y))
        # Ensure loop closure
        if pts and abs(pts[0][1] - pts[-1][1]) > 0.01:
            pts[-1] = (1.0, pts[0][1])
        self.set_points(pts)

    # ── Preset Shapes ──

    def set_shape_sine(self) -> None:
        n = 32
        pts = []
        for i in range(n):
            x = i / (n - 1)
            y = math.sin(2.0 * math.pi * x)
            pts.append((x, y))
        self._points = pts
        self._rebuild_table()

    def set_shape_saw(self) -> None:
        self._points = [(0.0, -1.0), (0.99, 1.0), (1.0, -1.0)]
        self._rebuild_table()

    def set_shape_square(self) -> None:
        self._points = [
            (0.0, 1.0), (0.49, 1.0), (0.5, -1.0), (0.99, -1.0), (1.0, 1.0)
        ]
        self._rebuild_table()

    def set_shape_triangle(self) -> None:
        self._points = [(0.0, 0.0), (0.25, 1.0), (0.5, 0.0), (0.75, -1.0), (1.0, 0.0)]
        self._rebuild_table()

    def set_shape_random(self) -> None:
        n = 16
        pts = [(0.0, 0.0)]
        for i in range(1, n - 1):
            x = i / (n - 1)
            y = float(np.random.uniform(-1.0, 1.0))
            pts.append((x, y))
        pts.append((1.0, pts[0][1]))
        self._points = pts
        self._rebuild_table()

    # ── Table Building ──

    def _rebuild_table(self) -> None:
        """Regenerate the lookup table from control points."""
        size = self.TABLE_SIZE
        table = np.zeros(size, dtype=np.float64)

        if len(self._points) < 2:
            self._table = table
            return

        pts = self._points

        if self._smooth and len(pts) >= 4:
            # Cubic (Catmull-Rom) interpolation
            table = self._interpolate_cubic(pts, size)
        else:
            # Linear interpolation
            table = self._interpolate_linear(pts, size)

        # Clamp to -1..+1
        table = np.clip(table, -1.0, 1.0)
        self._table = table

    @staticmethod
    def _interpolate_linear(pts: list[tuple[float, float]], size: int) -> np.ndarray:
        table = np.zeros(size, dtype=np.float64)
        for i in range(size):
            x = i / size
            # Find surrounding points
            lo_idx = 0
            for j in range(len(pts) - 1):
                if pts[j + 1][0] >= x:
                    lo_idx = j
                    break
            x0, y0 = pts[lo_idx]
            x1, y1 = pts[min(lo_idx + 1, len(pts) - 1)]
            if abs(x1 - x0) < 1e-10:
                table[i] = y0
            else:
                t = (x - x0) / (x1 - x0)
                table[i] = y0 + (y1 - y0) * t
        return table

    @staticmethod
    def _interpolate_cubic(pts: list[tuple[float, float]], size: int) -> np.ndarray:
        """Catmull-Rom spline interpolation."""
        table = np.zeros(size, dtype=np.float64)
        n = len(pts)

        for i in range(size):
            x = i / size
            # Find segment
            seg = 0
            for j in range(n - 1):
                if pts[j + 1][0] >= x:
                    seg = j
                    break

            # 4 control points (clamped at boundaries)
            p0 = pts[max(0, seg - 1)]
            p1 = pts[seg]
            p2 = pts[min(seg + 1, n - 1)]
            p3 = pts[min(seg + 2, n - 1)]

            if abs(p2[0] - p1[0]) < 1e-10:
                table[i] = p1[1]
                continue

            t = (x - p1[0]) / (p2[0] - p1[0])
            t2 = t * t
            t3 = t2 * t

            # Catmull-Rom coefficients
            table[i] = 0.5 * (
                (2.0 * p1[1]) +
                (-p0[1] + p2[1]) * t +
                (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2 +
                (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
            )

        return table

    # ── Rendering ──

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Vectorized table lookup — no per-sample Python loop."""
        dt = freq / sr
        size = self.TABLE_SIZE
        phase0 = self._phase

        # Vectorized phase array
        phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
        self._phase = (phase0 + frames * dt) % 1.0

        if phase_mod_buf is not None and self._phase_mod > 0.001:
            pm_len = min(frames, len(phase_mod_buf))
            phases[:pm_len] = (phases[:pm_len] + phase_mod_buf[:pm_len] * self._phase_mod) % 1.0

        # Vectorized table lookup with linear interpolation
        pos = phases * size
        idx_lo = pos.astype(np.intp) % size
        idx_hi = (idx_lo + 1) % size
        frac = pos - np.floor(pos)
        tbl = self._table
        return tbl[idx_lo] * (1.0 - frac) + tbl[idx_hi] * frac

    def get_table_for_display(self, resolution: int = 256) -> np.ndarray:
        """Return downsampled table data for UI waveform display."""
        if resolution >= self.TABLE_SIZE:
            return self._table.copy()
        step = max(1, self.TABLE_SIZE // resolution)
        return self._table[::step].copy()
