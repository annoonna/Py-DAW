"""Fusion Oscillator — Base class for all oscillator modules.

v0.0.20.572: Phase 1 core.
"""
from __future__ import annotations
import numpy as np
from typing import Optional


class OscillatorBase:
    """Abstract base for Fusion oscillator modules.

    Each oscillator renders audio into a buffer at the voice's current
    frequency. The base class manages phase accumulation and common
    parameters (pitch offset, octave, stereo detune, phase mod depth).
    """

    NAME: str = "Base"

    def __init__(self, sr: int = 48000):
        self._sr = int(sr)
        self._phase = 0.0          # 0..1 normalized phase
        self._pitch_st = 0.0       # semitone offset -7..+7
        self._octave_shift = 0     # octaves (-2..+3)
        self._detune_stereo = 0.0  # cents
        self._phase_mod = 0.0      # 0..1 phase mod from sub

    # ── Parameter Access ──

    def set_param(self, key: str, value: float) -> None:
        if key == "pitch_st":
            self._pitch_st = max(-7.0, min(7.0, float(value)))
        elif key == "octave_shift":
            self._octave_shift = int(round(float(value)))
        elif key == "detune_stereo":
            self._detune_stereo = max(-100.0, min(100.0, float(value)))
        elif key == "phase_mod":
            self._phase_mod = max(0.0, min(1.0, float(value)))

    def get_param(self, key: str) -> float:
        if key == "pitch_st":
            return self._pitch_st
        if key == "octave_shift":
            return float(self._octave_shift)
        if key == "detune_stereo":
            return self._detune_stereo
        if key == "phase_mod":
            return self._phase_mod
        return 0.0

    def param_names(self) -> list[str]:
        """Return parameter names specific to this oscillator type."""
        return []

    # ── DSP ──

    def reset_phase(self) -> None:
        self._phase = 0.0

    def calc_freq(self, base_freq: float) -> float:
        """Apply pitch offset + octave shift to a base frequency."""
        oct = 2.0 ** self._octave_shift
        st = 2.0 ** (self._pitch_st / 12.0)
        return base_freq * oct * st

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """Render audio frames at the given frequency.

        Override in subclasses. Returns mono float64 array of length `frames`.
        """
        return np.zeros(frames, dtype=np.float64)

    def _advance_phase(self, freq: float, sr: int) -> float:
        """Advance internal phase by one sample. Returns phase before advance (0..1)."""
        p = self._phase
        self._phase = (self._phase + freq / sr) % 1.0
        return p

    def _phase_increment(self, freq: float, sr: int) -> float:
        """Phase increment per sample."""
        return freq / sr
