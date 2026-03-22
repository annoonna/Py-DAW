"""Note Expression Lane (UI).

This widget is an optional, safe addition that visualizes and edits the
active Note Expression param for a single target note.

Stability rule (project directive): this lane is *opt-in* and does not
interfere with existing Piano-Roll note tools (move/resize/knife/etc.).

Target note selection priority:
1) Focus note (double-click focus mode)
2) Single selection
3) Hover note

Edit Tools:
- Draw:   left-drag to add/update sparse points
- Select: click point to select (multi-select via lasso), drag to move (t/v).
          Del = delete selected points.
- Erase:  left-drag to remove points near cursor

New in v0.0.20.199 (Lane Pro Tools, safe):
- Point constraints: SHIFT while dragging -> lock horizontal/vertical (auto-detect)
- Curve types: per segment (linear vs smooth). Toggle:
    * Press C to toggle segment near cursor (or segment after selected point)
    * Right-click on curve (not on point) toggles nearest segment
- Lasso-select: Select tool, drag in empty area to lasso points
- Quantize/Thin points:
    * Q = Quantize selected points to current grid
    * T = Thin selected points (remove redundant/too-close points)
New in v0.0.20.200 (Lane UX, safe):
- Segment UI affordances: small badges/handles on each segment (L/S) with hover highlight.
  * Left-click badge toggles that segment (linear <-> smooth).
  * Right-click segment/badge opens a context menu (no need for hotkeys).
- Context menu:
  * Segment: Set Linear / Set Smooth / Toggle / Insert Point
  * Point: Delete (Ctrl+RMB opens menu, otherwise quick delete keeps old behavior)
  * Empty: Quantize selected / Thin selected / Clear selection
- Value snapping per param:
  * Default ON in lane: values snap (velocity/chance/timbre/pressure/gain/pan) to 0.01,
    micropitch snaps to 0.05 semitones.
  * Hold ALT to edit free (no snapping).

New in v0.0.20.201 (Lane UX polish, safe):
- Segment-Badges now use icons (line/curve) instead of plain letters, with hover tooltips.
- Small on-canvas legend (top-right) explains the icons (Linear vs Smooth).


Other interactions:
- Right click on a point: delete it
- Double click: add a point (Draw) / delete point (Select)
- Undo/Redo: one snapshot per gesture (press -> release)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Set, Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget, QMenu, QToolTip, QSizePolicy, QDialog, QVBoxLayout


@dataclass
class _LaneDrag:
    before_snapshot: object
    idx: int
    param: str
    tool: str
    point_indices: Optional[List[int]] = None  # original indices (pre-sort) for select-drag
    start_pos: Optional[QPointF] = None
    start_points: Optional[List[Tuple[float, float]]] = None  # (t,v) per dragged point
    axis_lock: Optional[str] = None  # None | "x" | "y"


class NoteExpressionLane(QWidget):
    TOOL_DRAW = "draw"
    TOOL_SELECT = "select"
    TOOL_ERASE = "erase"

    def __init__(self, canvas, scroll_area, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.scroll_area = scroll_area

        self._drag: _LaneDrag | None = None
        self._tool_mode: str = self.TOOL_DRAW

        # selection
        self._selected_points: Set[int] = set()

        # lasso
        self._lasso_active: bool = False
        self._lasso_start: QPointF | None = None
        self._lasso_rect: QRectF | None = None

        # segment badges (for curve types)
        self._seg_badges: List[Tuple[QRectF, int, str]] = []  # (rect, seg_index, type)
        self._hover_point: int | None = None
        self._hover_segment: int | None = None
        self._hover_badge: int | None = None
        self._tooltip_key = None  # (\"badge\", seg_i, typ)
        self._last_mouse_pos: QPointF = QPointF(0.0, 0.0)

        # Zoom (visual only): improves readability without permanently stealing vertical space.
        # Ctrl+MouseWheel adjusts zoom. Context menu can open a bigger "Zoom" window.
        self._zoom_y: float = 1.0
        self._zoom_dialog = None

        # Height is controlled by PianoRollEditor (so it can truly collapse).
        self.setMinimumHeight(0)
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        try:
            self.setMouseTracking(True)
        except Exception:
            pass

        # Repaint on scroll/zoom/param change
        try:
            self.scroll_area.horizontalScrollBar().valueChanged.connect(self.update)
        except Exception:
            pass
        try:
            eng = getattr(self.canvas, "note_expression_engine", None)
            if eng is not None:
                eng.changed.connect(self.update)
        except Exception:
            pass
        # Selection/focus/hover changes on the PianoRoll canvas do not necessarily
        # emit engine.changed, but the lane target depends on them. A tiny UI-only
        # poll keeps the lane (and the detached zoom window) in sync without
        # touching audio/model code.
        self._last_target_key = None
        try:
            self._target_poll = QTimer(self)
            self._target_poll.setInterval(80)
            self._target_poll.timeout.connect(self._poll_target_change)
            self._target_poll.start()
        except Exception:
            self._target_poll = None

    def _poll_target_change(self) -> None:
        try:
            idx, note = self._target_note()
            key = (
                str(getattr(self.canvas, "clip_id", "") or ""),
                int(idx),
                int(getattr(self.canvas, "_expr_hover_idx", -1) or -1),
                -1 if getattr(self.canvas, "_expr_focus_idx", None) is None else int(getattr(self.canvas, "_expr_focus_idx", -1)),
                tuple(sorted(int(x) for x in (getattr(self.canvas, "selected_indices", set()) or set()))),
                float(getattr(note, "start_beats", -1.0)) if note is not None else -1.0,
                float(getattr(note, "length_beats", -1.0)) if note is not None else -1.0,
                int(getattr(note, "pitch", -1)) if note is not None else -1,
            )
        except Exception:
            key = None
        if key != getattr(self, "_last_target_key", None):
            self._last_target_key = key
            try:
                self.update()
            except Exception:
                pass

    # ---------------- public API (called from editor header buttons) ----------------

    def set_tool_mode(self, mode: str) -> None:
        mode = str(mode or self.TOOL_DRAW)
        if mode not in (self.TOOL_DRAW, self.TOOL_SELECT, self.TOOL_ERASE):
            mode = self.TOOL_DRAW
        self._tool_mode = mode
        if mode != self.TOOL_SELECT:
            self._selected_points.clear()
            self._cancel_lasso()
        self.update()

    def tool_mode(self) -> str:
        return str(self._tool_mode)

    # ---------------- helpers ----------------

    def _cancel_lasso(self) -> None:
        self._lasso_active = False
        self._lasso_start = None
        self._lasso_rect = None

    def _scroll_x(self) -> float:
        try:
            return float(self.scroll_area.horizontalScrollBar().value())
        except Exception:
            return 0.0

    def _ppb(self) -> float:
        try:
            return float(getattr(self.canvas, "pixels_per_beat", 90.0) or 90.0)
        except Exception:
            return 90.0

    def _grid_beats(self) -> float:
        """Return current grid size in beats (best-effort)."""
        try:
            g = float(getattr(self.canvas, "base_grid_beats", 0.25) or 0.25)
            return max(1.0 / 128.0, min(16.0, g))
        except Exception:
            return 0.25

    def _target_note(self):
        try:
            idx = int(getattr(self.canvas, "expression_target_index")())
        except Exception:
            idx = -1
        try:
            if idx < 0:
                return -1, None
            notes = self.canvas.project.get_midi_notes(self.canvas.clip_id)
            if 0 <= idx < len(notes):
                return idx, notes[idx]
        except Exception:
            pass
        return -1, None

    def _active_param(self) -> str:
        try:
            eng = getattr(self.canvas, "note_expression_engine", None)
            return str(getattr(eng, "active_param", "velocity") or "velocity")
        except Exception:
            return "velocity"

    def _enabled(self) -> bool:
        try:
            eng = getattr(self.canvas, "note_expression_engine", None)
            return bool(eng is not None and bool(getattr(eng, "enabled", False)))
        except Exception:
            return False

    def _x_to_beat(self, x: float) -> float:
        return (self._scroll_x() + float(x)) / max(1e-6, self._ppb())

    def _note_time_bounds(self, note):
        try:
            start = float(getattr(note, "start_beats", 0.0))
            length = max(1e-6, float(getattr(note, "length_beats", 1.0)))
        except Exception:
            start, length = 0.0, 1.0
        return start, length

    def _note_x_bounds(self, note):
        start, length = self._note_time_bounds(note)
        sx = start * self._ppb() - self._scroll_x()
        ex = (start + length) * self._ppb() - self._scroll_x()
        return sx, ex

    def _v_to_y(self, param: str, v: float) -> float:
        h = float(self.height() - 40)
        top = 28.0
        if param == "micropitch":
            z = max(1.0, min(8.0, float(getattr(self, "_zoom_y", 1.0) or 1.0)))
            vv = max(-12.0, min(12.0, float(v) * z))
            return top + (1.0 - ((vv + 12.0) / 24.0)) * h
        z = max(1.0, min(8.0, float(getattr(self, "_zoom_y", 1.0) or 1.0)))
        vv = float(v)
        vv = 0.5 + (vv - 0.5) * z
        vv = max(0.0, min(1.0, vv))
        return top + (1.0 - vv) * h

    def _y_to_v(self, param: str, y: float) -> float:
        top = 28.0
        h = float(self.height() - 40)
        yy = max(0.0, min(h, float(y) - top))
        if param == "micropitch":
            z = max(1.0, min(8.0, float(getattr(self, "_zoom_y", 1.0) or 1.0)))
            return (((1.0 - (yy / h)) * 24.0) - 12.0) / z
        z = max(1.0, min(8.0, float(getattr(self, "_zoom_y", 1.0) or 1.0)))
        n = 1.0 - (yy / h)
        v = 0.5 + (float(n) - 0.5) / z
        return max(0.0, min(1.0, float(v)))

    def _t_to_x(self, sx: float, ex: float, t: float) -> float:
        tt = max(0.0, min(1.0, float(t)))
        return sx + (ex - sx) * tt

    def _x_to_t(self, note, x: float) -> float:
        start, length = self._note_time_bounds(note)
        beat = self._x_to_beat(float(x))
        t = (float(beat) - float(start)) / float(length)
        return max(0.0, min(1.0, float(t)))

    def _get_points(self, note, param: str):
        try:
            pts = list(getattr(note, "get_expression_points")(param) or [])
        except Exception:
            pts = []
        try:
            pts.sort(key=lambda dd: float(dd.get("t", 0.0)))
        except Exception:
            pass
        return pts

    def _get_curve_types(self, note, param: str, n_points: int):
        try:
            segs = list(note.get_expression_curve_types(param, n_points) or [])
        except Exception:
            # fallback defaults
            default = "smooth" if param == "micropitch" else "linear"
            segs = [default] * max(0, int(n_points) - 1)
        # ensure length
        try:
            need = max(0, int(n_points) - 1)
        except Exception:
            need = 0
        default = "smooth" if param == "micropitch" else "linear"
        if len(segs) < need:
            segs = segs + [default] * (need - len(segs))
        if len(segs) > need:
            segs = segs[:need]
        return segs


    # ---------------- value snapping + segment UI helpers ----------------

    def _value_snap_enabled(self) -> bool:
        """Return True if value snapping is enabled for the Expression Lane."""
        try:
            from pydaw.core.settings_store import get_value
            from pydaw.core.settings import SettingsKeys
            keys = SettingsKeys()
            key = getattr(keys, "ui_pianoroll_expr_value_snap", "ui/pianoroll_expr_value_snap")
            return bool(get_value(key, True))
        except Exception:
            # Safe default: ON (Alt = free)
            return True

    def _value_step(self, param: str) -> float:
        p = str(param or "velocity")
        # Default steps (UI behavior only, data remains float)
        if p == "micropitch":
            return 0.05  # semitones
        return 0.01  # normalized params (0..1)

    def _snap_value(self, param: str, v: float) -> float:
        """Snap value to per-param step (best-effort)."""
        vv = float(v)
        if not self._value_snap_enabled():
            return vv
        step = float(self._value_step(param))
        if step <= 0:
            return vv
        try:
            vv = round(vv / step) * step
        except Exception:
            return float(v)
        # clamp
        if str(param) == "micropitch":
            vv = max(-12.0, min(12.0, float(vv)))
        else:
            vv = max(0.0, min(1.0, float(vv)))
        return float(vv)

    def _hit_seg_badge(self, pos: QPointF) -> int | None:
        """Return segment index if mouse hits a badge."""
        try:
            for r, seg_i, _typ in (self._seg_badges or []):
                if r.contains(pos):
                    return int(seg_i)
        except Exception:
            pass
        return None


    def _badge_label(self, seg_type: str) -> str:
        st = str(seg_type or '').strip().lower()
        return 'Smooth' if st == 'smooth' else 'Linear'

    def _badge_tooltip(self, seg_index: int, seg_type: str, param: str) -> str:
        kind = self._badge_label(seg_type)
        if str(seg_type).strip().lower() == 'smooth':
            interp = 'Bezier (Catmull-Rom → cubic)'
        else:
            interp = 'Straight (linear)'
        return (
            f"Segment {int(seg_index)+1}: {kind} ({interp})\n"
            f"Param: {param}\n"
            "Left-Click Badge: Toggle  |  Right-Click: Context Menu"
        )

    def _draw_segment_badge(self, p: QPainter, rect: QRectF, seg_type: str, hover: bool) -> None:
        # Draw Bitwig-style segment badge (icon + subtle chrome)
        st = str(seg_type or 'linear').strip().lower()
        fill = QColor(52, 56, 62, 235 if hover else 175)
        border = QColor(255, 185, 110, 235 if hover else 125)
        p.setBrush(fill)
        bp = QPen(border)
        bp.setWidth(1)
        p.setPen(bp)
        p.drawRoundedRect(rect, 3.0, 3.0)

        # icon
        icon_pen = QPen(QColor(245, 245, 245, 235 if hover else 205))
        icon_pen.setWidth(2)
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        icon_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(icon_pen)

        r = rect.adjusted(3.0, 3.0, -3.0, -3.0)
        if st == 'smooth':
            # small curve glyph
            path = QPainterPath()
            path.moveTo(r.left(), r.bottom())
            c1 = QPointF(r.left() + r.width() * 0.33, r.bottom())
            c2 = QPointF(r.left() + r.width() * 0.66, r.top())
            path.cubicTo(c1, c2, QPointF(r.right(), r.top()))
            p.drawPath(path)
        else:
            # small straight line glyph
            p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))

    def _maybe_update_tooltip(self, event_pos: QPointF, note, param: str, pts) -> None:
        # Show/hide tooltip for badge hover (best-effort, cheap)
        hit_badge = self._hit_seg_badge(event_pos)
        if hit_badge is None:
            if self._tooltip_key is not None:
                try:
                    QToolTip.hideText()
                except Exception:
                    pass
            self._tooltip_key = None
            self._hover_badge = None
            return

        # resolve type
        seg_types = self._get_curve_types(note, param, len(pts))
        try:
            st = seg_types[int(hit_badge)]
        except Exception:
            st = 'linear'

        key = ('badge', int(hit_badge), str(st))
        self._hover_badge = int(hit_badge)
        if self._tooltip_key == key:
            return
        self._tooltip_key = key
        try:
            QToolTip.showText(self.mapToGlobal(event_pos.toPoint()), self._badge_tooltip(int(hit_badge), str(st), str(param)), self)
        except Exception:
            pass

    def leaveEvent(self, event):  # noqa: ANN001
        try:
            QToolTip.hideText()
        except Exception:
            pass
        self._tooltip_key = None
        self._hover_badge = None
        self._hover_segment = None
        self._hover_point = None
        self.update()
        super().leaveEvent(event)

    def _set_curve_segment_type(self, idx: int, note, param: str, seg_index: int, seg_type: str) -> bool:
        pts = self._get_points(note, param)
        if len(pts) < 2:
            return False
        segs = self._get_curve_types(note, param, len(pts))
        if not (0 <= int(seg_index) < len(segs)):
            return False
        st = str(seg_type).strip().lower()
        if st not in ("linear", "smooth"):
            return False
        segs[int(seg_index)] = st
        return self._set_curve_types(idx, note, param, segs)

    def _show_context_menu(
        self,
        idx: int,
        note,
        param: str,
        pos: QPointF,
        *,
        hit_point: int | None = None,
        hit_segment: int | None = None,
    ) -> None:
        """Context menu for points/segments (safe, lane-only)."""
        menu = QMenu(self)

        act_toggle_seg = act_set_lin = act_set_smooth = act_insert = None
        act_del_point = None
        act_quant = act_thin = act_clear_sel = None
        act_zoom = None

        # Segment menu
        if hit_segment is not None:
            pts = self._get_points(note, param)
            segs = self._get_curve_types(note, param, len(pts))
            cur = None
            try:
                cur = segs[int(hit_segment)]
            except Exception:
                cur = None
            if cur:
                menu.addAction(f"Segment #{int(hit_segment)+1}: {cur.upper()}")
                menu.addSeparator()
            act_toggle_seg = menu.addAction("Toggle Linear/Smooth")
            act_set_lin = menu.addAction("Set Linear")
            act_set_smooth = menu.addAction("Set Smooth")
            menu.addSeparator()
            act_insert = menu.addAction("Insert Point Here")

        # Point menu
        if hit_point is not None:
            if hit_segment is not None:
                menu.addSeparator()
            menu.addAction(f"Point #{int(hit_point)+1}")
            act_del_point = menu.addAction("Delete Point")

        # Generic selection actions
        menu.addSeparator()
        act_quant = menu.addAction("Quantize Selected")
        act_thin = menu.addAction("Thin Selected")
        act_clear_sel = menu.addAction("Clear Selection")

        menu.addSeparator()
        act_zoom = menu.addAction("Open Zoom Window…")

        # Enable/disable
        if not self._selected_points:
            act_quant.setEnabled(False)
            act_thin.setEnabled(False)
            act_clear_sel.setEnabled(False)

        chosen = menu.exec(self.mapToGlobal(pos.toPoint()))
        if chosen is None:
            return

        # Snapshot only after user actually chose an action
        try:
            before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
        except Exception:
            before = None

        changed = False

        if chosen == act_zoom:
            try:
                self._open_zoom_window()
            except Exception:
                pass
            return

        # Segment actions
        if chosen == act_insert:
            # Insert uses snapping by default (Alt not held in menu)
            changed = self._add_or_update_point(idx, note, param, pos, alt_free=False)
        elif chosen == act_toggle_seg and hit_segment is not None:
            changed = self._toggle_curve_segment(idx, note, param, int(hit_segment))
        elif chosen == act_set_lin and hit_segment is not None:
            changed = self._set_curve_segment_type(idx, note, param, int(hit_segment), "linear")
        elif chosen == act_set_smooth and hit_segment is not None:
            changed = self._set_curve_segment_type(idx, note, param, int(hit_segment), "smooth")

        # Point actions
        elif chosen == act_del_point and hit_point is not None:
            # Ensure selection points at this point for delete semantics
            self._selected_points = {int(hit_point)}
            changed = self._delete_selected(idx, note, param)

        # Selection actions
        elif chosen == act_quant:
            changed = self._quantize_selected(idx, note, param)
        elif chosen == act_thin:
            changed = self._thin_selected(idx, note, param)
        elif chosen == act_clear_sel:
            self._selected_points.clear()
            changed = True

        if changed and before is not None:
            try:
                self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Expression Lane Edit ({param})")
            except Exception:
                pass

        self.update()
        try:
            self.canvas.update()
        except Exception:
            pass
    def _set_curve_types(self, idx: int, note, param: str, segs) -> bool:
        try:
            note.set_expression_curve_types(param, segs)
            notes = self.canvas.project.get_midi_notes(self.canvas.clip_id)
            if 0 <= idx < len(notes):
                notes[idx] = note
            self.canvas.project.set_midi_notes(self.canvas.clip_id, notes)
            return True
        except Exception:
            return False

    def _set_points(self, idx: int, note, param: str, pts) -> bool:
        """Set points and keep curve-types aligned."""
        try:
            note.set_expression_points(param, pts)
            # align curve types length
            try:
                segs = self._get_curve_types(note, param, len(note.get_expression_points(param)))
                note.set_expression_curve_types(param, segs)
            except Exception:
                pass
            notes = self.canvas.project.get_midi_notes(self.canvas.clip_id)
            if 0 <= idx < len(notes):
                notes[idx] = note
            self.canvas.project.set_midi_notes(self.canvas.clip_id, notes)
            return True
        except Exception:
            return False

    def _nearest_point_index(self, sx: float, ex: float, param: str, pts, pos: QPointF) -> int | None:
        if not pts:
            return None
        px, py = float(pos.x()), float(pos.y())
        best_i, best_d2 = None, 1e18
        for i, d in enumerate(pts):
            try:
                x = self._t_to_x(sx, ex, float(d.get("t", 0.0)))
                y = self._v_to_y(param, float(d.get("v", 0.0)))
            except Exception:
                continue
            dx, dy = x - px, y - py
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2, best_i = d2, i
        if best_i is not None and best_d2 <= (9.0 * 9.0):
            return int(best_i)
        return None

    def _nearest_segment_index(self, sx: float, ex: float, param: str, pts, pos: QPointF) -> int | None:
        """Return nearest segment index i for segment between pts[i] and pts[i+1]."""
        if not pts or len(pts) < 2:
            return None
        px, py = float(pos.x()), float(pos.y())
        best_i, best_d2 = None, 1e18
        for i in range(len(pts) - 1):
            try:
                x1 = self._t_to_x(sx, ex, float(pts[i].get("t", 0.0)))
                y1 = self._v_to_y(param, float(pts[i].get("v", 0.0)))
                x2 = self._t_to_x(sx, ex, float(pts[i + 1].get("t", 0.0)))
                y2 = self._v_to_y(param, float(pts[i + 1].get("v", 0.0)))
            except Exception:
                continue
            # distance point->segment
            vx, vy = x2 - x1, y2 - y1
            wx, wy = px - x1, py - y1
            denom = (vx * vx + vy * vy) or 1e-9
            t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
            cx, cy = x1 + t * vx, y1 + t * vy
            dx, dy = cx - px, cy - py
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2, best_i = d2, i
        if best_i is not None and best_d2 <= (10.0 * 10.0):
            return int(best_i)
        return None

    # ---------------- painting ----------------

    def paintEvent(self, event):  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # background
        p.fillRect(self.rect(), QColor(22, 24, 28))

        if not self._enabled():
            p.setPen(QPen(QColor(180, 180, 180, 120)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Note Expressions: AUS")
            p.end()
            return

        idx, note = self._target_note()
        if note is None:
            p.setPen(QPen(QColor(180, 180, 180, 140)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Expressions: Note auswählen / hover / focus")
            p.end()
            return

        param = self._active_param()
        pts = self._get_points(note, param)
        seg_types = self._get_curve_types(note, param, len(pts))

        # header label
        p.setPen(QPen(QColor(220, 220, 220, 200)))
        tool_lbl = {self.TOOL_DRAW: "Draw", self.TOOL_SELECT: "Select", self.TOOL_ERASE: "Erase"}.get(self._tool_mode, "Draw")
        vs = "ON" if self._value_snap_enabled() else "OFF"
        p.drawText(8, 16, f"Expression Lane: {param}  (Tool: {tool_lbl})  (Note #{idx})  | V-Snap:{vs} (Alt=free) | Segments: icons (Linear/Smooth) | Q=Quantize  T=Thin")

        # draw note bounds (in lane coordinates)
        sx, ex = self._note_x_bounds(note)
        bounds_pen = QPen(QColor(255, 185, 110, 90))
        bounds_pen.setWidth(1)
        p.setPen(bounds_pen)
        p.drawRect(int(sx), 24, int(ex - sx), self.height() - 34)

        # baseline (0 for micropitch)
        if param == "micropitch":
            midy = self._v_to_y(param, 0.0)
            base_pen = QPen(QColor(255, 255, 255, 45))
            base_pen.setWidth(1)
            p.setPen(base_pen)
            p.drawLine(int(sx), int(midy), int(ex), int(midy))

        # curve
        if len(pts) >= 2:
            xy = []
            for d in pts:
                try:
                    xy.append((self._t_to_x(sx, ex, float(d.get("t", 0.0))), self._v_to_y(param, float(d.get("v", 0.0)))))
                except Exception:
                    continue
            if len(xy) >= 2:
                curve_pen = QPen(QColor(255, 185, 110, 220))
                curve_pen.setWidth(2)
                p.setPen(curve_pen)
                path = QPainterPath()
                path.moveTo(xy[0][0], xy[0][1])

                pts2 = [(float(x), float(y)) for x, y in xy]
                tension = 1.0

                for i in range(len(pts2) - 1):
                    seg = seg_types[i] if i < len(seg_types) else ("smooth" if param == "micropitch" else "linear")
                    p1 = pts2[i]
                    p2 = pts2[i + 1]
                    if seg == "smooth" and param == "micropitch":
                        p0 = pts2[i - 1] if i - 1 >= 0 else pts2[i]
                        p3 = pts2[i + 2] if i + 2 < len(pts2) else pts2[i + 1]
                        c1x = p1[0] + (p2[0] - p0[0]) * (tension / 6.0)
                        c1y = p1[1] + (p2[1] - p0[1]) * (tension / 6.0)
                        c2x = p2[0] - (p3[0] - p1[0]) * (tension / 6.0)
                        c2y = p2[1] - (p3[1] - p1[1]) * (tension / 6.0)
                        path.cubicTo(c1x, c1y, c2x, c2y, p2[0], p2[1])
                    else:
                        path.lineTo(p2[0], p2[1])

                p.drawPath(path)

        # segment badges (curve types affordance)
        # Bitwig-style: icon badges + hover highlight. Tooltip appears on hover.
        self._seg_badges = []
        if len(pts) >= 2:
            try:
                for i in range(len(pts) - 1):
                    x1 = self._t_to_x(sx, ex, float(pts[i].get("t", 0.0)))
                    y1 = self._v_to_y(param, float(pts[i].get("v", 0.0)))
                    x2 = self._t_to_x(sx, ex, float(pts[i + 1].get("t", 0.0)))
                    y2 = self._v_to_y(param, float(pts[i + 1].get("v", 0.0)))
                    midx = (x1 + x2) * 0.5
                    midy = (y1 + y2) * 0.5
                    st = seg_types[i] if i < len(seg_types) else ("smooth" if param == "micropitch" else "linear")

                    rect = QRectF(midx - 9.0, midy - 20.0, 18.0, 14.0)
                    # clamp into visible area and note bounds
                    left = max(float(sx) + 2.0, min(float(rect.left()), float(ex) - float(rect.width()) - 2.0))
                    top = max(26.0, min(float(rect.top()), float(self.height() - 22)))
                    rect.moveTo(left, top)
                    self._seg_badges.append((rect, int(i), str(st)))

                    hover = (self._hover_badge == int(i)) or (self._hover_segment == int(i))
                    self._draw_segment_badge(p, rect, str(st), hover)
            except Exception:
                self._seg_badges = []

        # legend (top-right): explain icons (clearer / Bitwig-style)
        try:
            lx = max(8.0, float(self.width() - 210))
            ly = 4.0
            p.setPen(QPen(QColor(220, 220, 220, 160)))
            p.drawText(int(lx), 16, "Legend:")

            # Linear
            r1 = QRectF(lx + 52.0, ly + 2.0, 18.0, 14.0)
            self._draw_segment_badge(p, r1, "linear", False)
            p.setPen(QPen(QColor(220, 220, 220, 180)))
            p.drawText(int(r1.right() + 6.0), 16, "Linear")

            # Smooth
            r2 = QRectF(lx + 128.0, ly + 2.0, 18.0, 14.0)
            self._draw_segment_badge(p, r2, "smooth", False)
            p.setPen(QPen(QColor(220, 220, 220, 180)))
            p.drawText(int(r2.right() + 6.0), 16, "Smooth")
        except Exception:
            pass

        # points
        dot_pen = QPen(QColor(255, 220, 150, 220))
        dot_pen.setWidth(1)
        sel_pen = QPen(QColor(255, 255, 255, 220))
        sel_pen.setWidth(2)

        for i, d in enumerate(pts):
            try:
                x = self._t_to_x(sx, ex, float(d.get("t", 0.0)))
                y = self._v_to_y(param, float(d.get("v", 0.0)))
            except Exception:
                continue
            is_sel = (self._tool_mode == self.TOOL_SELECT and i in self._selected_points)
            if is_sel:
                p.setPen(sel_pen)
                p.drawEllipse(QPointF(x, y), 4.6, 4.6)
            p.setPen(dot_pen)
            p.drawEllipse(QPointF(x, y), 3.0, 3.0)

        # lasso rect
        if self._lasso_active and self._lasso_rect is not None:
            lpen = QPen(QColor(255, 255, 255, 140))
            lpen.setWidth(1)
            lpen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(lpen)
            p.drawRect(self._lasso_rect)

        # help text
        p.setPen(QPen(QColor(200, 200, 200, 120)))
        p.drawText(
            8,
            self.height() - 8,
            "Select: Lasso drag | SHIFT lock axis | Badge icons toggle | RMB segment menu | RMB point delete (Ctrl+RMB menu) | Q quantize | T thin | ALT=free (no snap)",
        )
        p.end()

    # ---------------- editing primitives ----------------

    def _add_or_update_point(self, idx: int, note, param: str, pos: QPointF, *, alt_free: bool = False) -> bool:
        sx, ex = self._note_x_bounds(note)
        t = self._x_to_t(note, float(pos.x()))
        v = self._y_to_v(param, float(pos.y()))
        if not bool(alt_free):
            v = self._snap_value(param, float(v))

        pts = self._get_points(note, param)

        # replace nearest t if close, else append
        replaced = False
        for d in pts:
            try:
                if abs(float(d.get("t", -999)) - float(t)) <= 0.03:
                    d["t"] = float(t)
                    d["v"] = float(v)
                    replaced = True
                    break
            except Exception:
                continue
        if not replaced:
            pts.append({"t": float(t), "v": float(v)})

        try:
            pts.sort(key=lambda dd: float(dd.get("t", 0.0)))
        except Exception:
            pass

        ok = self._set_points(idx, note, param, pts)
        if ok:
            hit = self._nearest_point_index(sx, ex, param, pts, pos)
            self._selected_points = {hit} if hit is not None else set()
        return ok

    def _erase_near(self, idx: int, note, param: str, pos: QPointF) -> bool:
        sx, ex = self._note_x_bounds(note)
        pts = self._get_points(note, param)
        if not pts:
            return False
        hit = self._nearest_point_index(sx, ex, param, pts, pos)
        if hit is None:
            return False
        try:
            pts.pop(int(hit))
        except Exception:
            return False
        self._selected_points.clear()
        return self._set_points(idx, note, param, pts)

    # ---------------- zoom interactions (readability) ----------------

    def wheelEvent(self, event):  # noqa: ANN001
        """Ctrl+Wheel zooms the lane vertically for readability.

        This is UI-only and safe (no model changes until an edit gesture commits).
        """
        try:
            mods = event.modifiers()
            if bool(mods & Qt.KeyboardModifier.ControlModifier):
                dy = 0.0
                try:
                    dy = float(event.angleDelta().y())
                except Exception:
                    dy = 0.0
                if dy == 0.0:
                    event.ignore()
                    return
                step = 0.15 if dy > 0 else -0.15
                self._zoom_y = max(1.0, min(8.0, float(self._zoom_y) + step))
                try:
                    QToolTip.showText(event.globalPosition().toPoint(), f"Lane Zoom: x{self._zoom_y:.2f}")
                except Exception:
                    pass
                self.update()
                event.accept()
                return
        except Exception:
            pass
        super().wheelEvent(event)

    def _open_zoom_window(self) -> None:
        """Open a larger, dockless zoom window for precise editing.

        This is purely UI. It shares the same canvas + horizontal scroll, so it
        stays in sync and edits apply to the same underlying note expressions.
        """
        # Re-use existing dialog if open.
        try:
            if self._zoom_dialog is not None and self._zoom_dialog.isVisible():
                self._zoom_dialog.raise_()
                self._zoom_dialog.activateWindow()
                return
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle("Expression Lane – Zoom")
        dlg.setModal(False)
        dlg.resize(820, 320)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)

        zoom_lane = NoteExpressionLane(self.canvas, self.scroll_area, parent=dlg)
        try:
            zoom_lane.set_tool_mode(self.tool_mode())
        except Exception:
            pass
        zoom_lane._zoom_y = max(2.5, float(getattr(self, "_zoom_y", 1.0) or 1.0))
        zoom_lane.setMinimumHeight(240)
        lay.addWidget(zoom_lane)

        def _on_close():
            try:
                self._zoom_dialog = None
            except Exception:
                pass

        try:
            dlg.finished.connect(lambda _=0: _on_close())
        except Exception:
            pass

        self._zoom_dialog = dlg
        dlg.show()

    def _delete_selected(self, idx: int, note, param: str) -> bool:
        pts = self._get_points(note, param)
        if not pts or not self._selected_points:
            return False
        keep = []
        for i, d in enumerate(pts):
            if i not in self._selected_points:
                keep.append(d)
        self._selected_points.clear()
        return self._set_points(idx, note, param, keep)

    def _move_points_to(self, idx: int, note, param: str, drag: _LaneDrag, pos: QPointF, shift: bool, alt_free: bool) -> bool:
        pts = self._get_points(note, param)
        if not pts or not drag.point_indices or not drag.start_points or drag.start_pos is None:
            return False

        # compute deltas in normalized space
        dx = float(pos.x()) - float(drag.start_pos.x())
        dy = float(pos.y()) - float(drag.start_pos.y())

        # convert dx to dt in note-local time
        start, length = self._note_time_bounds(note)
        dt_beats = dx / max(1e-6, self._ppb())
        dt = dt_beats / max(1e-6, float(length))

        # dy -> dv
        # Use y->v mapping delta: compute start v from y at start_pos
        dv = 0.0
        try:
            v0 = self._y_to_v(param, float(drag.start_pos.y()))
            v1 = self._y_to_v(param, float(pos.y()))
            dv = float(v1) - float(v0)
        except Exception:
            dv = 0.0

        # axis lock detection when shift held
        if shift:
            if drag.axis_lock is None:
                if abs(dx) > 6 or abs(dy) > 6:
                    drag.axis_lock = "x" if abs(dx) >= abs(dy) else "y"
            if drag.axis_lock == "x":
                dv = 0.0
            elif drag.axis_lock == "y":
                dt = 0.0
        else:
            drag.axis_lock = None

        # apply
        idxs = list(drag.point_indices)
        new_pts = pts[:]  # will edit by indices (note: indices refer to original order at press)
        for j, pi in enumerate(idxs):
            if not (0 <= int(pi) < len(new_pts)):
                continue
            t0, v0 = drag.start_points[j]
            new_t = max(0.0, min(1.0, float(t0) + float(dt)))
            new_v = float(v0) + float(dv)
            if param != "micropitch":
                new_v = max(0.0, min(1.0, float(new_v)))
            else:
                new_v = max(-12.0, min(12.0, float(new_v)))
            if not bool(alt_free):
                new_v = self._snap_value(param, float(new_v))
            new_pts[int(pi)]["t"] = float(new_t)
            new_pts[int(pi)]["v"] = float(new_v)

        # sort
        try:
            new_pts.sort(key=lambda dd: float(dd.get("t", 0.0)))
        except Exception:
            pass

        ok = self._set_points(idx, note, param, new_pts)
        if ok:
            # update selection by nearest in new positions (approx)
            self._selected_points = set()
            sx, ex = self._note_x_bounds(note)
            for j, (t0, v0) in enumerate(drag.start_points):
                # estimate new point position and re-hit
                nx = self._t_to_x(sx, ex, t0 + dt)
                ny = self._v_to_y(param, v0 + dv)
                hit = self._nearest_point_index(sx, ex, param, new_pts, QPointF(nx, ny))
                if hit is not None:
                    self._selected_points.add(int(hit))
        return ok

    def _toggle_curve_segment(self, idx: int, note, param: str, seg_index: int) -> bool:
        pts = self._get_points(note, param)
        if len(pts) < 2:
            return False
        segs = self._get_curve_types(note, param, len(pts))
        if not (0 <= int(seg_index) < len(segs)):
            return False
        segs[int(seg_index)] = "smooth" if segs[int(seg_index)] == "linear" else "linear"
        return self._set_curve_types(idx, note, param, segs)

    def _quantize_selected(self, idx: int, note, param: str) -> bool:
        pts = self._get_points(note, param)
        if not pts or not self._selected_points:
            return False
        start, length = self._note_time_bounds(note)
        grid = self._grid_beats()
        changed = False
        for i in list(self._selected_points):
            if not (0 <= int(i) < len(pts)):
                continue
            beat = float(start) + float(pts[int(i)].get("t", 0.0)) * float(length)
            qbeat = round(beat / grid) * grid
            t2 = (qbeat - float(start)) / max(1e-6, float(length))
            t2 = max(0.0, min(1.0, float(t2)))
            if abs(t2 - float(pts[int(i)].get("t", 0.0))) > 1e-9:
                pts[int(i)]["t"] = float(t2)
                changed = True
        if not changed:
            return False
        try:
            pts.sort(key=lambda dd: float(dd.get("t", 0.0)))
        except Exception:
            pass
        return self._set_points(idx, note, param, pts)

    def _thin_selected(self, idx: int, note, param: str) -> bool:
        pts = self._get_points(note, param)
        if not pts or not self._selected_points or len(pts) < 3:
            return False
        # Thin by removing selected points that are too close in time to neighbors
        start, length = self._note_time_bounds(note)
        grid = self._grid_beats()
        min_dt_norm = (grid * 0.5) / max(1e-6, float(length))
        min_dt_norm = max(1e-4, float(min_dt_norm))
        keep = []
        changed = False
        for i, d in enumerate(pts):
            if i in self._selected_points:
                # keep endpoints always
                if i == 0 or i == len(pts) - 1:
                    keep.append(d)
                    continue
                t = float(d.get("t", 0.0))
                t_prev = float(pts[i - 1].get("t", 0.0))
                t_next = float(pts[i + 1].get("t", 0.0))
                if (t - t_prev) < min_dt_norm or (t_next - t) < min_dt_norm:
                    changed = True
                    continue
            keep.append(d)
        if not changed:
            return False
        self._selected_points.clear()
        return self._set_points(idx, note, param, keep)

    # ---------------- Qt events ----------------

    def keyPressEvent(self, event):  # noqa: ANN001
        if not self._enabled():
            super().keyPressEvent(event)
            return

        idx, note = self._target_note()
        if note is None:
            super().keyPressEvent(event)
            return
        param = self._active_param()

        key = event.key()

        # Delete selected points
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._tool_mode == self.TOOL_SELECT and self._selected_points:
                try:
                    before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
                except Exception:
                    before = None
                ok = self._delete_selected(idx, note, param)
                if ok and before is not None:
                    try:
                        self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Delete Expression Points ({param})")
                    except Exception:
                        pass
                self.update()
                try:
                    self.canvas.update()
                except Exception:
                    pass
                event.accept()
                return

        # Quantize
        if key == Qt.Key.Key_Q and self._tool_mode == self.TOOL_SELECT:
            try:
                before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
            except Exception:
                before = None
            ok = self._quantize_selected(idx, note, param)
            if ok and before is not None:
                try:
                    self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Quantize Expression ({param})")
                except Exception:
                    pass
            self.update()
            try:
                self.canvas.update()
            except Exception:
                pass
            event.accept()
            return

        # Thin
        if key == Qt.Key.Key_T and self._tool_mode == self.TOOL_SELECT:
            try:
                before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
            except Exception:
                before = None
            ok = self._thin_selected(idx, note, param)
            if ok and before is not None:
                try:
                    self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Thin Expression ({param})")
                except Exception:
                    pass
            self.update()
            try:
                self.canvas.update()
            except Exception:
                pass
            event.accept()
            return

        # Toggle curve type
        if key == Qt.Key.Key_C:
            try:
                before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
            except Exception:
                before = None
            # prefer segment after selected point; else nearest to mouse (best-effort)
            seg_i = None
            if self._selected_points:
                seg_i = min(self._selected_points)
                if seg_i >= len(self._get_points(note, param)) - 1:
                    seg_i = len(self._get_points(note, param)) - 2
            ok = False
            if seg_i is not None and seg_i >= 0:
                ok = self._toggle_curve_segment(idx, note, param, int(seg_i))
            if ok and before is not None:
                try:
                    self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Toggle Curve Type ({param})")
                except Exception:
                    pass
            self.update()
            try:
                self.canvas.update()
            except Exception:
                pass
            event.accept()
            return

        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        if not self._enabled() or event.button() != Qt.MouseButton.LeftButton:
            return
        idx, note = self._target_note()
        if note is None:
            return
        param = self._active_param()
        try:
            before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
        except Exception:
            before = None

        changed = False
        if self._tool_mode == self.TOOL_SELECT:
            # double-click delete nearest
            changed = self._erase_near(idx, note, param, event.position())
        else:
            changed = self._add_or_update_point(idx, note, param, event.position(), alt_free=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))

        if changed and before is not None:
            try:
                self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Edit Expression ({param})")
            except Exception:
                pass
        self.update()
        try:
            self.canvas.update()
        except Exception:
            pass
        event.accept()

    def mousePressEvent(self, event):  # noqa: ANN001
        if not self._enabled() or not getattr(self.canvas, "clip_id", ""):
            return
        idx, note = self._target_note()
        if note is None:
            return

        param = self._active_param()
        sx, ex = self._note_x_bounds(note)
        pts = self._get_points(note, param)

        # Right click:
        # - Point: quick delete (legacy). Ctrl+RMB opens context menu.
        # - Segment/badge/empty: context menu (curve types, insert point, quantize/thin, etc.)
        if event.button() == Qt.MouseButton.RightButton:
            hit_pt = self._nearest_point_index(sx, ex, param, pts, event.position())
            hit_badge = self._hit_seg_badge(event.position())
            seg = hit_badge if hit_badge is not None else self._nearest_segment_index(sx, ex, param, pts, event.position())

            # Quick delete on point (keeps old behavior)
            if hit_pt is not None and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                try:
                    before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
                except Exception:
                    before = None

                changed = self._erase_near(idx, note, param, event.position())
                if changed and before is not None:
                    try:
                        self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Delete Expression Point ({param})")
                    except Exception:
                        pass
                self._selected_points.clear()
            else:
                # Context menu for segment/point/empty
                self._show_context_menu(int(idx), note, param, event.position(), hit_point=hit_pt, hit_segment=seg)

            self.update()
            try:
                self.canvas.update()
            except Exception:
                pass
            event.accept()
            return

        # Left click on segment badge toggles curve type (fast, no menu)
        if event.button() == Qt.MouseButton.LeftButton:
            seg_badge = self._hit_seg_badge(event.position())
            if seg_badge is not None:
                try:
                    before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
                except Exception:
                    before = None
                changed = self._toggle_curve_segment(int(idx), note, param, int(seg_badge))
                if changed and before is not None:
                    try:
                        self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, before, f"Toggle Curve Type ({param})")
                    except Exception:
                        pass
                self.update()
                try:
                    self.canvas.update()
                except Exception:
                    pass
                event.accept()
                return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        try:
            before = self.canvas.project.snapshot_midi_notes(self.canvas.clip_id)
        except Exception:
            before = None

        self._drag = _LaneDrag(before_snapshot=before, idx=int(idx), param=param, tool=self._tool_mode, start_pos=event.position())

        # Tool actions
        if self._tool_mode == self.TOOL_SELECT:
            hit = self._nearest_point_index(sx, ex, param, pts, event.position())

            # lasso if click on empty space (no hit)
            if hit is None:
                self._lasso_active = True
                self._lasso_start = event.position()
                self._lasso_rect = QRectF(self._lasso_start, self._lasso_start)
                # shift adds to selection, otherwise reset (common)
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._selected_points.clear()
                self.update()
                event.accept()
                return

            # point hit: single select unless shift-add
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._selected_points = {int(hit)}
            else:
                if int(hit) in self._selected_points:
                    self._selected_points.remove(int(hit))
                else:
                    self._selected_points.add(int(hit))

            # prepare drag of selected points
            drag_indices = sorted(self._selected_points)
            self._drag.point_indices = drag_indices
            self._drag.start_points = [(float(pts[i].get("t", 0.0)), float(pts[i].get("v", 0.0))) for i in drag_indices]
            self.update()
            event.accept()
            return

        if self._tool_mode == self.TOOL_ERASE:
            self._erase_near(idx, note, param, event.position())
            self.update()
            try:
                self.canvas.update()
            except Exception:
                pass
            event.accept()
            return

        # Draw tool
        self._add_or_update_point(idx, note, param, event.position(), alt_free=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
        self.update()
        try:
            self.canvas.update()
        except Exception:
            pass
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: ANN001
        # Track mouse for hover affordances (badges) even when not dragging
        try:
            self._last_mouse_pos = event.position()
        except Exception:
            pass

        if self._drag is None:
            # Hover detection (best-effort, lane-only)
            try:
                idx, note = self._target_note()
            except Exception:
                idx, note = -1, None
            if note is None:
                return
            try:
                param = self._active_param()
                sx, ex = self._note_x_bounds(note)
                pts = self._get_points(note, param)
                self._hover_point = self._nearest_point_index(sx, ex, param, pts, event.position())

                # badge hover + tooltip (icons)
                self._maybe_update_tooltip(event.position(), note, param, pts)

                seg = self._hover_badge
                if seg is None:
                    seg = self._nearest_segment_index(sx, ex, param, pts, event.position())
                self._hover_segment = seg
            except Exception:
                self._hover_point = None
                self._hover_segment = None
            self.update()
            return

        idx, note = self._target_note()
        if note is None:
            return
        param = self._drag.param

        if self._tool_mode == self.TOOL_SELECT and self._lasso_active and self._lasso_start is not None:
            # update lasso
            self._lasso_rect = QRectF(self._lasso_start, event.position()).normalized()
            self.update()
            event.accept()
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        changed = False
        if self._drag.tool == self.TOOL_SELECT:
            if not self._drag.point_indices:
                return
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            changed = self._move_points_to(idx, note, param, self._drag, event.position(), shift=shift, alt_free=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
        elif self._drag.tool == self.TOOL_ERASE:
            changed = self._erase_near(idx, note, param, event.position())
        else:
            changed = self._add_or_update_point(idx, note, param, event.position(), alt_free=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))

        if changed:
            try:
                self.canvas.update()
            except Exception:
                pass
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        if self._drag is None:
            return

        idx, note = self._target_note()
        param = self._drag.param

        # finalize lasso selection (no commit)
        if self._tool_mode == self.TOOL_SELECT and self._lasso_active and self._lasso_rect is not None and note is not None:
            sx, ex = self._note_x_bounds(note)
            pts = self._get_points(note, param)
            for i, d in enumerate(pts):
                try:
                    x = self._t_to_x(sx, ex, float(d.get("t", 0.0)))
                    y = self._v_to_y(param, float(d.get("v", 0.0)))
                except Exception:
                    continue
                if self._lasso_rect.contains(QPointF(x, y)):
                    self._selected_points.add(int(i))
            self._cancel_lasso()
            self._drag = None
            self.update()
            event.accept()
            return

        # commit gesture if it made changes (best-effort; commit is cheap)
        try:
            d = self._drag
            if d.before_snapshot is not None:
                self.canvas.project.commit_midi_notes_edit(self.canvas.clip_id, d.before_snapshot, f"Edit Expression ({d.param})")
        except Exception:
            pass

        self._drag = None
        self._cancel_lasso()
        event.accept()
