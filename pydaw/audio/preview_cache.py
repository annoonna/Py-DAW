"""
PreviewCache: simple LRU cache for Browser Preview renders.

Goal:
- Avoid re-rendering time-stretched preview buffers when the user repeatedly
  auditions the same sample (Sync/Raw, looped/non-looped).
- Keep GUI responsive (cache ops are O(1) and happen on UI thread).

Notes:
- In-memory cache only (fast). Keys include file mtime/size for invalidation.
- This module must be safe to import even if numpy is not available.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
import hashlib
import os
from typing import Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


@dataclass
class CacheEntry:
    buf: "np.ndarray"
    sr: int
    source_bpm: Optional[float]
    nbytes: int


class PreviewCache:
    def __init__(self, max_bytes: int = 256 * 1024 * 1024):
        self.max_bytes = int(max(16 * 1024 * 1024, max_bytes))
        self._od: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._bytes = 0

    # ---------------- keying

    def make_key(
        self,
        path: str,
        mode: str,
        loop: bool,
        project_bpm: float,
        beats_per_bar: float,
        source_bpm_hint: Optional[float],
        sr: int,
    ) -> str:
        try:
            ap = os.path.abspath(str(path))
            st = os.stat(ap)
            mtime = int(getattr(st, "st_mtime", 0))
            size = int(getattr(st, "st_size", 0))
        except Exception:
            ap = str(path)
            mtime = 0
            size = 0
        try:
            sb = float(source_bpm_hint or 0.0)
        except Exception:
            sb = 0.0
        try:
            pb = float(project_bpm or 120.0)
        except Exception:
            pb = 120.0
        try:
            bpb = float(beats_per_bar or 4.0)
        except Exception:
            bpb = 4.0

        raw = f"{ap}|{mtime}|{size}|{str(mode)}|{int(bool(loop))}|{pb:.3f}|{bpb:.3f}|{sb:.3f}|{int(sr)}"
        return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

    # ---------------- ops

    def get(self, key: str) -> Optional[Tuple["np.ndarray", int, Optional[float]]]:
        if np is None:
            return None
        try:
            ent = self._od.get(str(key))
            if ent is None:
                return None
            # move to end (MRU)
            self._od.move_to_end(str(key), last=True)
            return ent.buf, int(ent.sr), ent.source_bpm
        except Exception:
            return None

    def put(self, key: str, buf, sr: int, source_bpm: Optional[float]) -> None:
        if np is None:
            return
        try:
            k = str(key)
            b = np.asarray(buf, dtype=np.float32)
            nbytes = int(getattr(b, "nbytes", 0))
            if nbytes <= 0:
                return

            # if overwrite, remove old
            old = self._od.pop(k, None)
            if old is not None:
                self._bytes -= int(old.nbytes)

            self._od[k] = CacheEntry(buf=b, sr=int(sr or 48000), source_bpm=source_bpm, nbytes=nbytes)
            self._bytes += nbytes

            self._evict_if_needed()
        except Exception:
            return

    def clear(self) -> None:
        try:
            self._od.clear()
            self._bytes = 0
        except Exception:
            pass

    def stats(self) -> Tuple[int, int]:
        """(items, bytes)"""
        try:
            return len(self._od), int(self._bytes)
        except Exception:
            return 0, 0

    def _evict_if_needed(self) -> None:
        try:
            while self._bytes > self.max_bytes and len(self._od) > 1:
                _, ent = self._od.popitem(last=False)  # LRU
                self._bytes -= int(getattr(ent, "nbytes", 0))
        except Exception:
            pass


# Shared default cache instance (module-level singleton)
DEFAULT_PREVIEW_CACHE = PreviewCache()
