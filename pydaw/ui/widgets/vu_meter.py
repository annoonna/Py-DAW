"""VU Meter Widget — Professional Audio Level Metering (v0.0.20.40).

Ableton/Pro-DAW-quality metering with:
- dB-calibrated logarithmic scale (-60dB to +6dB)
- Segmented LED-style bars (48 segments)
- 4-zone color scheme: green / yellow / orange / red + clip
- Peak hold markers with 2s hold + 15 dB/s decay
- Clip indicator (stays lit until clicked)
- Stereo L/R channels
- 30 FPS update rate (33ms)
- Smooth ballistics: instant attack, ~1.7s peak fall, ~300ms RMS
- dB tick marks along the meter
"""

from __future__ import annotations

import math
import time

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QLinearGradient, QFont, QFontMetrics,
)


# ── dB conversion helpers ──────────────────────────────────────────────

_DB_MIN = -60.0   # bottom of meter
_DB_MAX = 6.0     # top of meter (headroom)
_DB_RANGE = _DB_MAX - _DB_MIN  # 66 dB

# Number of LED segments
_NUM_SEGMENTS = 48

# dB thresholds for color zones (Pro-DAW-Style)
_DB_GREEN_END = -18.0
_DB_YELLOW_END = -6.0
_DB_ORANGE_END = -3.0
_DB_RED_END = 0.0
# Above 0 dB → clip zone

# Peak hold timing
_PEAK_HOLD_SEC = 2.0      # seconds to hold peak marker
_PEAK_FALL_DBPS = 15.0    # dB per second fall rate after hold expires

# Level fall rate (meter bar)
_METER_FALL_DBPS = 26.0   # dB per second — snappy like Pro-DAW

# dB tick marks to draw
_DB_TICKS = [0, -3, -6, -12, -18, -24, -36, -48, -60]


def _linear_to_db(linear: float) -> float:
    """Convert linear amplitude (0.0+) to dB. Below threshold → _DB_MIN."""
    if linear <= 1e-10:
        return _DB_MIN
    db = 20.0 * math.log10(linear)
    return max(_DB_MIN, min(_DB_MAX, db))


def _db_to_fraction(db: float) -> float:
    """Map dB value to 0.0–1.0 fraction on the meter scale."""
    return max(0.0, min(1.0, (db - _DB_MIN) / _DB_RANGE))


def _segment_color(seg_db: float) -> QColor:
    """Return the color for a segment at a given dB level."""
    if seg_db > _DB_RED_END:
        return QColor(255, 20, 20)       # Clip / Red-hot
    elif seg_db > _DB_ORANGE_END:
        return QColor(255, 50, 30)        # Red zone
    elif seg_db > _DB_YELLOW_END:
        return QColor(255, 160, 0)        # Orange
    elif seg_db > _DB_GREEN_END:
        return QColor(220, 220, 0)        # Yellow
    else:
        return QColor(0, 200, 60)         # Green


def _segment_color_dim(seg_db: float) -> QColor:
    """Dim (unlit) segment color — subtle background indication."""
    if seg_db > _DB_RED_END:
        return QColor(60, 10, 10)
    elif seg_db > _DB_ORANGE_END:
        return QColor(55, 15, 10)
    elif seg_db > _DB_YELLOW_END:
        return QColor(50, 30, 5)
    elif seg_db > _DB_GREEN_END:
        return QColor(40, 40, 8)
    else:
        return QColor(8, 35, 15)


# Pre-compute segment dB positions and colors (hot path optimization)
_SEGMENT_DB = [
    _DB_MIN + (_DB_RANGE * i / _NUM_SEGMENTS)
    for i in range(_NUM_SEGMENTS)
]
_SEGMENT_FRAC = [float(i) / _NUM_SEGMENTS for i in range(_NUM_SEGMENTS)]
_SEGMENT_COLOR_LIT = [_segment_color(db) for db in _SEGMENT_DB]
_SEGMENT_COLOR_DIM = [_segment_color_dim(db) for db in _SEGMENT_DB]


class VUMeterWidget(QWidget):
    """Professional VU Meter Widget — Ableton/Pro-DAW quality.

    Accepts linear levels (0.0–1.0+) via set_levels().
    Internally converts to dB and renders with proper ballistics.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        # Size
        self.setFixedWidth(40)
        self.setMinimumHeight(100)

        # Current dB levels (after ballistics)
        self._db_l = _DB_MIN
        self._db_r = _DB_MIN

        # Peak hold
        self._peak_db_l = _DB_MIN
        self._peak_db_r = _DB_MIN
        self._peak_time_l = 0.0
        self._peak_time_r = 0.0

        # Clip indicators (sticky until clicked)
        self._clip_l = False
        self._clip_r = False

        # Timing
        self._last_update = time.monotonic()

        # Style
        self._bg_color = QColor(16, 16, 18)
        self._tick_font = QFont("monospace", 7)
        self._tick_font.setStyleHint(QFont.StyleHint.Monospace)

    def set_levels(self, l: float, r: float) -> None:
        """Update meter levels (linear amplitude, 0.0 to 1.0+).

        Called from the GUI timer at ~30 FPS.
        Applies professional ballistics internally.
        """
        now = time.monotonic()
        dt = min(0.1, max(0.001, now - self._last_update))
        self._last_update = now

        # Convert to dB
        new_db_l = _linear_to_db(max(0.0, float(l)))
        new_db_r = _linear_to_db(max(0.0, float(r)))

        # Clip detection
        if l > 1.0:
            self._clip_l = True
        if r > 1.0:
            self._clip_r = True

        # ── Meter bar ballistics ──
        # Attack: instant (follow new peak immediately)
        # Release: fall at _METER_FALL_DBPS
        fall = _METER_FALL_DBPS * dt

        if new_db_l >= self._db_l:
            self._db_l = new_db_l
        else:
            self._db_l = max(new_db_l, self._db_l - fall)

        if new_db_r >= self._db_r:
            self._db_r = new_db_r
        else:
            self._db_r = max(new_db_r, self._db_r - fall)

        # ── Peak hold ballistics ──
        if new_db_l >= self._peak_db_l:
            self._peak_db_l = new_db_l
            self._peak_time_l = now
        elif (now - self._peak_time_l) > _PEAK_HOLD_SEC:
            self._peak_db_l = max(_DB_MIN,
                                  self._peak_db_l - _PEAK_FALL_DBPS * dt)

        if new_db_r >= self._peak_db_r:
            self._peak_db_r = new_db_r
            self._peak_time_r = now
        elif (now - self._peak_time_r) > _PEAK_HOLD_SEC:
            self._peak_db_r = max(_DB_MIN,
                                  self._peak_db_r - _PEAK_FALL_DBPS * dt)

        self.update()

    def reset(self) -> None:
        """Reset all levels, peaks, and clip indicators."""
        self._db_l = _DB_MIN
        self._db_r = _DB_MIN
        self._peak_db_l = _DB_MIN
        self._peak_db_r = _DB_MIN
        self._peak_time_l = 0.0
        self._peak_time_r = 0.0
        self._clip_l = False
        self._clip_r = False
        self.update()

    def mousePressEvent(self, event) -> None:
        """Click to clear clip indicators and reset peaks."""
        self._clip_l = False
        self._clip_r = False
        self._peak_db_l = self._db_l
        self._peak_db_r = self._db_r
        self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        """Draw the segmented LED-style VU meter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, self._bg_color)

        # Layout: [ticks | L-ch | gap | R-ch | margin]
        tick_w = 16
        margin_r = 2
        gap = 1
        avail = w - tick_w - margin_r - gap
        ch_w = max(4, avail // 2)

        top_margin = 2
        bot_margin = 2
        clip_h = 4
        meter_h = h - top_margin - bot_margin - clip_h

        x_l = tick_w
        x_r = tick_w + ch_w + gap

        # ── Draw dB tick marks ──
        painter.setFont(self._tick_font)
        fm = QFontMetrics(self._tick_font)

        for db in _DB_TICKS:
            frac = _db_to_fraction(db)
            y = top_margin + clip_h + int((1.0 - frac) * meter_h)
            y = max(top_margin + clip_h, min(h - bot_margin, y))

            # Tick line
            painter.setPen(QPen(QColor(55, 55, 55), 1))
            painter.drawLine(tick_w - 3, y, tick_w - 1, y)

            # Label
            painter.setPen(QPen(QColor(90, 90, 90), 1))
            label = str(db)
            tw = fm.horizontalAdvance(label)
            painter.drawText(int(tick_w - 4 - tw), y + 3, label)

        # ── Draw channels ──
        seg_h = max(1, meter_h // _NUM_SEGMENTS)

        self._draw_channel(painter, x_l, top_margin + clip_h,
                           ch_w, meter_h,
                           self._db_l, self._peak_db_l, seg_h)
        self._draw_channel(painter, x_r, top_margin + clip_h,
                           ch_w, meter_h,
                           self._db_r, self._peak_db_r, seg_h)

        # ── Draw clip indicators ──
        clip_color_l = QColor(255, 0, 0) if self._clip_l else QColor(50, 10, 10)
        clip_color_r = QColor(255, 0, 0) if self._clip_r else QColor(50, 10, 10)
        painter.fillRect(x_l, top_margin, ch_w, clip_h - 1, clip_color_l)
        painter.fillRect(x_r, top_margin, ch_w, clip_h - 1, clip_color_r)

        # Border
        painter.setPen(QPen(QColor(40, 40, 40), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        painter.end()

    def _draw_channel(self, painter: QPainter,
                      x: int, y_top: int, ch_w: int, ch_h: int,
                      level_db: float, peak_db: float, seg_h: int) -> None:
        """Draw a single channel's segmented meter."""
        level_frac = _db_to_fraction(level_db)
        peak_frac = _db_to_fraction(peak_db)

        seg_gap = 1

        for i in range(_NUM_SEGMENTS):
            seg_frac = _SEGMENT_FRAC[i]

            # Y position: segment 0 is at bottom, highest segment at top
            seg_y = y_top + ch_h - (i + 1) * seg_h

            if seg_y < y_top:
                break

            actual_seg_h = max(1, seg_h - seg_gap)

            if seg_frac < level_frac:
                painter.fillRect(x, seg_y, ch_w, actual_seg_h,
                                 _SEGMENT_COLOR_LIT[i])
            else:
                painter.fillRect(x, seg_y, ch_w, actual_seg_h,
                                 _SEGMENT_COLOR_DIM[i])

        # ── Peak hold marker ──
        if peak_db > _DB_MIN + 1.0:
            peak_y = y_top + int((1.0 - peak_frac) * ch_h)
            peak_y = max(y_top, min(y_top + ch_h - 2, peak_y))

            if peak_db > _DB_RED_END:
                pc = QColor(255, 40, 40)
            elif peak_db > _DB_ORANGE_END:
                pc = QColor(255, 160, 0)
            elif peak_db > _DB_YELLOW_END:
                pc = QColor(220, 220, 0)
            else:
                pc = QColor(0, 255, 60)

            painter.setPen(QPen(pc, 2))
            painter.drawLine(x, peak_y, x + ch_w, peak_y)


class VUMeterWithLabel(QWidget):
    """VU Meter with optional label."""

    def __init__(self, label: str = "", parent: QWidget | None = None):
        super().__init__(parent)

        from PyQt6.QtWidgets import QVBoxLayout, QLabel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if label:
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 9px; color: #888;")
            layout.addWidget(lbl)

        self.meter = VUMeterWidget()
        layout.addWidget(self.meter, 1)

    def set_levels(self, l: float, r: float) -> None:
        self.meter.set_levels(l, r)

    def reset(self) -> None:
        self.meter.reset()


# Quick test
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget
    from PyQt6.QtCore import QTimer
    import random

    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("VU Meter Test — Professional")

    central = QWidget()
    layout = QHBoxLayout(central)

    meters = []
    for i in range(8):
        meter = VUMeterWithLabel(f"T{i+1}")
        layout.addWidget(meter)
        meters.append(meter)

    window.setCentralWidget(central)
    window.resize(400, 400)
    window.show()

    phase = [random.random() * 6.28 for _ in range(8)]

    def update_meters():
        t = time.monotonic()
        for i, meter in enumerate(meters):
            base = 0.3 + 0.15 * math.sin(t * 2.0 + phase[i])
            beat = max(0, math.sin(t * 4.0 + phase[i])) * 0.4
            noise = random.random() * 0.05
            level = base + beat + noise
            stereo_offset = random.random() * 0.08
            meter.set_levels(level + stereo_offset, level - stereo_offset)

    timer = QTimer()
    timer.timeout.connect(update_meters)
    timer.start(33)  # 30 FPS

    sys.exit(app.exec())
