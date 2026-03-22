"""Qt6 QAudioSink + QIODevice Skeleton (v0.0.19.7.54)

Dieses Modul ist ein *technisches Grundgerüst* für ein Clip-Launcher Playback
über QtMultimedia (QAudioSink) – unabhängig vom bestehenden JACK/sounddevice
Backend.

Ziel (Punkt 2 / User-Request):
- Gapless Playback durch kontinuierliches Füttern eines QAudioSink
  über ein eigenes QIODevice (Ringbuffer)
- GC-Schutz: QAudioSink/QIODevice als Instanzvariablen halten

Wichtig:
QtMultimedia erwartet PCM Bytes. Wir nutzen hier int16 Stereo.
"""

from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtCore import QIODevice, QByteArray

try:
    from PyQt6.QtMultimedia import QAudioSink, QAudioFormat, QMediaDevices
except Exception:  # pragma: no cover
    QAudioSink = None  # type: ignore
    QAudioFormat = None  # type: ignore
    QMediaDevices = None  # type: ignore


class AudioRingBufferIODevice(QIODevice):
    """Minimaler thread-sicherer Ringbuffer für PCM Bytes.

    Producer (z.B. Engine-Thread) -> write_pcm(...)
    Consumer (QAudioSink) -> readData(...)
    """

    def __init__(self, max_bytes: int = 4 * 1024 * 1024, parent=None):
        super().__init__(parent)
        self._max = int(max_bytes)
        self._buf = bytearray()
        self._lock = threading.RLock()
        self.open(QIODevice.OpenModeFlag.ReadOnly)

    def bytesAvailable(self) -> int:  # noqa: N802
        with self._lock:
            return len(self._buf) + super().bytesAvailable()

    # --- Producer API
    def write_pcm(self, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            # Drop-Oldest wenn Buffer zu voll (keine Blockade im Realtime-Pfad)
            extra = (len(self._buf) + len(data)) - self._max
            if extra > 0:
                del self._buf[:extra]
            self._buf.extend(data)

    # --- QIODevice required
    def readData(self, maxlen: int) -> bytes:  # noqa: N802
        with self._lock:
            if not self._buf:
                return bytes()
            n = min(int(maxlen), len(self._buf))
            out = self._buf[:n]
            del self._buf[:n]
            return bytes(out)

    def writeData(self, data: bytes) -> int:  # noqa: N802
        # Sink liest nur; Schreiben ignorieren.
        return 0


class QtAudioSinkPlayer:
    """Hält starke Referenzen auf Sink+IODevice, damit Qt6 GC nichts killt."""

    def __init__(self, sample_rate: int = 48000, channels: int = 2, parent=None):
        if QAudioSink is None or QAudioFormat is None or QMediaDevices is None:
            raise RuntimeError("QtMultimedia ist nicht verfügbar")

        self.sample_rate = int(sample_rate)
        self.channels = int(channels)

        self.io = AudioRingBufferIODevice(parent=parent)

        fmt = QAudioFormat()
        fmt.setSampleRate(self.sample_rate)
        fmt.setChannelCount(self.channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        dev = QMediaDevices.defaultAudioOutput()
        self.sink = QAudioSink(dev, fmt, parent)
        # Kleinere Buffer = niedrigere Latenz (Tradeoff: Dropouts)
        try:
            self.sink.setBufferSize(64 * 1024)
        except Exception:
            pass

    def start(self) -> None:
        # WICHTIG: Referenzen bleiben auf self.sink/self.io
        self.sink.start(self.io)

    def stop(self) -> None:
        try:
            self.sink.stop()
        except Exception:
            pass

    def push_int16_stereo(self, pcm_bytes: bytes) -> None:
        """Producer API: PCM Bytes (int16 stereo) in den Ringbuffer schreiben."""
        self.io.write_pcm(pcm_bytes)
