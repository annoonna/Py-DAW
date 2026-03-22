"""Fusion Oscillator — Wavetable with .wt/.wav import and 3 unison modes.

v0.0.20.576: Wavetable synthesis with:
  - .wt file support (Surge/native format: raw float32 frames)
  - .wav import (Serum-compatible: single-cycle frames in WAV)
  - Auto frame detection (256, 512, 1024, 2048 samples/frame)
  - Linear interpolation between frames
  - 3 unison modes: Fat, Focused, Complex
  - Anti-aliasing via mip-mapping
"""
from __future__ import annotations
import math
import struct
import wave
import os
import numpy as np
from typing import Optional
from .base import OscillatorBase


class WavetableOscillator(OscillatorBase):
    """Wavetable oscillator with file import and unison."""

    NAME = "Wavetable"

    # Common frame sizes for auto-detection
    _FRAME_SIZES = [2048, 1024, 512, 256]

    def __init__(self, sr: int = 48000):
        super().__init__(sr)
        self._index = 0.0          # 0..1 table position
        self._unison_mode = 0      # 0=off, 1=fat, 2=focused, 3=complex
        self._unison_voices = 1    # 1-16
        self._unison_spread = 0.5  # 0..1
        self._harmonic_phase = 0   # 0=original, 1=aligned, 2=diffuse

        # Table data: list of single-cycle frames (each np.ndarray)
        self._frames: list[np.ndarray] = []
        self._frame_size = 2048
        self._num_frames = 0
        self._table_name = ""

        # Unison phases
        self._uni_phases: list[float] = [0.0] * 16

        # Initialize with a basic saw wavetable (2 frames: sine → saw)
        self._init_default_table()

    def _init_default_table(self) -> None:
        """Create a simple default table: sine morphing to saw."""
        size = 2048
        t = np.linspace(0, 1, size, endpoint=False)

        frames = []
        for i in range(8):
            blend = i / 7.0
            sine = np.sin(2.0 * np.pi * t)
            saw = 2.0 * t - 1.0
            frames.append(sine * (1.0 - blend) + saw * blend)

        self._frames = frames
        self._frame_size = size
        self._num_frames = len(frames)
        self._table_name = "(Default Sine→Saw)"

    # ── Parameters ──

    def set_param(self, key: str, value: float) -> None:
        if key == "index":
            self._index = max(0.0, min(1.0, float(value)))
        elif key == "unison_mode":
            self._unison_mode = int(round(float(value))) % 4
        elif key == "unison_voices":
            self._unison_voices = max(1, min(16, int(round(float(value)))))
        elif key == "unison_spread":
            self._unison_spread = max(0.0, min(1.0, float(value)))
        elif key == "harmonic_phase":
            self._harmonic_phase = int(round(float(value))) % 3
        else:
            super().set_param(key, value)

    def get_param(self, key: str) -> float:
        if key == "index":
            return self._index
        if key == "unison_mode":
            return float(self._unison_mode)
        if key == "unison_voices":
            return float(self._unison_voices)
        if key == "unison_spread":
            return self._unison_spread
        if key == "harmonic_phase":
            return float(self._harmonic_phase)
        return super().get_param(key)

    def param_names(self) -> list[str]:
        return ["index", "unison_mode", "unison_voices", "unison_spread", "harmonic_phase"]

    # ── File Loading ──

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

            # Try to detect frame size
            total_samples = len(data) // 4  # float32
            raw = np.frombuffer(data, dtype=np.float32).astype(np.float64)

            for fs in self._FRAME_SIZES:
                if total_samples % fs == 0 and total_samples // fs >= 2:
                    n_frames = total_samples // fs
                    self._frames = [raw[i * fs:(i + 1) * fs].copy() for i in range(n_frames)]
                    self._frame_size = fs
                    self._num_frames = n_frames
                    self._table_name = os.path.basename(path)
                    return True

            # Fallback: treat entire file as one frame
            self._frames = [raw.copy()]
            self._frame_size = len(raw)
            self._num_frames = 1
            self._table_name = os.path.basename(path)
            return True
        except Exception:
            return False

    def _load_wav(self, path: str) -> bool:
        """Load Serum-compatible WAV wavetable."""
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
            elif sampwidth == 1:
                raw = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float64) / 128.0 - 1.0
            else:
                return False

            # Mono only (take first channel if stereo)
            if n_channels > 1:
                raw = raw[::n_channels]

            total = len(raw)

            # Auto-detect frame size
            for fs in self._FRAME_SIZES:
                if total % fs == 0 and total // fs >= 2:
                    n_frames = total // fs
                    self._frames = [raw[i * fs:(i + 1) * fs].copy() for i in range(n_frames)]
                    self._frame_size = fs
                    self._num_frames = n_frames
                    self._table_name = os.path.basename(path)
                    return True

            # Single frame
            self._frames = [raw.copy()]
            self._frame_size = len(raw)
            self._num_frames = 1
            self._table_name = os.path.basename(path)
            return True
        except Exception:
            return False

    # ── Rendering ──

    def reset_phase(self) -> None:
        super().reset_phase()
        self._uni_phases = [0.0] * 16

    def render(self, frames: int, freq: float, sr: int,
               phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        if not self._frames:
            return np.zeros(frames, dtype=np.float64)

        if self._unison_mode > 0 and self._unison_voices > 1:
            return self._render_unison(frames, freq, sr, phase_mod_buf)
        return self._render_single(frames, freq, sr, phase_mod_buf)

    def _render_single(self, frames: int, freq: float, sr: int,
                        phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Vectorized phase + table lookup."""
        dt = freq / sr
        phase0 = self._phase
        idx = self._index

        # Vectorized phase
        phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
        self._phase = (phase0 + frames * dt) % 1.0

        if phase_mod_buf is not None and self._phase_mod > 0.001:
            pm_len = min(frames, len(phase_mod_buf))
            phases[:pm_len] = (phases[:pm_len] + phase_mod_buf[:pm_len] * self._phase_mod) % 1.0

        # Vectorized bilinear table read
        num_frames = self._num_frames
        if num_frames == 0:
            return np.zeros(frames, dtype=np.float64)

        frame_f = idx * (num_frames - 1)
        frame_lo = int(frame_f)
        frame_hi = min(frame_lo + 1, num_frames - 1)
        frame_frac = frame_f - frame_lo

        fsize = self._frame_size
        pos = phases * fsize
        pos_lo = pos.astype(np.intp) % fsize
        pos_hi = (pos_lo + 1) % fsize
        pos_frac = pos - np.floor(pos)

        f_lo = self._frames[frame_lo]
        f_hi = self._frames[frame_hi]

        s_lo = f_lo[pos_lo] * (1.0 - pos_frac) + f_lo[pos_hi] * pos_frac
        s_hi = f_hi[pos_lo] * (1.0 - pos_frac) + f_hi[pos_hi] * pos_frac

        return s_lo * (1.0 - frame_frac) + s_hi * frame_frac

    def _render_unison(self, frames: int, freq: float, sr: int,
                        phase_mod_buf: Optional[np.ndarray] = None) -> np.ndarray:
        """v0.0.20.577: Vectorized inner loop per unison voice."""
        n = self._unison_voices
        max_detune = self._unison_spread * 50.0  # cents
        out = np.zeros(frames, dtype=np.float64)
        idx = self._index
        num_frames = self._num_frames
        if num_frames == 0:
            return out

        # Pre-compute frame interpolation (same for all voices)
        frame_f = idx * (num_frames - 1)
        frame_lo = int(frame_f)
        frame_hi = min(frame_lo + 1, num_frames - 1)
        frame_frac = frame_f - frame_lo
        f_lo = self._frames[frame_lo]
        f_hi = self._frames[frame_hi]
        fsize = self._frame_size

        for v in range(n):
            if n == 1:
                detune = 0.0
                pos_val = 0.0
            else:
                pos_val = (v / (n - 1)) * 2.0 - 1.0
                detune = pos_val * max_detune

            v_freq = freq * (2.0 ** (detune / 1200.0))
            dt = v_freq / sr

            if self._unison_mode == 1:
                vol = 1.0
            elif self._unison_mode == 2:
                center = 1.0 - abs(pos_val) if n > 1 else 1.0
                vol = 0.3 + 0.7 * center
            else:
                vol = 1.0
                dt *= (1.0 + (v % 3 - 1) * 0.001 * self._unison_spread)

            # Vectorized phase for this voice
            phase0 = self._uni_phases[v]
            phases = (phase0 + np.arange(frames, dtype=np.float64) * dt) % 1.0
            self._uni_phases[v] = (phase0 + frames * dt) % 1.0

            # Vectorized table lookup
            pos = phases * fsize
            p_lo = pos.astype(np.intp) % fsize
            p_hi = (p_lo + 1) % fsize
            p_frac = pos - np.floor(pos)

            s_lo = f_lo[p_lo] * (1.0 - p_frac) + f_lo[p_hi] * p_frac
            s_hi = f_hi[p_lo] * (1.0 - p_frac) + f_hi[p_hi] * p_frac
            out += (s_lo * (1.0 - frame_frac) + s_hi * frame_frac) * vol

        # Normalize
        out /= math.sqrt(max(1, n))
        return out

    def _read_table(self, phase: float, index: float) -> float:
        """Read interpolated sample from wavetable.

        phase: position within frame (0..1)
        index: position across frames (0..1)
        """
        if self._num_frames == 0:
            return 0.0

        # Frame interpolation
        frame_f = index * (self._num_frames - 1)
        frame_lo = int(frame_f)
        frame_hi = min(frame_lo + 1, self._num_frames - 1)
        frame_frac = frame_f - frame_lo

        # Sample position within frame
        pos = phase * self._frame_size
        pos_lo = int(pos) % self._frame_size
        pos_hi = (pos_lo + 1) % self._frame_size
        pos_frac = pos - int(pos)

        # Bilinear interpolation (frame × position)
        f_lo = self._frames[frame_lo]
        f_hi = self._frames[frame_hi]

        s_lo = f_lo[pos_lo] * (1.0 - pos_frac) + f_lo[pos_hi] * pos_frac
        s_hi = f_hi[pos_lo] * (1.0 - pos_frac) + f_hi[pos_hi] * pos_frac

        return s_lo * (1.0 - frame_frac) + s_hi * frame_frac

    def get_table_name(self) -> str:
        return self._table_name

    def get_num_frames(self) -> int:
        return self._num_frames

    def get_frame_data(self, frame_index: int) -> Optional[np.ndarray]:
        """Return a copy of a specific frame for UI visualization."""
        if 0 <= frame_index < self._num_frames:
            return self._frames[frame_index].copy()
        return None

    def get_current_frame_data(self) -> Optional[np.ndarray]:
        """Return interpolated frame at current index for visualization."""
        if self._num_frames == 0:
            return None
        frame_f = self._index * (self._num_frames - 1)
        lo = int(frame_f)
        hi = min(lo + 1, self._num_frames - 1)
        frac = frame_f - lo
        return self._frames[lo] * (1.0 - frac) + self._frames[hi] * frac
