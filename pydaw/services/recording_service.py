"""Recording service for PipeWire and JACK audio backends.

v0.0.20.632 — AP2 Phase 2A: Solides Single-Track Recording
v0.0.20.636 — AP2 Phase 2B: Multi-Track Recording

Features (Phase 2A — preserved):
- Record-Arm per Track (model flag + visual feedback)
- Pre-Roll / Count-In with metronome integration
- WAV file writing to project media folder (24-bit float)
- Automatic clip creation after recording stop
- Input monitoring (passthrough of hardware input)
- Backend auto-detection: JACK > PipeWire > sounddevice

Features (Phase 2B — new):
- Multiple tracks simultaneously armed + recorded
- Per-track input routing (stereo pair selection)
- Configurable buffer size (64/128/256/512/1024/2048)
- Plugin Delay Compensation (PDC) infrastructure
"""

from __future__ import annotations

import logging
import os
import queue
import struct
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

try:
    import numpy as np
    _NP_AVAILABLE = True
except ImportError:
    np = None
    _NP_AVAILABLE = False

if TYPE_CHECKING:
    from pydaw.services.transport_service import TransportService

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for multi-track recording state
# ---------------------------------------------------------------------------

@dataclass
class TrackRecordingState:
    """Per-track recording state for multi-track recording."""
    track_id: str
    input_pair: int = 1          # 1-based stereo pair index
    recorded_frames: list = field(default_factory=list)
    output_path: Optional[Path] = None
    start_beat: float = 0.0
    on_complete: Optional[Callable] = None  # per-track completion callback


# ---------------------------------------------------------------------------
# Buffer size constants
# ---------------------------------------------------------------------------

VALID_BUFFER_SIZES = (64, 128, 256, 512, 1024, 2048, 4096)
DEFAULT_BUFFER_SIZE = 512


class RecordingService:
    """Service for recording audio through PipeWire/JACK/sounddevice.

    v0.0.20.636 enhancements (Phase 2B):
    - Multi-track simultaneous recording
    - Per-track input routing (stereo pair)
    - Configurable buffer size
    - PDC (Plugin Delay Compensation) framework
    """

    def __init__(self):
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._backend = "sounddevice"  # default
        self._sample_rate = 48000
        self._channels = 2
        self._output_path: Path | None = None
        self._recorded_frames: list = []

        # v0.0.20.632: Enhanced recording state (Phase 2A — kept for compat)
        self._armed_track_id: str | None = None
        self._armed_input_pair: int = 1  # 1-based stereo pair index
        self._recording_start_beat: float = 0.0
        self._count_in_bars: int = 0  # 0 = no count-in
        self._count_in_active: bool = False
        self._input_monitoring: bool = False
        self._bit_depth: int = 24  # 16, 24, or 32

        # Callback for clip creation (set by MainWindow) — single-track compat
        self._on_recording_complete: Optional[Callable] = None

        # Transport reference (set by ServiceContainer)
        self._transport: Optional[TransportService] = None

        # Project media path (set before recording)
        self._project_media_path: Path | None = None

        # Streams
        self._sd_stream: Any = None
        self._jack_client: Any = None
        self._jack_ports: list = []

        # ──────────────────────────────────────────────────
        # v0.0.20.636: Multi-Track Recording (Phase 2B)
        # ──────────────────────────────────────────────────

        # Dict of armed tracks: track_id -> TrackRecordingState
        self._armed_tracks: Dict[str, TrackRecordingState] = {}

        # Active recording states (filled on start, cleared on stop)
        self._active_recordings: Dict[str, TrackRecordingState] = {}

        # Buffer size configuration
        self._buffer_size: int = DEFAULT_BUFFER_SIZE

        # PDC: per-track latency compensation in samples
        # track_id -> latency_samples (sum of plugin latencies on that track)
        self._pdc_latency: Dict[str, int] = {}

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self._punch_enabled: bool = False
        self._punch_in_beat: float = 0.0
        self._punch_out_beat: float = 0.0
        self._punch_recording_active: bool = False  # True when inside punch region

        # v0.0.20.639: Loop-Recording / Take-Lanes (AP2 Phase 2D)
        self._loop_recording: bool = False       # True when recording in loop mode
        self._take_group_ids: Dict[str, str] = {}  # track_id -> active take_group_id
        self._loop_pass: int = 0                 # current loop pass number
        self._take_service = None                # set via set_take_service()
        self._on_take_created: Optional[Callable] = None  # callback(clip, take_group_id)

        # Available hardware inputs (populated on detect)
        self._available_inputs: List[str] = []
        self._input_count: int = 2  # number of mono inputs (stereo pairs = count/2)

        # Detect available backends
        self._detect_backend()
        self._detect_inputs()

    def _detect_backend(self) -> None:
        """Detect which audio backend is available."""
        # Check for JACK
        try:
            import jack
            self._backend = "jack"
            log.info("Recording backend: JACK")
            return
        except ImportError:
            pass

        # Check for PipeWire via sounddevice
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for dev in devices:
                if 'pipewire' in str(dev.get('name', '')).lower():
                    self._backend = "pipewire"
                    log.info("Recording backend: PipeWire (via sounddevice)")
                    return
        except Exception:
            pass

        # Fallback to sounddevice
        self._backend = "sounddevice"
        log.info("Recording backend: sounddevice (fallback)")

    def _detect_inputs(self) -> None:
        """Detect available hardware audio inputs.

        v0.0.20.636: Populates _available_inputs and _input_count.
        """
        self._available_inputs = []
        self._input_count = 2  # default: at least 1 stereo pair

        if self._backend == "jack":
            try:
                import jack
                c = jack.Client("PyDAW_InputScan", no_start_server=True)
                ports = c.get_ports(is_physical=True, is_output=True, is_audio=True)
                self._input_count = len(ports)
                self._available_inputs = [str(p.name) for p in ports]
                c.close()
                log.info("JACK inputs detected: %d mono (%d stereo pairs)",
                         self._input_count, self._input_count // 2)
            except Exception as e:
                log.debug("JACK input scan failed: %s", e)
        else:
            try:
                import sounddevice as sd
                dev_info = sd.query_devices(kind='input')
                if dev_info is not None:
                    max_ch = int(dev_info.get('max_input_channels', 2))
                    self._input_count = max(2, max_ch)
                    name = str(dev_info.get('name', 'Default Input'))
                    for i in range(0, self._input_count, 2):
                        self._available_inputs.append(
                            f"{name} ({i+1}/{i+2})"
                        )
                    log.info("sounddevice inputs: %d channels on '%s'",
                             self._input_count, name)
            except Exception as e:
                log.debug("sounddevice input scan failed: %s", e)

        if not self._available_inputs:
            self._available_inputs = ["Stereo 1/2"]

    # --- Configuration ---------------------------------------------------

    def set_transport(self, transport: TransportService) -> None:
        """Set transport reference for beat-sync recording."""
        self._transport = transport

    def set_project_media_path(self, path: Path | str) -> None:
        """Set the project media folder for saving recordings."""
        self._project_media_path = Path(path)
        self._project_media_path.mkdir(parents=True, exist_ok=True)

    def set_on_recording_complete(self, callback: Callable) -> None:
        """Set callback for when recording is complete.

        Callback signature: callback(wav_path: Path, track_id: str, start_beat: float)
        """
        self._on_recording_complete = callback

    def set_count_in_bars(self, bars: int) -> None:
        """Set number of count-in bars before recording starts."""
        self._count_in_bars = max(0, int(bars))

    def set_input_monitoring(self, enabled: bool) -> None:
        """Enable/disable input monitoring (passthrough)."""
        self._input_monitoring = bool(enabled)

    def set_bit_depth(self, depth: int) -> None:
        """Set recording bit depth (16, 24, or 32)."""
        if depth in (16, 24, 32):
            self._bit_depth = depth

    def get_backend(self) -> str:
        """Get current recording backend."""
        return self._backend

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording

    @property
    def armed_track_id(self) -> str | None:
        """Currently armed track ID (first armed, for backward compat)."""
        if self._armed_tracks:
            return next(iter(self._armed_tracks))
        return self._armed_track_id

    # ──────────────────────────────────────────────────────
    # v0.0.20.636: Buffer Size Configuration (Phase 2B)
    # ──────────────────────────────────────────────────────

    def get_buffer_size(self) -> int:
        """Get current recording buffer size in samples."""
        return self._buffer_size

    def set_buffer_size(self, size: int) -> None:
        """Set recording buffer size.

        Args:
            size: Buffer size in samples (64, 128, 256, 512, 1024, 2048, 4096).
        """
        if size in VALID_BUFFER_SIZES:
            self._buffer_size = size
            log.info("Recording buffer size set to %d samples", size)
        else:
            log.warning("Invalid buffer size %d, keeping %d", size, self._buffer_size)

    def get_buffer_latency_ms(self) -> float:
        """Get current buffer latency in milliseconds."""
        return (self._buffer_size / max(1, self._sample_rate)) * 1000.0

    # ──────────────────────────────────────────────────────
    # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
    # ──────────────────────────────────────────────────────

    def set_punch(self, enabled: bool, in_beat: float = 0.0, out_beat: float = 0.0) -> None:
        """Configure punch in/out recording.

        When enabled, recording only captures audio between in_beat and out_beat.
        Audio before punch_in is discarded; recording auto-stops at punch_out.

        Args:
            enabled: Enable or disable punch mode.
            in_beat: Beat position where recording starts capturing.
            out_beat: Beat position where recording stops capturing.
        """
        self._punch_enabled = bool(enabled)
        self._punch_in_beat = max(0.0, float(in_beat))
        self._punch_out_beat = max(self._punch_in_beat + 0.25, float(out_beat))
        self._punch_recording_active = False
        log.info("Punch %s: in=%.2f, out=%.2f",
                 "enabled" if enabled else "disabled",
                 self._punch_in_beat, self._punch_out_beat)

    def is_punch_enabled(self) -> bool:
        """Return True if punch mode is active."""
        return self._punch_enabled

    def on_punch_triggered(self, boundary: str) -> None:
        """Called by TransportService when playhead crosses punch boundary.

        Args:
            boundary: "in" when playhead reaches punch_in_beat,
                     "out" when playhead reaches punch_out_beat.
        """
        if not self._punch_enabled or not self._recording:
            return

        if boundary == "in":
            self._punch_recording_active = True
            # Reset frame buffers — discard pre-roll audio
            for state in self._active_recordings.values():
                state.recorded_frames.clear()
            # Record actual start beat for clip placement
            if self._transport:
                for state in self._active_recordings.values():
                    state.start_beat = float(self._punch_in_beat)
            log.info("Punch IN at beat %.2f — recording active", self._punch_in_beat)

        elif boundary == "out":
            self._punch_recording_active = False
            log.info("Punch OUT at beat %.2f — stopping capture", self._punch_out_beat)
            # Auto-stop recording (will trigger save + callbacks)
            self.stop_recording()

    def _should_capture_frames(self) -> bool:
        """Check if we should capture audio frames right now.

        In punch mode, frames are only captured between punch_in and punch_out.
        Without punch mode, always capture (unless count-in is active).
        """
        if self._count_in_active:
            return False
        if not self._punch_enabled:
            return True
        return self._punch_recording_active

    # ──────────────────────────────────────────────────────
    # v0.0.20.639: Loop-Recording / Take-Lanes (AP2 Phase 2D)
    # ──────────────────────────────────────────────────────

    def set_take_service(self, ts) -> None:
        """Wire TakeService for loop-recording take management."""
        self._take_service = ts

    def set_on_take_created(self, callback: Optional[Callable]) -> None:
        """Set callback for when a new take is created during loop-recording.

        Callback signature: callback(wav_path: Path, track_id: str, start_beat: float, take_group_id: str, take_index: int)
        """
        self._on_take_created = callback

    def set_loop_recording(self, enabled: bool) -> None:
        """Enable/disable loop-recording mode.

        When enabled AND transport loop is active, each loop pass saves
        a separate take instead of appending to one long recording.
        """
        self._loop_recording = bool(enabled)
        self._loop_pass = 0
        log.info("Loop-recording %s", "enabled" if enabled else "disabled")

    def is_loop_recording(self) -> bool:
        """Check if loop-recording mode is active."""
        return self._loop_recording and self._recording

    def on_loop_boundary(self) -> None:
        """Called by TransportService when the playhead loops back.

        Saves the current pass as a take and starts a new pass.
        Only active during loop-recording.
        """
        if not self._loop_recording or not self._recording:
            return

        log.info("Loop boundary reached — saving take %d", self._loop_pass)

        # Save current frames as a take for each track
        for tid, state in self._active_recordings.items():
            if not state.recorded_frames:
                continue

            try:
                import numpy as np

                # Generate a unique path for this take
                take_path = self._generate_take_path(tid, self._loop_pass)
                if take_path:
                    take_path.parent.mkdir(parents=True, exist_ok=True)

                    audio_data = np.concatenate(state.recorded_frames, axis=0)

                    # Apply punch crossfade if relevant
                    if self._punch_enabled and len(audio_data) > 0:
                        audio_data = self._apply_punch_crossfade(audio_data)

                    self._write_wav_data(take_path, audio_data)

                    # Get take group (create if first pass)
                    tkg_id = self._take_group_ids.get(tid, "")
                    if not tkg_id and self._take_service:
                        loop_start = 0.0
                        loop_len = 4.0
                        if self._transport:
                            loop_start = float(getattr(self._transport, 'loop_start', 0.0))
                            loop_len = float(getattr(self._transport, 'loop_end', 4.0)) - loop_start
                        tkg_id = self._take_service.create_take_group(tid, loop_start, loop_len)
                        self._take_group_ids[tid] = tkg_id

                    # Fire callback for clip creation
                    if self._on_take_created and tkg_id:
                        try:
                            start_beat = state.start_beat
                            self._on_take_created(
                                take_path, tid, start_beat, tkg_id, self._loop_pass
                            )
                        except Exception as e:
                            log.error("Take callback error: %s", e)

                    log.info("Take %d saved for track '%s': %s", self._loop_pass, tid, take_path)

            except Exception as e:
                log.error("Failed to save take %d for track '%s': %s", self._loop_pass, tid, e)

            # Clear frames for next pass
            state.recorded_frames.clear()

        self._loop_pass += 1

    def _generate_take_path(self, track_id: str, take_index: int) -> Optional[Path]:
        """Generate WAV file path for a take."""
        if self._project_media_path:
            base = self._project_media_path
        else:
            base = Path.home() / "pydaw_recordings"
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = f"take_{track_id}_{ts}_pass{take_index:02d}.wav"
        return base / fname

    # ──────────────────────────────────────────────────────
    # v0.0.20.636: Available Inputs (Phase 2B)
    # ──────────────────────────────────────────────────────

    def get_available_inputs(self) -> List[str]:
        """Get list of available hardware input names."""
        return list(self._available_inputs)

    def get_stereo_pair_count(self) -> int:
        """Get number of available stereo input pairs."""
        return max(1, self._input_count // 2)

    def refresh_inputs(self) -> None:
        """Re-scan available hardware inputs."""
        self._detect_inputs()

    # ──────────────────────────────────────────────────────
    # v0.0.20.636: PDC — Plugin Delay Compensation (Phase 2B)
    # ──────────────────────────────────────────────────────

    def set_track_pdc_latency(self, track_id: str, latency_samples: int) -> None:
        """Set PDC latency for a track (sum of plugin latencies).

        This is used to offset the recorded audio so it aligns with
        other tracks even when plugin chains have different latencies.

        Args:
            track_id: Track identifier.
            latency_samples: Total latency in samples for this track's plugin chain.
        """
        self._pdc_latency[str(track_id)] = max(0, int(latency_samples))

    def get_track_pdc_latency(self, track_id: str) -> int:
        """Get PDC latency for a track in samples."""
        return self._pdc_latency.get(str(track_id), 0)

    def get_max_pdc_latency(self) -> int:
        """Get the maximum PDC latency across all tracks."""
        if not self._pdc_latency:
            return 0
        return max(self._pdc_latency.values())

    # ──────────────────────────────────────────────────────
    # Record Arm Management (v0.0.20.636: multi-track)
    # ──────────────────────────────────────────────────────

    def arm_track(self, track_id: str, input_pair: int = 1) -> None:
        """Arm a track for recording.

        v0.0.20.636: Now supports multiple armed tracks simultaneously.

        Args:
            track_id: Track identifier.
            input_pair: Stereo input pair (1-based). Pair 1 = inputs 1+2.
        """
        tid = str(track_id)
        pair = max(1, int(input_pair))

        self._armed_tracks[tid] = TrackRecordingState(
            track_id=tid,
            input_pair=pair,
        )
        # Backward compat: keep single-track fields in sync
        self._armed_track_id = tid
        self._armed_input_pair = pair

        log.info("Armed track '%s' with input pair %d (total armed: %d)",
                 tid, pair, len(self._armed_tracks))

    def disarm_track(self, track_id: str | None = None) -> None:
        """Disarm a track (or all tracks if track_id is None).

        v0.0.20.636: Supports selective disarm.
        """
        if track_id is None:
            self._armed_tracks.clear()
            self._armed_track_id = None
            log.info("Disarmed all tracks")
        else:
            tid = str(track_id)
            self._armed_tracks.pop(tid, None)
            if self._armed_track_id == tid:
                # Update compat field to next armed track (or None)
                if self._armed_tracks:
                    self._armed_track_id = next(iter(self._armed_tracks))
                else:
                    self._armed_track_id = None
            log.info("Disarmed track '%s' (remaining: %d)", tid, len(self._armed_tracks))

    def get_armed_track_ids(self) -> List[str]:
        """Get list of currently armed track IDs.

        v0.0.20.636: Returns all armed tracks.
        """
        return list(self._armed_tracks.keys())

    def is_track_armed(self, track_id: str) -> bool:
        """Check if a specific track is armed."""
        return str(track_id) in self._armed_tracks

    # ──────────────────────────────────────────────────────
    # Start / Stop Recording (v0.0.20.636: multi-track)
    # ──────────────────────────────────────────────────────

    def start_recording(
        self,
        output_path: str | Path | None = None,
        sample_rate: int = 48000,
        channels: int = 2,
        track_id: str | None = None,
        input_pair: int | None = None,
    ) -> bool:
        """Start recording audio.

        v0.0.20.636: Records all armed tracks simultaneously.
        Single-track args (track_id, input_pair, output_path) are still
        supported for backward compatibility — they arm that one track.

        Args:
            output_path: Path where to save the WAV file (single-track compat).
            sample_rate: Sample rate in Hz.
            channels: Number of audio channels (2 = stereo).
            track_id: Track to record to (overrides armed track, single-track compat).
            input_pair: Input pair to use (overrides armed input pair, single-track compat).

        Returns:
            True if recording started successfully.
        """
        if self._recording:
            log.warning("Already recording")
            return False

        # Backward compat: if explicit track_id given, arm it
        if track_id is not None:
            pair = max(1, int(input_pair)) if input_pair is not None else 1
            self.arm_track(track_id, pair)

        # If no tracks armed at all, try the legacy single-track field
        if not self._armed_tracks:
            if self._armed_track_id:
                self.arm_track(self._armed_track_id, self._armed_input_pair)
            else:
                log.error("No tracks armed for recording")
                return False

        self._sample_rate = sample_rate
        self._channels = channels

        # Record start beat position
        start_beat = 0.0
        if self._transport:
            start_beat = float(
                getattr(self._transport, 'current_beat', 0.0) or 0.0
            )
        self._recording_start_beat = start_beat

        # v0.0.20.637: Punch mode — clip starts at punch_in, not playhead
        clip_start_beat = start_beat
        if self._punch_enabled:
            clip_start_beat = float(self._punch_in_beat)
            self._punch_recording_active = False  # wait for punch_in trigger
            log.info("Punch recording: clip starts at beat %.2f (punch_in)", clip_start_beat)

        # Prepare per-track recording states
        self._active_recordings.clear()
        for tid, armed_state in self._armed_tracks.items():
            state = TrackRecordingState(
                track_id=tid,
                input_pair=armed_state.input_pair,
                recorded_frames=[],
                start_beat=clip_start_beat,
            )
            # Resolve output path
            if output_path is not None and len(self._armed_tracks) == 1:
                state.output_path = Path(output_path)
            else:
                state.output_path = self._generate_wav_path(tid)

            if state.output_path:
                state.output_path.parent.mkdir(parents=True, exist_ok=True)

            self._active_recordings[tid] = state

        # Legacy compat: keep single-track fields in sync
        first_state = next(iter(self._active_recordings.values()))
        self._output_path = first_state.output_path
        self._recorded_frames = first_state.recorded_frames

        log.info(
            "Starting multi-track recording: %d tracks, sr=%d, buffer=%d",
            len(self._active_recordings), sample_rate, self._buffer_size,
        )
        for tid, st in self._active_recordings.items():
            log.info("  Track '%s': input pair %d -> %s", tid, st.input_pair, st.output_path)

        # Count-in handling
        if self._count_in_bars > 0 and self._transport:
            self._count_in_active = True
            log.info("Count-in: %d bars", self._count_in_bars)

        # Start recording based on backend
        if self._backend == "jack":
            success = self._start_jack_recording()
        elif self._backend == "pipewire":
            success = self._start_pipewire_recording()
        else:
            success = self._start_sounddevice_recording()

        if success:
            self._recording = True
            log.info("Recording started successfully (%d tracks)", len(self._active_recordings))
        else:
            log.error("Failed to start recording")
            self._active_recordings.clear()

        return success

    def stop_recording(self) -> Path | None:
        """Stop recording and save all audio files.

        v0.0.20.636: Saves WAV for each armed track and fires callbacks.

        Returns:
            Path to the first saved WAV file (backward compat), or None.
        """
        if not self._recording:
            return None

        log.info("Stopping recording (%d tracks)...", len(self._active_recordings))
        self._recording = False
        self._count_in_active = False
        self._punch_recording_active = False  # v0.0.20.637: reset punch state

        # Stop streams
        self._stop_streams()

        # Wait for recording thread to finish
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=3.0)

        first_wav: Path | None = None

        # Save each track's recording
        for tid, state in self._active_recordings.items():
            if not state.recorded_frames or not state.output_path:
                log.warning("Track '%s': no frames recorded", tid)
                continue

            try:
                wav_path = self._save_wav_for_track(state)
                log.info("Track '%s' recording saved: %s", tid, wav_path)

                if first_wav is None:
                    first_wav = wav_path

                # Apply PDC offset if needed
                pdc_samples = self._pdc_latency.get(tid, 0)
                if pdc_samples > 0:
                    log.info("Track '%s': PDC offset %d samples", tid, pdc_samples)
                    pdc_seconds = pdc_samples / max(1, self._sample_rate)
                    bpm = 120.0
                    if self._transport:
                        bpm = float(getattr(self._transport, 'bpm', 120.0) or 120.0)
                    pdc_beats = pdc_seconds * (bpm / 60.0)
                    state.start_beat = max(0.0, state.start_beat - pdc_beats)

                # Fire completion callback
                if self._on_recording_complete and wav_path:
                    try:
                        self._on_recording_complete(
                            wav_path,
                            str(tid),
                            float(state.start_beat),
                        )
                    except Exception as e:
                        log.error("Clip creation callback failed for '%s': %s", tid, e)

            except Exception as e:
                log.error("Error saving recording for track '%s': %s", tid, e)

        self._active_recordings.clear()

        if not first_wav:
            log.warning("No frames recorded for any track")

        return first_wav

    def _stop_streams(self) -> None:
        """Stop all active audio streams."""
        # Close JACK client if active
        if self._jack_client is not None:
            try:
                self._jack_client.deactivate()
                self._jack_client.close()
            except Exception:
                pass
            self._jack_client = None
            self._jack_ports = []

        # Close sounddevice stream if active
        if self._sd_stream is not None:
            try:
                self._sd_stream.stop()
                self._sd_stream.close()
            except Exception:
                pass
            self._sd_stream = None

    # --- Path Generation -------------------------------------------------

    def _generate_wav_path(self, track_id: str | None = None) -> Path | None:
        """Generate a unique WAV file path in the project media folder."""
        base = self._project_media_path
        if base is None:
            # Fallback to cache directory
            base = Path(os.path.expanduser("~/.cache/Py_DAW/recordings"))
            base.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        track_name = (track_id or self._armed_track_id or "track")
        track_name = track_name.replace("/", "_").replace(" ", "_")
        filename = f"rec_{track_name}_{ts}.wav"
        return base / filename

    # --- Backend Implementations -----------------------------------------

    def _start_jack_recording(self) -> bool:
        """Start JACK recording.

        v0.0.20.636: Routes multiple input pairs to separate track buffers.
        """
        try:
            import jack

            client = jack.Client("PyDAW_Recorder")
            self._jack_client = client

            # Collect unique input pairs needed
            pairs_needed: Dict[int, List[str]] = {}  # pair_idx -> [track_ids]
            for tid, state in self._active_recordings.items():
                pair = state.input_pair
                pairs_needed.setdefault(pair, []).append(tid)

            # Create input ports for all needed pairs
            self._jack_ports = []
            port_pair_map: List[int] = []  # parallel to _jack_ports: pair number
            for pair_num in sorted(pairs_needed.keys()):
                for ch in range(self._channels):
                    port = client.inports.register(
                        f"input_p{pair_num}_ch{ch + 1}"
                    )
                    self._jack_ports.append(port)
                    port_pair_map.append(pair_num)

            # Process callback
            active_recs = self._active_recordings
            recording_ref = [True]
            count_in_ref = [self._count_in_active]
            punch_capture_ref = self  # v0.0.20.637: access _should_capture_frames via self ref
            channels = self._channels
            pairs_map = pairs_needed
            jack_ports = self._jack_ports

            @client.set_process_callback
            def process(frames):
                if not recording_ref[0]:
                    raise jack.CallbackExit
                if count_in_ref[0]:
                    return  # discard during count-in

                # v0.0.20.637: Punch guard — discard frames outside punch region
                if not punch_capture_ref._should_capture_frames():
                    return

                if not _NP_AVAILABLE:
                    return

                # Read from each pair's ports and distribute to tracks
                port_idx = 0
                for pair_num in sorted(pairs_map.keys()):
                    # Gather channels for this pair
                    pair_channels = []
                    for ch in range(channels):
                        if port_idx < len(jack_ports):
                            pair_channels.append(
                                jack_ports[port_idx].get_array()
                            )
                        port_idx += 1

                    if pair_channels:
                        chunk = np.column_stack(pair_channels).copy()
                        # Write chunk to all tracks using this pair
                        for tid in pairs_map.get(pair_num, []):
                            if tid in active_recs:
                                active_recs[tid].recorded_frames.append(chunk)

            client.activate()

            # Auto-connect to system capture ports
            capture_ports = client.get_ports(
                is_physical=True, is_output=True, is_audio=True
            )
            port_idx = 0
            for pair_num in sorted(pairs_needed.keys()):
                pair_offset = (pair_num - 1) * 2
                for ch in range(self._channels):
                    src_idx = pair_offset + ch
                    if port_idx < len(self._jack_ports) and src_idx < len(capture_ports):
                        client.connect(capture_ports[src_idx], self._jack_ports[port_idx])
                    port_idx += 1

            # Store refs for stop / count-in
            self._jack_recording_ref = recording_ref
            self._jack_countin_ref = count_in_ref

            return True

        except Exception as e:
            log.error("JACK recording failed: %s", e)
            return False

    def _start_pipewire_recording(self) -> bool:
        """Start PipeWire recording via sounddevice."""
        return self._start_sounddevice_recording()

    def _start_sounddevice_recording(self) -> bool:
        """Start sounddevice recording.

        v0.0.20.636: Multi-track support. When multiple tracks use different
        input pairs, we open a multi-channel stream and demux in the callback.
        """
        try:
            import sounddevice as sd

            active_recs = self._active_recordings
            count_in_ref = [self._count_in_active]

            # Determine max channels needed
            max_pair = 1
            for state in active_recs.values():
                max_pair = max(max_pair, state.input_pair)
            total_channels = max_pair * 2  # stereo pairs

            # Clamp to available inputs
            try:
                dev_info = sd.query_devices(kind='input')
                max_avail = int(dev_info.get('max_input_channels', 2))
                total_channels = min(total_channels, max(2, max_avail))
            except Exception:
                total_channels = min(total_channels, 2)

            def audio_callback(indata, frames, time_info, status):
                if status:
                    log.debug("Recording status: %s", status)
                if not self._recording or count_in_ref[0]:
                    return

                # v0.0.20.637: Punch guard — discard frames outside punch region
                if not self._should_capture_frames():
                    return

                # Demux: route channel pairs to their tracks
                for tid, state in active_recs.items():
                    pair = state.input_pair
                    ch_start = (pair - 1) * 2
                    ch_end = ch_start + 2

                    if ch_end <= indata.shape[1]:
                        chunk = indata[:, ch_start:ch_end].copy()
                    elif ch_start < indata.shape[1]:
                        # Partial: mono -> duplicate to stereo
                        mono = indata[:, ch_start:ch_start + 1].copy()
                        chunk = np.column_stack([mono, mono])
                    else:
                        # Input pair not available -> record silence
                        chunk = np.zeros((frames, 2), dtype=np.float32)

                    state.recorded_frames.append(chunk)

            self._sd_stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=total_channels,
                callback=audio_callback,
                dtype='float32',
                blocksize=self._buffer_size,
                device=None,
            )
            self._sd_stream.start()
            self._sd_count_in_ref = count_in_ref

            return True

        except Exception as e:
            log.error("Sounddevice recording failed: %s", e)
            return False

    # --- WAV File Writing ------------------------------------------------

    def _save_wav_for_track(self, state: TrackRecordingState) -> Path:
        """Save recorded frames for a single track to WAV file.

        v0.0.20.636: Per-track WAV writing extracted from _save_wav().
        v0.0.20.638: Applies crossfade at punch boundaries.
        """
        if not state.output_path:
            raise ValueError("No output path set for track '%s'" % state.track_id)

        state.output_path.parent.mkdir(parents=True, exist_ok=True)

        if not state.recorded_frames:
            raise ValueError("No recorded frames for track '%s'" % state.track_id)

        if not _NP_AVAILABLE:
            raise RuntimeError("numpy required for recording")

        # Concatenate all recorded frames
        audio_data = np.concatenate(state.recorded_frames, axis=0)

        # Apply PDC trimming: remove leading samples equal to PDC offset
        pdc_samples = self._pdc_latency.get(state.track_id, 0)
        if pdc_samples > 0 and pdc_samples < len(audio_data):
            log.info("Track '%s': trimming %d PDC samples from start",
                     state.track_id, pdc_samples)
            audio_data = audio_data[pdc_samples:]

        # v0.0.20.638: Apply crossfade at punch boundaries (AP2 Phase 2C)
        if self._punch_enabled and len(audio_data) > 0:
            audio_data = self._apply_punch_crossfade(audio_data)

        return self._write_wav_data(state.output_path, audio_data)

    def _apply_punch_crossfade(self, audio_data) -> 'np.ndarray':
        """Apply linear crossfade at punch in/out boundaries.

        v0.0.20.638: Prevents clicks/pops at hard cut boundaries by applying
        a short linear fade-in at the start and fade-out at the end.

        The crossfade length is read from AudioConfig (default 10ms, configurable).

        Args:
            audio_data: numpy array of shape (frames, channels) or (frames,).

        Returns:
            audio_data with crossfades applied (modified in-place).
        """
        try:
            from pydaw.core.audio_config import audio_config
            fade_samples = audio_config.crossfade_samples(self._sample_rate)
        except Exception:
            # Fallback: 10ms at current sample rate
            fade_samples = max(0, int(0.010 * self._sample_rate))

        if fade_samples <= 0:
            return audio_data

        n_frames = len(audio_data)
        if n_frames < fade_samples * 2:
            # Audio too short for full fade-in + fade-out; use half
            fade_samples = max(1, n_frames // 2)

        # Linear fade-in ramp: 0.0 → 1.0
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        # Linear fade-out ramp: 1.0 → 0.0
        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)

        if audio_data.ndim == 2:
            # Stereo: broadcast across channels
            fade_in = fade_in[:, np.newaxis]
            fade_out = fade_out[:, np.newaxis]

        # Apply in-place
        audio_data[:fade_samples] = audio_data[:fade_samples] * fade_in
        audio_data[-fade_samples:] = audio_data[-fade_samples:] * fade_out

        log.info("Punch crossfade applied: %d samples (%.1f ms) at %dHz",
                 fade_samples, fade_samples / max(1, self._sample_rate) * 1000.0,
                 self._sample_rate)

        return audio_data

    def _save_wav(self) -> Path:
        """Save recorded frames to WAV file (backward compat for single-track)."""
        if not self._output_path:
            raise ValueError("No output path set")

        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._recorded_frames:
            raise ValueError("No recorded frames")

        if not _NP_AVAILABLE:
            raise RuntimeError("numpy required for recording")

        audio_data = np.concatenate(self._recorded_frames, axis=0)
        return self._write_wav_data(self._output_path, audio_data)

    def _write_wav_data(self, path: Path, audio_data) -> Path:
        """Write numpy audio data to WAV file.

        v0.0.20.636: Extracted from _save_wav for reuse.
        """
        # Determine sample width and conversion
        if self._bit_depth == 32:
            sample_width = 4
            audio_bytes = audio_data.astype(np.float32).tobytes()
        elif self._bit_depth == 24:
            sample_width = 3
            clamped = np.clip(audio_data, -1.0, 1.0)
            scaled = (clamped * 8388607.0).astype(np.int32)
            # Pack as 3 bytes per sample (little-endian)
            audio_bytes = bytearray()
            for sample in scaled.flat:
                s = int(sample)
                audio_bytes.extend(struct.pack('<i', s)[:3])
            audio_bytes = bytes(audio_bytes)
        else:
            sample_width = 2
            audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

        channels = 2
        if audio_data.ndim == 2:
            channels = audio_data.shape[1]
        elif audio_data.ndim == 1:
            channels = 1

        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio_bytes)

        log.info(
            "WAV saved: %s (%d frames, %d-bit, %dHz, %dch)",
            path, len(audio_data), self._bit_depth, self._sample_rate, channels,
        )
        return path

    # --- Count-In Management ---------------------------------------------

    def finish_count_in(self) -> None:
        """Called by transport/metronome when count-in bars are complete."""
        if self._count_in_active:
            self._count_in_active = False
            log.info("Count-in complete, recording started")
            # Also update JACK callback ref if applicable
            if hasattr(self, '_jack_countin_ref'):
                self._jack_countin_ref[0] = False
            if hasattr(self, '_sd_count_in_ref'):
                self._sd_count_in_ref[0] = False

    # --- Input Monitoring ------------------------------------------------

    def get_input_level(self) -> tuple[float, float]:
        """Get current input level (peak L, peak R).

        For use in VU meter display of armed tracks.
        Returns (0.0, 0.0) if not monitoring.
        """
        if not self._recording:
            return (0.0, 0.0)

        # Check all active recordings for the latest chunk
        for state in self._active_recordings.values():
            if state.recorded_frames:
                try:
                    last_chunk = state.recorded_frames[-1]
                    if _NP_AVAILABLE and len(last_chunk) > 0:
                        if last_chunk.ndim == 2 and last_chunk.shape[1] >= 2:
                            return (
                                float(np.abs(last_chunk[:, 0]).max()),
                                float(np.abs(last_chunk[:, 1]).max()),
                            )
                        else:
                            peak = float(np.abs(last_chunk).max())
                            return (peak, peak)
                except Exception:
                    pass
        return (0.0, 0.0)

    def get_input_level_for_track(self, track_id: str) -> tuple[float, float]:
        """Get input level for a specific track.

        v0.0.20.636: Per-track metering for multi-track recording.
        """
        if not self._recording:
            return (0.0, 0.0)

        state = self._active_recordings.get(str(track_id))
        if not state or not state.recorded_frames:
            return (0.0, 0.0)

        try:
            last_chunk = state.recorded_frames[-1]
            if _NP_AVAILABLE and len(last_chunk) > 0:
                if last_chunk.ndim == 2 and last_chunk.shape[1] >= 2:
                    return (
                        float(np.abs(last_chunk[:, 0]).max()),
                        float(np.abs(last_chunk[:, 1]).max()),
                    )
                else:
                    peak = float(np.abs(last_chunk).max())
                    return (peak, peak)
        except Exception:
            pass
        return (0.0, 0.0)

    # --- Cleanup ---------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._recording:
            self.stop_recording()
        self._stop_streams()
        self._armed_tracks.clear()
        self._active_recordings.clear()
