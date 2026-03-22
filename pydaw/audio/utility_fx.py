"""Built-in Utility Audio FX (AP8 Phase 8C).

v0.0.20.644: Five professional utility effects for the built-in FX chain.

All effects inherit the same interface as Phase 8A/8B effects:
- __init__(track_id, device_id, rt_params, params, sr, **kw)
- process_inplace(buf, frames, sr) → modifies numpy stereo buffer in-place

Effects:
- GateFx:            Noise gate with threshold, attack, hold, release, sidechain
- DeEsserFx:         Frequency-selective compressor for sibilance control
- StereoWidenerFx:   Mid/Side based stereo width control
- UtilityFx:         Gain, phase invert, mono, DC offset removal
- SpectrumAnalyzerFx: FFT analysis with peak hold (pass-through, metering only)
"""

from __future__ import annotations

import math
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
# 1. GATE (Noise Gate with Sidechain)
# ==========================================================================

class GateFx:
    """Noise gate with configurable threshold, attack, hold, release.

    Supports external sidechain via ChainFx._sidechain_buf (same as CompressorFx).

    Parameters:
        threshold_db: Gate open threshold (-80..0 dB, default -40)
        attack_ms:    Attack time (0.01..50 ms, default 0.5)
        hold_ms:      Hold time before release (0..500 ms, default 50)
        release_ms:   Release time (1..2000 ms, default 100)
        range_db:     Attenuation when closed (-inf..-1 dB, default -80)
        mix:          Dry/wet mix (0..1, default 1.0)
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000, chain_ref: Any = None):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._chain_ref = chain_ref  # for sidechain access
        self._env = 0.0        # envelope follower state
        self._gate_gain = 0.0  # current gate gain (0=closed, 1=open)
        self._hold_counter = 0  # samples remaining in hold phase

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "threshold_db": float(defaults.get("threshold_db", -40.0)),
            "attack_ms": float(defaults.get("attack_ms", 0.5)),
            "hold_ms": float(defaults.get("hold_ms", 50.0)),
            "release_ms": float(defaults.get("release_ms", 100.0)),
            "range_db": float(defaults.get("range_db", -80.0)),
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
            threshold_db = _clamp(_rt_get(self.rt_params, p + "threshold_db", -40.0), -80.0, 0.0)
            attack_ms = max(0.01, _rt_get(self.rt_params, p + "attack_ms", 0.5))
            hold_ms = max(0.0, _rt_get(self.rt_params, p + "hold_ms", 50.0))
            release_ms = max(1.0, _rt_get(self.rt_params, p + "release_ms", 100.0))
            range_db = _clamp(_rt_get(self.rt_params, p + "range_db", -80.0), -80.0, -1.0)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 1.0), 0.0, 1.0)

            if mix < 0.001:
                return

            threshold_lin = 10.0 ** (threshold_db / 20.0)
            range_lin = 10.0 ** (range_db / 20.0)
            attack_coeff = math.exp(-1.0 / (self._sr * attack_ms * 0.001))
            release_coeff = math.exp(-1.0 / (self._sr * release_ms * 0.001))
            hold_samps = int(hold_ms * 0.001 * self._sr)

            # Sidechain buffer (if available)
            sc_buf = None
            if self._chain_ref is not None:
                sc_buf = getattr(self._chain_ref, '_sidechain_buf', None)

            env = self._env
            gate_gain = self._gate_gain
            hold_counter = self._hold_counter

            for n in range(frames):
                # Detect level from sidechain or main input
                if sc_buf is not None and n < sc_buf.shape[0]:
                    level = max(abs(float(sc_buf[n, 0])), abs(float(sc_buf[n, 1])))
                else:
                    level = max(abs(float(buf[n, 0])), abs(float(buf[n, 1])))

                # Envelope follower (peak)
                if level > env:
                    env = level
                else:
                    env = release_coeff * env + (1.0 - release_coeff) * level

                # Gate logic
                if env >= threshold_lin:
                    # Gate open
                    hold_counter = hold_samps
                    target = 1.0
                elif hold_counter > 0:
                    # Hold phase
                    hold_counter -= 1
                    target = 1.0
                else:
                    # Gate closing
                    target = range_lin

                # Smooth gain transitions
                if target > gate_gain:
                    # Opening (attack)
                    gate_gain = (1.0 - attack_coeff) * target + attack_coeff * gate_gain
                else:
                    # Closing (release)
                    gate_gain = (1.0 - release_coeff) * target + release_coeff * gate_gain

                # Apply gate gain with dry/wet mix
                gated_l = float(buf[n, 0]) * gate_gain
                gated_r = float(buf[n, 1]) * gate_gain
                buf[n, 0] = float(buf[n, 0]) * (1.0 - mix) + gated_l * mix
                buf[n, 1] = float(buf[n, 1]) * (1.0 - mix) + gated_r * mix

            self._env = env
            self._gate_gain = gate_gain
            self._hold_counter = hold_counter
        except Exception:
            pass


# ==========================================================================
# 2. DE-ESSER (Frequency-selective Compressor)
# ==========================================================================

class DeEsserFx:
    """Frequency-selective compressor targeting sibilance.

    Uses a bandpass filter to isolate the sibilance band, then applies
    gain reduction to the full signal when the band exceeds the threshold.

    Parameters:
        frequency:     Center frequency of detection band (2000..16000 Hz, default 6500)
        threshold_db:  Sibilance detection threshold (-40..0 dB, default -20)
        range_db:      Maximum reduction amount (0..24 dB, default 6)
        attack_ms:     Detector attack (0.01..10 ms, default 0.1)
        release_ms:    Detector release (10..200 ms, default 50)
        listen:        Solo the detection band (0/1, default 0)
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._env = 0.0  # envelope for detection
        # Biquad state for bandpass (L+R detection)
        self._bp_z1_l = 0.0
        self._bp_z2_l = 0.0
        self._bp_z1_r = 0.0
        self._bp_z2_r = 0.0
        self._bp_coeffs = (0.0, 0.0, 0.0, 0.0, 0.0)
        self._last_bp_params = None

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "frequency": float(defaults.get("frequency", 6500.0)),
            "threshold_db": float(defaults.get("threshold_db", -20.0)),
            "range_db": float(defaults.get("range_db", 6.0)),
            "attack_ms": float(defaults.get("attack_ms", 0.1)),
            "release_ms": float(defaults.get("release_ms", 50.0)),
            "listen": float(defaults.get("listen", 0.0)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

    def _compute_bandpass(self, freq: float, q: float = 2.0):
        """Compute biquad bandpass coefficients."""
        sr = self._sr
        freq = _clamp(freq, 100.0, sr * 0.49)
        w0 = 2.0 * math.pi * freq / sr
        alpha = math.sin(w0) / (2.0 * q)
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0 = 1.0 + alpha
        a1 = -2.0 * math.cos(w0)
        a2 = 1.0 - alpha
        if abs(a0) < 1e-12:
            return (0.0, 0.0, 0.0, 0.0, 0.0)
        return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

    def _apply_biquad(self, x: float, z1: float, z2: float, coeffs: tuple):
        """Apply DF2T biquad filter, return (output, new_z1, new_z2)."""
        b0, b1, b2, a1, a2 = coeffs
        y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        return y, z1, z2

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            freq = _clamp(_rt_get(self.rt_params, p + "frequency", 6500.0), 2000.0, 16000.0)
            threshold_db = _clamp(_rt_get(self.rt_params, p + "threshold_db", -20.0), -40.0, 0.0)
            range_db = _clamp(_rt_get(self.rt_params, p + "range_db", 6.0), 0.0, 24.0)
            attack_ms = max(0.01, _rt_get(self.rt_params, p + "attack_ms", 0.1))
            release_ms = max(1.0, _rt_get(self.rt_params, p + "release_ms", 50.0))
            listen = _rt_get(self.rt_params, p + "listen", 0.0) > 0.5

            threshold_lin = 10.0 ** (threshold_db / 20.0)
            attack_coeff = math.exp(-1.0 / (self._sr * attack_ms * 0.001))
            release_coeff = math.exp(-1.0 / (self._sr * release_ms * 0.001))
            # Max reduction in linear
            max_reduction = 10.0 ** (-range_db / 20.0)

            # Update bandpass if params changed
            bp_key = (freq,)
            if bp_key != self._last_bp_params:
                self._bp_coeffs = self._compute_bandpass(freq, q=2.0)
                self._last_bp_params = bp_key

            env = self._env
            z1_l, z2_l = self._bp_z1_l, self._bp_z2_l
            z1_r, z2_r = self._bp_z1_r, self._bp_z2_r
            coeffs = self._bp_coeffs

            for n in range(frames):
                in_l = float(buf[n, 0])
                in_r = float(buf[n, 1])

                # Bandpass filter for detection
                bp_l, z1_l, z2_l = self._apply_biquad(in_l, z1_l, z2_l, coeffs)
                bp_r, z1_r, z2_r = self._apply_biquad(in_r, z1_r, z2_r, coeffs)

                if listen:
                    # Solo detection band
                    buf[n, 0] = bp_l
                    buf[n, 1] = bp_r
                    continue

                # Envelope follower on detected band
                det_level = max(abs(bp_l), abs(bp_r))
                if det_level > env:
                    env = (1.0 - attack_coeff) * det_level + attack_coeff * env
                else:
                    env = (1.0 - release_coeff) * det_level + release_coeff * env

                # Compute gain reduction
                if env > threshold_lin and threshold_lin > 1e-12:
                    # How much over threshold (in dB)
                    over_db = 20.0 * math.log10(max(1e-12, env / threshold_lin))
                    # Apply reduction proportionally, capped at range_db
                    reduce_db = min(over_db, range_db)
                    gain = 10.0 ** (-reduce_db / 20.0)
                else:
                    gain = 1.0

                buf[n, 0] = in_l * gain
                buf[n, 1] = in_r * gain

            self._env = env
            self._bp_z1_l, self._bp_z2_l = z1_l, z2_l
            self._bp_z1_r, self._bp_z2_r = z1_r, z2_r
        except Exception:
            pass


# ==========================================================================
# 3. STEREO WIDENER (Mid/Side based)
# ==========================================================================

class StereoWidenerFx:
    """Mid/Side stereo width control.

    Encodes L/R to Mid/Side, adjusts balance, decodes back.
    Width=0 → mono, width=1 → normal, width=2 → extra wide.

    Parameters:
        width:       Stereo width (0..2, default 1.0; 0=mono, 1=original, 2=wide)
        mid_gain_db: Mid channel gain (-12..12 dB, default 0)
        side_gain_db: Side channel gain (-12..12 dB, default 0)
        mix:         Dry/wet mix (0..1, default 1.0)
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "width": float(defaults.get("width", 1.0)),
            "mid_gain_db": float(defaults.get("mid_gain_db", 0.0)),
            "side_gain_db": float(defaults.get("side_gain_db", 0.0)),
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
            width = _clamp(_rt_get(self.rt_params, p + "width", 1.0), 0.0, 2.0)
            mid_gain_db = _clamp(_rt_get(self.rt_params, p + "mid_gain_db", 0.0), -12.0, 12.0)
            side_gain_db = _clamp(_rt_get(self.rt_params, p + "side_gain_db", 0.0), -12.0, 12.0)
            mix = _clamp(_rt_get(self.rt_params, p + "mix", 1.0), 0.0, 1.0)

            if mix < 0.001:
                return

            mid_gain = 10.0 ** (mid_gain_db / 20.0)
            side_gain = 10.0 ** (side_gain_db / 20.0) * width

            for n in range(frames):
                l = float(buf[n, 0])
                r = float(buf[n, 1])

                # Encode to Mid/Side
                mid = (l + r) * 0.5
                side = (l - r) * 0.5

                # Apply gains
                mid *= mid_gain
                side *= side_gain

                # Decode back to L/R
                wet_l = mid + side
                wet_r = mid - side

                # Mix
                buf[n, 0] = l * (1.0 - mix) + wet_l * mix
                buf[n, 1] = r * (1.0 - mix) + wet_r * mix
        except Exception:
            pass


# ==========================================================================
# 4. UTILITY (Gain, Phase, Mono, DC Offset)
# ==========================================================================

class UtilityFx:
    """Swiss-army-knife utility plugin.

    Parameters:
        gain_db:       Gain adjustment (-inf..+36 dB, default 0)
        pan:           Stereo pan (-1..+1, default 0)
        phase_invert_l: Invert left phase (0/1, default 0)
        phase_invert_r: Invert right phase (0/1, default 0)
        mono:          Sum to mono (0/1, default 0)
        dc_block:      Remove DC offset (0/1, default 1)
        channel_swap:  Swap L/R channels (0/1, default 0)
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        # DC blocker state (1-pole HP at ~5 Hz)
        self._dc_x_l = 0.0
        self._dc_y_l = 0.0
        self._dc_x_r = 0.0
        self._dc_y_r = 0.0

        defaults = params if isinstance(params, dict) else {}
        defs = {
            "gain_db": float(defaults.get("gain_db", 0.0)),
            "pan": float(defaults.get("pan", 0.0)),
            "phase_invert_l": float(defaults.get("phase_invert_l", 0.0)),
            "phase_invert_r": float(defaults.get("phase_invert_r", 0.0)),
            "mono": float(defaults.get("mono", 0.0)),
            "dc_block": float(defaults.get("dc_block", 1.0)),
            "channel_swap": float(defaults.get("channel_swap", 0.0)),
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
            gain_db = _clamp(_rt_get(self.rt_params, p + "gain_db", 0.0), -96.0, 36.0)
            pan = _clamp(_rt_get(self.rt_params, p + "pan", 0.0), -1.0, 1.0)
            phase_inv_l = _rt_get(self.rt_params, p + "phase_invert_l", 0.0) > 0.5
            phase_inv_r = _rt_get(self.rt_params, p + "phase_invert_r", 0.0) > 0.5
            mono = _rt_get(self.rt_params, p + "mono", 0.0) > 0.5
            dc_block = _rt_get(self.rt_params, p + "dc_block", 1.0) > 0.5
            channel_swap = _rt_get(self.rt_params, p + "channel_swap", 0.0) > 0.5

            gain_lin = 10.0 ** (gain_db / 20.0) if gain_db > -95.0 else 0.0

            # Constant-power pan law
            # pan: -1=full left, 0=center, +1=full right
            pan_angle = (pan + 1.0) * 0.25 * math.pi  # 0..pi/2
            pan_l = math.cos(pan_angle)
            pan_r = math.sin(pan_angle)

            # DC blocker coefficient (~5 Hz HP at any sample rate)
            dc_coeff = 1.0 - (2.0 * math.pi * 5.0 / max(1, self._sr))
            dc_coeff = _clamp(dc_coeff, 0.9, 0.9999)

            dx_l, dy_l = self._dc_x_l, self._dc_y_l
            dx_r, dy_r = self._dc_x_r, self._dc_y_r

            for n in range(frames):
                l = float(buf[n, 0])
                r = float(buf[n, 1])

                # Channel swap
                if channel_swap:
                    l, r = r, l

                # Mono sum
                if mono:
                    m = (l + r) * 0.5
                    l = m
                    r = m

                # Phase invert
                if phase_inv_l:
                    l = -l
                if phase_inv_r:
                    r = -r

                # Apply gain + pan
                l = l * gain_lin * pan_l
                r = r * gain_lin * pan_r

                # DC blocking filter (1-pole HP)
                if dc_block:
                    new_dy_l = l - dx_l + dc_coeff * dy_l
                    dx_l = l
                    l = new_dy_l
                    dy_l = new_dy_l

                    new_dy_r = r - dx_r + dc_coeff * dy_r
                    dx_r = r
                    r = new_dy_r
                    dy_r = new_dy_r

                buf[n, 0] = l
                buf[n, 1] = r

            self._dc_x_l, self._dc_y_l = dx_l, dy_l
            self._dc_x_r, self._dc_y_r = dx_r, dy_r
        except Exception:
            pass


# ==========================================================================
# 5. SPECTRUM ANALYZER (FFT + Peak Hold, pass-through)
# ==========================================================================

class SpectrumAnalyzerFx:
    """FFT-based spectrum analyzer with peak hold.

    This is a PASS-THROUGH effect — it does NOT modify the audio.
    It computes magnitude spectrum data and stores it for GUI retrieval.

    The GUI polls get_spectrum_data() at ~30Hz to update the display.

    Parameters:
        fft_size:    FFT window size (512/1024/2048/4096, default 2048)
        peak_hold_s: Peak hold decay time in seconds (0..10, default 2.0)
        smoothing:   Spectral smoothing factor (0..0.95, default 0.7)
    """

    def __init__(self, track_id: str, device_id: str, rt_params: Any,
                 params: dict, sr: int = 48000):
        self.rt_params = rt_params
        self._sr = max(1, int(sr))
        self._prefix = f"afx:{track_id}:{device_id}:"
        self._track_id = track_id
        self._device_id = device_id

        defaults = params if isinstance(params, dict) else {}
        self._fft_size = int(defaults.get("fft_size", 2048))
        # Clamp to valid power-of-two
        if self._fft_size not in (512, 1024, 2048, 4096):
            self._fft_size = 2048

        # Accumulation buffer for FFT input
        self._acc_buf = [0.0] * self._fft_size
        self._acc_pos = 0

        # Spectrum data (magnitudes in dB, one per bin)
        num_bins = self._fft_size // 2 + 1
        self._magnitude_db = [-120.0] * num_bins
        self._peak_db = [-120.0] * num_bins
        self._smoothed_db = [-120.0] * num_bins

        # Hanning window (precomputed)
        self._window = [0.0] * self._fft_size
        for i in range(self._fft_size):
            self._window[i] = 0.5 * (1.0 - math.cos(2.0 * math.pi * i / self._fft_size))

        defs = {
            "fft_size": float(self._fft_size),
            "peak_hold_s": float(defaults.get("peak_hold_s", 2.0)),
            "smoothing": float(defaults.get("smoothing", 0.7)),
        }
        try:
            if hasattr(rt_params, "ensure"):
                for k, v in defs.items():
                    rt_params.ensure(self._prefix + k, v)
        except Exception:
            pass

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        """Pass-through: only accumulate samples for FFT, no audio modification."""
        if np is None or frames <= 0:
            return
        try:
            p = self._prefix
            peak_hold_s = max(0.0, _rt_get(self.rt_params, p + "peak_hold_s", 2.0))
            smoothing = _clamp(_rt_get(self.rt_params, p + "smoothing", 0.7), 0.0, 0.95)

            fft_size = self._fft_size
            acc = self._acc_buf
            pos = self._acc_pos

            # Accumulate mono-sum samples
            for n in range(frames):
                mono = (float(buf[n, 0]) + float(buf[n, 1])) * 0.5
                acc[pos] = mono
                pos = (pos + 1) % fft_size

                # When buffer is full, compute FFT
                if pos == 0:
                    self._compute_fft(acc, smoothing, peak_hold_s, frames)

            self._acc_pos = pos
        except Exception:
            pass

    def _compute_fft(self, acc: list, smoothing: float, peak_hold_s: float,
                     block_frames: int) -> None:
        """Compute FFT magnitudes from accumulated buffer."""
        try:
            if np is None:
                return
            fft_size = self._fft_size
            num_bins = fft_size // 2 + 1

            # Apply window
            windowed = np.array(acc, dtype=np.float64) * np.array(self._window, dtype=np.float64)

            # FFT
            spectrum = np.fft.rfft(windowed)
            magnitudes = np.abs(spectrum) / fft_size

            # Convert to dB
            mag_db = 20.0 * np.log10(np.maximum(magnitudes, 1e-10))

            # Peak hold decay
            decay_per_block = 0.0
            if peak_hold_s > 0.01 and block_frames > 0:
                blocks_per_sec = self._sr / max(1, block_frames)
                decay_per_block = 60.0 / max(1.0, peak_hold_s * blocks_per_sec)  # dB per block
            else:
                decay_per_block = 120.0  # instant decay

            for i in range(num_bins):
                db_val = float(mag_db[i])
                # Smoothing
                self._smoothed_db[i] = smoothing * self._smoothed_db[i] + (1.0 - smoothing) * db_val
                self._magnitude_db[i] = self._smoothed_db[i]
                # Peak hold
                if db_val > self._peak_db[i]:
                    self._peak_db[i] = db_val
                else:
                    self._peak_db[i] = max(-120.0, self._peak_db[i] - decay_per_block)
        except Exception:
            pass

    def get_spectrum_data(self) -> dict:
        """Return current spectrum data for GUI display.

        Returns dict with:
            'magnitudes': list of dB values per frequency bin
            'peaks': list of peak-hold dB values per bin
            'fft_size': current FFT size
            'sr': sample rate
            'num_bins': number of frequency bins
        """
        num_bins = self._fft_size // 2 + 1
        return {
            'magnitudes': list(self._magnitude_db),
            'peaks': list(self._peak_db),
            'fft_size': self._fft_size,
            'sr': self._sr,
            'num_bins': num_bins,
        }
