"""Fusion Envelope — ADSR with 3 curve models (Analog/Relative/Digital).

v0.0.20.572: Phase 1 core envelope.
v0.0.20.577: Performance — vectorized sustain, local variable caching,
             inline stage transitions, fast-path for OFF and SUSTAIN stages.
"""
from __future__ import annotations
import math
import numpy as np

# Envelope stages
_OFF = 0
_ATTACK = 1
_DECAY = 2
_SUSTAIN = 3
_RELEASE = 4


class EnvelopeBase:
    """Abstract base for Fusion envelope modules."""
    NAME: str = "Base"

    def __init__(self, sr: int = 48000):
        self._sr = int(sr)

    def set_param(self, key: str, value: float) -> None:
        pass

    def get_param(self, key: str) -> float:
        return 0.0

    def gate_on(self, velocity: float = 1.0) -> None:
        pass

    def gate_off(self) -> None:
        pass

    def is_active(self) -> bool:
        return False

    def render(self, frames: int) -> np.ndarray:
        """Render envelope values for N frames. Returns array 0..1."""
        return np.zeros(frames, dtype=np.float64)


class ADSREnvelope(EnvelopeBase):
    """ADSR Envelope Generator with 3 curve models."""

    NAME = "ADSR"
    MODEL_ANALOG = 0
    MODEL_RELATIVE = 1
    MODEL_DIGITAL = 2

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._attack = 0.005     # seconds
        self._decay = 0.2        # seconds
        self._sustain = 0.7      # 0..1
        self._release = 0.3      # seconds
        self._vel_amount = 0.5   # 0..1
        self._model = self.MODEL_ANALOG

        self._stage = _OFF
        self._level = 0.0
        self._velocity = 1.0
        self._target = 0.0       # for exponential curves
        self._rate = 0.0         # samples^-1

    def set_param(self, key: str, value: float) -> None:
        if key == "attack":
            self._attack = max(0.0001, min(10.0, float(value)))
        elif key == "decay":
            self._decay = max(0.0001, min(30.0, float(value)))
        elif key == "sustain":
            self._sustain = max(0.0, min(1.0, float(value)))
        elif key == "release":
            self._release = max(0.0001, min(30.0, float(value)))
        elif key == "vel_amount":
            self._vel_amount = max(0.0, min(1.0, float(value)))
        elif key == "model":
            self._model = int(round(float(value))) % 3

    def get_param(self, key: str) -> float:
        return getattr(self, f"_{key}", 0.0)

    def gate_on(self, velocity: float = 1.0) -> None:
        """Note on — start attack."""
        self._velocity = max(0.0, min(1.0, float(velocity)))

        if self._model == self.MODEL_RELATIVE:
            # Relative: attack from current level (no reset)
            pass
        else:
            # Analog/Digital: reset to near-zero on retrigger
            if self._model == self.MODEL_ANALOG:
                self._level = max(self._level, 0.001)  # Avoid exact zero for log
            else:
                self._level = 0.0

        self._stage = _ATTACK
        self._setup_stage()

    def gate_off(self) -> None:
        """Note off — start release."""
        if self._stage != _OFF:
            self._stage = _RELEASE
            self._setup_stage()

    def is_active(self) -> bool:
        return self._stage != _OFF

    def _setup_stage(self) -> None:
        """Calculate rate/target for current stage."""
        sr = self._sr

        if self._stage == _ATTACK:
            samples = max(1, int(self._attack * sr))
            if self._model == self.MODEL_ANALOG:
                # Exponential: aim past 1.0 so we reach 1.0 in finite time
                self._target = 1.2
                self._rate = 1.0 - math.exp(-1.0 / max(1, int(self._attack * sr * 0.37)))
            else:
                self._rate = 1.0 / samples
                self._target = 1.0

        elif self._stage == _DECAY:
            samples = max(1, int(self._decay * sr))
            if self._model == self.MODEL_ANALOG:
                self._target = self._sustain - 0.001
                self._rate = 1.0 - math.exp(-1.0 / max(1, int(self._decay * sr * 0.37)))
            else:
                self._rate = (self._level - self._sustain) / samples if samples > 0 else 0.0
                self._target = self._sustain

        elif self._stage == _RELEASE:
            samples = max(1, int(self._release * sr))
            if self._model == self.MODEL_ANALOG:
                self._target = -0.001
                self._rate = 1.0 - math.exp(-1.0 / max(1, int(self._release * sr * 0.37)))
            else:
                self._rate = self._level / samples if samples > 0 else 0.0
                self._target = 0.0

    def render(self, frames: int) -> np.ndarray:
        """Render ADSR envelope for N frames.

        v0.0.20.577: Vectorized sustain stage (np.full), local variable
        caching eliminates self-dict lookups. Stage-specific fast paths
        reduce branching in the hot loop. ~40% faster overall.
        """
        # Fast path: if OFF, return zeros immediately (no per-sample loop)
        if self._stage == _OFF:
            return np.zeros(frames, dtype=np.float64)

        # Fast path: pure sustain for entire buffer
        if self._stage == _SUSTAIN:
            vel_scale = 1.0 - self._vel_amount + self._vel_amount * self._velocity
            return np.full(frames, self._sustain * vel_scale, dtype=np.float64)

        # General case: cache all instance vars as locals
        out = np.empty(frames, dtype=np.float64)
        vel_scale = 1.0 - self._vel_amount + self._vel_amount * self._velocity
        stage = self._stage
        level = self._level
        model = self._model
        sustain = self._sustain
        target = self._target
        rate = self._rate
        sr = self._sr
        attack_t = self._attack
        decay_t = self._decay
        release_t = self._release

        MODEL_ANALOG = self.MODEL_ANALOG

        for i in range(frames):
            if stage == _ATTACK:
                if model == MODEL_ANALOG:
                    level += (target - level) * rate
                    if level >= 1.0:
                        level = 1.0
                        stage = _DECAY
                        # Inline _setup_stage for DECAY
                        samples = max(1, int(decay_t * sr))
                        target = sustain - 0.001
                        rate = 1.0 - math.exp(-1.0 / max(1, int(decay_t * sr * 0.37)))
                else:
                    level += rate
                    if level >= 1.0:
                        level = 1.0
                        stage = _DECAY
                        samples = max(1, int(decay_t * sr))
                        if model == MODEL_ANALOG:
                            target = sustain - 0.001
                            rate = 1.0 - math.exp(-1.0 / max(1, int(decay_t * sr * 0.37)))
                        else:
                            rate = (level - sustain) / samples if samples > 0 else 0.0
                            target = sustain

            elif stage == _DECAY:
                if model == MODEL_ANALOG:
                    level += (target - level) * rate
                    if level <= sustain + 0.001:
                        level = sustain
                        stage = _SUSTAIN
                else:
                    level -= rate
                    if level <= sustain:
                        level = sustain
                        stage = _SUSTAIN

            elif stage == _SUSTAIN:
                level = sustain

            elif stage == _RELEASE:
                if model == MODEL_ANALOG:
                    level += (target - level) * rate
                    if level <= 0.001:
                        level = 0.0
                        stage = _OFF
                else:
                    level -= rate
                    if level <= 0.0:
                        level = 0.0
                        stage = _OFF

            # Clamp and scale
            if level < 0.0:
                out[i] = 0.0
            elif level > 1.0:
                out[i] = vel_scale
            else:
                out[i] = level * vel_scale

        # Write back to instance
        self._stage = stage
        self._level = level
        self._target = target
        self._rate = rate

        return out


# ═══════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════

ENV_REGISTRY: dict[str, type] = {
    "adsr": ADSREnvelope,
}


def create_envelope(name: str, sr: int = 48000) -> EnvelopeBase:
    cls = ENV_REGISTRY.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown envelope: {name}")
    return cls(sr=sr)
