"""Entry point for Py DAW."""

from __future__ import annotations

import faulthandler
import os
import shutil
import signal
import sys
from pathlib import Path

faulthandler.enable(all_threads=True)
try:
    faulthandler.register(signal.SIGABRT, all_threads=True)
except Exception:
    pass


def _purge_local_pycache(project_root: Path) -> None:
    """Remove stale __pycache__/pyc from the local project folder.

    Users often unzip a new TEAM_READY build over an existing folder.
    Python may then load old *.pyc files whose timestamps still match the
    extracted sources (zip preserves mtimes). This can lead to "ghost" bugs
    like missing methods even though the source looks correct.

    Safe: only touches the current project folder.
    """

    try:
        for p in project_root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        for p in project_root.rglob("*.pyc"):
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass


# Avoid writing new bytecode (keeps project folders clean).
try:
    sys.dont_write_bytecode = True
except Exception:
    pass

# Purge local caches unless user explicitly disables it.
if os.environ.get("PYDAW_PURGE_PYCACHE", "1").lower() not in ("0", "false", "no", "off"):
    _purge_local_pycache(Path(__file__).resolve().parent)

# --- Wayland Auto-Fix for VST native editors (v0.0.20.398)
# VST2/VST3 native editors require X11 window embedding (winId).
# On Wayland, Qt must run under XWayland. We detect Wayland and force xcb
# BEFORE any Qt imports, so the entire app runs under XWayland.
# User can override: PYDAW_ALLOW_WAYLAND=1 python3 main.py
try:
    if os.environ.get("PYDAW_ALLOW_WAYLAND", "").lower() not in ("1", "true", "yes"):
        _sess = (os.environ.get("XDG_SESSION_TYPE", "") or "").lower()
        _has_wayland = bool(os.environ.get("WAYLAND_DISPLAY", ""))
        _qpa = (os.environ.get("QT_QPA_PLATFORM", "") or "").lower()
        if (_sess == "wayland") or _has_wayland or _qpa.startswith("wayland"):
            if not _qpa.startswith("xcb"):
                os.environ["QT_QPA_PLATFORM"] = "xcb"
                print("[PyDAW] Wayland detected — forcing QT_QPA_PLATFORM=xcb for VST editor compatibility")
except Exception:
    pass

# --- Qt Backend: PyQt6 (Linux) oder PySide6 (macOS) automatisch wählen
# Muss VOR allen Qt/pydaw-Imports stehen!
try:
    from pydaw.qt_shim import setup_qt_backend
    _qt_backend = setup_qt_backend()
    # Nur einmal loggen, nicht spammen
    print(f"[PyDAW] Qt Backend: {_qt_backend}")
except Exception as _e:
    print(f"[PyDAW] Qt-Shim Fehler: {_e}")

# --- Graphics backend selection (must happen BEFORE importing Qt)
# Linux default: Vulkan (when available). Override via:
#   PYDAW_GFX_BACKEND=opengl python3 main.py
try:
    from pydaw.utils.gfx_backend import configure_graphics_backend

    configure_graphics_backend()
except Exception:
    # Never block startup.
    pass

from pydaw.app import run

if __name__ == "__main__":
    run()
