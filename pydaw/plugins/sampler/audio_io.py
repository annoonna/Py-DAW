# -*- coding: utf-8 -*-
"""Audio I/O helpers — multi-format loader for the Sampler.

Supports: WAV, MP3, FLAC, OGG, AIFF, M4A, WV
Strategy:
  1. Try `soundfile` (WAV, FLAC, OGG, AIFF)
  2. Try `pydub` / ffmpeg fallback (MP3, M4A, WV, anything ffmpeg handles)
  3. Fallback: stdlib `wave` for basic WAV

Resamples with linear interpolation to target sample rate (default 48 kHz).
"""
from __future__ import annotations

from pathlib import Path
import struct
import wave
import numpy as np

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a", ".wv"}


def resample_linear(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if int(src_sr) == int(dst_sr):
        return data
    n = int(data.shape[0])
    if n <= 1:
        return data
    dur = (n - 1) / float(src_sr)
    n2 = int(round(dur * dst_sr)) + 1
    x_old = np.linspace(0.0, dur, n, dtype=np.float64)
    x_new = np.linspace(0.0, dur, n2, dtype=np.float64)
    out = np.empty((n2, data.shape[1]), dtype=np.float32)
    for ch in range(data.shape[1]):
        out[:, ch] = np.interp(x_new, x_old, data[:, ch]).astype(np.float32, copy=False)
    return out


def _pcm_to_float32(raw: bytes, sampwidth: int) -> np.ndarray:
    if sampwidth == 1:
        a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (a - 128.0) / 128.0
    if sampwidth == 2:
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if sampwidth == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        x = (x << 8) >> 8
        return x.astype(np.float32) / 8388608.0
    if sampwidth == 4:
        return np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    raise ValueError(f"Unsupported sampwidth: {sampwidth}")


def _load_stdlib_wav(path: str, target_sr: int) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        nch = int(wf.getnchannels())
        sr = int(wf.getframerate())
        sw = int(wf.getsampwidth())
        raw = wf.readframes(int(wf.getnframes()))
    pcm = _pcm_to_float32(raw, sw).reshape(-1, nch)
    data = np.repeat(pcm, 2, axis=1) if nch == 1 else pcm[:, :2].copy()
    data = resample_linear(data.astype(np.float32, copy=False), sr, target_sr)
    return data.astype(np.float32, copy=False), target_sr


def _load_soundfile(path: str, target_sr: int) -> tuple[np.ndarray, int]:
    import soundfile as sf
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2].copy()
    data = resample_linear(data, sr, target_sr)
    return data.astype(np.float32, copy=False), target_sr


def _load_pydub(path: str, target_sr: int) -> tuple[np.ndarray, int]:
    from pydub import AudioSegment
    seg = AudioSegment.from_file(str(path))
    seg = seg.set_frame_rate(target_sr).set_channels(2).set_sample_width(2)
    raw = seg.raw_data
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    data = pcm.reshape(-1, 2)
    return data.astype(np.float32, copy=False), target_sr


def load_audio(path: str | Path, target_sr: int = 48000) -> tuple[np.ndarray, int]:
    """Load audio file (multi-format). Returns (float32 stereo, sample_rate)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    ext = p.suffix.lower()

    # 1. Try soundfile (best quality, no ffmpeg needed for WAV/FLAC/OGG/AIFF)
    try:
        return _load_soundfile(str(p), target_sr)
    except ImportError:
        pass
    except Exception:
        if ext in (".wav", ".flac", ".ogg", ".aiff", ".aif"):
            pass  # fall through to other loaders

    # 2. Try pydub/ffmpeg (MP3, M4A, WV, or anything)
    try:
        return _load_pydub(str(p), target_sr)
    except ImportError:
        pass
    except Exception:
        pass

    # 3. Fallback: stdlib wave (WAV only)
    if ext == ".wav":
        return _load_stdlib_wav(str(p), target_sr)

    raise RuntimeError(f"Cannot load '{ext}' — install 'soundfile' or 'pydub' (+ ffmpeg).")


# Backward compat alias
def load_wav(path: str | Path, target_sr: int = 48000) -> tuple[np.ndarray, int]:
    return load_audio(path, target_sr)
