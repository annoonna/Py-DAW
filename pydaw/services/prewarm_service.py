"""PrewarmService (v0.0.20.9)

Background pre-rendering ("prewarm") for tempo-synced arrangement playback.

Goal:
- When the global BPM changes, prepare (decode + optional time-stretch) the
  *visible/active* audio clips in a background thread so the next Play is instant.
- Never block the GUI thread.
- Avoid stacking multiple expensive jobs while the user drags the BPM control
  (debounce + generation token).

This is intentionally conservative:
- It warms the ArrangerRenderCache only (shared cache used by arrangement_renderer).
- It does not modify playback state; it only fills caches.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Optional, Tuple, List

from PySide6.QtCore import QObject, Signal, QTimer

from pydaw.core.threading import ThreadPoolService, Worker
from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value
from pydaw.utils.logging_setup import get_logger

try:
    from pydaw.audio.arranger_cache import DEFAULT_ARRANGER_CACHE, ArrangerRenderCache
except Exception:  # pragma: no cover
    DEFAULT_ARRANGER_CACHE = None  # type: ignore
    ArrangerRenderCache = None  # type: ignore

# v0.0.20.23: Essentia Pool Integration for background time-stretching
try:
    from pydaw.audio.essentia_pool import (
        get_essentia_pool, PRIORITY_NORMAL, PRIORITY_HIGH
    )
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False

log = get_logger(__name__)


def _beats_per_bar(ts: str) -> float:
    """Compute beats per bar from a time signature string like '4/4'."""
    try:
        s = (ts or "4/4").strip()
        a, b = s.split("/", 1)
        num = max(1, int(a))
        den = max(1, int(b))
        return float(num) * (4.0 / float(den))
    except Exception:
        return 4.0


def _clip_overlaps_range(start: float, length: float, a: float, b: float) -> bool:
    try:
        s = float(start)
        e = float(start) + float(length)
        return (s < float(b)) and (e > float(a))
    except Exception:
        return False


@dataclass
class PrewarmStats:
    clips_considered: int = 0
    clips_warmed: int = 0
    cache_hits: int = 0
    stretches_submitted: int = 0
    stretches_completed: int = 0


class PrewarmService(QObject):
    status = Signal(str)
    error = Signal(str)

    def __init__(self, threadpool: ThreadPoolService, project_service, transport_service):
        super().__init__()
        self.threadpool = threadpool
        self.project = project_service
        self.transport = transport_service

        self._active_range: Optional[Tuple[float, float]] = None
        self._lock = threading.RLock()
        self._gen: int = 0

        # Debounce timer: avoids triggering a heavy warm job for every tiny BPM change.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)  # ms
        self._timer.timeout.connect(self._launch_warm_latest)

        # Settings
        self.lookahead_bars = 8  # warm a bit ahead of the visible range
        self.max_clips = 64      # safety cap (keeps worst-case in check)
        
        # v0.0.20.23: Essentia Pool for background time-stretching
        self._essentia_pool = None
        if ESSENTIA_AVAILABLE:
            try:
                self._essentia_pool = get_essentia_pool()
                log.info("PrewarmService: Essentia Pool available for time-stretching")
            except Exception as e:
                log.warning(f"PrewarmService: Failed to get Essentia Pool: {e}")

        # Auto-wire BPM change -> debounce trigger
        try:
            self.transport.bpm_changed.connect(self.on_bpm_changed)
        except Exception:
            pass

    def set_active_range(self, start_beat: float, end_beat: float) -> None:
        """Set the currently visible arranger range (beats)."""
        try:
            a = float(start_beat)
            b = float(end_beat)
            if b < a:
                a, b = b, a
            with self._lock:
                self._active_range = (max(0.0, a), max(0.0, b))
        except Exception:
            return

    def on_bpm_changed(self, _bpm: float) -> None:
        """Debounced handler for tempo changes."""
        try:
            with self._lock:
                self._gen += 1

            # Cancel older low-priority stretch work (prevents CPU backlog on fast BPM drags).
            # We keep CRITICAL/HIGH priorities intact (used for playback/visible items).
            if self._essentia_pool is not None and ESSENTIA_AVAILABLE:
                try:
                    self._essentia_pool.cancel_below_priority(PRIORITY_NORMAL)
                except Exception:
                    pass

            # restart debounce timer
            self._timer.start()
        except Exception:
            pass




    def _launch_warm_latest(self) -> None:
        """Launch a warm job for the latest generation."""
        with self._lock:
            gen = int(self._gen)
            active = self._active_range

        # Determine SR from settings (should match engine config in most setups).
        keys = SettingsKeys()
        try:
            sr = int(get_value(keys.sample_rate, 48000) or 48000)
        except Exception:
            sr = 48000

        try:
            bpm = float(getattr(self.project.ctx.project, "bpm", 120.0) or 120.0)
        except Exception:
            bpm = 120.0

        try:
            ts = str(getattr(self.project.ctx.project, "time_signature", "4/4") or "4/4")
        except Exception:
            ts = "4/4"

        bpb = _beats_per_bar(ts)
        lookahead = float(self.lookahead_bars) * float(bpb)

        loop_enabled = bool(getattr(self.transport, "loop_enabled", False))
        loop_a = float(getattr(self.transport, "loop_start_beat", 0.0) or 0.0)
        loop_b = float(getattr(self.transport, "loop_end_beat", 0.0) or 0.0)
        if loop_b < loop_a:
            loop_a, loop_b = loop_b, loop_a

        # Range priority:
        # - If loop is enabled, warm the loop region (plus lookahead).
        # - Else warm visible range (plus lookahead).
        # - Else fallback: warm around playhead (current beat).
        if loop_enabled and (loop_b - loop_a) > 0.001:
            a = max(0.0, loop_a)
            b = max(a, loop_b) + lookahead
        elif active and (active[1] - active[0]) > 0.001:
            a = max(0.0, float(active[0]))
            b = max(a, float(active[1])) + lookahead
        else:
            try:
                cur = float(getattr(self.transport, "current_beat", 0.0) or 0.0)
            except Exception:
                cur = 0.0
            a = max(0.0, cur - 2.0 * bpb)
            b = cur + (4.0 * bpb) + lookahead

        cache = None
        try:
            cache = DEFAULT_ARRANGER_CACHE
        except Exception:
            cache = None

        if cache is None:
            return

        def _job() -> PrewarmStats:
            st = PrewarmStats()
            try:
                # Snapshot project lists (avoid holding Qt objects across threads)
                proj = self.project.ctx.project
                clips = list(getattr(proj, "clips", []) or [])
                tracks = {t.id: t for t in (getattr(proj, "tracks", []) or [])}
            except Exception:
                return st

            # Filter relevant audio clips
            candidates: List[object] = []
            for c in clips:
                try:
                    if str(getattr(c, "kind", "audio")) != "audio":
                        continue
                    if not getattr(c, "source_path", None):
                        continue
                    tid = str(getattr(c, "track_id", "") or "")
                    tr = tracks.get(tid)
                    if tr is not None and bool(getattr(tr, "muted", False)):
                        # muted tracks are unlikely to be needed immediately
                        continue
                    if not _clip_overlaps_range(
                        float(getattr(c, "start_beats", 0.0) or 0.0),
                        float(getattr(c, "length_beats", 0.0) or 0.0),
                        a,
                        b,
                    ):
                        continue
                    candidates.append(c)
                except Exception:
                    continue

            # Safety cap: warm only first N (sorted by start position)
            try:
                candidates.sort(key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
            except Exception:
                pass
            if len(candidates) > self.max_clips:
                candidates = candidates[: self.max_clips]

            st.clips_considered = len(candidates)

            for c in candidates:
                # stop if a newer generation exists
                try:
                    with self._lock:
                        if int(self._gen) != int(gen):
                            break
                except Exception:
                    pass

                try:
                    path = str(getattr(c, "source_path", "") or "")
                    src_bpm = getattr(c, "source_bpm", None)

                    # decode-only warm
                    if src_bpm in (None, "", 0):
                        buf = cache.get_decoded(path, sr)
                        if buf is not None:
                            st.clips_warmed += 1
                        continue

                    sb = float(src_bpm)
                    if sb <= 1e-6:
                        buf = cache.get_decoded(path, sr)
                        if buf is not None:
                            st.clips_warmed += 1
                        continue

                    rate = float(bpm) / float(sb)

                    # Fast-path: already cached? (do not compute if missing)
                    try:
                        buf = cache.peek_stretched(path, sr, rate)
                    except Exception:
                        buf = None
                    if buf is not None:
                        st.cache_hits += 1
                        st.clips_warmed += 1
                        continue

                    # If we have a worker pool, submit stretch jobs asynchronously
                    if self._essentia_pool is not None:
                        base_buf = cache.get_decoded(path, sr)
                        if base_buf is None:
                            continue

                        try:
                            cache_key = cache.make_stretched_key(path, sr, rate)
                        except Exception:
                            cache_key = ""

                        def _on_done(job, _path=path, _sr=sr, _rate=rate, _gen=gen):
                            # Only store if this prewarm generation is still current
                            try:
                                with self._lock:
                                    if int(self._gen) != int(_gen):
                                        return
                            except Exception:
                                pass
                            try:
                                res = getattr(job, "result", None)
                                if res is None:
                                    return
                                cache.put_stretched(_path, _sr, _rate, res)
                            except Exception:
                                return

                        self._essentia_pool.submit_stretch(
                            audio_data=base_buf,
                            rate=rate,
                            sr=sr,
                            priority=PRIORITY_HIGH,
                            cache_key=cache_key,
                            callback=_on_done,
                        )
                        st.stretches_submitted += 1
                        continue

                    # Fallback (no pool): compute stretching inside this background job
                    buf2 = cache.get_stretched(path, sr, rate)
                    if buf2 is not None:
                        st.clips_warmed += 1

                except Exception:
                    continue

            return st


        w = Worker(_job)
        w.signals.result.connect(lambda st: self.status.emit(
            f"Prewarm: {getattr(st, 'clips_warmed', 0)}/{getattr(st, 'clips_considered', 0)} ready, "
            f"{getattr(st, 'stretches_submitted', 0)} stretch-jobs queued (BPM={bpm:.2f})"
        ))
        w.signals.error.connect(lambda e: self.error.emit(f"Prewarm Fehler: {e}"))
        w.signals.finished.connect(lambda: None)

        try:
            self.status.emit(f"Prewarm gestartet… (Range {a:.1f}–{b:.1f} beats)")
        except Exception:
            pass
        self.threadpool.submit(w)

    def submit_stretch_async(self, audio_data, target_sr: int, stretch_rate: float,
                             priority: int = 2, callback=None) -> Optional[str]:
        """Submit asynchronous time-stretch job to Essentia Pool.
        
        v0.0.20.23: Demo integration with Essentia Pool for background stretching.
        
        Args:
            audio_data: Audio numpy array
            target_sr: Target sample rate
            stretch_rate: Time-stretch factor (1.2 = 20% faster)
            priority: Job priority (0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW)
            callback: Optional callback(job_id, result_audio) when done
        
        Returns:
            job_id if submitted, None if Essentia Pool unavailable
        
        Example Usage in BPM-Change scenario:
            # When BPM changes, submit all visible clips for re-stretch
            for clip in visible_clips:
                audio = load_clip(clip.path)
                rate = new_bpm / clip.source_bpm
                prewarm.submit_stretch_async(
                    audio, 48000, rate,
                    priority=PRIORITY_HIGH,
                    callback=lambda jid, result: cache.put_stretched(clip.path, result, rate)
                )
        """
        if not self._essentia_pool:
            log.debug("Essentia Pool not available, skipping async stretch")
            return None
        
        try:
            # Submit to Essentia Pool
            job = self._essentia_pool.submit_stretch(
                audio_data=audio_data,
                rate=stretch_rate,
                sr=target_sr,
                priority=priority,
                callback=callback
            )
            return job.job_id if job else None
        except Exception as e:
            log.warning(f"Failed to submit stretch job to Essentia Pool: {e}")
            return None
