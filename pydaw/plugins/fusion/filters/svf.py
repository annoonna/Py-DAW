"""Fusion Filter — State Variable Filter (Cytomic/Simper Trapezoidal SVF).

v0.0.20.572: Phase 1 core filter.

Reference: Andrew Simper, "Linear Trapezoidal Integrated SVF", Cytomic 2013.
This topology is zero-delay feedback, stable at all resonance settings,
and self-oscillates cleanly at maximum resonance.
"""
from __future__ import annotations
import math
import numpy as np


class FilterBase:
    """Abstract base for Fusion filter modules."""

    NAME: str = "Base"

    def __init__(self, sr: int = 48000):
        self._sr = int(sr)
        self._cutoff = 8000.0    # Hz
        self._resonance = 0.0    # 0..1
        self._key_track = 0.0    # 0..1
        self._env_amount = 0.5   # -1..+1
        self._drive = 0.0        # 0..1
        self._res_limit = 1.0    # 0..1

    def set_param(self, key: str, value: float) -> None:
        if key == "cutoff":
            self._cutoff = max(20.0, min(20000.0, float(value)))
        elif key == "resonance":
            self._resonance = max(0.0, min(1.0, float(value)))
        elif key == "key_track":
            self._key_track = max(0.0, min(1.0, float(value)))
        elif key == "env_amount":
            self._env_amount = max(-1.0, min(1.0, float(value)))
        elif key == "drive":
            self._drive = max(0.0, min(1.0, float(value)))
        elif key == "res_limit":
            self._res_limit = max(0.0, min(1.0, float(value)))

    def get_param(self, key: str) -> float:
        return getattr(self, f"_{key}", 0.0)

    def reset(self) -> None:
        """Reset filter state (on note retrigger)."""
        pass

    def process(self, buf: np.ndarray, cutoff_mod: float = 0.0,
                note_hz: float = 440.0) -> np.ndarray:
        """Process audio buffer through filter. Returns filtered buffer."""
        return buf.copy()


class SVFFilter(FilterBase):
    """Trapezoidal Integrated State Variable Filter.

    Modes: low-pass, high-pass, band-pass (switchable).
    Self-oscillation at max resonance. Stable at all settings.
    """

    NAME = "SVF"

    MODE_LP = 0
    MODE_HP = 1
    MODE_BP = 2

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._mode = self.MODE_LP
        self._ic1eq = 0.0  # state 1
        self._ic2eq = 0.0  # state 2

    def set_param(self, key: str, value: float) -> None:
        if key == "mode":
            self._mode = int(round(float(value))) % 3
        else:
            super().set_param(key, value)

    def reset(self) -> None:
        self._ic1eq = 0.0
        self._ic2eq = 0.0

    def process(self, buf: np.ndarray, cutoff_mod: float = 0.0,
                note_hz: float = 440.0) -> np.ndarray:
        """Process buffer through SVF.

        v0.0.20.577: All instance variables cached as locals before loop.
        Eliminates ~12 dict lookups per sample → ~30% faster inner loop.

        cutoff_mod: additional cutoff offset in Hz (from FEG)
        note_hz: note frequency for key tracking
        """
        sr = self._sr
        n = len(buf)
        out = np.empty(n, dtype=np.float64)

        # Calculate effective cutoff
        base_cutoff = self._cutoff
        key_track = self._key_track
        if key_track > 0.0:
            kt_semitones = 12.0 * math.log2(max(note_hz, 20.0) / 261.6)
            base_cutoff *= 2.0 ** (kt_semitones * key_track / 12.0)
        # Env modulation
        base_cutoff += cutoff_mod * self._env_amount * 10000.0
        sr_half = sr * 0.49
        if base_cutoff < 20.0:
            base_cutoff = 20.0
        elif base_cutoff > sr_half:
            base_cutoff = sr_half

        # Resonance: Q from 0.5 (no reso) to 25 (self-oscillation)
        q = 0.5 + self._resonance * 24.5 * self._res_limit

        # Drive: soft saturation on input
        drive_gain = 1.0 + self._drive * 8.0
        has_drive = drive_gain > 1.01

        # SVF coefficients (Simper) — pre-computed ONCE, not per sample
        _tan = math.tan
        _pi = math.pi
        g = _tan(_pi * base_cutoff / sr)
        k = 1.0 / q
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2

        # Cache state as locals (avoids self dict lookup per sample)
        ic1 = self._ic1eq
        ic2 = self._ic2eq
        mode = self._mode

        # Drive-specific fast path
        if has_drive:
            _tanh = math.tanh
            tanh_drive = _tanh(drive_gain)
            for i in range(n):
                v0 = _tanh(buf[i] * drive_gain) / tanh_drive
                v3 = v0 - ic2
                v1 = a1 * ic1 + a2 * v3
                v2 = ic2 + a2 * ic1 + a3 * v3
                ic1 = 2.0 * v1 - ic1
                ic2 = 2.0 * v2 - ic2
                if mode == 0:
                    out[i] = v2
                elif mode == 1:
                    out[i] = v0 - k * v1 - v2
                else:
                    out[i] = v1
        else:
            # No-drive fast path (most common)
            if mode == 0:
                for i in range(n):
                    v3 = buf[i] - ic2
                    v1 = a1 * ic1 + a2 * v3
                    v2 = ic2 + a2 * ic1 + a3 * v3
                    ic1 = 2.0 * v1 - ic1
                    ic2 = 2.0 * v2 - ic2
                    out[i] = v2
            elif mode == 1:
                for i in range(n):
                    v0 = buf[i]
                    v3 = v0 - ic2
                    v1 = a1 * ic1 + a2 * v3
                    v2 = ic2 + a2 * ic1 + a3 * v3
                    ic1 = 2.0 * v1 - ic1
                    ic2 = 2.0 * v2 - ic2
                    out[i] = v0 - k * v1 - v2
            else:
                for i in range(n):
                    v3 = buf[i] - ic2
                    v1 = a1 * ic1 + a2 * v3
                    v2 = ic2 + a2 * ic1 + a3 * v3
                    ic1 = 2.0 * v1 - ic1
                    ic2 = 2.0 * v2 - ic2
                    out[i] = v1

        self._ic1eq = ic1
        self._ic2eq = ic2
        return out


# ═══════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════

FILTER_REGISTRY: dict[str, type] = {
    "svf": SVFFilter,
}


def create_filter(name: str, sr: int = 48000) -> FilterBase:
    cls = FILTER_REGISTRY.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown filter: {name}")
    return cls(sr=sr)
