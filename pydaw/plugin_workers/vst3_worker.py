# -*- coding: utf-8 -*-
"""VST3 Worker Process — Sandboxed VST3 plugin hosting via pedalboard.

v0.0.20.705 — Phase P2A/P2B/P2C

Runs as a standalone subprocess. Loads a VST3 plugin via pedalboard,
processes audio from shared memory, handles parameters and state via IPC.

Supports both FX and Instrument modes:
    - FX: reads input audio → process → writes output audio
    - Instrument: receives MIDI via IPC → renders audio → writes output

Can be started as:
    python3 -m pydaw.plugin_workers.vst3_worker \\
        --path /path/to/plugin.vst3 \\
        --sr 48000 --bs 512 --ch 2 \\
        --socket /tmp/pydaw_plugin_trk1_fx0.sock \\
        --instrument  (optional, for synths)

Or spawned via multiprocessing from SandboxProcessManager.

Architecture:
    ┌─────────────────────────────────────────────┐
    │  VST3 Worker Process                        │
    │                                             │
    │  pedalboard.load_plugin(path)               │
    │  ┌───────────────────────────────────┐      │
    │  │  Audio Loop (main thread)          │      │
    │  │  SharedAudioBuffer.read_input()    │      │
    │  │  plugin.process(input)             │      │
    │  │  SharedAudioBuffer.write_output()  │      │
    │  └───────────────────────────────────┘      │
    │  ┌───────────────────────────────────┐      │
    │  │  IPC Thread (commands/events)      │      │
    │  │  SetParam, GetState, Bypass, MIDI  │      │
    │  │  ShowEditor, HideEditor, Shutdown  │      │
    │  └───────────────────────────────────┘      │
    └─────────────────────────────────────────────┘
"""
from __future__ import annotations

import base64
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pedalboard availability
# ---------------------------------------------------------------------------

try:
    import pedalboard
    import numpy as np
    _PB_OK = True
except ImportError:
    _PB_OK = False
    np = None  # type: ignore


# ---------------------------------------------------------------------------
# Plugin loader (reuses vst3_host patterns)
# ---------------------------------------------------------------------------

def _load_plugin(path: str, plugin_name: str = "") -> Any:
    """Load a VST3 plugin via pedalboard."""
    if not _PB_OK:
        raise RuntimeError("pedalboard not installed")
    base = str(path or "")
    pname = str(plugin_name or "").strip()
    if pname:
        try:
            return pedalboard.load_plugin(base, plugin_name=pname)
        except TypeError:
            return pedalboard.load_plugin(base, pname)
    return pedalboard.load_plugin(base)


def _detect_channels(plugin: Any) -> Tuple[int, int]:
    """Detect input/output channel count from pedalboard plugin."""
    in_ch, out_ch = 2, 2
    for attr in ("input_channel_count", "num_input_channels"):
        try:
            v = getattr(plugin, attr, None)
            if v is not None and int(v) > 0:
                in_ch = int(v)
                break
        except Exception:
            continue
    for attr in ("output_channel_count", "num_output_channels"):
        try:
            v = getattr(plugin, attr, None)
            if v is not None and int(v) > 0:
                out_ch = int(v)
                break
        except Exception:
            continue
    return max(1, in_ch), max(1, out_ch)


def _get_raw_state_b64(plugin: Any) -> str:
    """Get plugin state as Base64 string."""
    try:
        raw = getattr(plugin, "raw_state", b"")
        if raw:
            if isinstance(raw, (bytes, bytearray)):
                return base64.b64encode(raw).decode("ascii")
            elif isinstance(raw, memoryview):
                return base64.b64encode(bytes(raw)).decode("ascii")
    except Exception:
        pass
    return ""


def _set_raw_state_b64(plugin: Any, b64: str) -> bool:
    """Restore plugin state from Base64 string."""
    if not b64:
        return False
    try:
        raw = base64.b64decode(b64)
        if raw:
            setattr(plugin, "raw_state", raw)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Param info extraction
# ---------------------------------------------------------------------------

def _get_param_infos(plugin: Any) -> List[Dict[str, Any]]:
    """Extract parameter metadata from pedalboard plugin."""
    infos: List[Dict[str, Any]] = []
    try:
        pb_params = plugin.parameters
        if not isinstance(pb_params, dict):
            return infos
        for name, param in pb_params.items():
            try:
                info: Dict[str, Any] = {
                    "name": str(name),
                    "min": float(getattr(param, "min_value", 0.0)),
                    "max": float(getattr(param, "max_value", 1.0)),
                    "default": float(getattr(param, "default_value", 0.0)),
                }
                try:
                    info["value"] = float(param.raw_value)
                except Exception:
                    info["value"] = info["default"]
                infos.append(info)
            except Exception:
                continue
    except Exception:
        pass
    return infos


# ---------------------------------------------------------------------------
# VST3 Worker Entry Point
# ---------------------------------------------------------------------------

def vst3_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
) -> None:
    """VST3 worker subprocess entry point.

    Args:
        config: SandboxPluginConfig with plugin_path, sample_rate, etc.
        input_buf: PingPongAudioBuffer for audio input (FX mode)
        output_buf: PingPongAudioBuffer for audio output
        ipc_socket_path: Path to Unix domain socket for commands/events
    """
    wlog = logging.getLogger(
        f"pydaw.vst3_worker.{config.track_id}.{config.slot_id}")

    # Basic setup
    logging.basicConfig(
        level=logging.INFO,
        format="[VST3-WRK %(name)s] %(message)s",
        stream=sys.stderr,
    )

    if not _PB_OK:
        wlog.error("pedalboard not available — cannot host VST3")
        return

    # Start IPC server
    try:
        from pydaw.services.plugin_ipc import (
            PluginIPCServer, WorkerAudioHandler,
        )
    except ImportError:
        wlog.error("plugin_ipc not importable")
        return

    ipc = PluginIPCServer(ipc_socket_path)
    if not ipc.start():
        wlog.error("IPC server start failed")
        return

    # Load plugin
    try:
        plugin = _load_plugin(config.plugin_path,
                              getattr(config, "plugin_name", ""))
    except Exception as e:
        wlog.error("Plugin load failed: %s", e)
        ipc.send_event({"evt": "error", "message": f"Load failed: {e}"})
        ipc.stop()
        return

    # Detect instrument mode
    is_instrument = bool(getattr(config, "is_instrument", False))
    if not is_instrument:
        try:
            is_instrument = bool(getattr(plugin, "is_instrument", False))
        except Exception:
            pass

    # Detect channel layout
    in_ch, out_ch = _detect_channels(plugin)
    sr = int(getattr(config, "sample_rate", 48000) or 48000)
    bs = int(getattr(config, "block_size", 512) or 512)

    # Restore state
    state_b64 = str(getattr(config, "state_b64", "") or "")
    if state_b64:
        try:
            _set_raw_state_b64(plugin, state_b64)
            wlog.info("State restored from Base64")
        except Exception as e:
            wlog.warning("State restore failed: %s", e)

    # Pre-allocate buffers
    pb_input = np.zeros((in_ch, bs * 2), dtype=np.float32)

    # Worker state
    bypassed = False
    editor_shown = False
    pending_midi: List[Tuple[bytes, float]] = []  # (midi_bytes, timestamp)

    # v0.0.20.710: P2B — Param Poller (from vst_gui_process.py)
    # When the editor is shown, polls parameters at ~12Hz and sends
    # param_changed events back to the main process via IPC.
    import threading as _threading
    import hashlib as _hashlib

    _param_poll_stop = _threading.Event()
    _param_poll_thread: Optional[_threading.Thread] = None
    _last_param_snapshot: Dict[str, float] = {}

    # Take initial param snapshot
    try:
        for pi in param_infos:
            _last_param_snapshot[str(pi.get("name", ""))] = float(pi.get("value", 0.0))
    except Exception:
        pass

    def _snapshot_params_dict() -> Dict[str, float]:
        """Current parameter values from pedalboard plugin."""
        out: Dict[str, float] = {}
        try:
            pb_params = plugin.parameters
            for name, param in pb_params.items():
                try:
                    out[str(name)] = float(param.raw_value)
                except Exception:
                    pass
        except Exception:
            pass
        return out

    def _param_poll_loop() -> None:
        """Background: polls params while editor is shown, sends changes via IPC."""
        nonlocal _last_param_snapshot
        _INTERVAL = 0.08  # ~12Hz
        _BATCH_THRESHOLD = 10  # preset switch detection
        _STATE_CHECK_INTERVAL = 8  # ~640ms
        _poll_count = 0
        _last_state_hash = ""
        _cooldown = 0

        try:
            raw = getattr(plugin, "raw_state", None)
            if raw and isinstance(raw, (bytes, bytearray, memoryview)):
                _last_state_hash = _hashlib.md5(bytes(raw) if isinstance(raw, memoryview) else raw).hexdigest()
        except Exception:
            pass

        while not _param_poll_stop.is_set():
            if _cooldown > 0:
                _cooldown -= 1

            changed_count = 0
            try:
                current = _snapshot_params_dict()
                for name, val in current.items():
                    prev = _last_param_snapshot.get(name)
                    if prev is None or abs(val - prev) > 1e-7:
                        _last_param_snapshot[name] = val
                        changed_count += 1
                        try:
                            ipc.send_event({
                                "evt": "param_changed",
                                "param_id": name,
                                "value": val,
                            })
                        except Exception:
                            pass
            except Exception:
                pass

            # Batch detection → preset switch → send full state
            if changed_count >= _BATCH_THRESHOLD and _cooldown <= 0:
                try:
                    b64 = _get_raw_state_b64(plugin)
                    if b64:
                        ipc.send_event({"evt": "state", "state_b64": b64})
                        _last_param_snapshot = _snapshot_params_dict()
                        _cooldown = 8
                except Exception:
                    pass

            # Periodic state hash check
            _poll_count += 1
            if _poll_count >= _STATE_CHECK_INTERVAL:
                _poll_count = 0
                try:
                    raw = getattr(plugin, "raw_state", None)
                    if raw:
                        data = bytes(raw) if isinstance(raw, memoryview) else raw
                        if isinstance(data, bytes) and len(data) > 0:
                            h = _hashlib.md5(data).hexdigest()
                            if h and h != _last_state_hash and _cooldown <= 0:
                                b64 = _get_raw_state_b64(plugin)
                                if b64:
                                    ipc.send_event({"evt": "state", "state_b64": b64})
                                    _last_param_snapshot = _snapshot_params_dict()
                                    _last_state_hash = h
                                    _cooldown = 8
                except Exception:
                    pass

            time.sleep(_INTERVAL)

    # ------ IPC command handler ------

    def handle_command(msg: dict) -> Optional[dict]:
        nonlocal bypassed, editor_shown, pending_midi, _param_poll_thread
        cmd = msg.get("cmd", "")

        if cmd == "ping":
            return {"evt": "pong", "seq": msg.get("seq", 0)}

        elif cmd == "set_param":
            param_name = str(msg.get("param_id", ""))
            value = float(msg.get("value", 0.0))
            try:
                pb_params = plugin.parameters
                if isinstance(pb_params, dict) and param_name in pb_params:
                    pb_params[param_name].raw_value = value
            except Exception as e:
                wlog.debug("set_param(%s) error: %s", param_name, e)

        elif cmd == "bypass":
            bypassed = bool(msg.get("enabled", False))

        elif cmd == "get_state":
            b64 = _get_raw_state_b64(plugin)
            return {"evt": "state", "state_b64": b64}

        elif cmd == "load_state":
            b64 = msg.get("state_b64", "")
            _set_raw_state_b64(plugin, b64)

        elif cmd == "get_params":
            infos = _get_param_infos(plugin)
            return {"evt": "params", "params": infos}

        # P2B: Editor commands + param polling (v0.0.20.710)
        elif cmd == "show_editor":
            try:
                if hasattr(plugin, "show_editor"):
                    # Start param poller before showing editor
                    _param_poll_stop.clear()
                    if _param_poll_thread is None or not _param_poll_thread.is_alive():
                        _param_poll_thread = _threading.Thread(
                            target=_param_poll_loop, daemon=True,
                            name="vst3-param-poller")
                        _param_poll_thread.start()
                    plugin.show_editor()
                    editor_shown = True
                    return {"evt": "editor_shown"}
            except Exception as e:
                wlog.warning("show_editor failed: %s", e)
                return {"evt": "error", "message": f"show_editor: {e}"}

        elif cmd == "hide_editor":
            try:
                if hasattr(plugin, "hide_editor"):
                    plugin.hide_editor()
                    editor_shown = False
                    # Stop param poller
                    _param_poll_stop.set()
            except Exception:
                pass

        # P2C: MIDI commands (instruments)
        elif cmd == "midi":
            # msg: {cmd: "midi", events: [[status, data1, data2], ...]}
            events = msg.get("events", [])
            for ev in events:
                try:
                    if isinstance(ev, (list, tuple)) and len(ev) >= 2:
                        midi_bytes = bytes(int(b) & 0xFF for b in ev[:3])
                        pending_midi.append((midi_bytes, 0.0))
                except Exception:
                    continue

        elif cmd == "note_on":
            pitch = max(0, min(127, int(msg.get("pitch", 60))))
            vel = max(1, min(127, int(msg.get("velocity", 100))))
            pending_midi.append((bytes([0x90, pitch, vel]), 0.0))

        elif cmd == "note_off":
            pitch = int(msg.get("pitch", -1))
            if pitch >= 0:
                pending_midi.append(
                    (bytes([0x80, pitch & 0x7F, 0]), 0.0))
            else:
                # All notes off
                pending_midi.append((bytes([0xB0, 123, 0]), 0.0))

        elif cmd == "all_notes_off":
            pending_midi.append((bytes([0xB0, 123, 0]), 0.0))

        elif cmd == "get_latency":
            # v0.0.20.709: P2C — Plugin Latency Report
            latency = 0
            try:
                if hasattr(plugin, 'get_latency'):
                    latency = int(plugin.get_latency())
                elif hasattr(plugin, 'latency'):
                    latency = int(plugin.latency)
            except Exception:
                pass
            return {"evt": "latency", "samples": latency}

        elif cmd == "shutdown":
            raise SystemExit(0)

        return None

    ipc.set_message_handler(handle_command)

    # Get param count for ready event
    param_infos = _get_param_infos(plugin)

    # Notify ready
    ipc.send_event({
        "evt": "ready",
        "plugin_name": getattr(config, "plugin_name", "") or str(config.plugin_path).split("/")[-1],
        "param_count": len(param_infos),
        "is_instrument": is_instrument,
        "input_channels": in_ch,
        "output_channels": out_ch,
    })

    wlog.info("VST3 worker ready: %s (inst=%s, %d→%d ch, %d params)",
              config.plugin_path, is_instrument, in_ch, out_ch,
              len(param_infos))

    # ------ Audio processing loop ------

    audio = WorkerAudioHandler(input_buf, output_buf)

    while True:
        try:
            if is_instrument:
                # Instrument mode: render from MIDI → audio
                _process_instrument(
                    plugin, audio, pending_midi, sr, bs,
                    out_ch, bypassed, wlog)
                pending_midi.clear()
            else:
                # FX mode: read input → process → write output
                _process_fx(
                    plugin, audio, pb_input, in_ch, out_ch,
                    sr, bs, bypassed, wlog)

        except SystemExit:
            break
        except Exception as e:
            wlog.error("Audio loop error: %s", e)
            try:
                audio.write_silence(bs)
            except Exception:
                pass
            time.sleep(0.001)

    # Cleanup
    _param_poll_stop.set()  # v0.0.20.710: stop param poller
    try:
        if editor_shown and hasattr(plugin, "hide_editor"):
            plugin.hide_editor()
    except Exception:
        pass
    try:
        ipc.stop()
    except Exception:
        pass
    wlog.info("VST3 worker shutdown")


# ---------------------------------------------------------------------------
# FX processing (P2A)
# ---------------------------------------------------------------------------

def _process_fx(
    plugin: Any,
    audio: Any,
    pb_input: Any,
    in_ch: int,
    out_ch: int,
    sr: int,
    bs: int,
    bypassed: bool,
    wlog: logging.Logger,
) -> None:
    """Process one audio block in FX mode.

    Reads from input buffer, processes through plugin, writes to output.
    If no input available, sleeps briefly (idle).
    """
    block = audio.read_input()
    if block is None:
        time.sleep(0.0005)  # ~500µs idle
        return

    frames = len(block)
    if frames <= 0:
        return

    if bypassed:
        audio.write_output(block, frames)
        return

    try:
        # block shape: (frames, channels) — convert to pedalboard (channels, frames)
        if block.ndim == 2:
            block_t = block.T.astype(np.float32)
        else:
            # mono
            block_t = block.reshape(1, -1).astype(np.float32)

        # Pad/trim to match plugin input channels
        actual_in_ch = block_t.shape[0]
        if actual_in_ch < in_ch:
            # Pad with zeros
            padded = np.zeros((in_ch, frames), dtype=np.float32)
            padded[:actual_in_ch] = block_t
            block_t = padded
        elif actual_in_ch > in_ch:
            block_t = block_t[:in_ch]

        # Process
        result = plugin.process(
            block_t[:, :frames],
            sample_rate=float(sr),
            reset=False,
        )

        # Convert back to (frames, channels)
        out = np.asarray(result, dtype=np.float32)
        if out.ndim == 2:
            out_t = out.T
        else:
            out_t = out.reshape(-1, 1)

        audio.write_output(out_t, min(frames, out_t.shape[0]))

    except Exception as e:
        wlog.debug("FX process error: %s", e)
        # Passthrough on error
        audio.write_output(block, frames)


# ---------------------------------------------------------------------------
# Instrument processing (P2C)
# ---------------------------------------------------------------------------

def _process_instrument(
    plugin: Any,
    audio: Any,
    pending_midi: List[Tuple[bytes, float]],
    sr: int,
    bs: int,
    out_ch: int,
    bypassed: bool,
    wlog: logging.Logger,
) -> None:
    """Render one audio block from MIDI in instrument mode.

    Called at a regular interval (~buffer cycle). Collects pending MIDI,
    renders audio via pedalboard, writes to output buffer.
    """
    if bypassed:
        audio.write_silence(bs)
        time.sleep(0.0005)
        return

    # Collect MIDI for this block
    midi_msgs = list(pending_midi)

    duration = float(bs) / float(sr) if sr > 0 else 0.01

    try:
        result = plugin.process(
            midi_msgs if midi_msgs else [],
            duration=duration,
            sample_rate=float(sr),
            num_channels=max(1, out_ch),
            buffer_size=bs,
            reset=False,
        )

        out = np.asarray(result, dtype=np.float32)
        if out.ndim == 2:
            # pedalboard returns (channels, samples)
            out_t = out.T  # → (samples, channels)
        elif out.ndim == 1:
            out_t = out.reshape(-1, 1)
        else:
            out_t = np.zeros((bs, max(1, out_ch)), dtype=np.float32)

        audio.write_output(out_t, min(bs, out_t.shape[0]))

    except Exception as e:
        wlog.debug("Instrument process error: %s", e)
        audio.write_silence(bs)

    # Small sleep to yield CPU when no MIDI pending
    if not midi_msgs:
        time.sleep(0.001)


# ---------------------------------------------------------------------------
# CLI entry point: python3 -m pydaw.plugin_workers.vst3_worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="VST3 Sandbox Worker (pedalboard)")
    parser.add_argument("--path", required=True, help="Plugin .vst3 path")
    parser.add_argument("--name", default="", help="Plugin name (for bundles)")
    parser.add_argument("--sr", type=int, default=48000, help="Sample rate")
    parser.add_argument("--bs", type=int, default=512, help="Block size")
    parser.add_argument("--ch", type=int, default=2, help="Channels")
    parser.add_argument("--socket", required=True, help="IPC socket path")
    parser.add_argument("--instrument", action="store_true",
                        help="Instrument mode (MIDI in)")
    parser.add_argument("--state", default="", help="State Base64 blob")

    args = parser.parse_args()

    # Create a minimal config-like object
    class _Config:
        track_id = "cli"
        slot_id = "0"
        plugin_path = args.path
        plugin_name = args.name
        plugin_type = "vst3"
        sample_rate = args.sr
        block_size = args.bs
        channels = args.ch
        state_b64 = args.state
        is_instrument = args.instrument

    # Create shared audio buffers (for CLI testing)
    try:
        from pydaw.services.plugin_ipc import PingPongAudioBuffer
        in_buf = PingPongAudioBuffer(
            name="cli_in", max_frames=args.bs * 4, channels=args.ch)
        out_buf = PingPongAudioBuffer(
            name="cli_out", max_frames=args.bs * 4, channels=args.ch)
        in_buf.create()
        out_buf.create()
    except Exception as e:
        print(f"Buffer creation failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        vst3_worker_entry(_Config(), in_buf, out_buf, args.socket)
    finally:
        in_buf.close()
        out_buf.close()
