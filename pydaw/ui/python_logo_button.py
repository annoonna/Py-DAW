from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QBrush
from PySide6.QtWidgets import QToolButton


class PythonLogoButton(QToolButton):
    """Round, asset-free Python logo button rendered via QPainter paths.

    Notes
    -----
    - No image assets are loaded.
    - The logo is drawn using vector paths, so it stays crisp at any scaling.
    - Colors are controlled via `color_top` / `color_bottom`.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Dynamic, code-controlled colors (see add-on request)
        self.color_top = QColor("#3776AB")     # Python blue
        self.color_bottom = QColor("#FFD43B")  # Python yellow

        self._default_top = QColor(self.color_top)
        self._default_bottom = QColor(self.color_bottom)

        # Lightweight internal state for hover/pressed rendering
        self._pressed = False
        self.setToolTip("Python")

        # Keep button round (handled by QSS + paint clipping), but make it
        # naturally square.
        self.setMinimumSize(22, 22)

    # -------- public API

    def reset_default_colors(self) -> None:
        self.color_top = QColor(self._default_top)
        self.color_bottom = QColor(self._default_bottom)
        self.update()

    def set_colors(self, top_hex: str, bottom_hex: str) -> None:
        self.color_top = QColor(top_hex)
        self.color_bottom = QColor(bottom_hex)
        self.update()

    def set_orange(self) -> None:
        # Requested orange overlay mode: set both snakes to orange.
        self.set_colors("#FF6000", "#FF6000")

    def sizeHint(self) -> QSize:
        return QSize(30, 30)

    # -------- mouse state (hover is handled in paint via underMouse())

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        return super().mouseReleaseEvent(event)

    # -------- rendering

    def paintEvent(self, event):
        """Custom paint.

        IMPORTANT:
        - PyQt6 treats unhandled Python exceptions inside paintEvent as fatal.
          So we must never let exceptions escape (otherwise Qt aborts with SIGABRT).
        - We avoid implicit type coercions (QColor -> QBrush) to stay compatible
          across PyQt6/Qt versions.
        """

        p = QPainter()
        try:
            p.begin(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            # NOTE: QPainterPath.addEllipse expects QRectF in PyQt6.
            # self.rect() returns QRect, so convert explicitly when building paths.
            r = self.rect().adjusted(1, 1, -1, -1)
            if r.width() <= 0 or r.height() <= 0:
                return

            # Clip to perfect circle.
            clip = QPainterPath()
            clip.addEllipse(r.toRectF())
            p.setClipPath(clip)

            # Background: transparent by default, subtle hover/pressed overlay.
            if self._pressed:
                p.fillPath(clip, QBrush(QColor(255, 255, 255, 26)))
            elif self.underMouse():
                p.fillPath(clip, QBrush(QColor(255, 255, 255, 16)))

            # Draw the Python logo in normalized 100x100 space.
            side = min(r.width(), r.height())
            p.save()
            # Center square
            ox = r.x() + (r.width() - side) / 2.0
            oy = r.y() + (r.height() - side) / 2.0
            p.translate(ox, oy)
            p.scale(side / 100.0, side / 100.0)

            # Bottom snake first, then top snake to mimic interlock.
            bottom_path, bottom_eye = self._snake_paths(top=False)
            top_path, top_eye = self._snake_paths(top=True)

            p.fillPath(bottom_path, QBrush(self.color_bottom))
            p.fillPath(top_path, QBrush(self.color_top))

            # White eyes
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#FFFFFF")))
            p.drawEllipse(bottom_eye)
            p.drawEllipse(top_eye)

            p.restore()
        except Exception:
            # Never crash the whole app from paintEvent.
            import traceback

            traceback.print_exc()
            try:
                super().paintEvent(event)
            except Exception:
                # If even the base paint fails, swallow to avoid SIGABRT.
                pass
        finally:
            if p.isActive():
                p.end()

    @staticmethod
    def _snake_paths(top: bool) -> tuple[QPainterPath, "QRectF"]:
        """Return (path, eye_rect) for one snake.

        We approximate the official logo with two rounded, stepped shapes.
        This is a crisp vector rendition and scales cleanly.
        """
        from PySide6.QtCore import QRectF

        # Geometry in 100x100 space.
        rad = 10.0

        if top:
            # Top snake sits upper-left and reaches to the mid-right.
            outer = QRectF(10, 12, 62, 40)
            notch = QRectF(52, 32, 20, 20)
            inner = QRectF(22, 22, 34, 20)
            eye = QRectF(29, 19, 6, 6)
        else:
            # Bottom snake sits lower-right and reaches to the mid-left.
            outer = QRectF(28, 48, 62, 40)
            notch = QRectF(28, 48, 20, 20)
            inner = QRectF(44, 58, 34, 20)
            eye = QRectF(67, 75, 6, 6)

        path = QPainterPath()
        path.addRoundedRect(outer, rad, rad)

        # Step/notch (carves the interlock)
        cut = QPainterPath()
        cut.addRoundedRect(notch, rad * 0.8, rad * 0.8)
        path = path.subtracted(cut)

        # Inner hole for the classic "snake body" look
        hole = QPainterPath()
        hole.addRoundedRect(inner, rad * 0.7, rad * 0.7)
        path = path.subtracted(hole)

        return path, eye
