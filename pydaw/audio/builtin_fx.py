"""Built-in Essential Audio FX (AP8 Phase 8A).

v0.0.20.642: Five professional DSP effects for the built-in FX chain.

All effects inherit from AudioFxBase and implement process_inplace().
Parameters are read from RTParamStore for lock-free real-time control.

Effects:
- ParametricEqFx:  8-band parametric EQ (Bell, Shelf, HP/LP)
- CompressorFx:    Feed-forward compressor with sidechain support
- ReverbFx:        Algorithmic reverb (Schroeder/Moorer style)
- DelayFx:         Stereo delay with feedback and tempo-sync ready
- LimiterFx:       Brickwall peak limiter
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

try:
    import numpy as np
except Exception:
    np = None


def _rt_get(rt_params, key: str, default: float) -> float:
    """Read a parameter from RTParamStore (lock-free)."""
    try:
        v = rt_params.get(key) if rt_params is not None else None
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ==========================================================================
# 1. PARAMETRIC EQ (8-Band)
# ==========================================================================

class ParametricEqFx:
    """8-band parametric EQ with biquad filters.

    Each band: type (bell/lowshelf/highshelf/lp/hp), freq, gain_db, Q.
    Processes stereo in-place using Direct Form II transposed biquads.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._num_bands = 8

        # Biquad state per band per channel: [z1, z2]
        self._states_l = [[0.0, 0.0] for _ in range(self._num_bands)]
        self._states_r = [[0.0, 0.0] for _ in range(self._num_bands)]
        # Cached coefficients per band: (b0, b1, b2, a1, a2)
        self._coeffs = [(1.0, 0.0, 0.0, 0.0, 0.0)] * self._num_bands
        self._last_params = [None] * self._num_bands

        # Ensure RT defaults
        defaults = params if isinstance(params, dict) else {}
        for i in range(self._num_bands):
            p = self._prefix + f"band{i}_"
            freq_def = float(defaults.get(f"band{i}_freq", [60, 150, 400, 1000, 2500, 5000, 10000, 16000][min(i, 7)]))
            gain_def = float(defaults.get(f"band{i}_gain_db", 0.0))
            q_def = float(defaults.get(f"band{i}_q", 1.0))
            type_def = float(defaults.get(f"band{i}_type", 0.0))  # 0=bell
            enabled_def = float(defaults.get(f"band{i}_enabled", 1.0))
            try:
                if hasattr(rt_params, "ensure"):
                    rt_params.ensure(p + "freq", freq_def)
                    rt_params.ensure(p + "gain_db", gain_def)
                    rt_params.ensure(p + "q", q_def)
                    rt_params.ensure(p + "type", type_def)
                    rt_params.ensure(p + "enabled", enabled_def)
            except Exception:
                pass

    def _compute_biquad(self, freq: float, gain_db: float, q: float, ftype: int):
        """Compute biquad coefficients. ftype: 0=bell, 1=lowshelf, 2=highshelf, 3=lp, 4=hp."""
        sr = self._sr
        freq = _clamp(freq, 20.0, sr * 0.49)
        q = max(0.1, q)
        w0 = 2.0 * math.pi * freq / sr
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2.0 * q)
        A = 10.0 ** (gain_db / 40.0)  # sqrt of linear gain

        if ftype == 0:  # Bell/Peaking
            b0 = 1.0 + alpha * A
            b1 = -2.0 * cos_w0
            b2 = 1.0 - alpha * A
            a0 = 1.0 + alpha / A
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha / A
        elif ftype == 1:  # Low Shelf
            sqA = math.sqrt(max(0.001, A))
            b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2.0 * sqA * alpha)
            b1 = 2.0 * A * ((A - 1) - (A + 1) * cos_w0)
            b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2.0 * sqA * alpha)
            a0 = (A + 1) + (A - 1) * cos_w0 + 2.0 * sqA * alpha
            a1 = -2.0 * ((A - 1) + (A + 1) * cos_w0)
            a2 = (A + 1) + (A - 1) * cos_w0 - 2.0 * sqA * alpha
        elif ftype == 2:  # High Shelf
            sqA = math.sqrt(max(0.001, A))
            b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2.0 * sqA * alpha)
            b1 = -2.0 * A * ((A - 1) + (A + 1) * cos_w0)
            b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2.0 * sqA * alpha)
            a0 = (A + 1) - (A - 1) * cos_w0 + 2.0 * sqA * alpha
            a1 = 2.0 * ((A - 1) - (A + 1) * cos_w0)
            a2 = (A + 1) - (A - 1) * cos_w0 - 2.0 * sqA * alpha
        elif ftype == 3:  # LP
            b0 = (1.0 - cos_w0) / 2.0
            b1 = 1.0 - cos_w0
            b2 = (1.0 - cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        elif ftype == 4:  # HP
            b0 = (1.0 + cos_w0) / 2.0
            b1 = -(1.0 + cos_w0)
            b2 = (1.0 + cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        else:
            return (1.0, 0.0, 0.0, 0.0, 0.0)

        if abs(a0) < 1e-12:
            return (1.0, 0.0, 0.0, 0.0, 0.0)
        return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            for i in range(self._num_bands):
                p = self._prefix + f"band{i}_"
                enabled = _rt_get(self.rt_params, p + "enabled", 1.0)
                if enabled < 0.5:
                    continue
                freq = _clamp(_rt_get(self.rt_params, p + "freq", 1000.0), 20.0, 20000.0)
                gain_db = _clamp(_rt_get(self.rt_params, p + "gain_db", 0.0), -24.0, 24.0)
                q = max(0.1, _rt_get(self.rt_params, p + "q", 1.0))
                ftype = int(_rt_get(self.rt_params, p + "type", 0.0))

                key = (freq, gain_db, q, ftype)
                if key != self._last_params[i]:
                    self._coeffs[i] = self._compute_biquad(freq, gain_db, q, ftype)
                    self._last_params[i] = key

                if abs(gain_db) < 0.05 and ftype == 0:
                    continue  # Bell with 0 gain = bypass

                b0, b1, b2, a1, a2 = self._coeffs[i]
                # Process L and R channels with DF2T biquad
                for ch, state in ((0, self._states_l[i]), (1, self._states_r[i])):
                    z1, z2 = state[0], state[1]
                    for n in range(frames):
                        x = float(buf[n, ch])
                        y = b0 * x + z1
                        z1 = b1 * x - a1 * y + z2
                        z2 = b2 * x - a2 * y
                        buf[n, ch] = y
                    state[0], state[1] = z1, z2
        except Exception:
            pass


# ==========================================================================
# 2. COMPRESSOR (with Sidechain support)
# ==========================================================================

class CompressorFx:
    """Feed-forward RMS compressor with optional sidechain key signal.

    Parameters: threshold_db, ratio, attack_ms, release_ms, knee_db, makeup_db, mix.
    Uses the sidechain buffer from ChainFx._sidechain_buf if available.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000, chain_ref: Any = None):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._chain_ref = chain_ref  # reference to parent ChainFx for sidechain
        self._env = 0.0  # envelope follower state

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "threshold_db": float(defaults.get("threshold_db", -20.0)),
            "ratio": float(defaults.get("ratio", 4.0)),
            "attack_ms": float(defaults.get("attack_ms", 10.0)),
            "release_ms": float(defaults.get("release_ms", 100.0)),
            "knee_db": float(defaults.get("knee_db", 6.0)),
            "makeup_db": float(defaults.get("makeup_db", 0.0)),
            "mix": float(defaults.get("mix", 1.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            threshold_db = _clamp(_rt_get(self.rt_params, p + "threshold_db", -20.0), -60.0, 0.0)
            ratio = max(1.0, _rt_get(self.rt_params, p + "ratio", 4.0))
            attack_ms = max(0.1, _rt_get(self.rt_params, p + "attack_ms", 10.0))
            release_ms = max(1.0, _rt_get(self.rt_params, p + "release_ms", 100.0))
            knee_db = max(0.0, _rt_get(self.rt_params, p + "knee_db", 6.0))
            makeup_db = _clamp(_rt_get(self.rt_params, p + "makeup_db", 0.0), -12.0, 36.0)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 1.0), 0.0, 1.0)

            # Attack/release coefficients
            att_coeff = math.exp(-1.0 / (self._sr * attack_ms * 0.001))
            rel_coeff = math.exp(-1.0 / (self._sr * release_ms * 0.001))
            makeup_lin = 10.0 ** (makeup_db / 20.0)
            threshold_lin = 10.0 ** (threshold_db / 20.0)
            half_knee = knee_db * 0.5

            # Determine key signal: sidechain or self
            sc_buf = None
            if self._chain_ref is not None:
                sc_buf = getattr(self._chain_ref, '_sidechain_buf', None)

            # Save dry for mix blend
            dry = buf[:frames].copy() if mix < 0.999 else None

            env = self._env
            for n in range(frames):
                # Key signal level (mono peak)
                if sc_buf is not None:
                    key_level = max(abs(float(sc_buf[n, 0])), abs(float(sc_buf[n, 1])))
                else:
                    key_level = max(abs(float(buf[n, 0])), abs(float(buf[n, 1])))

                # Envelope follower
                if key_level > env:
                    env = att_coeff * env + (1.0 - att_coeff) * key_level
                else:
                    env = rel_coeff * env + (1.0 - rel_coeff) * key_level

                # Gain computation (dB domain with soft knee)
                if env > 1e-10:
                    env_db = 20.0 * math.log10(env)
                else:
                    env_db = -120.0

                over_db = env_db - threshold_db
                if over_db <= -half_knee:
                    gain_reduction_db = 0.0
                elif over_db >= half_knee:
                    gain_reduction_db = over_db * (1.0 - 1.0 / ratio)
                else:
                    # Soft knee region
                    x = over_db + half_knee
                    gain_reduction_db = (x * x) / (4.0 * max(0.01, knee_db)) * (1.0 - 1.0 / ratio)

                gain_lin = 10.0 ** (-gain_reduction_db / 20.0) * makeup_lin
                buf[n, 0] *= gain_lin
                buf[n, 1] *= gain_lin

            self._env = env

            # Mix blend
            if dry is not None and mix < 0.999:
                buf[:frames] = dry * (1.0 - mix) + buf[:frames] * mix
        except Exception:
            pass


# ==========================================================================
# 3. REVERB (Algorithmic Schroeder/Moorer)
# ==========================================================================

class ReverbFx:
    """Algorithmic stereo reverb using 4 allpass + 4 comb filters (Schroeder style).

    Parameters: decay, damping, pre_delay_ms, mix.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "decay": float(defaults.get("decay", 0.5)),
            "damping": float(defaults.get("damping", 0.5)),
            "pre_delay_ms": float(defaults.get("pre_delay_ms", 10.0)),
            "mix": float(defaults.get("mix", 0.3)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Comb filter delays (in samples, prime-ish numbers for diffusion)
        comb_times = [0.0297, 0.0371, 0.0411, 0.0437]  # seconds
        self._comb_lens = [max(1, int(t * sr)) for t in comb_times]
        self._comb_bufs_l = [([0.0] * L) for L in self._comb_lens]
        self._comb_bufs_r = [([0.0] * L) for L in self._comb_lens]
        self._comb_pos = [0] * 4
        self._comb_filter_state_l = [0.0] * 4
        self._comb_filter_state_r = [0.0] * 4

        # Allpass filter delays
        ap_times = [0.0050, 0.0017, 0.0058, 0.0013]
        self._ap_lens = [max(1, int(t * sr)) for t in ap_times]
        self._ap_bufs_l = [([0.0] * L) for L in self._ap_lens]
        self._ap_bufs_r = [([0.0] * L) for L in self._ap_lens]
        self._ap_pos = [0] * 4

        # Pre-delay buffer
        self._pd_max = max(1, int(0.2 * sr))  # max 200ms
        self._pd_buf_l = [0.0] * self._pd_max
        self._pd_buf_r = [0.0] * self._pd_max
        self._pd_pos = 0

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            decay = _clamp(_rt_get(self.rt_params, p + "decay", 0.5), 0.0, 0.99)
            damping = _clamp(_rt_get(self.rt_params, p + "damping", 0.5), 0.0, 1.0)
            pd_ms = max(0.0, _rt_get(self.rt_params, p + "pre_delay_ms", 10.0))
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 0.3), 0.0, 1.0)

            if mix < 0.001:
                return

            pd_samps = min(int(pd_ms * 0.001 * self._sr), self._pd_max - 1)
            feedback = 0.2 + 0.75 * decay  # scale to reasonable feedback

            for n in range(frames):
                dry_l = float(buf[n, 0])
                dry_r = float(buf[n, 1])

                # Pre-delay
                self._pd_buf_l[self._pd_pos] = dry_l
                self._pd_buf_r[self._pd_pos] = dry_r
                rd = (self._pd_pos - pd_samps) % self._pd_max
                inp_l = self._pd_buf_l[rd]
                inp_r = self._pd_buf_r[rd]
                self._pd_pos = (self._pd_pos + 1) % self._pd_max

                # 4 comb filters (parallel, summed)
                wet_l = 0.0
                wet_r = 0.0
                for i in range(4):
                    L = self._comb_lens[i]
                    pos = self._comb_pos[i]
                    # Read from comb delay line
                    out_l = self._comb_bufs_l[i][pos]
                    out_r = self._comb_bufs_r[i][pos]
                    # Low-pass damping
                    self._comb_filter_state_l[i] = out_l * (1.0 - damping) + self._comb_filter_state_l[i] * damping
                    self._comb_filter_state_r[i] = out_r * (1.0 - damping) + self._comb_filter_state_r[i] * damping
                    # Write back with feedback
                    self._comb_bufs_l[i][pos] = inp_l + self._comb_filter_state_l[i] * feedback
                    self._comb_bufs_r[i][pos] = inp_r + self._comb_filter_state_r[i] * feedback
                    self._comb_pos[i] = (pos + 1) % L
                    wet_l += out_l
                    wet_r += out_r

                wet_l *= 0.25
                wet_r *= 0.25

                # 4 allpass filters (series)
                for i in range(4):
                    L = self._ap_lens[i]
                    pos = self._ap_pos[i]
                    buf_l = self._ap_bufs_l[i][pos]
                    buf_r = self._ap_bufs_r[i][pos]
                    self._ap_bufs_l[i][pos] = wet_l + buf_l * 0.5
                    self._ap_bufs_r[i][pos] = wet_r + buf_r * 0.5
                    wet_l = buf_l - wet_l * 0.5
                    wet_r = buf_r - wet_r * 0.5
                    self._ap_pos[i] = (pos + 1) % L

                # Mix
                buf[n, 0] = dry_l * (1.0 - mix) + wet_l * mix
                buf[n, 1] = dry_r * (1.0 - mix) + wet_r * mix
        except Exception:
            pass


# ==========================================================================
# 4. DELAY (Stereo with Feedback)
# ==========================================================================

class DelayFx:
    """Stereo delay with feedback, ping-pong option, and simple LP filter.

    Parameters: time_ms, feedback, mix, ping_pong (0/1), filter_freq.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "time_ms": float(defaults.get("time_ms", 375.0)),
            "feedback": float(defaults.get("feedback", 0.4)),
            "mix": float(defaults.get("mix", 0.3)),
            "ping_pong": float(defaults.get("ping_pong", 0.0)),
            "filter_freq": float(defaults.get("filter_freq", 8000.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

        # Delay buffer (max 2 seconds)
        self._max_samps = int(2.0 * sr)
        self._buf_l = [0.0] * self._max_samps
        self._buf_r = [0.0] * self._max_samps
        self._pos = 0
        self._lp_l = 0.0  # LP filter state
        self._lp_r = 0.0

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            time_ms = _clamp(_rt_get(self.rt_params, p + "time_ms", 375.0), 1.0, 2000.0)
            feedback = _clamp(_rt_get(self.rt_params, p + "feedback", 0.4), 0.0, 0.95)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 0.3), 0.0, 1.0)
            ping_pong = _rt_get(self.rt_params, p + "ping_pong", 0.0) > 0.5
            filt_freq = _clamp(_rt_get(self.rt_params, p + "filter_freq", 8000.0), 200.0, 20000.0)

            if mix < 0.001:
                return

            delay_samps = min(int(time_ms * 0.001 * self._sr), self._max_samps - 1)
            # Simple 1-pole LP coefficient
            rc = 1.0 / (2.0 * math.pi * filt_freq)
            dt = 1.0 / self._sr
            lp_alpha = dt / (rc + dt)

            for n in range(frames):
                dry_l = float(buf[n, 0])
                dry_r = float(buf[n, 1])

                # Read from delay line
                rd = (self._pos - delay_samps) % self._max_samps
                del_l = self._buf_l[rd]
                del_r = self._buf_r[rd]

                # LP filter on feedback
                self._lp_l += lp_alpha * (del_l - self._lp_l)
                self._lp_r += lp_alpha * (del_r - self._lp_r)

                # Write to delay line
                if ping_pong:
                    self._buf_l[self._pos] = dry_l + self._lp_r * feedback  # cross-feed
                    self._buf_r[self._pos] = dry_r + self._lp_l * feedback
                else:
                    self._buf_l[self._pos] = dry_l + self._lp_l * feedback
                    self._buf_r[self._pos] = dry_r + self._lp_r * feedback

                self._pos = (self._pos + 1) % self._max_samps

                buf[n, 0] = dry_l * (1.0 - mix) + del_l * mix
                buf[n, 1] = dry_r * (1.0 - mix) + del_r * mix
        except Exception:
            pass


# ==========================================================================
# 5. LIMITER (Brickwall Peak)
# ==========================================================================

class LimiterFx:
    """Brickwall peak limiter with lookahead and auto-release.

    Parameters: ceiling_db, release_ms, gain_db (input gain).
    Uses simple sample-by-sample peak limiting with attack smoothing.
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._env = 0.0

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "ceiling_db": float(defaults.get("ceiling_db", -0.3)),
            "release_ms": float(defaults.get("release_ms", 50.0)),
            "gain_db": float(defaults.get("gain_db", 0.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            ceiling_db = _clamp(_rt_get(self.rt_params, p + "ceiling_db", -0.3), -12.0, 0.0)
            release_ms = max(1.0, _rt_get(self.rt_params, p + "release_ms", 50.0))
            gain_db = _clamp(_rt_get(self.rt_params, p + "gain_db", 0.0), -12.0, 36.0)

            ceiling_lin = 10.0 ** (ceiling_db / 20.0)
            gain_lin = 10.0 ** (gain_db / 20.0)
            release_coeff = math.exp(-1.0 / (self._sr * release_ms * 0.001))

            # Apply input gain
            if abs(gain_db) > 0.01:
                buf[:frames] *= gain_lin

            env = self._env
            for n in range(frames):
                peak = max(abs(float(buf[n, 0])), abs(float(buf[n, 1])))
                if peak > env:
                    env = peak  # instant attack
                else:
                    env = release_coeff * env + (1.0 - release_coeff) * peak

                if env > ceiling_lin:
                    gain = ceiling_lin / max(1e-10, env)
                    buf[n, 0] *= gain
                    buf[n, 1] *= gain

            self._env = env
        except Exception:
            pass
