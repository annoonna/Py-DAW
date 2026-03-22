"""Very lightweight performance monitors for the UI.

Design goals:
- Must NEVER run inside the audio callback.
- Must be opt-in (OFF by default).
- Must be cross-platform and avoid heavy dependencies (no psutil required).

CPU sampling uses `time.process_time()` deltas / wall-time deltas.
This is extremely cheap and good enough for an in-app "is this heavy right now?" indicator.
"""

from __future__ import annotations

import os
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class CpuUsageMonitor(QObject):
    """Emit a process CPU usage percentage (normalized to 0..100%).

    Note: process CPU time can exceed wall time on multi-core systems.
    We normalize by logical CPU count to present a stable 0..100% range.
    """

    updated = pyqtSignal(float)  # percent

    def __init__(self, interval_ms: int = 1000, parent: QObject | None = None):
        super().__init__(parent)
        self._interval_ms = max(250, int(interval_ms))
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._tick)

        self._last_wall = time.perf_counter()
        self._last_cpu = time.process_time()

        c = os.cpu_count()
        self._cpu_count = int(c) if c and int(c) > 0 else 1

    def start(self) -> None:
        # Reset baseline so first tick doesn't spike.
        self._last_wall = time.perf_counter()
        self._last_cpu = time.process_time()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def set_interval_ms(self, interval_ms: int) -> None:
        self._interval_ms = max(250, int(interval_ms))
        self._timer.setInterval(self._interval_ms)

    def _tick(self) -> None:
        try:
            now_wall = time.perf_counter()
            now_cpu = time.process_time()

            d_wall = now_wall - self._last_wall
            d_cpu = now_cpu - self._last_cpu

            self._last_wall = now_wall
            self._last_cpu = now_cpu

            if d_wall <= 0:
                return

            pct = (d_cpu / d_wall) * 100.0 / float(self._cpu_count)
            if pct < 0:
                pct = 0.0
            # clamp to a sane display range
            if pct > 1000.0:
                pct = 1000.0

            self.updated.emit(float(pct))
        except Exception:
            # Best-effort: don't let perf monitoring affect app stability.
            pass
