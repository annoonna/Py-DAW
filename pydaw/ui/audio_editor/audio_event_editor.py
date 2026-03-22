"""AudioEventEditor (Phase 2.1)

Pro-DAW-Style Clip-Editor (Audio) – modular & low-risk.

Phase 2.0 delivered:
- AudioEvents (non-destructive segments) derived from slices
- Knife = split event, Eraser = merge near boundary
- Loop region overlay (per clip)
- Context menu stubs

Phase 2.1 adds:
- Arrow tool: select + GROUP MOVE selected AudioEvents (Pro-DAW-like)
- Consolidate (only for contiguous, source-aligned chains)
- Quantize (selected events)
- Fixes: missing handlers + indentation error in v0.0.19.7.50

Design rules:
- Single Source of Truth: ProjectService updates Clip dataclass
- Editor renders from model and writes changes back via ProjectService
- Loose coupling: context menu emits action text, editor/controller decides
"""

from __future__ import annotations

import math
import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover
    sf = None  # type: ignore

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QMimeData
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QDrag,
    QCursor,
    QKeyEvent,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# Drag&Drop: Export AudioEvent slice(s) from Audio Editor to Arranger
MIME_AUDIOEVENT_SLICE = 'application/x-pydaw-audioevent-slice'


@dataclass
class PeaksData:
    samplerate: int
    peaks: "np.ndarray"  # shape (N, 2): min/max per block
    block_size: int


@dataclass
class PeaksCacheEntry:
    """Cached peaks for one audio file."""

    mtime_ns: int
    samplerate: int
    block_size: int
    peaks: "np.ndarray"  # shape (N, 2)
    n_samples: int


class _FadeHandle(QGraphicsPolygonItem):
    """Draggable triangle handle for fade in/out (Bitwig-style).

    Renders as a small triangle that can be dragged horizontally to change fade length.
    """

    def __init__(self, x: float, height: float, *, role: str = "fade_in", on_moved=None):
        tri = QPolygonF()
        sz = 10.0  # triangle size
        if role == "fade_in":
            tri.append(QPointF(0.0, 0.0))
            tri.append(QPointF(sz, 0.0))
            tri.append(QPointF(0.0, sz))
        else:
            tri.append(QPointF(0.0, 0.0))
            tri.append(QPointF(-sz, 0.0))
            tri.append(QPointF(0.0, sz))
        super().__init__(tri)
        self.setPos(QPointF(float(x), 0.0))
        self.setZValue(35)
        self.setFlags(
            QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsPolygonItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._role = str(role)
        self._on_moved = on_moved
        color = QColor(255, 165, 0) if role == "fade_in" else QColor(100, 149, 237)
        self.setBrush(QBrush(color))
        pen = QPen(color.darker(130))
        pen.setWidth(1)
        self.setPen(pen)

    def hoverEnterEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsPolygonItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            return QPointF(p.x(), 0.0)  # constrain to horizontal
        if change == QGraphicsPolygonItem.GraphicsItemChange.ItemPositionHasChanged:
            try:
                if self._on_moved:
                    self._on_moved(float(self.pos().x()))
            except Exception:
                pass
        return super().itemChange(change, value)


class _LoopEdge(QGraphicsLineItem):
    """Draggable vertical line used as loop start/end edge.

    Note: QGraphicsItem is NOT a QObject, so we use a simple callback instead of Qt signals.
    """

    def __init__(self, x: float, height: float, *, color_role: str = "start"):
        # IMPORTANT:
        # Keep the line geometry anchored at x=0 and move it via setPos().
        # If we bake x into the line *and* move via setPos(), coordinates get doubled
        # (line at x + pos.x), which quickly leads to invalid values / re-entrant loops.
        super().__init__(0.0, 0.0, 0.0, height)
        try:
            self.setPos(QPointF(float(x), 0.0))
        except Exception:
            pass
        self.setZValue(30)
        self.setFlags(
            QGraphicsLineItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsLineItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._height = float(height)
        self._role = str(color_role)
        self._on_moved = None  # type: ignore[assignment]

        pen = QPen()
        pen.setWidth(2)
        if self._role == "start":
            pen.setColor(Qt.GlobalColor.cyan)
        else:
            pen.setColor(Qt.GlobalColor.green)
        self.setPen(pen)

    def set_on_moved(self, cb) -> None:  # noqa: ANN001
        self._on_moved = cb

    def hoverEnterEvent(self, event):  # noqa: ANN001
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # noqa: ANN001
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):  # noqa: ANN001
        if change == QGraphicsLineItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            # clamp Y, keep line anchored to top
            return QPointF(p.x(), 0.0)
        if change == QGraphicsLineItem.GraphicsItemChange.ItemPositionHasChanged:
            try:
                if self._on_moved:
                    self._on_moved(float(self.pos().x()))
            except Exception:
                pass
        return super().itemChange(change, value)


class BeatGridScene(QGraphicsScene):
    """Draws beat/bar grid as background via drawBackground."""

    def __init__(self, *, beats_per_bar: float = 4.0, px_per_beat: float = 80.0):
        super().__init__()
        self.beats_per_bar = float(beats_per_bar)
        self.px_per_beat = float(px_per_beat)

    def drawBackground(self, painter, rect):  # noqa: ANN001
        super().drawBackground(painter, rect)

        left = rect.left()
        right = rect.right()

        if self.px_per_beat <= 1e-6:
            return

        pen_beat = QPen(Qt.GlobalColor.darkGray)
        pen_beat.setWidth(1)
        pen_bar = QPen(Qt.GlobalColor.gray)
        pen_bar.setWidth(2)

        beat_start = max(0, int(math.floor(left / self.px_per_beat)) - 1)
        beat_end = int(math.ceil(right / self.px_per_beat)) + 1

        bpb = max(1, int(round(self.beats_per_bar)))
        for b in range(beat_start, beat_end + 1):
            x = b * self.px_per_beat
            is_bar = (b % bpb) == 0
            painter.setPen(pen_bar if is_bar else pen_beat)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))


class AudioEditorRuler(QWidget):
    """Bar/beat ruler with playhead, loop region, zoom and click-to-seek.

    Matches Arranger ruler functionality:
    - Bar/beat ticks + numbers
    - Red playhead line (draggable)
    - Loop region display (green shading)
    - Click on ruler = seek playhead to that bar
    - Ctrl+Wheel = zoom
    """

    seek_requested = pyqtSignal(float)  # beat position

    def __init__(self, editor: 'AudioEventEditor', parent=None):
        super().__init__(parent or editor)
        self._editor = editor
        self.setFixedHeight(28)
        self.setMinimumHeight(28)
        self.setMaximumHeight(28)
        self.setMouseTracking(True)
        self._drag_seek = False
        self._hover_zoom = False
        # Bitwig-style gesture state (zoom/seek/loop)
        self._drag_mode: str | None = None
        self._press_pos = None
        self._press_beat: float = 0.0
        self._zoom_last_y: int | None = None
        self._loop_anchor_beat: float | None = None

    def _beat_from_x(self, x_widget: int) -> float:
        """Convert widget x coordinate to beat position."""
        ed = self._editor
        view = getattr(ed, 'view', None)
        if view is None:
            return 0.0
        px_per_beat = float(getattr(ed, '_px_per_beat', 80.0) or 80.0)
        if px_per_beat <= 1e-6:
            return 0.0
        sp = view.mapToScene(view.viewport().rect().topLeft())
        # Widget x -> scene x
        scene_x = sp.x() + float(x_widget) / max(0.01, view.transform().m11())
        beat = scene_x / px_per_beat
        return max(0.0, float(beat))


    def mousePressEvent(self, event):
        # Arranger parity:
        # - Left click/drag = seek/scrub
        # - Right drag = draw loop region (like Arranger loop-brace)
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            beat = self._beat_from_x(event.pos().x())

            # Snap unless Shift
            try:
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    q = float(getattr(self._editor, '_snap_quantum_beats', lambda: 1.0)())
                    if q > 1e-9:
                        beat = round(float(beat) / q) * q
            except Exception:
                pass

            # NOTE: do NOT clamp to clip_len here.
            # The editor can temporarily extend its visible length during a loop-drag.
            beat = max(0.0, float(beat))

            self._press_pos = event.pos()
            self._press_beat = float(beat)
            self._zoom_last_y = int(event.pos().y())

            # Right-drag OR Alt+Drag on ruler = draw loop region (Ableton/Bitwig-style)
            if (event.button() == Qt.MouseButton.RightButton) or (event.modifiers() & Qt.KeyboardModifier.AltModifier):
                self._drag_mode = "loop"
                self._loop_anchor_beat = float(beat)
                try:
                    # live-update (small default length until user drags)
                    self._editor._on_loop_dragged(float(beat), float(beat) + 0.25)
                except Exception:
                    pass
                event.accept()
                return

            # Default: seek/scrub (left). Right click never seeks.
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_mode = "seek"
                self._drag_seek = True
                try:
                    self.seek_requested.emit(float(beat))
                except Exception:
                    pass
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Cursor feedback: Bitwig-style "magnifier" on beat ruler
        try:
            if self._drag_mode == "zoom":
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
        except Exception:
            pass

        if (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)) and self._drag_mode:
            # LOOP drawing
            if self._drag_mode == "loop" and self._loop_anchor_beat is not None:
                beat = self._beat_from_x(event.pos().x())
                try:
                    if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                        q = float(getattr(self._editor, '_snap_quantum_beats', lambda: 1.0)())
                        if q > 1e-9:
                            beat = round(float(beat) / q) * q
                except Exception:
                    pass
                beat = max(0.0, float(beat))
                a = float(self._loop_anchor_beat)
                b = float(beat)
                try:
                    self._editor._on_loop_dragged(min(a, b), max(a, b))
                except Exception:
                    pass
                self.update()
                event.accept()
                return

            # Decide between SEEK and ZOOM (Bitwig-style gesture)
            if self._drag_mode == "seek" and self._press_pos is not None:
                dx = int(event.pos().x() - self._press_pos.x())
                dy = int(event.pos().y() - self._press_pos.y())
                if abs(dy) > 3 and abs(dy) > abs(dx):
                    self._drag_mode = "zoom"
                    self._zoom_last_y = int(event.pos().y())
                else:
                    beat = self._beat_from_x(event.pos().x())
                    try:
                        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                            q = float(getattr(self._editor, '_snap_quantum_beats', lambda: 1.0)())
                            if q > 1e-9:
                                beat = round(float(beat) / q) * q
                    except Exception:
                        pass
                    beat = max(0.0, float(beat))
                    try:
                        self.seek_requested.emit(float(beat))
                    except Exception:
                        pass
                    self.update()
                    event.accept()
                    return

            if self._drag_mode == "zoom":
                view = getattr(self._editor, 'view', None)
                if view is not None:
                    try:
                        y = int(event.pos().y())
                        last = int(self._zoom_last_y) if self._zoom_last_y is not None else y
                        dy = y - last
                        if abs(dy) >= 1:
                            factor = 1.0 + (-float(dy) / 120.0)
                            factor = max(0.85, min(1.15, float(factor)))
                            view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                            view.scale(float(factor), 1.0)
                            try:
                                view.view_changed.emit()
                            except Exception:
                                pass
                        self._zoom_last_y = y
                    except Exception:
                        pass
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._drag_seek = False
            # If we just finished a loop-drag, finalize it (commit clip length resize if needed).
            try:
                if self._drag_mode == 'loop':
                    self._editor._on_loop_drag_finished()
            except Exception:
                pass
            self._drag_mode = None
            self._press_pos = None
            self._zoom_last_y = None
            self._loop_anchor_beat = None
        super().mouseReleaseEvent(event)
    def wheelEvent(self, event):
        """Ctrl+Wheel = zoom in ruler (like Arranger)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            view = getattr(self._editor, 'view', None)
            if view:
                delta = event.angleDelta().y()
                if delta != 0:
                    factor = 1.15 if delta > 0 else 1 / 1.15
                    view.scale(factor, 1.0)
                    try:
                        view.view_changed.emit()
                    except Exception:
                        pass
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click on ruler = zoom to fit."""
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                self._editor._on_zoom_fit()
            except Exception:
                pass
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _beats_per_bar(self) -> int:
        bpb = 4.0
        ed = self._editor
        try:
            if getattr(ed, 'transport', None) is not None:
                bpb = float(ed.transport.beats_per_bar() or 4.0)
            else:
                ts = getattr(ed.project.ctx.project, 'time_signature', '4/4')
                num, den = str(ts).split('/', 1)
                bpb = float(num) * (4.0 / float(den))
        except Exception:
            bpb = 4.0
        return max(1, int(round(float(bpb))))

    def paintEvent(self, event):  # noqa: ANN001
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pal = self.palette()
            bg = pal.base().color().darker(120)
            p.fillRect(self.rect(), bg)

            ed = self._editor
            view = getattr(ed, 'view', None)
            if view is None or view.scene() is None:
                return

            px_per_beat = float(getattr(ed, '_px_per_beat', 80.0) or 80.0)
            if px_per_beat <= 1e-6:
                return

            # Visible scene rect in beats
            vr = view.viewport().rect()
            sr = view.mapToScene(vr).boundingRect()
            left_b = float(sr.left() / px_per_beat)
            right_b = float(sr.right() / px_per_beat)

            bpb_i = self._beats_per_bar()

            beat_start = max(0, int(math.floor(left_b)) - 2)
            beat_end = max(0, int(math.ceil(right_b)) + 2)

            col_tick = pal.mid().color()
            col_text = pal.text().color()
            col_bar = pal.highlight().color()
            try:
                col_bar.setAlpha(220)
            except Exception:
                pass

            # --- Loop region shading (green, like Arranger) ---
            try:
                clip = getattr(ed, '_get_clip', lambda: None)()
                if clip:
                    ls = float(getattr(clip, 'loop_start_beats', getattr(clip, 'loop_start', 0.0)) or 0.0)
                    le = float(getattr(clip, 'loop_end_beats', getattr(clip, 'loop_end', 0.0)) or 0.0)
                    if le > ls + 0.01:
                        x_ls = int(view.mapFromScene(QPointF(ls * px_per_beat, 0.0)).x())
                        x_le = int(view.mapFromScene(QPointF(le * px_per_beat, 0.0)).x())
                        loop_color = QColor(60, 180, 80, 50)
                        p.fillRect(x_ls, 0, x_le - x_ls, self.height(), loop_color)
                        # Loop edges
                        p.setPen(QPen(QColor(60, 200, 80, 180), 2))
                        p.drawLine(x_ls, 0, x_ls, self.height())
                        p.drawLine(x_le, 0, x_le, self.height())
                        # LOOP label
                        p.setPen(QPen(QColor(60, 200, 80, 220), 1))
                        p.drawText(x_ls + 4, 12, "LOOP")
            except Exception:
                pass

            # Draw ticks + bar numbers
            for b in range(beat_start, beat_end + 1):
                x_scene = float(b) * px_per_beat
                x = int(view.mapFromScene(QPointF(x_scene, 0.0)).x())
                if x < -30 or x > self.width() + 30:
                    continue

                is_bar = (b % bpb_i) == 0
                if is_bar:
                    p.setPen(QPen(col_bar, 2))
                    p.drawLine(x, 0, x, self.height())
                    # bar number (1-based)
                    bar_idx = int(b // bpb_i) + 1
                    p.setPen(QPen(col_text, 1))
                    p.drawText(x + 4, 14, f"{bar_idx}")
                else:
                    p.setPen(QPen(col_tick, 1))
                    p.drawLine(x, self.height() - 10, x, self.height())

            # --- Playhead (red line, like Arranger) ---
            try:
                ph_beat = float(getattr(ed, '_playhead_beat', 0.0) or 0.0)
                if ph_beat >= 0:
                    x_ph = int(view.mapFromScene(QPointF(ph_beat * px_per_beat, 0.0)).x())
                    p.setPen(QPen(QColor(220, 40, 40, 240), 2))
                    p.drawLine(x_ph, 0, x_ph, self.height())
                    # Small triangle at top
                    p.setBrush(QBrush(QColor(220, 40, 40, 240)))
                    tri = QPolygonF()
                    tri.append(QPointF(float(x_ph) - 5.0, 0.0))
                    tri.append(QPointF(float(x_ph) + 5.0, 0.0))
                    tri.append(QPointF(float(x_ph), 6.0))
                    p.drawPolygon(tri)
            except Exception:
                pass

            # --- Cursor line (blue, thin, paste position) ---
            try:
                if bool(getattr(ed, '_has_cursor', False)):
                    cb = float(getattr(ed, '_cursor_beat', 0.0) or 0.0)
                    x_cb = int(view.mapFromScene(QPointF(cb * px_per_beat, 0.0)).x())
                    p.setPen(QPen(QColor(80, 160, 255, 180), 1, Qt.PenStyle.DashLine))
                    p.drawLine(x_cb, 0, x_cb, self.height())
            except Exception:
                pass

            # bottom border
            p.setPen(QPen(pal.mid().color().darker(140), 1))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        finally:
            p.end()


class AudioEditorView(QGraphicsView):
    """Main interactive view: zoom + tool routing + context menu."""

    request_slice = pyqtSignal(float)  # at_beats
    request_remove_slice = pyqtSignal(float)  # at_beats
    request_set_loop = pyqtSignal(float, float)  # start_beats, end_beats
    # Knife Cut+Drag: split then drag right-part(s) immediately
    request_slice_drag = pyqtSignal(float, float)  # at_beats, press_scene_x
    knife_drag_update = pyqtSignal(float, int)  # scene_x, modifiers(int)
    knife_drag_end = pyqtSignal()
    context_action_selected = pyqtSignal(str)
    # Pencil tool: add/move/delete automation points
    pencil_add_point = pyqtSignal(float, float)  # at_beats, normalized_value (0..1)
    pencil_remove_point = pyqtSignal(float)  # at_beats
    pencil_drag_point = pyqtSignal(float, float)  # at_beats, normalized_value

    # Stretch/Warp markers (double-click to add in Stretch overlay)
    stretch_add_marker = pyqtSignal(float)  # at_beats

    # UI sync: ruler needs repaint when view scroll/zoom changes
    view_changed = pyqtSignal()

    def __init__(self, scene: BeatGridScene, *, px_per_beat: float = 80.0, parent=None):
        super().__init__(scene, parent)
        self._scene = scene
        self._px_per_beat = float(px_per_beat)
        self._tool = "ARROW"
        self._clip_len_beats = 4.0
        # Snap quantum in beats (quarter-note beats). Updated by AudioEventEditor.
        self._snap_quantum_beats = 0.25

        self._drag_loop = False
        self._loop_drag_start_x: float | None = None

        # Zoom tool drag (magnifier)
        self._zoom_drag = False
        self._zoom_drag_last_y = None

        # Knife Cut+Drag state
        self._knife_drag_active = False
        self._knife_press_scene_x = 0.0

        # middle-mouse panning
        self._panning = False
        self._pan_last = None

        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setRenderHints(self.renderHints())

        # Keyboard focus for DAW shortcuts (Ctrl+C/V/Delete, etc.)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Editor backref (set by AudioEventEditor)
        self._editor_ref = None

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

        self.set_tool("ARROW")

    def set_tool(self, tool: str) -> None:
        self._tool = str(tool or "ARROW").upper()
        # Reset Cut+Drag when leaving Knife
        if self._tool != "KNIFE":
            self._knife_drag_active = False
        if self._tool == "KNIFE":
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self._tool in ("TIME", "TIMESELECT"):
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self._tool in ("ZOOM", "LUPE", "MAGNIFY"):
            # Bitwig-style zoom cursor (magnifier)
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self._tool in ("ERASE", "ERASER"):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self._tool == "PENCIL":
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self._tool in ("POINTER", "ZEIGER"):  # Zeiger tool
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            # Arrow: items handle dragging (group move)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def set_clip_length(self, beats: float) -> None:
        self._clip_len_beats = max(0.0, float(beats))

    def set_snap_quantum_beats(self, q: float) -> None:
        try:
            qf = float(q)
        except Exception:
            qf = 0.25
        self._snap_quantum_beats = max(1e-6, qf)

    def wheelEvent(self, event):  # noqa: ANN001
        # Default: zoom horizontally (like Arranger); Shift+Wheel: scroll
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.scale(factor, 1.0)
        try:
            self.view_changed.emit()
        except Exception:
            pass
        event.accept()

    def resizeEvent(self, event):  # noqa: ANN001
        super().resizeEvent(event)
        try:
            self.view_changed.emit()
        except Exception:
            pass

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: ANN001
        try:
            ed = getattr(self, '_editor_ref', None)
            if ed is not None and hasattr(ed, 'handle_key_event'):
                if bool(ed.handle_key_event(event)):
                    event.accept()
                    return
        except Exception:
            pass
        super().keyPressEvent(event)

    def mousePressEvent(self, event):  # noqa: ANN001
        # middle mouse: pan view
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # Give focus so keyboard shortcuts work immediately
            try:
                self.setFocus(Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass

            sp = self.mapToScene(event.pos())
            at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
            # clamp to clip bounds
            at_beats = max(0.0, min(float(self._clip_len_beats), float(at_beats)))
            mods = event.modifiers()

            # Zoom tool (Lupe): click+drag up/down to zoom like Bitwig.
            if self._tool in ("ZOOM", "LUPE", "MAGNIFY"):
                self._zoom_drag = True
                self._zoom_drag_last_y = int(event.pos().y())
                try:
                    self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                except Exception:
                    pass
                event.accept()
                return

            # Alt+Drag anywhere on the grid sets the clip loop region (no tool switch needed).
            # (On EventBlockItems, Alt is handled by the item itself for Duplicate-Drag.)
            if bool(mods & Qt.KeyboardModifier.AltModifier) and self._tool not in ("PENCIL",):
                self._drag_loop = True
                self._loop_drag_start_x = float(sp.x())
                event.accept()
                return

            if self._tool == "KNIFE":
                # Snap-to-grid unless Shift is held (Pro-DAW-like).
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    q = float(self._snap_quantum_beats) if self._snap_quantum_beats > 1e-9 else 0.25
                    at_beats = round(at_beats / q) * q
                    at_beats = max(0.0, min(float(self._clip_len_beats), float(at_beats)))
                # Cut+Drag: request a split, then drag starts immediately via editor
                self._knife_drag_active = True
                self._knife_press_scene_x = float(sp.x())
                try:
                    self.request_slice_drag.emit(float(at_beats), float(self._knife_press_scene_x))
                except Exception:
                    self.request_slice.emit(float(at_beats))
                event.accept()
                return

            if self._tool in ("ERASE", "ERASER"):
                self.request_remove_slice.emit(at_beats)
                event.accept()
                return

            if self._tool == "PENCIL":
                sp2 = self.mapToScene(event.pos())
                at_beats_p = float(sp2.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
                at_beats_p = max(0.0, min(float(self._clip_len_beats), at_beats_p))
                # Normalized value: y position relative to scene height
                scene_rect = self.scene().sceneRect() if self.scene() else QRectF(0, 0, 800, 220)
                h = max(1.0, scene_rect.height())
                norm_val = max(0.0, min(1.0, 1.0 - (float(sp2.y()) / h)))
                if event.button() == Qt.MouseButton.LeftButton:
                    self.pencil_add_point.emit(float(at_beats_p), float(norm_val))
                event.accept()
                return

            if self._tool in ("TIME", "TIMESELECT"):
                self._drag_loop = True
                self._loop_drag_start_x = float(sp.x())
                event.accept()
                return

            # Cursor for paste target (click empty background or grid area)
            # We must ignore grid-line items — only EventBlockItem / _LoopEdge
            # should block cursor placement.
            try:
                it = self.itemAt(event.pos())
                is_event_item = False
                if it is not None:
                    # Check if clicked item is an event block or loop handle
                    cls_name = type(it).__name__
                    is_event_item = cls_name in ("EventBlockItem", "_LoopEdge")
                if not is_event_item and getattr(self, '_editor_ref', None) is not None:
                    # Snap cursor to grid (like ruler seek) unless Shift held
                    cursor_beat = float(at_beats)
                    if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                        q = float(self._snap_quantum_beats) if self._snap_quantum_beats > 1e-9 else 0.25
                        cursor_beat = round(cursor_beat / q) * q
                        cursor_beat = max(0.0, min(float(self._clip_len_beats), cursor_beat))
                    getattr(self._editor_ref, 'set_cursor_beat', lambda *_: None)(float(cursor_beat))
                    # Also set playhead to match cursor
                    getattr(self._editor_ref, 'set_playhead_beat', lambda *_: None)(float(cursor_beat))
            except Exception:
                pass

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: ANN001
        # Zoom tool drag (Lupe)
        if bool(getattr(self, '_zoom_drag', False)) and self._tool in ("ZOOM", "LUPE", "MAGNIFY") and (event.buttons() & Qt.MouseButton.LeftButton):
            try:
                y = int(event.pos().y())
                last = int(self._zoom_drag_last_y) if self._zoom_drag_last_y is not None else y
                dy = y - last
                if abs(dy) >= 1:
                    # drag up = zoom in, down = zoom out
                    factor = 1.0 + (-float(dy) / 120.0)
                    factor = max(0.85, min(1.15, float(factor)))
                    self.scale(float(factor), 1.0)
                    self._zoom_drag_last_y = y
                    try:
                        self.view_changed.emit()
                    except Exception:
                        pass
                event.accept()
                return
            except Exception:
                pass

        if self._knife_drag_active and self._tool == "KNIFE" and (event.buttons() & Qt.MouseButton.LeftButton):
            sp = self.mapToScene(event.pos())
            try:
                self.knife_drag_update.emit(float(sp.x()), int(event.modifiers()))
            except Exception:
                pass
            event.accept()
            return

        # Pencil continuous drawing (draw while dragging)
        if self._tool == "PENCIL" and (event.buttons() & Qt.MouseButton.LeftButton):
            sp = self.mapToScene(event.pos())
            at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
            at_beats = max(0.0, min(float(self._clip_len_beats), at_beats))
            scene_rect = self.scene().sceneRect() if self.scene() else QRectF(0, 0, 800, 220)
            h = max(1.0, scene_rect.height())
            norm_val = max(0.0, min(1.0, 1.0 - (float(sp.y()) / h)))
            self.pencil_drag_point.emit(float(at_beats), float(norm_val))
            event.accept()
            return

        if self._panning and self._pan_last is not None:
            d = event.pos() - self._pan_last
            self._pan_last = event.pos()
            hs = self.horizontalScrollBar()
            vs = self.verticalScrollBar()
            hs.setValue(hs.value() - d.x())
            vs.setValue(vs.value() - d.y())
            event.accept()
            return

        if self._drag_loop and self._loop_drag_start_x is not None:
            sp = self.mapToScene(event.pos())
            x0 = float(self._loop_drag_start_x)
            x1 = float(sp.x())
            a = min(x0, x1) / self._px_per_beat
            b = max(x0, x1) / self._px_per_beat
            self.request_set_loop.emit(float(a), float(b))
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        # End zoom drag
        try:
            if self._tool in ("ZOOM", "LUPE", "MAGNIFY"):
                self._zoom_drag = False
                self._zoom_drag_last_y = None
        except Exception:
            pass

        if event.button() == Qt.MouseButton.LeftButton and self._knife_drag_active:
            self._knife_drag_active = False
            try:
                self.knife_drag_end.emit()
            except Exception:
                pass
            event.accept()
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._pan_last = None
            self.set_tool(self._tool)
            event.accept()
            return

        was_loop = bool(self._drag_loop)
        self._drag_loop = False
        self._loop_drag_start_x = None
        # Commit/refresh after a loop-drag (allows auto-extend clip length).
        try:
            if was_loop and getattr(self, '_editor_ref', None) is not None:
                getattr(self._editor_ref, '_on_loop_drag_finished', lambda: None)()
        except Exception:
            pass
        super().mouseReleaseEvent(event)

        # RubberBand selection can update at mouse-release; ensure editor cache is in sync
        try:
            ed = getattr(self, '_editor_ref', None)
            if ed is not None and hasattr(ed, '_on_selection_changed'):
                ed._on_selection_changed()
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        # Stretch/Warp: double-click adds a warp marker (only handled by editor when stretch overlay is active)
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._tool in ("POINTER", "ZEIGER"):
                sp = self.mapToScene(event.pos())
                at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
                at_beats = max(0.0, min(float(self._clip_len_beats), float(at_beats)))
                # Snap unless Shift
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    q = float(self._snap_quantum_beats) if self._snap_quantum_beats > 1e-9 else 0.25
                    at_beats = round(at_beats / q) * q
                    at_beats = max(0.0, min(float(self._clip_len_beats), float(at_beats)))
                self.stretch_add_marker.emit(float(at_beats))
                event.accept()
                return
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

    def _ctx_menu(self, pos):  # noqa: ANN001
        # In Pencil mode, right-click removes automation point instead of showing menu
        if self._tool == "PENCIL":
            sp = self.mapToScene(pos)
            at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
            at_beats = max(0.0, min(float(self._clip_len_beats), at_beats))
            self.pencil_remove_point.emit(float(at_beats))
            return

        ed = getattr(self, '_editor_ref', None)

        # Hit-test the event under the mouse (if any). Note: itemAt() might return a child
        # (waveform path etc.), so we walk up parents until we find an EventBlockItem.
        hit_item = None
        hit_event_id = None
        try:
            hit_item = self.itemAt(pos)
            while hit_item is not None and not isinstance(hit_item, EventBlockItem):
                try:
                    hit_item = hit_item.parentItem()
                except Exception:
                    break
            if isinstance(hit_item, EventBlockItem):
                hit_event_id = str(getattr(hit_item, 'event_id', '') or '').strip() or None
        except Exception:
            hit_item = None
            hit_event_id = None

        # DAW-like right-click selection:
        # If user right-clicks on an event that is not currently selected, we select
        # only that event before opening the menu. This prevents actions like Reverse
        # from affecting unrelated events when there is no active selection.
        try:
            if ed is not None:
                setattr(ed, '_context_menu_event_id', hit_event_id)
        except Exception:
            pass

        try:
            if ed is not None and hit_event_id:
                cur_sel = set(getattr(ed, '_selected_event_ids', set()) or set())
                if hit_event_id not in cur_sel:
                    try:
                        sc = self.scene()
                        if sc is not None:
                            for it in sc.selectedItems():
                                try:
                                    it.setSelected(False)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    try:
                        if hit_item is not None:
                            hit_item.setSelected(True)
                    except Exception:
                        pass
                    try:
                        ed._selected_event_ids = {hit_event_id}
                    except Exception:
                        pass
        except Exception:
            pass

        menu = QMenu(self)

        # IMPORTANT (v0.0.20.173): resolve current clip BEFORE gating Ultra-Pro actions.
        # Previously the menu checked `clip_obj.render_meta` while `clip_obj` was still
        # None (it was assigned later for the Reverse checkbox). Result: the user never
        # saw "Re-render (in place)" / "Restore Sources" entries.
        clip_obj = None
        try:
            clip_obj = ed._get_clip() if ed is not None else None  # type: ignore[attr-defined]
        except Exception:
            clip_obj = None

        # --- Clipboard operations (like Arranger) ---
        has_sel = bool(getattr(ed, '_selected_event_ids', set())) if ed else False
        has_clip = bool(getattr(ed, '_clipboard_templates', [])) if ed else False

        act_copy = menu.addAction("Copy (Ctrl+C)")
        act_copy.setEnabled(has_sel)
        act_cut = menu.addAction("Cut (Ctrl+X)")
        act_cut.setEnabled(has_sel)
        act_paste = menu.addAction("Paste (Ctrl+V)")
        act_paste.setEnabled(has_clip)
        act_del = menu.addAction("Delete (Del)")
        act_del.setEnabled(has_sel)
        menu.addSeparator()
        act_selall = menu.addAction("Select All (Ctrl+A)")
        act_dup = menu.addAction("Duplicate (Ctrl+D)")
        act_dup.setEnabled(has_sel)
        menu.addSeparator()

        menu.addAction("Split at Playhead")
        menu.addAction("Consolidate")
        menu.addAction("Consolidate (Trim)")
        menu.addAction("Consolidate (+Handles)")
        tail_sub = menu.addMenu("Consolidate (+Tail)")
        tail_sub.addAction("Tail +1/4 Beat")
        tail_sub.addAction("Tail +1 Beat")
        tail_sub.addAction("Tail +1 Bar")
        menu.addAction("Join to new Clip (keep events)")
        # Ultra-Pro / Ultra-Ultra (render_meta)
        # v0.0.20.174: Always show "Re-render (in place)" for audio clips.
        # It now also works for normal clips (initial render), not only consolidated ones.
        try:
            rm = getattr(clip_obj, 'render_meta', {}) if clip_obj is not None else {}
            src_ok = False
            if isinstance(rm, dict):
                src = rm.get('sources', {})
                if isinstance(src, dict) and str(src.get('source_clip_id', '') or '').strip():
                    src_ok = True

            menu.addSeparator()
            a_rr_from = menu.addAction("Re-render (from sources)")
            a_rr_from.setEnabled(bool(src_ok))
            menu.addAction("Re-render (in place)")

            a_restore = menu.addAction("Restore Sources (in place)")
            a_back = menu.addAction("Back to Sources")
            a_toggle = menu.addAction("Toggle Rendered ↔ Sources")
            a_rebuild = menu.addAction("Rebuild original clip state")
            if not src_ok:
                a_restore.setEnabled(False)
                a_back.setEnabled(False)
                a_toggle.setEnabled(False)
                a_rebuild.setEnabled(False)
        except Exception:
            pass

        menu.addSeparator()

        # Clip-level reverse (affects Arranger + Editor visual)
        act_rev_clip = menu.addAction("Reverse")
        act_rev_clip.setCheckable(True)
        # clip_obj is resolved above
        try:
            act_rev_clip.setChecked(bool(getattr(clip_obj, "reversed", False)) if clip_obj is not None else False)
        except Exception:
            pass
        act_rev_clip.setEnabled(bool(clip_obj is not None))

        # Per-event reverse (only for selected events)
        act_rev_events = menu.addAction("Reverse (Events)")
        act_rev_events.setEnabled(bool(has_sel))

        menu.addAction("Mute Clip")
        menu.addAction("Normalize")

        gain_sub = menu.addMenu("Gain")
        gain_sub.addAction("+3 dB")
        gain_sub.addAction("-3 dB")
        gain_sub.addAction("+6 dB")
        gain_sub.addAction("-6 dB")
        gain_sub.addAction("Reset (0 dB)")

        menu.addSeparator()

        fade_sub = menu.addMenu("Fades")
        fade_sub.addAction("Fade In 1/16")
        fade_sub.addAction("Fade In 1/8")
        fade_sub.addAction("Fade In 1/4")
        fade_sub.addAction("Fade In 1 Bar")
        fade_sub.addSeparator()
        fade_sub.addAction("Fade Out 1/16")
        fade_sub.addAction("Fade Out 1/8")
        fade_sub.addAction("Fade Out 1/4")
        fade_sub.addAction("Fade Out 1 Bar")
        fade_sub.addSeparator()
        fade_sub.addAction("Clear Fades")

        menu.addSeparator()
        menu.addAction("Quantize (Events)")

        sub = menu.addMenu("Transpose")
        sub.addAction("+1 Semitone")
        sub.addAction("-1 Semitone")
        sub.addAction("+12 Semitone (Octave Up)")
        sub.addAction("-12 Semitone (Octave Down)")

        menu.addSeparator()
        on = menu.addMenu("Onsets")
        on.addAction("Auto-Detect Onsets")
        on.addAction("Add Onset at Playhead")
        on.addAction("Slice at Onsets")
        on.addAction("Clear Onsets")

        # v0.0.20.641: Warp Markers submenu (AP3 Phase 3A)
        warp = menu.addMenu("Warp Markers")
        warp.addAction("Auto-Detect Warp Markers")
        warp.addAction("Clear Warp Markers")

        menu.addSeparator()
        menu.addAction("Snap to Zero-Crossing")

        menu.addSeparator()
        auto_sub = menu.addMenu("Clip Automation")
        auto_sub.addAction("Clear Gain Automation")
        auto_sub.addAction("Clear Pan Automation")
        auto_sub.addAction("Clear Pitch Automation")
        auto_sub.addAction("Clear All Clip Automation")

        act = menu.exec(self.mapToGlobal(pos))
        if act:
            txt = str(act.text())
            # Handle clipboard shortcuts from context menu
            if txt.startswith("Copy"):
                txt = "_ctx_copy"
            elif txt.startswith("Cut"):
                txt = "_ctx_cut"
            elif txt.startswith("Paste"):
                txt = "_ctx_paste"
            elif txt.startswith("Delete"):
                txt = "_ctx_delete"
            elif txt.startswith("Select All"):
                txt = "_ctx_select_all"
            elif txt.startswith("Duplicate"):
                txt = "_ctx_duplicate"
            try:
                self.context_action_selected.emit(str(txt))
            except Exception:
                pass


class EventBlockItem(QGraphicsRectItem):
    """Clickable + selectable block representing one AudioEvent.

    Phase 2.1: dragging one block moves ALL selected blocks together (group move).
    """

    def __init__(
        self,
        editor: "AudioEventEditor",
        *,
        event_id: str,
        start_beats: float,
        length_beats: float,
        px_per_beat: float,
        height: float,
        alt_shade: bool,
    ):
        self.editor = editor
        self.event_id = str(event_id)
        self._px_per_beat = float(px_per_beat)
        self._length_beats = float(max(0.0, length_beats))

        w = max(1.0, self._length_beats * self._px_per_beat)
        super().__init__(QRectF(0.0, 0.0, w, float(height)))
        self.setPos(QPointF(float(start_beats) * self._px_per_beat, 0.0))

        self.setZValue(6)
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)

        base = editor.palette().alternateBase().color()
        self._brush = QBrush(base)
        self._opacity = 0.10 if alt_shade else 0.06

        self._pen = QPen(editor.palette().mid().color())
        self._pen.setWidth(1)
        self._pen_sel = QPen(editor.palette().highlight().color())
        self._pen_sel.setWidth(2)

        # Export-drag (drag slice out of editor to Arranger)
        self._export_drag_started = False

    def start_beats(self) -> float:
        return float(self.pos().x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0

    def length_beats(self) -> float:
        return float(self._length_beats)

    def hoverEnterEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool in ("ARROW", "POINTER"):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool in ("ARROW", "POINTER"):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool not in ("ARROW", "POINTER") or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # Selection rule (DAW-like):
        # - plain click: single selection
        # - Ctrl: add to selection (do NOT toggle off on press; avoids breaking Ctrl+Drag duplicate)
        scene = self.scene()
        if scene and not ctrl:
            scene.clearSelection()
            self.setSelected(True)
        elif ctrl:
            # add
            self.setSelected(True)
        else:
            self.setSelected(True)

        self._export_drag_started = False
        self.editor._begin_group_drag(self, event.scenePos().x(), mods, alt_duplicate=alt)
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool not in ("ARROW", "POINTER"):
            event.ignore()
            return
        # If user drags selection out of the editor upwards, start export drag to Arranger
        if not self._export_drag_started and self.editor.view is not None:
            try:
                top = self.editor.view.viewport().mapToGlobal(self.editor.view.viewport().rect().topLeft()).y()
                cy = QCursor.pos().y()
                if cy < (top - 8):
                    self._export_drag_started = True
                    try:
                        self.editor._cancel_group_drag_visual()
                    except Exception:
                        pass
                    try:
                        scene = self.scene()
                        sel = [it.event_id for it in (scene.selectedItems() if scene else []) if isinstance(it, EventBlockItem)]
                    except Exception:
                        sel = []
                    if not sel:
                        sel = [self.event_id]
                    try:
                        self.editor._start_export_drag_to_arranger(sel)
                    except Exception:
                        pass
                    event.accept()
                    return
            except Exception:
                pass

        self.editor._update_group_drag(event.scenePos().x(), event.modifiers())
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool not in ("ARROW", "POINTER"):
            event.ignore()
            return
        self.editor._end_group_drag()
        event.accept()

    def paint(self, painter: QPainter, option, widget=None):  # noqa: ANN001
        painter.save()
        painter.setOpacity(self._opacity)
        painter.setBrush(self._brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        painter.restore()

        painter.save()
        painter.setOpacity(0.9)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self._pen_sel if self.isSelected() else self._pen)
        painter.drawRect(self.rect())
        painter.restore()


class AutomationPointItem(QGraphicsRectItem):
    """Draggable automation breakpoint (for Zeiger/Pointer tool)."""

    def __init__(
        self,
        editor: "AudioEventEditor",
        *,
        clip_id: str,
        param: str,
        beat: float,
        value: float,
        px_per_beat: float,
        height: float,
        color: QColor,
        dot_size: float = 9.0,
    ):
        super().__init__(QRectF(0.0, 0.0, float(dot_size), float(dot_size)))
        self.editor = editor
        self.clip_id = str(clip_id)
        self.param = str(param or '').strip().lower()
        self.beat = float(beat)
        self.value = float(value)
        self._px_per_beat = float(px_per_beat)
        self._height = float(height)
        self._dot = float(dot_size)

        self.setZValue(42)
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)

        self._brush = QBrush(color)
        self._pen = QPen(color.darker(140))
        self._pen.setWidth(1)
        self._pen_sel = QPen(color.lighter(130))
        self._pen_sel.setWidth(2)

        # Export-drag (drag slice out of editor to Arranger)
        self._export_drag_started = False

        self._dragging = False
        self._drag_start = None
        self._orig_beat = float(beat)

        self._sync_pos()

    def _sync_pos(self) -> None:
        bx = float(self.beat) * self._px_per_beat
        by = float(self._height) - (float(self.value) * float(self._height))
        self.setPos(QPointF(bx - self._dot / 2.0, by - self._dot / 2.0))

    def hoverEnterEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool == "POINTER":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool == "POINTER":
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):  # noqa: ANN001
        if self.editor.current_tool != "POINTER":
            event.ignore()
            return
        if event.button() == Qt.MouseButton.RightButton:
            # delete
            try:
                self.editor._remove_automation_point(self.param, float(self.beat))
            except Exception:
                pass
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        # only active when matching overlay
        if self.editor._active_overlay != self.param:
            event.ignore()
            return
        self._dragging = True
        self._orig_beat = float(self.beat)
        self._drag_start = event.scenePos()
        self.setSelected(True)
        # Avoid full refresh storms during drag
        self.editor._suppress_project_refresh = True
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if not self._dragging or self.editor.current_tool != "POINTER":
            event.ignore()
            return

        sp = event.scenePos()
        at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
        at_beats = max(0.0, min(float(self.editor._clip_len_beats), float(at_beats)))

        # snap unless Shift
        mods = event.modifiers()
        if not (mods & Qt.KeyboardModifier.ShiftModifier):
            q = float(self.editor._snap_quantum_beats())
            at_beats = round(at_beats / q) * q
            at_beats = max(0.0, min(float(self.editor._clip_len_beats), float(at_beats)))

        # y -> normalized value
        h = max(1.0, float(self._height))
        v = max(0.0, min(1.0, 1.0 - (float(sp.y()) / h)))

        # visual only during drag
        self.beat = float(at_beats)
        self.value = float(v)
        self._sync_pos()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        if not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self.editor._suppress_project_refresh = False

        try:
            self.editor._commit_automation_point_move(self.param, float(self._orig_beat), float(self.beat), float(self.value))
        except Exception:
            pass
        event.accept()

    def paint(self, painter: QPainter, option, widget=None):  # noqa: ANN001
        painter.save()
        painter.setBrush(self._brush)
        painter.setPen(self._pen_sel if self.isSelected() else self._pen)
        painter.drawRoundedRect(self.rect(), 2.0, 2.0)
        painter.restore()


class StretchWarpMarkerItem(QGraphicsRectItem):
    """Draggable warp marker (vertical orange line) for Stretch overlay."""

    def __init__(
        self,
        editor: "AudioEventEditor",
        *,
        clip_id: str,
        src_beat: float,
        dst_beat: float,
        px_per_beat: float,
        height: float,
        is_anchor: bool = False,
    ):
        self.editor = editor
        self.clip_id = str(clip_id)
        self.src_beat = float(src_beat)
        self.dst_beat = float(dst_beat)
        self._px_per_beat = float(px_per_beat)
        self._height = float(height)
        self.is_anchor = bool(is_anchor)
        self._w = 14.0
        super().__init__(QRectF(0.0, 0.0, self._w, float(height)))
        self.setZValue(30)
        self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._dragging = False
        self._orig_dst = float(dst_beat)
        self._sync_pos()

    def _sync_pos(self) -> None:
        x = float(self.dst_beat) * self._px_per_beat
        self.setPos(QPointF(x - self._w / 2.0, 0.0))

    def hoverEnterEvent(self, event):  # noqa: ANN001
        if not self.is_anchor and self.editor.current_tool == "POINTER" and self.editor._active_overlay == 'stretch':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # noqa: ANN001
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):  # noqa: ANN001
        if self.is_anchor:
            event.ignore()
            return
        if self.editor.current_tool != "POINTER" or self.editor._active_overlay != 'stretch':
            event.ignore()
            return
        if event.button() == Qt.MouseButton.RightButton:
            try:
                self.editor._remove_stretch_marker(float(self.dst_beat))
            except Exception:
                pass
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._orig_dst = float(self.dst_beat)
        self.editor._suppress_project_refresh = True
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if not self._dragging:
            event.ignore()
            return
        sp = event.scenePos()
        at_beats = float(sp.x() / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
        at_beats = max(0.0, min(float(self.editor._clip_len_beats), float(at_beats)))
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            q = float(self.editor._snap_quantum_beats())
            at_beats = round(at_beats / q) * q
            at_beats = max(0.0, min(float(self.editor._clip_len_beats), float(at_beats)))
        self.dst_beat = float(at_beats)
        self._sync_pos()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        if not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self.editor._suppress_project_refresh = False
        try:
            self.editor._commit_stretch_marker_move(float(self._orig_dst), float(self.dst_beat))
        except Exception:
            pass
        event.accept()

    def paint(self, painter: QPainter, option, widget=None):  # noqa: ANN001
        painter.save()
        # invisible hit rect
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())

        cx = self.rect().width() * 0.5
        # line
        col = QColor(255, 140, 0, 230 if not self.is_anchor else 120)
        pen = QPen(col)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawLine(QPointF(cx, 0.0), QPointF(cx, float(self._height)))

        # top handle triangle
        tri_size = 6.0
        poly = QPolygonF([
            QPointF(cx - tri_size, 0.0),
            QPointF(cx + tri_size, 0.0),
            QPointF(cx, tri_size * 1.6),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(col))
        painter.drawPolygon(poly)
        painter.restore()



class AudioEventEditor(QWidget):
    """Central widget shown in bottom editor area for audio clips."""

    status_message = pyqtSignal(str)

    def __init__(self, project_service, *, transport=None, editor_timeline=None, parent=None):
        super().__init__(parent)
        self.project = project_service
        self.transport = transport
        self._editor_timeline = editor_timeline  # v0.0.20.613: Dual-Clock Phase E

        # DAW-like clipboard + cursor for the Audio Editor (Ctrl+C/V/X/Delete)
        # Clipboard stores templates so paste works even after Cut.
        self._clipboard_templates: list[dict] = []
        self._cursor_beat: float = 0.0
        self._has_cursor: bool = False
        self._post_refresh_select_ids: set[str] = set()

        self._clip_id: str | None = None
        self._px_per_beat = 80.0
        self._last_adapter_beat: float = 0.0  # v0.0.20.613: Dual-Clock

        self._scene: BeatGridScene | None = None
        self.view: AudioEditorView | None = None
        self.ruler: AudioEditorRuler | None = None
        self.toolbar: QToolBar | None = None
        self.cmb_tool: QComboBox | None = None
        self.lbl_info: QLabel | None = None

        # Param controls (Gain/Pan/Pitch/Formant/Stretch)
        self.param_panel: QWidget | None = None
        self._param_spins: dict[str, QDoubleSpinBox] = {}
        self._param_labels: dict[str, QLabel] = {}
        self._suppress_param_signals = False
        self._show_onsets = False
        self._show_stretch = False
        self._stretch_items: list = []

        # Unified overlay mode: only ONE active at a time
        # Values: None, "stretch", "onsets", "gain", "pan", "pitch", "formant"
        self._active_overlay: str | None = None
        self._onset_items: list[QGraphicsLineItem] = []
        self._dup_drag_active = False
        self._dup_map: dict[str, str] = {}
        self._pending_dup_on_drag = False
        self._drag_base_item_ref: EventBlockItem | None = None

        self._wave_item: QGraphicsPathItem | None = None
        self._slice_items: list[QGraphicsLineItem] = []
        self._event_items: Dict[str, EventBlockItem] = {}
        self._selected_event_ids: Set[str] = set()

        # Waveform peaks cache (per source file)
        self._peaks_cache: Dict[str, PeaksCacheEntry] = {}

        self._loop_rect: QGraphicsRectItem | None = None
        self._loop_start_edge: _LoopEdge | None = None
        self._loop_end_edge: _LoopEdge | None = None

        # Fade overlays + handles
        self._fade_in_overlay: QGraphicsPathItem | None = None
        self._fade_out_overlay: QGraphicsPathItem | None = None
        self._fade_in_handle: _FadeHandle | None = None
        self._fade_out_handle: _FadeHandle | None = None
        self._fade_update_guard = False

        # Mute/Reverse overlays
        self._mute_overlay: QGraphicsRectItem | None = None
        self._mute_label: QGraphicsSimpleTextItem | None = None
        self._reverse_tint: QGraphicsRectItem | None = None

        self._drag_active = False
        self._drag_base_id: str | None = None
        self._drag_start_scene_x = 0.0
        self._drag_init_pos_px: Dict[str, float] = {}
        self._drag_applied_delta_px = 0.0

        self._clip_len_beats = 4.0
        self._clip_width_px = 800.0
        self._clip_height = 220.0

        self.current_tool = "ARROW"

        # Pencil tool state (clip automation envelopes)
        self._auto_param = "gain"  # current automation parameter for pencil
        self._auto_items: list = []  # rendered automation line items
        self._auto_point_items: list = []  # rendered breakpoint dots
        self._auto_drag_idx: int | None = None  # index of dragged breakpoint
        self._auto_drag_param: str = ""

        # Guards:
        # - _suppress_project_refresh: avoid full scene rebuild while we are actively dragging loop edges
        #   (project_updated is emitted synchronously and would otherwise call refresh() recursively).
        # - _loop_update_guard: prevent re-entrant setPos()/itemChange feedback loops.
        self._suppress_project_refresh = False
        self._loop_update_guard = False
        self._last_loop_pair: tuple[float, float] | None = None

        # When the user draws a loop beyond the current clip length, we temporarily
        # extend the editor's visible length (sceneRect) and commit the real clip
        # length on drag end.
        self._pending_resize_len_beats: float | None = None

        # Zoom-to-fit cache key: we must refit when clip length changes (not only clip id).
        self._last_fit_state: tuple[str | None, float] | None = None

        # Playhead (red line in scene, like Arranger)
        self._playhead_beat: float = 0.0
        self._playhead_line: QGraphicsLineItem | None = None
        # Cursor line (blue dashed, shows paste target position)
        self._cursor_line: QGraphicsLineItem | None = None

        self._build_ui()
        self._wire()

    def set_clip(self, clip_id: str | None) -> None:
        cid = str(clip_id or "").strip() if clip_id else ""
        self._clip_id = cid or None
        self.refresh()

    def refresh(self) -> None:
        scene = self._scene
        if scene is None:
            return

        prev_sel = set(self._selected_event_ids)
        scene.clear()

        self._wave_item = None
        self._slice_items = []
        self._onset_items = []
        self._event_items = {}
        self._selected_event_ids = set()

        self._loop_rect = None
        self._loop_start_edge = None
        self._loop_end_edge = None

        self._fade_in_overlay = None
        self._fade_out_overlay = None
        self._fade_in_handle = None
        self._fade_out_handle = None
        self._mute_overlay = None
        self._mute_label = None
        self._reverse_tint = None
        self._auto_items = []
        self._auto_point_items = []
        self._stretch_items = []

        clip = self._get_clip()

        # Ultra-Pro: one-shot selection coming from 'Back to Sources'
        try:
            pe = getattr(getattr(self.project, 'ctx', None), 'project', None)
            payload = getattr(pe, 'pending_event_select', None) if pe is not None else None
            if isinstance(payload, dict) and str(payload.get('clip_id', '')) == str(getattr(clip, 'id', '')):
                ids = payload.get('event_ids', [])
                if isinstance(ids, list) and ids:
                    self._post_refresh_select_ids = set(str(x) for x in ids)
                try:
                    setattr(pe, 'pending_event_select', None)
                except Exception:
                    pass
        except Exception:
            pass

        if not clip:
            scene.setSceneRect(QRectF(0, 0, 800, 220))
            t = scene.addText("Kein Audio-Clip ausgewählt.")
            t.setDefaultTextColor(self.palette().mid().color())
            return

        self._sync_param_controls(clip)

        length_beats = float(getattr(clip, "length_beats", 4.0) or 4.0)
        self._clip_len_beats = max(0.001, length_beats)
        self._clip_height = 220.0

        # --- Zoom-to-Fit: Calculate px_per_beat so the clip fills the editor width ---
        # This ensures automation lines, audio events, and waveform all align correctly.
        editor_width = max(800.0, float(self.view.viewport().width() if self.view else 800))
        self._px_per_beat = editor_width / self._clip_len_beats
        self._clip_width_px = self._clip_len_beats * self._px_per_beat

        scene.setSceneRect(QRectF(0, 0, self._clip_width_px, self._clip_height))
        scene.px_per_beat = self._px_per_beat  # sync grid rendering
        if self.view:
            self.view.set_clip_length(self._clip_len_beats)
            self.view._px_per_beat = self._px_per_beat  # sync zoom-to-fit
            # Reset view zoom when the clip OR its length changes.
            try:
                st = (self._clip_id, round(float(self._clip_len_beats), 6))
            except Exception:
                st = (self._clip_id, float(self._clip_len_beats))
            if getattr(self, '_last_fit_state', None) != st:
                self._last_fit_state = st
                self.view.resetTransform()
            # Keep view snapping in sync with global project grid.
            try:
                self.view.set_snap_quantum_beats(self._snap_quantum_beats())
            except Exception:
                pass

        # Waveform rendering:
        # We render waveforms **per AudioEvent** (child items) so moving/duplicating
        # events behaves like Bitwig/Ableton. A global background waveform would
        # stay at beat 0 and confuse users during event moves.
        path = getattr(clip, "source_path", None)
        if not (path and os.path.exists(path)):
            t = scene.addText("Audiofile fehlt (source_path).")
            t.setDefaultTextColor(self.palette().mid().color())

        # events
        try:
            evs = list(getattr(clip, "audio_events", []) or [])
        except Exception:
            evs = []
        if not evs:
            try:
                self.project._ensure_audio_events(clip)  # type: ignore[attr-defined]
                evs = list(getattr(clip, "audio_events", []) or [])
            except Exception:
                evs = []

        evs_sorted = sorted(evs, key=lambda x: float(getattr(x, "start_beats", 0.0) or 0.0))
        for i, e in enumerate(evs_sorted):
            try:
                eid = str(getattr(e, "id", ""))
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
            except Exception:
                continue
            if not eid or l <= 1e-6:
                continue
            item = EventBlockItem(
                self,
                event_id=eid,
                start_beats=s,
                length_beats=l,
                px_per_beat=self._px_per_beat,
                height=self._clip_height,
                alt_shade=(i % 2 == 0),
            )
            scene.addItem(item)
            self._event_items[eid] = item
            # Attach waveform preview INSIDE the event block (moves with it)
            try:
                self._attach_waveform_to_event(item, clip=clip, ev=e)
            except Exception:
                pass
            # Per-event reverse tint (orange overlay, v0.0.20.160)
            try:
                if bool(getattr(e, 'reversed', False)):
                    w = max(1.0, float(l) * self._px_per_beat)
                    r_tint = QGraphicsRectItem(QRectF(0.0, 0.0, w, self._clip_height), item)
                    r_tint.setBrush(QBrush(QColor(255, 140, 0, 40)))
                    r_tint.setPen(QPen(Qt.PenStyle.NoPen))
                    r_tint.setZValue(12)
                    r_tint.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            except Exception:
                pass

        # slices
        slices = list(getattr(clip, "audio_slices", []) or [])
        for s in slices:
            if not isinstance(s, (int, float)):
                continue
            x = float(s) * self._px_per_beat
            line = QGraphicsLineItem(x, 0.0, x, self._clip_height)
            pen = QPen(self.palette().highlight().color())
            try:
                c = pen.color()
                c.setAlpha(210)
                pen.setColor(c)
            except Exception:
                pass
            pen.setWidth(2)
            line.setPen(pen)
            line.setZValue(20)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            scene.addItem(line)
            self._slice_items.append(line)

        # Onset markers
        if bool(self._show_onsets):
            try:
                onsets = list(getattr(clip, 'onsets', []) or [])
            except Exception:
                onsets = []
            if onsets:
                try:
                    pen = QPen(self.palette().highlight().color())
                    pen.setWidthF(1.0)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    c = pen.color()
                    c.setAlpha(140)
                    pen.setColor(c)
                except Exception:
                    pen = QPen(Qt.GlobalColor.cyan)
                for ob in onsets:
                    try:
                        bx = float(ob) * float(self._px_per_beat)
                        ln = QGraphicsLineItem(bx, 0.0, bx, float(self._clip_height))
                        ln.setZValue(4)
                        ln.setPen(pen)
                        ln.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                        scene.addItem(ln)
                        self._onset_items.append(ln)
                    except Exception:
                        continue

        self._ensure_loop_items(clip, self._clip_width_px, self._clip_height)

        # --- Stretch warp markers (Bitwig-style, draggable) ---
        self._stretch_items = []
        if bool(self._show_stretch):
            try:
                L = float(self._clip_len_beats)
                raw = list(getattr(clip, 'stretch_markers', None) or [])

                # Coerce markers into dicts {src,dst}
                markers: list[dict] = []
                for mm in raw:
                    if isinstance(mm, dict):
                        try:
                            src = float(mm.get('src', mm.get('beat', 0.0)))
                            dst = float(mm.get('dst', mm.get('beat', src)))
                        except Exception:
                            continue
                        markers.append({'src': src, 'dst': dst})
                    elif isinstance(mm, (int, float)):
                        fv = float(mm)
                        markers.append({'src': fv, 'dst': fv})

                # Add anchors
                markers.append({'src': 0.0, 'dst': 0.0, 'anchor': True})
                markers.append({'src': L, 'dst': L, 'anchor': True})

                # Sort by src and remove duplicate src
                markers.sort(key=lambda x: float(x.get('src', 0.0)))
                dedup: list[dict] = []
                for mm in markers:
                    s = float(mm.get('src', 0.0))
                    if dedup and abs(float(dedup[-1].get('src', 0.0)) - s) < 1e-4:
                        dedup[-1] = mm
                    else:
                        dedup.append(mm)
                markers = dedup

                # Clamp dst to be monotonic (avoid crossings)
                outm: list[dict] = []
                eps = 0.02
                for i, mm in enumerate(markers):
                    s = max(0.0, min(L, float(mm.get('src', 0.0))))
                    d = max(0.0, min(L, float(mm.get('dst', s))))
                    lo = 0.0
                    hi = L
                    if outm:
                        lo = float(outm[-1].get('dst', 0.0)) + eps
                    if i < len(markers) - 1:
                        try:
                            hi = min(hi, float(markers[i + 1].get('dst', hi)) - eps)
                        except Exception:
                            pass
                    d = max(lo, min(hi, d))
                    outm.append({'src': s, 'dst': d, 'anchor': bool(mm.get('anchor', False))})

                # Force anchor endpoints exact
                outm[0]['src'] = 0.0
                outm[0]['dst'] = 0.0
                outm[0]['anchor'] = True
                outm[-1]['src'] = L
                outm[-1]['dst'] = L
                outm[-1]['anchor'] = True

                # Render markers
                for mm in outm:
                    dst = float(mm.get('dst', 0.0))
                    is_anchor = bool(mm.get('anchor', False))
                    it = StretchWarpMarkerItem(
                        self,
                        clip_id=str(getattr(self, '_clip_id', '') or ''),
                        src_beat=float(mm.get('src', 0.0)),
                        dst_beat=float(dst),
                        px_per_beat=float(self._px_per_beat),
                        height=float(self._clip_height),
                        is_anchor=bool(is_anchor),
                    )
                    scene.addItem(it)
                    self._stretch_items.append(it)

                # Info + Hint
                stretch_val = float(getattr(clip, 'stretch', 1.0) or 1.0)
                info_text = f"Stretch: ×{stretch_val:.2f}" if abs(stretch_val - 1.0) > 0.005 else "Stretch: ×1.00 (Normal)"
                info = QGraphicsSimpleTextItem(info_text)
                info.setZValue(52)
                info.setBrush(QBrush(QColor(255, 140, 0)))
                f = info.font()
                f.setPointSize(10)
                f.setBold(True)
                info.setFont(f)
                info.setPos(8, self._clip_height - 56)
                scene.addItem(info)
                self._stretch_items.append(info)

                hint = QGraphicsSimpleTextItem("Doppelklick: Warp-Marker | Ziehen: verschieben | Rechtsklick: löschen | Shift: kein Snap")
                hint.setZValue(52)
                hint.setBrush(QBrush(QColor(255, 140, 0, 160)))
                hf = hint.font()
                hf.setPointSize(8)
                hint.setFont(hf)
                hint.setPos(8, self._clip_height - 36)
                scene.addItem(hint)
                self._stretch_items.append(hint)

                hint2 = QGraphicsSimpleTextItem("Globaler Stretch: Stretch-SpinBox oben rechts")
                hint2.setZValue(52)
                hint2.setBrush(QBrush(QColor(255, 140, 0, 120)))
                hf2 = hint2.font()
                hf2.setPointSize(8)
                hint2.setFont(hf2)
                hint2.setPos(8, self._clip_height - 20)
                scene.addItem(hint2)
                self._stretch_items.append(hint2)

                # Highlight the stretch spinbox
                try:
                    sp = self._param_spins.get('Stretch')
                    if sp:
                        sp.setStyleSheet("QDoubleSpinBox { border: 2px solid #FF8C00; }")
                except Exception:
                    pass
            except Exception:
                pass
        else:
            # Remove stretch spinbox highlight when not in stretch mode
            try:
                sp = self._param_spins.get('Stretch')
                if sp:
                    sp.setStyleSheet("")
            except Exception:
                pass

        # --- Fade overlays + handles (Bitwig-style) ---
        self._render_fade_overlays(clip, self._clip_width_px, self._clip_height)

        # --- Reverse tint (orange overlay when reversed) ---
        if bool(getattr(clip, 'reversed', False)):
            try:
                r_rect = QGraphicsRectItem(QRectF(0.0, 0.0, self._clip_width_px, self._clip_height))
                r_rect.setZValue(11)
                r_rect.setBrush(QBrush(QColor(255, 140, 0, 25)))
                r_rect.setPen(QPen(Qt.PenStyle.NoPen))
                r_rect.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(r_rect)
                self._reverse_tint = r_rect
            except Exception:
                pass

        # --- Mute overlay ---
        if bool(getattr(clip, 'muted', False)):
            try:
                m_rect = QGraphicsRectItem(QRectF(0.0, 0.0, self._clip_width_px, self._clip_height))
                m_rect.setZValue(50)
                m_rect.setBrush(QBrush(QColor(0, 0, 0, 120)))
                m_rect.setPen(QPen(Qt.PenStyle.NoPen))
                m_rect.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(m_rect)
                self._mute_overlay = m_rect

                m_txt = QGraphicsSimpleTextItem("MUTED")
                m_txt.setZValue(51)
                m_txt.setBrush(QBrush(QColor(255, 80, 80)))
                f = m_txt.font()
                f.setPointSize(16)
                f.setBold(True)
                m_txt.setFont(f)
                m_txt.setPos(self._clip_width_px * 0.5 - 40, self._clip_height * 0.5 - 12)
                scene.addItem(m_txt)
                self._mute_label = m_txt
            except Exception:
                pass

        # --- Clip Automation Envelope (only when automation overlay is active) ---
        if self._active_overlay in ("gain", "pan", "pitch", "formant"):
            self._render_clip_automation(clip, self._clip_width_px, self._clip_height)

        for eid in prev_sel:
            it = self._event_items.get(eid)
            if it is not None:
                it.setSelected(True)
        self._selected_event_ids = set(prev_sel) & set(self._event_items.keys())

        # Post-refresh selection (used by Ctrl+V / Duplicate). This overrides the previous selection.
        try:
            wanted = set(getattr(self, '_post_refresh_select_ids', set()) or set())
        except Exception:
            wanted = set()
        if wanted:
            try:
                self._post_refresh_select_ids = set()
                try:
                    for it in (scene.selectedItems() if scene else []):
                        it.setSelected(False)
                except Exception:
                    pass
                for eid in wanted:
                    gi = self._event_items.get(str(eid))
                    if gi is not None:
                        gi.setSelected(True)
                self._selected_event_ids = set(wanted) & set(self._event_items.keys())
            except Exception:
                pass

        # Ruler repaint (bar display)
        try:
            if self.ruler is not None:
                self.ruler.update()
        except Exception:
            pass

        # --- Playhead line (red, like Arranger) ---
        try:
            self._playhead_line = None
            ph = float(self._playhead_beat)
            if ph >= 0 and self._px_per_beat > 0:
                x_ph = ph * self._px_per_beat
                line = QGraphicsLineItem(x_ph, 0.0, x_ph, self._clip_height)
                pen = QPen(QColor(220, 40, 40, 220))
                pen.setWidth(2)
                line.setPen(pen)
                line.setZValue(60)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(line)
                self._playhead_line = line
        except Exception:
            pass

        # --- Cursor line (blue dashed, paste target) ---
        try:
            self._cursor_line = None
            if self._has_cursor and self._px_per_beat > 0:
                x_cb = float(self._cursor_beat) * self._px_per_beat
                line = QGraphicsLineItem(x_cb, 0.0, x_cb, self._clip_height)
                pen = QPen(QColor(80, 160, 255, 160))
                pen.setWidth(1)
                pen.setStyle(Qt.PenStyle.DashLine)
                line.setPen(pen)
                line.setZValue(59)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(line)
                self._cursor_line = line
        except Exception:
            pass

        # Ensure playhead line exists after scene rebuild (important when transport is running)
        try:
            if self.transport is not None and clip is not None:
                self.set_playhead_beat(float(self._local_playhead_beats(clip)))
            else:
                self.set_playhead_beat(float(getattr(self, '_playhead_beat', 0.0) or 0.0))
        except Exception:
            pass

        if self.lbl_info:
            self.lbl_info.setText(
                f"Audio Clip: {self._clip_label_with_badges(clip)}   |   Gain {getattr(clip, 'gain', 1.0):0.2f}   Pan {getattr(clip, 'pan', 0.0):0.2f}   |   Events: {len(evs_sorted)}   |   Alt+Drag: Loop   Lasso: ziehen   Ctrl+C/V: Copy/Paste   Ctrl+D: Duplizieren   Ctrl+J: Consolidate   Shift+Ctrl+J: Trim   Alt+Ctrl+J: Handles   Ctrl+Shift+Alt+J: Join"
            )

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.lbl_info = QLabel("Audio Clip Editor")
        top.addWidget(self.lbl_info)
        top.addStretch(1)
        lay.addLayout(top)

        self.toolbar = QToolBar("Audio Tools")
        self.toolbar.setMovable(False)

        self.cmb_tool = QComboBox()
        self.cmb_tool.addItems(["Zeiger", "Arrow", "Knife", "Eraser", "Loop", "Lupe", "Pencil"])
        self.toolbar.addWidget(QLabel("Werkzeug: "))
        self.toolbar.addWidget(self.cmb_tool)
        self.toolbar.addSeparator()

        # Automation parameter selector (for Pencil tool)
        self.toolbar.addWidget(QLabel("Automation: "))
        self.cmb_auto_param = QComboBox()
        self.cmb_auto_param.addItems(["Gain", "Pan", "Pitch", "Formant"])
        self.cmb_auto_param.setFixedWidth(90)
        self.toolbar.addWidget(self.cmb_auto_param)
        self.toolbar.addSeparator()

        # Zoom controls
        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("🔍+")
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl+Wheel)")
        self.btn_zoom_in.setAutoRaise(True)
        self.toolbar.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("🔍−")
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+Wheel)")
        self.btn_zoom_out.setAutoRaise(True)
        self.toolbar.addWidget(self.btn_zoom_out)

        self.btn_zoom_fit = QToolButton()
        self.btn_zoom_fit.setText("⊞ Fit")
        self.btn_zoom_fit.setToolTip("Zoom to Fit (Clip füllt Editor)")
        self.btn_zoom_fit.setAutoRaise(True)
        self.toolbar.addWidget(self.btn_zoom_fit)
        self.toolbar.addSeparator()

        self._btns: dict[str, QToolButton] = {}
        # Overlay mode buttons: mutually exclusive (radio-button style)
        # Only ONE can be active at a time — its overlay is shown
        self._overlay_buttons = ["Stretch", "Onsets", "Gain", "Pan", "Pitch", "Formant"]
        for name in ["Audio Events", "Comping"] + self._overlay_buttons:
            b = QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setAutoRaise(True)
            self._btns[name] = b
            self.toolbar.addWidget(b)

        lay.addWidget(self.toolbar)

        # --- Parameter Inspector (Pro-DAW-like) ---
        self.param_panel = QWidget()
        self.param_panel.setObjectName('AudioParamPanel')
        ph = QHBoxLayout(self.param_panel)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(8)

        def _mk(name: str, mn: float, mx: float, step: float, dec: int, suffix: str = ''):
            lab = QLabel(name)
            sp = QDoubleSpinBox()
            sp.setRange(float(mn), float(mx))
            sp.setSingleStep(float(step))
            sp.setDecimals(int(dec))
            if suffix:
                sp.setSuffix(suffix)
            sp.setKeyboardTracking(False)  # avoid flooding during typing
            sp.setFixedWidth(110)
            self._param_labels[name] = lab
            self._param_spins[name] = sp
            ph.addWidget(lab)
            ph.addWidget(sp)

        _mk('Gain', 0.0, 4.0, 0.01, 2, '')
        _mk('Pan', -1.0, 1.0, 0.01, 2, '')
        _mk('Pitch', -24.0, 24.0, 0.10, 2, ' st')
        _mk('Formant', -24.0, 24.0, 0.10, 2, ' st')
        _mk('Stretch', 0.25, 4.0, 0.01, 2, '×')

        # v0.0.20.641: Stretch Mode ComboBox (AP3 Phase 3B)
        from PyQt6.QtWidgets import QComboBox as _QCB
        sm_lbl = QLabel("Mode:")
        sm_lbl.setStyleSheet("font-size: 9px; color: #aaa;")
        ph.addWidget(sm_lbl)
        self._stretch_mode_combo = _QCB()
        self._stretch_mode_combo.setFixedWidth(90)
        self._stretch_mode_combo.setFixedHeight(22)
        self._stretch_mode_combo.setStyleSheet("font-size: 9px;")
        self._stretch_mode_combo.addItem("Tones", "tones")
        self._stretch_mode_combo.addItem("Beats", "beats")
        self._stretch_mode_combo.addItem("Texture", "texture")
        self._stretch_mode_combo.addItem("Re-Pitch", "repitch")
        self._stretch_mode_combo.addItem("Complex", "complex")
        self._stretch_mode_combo.setToolTip(
            "Stretch Algorithm:\n"
            "Tones — Phase Vocoder (melodic material)\n"
            "Beats — Slice-based (drums, transient-heavy)\n"
            "Texture — Granular (ambient, pads)\n"
            "Re-Pitch — Resampling (changes pitch!)\n"
            "Complex — High-quality PV (CPU-intensive)"
        )
        self._stretch_mode_combo.currentIndexChanged.connect(self._on_stretch_mode_changed)
        ph.addWidget(self._stretch_mode_combo)

        ph.addStretch(1)
        lay.addWidget(self.param_panel)

        beats_per_bar = 4.0
        try:
            ts = getattr(self.project.ctx.project, "time_signature", "4/4")
            num, den = ts.split("/", 1)
            beats_per_bar = float(num) * (4.0 / float(den))
        except Exception:
            beats_per_bar = 4.0

        self._scene = BeatGridScene(beats_per_bar=beats_per_bar, px_per_beat=self._px_per_beat)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self.view = AudioEditorView(self._scene, px_per_beat=self._px_per_beat)
        # Backref so the view can forward keyboard shortcuts + cursor updates.
        try:
            self.view._editor_ref = self  # type: ignore[attr-defined]
        except Exception:
            pass

        # Bar/Beat ruler (Bitwig/Ableton-style)
        try:
            self.ruler = AudioEditorRuler(self)
            lay.addWidget(self.ruler)
        except Exception:
            self.ruler = None
        self.view.setMinimumHeight(240)
        lay.addWidget(self.view, 1)

    def _wire(self) -> None:
        if self.cmb_tool:
            self.cmb_tool.currentTextChanged.connect(self._on_tool_changed)

        # Param controls
        for _name, _sp in list(getattr(self, '_param_spins', {}).items()):
            try:
                _sp.valueChanged.connect(lambda _v, n=_name: self._on_param_changed(n, float(_v)))
            except Exception:
                pass

        # Toolbar button focus
        try:
            for _n in ['Gain', 'Pan', 'Pitch', 'Formant', 'Stretch', 'Onsets']:
                b = getattr(self, '_btns', {}).get(_n)
                if b is not None:
                    b.clicked.connect(lambda _chk=False, n=_n: self._on_param_button(n))
        except Exception:
            pass

        # Automation parameter selector
        try:
            if hasattr(self, 'cmb_auto_param') and self.cmb_auto_param:
                self.cmb_auto_param.currentTextChanged.connect(self._on_auto_param_changed)
        except Exception:
            pass

        # Zoom buttons
        try:
            self.btn_zoom_in.clicked.connect(self._on_zoom_in)
            self.btn_zoom_out.clicked.connect(self._on_zoom_out)
            self.btn_zoom_fit.clicked.connect(self._on_zoom_fit)
        except Exception:
            pass

        if self.view:
            self.view.request_slice.connect(self._on_slice_requested)
            self.view.request_remove_slice.connect(self._on_erase_requested)
            self.view.request_set_loop.connect(self._on_loop_dragged)
            self.view.context_action_selected.connect(self._on_context_action)

            # Pencil tool signals
            try:
                self.view.pencil_add_point.connect(self._on_pencil_add_point)
                self.view.pencil_remove_point.connect(self._on_pencil_remove_point)
                self.view.pencil_drag_point.connect(self._on_pencil_drag_point)
            except Exception:
                pass

            # Stretch/Warp markers (double-click)
            try:
                self.view.stretch_add_marker.connect(self._on_stretch_add_marker)
            except Exception:
                pass

            # Knife Cut+Drag
            try:
                self.view.request_slice_drag.connect(self._on_slice_drag_requested)
                self.view.knife_drag_update.connect(self._on_knife_drag_update)
                self.view.knife_drag_end.connect(self._on_knife_drag_end)
            except Exception:
                pass

            # Ruler repaint hooks (zoom/scroll)
            try:
                if self.ruler is not None:
                    self.view.view_changed.connect(self.ruler.update)
                    self.view.horizontalScrollBar().valueChanged.connect(lambda _v: self.ruler.update())
                    self.view.verticalScrollBar().valueChanged.connect(lambda _v: self.ruler.update())
                    # Ruler click-to-seek: move playhead + cursor
                    self.ruler.seek_requested.connect(self._on_ruler_seek)
            except Exception:
                pass

        try:
            self.project.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

        # Robust Ctrl+J variants (Clip-Launcher Audio Editor focus edge-cases)
        try:
            self._install_consolidate_shortcuts()
        except Exception:
            pass

        # Transport: keep Audio Editor playhead in sync with global transport
        # (Bitwig/Ableton-style: red playhead line runs in the clip editor while playing)
        # v0.0.20.613: Dual-Clock Phase E — Adapter hat Vorrang für playhead
        try:
            if self._editor_timeline is not None:
                self._editor_timeline.playhead_changed.connect(self._on_transport_playhead_changed)
            elif self.transport is not None:
                if hasattr(self.transport, 'playhead_changed'):
                    self.transport.playhead_changed.connect(self._on_transport_playhead_changed)
        except Exception:
            pass
        # playing_changed bleibt immer beim Transport (kein Adapter nötig)
        try:
            if self.transport is not None:
                if hasattr(self.transport, 'playing_changed'):
                    self.transport.playing_changed.connect(self._on_transport_playing_changed)
        except Exception:
            pass

    def _on_project_updated(self) -> None:
        """React to external project changes.

        We intentionally skip full refresh while loop handles are being dragged,
        because project_updated is emitted synchronously by ProjectService and a
        full scene rebuild during an itemChange() will crash Qt.
        """
        if self._suppress_project_refresh:
            return
        self.refresh()


    def _on_transport_playhead_changed(self, _beat: float) -> None:
        """Update local (clip) playhead from global transport tick.

        v0.0.20.613: _beat kommt jetzt vom EditorTimelineAdapter.
        Im Arranger-Modus ist das der globale Beat (Passthrough).
        Im Launcher-Modus ist das der lokale Slot-Beat.
        """
        self._last_adapter_beat = float(_beat)
        try:
            clip = self._get_clip()
            if clip and getattr(clip, "kind", "") == "audio":
                t = float(self._local_playhead_beats(clip))
                self.set_playhead_beat(float(t))
                return
        except Exception:
            pass
        try:
            self.set_playhead_beat(float(_beat))
        except Exception:
            pass

    def _on_transport_playing_changed(self, playing: bool) -> None:
        """Optional UI feedback when transport starts/stops."""
        try:
            if bool(playing):
                self.status_message.emit("▶ Playback (Audio Editor synced)")
            else:
                self.status_message.emit("■ Stop")
        except Exception:
            pass

    def _on_ruler_seek(self, beat: float) -> None:
        """Handle ruler click-to-seek: move playhead + cursor to beat position."""
        beat = max(0.0, float(beat))
        self.set_playhead_beat(beat)
        self.set_cursor_beat(beat)
        # Also inform transport if available
        try:
            if self.transport is not None and hasattr(self.transport, 'seek'):
                self.transport.seek(float(beat))
        except Exception:
            pass
        try:
            self.status_message.emit(f"Playhead → Beat {beat:.2f}")
        except Exception:
            pass

    # selection
    def _on_selection_changed(self) -> None:
        scene = self._scene
        if scene is None:
            return
        ids: Set[str] = set()
        for it in scene.selectedItems():
            if isinstance(it, EventBlockItem):
                ids.add(it.event_id)
        self._selected_event_ids = ids

    def _selected_event_ids_live(self) -> List[str]:
        """Return currently selected Event IDs (robust).

        We primarily track selection via _on_selection_changed(), but in some Qt
        focus/drag edge-cases (RubberBand selection, embedded Clip-Launcher editor)
        the cached set can be stale. This helper re-reads the scene selection.
        """
        ids: Set[str] = set(str(x) for x in (self._selected_event_ids or set()) if str(x))
        if not ids:
            try:
                sc = self._scene
                if sc is not None:
                    for it in sc.selectedItems():
                        if isinstance(it, EventBlockItem):
                            ids.add(str(getattr(it, 'event_id', '') or ''))
            except Exception:
                pass

        # Provide stable ordering by event start
        try:
            clip = self._get_clip()
            if clip is not None:
                evs = list(getattr(clip, 'audio_events', []) or [])
                start_map = {str(getattr(e, 'id', '')): float(getattr(e, 'start_beats', 0.0) or 0.0) for e in evs}
                return [x for x in sorted(ids, key=lambda k: start_map.get(str(k), 1e12)) if str(x).strip()]
        except Exception:
            pass
        return [x for x in list(ids) if str(x).strip()]

    def _do_consolidate_events(
        self,
        *,
        mode: str = 'bar',
        handles_beats: float = 0.0,
        tail_beats: float = 0.0,
        normalize: bool = False,
        join_keep_events: bool = False,
    ) -> None:
        """Consolidate helpers for Ctrl+J + context actions.

        IMPORTANT: This must stay UI-safe and MUST NOT break Ctrl+J.
        """
        clip = self._get_clip()
        if not clip or not self._clip_id:
            try:
                self.status_message.emit("Kein Audio-Clip ausgewählt")
            except Exception:
                pass
            return

        ids = self._selected_event_ids_live()
        if not ids:
            try:
                self.status_message.emit("Keine Events ausgewählt")
            except Exception:
                pass
            return

        # Join (keep events)
        if bool(join_keep_events):
            try:
                if hasattr(self.project, 'join_audio_events_to_new_clip'):
                    new_id = self.project.join_audio_events_to_new_clip(str(clip.id), list(ids))  # type: ignore[attr-defined]
                else:
                    new_id = None
                if new_id:
                    try:
                        self.project.select_clip(str(new_id))  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        self.status_message.emit(f"Clip erstellt aus {len(ids)} Events")
                    except Exception:
                        pass
                else:
                    try:
                        self.status_message.emit("Join nicht möglich")
                    except Exception:
                        pass
            except Exception:
                try:
                    self.status_message.emit("Join fehlgeschlagen")
                except Exception:
                    pass
            return

        # Default: Bounce consolidate
        try:
            new_id = None
            if hasattr(self.project, 'bounce_consolidate_audio_events_to_new_clip'):
                new_id = self.project.bounce_consolidate_audio_events_to_new_clip(
                    str(clip.id),
                    list(ids),
                    mode=str(mode),
                    handles_beats=float(handles_beats),
                    tail_beats=float(tail_beats),
                    normalize=bool(normalize),
                )  # type: ignore[attr-defined]
            if new_id:
                try:
                    self.project.select_clip(str(new_id))  # type: ignore[attr-defined]
                except Exception:
                    pass

                # friendly status
                try:
                    m = str(mode or 'bar').lower().strip()
                    if m == 'trim' and float(handles_beats) > 0:
                        self.status_message.emit(f"Audio TRIM + HANDLES (1 Clip aus {len(ids)} Events)")
                    elif m == 'trim':
                        self.status_message.emit(f"Audio TRIM (1 Clip aus {len(ids)} Events)")
                    elif float(handles_beats) > 0:
                        self.status_message.emit(f"Audio konsolidiert + HANDLES (1 Clip aus {len(ids)} Events)")
                    elif float(tail_beats) > 0:
                        self.status_message.emit(f"Audio konsolidiert + TAIL (1 Clip aus {len(ids)} Events)")
                    else:
                        self.status_message.emit(f"Audio konsolidiert (1 Clip aus {len(ids)} Events)")
                except Exception:
                    pass
            else:
                # Fallback: structural consolidate (only contiguous source chain)
                if hasattr(self.project, 'consolidate_audio_events'):
                    self.project.consolidate_audio_events(str(clip.id), list(ids))  # type: ignore[attr-defined]
                    try:
                        self.status_message.emit(f"Zusammengeführt ({len(ids)} Events)")
                    except Exception:
                        pass
        except Exception:
            try:
                self.status_message.emit("Zusammenführen fehlgeschlagen")
            except Exception:
                pass

    def _install_consolidate_shortcuts(self) -> None:
        """Ensure Ctrl+J variants work reliably inside the Audio Editor.

        Some desktop environments or focus edge-cases may prevent the QGraphicsView
        from receiving key events. These shortcuts are scoped to this editor widget
        (WidgetWithChildrenShortcut), so they won't affect other panels.
        """
        if getattr(self, '_consolidate_shortcuts_installed', False):
            return
        self._consolidate_shortcuts_installed = True
        self._shortcuts: list = []

        def _mk(seq: str, fn) -> None:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        # Defaults (keep existing behavior)
        _mk('Ctrl+J', lambda: self._do_consolidate_events(mode='bar'))
        _mk('Ctrl+Shift+J', lambda: self._do_consolidate_events(mode='trim'))
        _mk('Ctrl+Alt+J', lambda: self._do_consolidate_events(mode='bar', handles_beats=0.125))
        _mk('Ctrl+Shift+Alt+J', lambda: self._do_consolidate_events(join_keep_events=True))

    # --- DAW shortcuts helpers (Ctrl+C/V/X, Delete, Ctrl+D) ---

    def set_cursor_beat(self, beat: float) -> None:
        """Set the cursor (paste target) position and update visual."""
        self._cursor_beat = max(0.0, float(beat))
        self._has_cursor = True
        # Update cursor line position without full refresh
        try:
            if self._cursor_line and self._px_per_beat > 0:
                x = float(self._cursor_beat) * self._px_per_beat
                self._cursor_line.setLine(x, 0.0, x, self._clip_height)
            elif self._scene:
                # Create cursor line if it doesn't exist
                x = float(self._cursor_beat) * self._px_per_beat
                line = QGraphicsLineItem(x, 0.0, x, self._clip_height)
                pen = QPen(QColor(80, 160, 255, 160))
                pen.setWidth(1)
                pen.setStyle(Qt.PenStyle.DashLine)
                line.setPen(pen)
                line.setZValue(59)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._scene.addItem(line)
                self._cursor_line = line
        except Exception:
            pass
        try:
            if self.ruler:
                self.ruler.update()
        except Exception:
            pass

    def set_playhead_beat(self, beat: float) -> None:
        """Set the playhead position (red line) and update visual.

        This should be called from the transport timer during playback.
        Lightweight: only moves the existing line item, no full refresh.
        """
        self._playhead_beat = max(0.0, float(beat))
        try:
            if self._playhead_line and self._px_per_beat > 0:
                x = float(self._playhead_beat) * self._px_per_beat
                self._playhead_line.setLine(x, 0.0, x, self._clip_height)
            elif self._scene:
                x = float(self._playhead_beat) * self._px_per_beat
                line = QGraphicsLineItem(x, 0.0, x, self._clip_height)
                pen = QPen(QColor(220, 40, 40, 220))
                pen.setWidth(2)
                line.setPen(pen)
                line.setZValue(60)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._scene.addItem(line)
                self._playhead_line = line
        except Exception:
            pass
        try:
            if self.ruler:
                self.ruler.update()
        except Exception:
            pass

    def _cursor_or_transport_beat(self) -> float:
        """Best-effort paste target beat.

        Priority:
        1) user cursor (click in empty editor background)
        2) transport beat modulo clip length (useful when playing)
        3) 0.0
        """
        if bool(getattr(self, '_has_cursor', False)):
            return float(getattr(self, '_cursor_beat', 0.0) or 0.0)
        try:
            if self.transport is not None:
                cb = float(getattr(self.transport, 'current_beat', getattr(self.transport, 'beat', 0.0)) or 0.0)
                ln = float(getattr(self, '_clip_len_beats', 4.0) or 4.0)
                if ln > 1e-6:
                    return max(0.0, min(ln, cb % ln))
        except Exception:
            pass
        return 0.0

    def _collect_selected_event_templates(self) -> list[dict]:
        """Return templates for the currently selected AudioEvents."""
        clip = self._get_clip()
        if not clip:
            return []
        try:
            evs = list(getattr(clip, 'audio_events', []) or [])
        except Exception:
            evs = []
        wanted = set(str(x) for x in (self._selected_event_ids or set()) if str(x))
        if not wanted:
            return []
        out: list[dict] = []
        for e in evs:
            try:
                if str(getattr(e, 'id', '')) not in wanted:
                    continue
                out.append({
                    'start_beats': float(getattr(e, 'start_beats', 0.0) or 0.0),
                    'length_beats': float(getattr(e, 'length_beats', 0.0) or 0.0),
                    'source_offset_beats': float(getattr(e, 'source_offset_beats', 0.0) or 0.0),
                    'reversed': bool(getattr(e, 'reversed', False)),
                })
            except Exception:
                continue
        out.sort(key=lambda t: float(t.get('start_beats', 0.0) or 0.0))
        return out

    def handle_key_event(self, event: QKeyEvent) -> bool:
        """Handle standard DAW shortcuts in the Audio Editor.

        Returns True if handled.
        """
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # Ctrl+C
        if ctrl and key == Qt.Key.Key_C:
            templates = self._collect_selected_event_templates()
            if not templates:
                try:
                    self.status_message.emit('Keine Audio-Events ausgewählt')
                except Exception:
                    pass
                return True
            self._clipboard_templates = list(templates)
            try:
                self.status_message.emit(f"{len(templates)} Audio-Event(s) kopiert")
            except Exception:
                pass
            return True

        # Ctrl+X
        if ctrl and key == Qt.Key.Key_X:
            templates = self._collect_selected_event_templates()
            if not templates or not self._clip_id:
                try:
                    self.status_message.emit('Keine Audio-Events zum Ausschneiden')
                except Exception:
                    pass
                return True
            self._clipboard_templates = list(templates)
            try:
                self.project.delete_audio_events(str(self._clip_id), list(self._selected_event_ids), emit_updated=True)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self.status_message.emit(f"{len(templates)} Audio-Event(s) ausgeschnitten")
            except Exception:
                pass
            return True

        # Delete / Backspace
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if not self._clip_id or not self._selected_event_ids:
                return True
            try:
                self.project.delete_audio_events(str(self._clip_id), list(self._selected_event_ids), emit_updated=True)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self.status_message.emit('Audio-Event(s) gelöscht')
            except Exception:
                pass
            return True

        # Ctrl+V (Ctrl+Shift+V = paste without snap)
        if ctrl and key == Qt.Key.Key_V:
            if not self._clip_id:
                return True
            if not self._clipboard_templates:
                try:
                    self.status_message.emit('Zwischenablage ist leer')
                except Exception:
                    pass
                return True

            # determine paste target
            target = float(self._cursor_or_transport_beat())

            # optional snap
            if not shift:
                try:
                    q = float(self._snap_quantum_beats())
                    if q > 1e-9:
                        target = round(float(target) / q) * q
                except Exception:
                    pass

            # offset based on min template start
            try:
                min_s = min(float(t.get('start_beats', 0.0) or 0.0) for t in self._clipboard_templates)
            except Exception:
                min_s = 0.0
            delta = float(target) - float(min_s)

            try:
                new_ids = self.project.add_audio_events_from_templates(
                    str(self._clip_id),
                    list(self._clipboard_templates),
                    delta_beats=float(delta),
                    emit_updated=True,
                )  # type: ignore[attr-defined]
            except Exception:
                new_ids = []

            if new_ids:
                self._post_refresh_select_ids = set(str(x) for x in new_ids)
                try:
                    self.status_message.emit(f"{len(new_ids)} Audio-Event(s) eingefügt")
                except Exception:
                    pass
            return True

        # Ctrl+D (duplicate selected events to the right)
        if ctrl and key == Qt.Key.Key_D:
            if not self._clip_id or not self._selected_event_ids:
                return True
            templates = self._collect_selected_event_templates()
            if not templates:
                return True
            try:
                min_s = min(float(t.get('start_beats', 0.0) or 0.0) for t in templates)
                max_e = max(float(t.get('start_beats', 0.0) or 0.0) + float(t.get('length_beats', 0.0) or 0.0) for t in templates)
            except Exception:
                min_s, max_e = 0.0, 0.0
            span = max(0.25, float(max_e) - float(min_s))
            target = float(min_s) + float(span)
            try:
                q = float(self._snap_quantum_beats())
                if q > 1e-9:
                    target = round(float(target) / q) * q
            except Exception:
                pass
            delta = float(target) - float(min_s)
            try:
                new_ids = self.project.add_audio_events_from_templates(
                    str(self._clip_id),
                    list(templates),
                    delta_beats=float(delta),
                    emit_updated=True,
                )  # type: ignore[attr-defined]
            except Exception:
                new_ids = []
            if new_ids:
                self._post_refresh_select_ids = set(str(x) for x in new_ids)
                try:
                    self.status_message.emit('Audio-Event(s) dupliziert (Ctrl+D)')
                except Exception:
                    pass
            return True

        # Ctrl+A (select all audio events)
        if ctrl and key == Qt.Key.Key_A:
            try:
                if self._scene is not None:
                    self._scene.clearSelection()
                    for it in self._event_items.values():
                        try:
                            it.setSelected(True)
                        except Exception:
                            pass
                self._selected_event_ids = set(self._event_items.keys())
                return True
            except Exception:
                return True

        # Escape: clear selection
        if key == Qt.Key.Key_Escape:
            try:
                if self._scene is not None:
                    self._scene.clearSelection()
                self._selected_event_ids = set()
                return True
            except Exception:
                return True

        # Ctrl+J (Consolidate / Zusammenführen)
        # Pro-DAW-Style:
        # - Ctrl+J: Consolidate Time (bar-anchored, timing bleibt)
        # - Shift+Ctrl+J: Trim to Selection (ohne führende Stille)
        # - Alt+Ctrl+J: Consolidate + Handles (Edit-Handles im File, aber Timing bleibt via offset)
        # - Ctrl+Shift+Alt+J: Join to new Clip (Container, Events bleiben separat)
        if ctrl and key == Qt.Key.Key_J:
            try:
                # NOTE: Use robust selection (Clip-Launcher editor can have stale cached selection)
                join = bool(shift and alt)
                mode = 'trim' if bool(shift and not alt) else 'bar'
                handles = 0.125 if bool(alt and not join) else 0.0
                self._do_consolidate_events(
                    mode=str(mode),
                    handles_beats=float(handles),
                    tail_beats=0.0,
                    normalize=False,
                    join_keep_events=bool(join),
                )
            except Exception:
                try:
                    self.status_message.emit("Zusammenführen fehlgeschlagen")
                except Exception:
                    pass
            return True

        return False

    def _snap_quantum_beats(self) -> float:
        try:
            q = float(self.project.snap_quantum_beats())  # type: ignore[attr-defined]
            return max(1e-6, q)
        except Exception:
            return 0.25


    def _clip_label_with_badges(self, clip) -> str:  # noqa: ANN001
        """Label + Render-Badges (CONSOL/TRIM/+HANDLES/+TAIL) for quick visual feedback."""
        try:
            lab = str(getattr(clip, 'label', '') or '')
        except Exception:
            lab = ''
        try:
            rm = getattr(clip, 'render_meta', {})
            if isinstance(rm, dict):
                bs = rm.get('badges', [])
                if isinstance(bs, list) and bs:
                    bt = [str(x) for x in bs if str(x)]
                    if bt:
                        return lab + ' ' + ' '.join(f'[{b}]' for b in bt[:4])
        except Exception:
            pass
        return lab

    def _pick_cut_targets(self, clip, at_beats: float) -> List[str]:  # noqa: ANN001
        """Selection rules for Knife/Split.

        - If any *selected* event contains at_beats -> split those selected events.
        - Else split the event that contains at_beats ("under cursor").
        """
        try:
            t = float(at_beats)
        except Exception:
            return []

        try:
            evs = list(getattr(clip, "audio_events", []) or [])
        except Exception:
            evs = []
        if not evs:
            return []

        eps = 1e-6
        selected = set(self._selected_event_ids) if self._selected_event_ids else set()

        # First: selected events that contain t
        selected_hits: List[tuple[float, str]] = []
        hits: List[tuple[float, str]] = []
        for e in evs:
            try:
                eid = str(getattr(e, "id", ""))
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
            except Exception:
                continue
            if not eid or l <= eps:
                continue
            eend = s + l
            if (s - eps) <= t <= (eend + eps):
                hits.append((s, eid))
                if eid in selected:
                    selected_hits.append((s, eid))

        if selected_hits:
            # Return selected hits (sorted by start so result is stable)
            return [eid for _, eid in sorted(selected_hits, key=lambda x: x[0])]

        if hits:
            # If overlaps exist, pick the one with the latest start (closest/"top")
            hits.sort(key=lambda x: x[0])
            return [hits[-1][1]]

        return []

    # group drag
    def _begin_group_drag(self, base_item: EventBlockItem, scene_x: float, mods: Qt.KeyboardModifier | None = None, *, alt_duplicate: bool = False) -> None:
        if self._scene is None:
            return

        # Alt=Duplicate drag (Bitwig-style). Trigger immediately.
        try:
            if bool(alt_duplicate):
                self._dup_drag_active = True
                self._pending_dup_on_drag = False
                self._drag_base_item_ref = base_item
                self._begin_duplicate_drag(base_item, float(scene_x), mods)
                return
        except Exception:
            pass

        # Ctrl+Drag duplicate: arm duplication but trigger only once the user actually drags.
        try:
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier) if mods is not None else False
        except Exception:
            ctrl = False
        self._pending_dup_on_drag = bool(ctrl)
        self._dup_drag_active = False
        self._drag_base_item_ref = base_item
        sel = [it for it in self._scene.selectedItems() if isinstance(it, EventBlockItem)]
        if not sel:
            sel = [base_item]
        self._drag_active = True
        self._drag_base_id = base_item.event_id
        self._drag_start_scene_x = float(scene_x)
        self._drag_init_pos_px = {it.event_id: float(it.pos().x()) for it in sel}
        self._drag_applied_delta_px = 0.0

    
    def _begin_duplicate_drag(self, base_item: EventBlockItem, scene_x: float, mods: Qt.KeyboardModifier | None) -> None:
        """Alt=Duplicate: duplicate selected events and start dragging the duplicates."""
        if self._scene is None or not self._clip_id:
            return
        scene = self._scene
        sel_items = [it for it in scene.selectedItems() if isinstance(it, EventBlockItem)]
        if not sel_items:
            sel_items = [base_item]
        old_ids = [it.event_id for it in sel_items]

        # Duplicate in model (no immediate refresh to keep drag stable)
        try:
            self._suppress_project_refresh = True
            try:
                dup_map = self.project.duplicate_audio_events(self._clip_id, old_ids, emit_updated=True)  # type: ignore[attr-defined]
            finally:
                self._suppress_project_refresh = False
            if not isinstance(dup_map, dict) or not dup_map:
                return
        except Exception:
            return

        self._dup_map = {str(k): str(v) for k, v in dup_map.items() if str(k) and str(v)}
        new_ids = [self._dup_map.get(oid) for oid in old_ids if self._dup_map.get(oid)]
        if not new_ids:
            return

        # Create new graphics items for duplicates without full refresh
        clip = self._get_clip()
        if not clip:
            return
        try:
            evs = list(getattr(clip, 'audio_events', []) or [])
        except Exception:
            evs = []
        by_id = {str(getattr(e, 'id', '')): e for e in evs}

        # Deselect originals
        for it in sel_items:
            try:
                it.setSelected(False)
            except Exception:
                pass

        created: list[EventBlockItem] = []
        shade_toggle = False
        for oid in old_ids:
            nid = self._dup_map.get(str(oid))
            if not nid:
                continue
            e = by_id.get(str(nid))
            if e is None:
                continue
            try:
                start_b = float(getattr(e, 'start_beats', 0.0) or 0.0)
                len_b = float(getattr(e, 'length_beats', 0.0) or 0.0)
                it = EventBlockItem(self, event_id=str(nid), start_beats=start_b, length_beats=len_b, px_per_beat=self._px_per_beat, height=self._clip_height, alt_shade=shade_toggle)
                shade_toggle = not shade_toggle
                scene.addItem(it)
                self._event_items[str(nid)] = it
                created.append(it)
                try:
                    self._attach_waveform_to_event(it, clip=clip, ev=e)
                except Exception:
                    pass
                it.setSelected(True)
            except Exception:
                continue

        if not created:
            return

        # Start drag with duplicates selected
        self._selected_event_ids = set(new_ids)
        base_new = self._dup_map.get(str(base_item.event_id), str(new_ids[0]))
        base_it = self._event_items.get(str(base_new))
        if base_it is None:
            base_it = created[0]

        # init drag state
        self._drag_active = True
        self._drag_base_id = str(base_it.event_id)
        self._drag_start_scene_x = float(scene_x)
        self._drag_init_pos_px = {it.event_id: float(it.pos().x()) for it in created if it.isSelected()}
        self._drag_applied_delta_px = 0.0

    def _update_group_drag(self, scene_x: float, mods: Qt.KeyboardModifier) -> None:
        if not self._drag_active or not self._drag_init_pos_px:
            return
        desired_delta_px = float(scene_x) - float(self._drag_start_scene_x)

        # Ctrl+Drag duplicate (requested UX): trigger duplication once user actually drags.
        try:
            if (not bool(getattr(self, '_dup_drag_active', False))) and bool(getattr(self, '_pending_dup_on_drag', False)):
                if bool(mods & Qt.KeyboardModifier.ControlModifier) and abs(float(desired_delta_px)) >= 4.0:
                    base_it = getattr(self, '_drag_base_item_ref', None)
                    if base_it is None and self._drag_base_id:
                        base_it = self._event_items.get(str(self._drag_base_id))
                    if base_it is not None:
                        self._dup_drag_active = True
                        self._pending_dup_on_drag = False
                        # Start duplicate drag at the original press position so delta stays continuous.
                        self._begin_duplicate_drag(base_it, float(self._drag_start_scene_x), mods)
                        # recompute delta after duplication setup
                        desired_delta_px = float(scene_x) - float(self._drag_start_scene_x)
        except Exception:
            pass

        snap_enabled = not bool(mods & Qt.KeyboardModifier.ShiftModifier)
        delta_px = desired_delta_px

        if snap_enabled and self._drag_base_id and self._drag_base_id in self._drag_init_pos_px:
            q = self._snap_quantum_beats()
            init_x = self._drag_init_pos_px[self._drag_base_id]
            desired_base = init_x + desired_delta_px
            desired_beats = desired_base / self._px_per_beat
            snapped_beats = round(desired_beats / q) * q
            snapped_base = snapped_beats * self._px_per_beat
            delta_px = snapped_base - init_x

        min_init = min(self._drag_init_pos_px.values())
        max_init_end = 0.0
        for eid, ix in self._drag_init_pos_px.items():
            it = self._event_items.get(eid)
            if it is None:
                continue
            max_init_end = max(max_init_end, ix + it.rect().width())

        delta_min = -min_init
        delta_max = self._clip_width_px - max_init_end
        if delta_px < delta_min:
            delta_px = delta_min
        if delta_px > delta_max:
            delta_px = delta_max

        for eid, ix in self._drag_init_pos_px.items():
            it = self._event_items.get(eid)
            if it is None:
                continue
            it.setPos(QPointF(ix + delta_px, 0.0))

        self._drag_applied_delta_px = float(delta_px)

    def _end_group_drag(self) -> None:
        if not self._drag_active:
            return
        self._drag_active = False

        # reset duplicate-drag state
        try:
            self._pending_dup_on_drag = False
            self._dup_drag_active = False
            self._drag_base_item_ref = None
        except Exception:
            pass

        if not self._clip_id or not self._drag_init_pos_px:
            self._drag_init_pos_px = {}
            self._drag_base_id = None
            return

        delta_beats = float(self._drag_applied_delta_px / self._px_per_beat) if self._px_per_beat > 1e-6 else 0.0
        if abs(delta_beats) < 1e-6:
            self._drag_init_pos_px = {}
            self._drag_base_id = None
            return

        try:
            ids = list(self._drag_init_pos_px.keys())
            self.project.move_audio_events(self._clip_id, ids, delta_beats)  # type: ignore[attr-defined]
        except Exception:
            pass

        self._drag_init_pos_px = {}
        self._drag_base_id = None


    # --- Param Inspector handlers ---
    def _on_param_button(self, name: str) -> None:
        n = str(name or '').strip()

        # Overlay buttons are mutually exclusive (radio-button behavior)
        overlay_names = getattr(self, '_overlay_buttons', ["Stretch", "Onsets", "Gain", "Pan", "Pitch", "Formant"])
        if n in overlay_names:
            mode = n.lower()
            if self._active_overlay == mode:
                # Toggle off: deactivate overlay
                self._activate_overlay(None)
            else:
                # Activate this overlay
                self._activate_overlay(mode)
            self.refresh()
            return

        # Non-overlay buttons (Audio Events, Comping)
        sp = self._param_spins.get(n)
        if sp is not None:
            try:
                sp.setFocus()
                sp.selectAll()
            except Exception:
                pass

    def _on_auto_param_changed(self, text: str) -> None:
        """Handle automation parameter selector change — also activates overlay."""
        mode = str(text or "Gain").strip().lower()
        if mode in ("gain", "pan", "pitch", "formant"):
            self._activate_overlay(mode)
        self.refresh()

    def _on_zoom_in(self) -> None:
        """Zoom in (increase scale)."""
        if self.view:
            self.view.scale(1.3, 1.0)
            try:
                self.view.view_changed.emit()
            except Exception:
                pass

    def _on_zoom_out(self) -> None:
        """Zoom out (decrease scale)."""
        if self.view:
            self.view.scale(1 / 1.3, 1.0)
            try:
                self.view.view_changed.emit()
            except Exception:
                pass

    def _on_zoom_fit(self) -> None:
        """Reset zoom to fit entire clip in editor width."""
        if self.view:
            self._last_fit_clip_id = None  # force re-fit
            self.refresh()

    def _activate_overlay(self, mode: str | None) -> None:
        """Set the active overlay mode and sync all UI state.

        mode: None, "stretch", "onsets", "gain", "pan", "pitch", "formant"
        """
        self._active_overlay = mode
        self._show_onsets = (mode == "onsets")
        self._show_stretch = (mode == "stretch")
        if mode in ("gain", "pan", "pitch", "formant"):
            self._auto_param = mode
            try:
                self.cmb_auto_param.blockSignals(True)
                self.cmb_auto_param.setCurrentText(mode.capitalize())
                self.cmb_auto_param.blockSignals(False)
            except Exception:
                pass
        # Sync button checked states
        overlay_names = getattr(self, '_overlay_buttons', [])
        for bname in overlay_names:
            b = self._btns.get(bname)
            if b:
                b.blockSignals(True)
                b.setChecked(bname.lower() == (mode or ""))
                b.blockSignals(False)

    def _on_pencil_add_point(self, at_beats: float, norm_val: float) -> None:
        """Add an automation breakpoint at cursor position (Pencil tool)."""
        # Only allow drawing when an automation overlay is active
        if self._active_overlay not in ("gain", "pan", "pitch", "formant"):
            return
        clip = self._get_clip()
        if not clip or not self._clip_id:
            return
        param = str(self._auto_param or "gain").lower()
        try:
            self._suppress_project_refresh = True
            self.project.add_clip_automation_point(str(self._clip_id), param, float(at_beats), float(norm_val))
        except Exception:
            pass
        finally:
            self._suppress_project_refresh = False
        self._refresh_automation_only()
        try:
            self.status_message.emit(f"Automation: {param} @ {at_beats:.2f} = {norm_val:.2f}")
        except Exception:
            pass

    def _on_pencil_remove_point(self, at_beats: float) -> None:
        """Remove automation breakpoint near cursor (right-click in Pencil mode)."""
        if self._active_overlay not in ("gain", "pan", "pitch", "formant"):
            return
        if not self._clip_id:
            return
        param = str(self._auto_param or "gain").lower()
        try:
            self.project.remove_clip_automation_point(str(self._clip_id), param, float(at_beats))
        except Exception:
            pass
        self._refresh_automation_only()

    def _on_pencil_drag_point(self, at_beats: float, norm_val: float) -> None:
        """Continuous drawing: add/update points while dragging (Pencil tool).
        
        Throttled to ~15fps to prevent UI freeze during live drawing.
        """
        if self._active_overlay not in ("gain", "pan", "pitch", "formant"):
            return
        if not self._clip_id:
            return
        param = str(self._auto_param or "gain").lower()
        try:
            # Snap to grid for cleaner automation
            q = self._snap_quantum_beats()
            at_snapped = round(float(at_beats) / q) * q
            self._suppress_project_refresh = True
            self.project.add_clip_automation_point(str(self._clip_id), param, float(at_snapped), float(norm_val))
        except Exception:
            pass
        finally:
            self._suppress_project_refresh = False
        # Throttle refresh during drag: max ~15 fps
        import time as _time
        now = _time.monotonic()
        last = getattr(self, '_pencil_last_refresh', 0.0)
        if (now - last) >= 0.065:  # ~15fps
            self._pencil_last_refresh = now
            self._refresh_automation_only()
        else:
            # Schedule final refresh when drag ends
            if not getattr(self, '_pencil_refresh_pending', False):
                self._pencil_refresh_pending = True
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(70, self._pencil_deferred_refresh)

    def _pencil_deferred_refresh(self) -> None:
        """Deferred refresh after pencil drag stops."""
        self._pencil_refresh_pending = False
        self._refresh_automation_only()

    def _refresh_automation_only(self) -> None:
        """Lightweight refresh: only re-render automation lines without rebuilding scene."""
        clip = self._get_clip()
        if not clip:
            self.refresh()
            return
        scene = self.view.scene() if self.view else None
        if not scene:
            self.refresh()
            return
        # Remove old automation items (lines + dots)
        for item in list(getattr(self, '_auto_items', [])):
            try:
                scene.removeItem(item)
            except Exception:
                pass
        for item in list(getattr(self, '_auto_point_items', [])):
            try:
                scene.removeItem(item)
            except Exception:
                pass
        self._auto_items = []
        self._auto_point_items = []
        # Re-render automation overlay only
        try:
            self._render_clip_automation(clip, self._clip_width_px, self._clip_height)
        except Exception:
            pass



    # --- Zeiger/Pointer: move/delete automation points ---

    def _commit_automation_point_move(self, param: str, old_beat: float, new_beat: float, value: float) -> None:
        if not self._clip_id:
            return
        if self._active_overlay not in ("gain", "pan", "pitch", "formant"):
            return
        p = str(param or '').strip().lower()
        if p not in ("gain", "pan", "pitch", "formant"):
            return
        # snap for stable editing
        q = self._snap_quantum_beats()
        nb = round(float(new_beat) / q) * q
        nb = max(0.0, min(float(self._clip_len_beats), float(nb)))
        vv = max(0.0, min(1.0, float(value)))
        try:
            self._suppress_project_refresh = True
            self.project.move_clip_automation_point(str(self._clip_id), p, float(old_beat), float(nb), float(vv))  # type: ignore[attr-defined]
        except Exception:
            pass
        finally:
            self._suppress_project_refresh = False
        self._refresh_automation_only()

    def _remove_automation_point(self, param: str, beat: float) -> None:
        if not self._clip_id:
            return
        p = str(param or '').strip().lower()
        if p not in ("gain", "pan", "pitch", "formant"):
            return
        try:
            self.project.remove_clip_automation_point(str(self._clip_id), p, float(beat))  # type: ignore[attr-defined]
        except Exception:
            pass
        self._refresh_automation_only()

    # --- Stretch/Warp markers ---

    def _on_stretch_add_marker(self, at_beats: float) -> None:
        if self._active_overlay != 'stretch':
            return
        if not self._clip_id:
            return
        q = self._snap_quantum_beats()
        b = round(float(at_beats) / q) * q
        b = max(0.0, min(float(self._clip_len_beats), float(b)))
        try:
            self.project.add_stretch_marker(str(self._clip_id), float(b))  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh()

    def _commit_stretch_marker_move(self, old_dst: float, new_dst: float) -> None:
        if self._active_overlay != 'stretch':
            return
        if not self._clip_id:
            return
        try:
            self.project.move_stretch_marker(str(self._clip_id), float(old_dst), float(new_dst))  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh()

    def _remove_stretch_marker(self, dst_beat: float) -> None:
        if self._active_overlay != 'stretch':
            return
        if not self._clip_id:
            return
        try:
            self.project.remove_stretch_marker(str(self._clip_id), float(dst_beat))  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh()
    def _sync_param_controls(self, clip) -> None:  # noqa: ANN001
        if not self._param_spins:
            return
        self._suppress_param_signals = True
        try:
            def _set(name: str, v: float):
                sp = self._param_spins.get(name)
                if sp is None:
                    return
                try:
                    sp.blockSignals(True)
                    sp.setValue(float(v))
                finally:
                    sp.blockSignals(False)

            _set('Gain', float(getattr(clip, 'gain', 1.0) or 1.0))
            _set('Pan', float(getattr(clip, 'pan', 0.0) or 0.0))
            _set('Pitch', float(getattr(clip, 'pitch', 0.0) or 0.0))
            _set('Formant', float(getattr(clip, 'formant', 0.0) or 0.0))
            _set('Stretch', float(getattr(clip, 'stretch', 1.0) or 1.0))

            # v0.0.20.641: Sync stretch mode combo (AP3 Phase 3B)
            try:
                _smc = getattr(self, '_stretch_mode_combo', None)
                if _smc is not None:
                    _smc.blockSignals(True)
                    _sm = str(getattr(clip, 'stretch_mode', 'tones') or 'tones')
                    _modes = {'tones': 0, 'beats': 1, 'texture': 2, 'repitch': 3, 'complex': 4}
                    _smc.setCurrentIndex(_modes.get(_sm, 0))
                    _smc.blockSignals(False)
            except Exception:
                pass
        finally:
            self._suppress_param_signals = False

    def _on_param_changed(self, name: str, value: float) -> None:
        if self._suppress_param_signals or not self._clip_id:
            return
        clip = self._get_clip()
        if not clip:
            return
        # Clamp + dispatch to ProjectService (single source of truth)
        kwargs = {}
        n = str(name or '').strip().lower()
        try:
            if n == 'gain':
                kwargs['gain'] = max(0.0, float(value))
            elif n == 'pan':
                kwargs['pan'] = max(-1.0, min(1.0, float(value)))
            elif n == 'pitch':
                kwargs['pitch'] = float(value)
            elif n == 'formant':
                kwargs['formant'] = float(value)
            elif n == 'stretch':
                kwargs['stretch'] = max(0.01, float(value))
            else:
                return
        except Exception:
            return

        # Avoid full scene rebuild on every knob step in this editor only.
        self._suppress_project_refresh = True
        try:
            self.project.update_audio_clip_params(self._clip_id, **kwargs)  # type: ignore[attr-defined]
        except Exception:
            pass
        finally:
            self._suppress_project_refresh = False

        # Update info label quickly (no rebuild).
        try:
            if self.lbl_info:
                self.lbl_info.setText(
                    f"Audio Clip: {self._clip_label_with_badges(clip)}   |   Gain {getattr(clip, 'gain', 1.0):0.2f}   Pan {getattr(clip, 'pan', 0.0):0.2f}   |   Events: {len(getattr(clip, 'audio_events', []) or [])}"
                )
        except Exception:
            pass

    def _on_stretch_mode_changed(self, index: int) -> None:
        """Handle stretch mode ComboBox change (AP3 Phase 3B)."""
        if self._suppress_param_signals or not self._clip_id:
            return
        clip = self._get_clip()
        if not clip:
            return
        try:
            mode = str(self._stretch_mode_combo.itemData(index) or "tones")
            clip.stretch_mode = mode
            self.project.mark_dirty()
            try:
                self.status_message.emit(f"Stretch-Modus: {mode}")
            except Exception:
                pass
        except Exception:
            pass

    def _cancel_group_drag_visual(self) -> None:
        """Cancel an in-progress group drag without committing to the model.

        Used when an AudioEvent drag is turned into an export drag (QDrag) towards the Arranger.
        """
        try:
            if not self._drag_active:
                return
            for eid, x in (self._drag_init_pos_px or {}).items():
                it = self._event_items.get(eid)
                if it is not None:
                    try:
                        it.setPos(QPointF(float(x), 0.0))
                    except Exception:
                        pass
        except Exception:
            pass
        self._drag_active = False
        self._drag_base_id = None
        self._drag_start_scene_x = 0.0
        self._drag_init_pos_px = {}
        self._drag_applied_delta_px = 0.0

    def _start_export_drag_to_arranger(self, event_ids: List[str]) -> None:
        """Export selected AudioEvent(s) as a drag payload to the Arranger.

        The Arranger will create a new audio clip from these events (non-destructive).
        """
        if not self._clip_id or self.view is None:
            return
        ids = [str(x) for x in (event_ids or []) if str(x).strip()]
        if not ids:
            return
        try:
            payload = {
                'clip_id': str(self._clip_id),
                'event_ids': ids,
            }
            md = QMimeData()
            md.setData(MIME_AUDIOEVENT_SLICE, json.dumps(payload).encode('utf-8'))
            drag = QDrag(self.view.viewport())
            drag.setMimeData(md)
            try:
                drag.setHotSpot(self.view.mapFromGlobal(QCursor.pos()))
            except Exception:
                pass
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            return

    # tools
    def _on_tool_changed(self, text: str) -> None:
        t = (text or "").strip().upper()
        if t.startswith("ZE"):
            self.current_tool = "POINTER"
        elif t.startswith("AR"):
            self.current_tool = "ARROW"
        elif t.startswith("KN"):
            self.current_tool = "KNIFE"
        elif t.startswith("ER"):
            self.current_tool = "ERASE"
        elif t.startswith("PE"):
            self.current_tool = "PENCIL"
        elif t.startswith("LU") or t.startswith("ZO"):
            self.current_tool = "ZOOM"
        else:
            self.current_tool = "TIME"

        if self.view:
            self.view.set_tool(self.current_tool)

    def _knife_target_event_ids(self, clip, at_beats: float) -> List[str]:  # noqa: ANN001
        """Selection rules for Knife:

        - If selected events exist and one or more selected events contain the cut time,
          ONLY those selected events are cut.
        - Otherwise, cut the (first) event under the cursor/playhead.

        Returns a list (possibly empty) of eligible AudioEvent ids.
        """
        try:
            t = float(at_beats)
        except Exception:
            return []

        # Ensure events exist
        try:
            evs = list(getattr(clip, "audio_events", []) or [])
        except Exception:
            evs = []
        if not evs:
            try:
                self.project._ensure_audio_events(clip)  # type: ignore[attr-defined]
                evs = list(getattr(clip, "audio_events", []) or [])
            except Exception:
                evs = []
        if not evs:
            return []

        eps = 1e-6
        containing = []
        for e in evs:
            try:
                eid = str(getattr(e, "id", ""))
                s = float(getattr(e, "start_beats", 0.0) or 0.0)
                l = float(getattr(e, "length_beats", 0.0) or 0.0)
            except Exception:
                continue
            if not eid or l <= eps:
                continue
            end = s + l
            if (s - eps) <= t <= (end + eps):
                containing.append((s, eid))

        if not containing:
            return []

        sel = set(self._selected_event_ids) if self._selected_event_ids else set()
        if sel:
            sel_hits = [eid for _, eid in containing if eid in sel]
            if sel_hits:
                return sel_hits

        # no selected hit: return the event with the latest start (best match for overlaps)
        containing.sort(key=lambda x: float(x[0]))
        return [containing[-1][1]]

    def _right_ids_from_split(self, new_sel: list[str]) -> list[str]:
        """Selection policy after Knife: select only right-part(s).

        ProjectService.split_audio_events_at returns [left,right] per split.
        For multi-split, list is [L1,R1,L2,R2,...].
        """
        if not new_sel:
            return []
        if len(new_sel) >= 2:
            rights = [str(new_sel[i]) for i in range(1, len(new_sel), 2)]
            return [r for r in rights if r]
        return [str(new_sel[0])]

    def _on_slice_drag_requested(self, at_beats: float, press_scene_x: float) -> None:
        """Knife Cut+Drag: split then immediately start group-drag of right-part(s).

        press_scene_x is the mouse position in scene coordinates at press time.
        """
        clip = self._get_clip()
        if not clip or getattr(clip, 'kind', '') != 'audio':
            return
        ids = self._knife_target_event_ids(clip, float(at_beats))
        if not ids:
            return
        prev = bool(self._suppress_project_refresh)
        self._suppress_project_refresh = True
        new_sel: list[str] = []
        try:
            if hasattr(self.project, 'split_audio_events_at'):
                new_sel = list(self.project.split_audio_events_at(str(clip.id), float(at_beats), event_ids=list(ids)))  # type: ignore[attr-defined]
            else:
                self.project.split_audio_event(str(clip.id), float(at_beats))
        except Exception:
            new_sel = []
        finally:
            self._suppress_project_refresh = prev

        right_ids = self._right_ids_from_split(new_sel)
        if right_ids:
            self._selected_event_ids = set(right_ids)
        self.refresh()

        # Start drag on the right-part closest to the cut position.
        if not right_ids:
            return
        base_item = None
        best_d = None
        for rid in right_ids:
            it = self._event_items.get(rid)
            if it is None:
                continue
            d = abs(float(it.start_beats()) - float(at_beats))
            if best_d is None or d < best_d:
                best_d = d
                base_item = it
        if base_item is None:
            base_item = self._event_items.get(right_ids[0])
        if base_item is None:
            return
        # Begin group drag with current selection (right parts).
        self._begin_group_drag(base_item, float(press_scene_x))

    def _on_knife_drag_update(self, scene_x: float, modifiers_int: int) -> None:
        if not self._drag_active:
            return
        try:
            mods = Qt.KeyboardModifier(int(modifiers_int))
        except Exception:
            mods = Qt.KeyboardModifier.NoModifier
        self._update_group_drag(float(scene_x), mods)

    def _on_knife_drag_end(self) -> None:
        self._end_group_drag()

    def _on_slice_requested(self, at_beats: float) -> None:
        clip = self._get_clip()
        # --- Ultra-Pro actions (render_meta) ---
        if a == "Re-render (in place)":
            try:
                if hasattr(self.project, 'rerender_clip_in_place_from_meta'):
                    ok = self.project.rerender_clip_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Re-rendered (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render in place fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render in place fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Restore Sources (in place)":
            try:
                if hasattr(self.project, 'restore_sources_in_place_from_meta'):
                    ok = self.project.restore_sources_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Sources restored (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Restore sources fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Restore sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Re-render (from sources)":
            try:
                if hasattr(self.project, 'rerender_clip_from_meta'):
                    nid = self.project.rerender_clip_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if nid:
                        try:
                            self.status_message.emit('Re-rendered (Ultra-Pro)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Back to Sources":
            try:
                if hasattr(self.project, 'back_to_sources_from_meta'):
                    sid = self.project.back_to_sources_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if sid:
                        try:
                            self.status_message.emit('Back to sources')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Keine Source-Meta gefunden')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Back to sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Toggle Rendered ↔ Sources":
            try:
                if hasattr(self.project, 'toggle_rendered_sources_in_place_from_meta'):
                    ok = self.project.toggle_rendered_sources_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Toggled rendered/source')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Toggle fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Toggle fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Rebuild original clip state":
            try:
                if hasattr(self.project, 'rebuild_original_clip_state_from_meta'):
                    ok = self.project.rebuild_original_clip_state_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Original state rebuilt')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Rebuild fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Rebuild fehlgeschlagen')
                except Exception:
                    pass
            return

        if not clip or getattr(clip, "kind", "") != "audio":
            return
        ids = self._knife_target_event_ids(clip, float(at_beats))
        if not ids:
            return

        # Keep selection stable: suppress auto refresh, then refresh once with new ids.
        prev = bool(self._suppress_project_refresh)
        self._suppress_project_refresh = True
        new_sel: List[str] = []
        try:
            if hasattr(self.project, "split_audio_events_at"):
                new_sel = list(self.project.split_audio_events_at(str(clip.id), float(at_beats), event_ids=list(ids)))  # type: ignore[attr-defined]
            else:
                # fallback (legacy): splits first containing event only
                self.project.split_audio_event(str(clip.id), float(at_beats))
        except Exception:
            new_sel = []
        finally:
            self._suppress_project_refresh = prev

        if new_sel:
            self._selected_event_ids = set(self._right_ids_from_split(list(new_sel)))
        self.refresh()
        try:
            self.status_message.emit(f"Split @ {float(at_beats):0.2f} beats")
        except Exception:
            pass

    def _on_erase_requested(self, at_beats: float) -> None:
        clip = self._get_clip()
        # --- Ultra-Pro actions (render_meta) ---
        if a == "Re-render (in place)":
            try:
                if hasattr(self.project, 'rerender_clip_in_place_from_meta'):
                    ok = self.project.rerender_clip_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Re-rendered (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render in place fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render in place fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Restore Sources (in place)":
            try:
                if hasattr(self.project, 'restore_sources_in_place_from_meta'):
                    ok = self.project.restore_sources_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Sources restored (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Restore sources fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Restore sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Re-render (from sources)":
            try:
                if hasattr(self.project, 'rerender_clip_from_meta'):
                    nid = self.project.rerender_clip_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if nid:
                        try:
                            self.status_message.emit('Re-rendered (Ultra-Pro)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Back to Sources":
            try:
                if hasattr(self.project, 'back_to_sources_from_meta'):
                    sid = self.project.back_to_sources_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if sid:
                        try:
                            self.status_message.emit('Back to sources')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Keine Source-Meta gefunden')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Back to sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if not clip or getattr(clip, "kind", "") != "audio":
            return
        try:
            self.project.merge_audio_events_near(str(clip.id), float(at_beats), tolerance_beats=0.06)
            self.status_message.emit("Merge (Slice entfernt)")
        except Exception:
            pass

    def _on_loop_dragged(self, start_beats: float, end_beats: float) -> None:
        # Time-Selection tool: user drags a loop region.
        # We update overlay live, and persist to model, but we must NOT trigger a full refresh
        # while the drag is active (project_updated is synchronous).
        if self._loop_update_guard:
            return

        self._loop_update_guard = True
        try:
            clip = self._get_clip()
            if not clip or getattr(clip, "kind", "") != "audio":
                return

            # Requested loop (do NOT clamp to current clip length).
            try:
                s = max(0.0, float(min(start_beats, end_beats)))
                e = max(0.0, float(max(start_beats, end_beats)))
            except Exception:
                return

            # Minimal loop size
            if e <= s + 1e-6:
                try:
                    e = s + max(0.25, float(self._snap_quantum_beats()))
                except Exception:
                    e = s + 0.25

            # If the user draws beyond the current visible length, extend the editor view
            # immediately (Bitwig/Ableton feel). We commit the real clip length on drag end.
            try:
                cur_vis = float(getattr(self, '_clip_len_beats', 0.0) or 0.0)
            except Exception:
                cur_vis = 0.0

            def _beats_per_bar() -> float:
                try:
                    if getattr(self, 'transport', None) is not None:
                        return float(self.transport.beats_per_bar() or 4.0)
                except Exception:
                    pass
                try:
                    ts = str(getattr(self.project.ctx.project, 'time_signature', '4/4'))
                    num, den = ts.split('/', 1)
                    return float(num) * (4.0 / float(den))
                except Exception:
                    return 4.0

            if float(e) > float(cur_vis) + 1e-6 and self._scene is not None:
                bpb = max(1.0, float(_beats_per_bar()))
                new_vis = math.ceil(float(e) / float(bpb)) * float(bpb)
                # never shrink here
                if new_vis > cur_vis + 1e-6:
                    try:
                        self._clip_len_beats = max(0.25, float(new_vis))
                        self._clip_width_px = float(self._clip_len_beats) * float(self._px_per_beat)
                        self._scene.setSceneRect(QRectF(0, 0, float(self._clip_width_px), float(self._clip_height)))
                        self._scene.px_per_beat = float(self._px_per_beat)
                        if self.view is not None:
                            self.view.set_clip_length(float(self._clip_len_beats))
                        # commit later
                        self._pending_resize_len_beats = float(self._clip_len_beats)
                    except Exception:
                        pass

            pair = (round(s, 6), round(e, 6))
            if self._last_loop_pair is not None and pair == self._last_loop_pair:
                return
            self._last_loop_pair = pair

            x0 = s * self._px_per_beat
            x1 = e * self._px_per_beat
            if self._loop_rect:
                self._loop_rect.setRect(QRectF(x0, 0.0, max(1.0, x1 - x0), self._loop_rect.rect().height()))
            if self._loop_start_edge:
                self._loop_start_edge.setPos(QPointF(x0, 0.0))
            if self._loop_end_edge:
                self._loop_end_edge.setPos(QPointF(x1, 0.0))

            self._suppress_project_refresh = True
            try:
                self.project.set_audio_clip_loop(str(clip.id), float(s), float(e))
            finally:
                self._suppress_project_refresh = False
        finally:
            self._loop_update_guard = False

    def _on_loop_drag_finished(self) -> None:
        """Finalize a loop-drag.

        If the user dragged beyond the current clip length, we commit a resized
        clip length in the model and then refresh the editor once.
        """
        try:
            clip = self._get_clip()
            if not clip or getattr(clip, 'kind', '') != 'audio':
                self._pending_resize_len_beats = None
                return

            pending = self._pending_resize_len_beats
            self._pending_resize_len_beats = None
            if pending is None:
                return

            # Only grow (never shrink) and snap to bar.
            cur_len = float(getattr(clip, 'length_beats', 0.0) or 0.0)
            if float(pending) <= float(cur_len) + 1e-6:
                return

            bpb = 4.0
            try:
                if getattr(self, 'transport', None) is not None:
                    bpb = float(self.transport.beats_per_bar() or 4.0)
                else:
                    ts = str(getattr(self.project.ctx.project, 'time_signature', '4/4'))
                    num, den = ts.split('/', 1)
                    bpb = float(num) * (4.0 / float(den))
            except Exception:
                bpb = 4.0
            bpb = max(1.0, float(bpb))
            new_len = math.ceil(float(pending) / float(bpb)) * float(bpb)

            self._suppress_project_refresh = True
            try:
                # ProjectService already provides this generic API.
                self.project.resize_clip(str(clip.id), float(new_len), snap_beats=None)  # type: ignore[arg-type]
            except Exception:
                pass
            finally:
                self._suppress_project_refresh = False

            # Force a full refresh now so zoom-to-fit recalculates px_per_beat.
            self.refresh()
        except Exception:
            try:
                self._pending_resize_len_beats = None
            except Exception:
                pass

    def _on_context_action(self, action_text: str) -> None:
        clip = self._get_clip()
        if not clip or getattr(clip, "kind", "") != "audio":
            # Still handle clipboard actions if no clip restrictions apply
            pass

        a = str(action_text or "").strip()

        # --- Clipboard actions from context menu (simulated key events) ---
        if a == "_ctx_copy":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
            self.handle_key_event(ev)
            return
        if a == "_ctx_cut":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
            self.handle_key_event(ev)
            return
        if a == "_ctx_paste":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            self.handle_key_event(ev)
            return
        if a == "_ctx_delete":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
            self.handle_key_event(ev)
            return
        if a == "_ctx_select_all":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            self.handle_key_event(ev)
            return
        if a == "_ctx_duplicate":
            from PyQt6.QtCore import Qt
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
            self.handle_key_event(ev)
            return

        # --- Ultra-Pro actions (render_meta) ---
        if a == "Re-render (in place)":
            try:
                if hasattr(self.project, 'rerender_clip_in_place_from_meta'):
                    ok = self.project.rerender_clip_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Re-rendered (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render in place fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render in place fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Restore Sources (in place)":
            try:
                if hasattr(self.project, 'restore_sources_in_place_from_meta'):
                    ok = self.project.restore_sources_in_place_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if ok:
                        try:
                            self.status_message.emit('Sources restored (in place)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Restore sources fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Restore sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Re-render (from sources)":
            try:
                if hasattr(self.project, 'rerender_clip_from_meta'):
                    nid = self.project.rerender_clip_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if nid:
                        try:
                            self.status_message.emit('Re-rendered (Ultra-Pro)')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Re-render fehlgeschlagen')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Re-render fehlgeschlagen')
                except Exception:
                    pass
            return

        if a == "Back to Sources":
            try:
                if hasattr(self.project, 'back_to_sources_from_meta'):
                    sid = self.project.back_to_sources_from_meta(str(getattr(clip, 'id', '')))  # type: ignore[attr-defined]
                    if sid:
                        try:
                            self.status_message.emit('Back to sources')
                        except Exception:
                            pass
                    else:
                        try:
                            self.status_message.emit('Keine Source-Meta gefunden')
                        except Exception:
                            pass
            except Exception:
                try:
                    self.status_message.emit('Back to sources fehlgeschlagen')
                except Exception:
                    pass
            return

        if not clip or getattr(clip, "kind", "") != "audio":
            return

        if a == "Split at Playhead":
            t = self._local_playhead_beats(clip)
            ids = self._knife_target_event_ids(clip, float(t))
            if not ids:
                return

            prev = bool(self._suppress_project_refresh)
            self._suppress_project_refresh = True
            new_sel: List[str] = []
            try:
                if hasattr(self.project, "split_audio_events_at"):
                    new_sel = list(self.project.split_audio_events_at(str(clip.id), float(t), event_ids=list(ids)))  # type: ignore[attr-defined]
                else:
                    self.project.split_audio_event(str(clip.id), float(t))
            except Exception:
                new_sel = []
            finally:
                self._suppress_project_refresh = prev

            if new_sel:
                self._selected_event_ids = set(self._right_ids_from_split(list(new_sel)))
            self.refresh()
            try:
                self.status_message.emit(f"Split at Playhead @ {t:0.2f}")
            except Exception:
                pass
            return

        # --- Consolidate / Bounce variants (Audio-Events) ---
        if a in ("Consolidate", "Consolidate (Trim)", "Consolidate (+Handles)") or a.startswith("Tail +") or a.startswith("Join to new Clip"):
            try:
                if a.startswith('Join to new Clip'):
                    self._do_consolidate_events(join_keep_events=True)
                    return

                mode = 'bar'
                handles = 0.0
                tail = 0.0

                if a == 'Consolidate (Trim)':
                    mode = 'trim'
                if a == 'Consolidate (+Handles)':
                    handles = 0.125

                if a.startswith('Tail +'):
                    try:
                        ts = str(getattr(self.project.ctx.project, 'time_signature', '4/4') or '4/4')
                        bar_beats = float(ts.split('/')[0]) if '/' in ts else 4.0
                        if bar_beats <= 1e-9:
                            bar_beats = 4.0
                    except Exception:
                        bar_beats = 4.0
                    if '1/4' in a:
                        tail = 0.25
                    elif '1 Beat' in a:
                        tail = 1.0
                    elif '1 Bar' in a:
                        tail = float(bar_beats)
                    else:
                        tail = 1.0

                self._do_consolidate_events(mode=str(mode), handles_beats=float(handles), tail_beats=float(tail), normalize=False)
            except Exception:
                pass
            return


        if a.startswith("Quantize"):
            try:
                ids = list(self._selected_event_ids) if self._selected_event_ids else []
                self.project.quantize_audio_events(str(clip.id), ids)  # type: ignore[attr-defined]
                self.status_message.emit("Quantize")
            except Exception:
                pass
            return

        if a == "+1 Semitone":
            try:
                self.project.update_audio_clip_params(
                    str(clip.id), pitch=float(getattr(clip, "pitch", 0.0) or 0.0) + 1.0
                )
                self.status_message.emit("Pitch +1")
            except Exception:
                pass
            return

        if a == "-1 Semitone":
            try:
                self.project.update_audio_clip_params(
                    str(clip.id), pitch=float(getattr(clip, "pitch", 0.0) or 0.0) - 1.0
                )
                self.status_message.emit("Pitch -1")
            except Exception:
                pass
            return

        if a == "Reverse":
            try:
                cur = bool(getattr(clip, "reversed", False))
                new_val = not cur
                self.project.update_audio_clip_params(str(clip.id), reversed=new_val)
                state = "ON" if new_val else "OFF"
                self.status_message.emit(f"Reverse Clip {state}")
                self.refresh()
            except Exception:
                self.status_message.emit("Reverse (Fehler)")
            return


        if a == "Reverse (Events)":
            try:
                # Per-event reverse (v0.0.20.160): toggle reversed on selected events (or the event under mouse).
                sel_ids = set(self._selected_event_ids) if self._selected_event_ids else set()
                if not sel_ids:
                    try:
                        ctx_id = str(getattr(self, '_context_menu_event_id', '') or '').strip()
                    except Exception:
                        ctx_id = ''
                    if ctx_id:
                        sel_ids = {ctx_id}

                evs = list(getattr(clip, 'audio_events', []) or [])
                toggled = 0
                if sel_ids:
                    for ev in evs:
                        if str(getattr(ev, 'id', '')) in sel_ids:
                            cur = bool(getattr(ev, 'reversed', False))
                            ev.reversed = not cur
                            toggled += 1

                if toggled > 0:
                    self.project._emit_updated()
                    self.status_message.emit(f"Reverse toggled ({toggled} event{'s' if toggled != 1 else ''})")
                else:
                    self.status_message.emit("Reverse (keine Auswahl)")
                self.refresh()
            except Exception:
                self.status_message.emit("Reverse (Fehler)")
            return


        if a == "Mute Clip":
            try:
                cur = bool(getattr(clip, "muted", False))
                new_val = not cur
                self.project.update_audio_clip_params(str(clip.id), muted=new_val)
                state = "ON" if new_val else "OFF"
                self.status_message.emit(f"Mute {state}")
                self.refresh()
            except Exception:
                self.status_message.emit("Mute (Fehler)")
            return

        if a == "Normalize":
            try:
                if hasattr(self.project, 'normalize_audio_clip'):
                    new_gain = self.project.normalize_audio_clip(str(clip.id))
                    if new_gain is not None:
                        import math
                        db = 20.0 * math.log10(max(1e-10, new_gain))
                        self.status_message.emit(f"Normalized → Gain {db:+.1f} dB")
                    else:
                        self.project.update_audio_clip_params(str(clip.id), gain=1.0)
                        self.status_message.emit("Normalized (Gain → 0 dB)")
                else:
                    self.project.update_audio_clip_params(str(clip.id), gain=1.0)
                    self.status_message.emit("Normalized (Gain → 0 dB)")
                self.refresh()
            except Exception:
                self.status_message.emit("Normalize (Fehler)")
            return

        if a == "+3 dB":
            try:
                cur_gain = float(getattr(clip, "gain", 1.0) or 1.0)
                new_gain = min(4.0, cur_gain * 1.4125)  # +3dB
                self.project.update_audio_clip_params(str(clip.id), gain=new_gain)
                import math
                db = 20.0 * math.log10(max(1e-10, new_gain))
                self.status_message.emit(f"Gain → {db:+.1f} dB")
                self.refresh()
            except Exception:
                self.status_message.emit("Gain +3 dB (Fehler)")
            return

        if a == "-3 dB":
            try:
                cur_gain = float(getattr(clip, "gain", 1.0) or 1.0)
                new_gain = max(0.01, cur_gain * 0.7079)  # -3dB
                self.project.update_audio_clip_params(str(clip.id), gain=new_gain)
                import math
                db = 20.0 * math.log10(max(1e-10, new_gain))
                self.status_message.emit(f"Gain → {db:+.1f} dB")
                self.refresh()
            except Exception:
                self.status_message.emit("Gain -3 dB (Fehler)")
            return

        if a == "+6 dB":
            try:
                cur_gain = float(getattr(clip, "gain", 1.0) or 1.0)
                new_gain = min(4.0, cur_gain * 1.9953)  # +6dB
                self.project.update_audio_clip_params(str(clip.id), gain=new_gain)
                import math
                db = 20.0 * math.log10(max(1e-10, new_gain))
                self.status_message.emit(f"Gain → {db:+.1f} dB")
                self.refresh()
            except Exception:
                self.status_message.emit("Gain +6 dB (Fehler)")
            return

        if a == "-6 dB":
            try:
                cur_gain = float(getattr(clip, "gain", 1.0) or 1.0)
                new_gain = max(0.01, cur_gain * 0.5012)  # -6dB
                self.project.update_audio_clip_params(str(clip.id), gain=new_gain)
                import math
                db = 20.0 * math.log10(max(1e-10, new_gain))
                self.status_message.emit(f"Gain → {db:+.1f} dB")
                self.refresh()
            except Exception:
                self.status_message.emit("Gain -6 dB (Fehler)")
            return

        if a == "Reset (0 dB)":
            try:
                self.project.update_audio_clip_params(str(clip.id), gain=1.0)
                self.status_message.emit("Gain → 0 dB")
                self.refresh()
            except Exception:
                pass
            return

        # --- Fade actions ---
        if a.startswith("Fade In "):
            fade_map = {"1/16": 0.25, "1/8": 0.5, "1/4": 1.0, "1 Bar": 4.0}
            suffix = a.replace("Fade In ", "")
            beats = fade_map.get(suffix, 0.25)
            try:
                self.project.update_audio_clip_params(str(clip.id), fade_in_beats=beats)
                self.status_message.emit(f"Fade In → {suffix}")
                self.refresh()
            except Exception:
                self.status_message.emit("Fade In (Fehler)")
            return

        if a.startswith("Fade Out "):
            fade_map = {"1/16": 0.25, "1/8": 0.5, "1/4": 1.0, "1 Bar": 4.0}
            suffix = a.replace("Fade Out ", "")
            beats = fade_map.get(suffix, 0.25)
            try:
                self.project.update_audio_clip_params(str(clip.id), fade_out_beats=beats)
                self.status_message.emit(f"Fade Out → {suffix}")
                self.refresh()
            except Exception:
                self.status_message.emit("Fade Out (Fehler)")
            return

        if a == "Clear Fades":
            try:
                self.project.update_audio_clip_params(str(clip.id), fade_in_beats=0.0, fade_out_beats=0.0)
                self.status_message.emit("Fades gelöscht")
                self.refresh()
            except Exception:
                pass
            return

        # --- Transpose octave ---
        if a == "+12 Semitone (Octave Up)":
            try:
                self.project.update_audio_clip_params(
                    str(clip.id), pitch=float(getattr(clip, "pitch", 0.0) or 0.0) + 12.0
                )
                self.status_message.emit("Pitch +12 (Octave Up)")
            except Exception:
                pass
            return

        if a == "-12 Semitone (Octave Down)":
            try:
                self.project.update_audio_clip_params(
                    str(clip.id), pitch=float(getattr(clip, "pitch", 0.0) or 0.0) - 12.0
                )
                self.status_message.emit("Pitch -12 (Octave Down)")
            except Exception:
                pass
            return

        # --- Onset actions ---
        if a == "Auto-Detect Onsets":
            try:
                onsets = self.project.detect_onsets(str(clip.id))
                count = len(onsets) if onsets else 0
                self.status_message.emit(f"Onsets erkannt: {count}")
                # Auto-enable onset display
                self._activate_overlay("onsets")
                self.refresh()
            except Exception:
                self.status_message.emit("Onset-Erkennung (Fehler)")
            return

        if a == "Add Onset at Playhead":
            try:
                t = self._local_playhead_beats(clip)
                self.project.add_onset_at(str(clip.id), float(t))
                self.status_message.emit(f"Onset @ {t:0.2f}")
                self._activate_overlay("onsets")
                self.refresh()
            except Exception:
                self.status_message.emit("Onset hinzufügen (Fehler)")
            return

        if a == "Slice at Onsets":
            try:
                count = self.project.slice_at_onsets(str(clip.id))
                self.status_message.emit(f"Sliced at {count} onsets")
                self.refresh()
            except Exception:
                self.status_message.emit("Slice at Onsets (Fehler)")
            return

        if a == "Clear Onsets":
            try:
                self.project.clear_onsets(str(clip.id))
                self.status_message.emit("Onsets gelöscht")
                self.refresh()
            except Exception:
                self.status_message.emit("Clear Onsets (Fehler)")
            return

        # --- Warp Markers (v0.0.20.641 AP3 Phase 3A) ---
        if a == "Auto-Detect Warp Markers":
            try:
                count = 0
                if hasattr(self.project, 'auto_detect_warp_markers'):
                    count = self.project.auto_detect_warp_markers(str(clip.id))
                if count > 0:
                    self.status_message.emit(f"Warp-Marker gesetzt: {count}")
                    self._activate_overlay("stretch")
                else:
                    self.status_message.emit("Keine Beats erkannt — keine Warp-Marker")
                self.refresh()
            except Exception:
                self.status_message.emit("Warp-Marker Auto-Detect (Fehler)")
            return

        if a == "Clear Warp Markers":
            try:
                if hasattr(self.project, 'clear_warp_markers'):
                    self.project.clear_warp_markers(str(clip.id))
                    self.status_message.emit("Warp-Marker gelöscht")
                else:
                    clip.stretch_markers = []
                    self.status_message.emit("Warp-Marker gelöscht")
                self.refresh()
            except Exception:
                self.status_message.emit("Clear Warp-Marker (Fehler)")
            return

        # --- Zero-Crossing ---
        if a == "Snap to Zero-Crossing":
            try:
                t = self._local_playhead_beats(clip)
                zc = self.project.find_zero_crossings(str(clip.id), float(t))
                self.status_message.emit(f"Zero-Crossing @ {zc:0.4f} beats")
            except Exception:
                self.status_message.emit("Zero-Crossing (Fehler)")
            return

        # --- Clip Automation ---
        if a == "Clear Gain Automation":
            try:
                self.project.clear_clip_automation(str(clip.id), "gain")
                self.status_message.emit("Gain Automation gelöscht")
                self.refresh()
            except Exception:
                pass
            return

        if a == "Clear Pan Automation":
            try:
                self.project.clear_clip_automation(str(clip.id), "pan")
                self.status_message.emit("Pan Automation gelöscht")
                self.refresh()
            except Exception:
                pass
            return

        if a == "Clear Pitch Automation":
            try:
                self.project.clear_clip_automation(str(clip.id), "pitch")
                self.status_message.emit("Pitch Automation gelöscht")
                self.refresh()
            except Exception:
                pass
            return

        if a == "Clear All Clip Automation":
            try:
                self.project.clear_clip_automation(str(clip.id))
                self.status_message.emit("Alle Clip-Automation gelöscht")
                self.refresh()
            except Exception:
                pass
            return

    # helpers
    def _local_playhead_beats(self, clip) -> float:  # noqa: ANN001
        # v0.0.20.613: Dual-Clock — nutze den letzten Adapter-Beat
        # Im Arranger-Modus ist das der globale Beat (wie vorher).
        # Im Launcher-Modus ist das der lokale Slot-Beat vom Adapter.
        gb = float(self._last_adapter_beat or 0.0)
        if gb < 1e-6:
            # Fallback: direkt vom Transport lesen (z.B. beim ersten Aufruf)
            try:
                if self.transport is not None:
                    gb = float(getattr(self.transport, "current_beat", getattr(self.transport, "beat", 0.0)) or 0.0)
            except Exception:
                gb = 0.0

        length = max(1e-6, float(getattr(clip, "length_beats", 4.0) or 4.0))
        ls = float(getattr(clip, "loop_start_beats", 0.0) or 0.0)
        le = float(getattr(clip, "loop_end_beats", 0.0) or 0.0)
        if le > ls + 1e-6:
            L = max(1e-6, le - ls)
            return ls + (gb % L)
        return gb % length

    def _render_clip_automation(self, clip, width: float, height: float) -> None:
        """Render automation envelope lines for the current parameter (Bitwig/Ableton-style)."""
        scene = self._scene
        if scene is None:
            return

        self._auto_items = []
        self._auto_point_items = []

        auto = getattr(clip, 'clip_automation', None)
        if not auto or not isinstance(auto, dict):
            return

        param = str(self._auto_param or "gain").lower()
        pts = auto.get(param, [])
        if not pts:
            return

        # Color per parameter
        colors = {
            "gain": QColor(0, 255, 128),    # green
            "pan": QColor(255, 200, 0),     # yellow
            "pitch": QColor(0, 180, 255),   # blue
            "formant": QColor(255, 100, 255),  # magenta
        }
        color = colors.get(param, QColor(0, 255, 128))

        # Draw lines between breakpoints
        sorted_pts = sorted(pts, key=lambda p: float(p.get("beat", 0)))
        pen = QPen(color)
        pen.setWidthF(2.0)

        for i in range(len(sorted_pts) - 1):
            p0 = sorted_pts[i]
            p1 = sorted_pts[i + 1]
            x0 = float(p0.get("beat", 0)) * self._px_per_beat
            x1 = float(p1.get("beat", 0)) * self._px_per_beat
            v0 = float(p0.get("value", 0.5))
            v1 = float(p1.get("value", 0.5))
            y0 = height - (v0 * height)
            y1 = height - (v1 * height)

            line = QGraphicsLineItem(x0, y0, x1, y1)
            line.setZValue(40)
            line.setPen(pen)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            scene.addItem(line)
            self._auto_items.append(line)

        # Draw breakpoint dots (draggable in Zeiger/Pointer tool)
        dot_size = 9.0

        for pt in sorted_pts:
            bx = float(pt.get("beat", 0))
            v = float(pt.get("value", 0.5))
            try:
                dot = AutomationPointItem(
                    self,
                    clip_id=str(getattr(self, '_clip_id', '') or ''),
                    param=param,
                    beat=float(bx),
                    value=float(v),
                    px_per_beat=float(self._px_per_beat),
                    height=float(height),
                    color=color,
                    dot_size=float(dot_size),
                )
                scene.addItem(dot)
                self._auto_point_items.append(dot)
            except Exception:
                continue

    def _render_fade_overlays(self, clip, width: float, height: float) -> None:
        """Render fade in/out triangular overlays + draggable handles (Bitwig-style)."""
        scene = self._scene
        if scene is None:
            return

        fi = float(getattr(clip, 'fade_in_beats', 0.0) or 0.0)
        fo = float(getattr(clip, 'fade_out_beats', 0.0) or 0.0)

        # Fade In overlay (dark triangle, left side)
        if fi > 0.001:
            try:
                fi_px = fi * self._px_per_beat
                path = QPainterPath()
                path.moveTo(0.0, 0.0)
                path.lineTo(fi_px, 0.0)
                path.lineTo(0.0, height)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setZValue(25)
                item.setBrush(QBrush(QColor(0, 0, 0, 80)))
                pen = QPen(QColor(255, 165, 0))
                pen.setWidth(2)
                item.setPen(pen)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(item)
                self._fade_in_overlay = item
            except Exception:
                pass

        # Fade Out overlay (dark triangle, right side)
        if fo > 0.001:
            try:
                fo_px = fo * self._px_per_beat
                x_start = width - fo_px
                path = QPainterPath()
                path.moveTo(width, 0.0)
                path.lineTo(x_start, 0.0)
                path.lineTo(width, height)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setZValue(25)
                item.setBrush(QBrush(QColor(0, 0, 0, 80)))
                pen = QPen(QColor(100, 149, 237))
                pen.setWidth(2)
                item.setPen(pen)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                scene.addItem(item)
                self._fade_out_overlay = item
            except Exception:
                pass

        # Fade In handle (draggable triangle at fade boundary)
        fi_x = fi * self._px_per_beat
        handle_in = _FadeHandle(fi_x, height, role="fade_in",
                                on_moved=lambda x: self._on_fade_handle_moved("in", x))
        scene.addItem(handle_in)
        self._fade_in_handle = handle_in

        # Fade Out handle (draggable triangle at fade boundary)
        fo_x = width - fo * self._px_per_beat
        handle_out = _FadeHandle(fo_x, height, role="fade_out",
                                 on_moved=lambda x: self._on_fade_handle_moved("out", x))
        scene.addItem(handle_out)
        self._fade_out_handle = handle_out

    def _on_fade_handle_moved(self, which: str, x_pixels: float) -> None:
        """Handle drag of fade in/out handles."""
        if self._fade_update_guard:
            return
        self._fade_update_guard = True
        try:
            clip = self._get_clip()
            if not clip:
                return
            length_beats = float(getattr(clip, "length_beats", 4.0) or 4.0)
            max_fade = length_beats * 0.5  # max 50% of clip

            if which == "in":
                beats = max(0.0, min(max_fade, float(x_pixels) / self._px_per_beat))
                self._suppress_project_refresh = True
                try:
                    self.project.update_audio_clip_params(str(clip.id), fade_in_beats=beats)
                finally:
                    self._suppress_project_refresh = False
                # Update overlay live
                if self._fade_in_overlay and self._scene:
                    try:
                        self._scene.removeItem(self._fade_in_overlay)
                    except Exception:
                        pass
                    self._fade_in_overlay = None
                    if beats > 0.001:
                        try:
                            fi_px = beats * self._px_per_beat
                            path = QPainterPath()
                            path.moveTo(0.0, 0.0)
                            path.lineTo(fi_px, 0.0)
                            path.lineTo(0.0, self._clip_height)
                            path.closeSubpath()
                            item = QGraphicsPathItem(path)
                            item.setZValue(25)
                            item.setBrush(QBrush(QColor(0, 0, 0, 80)))
                            pen = QPen(QColor(255, 165, 0))
                            pen.setWidth(2)
                            item.setPen(pen)
                            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                            self._scene.addItem(item)
                            self._fade_in_overlay = item
                        except Exception:
                            pass
            else:  # "out"
                width_px = self._clip_width_px
                fo_px = max(0.0, width_px - float(x_pixels))
                beats = max(0.0, min(max_fade, fo_px / self._px_per_beat))
                self._suppress_project_refresh = True
                try:
                    self.project.update_audio_clip_params(str(clip.id), fade_out_beats=beats)
                finally:
                    self._suppress_project_refresh = False
                # Update overlay live
                if self._fade_out_overlay and self._scene:
                    try:
                        self._scene.removeItem(self._fade_out_overlay)
                    except Exception:
                        pass
                    self._fade_out_overlay = None
                    if beats > 0.001:
                        try:
                            fo_px_d = beats * self._px_per_beat
                            x_start = width_px - fo_px_d
                            path = QPainterPath()
                            path.moveTo(width_px, 0.0)
                            path.lineTo(x_start, 0.0)
                            path.lineTo(width_px, self._clip_height)
                            path.closeSubpath()
                            item = QGraphicsPathItem(path)
                            item.setZValue(25)
                            item.setBrush(QBrush(QColor(0, 0, 0, 80)))
                            pen = QPen(QColor(100, 149, 237))
                            pen.setWidth(2)
                            item.setPen(pen)
                            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                            self._scene.addItem(item)
                            self._fade_out_overlay = item
                        except Exception:
                            pass
        finally:
            self._fade_update_guard = False

    def _ensure_loop_items(self, clip, width: float, height: float) -> None:  # noqa: ANN001
        scene = self._scene
        if scene is None:
            return

        s = float(getattr(clip, "loop_start_beats", 0.0) or 0.0)
        e = float(getattr(clip, "loop_end_beats", 0.0) or 0.0)
        length_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)

        if e <= s + 1e-6:
            s = 0.0
            e = max(0.0, length_beats)

        x0 = s * self._px_per_beat
        x1 = e * self._px_per_beat

        rect = QGraphicsRectItem(QRectF(x0, 0.0, max(1.0, x1 - x0), height))
        rect.setZValue(10)
        rect.setBrush(QBrush(self.palette().highlight().color()))
        rect.setOpacity(0.10)
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        scene.addItem(rect)
        self._loop_rect = rect

        start_edge = _LoopEdge(x0, height, color_role="start")
        end_edge = _LoopEdge(x1, height, color_role="end")
        scene.addItem(start_edge)
        scene.addItem(end_edge)
        self._loop_start_edge = start_edge
        self._loop_end_edge = end_edge

        start_edge.set_on_moved(lambda x: self._on_loop_edge_moved("start", x))
        end_edge.set_on_moved(lambda x: self._on_loop_edge_moved("end", x))

        start_edge.setPos(QPointF(x0, 0.0))
        end_edge.setPos(QPointF(x1, 0.0))

    def _on_loop_edge_moved(self, which: str, x_pixels: float) -> None:
        # This callback is executed from within QGraphicsItem.itemChange.
        # Calling refresh() (via project_updated) while an itemChange is running will crash Qt.
        # We therefore:
        # 1) use a re-entrancy guard for setPos feedback loops
        # 2) suppress our own refresh while we update the model
        if self._loop_update_guard:
            return

        self._loop_update_guard = True
        try:
            clip = self._get_clip()
            if not clip:
                return

            length_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)
            length_px = max(0.0, length_beats * self._px_per_beat)
            x = max(0.0, min(float(x_pixels), length_px))

            s = float(getattr(clip, "loop_start_beats", 0.0) or 0.0)
            e = float(getattr(clip, "loop_end_beats", 0.0) or 0.0)
            if e <= s + 1e-6:
                s = 0.0
                e = max(0.0, length_beats)

            if which == "start":
                s = x / self._px_per_beat
            else:
                e = x / self._px_per_beat

            # enforce a small minimum loop size
            if e <= s + 1e-6:
                e = min(max(0.0, length_beats), s + 0.25)

            # clamp
            s = max(0.0, min(s, max(0.0, length_beats)))
            e = max(0.0, min(e, max(0.0, length_beats)))

            pair = (round(s, 6), round(e, 6))
            if self._last_loop_pair is not None and pair == self._last_loop_pair:
                # nothing changed (prevents spamming signals)
                return
            self._last_loop_pair = pair

            # Update overlay immediately (no scene rebuild)
            x0 = s * self._px_per_beat
            x1 = e * self._px_per_beat
            if self._loop_rect:
                self._loop_rect.setRect(QRectF(x0, 0.0, max(1.0, x1 - x0), self._loop_rect.rect().height()))
            if self._loop_start_edge:
                self._loop_start_edge.setPos(QPointF(x0, 0.0))
            if self._loop_end_edge:
                self._loop_end_edge.setPos(QPointF(x1, 0.0))

            # Persist to model (and let other UI update), but do not refresh THIS editor synchronously.
            self._suppress_project_refresh = True
            try:
                self.project.set_audio_clip_loop(str(clip.id), float(s), float(e))
            finally:
                self._suppress_project_refresh = False
        finally:
            self._loop_update_guard = False

    def _get_clip(self):
        if not self._clip_id:
            return None
        return next((c for c in self.project.ctx.project.clips if getattr(c, "id", "") == self._clip_id), None)

    
    def _draw_waveform(
        self,
        abs_path: str,
        width: float,
        height: float,
        *,
        clip_len_beats: float = 0.0,
        loop_start_beats: float = 0.0,
        loop_end_beats: float = 0.0,
        offset_seconds: float = 0.0,
        stretch: float = 1.0,
        gain: float = 1.0,
        reversed_display: bool = False,
    ) -> None:
        """Draw the clip waveform background.

        Important: In the Audio Editor, users expect Bitwig/Ableton-style *clip looping*:
        if a clip has a loop region (loop_start/loop_end), the waveform should visually
        repeat that region across the clip length.

        We do a lightweight, UI-safe approximation:
        - Read the full source file (soundfile)
        - Build a min/max peak table (per block)
        - For each display x-position, map to a beat inside the clip, apply loop wrap,
          then sample from the peak table.
        """
        scene = self._scene
        if scene is None:
            return
        if sf is None or np is None:
            t = scene.addText("Waveform: soundfile/numpy nicht verfügbar.")
            t.setDefaultTextColor(self.palette().mid().color())
            return

        try:
            data, _sr = sf.read(abs_path, always_2d=True, dtype="float32")
        except Exception as e:
            t = scene.addText(f"Waveform: Fehler beim Laden: {e}")
            t.setDefaultTextColor(self.palette().mid().color())
            return

        if data is None or getattr(data, "size", 0) == 0:
            return

        try:
            mono = data.mean(axis=1).astype("float32", copy=False)
        except Exception:
            return

        mono = mono * float(gain)
        n = int(mono.shape[0])
        if n <= 1:
            return

        # Display resolution
        points = int(max(512, min(8000, float(width))))
        # Peak block size in source samples
        block = max(1, n // max(1, points))
        blocks = int(math.ceil(n / block))

        mins = np.empty(blocks, dtype=np.float32)
        maxs = np.empty(blocks, dtype=np.float32)
        for i in range(blocks):
            a = i * block
            b = min(n, (i + 1) * block)
            seg = mono[a:b]
            if getattr(seg, "size", 0):
                mins[i] = float(seg.min())
                maxs[i] = float(seg.max())
            else:
                mins[i] = 0.0
                maxs[i] = 0.0

        # Clip length in beats (fallback to editor state)
        try:
            if float(clip_len_beats) <= 1e-6:
                clip_len_beats = float(getattr(self, "_clip_len_beats", 0.0) or 0.0)
        except Exception:
            clip_len_beats = 0.0
        if float(clip_len_beats) <= 1e-6:
            clip_len_beats = 1.0  # avoid div-by-zero; should not happen

        # Loop wrap in beat domain
        ls = float(loop_start_beats or 0.0)
        le = float(loop_end_beats or 0.0)
        if le <= ls + 1e-6:
            loop_enabled = False
        else:
            # Clamp to clip length
            ls = max(0.0, min(ls, float(clip_len_beats)))
            le = max(0.0, min(le, float(clip_len_beats)))
            loop_enabled = (le > ls + 1e-6)
        loop_len = max(1e-9, (le - ls)) if loop_enabled else 0.0

        # Time mapping: beat-domain -> seconds -> source samples.
        # This avoids 'stretch-to-fit' visuals and matches DAW expectations:
        # extending clip length shows repeated content only when a loop region is set.
        try:
            bpm = float(getattr(getattr(self.project, 'ctx', None), 'project', None).bpm)  # type: ignore[attr-defined]
        except Exception:
            try:
                bpm = float(getattr(getattr(self.project, 'ctx', None), 'bpm', 120.0) or 120.0)
            except Exception:
                bpm = 120.0
        bpm = max(1.0, float(bpm))
        sec_per_beat = 60.0 / float(bpm)
        off_s = float(offset_seconds or 0.0)
        st = max(1e-9, float(stretch or 1.0))

        disp_mins = np.empty(points, dtype=np.float32)
        disp_maxs = np.empty(points, dtype=np.float32)

        # Map: display-x -> beat -> (loop wrap) -> source sample -> peak block
        for i in range(points):
            frac = float(i) / float(max(1, points - 1))
            beat = frac * float(clip_len_beats)
            if loop_enabled and beat >= ls:
                beat = ls + ((beat - ls) % float(loop_len))

            # Map beat position to a source sample index
            src_sec = float(off_s) + (float(beat) * float(sec_per_beat)) / float(st)
            samp = int(round(float(src_sec) * float(_sr)))
            if reversed_display:
                samp = (n - 1) - samp
            if samp < 0:
                samp = 0
            if samp >= n:
                samp = n - 1

            bidx = int(samp // block)
            if bidx < 0:
                bidx = 0
            if bidx >= blocks:
                bidx = blocks - 1

            disp_mins[i] = mins[bidx]
            disp_maxs[i] = maxs[bidx]

        mid_y = float(height) * 0.5
        amp = float(height) * 0.42
        path = QPainterPath()

        for i in range(points):
            x = (float(i) / float(max(1, points - 1))) * float(width)
            y = mid_y - float(disp_maxs[i]) * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        for i in range(points - 1, -1, -1):
            x = (float(i) / float(max(1, points - 1))) * float(width)
            y = mid_y - float(disp_mins[i]) * amp
            path.lineTo(x, y)

        path.closeSubpath()

        item = QGraphicsPathItem(path)
        item.setZValue(12)
        pen = QPen(self.palette().text().color())
        pen.setWidth(1)
        item.setPen(pen)
        item.setBrush(QBrush(self.palette().mid().color()))
        item.setOpacity(0.35)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        scene.addItem(item)
        self._wave_item = item


    # --- Pro-DAW: per-AudioEvent waveform (moves with blocks, duplicates show correctly) ---
    def _get_peaks_entry(self, abs_path: str) -> PeaksCacheEntry | None:
        """Return cached peaks for a given file (or build them once)."""
        if sf is None or np is None:
            return None
        p = str(abs_path or '')
        if not p:
            return None
        try:
            st = os.stat(p)
            mtime_ns = int(getattr(st, 'st_mtime_ns', int(st.st_mtime * 1e9)))
        except Exception:
            mtime_ns = 0

        ent = self._peaks_cache.get(p)
        if ent is not None and int(ent.mtime_ns) == int(mtime_ns):
            return ent

        try:
            data, sr = sf.read(p, always_2d=True, dtype='float32')
        except Exception:
            return None
        if data is None or getattr(data, 'size', 0) == 0:
            return None
        try:
            mono = data.mean(axis=1).astype('float32', copy=False)
        except Exception:
            return None

        n = int(mono.shape[0])
        if n <= 1:
            return None

        # Keep peaks reasonably dense for segment rendering.
        points = int(max(1024, min(12000, n // 8)))
        block = max(1, n // max(1, points))
        blocks = int(math.ceil(n / block))
        peaks = np.empty((blocks, 2), dtype=np.float32)
        for i in range(blocks):
            a = i * block
            b = min(n, (i + 1) * block)
            seg = mono[a:b]
            if getattr(seg, 'size', 0):
                peaks[i, 0] = float(seg.min())
                peaks[i, 1] = float(seg.max())
            else:
                peaks[i, 0] = 0.0
                peaks[i, 1] = 0.0

        ent = PeaksCacheEntry(
            mtime_ns=int(mtime_ns),
            samplerate=int(sr),
            block_size=int(block),
            peaks=peaks,
            n_samples=int(n),
        )
        self._peaks_cache[p] = ent
        return ent

    def _attach_waveform_to_event(self, parent_item: EventBlockItem, *, clip, ev) -> None:  # noqa: ANN001
        """Attach a waveform child item to the given EventBlockItem.

        This ensures:
        - dragging an AudioEvent moves the waveform too
        - duplicates visually show repeated waveforms (Bitwig/Ableton expectation)
        """
        if sf is None or np is None:
            return
        try:
            path = str(getattr(clip, 'source_path', '') or '')
        except Exception:
            path = ''
        if not path or not os.path.exists(path):
            return

        ent = self._get_peaks_entry(path)
        if ent is None:
            return

        # Geometry
        try:
            w_px = float(parent_item.rect().width())
            h_px = float(parent_item.rect().height())
        except Exception:
            return
        if w_px <= 2 or h_px <= 2:
            return

        # Render resolution per block
        points = int(max(64, min(2400, w_px)))

        # Mapping beats -> seconds -> source samples
        try:
            bpm = float(getattr(getattr(self.project, 'ctx', None), 'project', None).bpm)  # type: ignore[attr-defined]
        except Exception:
            bpm = 120.0
        bpm = max(1.0, float(bpm))
        sec_per_beat = 60.0 / float(bpm)

        try:
            off_s = float(getattr(clip, 'offset_seconds', 0.0) or 0.0)
        except Exception:
            off_s = 0.0
        try:
            st = max(1e-9, float(getattr(clip, 'stretch', 1.0) or 1.0))
        except Exception:
            st = 1.0
        try:
            gain = float(getattr(clip, 'gain', 1.0) or 1.0)
        except Exception:
            gain = 1.0
        try:
            rev = bool(getattr(clip, 'reversed', False))
        except Exception:
            rev = False
        # Per-event reverse (v0.0.20.160): XOR with clip-level
        try:
            ev_rev = bool(getattr(ev, 'reversed', False))
            if ev_rev:
                rev = not rev
        except Exception:
            pass

        try:
            src_off_b = float(getattr(ev, 'source_offset_beats', 0.0) or 0.0)
            ev_len_b = float(getattr(ev, 'length_beats', 0.0) or 0.0)
        except Exception:
            return
        if ev_len_b <= 1e-6:
            return

        peaks = ent.peaks
        blocks = int(peaks.shape[0])
        block = int(ent.block_size)
        n = int(ent.n_samples)
        sr = float(ent.samplerate)

        disp_min = np.empty(points, dtype=np.float32)
        disp_max = np.empty(points, dtype=np.float32)

        for i in range(points):
            frac = float(i) / float(max(1, points - 1))
            beat = float(src_off_b) + (frac * float(ev_len_b))
            src_sec = float(off_s) + (float(beat) * float(sec_per_beat)) / float(st)
            samp = int(round(float(src_sec) * float(sr)))
            if rev:
                samp = (n - 1) - samp
            if samp < 0:
                samp = 0
            if samp >= n:
                samp = n - 1
            bidx = int(samp // block)
            if bidx < 0:
                bidx = 0
            if bidx >= blocks:
                bidx = blocks - 1
            disp_min[i] = float(peaks[bidx, 0]) * float(gain)
            disp_max[i] = float(peaks[bidx, 1]) * float(gain)

        # Draw inside the event bounds with a small inset so the border stays visible.
        inset_x = 2.0
        inset_y = 3.0
        ww = max(1.0, float(w_px) - 2.0 * inset_x)
        hh = max(1.0, float(h_px) - 2.0 * inset_y)
        mid_y = inset_y + hh * 0.5
        amp = hh * 0.42

        path = QPainterPath()
        for i in range(points):
            x = inset_x + (float(i) / float(max(1, points - 1))) * ww
            y = mid_y - float(disp_max[i]) * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        for i in range(points - 1, -1, -1):
            x = inset_x + (float(i) / float(max(1, points - 1))) * ww
            y = mid_y - float(disp_min[i]) * amp
            path.lineTo(x, y)
        path.closeSubpath()

        wf = QGraphicsPathItem(path, parent_item)
        wf.setZValue(1)  # relative to parent
        try:
            pen = QPen(self.palette().text().color())
            pen.setWidth(1)
            wf.setPen(pen)
            wf.setBrush(QBrush(self.palette().mid().color()))
            wf.setOpacity(0.45)
        except Exception:
            pass
        wf.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
