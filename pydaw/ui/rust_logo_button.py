"""Rust logo button (painted, no external assets).

Safety goals:
- Independent widget; does NOT inherit from QtLogoButton.
- Pure UI paint-only element, no audio or transport coupling.
- Uses the DAW piano-roll accent colors (cyan + amber) as a soft glow.

Design intent:
- Round badge similar in footprint to the existing Qt badge.
- Stylized "R" + small "s" so the badge reads as a Rust-focused mark
  without importing any external logo asset.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRegion, QLinearGradient
from PyQt6.QtWidgets import QToolButton


class RustLogoButton(QToolButton):
    """A lightweight, self-painted Rust-inspired badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rustLogoButton")
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Rust Core")
        self.setMinimumSize(22, 22)

        # Piano-roll accent colors requested by the user.
        self._cyan = QColor(105, 185, 255)
        self._amber = QColor(255, 175, 95)
        self._body = QColor("#16181F")
        self._rim = QColor("#242A35")
        self._text = QColor("#F8FAFF")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        except Exception:
            pass

    def paintEvent(self, event):  # noqa: ARG002 - Qt signature
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            d = max(1, min(self.width(), self.height()))
            inset = max(1.0, d * 0.08)
            outer = QRectF(inset, inset, d - 2.0 * inset, d - 2.0 * inset)

            # Soft dual glow in the same family as the piano-roll note colors.
            cyan_glow = QColor(self._cyan)
            cyan_glow.setAlpha(72)
            amber_glow = QColor(self._amber)
            amber_glow.setAlpha(68)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cyan_glow)
            p.drawEllipse(outer.adjusted(-d * 0.10, -d * 0.10, d * 0.02, d * 0.02))
            p.setBrush(amber_glow)
            p.drawEllipse(outer.adjusted(-d * 0.02, -d * 0.02, d * 0.10, d * 0.10))

            # Main dark body with a diagonal accent gradient.
            grad = QLinearGradient(outer.topLeft(), outer.bottomRight())
            grad.setColorAt(0.0, QColor(26, 34, 48))
            grad.setColorAt(0.35, self._body)
            grad.setColorAt(0.68, QColor(34, 28, 25))
            grad.setColorAt(1.0, QColor(48, 34, 25))
            p.setBrush(grad)
            p.drawEllipse(outer)

            # Rim stroke with subtle cyan/amber presence.
            rim_pen = QPen(self._rim)
            rim_pen.setWidthF(max(1.0, d * 0.06))
            p.setPen(rim_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(outer.adjusted(0.5, 0.5, -0.5, -0.5))

            accent_pen = QPen(QColor(self._cyan.red(), self._cyan.green(), self._cyan.blue(), 110))
            accent_pen.setWidthF(max(1.0, d * 0.03))
            accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(accent_pen)
            p.drawArc(outer.adjusted(d * 0.10, d * 0.10, -d * 0.10, -d * 0.10), 120 * 16, 105 * 16)
            accent_pen.setColor(QColor(self._amber.red(), self._amber.green(), self._amber.blue(), 120))
            p.setPen(accent_pen)
            p.drawArc(outer.adjusted(d * 0.10, d * 0.10, -d * 0.10, -d * 0.10), -40 * 16, 105 * 16)

            # Main letter R.
            text_rect = outer.adjusted(d * 0.05, d * 0.00, -d * 0.02, -d * 0.05)
            font_r = QFont()
            font_r.setBold(True)
            font_r.setPointSizeF(max(7.0, outer.height() * 0.44))
            p.setFont(font_r)
            p.setPen(QPen(self._text))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "R")

            # Small 's' in the lower-right belly, mirroring the Qt badge idea.
            font_s = QFont()
            font_s.setBold(True)
            font_s.setPointSizeF(max(4.5, outer.height() * 0.18))
            p.setFont(font_s)
            s_rect = QRectF(
                outer.center().x() + outer.width() * 0.05,
                outer.center().y() + outer.height() * 0.02,
                outer.width() * 0.24,
                outer.height() * 0.22,
            )
            p.drawText(s_rect, Qt.AlignmentFlag.AlignCenter, "s")
        finally:
            p.end()
