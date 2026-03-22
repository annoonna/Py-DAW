"""Qt logo button (painted, no external assets).

User request (v31 feature):
- Round QToolButton placed bottom-left next to the editor/view tabs.
- Paint the classic Qt logo via code:
  - Filled green circle (#41CD52)
  - White bold sans-serif 'Q'
  - Small white 't' inside the belly of the 'Q'
- Use antialiasing.

Safety/Performance:
- UI-only paintEvent (no timers).
- No interaction with audio/transport engines.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRegion
from PySide6.QtWidgets import QToolButton


class QtLogoButton(QToolButton):
    """A lightweight, self-painted Qt logo button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("qtLogoButton")
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Qt")

        # We want a perfectly round button, so keep it square.
        self.setMinimumSize(22, 22)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Hard clip to a circle so it's truly round (not just border-radius).
        try:
            self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        except Exception:
            # Mask can fail on some platforms/styles; painting will still be round.
            pass

    def paintEvent(self, event):
        # Fully custom paint. We intentionally do not call the base class.
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            w = self.width()
            h = self.height()
            d = max(1, min(w, h))

            # Slight inset to avoid edge clipping.
            inset = max(1, int(d * 0.06))
            r = QRectF(inset, inset, d - 2 * inset, d - 2 * inset)

            # Circle
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#41CD52"))
            p.drawEllipse(r)

            # White 'Q'
            font_q = QFont()
            font_q.setBold(True)
            # Keep font size proportional to circle.
            font_q.setPointSizeF(max(7.0, r.height() * 0.62))
            p.setFont(font_q)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Q")

            # Small 't' inside the belly (slightly right/down from center)
            font_t = QFont()
            font_t.setBold(True)
            font_t.setPointSizeF(max(5.0, r.height() * 0.26))
            p.setFont(font_t)

            cx = r.center().x()
            cy = r.center().y()
            ox = r.width() * 0.12
            oy = r.height() * 0.12
            tr = QRectF(cx + ox - r.width() * 0.18, cy + oy - r.height() * 0.18, r.width() * 0.36, r.height() * 0.36)
            p.drawText(tr, Qt.AlignmentFlag.AlignCenter, "t")
        finally:
            p.end()
