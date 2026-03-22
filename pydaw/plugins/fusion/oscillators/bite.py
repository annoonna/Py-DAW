"""Fusion Oscillator — Bite (dual oscillator with FM, Sync, PWM, Ring Mod).

v0.0.20.573: Phase 2 — Techniques-driven dual oscillator.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Optional
from .base import OscillatorBase
from .basic_waves import _polyblep

_WAVE_FUNCS = {
    0: lambda p: math.sin(2.0 * math.pi * p),                          # sine
    1: lambda p: (4.0 * p - 1.0 if p < 0.5 else 3.0 - 4.0 * p),     # triangle
    2: lambda p: 2.0 * p - 1.0,                                        # saw (naive)
    3: lambda p: (1.0 if p < 0.5 else -1.0),                          # pulse
}


class BiteOscillator(OscillatorBase):
    """Dual oscillator with Exp-FM, Hard Sync, PWM, Ring Mod."""

    NAME = "Bite"
    MODE_FM = 0
    MODE_SYNC = 1
    MODE_PWM = 2
    MODE_RING = 3

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._wave_a = 2      # 0=sine,1=tri,2=saw,3=pulse
        self._wave_b = 0
        self._width_a = 0.5
        self._width_b = 0.5
        self._ratio_b = 1.0   # 0.5..16
        self._mode = 0        # FM/Sync/PWM/Ring
        self._mix_a = 1.0
        self._mix_b = 0.0
        self._mix_rm = 0.0

        self._phase_a = 0.0
        self._phase_b = 0.0

    def set_param(self, key: str, value: float) -> None:
        if key == "wave_a":
            self._wave_a = int(round(float(value))) % 4
        elif key == "wave_b":
            self._wave_b = int(round(float(value))) % 4
        elif key == "width_a":
            self._width_a = max(0.01, min(0.99, float(value)))
        elif key == "width_b":
            self._width_b = max(0.01, min(0.99, float(value)))
        elif key == "ratio_b":
            self._ratio_b = max(0.5, min(16.0, float(value)))
        elif key == "mode":
            self._mode = int(round(float(value))) % 4
        elif key == "mix_a":
            self._mix_a = max(0.0, min(1.0, float(value)))
        elif key == "mix_b":
            self._mix_b = max(0.0, min(1.0, float(value)))
        elif key == "mix_rm":
            self._mix_rm = max(0.0, min(1.0, float(value)))
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key in ("wave_a", "wave_b", "width_a", "width_b", "ratio_b",
                    "mode", "mix_a", "mix_b", "mix_rm"):
            return getattr(self, f"_{key}", 0.0)
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["wave_a", "wave_b", "width_a", "width_b",
                "ratio_b", "mode", "mix_a", "mix_b", "mix_rm"]

    def reset_phase(self) -> None:
        super().reset_phase()
        self._phase_a = 0.0
        self._phase_b = 0.0

    def _wave_sample(self, wave_id: int, phase: float, width: float) -> float:
        if wave_id == 3:  # pulse with variable width
            return 1.0 if phase < width else -1.0
        return _WAVE_FUNCS.get(wave_id, _WAVE_FUNCS[0])(phase)

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Local variable caching, inline wave generation."""
        freq_a = freq
        freq_b = freq * self._ratio_b
        dt_a = freq_a / sr
        dt_b = freq_b / sr
        out = np.empty(frames, dtype=np.float64)
        TWO_PI = 2.0 * math.pi
        _sin = math.sin

        # Cache all as locals
        mode = self._mode
        wave_a = self._wave_a
        wave_b = self._wave_b
        width_a = self._width_a
        width_b = self._width_b
        mix_a = self._mix_a
        mix_b = self._mix_b
        mix_rm = self._mix_rm
        has_rm = mix_rm > 0.001
        phase_a = self._phase_a
        phase_b = self._phase_b

        # Inline wave function (avoids dict lookup + lambda call per sample)
        def _ws(wid, p, w):
            if wid == 0:
                return _sin(TWO_PI * p)
            elif wid == 1:
                return 4.0 * p - 1.0 if p < 0.5 else 3.0 - 4.0 * p
            elif wid == 2:
                return 2.0 * p - 1.0
            else:
                return 1.0 if p < w else -1.0

        if mode == 0:  # FM
            for i in range(frames):
                osc_b = _ws(wave_b, phase_b, width_b)
                fm_mod = 2.0 ** (osc_b * mix_b * 2.0)
                osc_a = _ws(wave_a, phase_a, width_a)
                phase_a = (phase_a + dt_a * fm_mod) % 1.0
                sample = osc_a * mix_a + osc_b * mix_b
                if has_rm:
                    sample += osc_a * osc_b * mix_rm
                out[i] = sample
                phase_b = (phase_b + dt_b) % 1.0
        elif mode == 1:  # SYNC
            for i in range(frames):
                osc_b = _ws(wave_b, phase_b, width_b)
                new_phase_b = (phase_b + dt_b) % 1.0
                if new_phase_b < phase_b:
                    phase_a = 0.0
                osc_a = _ws(wave_a, phase_a, width_a)
                phase_a = (phase_a + dt_a) % 1.0
                sample = osc_a * mix_a + osc_b * mix_b
                if has_rm:
                    sample += osc_a * osc_b * mix_rm
                out[i] = sample
                phase_b = new_phase_b
        elif mode == 2:  # PWM
            for i in range(frames):
                osc_b = _ws(wave_b, phase_b, width_b)
                mw = width_a + osc_b * mix_b * 0.4
                if mw < 0.05:
                    mw = 0.05
                elif mw > 0.95:
                    mw = 0.95
                osc_a = _ws(wave_a, phase_a, mw)
                phase_a = (phase_a + dt_a) % 1.0
                sample = osc_a * mix_a + osc_b * mix_b
                if has_rm:
                    sample += osc_a * osc_b * mix_rm
                out[i] = sample
                phase_b = (phase_b + dt_b) % 1.0
        else:  # RING
            for i in range(frames):
                osc_a = _ws(wave_a, phase_a, width_a)
                osc_b = _ws(wave_b, phase_b, width_b)
                phase_a = (phase_a + dt_a) % 1.0
                sample = osc_a * mix_a + osc_b * mix_b
                if has_rm:
                    sample += osc_a * osc_b * mix_rm
                out[i] = sample
                phase_b = (phase_b + dt_b) % 1.0

        self._phase_a = phase_a
        self._phase_b = phase_b
        return out
