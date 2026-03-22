"""Threading utilities (placeholders for later versions).

v0.0.1: Only a minimal Worker base is provided so the project structure is ready
for non-blocking work in v0.0.2+.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    """Signals for background work."""

    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int)


class Worker(QRunnable):
    """Generic QRunnable that executes a callable in a thread pool."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(res)
        except Exception as exc:  # pragma: no cover
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


@dataclass
class ThreadPoolService:
    """Small wrapper around QThreadPool."""

    pool: QThreadPool

    @classmethod
    def create_default(cls) -> "ThreadPoolService":
        return cls(pool=QThreadPool.globalInstance())

    def submit(self, worker: Worker) -> None:
        self.pool.start(worker)
