# -*- coding: utf-8 -*-
"""Sandbox Process Manager — Plugin subprocess lifecycle management.

v0.0.20.700 — Phase P1B

Manages the full lifecycle of sandboxed plugin worker subprocesses:
- Spawn with timeout and readiness check
- Kill with SIGTERM → SIGKILL escalation
- Restart with state recovery (last snapshot)
- Health monitoring via heartbeat pings
- Crash detection and auto-restart (max 3 attempts)
- Clean shutdown of all workers on DAW exit

Architecture:
    ProcessManager owns N WorkerHandles.
    Each WorkerHandle owns: subprocess, IPC client, audio buffers, state snapshot.
    Monitor thread pings all workers every 500ms.
    If a worker doesn't respond within 3s → mark as crashed → auto-restart.
"""
from __future__ import annotations

import base64
import logging
import multiprocessing
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .plugin_ipc import (
    PluginIPCClient, PluginIPCServer, PingPongAudioBuffer,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_WORKERS = 32
MAX_CRASH_RESTARTS = 3
HEARTBEAT_INTERVAL = 0.5    # seconds
HEARTBEAT_TIMEOUT = 3.0     # seconds before marking as crashed
SPAWN_TIMEOUT = 5.0         # seconds to wait for worker ready
STATE_SNAPSHOT_INTERVAL = 5.0  # seconds between state snapshots


# ---------------------------------------------------------------------------
# Plugin Config
# ---------------------------------------------------------------------------

@dataclass
class SandboxPluginConfig:
    """Configuration for a sandboxed plugin."""
    track_id: str = ""
    slot_id: str = ""           # unique slot identifier
    plugin_path: str = ""
    plugin_name: str = ""
    plugin_type: str = "vst3"   # vst3, vst2, clap, lv2, ladspa
    sample_rate: int = 48000
    block_size: int = 512
    channels: int = 2
    state_b64: str = ""         # plugin state to restore on (re)start
    is_instrument: bool = False # True for synths (need MIDI input)


# ---------------------------------------------------------------------------
# Worker Handle
# ---------------------------------------------------------------------------

class WorkerHandle:
    """Tracks everything about a single sandboxed plugin worker."""

    __slots__ = (
        "config", "process", "pid", "ipc_client", "ipc_socket_path",
        "input_buf", "output_buf",
        "is_alive", "is_ready", "crash_count", "muted_by_crash",
        "last_heartbeat", "last_state_snapshot", "ping_seq",
        "error_message", "state_b64", "latency_samples",
    )

    def __init__(self, config: SandboxPluginConfig):
        self.config = config
        self.process: Optional[multiprocessing.Process] = None
        self.pid: int = 0
        self.ipc_socket_path = f"/tmp/pydaw_plugin_{config.track_id}_{config.slot_id}.sock"
        self.ipc_client: Optional[PluginIPCClient] = None

        # Audio buffers (shared memory)
        buf_name = f"{config.track_id}_{config.slot_id}"
        self.input_buf = PingPongAudioBuffer(
            name=f"in_{buf_name}",
            max_frames=config.block_size * 4,  # 4 blocks headroom
            channels=config.channels,
        )
        self.output_buf = PingPongAudioBuffer(
            name=f"out_{buf_name}",
            max_frames=config.block_size * 4,
            channels=config.channels,
        )

        # State
        self.is_alive = False
        self.is_ready = False
        self.crash_count = 0
        self.muted_by_crash = False
        self.last_heartbeat = 0.0
        self.last_state_snapshot = 0.0
        self.ping_seq = 0
        self.error_message = ""
        self.state_b64 = config.state_b64 or ""
        self.latency_samples = 0  # v0.0.20.709: P2C plugin-reported latency

    def cleanup(self) -> None:
        """Release all resources."""
        try:
            if self.ipc_client:
                self.ipc_client.disconnect()
                self.ipc_client = None
        except Exception:
            pass
        self.input_buf.close()
        self.output_buf.close()
        try:
            os.unlink(self.ipc_socket_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Worker Entry Point (runs in subprocess)
# ---------------------------------------------------------------------------

def _worker_entry(config: SandboxPluginConfig,
                  input_buf: PingPongAudioBuffer,
                  output_buf: PingPongAudioBuffer,
                  ipc_socket_path: str) -> None:
    """Plugin worker subprocess entry point.

    Loads the plugin, starts IPC server, processes audio in a loop.
    If anything fatal happens, the subprocess exits and the manager detects it.
    """
    wlog = logging.getLogger(f"pydaw.worker.{config.track_id}.{config.slot_id}")

    try:
        # Start IPC server
        ipc = PluginIPCServer(ipc_socket_path)
        if not ipc.start():
            wlog.error("Failed to start IPC server")
            return

        # Load plugin
        plugin = _load_plugin(config, wlog)
        if plugin is None:
            ipc.send_event({"evt": "error", "message": "Plugin load failed"})
            ipc.stop()
            return

        # State
        bypassed = False

        def handle_command(msg: dict) -> Optional[dict]:
            nonlocal bypassed, plugin
            cmd = msg.get("cmd", "")

            if cmd == "ping":
                return {"evt": "pong", "seq": msg.get("seq", 0)}

            elif cmd == "set_param":
                pid = str(msg.get("param_id", ""))
                val = float(msg.get("value", 0.0))
                try:
                    if hasattr(plugin, 'set_parameter'):
                        plugin.set_parameter(pid, val)
                    elif hasattr(plugin, 'set_param'):
                        plugin.set_param(pid, val)
                except Exception as e:
                    wlog.debug("set_param error: %s", e)

            elif cmd == "bypass":
                bypassed = bool(msg.get("enabled", False))

            elif cmd == "get_state":
                try:
                    state_bytes = b""
                    if hasattr(plugin, 'get_state'):
                        state_bytes = plugin.get_state()
                    elif hasattr(plugin, 'save_state'):
                        state_bytes = plugin.save_state()
                    b64 = base64.b64encode(state_bytes).decode('ascii') if state_bytes else ""
                    return {"evt": "state", "state_b64": b64}
                except Exception as e:
                    return {"evt": "error", "message": f"get_state failed: {e}"}

            elif cmd == "load_state":
                try:
                    b64 = msg.get("state_b64", "")
                    if b64:
                        state_bytes = base64.b64decode(b64)
                        if hasattr(plugin, 'set_state'):
                            plugin.set_state(state_bytes)
                        elif hasattr(plugin, 'load_state'):
                            plugin.load_state(state_bytes)
                except Exception as e:
                    wlog.warning("load_state error: %s", e)

            elif cmd == "get_latency":
                # v0.0.20.709: P2C — Plugin Latency Report
                latency = 0
                try:
                    if hasattr(plugin, 'get_latency'):
                        latency = int(plugin.get_latency())
                    elif hasattr(plugin, 'latency'):
                        latency = int(plugin.latency)
                    elif hasattr(plugin, 'getLatency'):
                        latency = int(plugin.getLatency())
                except Exception:
                    pass
                return {"evt": "latency", "samples": latency}

            elif cmd == "shutdown":
                raise SystemExit(0)

            return None

        ipc.set_message_handler(handle_command)

        # Notify main process we're ready
        param_count = 0
        try:
            if hasattr(plugin, 'parameters'):
                param_count = len(plugin.parameters)
        except Exception:
            pass
        ipc.send_event({
            "evt": "ready",
            "plugin_name": config.plugin_name,
            "param_count": param_count,
        })

        wlog.info("Worker ready: %s (%s)", config.plugin_name, config.plugin_type)

        # Audio process loop
        import numpy as np
        from .plugin_ipc import WorkerAudioHandler
        audio = WorkerAudioHandler(input_buf, output_buf)

        while True:
            try:
                block = audio.read_input()
                if block is not None:
                    if bypassed:
                        # Bypass: pass through
                        audio.write_output(block, len(block))
                    else:
                        # Process through plugin
                        try:
                            if hasattr(plugin, 'process_inplace'):
                                plugin.process_inplace(block, len(block), config.sample_rate)
                                audio.write_output(block, len(block))
                            elif hasattr(plugin, 'process'):
                                result = plugin.process(
                                    block.astype(np.float32),
                                    config.sample_rate,
                                )
                                if result is not None:
                                    audio.write_output(result, len(result))
                                else:
                                    audio.write_output(block, len(block))
                            else:
                                audio.write_output(block, len(block))
                        except Exception as e:
                            wlog.error("Process error: %s", e)
                            audio.write_silence(config.block_size)
                else:
                    time.sleep(0.0005)  # ~0.5ms when idle
            except SystemExit:
                break
            except Exception:
                break

    except SystemExit:
        pass
    except Exception as e:
        wlog.critical("Worker fatal: %s", e)
    finally:
        try:
            ipc.stop()
        except Exception:
            pass


def _load_plugin(config: SandboxPluginConfig, wlog) -> Any:
    """Load a plugin in the worker subprocess. Returns plugin object or None."""
    plugin = None

    if config.plugin_type in ("vst3", "vst2"):
        try:
            from pydaw.audio.vst3_host import load_vst3_fx
            plugin = load_vst3_fx(config.plugin_path, config.sample_rate,
                                   plugin_name=config.plugin_name)
        except Exception as e:
            wlog.error("Failed to load VST3/2: %s", e)

    elif config.plugin_type == "clap":
        try:
            from pydaw.audio.clap_host import load_clap_plugin
            plugin = load_clap_plugin(config.plugin_path, config.sample_rate)
        except Exception as e:
            wlog.error("Failed to load CLAP: %s", e)

    elif config.plugin_type == "lv2":
        try:
            from pydaw.audio.lv2_host import Lv2Fx
            plugin = Lv2Fx(uri=config.plugin_path, sr=config.sample_rate)
        except Exception as e:
            wlog.error("Failed to load LV2: %s", e)

    elif config.plugin_type == "ladspa":
        try:
            from pydaw.audio.ladspa_host import LadspaFx
            plugin = LadspaFx(path=config.plugin_path, sr=config.sample_rate)
        except Exception as e:
            wlog.error("Failed to load LADSPA: %s", e)

    # Restore state
    if plugin and config.state_b64:
        try:
            state_bytes = base64.b64decode(config.state_b64)
            if hasattr(plugin, 'set_state'):
                plugin.set_state(state_bytes)
            elif hasattr(plugin, 'load_state'):
                plugin.load_state(state_bytes)
        except Exception as e:
            wlog.warning("State restore failed: %s", e)

    return plugin


# ---------------------------------------------------------------------------
# Process Manager (Main Process)
# ---------------------------------------------------------------------------

class SandboxProcessManager:
    """Manages all sandboxed plugin worker subprocesses.

    Usage:
        mgr = SandboxProcessManager()
        mgr.set_crash_callback(on_crash)
        mgr.spawn("trk1", "slot0", config)
        mgr.send_audio("trk1", "slot0", audio_block, frames)
        output = mgr.get_output("trk1", "slot0", frames)
        mgr.shutdown()
    """

    def __init__(self):
        self._workers: Dict[str, WorkerHandle] = {}  # key = "track_id:slot_id"
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._crash_callback: Optional[Callable[[str, str, str], None]] = None
        self._param_changed_callback: Optional[Callable[[str, str, str, float], None]] = None

    def set_crash_callback(self, cb: Callable[[str, str, str], None]) -> None:
        """Set callback: cb(track_id, slot_id, error_message)."""
        self._crash_callback = cb

    def set_param_changed_callback(
        self, cb: Callable[[str, str, str, float], None]
    ) -> None:
        """Set callback: cb(track_id, slot_id, param_id, value).

        v0.0.20.710: P2B — Bidirectional param sync from editor.
        Called when a plugin editor changes a parameter in the worker.
        """
        self._param_changed_callback = cb

    @staticmethod
    def _key(track_id: str, slot_id: str) -> str:
        return f"{track_id}:{slot_id}"

    def spawn(self, track_id: str, slot_id: str, config: SandboxPluginConfig) -> bool:
        """Spawn a plugin worker subprocess.

        Returns True if the worker started and reported ready.
        """
        key = self._key(track_id, slot_id)
        config.track_id = track_id
        config.slot_id = slot_id

        with self._lock:
            # Kill existing
            if key in self._workers:
                self._kill_worker(key)

            handle = WorkerHandle(config)

            # Create shared memory buffers
            if not handle.input_buf.create() or not handle.output_buf.create():
                _log.error("Buffer creation failed for %s", key)
                return False

            # Start subprocess
            try:
                # v0.0.20.706: Use format-specific workers (P2–P5)
                worker_target = _worker_entry  # generic fallback
                ptype = str(config.plugin_type or "").lower()

                if ptype == "vst3":
                    try:
                        from pydaw.plugin_workers.vst3_worker import vst3_worker_entry
                        worker_target = vst3_worker_entry
                    except ImportError:
                        _log.debug("vst3_worker not available, using generic")

                elif ptype == "vst2":
                    try:
                        from pydaw.plugin_workers.vst2_worker import vst2_worker_entry
                        worker_target = vst2_worker_entry
                    except ImportError:
                        _log.debug("vst2_worker not available, using generic")

                elif ptype == "lv2":
                    try:
                        from pydaw.plugin_workers.lv2_ladspa_worker import lv2_worker_entry
                        worker_target = lv2_worker_entry
                    except ImportError:
                        _log.debug("lv2_worker not available, using generic")

                elif ptype == "ladspa":
                    try:
                        from pydaw.plugin_workers.lv2_ladspa_worker import ladspa_worker_entry
                        worker_target = ladspa_worker_entry
                    except ImportError:
                        _log.debug("ladspa_worker not available, using generic")

                elif ptype == "clap":
                    try:
                        from pydaw.plugin_workers.clap_worker import clap_worker_entry
                        worker_target = clap_worker_entry
                    except ImportError:
                        _log.debug("clap_worker not available, using generic")

                if worker_target is not _worker_entry:
                    _log.info("Using %s-specific worker for %s", ptype, key)

                proc = multiprocessing.Process(
                    target=worker_target,
                    args=(config, handle.input_buf, handle.output_buf,
                          handle.ipc_socket_path),
                    daemon=True,
                    name=f"pydaw_sandbox_{key}",
                )
                proc.start()
                handle.process = proc
                handle.pid = proc.pid or 0
                handle.is_alive = True
                handle.last_heartbeat = time.monotonic()
            except Exception as e:
                _log.error("Failed to spawn worker %s: %s", key, e)
                handle.cleanup()
                return False

            # Connect IPC
            handle.ipc_client = PluginIPCClient(handle.ipc_socket_path)
            if not handle.ipc_client.connect(timeout=SPAWN_TIMEOUT):
                _log.error("IPC connect failed for %s", key)
                self._kill_handle(handle)
                return False

            # Set up event handler
            def on_event(msg, h=handle):
                if msg.get("evt") == "ready":
                    h.is_ready = True
                elif msg.get("evt") == "state":
                    h.state_b64 = msg.get("state_b64", "")
                elif msg.get("evt") == "latency":
                    # v0.0.20.709: P2C — plugin-reported latency
                    h.latency_samples = int(msg.get("samples", 0))
                elif msg.get("evt") == "param_changed":
                    # v0.0.20.710: P2B — editor param change → main
                    if self._param_changed_callback:
                        try:
                            self._param_changed_callback(
                                h.config.track_id,
                                h.config.slot_id,
                                str(msg.get("param_id", "")),
                                float(msg.get("value", 0.0)),
                            )
                        except Exception:
                            pass
                elif msg.get("evt") == "error":
                    h.error_message = msg.get("message", "")

            handle.ipc_client.set_event_handler(on_event)

            self._workers[key] = handle
            _log.info("Spawned worker %s (PID %d)", key, handle.pid)

        # Start monitor if needed
        if not self._running:
            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True,
                name="sandbox_monitor")
            self._monitor_thread.start()

        return True

    def kill(self, track_id: str, slot_id: str) -> None:
        """Kill a specific worker."""
        key = self._key(track_id, slot_id)
        with self._lock:
            self._kill_worker(key)

    def _kill_worker(self, key: str) -> None:
        """Internal: kill worker (must hold _lock)."""
        handle = self._workers.pop(key, None)
        if handle:
            self._kill_handle(handle)

    def _kill_handle(self, handle: WorkerHandle) -> None:
        """Kill a worker by handle."""
        # Try graceful shutdown via IPC
        if handle.ipc_client:
            try:
                handle.ipc_client.shutdown()
                time.sleep(0.1)
            except Exception:
                pass

        # SIGTERM
        try:
            if handle.process and handle.process.is_alive():
                handle.process.terminate()
                handle.process.join(timeout=2.0)
        except Exception:
            pass

        # SIGKILL if still alive
        try:
            if handle.process and handle.process.is_alive():
                handle.process.kill()
        except Exception:
            pass

        handle.is_alive = False
        handle.cleanup()

    def send_audio(self, track_id: str, slot_id: str, audio, frames: int) -> bool:
        """Send audio to a worker (RT-safe, non-blocking)."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h is None or not h.is_alive or h.muted_by_crash:
            return False
        return h.input_buf.write(audio, frames)

    def get_output(self, track_id: str, slot_id: str, frames: int = 0):
        """Get processed audio from a worker (RT-safe, non-blocking)."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h is None or not h.is_alive or h.muted_by_crash:
            return None
        return h.output_buf.read_latest(frames)

    def set_param(self, track_id: str, slot_id: str, param_id: str, value: float) -> bool:
        """Send parameter change to a worker."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client:
            return h.ipc_client.set_param(param_id, value)
        return False

    def set_bypass(self, track_id: str, slot_id: str, enabled: bool) -> bool:
        """Set bypass state on a worker."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client:
            return h.ipc_client.set_bypass(enabled)
        return False

    # v0.0.20.705: MIDI relay for instrument workers (P2C)

    def send_note_on(self, track_id: str, slot_id: str,
                     pitch: int, velocity: int = 100) -> bool:
        """Send MIDI note-on to an instrument worker."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.send_note_on(pitch, velocity)
        return False

    def send_note_off(self, track_id: str, slot_id: str,
                      pitch: int = -1) -> bool:
        """Send MIDI note-off to an instrument worker."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.send_note_off(pitch)
        return False

    def send_all_notes_off(self, track_id: str, slot_id: str) -> bool:
        """Send MIDI panic to an instrument worker."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.send_all_notes_off()
        return False

    def send_midi_events(self, track_id: str, slot_id: str,
                         events: list) -> bool:
        """Send batch MIDI events: [[status, d1, d2], ...]."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.send_midi_events(events)
        return False

    # v0.0.20.705: Editor commands (P2B)

    def show_editor(self, track_id: str, slot_id: str) -> bool:
        """Open plugin editor in worker process."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.show_editor()
        return False

    def hide_editor(self, track_id: str, slot_id: str) -> bool:
        """Close plugin editor in worker process."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.hide_editor()
        return False

    def is_alive(self, track_id: str, slot_id: str) -> bool:
        """Check if a worker is running and responsive."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        return h is not None and h.is_alive and not h.muted_by_crash

    def is_crashed(self, track_id: str, slot_id: str) -> bool:
        """Check if a worker has crashed."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        return h is not None and h.muted_by_crash

    def get_crash_info(self, track_id: str, slot_id: str) -> str:
        """Get crash error message."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        return h.error_message if h else ""

    # v0.0.20.709: P2C — Plugin Latency Report via IPC

    def get_latency(self, track_id: str, slot_id: str) -> int:
        """Get plugin-reported processing latency in samples."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        return h.latency_samples if h else 0

    def request_latency(self, track_id: str, slot_id: str) -> bool:
        """Request latency report from a worker plugin."""
        key = self._key(track_id, slot_id)
        h = self._workers.get(key)
        if h and h.ipc_client and h.is_alive:
            return h.ipc_client.request_latency()
        return False

    def restart(self, track_id: str, slot_id: str) -> bool:
        """Restart a crashed worker with its last state snapshot."""
        key = self._key(track_id, slot_id)
        with self._lock:
            h = self._workers.get(key)
            if h is None:
                return False
            config = h.config
            # Use last state snapshot for recovery
            if h.state_b64:
                config.state_b64 = h.state_b64
            self._kill_worker(key)

        return self.spawn(track_id, slot_id, config)

    def factory_restart(self, track_id: str, slot_id: str) -> bool:
        """Restart a crashed worker WITHOUT state (factory default).

        v0.0.20.704 — P6B: Reset-Button for Factory Default restart.
        """
        key = self._key(track_id, slot_id)
        with self._lock:
            h = self._workers.get(key)
            if h is None:
                return False
            config = h.config
            config.state_b64 = ""   # clear state → factory default
            self._kill_worker(key)

        return self.spawn(track_id, slot_id, config)

    def get_all_status(self) -> List[dict]:
        """Get status of all workers (for UI display)."""
        result = []
        with self._lock:
            for key, h in self._workers.items():
                result.append({
                    "key": key,
                    "track_id": h.config.track_id,
                    "slot_id": h.config.slot_id,
                    "plugin_name": h.config.plugin_name,
                    "plugin_type": h.config.plugin_type,
                    "pid": h.pid,
                    "alive": h.is_alive,
                    "ready": h.is_ready,
                    "crashed": h.muted_by_crash,
                    "crash_count": h.crash_count,
                    "error": h.error_message,
                    "latency_samples": h.latency_samples,  # v0.0.20.709: P2C
                })
        return result

    # --- Monitor ---

    def _monitor_loop(self) -> None:
        """Background: ping workers, detect crashes, auto-restart."""
        while self._running:
            try:
                time.sleep(HEARTBEAT_INTERVAL)
                now = time.monotonic()

                with self._lock:
                    for key, h in list(self._workers.items()):
                        if not h.is_alive:
                            continue

                        # Check process alive
                        try:
                            alive = h.process is not None and h.process.is_alive()
                        except Exception:
                            alive = False

                        if not alive:
                            # CRASHED
                            h.is_alive = False
                            h.crash_count += 1
                            h.error_message = (
                                f"Plugin crashed (exit: "
                                f"{getattr(h.process, 'exitcode', '?')})")
                            h.muted_by_crash = True
                            _log.error("Worker %s crashed (#%d): %s",
                                       key, h.crash_count, h.error_message)

                            if self._crash_callback:
                                try:
                                    self._crash_callback(
                                        h.config.track_id, h.config.slot_id,
                                        h.error_message)
                                except Exception:
                                    pass

                            # Auto-restart
                            if h.crash_count < MAX_CRASH_RESTARTS:
                                _log.info("Auto-restarting %s (%d/%d)",
                                          key, h.crash_count, MAX_CRASH_RESTARTS)
                                try:
                                    config = h.config
                                    if h.state_b64:
                                        config.state_b64 = h.state_b64
                                    self._kill_worker(key)
                                    # Spawn outside lock to avoid deadlock
                                    threading.Thread(
                                        target=self.spawn,
                                        args=(config.track_id, config.slot_id, config),
                                        daemon=True).start()
                                except Exception as e:
                                    _log.error("Auto-restart failed: %s", e)
                            continue

                        # Ping
                        if h.ipc_client:
                            h.ping_seq += 1
                            h.ipc_client.ping(h.ping_seq)

                        # State snapshot (every 5s)
                        if (now - h.last_state_snapshot) > STATE_SNAPSHOT_INTERVAL:
                            if h.ipc_client:
                                h.ipc_client.request_state()
                            h.last_state_snapshot = now

            except Exception as e:
                _log.error("Monitor error: %s", e)

    def shutdown(self) -> None:
        """Kill all workers and stop monitor."""
        self._running = False
        with self._lock:
            for key in list(self._workers.keys()):
                self._kill_worker(key)
        if self._monitor_thread:
            try:
                self._monitor_thread.join(timeout=3.0)
            except Exception:
                pass
        _log.info("SandboxProcessManager shutdown")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[SandboxProcessManager] = None
_instance_lock = threading.Lock()


def get_process_manager() -> SandboxProcessManager:
    """Get or create the global sandbox process manager."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SandboxProcessManager()
    return _instance
