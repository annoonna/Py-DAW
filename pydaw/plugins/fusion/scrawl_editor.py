"""Scrawl Editor — PyQt6 waveform drawing canvas with pen tool.

v0.0.20.576: Interactive waveform editor for the Scrawl oscillator.

Features:
  - Click to add points
  - Drag to draw freehand (pen tool)
  - Right-click to delete points
  - Preset shape buttons (Sine, Saw, Square, Tri, Random)
  - Smooth toggle (cubic vs linear interpolation)
  - Real-time waveform preview
"""
from __future__ import annotations
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel,
    QSizePolicy,
)


class ScrawlCanvas(QWidget):
    """Waveform drawing canvas — the core pen-tool area."""

    waveform_changed = pyqtSignal()  # Emitted when points change

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # v0.0.20.583: avoid hover-driven repaint storms.
        # The canvas no longer repaints continuously on plain mouse hover;
        # redraws happen while actively drawing or on explicit state changes.
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._points: list[tuple[float, float]] = []  # (x: 0..1, y: -1..+1)
        self._table: list[float] = []  # Display table (y values)
        self._drawing = False
        self._freehand_samples: list[float] = []
        self._hover_x = -1.0
        self._max_freehand_samples = 1024
        self._smooth = True

        # Colors
        self._bg = QColor("#1a1a2e")
        self._grid = QColor("#2a2a3e")
        self._wave = QColor("#ff9800")
        self._wave_fill = QColor(255, 152, 0, 40)
        self._point_color = QColor("#fff176")
        self._point_hover = QColor("#ff5252")
        self._zero_line = QColor("#444466")

    def set_points(self, points: list[tuple[float, float]]) -> None:
        self._points = sorted(points, key=lambda p: p[0])
        self.update()

    def get_points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def set_display_table(self, table: list[float]) -> None:
        """Set the rendered waveform for display (from ScrawlOscillator)."""
        self._table = list(table)
        self.update()

    def set_smooth(self, smooth: bool) -> None:
        self._smooth = smooth
        self.update()

    # ── Coordinate conversion ──

    def _to_canvas(self, x: float, y: float) -> QPointF:
        """Convert (0..1, -1..+1) to canvas pixel coords."""
        w, h = self.width(), self.height()
        px = x * w
        py = (1.0 - (y + 1.0) / 2.0) * h  # y=-1 → bottom, y=+1 → top
        return QPointF(px, py)

    def _from_canvas(self, px: float, py: float) -> tuple[float, float]:
        """Convert canvas pixels to (0..1, -1..+1)."""
        w, h = self.width(), self.height()
        x = max(0.0, min(1.0, px / max(1, w)))
        y = max(-1.0, min(1.0, 1.0 - 2.0 * py / max(1, h)))
        return (x, y)

    # ── Mouse Events ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._freehand_samples = []
            x, y = self._from_canvas(event.position().x(), event.position().y())
            self._hover_x = x
            self._freehand_samples.append(y)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # Delete nearest point
            x, _ = self._from_canvas(event.position().x(), event.position().y())
            self._delete_point_near(x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # v0.0.20.583: no continuous repaint on plain hover. Fusion only needs
        # live redraw while actually drawing. This keeps mouse movement from
        # flooding the Qt event loop and starving the heavier Fusion UI/DSP.
        if not self._drawing:
            return

        self._hover_x = event.position().x() / max(1, self.width())
        _, y = self._from_canvas(event.position().x(), event.position().y())

        if not self._freehand_samples or abs(y - self._freehand_samples[-1]) >= 0.002:
            if len(self._freehand_samples) < self._max_freehand_samples:
                self._freehand_samples.append(y)
            else:
                self._freehand_samples[-1] = y
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False
            if len(self._freehand_samples) < 3:
                # Single click: add a point
                x, y = self._from_canvas(event.position().x(), event.position().y())
                self._points.append((x, y))
                self._points.sort(key=lambda p: p[0])
            else:
                # Freehand draw: replace entire waveform
                self._points_from_freehand()
            self._hover_x = event.position().x() / max(1, self.width())
            self._freehand_samples = []
            self.update()
            self.waveform_changed.emit()

    def _delete_point_near(self, x: float) -> None:
        if len(self._points) <= 2:
            return
        best_idx = -1
        best_dist = 0.03
        for i, (px, _) in enumerate(self._points):
            if i == 0 or i == len(self._points) - 1:
                continue  # Don't delete anchors
            d = abs(px - x)
            if d < best_dist:
                best_idx = i
                best_dist = d
        if best_idx >= 0:
            self._points.pop(best_idx)
            self.update()
            self.waveform_changed.emit()

    def _points_from_freehand(self) -> None:
        """Convert freehand samples to control points."""
        samples = self._freehand_samples
        if len(samples) < 2:
            return
        n_target = min(64, max(8, len(samples) // 4))
        step = max(1, len(samples) // n_target)
        pts = []
        for i in range(0, len(samples), step):
            x = i / max(1, len(samples) - 1)
            y = max(-1.0, min(1.0, samples[i]))
            pts.append((x, y))
        if pts:
            pts[-1] = (1.0, pts[0][1])  # Loop closure
        self._points = pts

    # ── Painting ──

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, self._bg)

        # Grid
        p.setPen(QPen(self._grid, 1))
        for gx in [0.25, 0.5, 0.75]:
            p.drawLine(int(gx * w), 0, int(gx * w), h)
        for gy in [0.25, 0.5, 0.75]:
            p.drawLine(0, int(gy * h), w, int(gy * h))

        # Zero line
        p.setPen(QPen(self._zero_line, 1, Qt.PenStyle.DashLine))
        p.drawLine(0, h // 2, w, h // 2)

        # Waveform from table
        if self._table and len(self._table) > 1:
            path = QPainterPath()
            n = len(self._table)
            first = True
            for i in range(n):
                x_px = (i / (n - 1)) * w
                y_px = (1.0 - (self._table[i] + 1.0) / 2.0) * h
                if first:
                    path.moveTo(x_px, y_px)
                    first = False
                else:
                    path.lineTo(x_px, y_px)

            # Fill under curve
            fill_path = QPainterPath(path)
            fill_path.lineTo(w, h // 2)
            fill_path.lineTo(0, h // 2)
            fill_path.closeSubpath()
            p.fillPath(fill_path, self._wave_fill)

            # Draw wave line
            p.setPen(QPen(self._wave, 2))
            p.drawPath(path)

        # During freehand drawing: show live preview
        if self._drawing and len(self._freehand_samples) > 1:
            p.setPen(QPen(QColor("#ff5252"), 2))
            n = len(self._freehand_samples)
            for i in range(1, n):
                x0 = ((i - 1) / (n - 1)) * w
                y0 = (1.0 - (self._freehand_samples[i - 1] + 1.0) / 2.0) * h
                x1 = (i / (n - 1)) * w
                y1 = (1.0 - (self._freehand_samples[i] + 1.0) / 2.0) * h
                p.drawLine(int(x0), int(y0), int(x1), int(y1))

        # Control points
        p.setPen(QPen(self._point_color, 1))
        for px, py in self._points:
            cp = self._to_canvas(px, py)
            # Hover highlight
            if abs(px - self._hover_x) < 0.02:
                p.setBrush(self._point_hover)
                p.drawEllipse(cp, 5, 5)
            else:
                p.setBrush(self._point_color)
                p.drawEllipse(cp, 3, 3)

        p.end()


class ScrawlEditorWidget(QWidget):
    """Complete Scrawl editor panel: canvas + shape buttons + smooth toggle."""

    waveform_changed = pyqtSignal(list)  # Emits list of (x, y) points

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Canvas
        self.canvas = ScrawlCanvas()
        self.canvas.setFixedHeight(110)
        self.canvas.waveform_changed.connect(self._on_canvas_changed)
        layout.addWidget(self.canvas)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(3)
        toolbar.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("✏️")
        lbl.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(lbl)

        for name, slot in [
            ("Sine", self._shape_sine), ("Saw", self._shape_saw),
            ("Sqr", self._shape_square), ("Tri", self._shape_tri),
            ("Rnd", self._shape_random),
        ]:
            btn = QPushButton(name)
            btn.setFixedSize(36, 18)
            btn.setStyleSheet(
                "QPushButton { font-size: 8px; padding: 1px; border: 1px solid #555; "
                "border-radius: 2px; color: #ccc; }"
                "QPushButton:hover { background: #ff9800; color: #000; }"
            )
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        self._chk_smooth = QCheckBox("Smooth")
        self._chk_smooth.setChecked(True)
        self._chk_smooth.setStyleSheet("font-size: 8px; color: #aaa;")
        self._chk_smooth.toggled.connect(self._on_smooth_toggled)
        toolbar.addWidget(self._chk_smooth)

        toolbar.addStretch(1)

        hint = QLabel("Zeichne mit Maus | Rechtsklick = Punkt löschen")
        hint.setStyleSheet("font-size: 7px; color: #666;")
        toolbar.addWidget(hint)

        layout.addLayout(toolbar)

    def set_points(self, points: list[tuple[float, float]]) -> None:
        self.canvas.set_points(points)

    def set_display_table(self, table) -> None:
        if hasattr(table, 'tolist'):
            table = table.tolist()
        self.canvas.set_display_table(list(table))

    def _on_canvas_changed(self) -> None:
        pts = self.canvas.get_points()
        self.waveform_changed.emit(pts)

    def _on_smooth_toggled(self, checked: bool) -> None:
        self.canvas.set_smooth(checked)
        pts = self.canvas.get_points()
        self.waveform_changed.emit(pts)

    def _shape_sine(self) -> None:
        import math
        pts = [(i / 31, math.sin(2.0 * math.pi * i / 31)) for i in range(32)]
        self.canvas.set_points(pts)
        self.waveform_changed.emit(pts)

    def _shape_saw(self) -> None:
        pts = [(0.0, -1.0), (0.99, 1.0), (1.0, -1.0)]
        self.canvas.set_points(pts)
        self.waveform_changed.emit(pts)

    def _shape_square(self) -> None:
        pts = [(0.0, 1.0), (0.49, 1.0), (0.5, -1.0), (0.99, -1.0), (1.0, 1.0)]
        self.canvas.set_points(pts)
        self.waveform_changed.emit(pts)

    def _shape_tri(self) -> None:
        pts = [(0.0, 0.0), (0.25, 1.0), (0.5, 0.0), (0.75, -1.0), (1.0, 0.0)]
        self.canvas.set_points(pts)
        self.waveform_changed.emit(pts)

    def _shape_random(self) -> None:
        import random
        pts = [(0.0, 0.0)]
        for i in range(1, 15):
            pts.append((i / 15, random.uniform(-1.0, 1.0)))
        pts.append((1.0, pts[0][1]))
        self.canvas.set_points(pts)
        self.waveform_changed.emit(pts)

    def is_smooth(self) -> bool:
        return self._chk_smooth.isChecked()
