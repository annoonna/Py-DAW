"""Graphics backend selection — Cross-Platform (Linux/macOS/Windows).

v0.0.20.733 — Runtime platform detection:
    - macOS:   Metal (via wgpu) → OpenGL (deprecated) → Software
    - Linux:   Vulkan → OpenGL → Software
    - Windows: DirectX → Vulkan → OpenGL → Software

This module is intentionally pure-Python (no Qt imports) so it can be
executed safely from `main.py` before any PySide6 modules are imported.

Configuration:
    - Environment variable `PYDAW_GFX_BACKEND`:
        * auto (default) — picks the best for your OS
        * metal    — macOS only
        * vulkan   — Linux/Windows
        * opengl   — all platforms (deprecated on macOS)
        * software — QPainter fallback, works everywhere

    - Environment variable `PYDAW_GPU_WAVEFORMS`:
        * 1 (default) — GPU-accelerated waveform rendering
        * 0           — Force QPainter software rendering
"""

from __future__ import annotations

import ctypes.util
import os
import platform
import sys
from typing import Literal

Backend = Literal["auto", "metal", "vulkan", "opengl", "directx", "software"]

# ── Platform Detection ──

def _system() -> str:
    """Return 'linux', 'macos', or 'windows'."""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    elif s == "linux":
        return "linux"
    elif s == "windows":
        return "windows"
    return s

def _is_linux() -> bool:
    return _system() == "linux"

def _is_macos() -> bool:
    return _system() == "macos"

def _is_windows() -> bool:
    return _system() == "windows"

def _is_apple_silicon() -> bool:
    """Detect Apple M1/M2/M3/M4."""
    return _is_macos() and platform.machine() == "arm64"

# ── GPU Availability Checks ──

def _vulkan_available() -> bool:
    """Check if Vulkan loader is present."""
    try:
        if ctypes.util.find_library("vulkan"):
            return True
    except Exception:
        pass
    # Common Linux paths
    candidates = (
        "/usr/lib/x86_64-linux-gnu/libvulkan.so.1",
        "/usr/lib/aarch64-linux-gnu/libvulkan.so.1",
        "/usr/lib/libvulkan.so.1",
        "/lib/x86_64-linux-gnu/libvulkan.so.1",
    )
    return any(os.path.exists(p) for p in candidates)

def _metal_available() -> bool:
    """Check if Metal is available (macOS 10.14+ / Apple Silicon)."""
    if not _is_macos():
        return False
    try:
        # macOS 10.14+ has Metal
        ver = platform.mac_ver()[0]
        if ver:
            parts = ver.split(".")
            major = int(parts[0])
            return major >= 10  # macOS 10.14+ or 11+
    except Exception:
        pass
    return _is_macos()  # Assume yes on macOS

def _wgpu_available() -> bool:
    """Check if wgpu Python module is installed."""
    try:
        import wgpu  # noqa: F401
        return True
    except ImportError:
        return False

def _opengl_available() -> bool:
    """Check if OpenGL is available."""
    try:
        if _is_macos():
            # OpenGL is deprecated on macOS since 10.14
            # Still works but may have issues
            return True
        if ctypes.util.find_library("GL") or ctypes.util.find_library("OpenGL"):
            return True
        # Linux fallback paths
        return os.path.exists("/usr/lib/x86_64-linux-gnu/libGL.so.1")
    except Exception:
        return False

# ── Backend Selection ──

def configure_graphics_backend() -> str:
    """Configure the preferred graphics backend based on platform.

    Returns the chosen backend string.
    Must be called BEFORE importing Qt / creating QApplication.
    """
    requested = str(os.environ.get("PYDAW_GFX_BACKEND", "auto")).strip().lower()
    if requested not in ("auto", "metal", "vulkan", "opengl", "directx", "software"):
        requested = "auto"

    system = _system()
    backend: str

    if requested == "auto":
        if system == "macos":
            # macOS: Metal (via wgpu) → OpenGL → Software
            if _metal_available() and _wgpu_available():
                backend = "metal"
            elif _opengl_available():
                backend = "opengl"
            else:
                backend = "software"

        elif system == "linux":
            # Linux: Vulkan → OpenGL → Software
            if _vulkan_available():
                backend = "vulkan"
            elif _opengl_available():
                backend = "opengl"
            else:
                backend = "software"

        elif system == "windows":
            # Windows: Vulkan → OpenGL → Software
            # (DirectX is handled by Qt automatically via ANGLE)
            if _vulkan_available():
                backend = "vulkan"
            else:
                backend = "opengl"
        else:
            backend = "opengl"
    else:
        backend = requested

    # Set Qt environment variables BEFORE QApplication is created
    if backend == "metal":
        # Qt RHI Metal backend
        os.environ.setdefault("QT_QUICK_BACKEND", "rhi")
        os.environ.setdefault("QSG_RHI_BACKEND", "metal")
        # Disable OpenGL (deprecated on macOS)
        os.environ.setdefault("QT_OPENGL", "software")

    elif backend == "vulkan":
        os.environ.setdefault("QT_QUICK_BACKEND", "rhi")
        os.environ.setdefault("QSG_RHI_BACKEND", "vulkan")

    elif backend == "opengl":
        os.environ.setdefault("QT_QUICK_BACKEND", "rhi")
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

    elif backend == "software":
        os.environ.setdefault("QT_QUICK_BACKEND", "software")

    # Store result for other modules
    os.environ["PYDAW_GFX_BACKEND_EFFECTIVE"] = backend
    os.environ["PYDAW_PLATFORM"] = system

    return backend


def get_effective_backend() -> str:
    """Get the currently active backend (call after configure)."""
    return os.environ.get("PYDAW_GFX_BACKEND_EFFECTIVE", "opengl")


def get_gpu_info() -> dict:
    """Get GPU/platform info for diagnostics."""
    system = _system()
    return {
        "platform": system,
        "arch": platform.machine(),
        "apple_silicon": _is_apple_silicon(),
        "backend": get_effective_backend(),
        "metal_available": _metal_available() if system == "macos" else False,
        "vulkan_available": _vulkan_available(),
        "opengl_available": _opengl_available(),
        "wgpu_available": _wgpu_available(),
        "gpu_waveforms": os.environ.get("PYDAW_GPU_WAVEFORMS", "1") == "1",
    }

