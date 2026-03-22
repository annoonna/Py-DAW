"""Lock-Free Ring Buffer for DAW-grade Audio↔GUI Communication (v0.0.20.14).

Design:
- Uses numpy arrays backed by contiguous memory (mmap-friendly)
- Single-producer / single-consumer (SPSC) — NO LOCKS EVER
- Audio thread writes, GUI thread reads (or vice versa)
- Atomic index updates via Python GIL (int read/write is atomic under CPython)
- Zero allocations after init
- Supports both float32 parameter rings and stereo audio rings

v0.0.20.14 Additions:
- Per-track volume/pan/mute/solo via ParamRingBuffer (track param IDs)
- SharedMemory backing option for multi-process ring buffers
- TrackParamState: local per-track parameter cache for audio thread
"""
from __future__ import annotations

from typing import List, Tuple, Optional, Iterator, Dict

try:
    import numpy as np
except Exception:
    np = None

# Optional SharedMemory support (Python 3.8+)
_SHM_AVAILABLE = False
try:
    from multiprocessing import shared_memory
    _SHM_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Parameter ID scheme for per-track params
# ---------------------------------------------------------------------------

PARAM_MASTER_VOL = 0
PARAM_MASTER_PAN = 1

# Per-track: base_id = 100 + track_index * 10
PARAM_TRACK_BASE = 100
PARAM_TRACK_STRIDE = 10
TRACK_VOL = 0
TRACK_PAN = 1
TRACK_MUTE = 2
TRACK_SOLO = 3

MAX_TRACKS = 128


def track_param_id(track_idx: int, param_offset: int) -> int:
    """Compute ring buffer param_id for a track parameter."""
    return PARAM_TRACK_BASE + (int(track_idx) * PARAM_TRACK_STRIDE) + int(param_offset)


def decode_track_param(param_id: int) -> Tuple[int, int]:
    """Decode param_id back to (track_idx, param_offset). Returns (-1,-1) if not a track param."""
    if param_id < PARAM_TRACK_BASE:
        return (-1, -1)
    rel = param_id - PARAM_TRACK_BASE
    return (rel // PARAM_TRACK_STRIDE, rel % PARAM_TRACK_STRIDE)


# ---------------------------------------------------------------------------
# Per-Track Parameter State (audio thread local cache)
# ---------------------------------------------------------------------------

class TrackParamState:
    """Per-track parameter cache for the audio thread.

    Updated from ParamRingBuffer drain, used during render.
    Pre-allocated for MAX_TRACKS — zero allocations at runtime.
    """

    __slots__ = ("_vol", "_pan", "_mute", "_solo",
                 "_vol_smooth", "_pan_smooth",
                 "_any_solo", "_smooth_coeff")

    def __init__(self):
        if np is not None:
            self._vol = np.full(MAX_TRACKS, 0.8, dtype=np.float32)
            self._pan = np.zeros(MAX_TRACKS, dtype=np.float32)
            self._mute = np.zeros(MAX_TRACKS, dtype=np.float32)
            self._solo = np.zeros(MAX_TRACKS, dtype=np.float32)
            self._vol_smooth = np.full(MAX_TRACKS, 0.8, dtype=np.float32)
            self._pan_smooth = np.zeros(MAX_TRACKS, dtype=np.float32)
        else:
            self._vol = [0.8] * MAX_TRACKS
            self._pan = [0.0] * MAX_TRACKS
            self._mute = [0.0] * MAX_TRACKS
            self._solo = [0.0] * MAX_TRACKS
            self._vol_smooth = [0.8] * MAX_TRACKS
            self._pan_smooth = [0.0] * MAX_TRACKS
        self._any_solo = False
        self._smooth_coeff = 0.0

    def apply_param(self, track_idx: int, offset: int, value: float) -> None:
        """Apply a single parameter update (called during ring drain)."""
        if track_idx < 0 or track_idx >= MAX_TRACKS:
            return
        if offset == TRACK_VOL:
            self._vol[track_idx] = max(0.0, min(1.0, value))
        elif offset == TRACK_PAN:
            self._pan[track_idx] = max(-1.0, min(1.0, value))
        elif offset == TRACK_MUTE:
            self._mute[track_idx] = 1.0 if value > 0.5 else 0.0
        elif offset == TRACK_SOLO:
            self._solo[track_idx] = 1.0 if value > 0.5 else 0.0
            if np is not None:
                self._any_solo = bool(np.any(self._solo > 0.5))
            else:
                self._any_solo = any(s > 0.5 for s in self._solo)

    def advance_smoothing(self, coeff: float) -> None:
        """Advance IIR smoothing for all track vol/pan (audio thread)."""
        self._smooth_coeff = coeff
        if np is not None:
            self._vol_smooth += coeff * (self._vol - self._vol_smooth)
            self._pan_smooth += coeff * (self._pan - self._pan_smooth)
        else:
            for i in range(MAX_TRACKS):
                self._vol_smooth[i] += coeff * (self._vol[i] - self._vol_smooth[i])
                self._pan_smooth[i] += coeff * (self._pan[i] - self._pan_smooth[i])

    def get_track_gain(self, track_idx: int) -> Tuple[float, float, bool]:
        """Get (vol_smooth, pan_smooth, audible) for a track."""
        if track_idx < 0 or track_idx >= MAX_TRACKS:
            return (0.8, 0.0, True)
        vol = float(self._vol_smooth[track_idx])
        pan = float(self._pan_smooth[track_idx])
        if float(self._mute[track_idx]) > 0.5:
            return (vol, pan, False)
        if self._any_solo and float(self._solo[track_idx]) < 0.5:
            return (vol, pan, False)
        return (vol, pan, True)

    def is_audible(self, track_idx: int) -> bool:
        """Quick check if track should produce audio."""
        if track_idx < 0 or track_idx >= MAX_TRACKS:
            return True
        if float(self._mute[track_idx]) > 0.5:
            return False
        if self._any_solo and float(self._solo[track_idx]) < 0.5:
            return False
        return True


# ---------------------------------------------------------------------------
# SPSC Parameter Ring (GUI → Audio)
# ---------------------------------------------------------------------------

class ParamRingBuffer:
    """Lock-free SPSC ring for parameter updates.

    v0.0.20.14: Optional SharedMemory backing for multi-process rings.
    """

    __slots__ = ("_capacity", "_mask", "_buf_id", "_buf_val",
                 "_write_pos", "_read_pos", "_shm", "_shm_name")

    def __init__(self, capacity: int = 256, shm_name: Optional[str] = None):
        cap = 1
        while cap < max(16, int(capacity)):
            cap <<= 1
        self._capacity = cap
        self._mask = cap - 1
        self._shm = None
        self._shm_name = shm_name

        if shm_name and _SHM_AVAILABLE and np is not None:
            byte_size = cap * 2 + cap * 4 + 16
            try:
                self._shm = shared_memory.SharedMemory(
                    name=shm_name, create=True, size=byte_size)
            except FileExistsError:
                self._shm = shared_memory.SharedMemory(
                    name=shm_name, create=False)
            buf = self._shm.buf
            self._buf_id = np.ndarray(cap, dtype=np.uint16,
                                      buffer=buf[:cap * 2])
            self._buf_val = np.ndarray(cap, dtype=np.float32,
                                       buffer=buf[cap * 2:cap * 2 + cap * 4])
            if shm_name:
                self._buf_id.fill(0)
                self._buf_val.fill(0.0)
        else:
            if np is not None:
                self._buf_id = np.zeros(cap, dtype=np.uint16)
                self._buf_val = np.zeros(cap, dtype=np.float32)
            else:
                self._buf_id = [0] * cap
                self._buf_val = [0.0] * cap

        self._write_pos: int = 0
        self._read_pos: int = 0

    def push(self, param_id: int, value: float) -> bool:
        """Push a parameter update (GUI thread). Returns False if full."""
        w = self._write_pos
        r = self._read_pos
        if ((w + 1) & self._mask) == (r & self._mask):
            return False
        idx = w & self._mask
        self._buf_id[idx] = int(param_id) & 0xFFFF
        self._buf_val[idx] = float(value)
        self._write_pos = w + 1
        return True

    def push_track_param(self, track_idx: int, param: int, value: float) -> bool:
        """Push a per-track parameter update (GUI thread)."""
        return self.push(track_param_id(track_idx, param), value)

    def drain(self) -> Iterator[Tuple[int, float]]:
        """Drain all pending updates (audio thread). Yields (param_id, value)."""
        r = self._read_pos
        w = self._write_pos
        while r != w:
            idx = r & self._mask
            pid = int(self._buf_id[idx])
            val = float(self._buf_val[idx])
            r += 1
            yield pid, val
        self._read_pos = r

    def drain_into(self, track_state: TrackParamState) -> Iterator[Tuple[int, float]]:
        """Drain and apply track params to TrackParamState. Yields non-track params."""
        r = self._read_pos
        w = self._write_pos
        while r != w:
            idx = r & self._mask
            pid = int(self._buf_id[idx])
            val = float(self._buf_val[idx])
            r += 1
            ti, offset = decode_track_param(pid)
            if ti >= 0:
                track_state.apply_param(ti, offset, val)
            else:
                yield pid, val
        self._read_pos = r

    def available(self) -> int:
        return self._write_pos - self._read_pos

    def clear(self) -> None:
        self._read_pos = self._write_pos

    def close(self) -> None:
        if self._shm is not None:
            try:
                self._shm.close()
            except Exception:
                pass
            try:
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None


# ---------------------------------------------------------------------------
# SPSC Audio Ring (Audio → GUI)
# ---------------------------------------------------------------------------

class AudioRingBuffer:
    """Lock-free SPSC ring buffer for audio sample data.

    v0.0.20.14: Optional SharedMemory backing.
    """

    __slots__ = ("_capacity", "_mask", "_channels", "_buf",
                 "_write_pos", "_read_pos", "_shm")

    def __init__(self, capacity: int = 8192, channels: int = 2,
                 shm_name: Optional[str] = None):
        cap = 1
        while cap < max(256, int(capacity)):
            cap <<= 1
        self._capacity = cap
        self._mask = cap - 1
        self._channels = int(channels)
        self._shm = None

        if shm_name and _SHM_AVAILABLE and np is not None:
            byte_size = cap * self._channels * 4 + 16
            try:
                self._shm = shared_memory.SharedMemory(
                    name=shm_name, create=True, size=byte_size)
            except FileExistsError:
                self._shm = shared_memory.SharedMemory(
                    name=shm_name, create=False)
            self._buf = np.ndarray((cap, self._channels), dtype=np.float32,
                                   buffer=self._shm.buf[:cap * self._channels * 4])
            self._buf.fill(0.0)
        else:
            if np is not None:
                self._buf = np.zeros((cap, self._channels), dtype=np.float32)
            else:
                self._buf = [[0.0] * self._channels for _ in range(cap)]

        self._write_pos: int = 0
        self._read_pos: int = 0

    def write(self, block) -> int:
        if np is None or block is None:
            return 0
        try:
            b = np.asarray(block, dtype=np.float32)
            if b.ndim == 1:
                b = b.reshape(-1, 1)
            frames = b.shape[0]
            ch = min(b.shape[1], self._channels)
            w = self._write_pos
            for i in range(frames):
                idx = (w + i) & self._mask
                self._buf[idx, :ch] = b[i, :ch]
            self._write_pos = w + frames
            return frames
        except Exception:
            return 0

    def read_available(self, max_frames: int = 0) -> Optional["np.ndarray"]:
        if np is None:
            return None
        r = self._read_pos
        w = self._write_pos
        avail = w - r
        if avail <= 0:
            return None
        if max_frames > 0:
            avail = min(avail, max_frames)
        if avail > self._capacity:
            r = w - self._capacity
            avail = self._capacity
        out = np.empty((avail, self._channels), dtype=np.float32)
        for i in range(avail):
            idx = (r + i) & self._mask
            out[i] = self._buf[idx]
        self._read_pos = r + avail
        return out

    def read_peak(self, frames: int = 0) -> Tuple[float, float]:
        """Read peak levels from the ring (GUI thread, lock-free).

        Uses numpy vectorized operations for maximum performance.
        v0.0.20.40: Fully vectorized — no Python sample-loop.
        """
        if np is None:
            return (0.0, 0.0)
        r = self._read_pos
        w = self._write_pos
        avail = w - r
        if avail <= 0:
            return (0.0, 0.0)
        n = min(avail, max(frames, 256), self._capacity)
        start = w - n

        try:
            # Build index array (vectorized modulo)
            indices = np.arange(start, start + n) & self._mask
            block = self._buf[indices]  # fancy indexing: (n, channels)

            peak_l = float(np.max(np.abs(block[:, 0])))
            peak_r = float(np.max(np.abs(block[:, min(1, self._channels - 1)]))) if self._channels >= 2 else peak_l
        except Exception:
            peak_l = 0.0
            peak_r = 0.0

        self._read_pos = w
        return (peak_l, peak_r)

    def clear(self) -> None:
        self._read_pos = self._write_pos

    def close(self) -> None:
        if self._shm is not None:
            try:
                self._shm.close()
            except Exception:
                pass
            try:
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None


# ---------------------------------------------------------------------------
# Convenience: Track Meter Ring (one per mixer strip)
# ---------------------------------------------------------------------------

class TrackMeterRing:
    """Lightweight per-track metering ring (v0.0.20.40).

    Professional ballistics:
    - Instant peak attack (captures transients)
    - Configurable decay rate (default: ~26 dB/s fall time for 30 FPS)
    - Separate RMS integration (~300ms window) for optional RMS metering
    - All operations are lock-free (single writer from audio thread)
    """

    __slots__ = ("peak_l", "peak_r", "_decay", "_rms_l", "_rms_r", "_rms_alpha")

    def __init__(self, decay: float = 0.93):
        self.peak_l: float = 0.0
        self.peak_r: float = 0.0
        self._decay = float(decay)
        # RMS integration (exponential moving average)
        self._rms_l: float = 0.0
        self._rms_r: float = 0.0
        self._rms_alpha: float = 0.04  # ~300ms at typical block sizes

    def update_from_block(self, block, gain_l: float = 1.0,
                          gain_r: float = 1.0) -> None:
        """Update peak and RMS from an audio block (audio thread).

        Args:
            block: numpy array (frames, channels), raw audio data
            gain_l: left channel gain multiplier
            gain_r: right channel gain multiplier
        """
        if np is None or block is None:
            return
        try:
            b = np.asarray(block, dtype=np.float32)
            if b.ndim == 1:
                b = b.reshape(-1, 1)
            if b.shape[0] == 0:
                return

            # Vectorized peak detection
            abs_l = np.abs(b[:, 0])
            abs_r = np.abs(b[:, min(1, b.shape[1] - 1)])

            pl = float(np.max(abs_l)) * abs(gain_l)
            pr = float(np.max(abs_r)) * abs(gain_r)

            # Peak: instant attack, hold at max
            self.peak_l = max(self.peak_l * self._decay, pl)
            self.peak_r = max(self.peak_r * self._decay, pr)

            # RMS: exponential moving average (for optional RMS metering)
            rms_l = float(np.sqrt(np.mean(abs_l ** 2))) * abs(gain_l)
            rms_r = float(np.sqrt(np.mean(abs_r ** 2))) * abs(gain_r)
            alpha = self._rms_alpha
            self._rms_l += alpha * (rms_l - self._rms_l)
            self._rms_r += alpha * (rms_r - self._rms_r)
        except Exception:
            pass

    def read_and_decay(self) -> Tuple[float, float]:
        """Read peak levels and apply decay (GUI thread).

        Returns (peak_l, peak_r) as linear amplitudes.
        """
        l, r = self.peak_l, self.peak_r
        self.peak_l *= self._decay
        self.peak_r *= self._decay
        return (l, r)

    def read_rms(self) -> Tuple[float, float]:
        """Read RMS levels (GUI thread)."""
        return (self._rms_l, self._rms_r)
