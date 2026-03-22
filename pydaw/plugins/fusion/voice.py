"""Fusion Voice — Polyphonic voice manager.

v0.0.20.572: Phase 1 — 8-voice polyphony with last-note-priority stealing.

Each Voice owns one Oscillator + Filter + AEG + FEG instance.
The FusionEngine manages a pool of voices and dispatches MIDI.
"""
from __future__ import annotations
import numpy as np
from typing import Optional

from .oscillators.base import OscillatorBase
from .oscillators.basic_waves import SineOscillator, create_oscillator
from .filters.svf import FilterBase, SVFFilter, create_filter
from .envelopes.adsr import EnvelopeBase, ADSREnvelope, create_envelope


class Voice:
    """A single synthesis voice with OSC → FILTER → AMP (AEG)."""

    def __init__(self, sr: int = 48000):
        self._sr = sr
        self.osc: OscillatorBase = SineOscillator(sr)
        self.flt: FilterBase = SVFFilter(sr)
        self.aeg: ADSREnvelope = ADSREnvelope(sr)   # Amplitude EG
        self.feg: ADSREnvelope = ADSREnvelope(sr)   # Filter EG

        self.pitch: int = 60       # MIDI note
        self.velocity: float = 1.0
        self.freq: float = 440.0
        self.active: bool = False
        self.stealing: bool = False  # marked for steal
        self._age: int = 0          # samples since note-on

    def note_on(self, pitch: int, velocity: float) -> None:
        self.pitch = int(pitch)
        self.velocity = max(0.0, min(1.0, float(velocity) / 127.0))
        self.freq = 440.0 * (2.0 ** ((self.pitch - 69) / 12.0))
        self.active = True
        self.stealing = False
        self._age = 0

        self.osc.reset_phase()
        self.flt.reset()
        self.aeg.gate_on(self.velocity)
        self.feg.gate_on(self.velocity)

    def note_off(self) -> None:
        self.aeg.gate_off()
        self.feg.gate_off()

    def is_active(self) -> bool:
        return self.active and self.aeg.is_active()

    def render(self, frames: int, sr: int,
               sub_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """Render this voice for N frames. Returns stereo-ready mono.

        v0.0.20.577: Direct buffer multiply instead of np.mean for FEG,
        vectorized AEG application.
        """
        if not self.is_active():
            self.active = False
            return np.zeros(frames, dtype=np.float64)

        osc_freq = self.osc.calc_freq(self.freq)

        # Render sub as phase mod source
        pm_buf = sub_buf  # can be None

        # Oscillator
        raw = self.osc.render(frames, osc_freq, sr, phase_mod_buf=pm_buf)

        # Filter EG → cutoff modulation (use mean of FEG buffer)
        feg_buf = self.feg.render(frames)
        # Avoid np.mean call overhead — use sum/n for simple case
        n = len(feg_buf)
        avg_feg = float(feg_buf.sum()) / n if n > 0 else 0.0

        # Filter
        filtered = self.flt.process(raw, cutoff_mod=avg_feg, note_hz=self.freq)

        # Amplitude EG (vectorized multiply)
        aeg_buf = self.aeg.render(frames)
        np.multiply(filtered, aeg_buf, out=filtered)

        self._age += frames

        # Check if voice has finished
        if not self.aeg.is_active():
            self.active = False

        return filtered

    def swap_oscillator(self, osc_type: str) -> None:
        self.osc = create_oscillator(osc_type, self._sr)

    def swap_filter(self, flt_type: str) -> None:
        self.flt = create_filter(flt_type, self._sr)

    def swap_envelope(self, env_type: str) -> None:
        self.aeg = create_envelope(env_type, self._sr)
