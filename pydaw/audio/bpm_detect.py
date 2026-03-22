"""
BPM detection utilities for Browser Preview / Sync.

Primary: Essentia RhythmExtractor2013 (if installed).
Fallbacks:
- Parse BPM from filename (e.g. "loop_120bpm.wav", "Kick (110 BPM).wav")
- Simple autocorrelation-based estimator on an energy/onset envelope (best-effort)

This module must NEVER raise in production playback paths.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


_BPM_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*bpm", re.IGNORECASE)


def parse_bpm_from_filename(name: str) -> Optional[float]:
    try:
        s = str(name or "")
        m = _BPM_RE.search(s)
        if not m:
            return None
        v = float(m.group(1))
        if 20.0 <= v <= 400.0:
            return v
        return None
    except Exception:
        return None


@dataclass
class BPMResult:
    bpm: Optional[float]
    confidence: float = 0.0
    method: str = "unknown"


def _estimate_bpm_autocorr(audio_mono, sr: int) -> BPMResult:
    """Very simple BPM estimator (fallback)."""
    if np is None:
        return BPMResult(None, 0.0, "none")
    try:
        x = np.asarray(audio_mono, dtype=np.float32).copy()
        if x.size < sr // 2:
            return BPMResult(None, 0.0, "short")

        # downsample envelope for speed
        hop = max(64, int(sr // 200))  # ~200 Hz
        # energy envelope
        env = np.sqrt(np.convolve(x * x, np.ones(hop, dtype=np.float32) / float(hop), mode="same"))
        env = env[::hop]
        env -= float(env.mean())
        env = env.astype(np.float32, copy=False)

        # autocorrelation
        ac = np.correlate(env, env, mode="full")[len(env)-1:]
        if ac.size < 8:
            return BPMResult(None, 0.0, "ac_short")

        # limit lag range to plausible BPM
        env_sr = sr / float(hop)
        min_bpm, max_bpm = 60.0, 200.0
        max_lag = int(env_sr * 60.0 / min_bpm)
        min_lag = int(env_sr * 60.0 / max_bpm)
        max_lag = max(min_lag + 2, min(max_lag, ac.size - 1))
        min_lag = max(1, min(min_lag, max_lag - 1))

        seg = ac[min_lag:max_lag].copy()
        # pick peak
        k = int(np.argmax(seg)) + min_lag
        bpm = (60.0 * env_sr) / float(k)
        # crude confidence
        conf = float(seg.max() / (seg.mean() + 1e-9))
        conf = max(0.0, min(1.0, (conf - 1.0) / 3.0))
        return BPMResult(float(bpm), conf, "autocorr")
    except Exception:
        return BPMResult(None, 0.0, "autocorr_fail")


def estimate_bpm(audio_stereo, sr: int, filename_hint: str | None = None) -> BPMResult:
    """Estimate BPM from audio. Never raises."""
    try:
        # quick hint from filename
        if filename_hint:
            hb = parse_bpm_from_filename(filename_hint)
            if hb is not None:
                # still try essentia later; but keep as a fallback value
                hint = float(hb)
            else:
                hint = None
        else:
            hint = None

        if np is None:
            return BPMResult(hint, 0.2 if hint else 0.0, "filename" if hint else "none")

        x = np.asarray(audio_stereo, dtype=np.float32)
        if x.ndim == 2:
            mono = x.mean(axis=1)
        else:
            mono = x.reshape(-1)

        # Essentia primary
        try:
            import essentia.standard as es  # type: ignore
            # RhythmExtractor2013 expects float vector
            bpm, ticks, confidence, _ = es.RhythmExtractor2013(method="multifeature")(mono)
            bpm = float(bpm)
            confidence = float(confidence) if confidence is not None else 0.0
            if 20.0 <= bpm <= 400.0:
                return BPMResult(bpm, max(0.0, min(1.0, confidence)), "essentia_rhythm2013")
        except Exception:
            pass

        # fallback estimator
        r = _estimate_bpm_autocorr(mono, int(sr))
        if r.bpm is None and hint is not None:
            return BPMResult(hint, 0.2, "filename")
        return r if r.bpm is not None else BPMResult(hint, 0.2 if hint else 0.0, "filename" if hint else "unknown")
    except Exception:
        return BPMResult(None, 0.0, "fail")


@dataclass
class BeatPositions:
    """Result of beat-tracking: list of beat positions in seconds."""
    beats_seconds: list  # list of float — beat positions in seconds
    bpm: Optional[float] = None
    confidence: float = 0.0
    method: str = "unknown"


def detect_beat_positions(audio_stereo, sr: int) -> BeatPositions:
    """Detect individual beat positions in audio. Returns positions in seconds.

    v0.0.20.641 (AP3 Phase 3A): Used by auto-warp-marker placement.
    Primary: Essentia RhythmExtractor2013 (returns beat ticks).
    Fallback: Simple onset-based beat grid estimation.
    Never raises.
    """
    try:
        if np is None:
            return BeatPositions([], None, 0.0, "none")

        x = np.asarray(audio_stereo, dtype=np.float32)
        if x.ndim == 2:
            mono = x.mean(axis=1)
        else:
            mono = x.reshape(-1)

        if mono.size < int(sr) // 4:
            return BeatPositions([], None, 0.0, "short")

        # Essentia primary — returns beat tick positions
        try:
            import essentia.standard as es  # type: ignore
            bpm, ticks, confidence, _ = es.RhythmExtractor2013(method="multifeature")(mono)
            bpm = float(bpm)
            confidence = float(confidence) if confidence is not None else 0.0
            if 20.0 <= bpm <= 400.0 and len(ticks) > 0:
                beats = sorted([float(t) for t in ticks if 0.0 < float(t) < len(mono) / float(sr)])
                return BeatPositions(beats, bpm, max(0.0, min(1.0, confidence)), "essentia_rhythm2013")
        except Exception:
            pass

        # Fallback: generate a grid from estimated BPM
        r = _estimate_bpm_autocorr(mono, int(sr))
        if r.bpm is not None and r.bpm > 20.0:
            beat_interval = 60.0 / float(r.bpm)
            duration = float(len(mono)) / float(sr)
            beats = []
            t = beat_interval  # skip first beat at 0
            while t < duration - 0.01:
                beats.append(round(float(t), 6))
                t += beat_interval
            return BeatPositions(beats, r.bpm, r.confidence * 0.5, "autocorr_grid")

        return BeatPositions([], None, 0.0, "fail")
    except Exception:
        return BeatPositions([], None, 0.0, "fail")
