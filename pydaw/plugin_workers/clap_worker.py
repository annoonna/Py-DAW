# -*- coding: utf-8 -*-
"""CLAP Worker Process — Sandboxed CLAP plugin hosting via ctypes.

v0.0.20.706 — Phase P5A/P5B

Runs as a subprocess. Loads a CLAP plugin via the existing clap_host.py
ctypes layer, processes audio from shared memory, handles MIDI + state via IPC.

Supports both FX and Instrument modes.
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


def clap_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
) -> None:
    """CLAP worker subprocess entry point."""
    wlog = logging.getLogger(
        f"pydaw.clap_worker.{config.track_id}.{config.slot_id}")
    logging.basicConfig(level=logging.INFO,
                        format="[CLAP-WRK %(name)s] %(message)s",
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
    is_instrument = bool(getattr(config, "is_instrument", False))
    plugin = None
    plugin_fx = None
    plugin_inst = None

    try:
        if is_instrument:
            from pydaw.audio.clap_host import ClapInstrumentEngine
            plugin_inst = ClapInstrumentEngine(
                path=config.plugin_path,
                track_id=config.track_id,
                device_id=config.slot_id,
                rt_params=None,
                params={},
                sr=sr,
                max_frames=bs * 2,
            )
            plugin = plugin_inst
        else:
            # Try to import the FX class
            from pydaw.audio.clap_host import ClapAudioFxWidget
            # ClapAudioFxWidget is a QWidget — we need a headless wrapper
            # Use the lower-level CLAP host instead
            try:
                from pydaw.audio.clap_host import ClapPluginInstance
                plugin_fx = ClapPluginInstance(
                    path=config.plugin_path,
                    sr=sr,
                )
                plugin = plugin_fx
            except (ImportError, AttributeError):
                # Fall back to trying ClapAudioFxWidget headless
                wlog.warning("ClapPluginInstance not available, using generic loader")
                plugin = None
    except Exception as e:
        wlog.error("CLAP load failed: %s", e)
        ipc.send_event({"evt": "error", "message": f"Load failed: {e}"})
        ipc.stop()
        return

    if plugin is None:
        ipc.send_event({"evt": "error", "message": "CLAP plugin load failed"})
        ipc.stop()
        return

    # State restore
    state_b64 = str(getattr(config, "state_b64", "") or "")
    if state_b64:
        try:
            raw = base64.b64decode(state_b64)
            if hasattr(plugin, "set_state"):
                plugin.set_state(raw)
            elif hasattr(plugin, "load_state"):
                plugin.load_state(raw)
        except Exception as e:
            wlog.warning("State restore failed: %s", e)

    bypassed = False
    pending_midi: List[Tuple[bytes, float]] = []

    def handle_command(msg: dict) -> Optional[dict]:
        nonlocal bypassed, pending_midi
        cmd = msg.get("cmd", "")
        if cmd == "ping":
            return {"evt": "pong", "seq": msg.get("seq", 0)}
        elif cmd == "set_param":
            pid = str(msg.get("param_id", ""))
            val = float(msg.get("value", 0.0))
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
            return {"evt": "state", "state_b64": b64}
        elif cmd == "load_state":
            try:
                raw = base64.b64decode(msg.get("state_b64", ""))
                if raw:
                    if hasattr(plugin, "set_state"):
                        plugin.set_state(raw)
                    elif hasattr(plugin, "load_state"):
                        plugin.load_state(raw)
            except Exception:
                pass
        elif cmd == "note_on":
            pitch = max(0, min(127, int(msg.get("pitch", 60))))
            vel = max(1, min(127, int(msg.get("velocity", 100))))
            if plugin_inst:
                plugin_inst.note_on(pitch, vel)
            else:
                pending_midi.append((bytes([0x90, pitch, vel]), 0.0))
        elif cmd == "note_off":
            pitch = int(msg.get("pitch", -1))
            if plugin_inst:
                plugin_inst.note_off(pitch)
        elif cmd == "all_notes_off":
            if plugin_inst and hasattr(plugin_inst, "all_notes_off"):
                plugin_inst.all_notes_off()
            elif plugin_inst:
                plugin_inst.note_off(-1)
        elif cmd == "midi":
            events = msg.get("events", [])
            for ev in events:
                try:
                    if isinstance(ev, (list, tuple)) and len(ev) >= 2:
                        pending_midi.append(
                            (bytes(int(b) & 0xFF for b in ev[:3]), 0.0))
                except Exception:
                    continue
        elif cmd == "show_editor":
            # v0.0.20.711: P5B — CLAP GUI via clap_plugin_gui + X11
            try:
                shown = False
                # Method 1: Use existing show_editor() (high-level wrapper)
                if hasattr(plugin, "show_editor") and callable(getattr(plugin, "show_editor", None)):
                    plugin.show_editor()
                    shown = True
                # Method 2: Try clap_plugin_gui.create() via the host
                elif hasattr(plugin, "_clap_gui_create"):
                    try:
                        # Create X11 window for embedding
                        import ctypes, ctypes.util
                        x11_path = ctypes.util.find_library("X11")
                        if x11_path:
                            libx11 = ctypes.cdll.LoadLibrary(x11_path)
                            libx11.XOpenDisplay.restype = ctypes.c_void_p
                            display = libx11.XOpenDisplay(None)
                            if display:
                                root = libx11.XDefaultRootWindow(display)
                                win = libx11.XCreateSimpleWindow(
                                    display, root, 100, 100, 800, 600,
                                    1, 0, 0xFFFFFF)
                                if win:
                                    title = f"CLAP Editor — Py_DAW"
                                    libx11.XStoreName(display, win, title.encode())
                                    libx11.XMapWindow(display, win)
                                    libx11.XFlush(display)
                                    # Pass X11 window to CLAP GUI
                                    plugin._clap_gui_create(win)
                                    shown = True
                                    wlog.info("CLAP GUI created with X11 window=%d", win)
                    except Exception as gui_e:
                        wlog.debug("clap_plugin_gui.create failed: %s", gui_e)

                if shown:
                    return {"evt": "editor_shown"}
                else:
                    return {"evt": "error", "message": "CLAP editor not available"}
            except Exception as e:
                return {"evt": "error", "message": f"show_editor: {e}"}
        elif cmd == "hide_editor":
            try:
                if hasattr(plugin, "hide_editor"):
                    plugin.hide_editor()
                # v0.0.20.711: P5B — also try clap_plugin_gui.destroy()
                if hasattr(plugin, "_clap_gui_destroy"):
                    try:
                        plugin._clap_gui_destroy()
                    except Exception:
                        pass
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
        "is_instrument": is_instrument,
    })
    wlog.info("CLAP worker ready: %s (inst=%s)", config.plugin_path, is_instrument)

    audio = WorkerAudioHandler(input_buf, output_buf)

    while True:
        try:
            if is_instrument and plugin_inst:
                out = plugin_inst.pull(bs, sr)
                if out is not None:
                    audio.write_output(out, min(bs, len(out)))
                else:
                    audio.write_silence(bs)
                time.sleep(0.001)
            else:
                block = audio.read_input()
                if block is None:
                    time.sleep(0.0005)
                    continue
                frames = len(block)
                if bypassed:
                    audio.write_output(block, frames)
                else:
                    try:
                        if hasattr(plugin, "process_inplace"):
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
    wlog.info("CLAP worker shutdown")
