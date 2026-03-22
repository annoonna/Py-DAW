"""Asynchronous Sample Loader with Memory-Mapping (v0.0.20.13).

Design goals:
- GUI thread NEVER waits on disk I/O
- Samples are loaded via background threads into a shared cache
- Memory-mapped files for large samples (zero-copy when OS page cache is warm)
- LRU eviction with configurable byte budget
- Thread-safe: multiple workers can load simultaneously
- Callback-based notification when samples are ready

Architecture:
    ┌──────────────┐   request    ┌──────────────────┐   mmap/read    ┌──────┐
    │  GUI Thread   │ ──────────▶ │  LoaderPool       │ ────────────▶ │ Disk │
    │  (arranger)   │ ◀────────── │  (N worker threads)│ ◀──────────── │      │
    └──────────────┘   callback   └──────────────────┘   numpy array  └──────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │ SampleCache   │
                                  │ (LRU, bytes)  │
                                  └──────────────┘
"""
from __future__ import annotations

import mmap
import os
import struct
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None

try:
    import soundfile as sf
except Exception:
    sf = None

from pydaw.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Sample Cache (LRU, byte-budgeted)
# ---------------------------------------------------------------------------

@dataclass
class CachedSample:
    """A cached audio sample with metadata."""
    path: str
    data: Any  # np.ndarray (frames, channels) float32
    sr: int
    channels: int
    frames: int
    byte_size: int
    mtime: float  # file modification time for invalidation
    loaded_at: float = field(default_factory=time.monotonic)


class SampleCache:
    """Thread-safe LRU sample cache with byte budget.

    Evicts oldest entries when total byte usage exceeds budget.
    """

    def __init__(self, max_bytes: int = 512 * 1024 * 1024):  # 512 MB default
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, CachedSample] = OrderedDict()
        self._max_bytes = int(max_bytes)
        self._current_bytes = 0

    def get(self, path: str, target_sr: int = 0) -> Optional[CachedSample]:
        """Get cached sample (thread-safe). Returns None if not cached."""
        key = self._make_key(path, target_sr)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            # Validate mtime (auto-invalidate if file changed)
            try:
                current_mtime = os.path.getmtime(path)
                if abs(current_mtime - entry.mtime) > 0.01:
                    # File changed — invalidate
                    self._remove_entry(key)
                    return None
            except OSError:
                pass
            # Move to end (most recently used)
            try:
                self._cache.move_to_end(key)
            except Exception:
                pass
            return entry

    def put(self, path: str, data: Any, sr: int, target_sr: int = 0) -> None:
        """Store a sample in cache (thread-safe)."""
        if np is None or data is None:
            return
        try:
            arr = np.asarray(data, dtype=np.float32)
            byte_size = arr.nbytes
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
            channels = arr.shape[1] if arr.ndim == 2 else 1
            frames = arr.shape[0]

            entry = CachedSample(
                path=str(path),
                data=arr,
                sr=int(sr),
                channels=int(channels),
                frames=int(frames),
                byte_size=int(byte_size),
                mtime=float(mtime),
            )

            key = self._make_key(path, target_sr)
            with self._lock:
                # Remove old entry if exists
                if key in self._cache:
                    self._remove_entry(key)
                # Evict until we have space
                while self._current_bytes + byte_size > self._max_bytes and self._cache:
                    self._evict_oldest()
                self._cache[key] = entry
                self._current_bytes += byte_size
        except Exception as e:
            log.debug("SampleCache.put failed: %s", e)

    def invalidate(self, path: str) -> None:
        """Remove all cached versions of a file."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(str(path) + "|")]
            for k in keys_to_remove:
                self._remove_entry(k)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._cache),
                "bytes": self._current_bytes,
                "max_bytes": self._max_bytes,
                "mb_used": round(self._current_bytes / (1024 * 1024), 1),
            }

    def _make_key(self, path: str, target_sr: int) -> str:
        return f"{path}|{target_sr}"

    def _remove_entry(self, key: str) -> None:
        entry = self._cache.pop(key, None)
        if entry:
            self._current_bytes -= entry.byte_size

    def _evict_oldest(self) -> None:
        try:
            _, entry = self._cache.popitem(last=False)
            self._current_bytes -= entry.byte_size
        except KeyError:
            pass


# ---------------------------------------------------------------------------
# Memory-Mapped WAV Reader (zero-copy for PCM formats)
# ---------------------------------------------------------------------------

def _mmap_read_wav(path: str) -> Optional[Tuple[Any, int]]:
    """Attempt to memory-map a WAV file for zero-copy access.

    Only works for uncompressed PCM WAV files. Returns (data, sr) or None.
    Falls back to soundfile for compressed formats.
    """
    if np is None:
        return None
    try:
        with open(path, "rb") as f:
            # Read WAV header
            riff = f.read(4)
            if riff != b"RIFF":
                return None
            f.read(4)  # file size
            wave = f.read(4)
            if wave != b"WAVE":
                return None

            # Find fmt and data chunks
            sr = 0
            bits = 0
            channels = 0
            data_offset = 0
            data_size = 0

            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack("<I", f.read(4))[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                    if audio_format not in (1, 3):  # PCM int or PCM float
                        return None  # Compressed — use soundfile
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sr = struct.unpack("<I", fmt_data[4:8])[0]
                    bits = struct.unpack("<H", fmt_data[14:16])[0]
                elif chunk_id == b"data":
                    data_offset = f.tell()
                    data_size = chunk_size
                    break
                else:
                    f.seek(chunk_size, 1)

            if data_offset == 0 or data_size == 0 or sr == 0:
                return None

            # Memory-map the data section
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

            bytes_per_sample = bits // 8
            total_samples = data_size // bytes_per_sample
            frames = total_samples // max(1, channels)

            if bits == 16:
                raw = np.frombuffer(
                    mm, dtype=np.int16,
                    count=total_samples, offset=data_offset
                )
                data = raw.astype(np.float32) / 32768.0
            elif bits == 24:
                # 24-bit requires manual unpacking
                raw_bytes = mm[data_offset:data_offset + data_size]
                raw = np.zeros(total_samples, dtype=np.int32)
                for i in range(total_samples):
                    b = raw_bytes[i * 3:(i + 1) * 3]
                    val = b[0] | (b[1] << 8) | (b[2] << 16)
                    if val & 0x800000:
                        val -= 0x1000000
                    raw[i] = val
                data = raw.astype(np.float32) / 8388608.0
            elif bits == 32:
                if struct.unpack("<H", mm[20:22])[0] == 3:  # float
                    data = np.frombuffer(
                        mm, dtype=np.float32,
                        count=total_samples, offset=data_offset
                    ).copy()
                else:
                    raw = np.frombuffer(
                        mm, dtype=np.int32,
                        count=total_samples, offset=data_offset
                    )
                    data = raw.astype(np.float32) / 2147483648.0
            else:
                mm.close()
                return None

            mm.close()

            # Reshape to (frames, channels)
            if channels > 1:
                data = data.reshape(-1, channels)
            else:
                data = data.reshape(-1, 1)

            return (data.astype(np.float32, copy=False), int(sr))

    except Exception as e:
        log.debug("mmap_read_wav failed for %s: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Async Sample Loader
# ---------------------------------------------------------------------------

# Callback signature: (path, data, sr) or (path, None, 0) on error
SampleReadyCallback = Callable[[str, Any, int], None]


class AsyncSampleLoader:
    """Background sample loader with memory-mapping and caching.

    Provides non-blocking sample loading for the GUI thread.
    Samples are loaded in background threads and cached for reuse.
    """

    def __init__(self, cache: Optional[SampleCache] = None,
                 max_workers: int = 4):
        self._cache = cache or SampleCache()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="SampleLoader",
        )
        self._pending: Dict[str, bool] = {}  # path -> loading
        self._lock = threading.Lock()
        self._callbacks: Dict[str, List[SampleReadyCallback]] = {}
        # v0.0.20.22: Peak cache for waveform rendering
        self._peak_cache: Dict[str, np.ndarray] = {}  # "path:block_size" -> peaks

    @property
    def cache(self) -> SampleCache:
        return self._cache

    def request(self, path: str, target_sr: int = 48000,
                callback: Optional[SampleReadyCallback] = None) -> Optional[CachedSample]:
        """Request a sample load. Returns immediately.

        If sample is already cached, returns it directly.
        Otherwise, starts a background load and calls callback when done.
        """
        # Check cache first
        cached = self._cache.get(path, target_sr)
        if cached is not None:
            if callback:
                try:
                    callback(path, cached.data, cached.sr)
                except Exception:
                    pass
            return cached

        # Queue background load
        key = f"{path}|{target_sr}"
        with self._lock:
            if key in self._pending:
                # Already loading — just register callback
                if callback:
                    self._callbacks.setdefault(key, []).append(callback)
                return None
            self._pending[key] = True
            if callback:
                self._callbacks.setdefault(key, []).append(callback)

        self._pool.submit(self._load_worker, path, target_sr, key)
        return None

    def request_sync(self, path: str, target_sr: int = 48000) -> Optional[CachedSample]:
        """Synchronous load (for audio thread preparation). Blocking."""
        cached = self._cache.get(path, target_sr)
        if cached is not None:
            return cached

        data, sr = self._load_file(path)
        if data is None:
            return None

        # Resample if needed
        if int(sr) != int(target_sr) and data.shape[0] > 1:
            data = self._resample(data, sr, target_sr)
            sr = target_sr

        self._cache.put(path, data, sr, target_sr)
        return self._cache.get(path, target_sr)

    def _load_worker(self, path: str, target_sr: int, key: str) -> None:
        """Background worker thread."""
        data = None
        sr = 0
        try:
            data, sr = self._load_file(path)
            if data is not None and int(sr) != int(target_sr) and data.shape[0] > 1:
                data = self._resample(data, sr, target_sr)
                sr = target_sr
            if data is not None:
                self._cache.put(path, data, sr, target_sr)
        except Exception as e:
            log.debug("AsyncSampleLoader: load failed for %s: %s", path, e)
            data = None
            sr = 0
        finally:
            # Fire callbacks
            with self._lock:
                self._pending.pop(key, None)
                cbs = self._callbacks.pop(key, [])
            for cb in cbs:
                try:
                    cb(path, data, sr)
                except Exception:
                    pass

    def _load_file(self, path: str) -> Tuple[Optional[Any], int]:
        """Load audio file, preferring mmap for WAV."""
        if not os.path.isfile(path):
            return None, 0

        # Try memory-mapped WAV first (zero-copy)
        if path.lower().endswith(".wav"):
            result = _mmap_read_wav(path)
            if result is not None:
                return result

        # Fall back to soundfile (handles flac, ogg, mp3, etc.)
        if sf is not None:
            try:
                data, sr = sf.read(path, dtype="float32", always_2d=True)
                return data, int(sr)
            except Exception:
                pass

        return None, 0

    @staticmethod
    def _resample(data: Any, src_sr: int, target_sr: int) -> Any:
        """Linear interpolation resampling."""
        if np is None or data is None:
            return data
        ratio = float(target_sr) / float(src_sr)
        n_out = max(1, int(round(data.shape[0] * ratio)))
        x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        channels = data.shape[1] if data.ndim == 2 else 1
        if channels == 1:
            return np.interp(x_new, x_old, data.ravel()).astype(
                np.float32).reshape(-1, 1)
        cols = []
        for ch in range(min(channels, 2)):
            cols.append(np.interp(x_new, x_old, data[:, ch]))
        return np.column_stack(cols).astype(np.float32)

    def get_peaks(self, path: str, block_size: int = 512,
                  max_peaks: int = 10000) -> Optional[np.ndarray]:
        """Get peak data for waveform rendering.
        
        Computes peak values (max absolute amplitude) per block.
        Cached for reuse.
        
        Args:
            path: Audio file path
            block_size: Samples per peak (default 512 = ~10ms @ 48kHz)
            max_peaks: Maximum number of peaks to compute (for very long files)
        
        Returns:
            np.ndarray of shape (n_peaks, 2) with L/R peak values (0.0 to 1.0)
            or None if file not found/readable
        
        v0.0.20.22: For GPU waveform rendering with real audio data.
        """
        if np is None or sf is None:
            return None
        
        # Check peak cache
        cache_key = f"{path}:{block_size}"
        with self._lock:
            if cache_key in self._peak_cache:
                return self._peak_cache[cache_key]
        
        # Load file info
        try:
            info = sf.info(path)
            n_frames = int(info.frames)
            n_channels = int(info.channels)
            
            # Calculate number of peaks
            n_peaks = min(max_peaks, (n_frames + block_size - 1) // block_size)
            
            # For very long files, use subsampling
            if n_peaks > max_peaks:
                step = n_frames / max_peaks
                peaks = np.zeros((max_peaks, 2), dtype=np.float32)
                
                with sf.SoundFile(path) as f:
                    for i in range(max_peaks):
                        frame_start = int(i * step)
                        f.seek(frame_start)
                        block = f.read(min(block_size, n_frames - frame_start))
                        
                        if block.ndim == 1:
                            block = block.reshape(-1, 1)
                        
                        # Compute peaks (max abs per channel)
                        peaks[i, 0] = float(np.max(np.abs(block[:, 0])))
                        if n_channels > 1:
                            peaks[i, 1] = float(np.max(np.abs(block[:, 1])))
                        else:
                            peaks[i, 1] = peaks[i, 0]
            else:
                # Normal case: read entire file and compute peaks
                data, sr = self._load_file(path)
                if data is None:
                    return None
                
                if data.ndim == 1:
                    data = data.reshape(-1, 1)
                
                n_peaks = (data.shape[0] + block_size - 1) // block_size
                peaks = np.zeros((n_peaks, 2), dtype=np.float32)
                
                for i in range(n_peaks):
                    start = i * block_size
                    end = min((i + 1) * block_size, data.shape[0])
                    block = data[start:end]
                    
                    # Compute peaks
                    peaks[i, 0] = float(np.max(np.abs(block[:, 0])))
                    if data.shape[1] > 1:
                        peaks[i, 1] = float(np.max(np.abs(block[:, 1])))
                    else:
                        peaks[i, 1] = peaks[i, 0]
            
            # Normalize to 0-1 range
            max_peak = np.max(peaks)
            if max_peak > 0.0:
                peaks = peaks / max_peak
            
            # Cache
            with self._lock:
                self._peak_cache[cache_key] = peaks
            
            return peaks
            
        except Exception as e:
            log.warning(f"Failed to compute peaks for {path}: {e}")
            return None

    def shutdown(self) -> None:
        """Shutdown worker pool."""
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_global_loader: Optional[AsyncSampleLoader] = None
_global_cache: Optional[SampleCache] = None


def get_sample_cache() -> SampleCache:
    """Get or create the global sample cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = SampleCache()
    return _global_cache


def get_async_loader() -> AsyncSampleLoader:
    """Get or create the global async sample loader."""
    global _global_loader
    if _global_loader is None:
        _global_loader = AsyncSampleLoader(cache=get_sample_cache())
    return _global_loader
