"""Note Expression Engine (foundation + UI interaction helpers).

This module is the *modular* entry point for Bitwig/Cubase-style per-note
expressions.

Design goals:
- **Zero regressions**: existing Piano Roll edit tools (move/resize/knife/etc.)
  must stay untouched.
- **Opt-in editing**: expressions can be enabled/disabled; when disabled we
  still render a subtle hover triangle to advertise capability.
- **JSON-safe model**: expressions live on MidiNote as a dict/list structure.

The current PianoRollCanvas is QWidget/QPainter-based (not QGraphicsScene).
So the engine offers a painter-based draw hook:

    engine.draw_expressions(painter, note_rects, hovered_idx=..., focus_idx=...)

Where note_rects is an iterable of (idx, QRectF, MidiNote).

v0.0.20.197:
- Triangle hit-testing helper for interactions.
- Smooth curve rendering (Catmull-Rom -> cubic Bezier) for Micropitch (and
  generally nicer curves).
- Hover/focus aware drawing (triangle appears on hover, focus note can show a
  midline for Micropitch).

UI concepts implemented elsewhere:
- Overlay param selector (Velocity/Chance/Timbre/Pressure/Gain/Pan/Micropitch)
- Expression Triangle: click menu, Alt+Drag morph
- Expression lanes under the piano roll
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple, Optional, List

from PyQt6.QtCore import QObject, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from pydaw.model.midi import MidiNote


@dataclass(frozen=True)
class ExpressionParamSpec:
    key: str
    label: str


DEFAULT_PARAMS: tuple[ExpressionParamSpec, ...] = (
    ExpressionParamSpec("velocity", "Velocity"),
    ExpressionParamSpec("chance", "Chance"),
    ExpressionParamSpec("timbre", "Timbre"),
    ExpressionParamSpec("pressure", "Pressure"),
    ExpressionParamSpec("gain", "Gain"),
    ExpressionParamSpec("pan", "Pan"),
    ExpressionParamSpec("micropitch", "Micropitch"),
)


class NoteExpressionEngine(QObject):
    """Render hook + state holder for per-note expressions."""

    changed = pyqtSignal()

    # Visual mapping choices (UI-only):
    # For Micropitch we display +/- 2 semitones by default (Bitwig-like). The
    # underlying data can still be larger; we clamp for drawing.
    MICROPITCH_VIS_SEMITONES: float = 2.0

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.enabled: bool = False
        self.active_param: str = "velocity"

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == bool(self.enabled):
            return
        self.enabled = enabled
        self.changed.emit()

    def set_active_param(self, key: str) -> None:
        key = str(key or "velocity")
        if key == str(self.active_param):
            return
        self.active_param = key
        self.changed.emit()

    # ---------------- triangle helpers ----------------

    @staticmethod
    def triangle_rect(r: QRectF) -> QRectF:
        """Return the clickable rectangle for the dropdown triangle.

        Bitwig/Cubase-style affordance: a tiny ▾ button in the note's top-right
        corner, visually consistent with the Arranger clip dropdown.
        """
        # Keep a stable hit target even on short notes.
        size = float(max(11.0, min(13.0, float(r.height()) * 0.70)))
        # Shift left a bit so it doesn't collide with resize handles.
        x = float(r.right()) - (size + 3.0)
        y = float(r.top()) + 2.0
        return QRectF(x, y, size, size)

    def hit_triangle(self, x: float, y: float, r: QRectF) -> bool:
        """Return True if a point hits the triangle's clickable area."""
        try:
            return bool(self.triangle_rect(r).contains(float(x), float(y)))
        except Exception:
            return False

    def _draw_triangle(self, p: QPainter, r: QRectF, *, alpha: int) -> None:
        try:
            rr = self.triangle_rect(r)
            a = int(max(0, min(255, alpha)))
            # Background pill (matches arranger ▾ button feel)
            p.save()
            p.setOpacity(1.0)
            p.setPen(QPen(QColor(0, 0, 0, max(40, int(a * 0.35)))))
            p.setBrush(QColor(55, 55, 55, max(60, int(a * 0.55))))
            try:
                p.drawRoundedRect(rr, 2.8, 2.8)
            except Exception:
                p.drawRect(rr)
            # Down arrow
            p.setPen(QPen(QColor(255, 230, 200, a)))
            p.drawText(rr, 0x84, "▾")  # Qt.AlignCenter = 0x84
            p.restore()
        except Exception:
            pass

    # ---------------- curve rendering ----------------

    @staticmethod
    def _catmull_rom_path(points: List[QPointF]) -> QPainterPath:
        """Smooth Catmull-Rom spline converted to cubic Beziers.

        Works well for DAW-like curves while staying cheap.
        """
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        if len(points) == 1:
            return path
        if len(points) == 2:
            path.lineTo(points[1])
            return path

        # Standard Catmull-Rom -> Bezier conversion.
        for i in range(len(points) - 1):
            p0 = points[i - 1] if i - 1 >= 0 else points[i]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]

            c1 = QPointF(
                p1.x() + (p2.x() - p0.x()) / 6.0,
                p1.y() + (p2.y() - p0.y()) / 6.0,
            )
            c2 = QPointF(
                p2.x() - (p3.x() - p1.x()) / 6.0,
                p2.y() - (p3.y() - p1.y()) / 6.0,
            )
            path.cubicTo(c1, c2, p2)
        return path

    def draw_expressions(
        self,
        p: QPainter,
        note_rects: Iterable[Tuple[int, QRectF, MidiNote]],
        *,
        hovered_idx: int | None = None,
        focus_idx: int | None = None,
    ) -> None:
        """Draw expression overlays.

        When disabled, we only draw a subtle triangle for the hovered note.
        When enabled, we draw:
        - triangle hint (hovered note brighter)
        - optional midline for Micropitch
        - expression curve if there are points
        """

        # Subtle overlay color (kept minimal; UI polish later)
        pen = QPen(QColor(255, 185, 110, 210))
        pen.setWidth(1)

        # Midline pen for micropitch
        mid_pen = QPen(QColor(255, 255, 255, 55))
        mid_pen.setWidth(1)

        # Normalize hover/focus
        h_idx = int(hovered_idx) if hovered_idx is not None else -1
        f_idx = int(focus_idx) if focus_idx is not None else -1

        for idx, r, n in note_rects:
            try:
                if not isinstance(n, MidiNote):
                    continue

                has_any = bool(getattr(n, "expressions", None))
                pts = []
                if self.enabled:
                    pts = n.get_expression_points(self.active_param) or []

                # --- Triangle visibility
                if idx == h_idx:
                    self._draw_triangle(p, r, alpha=220)
                elif has_any and self.enabled:
                    self._draw_triangle(p, r, alpha=120)
                elif (not self.enabled) and idx == h_idx:
                    self._draw_triangle(p, r, alpha=140)

                # When disabled we do not draw curves.
                if not self.enabled:
                    continue

                # --- Micropitch midline hint (important for precision)
                if str(self.active_param) == "micropitch":
                    if idx == h_idx or idx == f_idx or bool(pts):
                        try:
                            p.setPen(mid_pen)
                            y = float(r.center().y())
                            p.drawLine(int(r.left()) + 1, int(y), int(r.right()) - 1, int(y))
                        except Exception:
                            pass

                if not pts:
                    continue

                # --- Build points in note-local coordinates
                mid_y = float(r.center().y())
                amp = float(r.height()) * 0.40

                qpts: List[QPointF] = []
                for d in pts:
                    try:
                        t = float(d.get("t", 0.0))
                        v = float(d.get("v", 0.0))
                    except Exception:
                        continue
                    t = max(0.0, min(1.0, t))

                    # Map value to -1..+1
                    if str(self.active_param) == "micropitch":
                        vis = float(self.MICROPITCH_VIS_SEMITONES)
                        vv = max(-vis, min(vis, v)) / max(1e-6, vis)
                    else:
                        vv = (max(0.0, min(1.0, v)) * 2.0) - 1.0

                    x = float(r.left()) + float(r.width()) * t
                    y = mid_y - (vv * amp)
                    qpts.append(QPointF(x, y))

                if len(qpts) < 2:
                    continue

                # --- Smooth curve (Bitwig-like) for micropitch and generally nicer curves
                try:
                    path = self._catmull_rom_path(qpts) if len(qpts) >= 3 else QPainterPath(qpts[0])
                    if len(qpts) == 2:
                        path.lineTo(qpts[1])
                except Exception:
                    path = QPainterPath(qpts[0])
                    for qp in qpts[1:]:
                        path.lineTo(qp)

                p.setPen(pen)
                p.drawPath(path)
            except Exception:
                continue
