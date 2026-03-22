"""v0.0.20.605: Clip Launcher Audio Recording Service.

Handles:
1. Audio Input → Launcher-Slot aufnehmen
2. Punch In/Out (Loop-gebunden)
3. Monitoring (Input immer hörbar während Aufnahme)

Architecture:
- Opens a sounddevice InputStream when recording is armed
- Records audio to a numpy buffer
- On stop: saves to WAV, creates/assigns audio clip to launcher slot
- Monitoring: routes input to the audio engine's output mix

Thread safety:
- Input callback runs on audio thread → writes to ring buffer
- GUI timer commits buffer to disk when stopped
"""
from __future__ import annotations

import logging
import threading
import wave
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


class ClipLauncherRecordService:
    """Audio recording into Clip Launcher slots."""

    def __init__(self, project: Any, audio_engine: Any, transport: Any) -> None:
        self.project = project
        self.audio_engine = audio_engine
        self.transport = transport

        self._recording: bool = False
        self._monitoring: bool = False
        self._target_slot_key: str = ''
        self._target_track_id: str = ''
        self._sample_rate: int = 48000
        self._channels: int = 2

        # Ring buffer for recording (pre-allocated, max 5 minutes)
        self._max_samples = 48000 * 60 * 5  # 5 min
        self._buffer: Optional[Any] = None  # np.ndarray
        self._write_pos: int = 0
        self._lock = threading.Lock()

        # Punch In/Out (beat positions)
        self._punch_in_beat: float = 0.0
        self._punch_out_beat: float = 0.0
        self._punch_enabled: bool = False

        # Monitoring buffer (latest input block for passthrough)
        self._monitor_buffer: Optional[Any] = None

        # Input stream handle
        self._stream = None

    def start_recording(self, slot_key: str, track_id: str, *,
                        punch_in: float = 0.0, punch_out: float = 0.0) -> bool:
        """Start recording audio input into the given launcher slot.

        Returns True if recording started successfully.
        """
        if np is None:
            log.warning("numpy not available — cannot record audio")
            return False
        if self._recording:
            self.stop_recording()

        self._target_slot_key = str(slot_key)
        self._target_track_id = str(track_id)
        self._punch_in_beat = float(punch_in)
        self._punch_out_beat = float(punch_out)
        self._punch_enabled = punch_out > punch_in + 0.01

        # Determine sample rate from audio engine
        try:
            sr = int(getattr(self.audio_engine, 'sample_rate', 48000) or 48000)
            self._sample_rate = sr if sr > 0 else 48000
        except Exception:
            self._sample_rate = 48000

        # Allocate buffer
        self._buffer = np.zeros((self._max_samples, self._channels), dtype=np.float32)
        self._write_pos = 0

        # Check monitoring setting from project model
        try:
            self._monitoring = bool(getattr(self.project.ctx.project, 'launcher_monitoring', True))
        except Exception:
            self._monitoring = True

        # Open input stream
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype='float32',
                callback=self._input_callback,
                blocksize=256,
            )
            self._stream.start()
            self._recording = True
            log.info("Clip Launcher: Recording started for slot %s (SR=%d)", slot_key, self._sample_rate)
            return True
        except Exception as e:
            log.error("Clip Launcher: Failed to start recording: %s", e)
            self._buffer = None
            return False

    def stop_recording(self) -> Optional[str]:
        """Stop recording and save to WAV file.

        Returns the path to the recorded WAV file, or None on failure.
        """
        if not self._recording:
            return None

        self._recording = False

        # Stop stream
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None

        # Save buffer to WAV
        if self._buffer is None or self._write_pos <= 0:
            self._buffer = None
            return None

        try:
            with self._lock:
                audio_data = self._buffer[:self._write_pos].copy()
            self._buffer = None

            # Generate unique filename
            media_dir = self._get_media_dir()
            os.makedirs(media_dir, exist_ok=True)
            ts = int(time.time() * 1000)
            filename = f"launcher_rec_{ts}.wav"
            filepath = os.path.join(media_dir, filename)

            # Write WAV (16-bit PCM)
            with wave.open(filepath, 'w') as wf:
                wf.setnchannels(self._channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self._sample_rate)
                # Convert float32 → int16
                int_data = np.clip(audio_data * 32767.0, -32768, 32767).astype(np.int16)
                wf.writeframes(int_data.tobytes())

            log.info("Clip Launcher: Recorded %d samples → %s", self._write_pos, filepath)

            # Create clip and assign to slot
            self._create_audio_clip(filepath)

            return filepath
        except Exception as e:
            log.error("Clip Launcher: Failed to save recording: %s", e)
            self._buffer = None
            return None

    def set_monitoring(self, enabled: bool) -> None:
        """Enable/disable input monitoring."""
        self._monitoring = bool(enabled)
        try:
            self.project.ctx.project.launcher_monitoring = bool(enabled)
        except Exception:
            pass

    def is_recording(self) -> bool:
        return bool(self._recording)

    def is_monitoring(self) -> bool:
        return bool(self._monitoring)

    def get_monitor_buffer(self) -> Optional[Any]:
        """Get latest input block for monitoring passthrough.

        Called by audio engine pull sources to mix input into output.
        """
        return self._monitor_buffer

    # ---- Internal ----

    def _input_callback(self, indata, frames, time_info, status):
        """sounddevice input callback (audio thread — no exceptions!)."""
        try:
            if np is None or self._buffer is None:
                return

            # Monitoring: store latest block
            if self._monitoring:
                self._monitor_buffer = indata.copy()
            else:
                self._monitor_buffer = None

            if not self._recording:
                return

            # Punch In/Out check
            if self._punch_enabled:
                try:
                    cur_beat = float(getattr(self.transport, 'current_beat', 0.0) or 0.0)
                    if cur_beat < self._punch_in_beat or cur_beat > self._punch_out_beat:
                        return
                except Exception:
                    pass

            # Write to buffer
            n = min(frames, len(indata))
            with self._lock:
                end = self._write_pos + n
                if end > self._max_samples:
                    # Buffer full — stop
                    n = self._max_samples - self._write_pos
                    if n <= 0:
                        return
                    end = self._write_pos + n
                self._buffer[self._write_pos:end] = indata[:n]
                self._write_pos = end
        except Exception:
            pass

    def _get_media_dir(self) -> str:
        """Get or create media directory for recordings."""
        try:
            proj_path = str(getattr(self.project.ctx, 'project_path', '') or '')
            if proj_path:
                return os.path.join(os.path.dirname(proj_path), 'media', 'recordings')
        except Exception:
            pass
        return os.path.join(os.path.expanduser('~'), '.pydaw', 'recordings')

    def _create_audio_clip(self, filepath: str) -> None:
        """Create audio clip from recorded WAV and assign to launcher slot."""
        try:
            from pydaw.model.project import Clip

            duration_beats = 4.0  # default
            try:
                bpm = float(getattr(self.project.ctx.project, 'bpm', 120.0) or 120.0)
                duration_sec = float(self._write_pos) / float(self._sample_rate)
                duration_beats = max(1.0, (duration_sec * bpm) / 60.0)
            except Exception:
                pass

            clip = Clip(
                kind='audio',
                track_id=str(self._target_track_id),
                start_beats=0.0,
                length_beats=float(duration_beats),
                label=f"Recording {time.strftime('%H:%M:%S')}",
                source_path=str(filepath),
            )

            try:
                clip.launcher_only = True
                clip.source_bpm = float(getattr(self.project.ctx.project, 'bpm', 120.0) or 120.0)
            except Exception:
                pass

            self.project.ctx.project.clips.append(clip)
            cid = str(getattr(clip, 'id', ''))
            if cid and self._target_slot_key:
                self.project.ctx.project.clip_launcher[str(self._target_slot_key)] = cid
                try:
                    self.project.project_updated.emit()
                    self.project.status.emit(f"Audio aufgenommen: {os.path.basename(filepath)}")
                except Exception:
                    pass
        except Exception as e:
            log.error("Failed to create clip from recording: %s", e)
