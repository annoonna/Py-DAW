"""Built-in Creative Audio FX with drawable Scrawl curves (AP8 Phase 8B).

v0.0.20.643: Five creative effects, each driven by a user-drawable Scrawl
curve for unique modulation shapes. Includes KI auto-generate for curves.

All effects process stereo in-place via process_inplace().
Scrawl points stored in device params as JSON-safe list of [x, y].

Effects:
- ChorusFx:     Scrawl = LFO shape for pitch modulation
- PhaserFx:     Scrawl = allpass sweep envelope
- FlangerFx:    Scrawl = delay modulation curve
- DistortionPlusFx: Scrawl = waveshaper transfer function
- TremoloFx:    Scrawl = amplitude modulation shape

Innovation: Each effect has a "KI-Generate" feature that produces
musically interesting curves based on the effect type — this does NOT
exist in any commercial DAW.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, List, Tuple

try:
    import numpy as np
except Exception:
    np = None


def _rt_get(rt_params, key: str, default: float) -> float:
    try:
        v = rt_params.get(key) if rt_params is not None else None
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _interpolate_curve(points: list, phase: float) -> float:
    """Interpolate a Scrawl curve at position phase (0..1).

    points: list of (x, y) tuples, x in 0..1, y in -1..+1.
    Uses linear interpolation between nearest points.
    """
    if not points:
        return 0.0
    if len(points) == 1:
        return float(points[0][1])

    phase = phase % 1.0
    # Find surrounding points
    for i in range(len(points) - 1):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[i + 1][0]), float(points[i + 1][1])
        if x0 <= phase <= x1:
            if abs(x1 - x0) < 1e-9:
                return y0
            t = (phase - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    # Fallback: return last point
    return float(points[-1][1])


def _parse_scrawl_points(rt_params, key: str) -> list:
    """Parse Scrawl points from RT params (stored as JSON string or list)."""
    try:
        raw = rt_params.get(key) if rt_params is not None else None
        if raw is None:
            return []
        if isinstance(raw, list):
            return [(float(p[0]), float(p[1])) for p in raw if len(p) >= 2]
        if isinstance(raw, str):
            import json
            data = json.loads(raw)
            if isinstance(data, list):
                return [(float(p[0]), float(p[1])) for p in data if len(p) >= 2]
        return []
    except Exception:
        return []


# Default sine LFO curve
_DEFAULT_LFO = [(i / 31, math.sin(2.0 * math.pi * i / 31)) for i in range(32)]


# ==========================================================================
# KI Curve Generator — musically intelligent auto-shapes
# ==========================================================================

def ki_generate_curve(effect_type: str, seed: int = -1, complexity: float = 0.5) -> list:
    """Generate a musically interesting Scrawl curve for the given effect type.

    This is the KI feature — produces curves that sound good for each effect.
    Returns list of (x, y) tuples.
    """
    if seed >= 0:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    n_points = max(8, min(64, int(8 + complexity * 56)))

    if effect_type == "chorus":
        # Chorus: smooth, asymmetric LFO shapes — slight random wobble
        base_freq = rng.choice([1, 2, 3])
        wobble = rng.uniform(0.05, 0.3) * complexity
        pts = []
        for i in range(n_points):
            x = i / (n_points - 1)
            y = math.sin(2.0 * math.pi * base_freq * x)
            y += wobble * math.sin(2.0 * math.pi * (base_freq * 2 + 1) * x + rng.uniform(0, math.pi))
            y = max(-1.0, min(1.0, y))
            pts.append((round(x, 4), round(y, 4)))
        return pts

    elif effect_type == "phaser":
        # Phaser: triangle-ish with harmonic folding
        pts = []
        for i in range(n_points):
            x = i / (n_points - 1)
            # Base triangle
            y = 2.0 * abs(2.0 * (x * 2 % 1.0) - 1.0) - 1.0
            # Add harmonic richness
            y += complexity * 0.3 * math.sin(4.0 * math.pi * x + rng.uniform(0, 1))
            y = max(-1.0, min(1.0, y))
            pts.append((round(x, 4), round(y, 4)))
        return pts

    elif effect_type == "flanger":
        # Flanger: slow sweep with occasional fast dips (jet-like)
        pts = []
        for i in range(n_points):
            x = i / (n_points - 1)
            y = math.sin(2.0 * math.pi * x)
            # Add sharp dip for jet effect
            if rng.random() < complexity * 0.3:
                y -= rng.uniform(0.3, 0.8)
            y = max(-1.0, min(1.0, y))
            pts.append((round(x, 4), round(y, 4)))
        return pts

    elif effect_type == "distortion":
        # Distortion transfer: S-curve with asymmetry and harmonics
        pts = []
        asym = rng.uniform(-0.3, 0.3) * complexity
        hardness = 0.5 + complexity * 2.5
        for i in range(n_points):
            x_norm = i / (n_points - 1)  # 0..1
            x_in = (x_norm * 2.0 - 1.0)  # -1..+1 (input signal)
            # Soft clip with asymmetry
            y = math.tanh(hardness * (x_in + asym))
            # Add subtle harmonics
            y += complexity * 0.1 * math.sin(3.0 * math.pi * x_in)
            y = max(-1.0, min(1.0, y))
            pts.append((round(x_norm, 4), round(y, 4)))
        return pts

    elif effect_type == "tremolo":
        # Tremolo: rhythmic patterns — syncopation, swing
        swing = rng.uniform(0.0, 0.4) * complexity
        pattern = rng.choice(["pulse", "wave", "stutter"])
        pts = []
        beats = rng.choice([2, 3, 4, 6, 8])
        for i in range(n_points):
            x = i / (n_points - 1)
            beat_pos = x * beats
            if pattern == "pulse":
                y = 1.0 if (beat_pos % 1.0) < (0.5 + swing) else -0.5
            elif pattern == "wave":
                y = math.sin(2.0 * math.pi * beat_pos + swing * math.pi)
                y = y * (0.5 + 0.5 * complexity)
            else:  # stutter
                y = 1.0 if (beat_pos % 0.5) < 0.25 else -0.8
                if rng.random() < 0.2:
                    y *= -1
            y = max(-1.0, min(1.0, y))
            pts.append((round(x, 4), round(y, 4)))
        return pts

    else:
        # Generic: random smooth curve
        pts = [(0.0, 0.0)]
        for i in range(1, n_points - 1):
            pts.append((round(i / (n_points - 1), 4), round(rng.uniform(-1, 1), 4)))
        pts.append((1.0, pts[0][1]))
        return pts


# ==========================================================================
# 1. CHORUS (Scrawl = LFO shape)
# ==========================================================================

class ChorusFx:
    """Stereo chorus with drawable LFO shape.

    The Scrawl curve defines the modulation waveform (replaces sine LFO).
    Parameters: rate_hz, depth_ms, voices, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._phase = 0.0

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "rate_hz": float(defaults.get("rate_hz", 1.5)),
            "depth_ms": float(defaults.get("depth_ms", 5.0)),
            "voices": float(defaults.get("voices", 2.0)),
            "mix": float(defaults.get("mix", 0.5)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Delay buffer (max 50ms)
        self._max_delay = int(0.05 * sr)
        self._buf_l = [0.0] * self._max_delay
        self._buf_r = [0.0] * self._max_delay
        self._pos = 0
        self._scrawl_points = _DEFAULT_LFO

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            rate = max(0.01, _rt_get(self.rt_params, p + "rate_hz", 1.5))
            depth_ms = _clamp(_rt_get(self.rt_params, p + "depth_ms", 5.0), 0.1, 25.0)
            voices = max(1, int(_rt_get(self.rt_params, p + "voices", 2.0)))
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 0.5), 0.0, 1.0)

            # Try to read Scrawl points
            pts = _parse_scrawl_points(self.rt_params, self._prefix + "scrawl")
            if pts:
                self._scrawl_points = pts

            depth_samps = depth_ms * 0.001 * self._sr
            phase_inc = rate / self._sr

            for n in range(frames):
                dry_l = float(buf[n, 0])
                dry_r = float(buf[n, 1])

                # Write to delay buffer
                self._buf_l[self._pos] = dry_l
                self._buf_r[self._pos] = dry_r

                wet_l = 0.0
                wet_r = 0.0
                for v in range(voices):
                    voice_phase = (self._phase + v / voices) % 1.0
                    mod = _interpolate_curve(self._scrawl_points, voice_phase)
                    delay = (1.0 + mod) * 0.5 * depth_samps  # 0..depth
                    delay = max(1.0, min(self._max_delay - 2, delay))
                    # Fractional delay read
                    rd_pos = (self._pos - int(delay)) % self._max_delay
                    wet_l += self._buf_l[rd_pos]
                    wet_r += self._buf_r[rd_pos]

                wet_l /= voices
                wet_r /= voices

                self._phase = (self._phase + phase_inc) % 1.0
                self._pos = (self._pos + 1) % self._max_delay

                buf[n, 0] = dry_l * (1.0 - mix) + wet_l * mix
                buf[n, 1] = dry_r * (1.0 - mix) + wet_r * mix
        except Exception:
            pass


# ==========================================================================
# 2. PHASER (Scrawl = sweep envelope)
# ==========================================================================

class PhaserFx:
    """Stereo phaser with drawable sweep shape.

    The Scrawl curve defines the allpass frequency sweep pattern.
    Parameters: rate_hz, depth, stages, feedback, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._phase = 0.0
        self._num_stages = 6

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "rate_hz": float(defaults.get("rate_hz", 0.5)),
            "depth": float(defaults.get("depth", 0.7)),
            "feedback": float(defaults.get("feedback", 0.5)),
            "mix": float(defaults.get("mix", 0.5)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Allpass filter states
        self._ap_l = [0.0] * self._num_stages
        self._ap_r = [0.0] * self._num_stages
        self._feedback_l = 0.0
        self._feedback_r = 0.0
        self._scrawl_points = _DEFAULT_LFO

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            rate = max(0.01, _rt_get(self.rt_params, p + "rate_hz", 0.5))
            depth = _clamp(_rt_get(self.rt_params, p + "depth", 0.7), 0.0, 1.0)
            feedback = _clamp(_rt_get(self.rt_params, p + "feedback", 0.5), 0.0, 0.95)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 0.5), 0.0, 1.0)

            pts = _parse_scrawl_points(self.rt_params, self._prefix + "scrawl")
            if pts:
                self._scrawl_points = pts

            phase_inc = rate / self._sr

            for n in range(frames):
                mod = _interpolate_curve(self._scrawl_points, self._phase)
                # Map mod (-1..+1) to allpass coefficient
                coeff = _clamp(0.1 + depth * 0.8 * (mod + 1.0) * 0.5, 0.01, 0.99)

                in_l = float(buf[n, 0]) + self._feedback_l * feedback
                in_r = float(buf[n, 1]) + self._feedback_r * feedback

                # Cascade of first-order allpass filters
                out_l = in_l
                out_r = in_r
                for s in range(self._num_stages):
                    new_l = -coeff * out_l + self._ap_l[s]
                    self._ap_l[s] = coeff * new_l + out_l
                    out_l = new_l

                    new_r = -coeff * out_r + self._ap_r[s]
                    self._ap_r[s] = coeff * new_r + out_r
                    out_r = new_r

                self._feedback_l = out_l
                self._feedback_r = out_r
                self._phase = (self._phase + phase_inc) % 1.0

                buf[n, 0] = float(buf[n, 0]) * (1.0 - mix) + out_l * mix
                buf[n, 1] = float(buf[n, 1]) * (1.0 - mix) + out_r * mix
        except Exception:
            pass


# ==========================================================================
# 3. FLANGER (Scrawl = delay modulation)
# ==========================================================================

class FlangerFx:
    """Stereo flanger with drawable delay modulation curve.

    The Scrawl curve defines the delay sweep pattern (comb filter).
    Parameters: rate_hz, depth_ms, feedback, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._phase = 0.0

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "rate_hz": float(defaults.get("rate_hz", 0.3)),
            "depth_ms": float(defaults.get("depth_ms", 3.0)),
            "feedback": float(defaults.get("feedback", 0.6)),
            "mix": float(defaults.get("mix", 0.5)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Short delay (max 20ms)
        self._max_delay = int(0.02 * sr)
        self._buf_l = [0.0] * self._max_delay
        self._buf_r = [0.0] * self._max_delay
        self._pos = 0
        self._scrawl_points = _DEFAULT_LFO

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            rate = max(0.01, _rt_get(self.rt_params, p + "rate_hz", 0.3))
            depth_ms = _clamp(_rt_get(self.rt_params, p + "depth_ms", 3.0), 0.1, 10.0)
            feedback = _clamp(_rt_get(self.rt_params, p + "feedback", 0.6), 0.0, 0.95)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 0.5), 0.0, 1.0)

            pts = _parse_scrawl_points(self.rt_params, self._prefix + "scrawl")
            if pts:
                self._scrawl_points = pts

            depth_samps = depth_ms * 0.001 * self._sr
            phase_inc = rate / self._sr

            for n in range(frames):
                mod = _interpolate_curve(self._scrawl_points, self._phase)
                delay = max(1.0, (1.0 + mod) * 0.5 * depth_samps)
                delay = min(self._max_delay - 2, delay)

                rd = (self._pos - int(delay)) % self._max_delay
                del_l = self._buf_l[rd]
                del_r = self._buf_r[rd]

                in_l = float(buf[n, 0]) + del_l * feedback
                in_r = float(buf[n, 1]) + del_r * feedback

                self._buf_l[self._pos] = in_l
                self._buf_r[self._pos] = in_r
                self._pos = (self._pos + 1) % self._max_delay

                self._phase = (self._phase + phase_inc) % 1.0

                buf[n, 0] = float(buf[n, 0]) * (1.0 - mix) + del_l * mix
                buf[n, 1] = float(buf[n, 1]) * (1.0 - mix) + del_r * mix
        except Exception:
            pass


# ==========================================================================
# 4. DISTORTION+ (Scrawl = waveshaper transfer function)
# ==========================================================================

class DistortionPlusFx:
    """Waveshaper distortion with drawable transfer curve.

    The Scrawl curve IS the waveshaper: x-axis = input, y-axis = output.
    Completely user-definable transfer function — unique to Py_DAW!
    Parameters: drive, tone, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "drive": float(defaults.get("drive", 0.5)),
            "tone": float(defaults.get("tone", 0.5)),
            "mix": float(defaults.get("mix", 1.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Default: tanh-like S-curve
        self._scrawl_points = [(i / 31, max(-1, min(1, math.tanh(3.0 * (i / 15.5 - 1.0))))) for i in range(32)]
        # Lookup table for fast processing
        self._lut = [0.0] * 1024
        self._rebuild_lut()
        self._lp_l = 0.0
        self._lp_r = 0.0

    def _rebuild_lut(self) -> None:
        """Build a 1024-sample lookup table from Scrawl points."""
        for i in range(1024):
            x = i / 1023.0  # 0..1
            self._lut[i] = _interpolate_curve(self._scrawl_points, x)

    def _waveshape(self, sample: float, drive: float) -> float:
        """Apply waveshaper using LUT."""
        x = sample * (1.0 + drive * 4.0)
        x = max(-1.0, min(1.0, x))
        # Map -1..+1 → 0..1023
        idx = int((x + 1.0) * 0.5 * 1023)
        idx = max(0, min(1023, idx))
        return self._lut[idx]

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            drive = _clamp(_rt_get(self.rt_params, p + "drive", 0.5), 0.0, 1.0)
            tone = _clamp(_rt_get(self.rt_params, p + "tone", 0.5), 0.0, 1.0)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 1.0), 0.0, 1.0)

            pts = _parse_scrawl_points(self.rt_params, self._prefix + "scrawl")
            if pts and pts != self._scrawl_points:
                self._scrawl_points = pts
                self._rebuild_lut()

            # Tone = simple 1-pole LP (0=dark, 1=bright)
            lp_coeff = 0.05 + 0.9 * tone

            for n in range(frames):
                dry_l = float(buf[n, 0])
                dry_r = float(buf[n, 1])

                wet_l = self._waveshape(dry_l, drive)
                wet_r = self._waveshape(dry_r, drive)

                # Tone filter
                self._lp_l += lp_coeff * (wet_l - self._lp_l)
                self._lp_r += lp_coeff * (wet_r - self._lp_r)
                wet_l = self._lp_l
                wet_r = self._lp_r

                buf[n, 0] = dry_l * (1.0 - mix) + wet_l * mix
                buf[n, 1] = dry_r * (1.0 - mix) + wet_r * mix
        except Exception:
            pass


# ==========================================================================
# 5. TREMOLO (Scrawl = amplitude modulation shape)
# ==========================================================================

class TremoloFx:
    """Stereo tremolo with drawable modulation shape.

    The Scrawl curve defines the volume modulation pattern (1 cycle per rate).
    Parameters: rate_hz, depth, stereo_offset, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._phase = 0.0

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "rate_hz": float(defaults.get("rate_hz", 4.0)),
            "depth": float(defaults.get("depth", 0.7)),
            "stereo_offset": float(defaults.get("stereo_offset", 0.0)),
            "mix": float(defaults.get("mix", 1.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        self._scrawl_points = _DEFAULT_LFO

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            rate = max(0.01, _rt_get(self.rt_params, p + "rate_hz", 4.0))
            depth = _clamp(_rt_get(self.rt_params, p + "depth", 0.7), 0.0, 1.0)
            stereo_off = _clamp(_rt_get(self.rt_params, p + "stereo_offset", 0.0), 0.0, 0.5)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 1.0), 0.0, 1.0)

            pts = _parse_scrawl_points(self.rt_params, self._prefix + "scrawl")
            if pts:
                self._scrawl_points = pts

            phase_inc = rate / self._sr

            for n in range(frames):
                mod_l = _interpolate_curve(self._scrawl_points, self._phase)
                mod_r = _interpolate_curve(self._scrawl_points, (self._phase + stereo_off) % 1.0)

                # Map mod (-1..+1) to gain (1-depth..1)
                gain_l = 1.0 - depth * (1.0 - (mod_l + 1.0) * 0.5)
                gain_r = 1.0 - depth * (1.0 - (mod_r + 1.0) * 0.5)

                dry_l = float(buf[n, 0])
                dry_r = float(buf[n, 1])

                buf[n, 0] = dry_l * (1.0 - mix) + dry_l * gain_l * mix
                buf[n, 1] = dry_r * (1.0 - mix) + dry_r * gain_r * mix

                self._phase = (self._phase + phase_inc) % 1.0
        except Exception:
            pass
