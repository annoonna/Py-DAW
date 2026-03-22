"""Ruler zoom handle (magnifier icon) used in multiple editors.

Goal
----
Provide a discoverable Ableton/Bitwig-style zoom handle directly inside rulers.

Design constraints
------------------
- No external image assets (painted with QPainter).
- Owner widgets keep full control of zoom logic (pixels-per-beat, view-range, ...).
- The handle is optional and purely UI (no engine/thread touch).

Usage
-----
- Call :func:`paint_magnifier` from the widget's paintEvent.
- Keep a QRect (hitbox) and intercept mouse press/move/release over the rect.

This module intentionally stays tiny and dependency-free.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QCursor, QPixmap


def paint_magnifier(p: QPainter, rect: QRect, *, color: QColor) -> None:
    """Paint a small magnifier icon inside *rect*.

    Args:
        p: active QPainter
        rect: target rectangle
        color: stroke color (typically palette().text().color())
    """
    try:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color)
        pen.setWidthF(1.4)
        pen.setCapStyle(pen.CapStyle.RoundCap)
        pen.setJoinStyle(pen.JoinStyle.RoundJoin)
        p.setPen(pen)

        # Circle
        d = min(rect.width(), rect.height())
        # Slight padding so it looks crisp
        pad = max(1, int(d * 0.18))
        cx = rect.x() + rect.width() // 2
        cy = rect.y() + rect.height() // 2
        r = (d - 2 * pad) // 2
        # Circle slightly up-left to make room for handle
        circle_x = cx - r - 1
        circle_y = cy - r - 1
        p.drawEllipse(circle_x, circle_y, 2 * r, 2 * r)

        # Handle (down-right)
        hx1 = circle_x + int(2 * r * 0.70)
        hy1 = circle_y + int(2 * r * 0.70)
        hx2 = rect.right() - pad
        hy2 = rect.bottom() - pad
        p.drawLine(hx1, hy1, hx2, hy2)

        # Small "plus" in the glass (subtle)
        plus_len = max(3, int(r * 0.55))
        px = circle_x + r
        py = circle_y + r
        p.drawLine(px - plus_len // 2, py, px + plus_len // 2, py)
        p.drawLine(px, py - plus_len // 2, px, py + plus_len // 2)

    except Exception:
        # Never crash the UI because of an icon
        pass
    finally:
        try:
            p.restore()
        except Exception:
            pass


def make_magnifier_cursor(color: QColor | None = None) -> QCursor:
    """Create a magnifier QCursor (no external assets).

    The cursor is used for hover/drag feedback on ruler zoom handles.
    """
    try:
        size = 32
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        col = color or QColor(240, 240, 240)
        paint_magnifier(p, QRect(6, 6, 20, 20), color=col)
        p.end()

        # Hotspot roughly in the glass center
        return QCursor(pm, 14, 14)
    except Exception:
        return QCursor(Qt.CursorShape.ArrowCursor)
