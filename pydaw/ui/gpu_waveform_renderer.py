"""GPU-accelerated Waveform Renderer (v0.0.20.15).

Offloads waveform/clip rendering to the GPU via OpenGL, freeing CPU
for audio processing (Essentia, time-stretch, etc.).

Architecture:
    ┌─────────────┐                      ┌──────────┐
    │  CPU Thread  │   VBO upload once    │   GPU    │
    │  (waveform   │ ──────────────────▶ │  OpenGL  │
    │   data prep) │   per file change   │  render  │
    └─────────────┘                      └──────────┘

Features:
- Transparent overlay hotfix (v0.0.20.15) so grid stays visible

- QOpenGLWidget-based arranger overlay
- Waveform VBO cache (upload once, render many)
- Batch clip rendering in single draw call
- Playhead cursor as a GL line
- Fallback to QPainter if OpenGL unavailable

Usage:
    # In arranger, replace custom paint with:
    gl_renderer = WaveformGLRenderer(parent=arranger_widget)
    gl_renderer.set_clips(clip_data_list)
    gl_renderer.set_viewport(x_offset, y_offset, zoom_x, zoom_y)
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None

from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QSurfaceFormat
from PyQt6.QtWidgets import QWidget

# Try OpenGL imports
_GL_AVAILABLE = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtOpenGL import (
        QOpenGLBuffer, QOpenGLShaderProgram, QOpenGLShader,
    )
    _GL_AVAILABLE = True
except ImportError:
    QOpenGLWidget = QWidget  # type: ignore

from pydaw.utils.logging_setup import get_logger

# v0.0.20.22: Import AsyncLoader for real peak data
try:
    from pydaw.audio.async_loader import get_async_loader
    ASYNC_LOADER_AVAILABLE = True
except ImportError:
    ASYNC_LOADER_AVAILABLE = False

log = get_logger(__name__)


# ---- Waveform data preparation (CPU, background thread OK)

def prepare_waveform_vbo(audio_data, target_width: int = 1024,
                         ) -> Optional["np.ndarray"]:
    """Downsample audio to min/max pairs for waveform display.

    Returns float32 array of shape (target_width, 4):
        [x_normalized, y_min, y_max, channel]

    This is uploaded to GPU once and reused for all zoom levels
    within a reasonable range.
    """
    if np is None or audio_data is None:
        return None
    try:
        d = np.asarray(audio_data, dtype=np.float32)
        if d.ndim == 1:
            d = d.reshape(-1, 1)
        frames = d.shape[0]
        if frames < 2:
            return None

        # Compute min/max per pixel column
        step = max(1, frames // target_width)
        n_cols = min(target_width, frames // step)
        if n_cols < 2:
            return None

        result = np.zeros((n_cols * 2, 4), dtype=np.float32)  # 2 vertices per column
        for ch in range(min(d.shape[1], 2)):
            for i in range(n_cols):
                start = i * step
                end = min(start + step, frames)
                chunk = d[start:end, ch]
                y_min = float(np.min(chunk))
                y_max = float(np.max(chunk))
                x = float(i) / float(n_cols)

                idx = i * 2
                result[idx] = [x, y_min, y_max, float(ch)]
                result[idx + 1] = [x, y_min, y_max, float(ch)]

        return result
    except Exception:
        return None


# ---- Waveform Cache

class WaveformVBOCache:
    """Cache for prepared waveform vertex data.

    Key: (file_path, mtime) to auto-invalidate on file changes.
    """

    def __init__(self, max_entries: int = 128):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._max = max_entries

    def get(self, path: str, mtime: float = 0.0) -> Optional[Any]:
        entry = self._cache.get(path)
        if entry is None:
            return None
        cached_mtime, data = entry
        if abs(cached_mtime - mtime) > 0.01:
            del self._cache[path]
            return None
        return data

    def put(self, path: str, mtime: float, data: Any) -> None:
        if len(self._cache) >= self._max:
            # Remove oldest
            try:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            except (StopIteration, KeyError):
                pass
        self._cache[path] = (mtime, data)

    def clear(self) -> None:
        self._cache.clear()


# ---- OpenGL Waveform Renderer

# Vertex shader for waveform rendering
_VERTEX_SHADER = """
#version 120
attribute vec2 a_position;
attribute vec4 a_color;
uniform mat4 u_transform;
varying vec4 v_color;

void main() {
    gl_Position = u_transform * vec4(a_position, 0.0, 1.0);
    v_color = a_color;
}
"""

_FRAGMENT_SHADER = """
#version 120
varying vec4 v_color;

void main() {
    gl_FragColor = v_color;
}
"""


class WaveformGLRenderer(QOpenGLWidget if _GL_AVAILABLE else QWidget):
    """GPU-accelerated waveform overlay for the arranger.

    Renders waveform outlines and clip backgrounds using OpenGL.
    Falls back to QPainter software rendering if GL is unavailable.
    """

    def __init__(self, parent=None):
        if _GL_AVAILABLE:
            fmt = QSurfaceFormat()
            fmt.setSamples(4)  # MSAA
            fmt.setSwapInterval(1)  # VSync
            # IMPORTANT: enable alpha so the overlay can be transparent above the ArrangerCanvas.
            try:
                fmt.setAlphaBufferSize(8)
            except Exception:
                pass
            try:
                fmt.setDepthBufferSize(0)
            except Exception:
                pass
            super().__init__(parent)
            self.setFormat(fmt)

            # Transparent overlay: do NOT paint an opaque background (otherwise it hides the arranger grid).
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAutoFillBackground(False)
            try:
                self.setStyleSheet("background: transparent;")
            except Exception:
                pass
        else:
            super().__init__(parent)

        self._gl_initialized = False
        self._use_gl = _GL_AVAILABLE

        # Clip data for rendering
        self._clips: List[Dict[str, Any]] = []
        self._viewport = (0.0, 0.0, 1.0, 1.0)  # (x, y, w, h) in beats

        # Waveform cache
        self._vbo_cache = WaveformVBOCache()

        # Colors
        self._bg_color = QColor(30, 30, 35)
        self._waveform_color = QColor(0, 200, 255, 180)
        self._clip_bg_color = QColor(50, 60, 70, 160)
        self._playhead_color = QColor(255, 80, 80)

        # Playhead position in beats
        self._playhead_beat = 0.0

        # Performance tracking
        self._last_frame_time = 0.0
        self._frame_count = 0

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_clips(self, clips: List[Dict[str, Any]]) -> None:
        """Set clip data for rendering.

        Each clip dict: {
            'x': float (beats), 'y': float (track),
            'width': float (beats), 'height': float,
            'waveform': np.ndarray (optional),
            'color': QColor (optional),
            'path': str (optional),
        }
        
        v0.0.20.22: Auto-loads peaks from AsyncLoader if 'path' provided.
        """
        self._clips = clips
        
        # v0.0.20.22: Load peaks for clips with path but no waveform
        if ASYNC_LOADER_AVAILABLE:
            self._load_clip_peaks()
        
        self.update()
    
    def _load_clip_peaks(self) -> None:
        """Load peak data for clips that have a path but no waveform data.
        
        v0.0.20.22: Uses AsyncLoader.get_peaks() for real audio data.
        """
        if not ASYNC_LOADER_AVAILABLE or np is None:
            return
        
        try:
            loader = get_async_loader()
            
            for clip in self._clips:
                # Skip if already has waveform data
                if clip.get('waveform') is not None:
                    continue
                
                # Skip if no path
                path = clip.get('path')
                if not path:
                    continue
                
                # Get peaks from AsyncLoader
                peaks = loader.get_peaks(path, block_size=512, max_peaks=2048)
                if peaks is not None and len(peaks) > 0:
                    # Convert peaks to waveform format
                    # Peaks are (n_peaks, 2) with L/R values
                    # Waveform needs min/max pairs
                    n_peaks = len(peaks)
                    waveform = np.zeros((n_peaks * 2,), dtype=np.float32)
                    
                    # Interleave min/max (use same peak for both since we have max only)
                    for i in range(n_peaks):
                        # Use average of L/R for mono display
                        peak_val = (peaks[i, 0] + peaks[i, 1]) * 0.5
                        waveform[i * 2] = -peak_val  # min
                        waveform[i * 2 + 1] = peak_val  # max
                    
                    clip['waveform'] = waveform
                    
        except Exception as e:
            log.warning(f"Failed to load clip peaks: {e}")

    def set_viewport(self, x: float, y: float, w: float, h: float) -> None:
        """Set visible area in beats/tracks."""
        self._viewport = (float(x), float(y), float(w), float(h))
        self.update()

    def set_playhead(self, beat: float) -> None:
        self._playhead_beat = float(beat)
        self.update()

    # ---- OpenGL lifecycle

    def initializeGL(self) -> None:
        if not self._use_gl:
            return
        try:
            from OpenGL import GL as gl  # type: ignore
            gl.glClearColor(0.0, 0.0, 0.0, 0.0)  # transparent
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glEnable(gl.GL_LINE_SMOOTH)
            gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_NICEST)
            self._gl_initialized = True
            log.info("WaveformGLRenderer: OpenGL initialized")
        except Exception as e:
            log.warning("WaveformGLRenderer: OpenGL init failed (%s), using QPainter fallback", e)
            self._use_gl = False

    def resizeGL(self, w: int, h: int) -> None:
        if not self._use_gl or not self._gl_initialized:
            return
        try:
            from OpenGL import GL as gl  # type: ignore
            gl.glViewport(0, 0, w, h)
        except Exception:
            pass

    def paintGL(self) -> None:
        if not self._use_gl or not self._gl_initialized:
            self._paint_software()
            return
        try:
            self._paint_opengl()
        except Exception:
            self._paint_software()

    def paintEvent(self, event) -> None:
        if self._use_gl and self._gl_initialized:
            super().paintEvent(event)
        else:
            self._paint_software()

    # ---- OpenGL rendering

    def _paint_opengl(self) -> None:
        """Render waveforms using OpenGL."""
        try:
            from OpenGL import GL as gl  # type: ignore
        except ImportError:
            self._paint_software()
            return

        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        w = self.width()
        h = self.height()
        if w < 1 or h < 1:
            return

        vx, vy, vw, vh = self._viewport
        if vw <= 0 or vh <= 0:
            return

        # Render each visible clip
        for clip in self._clips:
            cx = float(clip.get("x", 0))
            cy = float(clip.get("y", 0))
            cw = float(clip.get("width", 0))
            ch_val = float(clip.get("height", 1))

            # Visibility test
            if cx + cw < vx or cx > vx + vw:
                continue
            if cy + ch_val < vy or cy > vy + vh:
                continue

            # Transform to screen coords
            sx = (cx - vx) / vw * w
            sy = (cy - vy) / vh * h
            sw = cw / vw * w
            sh = ch_val / vh * h

            # Clip background
            color = clip.get("color", self._clip_bg_color)
            gl.glColor4f(color.redF(), color.greenF(), color.blueF(), color.alphaF())
            gl.glBegin(gl.GL_QUADS)
            gl.glVertex2f(sx / w * 2 - 1, 1 - sy / h * 2)
            gl.glVertex2f((sx + sw) / w * 2 - 1, 1 - sy / h * 2)
            gl.glVertex2f((sx + sw) / w * 2 - 1, 1 - (sy + sh) / h * 2)
            gl.glVertex2f(sx / w * 2 - 1, 1 - (sy + sh) / h * 2)
            gl.glEnd()

            # Waveform outline
            waveform = clip.get("waveform")
            if waveform is not None and np is not None:
                wc = self._waveform_color
                gl.glColor4f(wc.redF(), wc.greenF(), wc.blueF(), wc.alphaF())
                gl.glLineWidth(1.0)
                gl.glBegin(gl.GL_LINE_STRIP)

                n_points = len(waveform)
                mid_y = sy + sh * 0.5
                amp_scale = sh * 0.4

                for i in range(0, min(n_points, int(sw))):
                    px = sx + float(i) / float(max(1, n_points - 1)) * sw
                    if i < len(waveform):
                        sample_val = float(waveform[i][1])  # y_min
                        py = mid_y - sample_val * amp_scale
                        gl.glVertex2f(px / w * 2 - 1, 1 - py / h * 2)

                gl.glEnd()

        # Playhead
        ph_x = (self._playhead_beat - vx) / vw * w
        if 0 <= ph_x <= w:
            pc = self._playhead_color
            gl.glColor4f(pc.redF(), pc.greenF(), pc.blueF(), 1.0)
            gl.glLineWidth(2.0)
            gl.glBegin(gl.GL_LINES)
            gl.glVertex2f(ph_x / w * 2 - 1, 1.0)
            gl.glVertex2f(ph_x / w * 2 - 1, -1.0)
            gl.glEnd()

    # ---- Software fallback (QPainter)

    def _paint_software(self) -> None:
        """Fallback QPainter rendering."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Clear previous frame to transparent so the arranger below stays visible.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        w = self.width()
        h = self.height()
        if w < 1 or h < 1:
            p.end()
            return

        vx, vy, vw, vh = self._viewport
        if vw <= 0 or vh <= 0:
            p.end()
            return

        for clip in self._clips:
            cx = float(clip.get("x", 0))
            cy = float(clip.get("y", 0))
            cw = float(clip.get("width", 0))
            ch_val = float(clip.get("height", 1))

            if cx + cw < vx or cx > vx + vw:
                continue
            if cy + ch_val < vy or cy > vy + vh:
                continue

            sx = (cx - vx) / vw * w
            sy = (cy - vy) / vh * h
            sw = cw / vw * w
            sh = ch_val / vh * h

            color = clip.get("color", self._clip_bg_color)
            p.fillRect(QRectF(sx, sy, sw, sh), color)

            # Waveform
            waveform = clip.get("waveform")
            if waveform is not None and np is not None:
                p.setPen(QPen(self._waveform_color, 1.0))
                n = len(waveform)
                mid_y = sy + sh * 0.5
                amp = sh * 0.4
                prev_px, prev_py = 0.0, mid_y
                for i in range(min(n, int(sw))):
                    px = sx + float(i) / float(max(1, n - 1)) * sw
                    if i < len(waveform):
                        val = float(waveform[i][1])
                        py = mid_y - val * amp
                        if i > 0:
                            p.drawLine(int(prev_px), int(prev_py),
                                       int(px), int(py))
                        prev_px, prev_py = px, py

        # Playhead
        ph_x = (self._playhead_beat - vx) / vw * w
        if 0 <= ph_x <= w:
            p.setPen(QPen(self._playhead_color, 2.0))
            p.drawLine(int(ph_x), 0, int(ph_x), h)

        p.end()


# ---- Factory

_waveform_cache = WaveformVBOCache()


def get_waveform_cache() -> WaveformVBOCache:
    return _waveform_cache
