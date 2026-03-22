# -*- coding: utf-8 -*-
"""Safe offline sample operations for DrumMachine.

Design goals:
- Non-destructive: operations always create a new WAV file (no overwrite of original).
- Predictable: pure numpy operations, no DSP surprises.
- Cross-platform: uses stdlib wave writer (16-bit PCM) so we don't depend on soundfile.

These tools are intentionally *offline* (run only when the user clicks a menu action),
so they can't break realtime playback stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import os
import tempfile
import wave
import numpy as np

from pydaw.plugins.sampler.audio_io import load_audio


def _db_to_lin(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def _lin_to_db(x: float) -> float:
    x = max(float(x), 1e-12)
    return float(20.0 * math.log10(x))


def unique_path_near(src: Path, suffix: str, ext: str = ".wav") -> Path:
    """Create a unique sibling path near src."""
    src = Path(src)
    base = src.with_suffix("")
    cand = Path(f"{base}_{suffix}{ext}")
    if not cand.exists():
        return cand
    for i in range(1, 10_000):
        c = Path(f"{base}_{suffix}_{i}{ext}")
        if not c.exists():
            return c
    return Path(f"{base}_{suffix}_{os.getpid()}{ext}")


def write_wav16(path: Path, data: np.ndarray, sr: int) -> None:
    """Write float32 [-1..1] audio to 16-bit PCM WAV (stereo)."""
    path = Path(path)
    sr = int(sr)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    if data.shape[1] > 2:
        data = data[:, :2]
    data = np.asarray(data, dtype=np.float32)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def load_for_engine(path: str, target_sr: int) -> tuple[np.ndarray, int]:
    """Load multi-format audio and resample to target_sr (stereo float32)."""
    data, sr = load_audio(str(path), target_sr=int(target_sr))
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    if data.shape[1] > 2:
        data = data[:, :2]
    return data, int(sr)


def trim_silence(data: np.ndarray, sr: int, threshold_db: float = -45.0, pad_ms: float = 5.0) -> np.ndarray:
    """Trim leading/trailing silence by threshold with padding."""
    data = np.asarray(data, dtype=np.float32)
    thr = _db_to_lin(float(threshold_db))
    pad = int(round(float(pad_ms) * 0.001 * int(sr)))
    mono = np.max(np.abs(data), axis=1)
    idx = np.where(mono > thr)[0]
    if idx.size == 0:
        return data  # keep as-is (all silence)
    a = max(int(idx[0]) - pad, 0)
    b = min(int(idx[-1]) + pad + 1, data.shape[0])
    if b <= a:
        return data
    return data[a:b].copy()


def normalize_peak(data: np.ndarray, target_db: float = -0.2) -> np.ndarray:
    """Peak normalize to target_db."""
    data = np.asarray(data, dtype=np.float32)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak <= 1e-9:
        return data
    target = _db_to_lin(float(target_db))
    gain = target / peak
    return np.clip(data * gain, -1.0, 1.0).astype(np.float32, copy=False)


def reverse_audio(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32)
    return data[::-1].copy()


def fade_in_out(data: np.ndarray, sr: int, fade_in_ms: float = 5.0, fade_out_ms: float = 10.0) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32).copy()
    n = int(data.shape[0])
    fi = int(round(float(fade_in_ms) * 0.001 * int(sr)))
    fo = int(round(float(fade_out_ms) * 0.001 * int(sr)))
    if fi > 0:
        fi = min(fi, n)
        w = np.linspace(0.0, 1.0, fi, dtype=np.float32)
        data[:fi, :] *= w[:, None]
    if fo > 0:
        fo = min(fo, n)
        w = np.linspace(1.0, 0.0, fo, dtype=np.float32)
        data[n-fo:, :] *= w[:, None]
    return data


def dc_remove(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32)
    mean = data.mean(axis=0, keepdims=True)
    return (data - mean).astype(np.float32, copy=False)


def transient_shaper(data: np.ndarray, sr: int, window_ms: float = 20.0, transient_db: float = 6.0, sustain_db: float = 0.0) -> np.ndarray:
    """Very safe transient/sustain shaper:
    - Compute a smoothed 'sustain' component via moving average.
    - Transient component = original - sustain.
    - Mix with independent gains.
    """
    data = np.asarray(data, dtype=np.float32)
    n = int(data.shape[0])
    if n < 16:
        return data
    win = int(round(float(window_ms) * 0.001 * int(sr)))
    win = max(8, min(win, n))
    # simple moving average kernel
    k = np.ones(win, dtype=np.float32) / float(win)
    sustain = np.empty_like(data)
    for ch in range(data.shape[1]):
        sustain[:, ch] = np.convolve(data[:, ch], k, mode="same")
    trans = data - sustain
    tg = _db_to_lin(float(transient_db))
    sg = _db_to_lin(float(sustain_db))
    out = sustain * sg + trans * tg
    return np.clip(out, -1.0, 1.0).astype(np.float32, copy=False)


def slice_equal(data: np.ndarray, slices: int) -> list[np.ndarray]:
    data = np.asarray(data, dtype=np.float32)
    n = int(data.shape[0])
    s = max(1, int(slices))
    # minimum length guard
    if n < s:
        return [data.copy()]
    step = n // s
    out = []
    for i in range(s):
        a = i * step
        b = (i + 1) * step if i < s - 1 else n
        if b - a <= 0:
            continue
        out.append(data[a:b].copy())
    return out or [data.copy()]


def slice_transient(data: np.ndarray, sr: int, slices: int, min_ms: float = 30.0) -> list[np.ndarray]:
    """Simple onset-like slicing (best-effort).
    If it fails, the caller should fall back to equal slicing.
    """
    data = np.asarray(data, dtype=np.float32)
    n = int(data.shape[0])
    s = max(1, int(slices))
    if s <= 1 or n < 1024:
        return [data.copy()]
    mono = np.mean(np.abs(data), axis=1)
    # smooth envelope
    win = max(64, int(0.01 * sr))  # ~10ms
    k = np.ones(win, dtype=np.float32) / float(win)
    env = np.convolve(mono, k, mode="same")
    d = np.diff(env, prepend=env[:1])
    # pick candidate onsets: top percentile
    thr = np.percentile(d, 99.0)
    cand = np.where(d > thr)[0]
    if cand.size == 0:
        return [data.copy()]
    # enforce minimum distance
    min_len = int(round(float(min_ms) * 0.001 * int(sr)))
    onsets = []
    last = -10**9
    for idx in cand:
        if idx - last >= min_len:
            onsets.append(int(idx))
            last = int(idx)
        if len(onsets) >= (s - 1):
            break
    if not onsets:
        return [data.copy()]
    cuts = [0] + sorted(onsets) + [n]
    out = []
    for i in range(len(cuts) - 1):
        a, b = int(cuts[i]), int(cuts[i + 1])
        if b - a <= 0:
            continue
        out.append(data[a:b].copy())
    # reduce/extend to requested slices (best-effort)
    if len(out) > s:
        out = out[:s]
    return out or [data.copy()]


def _bezier_y(t: np.ndarray, y1: float, y2: float) -> np.ndarray:
    """Cubic Bezier y(t) with fixed endpoints (0,0)->(1,1).

    We keep it intentionally simple/safe (no inverse solve for x).
    y1/y2 are clamped to [0..1].
    """
    t = np.asarray(t, dtype=np.float32)
    y1 = float(max(0.0, min(1.0, float(y1))))
    y2 = float(max(0.0, min(1.0, float(y2))))
    omt = (1.0 - t)
    return (3.0 * omt * omt * t * y1 + 3.0 * omt * t * t * y2 + t * t * t).astype(np.float32)


def pitch_envelope_bezier(
    data: np.ndarray,
    sr: int,
    start_semitones: float = 0.0,
    end_semitones: float = 0.0,
    y1: float = 0.25,
    y2: float = 0.75,
) -> np.ndarray:
    """Offline pitch envelope using a simple Bezier curve.

    Safety goals:
    - No realtime processing.
    - Keeps output length equal to input length (so clips stay aligned).
    - Uses linear interpolation (fast, predictable).

    Note: This is not a phase-vocoder. It is a *creative* tool for drums/FX.
    """
    data = np.asarray(data, dtype=np.float32)
    n = int(data.shape[0])
    if n < 8:
        return data.copy()

    # Curve 0..1
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    y = _bezier_y(t, float(y1), float(y2))
    semi = float(start_semitones) + (float(end_semitones) - float(start_semitones)) * y
    rate = np.power(2.0, semi / 12.0).astype(np.float32)
    # normalize so total advance matches length
    total = float(np.sum(rate))
    if total <= 1e-9:
        return data.copy()
    rate *= float(n - 1) / total
    pos = np.cumsum(rate)
    pos = np.clip(pos, 0.0, float(n - 1)).astype(np.float32)

    x = np.arange(n, dtype=np.float32)
    out = np.zeros_like(data)
    for ch in range(data.shape[1]):
        out[:, ch] = np.interp(pos, x, data[:, ch]).astype(np.float32, copy=False)
    return out


def render_to_temp_wav(data: np.ndarray, sr: int, suffix: str = "proc") -> Path:
    """Write to a temp wav file and return its path."""
    fd, p = tempfile.mkstemp(prefix=f"pydaw_{suffix}_", suffix=".wav")
    os.close(fd)
    path = Path(p)
    write_wav16(path, data, int(sr))
    return path
