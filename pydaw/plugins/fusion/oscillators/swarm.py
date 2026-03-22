"""Fusion Oscillator — Swarm (multi-voice unison with stereo spread).

v0.0.20.573: Phase 2 — Up to 8 detuned voices with stereo panning.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Optional
from .base import OscillatorBase
from .basic_waves import _polyblep


class SwarmOscillator(OscillatorBase):
    """Eight-voice unison oscillator with detune spread."""

    NAME = "Swarm"

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._voices = 8         # 1-8
        self._spread = 0.5       # 0..1 (max detune in cents = spread * 50)
        self._waveform = 0       # 0=saw, 1=sine
        self._phases = [0.0] * 8

    def set_param(self, key: str, value: float) -> None:
        if key == "voices":
            self._voices = max(1, min(8, int(round(float(value)))))
        elif key == "spread":
            self._spread = max(0.0, min(1.0, float(value)))
        elif key == "waveform":
            self._waveform = int(round(float(value))) % 2
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "voices":
            return float(self._voices)
        if key == "spread":
            return self._spread
        if key == "waveform":
            return float(self._waveform)
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["voices", "spread", "waveform"]

    def reset_phase(self) -> None:
        super().reset_phase()
        self._phases = [0.0] * 8

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Vectorized sine path, local cache for saw path."""
        n = self._voices
        max_detune_cents = self._spread * 50.0
        out = np.zeros(frames, dtype=np.float64)
        TWO_PI = 2.0 * np.pi
        waveform = self._waveform

        for v_idx in range(n):
            if n == 1:
                detune = 0.0
            else:
                pos = (v_idx / (n - 1)) * 2.0 - 1.0
                detune = pos * max_detune_cents

            v_freq = freq * (2.0 ** (detune / 1200.0))
            dt = v_freq / sr
            phase0 = self._phases[v_idx]

            if waveform == 1:
                # Sine: fully vectorized
                phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
                out += np.sin(TWO_PI * phases)
                self._phases[v_idx] = (phase0 + frames * dt) % 1.0
            else:
                # Saw with inline PolyBLEP: local cache
                phase = phase0
                for i in range(frames):
                    raw = 2.0 * phase - 1.0
                    if phase < dt:
                        t_n = phase / dt
                        raw -= t_n + t_n - t_n * t_n - 1.0
                    elif phase > 1.0 - dt:
                        t_n = (phase - 1.0) / dt
                        raw -= t_n * t_n + t_n + t_n + 1.0
                    out[i] += raw
                    phase = (phase + dt) % 1.0
                self._phases[v_idx] = phase

        # Normalize
        if n > 0:
            out *= 1.0 / math.sqrt(n)

        return out
