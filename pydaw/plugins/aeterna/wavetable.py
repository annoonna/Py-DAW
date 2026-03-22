# -*- coding: utf-8 -*-
"""AETERNA Wavetable module — import, draw, FFT, morphing.

v0.0.20.657: Wavetable subsystem for AETERNA synthesizer
- Serum-compatible .wav import (single-cycle frames concatenated)
- .wt file support (Surge/raw float32 frames)
- Wavetable drawing (per-frame waveform editing)
- FFT-based additive synthesis (harmonic editor)
- Default wavetable library (Basic, Analog, Digital, Vocal, Noise)
- Frame morphing with position parameter (0..1)
- Unison engine with detune, spread, stereo width
- Thread-safe access for real-time audio rendering
"""
from __future__ import annotations

import base64
import math
import os
import struct
import threading
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

TWOPI = 2.0 * math.pi

# Common single-cycle frame sizes for auto-detection
_FRAME_SIZES = [2048, 1024, 512, 256]

# Default frame size for generated tables
DEFAULT_FRAME_SIZE = 2048

# Maximum number of frames in a wavetable
MAX_FRAMES = 256

# Maximum number of unison voices
MAX_UNISON_VOICES = 16


# ─── Default wavetable generators ───────────────────────────────────────────

def _gen_sine_to_saw(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate wavetable morphing from sine to saw."""
    t = np.linspace(0, 1, size, endpoint=False)
    frames = []
    for i in range(n_frames):
        blend = i / max(1, n_frames - 1)
        sine = np.sin(TWOPI * t)
        # Additive saw with increasing harmonics
        saw = np.zeros(size, dtype=np.float64)
        n_harm = 2 + int(blend * 30)
        for h in range(1, n_harm + 1):
            saw += ((-1.0) ** (h + 1)) * np.sin(TWOPI * h * t) / h
        saw *= 2.0 / np.pi
        frames.append(sine * (1.0 - blend) + saw * blend)
    return frames


def _gen_sine_to_square(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate wavetable morphing from sine to square."""
    t = np.linspace(0, 1, size, endpoint=False)
    frames = []
    for i in range(n_frames):
        blend = i / max(1, n_frames - 1)
        sine = np.sin(TWOPI * t)
        # Additive square
        square = np.zeros(size, dtype=np.float64)
        n_harm = 2 + int(blend * 20)
        for h in range(1, n_harm + 1, 2):
            square += np.sin(TWOPI * h * t) / h
        square *= 4.0 / np.pi
        frames.append(sine * (1.0 - blend) + square * blend)
    return frames


def _gen_pwm(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate pulse-width modulation wavetable."""
    t = np.linspace(0, 1, size, endpoint=False)
    frames = []
    for i in range(n_frames):
        duty = 0.10 + (i / max(1, n_frames - 1)) * 0.80
        frame = np.where(t < duty, 1.0, -1.0).astype(np.float64)
        # Smooth edges slightly
        frame = np.convolve(frame, np.hanning(8) / np.hanning(8).sum(), mode='same')
        frames.append(frame)
    return frames


def _gen_formant(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate vocal formant wavetable (A→E→I→O→U)."""
    t = np.linspace(0, 1, size, endpoint=False)
    # Formant frequencies (simplified, normalized)
    vowel_formants = [
        (2.2, 4.8, 0.7),   # A
        (1.8, 5.6, 0.5),   # E
        (1.2, 6.4, 0.4),   # I
        (2.0, 3.2, 0.8),   # O
        (1.4, 2.8, 0.6),   # U
    ]
    frames = []
    for i in range(n_frames):
        pos = (i / max(1, n_frames - 1)) * (len(vowel_formants) - 1)
        idx_lo = int(pos)
        idx_hi = min(idx_lo + 1, len(vowel_formants) - 1)
        frac = pos - idx_lo
        f1a, f2a, amp_a = vowel_formants[idx_lo]
        f1b, f2b, amp_b = vowel_formants[idx_hi]
        f1 = f1a * (1 - frac) + f1b * frac
        f2 = f2a * (1 - frac) + f2b * frac
        amp = amp_a * (1 - frac) + amp_b * frac
        # Simple formant synthesis
        carrier = np.sin(TWOPI * t)
        formant1 = np.sin(TWOPI * f1 * t) * np.exp(-4.0 * t)
        formant2 = np.sin(TWOPI * f2 * t) * np.exp(-6.0 * t) * 0.5
        frame = carrier * 0.3 + formant1 * amp + formant2 * (1.0 - amp) * 0.4
        frame = frame / max(0.01, float(np.max(np.abs(frame))))
        frames.append(frame)
    return frames


def _gen_noise_morph(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate noise morphing wavetable (clean sine → noisy)."""
    t = np.linspace(0, 1, size, endpoint=False)
    rng = np.random.default_rng(42)
    frames = []
    for i in range(n_frames):
        blend = i / max(1, n_frames - 1)
        sine = np.sin(TWOPI * t)
        noise = rng.uniform(-1.0, 1.0, size)
        # Filtered noise: less harsh at low blend
        if blend < 0.5:
            kernel_size = max(3, int((1.0 - blend * 2.0) * 32))
            kernel = np.hanning(kernel_size)
            kernel /= kernel.sum()
            noise = np.convolve(noise, kernel, mode='same')
        frame = sine * (1.0 - blend) + noise * blend
        frame = frame / max(0.01, float(np.max(np.abs(frame))))
        frames.append(frame)
    return frames


def _gen_additive_harmonics(n_frames: int = 16, size: int = DEFAULT_FRAME_SIZE) -> List[np.ndarray]:
    """Generate additive harmonic sweep wavetable."""
    t = np.linspace(0, 1, size, endpoint=False)
    frames = []
    for i in range(n_frames):
        frame = np.zeros(size, dtype=np.float64)
        n_harm = 1 + i * 2
        for h in range(1, n_harm + 1):
            amp = 1.0 / (h ** (0.5 + (i / max(1, n_frames - 1)) * 1.5))
            phase_offset = (h * 0.3 * i / max(1, n_frames - 1)) % TWOPI
            frame += amp * np.sin(TWOPI * h * t + phase_offset)
        peak = float(np.max(np.abs(frame)))
        if peak > 0.01:
            frame /= peak
        frames.append(frame)
    return frames


# Registry of built-in wavetables
BUILTIN_WAVETABLES: Dict[str, dict] = {
    "Basic (Sine→Saw)": {"generator": _gen_sine_to_saw, "category": "Basic"},
    "Basic (Sine→Square)": {"generator": _gen_sine_to_square, "category": "Basic"},
    "PWM (Pulse Width)": {"generator": _gen_pwm, "category": "Analog"},
    "Formant (Vowels)": {"generator": _gen_formant, "category": "Vocal"},
    "Noise Morph": {"generator": _gen_noise_morph, "category": "Noise"},
    "Harmonic Sweep": {"generator": _gen_additive_harmonics, "category": "Digital"},
}


# ─── Wavetable Bank ─────────────────────────────────────────────────────────

class WavetableBank:
    """Holds wavetable frames with import/export, draw, and FFT capabilities.

    Thread-safe: rendering reads are lock-free via atomic reference swap (GIL-safe).
    Mutations acquire _lock.
    """

    def __init__(self, frame_size: int = DEFAULT_FRAME_SIZE):
        self._lock = threading.RLock()
        self._frame_size: int = int(frame_size or DEFAULT_FRAME_SIZE)
        self._frames: List[np.ndarray] = []
        self._num_frames: int = 0
        self._table_name: str = ""
        self._file_path: str = ""
        # Initialize with default sine→saw
        self.load_builtin("Basic (Sine→Saw)")

    # ── Properties (thread-safe reads) ──

    @property
    def frame_size(self) -> int:
        return self._frame_size

    @property
    def num_frames(self) -> int:
        return self._num_frames

    @property
    def table_name(self) -> str:
        return self._table_name

    @property
    def file_path(self) -> str:
        return self._file_path

    # ── Built-in loading ──

    def load_builtin(self, name: str) -> bool:
        """Load a built-in wavetable by name."""
        spec = BUILTIN_WAVETABLES.get(name)
        if spec is None:
            return False
        try:
            gen = spec["generator"]
            frames = gen(n_frames=16, size=self._frame_size)
            with self._lock:
                self._frames = [np.asarray(f, dtype=np.float64) for f in frames]
                self._num_frames = len(self._frames)
                self._table_name = name
                self._file_path = ""
            return True
        except Exception:
            return False

    # ── File import ──

    def load_file(self, path: str) -> bool:
        """Load a .wt or .wav wavetable file. Returns True on success."""
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".wt":
                return self._load_wt(path)
            elif ext == ".wav":
                return self._load_wav(path)
            return False
        except Exception:
            return False

    def _load_wt(self, path: str) -> bool:
        """Load Surge-format .wt file (raw float32 frames)."""
        try:
            data = open(path, "rb").read()
            if len(data) < 16:
                return False
            total_samples = len(data) // 4
            raw = np.frombuffer(data, dtype=np.float32).astype(np.float64)

            for fs in _FRAME_SIZES:
                if total_samples % fs == 0 and total_samples // fs >= 2:
                    n_frames = min(total_samples // fs, MAX_FRAMES)
                    frames = [raw[i * fs:(i + 1) * fs].copy() for i in range(n_frames)]
                    with self._lock:
                        self._frames = frames
                        self._frame_size = fs
                        self._num_frames = n_frames
                        self._table_name = os.path.basename(path)
                        self._file_path = path
                    return True
            # Fallback: single frame
            with self._lock:
                self._frames = [raw[:self._frame_size].copy() if len(raw) >= self._frame_size else raw.copy()]
                self._num_frames = 1
                self._table_name = os.path.basename(path)
                self._file_path = path
            return True
        except Exception:
            return False

    def _load_wav(self, path: str) -> bool:
        """Load Serum-compatible WAV wavetable (single-cycle frames concatenated)."""
        try:
            with wave.open(path, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                n_samples = wf.getnframes()
                raw_bytes = wf.readframes(n_samples)

            # Convert to float64
            if sampwidth == 2:
                raw = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float64) / 32768.0
            elif sampwidth == 4:
                raw = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float64) / 2147483648.0
            elif sampwidth == 3:
                # 24-bit: unpack manually
                samples = []
                for i in range(0, len(raw_bytes), 3):
                    if i + 2 < len(raw_bytes):
                        val = struct.unpack_from('<i', raw_bytes[i:i+3] + b'\x00')[0] >> 8
                        samples.append(val / 8388608.0)
                raw = np.array(samples, dtype=np.float64)
            elif sampwidth == 1:
                raw = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float64) / 128.0 - 1.0
            else:
                return False

            # Mono (take first channel if stereo)
            if n_channels > 1:
                raw = raw[::n_channels]

            total = len(raw)
            # Try Serum clm chunk detection for frame size
            frame_size_detected = self._detect_serum_frame_size(path, total)

            if frame_size_detected and total % frame_size_detected == 0:
                n_frames = min(total // frame_size_detected, MAX_FRAMES)
                frames = [raw[i * frame_size_detected:(i + 1) * frame_size_detected].copy()
                          for i in range(n_frames)]
                with self._lock:
                    self._frames = frames
                    self._frame_size = frame_size_detected
                    self._num_frames = n_frames
                    self._table_name = os.path.basename(path)
                    self._file_path = path
                return True

            # Auto-detect frame size
            for fs in _FRAME_SIZES:
                if total % fs == 0 and total // fs >= 2:
                    n_frames = min(total // fs, MAX_FRAMES)
                    frames = [raw[i * fs:(i + 1) * fs].copy() for i in range(n_frames)]
                    with self._lock:
                        self._frames = frames
                        self._frame_size = fs
                        self._num_frames = n_frames
                        self._table_name = os.path.basename(path)
                        self._file_path = path
                    return True

            # Single frame fallback
            with self._lock:
                self._frames = [raw.copy()]
                self._frame_size = len(raw)
                self._num_frames = 1
                self._table_name = os.path.basename(path)
                self._file_path = path
            return True
        except Exception:
            return False

    def _detect_serum_frame_size(self, path: str, total_samples: int) -> Optional[int]:
        """Try to detect Serum's 'clm ' chunk which encodes frame size."""
        try:
            with open(path, "rb") as f:
                data = f.read()
            idx = data.find(b'clm ')
            if idx < 0:
                return None
            # Serum stores frame size as ASCII text after 'clm ' chunk header
            chunk_start = idx + 8  # skip 'clm ' + 4-byte size
            text = data[chunk_start:chunk_start + 32]
            for line in text.decode('ascii', errors='ignore').split('\n'):
                line = line.strip()
                if line.isdigit():
                    fs = int(line)
                    if fs in _FRAME_SIZES or (64 <= fs <= 8192 and total_samples % fs == 0):
                        return fs
            return None
        except Exception:
            return None

    # ── Drawing / editing ──

    def draw_frame(self, frame_index: int, samples: np.ndarray) -> bool:
        """Replace a single frame's waveform with drawn data."""
        with self._lock:
            if frame_index < 0 or frame_index >= self._num_frames:
                return False
            arr = np.asarray(samples, dtype=np.float64)
            if arr.size != self._frame_size:
                # Resample to match frame size
                x_old = np.linspace(0, 1, arr.size)
                x_new = np.linspace(0, 1, self._frame_size)
                arr = np.interp(x_new, x_old, arr)
            self._frames[frame_index] = np.clip(arr, -1.0, 1.0)
            return True

    def add_frame(self, samples: Optional[np.ndarray] = None) -> int:
        """Add a new frame (copy of last frame or provided samples). Returns new index."""
        with self._lock:
            if self._num_frames >= MAX_FRAMES:
                return -1
            if samples is not None:
                arr = np.asarray(samples, dtype=np.float64)
                if arr.size != self._frame_size:
                    x_old = np.linspace(0, 1, arr.size)
                    x_new = np.linspace(0, 1, self._frame_size)
                    arr = np.interp(x_new, x_old, arr)
            elif self._frames:
                arr = self._frames[-1].copy()
            else:
                arr = np.zeros(self._frame_size, dtype=np.float64)
            arr = np.clip(arr, -1.0, 1.0)
            self._frames.append(arr)
            self._num_frames = len(self._frames)
            return self._num_frames - 1

    def remove_frame(self, frame_index: int) -> bool:
        """Remove a frame (minimum 1 frame must remain)."""
        with self._lock:
            if self._num_frames <= 1 or frame_index < 0 or frame_index >= self._num_frames:
                return False
            self._frames.pop(frame_index)
            self._num_frames = len(self._frames)
            return True

    # ── FFT-based harmonic editing ──

    def get_frame_harmonics(self, frame_index: int, max_harmonics: int = 64) -> Optional[np.ndarray]:
        """Get harmonic amplitudes of a frame via FFT. Returns array of amplitudes."""
        with self._lock:
            if frame_index < 0 or frame_index >= self._num_frames:
                return None
            frame = self._frames[frame_index].copy()
        fft = np.fft.rfft(frame)
        magnitudes = np.abs(fft)
        # Normalize
        peak = float(np.max(magnitudes[1:])) if len(magnitudes) > 1 else 1.0
        if peak > 1e-8:
            magnitudes /= peak
        return magnitudes[1:max_harmonics + 1]

    def set_frame_from_harmonics(self, frame_index: int, harmonics: np.ndarray,
                                  phases: Optional[np.ndarray] = None) -> bool:
        """Reconstruct a frame from harmonic amplitudes via inverse FFT."""
        with self._lock:
            if frame_index < 0 or frame_index >= self._num_frames:
                return False
            n_bins = self._frame_size // 2 + 1
            spectrum = np.zeros(n_bins, dtype=np.complex128)
            harms = np.asarray(harmonics, dtype=np.float64)
            ph = np.asarray(phases, dtype=np.float64) if phases is not None else np.zeros(len(harms))
            for i, (amp, angle) in enumerate(zip(harms, ph)):
                bin_idx = i + 1
                if bin_idx < n_bins:
                    spectrum[bin_idx] = amp * np.exp(1j * angle)
            frame = np.fft.irfft(spectrum, n=self._frame_size)
            peak = float(np.max(np.abs(frame)))
            if peak > 1e-8:
                frame /= peak
            self._frames[frame_index] = frame
            return True

    def normalize_frame(self, frame_index: int) -> bool:
        """Normalize a single frame to peak amplitude 1.0."""
        with self._lock:
            if frame_index < 0 or frame_index >= self._num_frames:
                return False
            frame = self._frames[frame_index]
            peak = float(np.max(np.abs(frame)))
            if peak > 1e-8:
                self._frames[frame_index] = frame / peak
            return True

    def normalize_all(self) -> None:
        """Normalize all frames to consistent peak amplitude."""
        with self._lock:
            global_peak = 0.0
            for f in self._frames:
                global_peak = max(global_peak, float(np.max(np.abs(f))))
            if global_peak > 1e-8:
                for i in range(self._num_frames):
                    self._frames[i] = self._frames[i] / global_peak

    # ── Rendering (lock-free reads) ──

    def read_sample(self, phase: float, position: float) -> float:
        """Read single interpolated sample. phase: 0..1, position: 0..1."""
        frames = self._frames  # atomic read
        n = self._num_frames
        if n == 0:
            return 0.0
        # Frame interpolation
        frame_f = position * (n - 1)
        frame_lo = int(frame_f)
        frame_hi = min(frame_lo + 1, n - 1)
        frame_frac = frame_f - frame_lo

        fsize = self._frame_size
        pos = phase * fsize
        pos_lo = int(pos) % fsize
        pos_hi = (pos_lo + 1) % fsize
        pos_frac = pos - int(pos)

        f_lo = frames[frame_lo]
        f_hi = frames[frame_hi]

        s_lo = float(f_lo[pos_lo]) * (1.0 - pos_frac) + float(f_lo[pos_hi]) * pos_frac
        s_hi = float(f_hi[pos_lo]) * (1.0 - pos_frac) + float(f_hi[pos_hi]) * pos_frac
        return s_lo * (1.0 - frame_frac) + s_hi * frame_frac

    def read_block(self, phases: np.ndarray, position: float) -> np.ndarray:
        """Vectorized block read. phases: array of 0..1, position: 0..1.
        Returns float64 array of samples."""
        frames = self._frames  # atomic read
        n = self._num_frames
        if n == 0:
            return np.zeros(len(phases), dtype=np.float64)

        frame_f = position * (n - 1)
        frame_lo = int(frame_f)
        frame_hi = min(frame_lo + 1, n - 1)
        frame_frac = frame_f - frame_lo

        fsize = self._frame_size
        pos = phases * fsize
        pos_lo = pos.astype(np.intp) % fsize
        pos_hi = (pos_lo + 1) % fsize
        pos_frac = pos - np.floor(pos)

        f_lo = frames[frame_lo]
        f_hi = frames[frame_hi]

        s_lo = f_lo[pos_lo] * (1.0 - pos_frac) + f_lo[pos_hi] * pos_frac
        s_hi = f_hi[pos_lo] * (1.0 - pos_frac) + f_hi[pos_hi] * pos_frac

        return s_lo * (1.0 - frame_frac) + s_hi * frame_frac

    def read_block_modulated(self, phases: np.ndarray, position: np.ndarray) -> np.ndarray:
        """Block read with per-sample position modulation (for automation)."""
        frames = self._frames  # atomic read
        n = self._num_frames
        if n == 0:
            return np.zeros(len(phases), dtype=np.float64)

        pos_arr = np.clip(position, 0.0, 1.0) * (n - 1)
        frame_lo = np.clip(pos_arr.astype(np.intp), 0, n - 1)
        frame_hi = np.clip(frame_lo + 1, 0, n - 1)
        frame_frac = pos_arr - frame_lo.astype(np.float64)

        fsize = self._frame_size
        ph_pos = phases * fsize
        ph_lo = ph_pos.astype(np.intp) % fsize
        ph_hi = (ph_lo + 1) % fsize
        ph_frac = ph_pos - np.floor(ph_pos)

        # Gather samples from frames
        out = np.zeros(len(phases), dtype=np.float64)
        for i in range(n):
            mask_lo = (frame_lo == i)
            mask_hi = (frame_hi == i)
            if not np.any(mask_lo) and not np.any(mask_hi):
                continue
            f = frames[i]
            if np.any(mask_lo):
                s = f[ph_lo[mask_lo]] * (1.0 - ph_frac[mask_lo]) + f[ph_hi[mask_lo]] * ph_frac[mask_lo]
                out[mask_lo] += s * (1.0 - frame_frac[mask_lo])
            if np.any(mask_hi):
                s = f[ph_lo[mask_hi]] * (1.0 - ph_frac[mask_hi]) + f[ph_hi[mask_hi]] * ph_frac[mask_hi]
                out[mask_hi] += s * frame_frac[mask_hi]
        return out

    # ── Visualization ──

    def get_frame_data(self, frame_index: int) -> Optional[np.ndarray]:
        """Return copy of frame for UI visualization."""
        with self._lock:
            if 0 <= frame_index < self._num_frames:
                return self._frames[frame_index].copy()
        return None

    def get_interpolated_frame(self, position: float) -> Optional[np.ndarray]:
        """Return interpolated frame at position (0..1) for visualization."""
        with self._lock:
            if self._num_frames == 0:
                return None
            pos = max(0.0, min(1.0, position))
            frame_f = pos * (self._num_frames - 1)
            lo = int(frame_f)
            hi = min(lo + 1, self._num_frames - 1)
            frac = frame_f - lo
            return self._frames[lo] * (1.0 - frac) + self._frames[hi] * frac

    # ── Serialization ──

    def export_state(self) -> dict:
        """Export wavetable state for project save."""
        with self._lock:
            # Store frames as base64-encoded float32 blob
            if self._frames:
                combined = np.concatenate([f.astype(np.float32) for f in self._frames])
                blob = base64.b64encode(combined.tobytes()).decode('ascii')
            else:
                blob = ""
            return {
                "table_name": self._table_name,
                "file_path": self._file_path,
                "frame_size": self._frame_size,
                "num_frames": self._num_frames,
                "frames_blob": blob,
            }

    def import_state(self, d: dict) -> bool:
        """Restore wavetable state from project load."""
        if not isinstance(d, dict):
            return False
        try:
            name = str(d.get("table_name", ""))
            fpath = str(d.get("file_path", ""))
            fsize = int(d.get("frame_size", DEFAULT_FRAME_SIZE))
            nframes = int(d.get("num_frames", 0))
            blob = str(d.get("frames_blob", ""))

            if blob and nframes > 0:
                raw = np.frombuffer(base64.b64decode(blob), dtype=np.float32).astype(np.float64)
                expected = fsize * nframes
                if raw.size >= expected:
                    frames = [raw[i * fsize:(i + 1) * fsize].copy() for i in range(nframes)]
                    with self._lock:
                        self._frames = frames
                        self._frame_size = fsize
                        self._num_frames = nframes
                        self._table_name = name
                        self._file_path = fpath
                    return True

            # Fallback: try loading from file path
            if fpath and os.path.isfile(fpath):
                return self.load_file(fpath)

            # Fallback: try built-in
            if name and name in BUILTIN_WAVETABLES:
                return self.load_builtin(name)

            return False
        except Exception:
            return False


# ─── Unison Engine ───────────────────────────────────────────────────────────

@dataclass
class UnisonVoiceState:
    """Per-voice state for unison rendering."""
    phase: float = 0.0
    detune_cents: float = 0.0
    pan: float = 0.0  # -1..+1
    level: float = 1.0


class UnisonEngine:
    """Wavetable-aware unison engine with detune, spread, and stereo width.

    Modes:
    - Classic: even detune spread, equal levels
    - Supersaw: wider detune, slight level taper at edges
    - Hyper: extreme detune with random per-voice phase offsets
    """

    MODES = ("Off", "Classic", "Supersaw", "Hyper")

    def __init__(self):
        self._mode: int = 0  # 0=off, 1=classic, 2=supersaw, 3=hyper
        self._num_voices: int = 1
        self._detune: float = 0.20  # 0..1 → cents range
        self._spread: float = 0.50  # stereo spread 0..1
        self._width: float = 0.50   # stereo width 0..1
        self._voices: List[UnisonVoiceState] = [UnisonVoiceState()]
        self._rng = np.random.default_rng(12345)

    def configure(self, mode: int = 0, num_voices: int = 1,
                  detune: float = 0.20, spread: float = 0.50,
                  width: float = 0.50) -> None:
        """Configure unison parameters."""
        self._mode = max(0, min(3, int(mode)))
        self._num_voices = max(1, min(MAX_UNISON_VOICES, int(num_voices)))
        self._detune = max(0.0, min(1.0, float(detune)))
        self._spread = max(0.0, min(1.0, float(spread)))
        self._width = max(0.0, min(1.0, float(width)))
        self._rebuild_voices()

    def _rebuild_voices(self) -> None:
        """Rebuild voice array with proper detune/pan distribution."""
        n = self._num_voices
        mode = self._mode
        max_detune_cents = self._detune * 60.0  # 0..60 cents range

        new_voices = []
        for v in range(n):
            vs = UnisonVoiceState()
            if n == 1:
                vs.detune_cents = 0.0
                vs.pan = 0.0
                vs.level = 1.0
            else:
                pos = (v / (n - 1)) * 2.0 - 1.0  # -1..+1

                if mode == 1:  # Classic
                    vs.detune_cents = pos * max_detune_cents
                    vs.pan = pos * self._spread
                    vs.level = 1.0
                elif mode == 2:  # Supersaw
                    vs.detune_cents = pos * max_detune_cents * 1.3
                    vs.pan = pos * self._spread
                    vs.level = 1.0 - abs(pos) * 0.25
                elif mode == 3:  # Hyper
                    vs.detune_cents = pos * max_detune_cents * 1.8
                    vs.pan = pos * self._spread
                    vs.level = 0.8 + float(self._rng.uniform(0, 0.2))
                    vs.phase = float(self._rng.uniform(0, 1))  # random start phase
                else:
                    vs.detune_cents = 0.0
                    vs.pan = 0.0
                    vs.level = 1.0

            # Preserve phase from existing voices
            if v < len(self._voices):
                if mode != 3:  # Hyper gets random phases
                    vs.phase = self._voices[v].phase
            new_voices.append(vs)

        self._voices = new_voices

    def render_block(self, bank: WavetableBank, base_freq: float,
                     frames: int, sr: int, position: float) -> Tuple[np.ndarray, np.ndarray]:
        """Render unison voices through wavetable bank.

        Returns (left, right) stereo arrays.
        """
        if self._mode == 0 or self._num_voices <= 1:
            # Single voice, no unison
            vs = self._voices[0] if self._voices else UnisonVoiceState()
            dt = base_freq / float(sr)
            phases = (vs.phase + np.arange(frames, dtype=np.float64) * dt) % 1.0
            vs.phase = float((vs.phase + frames * dt) % 1.0)
            sig = bank.read_block(phases, position)
            return sig.copy(), sig.copy()

        out_l = np.zeros(frames, dtype=np.float64)
        out_r = np.zeros(frames, dtype=np.float64)
        width = self._width

        for vs in self._voices:
            v_freq = base_freq * (2.0 ** (vs.detune_cents / 1200.0))
            dt = v_freq / float(sr)
            phases = (vs.phase + np.arange(frames, dtype=np.float64) * dt) % 1.0
            vs.phase = float((vs.phase + frames * dt) % 1.0)
            sig = bank.read_block(phases, position) * vs.level

            # Stereo panning
            pan = vs.pan * width
            gain_l = math.sqrt(max(0.0, 0.5 * (1.0 - pan)))
            gain_r = math.sqrt(max(0.0, 0.5 * (1.0 + pan)))
            out_l += sig * gain_l
            out_r += sig * gain_r

        # Normalize by sqrt(n) to maintain consistent level
        norm = 1.0 / math.sqrt(max(1, self._num_voices))
        return out_l * norm, out_r * norm

    def reset_phases(self) -> None:
        """Reset all voice phases (e.g. on note-on with retrigger)."""
        if self._mode == 3:  # Hyper keeps random phases
            for vs in self._voices:
                vs.phase = float(self._rng.uniform(0, 1))
        else:
            for vs in self._voices:
                vs.phase = 0.0

    def export_state(self) -> dict:
        return {
            "mode": self._mode,
            "num_voices": self._num_voices,
            "detune": self._detune,
            "spread": self._spread,
            "width": self._width,
        }

    def import_state(self, d: dict) -> None:
        if not isinstance(d, dict):
            return
        self.configure(
            mode=int(d.get("mode", 0)),
            num_voices=int(d.get("num_voices", 1)),
            detune=float(d.get("detune", 0.20)),
            spread=float(d.get("spread", 0.50)),
            width=float(d.get("width", 0.50)),
        )
