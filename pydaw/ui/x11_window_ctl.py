# -*- coding: utf-8 -*-
"""Pure-Python X11 window control via ctypes + libX11.

Provides Pin (Always-on-Top) and Minimize/Restore for native windows
that are NOT owned by our Qt application (e.g. pedalboard/JUCE VST editors).

NO external tools needed — uses libX11.so.6 directly via ctypes.
libX11 is present on every Linux system with X11/XWayland.

v0.0.20.402 — Created for VST3 editor Pin/Shade support.
              Uses _NET_CLIENT_LIST (EWMH) for reliable window enumeration.
              Recursive XQueryTree was unreliable — WMs hide windows in
              virtual root windows that break recursive enumeration.

Usage:
    from pydaw.ui.x11_window_ctl import x11_find_windows, x11_set_above, x11_iconify, x11_activate

    wids = x11_find_windows("Dexed")     # finds by substring in window title
    if wids:
        x11_set_above(wids[0], True)     # pin to top
        x11_iconify(wids[0])             # minimize
        x11_activate(wids[0])            # restore / bring to front
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Optional

# ── Load libX11 ─────────────────────────────────────────────────────────────

_x11: Optional[ctypes.CDLL] = None
_display = None

# Xlib types
_Window = ctypes.c_ulong
_Atom = ctypes.c_ulong
_Bool = ctypes.c_int
_Status = ctypes.c_int

_SubstructureRedirectMask = (1 << 20)
_SubstructureNotifyMask = (1 << 19)
_ClientMessage = 33


def _load_x11() -> Optional[ctypes.CDLL]:
    global _x11
    if _x11 is not None:
        return _x11
    try:
        _x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
        return _x11
    except OSError:
        return None


def _get_display():
    global _display
    if _display is not None:
        return _display
    x11 = _load_x11()
    if x11 is None:
        return None
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    _display = x11.XOpenDisplay(None)
    return _display


def _get_root() -> int:
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return 0
    x11.XDefaultRootWindow.restype = _Window
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    return x11.XDefaultRootWindow(dpy)


# ── Atom Cache ──────────────────────────────────────────────────────────────

_atom_cache: dict = {}


def _get_atom(name: str) -> int:
    if name in _atom_cache:
        return _atom_cache[name]
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return 0
    x11.XInternAtom.restype = _Atom
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, _Bool]
    atom = x11.XInternAtom(dpy, name.encode("ascii"), 0)
    _atom_cache[name] = atom
    return atom


# ── XEvent for EWMH Client Messages ────────────────────────────────────────

class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", _Bool),
        ("display", ctypes.c_void_p),
        ("window", _Window),
        ("message_type", _Atom),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_char * 192),
    ]


# ── Read X11 Window Properties ─────────────────────────────────────────────

def _get_window_property_cardinals(wid: int, atom_name: str) -> list:
    """Read an X11 property that is a list of CARDINAL/WINDOW values."""
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return []

    prop_atom = _get_atom(atom_name)
    if prop_atom == 0:
        return []

    actual_type = _Atom()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    prop_return = ctypes.c_void_p()

    x11.XGetWindowProperty.restype = ctypes.c_int
    x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p, _Window, _Atom,
        ctypes.c_long, ctypes.c_long, _Bool, _Atom,
        ctypes.POINTER(_Atom), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_void_p),
    ]

    # AnyPropertyType = 0 — accept any type
    status = x11.XGetWindowProperty(
        dpy, wid, prop_atom,
        0, 0x7FFFFFFF, 0, 0,
        ctypes.byref(actual_type), ctypes.byref(actual_format),
        ctypes.byref(nitems), ctypes.byref(bytes_after),
        ctypes.byref(prop_return),
    )

    result = []
    if status == 0 and prop_return.value and nitems.value > 0:
        fmt = actual_format.value
        n = nitems.value
        if fmt == 32:
            arr = ctypes.cast(prop_return.value, ctypes.POINTER(ctypes.c_ulong))
            result = [arr[i] for i in range(n)]
        x11.XFree(prop_return)

    return result


def _get_window_property_string(wid: int, atom_name: str) -> str:
    """Read an X11 property that is a string (UTF8_STRING or STRING)."""
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return ""

    prop_atom = _get_atom(atom_name)
    if prop_atom == 0:
        return ""

    actual_type = _Atom()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    prop_return = ctypes.c_void_p()

    x11.XGetWindowProperty.restype = ctypes.c_int
    x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p, _Window, _Atom,
        ctypes.c_long, ctypes.c_long, _Bool, _Atom,
        ctypes.POINTER(_Atom), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_void_p),
    ]

    status = x11.XGetWindowProperty(
        dpy, wid, prop_atom,
        0, 0x7FFFFFFF, 0, 0,  # AnyPropertyType
        ctypes.byref(actual_type), ctypes.byref(actual_format),
        ctypes.byref(nitems), ctypes.byref(bytes_after),
        ctypes.byref(prop_return),
    )

    if status == 0 and prop_return.value and nitems.value > 0:
        raw = ctypes.string_at(prop_return.value, nitems.value)
        x11.XFree(prop_return)
        return raw.decode("utf-8", errors="replace")
    return ""


def _get_window_title(wid: int) -> str:
    """Get window title — tries _NET_WM_NAME (UTF-8) first, then WM_NAME."""
    # 1. _NET_WM_NAME — used by JUCE, GTK, Qt, and all modern toolkits
    name = _get_window_property_string(wid, "_NET_WM_NAME")
    if name:
        return name

    # 2. Classic WM_NAME via XFetchName
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return ""
    name_p = ctypes.c_char_p()
    x11.XFetchName.restype = _Status
    x11.XFetchName.argtypes = [ctypes.c_void_p, _Window, ctypes.POINTER(ctypes.c_char_p)]
    status = x11.XFetchName(dpy, wid, ctypes.byref(name_p))
    if status and name_p.value:
        result = name_p.value.decode("utf-8", errors="replace")
        x11.XFree(name_p)
        return result

    return ""


# ── Window Enumeration via _NET_CLIENT_LIST (EWMH) ─────────────────────────

def _get_all_managed_windows() -> list:
    """Get all top-level managed windows from the window manager.

    Uses _NET_CLIENT_LIST — the EWMH standard property that every modern
    window manager (GNOME, KDE, XFCE, i3, sway via XWayland, KWIN) maintains.

    This is MUCH more reliable than recursive XQueryTree which misses
    windows hidden in virtual root windows or reparented frames.
    """
    root = _get_root()
    if root == 0:
        return []

    # Try _NET_CLIENT_LIST first (standard)
    wids = _get_window_property_cardinals(root, "_NET_CLIENT_LIST")
    if wids:
        return wids

    # Fallback: _NET_CLIENT_LIST_STACKING (some WMs only set this)
    wids = _get_window_property_cardinals(root, "_NET_CLIENT_LIST_STACKING")
    return wids


def _get_all_visible_windows() -> list:
    """Get all visible top-level windows.

    v0.0.20.402: Uses ONLY _NET_CLIENT_LIST (fast, no freeze).
    For windows NOT in _NET_CLIENT_LIST (JUCE/pedalboard override-redirect),
    the focus-based detection (x11_get_focused_window) handles it separately.

    IMPORTANT: No XQueryTree tree-walk! That caused app freezes under
    Mutter/GNOME Wayland due to thousands of nested child windows.
    """
    return _get_all_managed_windows()


# ── Public API ──────────────────────────────────────────────────────────────

def x11_find_windows(title_substring: str) -> list:
    """Find all X11 windows whose title contains the given substring.

    Uses _NET_CLIENT_LIST (EWMH) for reliable enumeration of ALL managed
    top-level windows. Checks both _NET_WM_NAME and WM_NAME.

    Returns list of window IDs (integers). Empty list if nothing found.

    This function is GENERIC — works with ANY plugin name.
    """
    if not title_substring:
        return []

    if not x11_available():
        return []

    needle = title_substring.lower()
    found = []

    all_windows = _get_all_visible_windows()
    for wid in all_windows:
        try:
            name = _get_window_title(wid)
            if name and needle in name.lower():
                found.append(wid)
        except Exception:
            continue

    if found:
        print(f"[X11] Found {len(found)} window(s) matching '{title_substring}': "
              f"{[f'0x{w:x}' for w in found]}",
              file=sys.stderr, flush=True)
    return found


def x11_set_above(wid: int, enable: bool) -> bool:
    """Set or remove Always-on-Top (_NET_WM_STATE_ABOVE) for a window.

    Uses EWMH client message to the root window — works with all
    compliant window managers (GNOME, KDE, XFCE, i3, etc.).
    """
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return False

    root = _get_root()
    if root == 0:
        return False

    atom_state = _get_atom("_NET_WM_STATE")
    atom_above = _get_atom("_NET_WM_STATE_ABOVE")
    if atom_state == 0 or atom_above == 0:
        return False

    action = 1 if enable else 0

    event = _XEvent()
    event.xclient.type = _ClientMessage
    event.xclient.send_event = 1
    event.xclient.display = dpy
    event.xclient.window = wid
    event.xclient.message_type = atom_state
    event.xclient.format = 32
    event.xclient.data[0] = action
    event.xclient.data[1] = atom_above
    event.xclient.data[2] = 0
    event.xclient.data[3] = 1
    event.xclient.data[4] = 0

    x11.XSendEvent.restype = _Status
    x11.XSendEvent.argtypes = [
        ctypes.c_void_p, _Window, _Bool, ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]

    mask = _SubstructureRedirectMask | _SubstructureNotifyMask
    status = x11.XSendEvent(dpy, root, 0, mask, ctypes.byref(event))
    x11.XFlush(dpy)

    print(f"[X11] set_above({'ON' if enable else 'OFF'}) wid=0x{wid:x} status={status}",
          file=sys.stderr, flush=True)
    return status != 0


def x11_iconify(wid: int) -> bool:
    """Minimize (iconify) a window via XIconifyWindow."""
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return False

    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    screen = x11.XDefaultScreen(dpy)

    x11.XIconifyWindow.restype = _Status
    x11.XIconifyWindow.argtypes = [ctypes.c_void_p, _Window, ctypes.c_int]
    status = x11.XIconifyWindow(dpy, wid, screen)
    x11.XFlush(dpy)

    print(f"[X11] iconify wid=0x{wid:x} status={status}",
          file=sys.stderr, flush=True)
    return status != 0


def x11_activate(wid: int) -> bool:
    """Restore and bring a window to front via _NET_ACTIVE_WINDOW."""
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return False

    root = _get_root()
    if root == 0:
        return False

    atom_active = _get_atom("_NET_ACTIVE_WINDOW")
    if atom_active == 0:
        return False

    x11.XMapRaised.restype = ctypes.c_int
    x11.XMapRaised.argtypes = [ctypes.c_void_p, _Window]
    x11.XMapRaised(dpy, wid)

    event = _XEvent()
    event.xclient.type = _ClientMessage
    event.xclient.send_event = 1
    event.xclient.display = dpy
    event.xclient.window = wid
    event.xclient.message_type = atom_active
    event.xclient.format = 32
    event.xclient.data[0] = 2
    event.xclient.data[1] = 0
    event.xclient.data[2] = 0
    event.xclient.data[3] = 0
    event.xclient.data[4] = 0

    x11.XSendEvent.restype = _Status
    x11.XSendEvent.argtypes = [
        ctypes.c_void_p, _Window, _Bool, ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]

    mask = _SubstructureRedirectMask | _SubstructureNotifyMask
    status = x11.XSendEvent(dpy, root, 0, mask, ctypes.byref(event))
    x11.XFlush(dpy)

    print(f"[X11] activate wid=0x{wid:x} status={status}",
          file=sys.stderr, flush=True)
    return status != 0


def x11_available() -> bool:
    """Check if X11 window control is available."""
    return _load_x11() is not None and _get_display() is not None


def x11_get_wm_class(wid: int) -> str:
    """Get WM_CLASS for a window (JUCE, GTK, Qt set this to identify the app)."""
    return _get_window_property_string(wid, "WM_CLASS")


def x11_find_editor_candidates(exclude_title: str = "Py DAW") -> list:
    """Find windows that are likely VST editor windows.

    Returns ALL managed windows that are NOT our DAW main window.
    This catches JUCE/pedalboard windows even when they have EMPTY titles
    (which is exactly what happens with Surge XT via pedalboard).

    Returns list of (wid, title, wm_class) tuples.
    """
    exclude = exclude_title.lower()
    result = []

    for wid in _get_all_visible_windows():
        try:
            title = _get_window_title(wid)
            if title and exclude in title.lower():
                continue
            wm_class = x11_get_wm_class(wid)
            result.append((wid, title, wm_class))
        except Exception:
            continue

    if result:
        import sys
        print(f"[X11] Editor candidates (non-DAW windows): "
              f"{[(f'0x{w:x}', t or '<empty>', c or '<no-class>') for w, t, c in result]}",
              file=sys.stderr, flush=True)
    return result


def x11_list_all_windows() -> list:
    """Debug: list all managed windows with titles + WM_CLASS."""
    result = []
    for wid in _get_all_visible_windows():
        try:
            title = _get_window_title(wid)
            wm_class = x11_get_wm_class(wid)
            result.append((wid, title, wm_class))
        except Exception:
            result.append((wid, "<e>", ""))
    return result

# ── Focus-based Window Detection (v0.0.20.402) ────────────────────────────
# Instead of searching the entire X11 tree (which freezes under Mutter/GNOME),
# we simply ask X11 which window has the input focus AFTER the editor opens.
# JUCE/pedalboard's show_editor() creates a window and focuses it.
# One single X11 call — no tree walk, no search, no freeze.

def x11_get_focused_window() -> int:
    """Get the X11 window that currently has the input focus.

    After show_editor() opens a JUCE/pedalboard window, that window
    receives focus. This is the simplest and most reliable way to find it.

    Returns window ID or 0 if not available.
    """
    x11 = _load_x11()
    dpy = _get_display()
    if x11 is None or dpy is None:
        return 0

    focus_wid = _Window()
    revert_to = ctypes.c_int()

    x11.XGetInputFocus.restype = None
    x11.XGetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Window),
        ctypes.POINTER(ctypes.c_int),
    ]
    x11.XGetInputFocus(dpy, ctypes.byref(focus_wid), ctypes.byref(revert_to))

    wid = focus_wid.value
    # Filter out root window and PointerRoot (1)
    root = _get_root()
    if wid in (0, 1, root):
        return 0

    print(f"[X11] Focused window: 0x{wid:x}", file=sys.stderr, flush=True)
    return wid
