"""RustEngineBridge — Python ↔ Rust Audio-Engine IPC Bridge.

v0.0.20.630 — Phase 1A

This module provides the Python-side interface to the Rust audio engine.
Communication uses Unix Domain Sockets with MessagePack-encoded frames.

Frame format: [u32 LE length][msgpack payload]

Architecture:
    ┌─────────────────────────────────────────────┐
    │  Python GUI (PyQt6)                         │
    │                                             │
    │  RustEngineBridge                           │
    │  ├─ send_command(cmd)  → Unix Socket → Rust │
    │  ├─ _reader_thread     ← Unix Socket ← Rust│
    │  ├─ event signals (PyQt6)                   │
    │  └─ subprocess management                   │
    └─────────────────────────────────────────────┘

Usage:
    bridge = RustEngineBridge.instance()
    bridge.start_engine()
    bridge.play()
    bridge.set_tempo(140.0)
    bridge.stop()
    bridge.shutdown()

The bridge is a singleton — only one engine process per application.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import msgpack
    _MSGPACK_AVAILABLE = True
except ImportError:
    _MSGPACK_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, Signal, QTimer
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# v0.0.20.728: Cross-platform socket/pipe path
if sys.platform == "win32":
    DEFAULT_SOCKET_PATH = r"\\.\pipe\pydaw_engine"
elif sys.platform == "darwin":
    DEFAULT_SOCKET_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pydaw_engine.sock")
else:
    DEFAULT_SOCKET_PATH = "/tmp/pydaw_engine.sock"
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BUFFER_SIZE = 512
DEFAULT_BPM = 120.0

# Engine binary search paths (in priority order)
# v0.0.20.728: Extended for Nuitka standalone builds + cross-platform
_ENGINE_NAME = "pydaw_engine.exe" if sys.platform == "win32" else "pydaw_engine"
_ENGINE_SEARCH_PATHS = [
    # Nuitka standalone: binary sits NEXT TO the executable
    Path(getattr(sys, '_MEIPASS', '')) / _ENGINE_NAME if hasattr(sys, '_MEIPASS') else Path("."),
    Path(sys.executable).parent / _ENGINE_NAME,
    Path(os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))) / _ENGINE_NAME,
    # Same directory as this Python file (for dev + portable installs)
    Path(__file__).parent.parent.parent / _ENGINE_NAME,
    # Development: cargo build output
    Path(__file__).parent.parent.parent / "pydaw_engine" / "target" / "release" / _ENGINE_NAME,
    Path(__file__).parent.parent.parent / "pydaw_engine" / "target" / "debug" / _ENGINE_NAME,
    # Installed: alongside the Python package
    Path(sys.prefix) / "bin" / _ENGINE_NAME,
    # System-wide (Linux/macOS)
    Path("/usr/local/bin/pydaw_engine"),
    Path("/usr/bin/pydaw_engine"),
]


def _find_engine_binary() -> Optional[Path]:
    """Find the pydaw_engine binary."""
    # Check PYDAW_ENGINE_PATH env var first
    env_path = os.environ.get("PYDAW_ENGINE_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file() and os.access(str(p), os.X_OK):
            return p

    # Also check PATH
    which_result = shutil.which("pydaw_engine")
    if which_result:
        return Path(which_result)

    # Search known locations
    for path in _ENGINE_SEARCH_PATHS:
        if path.is_file() and os.access(str(path), os.X_OK):
            return path

    return None


# ---------------------------------------------------------------------------
# Frame encoding/decoding
# ---------------------------------------------------------------------------

def _encode_frame(data: dict) -> bytes:
    """Encode a command dict to a length-prefixed MessagePack frame."""
    if _MSGPACK_AVAILABLE:
        payload = msgpack.packb(data, use_bin_type=True)
    else:
        # Fallback to JSON (slower but works without msgpack)
        payload = json.dumps(data).encode("utf-8")
    length = struct.pack("<I", len(payload))
    return length + payload


def _decode_frame(payload: bytes) -> dict:
    """Decode a MessagePack payload to a dict."""
    if _MSGPACK_AVAILABLE:
        return msgpack.unpackb(payload, raw=False)
    else:
        return json.loads(payload.decode("utf-8"))


def _recv_frame(sock: socket.socket) -> Optional[bytes]:
    """Read one length-prefixed frame from a socket. Returns None on EOF."""
    # Read 4-byte length prefix
    len_buf = b""
    while len(len_buf) < 4:
        chunk = sock.recv(4 - len(len_buf))
        if not chunk:
            return None
        len_buf += chunk

    length = struct.unpack("<I", len_buf)[0]
    if length > 16 * 1024 * 1024:
        raise ValueError(f"Frame too large: {length} bytes")

    # Read payload
    buf = b""
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            return None
        buf += chunk

    return buf


# ---------------------------------------------------------------------------
# RustEngineBridge
# ---------------------------------------------------------------------------

if _QT_AVAILABLE:
    _BASE_CLASS = QObject
else:
    _BASE_CLASS = object


class RustEngineBridge(_BASE_CLASS):
    """Singleton bridge to the Rust audio engine process.

    Manages:
    - Engine subprocess lifecycle (start, monitor, restart, shutdown)
    - IPC via Unix Domain Socket (send commands, receive events)
    - PyQt6 signals for GUI integration (meter levels, playhead, etc.)

    Thread safety:
    - send_command() is thread-safe (uses a lock on the socket)
    - Events are received on a background thread and dispatched via Qt signals
    """

    # --- Qt Signals (only if Qt available) ---
    if _QT_AVAILABLE:
        # Transport
        playhead_changed = Signal(float, int, bool)  # beat, sample_pos, is_playing
        transport_state_changed = Signal(bool, float)  # is_playing, beat

        # Metering
        master_meter_changed = Signal(float, float, float, float)  # peak_l, peak_r, rms_l, rms_r
        track_meters_changed = Signal(list)  # list of (track_index, peak_l, peak_r, rms_l, rms_r)

        # Engine status
        engine_ready = Signal(int, int, str)  # sample_rate, buffer_size, device_name
        engine_error = Signal(int, str)  # code, message
        engine_pong = Signal(int, float, int)  # seq, cpu_load, xrun_count
        plugin_crashed = Signal(str, int, str)  # track_id, slot_index, message
        plugin_scan_result = Signal(list, int, list)  # plugins, scan_time_ms, errors
        plugin_loaded = Signal(str, int, str, str, int, int)  # track_id, slot, name, format, params, latency
        engine_shutdown = Signal()

    # Singleton
    _instance: Optional[RustEngineBridge] = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> RustEngineBridge:
        """Get or create the singleton bridge instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if _QT_AVAILABLE:
            super().__init__()
        self._socket: Optional[socket.socket] = None
        self._socket_lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._shutting_down = False  # v0.0.20.666: prevents error flood on disconnect

        self._socket_path = DEFAULT_SOCKET_PATH
        self._sample_rate = DEFAULT_SAMPLE_RATE
        self._buffer_size = DEFAULT_BUFFER_SIZE
        self._bpm = DEFAULT_BPM

        # Ping tracking
        self._ping_seq = 0
        self._last_pong_time = 0.0
        self._last_cpu_load = 0.0
        self._last_render_time_us = 0.0
        self._last_xrun_count = 0

        # Health check timer (Qt)
        self._health_timer: Optional[QTimer] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    # --- Engine Lifecycle -------------------------------------------------

    def start_engine(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> bool:
        """Start the Rust engine subprocess and connect via IPC.

        Returns True if successfully started and connected.
        """
        if self.is_running:
            log.warning("Engine already running")
            return True

        self._socket_path = socket_path
        self._sample_rate = sample_rate
        self._buffer_size = buffer_size

        # Find engine binary
        engine_bin = _find_engine_binary()
        if engine_bin is None:
            log.error(
                "Rust engine binary not found. Build with: "
                "cd pydaw_engine && cargo build --release"
            )
            return False

        log.info("Starting engine: %s", engine_bin)

        # Remove stale socket
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass

        # Start subprocess
        try:
            self._process = subprocess.Popen(
                [
                    str(engine_bin),
                    "--socket", socket_path,
                    "--sr", str(sample_rate),
                    "--buf", str(buffer_size),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            log.error("Failed to start engine: %s", e)
            return False

        log.info("Engine PID: %d", self._process.pid)

        # Wait for socket to appear (engine needs time to bind)
        for _ in range(50):  # max 5 seconds
            if os.path.exists(socket_path):
                break
            time.sleep(0.1)
        else:
            log.error("Engine socket did not appear within 5 seconds")
            self._kill_process()
            return False

        # Connect
        return self._connect()

    def _connect(self) -> bool:
        """Connect to the engine's Unix socket."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect(self._socket_path)
            sock.settimeout(None)  # blocking mode for reader thread
            self._socket = sock
            self._connected = True
            self._running = True
            log.info("Connected to engine at %s", self._socket_path)
        except (socket.error, OSError) as e:
            log.error("Failed to connect to engine: %s", e)
            return False

        # Start reader thread
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="pydaw-ipc-reader",
            daemon=True,
        )
        self._reader_thread.start()

        # Start health check timer
        if _QT_AVAILABLE:
            self._health_timer = QTimer()
            self._health_timer.setInterval(5000)  # 5 seconds
            self._health_timer.timeout.connect(self._health_check)
            self._health_timer.start()

        # Send initial configuration
        self.send_command({
            "cmd": "Configure",
            "sample_rate": self._sample_rate,
            "buffer_size": self._buffer_size,
            "device": "",
        })

        return True

    def shutdown(self):
        """Gracefully shut down the engine."""
        log.info("Shutting down engine bridge")

        # v0.0.20.666: Stop event dispatch IMMEDIATELY to prevent error flood
        self._shutting_down = True

        if self._health_timer:
            self._health_timer.stop()
            self._health_timer = None

        # Send shutdown command
        if self._connected:
            try:
                self.send_command({"cmd": "Shutdown"})
                time.sleep(0.2)
            except Exception:
                pass

        self._running = False
        self._connected = False

        # Close socket
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        # Wait for reader thread
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

        # Terminate process
        self._kill_process()

        # Cleanup socket file
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        log.info("Engine bridge shut down")

    def _kill_process(self):
        """Force-kill the engine process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                log.warning("Engine did not terminate, killing...")
                self._process.kill()
                self._process.wait(timeout=2.0)
            except Exception as e:
                log.error("Error killing engine: %s", e)
            self._process = None

    # --- IPC: Send Commands -----------------------------------------------

    def send_command(self, cmd: dict) -> bool:
        """Send a command to the engine. Thread-safe.

        Args:
            cmd: Command dict with "cmd" key matching ipc::Command variants.

        Returns:
            True if sent successfully.
        """
        if not self._connected or not self._socket:
            return False

        frame = _encode_frame(cmd)
        with self._socket_lock:
            try:
                self._socket.sendall(frame)
                return True
            except (socket.error, OSError) as e:
                log.error("Failed to send command: %s", e)
                self._connected = False
                return False

    # --- Convenience methods (typed command wrappers) ----------------------

    def play(self):
        """Start playback."""
        self.send_command({"cmd": "Play"})

    def stop(self):
        """Stop playback (reset to start)."""
        self.send_command({"cmd": "Stop"})

    def pause(self):
        """Pause playback (keep position)."""
        self.send_command({"cmd": "Pause"})

    def seek(self, beat: float):
        """Seek to a beat position."""
        self.send_command({"cmd": "Seek", "beat": float(beat)})

    def set_tempo(self, bpm: float):
        """Set tempo in BPM."""
        self.send_command({"cmd": "SetTempo", "bpm": float(bpm)})

    def set_time_signature(self, numerator: int, denominator: int):
        """Set time signature."""
        self.send_command({
            "cmd": "SetTimeSignature",
            "numerator": int(numerator),
            "denominator": int(denominator),
        })

    def set_loop(self, enabled: bool, start_beat: float, end_beat: float):
        """Set loop region."""
        self.send_command({
            "cmd": "SetLoop",
            "enabled": bool(enabled),
            "start_beat": float(start_beat),
            "end_beat": float(end_beat),
        })

    def add_track(self, track_id: str, track_index: int, kind: str = "audio"):
        """Add a track to the audio graph."""
        self.send_command({
            "cmd": "AddTrack",
            "track_id": str(track_id),
            "track_index": int(track_index),
            "kind": str(kind),
        })

    def remove_track(self, track_id: str):
        """Remove a track from the audio graph."""
        self.send_command({"cmd": "RemoveTrack", "track_id": str(track_id)})

    def set_track_param(self, track_index: int, param: str, value: float):
        """Set a track parameter (Volume, Pan, Mute, Solo)."""
        self.send_command({
            "cmd": "SetTrackParam",
            "track_index": int(track_index),
            "param": str(param),
            "value": float(value),
        })

    def set_group_routing(self, child_index: int, group_index: Optional[int]):
        """Set group bus routing."""
        self.send_command({
            "cmd": "SetGroupRouting",
            "child_track_index": int(child_index),
            "group_track_index": group_index,
        })

    def ping(self) -> int:
        """Send a ping, returns the sequence number."""
        self._ping_seq += 1
        self.send_command({"cmd": "Ping", "seq": self._ping_seq})
        return self._ping_seq

    def midi_note_on(self, track_id: str, channel: int, note: int, velocity: float):
        """Send MIDI note-on to a track."""
        self.send_command({
            "cmd": "MidiNoteOn",
            "track_id": str(track_id),
            "channel": int(channel),
            "note": int(note),
            "velocity": float(velocity),
        })

    def midi_note_off(self, track_id: str, channel: int, note: int):
        """Send MIDI note-off to a track."""
        self.send_command({
            "cmd": "MidiNoteOff",
            "track_id": str(track_id),
            "channel": int(channel),
            "note": int(note),
        })

    def midi_cc(self, track_id: str, channel: int, cc: int, value: float):
        """Send MIDI CC to a track."""
        self.send_command({
            "cmd": "MidiCC",
            "track_id": str(track_id),
            "channel": int(channel),
            "cc": int(cc),
            "value": float(value),
        })

    # --- Audio Data (Phase 1B) --------------------------------------------

    def load_audio_clip(
        self,
        clip_id: str,
        audio_data: bytes,
        channels: int = 2,
        sample_rate: int = 44100,
    ):
        """Load audio clip data into the Rust engine.

        Args:
            clip_id: Unique clip identifier.
            audio_data: Raw f32 LE interleaved PCM bytes.
            channels: Number of channels (1=mono, 2=stereo).
            sample_rate: Sample rate of the audio data.
        """
        import base64
        b64 = base64.b64encode(audio_data).decode("ascii")
        self.send_command({
            "cmd": "LoadAudioClip",
            "clip_id": str(clip_id),
            "channels": int(channels),
            "sample_rate": int(sample_rate),
            "audio_b64": b64,
        })

    def load_audio_clip_from_numpy(
        self,
        clip_id: str,
        samples: Any,
        channels: int = 2,
        sample_rate: int = 44100,
    ):
        """Load audio clip from a numpy array.

        Args:
            clip_id: Unique clip identifier.
            samples: numpy float32 array (interleaved if stereo).
            channels: Number of channels.
            sample_rate: Sample rate.
        """
        try:
            import numpy as np
            arr = np.asarray(samples, dtype=np.float32)
            self.load_audio_clip(clip_id, arr.tobytes(), channels, sample_rate)
        except ImportError:
            log.error("numpy required for load_audio_clip_from_numpy")

    def set_arrangement(self, clips: List[Dict[str, Any]]):
        """Set the arrangement (which clips play where).

        Args:
            clips: List of dicts with keys:
                clip_id (str), track_index (int), start_beat (float),
                end_beat (float), offset_samples (int), gain (float)
        """
        ipc_clips = []
        for c in clips:
            ipc_clips.append({
                "clip_id": str(c.get("clip_id", "")),
                "track_index": int(c.get("track_index", 0)),
                "start_beat": float(c.get("start_beat", 0.0)),
                "end_beat": float(c.get("end_beat", 0.0)),
                "offset_samples": int(c.get("offset_samples", 0)),
                "gain": float(c.get("gain", 1.0)),
            })
        self.send_command({
            "cmd": "SetArrangement",
            "clips": ipc_clips,
        })

    def set_track_param_ring(self, track_index: int, param_type: int, value: float):
        """Send a parameter update via the lock-free ring buffer encoding.

        The param_id encodes track_index in the high 16 bits and
        param_type in the low 16 bits:
            0 = Volume, 1 = Pan, 2 = Mute, 3 = Solo

        This is sent as a regular SetTrackParam command; the Rust engine
        also supports the ring buffer for ultra-low-latency updates.
        """
        param_names = {0: "Volume", 1: "Pan", 2: "Mute", 3: "Solo"}
        param_name = param_names.get(param_type, "Volume")
        self.send_command({
            "cmd": "SetTrackParam",
            "track_index": int(track_index),
            "param": param_name,
            "value": float(value),
        })

    # --- IPC: MultiSample Instrument (Phase R6B) -------------------------

    def load_instrument(self, track_id: str, instrument_type: str,
                        instrument_id: str = ""):
        """Load an instrument on a track.

        Args:
            track_id: Track identifier.
            instrument_type: One of 'pro_sampler', 'multi_sample',
                'drum_machine', 'aeterna', 'fusion', 'bach_orgel', 'sf2'.
            instrument_id: Optional unique ID (auto-generated if empty).
        """
        self.send_command({
            "cmd": "LoadInstrument",
            "track_id": str(track_id),
            "instrument_type": str(instrument_type),
            "instrument_id": str(instrument_id),
        })

    def unload_instrument(self, track_id: str):
        """Unload an instrument from a track."""
        self.send_command({
            "cmd": "UnloadInstrument",
            "track_id": str(track_id),
        })

    def load_sample(self, track_id: str, wav_path: str,
                    root_note: int = 60, fine_tune: int = 0):
        """Load a sample into a ProSampler instrument."""
        self.send_command({
            "cmd": "LoadSample",
            "track_id": str(track_id),
            "wav_path": str(wav_path),
            "root_note": int(root_note),
            "fine_tune": int(fine_tune),
        })

    def add_sample_zone(self, track_id: str, wav_path: str,
                        root_note: int = 60,
                        key_lo: int = 0, key_hi: int = 127,
                        vel_lo: int = 0, vel_hi: int = 127,
                        gain: float = 0.8, pan: float = 0.0,
                        tune_semitones: float = 0.0,
                        tune_cents: float = 0.0,
                        rr_group: int = 0):
        """Add a sample zone to a MultiSample instrument.

        Args:
            track_id: Track with a multi_sample instrument loaded.
            wav_path: Path to the WAV file.
            root_note: MIDI note that plays at original pitch.
            key_lo/key_hi: MIDI key range (0–127).
            vel_lo/vel_hi: Velocity range (0–127).
            gain: Zone gain (0.0–1.0).
            pan: Zone pan (-1.0..1.0).
            tune_semitones: Coarse tuning in semitones.
            tune_cents: Fine tuning in cents.
            rr_group: Round-robin group (0 = none, 1+ = group).
        """
        self.send_command({
            "cmd": "AddSampleZone",
            "track_id": str(track_id),
            "wav_path": str(wav_path),
            "root_note": int(root_note),
            "key_lo": int(key_lo),
            "key_hi": int(key_hi),
            "vel_lo": int(vel_lo),
            "vel_hi": int(vel_hi),
            "gain": float(gain),
            "pan": float(pan),
            "tune_semitones": float(tune_semitones),
            "tune_cents": float(tune_cents),
            "rr_group": int(rr_group),
        })

    def remove_sample_zone(self, track_id: str, zone_id: int):
        """Remove a zone from a MultiSample instrument."""
        self.send_command({
            "cmd": "RemoveSampleZone",
            "track_id": str(track_id),
            "zone_id": int(zone_id),
        })

    def clear_all_zones(self, track_id: str):
        """Clear all zones from a MultiSample instrument."""
        self.send_command({
            "cmd": "ClearAllZones",
            "track_id": str(track_id),
        })

    def set_zone_filter(self, track_id: str, zone_id: int,
                        filter_type: str = "off",
                        cutoff_hz: float = 8000.0,
                        resonance: float = 0.707,
                        env_amount: float = 0.0):
        """Set per-zone filter parameters.

        Args:
            filter_type: 'off', 'lp', 'hp', 'bp'
        """
        self.send_command({
            "cmd": "SetZoneFilter",
            "track_id": str(track_id),
            "zone_id": int(zone_id),
            "filter_type": str(filter_type),
            "cutoff_hz": float(cutoff_hz),
            "resonance": float(resonance),
            "env_amount": float(env_amount),
        })

    def set_zone_envelope(self, track_id: str, zone_id: int,
                          env_type: str = "amp",
                          attack: float = 0.005, decay: float = 0.15,
                          sustain: float = 1.0, release: float = 0.2):
        """Set per-zone envelope (amp or filter).

        Args:
            env_type: 'amp' or 'filter'
        """
        self.send_command({
            "cmd": "SetZoneEnvelope",
            "track_id": str(track_id),
            "zone_id": int(zone_id),
            "env_type": str(env_type),
            "attack": float(attack),
            "decay": float(decay),
            "sustain": float(sustain),
            "release": float(release),
        })

    def set_zone_lfo(self, track_id: str, zone_id: int,
                     lfo_index: int = 0,
                     rate_hz: float = 1.0,
                     shape: str = "sine"):
        """Set per-zone LFO parameters.

        Args:
            lfo_index: 0 or 1.
            shape: 'sine', 'triangle', 'square', 'saw', 'sample_hold'
        """
        self.send_command({
            "cmd": "SetZoneLfo",
            "track_id": str(track_id),
            "zone_id": int(zone_id),
            "lfo_index": int(lfo_index),
            "rate_hz": float(rate_hz),
            "shape": str(shape),
        })

    def set_zone_mod_slot(self, track_id: str, zone_id: int,
                          slot_index: int = 0,
                          source: str = "none",
                          destination: str = "none",
                          amount: float = 0.0):
        """Set per-zone modulation routing.

        Args:
            source: 'none', 'lfo1', 'lfo2', 'env_amp', 'env_filter',
                    'velocity', 'key_track'
            destination: 'none', 'pitch', 'filter_cutoff', 'amp', 'pan'
            amount: -1.0 .. 1.0
        """
        self.send_command({
            "cmd": "SetZoneModSlot",
            "track_id": str(track_id),
            "zone_id": int(zone_id),
            "slot_index": int(slot_index),
            "source": str(source),
            "destination": str(destination),
            "amount": float(amount),
        })

    def auto_map_zones(self, track_id: str, mode: str = "chromatic",
                       base_note: int = 60,
                       wav_paths: Optional[List[str]] = None):
        """Auto-map WAV files to zones on a MultiSample instrument.

        Args:
            mode: 'chromatic', 'drum', 'velocity_layer'
            base_note: Starting MIDI note.
            wav_paths: List of WAV file paths.
        """
        self.send_command({
            "cmd": "AutoMapZones",
            "track_id": str(track_id),
            "mode": str(mode),
            "base_note": int(base_note),
            "wav_paths": list(wav_paths or []),
        })

    # --- IPC: DrumMachine Instrument (Phase R7A) -------------------------

    def load_drum_pad_sample(self, track_id: str, pad_index: int,
                             wav_path: str):
        """Load a sample onto a drum pad.

        Args:
            track_id: Track with a drum_machine instrument loaded.
            pad_index: Pad slot (0–127).
            wav_path: Path to the WAV file.
        """
        self.send_command({
            "cmd": "LoadDrumPadSample",
            "track_id": str(track_id),
            "pad_index": int(pad_index),
            "wav_path": str(wav_path),
        })

    def clear_drum_pad(self, track_id: str, pad_index: int):
        """Clear a drum pad."""
        self.send_command({
            "cmd": "ClearDrumPad",
            "track_id": str(track_id),
            "pad_index": int(pad_index),
        })

    def set_drum_pad_param(self, track_id: str, pad_index: int,
                           param_name: str, value: float):
        """Set a drum pad parameter.

        Args:
            param_name: 'gain', 'pan', 'tune', 'choke', 'play_mode'
            value: Parameter value (play_mode: 0=one_shot, 1=gate).
        """
        self.send_command({
            "cmd": "SetDrumPadParam",
            "track_id": str(track_id),
            "pad_index": int(pad_index),
            "param_name": str(param_name),
            "value": float(value),
        })

    def clear_all_drum_pads(self, track_id: str):
        """Clear all drum pads."""
        self.send_command({
            "cmd": "ClearAllDrumPads",
            "track_id": str(track_id),
        })

    def set_drum_base_note(self, track_id: str, base_note: int = 36):
        """Set drum machine base MIDI note (default 36 = GM kick)."""
        self.send_command({
            "cmd": "SetDrumBaseNote",
            "track_id": str(track_id),
            "base_note": int(base_note),
        })

    def set_drum_pad_output(self, track_id: str, pad_index: int,
                            output_index: int = 0):
        """Set drum pad output routing (multi-output).

        Args:
            pad_index: Pad slot (0–127).
            output_index: Output bus (0=main, 1–15=aux).
        """
        self.send_command({
            "cmd": "SetDrumPadOutput",
            "track_id": str(track_id),
            "pad_index": int(pad_index),
            "output_index": int(output_index),
        })

    def set_drum_multi_output(self, track_id: str, enabled: bool = False,
                              output_count: int = 1):
        """Enable/disable drum machine multi-output.

        Args:
            enabled: Whether multi-output routing is active.
            output_count: Number of output buses (1–16).
        """
        self.send_command({
            "cmd": "SetDrumMultiOutput",
            "track_id": str(track_id),
            "enabled": bool(enabled),
            "output_count": int(output_count),
        })

    # --- External Plugin Hosting (Phase P7) --------------------------------

    def scan_plugins(self):
        """Request a full scan of all installed plugins (VST3 + CLAP + LV2).

        Results come back as a 'PluginScanResult' event.
        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({"cmd": "ScanPlugins"})

    def load_plugin(self, track_id: str, slot_index: int,
                    plugin_path: str, plugin_format: str,
                    plugin_id: str = ""):
        """Load an external plugin on a track.

        Args:
            track_id: Track ID string.
            slot_index: FX slot index (0-7).
            plugin_path: Path to .vst3 bundle, .clap file, or "" for LV2.
            plugin_format: "vst3", "clap", or "lv2".
            plugin_id: VST3 class_id, CLAP plugin_id, or LV2 URI.
                        Empty string = load first plugin in bundle.

        Results come back as 'PluginLoaded' event on success,
        or 'Error' event on failure.
        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({
            "cmd": "LoadPlugin",
            "track_id": str(track_id),
            "slot_index": int(slot_index),
            "plugin_path": str(plugin_path),
            "plugin_format": str(plugin_format),
            "plugin_id": str(plugin_id),
        })

    def unload_plugin(self, track_id: str, slot_index: int):
        """Unload a plugin from a track slot.

        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({
            "cmd": "UnloadPlugin",
            "track_id": str(track_id),
            "slot_index": int(slot_index),
        })

    def set_plugin_param(self, track_id: str, slot_index: int,
                         param_index: int, value: float):
        """Set an external plugin parameter.

        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({
            "cmd": "SetPluginParam",
            "track_id": str(track_id),
            "slot_index": int(slot_index),
            "param_index": int(param_index),
            "value": float(value),
        })

    def save_plugin_state(self, track_id: str, slot_index: int):
        """Request plugin state blob (comes back as PluginState event).

        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({
            "cmd": "SavePluginState",
            "track_id": str(track_id),
            "slot_index": int(slot_index),
        })

    def load_plugin_state(self, track_id: str, slot_index: int,
                          state_b64: str):
        """Load a plugin state from a base64-encoded blob.

        v0.0.20.718: Phase P7 Integration.
        """
        self.send_command({
            "cmd": "LoadPluginState",
            "track_id": str(track_id),
            "slot_index": int(slot_index),
            "state_b64": str(state_b64),
        })

    # --- IPC: Receive Events (background thread) --------------------------

    def _reader_loop(self):
        """Background thread: read events from engine, dispatch via signals.

        v0.0.20.725: Better error categorization + graceful disconnect handling.
        """
        log.info("IPC reader loop started")
        consecutive_errors = 0
        max_consecutive_errors = 5
        while self._running and self._socket:
            try:
                payload = _recv_frame(self._socket)
                if payload is None:
                    if not self._shutting_down:
                        log.info("Engine disconnected (EOF)")
                    break
                event = _decode_frame(payload)
                self._dispatch_event(event)
                consecutive_errors = 0  # Reset on success
            except (socket.error, OSError) as e:
                if self._shutting_down or not self._running:
                    break
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log.error("IPC reader: %d consecutive errors, giving up: %s",
                              consecutive_errors, e)
                    break
                log.warning("IPC reader error (%d/%d): %s",
                            consecutive_errors, max_consecutive_errors, e)
                import time
                time.sleep(0.1)  # Brief pause before retry
            except Exception as e:
                if self._shutting_down or not self._running:
                    break
                log.error("Event dispatch error: %s", e)

        self._connected = False
        if not self._shutting_down:
            log.info("IPC reader loop ended (engine disconnected)")
        else:
            log.info("IPC reader loop ended (shutdown)")

    def _dispatch_event(self, event: dict):
        """Dispatch a decoded event to the appropriate Qt signal.

        v0.0.20.666: Guarded against deleted C++ objects and shutdown state
        to prevent error-flood that freezes the GUI.
        """
        # Safety: do not emit signals during/after shutdown
        if self._shutting_down or not self._running:
            return

        evt_type = event.get("evt", "")

        try:
            if evt_type == "PlayheadPosition":
                if _QT_AVAILABLE:
                    self.playhead_changed.emit(
                        event.get("beat", 0.0),
                        event.get("sample_position", 0),
                        event.get("is_playing", False),
                    )

            elif evt_type == "TransportState":
                if _QT_AVAILABLE:
                    self.transport_state_changed.emit(
                        event.get("is_playing", False),
                        event.get("beat", 0.0),
                    )

            elif evt_type == "MasterMeterLevel":
                if _QT_AVAILABLE:
                    self.master_meter_changed.emit(
                        event.get("peak_l", 0.0),
                        event.get("peak_r", 0.0),
                        event.get("rms_l", 0.0),
                        event.get("rms_r", 0.0),
                    )

            elif evt_type == "MeterLevels":
                levels = event.get("levels", [])
                if _QT_AVAILABLE and levels:
                    parsed = [
                        (
                            lv.get("track_index", 0),
                            lv.get("peak_l", 0.0),
                            lv.get("peak_r", 0.0),
                            lv.get("rms_l", 0.0),
                            lv.get("rms_r", 0.0),
                        )
                        for lv in levels
                    ]
                    self.track_meters_changed.emit(parsed)

            elif evt_type == "Ready":
                log.info(
                    "Engine ready: sr=%s, buf=%s, dev='%s'",
                    event.get("sample_rate"),
                    event.get("buffer_size"),
                    event.get("device_name"),
                )
                if _QT_AVAILABLE:
                    self.engine_ready.emit(
                        event.get("sample_rate", 44100),
                        event.get("buffer_size", 512),
                        event.get("device_name", ""),
                    )

            elif evt_type == "Pong":
                self._last_pong_time = time.monotonic()
                self._last_cpu_load = float(event.get("cpu_load", 0.0))
                self._last_render_time_us = float(event.get("render_time_us", 0.0))
                self._last_xrun_count = int(event.get("xrun_count", 0))
                if _QT_AVAILABLE:
                    self.engine_pong.emit(
                        event.get("seq", 0),
                        event.get("cpu_load", 0.0),
                        event.get("xrun_count", 0),
                    )

            elif evt_type == "Error":
                log.error("Engine error [%d]: %s", event.get("code", 0), event.get("message", ""))
                if _QT_AVAILABLE:
                    self.engine_error.emit(
                        event.get("code", 0),
                        event.get("message", ""),
                    )

            elif evt_type == "PluginCrash":
                log.error(
                    "Plugin crash: track=%s slot=%d: %s",
                    event.get("track_id"),
                    event.get("slot_index", 0),
                    event.get("message", ""),
                )
                if _QT_AVAILABLE:
                    self.plugin_crashed.emit(
                        event.get("track_id", ""),
                        event.get("slot_index", 0),
                        event.get("message", ""),
                    )

            elif evt_type == "PluginState":
                # Plugin state is handled by specific callbacks
                log.debug(
                    "Plugin state received: track=%s slot=%d",
                    event.get("track_id"),
                    event.get("slot_index", 0),
                )

            elif evt_type == "PluginScanResult":
                plugins = event.get("plugins", [])
                scan_ms = event.get("scan_time_ms", 0)
                errors = event.get("errors", [])
                log.info(
                    "Plugin scan complete: %d plugins in %dms (%d errors)",
                    len(plugins), scan_ms, len(errors),
                )
                if _QT_AVAILABLE:
                    self.plugin_scan_result.emit(plugins, scan_ms, errors)

            elif evt_type == "PluginLoaded":
                log.info(
                    "Plugin loaded: %s '%s' on track=%s slot=%d (%d params, %d lat)",
                    event.get("plugin_format", ""),
                    event.get("plugin_name", ""),
                    event.get("track_id", ""),
                    event.get("slot_index", 0),
                    event.get("param_count", 0),
                    event.get("latency_samples", 0),
                )
                if _QT_AVAILABLE:
                    self.plugin_loaded.emit(
                        event.get("track_id", ""),
                        event.get("slot_index", 0),
                        event.get("plugin_name", ""),
                        event.get("plugin_format", ""),
                        event.get("param_count", 0),
                        event.get("latency_samples", 0),
                    )

            elif evt_type == "ShuttingDown":
                log.info("Engine confirmed shutdown")
                if _QT_AVAILABLE:
                    self.engine_shutdown.emit()

            else:
                log.debug("Unknown event type: %s", evt_type)

        except RuntimeError as e:
            # v0.0.20.666: "wrapped C/C++ object has been deleted" — stop immediately
            if "deleted" in str(e):
                self._shutting_down = True
                self._running = False
                log.warning("RustEngineBridge Qt object deleted — stopping event dispatch")
            else:
                log.error("Error dispatching event '%s': %s", evt_type, e)
        except Exception as e:
            log.error("Error dispatching event '%s': %s", evt_type, e)

    # --- Health Check -----------------------------------------------------

    def _health_check(self):
        """Periodic health check (called from Qt timer).

        v0.0.20.725: Added auto-reconnect on unexpected engine death.
        """
        # v0.0.20.722: Only check process health if WE started the process.
        if self._process is not None:
            if self._process.poll() is not None:
                exit_code = self._process.returncode
                log.warning("Engine process died unexpectedly! (exit code: %s)", exit_code)
                self._connected = False
                self._running = False

                # v0.0.20.725: Try auto-reconnect once
                reconnect_count = getattr(self, '_reconnect_count', 0)
                if reconnect_count < 1 and not self._shutting_down:
                    self._reconnect_count = reconnect_count + 1
                    log.info("Attempting auto-reconnect (%d/1)...", self._reconnect_count)
                    try:
                        self._process = None
                        success = self.start_engine(
                            self._socket_path,
                            self._sample_rate,
                            self._buffer_size,
                        )
                        if success:
                            log.info("Auto-reconnect succeeded!")
                            if _QT_AVAILABLE:
                                self.engine_error.emit(0, "Engine reconnected after crash")
                            return
                    except Exception as e:
                        log.error("Auto-reconnect failed: %s", e)

                if _QT_AVAILABLE:
                    self.engine_error.emit(
                        9999,
                        f"Engine process died unexpectedly (exit {exit_code})",
                    )
                return
        elif not self._connected:
            return

        # Send ping
        self.ping()

    # --- Feature Flag Integration -----------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check if the Rust engine is available (binary exists)."""
        return _find_engine_binary() is not None

    @staticmethod
    def is_enabled() -> bool:
        """Check if the Rust engine is available.

        v0.0.20.722: Auto-detect — engine binary OR running socket = enabled.
        USE_RUST_ENGINE=0 to explicitly disable.
        """
        env = os.environ.get("USE_RUST_ENGINE", "").lower()
        if env in ("0", "false", "no"):
            return False
        if env in ("1", "true", "yes"):
            return True
        # Auto-detect: check if socket exists (engine already running)
        if os.path.exists(DEFAULT_SOCKET_PATH):
            return True
        # Auto-detect: check if binary exists
        import pathlib
        for p in [
            pathlib.Path(__file__).parent.parent.parent / "pydaw_engine" / "target" / "release" / "pydaw_engine",
            pathlib.Path.home() / "pydaw_engine" / "target" / "release" / "pydaw_engine",
        ]:
            if p.exists():
                return True
        return False
