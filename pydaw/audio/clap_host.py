# -*- coding: utf-8 -*-
"""CLAP plugin hosting for Py_DAW via ctypes — zero external dependencies.

Design goals
------------
- SAFE: if loading fails, nothing crashes; ClapFx becomes no-op.
- Real-time friendly: load + connect at build time; process_inplace() only
  copies buffers + updates controls + calls process().
- Compatible API with Vst2Fx/Vst3Fx (process_inplace, get_param_infos) and
  Vst2InstrumentEngine (note_on, note_off, pull).
- No external dependencies beyond stdlib + numpy.

CLAP overview
-------------
- C ABI: .clap exports clap_entry (clap_plugin_entry_t)
- Entry has init(), deinit(), get_factory()
- Factory has get_plugin_count(), get_plugin_descriptor(), create_plugin()
- Plugin has init(), activate(), start_processing(), process(), ...
- Events are passed via clap_input_events_t / clap_output_events_t
- Parameters via clap.params extension

Standard paths
--------------
- Linux:  /usr/lib/clap/, ~/.clap/
- macOS:  /Library/Audio/Plug-Ins/CLAP/, ~/Library/Audio/Plug-Ins/CLAP/
- Windows: %COMMONPROGRAMFILES%\\CLAP\\, %LOCALAPPDATA%\\Programs\\Common\\CLAP\\

v0.0.20.457 — Initial CLAP native host
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
import threading
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

# ═══════════════════════════════════════════════════════════════════════════════
# CLAP C ABI Constants
# ═══════════════════════════════════════════════════════════════════════════════

CLAP_VERSION_MAJOR = 1
CLAP_VERSION_MINOR = 2
CLAP_VERSION_REVISION = 1

CLAP_PLUGIN_FACTORY_ID = b"clap.plugin-factory"

# Event types (CLAP_CORE_EVENT_SPACE_ID = 0)
CLAP_CORE_EVENT_SPACE_ID = 0
CLAP_EVENT_NOTE_ON = 0
CLAP_EVENT_NOTE_OFF = 1
CLAP_EVENT_NOTE_CHOKE = 2
CLAP_EVENT_NOTE_END = 3
CLAP_EVENT_NOTE_EXPRESSION = 4
CLAP_EVENT_PARAM_VALUE = 5
CLAP_EVENT_PARAM_MOD = 6
CLAP_EVENT_PARAM_GESTURE_BEGIN = 7
CLAP_EVENT_PARAM_GESTURE_END = 8
CLAP_EVENT_TRANSPORT = 9
CLAP_EVENT_MIDI = 10

# Process status
CLAP_PROCESS_ERROR = 0
CLAP_PROCESS_CONTINUE = 1
CLAP_PROCESS_CONTINUE_IF_NOT_QUIET = 2
CLAP_PROCESS_TAIL = 3
CLAP_PROCESS_SLEEP = 4

# Event flags
CLAP_EVENT_IS_LIVE = 1 << 0
CLAP_EVENT_DONT_RECORD = 1 << 1

# Param info flags
CLAP_PARAM_IS_STEPPED = 1 << 0
CLAP_PARAM_IS_PERIODIC = 1 << 1
CLAP_PARAM_IS_HIDDEN = 1 << 2
CLAP_PARAM_IS_READONLY = 1 << 3
CLAP_PARAM_IS_BYPASS = 1 << 4
CLAP_PARAM_IS_AUTOMATABLE = 1 << 5
CLAP_PARAM_IS_AUTOMATABLE_PER_NOTE_ID = 1 << 6
CLAP_PARAM_IS_AUTOMATABLE_PER_KEY = 1 << 7
CLAP_PARAM_IS_AUTOMATABLE_PER_CHANNEL = 1 << 8
CLAP_PARAM_IS_AUTOMATABLE_PER_PORT = 1 << 9
CLAP_PARAM_IS_MODULATABLE = 1 << 10
CLAP_PARAM_IS_MODULATABLE_PER_NOTE_ID = 1 << 11
CLAP_PARAM_IS_MODULATABLE_PER_KEY = 1 << 12
CLAP_PARAM_IS_MODULATABLE_PER_CHANNEL = 1 << 13
CLAP_PARAM_IS_MODULATABLE_PER_PORT = 1 << 14
CLAP_PARAM_REQUIRES_PROCESS = 1 << 15

# Feature strings
CLAP_PLUGIN_FEATURE_INSTRUMENT = "instrument"
CLAP_PLUGIN_FEATURE_AUDIO_EFFECT = "audio-effect"
CLAP_PLUGIN_FEATURE_NOTE_EFFECT = "note-effect"
CLAP_PLUGIN_FEATURE_ANALYZER = "analyzer"

# Size limits
CLAP_NAME_SIZE = 256
CLAP_PATH_SIZE = 1024

# Extension IDs
CLAP_EXT_PARAMS = b"clap.params"
CLAP_EXT_AUDIO_PORTS = b"clap.audio-ports"
CLAP_EXT_NOTE_PORTS = b"clap.note-ports"
CLAP_EXT_GUI = b"clap.gui"
CLAP_EXT_STATE = b"clap.state"  # v0.0.20.533
CLAP_EXT_POSIX_FD_SUPPORT = b"clap.posix-fd-support"
CLAP_EXT_TIMER_SUPPORT = b"clap.timer-support"

# GUI API identifiers
CLAP_WINDOW_API_X11 = b"x11"
CLAP_WINDOW_API_COCOA = b"cocoa"
CLAP_WINDOW_API_WIN32 = b"win32"

# Audio port type
CLAP_PORT_MONO = b"mono"
CLAP_PORT_STEREO = b"stereo"

# POSIX fd flags
CLAP_POSIX_FD_READ = 1 << 0
CLAP_POSIX_FD_WRITE = 1 << 1
CLAP_POSIX_FD_ERROR = 1 << 2

# ═══════════════════════════════════════════════════════════════════════════════
# CLAP C Structures (ctypes)
# ═══════════════════════════════════════════════════════════════════════════════


class clap_version_t(ctypes.Structure):
    _fields_ = [
        ("major", ctypes.c_uint32),
        ("minor", ctypes.c_uint32),
        ("revision", ctypes.c_uint32),
    ]


# --- Host callback types ---
CLAP_HOST_GET_EXTENSION_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)
CLAP_HOST_REQUEST_RESTART_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_HOST_REQUEST_PROCESS_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_HOST_REQUEST_CALLBACK_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


class clap_host_t(ctypes.Structure):
    _fields_ = [
        ("clap_version", clap_version_t),
        ("host_data", ctypes.c_void_p),
        ("name", ctypes.c_char_p),
        ("vendor", ctypes.c_char_p),
        ("url", ctypes.c_char_p),
        ("version", ctypes.c_char_p),
        ("get_extension", CLAP_HOST_GET_EXTENSION_FUNC),
        ("request_restart", CLAP_HOST_REQUEST_RESTART_FUNC),
        ("request_process", CLAP_HOST_REQUEST_PROCESS_FUNC),
        ("request_callback", CLAP_HOST_REQUEST_CALLBACK_FUNC),
    ]


class clap_plugin_descriptor_t(ctypes.Structure):
    _fields_ = [
        ("clap_version", clap_version_t),
        ("id", ctypes.c_char_p),
        ("name", ctypes.c_char_p),
        ("vendor", ctypes.c_char_p),
        ("url", ctypes.c_char_p),
        ("manual_url", ctypes.c_char_p),
        ("support_url", ctypes.c_char_p),
        ("version", ctypes.c_char_p),
        ("description", ctypes.c_char_p),
        ("features", ctypes.POINTER(ctypes.c_char_p)),  # null-terminated array
    ]


# Function pointer types for plugin
CLAP_PLUGIN_INIT_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_PLUGIN_DESTROY_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_PLUGIN_ACTIVATE_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32
)
CLAP_PLUGIN_DEACTIVATE_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_PLUGIN_START_PROCESSING_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_PLUGIN_STOP_PROCESSING_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_PLUGIN_RESET_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_PLUGIN_PROCESS_FUNC = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
CLAP_PLUGIN_GET_EXTENSION_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)
CLAP_PLUGIN_ON_MAIN_THREAD_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


class clap_plugin_t(ctypes.Structure):
    _fields_ = [
        ("desc", ctypes.POINTER(clap_plugin_descriptor_t)),
        ("plugin_data", ctypes.c_void_p),
        ("init", CLAP_PLUGIN_INIT_FUNC),
        ("destroy", CLAP_PLUGIN_DESTROY_FUNC),
        ("activate", CLAP_PLUGIN_ACTIVATE_FUNC),
        ("deactivate", CLAP_PLUGIN_DEACTIVATE_FUNC),
        ("start_processing", CLAP_PLUGIN_START_PROCESSING_FUNC),
        ("stop_processing", CLAP_PLUGIN_STOP_PROCESSING_FUNC),
        ("reset", CLAP_PLUGIN_RESET_FUNC),
        ("process", CLAP_PLUGIN_PROCESS_FUNC),
        ("get_extension", CLAP_PLUGIN_GET_EXTENSION_FUNC),
        ("on_main_thread", CLAP_PLUGIN_ON_MAIN_THREAD_FUNC),
    ]


# --- Audio buffer ---
class clap_audio_buffer_t(ctypes.Structure):
    _fields_ = [
        ("data32", ctypes.POINTER(ctypes.POINTER(ctypes.c_float))),
        ("data64", ctypes.POINTER(ctypes.POINTER(ctypes.c_double))),
        ("channel_count", ctypes.c_uint32),
        ("latency", ctypes.c_uint32),
        ("constant_mask", ctypes.c_uint64),
    ]


# --- Event structures ---
class clap_event_header_t(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("space_id", ctypes.c_uint16),
        ("type", ctypes.c_uint16),
        ("flags", ctypes.c_uint32),
    ]


class clap_event_note_t(ctypes.Structure):
    _fields_ = [
        ("header", clap_event_header_t),
        ("note_id", ctypes.c_int32),
        ("port_index", ctypes.c_int16),
        ("channel", ctypes.c_int16),
        ("key", ctypes.c_int16),
        ("velocity", ctypes.c_double),
    ]


class clap_event_param_value_t(ctypes.Structure):
    _fields_ = [
        ("header", clap_event_header_t),
        ("param_id", ctypes.c_uint32),
        ("cookie", ctypes.c_void_p),
        ("note_id", ctypes.c_int32),
        ("port_index", ctypes.c_int16),
        ("channel", ctypes.c_int16),
        ("key", ctypes.c_int16),
        ("value", ctypes.c_double),
    ]


# --- Input/Output events ---
CLAP_INPUT_EVENTS_SIZE_FUNC = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
CLAP_INPUT_EVENTS_GET_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
CLAP_OUTPUT_EVENTS_TRY_PUSH_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


class clap_input_events_t(ctypes.Structure):
    _fields_ = [
        ("ctx", ctypes.c_void_p),
        ("size", CLAP_INPUT_EVENTS_SIZE_FUNC),
        ("get", CLAP_INPUT_EVENTS_GET_FUNC),
    ]


class clap_output_events_t(ctypes.Structure):
    _fields_ = [
        ("ctx", ctypes.c_void_p),
        ("try_push", CLAP_OUTPUT_EVENTS_TRY_PUSH_FUNC),
    ]


# --- Process structure ---
class clap_process_t(ctypes.Structure):
    _fields_ = [
        ("steady_time", ctypes.c_int64),
        ("frames_count", ctypes.c_uint32),
        ("transport", ctypes.c_void_p),  # optional transport
        ("audio_inputs", ctypes.POINTER(clap_audio_buffer_t)),
        ("audio_outputs", ctypes.POINTER(clap_audio_buffer_t)),
        ("audio_inputs_count", ctypes.c_uint32),
        ("audio_outputs_count", ctypes.c_uint32),
        ("in_events", ctypes.POINTER(clap_input_events_t)),
        ("out_events", ctypes.POINTER(clap_output_events_t)),
    ]


# --- Entry point ---
CLAP_ENTRY_INIT_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_char_p)
CLAP_ENTRY_DEINIT_FUNC = ctypes.CFUNCTYPE(None)
CLAP_ENTRY_GET_FACTORY_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)


class clap_plugin_entry_t(ctypes.Structure):
    _fields_ = [
        ("clap_version", clap_version_t),
        ("init", CLAP_ENTRY_INIT_FUNC),
        ("deinit", CLAP_ENTRY_DEINIT_FUNC),
        ("get_factory", CLAP_ENTRY_GET_FACTORY_FUNC),
    ]


# --- Factory ---
CLAP_FACTORY_GET_PLUGIN_COUNT_FUNC = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
CLAP_FACTORY_GET_PLUGIN_DESCRIPTOR_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
CLAP_FACTORY_CREATE_PLUGIN_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
)


class clap_plugin_factory_t(ctypes.Structure):
    _fields_ = [
        ("get_plugin_count", CLAP_FACTORY_GET_PLUGIN_COUNT_FUNC),
        ("get_plugin_descriptor", CLAP_FACTORY_GET_PLUGIN_DESCRIPTOR_FUNC),
        ("create_plugin", CLAP_FACTORY_CREATE_PLUGIN_FUNC),
    ]


# --- Params extension ---
CLAP_PARAMS_COUNT_FUNC = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
CLAP_PARAMS_GET_INFO_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
CLAP_PARAMS_GET_VALUE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
CLAP_PARAMS_VALUE_TO_TEXT_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double, ctypes.c_char_p, ctypes.c_uint32
)
CLAP_PARAMS_TEXT_TO_VALUE_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_void_p
)
CLAP_PARAMS_FLUSH_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class clap_plugin_params_t(ctypes.Structure):
    _fields_ = [
        ("count", CLAP_PARAMS_COUNT_FUNC),
        ("get_info", CLAP_PARAMS_GET_INFO_FUNC),
        ("get_value", CLAP_PARAMS_GET_VALUE_FUNC),
        ("value_to_text", CLAP_PARAMS_VALUE_TO_TEXT_FUNC),
        ("text_to_value", CLAP_PARAMS_TEXT_TO_VALUE_FUNC),
        ("flush", CLAP_PARAMS_FLUSH_FUNC),
    ]


class clap_param_info_t(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("cookie", ctypes.c_void_p),
        ("name", ctypes.c_char * CLAP_NAME_SIZE),
        ("module", ctypes.c_char * CLAP_PATH_SIZE),
        ("min_value", ctypes.c_double),
        ("max_value", ctypes.c_double),
        ("default_value", ctypes.c_double),
    ]


# --- Audio ports extension ---
class clap_audio_port_info_t(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("name", ctypes.c_char * CLAP_NAME_SIZE),
        ("flags", ctypes.c_uint32),
        ("channel_count", ctypes.c_uint32),
        ("port_type", ctypes.c_char_p),
        ("in_place_pair", ctypes.c_uint32),
    ]


CLAP_AUDIO_PORTS_COUNT_FUNC = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_bool)
CLAP_AUDIO_PORTS_GET_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_bool, ctypes.c_void_p
)


class clap_plugin_audio_ports_t(ctypes.Structure):
    _fields_ = [
        ("count", CLAP_AUDIO_PORTS_COUNT_FUNC),
        ("get", CLAP_AUDIO_PORTS_GET_FUNC),
    ]


# --- GUI extension ---
class clap_window_t(ctypes.Structure):
    _fields_ = [
        ("api", ctypes.c_char_p),
        ("handle", ctypes.c_void_p),  # x11: Window, cocoa: NSView*, win32: HWND
    ]


CLAP_GUI_IS_API_SUPPORTED_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool)
CLAP_GUI_GET_PREFERRED_API_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_CREATE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool)
CLAP_GUI_DESTROY_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_GUI_SET_SCALE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_double)
CLAP_GUI_GET_SIZE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_CAN_RESIZE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_GUI_GET_RESIZE_HINTS_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_ADJUST_SIZE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_SET_SIZE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
CLAP_GUI_SET_PARENT_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_SET_TRANSIENT_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
CLAP_GUI_SUGGEST_TITLE_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p)
CLAP_GUI_SHOW_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_GUI_HIDE_FUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)


class clap_plugin_gui_t(ctypes.Structure):
    _fields_ = [
        ("is_api_supported", CLAP_GUI_IS_API_SUPPORTED_FUNC),
        ("get_preferred_api", CLAP_GUI_GET_PREFERRED_API_FUNC),
        ("create", CLAP_GUI_CREATE_FUNC),
        ("destroy", CLAP_GUI_DESTROY_FUNC),
        ("set_scale", CLAP_GUI_SET_SCALE_FUNC),
        ("get_size", CLAP_GUI_GET_SIZE_FUNC),
        ("can_resize", CLAP_GUI_CAN_RESIZE_FUNC),
        ("get_resize_hints", CLAP_GUI_GET_RESIZE_HINTS_FUNC),
        ("adjust_size", CLAP_GUI_ADJUST_SIZE_FUNC),
        ("set_size", CLAP_GUI_SET_SIZE_FUNC),
        ("set_parent", CLAP_GUI_SET_PARENT_FUNC),
        ("set_transient", CLAP_GUI_SET_TRANSIENT_FUNC),
        ("suggest_title", CLAP_GUI_SUGGEST_TITLE_FUNC),
        ("show", CLAP_GUI_SHOW_FUNC),
        ("hide", CLAP_GUI_HIDE_FUNC),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Host GUI extension (clap_host_gui_t) — required by DISTRHO and many plugins
# ═══════════════════════════════════════════════════════════════════════════════

CLAP_HOST_GUI_RESIZE_HINTS_CHANGED = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
CLAP_HOST_GUI_REQUEST_RESIZE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
CLAP_HOST_GUI_REQUEST_SHOW = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_HOST_GUI_REQUEST_HIDE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)
CLAP_HOST_GUI_CLOSED = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool)


class clap_host_gui_t(ctypes.Structure):
    _fields_ = [
        ("resize_hints_changed", CLAP_HOST_GUI_RESIZE_HINTS_CHANGED),
        ("request_resize", CLAP_HOST_GUI_REQUEST_RESIZE),
        ("request_show", CLAP_HOST_GUI_REQUEST_SHOW),
        ("request_hide", CLAP_HOST_GUI_REQUEST_HIDE),
        ("closed", CLAP_HOST_GUI_CLOSED),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# v0.0.20.533: CLAP State Extension (clap.state) — Plugin state save/load
# ═══════════════════════════════════════════════════════════════════════════════

# clap_istream_t / clap_ostream_t — simple memory-backed streams
# read(stream, buffer, size) -> int64 (bytes read, -1 on error)
# write(stream, buffer, size) -> int64 (bytes written, -1 on error)

CLAP_STREAM_READ_FUNC = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64)
CLAP_STREAM_WRITE_FUNC = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64)


class clap_istream_t(ctypes.Structure):
    _fields_ = [
        ("ctx", ctypes.c_void_p),
        ("read", CLAP_STREAM_READ_FUNC),
    ]


class clap_ostream_t(ctypes.Structure):
    _fields_ = [
        ("ctx", ctypes.c_void_p),
        ("write", CLAP_STREAM_WRITE_FUNC),
    ]


# plugin state extension: save(plugin, stream) -> bool, load(plugin, stream) -> bool
CLAP_PLUGIN_STATE_SAVE = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(clap_ostream_t))
CLAP_PLUGIN_STATE_LOAD = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(clap_istream_t))


class clap_plugin_state_t(ctypes.Structure):
    _fields_ = [
        ("save", CLAP_PLUGIN_STATE_SAVE),
        ("load", CLAP_PLUGIN_STATE_LOAD),
    ]


class _MemoryOutputStream:
    """In-memory output stream for CLAP state save."""

    def __init__(self):
        self.data = bytearray()
        # Create the C callback
        self._write_cb = CLAP_STREAM_WRITE_FUNC(self._write)
        self.stream = clap_ostream_t(
            ctx=ctypes.c_void_p(0),
            write=self._write_cb,
        )

    def _write(self, stream_ptr, buffer, size):
        try:
            size = int(size)
            if size <= 0:
                return 0
            buf = (ctypes.c_char * size).from_address(buffer)
            self.data.extend(buf[:size])
            return size
        except Exception:
            return -1


class _MemoryInputStream:
    """In-memory input stream for CLAP state load."""

    def __init__(self, data: bytes):
        self._data = bytes(data)
        self._pos = 0
        self._read_cb = CLAP_STREAM_READ_FUNC(self._read)
        self.stream = clap_istream_t(
            ctx=ctypes.c_void_p(0),
            read=self._read_cb,
        )

    def _read(self, stream_ptr, buffer, size):
        try:
            size = int(size)
            if size <= 0:
                return 0
            remaining = len(self._data) - self._pos
            to_read = min(size, remaining)
            if to_read <= 0:
                return 0
            chunk = self._data[self._pos:self._pos + to_read]
            ctypes.memmove(buffer, chunk, to_read)
            self._pos += to_read
            return to_read
        except Exception:
            return -1


# ═══════════════════════════════════════════════════════════════════════════════
# Host POSIX FD support (clap_host_posix_fd_support_t)
# ═══════════════════════════════════════════════════════════════════════════════

CLAP_PLUGIN_POSIX_FD_ON_FD = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32)


class clap_plugin_posix_fd_support_t(ctypes.Structure):
    _fields_ = [
        ("on_fd", CLAP_PLUGIN_POSIX_FD_ON_FD),
    ]


CLAP_HOST_POSIX_FD_REGISTER = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32)
CLAP_HOST_POSIX_FD_MODIFY = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32)
CLAP_HOST_POSIX_FD_UNREGISTER = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_int)


class clap_host_posix_fd_support_t(ctypes.Structure):
    _fields_ = [
        ("register_fd", CLAP_HOST_POSIX_FD_REGISTER),
        ("modify_fd", CLAP_HOST_POSIX_FD_MODIFY),
        ("unregister_fd", CLAP_HOST_POSIX_FD_UNREGISTER),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Host timer support (clap_host_timer_support_t)
# ═══════════════════════════════════════════════════════════════════════════════

CLAP_PLUGIN_TIMER_ON_TIMER = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)


class clap_plugin_timer_support_t(ctypes.Structure):
    _fields_ = [
        ("on_timer", CLAP_PLUGIN_TIMER_ON_TIMER),
    ]


CLAP_HOST_TIMER_REGISTER = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
CLAP_HOST_TIMER_UNREGISTER = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_uint32)


class clap_host_timer_support_t(ctypes.Structure):
    _fields_ = [
        ("register_timer", CLAP_HOST_TIMER_REGISTER),
        ("unregister_timer", CLAP_HOST_TIMER_UNREGISTER),
    ]


@CLAP_HOST_GUI_RESIZE_HINTS_CHANGED
def _host_gui_resize_hints_changed(host_ptr):
    pass


@CLAP_HOST_GUI_REQUEST_RESIZE
def _host_gui_request_resize(host_ptr, width, height):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._requested_gui_size = (int(width), int(height))
            inst._main_thread_callback_requested = True
        except Exception:
            pass
    return True


@CLAP_HOST_GUI_REQUEST_SHOW
def _host_gui_request_show(host_ptr):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._gui_requested_visible = True
            inst._main_thread_callback_requested = True
        except Exception:
            pass
    return True


@CLAP_HOST_GUI_REQUEST_HIDE
def _host_gui_request_hide(host_ptr):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._gui_requested_visible = False
        except Exception:
            pass
    return True


@CLAP_HOST_GUI_CLOSED
def _host_gui_closed(host_ptr, was_destroyed):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            if bool(was_destroyed):
                inst._gui_created = False
        except Exception:
            pass


@CLAP_HOST_POSIX_FD_REGISTER
def _host_posix_fd_register(host_ptr, fd, flags):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._registered_gui_fds[int(fd)] = int(flags)
            inst._main_thread_callback_requested = True
        except Exception:
            return False
    return True


@CLAP_HOST_POSIX_FD_MODIFY
def _host_posix_fd_modify(host_ptr, fd, flags):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._registered_gui_fds[int(fd)] = int(flags)
            inst._main_thread_callback_requested = True
        except Exception:
            return False
    return True


@CLAP_HOST_POSIX_FD_UNREGISTER
def _host_posix_fd_unregister(host_ptr, fd):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._registered_gui_fds.pop(int(fd), None)
            inst._main_thread_callback_requested = True
        except Exception:
            return False
    return True


@CLAP_HOST_TIMER_REGISTER
def _host_timer_register(host_ptr, period_ms, timer_id_out):
    inst = _get_host_instance(host_ptr)
    if inst is None:
        return False
    try:
        timer_id = int(inst._next_gui_timer_id)
        inst._next_gui_timer_id += 1
        inst._registered_gui_timers[timer_id] = max(1, int(period_ms))
        if timer_id_out:
            ctypes.cast(timer_id_out, ctypes.POINTER(ctypes.c_uint32)).contents.value = timer_id
        inst._main_thread_callback_requested = True
        return True
    except Exception:
        return False


@CLAP_HOST_TIMER_UNREGISTER
def _host_timer_unregister(host_ptr, timer_id):
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._registered_gui_timers.pop(int(timer_id), None)
            inst._main_thread_callback_requested = True
        except Exception:
            return False
    return True


# Module-level host GUI extension instance (must stay alive!)
_host_gui_ext = clap_host_gui_t(
    resize_hints_changed=_host_gui_resize_hints_changed,
    request_resize=_host_gui_request_resize,
    request_show=_host_gui_request_show,
    request_hide=_host_gui_request_hide,
    closed=_host_gui_closed,
)

_host_posix_fd_ext = clap_host_posix_fd_support_t(
    register_fd=_host_posix_fd_register,
    modify_fd=_host_posix_fd_modify,
    unregister_fd=_host_posix_fd_unregister,
)

_host_timer_ext = clap_host_timer_support_t(
    register_timer=_host_timer_register,
    unregister_timer=_host_timer_unregister,
)

# Per-plugin registry so host callbacks can reach the owning _ClapPlugin
_host_plugin_registry: "weakref.WeakValueDictionary[int, _ClapPlugin]" = weakref.WeakValueDictionary()


def _get_host_instance(host_ptr):
    """Resolve the owning _ClapPlugin from a clap_host_t* callback pointer."""
    try:
        if not host_ptr:
            return None
        host = ctypes.cast(host_ptr, ctypes.POINTER(clap_host_t)).contents
        cookie = int(host.host_data or 0)
        if cookie:
            return _host_plugin_registry.get(cookie)
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Host callback implementations
# ═══════════════════════════════════════════════════════════════════════════════

@CLAP_HOST_GET_EXTENSION_FUNC
def _host_get_extension(host_ptr, extension_id):
    """Return host extension pointers — plugins call this to query host capabilities."""
    try:
        ext_id = extension_id
        if isinstance(ext_id, bytes):
            pass
        elif isinstance(ext_id, str):
            ext_id = ext_id.encode("utf-8")
        else:
            return None

        if ext_id == CLAP_EXT_GUI or ext_id == b"clap.gui":
            return ctypes.addressof(_host_gui_ext)
        if ext_id == CLAP_EXT_POSIX_FD_SUPPORT or ext_id == b"clap.posix-fd-support":
            return ctypes.addressof(_host_posix_fd_ext)
        if ext_id == CLAP_EXT_TIMER_SUPPORT or ext_id == b"clap.timer-support":
            return ctypes.addressof(_host_timer_ext)
    except Exception:
        pass
    return None


@CLAP_HOST_REQUEST_RESTART_FUNC
def _host_request_restart(host_ptr):
    """Plugin requests restart — remember it for a later safe rebuild."""
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._restart_requested = True
        except Exception:
            pass


@CLAP_HOST_REQUEST_PROCESS_FUNC
def _host_request_process(host_ptr):
    """Plugin requests continued processing."""
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._process_requested = True
        except Exception:
            pass


@CLAP_HOST_REQUEST_CALLBACK_FUNC
def _host_request_callback(host_ptr):
    """Plugin requests a main-thread callback for GUI/event work."""
    inst = _get_host_instance(host_ptr)
    if inst is not None:
        try:
            inst._main_thread_callback_requested = True
        except Exception:
            pass


# Host callback wrappers are shared, but each _ClapPlugin gets its own
# clap_host_t instance with host_data pointing back to itself.


# ═══════════════════════════════════════════════════════════════════════════════
# Event list helpers (for passing events to plugin.process())
# ═══════════════════════════════════════════════════════════════════════════════

class _EventList:
    """Manages a list of CLAP events for a single process call."""

    def __init__(self, max_events: int = 256):
        self._events: List[ctypes.Array] = []
        self._max = max_events

        # Create the ctypes callback wrappers (must be kept alive!)
        self._size_cb = CLAP_INPUT_EVENTS_SIZE_FUNC(self._size_func)
        self._get_cb = CLAP_INPUT_EVENTS_GET_FUNC(self._get_func)
        self._push_cb = CLAP_OUTPUT_EVENTS_TRY_PUSH_FUNC(self._push_func)

        self.input_events = clap_input_events_t(
            ctx=ctypes.cast(ctypes.pointer(ctypes.c_int(0)), ctypes.c_void_p),
            size=self._size_cb,
            get=self._get_cb,
        )
        self.output_events = clap_output_events_t(
            ctx=ctypes.cast(ctypes.pointer(ctypes.c_int(0)), ctypes.c_void_p),
            try_push=self._push_cb,
        )

    def _size_func(self, ctx) -> int:
        return len(self._events)

    def _get_func(self, ctx, index) -> int:
        if 0 <= index < len(self._events):
            return ctypes.addressof(self._events[index])
        return 0

    def _push_func(self, ctx, event_ptr) -> bool:
        # We don't process output events from the plugin currently
        return True

    def clear(self):
        self._events.clear()

    def add_note_on(self, key: int, velocity: float = 1.0, channel: int = 0, time: int = 0):
        evt = clap_event_note_t(
            header=clap_event_header_t(
                size=ctypes.sizeof(clap_event_note_t),
                time=time,
                space_id=CLAP_CORE_EVENT_SPACE_ID,
                type=CLAP_EVENT_NOTE_ON,
                flags=0,
            ),
            note_id=-1,
            port_index=0,
            channel=channel,
            key=key,
            velocity=max(0.0, min(1.0, velocity)),
        )
        self._events.append(evt)

    def add_note_off(self, key: int, velocity: float = 0.0, channel: int = 0, time: int = 0):
        evt = clap_event_note_t(
            header=clap_event_header_t(
                size=ctypes.sizeof(clap_event_note_t),
                time=time,
                space_id=CLAP_CORE_EVENT_SPACE_ID,
                type=CLAP_EVENT_NOTE_OFF,
                flags=0,
            ),
            note_id=-1,
            port_index=0,
            channel=channel,
            key=key,
            velocity=max(0.0, min(1.0, velocity)),
        )
        self._events.append(evt)

    def add_param_value(self, param_id: int, value: float, time: int = 0):
        evt = clap_event_param_value_t(
            header=clap_event_header_t(
                size=ctypes.sizeof(clap_event_param_value_t),
                time=time,
                space_id=CLAP_CORE_EVENT_SPACE_ID,
                type=CLAP_EVENT_PARAM_VALUE,
                flags=0,
            ),
            param_id=param_id,
            cookie=None,
            note_id=-1,
            port_index=-1,
            channel=-1,
            key=-1,
            value=value,
        )
        self._events.append(evt)


# ═══════════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClapParamInfo:
    """Single CLAP plugin parameter descriptor."""
    id: int  # clap_id (uint32)
    name: str
    module: str  # hierarchical path like "Oscillator/Frequency"
    min_value: float
    max_value: float
    default_value: float
    flags: int = 0
    is_automatable: bool = True
    is_stepped: bool = False

    @property
    def range(self) -> float:
        return max(self.max_value - self.min_value, 1e-9)


@dataclass
class ClapPluginDescriptor:
    """Descriptor for a single CLAP plugin in a .clap file."""
    id: str          # unique plugin ID (e.g. "com.u-he.Diva")
    name: str
    vendor: str
    version: str
    description: str
    features: List[str] = field(default_factory=list)
    is_instrument: bool = False
    is_effect: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Low-level plugin loading
# ═══════════════════════════════════════════════════════════════════════════════

class _ClapPlugin:
    """Low-level CLAP plugin wrapper (single plugin instance)."""

    def __init__(self, path: str, plugin_id: str, sr: int = 48000, block_size: int = 8192):
        self._ok = False
        self._err = ""
        self._lib = None
        self._entry: Optional[clap_plugin_entry_t] = None
        self._factory_ptr = None
        self._plugin_ptr: Optional[ctypes.POINTER(clap_plugin_t)] = None
        self._plugin: Optional[clap_plugin_t] = None
        self._params_ext: Optional[clap_plugin_params_t] = None
        self._audio_ports_ext = None  # clap_plugin_audio_ports_t
        self._gui_ext = None  # clap_plugin_gui_t
        self._state_ext = None  # v0.0.20.533: clap_plugin_state_t
        self._posix_fd_ext = None  # clap_plugin_posix_fd_support_t
        self._timer_ext = None  # clap_plugin_timer_support_t
        self._path = str(path)
        self._plugin_id = str(plugin_id)
        self._sr = int(sr)
        self._block_size = int(block_size)
        self._activated = False
        self._processing = False
        self._gui_created = False
        self._gui_api = None  # which GUI API is active (x11/cocoa/win32)
        self._main_thread_callback_requested = False
        self._process_requested = False
        self._restart_requested = False
        self._requested_gui_size: Optional[Tuple[int, int]] = None
        self._gui_requested_visible: Optional[bool] = None
        self._gui_last_size: Optional[Tuple[int, int]] = None
        self._registered_gui_fds: Dict[int, int] = {}
        self._registered_gui_timers: Dict[int, int] = {}
        self._next_gui_timer_id = 1
        self._host_cookie = id(self)
        self._host_desc = clap_host_t(
            clap_version=clap_version_t(CLAP_VERSION_MAJOR, CLAP_VERSION_MINOR, CLAP_VERSION_REVISION),
            host_data=ctypes.c_void_p(self._host_cookie),
            name=b"ChronoScaleStudio",
            vendor=b"Py_DAW",
            url=b"https://github.com/pydaw",
            version=b"0.0.20.470",
            get_extension=_host_get_extension,
            request_restart=_host_request_restart,
            request_process=_host_request_process,
            request_callback=_host_request_callback,
        )
        _host_plugin_registry[self._host_cookie] = self

        # Audio buffers — initially 2 channels, will be rebuilt after audio-ports query
        self._n_in_channels = 2
        self._n_out_channels = 2
        self._n_channels = 2  # max(in, out) for buffer allocation
        self._in_ptrs = None
        self._out_ptrs = None
        self._in_bufs = []
        self._out_bufs = []
        self._audio_in = None
        self._audio_out = None

        # Event list
        self._events = _EventList()
        self._out_events_list = _EventList()

        self._load()

    def _setup_audio_buffers(self) -> None:
        """(Re)create audio buffers with current channel counts."""
        n = max(self._n_in_channels, self._n_out_channels, 1)
        self._n_channels = n
        self._in_ptrs = (ctypes.POINTER(ctypes.c_float) * n)()
        self._out_ptrs = (ctypes.POINTER(ctypes.c_float) * n)()
        self._in_bufs = []
        self._out_bufs = []
        for ch in range(n):
            in_buf = (ctypes.c_float * self._block_size)()
            out_buf = (ctypes.c_float * self._block_size)()
            self._in_bufs.append(in_buf)
            self._out_bufs.append(out_buf)
            self._in_ptrs[ch] = ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_float))
            self._out_ptrs[ch] = ctypes.cast(out_buf, ctypes.POINTER(ctypes.c_float))

        self._audio_in = clap_audio_buffer_t(
            data32=ctypes.cast(self._in_ptrs, ctypes.POINTER(ctypes.POINTER(ctypes.c_float))),
            data64=None,
            channel_count=self._n_in_channels,
            latency=0,
            constant_mask=0,
        )
        self._audio_out = clap_audio_buffer_t(
            data32=ctypes.cast(self._out_ptrs, ctypes.POINTER(ctypes.POINTER(ctypes.c_float))),
            data64=None,
            channel_count=self._n_out_channels,
            latency=0,
            constant_mask=0,
        )

    def _load(self) -> None:
        try:
            # Load shared library
            self._lib = ctypes.cdll.LoadLibrary(self._path)
        except Exception as e:
            self._err = f"dlopen failed: {e}"
            return

        # Get entry point
        try:
            entry_ptr = ctypes.cast(
                getattr(self._lib, "clap_entry"),
                ctypes.POINTER(clap_plugin_entry_t),
            )
            self._entry = entry_ptr.contents
        except Exception as e:
            self._err = f"clap_entry not found: {e}"
            return

        # Init entry
        try:
            path_bytes = self._path.encode("utf-8")
            if not self._entry.init(path_bytes):
                self._err = "clap_entry.init() returned false"
                return
        except Exception as e:
            self._err = f"clap_entry.init() failed: {e}"
            return

        # Get factory
        try:
            factory_void = self._entry.get_factory(CLAP_PLUGIN_FACTORY_ID)
            if not factory_void:
                self._err = "get_factory() returned null"
                self._entry.deinit()
                return
            self._factory_ptr = ctypes.cast(factory_void, ctypes.POINTER(clap_plugin_factory_t))
        except Exception as e:
            self._err = f"get_factory failed: {e}"
            self._entry.deinit()
            return

        # Create plugin
        try:
            plugin_id_bytes = self._plugin_id.encode("utf-8")
            plugin_void = self._factory_ptr.contents.create_plugin(
                factory_void,
                ctypes.addressof(self._host_desc),
                plugin_id_bytes,
            )
            if not plugin_void:
                self._err = f"create_plugin({self._plugin_id}) returned null"
                self._entry.deinit()
                return
            self._plugin_ptr = ctypes.cast(plugin_void, ctypes.POINTER(clap_plugin_t))
            self._plugin = self._plugin_ptr.contents
        except Exception as e:
            self._err = f"create_plugin failed: {e}"
            self._entry.deinit()
            return

        # Init plugin
        try:
            if not self._plugin.init(plugin_void):
                self._err = "plugin.init() returned false"
                self._plugin.destroy(plugin_void)
                self._entry.deinit()
                return
        except Exception as e:
            self._err = f"plugin.init() failed: {e}"
            try:
                self._plugin.destroy(plugin_void)
            except Exception:
                pass
            self._entry.deinit()
            return

        # Get params extension
        try:
            params_void = self._plugin.get_extension(plugin_void, CLAP_EXT_PARAMS)
            if params_void:
                self._params_ext = ctypes.cast(
                    params_void, ctypes.POINTER(clap_plugin_params_t)
                ).contents
        except Exception:
            self._params_ext = None

        # Get audio-ports extension — determine actual channel counts
        try:
            ap_void = self._plugin.get_extension(plugin_void, CLAP_EXT_AUDIO_PORTS)
            if ap_void:
                self._audio_ports_ext = ctypes.cast(
                    ap_void, ctypes.POINTER(clap_plugin_audio_ports_t)
                ).contents
                # Query input port 0
                try:
                    n_in = int(self._audio_ports_ext.count(plugin_void, True))
                    if n_in > 0:
                        info = clap_audio_port_info_t()
                        ok = self._audio_ports_ext.get(plugin_void, 0, True, ctypes.addressof(info))
                        if ok and int(info.channel_count) > 0:
                            self._n_in_channels = int(info.channel_count)
                            print(f"[CLAP] Audio input port 0: {self._n_in_channels} channels",
                                  file=sys.stderr, flush=True)
                    else:
                        self._n_in_channels = 0  # instrument, no audio input
                except Exception:
                    pass
                # Query output port 0
                try:
                    n_out = int(self._audio_ports_ext.count(plugin_void, False))
                    if n_out > 0:
                        info = clap_audio_port_info_t()
                        ok = self._audio_ports_ext.get(plugin_void, 0, False, ctypes.addressof(info))
                        if ok and int(info.channel_count) > 0:
                            self._n_out_channels = int(info.channel_count)
                            print(f"[CLAP] Audio output port 0: {self._n_out_channels} channels",
                                  file=sys.stderr, flush=True)
                except Exception:
                    pass
        except Exception:
            pass

        # Get GUI extension
        try:
            gui_void = self._plugin.get_extension(plugin_void, CLAP_EXT_GUI)
            if gui_void:
                self._gui_ext = ctypes.cast(
                    gui_void, ctypes.POINTER(clap_plugin_gui_t)
                ).contents
        except Exception:
            self._gui_ext = None

        # v0.0.20.533: Get state extension (clap.state) for save/load
        try:
            state_void = self._plugin.get_extension(plugin_void, CLAP_EXT_STATE)
            if state_void:
                self._state_ext = ctypes.cast(
                    state_void, ctypes.POINTER(clap_plugin_state_t)
                ).contents
        except Exception:
            self._state_ext = None

        # Optional main-thread GUI async helpers (Linux/X11 especially useful)
        try:
            fd_void = self._plugin.get_extension(plugin_void, CLAP_EXT_POSIX_FD_SUPPORT)
            if fd_void:
                self._posix_fd_ext = ctypes.cast(
                    fd_void, ctypes.POINTER(clap_plugin_posix_fd_support_t)
                ).contents
        except Exception:
            self._posix_fd_ext = None

        try:
            timer_void = self._plugin.get_extension(plugin_void, CLAP_EXT_TIMER_SUPPORT)
            if timer_void:
                self._timer_ext = ctypes.cast(
                    timer_void, ctypes.POINTER(clap_plugin_timer_support_t)
                ).contents
        except Exception:
            self._timer_ext = None

        # Setup audio buffers with correct channel counts
        self._setup_audio_buffers()

        # Activate
        try:
            ok = self._plugin.activate(
                plugin_void,
                float(self._sr),
                32,  # min_frames
                self._block_size,
            )
            if ok:
                self._activated = True
        except Exception as e:
            self._err = f"activate failed: {e}"
            self._plugin.destroy(plugin_void)
            self._entry.deinit()
            return

        # Start processing
        try:
            if self._activated:
                ok = self._plugin.start_processing(plugin_void)
                if ok:
                    self._processing = True
        except Exception:
            pass

        self._ok = True

    def get_param_count(self) -> int:
        if not self._ok or self._params_ext is None or self._plugin_ptr is None:
            return 0
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            return int(self._params_ext.count(plugin_void))
        except Exception:
            return 0

    def get_param_info(self, index: int) -> Optional[ClapParamInfo]:
        if not self._ok or self._params_ext is None or self._plugin_ptr is None:
            return None
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            info = clap_param_info_t()
            ok = self._params_ext.get_info(plugin_void, index, ctypes.addressof(info))
            if not ok:
                return None
            name = info.name.decode("utf-8", errors="replace").rstrip("\x00")
            module = info.module.decode("utf-8", errors="replace").rstrip("\x00")
            return ClapParamInfo(
                id=int(info.id),
                name=name,
                module=module,
                min_value=float(info.min_value),
                max_value=float(info.max_value),
                default_value=float(info.default_value),
                flags=int(info.flags),
                is_automatable=bool(info.flags & CLAP_PARAM_IS_AUTOMATABLE),
                is_stepped=bool(info.flags & CLAP_PARAM_IS_STEPPED),
            )
        except Exception:
            return None

    def get_param_value(self, param_id: int) -> Optional[float]:
        if not self._ok or self._params_ext is None or self._plugin_ptr is None:
            return None
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            out = ctypes.c_double(0.0)
            ok = self._params_ext.get_value(plugin_void, param_id, ctypes.byref(out))
            return float(out.value) if ok else None
        except Exception:
            return None

    # v0.0.20.533: State save/load via clap.state extension

    def get_state(self) -> Optional[bytes]:
        """Save plugin state to bytes via clap.state extension. Returns None if unsupported."""
        if self._state_ext is None or self._plugin_ptr is None:
            return None
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            out_stream = _MemoryOutputStream()
            ok = self._state_ext.save(plugin_void, ctypes.byref(out_stream.stream))
            if ok and out_stream.data:
                return bytes(out_stream.data)
        except Exception as e:
            print(f"[CLAP] get_state failed: {e}", file=sys.stderr, flush=True)
        return None

    def set_state(self, data: bytes) -> bool:
        """Load plugin state from bytes via clap.state extension."""
        if self._state_ext is None or self._plugin_ptr is None or not data:
            return False
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            in_stream = _MemoryInputStream(data)
            ok = self._state_ext.load(plugin_void, ctypes.byref(in_stream.stream))
            if ok:
                print(f"[CLAP] State loaded: {len(data)} bytes", file=sys.stderr, flush=True)
            return bool(ok)
        except Exception as e:
            print(f"[CLAP] set_state failed: {e}", file=sys.stderr, flush=True)
            return False

    def has_state(self) -> bool:
        """Check if the plugin supports clap.state."""
        return self._state_ext is not None

    def process(self, frames: int) -> None:
        """Run the plugin's process function with current buffers and events."""
        if not self._ok or self._plugin_ptr is None or not self._processing:
            return
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            proc = clap_process_t(
                steady_time=-1,
                frames_count=frames,
                transport=None,
                audio_inputs=ctypes.pointer(self._audio_in),
                audio_outputs=ctypes.pointer(self._audio_out),
                audio_inputs_count=1,
                audio_outputs_count=1,
                in_events=ctypes.pointer(self._events.input_events),
                out_events=ctypes.pointer(self._out_events_list.output_events),
            )
            self._plugin.process(plugin_void, ctypes.addressof(proc))
        except Exception:
            pass
        finally:
            self._events.clear()

    def has_gui(self) -> bool:
        """Check if plugin supports a native GUI."""
        if not self._ok or self._gui_ext is None or self._plugin_ptr is None:
            return False
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            # Check platform-specific GUI API
            if sys.platform.startswith("linux"):
                return bool(self._gui_ext.is_api_supported(plugin_void, CLAP_WINDOW_API_X11, False))
            elif sys.platform == "darwin":
                return bool(self._gui_ext.is_api_supported(plugin_void, CLAP_WINDOW_API_COCOA, False))
            elif sys.platform.startswith("win"):
                return bool(self._gui_ext.is_api_supported(plugin_void, CLAP_WINDOW_API_WIN32, False))
        except Exception:
            pass
        return False

    def create_gui(self, parent_window_id: int = 0) -> Tuple[bool, int, int]:
        """Create and embed the plugin GUI into a parent window.

        Args:
            parent_window_id: X11 Window ID / NSView* / HWND to embed into.

        Returns:
            (success, width, height) — size the plugin GUI wants.

        v0.0.20.469: run a staged CLAP main-thread handshake around
        create/set_parent/show.  Some editors (for example Surge XT under
        X11/XWayland) request main-thread work *during* GUI bootstrap; if the
        host only starts pumping after the full create_gui() call returns, the
        native child can stay blank although create_gui() reports success.
        """
        if not self._ok or self._gui_ext is None or self._plugin_ptr is None:
            return False, 0, 0
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)

            # Determine API
            if sys.platform.startswith("linux"):
                api = CLAP_WINDOW_API_X11
            elif sys.platform == "darwin":
                api = CLAP_WINDOW_API_COCOA
            elif sys.platform.startswith("win"):
                api = CLAP_WINDOW_API_WIN32
            else:
                return False, 0, 0

            # Create GUI
            ok = self._gui_ext.create(plugin_void, api, False)
            if not ok:
                return False, 0, 0
            self._gui_created = True
            self._gui_api = api

            # Some plugins queue GUI bootstrap work immediately during create().
            # Pump a short main-thread burst before parent/size/show so delayed
            # native child creation can settle on the real main thread.
            self._main_thread_callback_requested = True
            self.pump_main_thread(force=True, max_calls=8)

            # Best-effort scale handshake (safe no-op when unsupported/ignored).
            try:
                self._gui_ext.set_scale(plugin_void, ctypes.c_double(1.0))
            except Exception:
                pass

            # Get initial size after the first bootstrap callbacks.
            width = ctypes.c_uint32(800)
            height = ctypes.c_uint32(600)
            try:
                self._gui_ext.get_size(plugin_void, ctypes.byref(width), ctypes.byref(height))
            except Exception:
                pass

            # Set parent window only after the host window exists.
            if parent_window_id:
                window = clap_window_t(
                    api=api,
                    handle=ctypes.c_void_p(int(parent_window_id)),
                )
                try:
                    self._gui_ext.set_parent(plugin_void, ctypes.byref(window))
                except Exception:
                    pass
                self._main_thread_callback_requested = True
                self.pump_main_thread(force=True, max_calls=8)

            self._gui_last_size = (int(width.value), int(height.value))

            # Show and immediately service any show-time callback burst.
            self._gui_ext.show(plugin_void)
            self._main_thread_callback_requested = True
            self.pump_main_thread(force=True, max_calls=12)

            return True, int(width.value), int(height.value)
        except Exception as e:
            print(f"[CLAP] create_gui error: {e}", file=sys.stderr, flush=True)
            return False, 0, 0

    def pump_main_thread(self, *, force: bool = False, max_calls: int = 4) -> int:
        """Run pending CLAP main-thread callbacks.

        Some CLAP GUIs (for example Surge XT) request repeated
        request_callback()/on_main_thread() cycles right after GUI creation.
        Without pumping these callbacks the editor window can stay blank even
        though create_gui() succeeded.
        """
        if not self._ok or self._plugin_ptr is None or self._plugin is None:
            return 0
        if not force and not self._main_thread_callback_requested:
            return 0
        plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
        calls = 0
        try:
            self._main_thread_callback_requested = False
            for _ in range(max(1, int(max_calls))):
                self._plugin.on_main_thread(plugin_void)
                calls += 1
                if not force and not self._main_thread_callback_requested:
                    break
                self._main_thread_callback_requested = False
        except Exception:
            pass
        return calls

    def get_registered_gui_fds(self) -> Dict[int, int]:
        try:
            return dict(self._registered_gui_fds)
        except Exception:
            return {}

    def get_registered_gui_timers(self) -> Dict[int, int]:
        try:
            return dict(self._registered_gui_timers)
        except Exception:
            return {}

    def dispatch_gui_fd(self, fd: int, flags: int) -> None:
        if (not self._ok or self._plugin_ptr is None or self._posix_fd_ext is None):
            return
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            self._posix_fd_ext.on_fd(plugin_void, int(fd), int(flags))
        except Exception:
            pass

    def dispatch_gui_timer(self, timer_id: int) -> None:
        if (not self._ok or self._plugin_ptr is None or self._timer_ext is None):
            return
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            self._timer_ext.on_timer(plugin_void, int(timer_id))
        except Exception:
            pass

    def take_requested_gui_size(self) -> Optional[Tuple[int, int]]:
        try:
            size = self._requested_gui_size
            self._requested_gui_size = None
            return size
        except Exception:
            return None

    def take_requested_gui_visibility(self) -> Optional[bool]:
        try:
            visible = self._gui_requested_visible
            self._gui_requested_visible = None
            return visible
        except Exception:
            return None

    def set_gui_size(self, width: int, height: int) -> bool:
        if (not self._gui_created or self._gui_ext is None or
                self._plugin_ptr is None):
            return False
        try:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            w = ctypes.c_uint32(max(1, int(width)))
            h = ctypes.c_uint32(max(1, int(height)))
            try:
                can_resize = bool(self._gui_ext.can_resize(plugin_void))
            except Exception:
                can_resize = False
            if can_resize:
                try:
                    self._gui_ext.adjust_size(plugin_void, ctypes.byref(w), ctypes.byref(h))
                except Exception:
                    pass
                ok = bool(self._gui_ext.set_size(plugin_void, int(w.value), int(h.value)))
            else:
                ok = False
            if ok:
                self._gui_last_size = (int(w.value), int(h.value))
                self._main_thread_callback_requested = True
            return ok
        except Exception:
            return False

    def get_gui_last_size(self) -> Optional[Tuple[int, int]]:
        try:
            return self._gui_last_size
        except Exception:
            return None

    def destroy_gui(self) -> None:
        """Destroy the plugin GUI."""
        if self._gui_created and self._gui_ext is not None and self._plugin_ptr is not None:
            try:
                plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
                self._gui_ext.hide(plugin_void)
                self._gui_ext.destroy(plugin_void)
            except Exception:
                pass
            self._gui_created = False

    def close(self) -> None:
        """Shutdown and destroy the plugin."""
        # Destroy GUI first
        self.destroy_gui()

        try:
            _host_plugin_registry.pop(self._host_cookie, None)
        except Exception:
            pass

        if self._plugin_ptr is not None and self._plugin is not None:
            plugin_void = ctypes.cast(self._plugin_ptr, ctypes.c_void_p)
            try:
                if self._processing:
                    self._plugin.stop_processing(plugin_void)
                    self._processing = False
            except Exception:
                pass
            try:
                if self._activated:
                    self._plugin.deactivate(plugin_void)
                    self._activated = False
            except Exception:
                pass
            try:
                self._plugin.destroy(plugin_void)
            except Exception:
                pass
            self._plugin_ptr = None
            self._plugin = None

        if self._entry is not None:
            try:
                self._entry.deinit()
            except Exception:
                pass
            self._entry = None

        self._ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin enumeration (for scanner)
# ═══════════════════════════════════════════════════════════════════════════════

def enumerate_clap_plugins(path: str) -> List[ClapPluginDescriptor]:
    """Open a .clap file and return descriptors for all plugins inside."""
    results: List[ClapPluginDescriptor] = []
    lib = None
    entry = None
    try:
        lib = ctypes.cdll.LoadLibrary(path)
        entry_ptr = ctypes.cast(
            getattr(lib, "clap_entry"),
            ctypes.POINTER(clap_plugin_entry_t),
        )
        entry = entry_ptr.contents

        path_bytes = path.encode("utf-8")
        if not entry.init(path_bytes):
            return results

        factory_void = entry.get_factory(CLAP_PLUGIN_FACTORY_ID)
        if not factory_void:
            entry.deinit()
            return results

        factory = ctypes.cast(factory_void, ctypes.POINTER(clap_plugin_factory_t)).contents
        count = factory.get_plugin_count(factory_void)

        for i in range(min(count, 256)):  # safety cap
            try:
                desc_void = factory.get_plugin_descriptor(factory_void, i)
                if not desc_void:
                    continue
                desc = ctypes.cast(desc_void, ctypes.POINTER(clap_plugin_descriptor_t)).contents
                plugin_id = (desc.id or b"").decode("utf-8", errors="replace")
                name = (desc.name or b"").decode("utf-8", errors="replace")
                vendor = (desc.vendor or b"").decode("utf-8", errors="replace")
                version = (desc.version or b"").decode("utf-8", errors="replace")
                description = (desc.description or b"").decode("utf-8", errors="replace")

                # Parse features (null-terminated array of char*)
                features: List[str] = []
                is_instrument = False
                is_effect = False
                if desc.features:
                    idx = 0
                    while idx < 64:  # safety cap
                        try:
                            feat_ptr = desc.features[idx]
                            if not feat_ptr:
                                break
                            feat = feat_ptr.decode("utf-8", errors="replace")
                            features.append(feat)
                            if feat == CLAP_PLUGIN_FEATURE_INSTRUMENT:
                                is_instrument = True
                            if feat == CLAP_PLUGIN_FEATURE_AUDIO_EFFECT:
                                is_effect = True
                        except Exception:
                            break
                        idx += 1

                results.append(ClapPluginDescriptor(
                    id=plugin_id,
                    name=name,
                    vendor=vendor,
                    version=version,
                    description=description,
                    features=features,
                    is_instrument=is_instrument,
                    is_effect=is_effect,
                ))
            except Exception:
                continue

        entry.deinit()
    except Exception as e:
        print(f"[CLAP] enumerate_clap_plugins({path}) error: {e}", file=sys.stderr, flush=True)
        if entry is not None:
            try:
                entry.deinit()
            except Exception:
                pass
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def is_available() -> bool:
    """CLAP hosting is always available (ctypes, no external deps)."""
    return True


def availability_hint() -> str:
    return "CLAP Host: OK (ctypes, keine externen Abhängigkeiten)"


def is_clap_instrument(path: str, plugin_id: str = "") -> bool:
    """Check if a CLAP plugin is an instrument (has 'instrument' feature)."""
    try:
        descs = enumerate_clap_plugins(path)
        for d in descs:
            if plugin_id and d.id != plugin_id:
                continue
            if d.is_instrument:
                return True
    except Exception:
        pass
    return False


def describe_controls(path: str, plugin_id: str, sr: int = 48000) -> List[ClapParamInfo]:
    """Load a CLAP plugin temporarily and return all parameter infos."""
    result: List[ClapParamInfo] = []
    plugin = None
    try:
        plugin = _ClapPlugin(path, plugin_id, sr=sr, block_size=512)
        if not plugin._ok:
            return result
        count = plugin.get_param_count()
        for i in range(count):
            info = plugin.get_param_info(i)
            if info is not None:
                result.append(info)
    except Exception as e:
        print(f"[CLAP] describe_controls error: {e}", file=sys.stderr, flush=True)
    finally:
        if plugin is not None:
            try:
                plugin.close()
            except Exception:
                pass
    return result


def build_plugin_reference(path: str, plugin_id: str) -> str:
    """Build a canonical reference string for a CLAP plugin."""
    if plugin_id:
        return f"{path}::{plugin_id}"
    return path


def split_plugin_reference(ref: str) -> Tuple[str, str]:
    """Split a CLAP reference into (path, plugin_id)."""
    if "::" in ref:
        parts = ref.split("::", 1)
        return parts[0], parts[1]
    return ref, ""


# ═══════════════════════════════════════════════════════════════════════════════
# ClapFx — Audio FX wrapper (compatible with FxChain.process_inplace())
# ═══════════════════════════════════════════════════════════════════════════════

class ClapFx:
    """Live CLAP Audio-FX wrapper, compatible with FxChain.process_inplace().

    Same interface as Vst2Fx/Vst3Fx: _ok, process_inplace(buf, frames, sr),
    get_param_infos(), device_id, track_id.
    """

    def __init__(
        self,
        path: str,
        plugin_id: str,
        track_id: str,
        device_id: str,
        rt_params: Any,
        params: Dict[str, Any],
        sr: int = 48000,
        max_frames: int = 8192,
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
        self.plugin_id_str = str(plugin_id)
        self._plugin: Optional[_ClapPlugin] = None
        self._param_infos: List[ClapParamInfo] = []
        self._prefix = f"afx:{self.track_id}:{self.device_id}:clap:"
        self._param_id_to_info: Dict[int, ClapParamInfo] = {}
        self._param_name_to_id: Dict[str, int] = {}

        self._load()

    def _load(self) -> None:
        try:
            self._plugin = _ClapPlugin(
                self.path,
                self.plugin_id_str,
                sr=self._sr,
                block_size=self.max_frames,
            )
        except Exception as e:
            self._err = str(e)
            return

        if not self._plugin._ok:
            self._err = self._plugin._err
            return

        # Extract params
        count = self._plugin.get_param_count()
        for i in range(count):
            info = self._plugin.get_param_info(i)
            if info is not None:
                self._param_infos.append(info)
                self._param_id_to_info[info.id] = info
                self._param_name_to_id[info.name] = info.id

        # Register RT param defaults
        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                # Normalize to 0..1 range for RT store
                norm = (info.default_value - info.min_value) / info.range
                if hasattr(self.rt_params, "ensure"):
                    self.rt_params.ensure(key, norm)
            except Exception:
                pass

        # v0.0.20.533: Restore saved state from project (if available)
        state_b64 = self._params_init.get("__ext_state_b64")
        if state_b64 and self._plugin and self._plugin.has_state():
            try:
                import base64
                state_bytes = base64.b64decode(str(state_b64))
                if self._plugin.set_state(state_bytes):
                    print(f"[CLAP] Restored state from project: {len(state_bytes)} bytes", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[CLAP] State restore failed: {e}", file=sys.stderr, flush=True)

        self._ok = True
        desc_name = ""
        try:
            descs = enumerate_clap_plugins(self.path)
            for d in descs:
                if d.id == self.plugin_id_str:
                    desc_name = d.name
                    break
        except Exception:
            pass
        print(
            f"[CLAP] Loaded FX: {desc_name or self.plugin_id_str} "
            f"({os.path.basename(self.path)}) | params={len(self._param_infos)}",
            file=sys.stderr, flush=True,
        )

    def _apply_rt_params(self) -> None:
        """Sync parameters from RT store → plugin via param-value events."""
        if self._plugin is None or not self._ok:
            return
        rt = self.rt_params
        if rt is None:
            return

        for info in self._param_infos:
            key = self._prefix + info.name
            try:
                norm = 0.5
                if hasattr(rt, "get_smooth"):
                    norm = float(rt.get_smooth(key, (info.default_value - info.min_value) / info.range))
                elif hasattr(rt, "get_param"):
                    norm = float(rt.get_param(key, (info.default_value - info.min_value) / info.range))
                else:
                    continue
                norm = max(0.0, min(1.0, norm))
                # Denormalize to plugin range
                value = info.min_value + norm * info.range
                self._plugin._events.add_param_value(info.id, value, time=0)
            except Exception:
                continue

    def process_inplace(self, buf: Any, frames: int, sr: int) -> None:
        """Process audio in-place. buf shape: (frames, 2).

        Handles mono↔stereo bridging:
        - If plugin expects 1 input: downmix stereo→mono (average L+R)
        - If plugin outputs 1 channel: duplicate to both stereo channels
        """
        if not self._ok or np is None or self._plugin is None:
            return
        frames = int(frames)
        if frames <= 0 or frames > self.max_frames:
            return

        self._apply_rt_params()

        n_in = self._plugin._n_in_channels
        n_out = self._plugin._n_out_channels

        # Copy numpy buf → ctypes input buffers (with mono bridging)
        try:
            if n_in == 1:
                # Stereo → Mono: average both channels
                if buf.ndim == 2 and buf.shape[1] >= 2:
                    mono = ((buf[:frames, 0] + buf[:frames, 1]) * 0.5).astype(np.float32)
                else:
                    mono = buf[:frames].astype(np.float32)
                ctypes.memmove(self._plugin._in_bufs[0], mono.ctypes.data, frames * 4)
            elif n_in >= 2:
                for ch in range(min(n_in, 2)):
                    src = buf[:frames, ch] if buf.ndim == 2 else buf[:frames]
                    ctypes.memmove(
                        self._plugin._in_bufs[ch],
                        src.astype(np.float32).ctypes.data,
                        frames * 4,
                    )
            # n_in == 0: instrument, no audio input (buffers stay zeroed)
        except Exception:
            return

        # Process
        self._plugin.process(frames)

        # Copy ctypes output buffers → numpy buf (with mono bridging)
        try:
            if n_out == 1:
                # Mono → Stereo: duplicate to both channels
                out_arr = np.ctypeslib.as_array(
                    self._plugin._out_bufs[0], shape=(self._plugin._block_size,)
                )
                buf[:frames, 0] = out_arr[:frames]
                if buf.ndim == 2 and buf.shape[1] >= 2:
                    buf[:frames, 1] = out_arr[:frames]
            else:
                for ch in range(min(n_out, 2)):
                    out_arr = np.ctypeslib.as_array(
                        self._plugin._out_bufs[ch], shape=(self._plugin._block_size,)
                    )
                    buf[:frames, ch] = out_arr[:frames]
        except Exception:
            pass

    def get_param_infos(self) -> List[ClapParamInfo]:
        return list(self._param_infos)

    def has_gui(self) -> bool:
        """Check if this CLAP plugin supports a native GUI."""
        return self._plugin is not None and self._plugin.has_gui()

    def get_plugin(self) -> Optional[_ClapPlugin]:
        """Return the underlying _ClapPlugin (for GUI embedding)."""
        return self._plugin

    def get_state_b64(self) -> Optional[str]:
        """v0.0.20.533: Save current plugin state as Base64 string for project persistence."""
        if self._plugin is None or not self._ok:
            return None
        if not self._plugin.has_state():
            return None
        try:
            import base64
            state_bytes = self._plugin.get_state()
            if state_bytes:
                return base64.b64encode(state_bytes).decode("ascii")
        except Exception as e:
            print(f"[CLAP] get_state_b64 FX failed: {e}", file=sys.stderr, flush=True)
        return None

    def shutdown(self) -> None:
        if self._plugin is not None:
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None
        self._ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# ClapInstrumentEngine — Instrument wrapper (Pull-Source for Audio Engine)
# ═══════════════════════════════════════════════════════════════════════════════

class ClapInstrumentEngine:
    """CLAP Instrument engine — receives MIDI, produces audio via pull().

    Same interface as Vst2InstrumentEngine: note_on, note_off, pull, shutdown.
    """

    def __init__(
        self,
        path: str,
        plugin_id: str,
        track_id: str,
        sr: int = 48000,
        block_size: int = 8192,
        params: Optional[Dict[str, Any]] = None,
    ):
        self._ok = False
        self._err = ""
        self.track_id = str(track_id or "")
        self._sr = int(sr) if sr else 48000
        self._block_size = int(block_size) if block_size else 8192
        self.path = str(path)
        self.plugin_id_str = str(plugin_id)
        self._plugin: Optional[_ClapPlugin] = None
        self._param_infos: List[ClapParamInfo] = []
        self._params_init = dict(params) if isinstance(params, dict) else {}
        self._lock = threading.Lock()
        self._pending_notes: List[Tuple[str, int, float]] = []  # (on/off, key, vel)

        self._load()

    def _load(self) -> None:
        try:
            self._plugin = _ClapPlugin(
                self.path,
                self.plugin_id_str,
                sr=self._sr,
                block_size=self._block_size,
            )
        except Exception as e:
            self._err = str(e)
            return

        if not self._plugin._ok:
            self._err = self._plugin._err
            return

        # Extract params
        count = self._plugin.get_param_count()
        for i in range(count):
            info = self._plugin.get_param_info(i)
            if info is not None:
                self._param_infos.append(info)

        # v0.0.20.533: Restore saved state from project (if available)
        state_b64 = self._params_init.get("__ext_state_b64")
        if state_b64 and self._plugin and self._plugin.has_state():
            try:
                import base64
                state_bytes = base64.b64decode(str(state_b64))
                if self._plugin.set_state(state_bytes):
                    print(f"[CLAP] Instrument state restored: {len(state_bytes)} bytes", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[CLAP] Instrument state restore failed: {e}", file=sys.stderr, flush=True)

        self._ok = True
        print(
            f"[CLAP] Loaded Instrument: {self.plugin_id_str} "
            f"({os.path.basename(self.path)}) | params={len(self._param_infos)}",
            file=sys.stderr, flush=True,
        )

    def note_on(self, pitch: int, velocity: int = 100, **kwargs) -> bool:
        if not self._ok:
            return False
        vel_norm = max(0.0, min(1.0, velocity / 127.0))
        with self._lock:
            self._pending_notes.append(("on", int(pitch), vel_norm))
        return True

    def note_off(self, pitch: int = -1) -> None:
        if not self._ok:
            return
        with self._lock:
            self._pending_notes.append(("off", int(pitch), 0.0))

    def all_notes_off(self) -> None:
        """Send note-off for all 128 MIDI keys."""
        with self._lock:
            for k in range(128):
                self._pending_notes.append(("off", k, 0.0))

    def pull(self, frames: int, sr: int) -> Any:
        """Render audio frames. Returns numpy array (frames, 2) or None."""
        if not self._ok or np is None or self._plugin is None:
            return None
        frames = min(int(frames), self._block_size)
        if frames <= 0:
            return None

        # Zero input buffers (instrument generates audio from events only)
        n_buf = max(self._plugin._n_in_channels, self._plugin._n_out_channels, 1)
        for ch in range(n_buf):
            if ch < len(self._plugin._in_bufs):
                ctypes.memset(self._plugin._in_bufs[ch], 0, frames * 4)

        # Send pending notes as events
        with self._lock:
            notes = list(self._pending_notes)
            self._pending_notes.clear()

        for kind, key, vel in notes:
            if kind == "on":
                self._plugin._events.add_note_on(key, vel)
            else:
                self._plugin._events.add_note_off(key)

        # Process
        self._plugin.process(frames)

        # Copy output
        try:
            n_out = self._plugin._n_out_channels
            result = np.zeros((frames, 2), dtype=np.float32)
            for ch in range(min(n_out, 2)):
                out_arr = np.ctypeslib.as_array(
                    self._plugin._out_bufs[ch], shape=(self._plugin._block_size,)
                )
                result[:frames, ch] = out_arr[:frames]
            if n_out == 1:
                result[:frames, 1] = result[:frames, 0]
            return result
        except Exception:
            return None

    def get_param_infos(self) -> List[ClapParamInfo]:
        return list(self._param_infos)

    def has_gui(self) -> bool:
        """Check if this CLAP instrument supports a native GUI."""
        return self._plugin is not None and self._plugin.has_gui()

    def get_plugin(self) -> Optional[_ClapPlugin]:
        """Return the underlying _ClapPlugin (for GUI embedding)."""
        return self._plugin

    def get_state_b64(self) -> Optional[str]:
        """v0.0.20.533: Save current instrument state as Base64 for project persistence."""
        if self._plugin is None or not self._ok:
            return None
        if not self._plugin.has_state():
            return None
        try:
            import base64
            state_bytes = self._plugin.get_state()
            if state_bytes:
                return base64.b64encode(state_bytes).decode("ascii")
        except Exception as e:
            print(f"[CLAP] get_state_b64 Instrument failed: {e}", file=sys.stderr, flush=True)
        return None

    def shutdown(self) -> None:
        if self._plugin is not None:
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None
        self._ok = False


# ═══════════════════════════════════════════════════════════════════════════════
# v0.0.20.533: Project-level CLAP state embedding (analogous to VST3)
# ═══════════════════════════════════════════════════════════════════════════════

def embed_clap_project_state_blobs(project: Any, audio_engine: Any = None) -> int:
    """Embed CLAP plugin state as Base64 blobs in project device params.

    Called during project save. Scans all tracks for ext.clap devices,
    finds the running ClapFx/ClapInstrumentEngine instances from the
    audio engine, and saves their state via clap.state extension.

    Returns the number of blobs updated.
    """
    count = 0
    try:
        tracks = getattr(project, "tracks", []) or []
    except Exception:
        return 0

    # Collect running CLAP instances from audio engine
    fx_map = {}
    inst_map = {}
    if audio_engine is not None:
        try:
            _track_fx = getattr(audio_engine, "_track_audio_fx_map", {}) or {}
            for tid, chain in _track_fx.items():
                if chain is None:
                    continue
                for dev in getattr(chain, "devices", []):
                    if isinstance(dev, ClapFx) and hasattr(dev, "get_state_b64"):
                        fx_map[(str(tid), str(dev.device_id))] = dev
        except Exception:
            pass
        try:
            _inst_engines = getattr(audio_engine, "_vst_instrument_engines", {}) or {}
            for tid, eng in _inst_engines.items():
                if isinstance(eng, ClapInstrumentEngine) and hasattr(eng, "get_state_b64"):
                    inst_map[str(tid)] = eng
        except Exception:
            pass

    for trk in tracks:
        tid = str(getattr(trk, "id", "") or "")
        if not tid:
            continue

        # Check instrument
        if tid in inst_map:
            try:
                eng = inst_map[tid]
                blob = eng.get_state_b64()
                if blob:
                    # Find the instrument device in audio_fx_chain
                    chain = getattr(trk, "audio_fx_chain", None)
                    if isinstance(chain, dict):
                        for dev in (chain.get("devices", []) or []):
                            if isinstance(dev, dict):
                                pid = str(dev.get("plugin_id") or "")
                                if pid.startswith("ext.clap:"):
                                    params = dev.setdefault("params", {})
                                    if str(params.get("__ext_state_b64") or "") != blob:
                                        params["__ext_state_b64"] = blob
                                        count += 1
                    # Also check instrument_state
                    ist = getattr(trk, "instrument_state", None)
                    if isinstance(ist, dict) and ist.get("__ext_path", ""):
                        if str(ist.get("__ext_state_b64") or "") != blob:
                            ist["__ext_state_b64"] = blob
                            count += 1
            except Exception:
                pass

        # Check audio FX chain
        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            continue
        for dev in (chain.get("devices", []) or []):
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get("plugin_id") or "")
            if not pid.startswith("ext.clap:"):
                continue
            did = str(dev.get("id") or "")
            key = (tid, did)
            if key in fx_map:
                try:
                    fx = fx_map[key]
                    blob = fx.get_state_b64()
                    if blob:
                        params = dev.setdefault("params", {})
                        if str(params.get("__ext_state_b64") or "") != blob:
                            params["__ext_state_b64"] = blob
                            count += 1
                except Exception:
                    pass

    if count > 0:
        print(f"[CLAP] Embedded {count} state blob(s) in project", file=sys.stderr, flush=True)
    return count
