"""Staff renderer (minimal, DAW-integrated).

Implements Task 2 from PROJECT_DOCS/progress/TODO.md.

Design goals:
- No external notation font dependency required (uses unicode glyphs ♯ ♭ ♮).
- Pure QPainter drawing helpers, usable from QWidget.paintEvent or QGraphicsItem.
- Conservative defaults so it works on typical Linux setups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QFont, QColor
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True)
class StaffStyle:
    """Visual constants for staff rendering."""

    line_distance: int = 10
    lines: int = 5
    staff_pen_width: int = 1
    note_head_w: int = 12
    note_head_h: int = 8
    stem_len: int = 30
    accidental_font_pt: int = 14


class StaffRenderer:
    """Reusable drawing primitives for staff-based notation."""

    @staticmethod
    def staff_height(style: StaffStyle) -> int:
        return (style.lines - 1) * style.line_distance

    @staticmethod
    def line_y(y_offset: int, line_index: int, style: StaffStyle) -> int:
        """Y position of staff line.

        line_index: 0..(lines-1), where 0 is top line.
        """

        return int(y_offset + line_index * style.line_distance)

    
    @staticmethod
    def staff_y_from_halfsteps(staff_line: int, style: StaffStyle) -> float:
        """Return y-offset (relative to y_offset) for a diatonic staff position.

        In this project, staff positions increment by 1 per line/space step.
        """
        return (4 - int(staff_line)) * (float(style.line_distance) / 2.0)


    @staticmethod
    def render_staff(painter: QPainter, width: int, y_offset: int, style: StaffStyle = StaffStyle()):
        """Draw a 5-line staff."""

        pen = QPen(Qt.GlobalColor.black)
        pen.setWidth(style.staff_pen_width)
        painter.setPen(pen)

        for i in range(style.lines):
            y = StaffRenderer.line_y(y_offset, i, style)
            painter.drawLine(0, y, width, y)

    @staticmethod
    def render_note_head(
        painter: QPainter,
        x: float,
        line: int,
        y_offset: int,
        style: StaffStyle = StaffStyle(),
        filled: bool = True,
        fill_color: QColor | None = None,
        outline_color: QColor | None = None,
    ):
        """Draw a note head.

        Args:
            x: center x
            line: diatonic staff position (0 bottom line, 4 top line, allows ledger: -n..+n)
            y_offset: y offset of top staff line (same as render_staff)
        """

        # Convert "line" (bottom=0) to y in pixels.
        # Staff lines are spaced by line_distance; steps between lines are half that.
        top_line_y = StaffRenderer.line_y(y_offset, 0, style)
        bottom_line_y = StaffRenderer.line_y(y_offset, style.lines - 1, style)
        half_step = style.line_distance / 2.0
        # bottom line is line=0 -> y = bottom_line_y
        y = bottom_line_y - (line * half_step)

        rect = QRectF(
            float(x - style.note_head_w / 2),
            float(y - style.note_head_h / 2),
            float(style.note_head_w),
            float(style.note_head_h),
        )
        if outline_color is None:
            outline_color = QColor(Qt.GlobalColor.black)
        painter.setPen(QPen(outline_color))

        if not filled:
            painter.setBrush(QBrush(Qt.GlobalColor.white))
        else:
            painter.setBrush(QBrush(fill_color if fill_color is not None else QColor(Qt.GlobalColor.black)))
        painter.drawEllipse(rect)

        # Ledger lines for out-of-staff notes (simple, minimal)
        # Staff covers lines 0..(lines-1)*2 inclusive in half-steps -> in our "line" units,
        # in-staff note centers range roughly 0..8 (for 5 lines). We'll add ledgers when needed.
        min_line = -2
        max_line = (style.lines - 1) * 2 + 2
        # Convert line (in half-steps) to absolute half-step index from bottom line.
        half_idx = int(round(line))
        if half_idx < 0:
            for idx in range(0, half_idx - 1, -2):
                ly = bottom_line_y - (idx * half_step)
                painter.drawLine(int(x - style.note_head_w), int(ly), int(x + style.note_head_w), int(ly))
        elif half_idx > (style.lines - 1) * 2:
            for idx in range((style.lines - 1) * 2, half_idx + 1, 2):
                ly = bottom_line_y - (idx * half_step)
                painter.drawLine(int(x - style.note_head_w), int(ly), int(x + style.note_head_w), int(ly))

    @staticmethod
    def render_stem(
        painter: QPainter,
        x: float,
        line: int,
        y_offset: int,
        up: bool,
        style: StaffStyle = StaffStyle(),
    ):
        """Draw a stem for a note head."""

        top_line_y = StaffRenderer.line_y(y_offset, 0, style)
        bottom_line_y = StaffRenderer.line_y(y_offset, style.lines - 1, style)
        half_step = style.line_distance / 2.0
        y = bottom_line_y - (line * half_step)

        pen = QPen(Qt.GlobalColor.black)
        pen.setWidth(1)
        painter.setPen(pen)

        if up:
            x0 = x + style.note_head_w / 2.0
            painter.drawLine(int(x0), int(y), int(x0), int(y - style.stem_len))
        else:
            x0 = x - style.note_head_w / 2.0
            painter.drawLine(int(x0), int(y), int(x0), int(y + style.stem_len))

    @staticmethod
    def render_accidental(
        painter: QPainter,
        x: float,
        line: int,
        y_offset: int,
        accidental: int,
        style: StaffStyle = StaffStyle(),
    ):
        """Draw ♯/♭/♮.

        accidental: -1 flat, 0 none, +1 sharp, 2 natural
        """

        if accidental == 0:
            return

        glyph = "♯" if accidental > 0 else "♭"
        if accidental == 2:
            glyph = "♮"

        top_line_y = StaffRenderer.line_y(y_offset, 0, style)
        bottom_line_y = StaffRenderer.line_y(y_offset, style.lines - 1, style)
        half_step = style.line_distance / 2.0
        y = bottom_line_y - (line * half_step)

        font = QFont()
        font.setPointSize(style.accidental_font_pt)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.black))

        painter.drawText(QPointF(x - style.note_head_w * 1.6, y + style.note_head_h / 2.0), glyph)

    # ── Clef rendering (v0.0.20.447) ─────────────────────────────

    @staticmethod
    def render_clef(
        painter: QPainter,
        x: float,
        y_offset: int,
        clef_type: str = "treble",
        style: StaffStyle = StaffStyle(),
    ) -> QRectF:
        """Draw a clef symbol at the beginning of the staff.

        Returns the bounding rect of the clef (for click detection).
        """
        try:
            from pydaw.ui.notation.clef_dialog import get_clef

            info = get_clef(clef_type)
            bottom_line_y = StaffRenderer.line_y(y_offset, style.lines - 1, style)
            half_step = float(style.line_distance) / 2.0

            # Position: ref_line (0=bottom, 4=top)
            ref_y = bottom_line_y - (info.ref_line * 2 * half_step)

            # Draw the main clef symbol
            font = QFont("Serif", 26)
            painter.setFont(font)
            painter.setPen(QPen(QColor(30, 30, 50)))

            base_sym = str(info.symbol).rstrip("⁸₈↑↓")
            painter.drawText(QPointF(float(x), float(ref_y + 10)), base_sym)

            # Octave indicator (8va / 8vb)
            if info.octave_shift != 0:
                small_font = QFont("Sans", 7)
                painter.setFont(small_font)
                painter.setPen(QPen(QColor(80, 80, 180)))
                label = "8va" if info.octave_shift > 0 else "8vb"
                oy = ref_y - 18 if info.octave_shift > 0 else ref_y + 20
                painter.drawText(QPointF(float(x), float(oy)), label)

            # Return bounding rect for click detection
            return QRectF(float(x) - 4, float(y_offset) - 8,
                          28.0, float(StaffRenderer.staff_height(style)) + 16)
        except Exception:
            return QRectF()

    @staticmethod
    def render_time_signature(
        painter: QPainter,
        x: float,
        y_offset: int,
        numerator: int = 4,
        denominator: int = 4,
        style: StaffStyle = StaffStyle(),
    ):
        """Draw a time signature (e.g. 4/4) on the staff."""
        try:
            font = QFont("Serif", 16)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor(30, 30, 50)))

            staff_h = StaffRenderer.staff_height(style)
            mid_y = y_offset + staff_h // 2

            # Numerator above center, denominator below
            painter.drawText(QPointF(float(x), float(mid_y - 2)), str(numerator))
            painter.drawText(QPointF(float(x), float(mid_y + style.line_distance + 6)), str(denominator))
        except Exception:
            pass


class StaffRendererTestWidget(QWidget):
    """Simple widget used as rendering test target for Task 2."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("PyDAW – StaffRenderer Test")
        self.resize(900, 260)
        self._style = StaffStyle()

        # Some demo notes: (x, line, accidental, stem_up)
        self._notes = [
            (120, 0, 0, True),   # bottom line
            (180, 2, 1, True),   # sharp
            (240, 4, -1, False), # flat
            (300, 6, 2, False),  # natural
            (360, 8, 0, False),
            (430, 10, 1, False),
            (520, -2, -1, True),
        ]

    def paintEvent(self, _evt):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        y_offset = 80
        StaffRenderer.render_staff(painter, self.width(), y_offset, self._style)

        for x, line, acc, up in self._notes:
            StaffRenderer.render_accidental(painter, float(x), int(line), y_offset, int(acc), self._style)
            StaffRenderer.render_note_head(painter, float(x), int(line), y_offset, self._style, filled=True)
            StaffRenderer.render_stem(painter, float(x), int(line), y_offset, bool(up), self._style)

        painter.end()


def _run_demo():
    app = QApplication.instance() or QApplication([])
    w = StaffRendererTestWidget()
    w.show()
    app.exec()


if __name__ == "__main__":
    _run_demo()
