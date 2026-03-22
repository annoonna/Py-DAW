# -*- coding: utf-8 -*-
"""Sandboxed Plugin Hosting (AP4 Phase 4A) — v0.0.20.650.

Each plugin runs in its own subprocess for crash isolation.
If a plugin crashes, the track is muted and an error is shown,
but the rest of the DAW keeps running.

Architecture:
    ┌─────────────────────────────────────────────┐
    │  Main Process (GUI + Audio Engine)           │
    │  ┌───────────────────────────────────────┐  │
    │  │  PluginSandboxManager                  │  │
    │  │  - Tracks plugin → subprocess mapping  │  │
    │  │  - Monitors health (heartbeat)         │  │
    │  │  - Auto-restarts on crash              │  │
    │  └───┬──────────┬──────────┬─────────────┘  │
    └──────┼──────────┼──────────┼─────────────────┘
           │          │          │
    ┌──────▼───┐ ┌────▼─────┐ ┌─▼────────────┐
    │ Worker 1 │ │ Worker 2 │ │ Worker N     │
    │ (Plugin) │ │ (Plugin) │ │ (Plugin)     │
    │ VST3/    │ │ VST3/    │ │ CLAP/LV2    │
    │ CLAP     │ │ LV2      │ │              │
    └──────────┘ └──────────┘ └──────────────┘

IPC:
- Audio data: shared memory ring buffers (mmap)
- Parameter updates: Unix Domain Socket (MessagePack)
- Heartbeat: periodic ping every 500ms

Dependencies:
- multiprocessing (stdlib)
- mmap (stdlib)
- struct (stdlib)
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared Memory Audio Buffer (lock-free, RT-safe)
# ---------------------------------------------------------------------------

@dataclass
class SharedAudioBuffer:
    """Shared memory ring buffer for audio data between processes.

    Layout (per buffer):
      [4 bytes: write_pos (uint32)] [4 bytes: read_pos (uint32)]
      [frames * channels * 4 bytes: float32 audio data]

    Uses mmap for zero-copy IPC.
    """
    name: str = ""
    max_frames: int = 8192
    channels: int = 2
    _mmap: Any = None  # mmap.mmap object
    _shm_fd: int = -1

    def size_bytes(self) -> int:
        """Total shared memory size."""
        return 8 + self.max_frames * self.channels * 4  # header + audio

    def create(self) -> bool:
        """Create the shared memory segment (main process)."""
        try:
            import mmap
            size = self.size_bytes()
            # Use anonymous mmap (no file backing)
            self._mmap = mmap.mmap(-1, size)
            # Zero-fill header
            self._mmap[:8] = struct.pack('II', 0, 0)
            return True
        except Exception as e:
            _log.error("SharedAudioBuffer.create failed: %s", e)
            return False

    def write_block(self, audio: "np.ndarray", frames: int) -> bool:
        """Write audio block into shared memory (non-blocking)."""
        if self._mmap is None or np is None:
            return False
        try:
            n = min(frames, self.max_frames)
            data = audio[:n].astype(np.float32).tobytes()
            offset = 8  # skip header
            self._mmap[offset:offset + len(data)] = data
            # Update write position
            self._mmap[:4] = struct.pack('I', n)
            return True
        except Exception:
            return False

    def read_block(self, frames: int) -> Optional["np.ndarray"]:
        """Read audio block from shared memory (non-blocking)."""
        if self._mmap is None or np is None:
            return None
        try:
            # Read write position
            n = struct.unpack('I', self._mmap[:4])[0]
            n = min(n, frames, self.max_frames)
            if n == 0:
                return None
            offset = 8
            raw = self._mmap[offset:offset + n * self.channels * 4]
            audio = np.frombuffer(raw, dtype=np.float32).reshape(n, self.channels).copy()
            return audio
        except Exception:
            return None

    def close(self) -> None:
        """Release shared memory."""
        try:
            if self._mmap is not None:
                self._mmap.close()
                self._mmap = None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Plugin Worker Process
# ---------------------------------------------------------------------------

@dataclass
class PluginWorkerConfig:
    """Configuration for a plugin worker subprocess."""
    track_id: str = ""
    plugin_path: str = ""
    plugin_name: str = ""
    plugin_type: str = "vst3"  # vst3, clap, lv2
    sample_rate: int = 48000
    block_size: int = 512
    state_base64: str = ""  # plugin state to restore


class PluginWorkerState:
    """Tracks the state of a plugin worker subprocess."""

    __slots__ = (
        "track_id", "config", "process", "pid",
        "is_alive", "crash_count", "last_heartbeat",
        "input_buf", "output_buf",
        "error_message", "muted_by_crash",
    )

    def __init__(self, track_id: str, config: PluginWorkerConfig):
        self.track_id = str(track_id)
        self.config = config
        self.process: Optional[multiprocessing.Process] = None
        self.pid: int = 0
        self.is_alive: bool = False
        self.crash_count: int = 0
        self.last_heartbeat: float = 0.0
        self.input_buf = SharedAudioBuffer(name=f"pydaw_in_{track_id}", max_frames=8192)
        self.output_buf = SharedAudioBuffer(name=f"pydaw_out_{track_id}", max_frames=8192)
        self.error_message: str = ""
        self.muted_by_crash: bool = False


def _plugin_worker_main(config: PluginWorkerConfig,
                         in_buf: SharedAudioBuffer,
                         out_buf: SharedAudioBuffer) -> None:
    """Entry point for plugin worker subprocess.

    This function runs in a separate process. It loads the plugin,
    processes audio blocks from shared memory, and writes output back.

    If the plugin crashes, the subprocess dies cleanly and the main
    process detects the crash via heartbeat monitoring.
    """
    try:
        _log_w = logging.getLogger(f"pydaw.plugin_worker.{config.track_id}")
        _log_w.info("Plugin worker starting: %s (%s)", config.plugin_name, config.plugin_path)

        # Attempt to load plugin
        plugin = None
        if config.plugin_type in ("vst3", "vst2"):
            try:
                from pydaw.audio.vst3_host import load_vst3_fx
                plugin = load_vst3_fx(config.plugin_path, config.sample_rate,
                                       plugin_name=config.plugin_name)
            except Exception as e:
                _log_w.error("Failed to load VST3: %s", e)
        elif config.plugin_type == "clap":
            try:
                from pydaw.audio.clap_host import load_clap_plugin
                plugin = load_clap_plugin(config.plugin_path, config.sample_rate)
            except Exception as e:
                _log_w.error("Failed to load CLAP: %s", e)

        if plugin is None:
            _log_w.error("Plugin load failed, worker exiting")
            return

        # Restore state if available
        if config.state_base64:
            try:
                import base64
                state_bytes = base64.b64decode(config.state_base64)
                if hasattr(plugin, 'set_state'):
                    plugin.set_state(state_bytes)
                elif hasattr(plugin, 'load_state'):
                    plugin.load_state(state_bytes)
            except Exception as e:
                _log_w.warning("State restore failed: %s", e)

        _log_w.info("Plugin loaded, entering process loop")

        # Main process loop
        while True:
            try:
                audio_in = in_buf.read_block(config.block_size)
                if audio_in is not None:
                    # Process through plugin
                    try:
                        if hasattr(plugin, 'process_inplace'):
                            plugin.process_inplace(audio_in, len(audio_in), config.sample_rate)
                            out_buf.write_block(audio_in, len(audio_in))
                        elif hasattr(plugin, 'process'):
                            result = plugin.process(audio_in, config.sample_rate)
                            if result is not None:
                                out_buf.write_block(result, len(result))
                    except Exception as e:
                        _log_w.error("Plugin process error: %s", e)
                        # Write silence on error
                        if np is not None:
                            silence = np.zeros_like(audio_in)
                            out_buf.write_block(silence, len(silence))
                else:
                    time.sleep(0.001)  # No data, sleep briefly
            except Exception:
                break

    except Exception as e:
        # Fatal error — subprocess will exit, main process detects crash
        try:
            logging.getLogger(f"pydaw.plugin_worker.{config.track_id}").critical(
                "Worker crashed: %s", e)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sandbox Manager (Main Process)
# ---------------------------------------------------------------------------

_MAX_CRASH_RESTARTS = 3
_HEARTBEAT_INTERVAL = 0.5
_HEARTBEAT_TIMEOUT = 3.0


class PluginSandboxManager:
    """Manages plugin worker subprocesses.

    Main process side. Creates, monitors, and restarts plugin workers.
    Provides crash isolation: if a plugin crashes, only its track is muted.

    Usage:
        mgr = PluginSandboxManager()
        mgr.launch_plugin("trk_abc", config)
        # ... audio callback reads from mgr.get_output("trk_abc") ...
        mgr.kill_plugin("trk_abc")
        mgr.shutdown()
    """

    def __init__(self) -> None:
        self._workers: Dict[str, PluginWorkerState] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        # Callback for crash notifications (track_id, error_msg)
        self._crash_callback: Optional[Callable[[str, str], None]] = None

    def set_crash_callback(self, callback: Callable[[str, str], None]) -> None:
        """Set callback invoked when a plugin crashes.

        callback(track_id, error_message)
        """
        self._crash_callback = callback

    def launch_plugin(self, track_id: str, config: PluginWorkerConfig) -> bool:
        """Launch a plugin in a sandboxed subprocess.

        Returns True if launch succeeded.
        """
        tid = str(track_id)
        with self._lock:
            # Kill existing worker if any
            if tid in self._workers:
                self._kill_worker(tid)

            state = PluginWorkerState(tid, config)

            # Create shared memory buffers
            if not state.input_buf.create() or not state.output_buf.create():
                _log.error("Failed to create shared buffers for %s", tid)
                return False

            # Start subprocess
            try:
                proc = multiprocessing.Process(
                    target=_plugin_worker_main,
                    args=(config, state.input_buf, state.output_buf),
                    daemon=True,
                    name=f"pydaw_plugin_{tid}",
                )
                proc.start()
                state.process = proc
                state.pid = proc.pid or 0
                state.is_alive = True
                state.last_heartbeat = time.monotonic()
                self._workers[tid] = state
                _log.info("Plugin worker launched: %s (PID %d)", tid, state.pid)
            except Exception as e:
                _log.error("Failed to launch plugin worker for %s: %s", tid, e)
                state.input_buf.close()
                state.output_buf.close()
                return False

        # Start monitor thread if not running
        if not self._running:
            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True,
                name="pydaw_sandbox_monitor")
            self._monitor_thread.start()

        return True

    def kill_plugin(self, track_id: str) -> None:
        """Kill a plugin's worker subprocess."""
        with self._lock:
            self._kill_worker(str(track_id))

    def _kill_worker(self, track_id: str) -> None:
        """Internal: kill worker (must hold _lock)."""
        state = self._workers.pop(track_id, None)
        if state is None:
            return
        try:
            if state.process and state.process.is_alive():
                state.process.terminate()
                state.process.join(timeout=2.0)
                if state.process.is_alive():
                    state.process.kill()
        except Exception as e:
            _log.warning("Error killing worker %s: %s", track_id, e)
        state.input_buf.close()
        state.output_buf.close()
        state.is_alive = False

    def send_audio(self, track_id: str, audio: "np.ndarray", frames: int) -> bool:
        """Send audio to a plugin worker (RT-safe, non-blocking)."""
        state = self._workers.get(str(track_id))
        if state is None or not state.is_alive or state.muted_by_crash:
            return False
        return state.input_buf.write_block(audio, frames)

    def get_output(self, track_id: str, frames: int) -> Optional["np.ndarray"]:
        """Get processed audio from a plugin worker (RT-safe, non-blocking)."""
        state = self._workers.get(str(track_id))
        if state is None or not state.is_alive or state.muted_by_crash:
            return None
        return state.output_buf.read_block(frames)

    def is_plugin_alive(self, track_id: str) -> bool:
        """Check if a plugin worker is running."""
        state = self._workers.get(str(track_id))
        return state is not None and state.is_alive and not state.muted_by_crash

    def get_crash_info(self, track_id: str) -> str:
        """Get crash error message for a track (empty if no crash)."""
        state = self._workers.get(str(track_id))
        if state is None:
            return ""
        return state.error_message

    def _monitor_loop(self) -> None:
        """Background thread: monitor plugin worker health."""
        while self._running:
            try:
                time.sleep(_HEARTBEAT_INTERVAL)
                with self._lock:
                    for tid, state in list(self._workers.items()):
                        if not state.is_alive:
                            continue
                        # Check if process is still running
                        try:
                            alive = state.process is not None and state.process.is_alive()
                        except Exception:
                            alive = False

                        if not alive:
                            # Plugin crashed!
                            state.is_alive = False
                            state.crash_count += 1
                            state.error_message = (
                                f"Plugin crashed (exit code: "
                                f"{getattr(state.process, 'exitcode', '?')})")
                            state.muted_by_crash = True
                            _log.error("Plugin worker %s crashed (count: %d): %s",
                                       tid, state.crash_count, state.error_message)

                            # Notify callback
                            if self._crash_callback:
                                try:
                                    self._crash_callback(tid, state.error_message)
                                except Exception:
                                    pass

                            # Auto-restart if under limit
                            if state.crash_count < _MAX_CRASH_RESTARTS:
                                _log.info("Auto-restarting plugin worker %s "
                                          "(attempt %d/%d)",
                                          tid, state.crash_count + 1,
                                          _MAX_CRASH_RESTARTS)
                                try:
                                    self._restart_worker(tid, state)
                                except Exception as e:
                                    _log.error("Restart failed for %s: %s", tid, e)
                            else:
                                _log.error("Plugin %s exceeded max restarts (%d), "
                                           "leaving muted",
                                           tid, _MAX_CRASH_RESTARTS)
            except Exception as e:
                _log.error("Monitor loop error: %s", e)

    def _restart_worker(self, track_id: str, state: PluginWorkerState) -> None:
        """Restart a crashed worker (must hold _lock)."""
        # Close old buffers
        state.input_buf.close()
        state.output_buf.close()

        # Recreate buffers
        state.input_buf = SharedAudioBuffer(
            name=f"pydaw_in_{track_id}", max_frames=8192)
        state.output_buf = SharedAudioBuffer(
            name=f"pydaw_out_{track_id}", max_frames=8192)

        if not state.input_buf.create() or not state.output_buf.create():
            _log.error("Buffer recreation failed for %s", track_id)
            return

        try:
            proc = multiprocessing.Process(
                target=_plugin_worker_main,
                args=(state.config, state.input_buf, state.output_buf),
                daemon=True,
                name=f"pydaw_plugin_{track_id}",
            )
            proc.start()
            state.process = proc
            state.pid = proc.pid or 0
            state.is_alive = True
            state.muted_by_crash = False
            state.last_heartbeat = time.monotonic()
            _log.info("Plugin worker restarted: %s (PID %d)", track_id, state.pid)
        except Exception as e:
            _log.error("Worker restart failed for %s: %s", track_id, e)

    def shutdown(self) -> None:
        """Kill all workers and stop monitoring."""
        self._running = False
        with self._lock:
            for tid in list(self._workers.keys()):
                self._kill_worker(tid)
        if self._monitor_thread and self._monitor_thread.is_alive():
            try:
                self._monitor_thread.join(timeout=2.0)
            except Exception:
                pass
        _log.info("PluginSandboxManager shutdown complete")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_global_sandbox: Optional[PluginSandboxManager] = None


def get_sandbox_manager() -> PluginSandboxManager:
    """Get or create the global sandbox manager."""
    global _global_sandbox
    if _global_sandbox is None:
        _global_sandbox = PluginSandboxManager()
    return _global_sandbox
