# -*- coding: utf-8 -*-
"""VST2 hosting for Py_DAW via ctypes — zero external dependencies.

Design goals
------------
- SAFE: if loading fails, nothing crashes; Vst2Fx becomes no-op.
- Real-time friendly: load + connect at build time; process_inplace() only
  copies buffers + updates controls + calls processReplacing().
- Compatible API with Vst3Fx (process_inplace, get_param_infos) and
  Vst3InstrumentEngine (note_on, note_off, pull).
- No external dependencies beyond stdlib + numpy.

VST2 overview
-------------
- C ABI: .so exports VSTPluginMain(audioMasterCallback) → AEffect*
- AEffect struct contains function pointers: dispatcher, processReplacing,
  setParameter, getParameter
- Host communicates via dispatcher opcodes (effOpen, effClose, etc.)
- Plugin calls audioMasterCallback for host queries (sample rate, block size)

Validated
---------
- 112/115 Linux VST2 .so plugins successfully loaded via probe script
- Instruments (Dexed, Helm, Obxd, ZynAddSubFX, etc.) and effects all work

v0.0.20.392 — Initial VST2 native host
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

# ═══════════════════════════════════════════════════════════════════════════════
# VST2 C ABI Constants
# ═══════════════════════════════════════════════════════════════════════════════

kEffectMagic = 0x56737450  # 'VstP'

# Dispatcher opcodes
effOpen = 0
effClose = 1
effSetProgram = 2
effGetProgram = 3
effGetProgramName = 5
effGetParamLabel = 6
effGetParamDisplay = 7
effGetParamName = 8
effSetSampleRate = 10
effSetBlockSize = 11
effMainsChanged = 12
effEditGetRect = 13
effEditOpen = 14
effEditClose = 15
effEditIdle = 19
effGetChunk = 23
effSetChunk = 24
effCanBeAutomated = 26
effGetEffectName = 45
effGetVendorString = 47
effGetProductString = 48
effCanDo = 51
effStartProcess = 71
effStopProcess = 72

# Flags
effFlagsHasEditor = 1 << 0
effFlagsCanReplacing = 1 << 4
effFlagsProgramChunks = 1 << 5
effFlagsIsSynth = 1 << 8

# audioMaster opcodes
audioMasterAutomate = 0
audioMasterVersion = 1
audioMasterCurrentId = 2
audioMasterIdle = 3
audioMasterGetSampleRate = 6
audioMasterGetBlockSize = 11
audioMasterGetCurrentProcessLevel = 23
audioMasterGetVendorString = 32
audioMasterGetProductString = 33
audioMasterGetVendorVersion = 34
audioMasterCanDo = 37

# Process levels
kVstProcessLevelRealtime = 2

# ═══════════════════════════════════════════════════════════════════════════════
# ctypes type definitions (64-bit safe)
# ═══════════════════════════════════════════════════════════════════════════════

INTPTR = ctypes.c_int64 if struct.calcsize("P") == 8 else ctypes.c_int32

# audioMasterCallback signature
AUDIO_MASTER_CB_T = ctypes.CFUNCTYPE(
    INTPTR,             # return: intptr_t
    ctypes.c_void_p,    # AEffect*
    ctypes.c_int32,     # opcode
    ctypes.c_int32,     # index
    INTPTR,             # value
    ctypes.c_void_p,    # ptr
    ctypes.c_float,     # opt
)

# Function pointer types for AEffect fields
DISPATCHER_T = ctypes.CFUNCTYPE(
    INTPTR, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32,
    INTPTR, ctypes.c_void_p, ctypes.c_float,
)
SET_PARAM_T = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_float)
GET_PARAM_T = ctypes.CFUNCTYPE(ctypes.c_float, ctypes.c_void_p, ctypes.c_int32)
PROCESS_T = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p,
    ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
    ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
    ctypes.c_int32,
)

# VSTPluginMain entry point: returns void* (we cast to AEffect* manually)
VST_MAIN_T = ctypes.CFUNCTYPE(ctypes.c_void_p, AUDIO_MASTER_CB_T)


class AEffect(ctypes.Structure):
    """VST2 AEffect structure — matches the C layout exactly."""
    _fields_ = [
        ("magic",                      ctypes.c_int32),
        ("dispatcher",                 ctypes.c_void_p),
        ("_process_deprecated",        ctypes.c_void_p),
        ("setParameter",               ctypes.c_void_p),
        ("getParameter",               ctypes.c_void_p),
        ("numPrograms",                ctypes.c_int32),
        ("numParams",                  ctypes.c_int32),
        ("numInputs",                  ctypes.c_int32),
        ("numOutputs",                 ctypes.c_int32),
        ("flags",                      ctypes.c_int32),
        ("resvd1",                     INTPTR),
        ("resvd2",                     INTPTR),
        ("initialDelay",               ctypes.c_int32),
        ("_realQualities",             ctypes.c_int32),
        ("_offQualities",              ctypes.c_int32),
        ("_ioRatio",                   ctypes.c_float),
        ("object",                     ctypes.c_void_p),
        ("user",                       ctypes.c_void_p),
        ("uniqueID",                   ctypes.c_int32),
        ("version",                    ctypes.c_int32),
        ("processReplacing",           ctypes.c_void_p),
        ("processDoubleReplacing",     ctypes.c_void_p),
        ("future",                     ctypes.c_char * 56),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# VST2 Parameter Info (same interface as Vst3ParamInfo)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Vst2ParamInfo:
    """Describes one VST2 parameter for UI building.

    API-compatible with Vst3ParamInfo so the widget code can handle both.
    """
    name: str
    label: str
    minimum: float = 0.0
    maximum: float = 1.0
    default: float = 0.0
    is_boolean: bool = False
    is_integer: bool = False
    units: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Host Callback
# ═══════════════════════════════════════════════════════════════════════════════

# Per-instance host state (thread-safe via dict keyed by effect pointer)
_host_state: Dict[int, Dict[str, Any]] = {}
_host_state_lock = threading.Lock()


def _audio_master_callback(effect_ptr, opcode, index, value, ptr, opt):
    """audioMasterCallback — answers plugin queries about the host."""
    try:
        with _host_state_lock:
            state = _host_state.get(effect_ptr or 0, {})
        sr = state.get("sample_rate", 48000)
        bs = state.get("block_size", 1024)

        if opcode == audioMasterVersion:
            return 2400  # VST 2.4
        if opcode == audioMasterGetSampleRate:
            return int(sr)
        if opcode == audioMasterGetBlockSize:
            return int(bs)
        if opcode == audioMasterCurrentId:
            return 0
        if opcode == audioMasterAutomate:
            return 0  # Accept automation
        if opcode == audioMasterIdle:
            return 0
        if opcode == audioMasterGetCurrentProcessLevel:
            return kVstProcessLevelRealtime
        if opcode == audioMasterCanDo:
            return 0  # "don't know"
        if opcode == audioMasterGetVendorString:
            if ptr:
                ctypes.memmove(ptr, b"PyDAW\x00", 6)
            return 0
        if opcode == audioMasterGetProductString:
            if ptr:
                ctypes.memmove(ptr, b"ChronoScaleStudio\x00", 19)
            return 0
        if opcode == audioMasterGetVendorVersion:
            return 392
    except Exception:
        pass
    return 0


# Keep a reference alive so it doesn't get GC'd
_host_cb = AUDIO_MASTER_CB_T(_audio_master_callback)


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin Loader
# ═══════════════════════════════════════════════════════════════════════════════

class _Vst2Plugin:
    """Low-level wrapper around a loaded VST2 .so plugin instance.

    Handles: dlopen → VSTPluginMain → AEffect → effOpen → ready.
    Thread safety: all calls should be from one thread (audio or main).
    """

    def __init__(self, path: str, sr: int = 48000, block_size: int = 1024):
        self.path = str(path)
        self._ok = False
        self._err = ""
        self._lib = None
        self._effect_ptr = None  # raw c_void_p
        self._effect: Optional[AEffect] = None
        self._dispatch: Optional[DISPATCHER_T] = None
        self._get_param: Optional[GET_PARAM_T] = None
        self._set_param: Optional[SET_PARAM_T] = None
        self._process: Optional[PROCESS_T] = None
        self._sr = int(sr)
        self._block_size = int(block_size)

        # Audio buffers (allocated once, reused)
        self._in_bufs: List[Any] = []
        self._out_bufs: List[Any] = []
        self._in_ptrs: Any = None
        self._out_ptrs: Any = None

        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            self._err = f"File not found: {self.path}"
            return

        # 1. dlopen with RTLD_LOCAL to isolate plugin symbols from Qt/PyQt
        try:
            self._lib = ctypes.CDLL(self.path, mode=ctypes.RTLD_LOCAL)
        except OSError as e:
            self._err = f"dlopen failed: {e}"
            return

        # 2. Find entry point
        entry_fn = None
        for name in ("VSTPluginMain", "main"):
            try:
                entry_fn = VST_MAIN_T((name, self._lib))
                break
            except AttributeError:
                continue
        if entry_fn is None:
            self._err = "No VST2 entry point (VSTPluginMain/main)"
            return

        # 3. Register host state BEFORE calling entry (plugin may query SR)
        # Use 0 as key temporarily (effect pointer unknown yet)
        with _host_state_lock:
            _host_state[0] = {
                "sample_rate": self._sr,
                "block_size": self._block_size,
            }

        # 4. Call entry point
        try:
            raw_ptr = entry_fn(_host_cb)
        except Exception as e:
            self._err = f"Entry point crashed: {e}"
            return
        finally:
            with _host_state_lock:
                _host_state.pop(0, None)

        if not raw_ptr:
            self._err = "Entry point returned NULL"
            return

        # 5. Cast to AEffect
        self._effect_ptr = ctypes.c_void_p(raw_ptr)
        self._effect = ctypes.cast(raw_ptr, ctypes.POINTER(AEffect)).contents

        if self._effect.magic != kEffectMagic:
            self._err = f"Bad magic: 0x{self._effect.magic:08X}"
            return

        # 6. Register host state with real effect pointer
        with _host_state_lock:
            _host_state[raw_ptr] = {
                "sample_rate": self._sr,
                "block_size": self._block_size,
            }

        # 7. Cast function pointers
        if self._effect.dispatcher:
            self._dispatch = DISPATCHER_T(self._effect.dispatcher)
        else:
            self._err = "No dispatcher"
            return
        if self._effect.getParameter:
            self._get_param = GET_PARAM_T(self._effect.getParameter)
        if self._effect.setParameter:
            self._set_param = SET_PARAM_T(self._effect.setParameter)
        if self._effect.processReplacing:
            self._process = PROCESS_T(self._effect.processReplacing)
        else:
            self._err = "No processReplacing"
            return

        # 8. effOpen + configure
        try:
            self._dispatch(self._effect_ptr, effOpen, 0, 0, None, 0.0)
            self._dispatch(self._effect_ptr, effSetSampleRate, 0, 0, None, float(self._sr))
            self._dispatch(self._effect_ptr, effSetBlockSize, 0, self._block_size, None, 0.0)
            self._dispatch(self._effect_ptr, effMainsChanged, 0, 1, None, 0.0)
            # Some plugins need effStartProcess to begin producing audio
            self._dispatch(self._effect_ptr, effStartProcess, 0, 0, None, 0.0)
        except Exception as e:
            self._err = f"Setup failed: {e}"
            return

        # 9. Allocate audio buffers
        self._alloc_buffers()

        self._editor_active = False
        self._ok = True

    def _alloc_buffers(self) -> None:
        """Allocate ctypes audio buffers for processReplacing."""
        n_in = max(self.num_inputs, 1)
        n_out = max(self.num_outputs, 1)
        bs = self._block_size

        self._in_bufs = [(ctypes.c_float * bs)() for _ in range(n_in)]
        self._out_bufs = [(ctypes.c_float * bs)() for _ in range(n_out)]

        self._in_ptrs = (ctypes.POINTER(ctypes.c_float) * n_in)()
        for i in range(n_in):
            self._in_ptrs[i] = ctypes.cast(self._in_bufs[i], ctypes.POINTER(ctypes.c_float))

        self._out_ptrs = (ctypes.POINTER(ctypes.c_float) * n_out)()
        for i in range(n_out):
            self._out_ptrs[i] = ctypes.cast(self._out_bufs[i], ctypes.POINTER(ctypes.c_float))

    # ── Properties ──

    @property
    def num_params(self) -> int:
        return self._effect.numParams if self._effect else 0

    @property
    def num_inputs(self) -> int:
        return self._effect.numInputs if self._effect else 0

    @property
    def num_outputs(self) -> int:
        return self._effect.numOutputs if self._effect else 2

    @property
    def num_programs(self) -> int:
        return self._effect.numPrograms if self._effect else 0

    @property
    def flags(self) -> int:
        return self._effect.flags if self._effect else 0

    @property
    def is_synth(self) -> bool:
        return bool(self.flags & effFlagsIsSynth)

    @property
    def unique_id(self) -> int:
        return self._effect.uniqueID if self._effect else 0

    # ── Dispatcher helpers ──

    def _disp(self, opcode: int, index: int = 0, value: int = 0,
              ptr: Any = None, opt: float = 0.0) -> int:
        if self._dispatch is None:
            return 0
        try:
            return int(self._dispatch(self._effect_ptr, opcode, index, value, ptr, opt))
        except Exception:
            return 0

    def _get_string(self, opcode: int, index: int = 0) -> str:
        buf = ctypes.create_string_buffer(256)
        self._disp(opcode, index, 0, buf, 0.0)
        try:
            return buf.value.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def get_effect_name(self) -> str:
        return self._get_string(effGetEffectName)

    def get_vendor(self) -> str:
        return self._get_string(effGetVendorString)

    def get_param_name(self, idx: int) -> str:
        return self._get_string(effGetParamName, idx)

    def get_param_label(self, idx: int) -> str:
        return self._get_string(effGetParamLabel, idx)

    def get_param_display(self, idx: int) -> str:
        return self._get_string(effGetParamDisplay, idx)

    def get_parameter(self, idx: int) -> float:
        if self._get_param is None:
            return 0.0
        try:
            return float(self._get_param(self._effect_ptr, idx))
        except Exception:
            return 0.0

    def set_parameter(self, idx: int, value: float) -> None:
        if self._set_param is None:
            return
        try:
            self._set_param(self._effect_ptr, idx, float(value))
        except Exception:
            pass

    # ── MIDI (for instruments) ──

    def send_midi_event(self, status: int, data1: int, data2: int, delta_frames: int = 0) -> None:
        """Send a single MIDI event via dispatcher (effProcessEvents).

        v0.0.20.394: Fixed VstMidiEvent layout — midiData is at offset 24, not 16.
        Fixed VstEvents layout — events[0] pointer at offset 16 on 64-bit.
        """
        self.send_midi_events([(status, data1, data2, delta_frames)])

    def send_midi_events(self, events_list: list) -> None:
        """Send multiple MIDI events at once — buffers stay alive until processed.

        events_list: [(status, data1, data2, delta_frames), ...]
        """
        if self._dispatch is None or not events_list:
            return
        try:
            n = len(events_list)
            PTR_SIZE = struct.calcsize("P")

            # Allocate all VstMidiEvent structs (32 bytes each)
            midi_events = []
            for (status, d1, d2, delta) in events_list:
                ev = (ctypes.c_char * 32)()
                struct.pack_into("<i", ev, 0, 1)       # type = kVstMidiType
                struct.pack_into("<i", ev, 4, 32)      # byteSize
                struct.pack_into("<i", ev, 8, int(delta))  # deltaFrames
                ev[24] = status & 0xFF
                ev[25] = d1 & 0x7F
                ev[26] = d2 & 0x7F
                ev[27] = 0
                midi_events.append(ev)

            # VstEvents struct with N event pointers
            # 64-bit: numEvents(4) + pad(4) + reserved(8) + N*pointer(8)
            if PTR_SIZE == 8:
                header_size = 16  # numEvents + pad + reserved
            else:
                header_size = 8   # numEvents + reserved
            total_size = header_size + n * PTR_SIZE
            events_buf = (ctypes.c_char * total_size)()
            struct.pack_into("<i", events_buf, 0, n)  # numEvents

            # Write event pointers
            for i, ev in enumerate(midi_events):
                ev_ptr = ctypes.cast(ctypes.pointer(ev), ctypes.c_void_p).value
                offset = header_size + i * PTR_SIZE
                if PTR_SIZE == 8:
                    struct.pack_into("<Q", events_buf, offset, ev_ptr)
                else:
                    struct.pack_into("<I", events_buf, offset, ev_ptr)

            # Send — all buffers (midi_events, events_buf) are alive here
            self._disp(25, 0, 0, events_buf, 0.0)  # effProcessEvents = 25

            # Keep references alive — some plugins read events during processReplacing
            self._last_midi_events = midi_events
            self._last_events_buf = events_buf

        except Exception as exc:
            print(f"[VST2] send_midi_events error: {exc}", file=sys.stderr, flush=True)

    # ── Audio Processing ──

    def process_replacing(self, frames: int) -> None:
        """Call processReplacing with the internal buffers.

        Caller must fill _in_bufs before and read _out_bufs after.
        """
        if self._process is None:
            return
        try:
            self._process(self._effect_ptr, self._in_ptrs, self._out_ptrs, frames)
        except Exception:
            pass

    # ── State ──

    def get_chunk(self) -> bytes:
        """Get plugin state as opaque chunk (if supported)."""
        if not (self.flags & effFlagsProgramChunks):
            return b""
        try:
            ptr = ctypes.c_void_p()
            size = self._disp(effGetChunk, 0, 0, ctypes.byref(ptr), 0.0)
            if size > 0 and ptr.value:
                return ctypes.string_at(ptr.value, size)
        except Exception:
            pass
        return b""

    def set_chunk(self, data: bytes) -> None:
        """Restore plugin state from opaque chunk."""
        if not data or not (self.flags & effFlagsProgramChunks):
            return
        try:
            buf = ctypes.create_string_buffer(data)
            self._disp(effSetChunk, 0, len(data), buf, 0.0)
        except Exception:
            pass

    # ── Native Editor (X11) ──

    @property
    def has_editor(self) -> bool:
        return bool(self.flags & effFlagsHasEditor)

    def editor_get_rect(self) -> Tuple[int, int]:
        """Get the plugin's preferred editor size. Returns (width, height)."""
        if not self.has_editor or self._dispatch is None:
            return (640, 480)
        try:
            # effEditGetRect returns a pointer to an ERect struct:
            # struct ERect { int16 top, left, bottom, right; }
            rect_ptr = ctypes.c_void_p(0)
            self._disp(effEditGetRect, 0, 0, ctypes.byref(rect_ptr), 0.0)
            if rect_ptr.value:
                # Read 4x int16 from the pointer
                rect_data = (ctypes.c_int16 * 4).from_address(rect_ptr.value)
                top, left, bottom, right = rect_data[0], rect_data[1], rect_data[2], rect_data[3]
                w = max(100, int(right - left))
                h = max(100, int(bottom - top))
                return (w, h)
        except Exception:
            pass
        return (640, 480)

    def editor_open(self, window_handle: int) -> bool:
        """Open the native editor in the given window. Returns True on success."""
        if not self.has_editor or self._dispatch is None:
            return False
        try:
            self._disp(effEditOpen, 0, 0, ctypes.c_void_p(int(window_handle)), 0.0)
            self._editor_active = True
            return True
        except Exception:
            return False

    def editor_close(self) -> None:
        """Close the native editor."""
        self._editor_active = False
        if self._dispatch is None:
            return
        try:
            self._disp(effEditClose, 0, 0, None, 0.0)
        except Exception:
            pass

    def editor_idle(self) -> None:
        """Must be called regularly (~30ms) while the editor is open."""
        if self._dispatch is None:
            return
        try:
            self._disp(effEditIdle, 0, 0, None, 0.0)
        except Exception:
            pass

    # ── Lifecycle ──

    def close(self) -> None:
        # Close editor first if open
        self.editor_close()
        if self._dispatch is not None and self._effect_ptr is not None:
            try:
                self._dispatch(self._effect_ptr, effStopProcess, 0, 0, None, 0.0)
            except Exception:
                pass
            try:
                self._dispatch(self._effect_ptr, effMainsChanged, 0, 0, None, 0.0)
            except Exception:
                pass
            try:
                self._dispatch(self._effect_ptr, effClose, 0, 0, None, 0.0)
            except Exception:
                pass
        # Cleanup host state
        if self._effect_ptr:
            with _host_state_lock:
                _host_state.pop(self._effect_ptr.value, None)
        self._dispatch = None
        self._get_param = None
        self._set_param = None
        self._process = None
        self._effect = None
        self._ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# Parameter extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_vst2_param_infos(plugin: _Vst2Plugin) -> List[Vst2ParamInfo]:
    """Read parameter descriptors from a loaded VST2 plugin."""
    result: List[Vst2ParamInfo] = []
    for i in range(plugin.num_params):
        name = plugin.get_param_name(i) or f"param_{i}"
        label = plugin.get_param_label(i)
        default_val = plugin.get_parameter(i)
        # VST2 params are always 0.0–1.0 normalized
        result.append(Vst2ParamInfo(
            name=name,
            label=label,
            minimum=0.0,
            maximum=1.0,
            default=default_val,
            is_boolean=False,
            is_integer=False,
            units=label,
        ))
    return result


def is_vst2_instrument(path: str) -> bool:
    """Check if a VST2 .so is an instrument by checking effFlagsIsSynth.

    v0.0.20.393: Lightweight — only reads flags from AEffect after VSTPluginMain.
    Does NOT call effOpen. Caches result per path.
    Uses subprocess to avoid SIGSEGV crashing the main process.
    """
    _cache_key = f"vst2inst:{path}"
    if _cache_key in _is_instrument_cache:
        return _is_instrument_cache[_cache_key]

    # Use subprocess to safely probe — plugin crashes won't kill our process
    result = False
    try:
        import subprocess
        code = '''
import ctypes, struct, sys
path = sys.argv[1]
INTPTR = ctypes.c_int64 if struct.calcsize("P") == 8 else ctypes.c_int32
CB_T = ctypes.CFUNCTYPE(INTPTR, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, INTPTR, ctypes.c_void_p, ctypes.c_float)
def cb(e,o,i,v,p,f): return 2400 if o==1 else 0
_cb = CB_T(cb)
MAIN_T = ctypes.CFUNCTYPE(ctypes.c_void_p, CB_T)

class AE(ctypes.Structure):
    _fields_ = [("magic",ctypes.c_int32),("d",ctypes.c_void_p),("p",ctypes.c_void_p),
                ("sp",ctypes.c_void_p),("gp",ctypes.c_void_p),("np",ctypes.c_int32),
                ("npa",ctypes.c_int32),("ni",ctypes.c_int32),("no",ctypes.c_int32),
                ("flags",ctypes.c_int32)]

lib = ctypes.CDLL(path, mode=1)  # RTLD_LOCAL
fn = None
for n in ("VSTPluginMain","main"):
    try:
        fn = MAIN_T((n, lib)); break
    except: pass
if fn is None: sys.exit(1)
r = fn(_cb)
if not r: sys.exit(1)
e = ctypes.cast(r, ctypes.POINTER(AE)).contents
print("1" if (e.flags & 0x100) else "0")
'''
        proc = subprocess.run(
            [sys.executable, "-c", code, path],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip() == "1":
            result = True
    except Exception:
        result = False

    _is_instrument_cache[_cache_key] = result
    return result


_is_instrument_cache: Dict[str, bool] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Vst2Fx — Audio Effect (drop-in for Vst3Fx)
# ═══════════════════════════════════════════════════════════════════════════════

class Vst2Fx:
    """Live VST2 Audio-FX wrapper, compatible with FxChain.process_inplace().

    Same interface as Vst3Fx: _ok, process_inplace(buf, frames, sr),
    get_param_infos(), device_id, track_id.
    """

    def __init__(
        self,
        path: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Dict[str, Any],
        sr: int = 48000,
        max_frames: int = 8192,
        plugin_name: str = "",
    ):
        self._ok = False
        self._err = ""
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self._params_init = dict(params) if isinstance(params, dict) else {}
        self._sr = int(sr) if sr else 48000
        self.max_frames = int(max_frames) if max_frames else 8192
        self.path = str(path)
        self.plugin_name = str(plugin_name or os.path.basename(path))
        self._plugin: Optional[_Vst2Plugin] = None
        self._param_infos: List[Vst2ParamInfo] = []
        self._prefix = f"afx:{self.track_id}:{self.device_id}:vst2:"
        self._param_name_to_idx: Dict[str, int] = {}

        self._load()

    def _load(self) -> None:
        try:
            self._plugin = _Vst2Plugin(self.path, sr=self._sr, block_size=self.max_frames)
        except Exception as e:
            self._err = str(e)
            return

        if not self._plugin._ok:
            self._err = self._plugin._err
            return

        # Extract params
        self._param_infos = _extract_vst2_param_infos(self._plugin)
        for i, info in enumerate(self._param_infos):
            self._param_name_to_idx[info.name] = i

        # Register RT param defaults
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                if hasattr(self.rt_params, "ensure"):
                    self.rt_params.ensure(key, info.default)
            except Exception:
                pass

        # Restore state if available
        state_b64 = self._params_init.get("__ext_state_b64", "")
        if state_b64:
            try:
                import base64
                chunk = base64.b64decode(state_b64)
                self._plugin.set_chunk(chunk)
            except Exception:
                pass

        self._ok = True
        print(f"[VST2] Loaded FX: {self._plugin.get_effect_name()} "
              f"({os.path.basename(self.path)}) | params={len(self._param_infos)}",
              file=sys.stderr, flush=True)

    def _apply_rt_params(self) -> None:
        """Sync parameters between RT store and plugin.

        v0.0.20.396: When editor is open, REVERSE direction:
        read from plugin → write to RT store (so editor changes stick).
        When editor is closed: RT store → plugin (normal).
        """
        if self._plugin is None:
            return
        rt = self.rt_params
        if rt is None:
            return

        editor_active = getattr(self._plugin, "_editor_active", False)

        for info in self._param_infos:
            key = self._prefix + info.name
            idx = self._param_name_to_idx.get(info.name, -1)
            if idx < 0:
                continue
            try:
                if editor_active:
                    # REVERSE: plugin → RT store (editor controls the plugin)
                    val = self._plugin.get_parameter(idx)
                    if hasattr(rt, "set_smooth"):
                        rt.set_smooth(key, float(val))
                    elif hasattr(rt, "set_param"):
                        rt.set_param(key, float(val))
                else:
                    # NORMAL: RT store → plugin
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, info.default))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, info.default))
                    else:
                        continue
                    val = max(0.0, min(1.0, val))
                    self._plugin.set_parameter(idx, val)
            except Exception:
                continue

    def process_inplace(self, buf: Any, frames: int, sr: int) -> None:
        """Process audio in-place. buf shape: (frames, 2)."""
        if not self._ok or np is None or self._plugin is None:
            return
        frames = int(frames)
        if frames <= 0 or frames > self.max_frames:
            return

        self._apply_rt_params()

        plugin = self._plugin
        n_in = max(plugin.num_inputs, 1)
        n_out = max(plugin.num_outputs, 1)

        # Copy numpy buf → ctypes input buffers
        try:
            for ch in range(min(n_in, 2)):
                src = buf[:frames, ch] if buf.ndim == 2 else buf[:frames]
                ctypes.memmove(
                    plugin._in_bufs[ch],
                    src.astype(np.float32).ctypes.data,
                    frames * 4,
                )
            # Zero remaining input channels
            for ch in range(2, n_in):
                ctypes.memset(plugin._in_bufs[ch], 0, frames * 4)
        except Exception:
            return

        # Process
        plugin.process_replacing(frames)

        # Copy ctypes output buffers → numpy buf
        try:
            for ch in range(min(n_out, 2)):
                out_arr = np.ctypeslib.as_array(plugin._out_bufs[ch], shape=(self.max_frames,))
                buf[:frames, ch] = out_arr[:frames]
            # If mono output, copy to both channels
            if n_out == 1 and buf.ndim == 2 and buf.shape[1] >= 2:
                buf[:frames, 1] = buf[:frames, 0]
        except Exception:
            pass

    def get_param_infos(self) -> List[Vst2ParamInfo]:
        return list(self._param_infos)

    def shutdown(self) -> None:
        if self._plugin is not None:
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None
        self._ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# Vst2InstrumentEngine — Instrument (MIDI → Audio)
# ═══════════════════════════════════════════════════════════════════════════════

class Vst2InstrumentEngine:
    """Live VST2 Instrument wrapper: receives MIDI, produces audio.

    Same interface as Vst3InstrumentEngine: note_on, note_off, all_notes_off,
    pull(frames, sr), get_param_infos, shutdown.
    """

    def __init__(
        self,
        path: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Dict[str, Any],
        sr: int = 48000,
        max_frames: int = 8192,
        plugin_name: str = "",
    ):
        self._ok = False
        self._err = ""
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self._params_init = dict(params) if isinstance(params, dict) else {}
        self._sr = int(sr) if sr else 48000
        self.max_frames = int(max_frames) if max_frames else 8192
        self.path = str(path)
        self.plugin_name = str(plugin_name or os.path.basename(path))
        self._plugin: Optional[_Vst2Plugin] = None
        self._param_infos: List[Vst2ParamInfo] = []
        self._prefix = f"afx:{self.track_id}:{self.device_id}:vst2:"
        self._param_name_to_idx: Dict[str, int] = {}

        # MIDI accumulator
        self._pending_midi: List[Tuple[int, int, int]] = []  # (status, data1, data2)
        self._active_notes: Dict[int, bool] = {}

        self._load()

    def _load(self) -> None:
        try:
            self._plugin = _Vst2Plugin(self.path, sr=self._sr, block_size=self.max_frames)
        except Exception as e:
            self._err = str(e)
            return

        if not self._plugin._ok:
            self._err = self._plugin._err
            return

        # Extract params
        self._param_infos = _extract_vst2_param_infos(self._plugin)
        for i, info in enumerate(self._param_infos):
            self._param_name_to_idx[info.name] = i

        # Register RT param defaults
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                if hasattr(self.rt_params, "ensure"):
                    self.rt_params.ensure(key, info.default)
            except Exception:
                pass

        # Restore state
        state_b64 = self._params_init.get("__ext_state_b64", "")
        if state_b64:
            try:
                import base64
                chunk = base64.b64decode(state_b64)
                self._plugin.set_chunk(chunk)
            except Exception:
                pass

        self._ok = True
        print(f"[VST2-INST] Loaded instrument: {self._plugin.get_effect_name()} "
              f"({os.path.basename(self.path)}) | params={len(self._param_infos)}",
              file=sys.stderr, flush=True)

    # ── MIDI interface (called from SamplerRegistry) ──

    def note_on(self, pitch: int, velocity: int = 100, **kwargs) -> bool:
        if not self._ok:
            return False
        pitch = max(0, min(127, int(pitch)))
        velocity = max(1, min(127, int(velocity)))
        self._pending_midi.append((0x90, pitch, velocity))
        self._active_notes[pitch] = True
        return True

    def note_off(self, pitch: int = -1) -> None:
        if not self._ok:
            return
        if pitch >= 0:
            pitch = max(0, min(127, int(pitch)))
            self._pending_midi.append((0x80, pitch, 64))
            self._active_notes.pop(pitch, None)
        else:
            # All notes off
            for p in list(self._active_notes.keys()):
                self._pending_midi.append((0x80, p, 64))
            self._active_notes.clear()
            # CC#123 all notes off
            self._pending_midi.append((0xB0, 123, 0))

    def all_notes_off(self) -> None:
        self.note_off(pitch=-1)

    # ── Audio rendering (called from audio callback) ──

    def pull(self, frames: int, sr: int) -> Any:
        """Render audio from accumulated MIDI. Returns numpy (frames, 2) or None."""
        plugin = self._plugin
        if not self._ok or plugin is None or np is None:
            return None
        frames = int(frames)
        if frames <= 0:
            return None
        if frames > self.max_frames:
            frames = self.max_frames

        # v0.0.20.394: Only apply RT params every 10th call for large plugins
        self._pull_count = getattr(self, "_pull_count", 0) + 1
        if len(self._param_infos) < 50 or self._pull_count % 10 == 0:
            self._apply_rt_params()

        # Send accumulated MIDI events to plugin as a batch
        midi_events = list(self._pending_midi)
        self._pending_midi.clear()
        if midi_events:
            plugin.send_midi_events([(s, d1, d2, 0) for (s, d1, d2) in midi_events])

        # Debug: log MIDI events (first 20 calls only)
        if midi_events and getattr(self, "_midi_log_count", 0) < 20:
            self._midi_log_count = getattr(self, "_midi_log_count", 0) + 1
            print(f"[VST2-INST] pull: {len(midi_events)} MIDI events sent, frames={frames}",
                  file=sys.stderr, flush=True)

        # Zero input buffers (instrument — no audio input)
        n_in = max(plugin.num_inputs, 1)
        for ch in range(n_in):
            ctypes.memset(plugin._in_bufs[ch], 0, frames * 4)

        # Process
        plugin.process_replacing(frames)

        # Read output
        n_out = max(plugin.num_outputs, 1)
        try:
            result = np.zeros((frames, 2), dtype=np.float32)
            out0 = np.ctypeslib.as_array(plugin._out_bufs[0], shape=(self.max_frames,))
            result[:frames, 0] = out0[:frames]
            if n_out >= 2:
                out1 = np.ctypeslib.as_array(plugin._out_bufs[1], shape=(self.max_frames,))
                result[:frames, 1] = out1[:frames]
            else:
                result[:frames, 1] = out0[:frames]

            # Debug: log peak level (first 20 non-zero)
            peak = float(np.max(np.abs(result)))
            if peak > 0.0001 and getattr(self, "_peak_log_count", 0) < 20:
                self._peak_log_count = getattr(self, "_peak_log_count", 0) + 1
                print(f"[VST2-INST] pull: AUDIO peak={peak:.6f}",
                      file=sys.stderr, flush=True)

            return result
        except Exception:
            return None

    def _apply_rt_params(self) -> None:
        """v0.0.20.396: Bidirectional sync — reverse when editor is active."""
        plugin = self._plugin
        if plugin is None:
            return
        rt = self.rt_params
        if rt is None:
            return

        editor_active = getattr(plugin, "_editor_active", False)

        for info in self._param_infos:
            key = self._prefix + info.name
            idx = self._param_name_to_idx.get(info.name, -1)
            if idx < 0:
                continue
            try:
                if editor_active:
                    # REVERSE: plugin → RT store
                    val = plugin.get_parameter(idx)
                    if hasattr(rt, "set_smooth"):
                        rt.set_smooth(key, float(val))
                    elif hasattr(rt, "set_param"):
                        rt.set_param(key, float(val))
                else:
                    # NORMAL: RT store → plugin
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, info.default))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, info.default))
                    else:
                        continue
                    val = max(0.0, min(1.0, val))
                    plugin.set_parameter(idx, val)
            except Exception:
                continue

    def get_param_infos(self) -> List[Vst2ParamInfo]:
        return list(self._param_infos)

    def shutdown(self) -> None:
        if self._plugin is not None:
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None
        self._ok = False
