"""Arranger canvas (v0.0.20.98)

Additions in v0.0.20.98:
- FIXED: Ruler zoom now works Bitwig/Ableton-style across the FULL ruler height
- Magnifier cursor appears when hovering anywhere in the ruler (not just top 14px)
- Loop handles are prioritized: clicking near start/end loop markers edits the loop
- Double-click anywhere in ruler resets zoom
- Resize cursor shown near loop handles for discoverability
- QScrollArea viewport mouse tracking enabled for reliable hover events

Additions in v0.0.20.79:
- Ghost-clip overlay during cross-project drag (semi-transparent preview at cursor)
- Visual feedback for external file drops (audio/midi ghost preview)

Additions in v0.0.20.15:
- Optional GPU-accelerated waveform overlay via WaveformGLRenderer (QOpenGLWidget)
- Automatic fallback to QPainter software rendering if OpenGL unavailable
- GL overlay syncs viewport + playhead with main canvas

Previous additions (v0.0.19.2.0+):
- Default mouse-wheel zoom (like many DAWs); Shift+Wheel = track-height zoom; Alt+Wheel passthrough
- Zoom +/- actions in context menu (and API hooks used by ArrangerView buttons)
- Clip handles on BOTH sides (right: resize/extend, left: trim/extend with content offset)
- Audio waveform preview (threaded peak-cache) + MIDI mini-preview
- Track volume influences waveform height (dB curve mapping) + shown as dB text
- Right-click menu includes Snap toggle + Grid division (1/1..1/64)
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
import copy
import json
from pathlib import Path

from PySide6.QtWidgets import QWidget, QMenu, QApplication, QToolTip
from PySide6.QtGui import QPainter, QPen, QBrush, QDrag, QColor, QKeyEvent, QPixmap, QPolygonF
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QMimeData, QRect


MIME_AUDIOEVENT_SLICE = "application/x-pydaw-audioevent-slice"
MIME_PLUGIN_DRAG_PREVIEW = "application/x-pydaw-plugin"

from pydaw.services.project_service import ProjectService
from pydaw.services.transport_service import TransportService
from pydaw.ui.arranger_keyboard import ArrangerKeyboardHandler
from pydaw.ui.cross_project_drag import MIME_CROSS_PROJECT, parse_cross_project_drop
from pydaw.ui.bounce_freeze_dialog import ask_bounce_freeze_options
from pydaw.ui.widgets.ruler_zoom_handle import paint_magnifier, make_magnifier_cursor
from pydaw.ui.smartdrop_rules import evaluate_plugin_drop_target



log = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover
    sf = None  # type: ignore


@dataclass
class _DragMove:
    clip_id: str
    dx_beats: float


@dataclass
class _DragMoveMulti:
    """Move multiple selected clips as a group (Arranger lasso + drag).

    We anchor snapping on the primary dragged clip and keep all other selected
    clips at their relative offsets.
    """

    anchor_clip_id: str
    dx_beats: float
    # clip_id -> (origin_start_beats, origin_track_idx)
    origins: dict
    anchor_track_idx: int


@dataclass
class _DragResizeRight:
    clip_id: str
    origin_len: float
    origin_x: float


@dataclass
class _DragResizeLeft:
    clip_id: str
    origin_start: float
    origin_len: float
    origin_x: float
    origin_offset_beats: float
    origin_offset_seconds: float


@dataclass
class _DragLoop:
    mode: str  # "new" | "start" | "end"
    origin_beat: float


@dataclass
class _DragNewClip:
    """Drag-create a new MIDI clip in empty arranger space."""

    track_id: str
    start_beat: float
    cur_beat: float


@dataclass
class _DragLasso:
    """Lasso selection - drag rectangle to select multiple clips."""
    
    start_x: float
    start_y: float
    current_x: float
    current_y: float
    initial_selection: set  # Clips selected before lasso started (for Shift+Lasso)


@dataclass
class _DragCopyPreview:
    """Ctrl+Drag copy preview (DAW style): original stays, ghost moves, copy on drop.

    Supports multi-clip copy when a lasso selection exists.
    """

    anchor_clip_id: str
    dx_beats: float
    # clip_id -> (origin_start_beats, origin_track_idx)
    origins: dict
    anchor_track_idx: int
    # live preview state
    cur_anchor_start: float
    cur_target_track_idx: int
    snap_enabled: bool = True



@dataclass
class _DragContentScale:
    """Alt+Drag clip edge = Bitwig-style Free Content Scaling.

    MIDI: notes scaled proportionally on release.
    Audio: clip.stretch updated proportionally on release.
    During drag only clip.length_beats changes visually (Lazy Update).
    """
    clip_id: str
    side: str  # "right" | "left"
    clip_kind: str  # "midi" | "audio"
    origin_start: float
    origin_len: float
    origin_x: float
    origin_offset_beats: float
    origin_offset_seconds: float
    original_notes: list  # MIDI: [(start_beats, length_beats)]; Audio: []
    origin_stretch: float = 1.0  # Audio: original clip.stretch
    free_mode: bool = False


@dataclass
class _DragFade:
    """Drag clip fade handles (Arranger-level, Cubase/Bitwig-style).

    We keep this UI-only + non-destructive: it only updates clip.fade_in_beats / fade_out_beats
    via ProjectService.update_audio_clip_params().
    """

    clip_id: str
    which: str  # "in" | "out"
    start_x: float


@dataclass
class _DragGainPan:
    """Drag clip gain/pan mini handles (Arranger-level).

    v0.0.20.176:
    - Drag 'G' handle vertically to change clip.gain (dB-mapped).
    - Hold SHIFT while dragging 'G' to adjust pan (alternative quick mode).
    - Drag 'P' handle horizontally to change clip.pan.

    Non-destructive: updates clip.gain / clip.pan via ProjectService.update_audio_clip_params().
    """

    clip_id: str
    which: str  # "gain" | "pan"
    start_x: float
    start_y: float
    origin_gain: float
    origin_pan: float


@dataclass
class _PeaksData:
    mtime_ns: int
    block_size: int
    samplerate: int
    peaks: "np.ndarray"  # max peaks per block (legacy compat)
    mins: "np.ndarray | None" = None  # min envelope per block
    maxs: "np.ndarray | None" = None  # max envelope per block

    @property
    def peaks_per_second(self) -> float:
        return float(self.samplerate) / float(max(1, self.block_size))


class ArrangerCanvas(QWidget):
    zoom_changed = Signal(float)  # pixels_per_beat
    clip_activated = Signal(str)
    clip_selected = Signal(str)
    request_rename_clip = Signal(str)
    request_duplicate_clip = Signal(str)
    request_delete_clip = Signal(str)
    request_import_audio = Signal(str, float)  # track_id, start_beats
    request_add_track = Signal(str)  # FIXED v0.0.19.7.19: track_kind ("audio", "instrument", "bus")
    request_smartdrop_new_instrument_track = Signal(dict)  # v0.0.20.478: empty-space instrument SmartDrop payload
    request_smartdrop_instrument_to_track = Signal(str, dict)  # v0.0.20.479: instrument SmartDrop onto existing instrument track
    request_smartdrop_fx_to_track = Signal(str, dict)  # v0.0.20.480: compatible FX SmartDrop onto existing tracks
    request_smartdrop_instrument_morph_guard = Signal(str, dict)  # v0.0.20.482: non-mutating preview/validate/apply guard for Instrument→Audio
    status_message = Signal(str, int)  # (message, timeout_ms) - v0.0.19.7.0

    loop_region_committed = Signal(bool, float, float)
    punch_region_committed = Signal(bool, float, float)  # v0.0.20.637: enabled, in_beat, out_beat

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        # v0.0.20.607: Canvas must never push dock/window wider
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.project = project
        self.transport: TransportService | None = None
        self._tab_service = None  # v0.0.20.78: set via set_tab_service()

        # v0.0.20.79: Ghost-clip overlay during cross-project / external drag
        self._drag_ghost_pos: QPointF | None = None  # cursor pos during drag-over
        self._drag_ghost_label: str = ""  # label for ghost-clip preview
        self._drag_ghost_kind: str = ""  # "cross-project" | "audio" | "midi" | ""
        self._plugin_drag_preview_pos: QPointF | None = None
        self._plugin_drag_preview_track_id: str = ""
        self._plugin_drag_preview_kind: str = ""
        self._plugin_drag_preview_label: str = ""
        self._plugin_drag_preview_new_track_y: float | None = None
        self._plugin_drag_preview_new_track_label: str = ""
        self._plugin_drag_preview_actionable: bool = False
        self._plugin_drag_hint_text: str = ""
        self._plugin_drag_hint_visible: bool = False

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Needed so hover can update the cursor for discoverable ruler controls.
        self.setMouseTracking(True)

        # v0.0.20.174: Hover clip id for small per-clip dropdown button (Cubase-style discoverability)
        self._hover_clip_id: str = ""

        self.pixels_per_beat = 80.0
        self.track_height = 70
        self.ruler_height = 28

        # Ruler zoom handle (magnifier icon) — Ableton/Bitwig-style discoverable zoom control.
        # Drag the magnifier up/down to zoom time horizontally. Double-click resets.
        self._default_pixels_per_beat = float(self.pixels_per_beat)
        # Slightly larger hitbox so it's easy to hit (and visible on HiDPI).
        self._zoom_handle_rect = QRect(8, 1, 14, 14)  # in widget coords (ruler zoom band)
        self._zoom_drag_active = False
        self._zoom_drag_origin_y = 0.0
        self._zoom_drag_origin_ppb = float(self.pixels_per_beat)

        # Lazily created custom cursor (magnifier) for ruler zoom handle.
        self._magnifier_cursor = None
        self._hover_zoom_handle = False
        # v0.0.20.98: Track override cursor state to avoid stacking
        self._cursor_override_active: str = ""  # "" | "magnifier" | "loop_handle"

        # Ruler layout (Bitwig-style, top-to-bottom):
        #   [0 .. _ruler_zoom_band_h)   = Zoom zone (magnifier cursor, drag = zoom)
        #   [_ruler_zoom_band_h .. ruler_height] = Loop/playhead zone (drag = loop)
        # This gives a thin zoom strip at the very top edge and a larger loop area below.
        self._ruler_zoom_band_h = 10  # px — thin zoom strip at very top (Bitwig-style)
        self._zoom_handle_visible = False
        self._zoom_anchor_beat = 0.0
        self._zoom_anchor_view_x = 0.0

        self.playhead_beat = 0.0
        self._follow_playhead = True  # v0.0.20.438: Bitwig-style smooth scroll
        self.loop_enabled = False
        self.loop_start = 0.0
        self.loop_end = 16.0

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self.punch_enabled = False
        self.punch_in = 4.0
        self.punch_out = 16.0
        self._drag_punch_handle: str = ""  # "in" | "out" | ""

        # v0.0.20.639: TakeService reference for take-lane context menu
        self._take_service = None

        self.snap_beats = 0.25

        self.selected_clip_ids: set[str] = set()
        self.selected_clip_id: str = ""

        # Clip pixmap cache (Grafik-Turbo: pre-rendered clip visuals)
        self._clip_pixmap_cache: dict[str, QPixmap] = {}

        # Tool state (Pro-DAW-Style)
        self._active_tool: str = "select"  # select, knife, draw, erase

        # Fade handle drag (Arranger-level). Kept non-destructive.
        self._drag_fade: _DragFade | None = None
        self._drag_gainpan: _DragGainPan | None = None

        self._drag_move: _DragMove | None = None
        self._drag_move_multi: _DragMoveMulti | None = None
        self._drag_resize_r: _DragResizeRight | None = None
        self._drag_resize_l: _DragResizeLeft | None = None
        self._drag_content_scale: _DragContentScale | None = None
        self._drag_loop: _DragLoop | None = None
        self._drag_new_clip: _DragNewClip | None = None
        self._drag_lasso: _DragLasso | None = None

        self._dnd_drag_start: QPointF | None = None
        self._dnd_clip_id: str = ""

        # Ctrl+Drag horizontal copy mode (v0.0.19.7.0 - FIXED!)
        self._drag_is_copy: bool = False  # True if Ctrl was held during press
        self._drag_copy_source_clip_id: str = ""  # Original clip to copy from
        self._drag_copy_original_start: float = 0.0  # Original position before drag
        self._drag_copy_original_track: str = ""  # Original track before drag

        # v0.0.20.143: DAW-style Ctrl+Drag copy preview (supports multi-clip lasso)
        # Original stays in place; ghost preview follows mouse; copy is created on drop.
        self._drag_copy_preview: _DragCopyPreview | None = None

        # v0.0.20.143: Playhead seeking/dragging (red line)
        self._drag_playhead_active: bool = False
        self._drag_playhead_snap: bool = True
        self._last_playhead_px: int = 0

        # Auto-loop extension
        self._pending_auto_loop_end: float | None = None
        # v0.0.20.98: Suppress context menu after right-click loop drawing
        self._suppress_next_context_menu: bool = False

        # Waveform cache
        self._peaks_cache: dict[str, _PeaksData] = {}
        self._peaks_pending: set[str] = set()

        # Keyboard Handler for standard DAW shortcuts
        # Inject playhead + snap grid so Ctrl+V can paste at Bar 5/6 etc.
        self.keyboard_handler = ArrangerKeyboardHandler(
            self.project,
            get_playhead_beat=lambda: float(getattr(self, "playhead_beat", 0.0) or 0.0),
            get_snap_beats=lambda: float(getattr(self, "snap_beats", 0.25) or 0.25),
        )
        self.keyboard_handler.status_message.connect(self._on_keyboard_status)
        self.keyboard_handler.request_update.connect(self.update)

        self.project.project_updated.connect(self._on_project_updated)
        self._update_minimum_size()

        # v0.0.20.18: GPU waveform overlay is OFF by default.
        #
        # Why: QOpenGLWidget is composited above its parent. On some drivers/compositors
        # it can cover the arranger grid if it paints an opaque background.
        #
        # The preferred way is via View → "GPU Waveforms" (persisted). For debugging
        # you can still force enable via env:
        #   PYDAW_GPU_WAVEFORMS=1 python3 main.py
        self._gl_overlay = None
        self._gl_enabled = False
        self._gpu_force_env = str(os.environ.get("PYDAW_GPU_WAVEFORMS", "0")).strip().lower() in ("1", "true", "yes", "on")
        if self._gpu_force_env:
            self.set_gpu_waveforms_enabled(True)

    def _get_magnifier_cursor(self):
        """Return (and cache) a magnifier cursor for ruler zoom controls.
        
        v0.0.20.98: First tries custom pixmap cursor. If that fails or looks
        invisible (common on Wayland/GNOME), falls back to CrossCursor.
        """
        try:
            if self._magnifier_cursor is None:
                # Try custom pixmap first
                col = self.palette().text().color()
                custom = make_magnifier_cursor(col)
                # Verify it's not just a fallback arrow
                if custom.shape() == Qt.CursorShape.ArrowCursor:
                    # Fallback failed, use standard cross cursor
                    self._magnifier_cursor = Qt.CursorShape.CrossCursor
                else:
                    self._magnifier_cursor = custom
            return self._magnifier_cursor
        except Exception:
            return Qt.CursorShape.CrossCursor

    def _set_override_cursor(self, kind: str) -> None:
        """Set application-level override cursor (works through QScrollArea + Wayland).
        
        Uses QApplication.setOverrideCursor which bypasses all widget-level cursor
        issues (QScrollArea eating setCursor, Wayland ignoring pixmap cursors, etc.).
        """
        try:
            if self._cursor_override_active == kind:
                return  # Already set, avoid stacking
            # Restore previous override if any
            if self._cursor_override_active:
                QApplication.restoreOverrideCursor()
                self._cursor_override_active = ""
            
            if kind == "magnifier":
                # Try XCursor "zoom-in" (real magnifier icon on most Linux desktops)
                cursor = self._get_zoom_cursor()
                QApplication.setOverrideCursor(cursor)
            elif kind == "loop_handle":
                QApplication.setOverrideCursor(Qt.CursorShape.SizeHorCursor)
            elif kind == "fade":
                QApplication.setOverrideCursor(Qt.CursorShape.SizeHorCursor)
            elif kind == "gain":
                QApplication.setOverrideCursor(Qt.CursorShape.SizeVerCursor)
            elif kind == "pan":
                QApplication.setOverrideCursor(Qt.CursorShape.SizeHorCursor)
            elif kind == "copy":
                QApplication.setOverrideCursor(Qt.CursorShape.DragCopyCursor)
            elif kind == "content_scale":
                QApplication.setOverrideCursor(Qt.CursorShape.SplitHCursor)
            else:
                return
            self._cursor_override_active = kind
        except Exception:
            log.debug("_set_override_cursor failed for %s", kind, exc_info=True)

    def _get_zoom_cursor(self) -> QCursor:
        """Get a zoom/magnifier cursor. Tries multiple strategies:
        1. XCursor 'zoom-in' (real magnifier on GNOME/KDE)
        2. Custom painted magnifier pixmap (high contrast)
        3. CrossCursor fallback
        """
        if not hasattr(self, '_cached_zoom_cursor'):
            self._cached_zoom_cursor = None
            # Strategy 1: XCursor name (works on X11 and most Wayland compositors)
            try:
                from PySide6.QtGui import QCursor
                test = QCursor(Qt.CursorShape.CrossCursor)
                # QCursor doesn't have a string-name constructor in PyQt6,
                # but we can try via the xcb cursor name through QPixmap workaround.
                # Actually, the best approach for Linux: build a visible magnifier pixmap.
                pass
            except Exception:
                pass
            
            # Strategy 2: Compact magnifier pixmap (24x24, crisp)
            try:
                size = 24
                pm = QPixmap(size, size)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                
                # Glass circle
                glass_cx, glass_cy, glass_r = 9, 9, 6
                
                # Black outline (shadow)
                pen_bg = QPen(QColor(0, 0, 0, 220))
                pen_bg.setWidthF(2.5)
                p.setPen(pen_bg)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(glass_cx - glass_r, glass_cy - glass_r, 
                              glass_r * 2, glass_r * 2)
                hx1 = glass_cx + int(glass_r * 0.7)
                hy1 = glass_cy + int(glass_r * 0.7)
                p.drawLine(hx1, hy1, size - 3, size - 3)
                
                # White foreground
                pen_fg = QPen(QColor(255, 255, 255, 255))
                pen_fg.setWidthF(1.5)
                pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen_fg)
                p.drawEllipse(glass_cx - glass_r, glass_cy - glass_r,
                              glass_r * 2, glass_r * 2)
                p.drawLine(hx1, hy1, size - 3, size - 3)
                
                # Small plus
                plus = 3
                p.drawLine(glass_cx - plus, glass_cy, glass_cx + plus, glass_cy)
                p.drawLine(glass_cx, glass_cy - plus, glass_cx, glass_cy + plus)
                
                p.end()
                self._cached_zoom_cursor = QCursor(pm, glass_cx, glass_cy)
            except Exception:
                pass
            
            # Strategy 3: Fallback
            if self._cached_zoom_cursor is None:
                self._cached_zoom_cursor = QCursor(Qt.CursorShape.CrossCursor)
        
        return self._cached_zoom_cursor

    def _clear_override_cursor(self) -> None:
        """Remove the application-level override cursor."""
        try:
            if self._cursor_override_active:
                QApplication.restoreOverrideCursor()
                self._cursor_override_active = ""
        except Exception:
            pass

    
    def _find_hscrollbar(self):
        """Find a parent QScrollArea horizontal scrollbar (if any)."""
        try:
            w = self.parentWidget()
            while w is not None:
                if hasattr(w, 'horizontalScrollBar'):
                    try:
                        return w.horizontalScrollBar()
                    except Exception:
                        pass
                w = w.parentWidget()
        except Exception:
            pass
        return None

    def _update_zoom_handle_rect(self, x: float) -> None:
        """Move the magnifier hitbox to follow the mouse X inside the ruler."""
        try:
            size = int(self._zoom_handle_rect.width())
        except Exception:
            size = 20
        try:
            half = size // 2
            nx = int(x) - half
            nx = max(4, min(nx, max(4, self.width() - size - 4)))
            ny = 1
            new_rect = QRect(nx, ny, size, size)
            if new_rect != self._zoom_handle_rect:
                self._zoom_handle_rect = new_rect
        except Exception:
            pass

    def _apply_ppb_anchored(self, new_ppb: float) -> None:
        """Apply pixels-per-beat change while keeping the anchor beat under the cursor stable."""
        try:
            new_ppb = float(new_ppb)
        except Exception:
            return
        new_ppb = max(20.0, min(320.0, new_ppb))

        self.pixels_per_beat = float(new_ppb)
        self._update_minimum_size()

        try:
            beat = float(getattr(self, '_zoom_anchor_beat', 0.0) or 0.0)
            view_x = float(getattr(self, '_zoom_anchor_view_x', 0.0) or 0.0)
            bar = self._find_hscrollbar()
            if bar is not None:
                new_content_x = beat * float(new_ppb)
                new_scroll = int(max(0.0, new_content_x - view_x))
                bar.setValue(new_scroll)
        except Exception:
            pass

    def set_gpu_waveforms_enabled(self, enabled: bool) -> None:
        """Enable/disable the optional GPU waveform overlay.

        This is purely a visual overlay (waveforms) and must never affect editing.
        """
        enabled = bool(enabled)
        if enabled and self._gl_overlay is not None:
            self._gl_enabled = True
            try:
                self._gl_overlay.show()
                self._gl_overlay.raise_()
            except Exception:
                pass
            self._sync_gl_overlay()
            return

        if (not enabled) and self._gl_overlay is None:
            self._gl_enabled = False
            return

        if not enabled:
            # Disable and destroy overlay widget to avoid any compositor surprises.
            try:
                self._gl_overlay.hide()
            except Exception:
                pass
            try:
                self._gl_overlay.setParent(None)
            except Exception:
                pass
            try:
                self._gl_overlay.deleteLater()
            except Exception:
                pass
            self._gl_overlay = None
            self._gl_enabled = False
            self.update()
            return

        # Enable (create overlay)
        try:
            from pydaw.ui.gpu_waveform_renderer import WaveformGLRenderer, _GL_AVAILABLE
            if not bool(_GL_AVAILABLE):
                self._gl_overlay = None
                self._gl_enabled = False
                return
            self._gl_overlay = WaveformGLRenderer(parent=self)
            self._gl_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            try:
                self._gl_overlay.setAutoFillBackground(False)
            except Exception:
                pass
            self._gl_overlay.raise_()
            self._gl_enabled = True
            self._sync_gl_overlay()
        except Exception:
            self._gl_overlay = None
            self._gl_enabled = False

    # --- external setters

    def set_transport(self, transport: TransportService | None) -> None:
        self.transport = transport

    def set_tab_service(self, tab_service) -> None:
        """Set ProjectTabService for cross-project drag&drop (v0.0.20.78)."""
        self._tab_service = tab_service

    def set_playhead(self, beat: float) -> None:
        # v0.0.20.143: Avoid full-canvas repaints on every playhead tick.
        # Only invalidate the old/new playhead stripe area.
        try:
            old_x = int(getattr(self, '_last_playhead_px', int(self.playhead_beat * float(self.pixels_per_beat))))
        except Exception:
            old_x = int(self.playhead_beat * float(self.pixels_per_beat))

        self.playhead_beat = max(0.0, float(beat))
        new_x = int(self.playhead_beat * float(self.pixels_per_beat))
        self._last_playhead_px = int(new_x)
        # v0.0.20.14: sync GL overlay
        if self._gl_overlay is not None:
            try:
                self._gl_overlay.set_playhead(self.playhead_beat * float(self.pixels_per_beat))
            except Exception:
                pass

        # v0.0.20.438: Bitwig-style smooth follow — scroll when playhead
        # reaches 80% of visible width, reposition to 20% from left.
        _did_follow_scroll = False
        if getattr(self, '_follow_playhead', False):
            try:
                bar = self._find_hscrollbar()
                if bar is not None:
                    scroll_val = bar.value()
                    page_size = bar.pageStep()
                    if page_size > 0:
                        view_left = scroll_val
                        view_right = scroll_val + page_size
                        threshold_right = view_left + int(page_size * 0.80)
                        if new_x > threshold_right or new_x < view_left:
                            # Scroll so playhead is at 20% from left
                            target = int(new_x - page_size * 0.20)
                            bar.setValue(max(0, target))
                            _did_follow_scroll = True
            except Exception:
                pass

        # Repaint: nach Follow-Scroll volles Update (Grid muss neu gezeichnet werden),
        # sonst nur schmaler Playhead-Streifen (Performance)
        if _did_follow_scroll:
            self.update()
        else:
            try:
                pad = 8
                x1 = max(0, min(int(old_x), int(new_x)) - pad)
                x2 = min(self.width(), max(int(old_x), int(new_x)) + pad)
                self.update(QRect(x1, 0, max(1, x2 - x1), self.height()))
            except Exception:
                self.update()

    def set_loop_region(self, enabled: bool, start: float, end: float) -> None:
        self.loop_enabled = bool(enabled)
        self.loop_start = max(0.0, float(start))
        self.loop_end = max(self.loop_start + self.snap_beats, float(end))
        self.update()

    def set_punch_region(self, enabled: bool, in_beat: float, out_beat: float) -> None:
        """v0.0.20.637: Set punch in/out region for visual display."""
        self.punch_enabled = bool(enabled)
        self.punch_in = max(0.0, float(in_beat))
        self.punch_out = max(self.punch_in + self.snap_beats, float(out_beat))
        self.update()

    # --- playhead interactions (seek/drag)

    def _near_playhead(self, pos: QPointF, threshold_px: int = 5) -> bool:
        try:
            x = float(pos.x())
            phx = float(self.playhead_beat) * float(self.pixels_per_beat)
            return abs(x - phx) <= float(threshold_px)
        except Exception:
            return False

    def _seek_playhead(self, beat: float, *, snap: bool = True) -> None:
        """Seek playhead in a GUI-safe way.

        If a TransportService is bound, we update the transport and emit its signal,
        so all editors stay in sync.
        """
        try:
            b = float(beat)
        except Exception:
            b = 0.0
        if snap:
            try:
                b = float(self._snap(b))
            except Exception:
                b = max(0.0, float(b))
        else:
            b = max(0.0, float(b))

        if self.transport is not None:
            try:
                self.transport.current_beat = float(b)
            except Exception:
                pass
            try:
                self.transport.playhead_changed.emit(float(b))
            except Exception:
                # Fallback: local update
                self.set_playhead(float(b))
        else:
            self.set_playhead(float(b))

    def set_snap_division(self, div: str) -> None:
        """Set snap/grid division and update snap_beats."""
        # Beat unit is quarter = 1.0
        div = str(div or "1/16")
        mapping = {
            "1/1": 4.0,
            "1/2": 2.0,
            "1/4": 1.0,
            "1/8": 0.5,
            "1/16": 0.25,
            "1/32": 0.125,
            "1/64": 0.0625,
        }
        self.snap_beats = float(mapping.get(div, 0.25))

    # --- zoom helpers (used by ArrangerView buttons + context menu)

    def _zoom_by_factor(self, factor: float) -> None:
        self.pixels_per_beat = max(20.0, min(320.0, float(self.pixels_per_beat) * float(factor)))
        self._update_minimum_size()
        self._sync_gl_overlay()
        self.update()
        self.zoom_changed.emit(float(self.pixels_per_beat))

    def zoom_in(self) -> None:
        self._zoom_by_factor(1.1)

    def zoom_out(self) -> None:
        self._zoom_by_factor(0.9)

    def set_tool(self, tool: str) -> None:
        """Set active tool (select, knife, draw, erase, time_select)."""
        if tool in ("select", "knife", "draw", "erase", "time_select"):
            self._active_tool = str(tool)
            self.update()
    
    def get_tool(self) -> str:
        """Get current active tool."""
        return self._active_tool

    # --- model helpers

    def _beats_per_bar(self) -> float:
        """Return beats per bar based on Project.time_signature (num/den)."""
        ts = getattr(self.project.ctx.project, "time_signature", "4/4") or "4/4"
        try:
            num_s, den_s = str(ts).split("/")
            num = float(num_s)
            den = float(den_s)
            return float(num) * (4.0 / max(1.0, den))
        except Exception:
            return 4.0

    def _collapsed_group_ids(self) -> set[str]:
        try:
            return {str(g) for g in (getattr(self.project.ctx.project, "arranger_collapsed_group_ids", []) or []) if str(g)}
        except Exception:
            return set()

    def _lane_entries(self):
        tracks = list(getattr(self.project.ctx.project, "tracks", []) or [])
        collapsed = self._collapsed_group_ids()
        rendered_groups: set[str] = set()
        entries = []
        for t in tracks:
            kind = str(getattr(t, "kind", "") or "")
            # v0.0.20.357: Skip group-bus tracks — they don't have clips or their own lane
            if kind == "group":
                continue
            gid = str(getattr(t, "track_group_id", "") or "")
            if gid and kind != "master":
                members = [
                    mt for mt in tracks
                    if str(getattr(mt, "track_group_id", "") or "") == gid
                    and str(getattr(mt, "kind", "") or "") not in ("master", "group")
                ]
                if len(members) >= 2:
                    if gid in rendered_groups:
                        continue
                    rendered_groups.add(gid)
                    if gid in collapsed:
                        entries.append({
                            "kind": "group",
                            "group_id": gid,
                            "group_name": str(getattr(members[0], "track_group_name", "") or "Gruppe"),
                            "track": members[0],
                            "members": members,
                        })
                    else:
                        entries.append({
                            "kind": "group_header",
                            "group_id": gid,
                            "group_name": str(getattr(members[0], "track_group_name", "") or "Gruppe"),
                            "track": None,
                            "members": [],
                        })
                        for mt in members:
                            entries.append({"kind": "track", "track": mt, "members": [mt], "group_id": gid, "indented": True})
                    continue
            entries.append({"kind": "track", "track": t, "members": [t], "indented": False})
        return entries

    def _tracks(self):
        return [entry.get("track") for entry in self._lane_entries() if entry.get("track") is not None]

    def _lane_index_for_track_id(self, track_id: str) -> int:
        tid = str(track_id or "")
        for idx, entry in enumerate(self._lane_entries()):
            try:
                members = list(entry.get("members") or [])
            except Exception:
                members = []
            if any(str(getattr(t, "id", "") or "") == tid for t in members):
                return int(idx)
        return -1

    def _is_same_collapsed_group(self, track_id_a: str, track_id_b: str) -> bool:
        """Return True if both track IDs belong to the same currently-collapsed group.

        This prevents clip track reassignment when dragging inside a collapsed group
        (v0.0.20.355 bugfix: clips were silently moved to members[0] on any drag).
        """
        if not track_id_a or not track_id_b:
            return False
        tid_a = str(track_id_a)
        tid_b = str(track_id_b)
        if tid_a == tid_b:
            return True  # same track, no move needed anyway
        collapsed = self._collapsed_group_ids()
        if not collapsed:
            return False
        tracks = list(getattr(self.project.ctx.project, "tracks", []) or [])
        # Find group_id for track_id_a
        gid_a = ""
        for t in tracks:
            if str(getattr(t, "id", "") or "") == tid_a:
                gid_a = str(getattr(t, "track_group_id", "") or "")
                break
        if not gid_a or gid_a not in collapsed:
            return False
        # Check if track_id_b is in the same group
        for t in tracks:
            if str(getattr(t, "id", "") or "") == tid_b:
                return str(getattr(t, "track_group_id", "") or "") == gid_a
        return False

    def _arranger_clips(self):
        """Return clips that belong to the Arranger timeline (exclude Clip-Launcher-only clips)."""
        return [c for c in self.project.ctx.project.clips if not getattr(c, 'launcher_only', False)]

    def _track_at_y(self, y: float):
        entries = self._lane_entries()
        if y <= self.ruler_height:
            return None
        idx = int((y - self.ruler_height) // self.track_height)
        if idx < 0 or idx >= len(entries):
            return None
        try:
            entry = entries[idx]
            if str(entry.get("kind", "")) == "group_header":
                return None
            return entry.get("track")
        except Exception:
            return None

    def _parse_plugin_drag_info(self, mime_data) -> tuple[str, str] | None:  # noqa: ANN001
        try:
            payload = self._parse_plugin_drag_payload(mime_data)
            if not isinstance(payload, dict):
                return None
            params = payload.get("params") or {}
            device_kind = str(payload.get("device_kind") or payload.get("kind") or "").strip().lower()
            if device_kind not in ("instrument", "audio_fx", "note_fx"):
                is_inst = bool(payload.get("is_instrument"))
                if isinstance(params, dict):
                    is_inst = is_inst or bool(params.get("__ext_is_instrument"))
                device_kind = "instrument" if is_inst else "audio_fx"
            name = str(payload.get("name") or "").strip() or "Device"
            return device_kind, name
        except Exception:
            return None

    def _parse_plugin_drag_payload(self, mime_data) -> dict | None:  # noqa: ANN001
        try:
            if mime_data is None or not mime_data.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                return None
            raw = bytes(mime_data.data(MIME_PLUGIN_DRAG_PREVIEW)).decode("utf-8", "ignore")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                return None
            return payload
        except Exception:
            return None

    def _plugin_drop_target_info(self, track, device_kind: str) -> dict:  # noqa: ANN001
        try:
            project_obj = getattr(getattr(self.project, "ctx", None), "project", None)
            return dict(evaluate_plugin_drop_target(project_obj, track, device_kind) or {})
        except Exception:
            return {}

    def _plugin_drop_target_state(self, track, device_kind: str) -> tuple[str, bool]:  # noqa: ANN001
        try:
            info = self._plugin_drop_target_info(track, device_kind)
            return str(info.get("label") or ""), bool(info.get("actionable"))
        except Exception:
            return "", False

    def _is_below_last_lane_y(self, y: float) -> bool:
        try:
            lane_entries = self._lane_entries()
            last_lane_bottom = float(self.ruler_height + len(lane_entries) * self.track_height)
            return float(y) >= max(float(self.ruler_height), last_lane_bottom - 2.0)
        except Exception:
            return False

    def _plugin_drag_hint_message(self) -> str:
        base = ""
        if self._plugin_drag_preview_new_track_label:
            base = self._plugin_drag_preview_new_track_label
        elif self._plugin_drag_preview_label:
            base = self._plugin_drag_preview_label
        base = str(base or "").strip()
        if not base:
            return ""
        if bool(getattr(self, "_plugin_drag_preview_actionable", False)):
            return base
        return f"{base} · Nur Preview — SmartDrop folgt später"

    def _plugin_drag_global_pos(self, pos=None):  # noqa: ANN001
        try:
            if pos is None:
                pos = self._plugin_drag_preview_pos
            if pos is None:
                return None
            if hasattr(pos, "toPoint"):
                qpt = pos.toPoint()
            else:
                qpt = QPoint(int(float(pos.x())), int(float(pos.y())))
            return self.mapToGlobal(qpt + QPoint(18, 24))
        except Exception:
            return None

    def _sync_plugin_drag_hint(self, pos=None) -> None:  # noqa: ANN001
        text = self._plugin_drag_hint_message()
        try:
            self.setToolTip(text)
        except Exception:
            pass
        if not text:
            try:
                if self._plugin_drag_hint_text or self._plugin_drag_hint_visible:
                    self.status_message.emit("", 1)
            except Exception:
                pass
            try:
                QToolTip.hideText()
            except Exception:
                pass
            self._plugin_drag_hint_text = ""
            self._plugin_drag_hint_visible = False
            return
        try:
            if text != self._plugin_drag_hint_text:
                self.status_message.emit(text, 1800)
        except Exception:
            pass
        try:
            global_pos = self._plugin_drag_global_pos(pos)
            if global_pos is not None and (text != self._plugin_drag_hint_text or not self._plugin_drag_hint_visible):
                QToolTip.showText(global_pos, text, self)
                self._plugin_drag_hint_visible = True
        except Exception:
            pass
        self._plugin_drag_hint_text = text

    def _clear_plugin_drag_preview(self) -> None:
        self._plugin_drag_preview_pos = None
        self._plugin_drag_preview_track_id = ""
        self._plugin_drag_preview_kind = ""
        self._plugin_drag_preview_label = ""
        self._plugin_drag_preview_new_track_y = None
        self._plugin_drag_preview_new_track_label = ""
        self._plugin_drag_preview_actionable = False
        self._sync_plugin_drag_hint()

    def _update_plugin_drag_preview(self, pos, mime_data) -> None:  # noqa: ANN001
        info = self._parse_plugin_drag_info(mime_data)
        if info is None:
            self._clear_plugin_drag_preview()
            self.update()
            return
        device_kind, plugin_name = info
        try:
            pt = pos.toPointF() if hasattr(pos, "toPointF") else QPointF(pos)
        except Exception:
            try:
                pt = QPointF(float(pos.x()), float(pos.y()))
            except Exception:
                self._clear_plugin_drag_preview()
                self.update()
                return

        tracks = self._tracks()
        lane_entries = self._lane_entries()
        track = self._track_at_y(float(pt.y()))
        if track is not None:
            label, actionable = self._plugin_drop_target_state(track, device_kind)
            self._plugin_drag_preview_pos = QPointF(pt)
            self._plugin_drag_preview_track_id = str(getattr(track, "id", "") or "")
            self._plugin_drag_preview_kind = device_kind
            self._plugin_drag_preview_label = label
            self._plugin_drag_preview_new_track_y = None
            self._plugin_drag_preview_new_track_label = ""
            self._plugin_drag_preview_actionable = actionable
            self.update()
            return

        # v0.0.20.479: Instrument-Drop auf echte Ziele bleibt weiterhin klein:
        # - bestehende Instrument-Spur -> echter SmartDrop
        # - unterhalb der letzten Spur -> neue Instrument-Spur
        last_lane_bottom = float(self.ruler_height + len(lane_entries) * self.track_height)
        is_below_last_lane = self._is_below_last_lane_y(float(pt.y()))
        if device_kind == "instrument" and is_below_last_lane:
            line_y = max(float(self.ruler_height + 4), last_lane_bottom + 2.0)
            self._plugin_drag_preview_pos = QPointF(pt)
            self._plugin_drag_preview_track_id = ""
            self._plugin_drag_preview_kind = device_kind
            self._plugin_drag_preview_label = ""
            self._plugin_drag_preview_new_track_y = line_y
            self._plugin_drag_preview_new_track_label = f"Neue Instrument-Spur: {plugin_name}"
            self._plugin_drag_preview_actionable = True
            self.update()
            return

        self._clear_plugin_drag_preview()
        self.update()

    def _clip_rects(self):
        rects = []
        for clip in self._arranger_clips():
            track_idx = self._lane_index_for_track_id(getattr(clip, "track_id", ""))
            if track_idx < 0:
                continue
            x = float(clip.start_beats) * self.pixels_per_beat
            w = max(10.0, float(clip.length_beats) * self.pixels_per_beat)
            y = self.ruler_height + track_idx * self.track_height + 8
            h = self.track_height - 16
            rects.append((clip.id, QRectF(x, y, w, h), clip))
        return rects

    def _clip_at_pos(self, pos: QPointF) -> str:
        for cid, r, _clip in self._clip_rects():
            if r.contains(pos):
                return cid
        return ""

    def _clip_rect(self, clip_id: str):
        for cid, r, clip in self._clip_rects():
            if cid == clip_id:
                return r, clip
        return None, None

    def _hit_resize_handle_right(self, rect: QRectF, pos: QPointF) -> bool:
        handle = QRectF(rect.right() - 6, rect.top(), 12, rect.height())
        return handle.contains(pos)

    def _hit_resize_handle_left(self, rect: QRectF, pos: QPointF) -> bool:
        handle = QRectF(rect.left() - 6, rect.top(), 12, rect.height())
        return handle.contains(pos)

    # --- Fade handle hit-testing (Arranger-level, Cubase/Bitwig-style)
    def _hit_fade_handle_in(self, rect: QRectF, pos: QPointF) -> bool:
        # top-left corner zone (avoid interfering with normal resize/trim by requiring top area)
        handle = QRectF(rect.left() + 8.0, rect.top() + 3.0, 13.0, 13.0)
        return handle.contains(pos)
    
    def _hit_fade_handle_out(self, rect: QRectF, pos: QPointF) -> bool:
        # top-right corner zone, shifted left so it doesn't overlap the ▾ dropdown button
        handle = QRectF(rect.right() - 32.0, rect.top() + 3.0, 13.0, 13.0)
        return handle.contains(pos)
    
    def _fade_dropdown_rect(self, rect: QRectF) -> QRectF:
        return QRectF(rect.right() - 16.0, rect.top() + 3.0, 13.0, 13.0)

    # --- Gain/Pan mini handle hit-testing (Arranger-level, Cubase-style)
    def _gain_handle_rect(self, rect: QRectF) -> QRectF:
        # top-center (slightly left), so it doesn't collide with fade handles or ▾
        x = float(rect.center().x()) - 14.0
        return QRectF(x, rect.top() + 3.0, 13.0, 13.0)

    def _pan_handle_rect(self, rect: QRectF) -> QRectF:
        # top-center (slightly right)
        x = float(rect.center().x()) + 1.0
        return QRectF(x, rect.top() + 3.0, 13.0, 13.0)

    def _hit_gain_handle(self, rect: QRectF, pos: QPointF) -> bool:
        if rect.width() < 90 or rect.height() < 18:
            return False
        return self._gain_handle_rect(rect).contains(pos)

    def _hit_pan_handle(self, rect: QRectF, pos: QPointF) -> bool:
        if rect.width() < 90 or rect.height() < 18:
            return False
        # Avoid overlap with ▾ dropdown rect (defensive)
        try:
            if self._fade_dropdown_rect(rect).contains(pos):
                return False
        except Exception:
            pass
        return self._pan_handle_rect(rect).contains(pos)
    
    
    
    def _hit_loop_handle(self, pos: QPointF) -> str:
        if pos.y() > self.ruler_height:
            return ""
        x = pos.x()
        x1 = self.loop_start * self.pixels_per_beat
        x2 = self.loop_end * self.pixels_per_beat
        if abs(x - x1) <= 6:
            return "start"
        if abs(x - x2) <= 6:
            return "end"
        return ""

    def _hit_punch_handle(self, pos: QPointF) -> str:
        """v0.0.20.637: Hit-test for punch in/out handles in the ruler."""
        if not self.punch_enabled:
            return ""
        if pos.y() > self.ruler_height:
            return ""
        x = pos.x()
        x_in = self.punch_in * self.pixels_per_beat
        x_out = self.punch_out * self.pixels_per_beat
        if abs(x - x_in) <= 6:
            return "in"
        if abs(x - x_out) <= 6:
            return "out"
        return ""

    def _hit_take_lane_clip(self, pos: QPointF):
        """v0.0.20.640: Hit-test for inactive take clips in take-lane area.

        Returns (track_id, clip) or (None, None) if no hit.
        """
        take_svc = getattr(self, '_take_service', None)
        if not take_svc:
            return None, None
        try:
            ppb = float(self.pixels_per_beat or 1.0)
            entries = self._lane_entries()
            for lane_idx, entry in enumerate(entries):
                trk = entry.get("track")
                if not trk or not getattr(trk, 'take_lanes_visible', False):
                    continue
                tid = str(getattr(trk, 'id', ''))
                groups = take_svc.get_take_groups_for_track(tid)
                if not groups:
                    continue
                take_h = max(20, int(getattr(trk, 'take_lanes_height', 40)))
                base_y = self.ruler_height + lane_idx * self.track_height + self.track_height
                sub_idx = 0
                for gid, takes in groups.items():
                    for tc in takes:
                        if getattr(tc, 'is_comp_active', True):
                            continue
                        tx = float(getattr(tc, 'start_beats', 0)) * ppb
                        tw = max(10.0, float(getattr(tc, 'length_beats', 4)) * ppb)
                        ty = base_y + sub_idx * take_h
                        tr = QRectF(tx, ty, tw, take_h - 2)
                        if tr.contains(pos):
                            return tid, tc
                        sub_idx += 1
        except Exception:
            pass
        return None, None

    def _get_lasso_rect(self) -> QRectF:
        """Get lasso selection rectangle."""
        if self._drag_lasso is None:
            return QRectF()
        
        x1 = min(self._drag_lasso.start_x, self._drag_lasso.current_x)
        x2 = max(self._drag_lasso.start_x, self._drag_lasso.current_x)
        y1 = min(self._drag_lasso.start_y, self._drag_lasso.current_y)
        y2 = max(self._drag_lasso.start_y, self._drag_lasso.current_y)
        
        return QRectF(x1, y1, x2 - x1, y2 - y1)

    def _x_to_beats(self, x: float) -> float:
        return max(0.0, float(x) / float(self.pixels_per_beat))

    def _snap(self, beat: float) -> float:
        g = float(self.snap_beats)
        if g <= 0.0:
            return max(0.0, float(beat))
        return max(0.0, round(float(beat) / g) * g)

    def _beats_to_seconds(self, beats: float) -> float:
        bpm = float(getattr(self.project.ctx.project, "bpm", 120.0) or 120.0)
        return (float(beats) * 60.0) / max(1e-6, bpm)

    # --- auto-loop extension

    def _mark_auto_loop_end_for_clip(self, clip_id: str) -> None:
        """Auto-loop extension disabled - loop region stays fixed."""
        # User feedback: "Loop verschwindet beim Clip erstellen - nervt!"
        # Solution: Loop region is now completely manual, no auto-extension
        pass

    def _commit_auto_loop_end(self) -> None:
        """Auto-loop extension disabled - loop stays manual."""
        # No longer automatically extending loop region
        pass

    def _disable_loop(self) -> None:
        self.loop_enabled = False
        self.loop_region_committed.emit(False, float(self.loop_start), float(self.loop_end))
        if self.transport is not None:
            try:
                self.transport.set_loop(False, float(self.loop_start), float(self.loop_end))
            except Exception:
                pass
        self.update()

    # --- waveform cache

    def _volume_to_db(self, vol: float) -> float:
        """Visual-only mapping: fader position -> dB."""
        v = float(vol)
        if v <= 0.0:
            return -120.0
        if v <= 1.0:
            return -60.0 + (60.0 * v)
        v = min(v, 2.0)
        return 6.0 * (v - 1.0)

    def _db_to_gain(self, db: float) -> float:
        if db <= -120.0:
            return 0.0
        return float(10.0 ** (float(db) / 20.0))

    def _display_gain_for_volume(self, vol: float) -> tuple[float, float]:
        db = self._volume_to_db(float(vol))
        return (self._db_to_gain(db), db)

    def _get_peaks_for_path(self, path_str: str) -> _PeaksData | None:
        if sf is None or np is None:
            return None
        if not path_str:
            return None
        try:
            p = os.path.abspath(path_str)
            st = os.stat(p)
            mtime = int(st.st_mtime_ns)
        except Exception:
            return None

        cached = self._peaks_cache.get(p)
        if cached and int(cached.mtime_ns) == mtime:
            # Force re-compute if old cache entry lacks min/max envelope
            if cached.mins is not None and cached.maxs is not None:
                return cached
            # Fall through to re-compute with envelope data

        if p not in self._peaks_pending:
            self._peaks_pending.add(p)
            self._submit_peaks_compute(p, mtime)
        return None

    def _submit_peaks_compute(self, abs_path: str, mtime_ns: int) -> None:
        def fn():
            return self._compute_peaks(abs_path)

        def ok(res):
            try:
                if res is None:
                    return
                peaks_arr, sr, bs, mins_arr, maxs_arr = res
                self._peaks_cache[str(abs_path)] = _PeaksData(
                    mtime_ns=int(mtime_ns),
                    block_size=int(bs),
                    samplerate=int(sr),
                    peaks=peaks_arr,
                    mins=mins_arr,
                    maxs=maxs_arr,
                )
            finally:
                self._peaks_pending.discard(str(abs_path))
                self.update()

        def err(_msg: str):
            self._peaks_pending.discard(str(abs_path))

        try:
            self.project._submit(fn, ok, err)  # type: ignore[attr-defined]
        except Exception:
            try:
                res = self._compute_peaks(abs_path)
                if res is not None:
                    peaks_arr, sr, bs, mins_arr, maxs_arr = res
                    self._peaks_cache[str(abs_path)] = _PeaksData(
                        mtime_ns=int(mtime_ns),
                        block_size=int(bs),
                        samplerate=int(sr),
                        peaks=peaks_arr,
                        mins=mins_arr,
                        maxs=maxs_arr,
                    )
            finally:
                self._peaks_pending.discard(str(abs_path))
                self.update()

    def _compute_peaks(self, abs_path: str):
        """Compute min/max envelope for waveform display (Arranger preview).

        v0.0.20.144:
        - Higher detail (block_size=512)
        - Robust decode: soundfile first, then optional pydub/ffmpeg fallback (MP3/M4A/MP4/etc.)
        """
        if sf is None or np is None:
            return None

        block_size = 512  # more detail than 1024, still fast

        def _compute_from_array(data, sr: int):
            if data is None or getattr(data, 'size', 0) == 0:
                return None
            # Ensure 2D
            if len(getattr(data, 'shape', ())) == 1:
                data2 = data.reshape(-1, 1)
            else:
                data2 = data
            # Mono mix
            mono = data2.mean(axis=1) if data2.shape[1] > 1 else data2[:, 0]
            n = int(mono.shape[0])
            if n <= 0:
                return None
            peaks_list = []
            mins_list = []
            maxs_list = []
            n_chunks = (n + block_size - 1) // block_size
            for i in range(n_chunks):
                s = i * block_size
                e = min(n, (i + 1) * block_size)
                seg = mono[s:e]
                if seg.size == 0:
                    continue
                peaks_list.append(float(np.max(np.abs(seg))))
                mins_list.append(float(np.min(seg)))
                maxs_list.append(float(np.max(seg)))
            if not peaks_list:
                return None
            arr = np.asarray(peaks_list, dtype='float32')
            arr = np.clip(arr, 0.0, 1.0)
            mins_arr = np.asarray(mins_list, dtype='float32')
            maxs_arr = np.asarray(maxs_list, dtype='float32')
            return arr, int(sr or 48000), block_size, mins_arr, maxs_arr

        # 1) soundfile streaming (best quality + memory)
        try:
            f = sf.SoundFile(abs_path)
        except Exception:
            f = None

        if f is not None:
            sr = int(getattr(f, 'samplerate', 48000) or 48000)
            peaks_list = []
            mins_list = []
            maxs_list = []
            try:
                for block in f.blocks(blocksize=block_size, dtype='float32', always_2d=True):
                    if block is None or block.shape[0] == 0:
                        continue
                    mono = block.mean(axis=1) if block.shape[1] > 1 else block[:, 0]
                    peaks_list.append(float(np.max(np.abs(mono))))
                    mins_list.append(float(np.min(mono)))
                    maxs_list.append(float(np.max(mono)))
            except Exception:
                # fallback: read all via soundfile
                try:
                    data = f.read(dtype='float32', always_2d=True)
                    res = _compute_from_array(data, sr)
                    return res
                except Exception:
                    pass
            finally:
                try:
                    f.close()
                except Exception:
                    pass

            if peaks_list:
                arr = np.asarray(peaks_list, dtype='float32')
                arr = np.clip(arr, 0.0, 1.0)
                mins_arr = np.asarray(mins_list, dtype='float32')
                maxs_arr = np.asarray(maxs_list, dtype='float32')
                return arr, sr, block_size, mins_arr, maxs_arr

        # 2) optional pydub/ffmpeg fallback (MP3/M4A/MP4/etc.)
        try:
            from pydub import AudioSegment  # type: ignore
        except Exception:
            return None

        try:
            seg = AudioSegment.from_file(str(abs_path))
            sr = int(getattr(seg, 'frame_rate', 48000) or 48000)
            # normalize to 2ch int16 for predictable conversion
            seg = seg.set_channels(2).set_sample_width(2)
            raw = seg.raw_data
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            data = pcm.reshape(-1, 2)
            return _compute_from_array(data, sr)
        except Exception:
            return None


    # --- drawing helpers

    def _draw_handle_strips(self, p: QPainter, rect: QRectF, is_sel: bool) -> None:
        w = 6.0
        col = self.palette().highlight().color() if is_sel else self.palette().dark().color()
        p.fillRect(QRectF(rect.left(), rect.top(), w, rect.height()), QBrush(col))
        p.fillRect(QRectF(rect.right() - w, rect.top(), w, rect.height()), QBrush(col))


    def _draw_clip_fades(self, p: QPainter, rect: QRectF, clip, *, show_handles: bool) -> None:
        """Draw fade-in/out overlays + optional handles on arranger clips (audio only).

        Non-destructive: reads/writes clip.fade_in_beats / fade_out_beats.
        """
        try:
            if str(getattr(clip, "kind", "")) != "audio":
                return
        except Exception:
            return

        try:
            fi = float(getattr(clip, "fade_in_beats", 0.0) or 0.0)
            fo = float(getattr(clip, "fade_out_beats", 0.0) or 0.0)
        except Exception:
            fi, fo = 0.0, 0.0

        # Overlays (always visible if non-zero)
        try:
            if fi > 0.001:
                fi_px = max(0.0, min(float(rect.width()), float(fi) * float(self.pixels_per_beat)))
                poly = [
                    QPointF(rect.left(), rect.top()),
                    QPointF(rect.left() + fi_px, rect.top()),
                    QPointF(rect.left(), rect.bottom()),
                ]
                p.save()
                p.setBrush(QBrush(QColor(0, 0, 0, 70)))
                pen = QPen(QColor(255, 165, 0, 220))
                pen.setWidth(2)
                p.setPen(pen)
                p.drawPolygon(QPolygonF(poly))
                p.restore()
        except Exception:
            pass

        try:
            if fo > 0.001:
                fo_px = max(0.0, min(float(rect.width()), float(fo) * float(self.pixels_per_beat)))
                poly = [
                    QPointF(rect.right(), rect.top()),
                    QPointF(rect.right() - fo_px, rect.top()),
                    QPointF(rect.right(), rect.bottom()),
                ]
                p.save()
                p.setBrush(QBrush(QColor(0, 0, 0, 70)))
                pen = QPen(QColor(100, 149, 237, 220))
                pen.setWidth(2)
                p.setPen(pen)
                p.drawPolygon(QPolygonF(poly))
                p.restore()
        except Exception:
            pass

        if not show_handles:
            return

        # Handles (only on hover/selection to avoid clutter)
        try:
            if rect.width() < 60 or rect.height() < 18:
                return

            # Fade-In handle (top-left)
            hin = QRectF(rect.left() + 8.0, rect.top() + 3.0, 13.0, 13.0)
            p.save()
            p.setOpacity(0.92)
            p.setPen(QPen(self.palette().text().color()))
            p.setBrush(QBrush(self.palette().midlight().color()))
            try:
                p.drawRoundedRect(hin, 2.5, 2.5)
            except Exception:
                p.drawRect(hin)
            tri = [
                QPointF(hin.left() + 3, hin.top() + 3),
                QPointF(hin.right() - 3, hin.top() + 3),
                QPointF(hin.left() + 3, hin.bottom() - 3),
            ]
            p.setBrush(QBrush(QColor(255, 165, 0, 240)))
            p.setPen(QPen(QColor(255, 165, 0, 240)))
            p.drawPolygon(QPolygonF(tri))
            p.restore()

            # Fade-Out handle (top-right, left of ▾ dropdown)
            hout = QRectF(rect.right() - 32.0, rect.top() + 3.0, 13.0, 13.0)
            p.save()
            p.setOpacity(0.92)
            p.setPen(QPen(self.palette().text().color()))
            p.setBrush(QBrush(self.palette().midlight().color()))
            try:
                p.drawRoundedRect(hout, 2.5, 2.5)
            except Exception:
                p.drawRect(hout)
            tri2 = [
                QPointF(hout.right() - 3, hout.top() + 3),
                QPointF(hout.left() + 3, hout.top() + 3),
                QPointF(hout.right() - 3, hout.bottom() - 3),
            ]
            p.setBrush(QBrush(QColor(100, 149, 237, 240)))
            p.setPen(QPen(QColor(100, 149, 237, 240)))
            p.drawPolygon(QPolygonF(tri2))
            p.restore()
        except Exception:
            return

    def _draw_clip_gain_pan_controls(self, p: QPainter, rect: QRectF, clip, *, show_handles: bool) -> None:
        """Draw small Gain/Pan mini-handles on audio clips (Arranger-level).

        v0.0.20.176:
        - Two mini buttons in the clip header: G (gain) and P (pan).
        - Non-destructive: updates clip.gain / clip.pan via ProjectService.update_audio_clip_params().
        """
        if not show_handles:
            return
        try:
            if str(getattr(clip, "kind", "")) != "audio":
                return
        except Exception:
            return
        if rect.width() < 90 or rect.height() < 18:
            return

        try:
            g_rect = self._gain_handle_rect(rect)
            p_rect = self._pan_handle_rect(rect)
        except Exception:
            return

        # Active highlight when dragging
        active = self._drag_gainpan
        active_gain = bool(active and str(getattr(active, 'clip_id', '')) == str(getattr(clip, 'id', '')) and str(getattr(active, 'which', '')) == 'gain')
        active_pan = bool(active and str(getattr(active, 'clip_id', '')) == str(getattr(clip, 'id', '')) and str(getattr(active, 'which', '')) == 'pan')

        def draw_btn(r: QRectF, label: str, is_active: bool) -> None:
            p.save()
            p.setOpacity(0.92)
            pen_col = self.palette().highlight().color() if is_active else self.palette().text().color()
            bg_col = self.palette().highlight().color() if is_active else self.palette().midlight().color()
            bg = QColor(bg_col)
            bg.setAlpha(170 if is_active else 190)
            p.setPen(QPen(pen_col))
            p.setBrush(QBrush(bg))
            try:
                p.drawRoundedRect(r, 2.5, 2.5)
            except Exception:
                p.drawRect(r)
            p.setOpacity(1.0)
            p.setPen(QPen(self.palette().text().color()))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
            p.restore()

        draw_btn(g_rect, 'G', active_gain)
        draw_btn(p_rect, 'P', active_pan)

        # Tiny pan indicator inside the P button
        try:
            pan = float(getattr(clip, 'pan', 0.0) or 0.0)
        except Exception:
            pan = 0.0
        try:
            cx = float(p_rect.center().x())
            cy = float(p_rect.center().y())
            # baseline
            p.save()
            p.setPen(QPen(self.palette().mid().color()))
            p.drawLine(QPointF(p_rect.left() + 2.0, cy + 4.0), QPointF(p_rect.right() - 2.0, cy + 4.0))
            # dot mapped to pan [-1..1]
            xdot = cx + (max(-1.0, min(1.0, pan)) * (p_rect.width() * 0.35))
            p.setBrush(QBrush(self.palette().text().color()))
            p.setPen(QPen(self.palette().text().color()))
            p.drawEllipse(QPointF(xdot, cy + 4.0), 1.6, 1.6)
            p.restore()
        except Exception:
            pass
    def _draw_audio_waveform(self, p: QPainter, rect: QRectF, clip, track_volume: float) -> None:
        """Draw audio waveform as filled min/max envelope (Audio-Editor quality)."""
        peaks = self._get_peaks_for_path(str(getattr(clip, "source_path", "") or ""))
        if peaks is None or np is None:
            p.setPen(QPen(self.palette().mid().color()))
            p.drawText(rect.adjusted(6, 2, -6, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Waveform…")
            return

        beats_to_sec = self._beats_to_seconds(1.0)
        offset_sec = float(getattr(clip, "offset_seconds", 0.0) or 0.0)
        length_sec = float(getattr(clip, "length_beats", 0.0) or 0.0) * beats_to_sec
        if length_sec <= 0.0:
            return

        pps = peaks.peaks_per_second
        start_i = int(max(0.0, offset_sec * pps))
        end_i = int(max(start_i + 1, (offset_sec + length_sec) * pps))

        # Use min/max envelope if available, fallback to peak-only
        has_envelope = (peaks.mins is not None and peaks.maxs is not None
                        and len(peaks.mins) > 0 and len(peaks.maxs) > 0)

        if has_envelope:
            seg_mins = peaks.mins[start_i:min(end_i, len(peaks.mins))]
            seg_maxs = peaks.maxs[start_i:min(end_i, len(peaks.maxs))]
        else:
            seg = peaks.peaks[start_i:min(end_i, len(peaks.peaks))]
            if seg.size == 0:
                return
            seg_mins = -np.abs(seg)
            seg_maxs = np.abs(seg)

        if seg_mins.size == 0 or seg_maxs.size == 0:
            return

        # Resample to pixel width
        n = max(8, int(rect.width()))
        if seg_mins.size != n:
            x_old = np.linspace(0.0, 1.0, num=int(seg_mins.size), dtype=np.float32)
            x_new = np.linspace(0.0, 1.0, num=int(n), dtype=np.float32)
            seg_mins = np.interp(x_new, x_old, seg_mins).astype(np.float32)
            seg_maxs = np.interp(x_new, x_old, seg_maxs).astype(np.float32)

        # Apply volume gain
        gain, _db = self._display_gain_for_volume(track_volume)
        clip_gain = float(getattr(clip, "gain", 1.0) or 1.0)
        total_gain = float(gain) * float(clip_gain)
        seg_mins = np.clip(seg_mins * total_gain, -1.0, 1.0)
        seg_maxs = np.clip(seg_maxs * total_gain, -1.0, 1.0)

        # v0.0.20.144: visual normalization (UI-only)
        # Arranger clips can be very short in height; boost quiet material so you can SEE cut points.
        try:
            seg_peak = float(max(np.max(np.abs(seg_mins)), np.max(np.abs(seg_maxs))))
            if seg_peak > 1e-6:
                boost = max(1.0, min(8.0, 0.75 / seg_peak))
                if boost > 1.01:
                    seg_mins = np.clip(seg_mins * boost, -1.0, 1.0)
                    seg_maxs = np.clip(seg_maxs * boost, -1.0, 1.0)
        except Exception:
            pass

        # Reverse waveform display when clip is reversed
        if bool(getattr(clip, "reversed", False)):
            seg_mins = seg_mins[::-1].copy()
            seg_maxs = seg_maxs[::-1].copy()

        # Draw filled envelope path (same technique as Audio Editor)
        from PySide6.QtGui import QPainterPath
        mid_y = rect.center().y()
        amp_h = rect.height() * 0.42
        x0 = float(rect.left())

        path = QPainterPath()

        # Top envelope (maxs) left-to-right
        for i in range(n):
            x = x0 + float(i)
            y = mid_y - float(seg_maxs[i]) * amp_h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # Bottom envelope (mins) right-to-left
        for i in range(n - 1, -1, -1):
            x = x0 + float(i)
            y = mid_y - float(seg_mins[i]) * amp_h
            path.lineTo(x, y)

        path.closeSubpath()

        # Draw with fill + outline
        wave_color = self.palette().text().color()
        fill_color = QColor(self.palette().mid().color())
        fill_color.setAlpha(110)

        p.save()
        p.setPen(QPen(wave_color, 1))
        p.setBrush(QBrush(fill_color))
        p.drawPath(path)

        # Center line
        pen_center = QPen(self.palette().mid().color())
        pen_center.setWidth(1)
        p.setPen(pen_center)
        p.drawLine(QPointF(rect.left(), mid_y), QPointF(rect.right(), mid_y))
        p.restore()

    # v0.0.20.650: Clip-Warp im Arranger (AP3 Phase 3C Task 4)
    def _draw_clip_warp_markers(self, p: QPainter, rect: QRectF, clip) -> None:
        """Draw warp markers as small triangles inside audio clips in the arranger.

        Warp markers show where time-stretching anchor points are placed.
        They appear as orange triangles at the bottom of the clip with thin
        vertical dashed lines running up through the waveform.
        """
        try:
            markers = getattr(clip, 'stretch_markers', None)
            if not markers or not isinstance(markers, list):
                return
            clip_len = float(getattr(clip, 'length_beats', 0.0) or 0.0)
            if clip_len <= 0.0:
                return

            p.save()
            marker_color = QColor(255, 160, 40, 200)  # warm orange
            line_color = QColor(255, 160, 40, 80)      # semi-transparent

            for m in markers:
                try:
                    # Support both dict {src_beat, dst_beat} and float (simple position)
                    if isinstance(m, dict):
                        dst = float(m.get('dst_beat', m.get('beat', 0.0)) or 0.0)
                    elif isinstance(m, (int, float)):
                        dst = float(m)
                    else:
                        continue

                    # Normalise position within clip
                    frac = dst / clip_len
                    if frac < 0.0 or frac > 1.0:
                        continue

                    x = rect.left() + frac * rect.width()

                    # Dashed vertical line
                    pen = QPen(line_color)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    pen.setWidth(1)
                    p.setPen(pen)
                    p.drawLine(QPointF(x, rect.top() + 2), QPointF(x, rect.bottom() - 6))

                    # Small triangle marker at bottom
                    tri_h = min(6.0, rect.height() * 0.15)
                    tri_w = 4.0
                    from PySide6.QtGui import QPainterPath as _WarpPath
                    tri = _WarpPath()
                    tri.moveTo(x, rect.bottom() - tri_h)
                    tri.lineTo(x - tri_w, rect.bottom())
                    tri.lineTo(x + tri_w, rect.bottom())
                    tri.closeSubpath()
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(marker_color))
                    p.drawPath(tri)

                except Exception:
                    continue

            # Stretch mode badge (top-right, compact)
            smode = str(getattr(clip, 'stretch_mode', 'tones') or 'tones')
            if smode != 'tones' and rect.width() > 50:
                badge_map = {'beats': '🥁', 'texture': '🌊', 'repitch': '🎵',
                             'complex': '💎'}
                badge = badge_map.get(smode, '')
                if badge:
                    p.setPen(QPen(QColor(255, 200, 100, 220)))
                    from PySide6.QtGui import QFont as _WarpFont
                    f = p.font()
                    f.setPointSize(max(7, f.pointSize() - 1))
                    p.setFont(f)
                    p.drawText(QRectF(rect.right() - 24, rect.bottom() - 14, 20, 12),
                               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, badge)

            p.restore()
        except Exception:
            try:
                p.restore()
            except Exception:
                pass

    def _draw_midi_preview(self, p: QPainter, rect: QRectF, clip) -> None:
        notes = []
        try:
            notes = list(self.project.ctx.project.midi_notes.get(clip.id, []))
        except Exception:
            notes = []
        if not notes:
            p.setPen(QPen(self.palette().mid().color()))
            p.drawText(rect.adjusted(6, 2, -6, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "MIDI…")
            return

        off_beats = float(getattr(clip, "offset_beats", 0.0) or 0.0)
        clip_len = max(1e-6, float(getattr(clip, "length_beats", 1.0) or 1.0))

        # v0.0.20.361: During content scale drag, use ORIGINAL clip length
        # so notes visually fill the stretched clip (preview of scaling result).
        _cs = getattr(self, '_drag_content_scale', None)
        if _cs is not None and str(getattr(_cs, 'clip_id', '')) == str(clip.id):
            clip_len = max(1e-6, float(_cs.origin_len))

        vis = []
        for n in notes:
            st = float(getattr(n, "start_beats", 0.0) or 0.0) - off_beats
            en = st + float(getattr(n, "length_beats", 0.0) or 0.0)
            if en < 0.0 or st > clip_len:
                continue
            vis.append(n)
        if not vis:
            p.setPen(QPen(self.palette().mid().color()))
            p.drawText(rect.adjusted(6, 2, -6, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "MIDI…")
            return

        pitches = [int(getattr(n, "pitch", 60) or 60) for n in vis]
        pmin = min(pitches)
        pmax = max(pitches)
        if pmax <= pmin:
            pmax = pmin + 1

        def y_for_pitch(pitch: int) -> float:
            t = (pitch - pmin) / float(pmax - pmin)
            return rect.bottom() - (t * rect.height())

        # Draw MIDI preview bars with VISIBLE borders but SUBTLE fill
        # User wants: "100% MIDI bausteine sehen" with "3% füllfarbe"
        border_color = self.palette().highlight().color()
        border_color.setAlpha(180)  # Visible border (70%)
        p.setPen(QPen(border_color, 1))  # 1px border
        
        # Fill color: VERY subtle (3% as requested)
        fill_color = self.palette().highlight().color()
        fill_color.setAlpha(8)  # 3% fill
        p.setBrush(QBrush(fill_color))
        
        for n in vis:
            st = float(getattr(n, "start_beats", 0.0) or 0.0) - off_beats
            ln = float(getattr(n, "length_beats", 0.0) or 0.0)
            pitch = int(getattr(n, "pitch", 60) or 60)
            x1 = rect.left() + (st / clip_len) * rect.width()
            x2 = rect.left() + ((st + ln) / clip_len) * rect.width()
            y = y_for_pitch(pitch)
            h = max(3.0, rect.height() / 12.0)
            r = QRectF(x1, y - h, max(2.0, x2 - x1), h)
            p.drawRect(r)  # Draw with border + fill

    # --- Drag&Drop (Arranger target + source)

    def _start_clip_drag(self, clip_id: str) -> None:
        drag = QDrag(self)
        md = QMimeData()
        md.setData("application/x-pydaw-clipid", clip_id.encode("utf-8"))
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):  # noqa: ANN001
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = event.mimeData()
            if md and md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                self._update_plugin_drag_preview(event.position(), md)
                self._sync_plugin_drag_hint(event.position())
                event.acceptProposedAction()
                return
            if md and md.hasFormat("application/x-pydaw-clipid"):
                event.acceptProposedAction()
                # v0.0.20.589: Show ghost preview for Launcher→Arranger drag
                try:
                    cid = bytes(md.data("application/x-pydaw-clipid")).decode("utf-8")
                    clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(cid)), None)
                    if clip_obj and getattr(clip_obj, 'launcher_only', False):
                        lbl = str(getattr(clip_obj, 'label', '') or 'Clip')
                        kind = str(getattr(clip_obj, 'kind', '') or '')
                        icon = '🎵' if kind == 'midi' else '🔊'
                        self._drag_ghost_kind = "launcher-clip"
                        self._drag_ghost_label = f"{icon} {lbl}"
                        self._drag_ghost_pos = QPointF(event.position())
                        self.update()
                    else:
                        self._drag_ghost_kind = ""  # internal arranger drag — no ghost needed
                except Exception:
                    self._drag_ghost_kind = ""
                return

            # Audio-Editor Slice export
            if md and md.hasFormat(MIME_AUDIOEVENT_SLICE):
                event.acceptProposedAction()
                self._drag_ghost_kind = "audio-slice"
                self._drag_ghost_label = "✂ Slice"
                self._drag_ghost_pos = QPointF(event.position())
                self.update()
                return
            if md and md.hasFormat(MIME_CROSS_PROJECT):
                event.acceptProposedAction()
                # v0.0.20.79: set ghost metadata from cross-project payload
                self._drag_ghost_kind = "cross-project"
                try:
                    payload = parse_cross_project_drop(md)
                    if payload:
                        itype = payload.get("item_type", "")
                        ids = payload.get("track_ids", []) or payload.get("clip_ids", [])
                        count = len(ids) if ids else 1
                        self._drag_ghost_label = f"↗ {count} {itype.title()}"
                    else:
                        self._drag_ghost_label = "↗ Cross-Project"
                except Exception:
                    self._drag_ghost_label = "↗ Cross-Project"
                self._drag_ghost_pos = QPointF(event.position())
                self.update()
                return
            if md and md.hasUrls():
                event.acceptProposedAction()
                # v0.0.20.79: ghost for audio/midi file drops
                try:
                    pth = md.urls()[0].toLocalFile() if md.urls() else ""
                    ext = Path(pth).suffix.lower() if pth else ""
                    if ext in (".mid", ".midi"):
                        self._drag_ghost_kind = "midi"
                        self._drag_ghost_label = f"🎵 {Path(pth).name}"
                    else:
                        self._drag_ghost_kind = "audio"
                        self._drag_ghost_label = f"🔊 {Path(pth).name}"
                except Exception:
                    self._drag_ghost_kind = "audio"
                    self._drag_ghost_label = "🔊 Audio"
                self._drag_ghost_pos = QPointF(event.position())
                self.update()
                return
        except Exception:
            log.exception("ArrangerCanvas.dragEnterEvent failed")
        try:
            super().dragEnterEvent(event)
        except Exception:
            pass

    def dragMoveEvent(self, event):  # noqa: ANN001
        """Accept drag-move for all supported MIME types (v0.0.20.78).
        
        v0.0.20.79: Also tracks cursor position for ghost-clip overlay.
        """
        try:
            md = event.mimeData()
            if md and md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                self._update_plugin_drag_preview(event.position(), md)
                self._sync_plugin_drag_hint(event.position())
                event.acceptProposedAction()
                return
            if md and (md.hasFormat("application/x-pydaw-clipid")
                       or md.hasFormat(MIME_CROSS_PROJECT)
                       or md.hasFormat(MIME_AUDIOEVENT_SLICE)
                       or md.hasUrls()):
                event.acceptProposedAction()
                # v0.0.20.79: update ghost position
                if self._drag_ghost_kind:
                    self._drag_ghost_pos = QPointF(event.position())
                    self.update()
                return
        except Exception:
            log.exception("ArrangerCanvas.dragMoveEvent failed")
        try:
            super().dragMoveEvent(event)
        except Exception:
            pass

    def dragLeaveEvent(self, event):  # noqa: ANN001
        """v0.0.20.79: Clear ghost-clip overlay when drag leaves canvas."""
        try:
            self._drag_ghost_pos = None
            self._drag_ghost_kind = ""
            self._drag_ghost_label = ""
            self._clear_plugin_drag_preview()
            self.update()
        except Exception:
            pass
        try:
            super().dragLeaveEvent(event)
        except Exception:
            pass

    def dropEvent(self, event):  # noqa: ANN001
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        # v0.0.20.79: clear ghost overlay on drop
        self._drag_ghost_pos = None
        self._drag_ghost_kind = ""
        self._drag_ghost_label = ""
        self._clear_plugin_drag_preview()
        try:
            md = event.mimeData()
            if not md:
                try:
                    event.ignore()
                except Exception:
                    pass
                return

            if md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                blocked_message = ""
                payload = self._parse_plugin_drag_payload(md) or {}
                info = self._parse_plugin_drag_info(md)
                pos = event.position()
                if info is not None:
                    device_kind, _plugin_name = info
                    if device_kind == "instrument" and self._is_below_last_lane_y(float(pos.y())):
                        try:
                            self.request_smartdrop_new_instrument_track.emit(dict(payload))
                            event.acceptProposedAction()
                        except Exception:
                            try:
                                event.ignore()
                            except Exception:
                                pass
                        return
                    trk = self._track_at_y(float(pos.y()))
                    track_id = str(getattr(trk, "id", "") or "")
                    info = self._plugin_drop_target_info(trk, device_kind) if trk is not None else {}
                    _label = str(info.get("label") or "")
                    actionable = bool(info.get("actionable"))
                    blocked_message = str(info.get("blocked_message") or "")
                    target_kind = str(info.get("target_kind") or "")
                    if track_id and actionable:
                        try:
                            if device_kind == "instrument":
                                self.request_smartdrop_instrument_to_track.emit(track_id, dict(payload))
                            else:
                                self.request_smartdrop_fx_to_track.emit(track_id, dict(payload))
                            event.acceptProposedAction()
                        except Exception:
                            try:
                                event.ignore()
                            except Exception:
                                pass
                        return
                    if track_id and device_kind == "instrument" and target_kind == "audio":
                        try:
                            self.request_smartdrop_instrument_morph_guard.emit(track_id, dict(payload))
                            blocked_message = ""
                        except Exception:
                            pass
                if blocked_message:
                    try:
                        self.status_message.emit(blocked_message, 3600)
                    except Exception:
                        pass
                try:
                    event.ignore()
                except Exception:
                    pass
                return

            # external files (audio/midi)
            if md.hasUrls() and not md.hasFormat("application/x-pydaw-clipid"):
                urls = md.urls()
                if not urls:
                    return
                pth = urls[0].toLocalFile()
                if not pth:
                    return
                path = Path(pth)
                pos = event.position()
                trk = self._track_at_y(pos.y())
                if not trk:
                    return
                beat = self._snap(self._x_to_beats(pos.x()))
                ext = path.suffix.lower()
                if ext in (".mid", ".midi"):
                    self.project.import_midi_to_track_at(trk.id, path, start_beats=beat)
                else:
                    source_bpm_override = None
                    try:
                        if md.hasFormat("application/x-pydaw-audio-bpm"):
                            raw = bytes(md.data("application/x-pydaw-audio-bpm")).decode("utf-8")
                            source_bpm_override = float(raw.strip())
                    except Exception:
                        source_bpm_override = None
                    self.project.add_audio_clip_from_file_at(
                        trk.id,
                        path,
                        start_beats=beat,
                        source_bpm_override=source_bpm_override,
                    )
                event.acceptProposedAction()
                return

            # Cross-project drag&drop: tracks/clips from another tab (v0.0.20.78)
            if md.hasFormat(MIME_CROSS_PROJECT):
                payload = parse_cross_project_drop(md)
                if payload and self._tab_service:
                    try:
                        src_idx = payload.get("source_tab_index", -1)
                        item_type = payload.get("item_type", "")
                        pos = event.position()
                        trk = self._track_at_y(pos.y())
                        target_idx = self._tab_service.active_index

                        if item_type == "tracks" and src_idx != target_idx:
                            track_ids = payload.get("track_ids", [])
                            if track_ids:
                                self._tab_service.copy_tracks_between_tabs(
                                    src_idx, target_idx, track_ids,
                                    include_clips=payload.get("include_clips", True),
                                    include_device_chains=payload.get("include_device_chains", True),
                                )
                                # v0.0.20.86: emit project_updated so TrackList/Mixer/etc. refresh
                                try:
                                    self.project.project_updated.emit()
                                except Exception:
                                    pass
                                self.update()
                                log.info("Cross-project: copied %d track(s) from tab %d → %d",
                                         len(track_ids), src_idx, target_idx)

                        elif item_type == "clips" and src_idx != target_idx:
                            clip_ids = payload.get("clip_ids", [])
                            if clip_ids and trk:
                                self._tab_service.copy_clips_between_tabs(
                                    src_idx, target_idx, clip_ids,
                                    target_track_id=trk.id,
                                )
                                # v0.0.20.86: emit project_updated
                                try:
                                    self.project.project_updated.emit()
                                except Exception:
                                    pass
                                self.update()
                                log.info("Cross-project: copied %d clip(s) from tab %d → %d",
                                         len(clip_ids), src_idx, target_idx)
                    except Exception:
                        log.exception("Cross-project drop failed")
                event.acceptProposedAction()
                return

                        # Audio-Editor Slice export drop: create a new clip from selected AudioEvents
            if md.hasFormat(MIME_AUDIOEVENT_SLICE):
                try:
                    raw = bytes(md.data(MIME_AUDIOEVENT_SLICE)).decode('utf-8')
                    payload = json.loads(raw) if raw else {}
                except Exception:
                    payload = {}
                try:
                    src_clip_id = str(payload.get('clip_id', '') or '').strip()
                    event_ids = payload.get('event_ids', []) or []
                except Exception:
                    src_clip_id = ''
                    event_ids = []
                if not src_clip_id or not event_ids:
                    return
                pos = event.position()
                trk = self._track_at_y(pos.y())
                if not trk:
                    return
                beat = self._snap(self._x_to_beats(pos.x()))
                try:
                    new_id = self.project.add_audio_clip_from_clip_events_at(src_clip_id, list(event_ids), trk.id, start_beats=float(beat))
                except Exception:
                    new_id = None
                if new_id:
                    try:
                        self.selected_clip_ids = {str(new_id)}
                        self.selected_clip_id = str(new_id)
                        self.clip_selected.emit(str(new_id))
                    except Exception:
                        pass
                    self._mark_auto_loop_end_for_clip(str(new_id))
                    self.update()
                event.acceptProposedAction()
                return

# internal clip drag (copy)
            if not md.hasFormat("application/x-pydaw-clipid"):
                return
            clip_id = bytes(md.data("application/x-pydaw-clipid")).decode("utf-8")
            src = next((c for c in self._arranger_clips() if c.id == clip_id), None)

            # v0.0.20.589: Accept launcher_only clips (Bitwig Launcher→Arranger drag)
            is_from_launcher = False
            if not src:
                src = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(clip_id)), None)
                if src and getattr(src, 'launcher_only', False):
                    is_from_launcher = True
                else:
                    return

            pos = event.position()
            trk = self._track_at_y(pos.y())
            if not trk:
                return

            beat = self._snap(self._x_to_beats(pos.x()))
            self.project.duplicate_clip(clip_id)
            dup_id = self.project.ctx.project.clips[-1].id

            # v0.0.20.589: Promote duplicate to arranger clip (launcher_only=False)
            dup_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(dup_id)), None)
            if dup_obj is not None:
                dup_obj.launcher_only = False

            self.project.move_clip(dup_id, beat, snap_beats=self.snap_beats)
            self.project.move_clip_track(dup_id, trk.id)
            self.selected_clip_ids = {dup_id}
            self.selected_clip_id = dup_id
            self.clip_selected.emit(dup_id)
            self._mark_auto_loop_end_for_clip(dup_id)
            self.update()
            event.acceptProposedAction()
        except Exception:
            log.exception("ArrangerCanvas.dropEvent failed")
            try:
                event.ignore()
            except Exception:
                pass

    # --- interactions

    def contextMenuEvent(self, event):  # noqa: ANN001
        # v0.0.20.98: Suppress after right-click loop drawing or lasso
        if self._suppress_next_context_menu:
            self._suppress_next_context_menu = False
            event.accept()
            return
        pos = QPointF(event.pos())

        def add_grid_menu(menu: QMenu) -> None:
            menu.addSeparator()
            a_snap = menu.addAction("Snap")
            a_snap.setCheckable(True)
            a_snap.setChecked(bool(self.snap_beats and self.snap_beats > 0))

            sub = menu.addMenu("Grid")
            current = str(getattr(self.project.ctx.project, "snap_division", "1/16") or "1/16")
            for d in ["1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]:
                a = sub.addAction(d)
                a.setCheckable(True)
                a.setChecked(d == current)

            menu.addSeparator()
            a_zi = menu.addAction("Zoom +")
            a_zo = menu.addAction("Zoom -")

            return a_snap, sub, a_zi, a_zo

        # Ruler
        if pos.y() <= self.ruler_height:
            menu = QMenu(self)
            a_off = menu.addAction("Loop Off")
            a_off.setShortcut("Ctrl+L")
            a_snap, sub, a_zi, a_zo = add_grid_menu(menu)
            act = menu.exec(event.globalPos())
            if act == a_off:
                self._disable_loop()
                return
            if act == a_snap:
                if self.snap_beats and self.snap_beats > 0:
                    self.snap_beats = 0.0
                else:
                    self.set_snap_division(str(getattr(self.project.ctx.project, "snap_division", "1/16") or "1/16"))
                self.update()
                return
            if act in sub.actions():
                div = act.text()
                try:
                    self.project.set_snap_division(div)
                except Exception:
                    setattr(self.project.ctx.project, "snap_division", div)
                self.set_snap_division(div)
                self.update()
                return
            if act == a_zi:
                self.zoom_in()
                return
            if act == a_zo:
                self.zoom_out()
                return
            return


        # Clip
        cid = self._clip_at_pos(pos)
        if cid:
            # DAW-like right-click selection:
            # - If user right-clicks a clip that is NOT in the current selection, select only that clip.
            # - If user right-clicks a clip that IS already selected (multi-selection), keep the selection.
            try:
                cur_sel = set(self.selected_clip_ids or set())
            except Exception:
                cur_sel = set()
            if cid not in cur_sel:
                self.selected_clip_ids = {cid}
            else:
                # keep existing selection (ensure it's a set)
                self.selected_clip_ids = set(cur_sel) if cur_sel else {cid}

            self.selected_clip_id = cid
            self.clip_selected.emit(cid)
            self.update()

            menu = QMenu(self)
            a_rename = menu.addAction("Umbenennen…")
            a_dup = menu.addAction("Duplizieren")

            # Selected clips (for multi operations)
            try:
                sel_ids = set(self.selected_clip_ids or set())
            except Exception:
                sel_ids = {cid}
            try:
                sel_clips = [c for c in self._arranger_clips() if str(getattr(c, "id", "")) in sel_ids]
            except Exception:
                sel_clips = []

            # Export MIDI (nur für MIDI Clips)
            a_export_midi = None
            clip = next((c for c in self._arranger_clips() if c.id == cid), None)
            if clip and getattr(clip, "kind", "") == "midi":
                menu.addSeparator()
                a_export_midi = menu.addAction("Export as MIDI...")

            # Split Clip (nur ein Clip selektiert)
            a_split = None
            if len(sel_ids) == 1:
                menu.addSeparator()
                a_split = menu.addAction("Clip teilen (an Cursor)")
                a_split.setShortcut("K")

            # Bounce in Place (sicherer Audio-Proxy auf neuer Spur)
            a_bip = None
            a_bip_mute = None
            a_bip_dry = None
            try:
                if sel_clips:
                    kinds_bip = {str(getattr(c, "kind", "")) for c in sel_clips}
                    tracks_bip = {str(getattr(c, "track_id", "")) for c in sel_clips}
                    if len(tracks_bip) == 1 and kinds_bip.issubset({"audio", "midi"}):
                        menu.addSeparator()
                        a_bip = menu.addAction("Bounce in Place…")
                        a_bip_mute = menu.addAction("Bounce in Place + Quelle stummschalten")
                        a_bip_dry = menu.addAction("Bounce in Place (Dry)…")
            except Exception:
                a_bip = None
                a_bip_mute = None
                a_bip_dry = None

            # Join/Consolidate (nur wenn mehrere selektiert, gleiche Spur, gleicher Typ)
            a_join = None
            a_keep = None
            a_trim = None
            a_handles = None
            a_trim_handles = None
            a_keep_trim = None
            a_keep_handles = None
            a_keep_trim_handles = None
            if len(sel_clips) >= 2:
                try:
                    kinds = {str(getattr(c, "kind", "")) for c in sel_clips}
                    tracks = {str(getattr(c, "track_id", "")) for c in sel_clips}
                except Exception:
                    kinds = set()
                    tracks = set()

                if len(kinds) == 1 and len(tracks) == 1:
                    kind = next(iter(kinds)) if kinds else ""
                    menu.addSeparator()
                    if kind == "audio":
                        a_join = menu.addAction(f"Consolidate ({len(sel_clips)} Clips)")
                        a_join.setShortcut("Ctrl+J")
                        a_keep = menu.addAction("Consolidate (Originale behalten)")
                        # Pro variants (future-proof): Trim / Handles + optional keep originals
                        pro = menu.addMenu("Consolidate (Pro)")
                        a_trim = pro.addAction("Consolidate (Trim)")
                        a_handles = pro.addAction("Consolidate (+Handles)")
                        a_trim_handles = pro.addAction("Consolidate (Trim + Handles)")
                        pro.addSeparator()
                        a_keep_trim = pro.addAction("Trim (Originale behalten)")
                        a_keep_handles = pro.addAction("+Handles (Originale behalten)")
                        a_keep_trim_handles = pro.addAction("Trim + Handles (Originale behalten)")
                    else:
                        a_join = menu.addAction(f"Clips vereinen ({len(sel_clips)} Clips)")
                        a_join.setShortcut("Ctrl+J")

            # Reverse (nur Audio-Clips) — clip-level, zeigt im Arranger direkt den Reverse-Zustand
            a_rev = None
            if sel_clips and all(str(getattr(c, "kind", "")) == "audio" for c in sel_clips):
                menu.addSeparator()
                a_rev = menu.addAction("Reverse")
                a_rev.setCheckable(True)
                try:
                    all_rev = all(bool(getattr(c, "reversed", False)) for c in sel_clips)
                    a_rev.setChecked(all_rev)
                except Exception:
                    pass

            # v0.0.20.650: Warp/Stretch im Arranger (AP3 Phase 3C Task 4)
            warp_mode_actions = {}
            a_warp_auto = None
            a_warp_clear = None
            if sel_clips and all(str(getattr(c, "kind", "")) == "audio" for c in sel_clips):
                try:
                    menu.addSeparator()
                    warp_sub = menu.addMenu("🔀 Warp / Stretch")

                    # Stretch mode selection
                    mode_sub = warp_sub.addMenu("Stretch-Modus")
                    cur_mode = str(getattr(sel_clips[0], 'stretch_mode', 'tones') or 'tones')
                    for mode_id, mode_label in [("tones", "Tones (melodisch)"),
                                                 ("beats", "Beats (perkussiv)"),
                                                 ("texture", "Texture (Ambient/Pads)"),
                                                 ("repitch", "Re-Pitch (kein Stretch)"),
                                                 ("complex", "Complex (höchste Qualität)")]:
                        a_m = mode_sub.addAction(mode_label)
                        a_m.setCheckable(True)
                        a_m.setChecked(mode_id == cur_mode)
                        warp_mode_actions[a_m] = mode_id

                    warp_sub.addSeparator()
                    a_warp_auto = warp_sub.addAction("Auto-Warp (Beat Detection)")
                    a_warp_clear = warp_sub.addAction("Warp-Marker löschen")
                    n_markers = len(getattr(sel_clips[0], 'stretch_markers', []) or [])
                    if n_markers == 0:
                        a_warp_clear.setEnabled(False)
                except Exception:
                    warp_mode_actions = {}
                    a_warp_auto = None
                    a_warp_clear = None

            
            # Fades (nur Audio-Clips) — presets + clear (Cubase-style quick access)
            fade_actions = {}
            a_clear_fades = None
            if sel_clips and all(str(getattr(c, "kind", "")) == "audio" for c in sel_clips):
                try:
                    menu.addSeparator()
                    fade_sub = menu.addMenu("Fades")
                    # Presets in beats (assuming 4/4: 1/16=0.25 beats, 1/8=0.5, 1/4=1.0, 1 Bar=4.0)
                    fade_map = [("1/16", 0.25), ("1/8", 0.5), ("1/4", 1.0), ("1 Bar", 4.0)]
                    for name, beats in fade_map:
                        a = fade_sub.addAction(f"Fade In {name}")
                        fade_actions[a] = ("in", float(beats))
                    fade_sub.addSeparator()
                    for name, beats in fade_map:
                        a = fade_sub.addAction(f"Fade Out {name}")
                        fade_actions[a] = ("out", float(beats))
                    fade_sub.addSeparator()
                    a_clear_fades = fade_sub.addAction("Clear Fades")
                except Exception:
                    fade_actions = {}
                    a_clear_fades = None
            
            # Ultra-Pro / Ultra-Ultra (render_meta)
            a_rerender = None
            a_rerender_ip = None
            a_restore_ip = None
            a_back = None
            a_toggle = None
            a_rebuild = None
            try:
                # v0.0.20.173+: If right-click is slightly off the clip but exactly one clip is selected,
                # use the selected clip as fallback so advanced actions are discoverable.
                clip_for_meta = clip if clip is not None else (sel_clips[0] if len(sel_clips) == 1 else None)
                if len(sel_ids) == 1 and clip_for_meta is not None and str(getattr(clip_for_meta, 'kind', '')) == 'audio':
                    rm = getattr(clip_for_meta, 'render_meta', {}) or {}
                    src_ok = False
                    try:
                        if isinstance(rm, dict):
                            src = rm.get('sources', {})
                            if isinstance(src, dict) and str(src.get('source_clip_id', '') or '').strip():
                                src_ok = True
                    except Exception:
                        src_ok = False

                    # v0.0.20.174: Always show "Re-render (in place)" for audio clips.
                    # It now also works for normal clips (initial render), not only consolidated ones.
                    menu.addSeparator()

                    # Keep the classic order (like our Editor menu)
                    a_rerender = menu.addAction('Re-render (from sources)')
                    if not src_ok:
                        a_rerender.setEnabled(False)

                    a_rerender_ip = menu.addAction('Re-render (in place)')

                    a_restore_ip = menu.addAction('Restore Sources (in place)')
                    a_back = menu.addAction('Back to Sources')
                    a_toggle = menu.addAction('Toggle Rendered ↔ Sources')
                    a_rebuild = menu.addAction('Rebuild original clip state')

                    if not src_ok:
                        try:
                            a_restore_ip.setEnabled(False)
                            a_back.setEnabled(False)
                            a_toggle.setEnabled(False)
                            a_rebuild.setEnabled(False)
                        except Exception:
                            pass
            except Exception:
                pass

            # v0.0.20.639: Take-Lanes / Comping (AP2 Phase 2D)
            a_take_show = None
            a_take_flatten = None
            a_take_activate = None
            a_take_delete = None
            take_gid = str(getattr(clip, 'take_group_id', '') or '') if clip else ''
            if take_gid:
                menu.addSeparator()
                take_sub = menu.addMenu("🎙️ Take-Lanes")
                a_take_activate = take_sub.addAction("✅ Diesen Take aktivieren")
                a_take_show = take_sub.addAction("Take-Lanes ein/ausblenden")
                a_take_flatten = take_sub.addAction("Flatten (nur aktiven Take behalten)")
                a_take_delete = take_sub.addAction("Diesen Take löschen")
            else:
                # Check if track has takes at all
                try:
                    t_id = str(getattr(clip, 'track_id', ''))
                    take_svc = getattr(self, '_take_service', None)
                    if take_svc and take_svc.has_takes(t_id):
                        menu.addSeparator()
                        a_take_show = menu.addAction("🎙️ Take-Lanes ein/ausblenden")
                except Exception:
                    pass

            menu.addSeparator()
            a_del = menu.addAction("Löschen")
            a_snap, sub, a_zi, a_zo = add_grid_menu(menu)
            act = menu.exec(event.globalPos())

            if act == a_rename:
                self.request_rename_clip.emit(cid)
                return
            if act == a_dup:
                self.request_duplicate_clip.emit(cid)
                return
            if a_export_midi and act == a_export_midi:
                self._export_midi_clip(cid)
                return
            if a_bip and act == a_bip:
                try:
                    opts = ask_bounce_freeze_options(
                        self,
                        title="Bounce in Place",
                        info_text="Erstellt sicher eine neue Audiospur aus den ausgewählten Clips. Optional können die Quell-Clips danach stummgeschaltet werden.",
                        default_label="Bounce in Place",
                        include_fx=True,
                        mute_sources=False,
                        allow_mute_sources=True,
                    )
                    if opts.accepted:
                        new_id = self.project.bounce_selected_clips_to_new_audio_track(
                            list(self.selected_clip_ids),
                            include_fx=bool(opts.include_fx),
                            mute_sources=bool(opts.mute_sources),
                            label=str(opts.label or "Bounce in Place"),
                        )
                        if new_id:
                            self.selected_clip_ids = {str(new_id)}
                            self.selected_clip_id = str(new_id)
                            self.clip_selected.emit(str(new_id))
                            self.update()
                except Exception:
                    pass
                return
            if a_bip_mute and act == a_bip_mute:
                try:
                    new_id = self.project.bounce_selected_clips_to_new_audio_track(list(self.selected_clip_ids), include_fx=True, mute_sources=True, label="Bounce in Place")
                    if new_id:
                        self.selected_clip_ids = {str(new_id)}
                        self.selected_clip_id = str(new_id)
                        self.clip_selected.emit(str(new_id))
                        self.update()
                except Exception:
                    pass
                return
            if a_bip_dry and act == a_bip_dry:
                try:
                    opts = ask_bounce_freeze_options(
                        self,
                        title="Bounce in Place (Dry)",
                        info_text="Erstellt sicher eine neue Audiospur ohne Insert-FX aus den ausgewählten Clips. Optional können die Quell-Clips danach stummgeschaltet werden.",
                        default_label="Bounce Dry",
                        include_fx=False,
                        mute_sources=False,
                        allow_mute_sources=True,
                    )
                    if opts.accepted:
                        new_id = self.project.bounce_selected_clips_to_new_audio_track(
                            list(self.selected_clip_ids),
                            include_fx=bool(opts.include_fx),
                            mute_sources=bool(opts.mute_sources),
                            label=str(opts.label or "Bounce Dry"),
                        )
                        if new_id:
                            self.selected_clip_ids = {str(new_id)}
                            self.selected_clip_id = str(new_id)
                            self.clip_selected.emit(str(new_id))
                            self.update()
                except Exception:
                    pass
                return
            if a_split and act == a_split:
                # Split clip at mouse cursor position
                try:
                    beat = self._snap(self._x_to_beats(pos.x()))
                    result = self.project.split_clip(cid, float(beat))
                    if result:
                        left_id, right_id = result
                        self.selected_clip_ids = {right_id}
                        self.selected_clip_id = right_id
                        self.clip_selected.emit(right_id)
                        self.update()
                except Exception:
                    pass
                return

            if a_join and act == a_join:
                # Join/Consolidate selected clips (MIDI join + Audio bounce)
                try:
                    if hasattr(self, "keyboard_handler") and self.keyboard_handler is not None:
                        self.keyboard_handler._join_clips(self.selected_clip_ids)
                        try:
                            if len(self.selected_clip_ids) == 1:
                                nid = next(iter(self.selected_clip_ids))
                                self.selected_clip_id = str(nid)
                                self.clip_selected.emit(str(nid))
                        except Exception:
                            pass
                        self.update()
                    else:
                        # Legacy fallback
                        clip_ids = list(self.selected_clip_ids)
                        new_id = self.project.join_clips(clip_ids)
                        if new_id:
                            self.selected_clip_ids = {new_id}
                            self.selected_clip_id = new_id
                            self.clip_selected.emit(new_id)
                            self.update()
                except Exception:
                    pass
                return

            if a_keep and act == a_keep:
                # Audio consolidate, but keep originals (non-destructive)
                try:
                    snap = None
                    try:
                        if self.snap_beats and float(self.snap_beats) > 0:
                            snap = float(self.snap_beats)
                    except Exception:
                        snap = None
                    new_id = None
                    if hasattr(self.project, "consolidate_audio_clips_bounce"):
                        new_id = self.project.consolidate_audio_clips_bounce(
                            list(self.selected_clip_ids),
                            snap_beats=snap,
                            delete_originals=False,
                            label="Consolidated Audio",
                        )
                    if new_id:
                        self.selected_clip_ids = {str(new_id)}
                        self.selected_clip_id = str(new_id)
                        self.clip_selected.emit(str(new_id))
                        self.update()
                except Exception:
                    pass

            # Pro Consolidate variants (Trim / Handles) + keep originals
            if (a_trim and act == a_trim) or (a_handles and act == a_handles) or (a_trim_handles and act == a_trim_handles)                or (a_keep_trim and act == a_keep_trim) or (a_keep_handles and act == a_keep_handles) or (a_keep_trim_handles and act == a_keep_trim_handles):
                try:
                    if hasattr(self, "keyboard_handler") and self.keyboard_handler is not None:
                        mode = 'default'
                        del_orig = True
                        if a_trim and act == a_trim:
                            mode = 'trim'
                        elif a_handles and act == a_handles:
                            mode = 'handles'
                        elif a_trim_handles and act == a_trim_handles:
                            mode = 'trim_handles'
                        elif a_keep_trim and act == a_keep_trim:
                            mode = 'trim'
                            del_orig = False
                        elif a_keep_handles and act == a_keep_handles:
                            mode = 'handles'
                            del_orig = False
                        elif a_keep_trim_handles and act == a_keep_trim_handles:
                            mode = 'trim_handles'
                            del_orig = False

                        self.keyboard_handler._join_clips(self.selected_clip_ids, mode=str(mode), delete_originals=bool(del_orig))

                        try:
                            if len(self.selected_clip_ids) == 1:
                                nid = next(iter(self.selected_clip_ids))
                                self.selected_clip_id = str(nid)
                                self.clip_selected.emit(str(nid))
                        except Exception:
                            pass
                        self.update()
                except Exception:
                    pass
                return

                return

            # Ultra-Pro actions (render_meta)
            if a_rerender and act == a_rerender:
                try:
                    if hasattr(self.project, 'rerender_clip_from_meta'):
                        self.project.rerender_clip_from_meta(str(cid), replace_usages=True)  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_rerender_ip and act == a_rerender_ip:
                try:
                    if hasattr(self.project, 'rerender_clip_in_place_from_meta'):
                        self.project.rerender_clip_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_restore_ip and act == a_restore_ip:
                try:
                    if hasattr(self.project, 'restore_sources_in_place_from_meta'):
                        self.project.restore_sources_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_toggle and act == a_toggle:
                try:
                    if hasattr(self.project, 'toggle_rendered_sources_in_place_from_meta'):
                        self.project.toggle_rendered_sources_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_rebuild and act == a_rebuild:
                try:
                    if hasattr(self.project, 'rebuild_original_clip_state_from_meta'):
                        self.project.rebuild_original_clip_state_from_meta(str(cid))  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_back and act == a_back:
                try:
                    if hasattr(self.project, 'back_to_sources_from_meta'):
                        self.project.back_to_sources_from_meta(str(cid))  # type: ignore[attr-defined]
                        self.update()
                except Exception:
                    pass
                return

            if a_rev and act == a_rev:
                # Reverse selected audio clip(s) at clip-level
                try:
                    desired = bool(a_rev.isChecked())
                    for c in sel_clips:
                        try:
                            self.project.update_audio_clip_params(str(getattr(c, "id", "")), reversed=desired)
                        except Exception:
                            pass
                    self.update()
                except Exception:
                    pass
                return

            # v0.0.20.650: Warp mode actions (AP3 Phase 3C Task 4)
            if act in (warp_mode_actions or {}):
                try:
                    new_mode = warp_mode_actions[act]
                    for c in sel_clips:
                        try:
                            self.project.update_audio_clip_params(str(getattr(c, "id", "")), stretch_mode=str(new_mode))
                        except Exception:
                            pass
                    self.update()
                    self.status_message.emit(f"Stretch-Modus → {new_mode}", 2000)
                except Exception:
                    pass
                return

            if a_warp_auto and act == a_warp_auto:
                try:
                    for c in sel_clips:
                        try:
                            cid_w = str(getattr(c, "id", ""))
                            src = str(getattr(c, "source_path", "") or "")
                            if not src:
                                continue
                            # Use time_stretch module for beat detection
                            from pydaw.audio.time_stretch import auto_detect_warp_markers
                            bpm = float(getattr(self.project.ctx.project, "bpm", 120.0) or 120.0)
                            markers = auto_detect_warp_markers(src, bpm)
                            if markers:
                                marker_dicts = [{"src_beat": float(m.src_beat), "dst_beat": float(m.dst_beat),
                                                 "is_anchor": bool(m.is_anchor)} for m in markers]
                                self.project.update_audio_clip_params(cid_w, stretch_markers=marker_dicts)
                        except Exception:
                            pass
                    self.update()
                    self.status_message.emit("Auto-Warp: Marker gesetzt", 2000)
                except Exception:
                    pass
                return

            if a_warp_clear and act == a_warp_clear:
                try:
                    for c in sel_clips:
                        try:
                            self.project.update_audio_clip_params(str(getattr(c, "id", "")), stretch_markers=[])
                        except Exception:
                            pass
                    self.update()
                    self.status_message.emit("Warp-Marker gelöscht", 2000)
                except Exception:
                    pass
                return


            # Fade actions (presets)
            if act in (fade_actions or {}):
                try:
                    which, beats = fade_actions.get(act, ("", 0.0))
                    for c in sel_clips:
                        try:
                            if str(which) == "in":
                                self.project.update_audio_clip_params(str(getattr(c, "id", "")), fade_in_beats=float(beats))
                            elif str(which) == "out":
                                self.project.update_audio_clip_params(str(getattr(c, "id", "")), fade_out_beats=float(beats))
                        except Exception:
                            pass
                    self.update()
                except Exception:
                    pass
                return
            
            if a_clear_fades and act == a_clear_fades:
                try:
                    for c in sel_clips:
                        try:
                            self.project.update_audio_clip_params(str(getattr(c, "id", "")), fade_in_beats=0.0, fade_out_beats=0.0)
                        except Exception:
                            pass
                    self.update()
                except Exception:
                    pass
                return
            

            # v0.0.20.639: Take-Lane action handlers
            if a_take_activate and act == a_take_activate:
                try:
                    ts = getattr(self, '_take_service', None)
                    if ts and take_gid:
                        ts.set_active_take(take_gid, cid)
                        self.update()
                except Exception:
                    pass
                return
            if a_take_show and act == a_take_show:
                try:
                    ts = getattr(self, '_take_service', None)
                    t_id = str(getattr(clip, 'track_id', ''))
                    if ts and t_id:
                        ts.toggle_take_lanes(t_id)
                        self.update()
                except Exception:
                    pass
                return
            if a_take_flatten and act == a_take_flatten:
                try:
                    ts = getattr(self, '_take_service', None)
                    if ts and take_gid:
                        ts.flatten_take_group(take_gid)
                        self.update()
                except Exception:
                    pass
                return
            if a_take_delete and act == a_take_delete:
                try:
                    ts = getattr(self, '_take_service', None)
                    if ts:
                        ts.delete_take(cid)
                        self.update()
                except Exception:
                    pass
                return

            if act == a_del:
                self.request_delete_clip.emit(cid)
                return
            if act == a_snap:
                if self.snap_beats and self.snap_beats > 0:
                    self.snap_beats = 0.0
                else:
                    self.set_snap_division(str(getattr(self.project.ctx.project, "snap_division", "1/16") or "1/16"))
                self.update()
                return
            if act in sub.actions():
                div = act.text()
                try:
                    self.project.set_snap_division(div)
                except Exception:
                    setattr(self.project.ctx.project, "snap_division", div)
                self.set_snap_division(div)
                self.update()
                return
            if act == a_zi:
                self.zoom_in()
                return
            if act == a_zo:
                self.zoom_out()
                return
            return

        # Empty area: Grid/Zoom + Add Tracks (v0.0.19.7.19)
        menu = QMenu(self)
        
        # FIXED v0.0.19.7.19: Add Track Options im Context Menu! ✅
        a_add_inst = menu.addAction("🎹 Instrument Track hinzufügen")
        a_add_audio = menu.addAction("🔊 Audio Track hinzufügen")
        a_add_bus = menu.addAction("🎚️ Bus Track hinzufügen")
        menu.addSeparator()

        # v0.0.20.637: Punch In/Out context menu (AP2 Phase 2C)
        punch_menu = menu.addMenu("🎯 Punch In/Out")
        a_punch_toggle = punch_menu.addAction("✅ Punch aktiv" if self.punch_enabled else "☐ Punch aktivieren")
        a_punch_from_loop = punch_menu.addAction("Punch = Loop Region übernehmen")
        a_punch_from_loop.setEnabled(self.loop_enabled)
        a_punch_set_here = punch_menu.addAction(f"Punch In hier setzen (Beat {self._snap(self._x_to_beats(float(event.pos().x()))):.1f})")
        menu.addSeparator()

        a_snap, sub, a_zi, a_zo = add_grid_menu(menu)
        act = menu.exec(event.globalPos())
        
        # Handle Add Track actions
        if act == a_add_inst:
            self.request_add_track.emit("instrument")
            return
        if act == a_add_audio:
            self.request_add_track.emit("audio")
            return
        if act == a_add_bus:
            self.request_add_track.emit("bus")
            return

        # v0.0.20.637: Punch context menu handlers
        if act == a_punch_toggle:
            self.punch_enabled = not self.punch_enabled
            self.punch_region_committed.emit(bool(self.punch_enabled), float(self.punch_in), float(self.punch_out))
            self.update()
            return
        if act == a_punch_from_loop:
            self.punch_in = self.loop_start
            self.punch_out = self.loop_end
            self.punch_enabled = True
            self.punch_region_committed.emit(True, float(self.punch_in), float(self.punch_out))
            self.update()
            return
        if act == a_punch_set_here:
            beat = self._snap(self._x_to_beats(float(event.pos().x())))
            self.punch_in = beat
            self.punch_out = max(beat + self.snap_beats * 4, self.punch_out)
            self.punch_enabled = True
            self.punch_region_committed.emit(True, float(self.punch_in), float(self.punch_out))
            self.update()
            return
        
        if act == a_snap:
            if self.snap_beats and self.snap_beats > 0:
                self.snap_beats = 0.0
            else:
                self.set_snap_division(str(getattr(self.project.ctx.project, "snap_division", "1/16") or "1/16"))
            self.update()
            return
        if act in sub.actions():
            div = act.text()
            try:
                self.project.set_snap_division(div)
            except Exception:
                setattr(self.project.ctx.project, "snap_division", div)
            self.set_snap_division(div)
            self.update()
            return
        if act == a_zi:
            self.zoom_in()
            return
        if act == a_zo:
            self.zoom_out()
            return

    def wheelEvent(self, event):  # noqa: ANN001
        mods = event.modifiers()
        delta = event.angleDelta().y()

        if mods & Qt.KeyboardModifier.AltModifier:
            super().wheelEvent(event)
            return

        if mods & Qt.KeyboardModifier.ShiftModifier:
            factor = 1.1 if delta > 0 else 0.9
            self.track_height = int(max(40, min(140, self.track_height * factor)))
            self._update_minimum_size()
            self.update()
            event.accept()
            return

        factor = 1.1 if delta > 0 else 0.9
        self._zoom_by_factor(factor)
        event.accept()

    def mousePressEvent(self, event):  # noqa: ANN001
        pos = event.position()
        cid = self._clip_at_pos(pos)

        # Right-Click in ruler = draw loop, otherwise let contextMenuEvent handle it
        if event.button() == Qt.MouseButton.RightButton:
            if pos.y() <= self.ruler_height:
                # Right-click in ruler = draw new loop region
                b = self._snap(self._x_to_beats(pos.x()))
                handle = self._hit_loop_handle(pos) if self.loop_enabled else ""
                if handle:
                    self._drag_loop = _DragLoop(mode=handle, origin_beat=b)
                else:
                    self._drag_loop = _DragLoop(mode="new", origin_beat=b)
                    self.loop_enabled = True
                    self.loop_start = b
                    self.loop_end = b + max(self.snap_beats, 1.0)
                self._suppress_next_context_menu = True
                self.update()
                return
            # Below ruler: do NOT intercept — let Qt fire contextMenuEvent normally
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)

            # v0.0.20.176: Arranger Gain/Pan mini handles (audio only)
            try:
                show_micro = bool(is_sel) or (str(getattr(self, "_hover_clip_id", "")) == str(cid))
                self._draw_clip_gain_pan_controls(p, rect, clip, show_handles=bool(show_micro))
            except Exception:
                pass

            # v0.0.20.174: Small per-clip dropdown button (triangle) — click opens the same menu as right-click.
            # We implement this by forwarding a tiny "fake" context menu event to the existing handler.
            if cid:
                try:
                    rect, _clip = self._clip_rect(str(cid))
                    if rect:
                        btn = QRectF(rect.right() - 16, rect.top() + 3, 13, 13)
                        if btn.contains(pos):
                            try:
                                gp = event.globalPosition().toPoint()
                            except Exception:
                                gp = self.mapToGlobal(pos.toPoint())
                            class _FakeCtxEvent:
                                def __init__(self, p, g):
                                    self._p = p
                                    self._g = g
                                def pos(self):
                                    return self._p
                                def globalPos(self):
                                    return self._g
                                def accept(self):
                                    pass
                            self.contextMenuEvent(_FakeCtxEvent(pos.toPoint(), gp))
                            event.accept()
                            return
                except Exception:
                    pass

            # Bitwig-style ruler with two zones:
            # Top strip (0..zoom_band_h): zoom drag
            # Lower area (zoom_band_h..ruler_height): loop editing
            try:
                zoom_band = float(self._ruler_zoom_band_h)
                if pos.y() <= self.ruler_height:
                    if pos.y() <= zoom_band:
                        # === TOP ZONE: Zoom drag ===
                        self._update_zoom_handle_rect(float(pos.x()))
                        self._zoom_handle_visible = True
                        self._zoom_drag_active = True
                        self._zoom_drag_origin_y = float(pos.y())
                        self._zoom_drag_origin_ppb = float(self.pixels_per_beat)
                        self._zoom_anchor_beat = float(pos.x()) / max(1e-9, float(self.pixels_per_beat))
                        bar = self._find_hscrollbar()
                        self._zoom_anchor_view_x = float(pos.x()) - float(bar.value()) if bar is not None else float(pos.x())
                        self._set_override_cursor("magnifier")
                        event.accept()
                        return
                    else:
                        # === LOWER ZONE: Playhead + Loop handles ===
                        # Priority:
                        #   1) If user hits loop handles -> resize loop
                        #   2) Otherwise -> seek/drag PLAYHEAD (DAW-style)
                        handle = self._hit_loop_handle(pos) if self.loop_enabled else ""
                        if handle:
                            b = self._snap(self._x_to_beats(pos.x()))
                            self._drag_loop = _DragLoop(mode=handle, origin_beat=b)
                            self.update()
                            return

                        # v0.0.20.637: Punch handle drag (AP2 Phase 2C)
                        punch_handle = self._hit_punch_handle(pos)
                        if punch_handle:
                            self._drag_punch_handle = punch_handle
                            self.update()
                            return

                        # Seek + start playhead drag
                        self._drag_playhead_active = True
                        self._drag_playhead_snap = not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                        self._set_override_cursor("loop_handle")
                        self._seek_playhead(self._x_to_beats(pos.x()), snap=self._drag_playhead_snap)
                        event.accept()
                        return
            except Exception:
                pass

            # Dragging the red playhead line (anywhere on the canvas)
            try:
                if pos.y() > float(self.ruler_height) and self._near_playhead(pos, threshold_px=4):
                    self._drag_playhead_active = True
                    self._drag_playhead_snap = not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    self._set_override_cursor("loop_handle")
                    self._seek_playhead(self._x_to_beats(pos.x()), snap=self._drag_playhead_snap)
                    event.accept()
                    return
            except Exception:
                pass

            # v0.0.20.640: Comp-Tool — click on take-lane clip to select it
            if not cid:
                try:
                    take_tid, take_clip = self._hit_take_lane_clip(pos)
                    if take_tid and take_clip:
                        ts = getattr(self, '_take_service', None)
                        if ts:
                            take_cid = str(getattr(take_clip, 'id', ''))
                            ts.comp_select_take_at(take_tid, take_cid)
                            self.status_message.emit(
                                f"Comp: Take '{getattr(take_clip, 'label', '?')}' ausgewählt", 2000
                            )
                            self.update()
                            event.accept()
                            return
                except Exception:
                    pass

            # Selection (Shift toggles multi-select)
            if cid:
                # TOOL HANDLING
                # Knife Tool: Split clip at click position
                if self._active_tool == "knife":
                    try:
                        beat = self._snap(self._x_to_beats(pos.x()))
                        result = self.project.split_clip(cid, float(beat))
                        if result:
                            left_id, right_id = result
                            self.selected_clip_ids = {right_id}
                            self.selected_clip_id = right_id
                            self.clip_selected.emit(right_id)
                        self.update()
                    except Exception:
                        pass
                    return
                
                # Erase Tool: Delete clip
                if self._active_tool == "erase":
                    try:
                        self.project.delete_clip(cid)
                        self.selected_clip_ids.discard(cid)
                        if self.selected_clip_id == cid:
                            self.selected_clip_id = ""
                            self.clip_selected.emit("")
                        self.update()
                    except Exception:
                        pass
                    return
                
                # Select Tool: Normal selection behavior
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    if cid in self.selected_clip_ids:
                        self.selected_clip_ids.remove(cid)
                    else:
                        self.selected_clip_ids.add(cid)
                else:
                    # DAW-style: if the user clicks on a clip that is already part
                    # of the current multi-selection, keep the selection intact.
                    # This enables "lasso-select -> drag any selected clip -> move group".
                    if cid not in self.selected_clip_ids:
                        self.selected_clip_ids = {cid}
            else:
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.selected_clip_ids = set()

            self.selected_clip_id = cid
            self.clip_selected.emit(cid)
            self.update()

            # --- Lasso Selection or empty click ---
            # FIXED v0.0.19.7.22: Removed Draw Tool single-click creation!
            # Normal-Drag on empty space = Lasso (better UX!)
            # Double-Click on track = Create clip (see mouseDoubleClickEvent)
            if (not cid) and pos.y() > self.ruler_height:
                trk = self._track_at_y(pos.y())
                mods = event.modifiers()
                
                # Draw Tool is REMOVED! Use Double-Click instead!
                # Old behavior: Single-click with Draw Tool created clip ❌
                # New behavior: Only Double-Click creates clip ✅
                
                # Lasso: Normal-Drag on empty space (default for all tools)
                if not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
                    self._drag_lasso = _DragLasso(
                        start_x=pos.x(),
                        start_y=pos.y(),
                        current_x=pos.x(),
                        current_y=pos.y(),
                        initial_selection=set(self.selected_clip_ids)
                    )
                    if not (mods & Qt.KeyboardModifier.ShiftModifier):
                        self.selected_clip_ids = set()
                    self.update()
                    return


            # v0.0.20.175: Fade handles on arranger clips (audio) — click+drag on the small triangles.
            # Safe/non-destructive: only updates fade_in_beats / fade_out_beats via ProjectService.
            if cid:
                try:
                    rect_f, clip_f = self._clip_rect(cid)
                    mods = event.modifiers()
                    if rect_f and clip_f and str(getattr(clip_f, "kind", "")) == "audio" and str(getattr(self, "_active_tool", "select")) == "select":
                        # Avoid interfering with Ctrl+Drag copy preview / Alt gestures
                        if not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
                            # Fade-in handle (top-left)
                            if self._hit_fade_handle_in(rect_f, pos):
                                self._drag_fade = _DragFade(clip_id=str(cid), which="in", start_x=float(pos.x()))
                                self._set_override_cursor("fade")
                                event.accept()
                                return
                            # Fade-out handle (top-right; does not overlap ▾ dropdown)
                            if self._hit_fade_handle_out(rect_f, pos) and (not self._fade_dropdown_rect(rect_f).contains(pos)):
                                self._drag_fade = _DragFade(clip_id=str(cid), which="out", start_x=float(pos.x()))
                                self._set_override_cursor("fade")
                                event.accept()
                                return
                except Exception:
                    pass
            


            # v0.0.20.176: Gain/Pan mini handles on arranger clips (audio)
            # Safe/non-destructive: updates clip.gain / clip.pan via ProjectService.
            if cid:
                try:
                    rect_gp, clip_gp = self._clip_rect(str(cid))
                    mods = event.modifiers()
                    if rect_gp and clip_gp and str(getattr(clip_gp, "kind", "")) == "audio" and str(getattr(self, "_active_tool", "select")) == "select":
                        # Avoid interfering with Ctrl+Drag copy preview / Alt gestures
                        if not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
                            og = float(getattr(clip_gp, "gain", 1.0) or 1.0)
                            op = float(getattr(clip_gp, "pan", 0.0) or 0.0)
                            if self._hit_gain_handle(rect_gp, pos):
                                self._drag_gainpan = _DragGainPan(
                                    clip_id=str(cid),
                                    which="gain",
                                    start_x=float(pos.x()),
                                    start_y=float(pos.y()),
                                    origin_gain=float(og),
                                    origin_pan=float(op),
                                )
                                self._set_override_cursor("gain")
                                event.accept()
                                return
                            if self._hit_pan_handle(rect_gp, pos):
                                self._drag_gainpan = _DragGainPan(
                                    clip_id=str(cid),
                                    which="pan",
                                    start_x=float(pos.x()),
                                    start_y=float(pos.y()),
                                    origin_gain=float(og),
                                    origin_pan=float(op),
                                )
                                self._set_override_cursor("pan")
                                event.accept()
                                return
                except Exception:
                    pass

            # DnD start
            self._dnd_drag_start = pos
            self._dnd_clip_id = cid

            # v0.0.20.143: Ctrl+Drag = DAW-style COPY PREVIEW (no moving originals).
            # Supports multi-clip lasso copy when the user drags any selected clip.
            if cid and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                try:
                    # Determine group: if the clicked clip is in the current selection, copy the whole selection.
                    group_ids = set(self.selected_clip_ids) if (cid in self.selected_clip_ids and len(self.selected_clip_ids) > 0) else {cid}
                    tracks = self._lane_entries()
                    origins: dict[str, tuple[float, int]] = {}

                    clicked = next((c for c in self._arranger_clips() if str(getattr(c, 'id', '')) == str(cid)), None)
                    if clicked is None:
                        group_ids = {cid}
                        clicked = next((c for c in self._arranger_clips() if str(getattr(c, 'id', '')) == str(cid)), None)

                    if clicked is not None:
                        anchor_track_idx = max(0, int(self._lane_index_for_track_id(getattr(clicked, 'track_id', ''))))
                        for c2 in self._arranger_clips():
                            c2id = str(getattr(c2, 'id', ''))
                            if c2id not in group_ids:
                                continue
                            tidx = max(0, int(self._lane_index_for_track_id(getattr(c2, 'track_id', ''))))
                            origins[c2id] = (float(getattr(c2, 'start_beats', 0.0) or 0.0), int(tidx))

                        beat_mouse = float(self._x_to_beats(pos.x()))
                        dx_beats = float(beat_mouse - float(getattr(clicked, 'start_beats', 0.0) or 0.0))
                        snap_enabled = not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                        self._drag_copy_preview = _DragCopyPreview(
                            anchor_clip_id=str(cid),
                            dx_beats=float(dx_beats),
                            origins=origins,
                            anchor_track_idx=int(anchor_track_idx),
                            cur_anchor_start=float(getattr(clicked, 'start_beats', 0.0) or 0.0),
                            cur_target_track_idx=int(anchor_track_idx),
                            snap_enabled=bool(snap_enabled),
                        )
                        self._drag_is_copy = True
                        self._set_override_cursor('copy')
                        self.update()
                        event.accept()
                        return
                except Exception:
                    # Fallback: do nothing special; continue with normal move.
                    self._drag_copy_preview = None
                    self._drag_is_copy = False
            else:
                self._drag_is_copy = False
                self._drag_copy_preview = None
            
            if cid:
                rect, clip = self._clip_rect(cid)
                if rect and clip:
                    # v0.0.20.361: Alt + Resize Handle = Content Scaling (Bitwig-style)
                    _alt_held = bool(mods & Qt.KeyboardModifier.AltModifier)
                    _shift_held = bool(mods & Qt.KeyboardModifier.ShiftModifier)
                    _hit_right = self._hit_resize_handle_right(rect, pos)
                    _hit_left = self._hit_resize_handle_left(rect, pos)

                    if _alt_held and (_hit_right or _hit_left):
                        _clip_kind = str(getattr(clip, 'kind', 'midi'))
                        _notes = []
                        _origin_stretch = 1.0
                        if _clip_kind == 'midi':
                            _raw = self.project.ctx.project.midi_notes.get(str(cid), [])
                            _notes = [(float(getattr(n, 'start_beats', 0.0)), float(getattr(n, 'length_beats', 0.25))) for n in _raw]
                        else:
                            _origin_stretch = float(getattr(clip, 'stretch', 1.0) or 1.0)
                        self._drag_content_scale = _DragContentScale(
                            clip_id=str(cid),
                            side="right" if _hit_right else "left",
                            clip_kind=_clip_kind,
                            origin_start=float(clip.start_beats),
                            origin_len=float(clip.length_beats),
                            origin_x=pos.x(),
                            origin_offset_beats=float(getattr(clip, "offset_beats", 0.0) or 0.0),
                            origin_offset_seconds=float(getattr(clip, "offset_seconds", 0.0) or 0.0),
                            original_notes=_notes,
                            origin_stretch=_origin_stretch,
                            free_mode=bool(_shift_held),
                        )
                        self._drag_resize_r = None
                        self._drag_resize_l = None
                        self._drag_move = None
                        self._drag_move_multi = None
                        self._set_override_cursor('content_scale')
                        self.update()
                        event.accept()
                        return

                    if self._hit_resize_handle_right(rect, pos):
                        self._drag_resize_r = _DragResizeRight(
                            clip_id=cid,
                            origin_len=float(clip.length_beats),
                            origin_x=pos.x(),
                        )
                        self._drag_resize_l = None
                        self._drag_move = None
                        self._drag_move_multi = None
                    elif self._hit_resize_handle_left(rect, pos):
                        self._drag_resize_l = _DragResizeLeft(
                            clip_id=cid,
                            origin_start=float(clip.start_beats),
                            origin_len=float(clip.length_beats),
                            origin_x=pos.x(),
                            origin_offset_beats=float(getattr(clip, "offset_beats", 0.0) or 0.0),
                            origin_offset_seconds=float(getattr(clip, "offset_seconds", 0.0) or 0.0),
                        )
                        self._drag_resize_r = None
                        self._drag_move = None
                        self._drag_move_multi = None
                    else:
                        beat = self._x_to_beats(pos.x())
                        # If multiple clips are selected and the user drags one of them,
                        # move the whole selection as a group (DAW-style).
                        if cid in self.selected_clip_ids and len(self.selected_clip_ids) > 1:
                            tracks = self._tracks()
                            origins: dict[str, tuple[float, int]] = {}
                            anchor_track_idx = 0
                            for c2 in self._arranger_clips():
                                c2id = str(c2.id)
                                if c2id not in self.selected_clip_ids:
                                    continue
                                tidx = max(0, int(self._lane_index_for_track_id(c2.track_id)))
                                origins[c2id] = (float(getattr(c2, "start_beats", 0.0) or 0.0), int(tidx))
                                if c2id == str(cid):
                                    anchor_track_idx = int(tidx)
                            self._drag_move_multi = _DragMoveMulti(
                                anchor_clip_id=str(cid),
                                dx_beats=float(beat - float(clip.start_beats)),
                                origins=origins,
                                anchor_track_idx=int(anchor_track_idx),
                            )
                            self._drag_move = None
                        else:
                            self._drag_move = _DragMove(clip_id=cid, dx_beats=beat - float(clip.start_beats))
                            self._drag_move_multi = None
                        self._drag_resize_r = None
                        self._drag_resize_l = None


            super().mousePressEvent(event)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: ANN001
        pos = event.position()

        # v0.0.20.143: Playhead drag (red line)
        if getattr(self, '_drag_playhead_active', False):
            try:
                snap = bool(getattr(self, '_drag_playhead_snap', True)) and not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._seek_playhead(self._x_to_beats(pos.x()), snap=snap)
                event.accept()
                return
            except Exception:
                pass

        # v0.0.20.143: Ctrl+Drag copy preview (no project mutations during drag)
        if self._drag_copy_preview is not None:
            try:
                d = self._drag_copy_preview
                beat_mouse = float(self._x_to_beats(pos.x()))
                anchor_new = float(beat_mouse - float(d.dx_beats))
                snap = bool(d.snap_enabled) and not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if snap:
                    anchor_new = float(self._snap(anchor_new))
                else:
                    anchor_new = max(0.0, float(anchor_new))

                tracks = self._tracks()
                trk = self._track_at_y(pos.y())
                target_idx = int(d.anchor_track_idx)
                if trk is not None:
                    target_idx = max(0, int(self._lane_index_for_track_id(getattr(trk, 'id', '')))) if trk is not None else int(d.anchor_track_idx)

                d.cur_anchor_start = float(anchor_new)
                d.cur_target_track_idx = int(target_idx)
                self._set_override_cursor('copy')
                self.update()
                event.accept()
                return
            except Exception:
                pass

        # v0.0.20.175: Fade handle drag (audio clips) — updates clip.fade_in_beats / fade_out_beats.
        if self._drag_fade is not None:
            try:
                d = self._drag_fade
                rect_f, clip_f = self._clip_rect(str(d.clip_id))
                if not rect_f or not clip_f:
                    return
                if str(getattr(clip_f, "kind", "")) != "audio":
                    return
        
                # compute beats from mouse position
                ppb = float(self.pixels_per_beat) if float(self.pixels_per_beat) > 1e-6 else 80.0
                length_beats = float(getattr(clip_f, "length_beats", 4.0) or 4.0)
                max_fade = max(0.0, length_beats * 0.5)
        
                if str(d.which) == "in":
                    beats = (float(pos.x()) - float(rect_f.left())) / ppb
                else:
                    beats = (float(rect_f.right()) - float(pos.x())) / ppb
        
                beats = max(0.0, min(float(max_fade), float(beats)))
        
                # Hold SHIFT to snap fades to the current grid (otherwise smooth)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    beats = float(self._snap(float(beats)))
        
                if str(d.which) == "in":
                    self.project.update_audio_clip_params(str(d.clip_id), fade_in_beats=float(beats))
                else:
                    self.project.update_audio_clip_params(str(d.clip_id), fade_out_beats=float(beats))
        
                self.update()
                event.accept()
                return
            except Exception:
                pass
        


        # v0.0.20.176: Gain/Pan handle drag (audio clips) — updates clip.gain / clip.pan.
        if self._drag_gainpan is not None:
            try:
                d = self._drag_gainpan
                rect_gp, clip_gp = self._clip_rect(str(getattr(d, 'clip_id', '')))
                if not rect_gp or not clip_gp:
                    return
                if str(getattr(clip_gp, 'kind', '')) != 'audio':
                    return

                mods = event.modifiers()
                shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

                def _fmt_pan(val: float) -> str:
                    v = float(max(-1.0, min(1.0, val)))
                    if abs(v) < 0.01:
                        return 'C'
                    side = 'L' if v < 0 else 'R'
                    return f"{side} {abs(v)*100:.0f}%"

                if str(getattr(d, 'which', '')) == 'gain':
                    # Default: vertical = gain. Hold SHIFT: horizontal = pan.
                    if shift:
                        dx = float(pos.x()) - float(getattr(d, 'start_x', 0.0))
                        new_pan = float(getattr(d, 'origin_pan', 0.0)) + (dx / 120.0)
                        new_pan = max(-1.0, min(1.0, float(new_pan)))
                        self.project.update_audio_clip_params(str(d.clip_id), pan=float(new_pan))
                        try:
                            self.status_message.emit(f"Clip Pan: {_fmt_pan(float(new_pan))}", 700)
                        except Exception:
                            pass
                        self._set_override_cursor('pan')
                    else:
                        dy = float(pos.y()) - float(getattr(d, 'start_y', 0.0))
                        og = float(getattr(d, 'origin_gain', 1.0) or 1.0)
                        # dB mapping: 5px ≈ 1dB
                        import math
                        db0 = 20.0 * math.log10(max(1e-6, og))
                        new_db = float(db0) + (-float(dy) * 0.2)
                        new_db = max(-120.0, min(12.0, float(new_db)))
                        new_gain = float(10.0 ** (float(new_db) / 20.0))
                        new_gain = max(0.0, min(4.0, float(new_gain)))
                        self.project.update_audio_clip_params(str(d.clip_id), gain=float(new_gain))
                        try:
                            self.status_message.emit(f"Clip Gain: {new_db:+.1f} dB", 700)
                        except Exception:
                            pass
                        self._set_override_cursor('gain')

                    self.update()
                    event.accept()
                    return

                # Pan handle: horizontal pan, SHIFT = fine (slower)
                dx = float(pos.x()) - float(getattr(d, 'start_x', 0.0))
                denom = 360.0 if shift else 120.0
                new_pan = float(getattr(d, 'origin_pan', 0.0)) + (dx / float(denom))
                new_pan = max(-1.0, min(1.0, float(new_pan)))
                self.project.update_audio_clip_params(str(d.clip_id), pan=float(new_pan))
                try:
                    self.status_message.emit(f"Clip Pan: {_fmt_pan(float(new_pan))}", 700)
                except Exception:
                    pass
                self._set_override_cursor('pan')
                self.update()
                event.accept()
                return
            except Exception:
                pass

        # Hover feedback: thin zoom strip at top of ruler shows magnifier,
        # lower ruler area shows normal or loop-handle cursor.
        try:
            if not getattr(self, '_zoom_drag_active', False) and event.buttons() == Qt.MouseButton.NoButton:
                zoom_band = float(self._ruler_zoom_band_h)
                in_zoom_strip = bool(pos.y() <= zoom_band)
                in_loop_zone = bool(zoom_band < pos.y() <= self.ruler_height)
                
                if in_zoom_strip:
                    # Top zoom strip → magnifier cursor
                    self._update_zoom_handle_rect(float(pos.x()))
                    if not getattr(self, '_zoom_handle_visible', False):
                        self._zoom_handle_visible = True
                        self.update()
                    self._hover_zoom_handle = True
                    self._set_override_cursor("magnifier")
                elif in_loop_zone:
                    # Lower ruler area → check loop handles
                    if self._zoom_handle_visible:
                        self._zoom_handle_visible = False
                        self.update()
                    self._hover_zoom_handle = False
                    loop_handle = self._hit_loop_handle(pos) if self.loop_enabled else ""
                    if loop_handle:
                        self._set_override_cursor("loop_handle")
                    elif self._hit_punch_handle(pos):
                        self._set_override_cursor("loop_handle")  # reuse same resize cursor
                    else:
                        self._clear_override_cursor()
                else:
                    # Below ruler
                    if self._zoom_handle_visible:
                        self._zoom_handle_visible = False
                        self.update()
                    if self._hover_zoom_handle:
                        self._hover_zoom_handle = False
                    self._clear_override_cursor()
        except Exception:
            pass

        # Zoom handle drag (magnifier)
        if getattr(self, '_zoom_drag_active', False):
            try:
                dy = float(pos.y()) - float(self._zoom_drag_origin_y)
                # Up = zoom in, Down = zoom out
                factor = 1.0 + (-dy / 160.0)
                factor = max(0.25, min(4.0, factor))
                new_ppb = max(20.0, min(320.0, float(self._zoom_drag_origin_ppb) * float(factor)))
                self._apply_ppb_anchored(float(new_ppb))
                self._sync_gl_overlay()
                self.update()
                self.zoom_changed.emit(float(self.pixels_per_beat))
                event.accept()
                return
            except Exception:
                pass
        
        # FIXED v0.0.19.7.5: Update cursor if Ctrl is released during drag
        if self._drag_is_copy and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # User released Ctrl during drag - cancel copy mode
            self._drag_is_copy = False
            self._drag_copy_source_clip_id = ""
            self._drag_copy_preview = None
            self._clear_override_cursor()
            # print(f"[ArrangerCanvas.mouseMoveEvent] Ctrl released - copy mode cancelled, cursor reset")

        # Lasso selection - update rectangle
        if self._drag_lasso is not None:
            self._drag_lasso.current_x = pos.x()
            self._drag_lasso.current_y = pos.y()
            
            # Find all clips in lasso rectangle
            lasso_rect = self._get_lasso_rect()
            clips_in_lasso = set()
            
            for clip in self._arranger_clips():
                clip_rect, _c = self._clip_rect(str(clip.id))
                if clip_rect and lasso_rect.intersects(clip_rect):
                    clips_in_lasso.add(str(clip.id))
            
            # Update selection based on Shift modifier
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Lasso: Add to initial selection
                self.selected_clip_ids = self._drag_lasso.initial_selection | clips_in_lasso
            else:
                # Normal Lasso: Replace selection
                self.selected_clip_ids = clips_in_lasso
            
            self.update()
            return

        if self._drag_new_clip is not None:
            b = self._snap(self._x_to_beats(pos.x()))
            self._drag_new_clip.cur_beat = float(b)
            self.update()
            return

        if self._drag_loop is not None:
            b = self._snap(self._x_to_beats(pos.x()))
            if self._drag_loop.mode == "new":
                s = min(self._drag_loop.origin_beat, b)
                e = max(self._drag_loop.origin_beat, b)
                self.loop_start = s
                self.loop_end = max(s + self.snap_beats, e)
                self.loop_enabled = True
            elif self._drag_loop.mode == "start":
                self.loop_start = min(b, self.loop_end - self.snap_beats)
            elif self._drag_loop.mode == "end":
                self.loop_end = max(b, self.loop_start + self.snap_beats)
            self.update()
            return

        # v0.0.20.637: Punch handle drag (AP2 Phase 2C)
        if self._drag_punch_handle:
            b = self._snap(self._x_to_beats(pos.x()))
            if self._drag_punch_handle == "in":
                self.punch_in = min(b, self.punch_out - self.snap_beats)
            elif self._drag_punch_handle == "out":
                self.punch_out = max(b, self.punch_in + self.snap_beats)
            self.update()
            return

        # v0.0.20.361: Content Scale drag (Alt+Resize)
        if self._drag_content_scale is not None:
            d = self._drag_content_scale
            _rect, clip = self._clip_rect(d.clip_id)
            if not clip:
                return
            dx = pos.x() - d.origin_x
            dbeats = dx / max(1e-9, self.pixels_per_beat)
            d.free_mode = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if d.side == "right":
                new_len = max(self.snap_beats, d.origin_len + dbeats)
                if not d.free_mode:
                    g = float(self.snap_beats)
                    if g > 0:
                        new_len = max(g, round(new_len / g) * g)
                clip.length_beats = float(new_len)
            else:
                new_start = d.origin_start + dbeats
                if not d.free_mode:
                    new_start = self._snap(new_start)
                delta = float(new_start) - float(d.origin_start)
                new_len = float(d.origin_len) - delta
                min_len = max(self.snap_beats, 0.25)
                if new_len < min_len:
                    new_len = min_len
                    new_start = float(d.origin_start) + (float(d.origin_len) - new_len)
                clip.start_beats = float(new_start)
                clip.length_beats = float(new_len)

            try:
                keys_to_remove = [k for k in self._clip_pixmap_cache if k.startswith(f"{d.clip_id}:")]
                for k in keys_to_remove:
                    del self._clip_pixmap_cache[k]
            except Exception:
                pass
            self.update()
            return

        if self._drag_resize_r is not None:
            _rect, clip = self._clip_rect(self._drag_resize_r.clip_id)
            if not clip:
                return
            dx = pos.x() - self._drag_resize_r.origin_x
            dbeats = dx / self.pixels_per_beat
            new_len = max(self.snap_beats, self._drag_resize_r.origin_len + dbeats)
            self.project.resize_clip(self._drag_resize_r.clip_id, new_len, snap_beats=self.snap_beats)
            self._mark_auto_loop_end_for_clip(self._drag_resize_r.clip_id)
            return

        if self._drag_resize_l is not None:
            _rect, clip = self._clip_rect(self._drag_resize_l.clip_id)
            if not clip:
                return
            dx = pos.x() - self._drag_resize_l.origin_x
            dbeats = dx / self.pixels_per_beat

            new_start = self._snap(self._drag_resize_l.origin_start + dbeats)
            delta = float(new_start) - float(self._drag_resize_l.origin_start)
            new_len = float(self._drag_resize_l.origin_len) - delta

            min_len = max(self.snap_beats, 0.25)
            if new_len < min_len:
                new_len = min_len
                # recompute start to keep right edge stable
                new_start = float(self._drag_resize_l.origin_start) + (float(self._drag_resize_l.origin_len) - new_len)
                new_start = self._snap(new_start)
                delta = float(new_start) - float(self._drag_resize_l.origin_start)

            # Content offset (beats + seconds)
            off_beats = max(0.0, float(self._drag_resize_l.origin_offset_beats) + delta)
            off_secs = max(0.0, float(self._drag_resize_l.origin_offset_seconds) + self._beats_to_seconds(delta))
            self.project.trim_clip_left(self._drag_resize_l.clip_id, new_start, new_len, off_beats, off_secs, snap_beats=self.snap_beats)
            self._mark_auto_loop_end_for_clip(self._drag_resize_l.clip_id)
            return

        if self._drag_move_multi is not None:
            d = self._drag_move_multi
            # anchor clip must still exist
            _rect, clip = self._clip_rect(d.anchor_clip_id)
            if not clip:
                return
            # Compute new anchor start (snap on anchor only).
            anchor_new = self._snap(self._x_to_beats(pos.x()) - float(d.dx_beats))
            anchor_origin = float(d.origins.get(str(d.anchor_clip_id), (float(getattr(clip, 'start_beats', 0.0) or 0.0), d.anchor_track_idx))[0])
            delta_beats = float(anchor_new) - float(anchor_origin)
            # Track delta derived from where the mouse is currently hovering.
            tracks = self._tracks()
            trk = self._track_at_y(pos.y())
            if trk is not None:
                try:
                    target_idx = max(0, int(self._lane_index_for_track_id(getattr(trk, 'id', '')))) if trk is not None else d.anchor_track_idx
                except Exception:
                    target_idx = d.anchor_track_idx
            else:
                target_idx = d.anchor_track_idx
            delta_idx = int(target_idx) - int(d.anchor_track_idx)
            # Move each selected clip preserving relative offsets.
            for cid, (o_start, o_tidx) in d.origins.items():
                new_start = max(0.0, float(o_start) + float(delta_beats))
                # Avoid per-clip re-snapping: snap is anchored already.
                self.project.move_clip(str(cid), float(new_start), snap_beats=None)
                # Vertical track move (optional): keep relative track positions.
                new_tidx = int(o_tidx) + int(delta_idx)
                if tracks:
                    new_tidx = max(0, min(new_tidx, len(tracks) - 1))
                    new_track_id = str(tracks[new_tidx].id)
                    try:
                        # Only move if different
                        cobj = next((c for c in self._arranger_clips() if str(c.id) == str(cid)), None)
                        if cobj and str(getattr(cobj, 'track_id', '')) != new_track_id:
                            # v0.0.20.355 bugfix: Don't reassign track inside collapsed group.
                            if not self._is_same_collapsed_group(str(getattr(cobj, 'track_id', '')), new_track_id):
                                self.project.move_clip_track(str(cid), new_track_id)
                    except Exception:
                        pass
                self._mark_auto_loop_end_for_clip(str(cid))
            return

        if self._drag_move is not None:
            _rect, clip = self._clip_rect(self._drag_move.clip_id)
            if not clip:
                return
            beat = self._snap(self._x_to_beats(pos.x()) - self._drag_move.dx_beats)
            self.project.move_clip(self._drag_move.clip_id, beat, snap_beats=self.snap_beats)

            trk = self._track_at_y(pos.y())
            if trk and trk.id != clip.track_id:
                # v0.0.20.355 bugfix: Don't reassign track when dragging inside a collapsed group.
                # _track_at_y returns members[0] for collapsed groups, which would silently
                # move clips from snare/hi-hat/etc to the first member (kick).
                if not self._is_same_collapsed_group(str(clip.track_id), str(trk.id)):
                    self.project.move_clip_track(self._drag_move.clip_id, trk.id)
            self._mark_auto_loop_end_for_clip(self._drag_move.clip_id)
            return

        # v0.0.20.584: Throttled hover detection (was: every pixel → now: max 20fps).
        # Merges two separate _clip_at_pos calls into one, cutting iteration cost in half.
        import time as _time_mod
        _hover_now = _time_mod.monotonic()
        if (_hover_now - getattr(self, '_last_hover_time', 0.0)) >= 0.05:
            self._last_hover_time = _hover_now

            # v0.0.20.174: Hover tracking for the small per-clip dropdown button
            try:
                hover_cid = str(self._clip_at_pos(pos) or "")
                if hover_cid != str(getattr(self, "_hover_clip_id", "")):
                    self._hover_clip_id = hover_cid
                    self.update()
            except Exception:
                hover_cid = ""

            # v0.0.20.176: Hover cursor for clip micro handles (Fade/Gain/Pan)
            try:
                if event.buttons() == Qt.MouseButton.NoButton and (not getattr(self, "_zoom_drag_active", False)):
                    kind = ""
                    if hover_cid:
                        rect_h, clip_h = self._clip_rect(str(hover_cid))
                        if rect_h and clip_h and str(getattr(clip_h, "kind", "")) == "audio":
                            try:
                                if self._hit_fade_handle_in(rect_h, pos):
                                    kind = "fade"
                                elif self._hit_fade_handle_out(rect_h, pos) and (not self._fade_dropdown_rect(rect_h).contains(pos)):
                                    kind = "fade"
                                elif self._hit_gain_handle(rect_h, pos):
                                    kind = "gain"
                                elif self._hit_pan_handle(rect_h, pos):
                                    kind = "pan"
                            except Exception:
                                kind = ""

                    if kind:
                        self._set_override_cursor(kind)
                    else:
                        if str(getattr(self, "_cursor_override_active", "")) in ("fade", "gain", "pan"):
                            self._clear_override_cursor()
            except Exception:
                pass


        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        # Zoom drag release
        if getattr(self, '_zoom_drag_active', False):
            self._zoom_drag_active = False
            try:
                pos = event.position()
                if pos.y() <= float(self._ruler_zoom_band_h):
                    self._set_override_cursor("magnifier")
                else:
                    self._clear_override_cursor()
            except Exception:
                pass
            event.accept()
            return

        # v0.0.20.143: Playhead drag release
        if getattr(self, '_drag_playhead_active', False):
            self._drag_playhead_active = False
            try:
                self._clear_override_cursor()
            except Exception:
                pass
            event.accept()
            return



        # v0.0.20.175: Fade drag release
        if self._drag_fade is not None:
            self._drag_fade = None
            try:
                self._clear_override_cursor()
            except Exception:
                pass
            event.accept()
            return

        # v0.0.20.176: Gain/Pan drag release
        if self._drag_gainpan is not None:
            self._drag_gainpan = None
            try:
                self._clear_override_cursor()
            except Exception:
                pass
            event.accept()
            return

        # v0.0.20.361: Content Scale commit (Alt+Drag resize)
        if self._drag_content_scale is not None:
            try:
                d = self._drag_content_scale
                self._drag_content_scale = None
                clip = next((c for c in self._arranger_clips() if str(c.id) == str(d.clip_id)), None)
                if clip:
                    new_len = float(clip.length_beats)
                    old_len = float(d.origin_len)
                    if old_len > 1e-9 and abs(new_len - old_len) > 1e-9:
                        scale_factor = new_len / old_len

                        if d.clip_kind == 'midi' and d.original_notes:
                            # MIDI: scale note positions + durations
                            self.project.scale_clip_content(str(d.clip_id), scale_factor, d.original_notes)
                            try:
                                mode = "Free" if d.free_mode else "Grid"
                                self.status_message.emit(f"Content Scaling ×{scale_factor:.2f} ({mode}) — {len(d.original_notes)} Noten skaliert", 3000)
                            except Exception:
                                pass
                        else:
                            # Audio: update clip.stretch proportionally
                            new_stretch = float(d.origin_stretch) * scale_factor
                            clip.stretch = max(0.1, min(10.0, new_stretch))
                            try:
                                mode = "Free" if d.free_mode else "Grid"
                                self.status_message.emit(f"Audio Scaling ×{scale_factor:.2f} ({mode}) — stretch={clip.stretch:.2f}", 3000)
                            except Exception:
                                pass

                # Invalidate pixmap cache so the clip redraws with new content
                try:
                    keys_to_remove = [k for k in self._clip_pixmap_cache if k.startswith(f"{d.clip_id}:")]
                    for k in keys_to_remove:
                        del self._clip_pixmap_cache[k]
                except Exception:
                    pass

                try:
                    self.project._emit_updated()
                except Exception:
                    pass
                self.update()
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                try:
                    self._clear_override_cursor()
                except Exception:
                    pass
            event.accept()
            return



        # v0.0.20.143: Ctrl+Drag copy preview commit
        if self._drag_copy_preview is not None:
            try:
                from pydaw.model.project import new_id

                d = self._drag_copy_preview
                self._drag_copy_preview = None

                tracks = self._tracks()
                anchor_origin = float(d.origins.get(str(d.anchor_clip_id), (0.0, int(d.anchor_track_idx)))[0])
                delta_beats = float(d.cur_anchor_start) - float(anchor_origin)
                delta_tracks = int(d.cur_target_track_idx) - int(d.anchor_track_idx)

                # Batch build to avoid GUI freeze
                new_clips = []
                new_ids: list[str] = []

                for src_id, (orig_start, orig_tidx) in (d.origins or {}).items():
                    src = next((c for c in self._arranger_clips() if str(getattr(c, 'id', '')) == str(src_id)), None)
                    if src is None:
                        continue

                    new_start = max(0.0, float(orig_start) + float(delta_beats))
                    nt = int(orig_tidx) + int(delta_tracks)
                    src_track_id = str(getattr(src, 'track_id', ''))
                    if tracks:
                        nt = max(0, min(int(nt), int(len(tracks) - 1)))
                        new_track_id = str(getattr(tracks[nt], 'id', src_track_id))
                    else:
                        new_track_id = src_track_id
                    # v0.0.20.355 bugfix: When copying inside a collapsed group,
                    # keep the clip on its original track (don't move to members[0]).
                    if self._is_same_collapsed_group(src_track_id, new_track_id):
                        new_track_id = src_track_id

                    dup = copy.deepcopy(src)
                    dup.id = new_id('clip')
                    dup.start_beats = float(new_start)
                    dup.track_id = str(new_track_id)
                    # Avoid tying the new clip into the old group by default.
                    try:
                        dup.group_id = ""
                    except Exception:
                        pass
                    try:
                        base_label = str(getattr(dup, 'label', '') or '')
                        if base_label and (not base_label.endswith(' Copy')):
                            dup.label = base_label + ' Copy'
                    except Exception:
                        pass

                    new_clips.append(dup)
                    new_ids.append(str(getattr(dup, 'id', '')))

                    # MIDI notes: bulk deepcopy
                    if str(getattr(src, 'kind', '')) == 'midi':
                        try:
                            self.project.ctx.project.midi_notes[str(dup.id)] = copy.deepcopy(
                                self.project.ctx.project.midi_notes.get(str(getattr(src, 'id', '')), [])
                            )
                        except Exception:
                            self.project.ctx.project.midi_notes[str(dup.id)] = []

                if new_clips:
                    try:
                        self.project.ctx.project.clips.extend(new_clips)
                    except Exception:
                        for c in new_clips:
                            try:
                                self.project.ctx.project.clips.append(c)
                            except Exception:
                                pass

                    # Select the new group
                    try:
                        self.selected_clip_ids = set(new_ids)
                        self.selected_clip_id = str(new_ids[-1]) if new_ids else ""
                        self.clip_selected.emit(self.selected_clip_id)
                    except Exception:
                        pass

                    try:
                        self.project._emit_updated()
                    except Exception:
                        try:
                            self.project.project_updated.emit()
                        except Exception:
                            pass

                    try:
                        self.status_message.emit(f"{len(new_ids)} Clip(s) kopiert (Strg+Drag)", 2000)
                    except Exception:
                        pass

            finally:
                # reset cursor + flags
                try:
                    self._clear_override_cursor()
                except Exception:
                    pass
                self._drag_is_copy = False
            event.accept()
            return

        # Lasso selection - finalize
        if self._drag_lasso is not None:
            # Selection is already updated in mouseMoveEvent
            # Just clean up and emit signal if needed
            if self.selected_clip_ids:
                # Set selected_clip_id to first in set (for single-clip context)
                self.selected_clip_id = next(iter(self.selected_clip_ids)) if self.selected_clip_ids else ""
                self.clip_selected.emit(self.selected_clip_id)
            self._drag_lasso = None
            self.update()
            return

        if self._drag_new_clip is not None:
            try:
                d = self._drag_new_clip
                start = float(min(d.start_beat, d.cur_beat))
                end = float(max(d.start_beat, d.cur_beat))
                length = float(end - start)

                # If the user just clicked (tiny drag), create one bar by default.
                if length < float(self.snap_beats) * 1.5:
                    length = float(self._beats_per_bar())
                length = max(float(self.snap_beats), float(self._snap(length)))

                trk = next((t for t in self.project.ctx.project.tracks if t.id == str(d.track_id)), None)
                if trk and str(getattr(trk, "kind", "audio")) == "audio":
                    # On audio tracks we import an audio file at the position instead of creating a MIDI clip.
                    self.request_import_audio.emit(str(d.track_id), float(start))
                    self.update()
                    return

                new_id = self.project.add_midi_clip_at(d.track_id, start_beats=start, length_beats=length)  # label auto-generated!
                self.selected_clip_ids = {new_id}
                self.selected_clip_id = new_id
                self.clip_selected.emit(new_id)
                self._mark_auto_loop_end_for_clip(new_id)
                self.update()
                # Open the created clip immediately.
                self.clip_activated.emit(new_id)
            finally:
                self._drag_new_clip = None
            return

        if self._drag_loop is not None:
            self._drag_loop = None
            self.loop_region_committed.emit(bool(self.loop_enabled), float(self.loop_start), float(self.loop_end))
            self.update()
            return

        # v0.0.20.637: Punch handle release (AP2 Phase 2C)
        if self._drag_punch_handle:
            self._drag_punch_handle = ""
            self.punch_region_committed.emit(bool(self.punch_enabled), float(self.punch_in), float(self.punch_out))
            self.update()
            return

        self._commit_auto_loop_end()
        
        # FIXED v0.0.20.98: Ctrl+Drag = keep original, create COPY at drop position
        if self._drag_is_copy and self._drag_copy_source_clip_id and self._drag_move:
            try:
                import copy as copy_mod
                moved_clip = next((c for c in self._arranger_clips() 
                                 if c.id == self._drag_move.clip_id), None)
                
                if moved_clip:
                    # Save the drop position (where the clip is NOW after dragging)
                    drop_start = float(moved_clip.start_beats)
                    drop_track = str(moved_clip.track_id)
                    
                    # Move the original clip BACK to where it was before drag
                    orig_start = getattr(self, '_drag_copy_original_start', drop_start)
                    orig_track = getattr(self, '_drag_copy_original_track', drop_track)
                    self.project.move_clip(moved_clip.id, orig_start, snap_beats=0)
                    if str(moved_clip.track_id) != orig_track and orig_track:
                        self.project.move_clip_track(moved_clip.id, orig_track)
                    
                    # Generate label
                    original_label = str(getattr(moved_clip, "label", ""))
                    new_label = original_label if original_label.endswith(" Copy") else (original_label + " Copy")
                    
                    # Create copy at DROP position
                    new_id = None
                    if moved_clip.kind == "midi":
                        new_id = self.project.add_midi_clip_at(
                            drop_track, start_beats=drop_start,
                            length_beats=float(moved_clip.length_beats), label=new_label
                        )
                        notes = self.project.ctx.project.midi_notes.get(moved_clip.id, [])
                        self.project.ctx.project.midi_notes[new_id] = [copy_mod.deepcopy(n) for n in notes]
                        self.project._emit_updated()
                    elif moved_clip.kind == "audio":
                        audio_path = str(getattr(moved_clip, "source_path", ""))
                        if audio_path:
                            new_id = self.project.add_audio_clip_from_file_at(
                                drop_track, audio_path, start_beats=drop_start
                            )
                            if new_id:
                                new_c = next((c for c in self._arranger_clips() if c.id == new_id), None)
                                if new_c:
                                    new_c.label = new_label
                    
                    if new_id:
                        self.selected_clip_ids = {new_id}
                        self.selected_clip_id = new_id
                        self.clip_selected.emit(new_id)
                        self.status_message.emit("Clip kopiert (Strg+Drag)", 2000)

                    # v0.0.20.442: Copy automation breakpoints from source range to drop position
                    try:
                        am = getattr(self, '_automation_manager', None)
                        if am is None:
                            # Try finding it through services
                            w = self
                            for _ in range(10):
                                w = getattr(w, 'parent', None) or (w.parentWidget() if hasattr(w, 'parentWidget') else None)
                                if w is None:
                                    break
                                svc = getattr(w, 'services', None)
                                if svc:
                                    am = getattr(svc, 'automation_manager', None)
                                    break
                        if am is not None and moved_clip:
                            src_start = float(orig_start)
                            src_end = src_start + float(moved_clip.length_beats)
                            am.copy_automation_range(str(drop_track), src_start, src_end, drop_start)
                    except Exception:
                        pass
                    
            except Exception:
                import traceback
                traceback.print_exc()
        
        # Reset copy flags and cursor
        if self._drag_is_copy:
            # Reset cursor back to normal ✅
            self._clear_override_cursor()
        
        self._drag_is_copy = False
        self._drag_copy_source_clip_id = ""

        self._drag_move = None
        self._drag_move_multi = None
        self._drag_resize_r = None
        self._drag_resize_l = None
        self._drag_content_scale = None
        self._dnd_drag_start = None
        self._dnd_clip_id = ""

        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        """Ensure we don't leave the magnifier cursor stuck when leaving the widget."""
        try:
            self._hover_zoom_handle = False
            self._zoom_handle_visible = False
            # v0.0.20.174: hide per-clip dropdown when leaving widget
            self._hover_clip_id = ""
            self._clear_override_cursor()
            self.update()
        except Exception:
            pass
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        """Double click handling.

        IMPORTANT: Do not let Python exceptions escape into Qt. Depending on the
        PyQt6 configuration, uncaught exceptions inside event handlers/slots can
        trigger a Qt fatal error (SIGABRT).
        """
        try:
            pos = event.position()
            # Double-click in zoom strip -> reset zoom
            try:
                if pos.y() <= float(self._ruler_zoom_band_h):
                    self.pixels_per_beat = float(getattr(self, "_default_pixels_per_beat", 80.0) or 80.0)
                    self._update_minimum_size()
                    self._sync_gl_overlay()
                    self.update()
                    self.zoom_changed.emit(float(self.pixels_per_beat))
                    event.accept()
                    return
            except Exception:
                pass

            cid = self._clip_at_pos(pos)
            if cid:
                self.clip_activated.emit(cid)
                super().mouseDoubleClickEvent(event)
                return

            # Double-click empty space -> create a 1-bar clip on that track (Region-first workflow).
            if pos.y() > self.ruler_height:
                trk = self._track_at_y(pos.y())
                if trk and str(getattr(trk, "kind", "")) != "master":
                    start = float(self._snap(self._x_to_beats(pos.x())))
                    length = float(self._beats_per_bar())

                    if str(getattr(trk, "kind", "audio")) == "instrument":
                        new_id = self.project.add_midi_clip_at(
                            str(trk.id), start_beats=start, length_beats=length
                        )  # label auto-generated!
                        self.selected_clip_ids = {new_id}
                        self.selected_clip_id = new_id
                        self.clip_selected.emit(new_id)
                        self._mark_auto_loop_end_for_clip(new_id)
                        self.update()
                        # Open immediately (PianoRoll)
                        self.clip_activated.emit(new_id)
                    else:
                        # audio/bus: create placeholder clip (no import dialog)
                        new_id = self.project.add_audio_clip_placeholder_at(
                            str(trk.id), start_beats=start, length_beats=length, label="Audio Clip"
                        )
                        self.selected_clip_ids = {new_id}
                        self.selected_clip_id = new_id
                        self.clip_selected.emit(new_id)
                        self._mark_auto_loop_end_for_clip(new_id)
                        self.update()
        except Exception:
            # swallow: safety first (prevent SIGABRT)
            pass

        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):  # noqa: ANN001
        """Handle keyboard shortcuts."""
        
        # Space: Play/Pause toggle (DAW standard!)
        if event.key() == Qt.Key.Key_Space:
            try:
                if self.transport is not None:
                    self.transport.toggle_play()
            except Exception:
                pass
            event.accept()
            return
        
        # TOOL SHORTCUTS (Pro-DAW-Style)
        # V: Select Tool
        if event.key() == Qt.Key.Key_V:
            self.set_tool("select")
            event.accept()
            return
        
        # K: Knife Tool (split)
        if event.key() == Qt.Key.Key_K:
            self.set_tool("knife")
            event.accept()
            return
        
        # D: Draw Tool
        if event.key() == Qt.Key.Key_D:
            self.set_tool("draw")
            event.accept()
            return
        
        # E: Erase Tool
        if event.key() == Qt.Key.Key_E:
            self.set_tool("erase")
            event.accept()
            return

# Ctrl+D: Duplicate selected clips
        if event.key() == Qt.Key.Key_D and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.selected_clip_ids:
                try:
                    for clip_id in list(self.selected_clip_ids):
                        self.project.duplicate_clip(clip_id)
                    self.update()
                    event.accept()
                    return
                except Exception:
                    pass
        
        # Delete key: Delete selected clips
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            if self.selected_clip_ids:
                try:
                    for clip_id in list(self.selected_clip_ids):
                        self.project.delete_clip(clip_id)
                    self.selected_clip_ids = set()
                    self.selected_clip_id = ""
                    self.clip_selected.emit("")
                    self.update()
                    event.accept()
                    return
                except Exception:
                    pass
        
        # Ctrl+A: Select all clips
        if event.key() == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            try:
                self.selected_clip_ids = {str(c.id) for c in self._arranger_clips()}
                if self.selected_clip_ids:
                    self.selected_clip_id = next(iter(self.selected_clip_ids))
                    self.clip_selected.emit(self.selected_clip_id)
                self.update()
                event.accept()
                return
            except Exception:
                pass
        
        # NEW in v0.0.19.7.0: Standard DAW shortcuts via Keyboard Handler
        # (Strg+C/V/X, ESC, Undo/Redo placeholders)
        # print(f"[ArrangerCanvas] Calling keyboard_handler with key={event.key()}")
        if self.keyboard_handler.handle_key_press(event, self.selected_clip_ids, self.selected_clip_id):
            event.accept()
            return
        
        super().keyPressEvent(event)
    
    def _on_keyboard_status(self, message: str, timeout_ms: int) -> None:
        """Forward keyboard handler status messages."""
        # print(f"[ArrangerCanvas._on_keyboard_status] {message}")
        self.status_message.emit(message, timeout_ms)
    
    def _export_midi_clip(self, clip_id: str) -> None:
        """FIXED v0.0.19.7.15: Export MIDI Clip to .mid file."""
        from PySide6.QtWidgets import QFileDialog
        from pydaw.audio.midi_export import export_midi_clip
        
        # Get clip
        clip = next((c for c in self._arranger_clips() if c.id == clip_id), None)
        if not clip or getattr(clip, "kind", "") != "midi":
            return
        
        # Get notes
        notes = self.project.ctx.project.midi_notes.get(clip_id, [])
        if not notes:
            self.status_message.emit("Clip hat keine Noten zum Exportieren!", 3000)
            return
        
        # Get clip name for default filename
        clip_name = getattr(clip, "name", "midi_clip")
        default_filename = f"{clip_name}.mid"
        
        # Ask user for save location
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "MIDI Clip exportieren",
            default_filename,
            "MIDI Files (*.mid);;All Files (*)"
        )
        
        if not filepath:
            return  # User cancelled
        
        # Ensure .mid extension
        if not filepath.lower().endswith('.mid'):
            filepath += '.mid'
        
        # Export
        bpm = float(getattr(self.project.ctx.project, "bpm", 120.0))
        success = export_midi_clip(clip, notes, Path(filepath), bpm)
        
        if success:
            self.status_message.emit(f"MIDI exportiert: {Path(filepath).name}", 3000)
        else:
            self.status_message.emit("MIDI Export fehlgeschlagen!", 3000)

    # --- painting

    def paintEvent(self, event):  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # v0.0.20.143: Respect the paint event clip rect.
        # This prevents O(project_length) grid loops when the canvas is very wide.
        clip_rect = event.rect() if event is not None else self.rect()
        try:
            p.setClipRect(clip_rect)
        except Exception:
            clip_rect = self.rect()
        p.fillRect(clip_rect, self.palette().base())

        ppb = float(self.pixels_per_beat or 1.0)
        bpb = max(0.5, float(self._beats_per_bar()))

        # Visible beat span (based on clip rect, not full widget width)
        try:
            vis_l = float(clip_rect.left())
            vis_r = float(clip_rect.right())
        except Exception:
            vis_l = 0.0
            vis_r = float(self.width())
        start_beat_vis = max(0.0, vis_l / max(1e-9, ppb))
        end_beat_vis = max(start_beat_vis + 0.001, vis_r / max(1e-9, ppb))

        # Loop shading
        if self.loop_enabled:
            x1 = int(self.loop_start * self.pixels_per_beat)
            x2 = int(self.loop_end * self.pixels_per_beat)
            p.fillRect(QRectF(x1, 0, max(0, x2 - x1), self.height()), QBrush(self.palette().alternateBase()))

        # v0.0.20.637: Punch region shading (red-tinted overlay)
        if self.punch_enabled:
            px1 = int(self.punch_in * self.pixels_per_beat)
            px2 = int(self.punch_out * self.pixels_per_beat)
            punch_color = QColor(220, 60, 60, 25)  # subtle red overlay
            p.fillRect(QRectF(px1, self.ruler_height, max(0, px2 - px1), self.height() - self.ruler_height), QBrush(punch_color))

        # Ruler background
        p.fillRect(0, 0, self.width(), self.ruler_height, self.palette().window())
        # Subtle darker tint for the zoom strip at top (visual hint for the user)
        zoom_h = int(self._ruler_zoom_band_h)
        zoom_tint = QColor(self.palette().window().color().darker(115))
        p.fillRect(0, 0, self.width(), zoom_h, zoom_tint)
        # Thin separator line between zoom strip and loop zone
        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.drawLine(0, zoom_h, self.width(), zoom_h)
        # Ruler helper text padding (keep small; magnifier is drawn on top and follows mouse).
        ruler_left_pad = 6

        # Loop handles in ruler
        if self.loop_enabled:
            pen = QPen(self.palette().highlight().color())
            pen.setWidth(2)
            p.setPen(pen)
            x1 = int(self.loop_start * self.pixels_per_beat)
            x2 = int(self.loop_end * self.pixels_per_beat)
            p.drawLine(x1, 0, x1, self.ruler_height)
            p.drawLine(x2, 0, x2, self.ruler_height)
            # Keep the LOOP label from colliding with the zoom handle.
            lx = max(min(x1, x2) + 6, ruler_left_pad)
            p.drawText(lx, 18, "LOOP")
        else:
            p.setPen(QPen(self.palette().mid().color()))
            p.drawText(ruler_left_pad, 18, "Loop: Off (Rechtsklick+ziehen im Lineal)")

        # v0.0.20.637: Punch In/Out handles in ruler (red/orange)
        if self.punch_enabled:
            punch_pen = QPen(QColor(220, 80, 60))  # red-orange
            punch_pen.setWidth(2)
            p.setPen(punch_pen)
            px1 = int(self.punch_in * self.pixels_per_beat)
            px2 = int(self.punch_out * self.pixels_per_beat)
            # Draw dashed lines through entire height for punch boundaries
            p.drawLine(px1, 0, px1, self.height())
            p.drawLine(px2, 0, px2, self.height())
            # Label in ruler
            punch_lx = max(min(px1, px2) + 6, ruler_left_pad)
            p.drawText(punch_lx, 28, "PUNCH")
            # Small triangular markers at top of ruler
            tri_h = 6
            for px in (px1, px2):
                tri = QPolygonF([
                    QPointF(px, zoom_h),
                    QPointF(px - tri_h, zoom_h + tri_h),
                    QPointF(px + tri_h, zoom_h + tri_h),
                ])
                p.setBrush(QBrush(QColor(220, 80, 60)))
                p.drawPolygon(tri)
            p.setBrush(Qt.BrushStyle.NoBrush)

        # Grid (Bar / Beat / Snap subdivisions)
        bpb = float(self._beats_per_bar())
        beat_start = int(max(0, math.floor(start_beat_vis)))
        beat_end = int(math.ceil(end_beat_vis)) + 2
        bar_start = int(max(0, math.floor(start_beat_vis / max(1e-9, bpb))))
        bar_end = int(math.ceil(end_beat_vis / max(1e-9, bpb))) + 3

        # Contrast-tuned grid colors (match PianoRoll readability)
        grid_sub = QColor(70, 74, 84, 140)   # ~55% alpha
        grid_beat = QColor(92, 96, 110, 180) # ~70% alpha
        grid_bar = QColor(130, 134, 152, 220)

        # Alternate bar shading for easier placement
        shade = QColor(255, 255, 255, 0)
        try:
            shade = QColor(self.palette().alternateBase().color())
        except Exception:
            pass
        for k in range(bar_start, bar_end):
            if k % 2 == 1:
                x = int(k * bpb * self.pixels_per_beat)
                w = int(bpb * self.pixels_per_beat)
                p.setOpacity(0.12)  # stronger than before
                p.fillRect(QRectF(x, self.ruler_height, w, self.height() - self.ruler_height), QBrush(shade))
                p.setOpacity(1.0)

        # Snap subdivision lines (e.g. 1/16)
        snap = float(self.snap_beats or 1.0)
        if 0.0 < snap < 1.0:
            pen_sub = QPen(grid_sub)
            pen_sub.setStyle(Qt.PenStyle.SolidLine)
            pen_sub.setWidth(1)
            p.setPen(pen_sub)
            sub_start = int(max(0, math.floor(start_beat_vis / max(1e-9, snap))))
            sub_end = int(math.ceil(end_beat_vis / max(1e-9, snap))) + 2
            for i in range(sub_start, sub_end):
                beat = float(i) * float(snap)
                # Skip full beats (handled by beat lines)
                if abs((beat % 1.0)) < 1e-6:
                    continue
                x = int(beat * self.pixels_per_beat)
                p.drawLine(x, self.ruler_height, x, self.height())

        # Beat lines (stronger)
        pen_beat = QPen(grid_beat)
        pen_beat.setStyle(Qt.PenStyle.SolidLine)
        pen_beat.setWidth(1)
        p.setPen(pen_beat)
        for b in range(beat_start, beat_end):
            x = int(float(b) * self.pixels_per_beat)
            p.drawLine(x, self.ruler_height, x, self.height())

        # Bar lines + labels
        pen_bar = QPen(grid_bar)
        pen_bar.setWidth(2)
        p.setPen(pen_bar)
        for k in range(bar_start, bar_end):
            beat = float(k) * float(bpb)
            x = int(beat * self.pixels_per_beat)
            p.drawLine(x, 0, x, self.height())
            # Keep the first label from overlapping the zoom handle.
            tx = x + 4
            if tx < ruler_left_pad:
                tx = ruler_left_pad
            p.drawText(tx, 18, f"Bar {k+1}")

        # Zoom handle icon (magnifier) — draw LAST so it stays visible on top.
        try:
            if bool(getattr(self, '_zoom_handle_visible', False)) or bool(getattr(self, '_zoom_drag_active', False)):
                bg = QColor(self.palette().base().color())
                bg.setAlpha(185)
                box = self._zoom_handle_rect.adjusted(-4, -4, 4, 4)
                p.fillRect(box, bg)
                p.setPen(QPen(self.palette().mid().color()))
                p.drawRect(box)
                paint_magnifier(p, self._zoom_handle_rect, color=self.palette().text().color())
        except Exception:
            pass

        # Track lanes
        p.setPen(QPen(self.palette().dark().color()))
        lane_entries = self._lane_entries()
        tracks = [entry.get("track") for entry in lane_entries if entry.get("track") is not None]
        for i, entry in enumerate(lane_entries):
            y = self.ruler_height + i * self.track_height
            ek = str(entry.get("kind", ""))
            if ek in ("group", "group_header"):
                try:
                    bg = QColor(255, 185, 110, 18 if ek == "group" else 12)
                    p.fillRect(QRectF(0, y + 1, self.width(), max(0, self.track_height - 2)), QBrush(bg))
                    p.setPen(QPen(QColor(255, 185, 110, 96 if ek == "group" else 72)))
                    arrow = "▸" if ek == "group" else "▾"
                    suffix = f" ({len(entry.get('members', []) or [])})" if ek == "group" else ""
                    p.drawText(QRectF(10, y + 4, 320, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{arrow} {entry.get('group_name', 'Gruppe')}{suffix}")
                    p.setPen(QPen(self.palette().dark().color()))
                except Exception:
                    p.setPen(QPen(self.palette().dark().color()))
            p.drawLine(0, y, self.width(), y)

        # New-clip ghost (while drag-creating)
        if self._drag_new_clip is not None:
            try:
                d = self._drag_new_clip
                idx = int(self._lane_index_for_track_id(getattr(d, "track_id", "")))
                if idx >= 0:
                    s = float(min(d.start_beat, d.cur_beat))
                    e = float(max(d.start_beat, d.cur_beat))
                    ln = float(e - s)
                    if ln < float(self.snap_beats) * 1.5:
                        ln = float(self._beats_per_bar())
                    x = s * self.pixels_per_beat
                    y = self.ruler_height + idx * self.track_height + 2
                    w = max(16.0, ln * self.pixels_per_beat)
                    h = float(self.track_height) - 4.0
                    ghost = QRectF(x, y, w, h)
                    p.setPen(QPen(self.palette().highlight().color()))
                    p.setBrush(QBrush(self.palette().alternateBase().color()))
                    p.setOpacity(0.55)
                    p.drawRect(ghost)
                    p.setOpacity(1.0)
            except Exception:
                p.setOpacity(1.0)

        # Clips (with QPixmap cache for performance)
        for cid, rect, clip in self._clip_rects():
            # Only draw clips that intersect the current paint region.
            try:
                if not QRectF(clip_rect).intersects(rect):
                    continue
            except Exception:
                pass
            is_sel = cid in self.selected_clip_ids if self.selected_clip_ids else (cid == self.selected_clip_id)

            # Cache key based on clip state + dimensions
            trk = next((t for t in tracks if t.id == clip.track_id), None)
            # v0.0.20.355 bugfix: For collapsed groups, tracks list only has members[0].
            # Fall back to full project track list to get correct volume/name.
            if trk is None:
                trk = next((t for t in (getattr(self.project.ctx.project, "tracks", []) or []) if str(getattr(t, "id", "")) == str(clip.track_id)), None)
            vol = float(getattr(trk, "volume", 1.0) or 1.0) if trk else 1.0
            # Determine if this clip is on a collapsed group lane (for label prefix)
            _clip_in_collapsed = False
            _clip_track_name = ""
            try:
                _clip_gid = str(getattr(trk, "track_group_id", "") or "") if trk else ""
                if _clip_gid and _clip_gid in self._collapsed_group_ids():
                    _clip_in_collapsed = True
                    _clip_track_name = str(getattr(trk, "name", "") or "")
            except Exception:
                pass
            w_i = max(1, int(rect.width()))
            h_i = max(1, int(rect.height()))
            cache_key = f"{cid}:{w_i}:{h_i}:{vol:.2f}:{getattr(clip,'gain',1.0):.2f}:{clip.kind}:{getattr(clip,'reversed',False)}:{getattr(clip,'muted',False)}:{getattr(clip,'stretch',1.0):.2f}:{_clip_in_collapsed}:{_clip_track_name}"

            cached = self._clip_pixmap_cache.get(cache_key)
            if cached is None or cached.width() != w_i or cached.height() != h_i:
                # Render clip to pixmap
                pxm = QPixmap(w_i, h_i)
                pxm.fill(QColor(0, 0, 0, 0))
                pp = QPainter(pxm)
                # No anti-aliasing for cached pixmaps (much faster rendering)

                local_rect = QRectF(0, 0, w_i, h_i)

                # Clip background
                if clip.kind == "audio":
                    base = self.palette().alternateBase()
                else:
                    base_color = self.palette().base().color().darker(110)
                    base = base_color
                pp.fillRect(local_rect, QBrush(base))
                pp.setPen(QPen(self.palette().text().color()))
                pp.drawRect(local_rect)

                # Muted clip overlay
                if getattr(clip, "muted", False):
                    pp.setOpacity(0.5)
                    pp.fillRect(local_rect, QBrush(QColor(60, 60, 60, 140)))
                    pp.setOpacity(1.0)

                # Reversed clip overlay (orange tint like Bitwig)
                if getattr(clip, "reversed", False):
                    pp.setOpacity(0.15)
                    pp.fillRect(local_rect, QBrush(QColor(255, 140, 0)))
                    pp.setOpacity(1.0)

                # Preview region
                # v0.0.20.144: dynamic waveform area (small track heights must still show usable waveforms)
                label_h = 18.0
                if h_i < 44:
                    label_h = max(12.0, float(h_i) * 0.30)
                if h_i < 30:
                    label_h = max(10.0, float(h_i) * 0.25)
                bottom_h = 6.0 if h_i >= 30 else 4.0
                inner = local_rect.adjusted(8, label_h, -8, -bottom_h)
                if inner.width() > 20 and inner.height() > 6:
                    if clip.kind == "audio":
                        self._draw_audio_waveform(pp, inner, clip, vol)
                    else:
                        self._draw_midi_preview(pp, inner, clip)

                # Title + volume
                kind_tag = "AUDIO" if clip.kind == "audio" else "MIDI"
                label = str(getattr(clip, "label", "") or kind_tag)
                # v0.0.20.355: Show track name prefix on collapsed group lanes
                # so the user can distinguish which clip belongs to which member track.
                track_prefix = f"🔹{_clip_track_name}: " if _clip_in_collapsed and _clip_track_name else ""
                rev_tag = " ◄" if getattr(clip, "reversed", False) else ""
                mute_tag = " [M]" if getattr(clip, "muted", False) else ""
                stretch_val = float(getattr(clip, "stretch", 1.0) or 1.0)
                stretch_tag = f" ×{stretch_val:.2f}" if abs(stretch_val - 1.0) > 0.01 else ""

                # Render badges (future-proof feedback): CONSOL / TRIM / +HANDLES / +TAIL ...
                meta_tag = ""
                try:
                    rm = getattr(clip, 'render_meta', {})
                    if isinstance(rm, dict):
                        bs = rm.get('badges', [])
                        if isinstance(bs, list):
                            bt = [str(x) for x in bs if str(x)]
                            if bt:
                                meta_tag = " " + " ".join(f"[{b}]" for b in bt[:4])
                except Exception:
                    meta_tag = ""

                _gain, db = self._display_gain_for_volume(vol)

                pp.setPen(QPen(self.palette().text().color()))
                pp.drawText(local_rect.adjusted(10, 2, -10, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"[ {kind_tag}: {track_prefix}{label}{rev_tag}{mute_tag}{stretch_tag}{meta_tag} ]")
                pp.setPen(QPen(self.palette().mid().color()))
                pp.drawText(local_rect.adjusted(10, 2, -10, -2), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, f"VOL: {db:+.1f} dB")

                # Handle strips
                self._draw_handle_strips(pp, local_rect, is_sel)

                pp.end()
                self._clip_pixmap_cache[cache_key] = pxm
                cached = pxm

                # Limit cache size
                if len(self._clip_pixmap_cache) > 200:
                    keys = list(self._clip_pixmap_cache.keys())
                    for k in keys[:100]:
                        del self._clip_pixmap_cache[k]

            # Draw cached pixmap
            p.drawPixmap(int(rect.x()), int(rect.y()), cached)

            if is_sel:
                sel_color = self.palette().highlight().color()
                sel_color.setAlpha(200)
                pen_sel = QPen(sel_color)
                pen_sel.setWidth(2)
                p.setPen(pen_sel)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(1, 1, -1, -1))

            # v0.0.20.361: Content Scale neon glow
            if self._drag_content_scale is not None and str(getattr(self._drag_content_scale, 'clip_id', '')) == str(cid):
                try:
                    p.save()
                    for alpha, width in [(60, 8), (100, 5), (180, 2)]:
                        glow_pen = QPen(QColor(0, 255, 220, alpha))
                        glow_pen.setWidth(width)
                        p.setPen(glow_pen)
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        margin = (8 - width) / 2
                        p.drawRoundedRect(rect.adjusted(margin, margin, -margin, -margin), 3.0, 3.0)
                    old_len = float(getattr(self._drag_content_scale, 'origin_len', 1.0) or 1.0)
                    cur_len = float(getattr(clip, 'length_beats', old_len) or old_len)
                    if old_len > 1e-9:
                        factor = cur_len / old_len
                        mode_label = "FREE" if getattr(self._drag_content_scale, 'free_mode', False) else "GRID"
                        p.setPen(QPen(QColor(0, 255, 220, 230)))
                        from PySide6.QtGui import QFont
                        f = p.font()
                        f.setPointSize(max(8, f.pointSize()))
                        f.setBold(True)
                        p.setFont(f)
                        p.drawText(QRectF(rect.x() + 4, rect.top() + 2, rect.width() - 8, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"⚡ ×{factor:.2f} {mode_label} {'🎵' if getattr(self._drag_content_scale, 'clip_kind', '') == 'midi' else '🔊'}")
                    p.restore()
                except Exception:
                    try:
                        p.restore()
                    except Exception:
                        pass

            # v0.0.20.175: Arranger Fade overlays + handles (audio only)
            try:
                show_fade = bool(is_sel) or (str(getattr(self, "_hover_clip_id", "")) == str(cid))
                self._draw_clip_fades(p, rect, clip, show_handles=bool(show_fade))
            except Exception:
                pass

            # v0.0.20.650: Warp markers in Arranger (AP3 Phase 3C Task 4)
            try:
                if str(getattr(clip, 'kind', '')) == 'audio':
                    self._draw_clip_warp_markers(p, rect, clip)
            except Exception:
                pass

            # v0.0.20.174: Small per-clip dropdown button (Cubase-style discoverability)
            # Appears on hover or when selected. Click opens the same context menu as right-click.
            try:
                show_btn = bool(is_sel) or (str(getattr(self, "_hover_clip_id", "")) == str(cid))
                if show_btn and rect.width() >= 26 and rect.height() >= 18:
                    btn = QRectF(rect.right() - 16, rect.top() + 3, 13, 13)
                    p.save()
                    p.setPen(QPen(self.palette().text().color()))
                    p.setBrush(QBrush(self.palette().midlight().color()))
                    p.setOpacity(0.9)
                    try:
                        p.drawRoundedRect(btn, 2.5, 2.5)
                    except Exception:
                        p.drawRect(btn)
                    p.setOpacity(1.0)
                    p.drawText(btn, Qt.AlignmentFlag.AlignCenter, "▾")
                    p.restore()
            except Exception:
                pass

        # v0.0.20.639: Take-Lanes — render inactive takes below their track (AP2 Phase 2D)
        try:
            take_svc = getattr(self, '_take_service', None)
            if take_svc:
                entries = self._lane_entries()
                for lane_idx, entry in enumerate(entries):
                    trk = entry.get("track")
                    if not trk or not getattr(trk, 'take_lanes_visible', False):
                        continue
                    tid = str(getattr(trk, 'id', ''))
                    groups = take_svc.get_take_groups_for_track(tid)
                    if not groups:
                        continue
                    take_h = max(20, int(getattr(trk, 'take_lanes_height', 40)))
                    base_y = self.ruler_height + lane_idx * self.track_height + self.track_height
                    sub_idx = 0
                    for gid, takes in groups.items():
                        for tc in takes:
                            if getattr(tc, 'is_comp_active', True):
                                continue  # skip active take (already drawn as main clip)
                            tx = float(getattr(tc, 'start_beats', 0)) * ppb
                            tw = max(10.0, float(getattr(tc, 'length_beats', 4)) * ppb)
                            ty = base_y + sub_idx * take_h
                            tr = QRectF(tx, ty, tw, take_h - 2)
                            # Dimmed clip appearance
                            p.setOpacity(0.5)
                            take_col = QColor(180, 100, 100, 160)
                            p.fillRect(tr, QBrush(take_col))
                            p.setPen(QPen(QColor(200, 120, 120)))
                            p.drawRect(tr)
                            lbl = str(getattr(tc, 'label', f'Take {getattr(tc, "take_index", 0) + 1}'))
                            p.drawText(tr.adjusted(4, 1, -4, -1), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, lbl)
                            p.setOpacity(1.0)
                            sub_idx += 1
        except Exception:
            pass

        # v0.0.20.640: Comp regions — colored markers on tracks showing comp selections
        try:
            take_svc = getattr(self, '_take_service', None)
            if take_svc:
                comp_colors = [
                    QColor(60, 180, 120, 100),   # green
                    QColor(60, 120, 200, 100),   # blue
                    QColor(200, 160, 60, 100),   # gold
                    QColor(180, 80, 180, 100),   # purple
                    QColor(200, 100, 60, 100),   # orange
                ]
                entries = self._lane_entries()
                for lane_idx, entry in enumerate(entries):
                    trk = entry.get("track")
                    if not trk:
                        continue
                    regions = list(getattr(trk, 'comp_regions', []) or [])
                    if not regions:
                        continue
                    # Build clip_id → color index mapping
                    clip_ids_seen = []
                    for r in regions:
                        cid_r = str(r.get('source_clip_id', ''))
                        if cid_r and cid_r not in clip_ids_seen:
                            clip_ids_seen.append(cid_r)
                    for r in regions:
                        rs = float(r.get('start_beat', 0))
                        re = float(r.get('end_beat', 0))
                        cid_r = str(r.get('source_clip_id', ''))
                        ci = clip_ids_seen.index(cid_r) if cid_r in clip_ids_seen else 0
                        col = comp_colors[ci % len(comp_colors)]
                        rx = int(rs * ppb)
                        rw = max(2, int((re - rs) * ppb))
                        ry = self.ruler_height + lane_idx * self.track_height
                        rh = 4  # thin colored bar at top of track
                        p.fillRect(QRectF(rx, ry, rw, rh), QBrush(col))
        except Exception:
            pass

        # v0.0.20.143: Ctrl+Drag copy preview ghost (multi-clip)
        if self._drag_copy_preview is not None:
            try:
                d = self._drag_copy_preview
                anchor_origin = float(d.origins.get(str(d.anchor_clip_id), (0.0, int(d.anchor_track_idx)))[0])
                delta_beats = float(d.cur_anchor_start) - float(anchor_origin)
                delta_tracks = int(d.cur_target_track_idx) - int(d.anchor_track_idx)

                ghost_fill = QColor(self.palette().highlight().color())
                ghost_fill.setAlpha(55)
                ghost_pen_col = QColor(self.palette().highlight().color())
                ghost_pen_col.setAlpha(190)
                pen = QPen(ghost_pen_col)
                pen.setWidth(2)
                pen.setStyle(Qt.PenStyle.DashLine)

                p.setOpacity(0.9)
                p.setPen(pen)
                p.setBrush(QBrush(ghost_fill))

                for src_id, (orig_start, orig_tidx) in (d.origins or {}).items():
                    src = next((c for c in self._arranger_clips() if str(getattr(c, 'id', '')) == str(src_id)), None)
                    if src is None:
                        continue
                    ns = max(0.0, float(orig_start) + float(delta_beats))
                    nt = int(orig_tidx) + int(delta_tracks)
                    if tracks:
                        nt = max(0, min(int(nt), int(len(tracks) - 1)))
                    else:
                        nt = max(0, int(nt))
                    x = float(ns) * float(self.pixels_per_beat)
                    y = float(self.ruler_height) + float(nt) * float(self.track_height) + 2.0
                    w = max(10.0, float(getattr(src, 'length_beats', 1.0) or 1.0) * float(self.pixels_per_beat))
                    h = float(self.track_height) - 4.0
                    gr = QRectF(x, y, w, h)
                    # Only paint if in current clip rect
                    try:
                        if not QRectF(clip_rect).intersects(gr):
                            continue
                    except Exception:
                        pass
                    p.drawRoundedRect(gr, 3.0, 3.0)

                p.setOpacity(1.0)
            except Exception:
                p.setOpacity(1.0)

        # Playline
        x = int(self.playhead_beat * self.pixels_per_beat)
        pen_play = QPen(Qt.GlobalColor.red)
        pen_play.setWidth(2)
        p.setPen(pen_play)
        p.drawLine(x, 0, x, self.height())

        # Lasso selection rectangle
        if self._drag_lasso is not None:
            lasso_rect = self._get_lasso_rect()
            if not lasso_rect.isEmpty():
                # Draw semi-transparent fill
                p.setPen(Qt.PenStyle.NoPen)
                lasso_color = self.palette().highlight().color()
                lasso_color.setAlpha(50)
                p.setBrush(QBrush(lasso_color))
                p.drawRect(lasso_rect)
                
                # Draw border
                pen_lasso = QPen(self.palette().highlight().color())
                pen_lasso.setWidth(2)
                pen_lasso.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen_lasso)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(lasso_rect)

        # v0.0.20.474 / v0.0.20.475: Plugin-Drag Preview (Track-Lane + Leerraum-Neuspur, nur visuell)
        if self._plugin_drag_preview_kind:
            try:
                if self._plugin_drag_preview_track_id:
                    idx_p = next(
                        (
                            i for i, entry in enumerate(lane_entries)
                            if str(getattr(entry.get("track"), "id", "") or "") == str(self._plugin_drag_preview_track_id)
                        ),
                        -1,
                    )
                    if idx_p >= 0:
                        y_p = self.ruler_height + idx_p * self.track_height + 2
                        preview_rect = QRectF(4.0, float(y_p), max(24.0, float(self.width()) - 8.0), max(8.0, float(self.track_height) - 4.0))
                        fill_alpha = 54 if self._plugin_drag_preview_kind == "instrument" else 34
                        fill = QColor(0, 229, 255, fill_alpha)
                        border = QColor(110, 245, 255, 230 if self._plugin_drag_preview_kind == "instrument" else 190)
                        p.setPen(QPen(border, 2, Qt.PenStyle.DashLine))
                        p.setBrush(QBrush(fill))
                        p.drawRoundedRect(preview_rect, 6.0, 6.0)
                        text_rect = preview_rect.adjusted(10.0, 4.0, -10.0, -4.0)
                        p.setPen(QPen(QColor(255, 255, 255, 235)))
                        p.drawText(
                            text_rect,
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            self._plugin_drag_preview_label,
                        )
                elif self._plugin_drag_preview_new_track_y is not None and self._plugin_drag_preview_new_track_label:
                    line_y = float(self._plugin_drag_preview_new_track_y)
                    line_pen = QPen(QColor(110, 245, 255, 236), 3, Qt.PenStyle.DashLine)
                    p.setPen(line_pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawLine(8, int(line_y), max(8, int(self.width()) - 8), int(line_y))
                    badge_rect = QRectF(12.0, max(float(self.ruler_height) + 4.0, line_y - 26.0), min(420.0, float(self.width()) - 24.0), 22.0)
                    p.setPen(QPen(QColor(110, 245, 255, 245), 1))
                    p.setBrush(QBrush(QColor(0, 229, 255, 48)))
                    p.drawRoundedRect(badge_rect, 8.0, 8.0)
                    p.setPen(QPen(QColor(255, 255, 255, 235)))
                    p.drawText(
                        badge_rect.adjusted(10.0, 0.0, -10.0, 0.0),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        self._plugin_drag_preview_new_track_label,
                    )
            except Exception:
                pass

        # v0.0.20.79: Ghost-clip overlay during cross-project / external drag
        if self._drag_ghost_pos is not None and self._drag_ghost_kind:
            try:
                gx = self._drag_ghost_pos.x()
                gy = self._drag_ghost_pos.y()
                trk = self._track_at_y(gy)
                if trk:
                    idx_g = next((i for i, t in enumerate(tracks) if getattr(t, "id", "") == trk.id), -1)
                    if idx_g >= 0:
                        # Snap to grid
                        beat_g = self._snap(self._x_to_beats(gx))
                        x_g = beat_g * self.pixels_per_beat
                        y_g = self.ruler_height + idx_g * self.track_height + 2
                        # Default ghost width: 4 beats (1 bar in 4/4)
                        w_g = max(40.0, self._beats_per_bar() * self.pixels_per_beat)
                        h_g = float(self.track_height) - 4.0
                        ghost_rect = QRectF(x_g, y_g, w_g, h_g)

                        # Color by drag type
                        if self._drag_ghost_kind == "cross-project":
                            ghost_fill = QColor(80, 160, 255, 60)   # blue tint
                            ghost_border = QColor(80, 160, 255, 180)
                        elif self._drag_ghost_kind == "midi":
                            ghost_fill = QColor(120, 200, 120, 60)  # green tint
                            ghost_border = QColor(120, 200, 120, 180)
                        else:  # audio
                            ghost_fill = QColor(200, 160, 80, 60)   # amber tint
                            ghost_border = QColor(200, 160, 80, 180)

                        p.setOpacity(0.7)
                        p.setBrush(QBrush(ghost_fill))
                        pen_ghost = QPen(ghost_border)
                        pen_ghost.setWidth(2)
                        pen_ghost.setStyle(Qt.PenStyle.DashLine)
                        p.setPen(pen_ghost)
                        p.drawRoundedRect(ghost_rect, 4.0, 4.0)

                        # Label
                        p.setPen(QPen(QColor(255, 255, 255, 220)))
                        p.drawText(
                            ghost_rect.adjusted(8, 4, -4, -4),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            self._drag_ghost_label,
                        )
                        p.setOpacity(1.0)
            except Exception:
                p.setOpacity(1.0)

        p.end()

    # --- canvas size management

    def _update_minimum_size(self) -> None:
        tracks = self._lane_entries()
        width_beats = 0.0
        for c in self._arranger_clips():
            width_beats = max(width_beats, float(c.start_beats) + float(c.length_beats) + 4.0)
        # Also ensure loop end is visible
        width_beats = max(width_beats, float(self.loop_end) + 2.0)
        w = int(max(640, width_beats * self.pixels_per_beat))
        h = int(max(320, self.ruler_height + len(tracks) * self.track_height + 20))
        # v0.0.20.597: Use resize() instead of setMinimumSize() so the canvas
        # doesn't force the main window wider than the screen.
        # The scroll area handles scrollbars automatically.
        self.resize(w, h)

    def _on_project_updated(self) -> None:
        # Throttle repaints: max ~20 fps to prevent GIL starvation during drag ops
        import time
        now = time.monotonic()
        last = getattr(self, '_last_update_time', 0.0)
        if (now - last) < 0.045:  # ~22 fps max
            # Schedule a deferred update if not already pending
            if not getattr(self, '_deferred_update_pending', False):
                self._deferred_update_pending = True
                from PySide6.QtCore import QTimer
                QTimer.singleShot(50, self._deferred_project_update)
            return
        self._last_update_time = now
        self._deferred_update_pending = False
        self._do_project_update()

    def _deferred_project_update(self) -> None:
        self._deferred_update_pending = False
        self._do_project_update()

    def _do_project_update(self) -> None:
        # Smart cache invalidation: only clear if track/clip structure changed.
        try:
            proj = self.project.ctx.project
            clips = getattr(proj, 'clips', []) or []
            new_sig = len(clips)
            if getattr(self, '_last_clip_count', -1) != new_sig:
                self._clip_pixmap_cache.clear()
                self._last_clip_count = new_sig
        except Exception:
            self._clip_pixmap_cache.clear()
        # Keep snap division in sync with project (if present)
        try:
            div = str(getattr(self.project.ctx.project, "snap_division", "1/16") or "1/16")
            self.set_snap_division(div)
        except Exception:
            pass
        self._update_minimum_size()
        self._sync_gl_overlay()
        self.update()

    def _sync_gl_overlay(self) -> None:
        """Sync the GPU overlay with current canvas state."""
        if self._gl_overlay is None:
            return
        try:
            # Resize overlay to match canvas
            self._gl_overlay.setGeometry(0, 0, self.width(), self.height())

            # Build clip data for GL renderer
            clips_data = []
            tracks = self._tracks()
            for cid, rect, clip in self._clip_rects():
                if clip.kind != "audio":
                    continue
                clips_data.append({
                    "x": float(rect.x()),
                    "y": float(rect.y()),
                    "width": float(rect.width()),
                    "height": float(rect.height()),
                })

            # Update viewport (pixel coords)
            w = max(1.0, float(self.width()))
            h = max(1.0, float(self.height()))
            self._gl_overlay.set_viewport(0, 0, w, h)
            self._gl_overlay.set_clips(clips_data)
            self._gl_overlay.set_playhead(self.playhead_beat * float(self.pixels_per_beat))
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_gl_overlay()
