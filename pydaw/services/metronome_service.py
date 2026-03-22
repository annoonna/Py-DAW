"""MetronomeService (v0.0.13).

Plays a simple click on metronome ticks without blocking the GUI.

Implementation strategy:
- Prefer sounddevice OutputStream (PortAudio) if available.
- If unavailable or fails, falls back to a no-op with status messages.

This is placeholder-quality audio, sufficient for a first "real DAW" step.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Optional, Callable

import numpy as np

try:
    import sounddevice as sd  # type: ignore
except Exception:  # noqa: BLE001
    sd = None  # type: ignore


@dataclass
class MetronomeConfig:
    samplerate: int = 48000
    device: Optional[int] = None
    volume: float = 0.35


class MetronomeService:
    def __init__(self, on_status: Callable[[str], None] | None = None):
        self.cfg = MetronomeConfig()
        self._lock = threading.Lock()
        self._enabled = True
        self._stream = None
        self._queue: list[np.ndarray] = []
        self._on_status = on_status or (lambda _m: None)

    def configure(self, samplerate: int | None = None, device: int | None = None, volume: float | None = None) -> None:
        with self._lock:
            if samplerate is not None:
                self.cfg.samplerate = int(samplerate)
            if device is not None:
                self.cfg.device = int(device)
            if volume is not None:
                self.cfg.volume = float(volume)
        self._restart_stream()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def shutdown(self) -> None:
        with self._lock:
            self._queue.clear()
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    def play_click(self, accent: bool = False) -> None:
        if not self._enabled:
            return
        if sd is None:
            return

        # create a short click (noise burst + decay)
        sr = int(self.cfg.samplerate)
        length_ms = 18 if accent else 12
        n = max(1, int(sr * length_ms / 1000.0))
        t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
        env = np.exp(-t * (18.0 if accent else 22.0)).astype(np.float32)
        noise = (np.random.uniform(-1.0, 1.0, n).astype(np.float32) * env)
        click = (noise * float(self.cfg.volume) * (1.35 if accent else 1.0)).astype(np.float32)
        stereo = np.column_stack([click, click])

        with self._lock:
            self._queue.append(stereo)
        self._ensure_stream()

    # --- internal

    def _ensure_stream(self) -> None:
        if sd is None:
            return
        with self._lock:
            if self._stream is not None:
                return
        self._restart_stream()

    def _restart_stream(self) -> None:
        if sd is None:
            return
        with self._lock:
            # close old
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            try:
                self._stream = sd.OutputStream(
                    samplerate=int(self.cfg.samplerate),
                    channels=2,
                    dtype="float32",
                    device=self.cfg.device,
                    callback=self._callback,
                    blocksize=0,
                )
                self._stream.start()
                self._on_status("Metronom Audio: OutputStream aktiv.")
            except Exception as exc:  # noqa: BLE001
                self._stream = None
                self._on_status(f"Metronom Audio deaktiviert: {exc}")

    def _callback(self, outdata, frames, time, status):  # noqa: ANN001
        # Called from PortAudio thread.
        outdata[:] = 0.0
        if status:
            # don't spam
            pass
        with self._lock:
            if not self._queue:
                return
            buf = self._queue[0]
            take = min(frames, buf.shape[0])
            outdata[:take, :] = buf[:take, :]
            if take < buf.shape[0]:
                self._queue[0] = buf[take:, :]
            else:
                self._queue.pop(0)
