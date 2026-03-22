"""Arranger GPU Waveform Overlay (v0.0.20.14).

Integrates WaveformGLRenderer as a transparent overlay on top of the
ArrangerCanvas. The overlay renders waveforms and clip backgrounds via
OpenGL (or QPainter fallback), freeing CPU for audio processing.

Usage in ArrangerCanvas.__init__:
    from pydaw.ui.arranger_gl_overlay import ArrangerGLOverlay
    self._gl_overlay = ArrangerGLOverlay(self)
    self._gl_overlay.set_clip_data(clips_list)

The overlay:
- Is a child widget of ArrangerCanvas, stacked on top
- Receives mouse events pass-through (WA_TransparentForMouseEvents)
- Syncs viewport (scroll, zoom) from parent
- Falls back to QPainter if OpenGL is unavailable
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None

from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget

from pydaw.utils.logging_setup import get_logger

log = get_logger(__name__)

# Try to import GPU renderer
_GL_OVERLAY_AVAILABLE = False
try:
    from pydaw.ui.gpu_waveform_renderer import (
        WaveformGLRenderer, WaveformVBOCache, prepare_waveform_vbo,
        _GL_AVAILABLE,
    )
    _GL_OVERLAY_AVAILABLE = True
except ImportError:
    _GL_AVAILABLE = False


class ArrangerGLOverlay:
    """Manages a WaveformGLRenderer as an overlay on ArrangerCanvas.

    Handles:
    - Creation and positioning of the GL widget as a child of the canvas
    - Syncing viewport (scroll offset, zoom) from the arranger
    - Feeding clip data (positions, waveform peaks) to the renderer
    - Playhead cursor sync from transport
    - Fallback detection and graceful degradation
    """

    def __init__(self, canvas: QWidget, enabled: bool = True):
        self._canvas = canvas
        self._enabled = enabled and _GL_OVERLAY_AVAILABLE and _GL_AVAILABLE
        self._renderer: Optional[Any] = None
        self._clip_data: List[Dict[str, Any]] = []
        self._playhead_x: float = -1.0

        if self._enabled:
            try:
                self._renderer = WaveformGLRenderer(parent=canvas)
                self._renderer.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                self._renderer.setGeometry(canvas.rect())
                self._renderer.show()
                self._renderer.raise_()
                log.info("ArrangerGLOverlay: OpenGL waveform overlay aktiv")
            except Exception as e:
                log.warning(f"ArrangerGLOverlay: GL init failed, fallback: {e}")
                self._enabled = False
                self._renderer = None

        # Sync timer (v0.0.20.584: 30fps — was 60fps, saves ~30 callbacks/s)
        self._sync_timer = QTimer()
        self._sync_timer.setInterval(33)
        self._sync_timer.timeout.connect(self._sync_viewport)
        if self._enabled:
            self._sync_timer.start()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def renderer(self) -> Optional[Any]:
        return self._renderer

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if self._renderer is not None:
            self._renderer.setVisible(enabled)
            if enabled:
                self._sync_timer.start()
            else:
                self._sync_timer.stop()

    def set_clip_data(self, clips: List[Dict[str, Any]]) -> None:
        """Update clip data for rendering.

        Each clip dict: x, y, width, height, color, waveform_peaks, label
        """
        self._clip_data = clips
        if self._renderer is not None and self._enabled:
            try:
                self._renderer.set_clips(clips)
                self._renderer.update()
            except Exception:
                pass

    def set_playhead(self, x_position: float) -> None:
        self._playhead_x = x_position
        if self._renderer is not None and self._enabled:
            try:
                self._renderer.set_playhead(x_position)
            except Exception:
                pass

    def set_viewport(self, offset_x: float, offset_y: float,
                     zoom_x: float, zoom_y: float) -> None:
        if self._renderer is not None and self._enabled:
            try:
                self._renderer.set_viewport(offset_x, offset_y, zoom_x, zoom_y)
            except Exception:
                pass

    def resize(self, width: int, height: int) -> None:
        if self._renderer is not None:
            self._renderer.setGeometry(0, 0, width, height)

    def _sync_viewport(self) -> None:
        if not self._enabled or self._renderer is None:
            return
        try:
            canvas = self._canvas
            if (self._renderer.width() != canvas.width() or
                    self._renderer.height() != canvas.height()):
                self._renderer.setGeometry(0, 0, canvas.width(), canvas.height())
            self._renderer.raise_()
        except Exception:
            pass

    def hide(self) -> None:
        if self._renderer is not None:
            self._renderer.hide()
        self._sync_timer.stop()

    def show(self) -> None:
        if self._renderer is not None and self._enabled:
            self._renderer.show()
            self._renderer.raise_()
            self._sync_timer.start()

    def destroy(self) -> None:
        self._sync_timer.stop()
        if self._renderer is not None:
            try:
                self._renderer.hide()
                self._renderer.setParent(None)
                self._renderer.deleteLater()
            except Exception:
                pass
            self._renderer = None


def prepare_clips_for_overlay(
    project: Any,
    beats_per_pixel: float,
    track_height: int,
    scroll_x: float = 0.0,
    scroll_y: float = 0.0,
) -> List[Dict[str, Any]]:
    """Convert project clips to overlay-compatible format."""
    if project is None:
        return []

    clips_data = []
    tracks = getattr(project, "tracks", []) or []
    track_indices = {t.id: i for i, t in enumerate(tracks)}

    CLIP_COLORS = [
        (0, 180, 220), (220, 120, 30), (120, 220, 80),
        (220, 60, 180), (80, 140, 220), (220, 200, 40),
        (160, 80, 220), (40, 200, 160),
    ]

    for clip in getattr(project, "clips", []) or []:
        try:
            track_idx = track_indices.get(getattr(clip, "track_id", ""), -1)
            if track_idx < 0:
                continue

            start_beats = float(getattr(clip, "start_beats", 0.0) or 0.0)
            length_beats = float(getattr(clip, "length_beats", 4.0) or 4.0)

            x = start_beats / max(0.001, beats_per_pixel) - scroll_x
            y = track_idx * track_height - scroll_y
            width = length_beats / max(0.001, beats_per_pixel)
            height = track_height - 2

            color = CLIP_COLORS[track_idx % len(CLIP_COLORS)]

            clip_dict = {
                "x": x, "y": y, "width": width, "height": height,
                "color": QColor(*color),
                "waveform_peaks": None,
                "label": str(getattr(clip, "name", "") or ""),
                "kind": str(getattr(clip, "kind", "") or ""),
                "clip_id": str(getattr(clip, "id", "") or ""),
            }

            if clip_dict["kind"] == "audio" and np is not None:
                source_path = getattr(clip, "source_path", None)
                if source_path and _GL_OVERLAY_AVAILABLE:
                    try:
                        import soundfile as sf
                        data, _ = sf.read(str(source_path), dtype="float32",
                                          always_2d=True)
                        target_w = max(8, int(width))
                        peaks = prepare_waveform_vbo(data, target_width=target_w)
                        clip_dict["waveform_peaks"] = peaks
                    except Exception:
                        pass

            clips_data.append(clip_dict)
        except Exception:
            continue

    return clips_data
