# -*- coding: utf-8 -*-
"""WAV I/O helpers for the modular Sampler.

- No soundfile/librosa dependency: uses stdlib `wave` + numpy.
- Loads PCM WAV (8/16/24/32-bit), mono/stereo/multichannel.
- Resamples with simple linear interpolation to a target sample rate (default: 48kHz).
"""

from __future__ import annotations

from pathlib import Path
import wave
import numpy as np


def _pcm_to_float32(raw: bytes, sampwidth: int) -> np.ndarray:
    """Decode PCM byte buffer to float32 array in [-1, 1]."""
    if sampwidth == 1:
        # unsigned 8-bit
        a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        a = (a - 128.0) / 128.0
        return a
    if sampwidth == 2:
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        return a / 32768.0
    if sampwidth == 3:
        # 24-bit little endian -> int32 sign-extended
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b.reshape(-1, 3)
        x = (b[:, 0].astype(np.int32)
             | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int32) << 16))
        # sign extend
        x = (x << 8) >> 8
        return (x.astype(np.float32) / 8388608.0)
    if sampwidth == 4:
        # Usually int32 PCM
        a = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        return a / 2147483648.0
    raise ValueError(f"Unsupported sampwidth: {sampwidth}")


def resample_linear(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Linear resample (good enough for preview / lightweight sampling)."""
    if int(src_sr) == int(dst_sr):
        return data
    src_sr = int(src_sr)
    dst_sr = int(dst_sr)
    n = int(data.shape[0])
    if n <= 1:
        return data

    dur = (n - 1) / float(src_sr)
    n2 = int(round(dur * dst_sr)) + 1
    # positions in source samples
    x_old = np.linspace(0.0, dur, n, dtype=np.float64)
    x_new = np.linspace(0.0, dur, n2, dtype=np.float64)

    out = np.empty((n2, data.shape[1]), dtype=np.float32)
    for ch in range(data.shape[1]):
        out[:, ch] = np.interp(x_new, x_old, data[:, ch]).astype(np.float32, copy=False)
    return out


def load_wav(path: str | Path, target_sr: int = 48000) -> tuple[np.ndarray, int]:
    """Load WAV file and return (float32 stereo, sample_rate)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    with wave.open(str(p), "rb") as wf:
        nch = int(wf.getnchannels())
        sr = int(wf.getframerate())
        sampwidth = int(wf.getsampwidth())
        nframes = int(wf.getnframes())
        raw = wf.readframes(nframes)

    pcm = _pcm_to_float32(raw, sampwidth)
    if nch <= 0:
        raise ValueError("Invalid channel count")
    pcm = pcm.reshape(-1, nch)

    # Normalize channel count to stereo
    if nch == 1:
        data = np.repeat(pcm, 2, axis=1)
    else:
        data = pcm[:, :2].copy()

    data = resample_linear(data.astype(np.float32, copy=False), sr, int(target_sr))
    return data.astype(np.float32, copy=False), int(target_sr)
