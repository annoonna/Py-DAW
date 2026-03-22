"""Essentia Worker Pool — Priority-Queued Time-Stretch Processing (v0.0.20.14).

Offloads CPU-intensive time-stretch and BPM analysis to a thread pool
with priority ordering: visible/playing clips get processed first.

Architecture:
    ┌──────────────┐                    ┌───────────────────┐
    │  GUI Thread   │   submit_job()    │  Worker Pool      │
    │  (Arranger/   │ ─────────────────▶│  (4 threads)      │
    │   Transport)  │                   │  Priority Queue   │
    │               │ ◀─────────────────│  [HIGH] → [LOW]   │
    │               │   on_complete cb  │  Time-Stretch     │
    └──────────────┘                    │  BPM Detect       │
                                        └───────────────────┘

Job Priorities:
    0 = CRITICAL (playing clip needs stretch NOW)
    1 = HIGH (visible clip being prepared)
    2 = NORMAL (prewarm background job)
    3 = LOW (cache prefill)

Usage:
    pool = EssentiaWorkerPool(workers=4)
    job = pool.submit_stretch(
        audio_data=data, rate=1.2, sr=48000,
        priority=PRIORITY_HIGH,
        callback=on_done
    )
    # Cancel if no longer needed
    pool.cancel(job.job_id)
    # Shutdown
    pool.shutdown()
"""
from __future__ import annotations

import hashlib
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None

from pydaw.utils.logging_setup import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

PRIORITY_CRITICAL = 0  # Playing clip needs stretch NOW
PRIORITY_HIGH = 1      # Visible clip being prepared
PRIORITY_NORMAL = 2    # Prewarm background job
PRIORITY_LOW = 3       # Cache prefill / speculative


class JobStatus(IntEnum):
    PENDING = 0
    RUNNING = 1
    DONE = 2
    CANCELLED = 3
    FAILED = 4


@dataclass(order=True)
class StretchJob:
    """A queued time-stretch job with priority ordering."""
    priority: int
    submit_time: float = field(compare=True)
    job_id: str = field(compare=False)
    # Input
    audio_path: str = field(compare=False, default="")
    audio_data: Any = field(compare=False, default=None)  # np.ndarray or None
    rate: float = field(compare=False, default=1.0)
    sr: int = field(compare=False, default=48000)
    # Cache key (for dedup)
    cache_key: str = field(compare=False, default="")
    # Output
    result: Any = field(compare=False, default=None)  # np.ndarray
    status: JobStatus = field(compare=False, default=JobStatus.PENDING)
    error: Optional[str] = field(compare=False, default=None)
    # Callback
    on_complete: Optional[Callable] = field(compare=False, default=None)
    # Generation (for cancellation)
    generation: int = field(compare=False, default=0)


@dataclass(order=True)
class BPMJob:
    """A queued BPM analysis job."""
    priority: int
    submit_time: float = field(compare=True)
    job_id: str = field(compare=False)
    audio_path: str = field(compare=False, default="")
    audio_data: Any = field(compare=False, default=None)
    sr: int = field(compare=False, default=48000)
    result_bpm: float = field(compare=False, default=0.0)
    status: JobStatus = field(compare=False, default=JobStatus.PENDING)
    error: Optional[str] = field(compare=False, default=None)
    on_complete: Optional[Callable] = field(compare=False, default=None)
    generation: int = field(compare=False, default=0)


class EssentiaWorkerPool:
    """Priority-queued thread pool for time-stretch and BPM analysis.

    Features:
    - PriorityQueue ensures critical/visible clips are processed first
    - Duplicate detection via cache_key prevents redundant work
    - Cancellation support (generation-based, no thread killing)
    - Result cache (LRU, byte-budgeted) for reuse
    - Graceful shutdown with timeout
    """

    def __init__(self, workers: int = 4, cache_budget_mb: int = 256):
        self._workers = max(1, int(workers))
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._pool = ThreadPoolExecutor(max_workers=self._workers,
                                        thread_name_prefix="essentia")
        self._lock = threading.Lock()

        # Active/pending jobs by job_id
        self._jobs: Dict[str, Any] = {}
        # Cache key → result (prevents redundant processing)
        self._pending_keys: Dict[str, str] = {}  # cache_key → job_id

        # Result cache (LRU, byte-budgeted)
        self._cache: Dict[str, Any] = {}  # cache_key → np.ndarray
        self._cache_order: List[str] = []  # LRU order
        self._cache_bytes: int = 0
        self._cache_budget = int(cache_budget_mb) * 1024 * 1024

        # Generation counter (for bulk cancellation)
        self._generation: int = 0
        self._shutdown = False

        # Start worker threads
        for _ in range(self._workers):
            self._pool.submit(self._worker_loop)

    def _worker_loop(self) -> None:
        """Worker thread main loop — pulls from priority queue."""
        while not self._shutdown:
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception:
                continue

            if self._shutdown:
                break

            if isinstance(job, StretchJob):
                self._execute_stretch(job)
            elif isinstance(job, BPMJob):
                self._execute_bpm(job)

    def _execute_stretch(self, job: StretchJob) -> None:
        """Execute a time-stretch job."""
        if job.status == JobStatus.CANCELLED:
            return

        # Check if cancelled by generation
        if job.generation < self._generation:
            job.status = JobStatus.CANCELLED
            self._cleanup_job(job.job_id)
            return

        # Check cache first
        if job.cache_key and job.cache_key in self._cache:
            job.result = self._cache[job.cache_key]
            job.status = JobStatus.DONE
            self._fire_callback(job)
            self._cleanup_job(job.job_id)
            return

        job.status = JobStatus.RUNNING
        try:
            data = job.audio_data
            if data is None and job.audio_path:
                # Load from file
                try:
                    import soundfile as sf
                    data, file_sr = sf.read(job.audio_path, dtype="float32",
                                            always_2d=True)
                    if int(file_sr) != int(job.sr) and data.shape[0] > 1:
                        # Resample
                        ratio = float(job.sr) / float(file_sr)
                        n_out = max(1, int(round(data.shape[0] * ratio)))
                        x_old = np.linspace(0, 1, data.shape[0], endpoint=False)
                        x_new = np.linspace(0, 1, n_out, endpoint=False)
                        data = np.vstack([
                            np.interp(x_new, x_old, data[:, c])
                            for c in range(min(2, data.shape[1]))
                        ]).T.astype(np.float32)
                except Exception as e:
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    self._fire_callback(job)
                    self._cleanup_job(job.job_id)
                    return

            if data is None or data.shape[0] < 2:
                job.status = JobStatus.FAILED
                job.error = "No audio data"
                self._fire_callback(job)
                self._cleanup_job(job.job_id)
                return

            # Check cancelled again before expensive operation
            if job.generation < self._generation:
                job.status = JobStatus.CANCELLED
                self._cleanup_job(job.job_id)
                return

            # Time-stretch
            try:
                from .time_stretch import time_stretch_stereo
                result = time_stretch_stereo(data, rate=job.rate, sr=job.sr)
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = f"stretch failed: {e}"
                self._fire_callback(job)
                self._cleanup_job(job.job_id)
                return

            job.result = result
            job.status = JobStatus.DONE

            # Store in cache
            if job.cache_key and result is not None:
                self._cache_put(job.cache_key, result)

            self._fire_callback(job)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            self._fire_callback(job)

        self._cleanup_job(job.job_id)

    def _execute_bpm(self, job: BPMJob) -> None:
        """Execute a BPM analysis job."""
        if job.status == JobStatus.CANCELLED:
            return
        if job.generation < self._generation:
            job.status = JobStatus.CANCELLED
            self._cleanup_job(job.job_id)
            return

        job.status = JobStatus.RUNNING
        try:
            from .bpm_detect import detect_bpm
            bpm = detect_bpm(
                path=job.audio_path if job.audio_path else None,
                audio_data=job.audio_data,
                sr=job.sr,
            )
            job.result_bpm = float(bpm or 0.0)
            job.status = JobStatus.DONE
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.result_bpm = 0.0

        self._fire_callback(job)
        self._cleanup_job(job.job_id)

    def _fire_callback(self, job: Any) -> None:
        """Fire the on_complete callback (in worker thread)."""
        if job.on_complete is not None:
            try:
                job.on_complete(job)
            except Exception:
                pass

    def _cleanup_job(self, job_id: str) -> None:
        """Remove job from tracking dict."""
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is not None and hasattr(job, "cache_key") and job.cache_key:
                self._pending_keys.pop(job.cache_key, None)

    def _cache_put(self, key: str, data: Any) -> None:
        """Store result in LRU cache with budget enforcement."""
        if np is None or data is None:
            return
        try:
            nbytes = int(data.nbytes)
        except Exception:
            return
        with self._lock:
            if key in self._cache:
                return
            # Evict until budget allows
            while self._cache_bytes + nbytes > self._cache_budget and self._cache_order:
                old_key = self._cache_order.pop(0)
                old_data = self._cache.pop(old_key, None)
                if old_data is not None:
                    try:
                        self._cache_bytes -= int(old_data.nbytes)
                    except Exception:
                        pass
            self._cache[key] = data
            self._cache_order.append(key)
            self._cache_bytes += nbytes

    def cache_get(self, key: str) -> Optional[Any]:
        """Check if result is already cached."""
        with self._lock:
            return self._cache.get(key)

    @staticmethod
    def make_stretch_key(path: str, sr: int, rate: float) -> str:
        """Generate a cache key for a stretch job."""
        raw = f"{path}:{sr}:{rate:.6f}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    # ---- Public API

    def submit_stretch(self, audio_data: Any = None,
                       audio_path: str = "",
                       rate: float = 1.0, sr: int = 48000,
                       priority: int = PRIORITY_NORMAL,
                       cache_key: str = "",
                       callback: Optional[Callable] = None) -> StretchJob:
        """Submit a time-stretch job.

        Returns the StretchJob (can be used for status check / cancellation).
        """
        job_id = str(uuid.uuid4())[:12]

        # Dedup: if same cache_key is already pending, return that job.
        # Important: allow multiple callers to attach callbacks to the same work item.
        if cache_key:
            with self._lock:
                if cache_key in self._pending_keys:
                    existing_id = self._pending_keys[cache_key]
                    existing = self._jobs.get(existing_id)
                    if existing is not None:
                        if callback is not None:
                            try:
                                prev = getattr(existing, "on_complete", None)
                                if prev is None:
                                    existing.on_complete = callback
                                elif prev is not callback:
                                    def _chained(job, _prev=prev, _cb=callback):
                                        try:
                                            _prev(job)
                                        finally:
                                            _cb(job)
                                    existing.on_complete = _chained
                            except Exception:
                                pass
                        return existing

        job = StretchJob(
            priority=priority,
            submit_time=time.monotonic(),
            job_id=job_id,
            audio_path=audio_path,
            audio_data=audio_data,
            rate=rate,
            sr=sr,
            cache_key=cache_key,
            on_complete=callback,
            generation=self._generation,
        )

        with self._lock:
            self._jobs[job_id] = job
            if cache_key:
                self._pending_keys[cache_key] = job_id

        self._queue.put(job)
        return job

    def submit_bpm(self, audio_path: str = "",
                   audio_data: Any = None,
                   sr: int = 48000,
                   priority: int = PRIORITY_NORMAL,
                   callback: Optional[Callable] = None) -> BPMJob:
        """Submit a BPM detection job."""
        job_id = str(uuid.uuid4())[:12]
        job = BPMJob(
            priority=priority,
            submit_time=time.monotonic(),
            job_id=job_id,
            audio_path=audio_path,
            audio_data=audio_data,
            sr=sr,
            on_complete=callback,
            generation=self._generation,
        )
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job)
        return job

    def cancel(self, job_id: str) -> bool:
        """Cancel a specific job. Returns True if found."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = JobStatus.CANCELLED
                return True
        return False

    def cancel_all(self) -> int:
        """Cancel all pending jobs. Returns count cancelled."""
        count = 0
        self._generation += 1
        with self._lock:
            for jid, job in list(self._jobs.items()):
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    job.status = JobStatus.CANCELLED
                    count += 1
            self._jobs.clear()
            self._pending_keys.clear()
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        return count

    def cancel_below_priority(self, max_priority: int) -> int:
        """Cancel all jobs with priority >= max_priority (lower priority)."""
        count = 0
        with self._lock:
            for jid, job in list(self._jobs.items()):
                if job.priority >= max_priority and job.status == JobStatus.PENDING:
                    job.status = JobStatus.CANCELLED
                    count += 1
        return count

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def cache_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._cache),
                "bytes": self._cache_bytes,
                "mb_used": self._cache_bytes / (1024 * 1024),
                "budget_mb": self._cache_budget / (1024 * 1024),
            }

    def shutdown(self, timeout: float = 5.0) -> None:
        """Graceful shutdown."""
        self._shutdown = True
        self.cancel_all()
        try:
            self._pool.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python < 3.9 doesn't have cancel_futures
            self._pool.shutdown(wait=True)


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_global_pool: Optional[EssentiaWorkerPool] = None


def get_essentia_pool(workers: int = 4) -> EssentiaWorkerPool:
    """Get or create the global Essentia worker pool."""
    global _global_pool
    if _global_pool is None:
        _global_pool = EssentiaWorkerPool(workers=workers)
    return _global_pool
