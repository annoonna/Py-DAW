# -*- coding: utf-8 -*-
"""DSP helpers used by Pro Audio Sampler (pure numpy/math).

Ported from the standalone Qt5 sampler into the ChronoScaleStudio DAW (PyQt6).
"""

from __future__ import annotations

import math
import numpy as np


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, t):
    return a + (b - a) * t


def softclip(x: float) -> float:
    return math.tanh(x)


def limiter_soft(x: float, thr: float = 0.98) -> float:
    if x > thr:
        return thr + (x - thr) * 0.1
    if x < -thr:
        return -thr + (x + thr) * 0.1
    return x


class BiquadDF2T:
    def __init__(self):
        self.b0 = 1.0
        self.b1 = 0.0
        self.b2 = 0.0
        self.a1 = 0.0
        self.a2 = 0.0
        self.z1 = 0.0
        self.z2 = 0.0

    def reset(self):
        self.z1 = 0.0
        self.z2 = 0.0

    def set_coeffs(self, b0, b1, b2, a1, a2):
        self.b0 = float(b0)
        self.b1 = float(b1)
        self.b2 = float(b2)
        self.a1 = float(a1)
        self.a2 = float(a2)

    def process(self, x: float) -> float:
        y = self.b0 * x + self.z1
        self.z1 = self.b1 * x - self.a1 * y + self.z2
        self.z2 = self.b2 * x - self.a2 * y
        return y


class DelayLine:
    def __init__(self, max_samples=48000):
        self.buf = np.zeros(int(max_samples), dtype=np.float32)
        self.size = int(max_samples)
        self.w = 0

    def write(self, x: float):
        self.buf[self.w] = x
        self.w = (self.w + 1) % self.size

    def read_frac(self, delay_samples: float) -> float:
        d = clamp(delay_samples, 0.0, self.size - 2.0)
        r = self.w - d
        while r < 0:
            r += self.size
        i0 = int(r)
        i1 = (i0 + 1) % self.size
        frac = r - i0
        return float(self.buf[i0] * (1.0 - frac) + self.buf[i1] * frac)


def rbj_biquad(sr: float, ftype: str, fc: float, q: float):
    sr = float(max(1.0, sr))
    # Backwards/UX-friendly aliases (UI often uses full words)
    try:
        ft = str(ftype or "off").lower().strip()
    except Exception:
        ft = "off"
    if ft in ("lowpass", "low-pass", "lp"):
        ftype = "lp"
    elif ft in ("highpass", "high-pass", "hp"):
        ftype = "hp"
    elif ft in ("bandpass", "band-pass", "bp"):
        ftype = "bp"
    else:
        ftype = ft
    if ftype == "off":
        return (1.0, 0.0, 0.0, 0.0, 0.0)

    fc = clamp(fc, 20.0, 0.49 * sr)
    q = clamp(q, 0.25, 12.0)

    w0 = 2.0 * math.pi * (fc / sr)
    cosw = math.cos(w0)
    sinw = math.sin(w0)
    alpha = sinw / (2.0 * q)

    if ftype == "lp":
        b0 = (1 - cosw) / 2
        b1 = 1 - cosw
        b2 = (1 - cosw) / 2
        a0 = 1 + alpha
        a1 = -2 * cosw
        a2 = 1 - alpha
    elif ftype == "hp":
        b0 = (1 + cosw) / 2
        b1 = -(1 + cosw)
        b2 = (1 + cosw) / 2
        a0 = 1 + alpha
        a1 = -2 * cosw
        a2 = 1 - alpha
    else:  # bp
        b0 = sinw / 2
        b1 = 0.0
        b2 = -sinw / 2
        a0 = 1 + alpha
        a1 = -2 * cosw
        a2 = 1 - alpha

    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    return (b0, b1, b2, a1, a2)


def rbj_peaking(sr: float, fc: float, q: float, gain_db: float):
    """RBJ peaking EQ biquad."""
    sr = float(max(1.0, sr))
    fc = clamp(float(fc), 20.0, 0.49 * sr)
    q = clamp(float(q), 0.25, 24.0)
    A = 10.0 ** (float(gain_db) / 40.0)

    w0 = 2.0 * math.pi * (fc / sr)
    cosw = math.cos(w0)
    sinw = math.sin(w0)
    alpha = sinw / (2.0 * q)

    b0 = 1.0 + alpha * A
    b1 = -2.0 * cosw
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha / A

    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    return (b0, b1, b2, a1, a2)


def rbj_lowshelf(sr: float, fc: float, q: float, gain_db: float):
    """RBJ low-shelf biquad."""
    sr = float(max(1.0, sr))
    fc = clamp(float(fc), 20.0, 0.49 * sr)
    q = clamp(float(q), 0.25, 24.0)
    A = 10.0 ** (float(gain_db) / 40.0)

    w0 = 2.0 * math.pi * (fc / sr)
    cosw = math.cos(w0)
    sinw = math.sin(w0)
    S = clamp(float(q) / 2.0, 0.25, 2.0)
    alpha = sinw / 2.0 * math.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
    two_sqrtA_alpha = 2.0 * math.sqrt(A) * alpha

    b0 = A * ((A + 1) - (A - 1) * cosw + two_sqrtA_alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * cosw)
    b2 = A * ((A + 1) - (A - 1) * cosw - two_sqrtA_alpha)
    a0 = (A + 1) + (A - 1) * cosw + two_sqrtA_alpha
    a1 = -2 * ((A - 1) + (A + 1) * cosw)
    a2 = (A + 1) + (A - 1) * cosw - two_sqrtA_alpha

    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    return (b0, b1, b2, a1, a2)


def rbj_highshelf(sr: float, fc: float, q: float, gain_db: float):
    """RBJ high-shelf biquad."""
    sr = float(max(1.0, sr))
    fc = clamp(float(fc), 20.0, 0.49 * sr)
    q = clamp(float(q), 0.25, 24.0)
    A = 10.0 ** (float(gain_db) / 40.0)

    w0 = 2.0 * math.pi * (fc / sr)
    cosw = math.cos(w0)
    sinw = math.sin(w0)
    S = clamp(float(q) / 2.0, 0.25, 2.0)
    alpha = sinw / 2.0 * math.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
    two_sqrtA_alpha = 2.0 * math.sqrt(A) * alpha

    b0 = A * ((A + 1) + (A - 1) * cosw + two_sqrtA_alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * cosw)
    b2 = A * ((A + 1) + (A - 1) * cosw - two_sqrtA_alpha)
    a0 = (A + 1) - (A - 1) * cosw + two_sqrtA_alpha
    a1 = 2 * ((A - 1) - (A + 1) * cosw)
    a2 = (A + 1) - (A - 1) * cosw - two_sqrtA_alpha

    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    return (b0, b1, b2, a1, a2)
