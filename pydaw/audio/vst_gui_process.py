#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone VST3/VST2 native editor subprocess helper.

Launched by Vst3AudioFxWidget via QProcess.  Loads one VST plugin, shows
its native editor window, and maintains bidirectional parameter sync with
the parent DAW process via JSON-Lines over stdout/stdin.

Usage (internal, called by Vst3AudioFxWidget):
    python3 vst_gui_process.py <plugin_path> [plugin_name]
                               [--title WINDOW_TITLE] [--track TRACK_NAME]

Exit codes:
    0  — editor closed normally
    1  — plugin could not be loaded
    2  — show_editor() not available / not supported on this platform
    3  — pedalboard not installed

Protocol — stdout (subprocess → parent), one JSON line per event:
    {"event": "ready",   "plugin": "<n>", "params": [{"name":..,"value":..}, ...]}
    {"event": "param",   "name": "<param>",  "value": <float>}
    {"event": "closed"}
    {"event": "error",   "msg": "<reason>"}

Protocol — stdin (parent → subprocess), one JSON line per command:
    {"cmd": "set_param", "name": "<param>", "value": <float>}
    {"cmd": "quit"}

v0.0.20.377 — Korrekte pedalboard Parameter-API (plugin.parameters dict +
               param.raw_value); robuste Snapshot-Logik; QPushButton-
               deleted-Guard im Parent via Widget-weak-ref.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional


# ── Helpers ──────────────────────────────────────────────────────────────────

_stdout_lock = threading.Lock()


def _emit(obj: dict) -> None:
    """Write one JSON event line to stdout — thread-safe."""
    try:
        line = json.dumps(obj, ensure_ascii=False)
        with _stdout_lock:
            print(line, flush=True)
    except Exception:
        pass


def _parse_args() -> tuple[str, str, str, str]:
    """Return (plugin_path, plugin_name, window_title, track_name)."""
    args = sys.argv[1:]
    positional: List[str] = []
    window_title = ""
    track_name = ""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--title" and i + 1 < len(args):
            window_title = args[i + 1]
            i += 2
        elif a == "--track" and i + 1 < len(args):
            track_name = args[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1
    plugin_path = positional[0] if positional else ""
    plugin_name = positional[1] if len(positional) > 1 else ""
    return plugin_path, plugin_name, window_title, track_name


def _load_plugin(path: str, plugin_name: str) -> Any:
    """Load a VST plugin via pedalboard."""
    import pedalboard
    if plugin_name:
        try:
            return pedalboard.load_plugin(path, plugin_name=plugin_name)
        except TypeError:
            return pedalboard.load_plugin(path, plugin_name)
    return pedalboard.load_plugin(path)


def _snapshot_params(plugin: Any) -> Dict[str, float]:
    """Snapshot all current parameter values using pedalboard's official API.

    pedalboard exposes a `.parameters` dict:  name (str) → AudioProcessorParameter
    Each AudioProcessorParameter has `.raw_value` (float) for the current value.

    v0.0.20.377 — replaced broken dir()-based fallback with proper API.
    """
    out: Dict[str, float] = {}
    try:
        params = plugin.parameters  # dict: name → AudioProcessorParameter
        for name, param in params.items():
            try:
                out[str(name)] = float(param.raw_value)
            except Exception:
                # Fallback: some pedalboard builds expose value directly as attr
                try:
                    v = getattr(plugin, name, None)
                    if isinstance(v, (int, float, bool)):
                        out[str(name)] = float(v)
                except Exception:
                    pass
    except Exception:
        pass
    return out


# ── Background threads ────────────────────────────────────────────────────────

class _StdinReader(threading.Thread):
    """Reads JSON commands from stdin and applies them to the plugin."""

    def __init__(self, plugin: Any, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="vst-stdin-reader")
        self._plugin = plugin
        self._stop = stop_event

    def run(self) -> None:
        try:
            for raw in sys.stdin:
                if self._stop.is_set():
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    cmd = json.loads(raw)
                except Exception:
                    continue
                action = cmd.get("cmd", "")
                if action == "set_param":
                    name = str(cmd.get("name", ""))
                    value = cmd.get("value")
                    if name and value is not None:
                        try:
                            # Use raw_value setter (normalized 0-1) via parameters dict
                            params = self._plugin.parameters
                            if name in params:
                                param = params[name]
                                if getattr(param, "is_boolean", False):
                                    setattr(self._plugin, name, bool(float(value) >= 0.5))
                                else:
                                    param.raw_value = float(value)
                            else:
                                setattr(self._plugin, name, float(value))
                        except Exception:
                            try:
                                setattr(self._plugin, name, float(value))
                            except Exception:
                                pass
                elif action == "quit":
                    self._stop.set()
                    break
        except Exception:
            pass


class _ParamPoller(threading.Thread):
    """Polls plugin params every INTERVAL_S and emits changes via stdout.

    v0.0.20.459: Robust preset-change detection via TWO methods:
    1. Batch detection: if >5 params change in a single poll, it's a preset switch
    2. raw_state hash: backup check every ~500ms

    When a preset switch is detected, the full raw_state blob is sent as Base64
    so the host can apply it to the audio-engine plugin instance.
    """

    INTERVAL_S = 0.08  # 80 ms
    STATE_CHECK_INTERVAL = 8  # every 8th poll ≈ 640ms
    BATCH_THRESHOLD = 10  # if this many params change at once → preset switch

    def __init__(self, plugin: Any, stop_event: threading.Event,
                 initial_params: Dict[str, float]) -> None:
        super().__init__(daemon=True, name="vst-param-poller")
        self._plugin = plugin
        self._stop = stop_event
        self._last: Dict[str, float] = dict(initial_params)
        self._poll_count = 0
        self._last_state_hash = self._get_state_hash()
        self._state_send_cooldown = 0  # prevent rapid re-sends

    def _get_state_hash(self) -> str:
        try:
            import hashlib
            raw = getattr(self._plugin, "raw_state", None)
            if raw is not None:
                data = bytes(raw) if isinstance(raw, (memoryview, bytearray)) else raw
                if isinstance(data, bytes) and len(data) > 0:
                    return hashlib.md5(data).hexdigest()
        except Exception:
            pass
        return ""

    def _get_state_b64(self) -> str:
        try:
            import base64
            raw = getattr(self._plugin, "raw_state", None)
            if raw is not None:
                data = bytes(raw) if isinstance(raw, (memoryview, bytearray)) else raw
                if isinstance(data, bytes) and len(data) > 0:
                    return base64.b64encode(data).decode("ascii")
        except Exception:
            pass
        return ""

    def _send_state_blob(self, reason: str) -> None:
        """Send the full plugin state as a 'state' event."""
        if self._state_send_cooldown > 0:
            return
        blob = self._get_state_b64()
        if blob:
            _emit({"event": "state", "blob": blob})
            self._last_state_hash = self._get_state_hash()
            # Update _last with CURRENT values (not clear!) so next poll
            # only detects NEW changes, not all 775 params again
            try:
                self._last = _snapshot_params(self._plugin)
            except Exception:
                pass
            self._state_send_cooldown = 8  # ~640ms cooldown
            import sys
            print(f"[VST-POLLER] State blob sent ({reason}, {len(blob)} chars b64)",
                  file=sys.stderr, flush=True)

    def run(self) -> None:
        import sys
        print("[VST-POLLER] Started (batch_threshold={}, interval={}ms)".format(
            self.BATCH_THRESHOLD, int(self.INTERVAL_S * 1000)),
            file=sys.stderr, flush=True)

        while not self._stop.is_set():
            if self._state_send_cooldown > 0:
                self._state_send_cooldown -= 1

            # ── Poll parameters ─────────────────────────────────────────
            changed_count = 0
            try:
                current = _snapshot_params(self._plugin)
                for name, val in current.items():
                    prev = self._last.get(name)
                    if prev is None or abs(val - prev) > 1e-7:
                        self._last[name] = val
                        changed_count += 1
                        _emit({"event": "param", "name": name, "value": val})
            except Exception:
                pass

            # ── Method 1: Batch detection ───────────────────────────────
            # Many params changing at once = preset switch
            if changed_count >= self.BATCH_THRESHOLD:
                self._send_state_blob(f"batch={changed_count}")

            # ── Method 2: raw_state hash check (backup) ─────────────────
            self._poll_count += 1
            if self._poll_count >= self.STATE_CHECK_INTERVAL:
                self._poll_count = 0
                try:
                    h = self._get_state_hash()
                    if h and h != self._last_state_hash:
                        self._send_state_blob("hash_changed")
                except Exception:
                    pass

            time.sleep(self.INTERVAL_S)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    plugin_path, plugin_name, window_title, track_name = _parse_args()

    if not plugin_path:
        _emit({"event": "error", "msg": "No plugin path supplied"})
        return 1

    # ── pedalboard check ────────────────────────────────────────────────────
    try:
        import pedalboard  # noqa: F401
    except ImportError:
        _emit({"event": "error", "msg": "pedalboard not installed (pip install pedalboard)"})
        return 3

    # ── load plugin ─────────────────────────────────────────────────────────
    try:
        plugin = _load_plugin(plugin_path, plugin_name)
    except Exception as exc:
        _emit({"event": "error", "msg": f"Load failed: {exc}"})
        return 1

    # ── initial param snapshot ──────────────────────────────────────────────
    initial_params = _snapshot_params(plugin)
    params_list = [{"name": k, "value": v} for k, v in sorted(initial_params.items())]

    disp_name = plugin_name or os.path.basename(plugin_path)
    _emit({"event": "ready", "plugin": disp_name, "params": params_list})

    # ── show_editor() check ─────────────────────────────────────────────────
    show_fn = getattr(plugin, "show_editor", None)
    if not callable(show_fn):
        _emit({"event": "error", "msg": "show_editor() not available for this plugin"})
        return 2

    # ── build window title ──────────────────────────────────────────────────
    if not window_title:
        parts = [disp_name]
        if track_name:
            parts.append(f"[{track_name}]")
        parts.append("— Py_DAW")
        window_title = "  ".join(parts)

    # ── start background threads ────────────────────────────────────────────
    stop_event = threading.Event()
    stdin_reader = _StdinReader(plugin, stop_event)
    param_poller = _ParamPoller(plugin, stop_event, initial_params)
    stdin_reader.start()
    param_poller.start()

    # ── show editor (blocks until window closed) ────────────────────────────
    try:
        try:
            show_fn(window_title=window_title)
        except TypeError:
            try:
                show_fn(window_title)
            except TypeError:
                show_fn()
        _emit({"event": "closed"})
        return 0
    except KeyboardInterrupt:
        _emit({"event": "closed"})
        return 0
    except Exception as exc:
        _emit({"event": "error", "msg": f"show_editor() failed: {exc}"})
        return 2
    finally:
        stop_event.set()


if __name__ == "__main__":
    sys.exit(main())
