"""Fusion Oscillator — Union (3-wave crossfade blend).

v0.0.20.573: Phase 2 extended oscillators.

Union blends three waveforms with a single Shape control:
  Left (-1): Pulse +1 octave
  Center (0): Sawtooth
  Right (+1): Saw +1 octave
Plus a Sub pulse oscillator one octave down.
"""
from __future__ import annotations
import numpy as np
from typing import Optional
from .base import OscillatorBase
from .basic_waves import _polyblep


class UnionOscillator(OscillatorBase):
    """Three-wave blend oscillator with sub."""

    NAME = "Union"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._shape = 0.0       # -1..+1
        self._sub_width = 0.5   # pulse width for sub
        self._sub_level = 0.0   # 0..1
        self._phase_hi = 0.0    # phase for +1oct oscillator
        self._phase_sub = 0.0   # phase for sub oscillator

    def set_param(self, key: str, value: float) -> None:
        if key == "shape":
            self._shape = max(-1.0, min(1.0, float(value)))
        elif key == "sub_width":
            self._sub_width = max(0.01, min(0.99, float(value)))
        elif key == "sub_level":
            self._sub_level = max(0.0, min(1.0, float(value)))
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "shape":
            return self._shape
        if key == "sub_width":
            return self._sub_width
        if key == "sub_level":
            return self._sub_level
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["shape", "sub_width", "sub_level"]

    def reset_phase(self) -> None:
        super().reset_phase()
        self._phase_hi = 0.0
        self._phase_sub = 0.0

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Local variable caching, inline PolyBLEP."""
        dt = freq / sr
        dt_hi = freq * 2.0 / sr       # +1 octave
        dt_sub = freq * 0.5 / sr       # -1 octave
        out = np.empty(frames, dtype=np.float64)

        # Cache as locals
        shape = self._shape
        sub_level = self._sub_level
        sub_width = self._sub_width
        phase = self._phase
        phase_hi = self._phase_hi
        phase_sub = self._phase_sub
        has_sub = sub_level > 0.001

        for i in range(frames):
            p = phase
            p_hi = phase_hi

            # Main saw (center) + inline PolyBLEP
            saw_main = 2.0 * p - 1.0
            if p < dt:
                t_n = p / dt
                saw_main -= t_n + t_n - t_n * t_n - 1.0
            elif p > 1.0 - dt:
                t_n = (p - 1.0) / dt
                saw_main -= t_n * t_n + t_n + t_n + 1.0

            if shape < 0:
                blend = -shape
                pw = 0.5
                pulse_hi = 1.0 if p_hi < pw else -1.0
                # PolyBLEP at rising edge
                if p_hi < dt_hi:
                    t_n = p_hi / dt_hi
                    pulse_hi -= t_n + t_n - t_n * t_n - 1.0
                elif p_hi > 1.0 - dt_hi:
                    t_n = (p_hi - 1.0) / dt_hi
                    pulse_hi -= t_n * t_n + t_n + t_n + 1.0
                # PolyBLEP at falling edge
                tp2 = (p_hi - pw + 1.0) % 1.0
                if tp2 < dt_hi:
                    t_n = tp2 / dt_hi
                    pulse_hi += t_n + t_n - t_n * t_n - 1.0
                elif tp2 > 1.0 - dt_hi:
                    t_n = (tp2 - 1.0) / dt_hi
                    pulse_hi += t_n * t_n + t_n + t_n + 1.0
                sample = saw_main * (1.0 - blend) + pulse_hi * blend
            else:
                blend = shape
                saw_hi = 2.0 * p_hi - 1.0
                if p_hi < dt_hi:
                    t_n = p_hi / dt_hi
                    saw_hi -= t_n + t_n - t_n * t_n - 1.0
                elif p_hi > 1.0 - dt_hi:
                    t_n = (p_hi - 1.0) / dt_hi
                    saw_hi -= t_n * t_n + t_n + t_n + 1.0
                sample = saw_main * (1.0 - blend) + saw_hi * blend

            if has_sub:
                p_s = phase_sub
                w = sub_width
                sub = 1.0 if p_s < w else -1.0
                if p_s < dt_sub:
                    t_n = p_s / dt_sub
                    sub -= t_n + t_n - t_n * t_n - 1.0
                elif p_s > 1.0 - dt_sub:
                    t_n = (p_s - 1.0) / dt_sub
                    sub -= t_n * t_n + t_n + t_n + 1.0
                tp2 = (p_s - w + 1.0) % 1.0
                if tp2 < dt_sub:
                    t_n = tp2 / dt_sub
                    sub += t_n + t_n - t_n * t_n - 1.0
                elif tp2 > 1.0 - dt_sub:
                    t_n = (tp2 - 1.0) / dt_sub
                    sub += t_n * t_n + t_n + t_n + 1.0
                sample += sub * sub_level

            out[i] = sample

            phase = (phase + dt) % 1.0
            phase_hi = (phase_hi + dt_hi) % 1.0
            phase_sub = (phase_sub + dt_sub) % 1.0

        self._phase = phase
        self._phase_hi = phase_hi
        self._phase_sub = phase_sub
        return out
