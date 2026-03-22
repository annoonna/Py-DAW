"""Graphics backend selection (Linux Vulkan default).

Goal (v0.0.20.18):
    - Prefer Vulkan on Linux *when available*.
    - Never hard-crash the app just because Vulkan is missing.
    - Keep configuration *early* (before importing PyQt6 / creating QApplication).

This module is intentionally pure-Python (no Qt imports) so it can be
executed safely from `main.py` before any `PyQt6` modules are imported.

Configuration:
    - Environment variable `PYDAW_GFX_BACKEND`:
        * auto (default)
        * vulkan
        * opengl
        * software

Notes:
    - This primarily affects Qt Quick / RHI users (QSG_RHI_BACKEND).
      The current UI is QWidget-based, so the immediate benefit is limited,
      but this prepares the project for Vulkan-backed renderers.
"""

from __future__ import annotations

import ctypes.util
import os
import platform
from typing import Literal


Backend = Literal["auto", "vulkan", "opengl", "software"]


def _is_linux() -> bool:
    try:
        return platform.system().lower() == "linux"
    except Exception:
        return False


def _vulkan_loader_present() -> bool:
    """Best-effort check for a Vulkan loader on the system.

    We *must not* import any GUI libs here. This function only checks common
    loader availability via `ctypes.util.find_library` and a few fallback
    paths.
    """
    try:
        if ctypes.util.find_library("vulkan"):
            return True
    except Exception:
        pass

    # Common loader names/paths (Debian/Ubuntu)
    candidates = (
        "/usr/lib/x86_64-linux-gnu/libvulkan.so.1",
        "/usr/lib/aarch64-linux-gnu/libvulkan.so.1",
        "/usr/lib/libvulkan.so.1",
        "/lib/x86_64-linux-gnu/libvulkan.so.1",
        "/lib/aarch64-linux-gnu/libvulkan.so.1",
        "/lib/libvulkan.so.1",
    )
    return any(os.path.exists(p) for p in candidates)


def configure_graphics_backend() -> str:
    """Configure the preferred graphics backend.

    Returns the chosen backend string.
    """
    requested = str(os.environ.get("PYDAW_GFX_BACKEND", "auto")).strip().lower()
    if requested not in ("auto", "vulkan", "opengl", "software"):
        requested = "auto"

    backend: Backend
    if requested == "auto":
        # Linux default: Vulkan if present, otherwise OpenGL.
        if _is_linux() and _vulkan_loader_present():
            backend = "vulkan"
        else:
            backend = "opengl"
    else:
        backend = requested  # type: ignore

    # These env vars must be set BEFORE importing Qt / creating QApplication.
    # Qt Quick (RHI) backend selection:
    if backend in ("vulkan", "opengl"):
        os.environ.setdefault("QT_QUICK_BACKEND", "rhi")
        os.environ.setdefault("QSG_RHI_BACKEND", backend)
    elif backend == "software":
        # Qt Quick software renderer
        os.environ.setdefault("QT_QUICK_BACKEND", "software")

    # Expose final choice for debugging/logging.
    os.environ["PYDAW_GFX_BACKEND_EFFECTIVE"] = backend
    return backend
