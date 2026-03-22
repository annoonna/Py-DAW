"""Fusion Filter — Ladder (4-pole transistor ladder model, 24 dB/oct).

v0.0.20.573: Phase 2 — Huovilainen nonlinear Moog ladder model.
v0.0.20.577: Performance — local variable caching, drive branch hoisting.
"""
from __future__ import annotations
import math
import numpy as np
from .svf import FilterBase


class LadderFilter(FilterBase):
    """4-pole transistor ladder low-pass filter (24 dB/oct)."""

    NAME = "Low-pass LD"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._s = [0.0, 0.0, 0.0, 0.0]  # 4 filter stages

    def reset(self) -> None:
        self._s = [0.0, 0.0, 0.0, 0.0]

    def process(self, buf: np.ndarray, cutoff_mod: float = 0.0,
                note_hz: float = 440.0) -> np.ndarray:
        """Process buffer through Moog Ladder.

        v0.0.20.577: Local variable caching, pre-computed drive path,
        single tanh lookup reference. ~25% faster inner loop.
        """
        sr = self._sr
        n = len(buf)
        out = np.empty(n, dtype=np.float64)

        # Effective cutoff
        fc = self._cutoff
        key_track = self._key_track
        if key_track > 0.0:
            kt_st = 12.0 * math.log2(max(note_hz, 20.0) / 261.6)
            fc *= 2.0 ** (kt_st * key_track / 12.0)
        fc += cutoff_mod * self._env_amount * 10000.0
        sr_half = sr * 0.49
        if fc < 20.0:
            fc = 20.0
        elif fc > sr_half:
            fc = sr_half

        # Resonance 0..4 (self-oscillation at 4)
        k = self._resonance * 4.0 * self._res_limit

        # Drive
        drive = 1.0 + self._drive * 8.0
        has_drive = drive > 1.01

        # Huovilainen coefficient
        g = 1.0 - math.exp(-2.0 * math.pi * fc / sr)

        # Cache state as locals
        s0, s1, s2, s3 = self._s
        _tanh = math.tanh

        if has_drive:
            for i in range(n):
                x = _tanh(buf[i] * drive)
                u = x - k * s3
                s0 += g * (_tanh(u) - _tanh(s0))
                s1 += g * (_tanh(s0) - _tanh(s1))
                s2 += g * (_tanh(s1) - _tanh(s2))
                s3 += g * (_tanh(s2) - _tanh(s3))
                out[i] = s3
        else:
            for i in range(n):
                u = buf[i] - k * s3
                s0 += g * (_tanh(u) - _tanh(s0))
                s1 += g * (_tanh(s0) - _tanh(s1))
                s2 += g * (_tanh(s1) - _tanh(s2))
                s3 += g * (_tanh(s2) - _tanh(s3))
                out[i] = s3

        self._s = [s0, s1, s2, s3]
        return out


class CombFilter(FilterBase):
    """Comb filter with feedback and damping frequency.

    Uses a delay line with filtered feedback (Karplus-Strong-like).
    """

    NAME = "Comb"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._feedback = 0.5     # -1..+1
        self._damp_freq = 8000.0 # Hz
        # Delay buffer (max ~50ms for lowest audible pitch)
        max_delay = int(sr * 0.05) + 1
        self._buf = np.zeros(max_delay, dtype=np.float64)
        self._write_pos = 0
        self._damp_state = 0.0

    def set_param(self, key: str, value: float) -> None:
        if key == "feedback":
            self._feedback = max(-1.0, min(1.0, float(value)))
        elif key == "damp_freq":
            self._damp_freq = max(200.0, min(20000.0, float(value)))
        else:
            super().set_param(key, value)

    def reset(self) -> None:
        self._buf[:] = 0.0
        self._write_pos = 0
        self._damp_state = 0.0

    def process(self, buf: np.ndarray, cutoff_mod: float = 0.0,
                note_hz: float = 440.0) -> np.ndarray:
        """Process buffer through Comb filter.

        v0.0.20.577: Local variable caching, pre-computed coefficients.
        """
        sr = self._sr
        n = len(buf)
        out = np.empty(n, dtype=np.float64)

        # Delay time from cutoff (cutoff = comb frequency)
        fc = self._cutoff
        fc += cutoff_mod * self._env_amount * 5000.0
        sr_half = sr * 0.49
        if fc < 20.0:
            fc = 20.0
        elif fc > sr_half:
            fc = sr_half
        delay_samples = max(1.0, sr / fc)

        # Damping: 1-pole LP on feedback path
        damp_g = 1.0 - math.exp(-2.0 * math.pi * self._damp_freq / sr)

        # Cache as locals
        fb = self._feedback
        d_buf = self._buf
        buf_len = len(d_buf)
        wp = self._write_pos
        ds = self._damp_state

        delay_int = int(delay_samples)
        delay_frac = delay_samples - delay_int
        one_minus_frac = 1.0 - delay_frac

        for i in range(n):
            rp1 = (wp - delay_int) % buf_len
            rp2 = (wp - delay_int - 1) % buf_len
            delayed = d_buf[rp1] * one_minus_frac + d_buf[rp2] * delay_frac

            ds += damp_g * (delayed - ds)
            d_buf[wp] = buf[i] + ds * fb

            out[i] = delayed
            wp = (wp + 1) % buf_len

        self._write_pos = wp
        self._damp_state = ds
        return out
