# -*- coding: utf-8 -*-
"""Qt hardening utilities (Wayland/Qt6 + PyQt6 safety).

Why this exists
--------------
On some Linux/Wayland setups, PyQt6 can terminate the whole process with SIGABRT
when a Python exception escapes a *Qt virtual method* implemented in Python
(e.g. paintEvent/eventFilter/mouse handlers). SIP/PyQt prints
"Unhandled Python exception" and calls qFatal.

This module installs defensive wrappers around common virtual methods for
*our own* UI classes (pydaw.ui.*) so that exceptions are:
- caught
- logged (once per class+method by default)
- converted to safe defaults

It is deliberately additive: it does not change the normal execution path.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from functools import wraps
from types import ModuleType
from typing import Any, Callable, Dict, Optional, Set, Tuple


log = logging.getLogger(__name__)


# Virtual methods where PyQt6 may abort on uncaught exceptions.
_VIRTUALS: Tuple[str, ...] = (
    "paintEvent",
    "event",
    "eventFilter",
    "timerEvent",
    "resizeEvent",
    "showEvent",
    "hideEvent",
    "closeEvent",
    "contextMenuEvent",
    "keyPressEvent",
    "keyReleaseEvent",
    "mousePressEvent",
    "mouseMoveEvent",
    "mouseReleaseEvent",
    "mouseDoubleClickEvent",
    "wheelEvent",
    "dragEnterEvent",
    "dragMoveEvent",
    "dragLeaveEvent",
    "dropEvent",
)


_DEFAULT_RETURN: Dict[str, Any] = {
    "eventFilter": False,
    "event": False,
}


def _should_log_once() -> bool:
    return os.environ.get("PYDAW_QT_HARDEN_VERBOSE", "0").lower() not in ("1", "true", "yes", "on")


def _wrap_method(cls: type, name: str, fn: Callable[..., Any], seen: Set[Tuple[str, str]]) -> Callable[..., Any]:
    """Return a wrapped method that never lets exceptions escape."""

    @wraps(fn)
    def _wrapped(self, *a, **k):  # noqa: ANN001
        try:
            return fn(self, *a, **k)
        except Exception:
            try:
                key = (f"{cls.__module__}.{cls.__qualname__}", name)
                if (not _should_log_once()) or (key not in seen):
                    seen.add(key)
                    log.exception("Qt hardening: swallowed exception in %s.%s", key[0], name)
            except Exception:
                # Never raise from the wrapper.
                pass
            return _DEFAULT_RETURN.get(name, None)

    return _wrapped


def _iter_ui_modules() -> Tuple[ModuleType, ...]:
    mods = []
    for mn, m in list(sys.modules.items()):
        if not mn.startswith("pydaw.ui"):
            continue
        if isinstance(m, ModuleType):
            mods.append(m)
    return tuple(mods)


def harden_qt_virtuals() -> int:
    """Wrap common Qt virtual methods on pydaw.ui classes.

    Returns
    -------
    int
        Number of method wrappers installed.

    Environment
    -----------
    PYDAW_HARDEN_QT=0  -> disable hardening
    PYDAW_QT_HARDEN_VERBOSE=1 -> log every swallowed exception (default logs once per method)
    """

    if os.environ.get("PYDAW_HARDEN_QT", "1").lower() in ("0", "false", "no", "off"):
        return 0

    wrapped = 0
    seen: Set[Tuple[str, str]] = set()

    for mod in _iter_ui_modules():
        try:
            for name, obj in list(vars(mod).items()):
                if not isinstance(obj, type):
                    continue
                # Only patch our own UI classes.
                if not (getattr(obj, "__module__", "") or "").startswith("pydaw.ui"):
                    continue

                for meth in _VIRTUALS:
                    try:
                        if meth not in obj.__dict__:
                            continue
                        fn = obj.__dict__.get(meth)
                        if not callable(fn):
                            continue
                        # Avoid double-wrapping.
                        if getattr(fn, "__pydaw_hardened__", False):
                            continue
                        new_fn = _wrap_method(obj, meth, fn, seen)
                        try:
                            setattr(new_fn, "__pydaw_hardened__", True)
                        except Exception:
                            pass
                        setattr(obj, meth, new_fn)
                        wrapped += 1
                    except Exception:
                        continue
        except Exception:
            continue

    if wrapped:
        try:
            log.info("Qt hardening active: wrapped %s virtual methods", wrapped)
        except Exception:
            pass
    return wrapped


# -----------------------------------------------------------------------------
# PyQt6 slot safety
# -----------------------------------------------------------------------------

_SAFE_CONNECT_INSTALLED: bool = False
_ORIG_SIGNAL_CONNECT: Optional[Callable[..., Any]] = None
_ORIG_SIGNAL_DISCONNECT: Optional[Callable[..., Any]] = None


def harden_signal_slots() -> bool:
    """Monkey-patch PyQt6 signal.connect to wrap Python slots with try/except.

    Why
    ----
    On some PyQt6/Wayland setups, exceptions raised inside Python slots can be
    escalated by SIP/PyQt into qFatal("Unhandled Python exception") which aborts
    the whole process (SIGABRT).

    This function wraps *Python* callables passed to ``signal.connect`` so that
    exceptions are swallowed and logged, preventing a fatal abort.

    Environment
    -----------
    PYDAW_SAFE_SIGNAL_CONNECT=0  -> disable
    """

    global _SAFE_CONNECT_INSTALLED, _ORIG_SIGNAL_CONNECT, _ORIG_SIGNAL_DISCONNECT  # noqa: PLW0603

    if os.environ.get("PYDAW_SAFE_SIGNAL_CONNECT", "1").lower() in ("0", "false", "no", "off"):
        return False

    if _SAFE_CONNECT_INSTALLED:
        return True

    try:
        from PySide6.QtCore import pyqtBoundSignal  # type: ignore
    except Exception:
        return False

    try:
        _ORIG_SIGNAL_CONNECT = pyqtBoundSignal.connect
    except Exception:
        return False

    try:
        _ORIG_SIGNAL_DISCONNECT = pyqtBoundSignal.disconnect
    except Exception:
        _ORIG_SIGNAL_DISCONNECT = None

    _seen_slot_exc: set[tuple[str, str, str]] = set()
    # Map original python callables -> wrapped safe callables so disconnect() works.
    # Without this, code that does `connect(fn); disconnect(fn)` will fail because
    # the connected object is the wrapper, not the original callable.
    import weakref
    _slot_map: "weakref.WeakKeyDictionary[Callable[..., Any], Callable[..., Any]]" = weakref.WeakKeyDictionary()

    def _wrap_slot(slot: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a python slot so exceptions cannot abort the Qt event loop.

        Also provides a small compatibility feature: if a signal emits extra
        positional args (e.g. QAction.triggered(bool)) but the slot expects
        fewer args (common `lambda: ...` pattern), we retry with fewer args.
        """
        # Avoid double wrapping.
        if getattr(slot, "__pydaw_safe_slot__", False):
            return slot

        @wraps(slot)
        def _safe(*a, **k):  # noqa: ANN001
            tb = ''
            try:
                return slot(*a, **k)
            except TypeError as e:
                tb = traceback.format_exc()
                # Try again with fewer positional args (ignore extra signal args).
                try:
                    if a:
                        for n in range(len(a) - 1, -1, -1):
                            try:
                                return slot(*a[:n], **k)
                            except TypeError:
                                continue
                except Exception:
                    pass
                # Fall through to logging/swallowing.
                exc = e
            except Exception as e:  # noqa: BLE001
                tb = traceback.format_exc()
                exc = e

            # Log once per (slot, exc_type, message) unless verbose is enabled.
            try:
                key = (repr(slot), type(exc).__name__, str(exc))
                if (not _should_log_once()) or (key not in _seen_slot_exc):
                    _seen_slot_exc.add(key)
                    log.error("Qt hardening: swallowed exception in slot %r\n%s", slot, tb)
            except Exception:
                try:
                    traceback.print_exc()
                except Exception:
                    pass
            return None

        try:
            setattr(_safe, "__pydaw_safe_slot__", True)
        except Exception:
            pass
        try:
            setattr(_safe, "__pydaw_orig_slot__", slot)
        except Exception:
            pass
        return _safe

    def _safe_connect(self, slot, *args, **kwargs):  # noqa: ANN001
        try:
            # Skip signal-to-signal connections.
            if isinstance(slot, pyqtBoundSignal):
                return _ORIG_SIGNAL_CONNECT(self, slot, *args, **kwargs)
            # Only wrap Python callables.
            if callable(slot):
                orig = slot
                slot = _wrap_slot(slot)
                try:
                    # store mapping for disconnect
                    _slot_map[orig] = slot
                except Exception:
                    pass
            return _ORIG_SIGNAL_CONNECT(self, slot, *args, **kwargs)
        except Exception:
            # Never allow connect() itself to raise during UI construction.
            try:
                log.exception("Qt hardening: swallowed exception in signal.connect")
            except Exception:
                pass
            return None

    def _safe_disconnect(self, slot=None):  # noqa: ANN001
        """Disconnect with support for original (pre-wrapped) python callables."""
        try:
            if _ORIG_SIGNAL_DISCONNECT is None:
                # Fallback: best effort
                return None
            if slot is None:
                return _ORIG_SIGNAL_DISCONNECT(self)
            # If caller passes the original slot, translate to the wrapped callable.
            try:
                if callable(slot) and (slot in _slot_map):
                    slot = _slot_map.get(slot, slot)
            except Exception:
                pass
            return _ORIG_SIGNAL_DISCONNECT(self, slot)
        except TypeError as e:
            # Harmlos, kommt vor wenn disconnect() auf eine nicht-verbundene Methode aufgerufen wird.
            try:
                if "is not connected" in str(e):
                    return None
            except Exception:
                pass
            try:
                log.exception("Qt hardening: swallowed TypeError in signal.disconnect")
            except Exception:
                pass
            return None
        except Exception:
            try:
                log.exception("Qt hardening: swallowed exception in signal.disconnect")
            except Exception:
                pass
            return None

    try:
        pyqtBoundSignal.connect = _safe_connect  # type: ignore[assignment]
        # Also patch disconnect so "connect(fn); disconnect(fn)" keeps working.
        try:
            pyqtBoundSignal.disconnect = _safe_disconnect  # type: ignore[assignment]
        except Exception:
            pass
        _SAFE_CONNECT_INSTALLED = True
        log.info("Qt hardening active: safe signal.connect installed")
        return True
    except Exception:
        return False
