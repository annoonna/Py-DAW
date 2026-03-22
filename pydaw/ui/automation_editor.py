"""Enhanced Automation Lane Editor (v0.0.20.89).

Replaces the basic _AutomationCurveEditor with a production-grade editor:
- Bezier curves with draggable control points
- Multiple curve types: Linear, Bezier, Step, Smooth (S-curve)
- FX parameter selection (Volume, Pan, + all registered FX params)
- Arranger-synced view (horizontal scroll/zoom linked to ArrangerCanvas)
- Grid overlay with beat/bar markers
- Playhead indicator
- Undo-friendly: all changes go through AutomationManager

Usage:
    editor = EnhancedAutomationEditor(automation_manager, project_service)
    editor.set_parameter("trk:abc:vol")
    editor.set_view_range(0.0, 32.0)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal, QRect
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath,
    QLinearGradient, QFont,
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QComboBox, QToolButton, QMenu, QListWidget, QListWidgetItem,
    QSizePolicy, QLineEdit, QCompleter, QSplitter, QPushButton,
    QScrollArea, QFrame,
)

from pydaw.ui.widgets.ruler_zoom_handle import paint_magnifier

from pydaw.audio.automatable_parameter import (
    AutomationManager, AutomationLane, BreakPoint, CurveType,
)


# ─── Color palette ───────────────────────────────────────────────────────

COL_BG = QColor(30, 30, 35)
COL_GRID_MAJOR = QColor(60, 60, 65)
COL_GRID_MINOR = QColor(45, 45, 50)
COL_BORDER = QColor(80, 80, 85)
COL_CURVE = QColor(0, 191, 255)          # deep sky blue
COL_CURVE_DISABLED = QColor(80, 80, 90)
COL_POINT = QColor(255, 255, 255)
COL_POINT_SELECTED = QColor(255, 200, 0)
COL_POINT_HOVER = QColor(100, 200, 255)
COL_BEZIER_CTRL = QColor(255, 140, 0, 180)
COL_BEZIER_LINE = QColor(255, 140, 0, 80)
COL_PLAYHEAD = QColor(255, 60, 60)
COL_ZERO_LINE = QColor(80, 80, 90)
COL_TEXT = QColor(160, 160, 165)
COL_VALUE_BG = QColor(20, 20, 25, 200)


# ─── Snap helper ──────────────────────────────────────────────────────────

def _snap_beats(beat: float, division: str) -> float:
    mapping = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125, "1/64": 0.0625}
    snap = mapping.get(str(division), 0.25)
    if snap > 0:
        return round(beat / snap) * snap
    return beat


# ─── Enhanced Curve Editor Widget ─────────────────────────────────────────

class EnhancedAutomationEditor(QWidget):
    """Professional automation curve editor with Bezier support.

    X-axis: beats (synced with arranger view range)
    Y-axis: 0..1 normalized parameter value
    """

    # Emitted when lane data changes (for project dirty-state)
    lane_changed = Signal(str)  # parameter_id

    POINT_RADIUS = 5.0
    CTRL_RADIUS = 4.0
    HIT_RADIUS = 8.0
    MARGIN = 10

    def __init__(self, automation_manager: AutomationManager, project: Any = None, parent=None):
        super().__init__(parent)
        self._mgr = automation_manager
        self._project = project
        self._parameter_id: str = ""

        # View range (beats) — synced with arranger
        self._view_start = 0.0
        self._view_end = 32.0

        # Playhead
        self._playhead_beat = 0.0

        # Interaction state
        self._drag_point_idx: Optional[int] = None
        self._drag_ctrl: bool = False  # dragging Bezier control point
        self._hover_idx: Optional[int] = None
        self._selected_idx: Optional[int] = None
        self._current_curve_type = CurveType.LINEAR

        # Snap
        self._snap_division = "1/16"

        # v0.0.20.440: Active tool (pointer/pencil/eraser)
        self._active_tool = "pointer"
        self._pencil_drawing = False
        self._pencil_points: list = []  # [(beat, value), ...] for freehand draw
        self._eraser_dragging = False
        self._eraser_rect: Optional[QRectF] = None

        self.setMinimumHeight(100)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Ruler zoom handle (magnifier)
        self._zoom_handle_rect = QRect(6, 6, 16, 16)
        self._zoom_drag = False
        self._zoom_origin_y = 0.0
        self._zoom_origin_start = float(self._view_start)
        self._zoom_origin_end = float(self._view_end)
        self._zoom_anchor_x = 0.0
        self._zoom_anchor_beat = 0.0
        self._default_view_span = float(self._view_end - self._view_start) if (self._view_end > self._view_start) else 32.0

    # ─── Public API ───

    def set_parameter(self, parameter_id: str) -> None:
        """Set which parameter's automation lane to edit."""
        self._parameter_id = parameter_id
        self._selected_idx = None
        self._drag_point_idx = None
        self.update()

    def set_view_range(self, start_beat: float, end_beat: float) -> None:
        s, e = float(start_beat), float(end_beat)
        if e <= s:
            return
        self._view_start = max(0.0, s)
        self._view_end = max(self._view_start + 0.25, e)
        self.update()

    def set_playhead(self, beat: float) -> None:
        self._playhead_beat = float(beat)
        self.update()

    def set_snap_division(self, div: str) -> None:
        self._snap_division = str(div)

    def set_curve_type(self, ct: CurveType) -> None:
        """Set curve type for new points and selected point."""
        self._current_curve_type = ct
        lane = self._get_lane()
        if lane and self._selected_idx is not None and 0 <= self._selected_idx < len(lane.points):
            lane.points[self._selected_idx].curve_type = ct
            self._emit_change()
            self.update()

    # ─── Lane access ───

    def _get_lane(self) -> Optional[AutomationLane]:
        if not self._parameter_id:
            return None
        return self._mgr.get_lane(self._parameter_id)

    def _get_or_create_lane(self) -> AutomationLane:
        param = self._mgr.get_parameter(self._parameter_id)
        return self._mgr.get_or_create_lane(
            self._parameter_id,
            track_id=param.track_id if param else "",
            param_name=param.name if param else self._parameter_id,
        )

    def _emit_change(self) -> None:
        self.lane_changed.emit(self._parameter_id)

    # ─── Coordinate mapping ───

    def _px_to_beat(self, x: float) -> float:
        w = max(1.0, float(self.width() - 2 * self.MARGIN))
        span = max(1e-9, self._view_end - self._view_start)
        return self._view_start + ((x - self.MARGIN) / w) * span

    def _beat_to_px(self, beat: float) -> float:
        w = max(1.0, float(self.width() - 2 * self.MARGIN))
        span = max(1e-9, self._view_end - self._view_start)
        return self.MARGIN + ((beat - self._view_start) / span) * w

    def _px_to_value(self, y: float) -> float:
        h = max(1.0, float(self.height() - 2 * self.MARGIN))
        return 1.0 - max(0.0, min(1.0, (y - self.MARGIN) / h))

    def _value_to_px(self, value: float) -> float:
        h = max(1.0, float(self.height() - 2 * self.MARGIN))
        return self.MARGIN + (1.0 - max(0.0, min(1.0, value))) * h

    # ─── Hit testing ───

    def _hit_test_point(self, pos: QPointF, pts: List[BreakPoint]) -> Optional[int]:
        for i, pt in enumerate(pts):
            px = self._beat_to_px(pt.beat)
            py = self._value_to_px(pt.value)
            if (pos.x() - px) ** 2 + (pos.y() - py) ** 2 < self.HIT_RADIUS ** 2:
                return i
        return None

    def _hit_test_ctrl(self, pos: QPointF, pts: List[BreakPoint]) -> Optional[int]:
        """Hit test Bezier control points."""
        for i in range(len(pts) - 1):
            if pts[i].curve_type != CurveType.BEZIER:
                continue
            # Control point is at relative position within segment
            p0, p1 = pts[i], pts[i + 1]
            cx = self._beat_to_px(p0.beat + p0.bezier_cx * (p1.beat - p0.beat))
            cy = self._value_to_px(p0.value + p0.bezier_cy * (p1.value - p0.value))
            if (pos.x() - cx) ** 2 + (pos.y() - cy) ** 2 < self.HIT_RADIUS ** 2:
                return i
        return None

    # ─── Mouse events ───

    def _apply_view_span(self, new_span: float, anchor_beat: float, anchor_x: float) -> None:
        """Apply zoom by changing view span (beats) while keeping anchor stable."""
        try:
            new_span = float(max(0.5, min(512.0, new_span)))
            w = max(1.0, float(self.width() - 2 * self.MARGIN))
            t = max(0.0, min(1.0, (float(anchor_x) - float(self.MARGIN)) / w))
            new_start = max(0.0, float(anchor_beat) - t * new_span)
            self.set_view_range(new_start, new_start + new_span)
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:
        if not self._parameter_id:
            return
        pos = event.position()

        # Zoom handle drag start (magnifier in top-left)
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                self._zoom_drag = True
                self._zoom_origin_y = float(pos.y())
                self._zoom_origin_start = float(self._view_start)
                self._zoom_origin_end = float(self._view_end)
                self._zoom_anchor_x = float(pos.x())
                self._zoom_anchor_beat = float(self._px_to_beat(pos.x()))
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                event.accept()
                return
        except Exception:
            pass

        lane = self._get_lane()
        pts = lane.points if lane else []

        if event.button() == Qt.MouseButton.RightButton:
            # Delete nearest point (all tools)
            idx = self._hit_test_point(pos, pts)
            if idx is not None and lane:
                lane.points.pop(idx)
                lane.sort_points()
                self._selected_idx = None
                self._emit_change()
                self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            tool = getattr(self, '_active_tool', 'pointer')

            # ── Pencil tool: start freehand drawing ──
            if tool == "pencil":
                self._pencil_drawing = True
                beat = self._px_to_beat(pos.x())
                value = max(0.0, min(1.0, self._px_to_value(pos.y())))
                self._pencil_points = [(beat, value)]
                return

            # ── Eraser tool: start drag-delete area ──
            if tool == "eraser":
                self._eraser_dragging = True
                self._eraser_start = pos
                self._eraser_rect = QRectF(pos.x(), pos.y(), 0, 0)
                return

            # ── Pointer tool (default): existing behavior ──
            # Check Bezier control point first
            ctrl_idx = self._hit_test_ctrl(pos, pts)
            if ctrl_idx is not None:
                self._drag_point_idx = ctrl_idx
                self._drag_ctrl = True
                return

            # Check regular point
            idx = self._hit_test_point(pos, pts)
            if idx is not None:
                self._drag_point_idx = idx
                self._drag_ctrl = False
                self._selected_idx = idx
                self.update()
                return

            # Add new point
            beat = _snap_beats(self._px_to_beat(pos.x()), self._snap_division)
            value = self._px_to_value(pos.y())
            value = max(0.0, min(1.0, value))

            lane = self._get_or_create_lane()
            bp = BreakPoint(beat=beat, value=value, curve_type=self._current_curve_type)
            lane.points.append(bp)
            lane.sort_points()
            # Select the newly added point
            self._selected_idx = next(
                (i for i, p in enumerate(lane.points) if abs(p.beat - beat) < 1e-6),
                None,
            )
            self._emit_change()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()

        # Zoom drag in progress
        if getattr(self, '_zoom_drag', False):
            try:
                dy = float(pos.y()) - float(self._zoom_origin_y)
                span0 = max(1e-6, float(self._zoom_origin_end) - float(self._zoom_origin_start))
                factor = 1.0 + (dy / 160.0)  # drag down -> zoom out (bigger span)
                factor = max(0.25, min(4.0, factor))
                new_span = span0 * factor
                self._apply_view_span(new_span, float(self._zoom_anchor_beat), float(self._zoom_anchor_x))
                event.accept()
                return
            except Exception:
                pass

        # v0.0.20.440: Pencil freehand drawing
        if getattr(self, '_pencil_drawing', False):
            beat = self._px_to_beat(pos.x())
            value = max(0.0, min(1.0, self._px_to_value(pos.y())))
            self._pencil_points.append((beat, value))
            self.update()
            return

        # v0.0.20.440: Eraser drag area
        if getattr(self, '_eraser_dragging', False):
            start = getattr(self, '_eraser_start', pos)
            x1, y1 = min(start.x(), pos.x()), min(start.y(), pos.y())
            x2, y2 = max(start.x(), pos.x()), max(start.y(), pos.y())
            self._eraser_rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            self.update()
            return

        lane = self._get_lane()

        if self._drag_point_idx is not None and lane:
            pts = lane.points
            idx = self._drag_point_idx

            if self._drag_ctrl and 0 <= idx < len(pts) - 1:
                # Move Bezier control point
                p0 = pts[idx]
                p1 = pts[idx + 1]
                beat_span = p1.beat - p0.beat
                val_span = p1.value - p0.value

                beat = self._px_to_beat(pos.x())
                value = self._px_to_value(pos.y())

                if beat_span != 0:
                    p0.bezier_cx = max(0.0, min(1.0, (beat - p0.beat) / beat_span))
                if val_span != 0:
                    p0.bezier_cy = max(-0.5, min(1.5, (value - p0.value) / val_span))
                else:
                    p0.bezier_cy = 0.5

                self._emit_change()
                self.update()
                return

            if 0 <= idx < len(pts):
                beat = _snap_beats(self._px_to_beat(pos.x()), self._snap_division)
                value = max(0.0, min(1.0, self._px_to_value(pos.y())))
                pts[idx].beat = beat
                pts[idx].value = value
                lane.sort_points()
                self._emit_change()
                self.update()
            return

        # Hover detection
        if lane:
            old_hover = self._hover_idx
            self._hover_idx = self._hit_test_point(pos, lane.points)
            if self._hover_idx != old_hover:
                self.update()

    def mouseReleaseEvent(self, event) -> None:
        if getattr(self, '_zoom_drag', False):
            self._zoom_drag = False
            try:
                self.unsetCursor()
            except Exception:
                pass
            event.accept()
            return

        # v0.0.20.440: Pencil release — commit drawn points + auto-thin
        if getattr(self, '_pencil_drawing', False):
            self._pencil_drawing = False
            raw_pts = self._pencil_points
            self._pencil_points = []
            if raw_pts and len(raw_pts) >= 2:
                lane = self._get_or_create_lane()
                for beat, value in raw_pts:
                    bp = BreakPoint(beat=beat, value=value, curve_type=self._current_curve_type)
                    lane.points.append(bp)
                lane.sort_points()
                # Auto-thin the freehand drawing (Bitwig-style clean curves)
                lane.thin(0.012)
                self._emit_change()
            self.update()
            return

        # v0.0.20.440: Eraser release — delete all points inside drag rect
        if getattr(self, '_eraser_dragging', False):
            self._eraser_dragging = False
            rect = self._eraser_rect
            self._eraser_rect = None
            if rect and rect.width() > 2 and rect.height() > 2:
                lane = self._get_lane()
                if lane and lane.points:
                    beat_lo = self._px_to_beat(rect.x())
                    beat_hi = self._px_to_beat(rect.x() + rect.width())
                    val_lo = self._px_to_value(rect.y() + rect.height())
                    val_hi = self._px_to_value(rect.y())
                    before = len(lane.points)
                    lane.points = [
                        p for p in lane.points
                        if not (beat_lo <= p.beat <= beat_hi and val_lo <= p.value <= val_hi)
                    ]
                    if len(lane.points) < before:
                        self._emit_change()
            self.update()
            return

        self._drag_point_idx = None
        self._drag_ctrl = False

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click magnifier resets the view span."""
        try:
            pos = event.position()
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                anchor_x = float(pos.x())
                anchor_beat = float(self._px_to_beat(pos.x()))
                new_span = float(getattr(self, '_default_view_span', 32.0) or 32.0)
                self._apply_view_span(new_span, anchor_beat, anchor_x)
                event.accept()
                return
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        """Wheel on magnifier = horizontal zoom in/out."""
        try:
            pos = event.position()
            if self._zoom_handle_rect.contains(int(pos.x()), int(pos.y())):
                dy = float(event.angleDelta().y())
                factor = 1.15 if dy > 0 else 1.0 / 1.15
                span = max(1e-6, float(self._view_end) - float(self._view_start))
                new_span = span / factor
                self._apply_view_span(new_span, float(self._px_to_beat(pos.x())), float(pos.x()))
                event.accept()
                return
        except Exception:
            pass
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        """Delete selected point with Del/Backspace."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            lane = self._get_lane()
            if lane and self._selected_idx is not None and 0 <= self._selected_idx < len(lane.points):
                lane.points.pop(self._selected_idx)
                self._selected_idx = None
                self._emit_change()
                self.update()
                event.accept()
                return
        super().keyPressEvent(event)

    # ─── Paint ───
    # ─── Paint ───

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(self.rect(), COL_BG)

        # Grid
        self._draw_grid(p, w, h)

        # Zoom handle icon (magnifier)
        try:
            paint_magnifier(p, self._zoom_handle_rect, color=COL_TEXT)
        except Exception:
            pass

        # Border
        p.setPen(QPen(COL_BORDER, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        lane = self._get_lane()
        pts = lane.points if lane else []
        enabled = lane.enabled if lane else False

        if not self._parameter_id:
            p.setPen(QPen(COL_TEXT))
            p.drawText(self.MARGIN + 4, self.MARGIN + 14, "Kein Parameter ausgewählt")
            p.end()
            return

        if not pts:
            p.setPen(QPen(COL_TEXT))
            p.drawText(self.MARGIN + 4, self.MARGIN + 14, "Klick = Punkt setzen | Rechtsklick = löschen")
            p.end()
            return

        curve_color = COL_CURVE if enabled else COL_CURVE_DISABLED

        # Draw curve segments
        self._draw_curve(p, pts, curve_color)

        # Draw Bezier control points + helper lines
        self._draw_bezier_controls(p, pts)

        # Draw points
        self._draw_points(p, pts)

        # Playhead
        ph_x = self._beat_to_px(self._playhead_beat)
        if self.MARGIN <= ph_x <= w - self.MARGIN:
            p.setPen(QPen(COL_PLAYHEAD, 1.5))
            p.drawLine(QPointF(ph_x, self.MARGIN), QPointF(ph_x, h - self.MARGIN))

        # Value readout for hovered point
        if self._hover_idx is not None and 0 <= self._hover_idx < len(pts):
            pt = pts[self._hover_idx]
            self._draw_tooltip(p, pt)

        # v0.0.20.440: Pencil freehand preview
        pencil_pts = getattr(self, '_pencil_points', [])
        if pencil_pts and len(pencil_pts) >= 2:
            pen = QPen(QColor(255, 200, 0, 200), 2.0)
            p.setPen(pen)
            for i in range(1, len(pencil_pts)):
                x0, y0 = self._beat_to_px(pencil_pts[i-1][0]), self._value_to_px(pencil_pts[i-1][1])
                x1, y1 = self._beat_to_px(pencil_pts[i][0]), self._value_to_px(pencil_pts[i][1])
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        # v0.0.20.440: Eraser selection rect
        eraser_rect = getattr(self, '_eraser_rect', None)
        if eraser_rect and eraser_rect.width() > 0:
            p.setPen(QPen(QColor(255, 80, 80, 200), 1.0, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(255, 80, 80, 40)))
            p.drawRect(eraser_rect)

        p.end()

    def _draw_grid(self, p: QPainter, w: int, h: int) -> None:
        """Draw beat/bar grid lines."""
        span = max(1e-6, self._view_end - self._view_start)
        beats_per_bar = 4.0  # TODO: from time signature

        # Determine grid density
        pixels_per_beat = (w - 2 * self.MARGIN) / span
        if pixels_per_beat < 5:
            step = beats_per_bar * 4  # every 4 bars
        elif pixels_per_beat < 15:
            step = beats_per_bar  # every bar
        elif pixels_per_beat < 40:
            step = 1.0  # every beat
        else:
            step = 0.25  # every 16th

        # Vertical grid lines
        b = math.floor(self._view_start / step) * step
        while b <= self._view_end:
            x = self._beat_to_px(b)
            if self.MARGIN <= x <= w - self.MARGIN:
                is_bar = abs(b % beats_per_bar) < 0.001
                p.setPen(QPen(COL_GRID_MAJOR if is_bar else COL_GRID_MINOR, 1))
                p.drawLine(int(x), self.MARGIN, int(x), h - self.MARGIN)

                # Bar number
                if is_bar and pixels_per_beat >= 8:
                    bar_num = int(b / beats_per_bar) + 1
                    p.setPen(QPen(COL_TEXT))
                    font = p.font()
                    font.setPointSize(7)
                    p.setFont(font)
                    tx = int(x) + 2
                    try:
                        if self._zoom_handle_rect.intersects(QRect(tx, self.MARGIN, 18, 14)):
                            tx = self._zoom_handle_rect.right() + 6
                    except Exception:
                        pass
                    p.drawText(tx, self.MARGIN + 10, str(bar_num))
            b += step

        # Horizontal grid: 0%, 25%, 50%, 75%, 100%
        for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = self._value_to_px(frac)
            p.setPen(QPen(COL_GRID_MAJOR if frac == 0.5 else COL_GRID_MINOR, 1))
            p.drawLine(self.MARGIN, int(y), w - self.MARGIN, int(y))

    def _draw_curve(self, p: QPainter, pts: List[BreakPoint], color: QColor) -> None:
        """Draw the automation curve with proper interpolation visualization."""
        if len(pts) < 2:
            if pts:
                # Single point: draw horizontal line
                y = self._value_to_px(pts[0].value)
                p.setPen(QPen(color, 2))
                p.drawLine(self.MARGIN, int(y), self.width() - self.MARGIN, int(y))
            return

        p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            x0, y0 = self._beat_to_px(p0.beat), self._value_to_px(p0.value)
            x1, y1 = self._beat_to_px(p1.beat), self._value_to_px(p1.value)

            if p0.curve_type == CurveType.STEP:
                # Horizontal then vertical
                p.drawLine(QPointF(x0, y0), QPointF(x1, y0))
                p.drawLine(QPointF(x1, y0), QPointF(x1, y1))

            elif p0.curve_type == CurveType.BEZIER:
                # QPainterPath quadratic Bezier
                cx_rel = p0.bezier_cx
                cy_rel = p0.bezier_cy
                ctrl_x = x0 + cx_rel * (x1 - x0)
                ctrl_y = self._value_to_px(p0.value + cy_rel * (p1.value - p0.value))

                path = QPainterPath()
                path.moveTo(x0, y0)
                path.quadTo(ctrl_x, ctrl_y, x1, y1)
                p.drawPath(path)

            elif p0.curve_type == CurveType.SMOOTH:
                # Approximate S-curve with many line segments
                path = QPainterPath()
                path.moveTo(x0, y0)
                steps = max(8, int(abs(x1 - x0) / 3))
                for s in range(1, steps + 1):
                    t = s / steps
                    # Cubic ease-in-out
                    t_smooth = t * t * (3.0 - 2.0 * t)
                    bx = x0 + t * (x1 - x0)
                    bv = p0.value + t_smooth * (p1.value - p0.value)
                    by = self._value_to_px(bv)
                    path.lineTo(bx, by)
                p.drawPath(path)

            else:
                # LINEAR
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        # Extend from first point to left edge
        if pts:
            y_first = self._value_to_px(pts[0].value)
            x_first = self._beat_to_px(pts[0].beat)
            old_pen = p.pen()
            p.setPen(QPen(color.darker(150), 1, Qt.PenStyle.DashLine))
            p.drawLine(self.MARGIN, int(y_first), int(x_first), int(y_first))
            # Extend from last point to right edge
            y_last = self._value_to_px(pts[-1].value)
            x_last = self._beat_to_px(pts[-1].beat)
            p.drawLine(int(x_last), int(y_last), self.width() - self.MARGIN, int(y_last))
            p.setPen(old_pen)

    def _draw_bezier_controls(self, p: QPainter, pts: List[BreakPoint]) -> None:
        """Draw Bezier control points and helper lines."""
        for i in range(len(pts) - 1):
            if pts[i].curve_type != CurveType.BEZIER:
                continue
            p0, p1 = pts[i], pts[i + 1]
            x0, y0 = self._beat_to_px(p0.beat), self._value_to_px(p0.value)
            x1, y1 = self._beat_to_px(p1.beat), self._value_to_px(p1.value)

            cx = x0 + p0.bezier_cx * (x1 - x0)
            cy = self._value_to_px(p0.value + p0.bezier_cy * (p1.value - p0.value))

            # Helper lines
            p.setPen(QPen(COL_BEZIER_LINE, 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x0, y0), QPointF(cx, cy))
            p.drawLine(QPointF(cx, cy), QPointF(x1, y1))

            # Control point diamond
            p.setPen(QPen(COL_BEZIER_CTRL, 1))
            p.setBrush(QBrush(COL_BEZIER_CTRL))
            diamond = QPainterPath()
            r = self.CTRL_RADIUS
            diamond.moveTo(cx, cy - r)
            diamond.lineTo(cx + r, cy)
            diamond.lineTo(cx, cy + r)
            diamond.lineTo(cx - r, cy)
            diamond.closeSubpath()
            p.drawPath(diamond)

    def _draw_points(self, p: QPainter, pts: List[BreakPoint]) -> None:
        """Draw automation breakpoints."""
        for i, pt in enumerate(pts):
            x = self._beat_to_px(pt.beat)
            y = self._value_to_px(pt.value)

            if i == self._selected_idx:
                color = COL_POINT_SELECTED
                radius = self.POINT_RADIUS + 1
            elif i == self._hover_idx:
                color = COL_POINT_HOVER
                radius = self.POINT_RADIUS + 1
            else:
                color = COL_POINT
                radius = self.POINT_RADIUS

            p.setPen(QPen(color, 1.5))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(x, y), radius, radius)

            # Curve type indicator
            if pt.curve_type == CurveType.BEZIER:
                p.setPen(QPen(COL_BEZIER_CTRL, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x, y), radius + 3, radius + 3)

    def _draw_tooltip(self, p: QPainter, pt: BreakPoint) -> None:
        """Draw value tooltip near hovered point."""
        x = self._beat_to_px(pt.beat)
        y = self._value_to_px(pt.value)

        text = f"Beat: {pt.beat:.2f}  Value: {pt.value:.3f}  [{pt.curve_type.value}]"
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 8
        th = fm.height() + 4

        tx = min(x + 10, self.width() - tw - 4)
        ty = max(y - th - 8, 4)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(COL_VALUE_BG))
        p.drawRoundedRect(QRectF(tx, ty, tw, th), 3, 3)

        p.setPen(QPen(COL_TEXT))
        p.drawText(QRectF(tx + 4, ty + 2, tw - 8, th - 4), Qt.AlignmentFlag.AlignLeft, text)


# ─── Lane Strip (v0.0.20.432 — Multi-Lane Stacking) ─────────────────────

class _LaneStrip(QWidget):
    """Single automation lane with its own parameter selector + curve editor.

    Used by EnhancedAutomationLanePanel to show multiple lanes simultaneously.
    Each strip has:
    - Mini header: [parameter combo] [curve combo] [close button]
    - EnhancedAutomationEditor below

    v0.0.20.432: Bitwig-style multi-lane stacking.
    """

    close_requested = Signal(object)  # self

    def __init__(self, mgr: AutomationManager, project: Any = None, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── Header bar ──
        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 0)
        header.setSpacing(4)

        self.cmb_param = QComboBox()
        self.cmb_param.setEditable(True)
        self.cmb_param.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cmb_param.setMinimumWidth(100)
        self.cmb_param.setMaximumHeight(22)
        header.addWidget(self.cmb_param, 1)

        self.cmb_curve = QComboBox()
        self.cmb_curve.addItems(["linear", "bezier", "step", "smooth"])
        self.cmb_curve.setMaximumWidth(80)
        self.cmb_curve.setMaximumHeight(22)
        header.addWidget(self.cmb_curve)

        # v0.0.20.440: Lane tool buttons (Bitwig-style)
        _tool_style = (
            "QToolButton { color: #888; padding: 1px 4px; font-size: 11px; border: none; }"
            "QToolButton:checked { color: #fff; background: #3a6fa0; border-radius: 2px; }"
        )
        self.btn_tool_ptr = QToolButton()
        self.btn_tool_ptr.setText("↖")
        self.btn_tool_ptr.setToolTip("Pointer — Punkte auswählen/verschieben")
        self.btn_tool_ptr.setCheckable(True)
        self.btn_tool_ptr.setChecked(True)
        self.btn_tool_ptr.setMaximumSize(22, 22)
        self.btn_tool_ptr.setStyleSheet(_tool_style)
        header.addWidget(self.btn_tool_ptr)

        self.btn_tool_pen = QToolButton()
        self.btn_tool_pen.setText("✏")
        self.btn_tool_pen.setToolTip("Pencil — Freihand zeichnen (mit Auto-Thin)")
        self.btn_tool_pen.setCheckable(True)
        self.btn_tool_pen.setMaximumSize(22, 22)
        self.btn_tool_pen.setStyleSheet(_tool_style)
        header.addWidget(self.btn_tool_pen)

        self.btn_tool_eraser = QToolButton()
        self.btn_tool_eraser.setText("⌫")
        self.btn_tool_eraser.setToolTip("Eraser — Punkte löschen per Drag")
        self.btn_tool_eraser.setCheckable(True)
        self.btn_tool_eraser.setMaximumSize(22, 22)
        self.btn_tool_eraser.setStyleSheet(_tool_style)
        header.addWidget(self.btn_tool_eraser)

        # Make tool buttons mutually exclusive
        self.btn_tool_ptr.clicked.connect(lambda: self._set_tool("pointer"))
        self.btn_tool_pen.clicked.connect(lambda: self._set_tool("pencil"))
        self.btn_tool_eraser.clicked.connect(lambda: self._set_tool("eraser"))

        self.btn_clear = QToolButton()
        self.btn_clear.setText("🗑")
        self.btn_clear.setToolTip("Lane leeren")
        self.btn_clear.setMaximumSize(22, 22)
        header.addWidget(self.btn_clear)

        self.btn_close = QToolButton()
        self.btn_close.setText("×")
        self.btn_close.setToolTip("Lane entfernen")
        self.btn_close.setMaximumSize(22, 22)
        header.addWidget(self.btn_close)

        layout.addLayout(header)

        # ── Separator line ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setMaximumHeight(1)
        layout.addWidget(line)

        # ── Editor ──
        self.editor = EnhancedAutomationEditor(mgr, project)
        self.editor.setMinimumHeight(60)
        layout.addWidget(self.editor, 1)

        # ── Connections ──
        self.cmb_param.currentIndexChanged.connect(self._on_param_changed)
        self.cmb_curve.currentTextChanged.connect(self._on_curve_changed)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_close.clicked.connect(lambda: self.close_requested.emit(self))

    def parameter_id(self) -> str:
        return str(self.cmb_param.currentData() or "")

    def set_parameter(self, parameter_id: str) -> None:
        idx = self.cmb_param.findData(parameter_id)
        if idx >= 0:
            self.cmb_param.setCurrentIndex(idx)
        self.editor.set_parameter(parameter_id)

    def populate_params(self, items: list) -> None:
        """Fill the parameter combo. items = [(label, data), ...]"""
        old = self.cmb_param.currentData()
        self.cmb_param.blockSignals(True)
        self.cmb_param.clear()
        for label, data in items:
            self.cmb_param.addItem(label, data)
        if old:
            idx = self.cmb_param.findData(old)
            if idx >= 0:
                self.cmb_param.setCurrentIndex(idx)
        self.cmb_param.blockSignals(False)

    def _on_param_changed(self, index: int = 0) -> None:
        pid = self.cmb_param.currentData() or ""
        self.editor.set_parameter(pid)

    def _on_curve_changed(self, text: str) -> None:
        ct_map = {
            "linear": CurveType.LINEAR, "bezier": CurveType.BEZIER,
            "step": CurveType.STEP, "smooth": CurveType.SMOOTH,
        }
        self.editor.set_curve_type(ct_map.get(text, CurveType.LINEAR))

    def _on_clear(self) -> None:
        pid = self.parameter_id()
        if pid:
            lane = self._mgr.get_lane(pid)
            if lane:
                lane.points.clear()
                self.editor.update()

    def _set_tool(self, tool: str) -> None:
        """v0.0.20.440: Set active lane tool and update button states."""
        self.btn_tool_ptr.setChecked(tool == "pointer")
        self.btn_tool_pen.setChecked(tool == "pencil")
        self.btn_tool_eraser.setChecked(tool == "eraser")
        self.editor._active_tool = tool


# ─── Enhanced Automation Lane Panel ───────────────────────────────────────

class EnhancedAutomationLanePanel(QWidget):
    """Full automation panel with track/parameter selection + curve editor.

    v0.0.20.432: Multi-Lane Stacking (Bitwig-style).

    Features:
    - Multiple automation lanes visible simultaneously
    - Each lane has its own parameter + curve selector
    - "+" button to add lanes, "×" to remove
    - Track + Mode selectors shared across all lanes
    - Touch/Latch automation modes
    """

    def __init__(self, automation_manager: AutomationManager, project: Any = None, parent=None):
        super().__init__(parent)
        self._mgr = automation_manager
        self._project = project

        self._build_ui()
        self._connect_signals()

        # React to external "show automation" requests
        self._mgr.request_show_automation.connect(self._on_show_request)

        if self._project:
            try:
                self._project.project_updated.connect(self._refresh_tracks)
            except Exception:
                pass
        self._refresh_tracks()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Left: Track + Mode (shared across all lanes)
        left = QVBoxLayout()
        left.setSpacing(4)

        left.addWidget(QLabel("Track:"))
        self.cmb_track = QComboBox()
        self.cmb_track.setMaximumWidth(200)
        left.addWidget(self.cmb_track)

        left.addWidget(QLabel("Mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["off", "read", "write", "touch", "latch"])
        self.cmb_mode.setMaximumWidth(200)
        self.cmb_mode.setToolTip(
            "off = keine Automation\n"
            "read = Automation abspielen\n"
            "write = Automation aufzeichnen (immer)\n"
            "touch = Aufzeichnen nur solange Controller bewegt\n"
            "latch = Aufzeichnen ab erstem CC bis Transport-Stop"
        )
        left.addWidget(self.cmb_mode)

        # v0.0.20.433: Quick REC button — toggles touch mode for instant recording
        self.btn_rec = QPushButton("● REC")
        self.btn_rec.setCheckable(True)
        self.btn_rec.setMaximumWidth(200)
        self.btn_rec.setToolTip(
            "Automation aufzeichnen (Touch-Modus).\n"
            "Drehe einen MIDI-Knob/Slider und die Kurve\n"
            "wird live in die Automation-Lane geschrieben."
        )
        self.btn_rec.setStyleSheet(
            "QPushButton { color: #aaa; border: 1px solid #555; padding: 3px 8px; border-radius: 3px; }"
            "QPushButton:checked { color: #fff; background: #cc2020; border: 1px solid #ff4040; font-weight: bold; }"
        )
        left.addWidget(self.btn_rec)

        # Actions
        self.btn_actions = QToolButton()
        self.btn_actions.setText("⋯")
        self.btn_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        actions_menu = QMenu(self.btn_actions)
        self._a_clear = actions_menu.addAction("🗑 Aktive Lane leeren")
        self._a_enable = actions_menu.addAction("✅ Lane aktiv")
        self._a_enable.setCheckable(True)
        self._a_enable.setChecked(True)
        self.btn_actions.setMenu(actions_menu)
        left.addWidget(self.btn_actions)

        # v0.0.20.432: Add Lane button
        self.btn_add_lane = QPushButton("+ Lane")
        self.btn_add_lane.setToolTip("Weitere Automation-Lane hinzufügen (Multi-Lane)")
        self.btn_add_lane.setMaximumWidth(200)
        left.addWidget(self.btn_add_lane)

        left.addStretch(1)
        layout.addLayout(left, 0)

        # Right: Multi-Lane Stack (v0.0.20.432)
        self._lane_strips: List[_LaneStrip] = []
        self._lane_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self._lane_splitter, 1)

        # Create the initial lane strip
        self._add_lane_strip()

        # ── Backward compat aliases ──
        # self.editor = first strip's editor (for set_playhead/set_view_range)
        # self.cmb_param = first strip's combo (for _refresh_params, _on_show_request)
        self._update_compat_aliases()

    def _add_lane_strip(self, parameter_id: str = "") -> _LaneStrip:
        """Add a new lane strip to the multi-lane stack."""
        strip = _LaneStrip(self._mgr, self._project)
        strip.close_requested.connect(self._on_lane_strip_close)
        self._lane_strips.append(strip)
        self._lane_splitter.addWidget(strip)

        # Populate with current track's parameters
        self._populate_strip_params(strip)

        # If a specific parameter was requested, select it
        if parameter_id:
            strip.set_parameter(parameter_id)

        # Hide close button if only one lane
        self._update_close_buttons()
        self._update_compat_aliases()
        return strip

    def _on_lane_strip_close(self, strip: _LaneStrip) -> None:
        """Remove a lane strip from the stack."""
        if len(self._lane_strips) <= 1:
            return  # always keep at least one
        if strip in self._lane_strips:
            self._lane_strips.remove(strip)
            strip.setParent(None)
            strip.deleteLater()
        self._update_close_buttons()
        self._update_compat_aliases()

    def _update_close_buttons(self) -> None:
        """Hide close button when only 1 lane."""
        single = len(self._lane_strips) <= 1
        for s in self._lane_strips:
            try:
                s.btn_close.setVisible(not single)
            except Exception:
                pass

    def _update_compat_aliases(self) -> None:
        """Keep self.editor and self.cmb_param pointing to first strip."""
        if self._lane_strips:
            self.editor = self._lane_strips[0].editor
            self.cmb_param = self._lane_strips[0].cmb_param
            # Also set up a cmb_curve alias for backward compat
            self.cmb_curve = self._lane_strips[0].cmb_curve
        else:
            self.editor = EnhancedAutomationEditor(self._mgr, self._project)
            self.cmb_param = QComboBox()
            self.cmb_curve = QComboBox()

    def _populate_strip_params(self, strip: _LaneStrip) -> None:
        """Fill a strip's parameter combo with current track's parameters."""
        tid = self.cmb_track.currentData() or ""
        items = []

        # Always show Volume + Pan
        items.append(("Volume", f"trk:{tid}:volume"))
        items.append(("Pan", f"trk:{tid}:pan"))

        # Registered FX parameters
        for param in self._mgr.get_parameters_for_track(tid):
            pid = param.parameter_id
            if pid.endswith(":volume") or pid.endswith(":pan"):
                continue
            items.append((f"🎛 {param.name}", pid))

        # MIDI-recorded lanes
        shown = {d for _, d in items}
        for lane in self._mgr.get_lanes_for_track(tid):
            if lane.parameter_id not in shown:
                label = lane.param_name or lane.parameter_id.split(":")[-1]
                items.append((f"📈 {label}", lane.parameter_id))

        strip.populate_params(items)

    def _connect_signals(self) -> None:
        self.cmb_track.currentIndexChanged.connect(self._on_track_changed)
        self.cmb_mode.currentTextChanged.connect(self._on_mode_changed)
        self.btn_rec.clicked.connect(self._on_rec_toggled)
        self._a_clear.triggered.connect(self._on_clear_lane)
        self._a_enable.triggered.connect(self._on_toggle_enable)
        self.btn_add_lane.clicked.connect(self._on_add_lane_clicked)

        # v0.0.20.431: Repaint editors when MIDI recording adds automation points
        try:
            self._mgr.lane_data_changed.connect(self._on_external_lane_update)
        except Exception:
            pass

    # ─── Track/Param refresh ───

    def _refresh_tracks(self) -> None:
        """Populate track combobox from project."""
        old_tid = self.cmb_track.currentData()
        self.cmb_track.blockSignals(True)
        self.cmb_track.clear()

        if self._project:
            proj = getattr(self._project, "ctx", None)
            if proj:
                proj = getattr(proj, "project", None)
            if not proj:
                proj = getattr(self._project, "project", None)
            if proj:
                for t in getattr(proj, "tracks", []):
                    label = f"{getattr(t, 'name', '?')} [{getattr(t, 'kind', '?')}]"
                    self.cmb_track.addItem(label, getattr(t, "id", ""))

        # Restore selection
        if old_tid:
            idx = self.cmb_track.findData(old_tid)
            if idx >= 0:
                self.cmb_track.setCurrentIndex(idx)

        self.cmb_track.blockSignals(False)
        self._refresh_params()

    def _refresh_params(self) -> None:
        """Populate parameter combos for all lane strips."""
        for strip in self._lane_strips:
            self._populate_strip_params(strip)

    # ─── Slots ───

    def _on_track_changed(self, index: int) -> None:
        self._refresh_params()
        tid = self.cmb_track.currentData() or ""
        # Update mode combobox
        if self._project:
            proj = getattr(self._project, "ctx", None)
            if proj:
                proj = getattr(proj, "project", None)
            if not proj:
                proj = getattr(self._project, "project", None)
            if proj:
                trk = next((t for t in getattr(proj, "tracks", []) if getattr(t, "id", "") == tid), None)
                if trk:
                    self.cmb_mode.blockSignals(True)
                    self.cmb_mode.setCurrentText(getattr(trk, "automation_mode", "off"))
                    self.cmb_mode.blockSignals(False)
                    # v0.0.20.433: Sync REC button
                    try:
                        mode = getattr(trk, "automation_mode", "off")
                        self.btn_rec.blockSignals(True)
                        self.btn_rec.setChecked(mode in ("write", "touch", "latch"))
                        self.btn_rec.blockSignals(False)
                    except Exception:
                        pass

    def _on_add_lane_clicked(self) -> None:
        """v0.0.20.432: Add a new automation lane strip."""
        if len(self._lane_strips) >= 8:
            return  # sane limit
        strip = self._add_lane_strip()
        # Default to next unused parameter
        used_pids = {s.parameter_id() for s in self._lane_strips if s is not strip}
        for i in range(strip.cmb_param.count()):
            pid = strip.cmb_param.itemData(i)
            if pid and pid not in used_pids:
                strip.cmb_param.setCurrentIndex(i)
                break

    def _on_mode_changed(self, mode: str) -> None:
        tid = self.cmb_track.currentData() or ""
        if not tid or not self._project:
            return
        proj = getattr(self._project, "ctx", None)
        if proj:
            proj = getattr(proj, "project", None)
        if not proj:
            proj = getattr(self._project, "project", None)
        if proj:
            trk = next((t for t in getattr(proj, "tracks", []) if getattr(t, "id", "") == tid), None)
            if trk:
                trk.automation_mode = str(mode)
                try:
                    self._project.project_updated.emit()
                except Exception:
                    pass
        # v0.0.20.433: Sync REC button with mode dropdown
        try:
            self.btn_rec.blockSignals(True)
            self.btn_rec.setChecked(mode in ("write", "touch", "latch"))
            self.btn_rec.blockSignals(False)
        except Exception:
            pass

    def _on_rec_toggled(self, checked: bool) -> None:
        """v0.0.20.433: Quick REC toggle — switches between read and touch mode.

        Touch mode is the most intuitive for live knob recording:
        it records while you move the controller and stops automatically.
        """
        if checked:
            self.cmb_mode.setCurrentText("touch")
        else:
            self.cmb_mode.setCurrentText("read")

    def _on_clear_lane(self) -> None:
        """Clear the first strip's active lane."""
        pid = self.cmb_param.currentData() or ""
        if pid:
            lane = self._mgr.get_lane(pid)
            if lane:
                lane.points.clear()
                self.editor.update()

    def _on_toggle_enable(self, checked: bool) -> None:
        pid = self.cmb_param.currentData() or ""
        if pid:
            lane = self._mgr.get_lane(pid)
            if lane:
                lane.enabled = checked
                self.editor.update()

    def _on_show_request(self, parameter_id: str) -> None:
        """Handle request from a widget to show its automation.

        v0.0.20.432: Adds a new lane strip if the parameter isn't already shown.
        """
        # Find the track
        param = self._mgr.get_parameter(parameter_id)
        if param and param.track_id:
            idx = self.cmb_track.findData(param.track_id)
            if idx >= 0:
                self.cmb_track.setCurrentIndex(idx)

        # Check if any existing strip already shows this parameter
        for strip in self._lane_strips:
            if strip.parameter_id() == parameter_id:
                # Already visible — nothing to do
                if self.cmb_mode.currentText() == "off":
                    self.cmb_mode.setCurrentText("read")
                return

        # Auto-register the lane
        self._mgr.get_or_create_lane(parameter_id)
        self._refresh_params()

        # If the first strip is on a default param, reuse it; otherwise add a new strip
        first_pid = self._lane_strips[0].parameter_id() if self._lane_strips else ""
        if first_pid.endswith(":volume") and len(self._lane_strips) == 1:
            # Reuse the only strip
            self._lane_strips[0].set_parameter(parameter_id)
        else:
            # Add a new strip for this parameter
            self._add_lane_strip(parameter_id)

        # Ensure mode is at least "read"
        if self.cmb_mode.currentText() == "off":
            self.cmb_mode.setCurrentText("read")

    def _on_external_lane_update(self, parameter_id: str) -> None:
        """v0.0.20.431: Repaint editors when MIDI recording adds points.

        v0.0.20.432: Check ALL lane strips, not just the first one.
        """
        try:
            for strip in self._lane_strips:
                if strip.parameter_id() == parameter_id:
                    strip.editor.update()
        except Exception:
            pass

    # ─── External sync ───

    def set_playhead(self, beat: float) -> None:
        """Update playhead on ALL lane strip editors."""
        for strip in self._lane_strips:
            try:
                strip.editor.set_playhead(float(beat))
            except Exception:
                pass

    def set_view_range(self, start_beat: float, end_beat: float) -> None:
        """Sync view range to ALL lane strip editors."""
        for strip in self._lane_strips:
            try:
                strip.editor.set_view_range(float(start_beat), float(end_beat))
            except Exception:
                pass

    def set_snap_division(self, div: str) -> None:
        for strip in self._lane_strips:
            try:
                strip.editor.set_snap_division(div)
            except Exception:
                pass
