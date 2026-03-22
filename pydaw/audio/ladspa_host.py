# -*- coding: utf-8 -*-
"""LADSPA hosting (Audio-FX) for Py_DAW via ctypes.

Design goals
------------
- SAFE: if loading fails, nothing crashes; LADSPA FX becomes no-op.
- Real-time friendly: allocate/connect at build time; process_inplace() only
  copies buffers + updates controls + calls run().
- No external dependencies beyond stdlib + numpy.

LADSPA overview
---------------
- C API with LADSPA_Descriptor struct in .so files
- Simpler than LV2: no TTL metadata, no URIs
- Ports are: AUDIO|CONTROL × INPUT|OUTPUT
- Each .so can contain multiple plugins (by index)

Dependencies
------------
- numpy (already a project dependency)
- ctypes (stdlib)

v0.0.20.244 — Initial LADSPA live hosting
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

# ─── LADSPA C API Constants ─────────────────────────────────────────────────

LADSPA_PORT_INPUT = 0x1
LADSPA_PORT_OUTPUT = 0x2
LADSPA_PORT_CONTROL = 0x4
LADSPA_PORT_AUDIO = 0x8

LADSPA_HINT_BOUNDED_BELOW = 0x1
LADSPA_HINT_BOUNDED_ABOVE = 0x2
LADSPA_HINT_TOGGLED = 0x4
LADSPA_HINT_SAMPLE_RATE = 0x8
LADSPA_HINT_LOGARITHMIC = 0x10
LADSPA_HINT_INTEGER = 0x20
LADSPA_HINT_DEFAULT_MASK = 0x3C0
LADSPA_HINT_DEFAULT_NONE = 0x0
LADSPA_HINT_DEFAULT_MINIMUM = 0x40
LADSPA_HINT_DEFAULT_LOW = 0x80
LADSPA_HINT_DEFAULT_MIDDLE = 0xC0
LADSPA_HINT_DEFAULT_HIGH = 0x100
LADSPA_HINT_DEFAULT_MAXIMUM = 0x140
LADSPA_HINT_DEFAULT_0 = 0x200
LADSPA_HINT_DEFAULT_1 = 0x240
LADSPA_HINT_DEFAULT_100 = 0x280
LADSPA_HINT_DEFAULT_440 = 0x2C0

LADSPA_PROPERTY_REALTIME = 0x1
LADSPA_PROPERTY_INPLACE_BROKEN = 0x2
LADSPA_PROPERTY_HARD_RT_CAPABLE = 0x4


# ─── LADSPA C Structs (ctypes) ──────────────────────────────────────────────

class LADSPA_PortRangeHint(ctypes.Structure):
    _fields_ = [
        ("HintDescriptor", ctypes.c_int),
        ("LowerBound", ctypes.c_float),
        ("UpperBound", ctypes.c_float),
    ]


# NOTE: The LADSPA ABI places `ImplementationData` between `PortRangeHints`
# and `instantiate`. Omitting that field shifts every callback pointer and can
# turn a normal button click into a hard SIGSEGV when ctypes calls the wrong
# address. Keep this layout aligned with ladspa.h.


class LADSPA_Descriptor(ctypes.Structure):
    """Forward-declared LADSPA descriptor.

    ctypes cannot safely reference the class from inside its own class body,
    so `_fields_` is assigned *after* the class statement.
    """
    pass


LADSPA_Descriptor._fields_ = [
    ("UniqueID", ctypes.c_ulong),
    ("Label", ctypes.c_char_p),
    ("Properties", ctypes.c_int),
    ("Name", ctypes.c_char_p),
    ("Maker", ctypes.c_char_p),
    ("Copyright", ctypes.c_char_p),
    ("PortCount", ctypes.c_ulong),
    ("PortDescriptors", ctypes.POINTER(ctypes.c_int)),
    ("PortNames", ctypes.POINTER(ctypes.c_char_p)),
    ("PortRangeHints", ctypes.POINTER(LADSPA_PortRangeHint)),
    ("ImplementationData", ctypes.c_void_p),
    # Function pointers
    ("instantiate", ctypes.CFUNCTYPE(
        ctypes.c_void_p,  # LADSPA_Handle
        ctypes.POINTER(LADSPA_Descriptor),  # descriptor
        ctypes.c_ulong,  # sample_rate
    )),
    ("connect_port", ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,  # handle
        ctypes.c_ulong,   # port
        ctypes.POINTER(ctypes.c_float),  # data
    )),
    ("activate", ctypes.CFUNCTYPE(None, ctypes.c_void_p)),
    ("run", ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,  # handle
        ctypes.c_ulong,   # sample_count
    )),
    ("run_adding", ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,
        ctypes.c_ulong,
    )),
    ("set_run_adding_gain", ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,
        ctypes.c_float,
    )),
    ("deactivate", ctypes.CFUNCTYPE(None, ctypes.c_void_p)),
    ("cleanup", ctypes.CFUNCTYPE(None, ctypes.c_void_p)),
]


# Function type for ladspa_descriptor(index) → LADSPA_Descriptor*
LADSPA_DESCRIPTOR_FUNC = ctypes.CFUNCTYPE(
    ctypes.POINTER(LADSPA_Descriptor),
    ctypes.c_ulong,
)


# ─── Python-level data ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class LadspaPortInfo:
    index: int
    name: str
    descriptor: int  # bitmask
    hint: int
    lower: float
    upper: float
    default: float
    is_audio: bool
    is_control: bool
    is_input: bool
    is_output: bool


@dataclass(frozen=True)
class LadspaPluginInfo:
    unique_id: int
    label: str
    name: str
    maker: str
    port_count: int
    ports: List[LadspaPortInfo]
    properties: int


def _compute_default(hint: int, lower: float, upper: float, sr: int = 48000) -> float:
    """Compute default value from LADSPA port range hints."""
    hd = hint & LADSPA_HINT_DEFAULT_MASK
    lo = lower if (hint & LADSPA_HINT_BOUNDED_BELOW) else 0.0
    hi = upper if (hint & LADSPA_HINT_BOUNDED_ABOVE) else 1.0

    if hint & LADSPA_HINT_SAMPLE_RATE:
        lo *= sr
        hi *= sr

    if hd == LADSPA_HINT_DEFAULT_MINIMUM:
        return lo
    elif hd == LADSPA_HINT_DEFAULT_LOW:
        if hint & LADSPA_HINT_LOGARITHMIC:
            return float(lo ** 0.75 * hi ** 0.25) if lo > 0 and hi > 0 else lo * 0.75 + hi * 0.25
        return lo * 0.75 + hi * 0.25
    elif hd == LADSPA_HINT_DEFAULT_MIDDLE:
        if hint & LADSPA_HINT_LOGARITHMIC:
            return float((lo * hi) ** 0.5) if lo > 0 and hi > 0 else (lo + hi) * 0.5
        return (lo + hi) * 0.5
    elif hd == LADSPA_HINT_DEFAULT_HIGH:
        if hint & LADSPA_HINT_LOGARITHMIC:
            return float(lo ** 0.25 * hi ** 0.75) if lo > 0 and hi > 0 else lo * 0.25 + hi * 0.75
        return lo * 0.25 + hi * 0.75
    elif hd == LADSPA_HINT_DEFAULT_MAXIMUM:
        return hi
    elif hd == LADSPA_HINT_DEFAULT_0:
        return 0.0
    elif hd == LADSPA_HINT_DEFAULT_1:
        return 1.0
    elif hd == LADSPA_HINT_DEFAULT_100:
        return 100.0
    elif hd == LADSPA_HINT_DEFAULT_440:
        return 440.0
    else:
        # No default hint — pick midpoint or 0
        if (hint & LADSPA_HINT_BOUNDED_BELOW) and (hint & LADSPA_HINT_BOUNDED_ABOVE):
            return (lo + hi) * 0.5
        return 0.0


# ─── Library loader cache ───────────────────────────────────────────────────

_LIB_CACHE: Dict[str, Any] = {}  # path → ctypes.CDLL or None


def _load_lib(path: str) -> Any:
    """Load a LADSPA .so file (cached)."""
    path = str(path or "")
    if path in _LIB_CACHE:
        return _LIB_CACHE[path]
    try:
        lib = ctypes.CDLL(path)
        _LIB_CACHE[path] = lib
        return lib
    except Exception as e:
        print(f"[LADSPA] Failed to load {path}: {e}", file=sys.stderr, flush=True)
        _LIB_CACHE[path] = None
        return None


def _get_descriptor(lib: Any, index: int) -> Any:
    """Get LADSPA_Descriptor* for plugin at given index."""
    try:
        func = lib.ladspa_descriptor
        func.restype = ctypes.POINTER(LADSPA_Descriptor)
        func.argtypes = [ctypes.c_ulong]
        desc_ptr = func(ctypes.c_ulong(index))
        if desc_ptr and desc_ptr.contents:
            return desc_ptr
        return None
    except Exception:
        return None


def describe_plugin(path: str, index: int = 0, sr: int = 48000) -> Optional[LadspaPluginInfo]:
    """Load a LADSPA plugin and extract its metadata."""
    lib = _load_lib(path)
    if lib is None:
        return None
    desc_ptr = _get_descriptor(lib, index)
    if desc_ptr is None:
        return None
    try:
        desc = desc_ptr.contents
        ports: List[LadspaPortInfo] = []
        n = int(desc.PortCount)
        for i in range(n):
            pd = int(desc.PortDescriptors[i])
            pname = ""
            try:
                raw = desc.PortNames[i]
                pname = raw.decode("utf-8", errors="replace") if raw else f"port_{i}"
            except Exception:
                pname = f"port_{i}"

            hint_desc = 0
            lo = 0.0
            hi = 1.0
            try:
                h = desc.PortRangeHints[i]
                hint_desc = int(h.HintDescriptor)
                lo = float(h.LowerBound) if (hint_desc & LADSPA_HINT_BOUNDED_BELOW) else 0.0
                hi = float(h.UpperBound) if (hint_desc & LADSPA_HINT_BOUNDED_ABOVE) else 1.0
            except Exception:
                pass

            # Sanitize
            import math
            if math.isnan(lo) or math.isinf(lo):
                lo = 0.0
            if math.isnan(hi) or math.isinf(hi):
                hi = 1.0
            if hi <= lo:
                hi = lo + 1.0

            df = _compute_default(hint_desc, lo, hi, sr)
            if math.isnan(df) or math.isinf(df):
                df = (lo + hi) * 0.5

            ports.append(LadspaPortInfo(
                index=i,
                name=pname,
                descriptor=pd,
                hint=hint_desc,
                lower=lo,
                upper=hi,
                default=df,
                is_audio=bool(pd & LADSPA_PORT_AUDIO),
                is_control=bool(pd & LADSPA_PORT_CONTROL),
                is_input=bool(pd & LADSPA_PORT_INPUT),
                is_output=bool(pd & LADSPA_PORT_OUTPUT),
            ))

        label = ""
        name = ""
        maker = ""
        try:
            label = (desc.Label or b"").decode("utf-8", errors="replace")
            name = (desc.Name or b"").decode("utf-8", errors="replace")
            maker = (desc.Maker or b"").decode("utf-8", errors="replace")
        except Exception:
            pass

        return LadspaPluginInfo(
            unique_id=int(desc.UniqueID),
            label=label,
            name=name or label,
            maker=maker,
            port_count=n,
            ports=ports,
            properties=int(desc.Properties),
        )
    except Exception as e:
        print(f"[LADSPA] describe_plugin failed for {path}#{index}: {e}", file=sys.stderr, flush=True)
        return None


def list_plugins_in_lib(path: str) -> List[Tuple[int, str, str]]:
    """List all plugins in a LADSPA .so: [(index, label, name), ...]"""
    lib = _load_lib(path)
    if lib is None:
        return []
    out: List[Tuple[int, str, str]] = []
    for i in range(256):  # sanity limit
        desc_ptr = _get_descriptor(lib, i)
        if desc_ptr is None:
            break
        try:
            desc = desc_ptr.contents
            label = (desc.Label or b"").decode("utf-8", errors="replace")
            name = (desc.Name or b"").decode("utf-8", errors="replace")
            out.append((i, label, name or label))
        except Exception:
            break
    return out


def _resolve_plugin_index(path: str, plugin_id: str) -> int:
    """Resolve plugin index from the plugin_id.

    plugin_id can be:
    - Just a path → index 0
    - "path#index" → specific index
    - "label_NNNNN" → match by unique ID in the label
    """
    # Check for #index suffix
    if "#" in plugin_id:
        try:
            return int(plugin_id.rsplit("#", 1)[1])
        except Exception:
            pass
    # Check if the filename contains a unique ID (e.g. adsr_1653.so → ID 1653)
    import re
    m = re.search(r"_(\d+)\.so$", path)
    if m:
        target_id = int(m.group(1))
        lib = _load_lib(path)
        if lib:
            for i in range(256):
                desc_ptr = _get_descriptor(lib, i)
                if desc_ptr is None:
                    break
                try:
                    if int(desc_ptr.contents.UniqueID) == target_id:
                        return i
                except Exception:
                    pass
    return 0


# ─── LADSPA Audio-FX Processor ──────────────────────────────────────────────

class LadspaFx:
    """LADSPA Audio-FX (in-place stereo buffer)."""

    def __init__(
        self,
        *,
        path: str,
        plugin_index: int = 0,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Optional[Dict[str, Any]] = None,
        sr: int = 48000,
        max_frames: int = 8192,
    ) -> None:
        self.path = str(path or "")
        self.plugin_index = int(plugin_index)
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self.sr = int(sr) if sr else 48000
        self.max_frames = int(max_frames) if max_frames else 8192

        self._ok = False
        self._handle = None
        self._desc_ptr = None
        self._err: str = ""
        self._info: Optional[LadspaPluginInfo] = None

        # Port buffers
        self._ctl_in: List[Tuple[int, str, Any, float]] = []  # (port_idx, rt_key, buf1, default)
        self._ctl_out_bufs: List[Any] = []  # dummy buffers for output control ports
        self._ain_idx: List[int] = []
        self._aout_idx: List[int] = []
        self._ain_bufs: List[Any] = []
        self._aout_bufs: List[Any] = []

        # Stored function pointers (avoid repeated attribute lookup)
        self._fn_run = None
        self._fn_connect_port = None

        if np is None:
            self._err = "numpy fehlt"
            return

        try:
            self._build(params or {})
        except Exception as e:
            self._ok = False
            if not self._err:
                self._err = f"LADSPA init failed: {type(e).__name__}: {e}"

    def _build(self, params: dict) -> None:
        lib = _load_lib(self.path)
        if lib is None:
            self._err = f"LADSPA: Cannot load {self.path}"
            return

        desc_ptr = _get_descriptor(lib, self.plugin_index)
        if desc_ptr is None:
            self._err = f"LADSPA: No plugin at index {self.plugin_index} in {self.path}"
            return

        self._desc_ptr = desc_ptr
        desc = desc_ptr.contents

        self._info = describe_plugin(self.path, self.plugin_index, self.sr)

        # Instantiate
        try:
            if desc.instantiate:
                handle = desc.instantiate(desc_ptr, ctypes.c_ulong(self.sr))
                if not handle:
                    self._err = "LADSPA: instantiate() returned NULL"
                    return
                self._handle = handle
            else:
                self._err = "LADSPA: No instantiate function"
                return
        except Exception as e:
            self._err = f"LADSPA instantiate failed: {e}"
            return

        n = int(desc.PortCount)

        # Categorize ports
        for i in range(n):
            pd = int(desc.PortDescriptors[i])
            is_audio = bool(pd & LADSPA_PORT_AUDIO)
            is_control = bool(pd & LADSPA_PORT_CONTROL)
            is_input = bool(pd & LADSPA_PORT_INPUT)
            is_output = bool(pd & LADSPA_PORT_OUTPUT)

            if is_audio and is_input:
                self._ain_idx.append(i)
            elif is_audio and is_output:
                self._aout_idx.append(i)
            elif is_control and is_input:
                # Get port info
                pinfo = self._info.ports[i] if self._info and i < len(self._info.ports) else None
                pname = pinfo.name if pinfo else f"port_{i}"
                df = pinfo.default if pinfo else 0.0

                # User-provided value overrides default
                sym = f"p{i}"  # Use port index as key
                try:
                    if str(i) in params and isinstance(params[str(i)], (int, float)):
                        df = float(params[str(i)])
                    elif pname in params and isinstance(params[pname], (int, float)):
                        df = float(params[pname])
                    elif sym in params and isinstance(params[sym], (int, float)):
                        df = float(params[sym])
                except Exception:
                    pass

                rt_key = f"afx:{self.track_id}:{self.device_id}:ladspa:{i}"
                buf1 = np.zeros((1,), dtype=np.float32)
                buf1[0] = np.float32(df)

                # Register in RT store
                try:
                    if hasattr(self.rt_params, "ensure"):
                        self.rt_params.ensure(rt_key, float(df))
                    elif hasattr(self.rt_params, "set_param"):
                        self.rt_params.set_param(rt_key, float(df))
                except Exception:
                    pass

                # Connect
                try:
                    desc.connect_port(self._handle, ctypes.c_ulong(i), buf1.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
                except Exception:
                    pass

                self._ctl_in.append((i, rt_key, buf1, float(df)))

            elif is_control and is_output:
                # Dummy output buffer
                buf1 = np.zeros((1,), dtype=np.float32)
                try:
                    desc.connect_port(self._handle, ctypes.c_ulong(i), buf1.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
                except Exception:
                    pass
                self._ctl_out_bufs.append(buf1)

        # Allocate audio buffers
        self._ain_bufs = [np.zeros((self.max_frames,), dtype=np.float32) for _ in self._ain_idx]
        self._aout_bufs = [np.zeros((self.max_frames,), dtype=np.float32) for _ in self._aout_idx]

        # Connect audio ports
        for idx, buf in zip(self._ain_idx, self._ain_bufs):
            try:
                desc.connect_port(self._handle, ctypes.c_ulong(idx), buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
            except Exception:
                pass
        for idx, buf in zip(self._aout_idx, self._aout_bufs):
            try:
                desc.connect_port(self._handle, ctypes.c_ulong(idx), buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
            except Exception:
                pass

        # Activate
        try:
            if desc.activate:
                desc.activate(self._handle)
        except Exception:
            pass

        # Cache function pointers
        self._fn_run = desc.run
        self._fn_connect_port = desc.connect_port

        # Need at least some audio I/O
        if len(self._ain_idx) >= 1 and len(self._aout_idx) >= 1:
            self._ok = True
        else:
            if not self._err:
                self._err = f"LADSPA: No audio I/O (in={len(self._ain_idx)}, out={len(self._aout_idx)})"

        # Log
        print(f"[LADSPA] {self.path}#{self.plugin_index}: ok={self._ok} "
              f"ain={len(self._ain_idx)} aout={len(self._aout_idx)} "
              f"ctl_in={len(self._ctl_in)} ctl_out={len(self._ctl_out_bufs)}",
              file=sys.stderr, flush=True)

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        """Process audio in-place. buf shape: (frames, 2)."""
        if not self._ok or np is None or self._fn_run is None:
            return

        frames = int(frames)
        if frames <= 0:
            return
        if frames > self.max_frames:
            frames = self.max_frames

        # Update control inputs from RT params
        for _, rt_key, buf1, dv in self._ctl_in:
            try:
                val = dv
                rt = self.rt_params
                if rt is not None:
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(rt_key, dv))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(rt_key, dv))
                buf1[0] = np.float32(val)
            except Exception:
                continue

        # Feed audio inputs
        try:
            if len(self._ain_bufs) >= 2:
                self._ain_bufs[0][:frames] = buf[:frames, 0]
                self._ain_bufs[1][:frames] = buf[:frames, 1]
            elif len(self._ain_bufs) == 1:
                self._ain_bufs[0][:frames] = (buf[:frames, 0] + buf[:frames, 1]) * 0.5
        except Exception:
            return

        # Run
        try:
            self._fn_run(self._handle, ctypes.c_ulong(frames))
        except Exception:
            return

        # Copy outputs back
        try:
            if len(self._aout_bufs) >= 2:
                buf[:frames, 0] = self._aout_bufs[0][:frames]
                buf[:frames, 1] = self._aout_bufs[1][:frames]
            elif len(self._aout_bufs) == 1:
                buf[:frames, 0] = self._aout_bufs[0][:frames]
                buf[:frames, 1] = self._aout_bufs[0][:frames]
        except Exception:
            return

    def get_control_ports(self) -> List[Dict[str, Any]]:
        """Return control port info for UI."""
        if not self._info:
            return []
        out = []
        for port in self._info.ports:
            if port.is_control and port.is_input:
                out.append({
                    'index': port.index,
                    'name': port.name,
                    'lower': port.lower,
                    'upper': port.upper,
                    'default': port.default,
                    'hint': port.hint,
                    'is_toggled': bool(port.hint & LADSPA_HINT_TOGGLED),
                    'is_integer': bool(port.hint & LADSPA_HINT_INTEGER),
                    'is_logarithmic': bool(port.hint & LADSPA_HINT_LOGARITHMIC),
                })
        return out

    def __del__(self):
        """Cleanup on GC."""
        try:
            if self._handle and self._desc_ptr:
                desc = self._desc_ptr.contents
                if desc.deactivate:
                    desc.deactivate(self._handle)
                if desc.cleanup:
                    desc.cleanup(self._handle)
        except Exception:
            pass
        self._handle = None
