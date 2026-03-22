"""
Time-stretch utilities (pitch-preserving) for PyDAW.

Design goals:
- Robust: never crash playback if stretching fails.
- Optional Essentia integration (if available).
- Pure-numpy fallback (phase vocoder) so the DAW still works without Essentia.

Convention:
- `rate` is a *play-rate* multiplier:
    rate > 1.0  -> faster / shorter
    rate < 1.0  -> slower / longer
So the stretched output length is approximately len(input) / rate.
"""

from __future__ import annotations

from typing import Optional

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


def _clamp_rate(rate: float) -> float:
    try:
        r = float(rate)
    except Exception:
        r = 1.0
    if not (0.01 < r < 100.0):
        return 1.0
    return r


def _pv_time_stretch_mono(x, rate: float, n_fft: int = 2048, hop: int = 512):
    """
    Simple phase-vocoder time-stretch (mono), pitch-preserving.

    This is a pragmatic implementation meant for preview/arranger sync.
    Quality is acceptable for loops; can be replaced by higher-quality engines later.
    """
    if np is None:
        return x
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 1 or x.size < 8:
        return x

    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return x

    n_fft = int(n_fft)
    hop = int(hop)
    n_fft = max(256, n_fft)
    hop = max(64, min(hop, n_fft // 2))

    # Pad so we can frame safely
    pad = n_fft
    x_pad = np.pad(x, (pad, pad), mode="constant")
    win = np.hanning(n_fft).astype(np.float32)

    # Frame count
    n_frames = 1 + (len(x_pad) - n_fft) // hop
    if n_frames <= 2:
        return x

    # STFT
    frames = np.lib.stride_tricks.as_strided(
        x_pad,
        shape=(n_frames, n_fft),
        strides=(x_pad.strides[0] * hop, x_pad.strides[0]),
        writeable=False,
    )
    frames_win = frames * win[None, :]
    spec = np.fft.rfft(frames_win, axis=1).astype(np.complex64)  # (frames, bins)
    spec = spec.T  # (bins, frames)

    # Time steps in analysis frames
    time_steps = np.arange(0, spec.shape[1], rate, dtype=np.float32)
    n_out_frames = int(len(time_steps))
    if n_out_frames <= 1:
        return x

    # Expected phase advance per bin
    omega = (2.0 * np.pi * np.arange(spec.shape[0], dtype=np.float32) * hop) / float(n_fft)

    phase_acc = np.angle(spec[:, 0]).astype(np.float32)
    last_phase = phase_acc.copy()

    out_spec = np.empty((spec.shape[0], n_out_frames), dtype=np.complex64)

    for t, step in enumerate(time_steps):
        i = int(step)
        if i >= spec.shape[1] - 1:
            i = spec.shape[1] - 2
        frac = float(step - i)

        s0 = spec[:, i]
        s1 = spec[:, i + 1]

        # Linear interp magnitudes
        mag = (1.0 - frac) * np.abs(s0) + frac * np.abs(s1)

        phase = np.angle(s0).astype(np.float32)
        delta = phase - last_phase - omega
        delta -= 2.0 * np.pi * np.round(delta / (2.0 * np.pi)).astype(np.float32)

        phase_acc += omega + delta
        last_phase = phase

        out_spec[:, t] = mag.astype(np.float32) * np.exp(1.0j * phase_acc.astype(np.float32))

    # ISTFT (overlap-add)
    out_frames = np.fft.irfft(out_spec.T, n=n_fft, axis=1).astype(np.float32)
    out_len = n_out_frames * hop + n_fft
    y = np.zeros(out_len, dtype=np.float32)
    win_sum = np.zeros(out_len, dtype=np.float32)

    for i in range(n_out_frames):
        start = i * hop
        y[start:start + n_fft] += out_frames[i] * win
        win_sum[start:start + n_fft] += win * win

    # Normalize windowing
    nz = win_sum > 1e-8
    y[nz] /= win_sum[nz]

    # Remove initial padding
    y = y[pad:-pad]

    # Ensure approximate target length
    target_len = max(1, int(round(len(x) / rate)))
    if len(y) > target_len + hop:
        y = y[:target_len]
    elif len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)), mode="constant")

    return y.astype(np.float32, copy=False)


def _try_essentia_stretch_mono(x, rate: float) -> Optional["np.ndarray"]:
    """Best-effort Essentia stretch (mono). Returns None if unavailable."""
    if np is None:
        return None
    try:
        import essentia.standard as es  # type: ignore
    except Exception:
        return None

    x = np.asarray(x, dtype=np.float32).reshape(-1)

    # Try a few algorithm names/signatures defensively.
    # We keep this very safe: any failure => None => fallback to numpy PV.
    for ctor_name in ("TimeStretch", "FStretch"):
        try:
            ctor = getattr(es, ctor_name, None)
            if ctor is None:
                continue
            try:
                alg = ctor(rate=float(rate))
                y = alg(x)
                if y is not None and len(y) > 8:
                    return np.asarray(y, dtype=np.float32)
            except TypeError:
                # Some builds may require different args; skip.
                continue
        except Exception:
            continue
    return None


def time_stretch_mono(x, rate: float, *, prefer_essentia: bool = True):
    """Public mono stretch helper."""
    if np is None:
        return x
    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return np.asarray(x, dtype=np.float32)

    if prefer_essentia:
        y = _try_essentia_stretch_mono(x, rate)
        if y is not None:
            return y

    return _pv_time_stretch_mono(x, rate)


def time_stretch_stereo(data, rate: float, sr: int, *, prefer_essentia: bool = True):
    """
    Pitch-preserving time-stretch for stereo float32 arrays.

    `data`: shape (n, 2) or (n,1). Returns shape (m,2).
    """
    if np is None:
        return data
    rate = _clamp_rate(rate)
    d = np.asarray(data, dtype=np.float32)
    if d.ndim != 2:
        d = np.atleast_2d(d).astype(np.float32)
    if d.shape[1] == 1:
        d = np.repeat(d, 2, axis=1)
    elif d.shape[1] > 2:
        d = d[:, :2]

    if d.shape[0] < 8 or abs(rate - 1.0) < 1e-3:
        return d.astype(np.float32, copy=False)

    l = time_stretch_mono(d[:, 0], rate, prefer_essentia=prefer_essentia)
    r = time_stretch_mono(d[:, 1], rate, prefer_essentia=prefer_essentia)

    n = min(len(l), len(r))
    out = np.stack([l[:n], r[:n]], axis=1).astype(np.float32, copy=False)
    return out


# ==========================================================================
# v0.0.20.641: Stretch Modes (AP3 Phase 3B)
# ==========================================================================

# Valid stretch mode names
STRETCH_MODES = ("tones", "beats", "texture", "repitch", "complex")


def _repitch_mono(x, rate: float):
    """Re-Pitch mode: simple resampling — changes pitch, no time-stretch.

    rate > 1 → shorter + higher pitch. rate < 1 → longer + lower pitch.
    This is just linear interpolation resampling (varispeed).
    """
    if np is None:
        return x
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return x

    out_len = max(1, int(round(len(x) / rate)))
    indices = np.linspace(0.0, len(x) - 1, out_len, dtype=np.float64)
    idx_int = indices.astype(np.int64)
    idx_frac = (indices - idx_int).astype(np.float32)
    # Clamp
    idx_int = np.clip(idx_int, 0, len(x) - 2)
    y = x[idx_int] * (1.0 - idx_frac) + x[idx_int + 1] * idx_frac
    return y.astype(np.float32, copy=False)


def _beats_stretch_mono(x, rate: float, sr: int = 48000, onsets=None):
    """Beats mode: slice-based stretching for drums/percussion.

    Preserves transient attacks by cutting at onsets and repositioning slices
    in time. Gaps are filled with silence, overlaps are crossfaded.
    """
    if np is None:
        return x
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return x

    out_len = max(1, int(round(len(x) / rate)))

    # Find onset positions (in samples)
    if onsets is not None and len(onsets) > 0:
        onset_samps = sorted([int(round(float(o) * sr)) for o in onsets if 0 < float(o) * sr < len(x)])
    else:
        # Auto-detect onsets: energy-based
        try:
            hop = max(64, sr // 200)
            env = np.sqrt(np.convolve(x * x, np.ones(hop, dtype=np.float32) / float(hop), mode="same"))
            threshold = float(env.mean()) + 2.0 * float(env.std())
            above = env > threshold
            # Find rising edges
            onset_samps = []
            was_below = True
            min_gap = int(sr * 0.05)  # 50ms minimum gap
            for i in range(0, len(above), hop):
                if above[i] and was_below:
                    if not onset_samps or (i - onset_samps[-1]) > min_gap:
                        onset_samps.append(i)
                    was_below = False
                elif not above[i]:
                    was_below = True
        except Exception:
            onset_samps = []

    if not onset_samps:
        # Fallback to regular slicing
        slice_len = max(sr // 8, int(sr * 60.0 / 120.0))  # ~eighth note at 120 BPM
        onset_samps = list(range(0, len(x), slice_len))

    # Ensure 0 is first
    if onset_samps[0] != 0:
        onset_samps.insert(0, 0)

    # Build output by repositioning slices
    y = np.zeros(out_len, dtype=np.float32)
    xfade = min(256, sr // 100)  # ~10ms crossfade

    for i, start in enumerate(onset_samps):
        end = onset_samps[i + 1] if i + 1 < len(onset_samps) else len(x)
        slice_data = x[start:end].copy()
        # New position in output
        new_start = int(round(start / rate))
        if new_start >= out_len:
            break
        copy_len = min(len(slice_data), out_len - new_start)
        if copy_len <= 0:
            continue
        # Simple overlap-add with short crossfade
        if new_start > 0 and xfade > 0:
            fade_len = min(xfade, copy_len)
            fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            slice_data[:fade_len] *= fade_in
        y[new_start:new_start + copy_len] += slice_data[:copy_len]

    return y


def _texture_stretch_mono(x, rate: float, grain_ms: float = 60.0, sr: int = 48000):
    """Texture mode: granular time-stretch for ambient/pads.

    Uses overlapping grains with random jitter for a smeared, textural sound.
    Good for pads, ambient, textures. Not suitable for transient-heavy material.
    """
    if np is None:
        return x
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return x

    grain_len = max(256, int(grain_ms * 0.001 * sr))
    hop_out = grain_len // 2  # 50% overlap in output
    hop_in = max(1, int(hop_out * rate))  # input hop

    out_len = max(1, int(round(len(x) / rate)))
    y = np.zeros(out_len + grain_len, dtype=np.float32)
    win_sum = np.zeros(out_len + grain_len, dtype=np.float32)
    win = np.hanning(grain_len).astype(np.float32)

    rng = np.random.RandomState(42)  # deterministic for consistency
    jitter_range = max(1, grain_len // 8)

    out_pos = 0
    in_pos = 0

    while out_pos < out_len:
        # Add small random jitter to input position
        jittered_in = int(in_pos) + rng.randint(-jitter_range, jitter_range + 1)
        jittered_in = max(0, min(len(x) - grain_len, jittered_in))

        if jittered_in + grain_len > len(x):
            break

        grain = x[jittered_in:jittered_in + grain_len] * win
        end = min(out_pos + grain_len, len(y))
        copy_len = end - out_pos
        y[out_pos:end] += grain[:copy_len]
        win_sum[out_pos:end] += win[:copy_len] * win[:copy_len]

        out_pos += hop_out
        in_pos += hop_in

    # Normalize
    nz = win_sum > 1e-8
    y[nz] /= win_sum[nz]

    return y[:out_len].astype(np.float32, copy=False)


def _complex_stretch_mono(x, rate: float, n_fft: int = 4096, hop: int = 256):
    """Complex mode: high-quality phase vocoder with larger FFT and finer hop.

    Same algorithm as the standard PV but with higher resolution for better quality.
    More CPU-intensive due to larger FFT size.
    """
    return _pv_time_stretch_mono(x, rate, n_fft=n_fft, hop=hop)


def time_stretch_mono_mode(x, rate: float, mode: str = "tones",
                           sr: int = 48000, onsets=None,
                           prefer_essentia: bool = True):
    """Stretch mono audio using the specified mode.

    v0.0.20.641 (AP3 Phase 3B): Multi-mode stretch dispatch.

    Modes:
        tones:   Phase vocoder / Essentia (default, melodic)
        beats:   Slice-based (drums/percussion)
        texture: Granular (ambient/pads)
        repitch: Simple resampling (changes pitch)
        complex: High-quality phase vocoder (CPU-intensive)
    """
    if np is None:
        return x
    rate = _clamp_rate(rate)
    if abs(rate - 1.0) < 1e-3:
        return np.asarray(x, dtype=np.float32)

    mode = str(mode or "tones").strip().lower()

    if mode == "repitch":
        return _repitch_mono(x, rate)
    elif mode == "beats":
        return _beats_stretch_mono(x, rate, sr=sr, onsets=onsets)
    elif mode == "texture":
        return _texture_stretch_mono(x, rate, sr=sr)
    elif mode == "complex":
        return _complex_stretch_mono(x, rate)
    else:
        # "tones" or unknown → default (Essentia + PV fallback)
        return time_stretch_mono(x, rate, prefer_essentia=prefer_essentia)


def time_stretch_stereo_mode(data, rate: float, mode: str = "tones",
                              sr: int = 48000, onsets=None,
                              prefer_essentia: bool = True):
    """Stretch stereo audio using the specified mode.

    v0.0.20.641 (AP3 Phase 3B): Multi-mode stretch dispatch for stereo.
    """
    if np is None:
        return data
    rate = _clamp_rate(rate)
    d = np.asarray(data, dtype=np.float32)
    if d.ndim != 2:
        d = np.atleast_2d(d).astype(np.float32)
    if d.shape[1] == 1:
        d = np.repeat(d, 2, axis=1)
    elif d.shape[1] > 2:
        d = d[:, :2]

    if d.shape[0] < 8 or abs(rate - 1.0) < 1e-3:
        return d.astype(np.float32, copy=False)

    l = time_stretch_mono_mode(d[:, 0], rate, mode=mode, sr=sr, onsets=onsets, prefer_essentia=prefer_essentia)
    r = time_stretch_mono_mode(d[:, 1], rate, mode=mode, sr=sr, onsets=onsets, prefer_essentia=prefer_essentia)

    n = min(len(l), len(r))
    out = np.stack([l[:n], r[:n]], axis=1).astype(np.float32, copy=False)
    return out
