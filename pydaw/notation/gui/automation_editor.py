# ChronoScaleStudio – Automation Editor (Volume)
# Zeichnen per Maus: Links gedrückt halten und Linie ziehen.

from __future__ import annotations

from pydaw.notation.qt_compat import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget
from pydaw.notation.qt_compat import QPainter, QPen
from pydaw.notation.qt_compat import Qt, QPointF

from pydaw.notation.music.automation import AutomationLane


class AutomationCanvas(QWidget):
    def __init__(self, lane: AutomationLane, length_beats: int = 16, quant_step: float = 0.25):
        super().__init__()
        self.lane = lane
        self.length_beats = int(length_beats)
        self.quant_step = float(quant_step)

        # points: beat -> value
        self._points = {}  # float->float
        self.load_from_lane()

        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_length_beats(self, beats: int):
        self.length_beats = max(4, int(beats))
        self.update()

    def load_from_lane(self):
        self._points.clear()
        for p in self.lane.get_points():
            self._points[float(p.beat)] = float(p.value)

    def clear_points(self):
        self._points.clear()
        self.update()

    def _beat_from_x(self, x: float) -> float:
        w = max(1, self.width())
        beat = (x / w) * self.length_beats
        step = max(0.03125, self.quant_step)
        beat = round(beat / step) * step
        return max(0.0, min(float(self.length_beats), beat))

    def _value_from_y(self, y: float) -> float:
        h = max(1, self.height())
        v = 1.0 - (y / h)
        return max(0.0, min(1.0, float(v)))

    def _x_from_beat(self, beat: float) -> float:
        w = max(1, self.width())
        return (float(beat) / self.length_beats) * w

    def _y_from_value(self, value: float) -> float:
        h = max(1, self.height())
        return (1.0 - float(value)) * h

    def mousePressEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            beat = self._beat_from_x(event.position().x())
            val = self._value_from_y(event.position().y())
            self._points[beat] = val
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            beat = self._beat_from_x(event.position().x())
            val = self._value_from_y(event.position().y())
            self._points[beat] = val
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Grid
        grid_pen = QPen(Qt.lightGray)
        grid_pen.setStyle(Qt.DashLine)
        p.setPen(grid_pen)

        # Vertical beats
        for b in range(self.length_beats + 1):
            x = (b / self.length_beats) * w
            p.drawLine(int(x), 0, int(x), h)

        # Horizontal levels (0..1 in 0.25)
        for i in range(5):
            y = int((i / 4) * h)
            p.drawLine(0, y, w, y)

        # Curve
        pts = sorted(self._points.items(), key=lambda kv: kv[0])
        if not pts:
            return

        curve_pen = QPen(Qt.darkGray)
        curve_pen.setWidth(2)
        p.setPen(curve_pen)

        last = None
        for beat, val in pts:
            x = self._x_from_beat(beat)
            y = self._y_from_value(val)
            if last is not None:
                p.drawLine(int(last.x()), int(last.y()), int(x), int(y))
            last = QPointF(x, y)

        # Points
        point_pen = QPen(Qt.black)
        p.setPen(point_pen)
        for beat, val in pts:
            x = self._x_from_beat(beat)
            y = self._y_from_value(val)
            p.drawEllipse(int(x) - 3, int(y) - 3, 6, 6)

    def export_points(self):
        pts = sorted(self._points.items(), key=lambda kv: kv[0])
        return [(float(b), float(v)) for b, v in pts]


class AutomationEditor(QDialog):
    def __init__(self, lane: AutomationLane, length_beats: int = 16, quant_step: float = 0.25, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Automationen – Volume")

        layout = QVBoxLayout(self)

        self.canvas = AutomationCanvas(lane=lane, length_beats=length_beats, quant_step=quant_step)
        layout.addWidget(QLabel("Links gedrückt halten und die Lautstärke-Kurve zeichnen (oben = laut, unten = leise)."))
        layout.addWidget(self.canvas)

        row = QHBoxLayout()
        row.addWidget(QLabel("Länge (Beats):"))
        self.len_spin = QSpinBox()
        self.len_spin.setRange(4, 128)
        self.len_spin.setValue(int(length_beats))
        self.len_spin.valueChanged.connect(lambda v: self.canvas.set_length_beats(v))
        row.addWidget(self.len_spin)
        row.addStretch(1)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        self.btn_clear = QPushButton("Clear")
        self.btn_apply = QPushButton("Apply")
        self.btn_close = QPushButton("Close")
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(self.btn_apply)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self.btn_clear.clicked.connect(self.canvas.clear_points)
        self.btn_apply.clicked.connect(self.apply)
        self.btn_close.clicked.connect(self.close)

    def apply(self):
        points = self.canvas.export_points()
        self.canvas.lane.set_points(points)
        self.accept()
