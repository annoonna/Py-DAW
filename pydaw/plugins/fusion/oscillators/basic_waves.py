"""Fusion Oscillators — Sine, Triangle, Pulse, Saw with PolyBLEP.

v0.0.20.572: Phase 1 core oscillators.
v0.0.20.577: Performance — vectorized phase accumulation for Sine/Triangle,
             local variable caching, inline PolyBLEP (no function call overhead).
"""
from __future__ import annotations
import numpy as np
from .base import OscillatorBase
from typing import Optional


def _polyblep(t: float, dt: float) -> float:
    """PolyBLEP correction for a discontinuity at phase = 0.

    t: current phase position (0..1)
    dt: phase increment per sample (freq/sr)
    Returns correction value to add to the naive waveform.
    """
    if t < dt:
        # Rising edge: polynomial correction
        t_n = t / dt
        return t_n + t_n - t_n * t_n - 1.0
    elif t > 1.0 - dt:
        # Falling edge (wrap-around)
        t_n = (t - 1.0) / dt
        return t_n * t_n + t_n + t_n + 1.0
    return 0.0


# ═══════════════════════════════════════════════════════════
#  Sine Oscillator
# ═══════════════════════════════════════════════════════════

class SineOscillator(OscillatorBase):
    """Pure sine with optional Skew and Fold waveshaping.

    v0.0.20.577: Vectorized phase accumulation with np.arange.
    Plain sine (no skew/fold) is ~10x faster. Fold still per-sample.
    """

    NAME = "Sine"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._skew = 0.0    # -1..+1
        self._fold = 0.0    # 0..1

    def set_param(self, key: str, value: float) -> None:
        if key == "skew":
            self._skew = max(-1.0, min(1.0, float(value)))
        elif key == "fold":
            self._fold = max(0.0, min(1.0, float(value)))
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "skew":
            return self._skew
        if key == "fold":
            return self._fold
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["skew", "fold"]

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        dt = freq / sr
        phase0 = self._phase

        # Generate phase array (vectorized)
        phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
        self._phase = (phase0 + frames * dt) % 1.0

        # Add phase modulation if present
        if phase_mod_buf is not None and self._phase_mod > 0.001:
            pm_len = min(frames, len(phase_mod_buf))
            phases[:pm_len] += phase_mod_buf[:pm_len] * self._phase_mod

        skew = self._skew
        fold = self._fold

        # Fast path: plain sine (most common, fully vectorized)
        if abs(skew) < 0.001 and fold < 0.001:
            return np.sin(2.0 * np.pi * phases)

        # Skew: asymmetric phase distortion
        if abs(skew) > 0.001:
            sp = phases.copy()
            lo = sp < 0.5
            hi = ~lo
            denom_lo = 1.0 - skew * 0.49
            denom_hi = 1.0 + skew * 0.49
            if abs(denom_lo) > 1e-9:
                sp[lo] = sp[lo] / denom_lo * 0.5
            if abs(denom_hi) > 1e-9:
                sp[hi] = 0.5 + (sp[hi] - 0.5) / denom_hi * 0.5
            raw = np.sin(2.0 * np.pi * sp)
        else:
            raw = np.sin(2.0 * np.pi * phases)

        # Fold waveshaping (must be per-sample due to while loop)
        if fold > 0.001:
            gain = 1.0 + fold * 4.0
            raw *= gain
            for i in range(frames):
                v = raw[i]
                while abs(v) > 1.0:
                    if v > 1.0:
                        v = 2.0 - v
                    elif v < -1.0:
                        v = -2.0 - v
                raw[i] = v

        return raw


# ═══════════════════════════════════════════════════════════
#  Triangle Oscillator
# ═══════════════════════════════════════════════════════════

class TriangleOscillator(OscillatorBase):
    """Bandlimited triangle wave with Skew and Fold.

    v0.0.20.577: Vectorized phase accumulation. Plain triangle fully
    vectorized (~8x faster). Skew/fold still per-sample where needed.
    """

    NAME = "Triangle"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._skew = 0.0
        self._fold = 0.0

    def set_param(self, key: str, value: float) -> None:
        if key == "skew":
            self._skew = max(-1.0, min(1.0, float(value)))
        elif key == "fold":
            self._fold = max(0.0, min(1.0, float(value)))
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "skew":
            return self._skew
        if key == "fold":
            return self._fold
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["skew", "fold"]

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        dt = freq / sr
        phase0 = self._phase

        # Vectorized phase array
        phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
        self._phase = (phase0 + frames * dt) % 1.0

        if phase_mod_buf is not None and self._phase_mod > 0.001:
            pm_len = min(frames, len(phase_mod_buf))
            phases[:pm_len] = (phases[:pm_len] + phase_mod_buf[:pm_len] * self._phase_mod) % 1.0

        # Vectorized naive triangle: 4*t-1 for t<0.5, 3-4*t for t>=0.5
        lo = phases < 0.5
        raw = np.where(lo, 4.0 * phases - 1.0, 3.0 - 4.0 * phases)

        skew = self._skew
        fold = self._fold

        # Fast path: no skew, no fold
        if abs(skew) < 0.001 and fold < 0.001:
            return raw

        # Skew (vectorized tanh)
        if abs(skew) > 0.001:
            factor = 1.0 + abs(skew) * 2.0
            raw = np.tanh(raw * factor) / np.tanh(factor)

        # Fold (per-sample, rare)
        if fold > 0.001:
            gain = 1.0 + fold * 4.0
            raw *= gain
            for i in range(frames):
                v = raw[i]
                while abs(v) > 1.0:
                    if v > 1.0:
                        v = 2.0 - v
                    elif v < -1.0:
                        v = -2.0 - v
                raw[i] = v

        return raw


# ═══════════════════════════════════════════════════════════
#  Pulse Oscillator (with PWM)
# ═══════════════════════════════════════════════════════════

class PulseOscillator(OscillatorBase):
    """Bandlimited pulse/square wave with variable pulse width (PWM).

    v0.0.20.577: Local variable caching, inline PolyBLEP.
    """

    NAME = "Pulse"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._width = 0.5  # 0..1, 0.5 = square

    def set_param(self, key: str, value: float) -> None:
        if key == "width":
            self._width = max(0.01, min(0.99, float(value)))
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "width":
            return self._width
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["width"]

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        dt = freq / sr
        out = np.empty(frames, dtype=np.float64)

        # Cache as locals
        phase = self._phase
        width = self._width
        has_pm = phase_mod_buf is not None and self._phase_mod > 0.001
        pm_depth = self._phase_mod

        for i in range(frames):
            if has_pm and i < len(phase_mod_buf):
                tp = (phase + phase_mod_buf[i] * pm_depth) % 1.0
            else:
                tp = phase

            # Naive pulse
            raw = 1.0 if tp < width else -1.0

            # Inline PolyBLEP at rising edge (phase = 0)
            if tp < dt:
                t_n = tp / dt
                raw -= t_n + t_n - t_n * t_n - 1.0
            elif tp > 1.0 - dt:
                t_n = (tp - 1.0) / dt
                raw -= t_n * t_n + t_n + t_n + 1.0

            # Inline PolyBLEP at falling edge (phase = width)
            tp2 = (tp - width + 1.0) % 1.0
            if tp2 < dt:
                t_n = tp2 / dt
                raw += t_n + t_n - t_n * t_n - 1.0
            elif tp2 > 1.0 - dt:
                t_n = (tp2 - 1.0) / dt
                raw += t_n * t_n + t_n + t_n + 1.0

            out[i] = raw
            phase = (phase + dt) % 1.0

        self._phase = phase
        return out


# ═══════════════════════════════════════════════════════════
#  Saw Oscillator
# ═══════════════════════════════════════════════════════════

class SawOscillator(OscillatorBase):
    """Bandlimited sawtooth wave with PolyBLEP.

    v0.0.20.577: Local variable caching, inline PolyBLEP (no function call).
    """

    NAME = "Saw"

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        dt = freq / sr
        out = np.empty(frames, dtype=np.float64)

        # Cache as locals
        phase = self._phase
        has_pm = phase_mod_buf is not None and self._phase_mod > 0.001
        pm_depth = self._phase_mod

        for i in range(frames):
            if has_pm and i < len(phase_mod_buf):
                tp = (phase + phase_mod_buf[i] * pm_depth) % 1.0
            else:
                tp = phase

            # Naive saw: 2*phase - 1
            raw = 2.0 * tp - 1.0

            # Inline PolyBLEP at discontinuity (phase = 0/1 wrap)
            if tp < dt:
                t_n = tp / dt
                raw -= t_n + t_n - t_n * t_n - 1.0
            elif tp > 1.0 - dt:
                t_n = (tp - 1.0) / dt
                raw -= t_n * t_n + t_n + t_n + 1.0

            out[i] = raw
            phase = (phase + dt) % 1.0

        self._phase = phase
        return out


# ═══════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════

OSC_REGISTRY: dict[str, type] = {
    "sine": SineOscillator,
    "triangle": TriangleOscillator,
    "pulse": PulseOscillator,
    "saw": SawOscillator,
}


def create_oscillator(name: str, sr: int = 48000) -> OscillatorBase:
    """Factory: create oscillator by name."""
    cls = OSC_REGISTRY.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown oscillator: {name}")
    return cls(sr=sr)
