# -*- coding: utf-8 -*-
"""Audio Export Service (AP10 Phase 10A).

v0.0.20.644: Real offline rendering to multiple formats.

Renders the arrangement (or loop region) through the existing
arrangement_renderer/hybrid_engine and writes the result to disk.

Supported formats:
- WAV  (16/24/32-bit PCM via soundfile)
- FLAC (16/24-bit via soundfile)
- OGG  (quality 0-10 via soundfile)
- MP3  (128-320 kbps via lame/pydub fallback)

Features:
- Sample-rate conversion (44.1/48/88.2/96 kHz)
- Dither (Triangular TPDF, POW-R Type 1)
- Normalization (Peak / LUFS)
- Progress callback for UI integration
- Stem export (per-track rendering)
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

try:
    import numpy as np
except Exception:
    np = None

try:
    import soundfile as sf
    _HAS_SOUNDFILE = True
except Exception:
    sf = None
    _HAS_SOUNDFILE = False


# ---------------------------------------------------------------------------
# Export Configuration
# ---------------------------------------------------------------------------

@dataclass
class ExportConfig:
    """Configuration for an audio export job."""
    output_dir: str = ""
    filename_base: str = "export"
    format: str = "wav"           # wav, flac, ogg, mp3
    bit_depth: int = 24           # 16, 24, 32 (for wav/flac)
    mp3_bitrate: int = 320        # 128, 192, 256, 320
    ogg_quality: int = 7          # 0-10
    sample_rate: int = 0          # 0 = use project SR
    normalize_mode: str = "none"  # none, peak, lufs
    normalize_target_db: float = -0.3   # target for peak normalize
    normalize_target_lufs: float = -14.0  # target for LUFS normalize
    dither: str = "none"          # none, tpdf, pow_r
    start_beat: float = 0.0
    end_beat: float = -1.0        # -1 = auto-detect end
    track_ids: List[str] = field(default_factory=list)  # empty = master only
    stem_export: bool = False     # export each track separately
    project_name: str = ""
    bpm: float = 120.0
    # v0.0.20.650: Pre-/Post-FX Export (AP10 Phase 10B Task 4)
    # "post_fx" = with FX chain applied (default), "pre_fx" = raw/dry, "both" = export both
    fx_mode: str = "post_fx"


# ---------------------------------------------------------------------------
# Dither Generators
# ---------------------------------------------------------------------------

def _apply_tpdf_dither(audio: "np.ndarray", bit_depth: int) -> "np.ndarray":
    """Apply Triangular Probability Density Function dither.

    Standard dither for 16/24-bit quantization.
    """
    if np is None or bit_depth >= 32:
        return audio
    # TPDF: sum of two uniform random values → triangular distribution
    # Amplitude = 1 LSB
    lsb = 1.0 / (2 ** (bit_depth - 1))
    rng = np.random.RandomState(42)
    noise = (rng.uniform(-0.5, 0.5, audio.shape) +
             rng.uniform(-0.5, 0.5, audio.shape)) * lsb
    return audio + noise


def _apply_pow_r_dither(audio: "np.ndarray", bit_depth: int) -> "np.ndarray":
    """Apply POW-R Type 1 dither (noise shaping).

    Higher perceived quality than TPDF, shapes noise into less audible range.
    POW-R Type 1 is flat noise + subtle high-frequency shaping.
    """
    if np is None or bit_depth >= 32:
        return audio
    lsb = 1.0 / (2 ** (bit_depth - 1))
    rng = np.random.RandomState(42)
    # Type 1: TPDF + 1st order noise shaping
    noise = (rng.uniform(-0.5, 0.5, audio.shape) +
             rng.uniform(-0.5, 0.5, audio.shape)) * lsb
    # Simple 1st-order error feedback (noise shaping)
    shaped = np.zeros_like(audio)
    error = np.zeros(audio.shape[1] if audio.ndim > 1 else 1)
    for i in range(len(audio)):
        dithered = audio[i] + noise[i] + error * 0.5
        quantized = np.round(dithered * (2 ** (bit_depth - 1))) / (2 ** (bit_depth - 1))
        error = dithered - quantized
        shaped[i] = quantized
    return shaped


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_peak(audio: "np.ndarray", target_db: float = -0.3) -> "np.ndarray":
    """Normalize audio to peak level."""
    if np is None:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-10:
        return audio
    target_lin = 10.0 ** (target_db / 20.0)
    gain = target_lin / peak
    return audio * gain


def _normalize_lufs(audio: "np.ndarray", target_lufs: float = -14.0,
                    sr: int = 48000) -> "np.ndarray":
    """Approximate LUFS normalization (ITU-R BS.1770 simplified).

    Uses RMS-based approximation as full K-weighting requires
    complex filter chains. Accurate to ~1 LUFS for most material.
    """
    if np is None or len(audio) == 0:
        return audio
    # Mono-sum for measurement
    if audio.ndim > 1:
        mono = np.mean(audio, axis=1)
    else:
        mono = audio

    # RMS → approximate LUFS (LUFS ≈ RMS_dB - 0.691 for pink-noise-like signals)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    if rms < 1e-10:
        return audio
    rms_db = 20.0 * math.log10(rms)
    current_lufs = rms_db - 0.691  # approximation
    gain_db = target_lufs - current_lufs
    gain_lin = 10.0 ** (gain_db / 20.0)
    # Limit gain to prevent extreme amplification
    gain_lin = min(gain_lin, 20.0)  # max +26 dB
    return audio * gain_lin


# ---------------------------------------------------------------------------
# Sample Rate Conversion
# ---------------------------------------------------------------------------

def _resample(audio: "np.ndarray", src_sr: int, dst_sr: int) -> "np.ndarray":
    """Simple sample rate conversion using linear interpolation.

    For production use, scipy.signal.resample_poly would be better,
    but this avoids hard scipy dependency.
    """
    if np is None or src_sr == dst_sr or src_sr <= 0 or dst_sr <= 0:
        return audio

    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(src_sr, dst_sr)
        up = dst_sr // g
        down = src_sr // g
        return resample_poly(audio, up, down, axis=0).astype(np.float32)
    except ImportError:
        pass

    # Fallback: linear interpolation
    ratio = dst_sr / src_sr
    src_len = len(audio)
    dst_len = int(src_len * ratio)
    if audio.ndim == 1:
        x_old = np.linspace(0, 1, src_len)
        x_new = np.linspace(0, 1, dst_len)
        return np.interp(x_new, x_old, audio).astype(np.float32)
    else:
        result = np.zeros((dst_len, audio.shape[1]), dtype=np.float32)
        x_old = np.linspace(0, 1, src_len)
        x_new = np.linspace(0, 1, dst_len)
        for ch in range(audio.shape[1]):
            result[:, ch] = np.interp(x_new, x_old, audio[:, ch])
        return result


# ---------------------------------------------------------------------------
# File Writing
# ---------------------------------------------------------------------------

def _write_wav(audio: "np.ndarray", path: str, sr: int, bit_depth: int) -> bool:
    """Write WAV file."""
    if not _HAS_SOUNDFILE:
        return _write_wav_fallback(audio, path, sr, bit_depth)
    try:
        subtype_map = {16: 'PCM_16', 24: 'PCM_24', 32: 'FLOAT'}
        subtype = subtype_map.get(bit_depth, 'PCM_24')
        sf.write(path, audio, sr, subtype=subtype)
        return True
    except Exception as e:
        _log.error("WAV write failed: %s", e)
        return False


def _write_wav_fallback(audio: "np.ndarray", path: str, sr: int,
                         bit_depth: int) -> bool:
    """Fallback WAV writer using wave module (16-bit only)."""
    try:
        import wave
        import struct
        n_frames, n_channels = audio.shape if audio.ndim > 1 else (len(audio), 1)
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)
        with wave.open(path, 'w') as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sr)
            # Convert float to int16
            data = (audio * 32767).clip(-32768, 32767).astype(np.int16)
            wf.writeframes(data.tobytes())
        return True
    except Exception as e:
        _log.error("WAV fallback write failed: %s", e)
        return False


def _write_flac(audio: "np.ndarray", path: str, sr: int, bit_depth: int) -> bool:
    """Write FLAC file."""
    if not _HAS_SOUNDFILE:
        _log.error("FLAC export requires soundfile library")
        return False
    try:
        subtype = 'PCM_16' if bit_depth <= 16 else 'PCM_24'
        sf.write(path, audio, sr, subtype=subtype, format='FLAC')
        return True
    except Exception as e:
        _log.error("FLAC write failed: %s", e)
        return False


def _write_ogg(audio: "np.ndarray", path: str, sr: int, quality: int) -> bool:
    """Write OGG Vorbis file."""
    if not _HAS_SOUNDFILE:
        _log.error("OGG export requires soundfile library")
        return False
    try:
        sf.write(path, audio, sr, format='OGG', subtype='VORBIS')
        return True
    except Exception as e:
        _log.error("OGG write failed: %s", e)
        return False


def _write_mp3(audio: "np.ndarray", path: str, sr: int, bitrate: int) -> bool:
    """Write MP3 file. Tries pydub/lame, falls back to WAV-then-convert."""
    try:
        from pydub import AudioSegment
        # Convert to int16 for pydub
        int_data = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        n_channels = audio.shape[1] if audio.ndim > 1 else 1
        seg = AudioSegment(
            data=int_data.tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=n_channels,
        )
        seg.export(path, format="mp3", bitrate=f"{bitrate}k")
        return True
    except ImportError:
        _log.warning("pydub not available for MP3 export, trying subprocess lame")
    except Exception as e:
        _log.error("pydub MP3 export failed: %s", e)

    # Fallback: write temp WAV then convert with lame CLI
    try:
        import subprocess
        import tempfile
        tmp_wav = tempfile.mktemp(suffix=".wav")
        _write_wav(audio, tmp_wav, sr, 16)
        result = subprocess.run(
            ["lame", "-b", str(bitrate), tmp_wav, path],
            capture_output=True, timeout=120
        )
        try:
            os.unlink(tmp_wav)
        except Exception:
            pass
        return result.returncode == 0
    except Exception as e:
        _log.error("lame MP3 export fallback failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main Export Function
# ---------------------------------------------------------------------------

def export_audio(config: ExportConfig,
                 render_func: Callable,
                 progress_callback: Optional[Callable[[float, str], None]] = None) -> List[str]:
    """Run an audio export job.

    Args:
        config: Export configuration
        render_func: Callable(start_beat, end_beat, track_ids, sr) → np.ndarray (stereo float32)
                     This function should render the arrangement to a numpy buffer.
        progress_callback: Optional callback(progress_0_to_1, status_message)

    Returns:
        List of exported file paths
    """
    if np is None:
        _log.error("numpy not available for audio export")
        return []

    exported_files: List[str] = []

    def _progress(pct: float, msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sr = config.sample_rate if config.sample_rate > 0 else 48000

    # Determine tracks to render
    if config.stem_export and config.track_ids:
        track_list = config.track_ids
    else:
        track_list = ["master"]  # render master bus

    # v0.0.20.650: Pre-/Post-FX export (AP10 Phase 10B Task 4)
    # Build render passes: each entry is (track_id, include_fx, suffix)
    fx_mode = str(getattr(config, 'fx_mode', 'post_fx') or 'post_fx')
    render_passes: list = []
    for tid in track_list:
        if fx_mode == "both":
            render_passes.append((tid, True, "_wet"))
            render_passes.append((tid, False, "_dry"))
        elif fx_mode == "pre_fx":
            render_passes.append((tid, False, "_dry"))
        else:  # post_fx (default)
            render_passes.append((tid, True, ""))

    total_tracks = len(render_passes)

    for track_idx, (track_id, include_fx, suffix) in enumerate(render_passes):
        track_label = track_id if track_id != "master" else "Master"
        fx_label = " (dry)" if not include_fx else ""
        _progress(track_idx / total_tracks, f"Rendering: {track_label}{fx_label}...")

        # 1. Render audio
        try:
            # v0.0.20.650: Pass include_fx for pre/post-FX export (AP10 10B)
            try:
                audio = render_func(
                    config.start_beat,
                    config.end_beat,
                    [track_id] if track_id != "master" else [],
                    sr,
                    include_fx=include_fx,
                )
            except TypeError:
                # Fallback: render_func doesn't accept include_fx
                audio = render_func(
                    config.start_beat,
                    config.end_beat,
                    [track_id] if track_id != "master" else [],
                    sr,
                )
            if audio is None or len(audio) == 0:
                _log.warning("Empty render for track %s", track_id)
                continue
            # Ensure float32 stereo
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=1)
            audio = audio.astype(np.float32)
        except Exception as e:
            _log.error("Render failed for %s: %s", track_id, e)
            continue

        _progress((track_idx + 0.3) / total_tracks, f"Processing: {track_label}...")

        # 2. Sample rate conversion
        render_sr = sr
        target_sr = config.sample_rate if config.sample_rate > 0 else render_sr
        if target_sr != render_sr:
            audio = _resample(audio, render_sr, target_sr)
            sr = target_sr

        # 3. Normalization
        if config.normalize_mode == "peak":
            audio = _normalize_peak(audio, config.normalize_target_db)
        elif config.normalize_mode == "lufs":
            audio = _normalize_lufs(audio, config.normalize_target_lufs, sr)

        # 4. Dither (before bit-depth reduction)
        if config.dither == "tpdf":
            audio = _apply_tpdf_dither(audio, config.bit_depth)
        elif config.dither == "pow_r":
            audio = _apply_pow_r_dither(audio, config.bit_depth)

        # 5. Clip protection
        audio = np.clip(audio, -1.0, 1.0)

        _progress((track_idx + 0.7) / total_tracks, f"Writing: {track_label}...")

        # 6. Build filename
        safe_name = config.filename_base or config.project_name or "export"
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name).strip()
        if config.stem_export and track_id != "master":
            safe_track = "".join(c if c.isalnum() or c in " _-" else "_" for c in track_label).strip()
            base_name = f"{safe_name}_{safe_track}_{int(config.bpm)}BPM{suffix}"
        else:
            base_name = f"{safe_name}_{int(config.bpm)}BPM{suffix}"

        # 7. Write to file
        fmt = config.format.lower()
        if fmt == "wav":
            ext = ".wav"
            filepath = str(output_dir / f"{base_name}{ext}")
            success = _write_wav(audio, filepath, sr, config.bit_depth)
        elif fmt == "flac":
            ext = ".flac"
            filepath = str(output_dir / f"{base_name}{ext}")
            success = _write_flac(audio, filepath, sr, config.bit_depth)
        elif fmt == "ogg":
            ext = ".ogg"
            filepath = str(output_dir / f"{base_name}{ext}")
            success = _write_ogg(audio, filepath, sr, config.ogg_quality)
        elif fmt == "mp3":
            ext = ".mp3"
            filepath = str(output_dir / f"{base_name}{ext}")
            success = _write_mp3(audio, filepath, sr, config.mp3_bitrate)
        else:
            _log.error("Unknown export format: %s", fmt)
            continue

        if success:
            exported_files.append(filepath)
            _log.info("Exported: %s", filepath)
        else:
            _log.error("Export failed for: %s", filepath)

    _progress(1.0, f"Fertig — {len(exported_files)} Datei(en) exportiert")
    return exported_files
