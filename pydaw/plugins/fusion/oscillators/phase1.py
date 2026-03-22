"""Fusion Oscillator — Phase-1 (Phase Distortion with 5 algorithms).

v0.0.20.573: Phase 2 — Casio CZ-style phase distortion synthesis.

Each algorithm distorts the linear phase ramp before feeding it to sin(),
producing different harmonic spectra from a single parameter sweep.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Optional
from .base import OscillatorBase


class Phase1Oscillator(OscillatorBase):
    """Phase distortion oscillator with 5 algorithms + feedback."""

    NAME = "Phase-1"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._algorithm = 0      # 0-4
        self._amount = 0.5       # 0..1
        self._feedback = 0.0     # 0..1
        self._formant = False
        self._prev_output = 0.0  # for feedback

    def set_param(self, key: str, value: float) -> None:
        if key == "algorithm":
            self._algorithm = int(round(float(value))) % 5
        elif key == "amount":
            self._amount = max(0.0, min(1.0, float(value)))
        elif key == "feedback":
            self._feedback = max(0.0, min(1.0, float(value)))
        elif key == "formant":
            self._formant = bool(float(value) > 0.5)
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "algorithm":
            return float(self._algorithm)
        if key == "amount":
            return self._amount
        if key == "feedback":
            return self._feedback
        if key == "formant":
            return 1.0 if self._formant else 0.0
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["algorithm", "amount", "feedback", "formant"]

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Local variable caching, inline phase distortion."""
        dt = freq / sr
        out = np.empty(frames, dtype=np.float64)
        algo = self._algorithm
        amt = self._amount
        fb = self._feedback
        formant = self._formant
        TWO_PI = 2.0 * math.pi
        _sin = math.sin
        _pi = math.pi
        a = amt * 0.95

        # Cache as locals
        phase = self._phase
        prev_out = self._prev_output
        has_pm = phase_mod_buf is not None and self._phase_mod > 0.001
        pm_depth = self._phase_mod

        for i in range(frames):
            fb_offset = prev_out * fb * 0.3

            if has_pm and i < len(phase_mod_buf):
                lp = (phase + phase_mod_buf[i] * pm_depth + fb_offset) % 1.0
            else:
                lp = (phase + fb_offset) % 1.0

            # Inline phase distortion (avoid method call overhead)
            if algo == 0:
                if lp < 0.5:
                    dp = lp * (1.0 + a)
                else:
                    dp = 0.5 * (1.0 + a) + (lp - 0.5) * (1.0 - a) if (1.0 - a) > 0 else 0.5
            elif algo == 1:
                bp = 0.5 - a * 0.45
                if bp < 0.01:
                    bp = 0.01
                if lp < bp:
                    dp = lp / bp * 0.5
                else:
                    dp = 0.5 + (lp - bp) / (1.0 - bp) * 0.5
            elif algo == 2:
                if lp < 0.5:
                    dp = lp + a * 0.5 * _sin(_pi * lp * 2.0)
                else:
                    dp = lp
            elif algo == 3:
                dp = (lp * (1.0 + a * 4.0)) % 2.0
                if dp > 1.0:
                    dp = 2.0 - dp
            elif algo == 4:
                dp = (lp * (1.0 + a * 7.0)) % 1.0
            else:
                dp = lp

            if formant:
                dp = (dp * (1.0 + amt * 3.0)) % 1.0

            sample = _sin(TWO_PI * dp)
            prev_out = sample
            out[i] = sample

            phase = (phase + dt) % 1.0

        self._phase = phase
        self._prev_output = prev_out
        return out

    @staticmethod
    def _distort_phase(p: float, amount: float, algo: int) -> float:
        """Apply phase distortion algorithm.

        p: input phase 0..1
        amount: distortion depth 0..1
        Returns: distorted phase 0..1
        """
        a = amount * 0.95  # prevent division by zero at extremes

        if algo == 0:
            # Saw-like PD: compress first half, stretch second
            if p < 0.5:
                return p * (1.0 + a) if (1.0 + a) > 0 else p
            else:
                return 0.5 * (1.0 + a) + (p - 0.5) * (1.0 - a) if (1.0 - a) > 0 else 0.5

        elif algo == 1:
            # Resonant PD: sharp peak creates resonant-like harmonics
            bp = 0.5 - a * 0.45  # breakpoint shifts with amount
            if bp < 0.01:
                bp = 0.01
            if p < bp:
                return p / bp * 0.5
            else:
                return 0.5 + (p - bp) / (1.0 - bp) * 0.5

        elif algo == 2:
            # Pulse PD: phase jump creates pulse-like waveform
            jump = a * 0.5
            if p < 0.5:
                return p + jump * math.sin(math.pi * p * 2.0)
            else:
                return p

        elif algo == 3:
            # Metal PD: multiple phase folds for metallic harmonics
            folds = 1.0 + a * 4.0
            dp = p * folds
            # Triangle fold
            dp = dp % 2.0
            if dp > 1.0:
                dp = 2.0 - dp
            return dp

        elif algo == 4:
            # Formant PD: phase scaling for vocal-like formants
            scale = 1.0 + a * 7.0
            return (p * scale) % 1.0

        return p
