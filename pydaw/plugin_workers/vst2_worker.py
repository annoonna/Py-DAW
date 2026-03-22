# -*- coding: utf-8 -*-
"""VST2 Worker Process — Sandboxed VST2 plugin hosting via ctypes.

v0.0.20.706 — Phase P3A/P3B

Runs as a subprocess. Loads a VST2 plugin via the existing vst2_host.py
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


# ---------------------------------------------------------------------------
# v0.0.20.711: P3B — VST2 Editor via effEditOpen + X11
# ---------------------------------------------------------------------------

def _vst2_show_editor(plugin: Any, wlog: Any) -> Tuple[Any, bool]:
    """Open VST2 native editor window via effEditOpen + X11.

    Creates an X11 window and passes it to the plugin.
    Returns (window_handle, success).

    If X11 is not available (headless server), returns (None, False).
    """
    # Check if plugin supports editor
    if not hasattr(plugin, "_effect") and not hasattr(plugin, "_dll"):
        wlog.debug("No _effect attribute — editor not supported")
        return None, False

    try:
        import ctypes
        import ctypes.util

        # Try to open X11 display
        x11_path = ctypes.util.find_library("X11")
        if not x11_path:
            wlog.info("libX11 not found — editor not available")
            return None, False

        libx11 = ctypes.cdll.LoadLibrary(x11_path)

        # Open display
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        display = libx11.XOpenDisplay(None)
        if not display:
            wlog.info("Cannot open X11 display — headless?")
            return None, False

        # Get default screen + root window
        screen = libx11.XDefaultScreen(display)
        root = libx11.XDefaultRootWindow(display)

        # Query plugin editor size (effEditGetRect)
        width, height = 800, 600
        try:
            # effEditGetRect = 13
            rect_ptr = ctypes.c_void_p(0)
            dispatcher = getattr(plugin, "_dispatch", None)
            if callable(dispatcher):
                dispatcher(13, 0, 0, ctypes.byref(rect_ptr), 0.0)
                if rect_ptr.value:
                    # ERect struct: short top, left, bottom, right
                    class ERect(ctypes.Structure):
                        _fields_ = [
                            ("top", ctypes.c_short),
                            ("left", ctypes.c_short),
                            ("bottom", ctypes.c_short),
                            ("right", ctypes.c_short),
                        ]
                    rect = ctypes.cast(rect_ptr, ctypes.POINTER(ERect)).contents
                    width = max(200, int(rect.right - rect.left))
                    height = max(100, int(rect.bottom - rect.top))
        except Exception:
            pass

        # Create X11 window
        window = libx11.XCreateSimpleWindow(
            display, root,
            100, 100,  # x, y
            width, height,
            1,  # border_width
            0,  # border color (black)
            0xFFFFFF,  # background (white)
        )
        if not window:
            libx11.XCloseDisplay(display)
            return None, False

        # Set window title
        title = f"VST2 Editor — {getattr(plugin, '_name', 'Plugin')} — Py_DAW"
        libx11.XStoreName(display, window, title.encode("utf-8"))

        # Map (show) the window
        libx11.XMapWindow(display, window)
        libx11.XFlush(display)

        # Send effEditOpen (opcode 14) with X11 window handle
        try:
            dispatcher = getattr(plugin, "_dispatch", None)
            if callable(dispatcher):
                dispatcher(14, 0, 0, ctypes.c_void_p(window), 0.0)
                wlog.info("VST2 effEditOpen sent (X11 window=%d, %dx%d)",
                          window, width, height)
            else:
                wlog.warning("No _dispatch method — cannot send effEditOpen")
                libx11.XDestroyWindow(display, window)
                libx11.XCloseDisplay(display)
                return None, False
        except Exception as e:
            wlog.warning("effEditOpen failed: %s", e)
            libx11.XDestroyWindow(display, window)
            libx11.XCloseDisplay(display)
            return None, False

        # Return handle tuple for cleanup
        return {"display": display, "window": window, "libx11": libx11}, True

    except Exception as e:
        wlog.info("VST2 editor setup failed: %s", e)
        return None, False


def _vst2_hide_editor(plugin: Any, editor_handle: Any, wlog: Any) -> None:
    """Close VST2 editor and destroy X11 window."""
    if editor_handle is None:
        return

    try:
        # effEditClose = 15
        dispatcher = getattr(plugin, "_dispatch", None)
        if callable(dispatcher):
            dispatcher(15, 0, 0, None, 0.0)
    except Exception:
        pass

    try:
        display = editor_handle.get("display")
        window = editor_handle.get("window")
        libx11 = editor_handle.get("libx11")
        if display and window and libx11:
            libx11.XDestroyWindow(display, window)
            libx11.XCloseDisplay(display)
            wlog.info("VST2 editor window destroyed")
    except Exception as e:
        wlog.debug("Editor cleanup: %s", e)


def vst2_worker_entry(
    config: Any,
    input_buf: Any,
    output_buf: Any,
    ipc_socket_path: str,
) -> None:
    """VST2 worker subprocess entry point."""
    wlog = logging.getLogger(
        f"pydaw.vst2_worker.{config.track_id}.{config.slot_id}")
    logging.basicConfig(level=logging.INFO,
                        format="[VST2-WRK %(name)s] %(message)s",
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

    # Load VST2 plugin
    sr = int(getattr(config, "sample_rate", 48000) or 48000)
    bs = int(getattr(config, "block_size", 512) or 512)
    is_instrument = bool(getattr(config, "is_instrument", False))
    plugin = None
    plugin_fx = None
    plugin_inst = None

    try:
        if is_instrument:
            from pydaw.audio.vst2_host import Vst2InstrumentEngine
            plugin_inst = Vst2InstrumentEngine(
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
            from pydaw.audio.vst2_host import Vst2Fx
            plugin_fx = Vst2Fx(
                path=config.plugin_path,
                track_id=config.track_id,
                device_id=config.slot_id,
                rt_params=None,
                params={},
                sr=sr,
                max_frames=bs * 2,
            )
            plugin = plugin_fx
    except Exception as e:
        wlog.error("VST2 load failed: %s", e)
        ipc.send_event({"evt": "error", "message": f"Load failed: {e}"})
        ipc.stop()
        return

    if plugin is None or not getattr(plugin, "_ok", False):
        err = getattr(plugin, "_err", "unknown")
        wlog.error("VST2 plugin not OK: %s", err)
        ipc.send_event({"evt": "error", "message": f"Plugin not OK: {err}"})
        ipc.stop()
        return

    # Restore state
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

    # Worker state
    bypassed = False
    pending_midi: List[Tuple[bytes, float]] = []
    editor_window = None  # v0.0.20.711: P3B X11 window handle
    editor_shown = False

    def handle_command(msg: dict) -> Optional[dict]:
        nonlocal bypassed, pending_midi, editor_window, editor_shown
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
                elif hasattr(plugin, "get_raw_state_b64"):
                    return {"evt": "state", "state_b64": plugin.get_raw_state_b64()}
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

        # v0.0.20.711: P3B — VST2 Editor via effEditOpen + X11
        elif cmd == "show_editor":
            try:
                editor_window, editor_shown = _vst2_show_editor(
                    plugin, wlog)
                if editor_shown:
                    return {"evt": "editor_shown"}
                else:
                    return {"evt": "error",
                            "message": "VST2 editor not supported or X11 unavailable"}
            except Exception as e:
                wlog.warning("show_editor failed: %s", e)
                return {"evt": "error", "message": f"show_editor: {e}"}

        elif cmd == "hide_editor":
            try:
                _vst2_hide_editor(plugin, editor_window, wlog)
                editor_window = None
                editor_shown = False
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
            else:
                if pitch >= 0:
                    pending_midi.append((bytes([0x80, pitch & 0x7F, 0]), 0.0))
        elif cmd == "all_notes_off":
            if plugin_inst:
                if hasattr(plugin_inst, "all_notes_off"):
                    plugin_inst.all_notes_off()
                else:
                    plugin_inst.note_off(-1)
        elif cmd == "midi":
            events = msg.get("events", [])
            for ev in events:
                try:
                    if isinstance(ev, (list, tuple)) and len(ev) >= 2:
                        midi_bytes = bytes(int(b) & 0xFF for b in ev[:3])
                        pending_midi.append((midi_bytes, 0.0))
                except Exception:
                    continue
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
    wlog.info("VST2 worker ready: %s (inst=%s)", config.plugin_path, is_instrument)

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
                        plugin_fx.process_inplace(block, frames, sr)
                        audio.write_output(block, frames)
                    except Exception:
                        audio.write_output(block, frames)
        except SystemExit:
            break
        except Exception as e:
            wlog.error("Audio loop error: %s", e)
            time.sleep(0.001)

    # Cleanup editor if shown
    if editor_shown and editor_window:
        try:
            _vst2_hide_editor(plugin, editor_window, wlog)
        except Exception:
            pass

    try:
        ipc.stop()
    except Exception:
        pass
    wlog.info("VST2 worker shutdown")
