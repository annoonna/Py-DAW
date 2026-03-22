# -*- coding: utf-8 -*-
"""LV2 + LADSPA Worker Process — Sandboxed plugin hosting.

v0.0.20.706 — Phase P4A/P4B

Runs as a subprocess. Loads LV2 plugins via lilv or LADSPA plugins
via ctypes, processes audio from shared memory, handles params via IPC.

LV2: Full support (audio, MIDI, state, parameters)
LADSPA: FX only (no state save — parameter snapshot instead)
"""
from __future__ import annotations

import base64
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    np = None  # type: ignore
    _NP_OK = False


def lv2_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
) -> None:
    """LV2 worker subprocess entry point."""
    _format_worker_entry(config, input_buf, output_buf, ipc_socket_path, "lv2")


def ladspa_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
) -> None:
    """LADSPA worker subprocess entry point."""
    _format_worker_entry(config, input_buf, output_buf, ipc_socket_path, "ladspa")


def _format_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
    fmt: str,
) -> None:
    """Shared worker entry for LV2 and LADSPA plugins."""
    tag = fmt.upper()
    wlog = logging.getLogger(
        f"pydaw.{fmt}_worker.{config.track_id}.{config.slot_id}")
    logging.basicConfig(level=logging.INFO,
                        format=f"[{tag}-WRK %(name)s] %(message)s",
                        stream=sys.stderr)

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

    sr = int(getattr(config, "sample_rate", 48000) or 48000)
    bs = int(getattr(config, "block_size", 512) or 512)
    plugin = None

    # Load plugin
    try:
        if fmt == "lv2":
            # v0.0.20.709: P4A — Worker-eigene URID Map
            # Force-create a fresh lilv.World in this subprocess so the
            # URID map is fully independent from the main process.
            # This prevents stale state after fork() and ensures clean
            # plugin discovery + instantiation.
            try:
                from pydaw.audio import lv2_host as _lv2mod
                _reg = getattr(_lv2mod, "_registry", None)
                if _reg is not None and hasattr(_reg, "_world"):
                    _reg._world = None  # force re-creation on next access
                    wlog.info("LV2 worker: forced fresh lilv.World (own URID map)")
            except Exception:
                pass

            from pydaw.audio.lv2_host import Lv2Fx
            plugin = Lv2Fx(
                uri=config.plugin_path,
                sr=sr,
                track_id=getattr(config, "track_id", ""),
                device_id=getattr(config, "slot_id", ""),
                rt_params=None,
                params={},
            )
        elif fmt == "ladspa":
            from pydaw.audio.ladspa_host import LadspaFx
            plugin = LadspaFx(
                path=config.plugin_path,
                sr=sr,
                track_id=getattr(config, "track_id", ""),
                device_id=getattr(config, "slot_id", ""),
                rt_params=None,
                params={},
            )
    except Exception as e:
        wlog.error("%s load failed: %s", tag, e)
        ipc.send_event({"evt": "error", "message": f"Load failed: {e}"})
        ipc.stop()
        return

    if plugin is None:
        ipc.send_event({"evt": "error", "message": f"{tag} plugin is None"})
        ipc.stop()
        return

    # State restore (LV2 only — LADSPA has no state)
    state_b64 = str(getattr(config, "state_b64", "") or "")
    if state_b64 and fmt == "lv2":
        try:
            raw = base64.b64decode(state_b64)
            if hasattr(plugin, "set_state"):
                plugin.set_state(raw)
            elif hasattr(plugin, "load_state"):
                plugin.load_state(raw)
        except Exception as e:
            wlog.warning("State restore failed: %s", e)

    # Parameter snapshot for LADSPA (no native state)
    _param_snapshot: Dict[str, float] = {}

    bypassed = False

    def handle_command(msg: dict) -> Optional[dict]:
        nonlocal bypassed
        cmd = msg.get("cmd", "")
        if cmd == "ping":
            return {"evt": "pong", "seq": msg.get("seq", 0)}
        elif cmd == "set_param":
            pid = str(msg.get("param_id", ""))
            val = float(msg.get("value", 0.0))
            _param_snapshot[pid] = val
            try:
                if hasattr(plugin, "set_parameter"):
                    plugin.set_parameter(pid, val)
                elif hasattr(plugin, "set_param"):
                    plugin.set_param(pid, val)
            except Exception:
                pass
        elif cmd == "bypass":
            bypassed = bool(msg.get("enabled", False))
        elif cmd == "get_state":
            b64 = ""
            if fmt == "lv2":
                try:
                    raw = b""
                    if hasattr(plugin, "get_state"):
                        raw = plugin.get_state()
                    elif hasattr(plugin, "save_state"):
                        raw = plugin.save_state()
                    if raw:
                        b64 = base64.b64encode(raw).decode("ascii")
                except Exception:
                    pass
            else:
                # LADSPA: serialize param snapshot as JSON
                import json
                try:
                    b64 = base64.b64encode(
                        json.dumps(_param_snapshot).encode()
                    ).decode("ascii")
                except Exception:
                    pass
            return {"evt": "state", "state_b64": b64}
        elif cmd == "load_state":
            b64_val = msg.get("state_b64", "")
            if b64_val:
                if fmt == "lv2":
                    try:
                        raw = base64.b64decode(b64_val)
                        if hasattr(plugin, "set_state"):
                            plugin.set_state(raw)
                        elif hasattr(plugin, "load_state"):
                            plugin.load_state(raw)
                    except Exception:
                        pass
                else:
                    # LADSPA: restore param snapshot
                    import json
                    try:
                        snap = json.loads(base64.b64decode(b64_val))
                        for k, v in snap.items():
                            _param_snapshot[k] = float(v)
                            if hasattr(plugin, "set_parameter"):
                                plugin.set_parameter(k, float(v))
                            elif hasattr(plugin, "set_param"):
                                plugin.set_param(k, float(v))
                    except Exception:
                        pass
        elif cmd == "get_latency":
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
    ipc.send_event({
        "evt": "ready",
        "plugin_name": getattr(config, "plugin_name", ""),
        "param_count": 0,
        "is_instrument": False,
    })
    wlog.info("%s worker ready: %s", tag, config.plugin_path)

    audio = WorkerAudioHandler(input_buf, output_buf)

    while True:
        try:
            block = audio.read_input()
            if block is None:
                time.sleep(0.0005)
                continue
            frames = len(block)
            if bypassed:
                audio.write_output(block, frames)
            else:
                try:
                    plugin.process_inplace(block, frames, sr)
                    audio.write_output(block, frames)
                except Exception:
                    audio.write_output(block, frames)
        except SystemExit:
            break
        except Exception as e:
            wlog.error("Audio loop error: %s", e)
            time.sleep(0.001)

    try:
        ipc.stop()
    except Exception:
        pass
    wlog.info("%s worker shutdown", tag)
