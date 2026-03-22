# -*- coding: utf-8 -*-
"""VST3/VST2 hosting helpers for Py_DAW via pedalboard (Spotify).

Design goals
------------
- SAFE: if loading fails, nothing crashes; VST FX becomes a no-op.
- Real-time friendly: allocate at build time; process_inplace() uses
  pre-allocated numpy arrays + pedalboard's process().
- Backward compatible: plain file paths still work; multi-plugin bundles can
  additionally address one explicit sub-plugin via ``plugin_name``.
- Browser-friendly: scanner/UI can enumerate multi-plugin bundles like
  ``lsp-plugins.vst3`` into separate selectable entries.

Dependencies
------------
- pedalboard (pip install pedalboard)
- numpy (already a project dependency)

v0.0.20.364 — Multi-plugin bundle helpers + exact sub-plugin loading
"""

from __future__ import annotations

import base64
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, unquote

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

try:
    import pedalboard
    _PEDALBOARD_OK = True
except Exception:
    pedalboard = None  # type: ignore
    _PEDALBOARD_OK = False


_PLUGIN_REF_SEP = "::pydaw_plugin::"


# ─── Public API ─────────────────────────────────────────────────────────────

def is_available() -> bool:
    """Return True if pedalboard is importable."""
    return _PEDALBOARD_OK


def availability_hint() -> str:
    if _PEDALBOARD_OK:
        ver = getattr(pedalboard, "__version__", "?")
        return f"pedalboard {ver} OK"
    return "pedalboard nicht installiert (pip install pedalboard)"


def build_plugin_reference(path: str, plugin_name: str = "") -> str:
    """Build one stable reference string for a VST file + optional sub-plugin.

    Plain paths remain unchanged for single-plugin files.
    Multi-plugin bundles append one encoded sub-plugin marker.
    """
    base = str(path or "")
    pname = str(plugin_name or "").strip()
    if not base or not pname:
        return base
    return f"{base}{_PLUGIN_REF_SEP}{quote(pname, safe='')}"


def split_plugin_reference(ref_or_path: str) -> Tuple[str, str]:
    """Split a stored reference back into filesystem path + plugin_name."""
    raw = str(ref_or_path or "")
    if _PLUGIN_REF_SEP not in raw:
        return raw, ""
    base, enc = raw.rsplit(_PLUGIN_REF_SEP, 1)
    try:
        return base, unquote(enc)
    except Exception:
        return base, enc


def resolve_plugin_reference(ref_or_path: str, plugin_name: str = "") -> Tuple[str, str]:
    """Resolve explicit plugin_name overrides on top of stored references."""
    base, ref_name = split_plugin_reference(ref_or_path)
    explicit = str(plugin_name or "").strip()
    return base, (explicit or ref_name)


def parse_multi_plugin_names(message: str) -> List[str]:
    """Parse pedalboard's 'contains N plugins' error into plugin names."""
    text = str(message or "")
    if "plugin_name" not in text or "contains" not in text:
        return []
    tail = text.split("following values:", 1)[1] if "following values:" in text else text
    out: List[str] = []
    seen = set()
    for name in re.findall(r'"([^"\n]+)"', tail):
        name = str(name or "").strip()
        if not name or name == "plugin_name":
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def probe_multi_plugin_names(path: str) -> List[str]:
    """Return sub-plugin names if the file contains multiple plugins.

    Safe fallback: returns [] when pedalboard is unavailable or the file is a
    normal single-plugin bundle.  Aborts after 15 s to protect against hangs.
    """
    if not _PEDALBOARD_OK:
        return []
    base = str(path or "")
    if not base:
        return []

    import concurrent.futures

    def _do_probe() -> List[str]:
        try:
            plugin = _load_pedalboard_plugin(base, "")
            try:
                del plugin
            except Exception:
                pass
            return []
        except Exception as exc:
            return parse_multi_plugin_names(str(exc))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_do_probe)
            return fut.result(timeout=15.0)
    except concurrent.futures.TimeoutError:
        import sys
        print(f"[VST3] probe_multi_plugin_names: timeout for {base!r}", file=sys.stderr)
        return []
    except Exception:
        return []


# ─── Internal helpers ───────────────────────────────────────────────────────

def _display_reference(path: str, plugin_name: str = "") -> str:
    return build_plugin_reference(path, plugin_name)


def _load_pedalboard_plugin(path: str, plugin_name: str = ""):
    if not _PEDALBOARD_OK:
        raise RuntimeError("pedalboard nicht installiert")
    base = str(path or "")
    pname = str(plugin_name or "").strip()
    if pname:
        try:
            return pedalboard.load_plugin(base, plugin_name=pname)
        except TypeError:
            return pedalboard.load_plugin(base, pname)
    return pedalboard.load_plugin(base)


def _coerce_channel_count(value: Any) -> int:
    """Best-effort conversion of plugin bus metadata to a usable channel count."""
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            iv = int(value)
            return iv if iv > 0 else 0
        if isinstance(value, (list, tuple)):
            for item in value:
                iv = _coerce_channel_count(item)
                if iv > 0:
                    return iv
            return 0
        if isinstance(value, dict):
            for key in ("channels", "count", "num_channels", "main", "default"):
                if key in value:
                    iv = _coerce_channel_count(value.get(key))
                    if iv > 0:
                        return iv
            return 0
        for key in ("channels", "count", "num_channels"):
            if hasattr(value, key):
                iv = _coerce_channel_count(getattr(value, key))
                if iv > 0:
                    return iv
        iv = int(value)
        return iv if iv > 0 else 0
    except Exception:
        return 0


def _read_plugin_channel_attr(plugin: Any, names: List[str]) -> int:
    for name in names:
        try:
            if not hasattr(plugin, name):
                continue
            value = getattr(plugin, name)
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    continue
            iv = _coerce_channel_count(value)
            if iv > 0:
                return iv
        except Exception:
            continue
    return 0


def _detect_plugin_channel_layout(plugin: Any) -> Tuple[int, int]:
    """Try to discover the main bus layout from pedalboard/native attrs."""
    if plugin is None:
        return 0, 0
    in_names = [
        "input_channel_count",
        "num_input_channels",
        "input_channels",
        "main_input_channel_count",
        "main_bus_input_channel_count",
        "main_input_channels",
        "num_inputs",
        "inputs",
    ]
    out_names = [
        "output_channel_count",
        "num_output_channels",
        "output_channels",
        "main_output_channel_count",
        "main_bus_output_channel_count",
        "main_output_channels",
        "num_outputs",
        "outputs",
    ]
    return _read_plugin_channel_attr(plugin, in_names), _read_plugin_channel_attr(plugin, out_names)


def _parse_layout_from_process_error(message: str) -> Tuple[int, int]:
    text = str(message or "")
    m = re.search(
        r"expects\s+(\d+)\s+input\s+channels?\s+and\s+(\d+)\s+output\s+channels?",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        try:
            return max(1, int(m.group(1))), max(1, int(m.group(2)))
        except Exception:
            return 0, 0
    return 0, 0

def _coerce_raw_state_bytes(value: Any) -> bytes:
    """Convert plugin raw_state payloads to bytes (best effort)."""
    try:
        if value is None:
            return b""
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, memoryview):
            return value.tobytes()
        if isinstance(value, str):
            return value.encode("utf-8")
        return bytes(value)
    except Exception:
        return b""


def _encode_raw_state_b64(value: Any) -> str:
    raw = _coerce_raw_state_bytes(value)
    if not raw:
        return ""
    try:
        return base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


def _decode_raw_state_b64(value: Any) -> bytes:
    text = str(value or "").strip()
    if not text:
        return b""
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except Exception:
        return b""


def _apply_raw_state_to_plugin(plugin: Any, state_b64: Any) -> bool:
    """Restore one Base64-encoded raw_state blob onto a pedalboard plugin."""
    raw = _decode_raw_state_b64(state_b64)
    if not raw or plugin is None:
        return False
    try:
        setattr(plugin, "raw_state", raw)
        return True
    except Exception:
        return False


def export_state_blob(vst_ref_or_path: str, params: Dict[str, Any] | None = None, plugin_name: str = "") -> str:
    """Create one Base64 raw_state blob from the current project-side params.

    Safety-first design: this helper loads a fresh plugin instance on the caller
    thread, applies the currently persisted parameter values and serializes
    ``plugin.raw_state``.  It intentionally does **not** touch the live DSP
    instance, so project save can embed state without racing the audio callback.
    """
    if not _PEDALBOARD_OK:
        return ""
    base, pname = resolve_plugin_reference(vst_ref_or_path, plugin_name)
    if not base:
        return ""
    payload = dict(params) if isinstance(params, dict) else {}
    try:
        plugin = _load_pedalboard_plugin(base, pname)
    except Exception as exc:
        print(f"[VST3] export_state_blob: load failed for {_display_reference(base, pname)}: {exc}", file=sys.stderr, flush=True)
        return ""

    try:
        infos = _extract_param_infos(plugin)
        for info in infos:
            if info.name not in payload:
                continue
            try:
                val = float(payload.get(info.name, info.default))
                val = max(info.minimum, min(info.maximum, val))
                setattr(plugin, info.name, val)
            except Exception:
                continue
        blob = _encode_raw_state_b64(getattr(plugin, "raw_state", b""))
        return blob
    except Exception as exc:
        print(f"[VST3] export_state_blob: state encode failed for {_display_reference(base, pname)}: {exc}", file=sys.stderr, flush=True)
        return ""
    finally:
        try:
            del plugin
        except Exception:
            pass


def embed_project_state_blobs(project: Any) -> int:
    """Embed Base64 raw_state blobs for external VST2/VST3 devices into project JSON.

    Returns the number of devices whose state blob was freshly updated.  Failures
    are tolerated; existing blobs stay untouched.
    """
    tracks = getattr(project, "tracks", None)
    if not isinstance(tracks, list):
        return 0
    updated = 0
    for track in tracks:
        chain = getattr(track, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            continue
        devices = chain.get("devices") or []
        if not isinstance(devices, list):
            continue
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get("plugin_id") or dev.get("type") or "")
            pid_norm = pid.lower()
            if not (pid_norm.startswith("ext.vst3:") or pid_norm.startswith("ext.vst2:")):
                continue
            params = dev.get("params")
            if not isinstance(params, dict):
                params = {}
                dev["params"] = params
            vst_ref = str(params.get("__ext_ref") or (pid.split(":", 1)[1] if ":" in pid else ""))
            plugin_name = str(params.get("__ext_plugin_name") or "")
            blob = export_state_blob(vst_ref, params, plugin_name)
            if blob:
                if str(params.get("__ext_state_b64") or "") != blob:
                    params["__ext_state_b64"] = blob
                    updated += 1
    return updated


# ─── Parameter descriptor ───────────────────────────────────────────────────

@dataclass
class Vst3ParamInfo:
    """Describes one VST parameter for UI building."""
    name: str
    label: str
    minimum: float = 0.0
    maximum: float = 1.0
    default: float = 0.0
    is_boolean: bool = False
    is_integer: bool = False
    units: str = ""


def _extract_param_infos(plugin: Any) -> List[Vst3ParamInfo]:
    """Read parameter descriptors from an already loaded pedalboard plugin."""
    try:
        params = plugin.parameters
    except Exception:
        return []
    result: List[Vst3ParamInfo] = []
    for name, param in params.items():
        try:
            mn = float(getattr(param, "minimum_value", 0.0))
            mx = float(getattr(param, "maximum_value", 1.0))
            dv = float(getattr(param, "default_value", 0.0))
            if mx > mn:
                dv = max(mn, min(mx, dv))
            is_bool = bool(getattr(param, "is_boolean", False))
            is_int = bool(getattr(param, "is_integer", False))
            # v0.0.20.378 — REMOVED wrong heuristic that set is_bool=True for all
            # params with 0-1 range.  pedalboard reports ALL VST3 params normalized
            # to [0.0, 1.0] via minimum_value/maximum_value — so the old check
            # "if mx==1.0 and mn==0.0" incorrectly turned every continuous param
            # (time_ms, lpf_hz, feedback …) into a checkbox.  Trust is_boolean only.
            units = str(getattr(param, "units", "") or "")
            result.append(Vst3ParamInfo(
                name=name,
                label=name,
                minimum=mn,
                maximum=mx,
                default=dv,
                is_boolean=is_bool,
                is_integer=is_int,
                units=units,
            ))
        except Exception:
            continue
    return result


def describe_controls(vst_ref_or_path: str, plugin_name: str = "") -> List[Vst3ParamInfo]:
    """Load the plugin and return parameter descriptors.

    ``vst_ref_or_path`` may either be a plain filesystem path or one reference
    created by :func:`build_plugin_reference`.
    Returns an empty list on failure (safe).
    """
    if not _PEDALBOARD_OK or not vst_ref_or_path:
        return []
    base, pname = resolve_plugin_reference(vst_ref_or_path, plugin_name)
    display_ref = _display_reference(base, pname)
    try:
        plugin = _load_pedalboard_plugin(base, pname)
    except Exception as exc:
        print(f"[VST3] describe_controls: load failed for {display_ref}: {exc}",
              file=sys.stderr, flush=True)
        return []
    return _extract_param_infos(plugin)


# ─── Vst3Fx — the RT audio-FX object ────────────────────────────────────────

class Vst3Fx:
    """Live VST Audio-FX wrapper, compatible with FxChain.process_inplace().

    Host side is always stereo ``(frames, 2)``.
    External plugins may expose mono or stereo main busses, therefore this
    wrapper adapts channel counts safely at the bridge boundary.
    If loading fails, ``_ok=False`` and processing becomes a safe no-op.
    """

    def __init__(
        self,
        path: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Dict[str, Any],
        sr: int = 44100,
        max_frames: int = 8192,
        plugin_name: str = "",
    ):
        self._ok = False
        self._err = ""
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self._params_init = dict(params) if isinstance(params, dict) else {}
        self._sr = int(sr) if sr else 44100
        self.max_frames = int(max_frames) if max_frames else 8192
        self._plugin = None
        self._param_infos: List[Vst3ParamInfo] = []
        self._prefix = f"afx:{self.track_id}:{self.device_id}:vst3:"
        self._pb_in: Any = None
        self._pb_out: Any = None
        self._input_channels = 2
        self._output_channels = 2
        self._last_process_error = ""

        explicit_name = str(plugin_name or self._params_init.get("__ext_plugin_name") or "")
        self.path, self.plugin_name = resolve_plugin_reference(path, explicit_name)
        self._display_ref = _display_reference(self.path, self.plugin_name)

        self._load()

    def _set_bus_layout(self, input_channels: int, output_channels: int) -> None:
        if np is None:
            return
        in_ch = max(1, int(input_channels or 2))
        out_ch = max(1, int(output_channels or in_ch or 2))
        if self._pb_in is None or getattr(self._pb_in, "shape", (0, 0))[0] != in_ch:
            self._pb_in = np.zeros((in_ch, self.max_frames), dtype=np.float32)
        self._input_channels = in_ch
        self._output_channels = out_ch

    def _apply_rt_params(self) -> None:
        """Apply current RT-store values to the pedalboard plugin.

        v0.0.20.378 — Use plugin.parameters[name].raw_value (normalized 0-1 setter)
        instead of setattr(plugin, name, val).  pedalboard's setattr() expects the
        *physical* value (e.g. 500.0 for 500 ms), but our sliders store the *normalized*
        0-1 value because pedalboard reports minimum_value=0.0 / maximum_value=1.0 for
        all VST3 params.  Setting a 0-1 slider value as a physical value would give
        near-zero results (e.g. 0.5 ms, 0.5 Hz), making every plugin appear broken.
        raw_value accepts and applies the same 0-1 normalized range.
        """
        try:
            pb_params = self._plugin.parameters  # dict: name → AudioProcessorParameter
        except Exception:
            pb_params = {}
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                rt = self.rt_params
                val = info.default
                if rt is not None:
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, info.default))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, info.default))
                val = max(info.minimum, min(info.maximum, val))
                # Apply via normalized raw_value setter (0-1)
                if info.name in pb_params:
                    if info.is_boolean:
                        # Boolean params: use Python attribute (True/False)
                        setattr(self._plugin, info.name, bool(val >= 0.5))
                    else:
                        pb_params[info.name].raw_value = val
                else:
                    # Fallback for params not in .parameters dict
                    setattr(self._plugin, info.name, val)
            except Exception:
                continue
            except Exception:
                continue

    def _prepare_process_input(self, buf: Any, frames: int) -> bool:
        if np is None or self._pb_in is None:
            return False
        try:
            self._pb_in[:, :frames] = 0.0
        except Exception:
            return False

        try:
            host_channels = int(buf.shape[1]) if getattr(buf, "ndim", 0) >= 2 else 1
        except Exception:
            host_channels = 1

        try:
            if self._input_channels <= 1:
                if host_channels >= 2:
                    np.add(buf[:frames, 0], buf[:frames, 1], out=self._pb_in[0, :frames])
                    self._pb_in[0, :frames] *= 0.5
                elif getattr(buf, "ndim", 0) >= 2:
                    self._pb_in[0, :frames] = buf[:frames, 0]
                else:
                    self._pb_in[0, :frames] = buf[:frames]
                return True

            if getattr(buf, "ndim", 0) >= 2:
                self._pb_in[0, :frames] = buf[:frames, 0]
                if self._input_channels >= 2:
                    if host_channels >= 2:
                        self._pb_in[1, :frames] = buf[:frames, 1]
                    else:
                        self._pb_in[1, :frames] = buf[:frames, 0]
            else:
                self._pb_in[0, :frames] = buf[:frames]
                if self._input_channels >= 2:
                    self._pb_in[1, :frames] = buf[:frames]
            return True
        except Exception:
            return False

    def _write_process_output(self, buf: Any, pb_out: Any, frames: int) -> bool:
        if np is None or pb_out is None:
            return False
        try:
            out = np.asarray(pb_out, dtype=np.float32)
        except Exception:
            return False
        try:
            if out.ndim == 1:
                out_frames = min(frames, len(out))
                buf[:out_frames, 0] = out[:out_frames]
                buf[:out_frames, 1] = out[:out_frames]
                return True
            if out.ndim != 2 or out.shape[0] <= 0:
                return False
            out_frames = min(frames, out.shape[1])
            if out.shape[0] == 1:
                buf[:out_frames, 0] = out[0, :out_frames]
                buf[:out_frames, 1] = out[0, :out_frames]
                return True
            buf[:out_frames, 0] = out[0, :out_frames]
            buf[:out_frames, 1] = out[1, :out_frames]
            return True
        except Exception:
            return False

    def _adapt_layout_from_error(self, exc: Exception) -> bool:
        in_ch, out_ch = _parse_layout_from_process_error(str(exc))
        if in_ch <= 0 and out_ch <= 0:
            return False
        in_ch = max(1, int(in_ch or self._input_channels or 2))
        out_ch = max(1, int(out_ch or self._output_channels or in_ch))
        if in_ch == self._input_channels and out_ch == self._output_channels:
            return False
        self._set_bus_layout(in_ch, out_ch)
        print(
            f"[VST3] adapted bus layout for {self._display_ref}: in={in_ch} out={out_ch}",
            file=sys.stderr,
            flush=True,
        )
        return True

    def _log_process_error_once(self, exc: Exception) -> None:
        msg = str(exc or "")
        if msg == self._last_process_error:
            return
        self._last_process_error = msg
        print(
            f"[VST3] process error in {self._display_ref}: {msg}",
            file=sys.stderr,
            flush=True,
        )

    def _load(self) -> None:
        if not _PEDALBOARD_OK:
            self._err = "pedalboard nicht installiert"
            return
        if np is None:
            self._err = "numpy nicht verfügbar"
            return
        if not self.path:
            self._err = "leerer Pfad"
            return
        try:
            self._plugin = _load_pedalboard_plugin(self.path, self.plugin_name)
        except Exception as exc:
            self._err = str(exc)
            print(f"[VST3] load failed for {self._display_ref}: {exc}",
                  file=sys.stderr, flush=True)
            return

        try:
            if _apply_raw_state_to_plugin(self._plugin, self._params_init.get("__ext_state_b64")):
                print(f"[VST3] restored raw_state for {self._display_ref}", file=sys.stderr, flush=True)
        except Exception:
            pass

        self._param_infos = _extract_param_infos(self._plugin)
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                init_val = float(getattr(self._plugin, info.name, info.default))
            except Exception:
                init_val = info.default
            if info.name in self._params_init:
                try:
                    init_val = float(self._params_init[info.name])
                except Exception:
                    pass
            init_val = max(info.minimum, min(info.maximum, init_val))
            try:
                if hasattr(self.rt_params, "ensure"):
                    self.rt_params.ensure(key, init_val)
            except Exception:
                pass
            try:
                setattr(self._plugin, info.name, init_val)
            except Exception:
                pass

        in_ch, out_ch = _detect_plugin_channel_layout(self._plugin)
        self._set_bus_layout(in_ch or 2, out_ch or in_ch or 2)

        self._ok = True
        print(
            f"[VST3] loaded: {self._display_ref} | params={len(self._param_infos)} | sr={self._sr} | bus={self._input_channels}->{self._output_channels}",
            file=sys.stderr,
            flush=True,
        )

    def process_inplace(self, buf: Any, frames: int, sr: int) -> None:
        if not self._ok or np is None or self._plugin is None:
            return
        frames = int(frames)
        if frames <= 0:
            return
        if frames > self.max_frames:
            frames = self.max_frames

        self._apply_rt_params()
        if not self._prepare_process_input(buf, frames):
            return

        sample_rate = float(sr if sr > 0 else self._sr)
        try:
            pb_out = self._plugin.process(
                self._pb_in[:, :frames],
                sample_rate=sample_rate,
                reset=False,
            )
        except Exception as exc:
            if self._adapt_layout_from_error(exc) and self._prepare_process_input(buf, frames):
                try:
                    pb_out = self._plugin.process(
                        self._pb_in[:, :frames],
                        sample_rate=sample_rate,
                        reset=False,
                    )
                except Exception as retry_exc:
                    self._log_process_error_once(retry_exc)
                    return
            else:
                self._log_process_error_once(exc)
                return

        if self._write_process_output(buf, pb_out, frames):
            self._last_process_error = ""

    def get_param_infos(self) -> List[Vst3ParamInfo]:
        return list(self._param_infos)

    def get_main_bus_layout(self) -> Tuple[int, int]:
        return (int(getattr(self, "_input_channels", 0) or 0),
                int(getattr(self, "_output_channels", 0) or 0))

    def get_raw_state_b64(self) -> str:
        if not self._ok or self._plugin is None:
            return ""
        try:
            return _encode_raw_state_b64(getattr(self._plugin, "raw_state", b""))
        except Exception:
            return ""

    def get_current_values(self) -> Dict[str, float]:
        """Return current parameter values as normalized 0-1 raw_values.

        v0.0.20.378 — Use plugin.parameters[name].raw_value so the returned values
        are consistent with the 0-1 range used by sliders and RTParamStore.
        """
        if not self._ok or self._plugin is None:
            return {}
        out: Dict[str, float] = {}
        try:
            pb_params = self._plugin.parameters
        except Exception:
            pb_params = {}
        for info in self._param_infos:
            try:
                if info.name in pb_params:
                    if info.is_boolean:
                        val = float(bool(getattr(self._plugin, info.name, info.default)))
                    else:
                        val = float(pb_params[info.name].raw_value)
                else:
                    val = float(getattr(self._plugin, info.name, info.default))
                out[info.name] = val
            except Exception:
                out[info.name] = info.default
        return out

    def __del__(self) -> None:
        try:
            self._plugin = None
        except Exception:
            pass


# ─── Instrument detection ──────────────────────────────────────────────────

_is_instrument_cache: Dict[str, bool] = {}  # path → True/False


def is_vst_instrument(path: str, plugin_name: str = "") -> bool:
    """Check if a VST plugin is an instrument (MIDI→Audio) vs. an effect.

    v0.0.20.384: Results are cached per path to avoid repeated slow load_plugin() calls.
    Surge XT takes ~2s per load — without cache, every rebuild_fx_maps() would freeze.
    """
    if not _PEDALBOARD_OK:
        return False
    base, pname = resolve_plugin_reference(path, plugin_name)
    if not base:
        return False
    cache_key = f"{base}||{pname}"
    if cache_key in _is_instrument_cache:
        return _is_instrument_cache[cache_key]
    try:
        plugin = _load_pedalboard_plugin(base, pname)
        result = bool(getattr(plugin, "is_instrument", False))
        try:
            del plugin
        except Exception:
            pass
        _is_instrument_cache[cache_key] = result
        return result
    except Exception:
        # Don't cache failures — might succeed next time (e.g. main-thread retry)
        return False


# ─── Vst3InstrumentEngine — RT MIDI→Audio host for VST instruments ────────

class Vst3InstrumentEngine:
    """Live VST Instrument wrapper: receives MIDI, produces audio.

    Designed to be registered in SamplerRegistry (note_on/note_off) and
    as a pull source in the audio callback (pull → numpy audio).

    v0.0.20.380: Initial implementation for Surge XT and similar synths.

    Architecture:
        SamplerRegistry ─note_on/note_off─► Vst3InstrumentEngine
                                             │ (accumulates MIDI bytes)
        AudioCallback ───pull(frames, sr)───► process(midi_msgs, duration, sr)
                                             │
                                             ▼ numpy (frames, 2)
    """

    def __init__(
        self,
        path: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Dict[str, Any],
        sr: int = 44100,
        max_frames: int = 8192,
        plugin_name: str = "",
    ):
        self._ok = False
        self._err = ""
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self._params_init = dict(params) if isinstance(params, dict) else {}
        self._sr = int(sr) if sr else 44100
        self.max_frames = int(max_frames) if max_frames else 8192
        self._plugin: Any = None
        self._param_infos: List[Vst3ParamInfo] = []
        self._prefix = f"afx:{self.track_id}:{self.device_id}:vst3:"

        # MIDI accumulator: list of (bytes, timestamp_seconds) per block
        self._pending_midi: List[Tuple[bytes, float]] = []
        # Active notes for polyphonic note_off: pitch → True
        self._active_notes: Dict[int, bool] = {}

        # Output buffer (pre-allocated)
        self._out_buf: Any = None
        if np is not None:
            self._out_buf = np.zeros((max_frames, 2), dtype=np.float32)

        explicit_name = str(plugin_name or self._params_init.get("__ext_plugin_name") or "")
        self.path, self.plugin_name = resolve_plugin_reference(path, explicit_name)
        self._display_ref = _display_reference(self.path, self.plugin_name)

        self._load()

    def _load(self) -> None:
        if not _PEDALBOARD_OK:
            self._err = "pedalboard nicht installiert"
            return
        if np is None:
            self._err = "numpy nicht verfügbar"
            return
        if not self.path:
            self._err = "leerer Pfad"
            return
        try:
            self._plugin = _load_pedalboard_plugin(self.path, self.plugin_name)
        except Exception as exc:
            self._err = str(exc)
            print(f"[VST3-INST] load failed for {self._display_ref}: {exc}",
                  file=sys.stderr, flush=True)
            return

        # Verify it IS an instrument
        if not getattr(self._plugin, "is_instrument", False):
            self._err = "Plugin is not an instrument"
            print(f"[VST3-INST] {self._display_ref} is NOT an instrument, refusing instrument-mode host",
                  file=sys.stderr, flush=True)
            return

        # Restore state blob if available
        try:
            if _apply_raw_state_to_plugin(self._plugin, self._params_init.get("__ext_state_b64")):
                print(f"[VST3-INST] restored raw_state for {self._display_ref}",
                      file=sys.stderr, flush=True)
        except Exception:
            pass

        # Extract and apply parameters
        self._param_infos = _extract_param_infos(self._plugin)
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                init_val = float(getattr(self._plugin, info.name, info.default))
            except Exception:
                init_val = info.default
            if info.name in self._params_init:
                try:
                    init_val = float(self._params_init[info.name])
                except Exception:
                    pass
            init_val = max(info.minimum, min(info.maximum, init_val))
            try:
                if hasattr(self.rt_params, "ensure"):
                    self.rt_params.ensure(key, init_val)
            except Exception:
                pass
            try:
                setattr(self._plugin, info.name, init_val)
            except Exception:
                pass

        self._ok = True
        print(
            f"[VST3-INST] loaded instrument: {self._display_ref} | params={len(self._param_infos)}",
            file=sys.stderr, flush=True,
        )

    # ── MIDI interface (called from SamplerRegistry / audio thread) ──

    def note_on(self, pitch: int, velocity: int = 100, *,
                pitch_offset_semitones: float = 0.0,
                micropitch_curve: list = None,
                note_duration_samples: int = 0) -> bool:
        """Queue a MIDI note-on for the next pull() call.

        Returns True if the engine is alive and accepted the note.
        pitch_offset_semitones / micropitch_curve are ignored for external VSTs
        (they use standard MIDI tuning).
        """
        if not self._ok:
            return False
        try:
            pitch = max(0, min(127, int(pitch)))
            velocity = max(1, min(127, int(velocity)))
            # MIDI note-on: 0x90 | channel 0
            midi_bytes = bytes([0x90, pitch, velocity])
            self._pending_midi.append((midi_bytes, 0.0))
            self._active_notes[pitch] = True
            return True
        except Exception:
            return False

    def note_off(self, pitch: int = -1) -> None:
        """Queue a MIDI note-off.

        If pitch >= 0: release that specific note (polyphonic).
        If pitch < 0: release ALL active notes (legacy mono behaviour).
        """
        if not self._ok:
            return
        try:
            if pitch >= 0:
                midi_bytes = bytes([0x80, int(pitch) & 0x7F, 0])
                self._pending_midi.append((midi_bytes, 0.0))
                self._active_notes.pop(int(pitch), None)
            else:
                # All notes off
                for p in list(self._active_notes.keys()):
                    midi_bytes = bytes([0x80, int(p) & 0x7F, 0])
                    self._pending_midi.append((midi_bytes, 0.0))
                self._active_notes.clear()
        except Exception:
            pass

    def all_notes_off(self) -> None:
        """Panic: release all notes immediately."""
        self.note_off(-1)
        # Also send CC#123 (All Notes Off) as safety
        try:
            self._pending_midi.append((bytes([0xB0, 123, 0]), 0.0))
        except Exception:
            pass

    # ── Audio pull interface (called from audio callback) ──

    def pull(self, frames: int, sr: int) -> Any:
        """Render audio from accumulated MIDI events.

        Returns numpy array (frames, 2) or None.
        """
        if not self._ok or self._plugin is None or np is None:
            return None
        frames = int(frames)
        if frames <= 0:
            return None

        # Apply RT params before rendering
        self._apply_rt_params()

        # Collect pending MIDI and clear
        midi_msgs = list(self._pending_midi)
        self._pending_midi.clear()

        duration = float(frames) / float(sr if sr > 0 else self._sr)

        try:
            audio = self._plugin.process(
                midi_msgs,
                duration=duration,
                sample_rate=float(sr if sr > 0 else self._sr),
                num_channels=2,
                buffer_size=min(frames, self.max_frames),
                reset=False,
            )
        except Exception as exc:
            print(f"[VST3-INST] process error in {self._display_ref}: {exc}",
                  file=sys.stderr, flush=True)
            return None

        # Convert to (frames, 2) layout for the callback
        try:
            out = np.asarray(audio, dtype=np.float32)
            if out.ndim == 1:
                n = min(frames, len(out))
                result = np.zeros((frames, 2), dtype=np.float32)
                result[:n, 0] = out[:n]
                result[:n, 1] = out[:n]
                return result
            if out.ndim == 2:
                # pedalboard returns (channels, samples)
                n = min(frames, out.shape[1])
                result = np.zeros((frames, 2), dtype=np.float32)
                result[:n, 0] = out[0, :n]
                if out.shape[0] >= 2:
                    result[:n, 1] = out[1, :n]
                else:
                    result[:n, 1] = out[0, :n]
                return result
        except Exception:
            pass
        return None

    def _apply_rt_params(self) -> None:
        """Apply current RT-store values to the plugin (same logic as Vst3Fx)."""
        try:
            pb_params = self._plugin.parameters
        except Exception:
            pb_params = {}
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                rt = self.rt_params
                val = info.default
                if rt is not None:
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, info.default))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, info.default))
                val = max(info.minimum, min(info.maximum, val))
                if info.name in pb_params:
                    if info.is_boolean:
                        setattr(self._plugin, info.name, bool(val >= 0.5))
                    else:
                        pb_params[info.name].raw_value = val
                else:
                    setattr(self._plugin, info.name, val)
            except Exception:
                continue

    def get_param_infos(self) -> List[Vst3ParamInfo]:
        return list(self._param_infos)

    def get_main_bus_layout(self) -> Tuple[int, int]:
        try:
            return tuple(int(v or 0) for v in _detect_plugin_channel_layout(self._plugin))
        except Exception:
            return (0, 0)

    def get_raw_state_b64(self) -> str:
        if not self._ok or self._plugin is None:
            return ""
        try:
            return _encode_raw_state_b64(getattr(self._plugin, "raw_state", b""))
        except Exception:
            return ""

    def get_current_values(self) -> Dict[str, float]:
        if not self._ok or self._plugin is None:
            return {}
        out: Dict[str, float] = {}
        try:
            pb_params = self._plugin.parameters
        except Exception:
            pb_params = {}
        for info in self._param_infos:
            try:
                if info.name in pb_params:
                    if info.is_boolean:
                        val = float(bool(getattr(self._plugin, info.name, info.default)))
                    else:
                        val = float(pb_params[info.name].raw_value)
                else:
                    val = float(getattr(self._plugin, info.name, info.default))
                out[info.name] = val
            except Exception:
                out[info.name] = info.default
        return out

    def shutdown(self) -> None:
        """Clean up (called from SamplerRegistry.unregister)."""
        try:
            self.all_notes_off()
        except Exception:
            pass
        try:
            self._plugin = None
        except Exception:
            pass
        self._ok = False

    def __del__(self) -> None:
        try:
            self._plugin = None
        except Exception:
            pass
