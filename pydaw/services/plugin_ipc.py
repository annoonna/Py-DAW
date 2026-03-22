# -*- coding: utf-8 -*-
"""Plugin IPC — MessagePack-based parameter & control protocol.

v0.0.20.700 — Phase P1A

Communication between main process and plugin worker subprocesses
via Unix Domain Sockets + MessagePack (fast binary serialization).

Protocol:
    [4 bytes: message length (uint32 LE)] [N bytes: msgpack payload]

Message types:
    Main → Worker:
        SetParam      {cmd: "set_param", param_id: str, value: float}
        GetState      {cmd: "get_state"}
        LoadState     {cmd: "load_state", state_b64: str}
        Bypass        {cmd: "bypass", enabled: bool}
        Shutdown      {cmd: "shutdown"}
        Ping          {cmd: "ping", seq: int}
        Configure     {cmd: "configure", sample_rate: int, block_size: int}
        ShowEditor    {cmd: "show_editor"}
        HideEditor    {cmd: "hide_editor"}

    Worker → Main:
        StateBlob     {evt: "state", state_b64: str}
        ParamChanged  {evt: "param_changed", param_id: str, value: float}
        Pong          {evt: "pong", seq: int}
        Error         {evt: "error", message: str}
        Crashed       {evt: "crashed", message: str}
        Ready         {evt: "ready", plugin_name: str, param_count: int}

Dependencies:
    - msgpack (pip install msgpack)
    - socket (stdlib)
    - struct (stdlib)
"""
from __future__ import annotations

import base64
import logging
import os
import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

try:
    import msgpack
except ImportError:
    msgpack = None  # type: ignore

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEADER_SIZE = 4       # uint32 LE length prefix
_MAX_MSG_SIZE = 4 * 1024 * 1024  # 4 MB max message (for state blobs)
_RECV_TIMEOUT = 0.1    # seconds, for non-blocking recv
_CONNECT_TIMEOUT = 5.0 # seconds, for initial connection


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _pack_msg(obj: dict) -> bytes:
    """Pack a dict into a length-prefixed msgpack message."""
    payload = msgpack.packb(obj, use_bin_type=True)
    return struct.pack('<I', len(payload)) + payload


def _unpack_msg(data: bytes) -> Optional[dict]:
    """Unpack a msgpack payload into a dict."""
    try:
        return msgpack.unpackb(data, raw=False)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IPC Server (runs in worker subprocess)
# ---------------------------------------------------------------------------

class PluginIPCServer:
    """IPC server running inside the plugin worker subprocess.

    Listens on a Unix Domain Socket for commands from the main process.
    Sends events (state changes, param updates, heartbeat) back.

    Usage in worker:
        server = PluginIPCServer(socket_path)
        server.start()
        server.set_message_handler(my_handler)
        # ... worker loop ...
        server.send_event({"evt": "param_changed", "param_id": "cutoff", "value": 0.5})
        server.stop()
    """

    def __init__(self, socket_path: str):
        self._path = socket_path
        self._sock: Optional[socket.socket] = None
        self._client: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._handler: Optional[Callable[[dict], Optional[dict]]] = None
        self._lock = threading.Lock()

    def set_message_handler(self, handler: Callable[[dict], Optional[dict]]) -> None:
        """Set callback for incoming commands. Return dict to send response."""
        self._handler = handler

    def start(self) -> bool:
        """Start listening for connections."""
        try:
            # Clean up stale socket
            try:
                os.unlink(self._path)
            except FileNotFoundError:
                pass

            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.bind(self._path)
            self._sock.listen(1)
            self._sock.settimeout(1.0)
            self._running = True

            self._thread = threading.Thread(
                target=self._accept_loop, daemon=True,
                name=f"plugin_ipc_server")
            self._thread.start()
            return True
        except Exception as e:
            _log.error("PluginIPCServer.start failed: %s", e)
            return False

    def _accept_loop(self) -> None:
        """Accept one client connection, then read commands."""
        while self._running:
            try:
                self._client, _ = self._sock.accept()
                self._client.settimeout(_RECV_TIMEOUT)
                self._read_loop()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    _log.debug("Accept error: %s", e)

    def _read_loop(self) -> None:
        """Read commands from connected client."""
        buf = bytearray()
        while self._running and self._client:
            try:
                data = self._client.recv(65536)
                if not data:
                    break  # client disconnected
                buf.extend(data)

                # Process complete messages
                while len(buf) >= _HEADER_SIZE:
                    msg_len = struct.unpack('<I', buf[:_HEADER_SIZE])[0]
                    if msg_len > _MAX_MSG_SIZE:
                        _log.error("Message too large: %d", msg_len)
                        buf.clear()
                        break
                    if len(buf) < _HEADER_SIZE + msg_len:
                        break  # incomplete message
                    payload = bytes(buf[_HEADER_SIZE:_HEADER_SIZE + msg_len])
                    del buf[:_HEADER_SIZE + msg_len]

                    msg = _unpack_msg(payload)
                    if msg and self._handler:
                        try:
                            response = self._handler(msg)
                            if response:
                                self.send_event(response)
                        except Exception as e:
                            _log.error("Handler error: %s", e)

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    _log.debug("Read error: %s", e)
                break

    def send_event(self, event: dict) -> bool:
        """Send an event to the main process."""
        with self._lock:
            if self._client is None:
                return False
            try:
                self._client.sendall(_pack_msg(event))
                return True
            except Exception:
                return False

    def stop(self) -> None:
        """Stop the server and clean up."""
        self._running = False
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        try:
            os.unlink(self._path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# IPC Client (runs in main process)
# ---------------------------------------------------------------------------

class PluginIPCClient:
    """IPC client in the main process, connects to a worker's socket.

    Sends commands (set_param, bypass, shutdown, etc.) to the worker.
    Receives events (state_blob, param_changed, pong) from the worker.

    Usage:
        client = PluginIPCClient(socket_path)
        client.connect()
        client.set_event_handler(my_handler)
        client.send_command({"cmd": "set_param", "param_id": "gain", "value": 0.8})
        client.disconnect()
    """

    def __init__(self, socket_path: str):
        self._path = socket_path
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._handler: Optional[Callable[[dict], None]] = None
        self._lock = threading.Lock()
        self._last_pong_seq: int = 0
        self._last_pong_time: float = 0.0

    def set_event_handler(self, handler: Callable[[dict], None]) -> None:
        """Set callback for incoming events from the worker."""
        self._handler = handler

    def connect(self, timeout: float = _CONNECT_TIMEOUT) -> bool:
        """Connect to the worker's IPC socket."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.settimeout(_RECV_TIMEOUT)
                self._sock.connect(self._path)
                self._running = True

                # Start reader thread
                self._thread = threading.Thread(
                    target=self._read_loop, daemon=True,
                    name=f"plugin_ipc_client")
                self._thread.start()
                return True
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.05)
            except Exception as e:
                _log.debug("Connect attempt failed: %s", e)
                time.sleep(0.05)
        return False

    def _read_loop(self) -> None:
        """Read events from the worker."""
        buf = bytearray()
        while self._running and self._sock:
            try:
                data = self._sock.recv(65536)
                if not data:
                    break
                buf.extend(data)

                while len(buf) >= _HEADER_SIZE:
                    msg_len = struct.unpack('<I', buf[:_HEADER_SIZE])[0]
                    if msg_len > _MAX_MSG_SIZE:
                        buf.clear()
                        break
                    if len(buf) < _HEADER_SIZE + msg_len:
                        break
                    payload = bytes(buf[_HEADER_SIZE:_HEADER_SIZE + msg_len])
                    del buf[:_HEADER_SIZE + msg_len]

                    msg = _unpack_msg(payload)
                    if msg:
                        # Handle pong internally
                        if msg.get("evt") == "pong":
                            self._last_pong_seq = msg.get("seq", 0)
                            self._last_pong_time = time.monotonic()
                        if self._handler:
                            try:
                                self._handler(msg)
                            except Exception:
                                pass

            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    break

    def send_command(self, cmd: dict) -> bool:
        """Send a command to the worker."""
        with self._lock:
            if self._sock is None:
                return False
            try:
                self._sock.sendall(_pack_msg(cmd))
                return True
            except Exception:
                return False

    def set_param(self, param_id: str, value: float) -> bool:
        """Convenience: send SetParam command."""
        return self.send_command({
            "cmd": "set_param", "param_id": str(param_id), "value": float(value)
        })

    def set_bypass(self, enabled: bool) -> bool:
        """Convenience: send Bypass command."""
        return self.send_command({"cmd": "bypass", "enabled": bool(enabled)})

    def request_state(self) -> bool:
        """Convenience: request plugin state blob."""
        return self.send_command({"cmd": "get_state"})

    def load_state(self, state_b64: str) -> bool:
        """Convenience: load plugin state from base64."""
        return self.send_command({"cmd": "load_state", "state_b64": str(state_b64)})

    def ping(self, seq: int) -> bool:
        """Send heartbeat ping."""
        return self.send_command({"cmd": "ping", "seq": int(seq)})

    def shutdown(self) -> bool:
        """Tell the worker to shut down cleanly."""
        return self.send_command({"cmd": "shutdown"})

    # v0.0.20.705: MIDI commands for instrument workers (P2C)

    def send_note_on(self, pitch: int, velocity: int = 100) -> bool:
        """Send MIDI note-on to instrument worker."""
        return self.send_command({
            "cmd": "note_on",
            "pitch": max(0, min(127, int(pitch))),
            "velocity": max(1, min(127, int(velocity))),
        })

    def send_note_off(self, pitch: int = -1) -> bool:
        """Send MIDI note-off to instrument worker.

        pitch >= 0: specific note off.
        pitch < 0: all notes off.
        """
        return self.send_command({"cmd": "note_off", "pitch": int(pitch)})

    def send_all_notes_off(self) -> bool:
        """Send MIDI panic (all notes off) to instrument worker."""
        return self.send_command({"cmd": "all_notes_off"})

    def send_midi_events(self, events: list) -> bool:
        """Send batch of MIDI events: [[status, data1, data2], ...]."""
        return self.send_command({"cmd": "midi", "events": events})

    # v0.0.20.705: Editor commands for GUI support (P2B)

    def show_editor(self) -> bool:
        """Tell worker to open plugin editor window."""
        return self.send_command({"cmd": "show_editor"})

    def hide_editor(self) -> bool:
        """Tell worker to close plugin editor window."""
        return self.send_command({"cmd": "hide_editor"})

    def is_responsive(self, timeout_sec: float = 3.0) -> bool:
        """Check if the worker responded to the last ping within timeout."""
        return (time.monotonic() - self._last_pong_time) < timeout_sec

    # v0.0.20.709: P2C — Plugin Latency Report via IPC
    def request_latency(self) -> bool:
        """Request plugin processing latency from worker.

        Worker responds with {evt: "latency", samples: int}.
        """
        return self.send_command({"cmd": "get_latency"})

    def disconnect(self) -> None:
        """Disconnect from the worker."""
        self._running = False
        try:
            if self._sock:
                self._sock.close()
                self._sock = None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Ping-Pong Audio Buffer (improved SharedAudioBuffer)
# ---------------------------------------------------------------------------

class PingPongAudioBuffer:
    """Double-buffered shared memory audio transport.

    Uses two buffers (A and B). While the worker processes buffer A,
    the main process writes to buffer B. Then they swap.

    Layout per buffer:
        [4 bytes: frame_count (uint32)]
        [4 bytes: flags (uint32) — bit 0: ready, bit 1: which buffer]
        [max_frames * channels * 4 bytes: float32 audio]

    Total: 2 × (8 + max_frames × channels × 4) bytes
    """

    def __init__(self, name: str = "", max_frames: int = 8192, channels: int = 2):
        self.name = name
        self.max_frames = max_frames
        self.channels = channels
        self._mmap = None
        self._buf_size = 8 + max_frames * channels * 4  # per buffer
        self._total_size = self._buf_size * 2  # double buffer
        self._current_write = 0  # 0 or 1

    def create(self) -> bool:
        """Create the shared memory (call from main process)."""
        try:
            import mmap
            self._mmap = mmap.mmap(-1, self._total_size)
            self._mmap[:self._total_size] = b'\x00' * self._total_size
            return True
        except Exception as e:
            _log.error("PingPongAudioBuffer.create failed: %s", e)
            return False

    def _buf_offset(self, buf_idx: int) -> int:
        return buf_idx * self._buf_size

    def write(self, audio, frames: int) -> bool:
        """Write audio block to the current write buffer.

        audio: numpy array, shape (frames, channels) or flat
        Returns True on success.
        """
        if self._mmap is None:
            return False
        try:
            import numpy as np
            n = min(frames, self.max_frames)
            arr = np.asarray(audio, dtype=np.float32)
            if arr.ndim == 1:
                # Mono or interleaved → reshape
                if len(arr) >= n * self.channels:
                    arr = arr[:n * self.channels]
                else:
                    arr = arr[:n]
            elif arr.ndim == 2:
                arr = arr[:n].flatten()
            else:
                return False

            data = arr.astype(np.float32).tobytes()
            off = self._buf_offset(self._current_write)

            # Write frame count
            self._mmap[off:off + 4] = struct.pack('<I', n)
            # Write flags (ready=1, buf_idx)
            self._mmap[off + 4:off + 8] = struct.pack('<I', 1 | (self._current_write << 1))
            # Write audio data
            self._mmap[off + 8:off + 8 + len(data)] = data

            # Swap write buffer
            self._current_write = 1 - self._current_write
            return True
        except Exception as e:
            _log.debug("PingPongAudioBuffer.write error: %s", e)
            return False

    def read(self, buf_idx: int, max_frames: int = 0) -> Optional[Any]:
        """Read audio from a specific buffer.

        Returns numpy array (frames, channels) or None.
        """
        if self._mmap is None:
            return None
        try:
            import numpy as np
            off = self._buf_offset(buf_idx)
            n = struct.unpack('<I', self._mmap[off:off + 4])[0]
            flags = struct.unpack('<I', self._mmap[off + 4:off + 8])[0]

            if not (flags & 1):  # not ready
                return None

            n = min(n, max_frames or self.max_frames, self.max_frames)
            if n == 0:
                return None

            byte_count = n * self.channels * 4
            raw = bytes(self._mmap[off + 8:off + 8 + byte_count])
            audio = np.frombuffer(raw, dtype=np.float32).reshape(n, self.channels).copy()

            # Clear ready flag
            self._mmap[off + 4:off + 8] = struct.pack('<I', 0)
            return audio
        except Exception:
            return None

    def read_latest(self, max_frames: int = 0) -> Optional[Any]:
        """Read from whichever buffer has data ready (prefer newest)."""
        # Try the buffer that was most recently written
        newest = 1 - self._current_write
        result = self.read(newest, max_frames)
        if result is not None:
            return result
        # Fallback to the other
        return self.read(self._current_write, max_frames)

    def close(self) -> None:
        """Release shared memory."""
        try:
            if self._mmap is not None:
                self._mmap.close()
                self._mmap = None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Worker-side audio handler convenience
# ---------------------------------------------------------------------------

class WorkerAudioHandler:
    """Convenience wrapper for the worker side of audio IPC.

    Reads input audio from shared memory, provides it to the plugin,
    writes processed output back.
    """

    def __init__(self, input_buf: PingPongAudioBuffer, output_buf: PingPongAudioBuffer):
        self.input_buf = input_buf
        self.output_buf = output_buf
        self._block_size = input_buf.max_frames

    def read_input(self) -> Optional[Any]:
        """Read input audio (non-blocking). Returns numpy array or None."""
        return self.input_buf.read_latest(self._block_size)

    def write_output(self, audio, frames: int) -> bool:
        """Write processed audio back to main process."""
        return self.output_buf.write(audio, frames)

    def write_silence(self, frames: int) -> bool:
        """Write silence (for error recovery)."""
        try:
            import numpy as np
            silence = np.zeros((frames, self.input_buf.channels), dtype=np.float32)
            return self.output_buf.write(silence, frames)
        except Exception:
            return False
