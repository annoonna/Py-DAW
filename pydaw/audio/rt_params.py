"""Real-time Parameter Store (v0.0.20.1).

Thread-safe, lock-free parameter system for DAW-grade audio.

Design:
- GUI thread writes target values via set_param()  [atomic float write]
- Audio thread reads smoothed values via get_smooth() [atomic float read]
- advance() runs per audio block — single-pole IIR exponential smoothing
- Zero locks, zero allocations in the audio path

Usage:
    store = RTParamStore()
    store.set_param("master:vol", 0.8)       # GUI thread
    # audio callback:
    store.advance(256, 48000)                 # once per block
    vol = store.get_smooth("master:vol", 0.8) # per-sample read
"""
from __future__ import annotations

import math
from typing import Dict


class _RTParam:
    """Single real-time parameter with exponential smoothing."""

    __slots__ = ("target", "current", "smooth_ms", "_coeff", "_last_sr")

    def __init__(self, initial: float = 0.0, smooth_ms: float = 5.0):
        self.target = float(initial)
        self.current = float(initial)
        self.smooth_ms = float(smooth_ms)
        self._coeff = 0.0
        self._last_sr = 0

    def set_target(self, value: float) -> None:
        """Called from GUI thread — atomic float write under GIL."""
        self.target = float(value)

    def snap(self) -> None:
        """Instantly set current = target (for init or reset)."""
        self.current = self.target

    def advance_block(self, frames: int, sr: int) -> None:
        """Advance smoothing for one audio block.

        Single-pole IIR: current += coeff * (target - current)
        coeff = 1 - exp(-frames / (smooth_ms * sr / 1000))
        """
        if sr != self._last_sr or self._coeff == 0.0:
            tau = max(0.1, self.smooth_ms) * float(sr) / 1000.0
            self._coeff = 1.0 - math.exp(-float(frames) / max(1.0, tau))
            self._last_sr = sr

        diff = self.target - self.current
        if abs(diff) < 1e-8:
            self.current = self.target
        else:
            self.current += self._coeff * diff


class RTParamStore:
    """Lock-free real-time parameter store.

    Thread safety model:
    - GUI thread: set_param() writes float (atomic under GIL)
    - Audio thread: get_smooth()/advance() reads float (atomic under GIL)
    - No mutexes, no locks in the audio path — ever
    """

    def __init__(self, default_smooth_ms: float = 5.0):
        self._params: Dict[str, _RTParam] = {}
        self._default_smooth_ms = float(default_smooth_ms)

    # ---- Setup (call from init, NOT from audio thread)

    def ensure(self, key: str, initial: float = 0.0,
               smooth_ms: float = -1.0) -> None:
        """Ensure a parameter exists. Safe to call multiple times."""
        if key not in self._params:
            sm = smooth_ms if smooth_ms >= 0 else self._default_smooth_ms
            self._params[key] = _RTParam(initial, sm)

    # ---- GUI thread writes

    def set_param(self, key: str, value: float,
                  smooth_ms: float = -1.0) -> None:
        """Set parameter target (GUI thread)."""
        p = self._params.get(key)
        if p is None:
            sm = smooth_ms if smooth_ms >= 0 else self._default_smooth_ms
            p = _RTParam(value, sm)
            self._params[key] = p
        p.set_target(value)

    def set_immediate(self, key: str, value: float) -> None:
        """Set parameter immediately without smoothing (mute/solo)."""
        p = self._params.get(key)
        if p is None:
            p = _RTParam(value, self._default_smooth_ms)
            self._params[key] = p
        p.target = float(value)
        p.current = float(value)

    # ---- Audio thread reads (NO LOCKS)

    def get_smooth(self, key: str, default: float = 0.0) -> float:
        """Read smoothed value (audio thread — zero locks)."""
        p = self._params.get(key)
        return p.current if p is not None else default

    def get_target(self, key: str, default: float = 0.0) -> float:
        """Read target value (GUI thread)."""
        p = self._params.get(key)
        return p.target if p is not None else default

    def advance(self, frames: int, sr: int) -> None:
        """Advance all smoothers for one audio block (audio thread)."""
        for p in self._params.values():
            p.advance_block(frames, sr)

    def snap_all(self) -> None:
        """Snap all parameters to targets (e.g. on transport start)."""
        for p in self._params.values():
            p.snap()

    # ---- Convenience: Track parameter keys

    @staticmethod
    def track_vol_key(track_id: str) -> str:
        return f"trk:{track_id}:vol"

    @staticmethod
    def track_pan_key(track_id: str) -> str:
        return f"trk:{track_id}:pan"

    @staticmethod
    def track_mute_key(track_id: str) -> str:
        return f"trk:{track_id}:mute"

    @staticmethod
    def track_solo_key(track_id: str) -> str:
        return f"trk:{track_id}:solo"

    # ---- Convenience: Track parameter helpers

    def set_track_vol(self, track_id: str, vol: float) -> None:
        self.set_param(self.track_vol_key(track_id),
                       max(0.0, min(1.0, vol)))

    def set_track_pan(self, track_id: str, pan: float) -> None:
        self.set_param(self.track_pan_key(track_id),
                       max(-1.0, min(1.0, pan)))

    def set_track_mute(self, track_id: str, muted: bool) -> None:
        self.set_immediate(self.track_mute_key(track_id),
                           1.0 if muted else 0.0)

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        self.set_immediate(self.track_solo_key(track_id),
                           1.0 if solo else 0.0)

    def get_track_vol(self, track_id: str) -> float:
        return self.get_smooth(self.track_vol_key(track_id), 0.8)

    def get_track_pan(self, track_id: str) -> float:
        return self.get_smooth(self.track_pan_key(track_id), 0.0)

    def is_track_muted(self, track_id: str) -> bool:
        return self.get_smooth(self.track_mute_key(track_id), 0.0) > 0.5

    def is_track_solo(self, track_id: str) -> bool:
        return self.get_smooth(self.track_solo_key(track_id), 0.0) > 0.5

    def any_solo(self) -> bool:
        """Check if any track has solo enabled (for solo logic)."""
        for key, p in self._params.items():
            if key.endswith(":solo") and p.current > 0.5:
                return True
        return False
