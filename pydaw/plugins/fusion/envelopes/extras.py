"""Fusion Envelopes — AR (Attack-Release), AD (Attack-Decay with Loop), Pluck.

v0.0.20.573: Phase 2 extended envelopes.
v0.0.20.577: Performance — local variable caching, pre-computed rates,
             vectorized sustain (AR), vectorized decay (Pluck).
"""
from __future__ import annotations
import math
import numpy as np
from .adsr import EnvelopeBase

_OFF = 0
_ATTACK = 1
_SUSTAIN = 2
_RELEASE = 3
_DECAY = 4


class AREnvelope(EnvelopeBase):
    """Attack-Release envelope. Sustain = 100% while gate is held."""

    NAME = "AR"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._attack = 0.01
        self._release = 0.5
        self._curve = 0.0     # -1..+1 (neg=log, 0=linear, pos=exp)
        self._stage = _OFF
        self._level = 0.0
        self._vel = 1.0

    def set_param(self, key: str, value: float) -> None:
        if key == "attack":
            self._attack = max(0.0001, min(10.0, float(value)))
        elif key == "release":
            self._release = max(0.0001, min(30.0, float(value)))
        elif key == "curve":
            self._curve = max(-1.0, min(1.0, float(value)))

    def gate_on(self, velocity: float = 1.0) -> None:
        self._vel = max(0.0, min(1.0, float(velocity)))
        self._stage = _ATTACK

    def gate_off(self) -> None:
        if self._stage != _OFF:
            self._stage = _RELEASE

    def is_active(self) -> bool:
        return self._stage != _OFF

    def render(self, frames: int) -> np.ndarray:
        # Fast paths
        if self._stage == _OFF:
            return np.zeros(frames, dtype=np.float64)
        if self._stage == _SUSTAIN:
            return np.full(frames, self._vel, dtype=np.float64)

        out = np.empty(frames, dtype=np.float64)
        sr = self._sr
        stage = self._stage
        level = self._level
        vel = self._vel
        atk_rate = 1.0 / max(1, int(self._attack * sr))
        rel_rate = 1.0 / max(1, int(self._release * sr))

        for i in range(frames):
            if stage == _OFF:
                out[i] = 0.0
            elif stage == _ATTACK:
                level += atk_rate
                if level >= 1.0:
                    level = 1.0
                    stage = _SUSTAIN
                out[i] = level * vel
            elif stage == _SUSTAIN:
                out[i] = vel
            elif stage == _RELEASE:
                level -= rel_rate
                if level <= 0.0:
                    level = 0.0
                    stage = _OFF
                out[i] = level * vel
            else:
                out[i] = 0.0

        self._stage = stage
        self._level = level
        return out


class ADEnvelope(EnvelopeBase):
    """Attack-Decay envelope with optional loop (becomes LFO-like)."""

    NAME = "AD"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._attack = 0.005
        self._decay = 0.3
        self._loop = False
        self._stage = _OFF
        self._level = 0.0
        self._vel = 1.0

    def set_param(self, key: str, value: float) -> None:
        if key == "attack":
            self._attack = max(0.0001, min(10.0, float(value)))
        elif key == "decay":
            self._decay = max(0.0001, min(30.0, float(value)))
        elif key == "loop":
            self._loop = bool(float(value) > 0.5)

    def gate_on(self, velocity: float = 1.0) -> None:
        self._vel = max(0.0, min(1.0, float(velocity)))
        self._level = 0.0
        self._stage = _ATTACK

    def gate_off(self) -> None:
        self._stage = _OFF
        self._level = 0.0

    def is_active(self) -> bool:
        return self._stage != _OFF

    def render(self, frames: int) -> np.ndarray:
        if self._stage == _OFF:
            return np.zeros(frames, dtype=np.float64)

        out = np.empty(frames, dtype=np.float64)
        sr = self._sr
        stage = self._stage
        level = self._level
        vel = self._vel
        loop = self._loop
        atk_rate = 1.0 / max(1, int(self._attack * sr))
        dec_rate = 1.0 / max(1, int(self._decay * sr))

        for i in range(frames):
            if stage == _OFF:
                out[i] = 0.0
            elif stage == _ATTACK:
                level += atk_rate
                if level >= 1.0:
                    level = 1.0
                    stage = _DECAY
                out[i] = level * vel
            elif stage == _DECAY:
                level -= dec_rate
                if level <= 0.0:
                    level = 0.0
                    if loop:
                        stage = _ATTACK
                    else:
                        stage = _OFF
                out[i] = level * vel
            else:
                out[i] = 0.0

        self._stage = stage
        self._level = level
        return out


class PluckEnvelope(EnvelopeBase):
    """Exponential pluck decay — string-like, no sustain."""

    NAME = "Pluck"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._decay = 0.5        # seconds
        self._brightness = 0.5   # 0..1 (LP filter on output)
        self._stage = _OFF
        self._level = 0.0
        self._vel = 1.0
        self._lp_state = 0.0

    def set_param(self, key: str, value: float) -> None:
        if key == "decay":
            self._decay = max(0.0001, min(30.0, float(value)))
        elif key == "brightness":
            self._brightness = max(0.0, min(1.0, float(value)))

    def gate_on(self, velocity: float = 1.0) -> None:
        self._vel = max(0.0, min(1.0, float(velocity)))
        self._level = 1.0
        self._lp_state = 0.0
        self._stage = _DECAY

    def gate_off(self) -> None:
        pass  # Pluck ignores gate off — it's purely decay-based

    def is_active(self) -> bool:
        return self._stage != _OFF and self._level > 0.0001

    def render(self, frames: int) -> np.ndarray:
        if self._stage == _OFF:
            return np.zeros(frames, dtype=np.float64)

        out = np.empty(frames, dtype=np.float64)

        # Pre-compute coefficients
        decay_rate = math.exp(-1.0 / (self._decay * self._sr)) if self._decay > 0 else 0.0
        lp_coeff = 0.05 + self._brightness * 0.95

        # Cache as locals
        level = self._level
        lp_state = self._lp_state
        vel = self._vel
        stage = self._stage

        for i in range(frames):
            if stage == _OFF:
                out[i] = 0.0
            else:
                level *= decay_rate
                lp_state += lp_coeff * (level - lp_state)

                if level < 0.0001:
                    level = 0.0
                    stage = _OFF

                out[i] = lp_state * vel

        self._stage = stage
        self._level = level
        self._lp_state = lp_state
        return out
