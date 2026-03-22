"""ArrangerRenderCache

Cache layer for arrangement playback preparation.

Goals:
- Never run time-stretching inside realtime callbacks.
- Reuse decoded/resampled audio buffers across Play/Stop cycles.
- Reuse time-stretched (tempo-synced) buffers across Play/Stop cycles.

Design:
- Two independent LRU caches:
  1) decoded/resampled stereo float32 buffers at the target sample rate.
  2) time-stretched buffers keyed by (file, rate, sr).
- Keys include file mtime/size for automatic invalidation.

Notes:
- Safe to import even if numpy/soundfile are unavailable (methods will fall back).
- Disk cache is deliberately optional and OFF by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
import hashlib
import os
import threading
from typing import Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None


def _safe_float(x: object, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _safe_int(x: object, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)


@dataclass
class _Entry:
    buf: "np.ndarray"
    nbytes: int


class _LRUBytes:
    """Byte-budgeted LRU cache for numpy buffers."""

    def __init__(self, max_bytes: int):
        self.max_bytes = int(max(16 * 1024 * 1024, max_bytes))
        self._od: "OrderedDict[str, _Entry]" = OrderedDict()
        self._bytes: int = 0

    def get(self, key: str):
        if np is None:
            return None
        try:
            ent = self._od.get(str(key))
            if ent is None:
                return None
            self._od.move_to_end(str(key), last=True)
            return ent.buf
        except Exception:
            return None

    def put(self, key: str, buf) -> None:  # noqa: ANN001
        if np is None:
            return
        try:
            k = str(key)
            b = np.asarray(buf, dtype=np.float32)
            nbytes = int(getattr(b, "nbytes", 0) or 0)
            if nbytes <= 0:
                return
            old = self._od.pop(k, None)
            if old is not None:
                self._bytes -= int(old.nbytes)
            self._od[k] = _Entry(buf=b, nbytes=nbytes)
            self._bytes += nbytes
            self._evict_if_needed()
        except Exception:
            return

    def _evict_if_needed(self) -> None:
        try:
            while self._bytes > self.max_bytes and len(self._od) > 1:
                _, ent = self._od.popitem(last=False)
                self._bytes -= int(getattr(ent, "nbytes", 0) or 0)
        except Exception:
            pass

    def stats(self) -> Tuple[int, int]:
        try:
            return len(self._od), int(self._bytes)
        except Exception:
            return 0, 0

    def clear(self) -> None:
        try:
            self._od.clear()
            self._bytes = 0
        except Exception:
            pass


class ArrangerRenderCache:
    """Shared cache for arrangement preparation."""

    def __init__(
        self,
        decoded_max_bytes: int = 256 * 1024 * 1024,
        stretched_max_bytes: int = 512 * 1024 * 1024,
        enable_disk_cache: bool = False,
    ):
        self._lock = threading.RLock()
        self._decoded = _LRUBytes(decoded_max_bytes)
        self._stretched = _LRUBytes(stretched_max_bytes)
        self.enable_disk_cache = bool(enable_disk_cache)

        # Disk cache directory is optional; kept separate per SR.
        self._disk_dir = os.path.join(os.path.expanduser("~"), ".cache", "pydaw", "arranger")

    # ---------------- key helpers

    def _file_sig(self, path: str) -> Tuple[str, int, int]:
        ap = os.path.abspath(str(path))
        try:
            st = os.stat(ap)
            return ap, int(getattr(st, "st_mtime", 0) or 0), int(getattr(st, "st_size", 0) or 0)
        except Exception:
            return ap, 0, 0

    def _decoded_key(self, path: str, sr: int) -> str:
        ap, mtime, size = self._file_sig(path)
        raw = f"D|{ap}|{mtime}|{size}|{int(sr)}"
        return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _stretched_key(self, path: str, sr: int, rate: float) -> str:
        ap, mtime, size = self._file_sig(path)
        raw = f"S|{ap}|{mtime}|{size}|{int(sr)}|{float(rate):.8f}"
        return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

    # ---------------- public API

    def get_decoded(self, path: str, sr: int):
        """Return stereo float32 at target SR (decoded+resampled)."""
        if np is None or sf is None:
            return None
        sr = _safe_int(sr, 48000)
        k = self._decoded_key(path, sr)
        with self._lock:
            buf = self._decoded.get(k)
        if buf is not None:
            return buf

        try:
            data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception:
            return None

        # Normalize channels to stereo
        try:
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            elif data.shape[1] >= 2:
                data = data[:, :2]
        except Exception:
            return None

        # Resample (linear) if needed
        try:
            if int(file_sr) != int(sr) and data.shape[0] > 1:
                ratio = float(sr) / float(file_sr)
                n_out = max(1, int(round(data.shape[0] * ratio)))
                x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                data = np.vstack([
                    np.interp(x_new, x_old, data[:, 0]),
                    np.interp(x_new, x_old, data[:, 1]),
                ]).T.astype(np.float32, copy=False)
        except Exception:
            # If resampling fails, keep original rate buffer.
            pass

        with self._lock:
            self._decoded.put(k, data)
        return data

    def get_stretched(self, path: str, sr: int, rate: float):
        """Return tempo-synced buffer (stretched) for the given play-rate."""
        if np is None:
            return None
        sr = _safe_int(sr, 48000)
        rate = _safe_float(rate, 1.0)
        if abs(rate - 1.0) < 1e-3:
            return self.get_decoded(path, sr)

        k = self._stretched_key(path, sr, rate)
        with self._lock:
            buf = self._stretched.get(k)
        if buf is not None:
            return buf

        # optional disk cache
        if self.enable_disk_cache:
            try:
                os.makedirs(self._disk_dir, exist_ok=True)
                p = os.path.join(self._disk_dir, f"{k}.npy")
                if os.path.exists(p):
                    arr = np.load(p, allow_pickle=False)
                    if isinstance(arr, np.ndarray) and arr.ndim == 2 and arr.shape[1] >= 2:
                        arr = arr[:, :2].astype(np.float32, copy=False)
                        with self._lock:
                            self._stretched.put(k, arr)
                        return arr
            except Exception:
                pass

        base = self.get_decoded(path, sr)
        if base is None:
            return None

        try:
            from .time_stretch import time_stretch_stereo

            stretched = time_stretch_stereo(base, rate=float(rate), sr=int(sr))
            stretched = np.asarray(stretched, dtype=np.float32)
            if stretched.ndim != 2:
                return base
            if stretched.shape[1] == 1:
                stretched = np.repeat(stretched, 2, axis=1)
            elif stretched.shape[1] > 2:
                stretched = stretched[:, :2]

            with self._lock:
                self._stretched.put(k, stretched)

            if self.enable_disk_cache:
                try:
                    os.makedirs(self._disk_dir, exist_ok=True)
                    np.save(os.path.join(self._disk_dir, f"{k}.npy"), stretched)
                except Exception:
                    pass

            return stretched
        except Exception:
            return base


def make_stretched_key(self, path: str, sr: int, rate: float) -> str:
    """Return the internal stretched-cache key for (path, sr, rate).

    This key includes file signature (mtime/size) so results auto-invalidate
    when the source file changes.
    """
    sr = _safe_int(sr, 48000)
    rate = _safe_float(rate, 1.0)
    return self._stretched_key(path, sr, rate)

def peek_stretched(self, path: str, sr: int, rate: float):
    """Fast path: return stretched buffer if already cached (RAM or disk).

    Unlike get_stretched(), this will NOT compute time-stretch if missing.
    """
    if np is None:
        return None
    sr = _safe_int(sr, 48000)
    rate = _safe_float(rate, 1.0)
    if abs(rate - 1.0) < 1e-3:
        # decoded cache only (do not trigger decode from disk)
        k = self._decoded_key(path, sr)
        with self._lock:
            return self._decoded.get(k)

    k = self._stretched_key(path, sr, rate)
    with self._lock:
        buf = self._stretched.get(k)
    if buf is not None:
        return buf

    if self.enable_disk_cache:
        try:
            os.makedirs(self._disk_dir, exist_ok=True)
            p = os.path.join(self._disk_dir, f"{k}.npy")
            if os.path.exists(p):
                arr = np.load(p, allow_pickle=False)
                if isinstance(arr, np.ndarray) and arr.ndim == 2 and arr.shape[1] >= 2:
                    arr = arr[:, :2].astype(np.float32, copy=False)
                    with self._lock:
                        self._stretched.put(k, arr)
                    return arr
        except Exception:
            pass
    return None

def put_stretched(self, path: str, sr: int, rate: float, buf) -> bool:  # noqa: ANN001
    """Insert a stretched buffer into the cache.

    Used by background worker pools (e.g. EssentiaWorkerPool) to populate
    the ArrangerRenderCache without recomputing.
    """
    if np is None or buf is None:
        return False
    sr = _safe_int(sr, 48000)
    rate = _safe_float(rate, 1.0)
    try:
        arr = np.asarray(buf, dtype=np.float32)
        if arr.ndim != 2:
            return False
        if arr.shape[1] == 1:
            arr = np.repeat(arr, 2, axis=1)
        elif arr.shape[1] > 2:
            arr = arr[:, :2]
    except Exception:
        return False

    if abs(rate - 1.0) < 1e-3:
        k = self._decoded_key(path, sr)
        with self._lock:
            self._decoded.put(k, arr)
        return True

    k = self._stretched_key(path, sr, rate)
    with self._lock:
        self._stretched.put(k, arr)

    if self.enable_disk_cache:
        try:
            os.makedirs(self._disk_dir, exist_ok=True)
            np.save(os.path.join(self._disk_dir, f"{k}.npy"), arr)
        except Exception:
            pass

    return True
    def stats(self) -> dict:
        d_items, d_bytes = self._decoded.stats()
        s_items, s_bytes = self._stretched.stats()
        return {
            "decoded_items": int(d_items),
            "decoded_bytes": int(d_bytes),
            "stretched_items": int(s_items),
            "stretched_bytes": int(s_bytes),
        }

    def clear(self) -> None:
        with self._lock:
            self._decoded.clear()
            self._stretched.clear()


# Shared module-level cache used by default.
DEFAULT_ARRANGER_CACHE = ArrangerRenderCache()
