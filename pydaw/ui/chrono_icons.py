# -*- coding: utf-8 -*-
"""ChronoScaleStudio small vector icons (QPainter-based, no external assets).

Style:
- Python Blue: #3776AB
- Qt Green:    #41CD52

Icons are tiny (toolbutton size) and designed for dark UI backgrounds.
"""
from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


_PY_BLUE = QColor("#3776AB")
_QT_GREEN = QColor("#41CD52")

_cache: Dict[Tuple[str, int], QIcon] = {}


def icon(name: str, size: int = 16) -> QIcon:
    key = (str(name or "").lower(), int(size))
    if key in _cache:
        return _cache[key]

    s = int(size)
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        n = key[0]
        if n in ("up", "arrow_up"):
            _paint_arrow(p, s, up=True)
        elif n in ("down", "arrow_down"):
            _paint_arrow(p, s, up=False)
        elif n in ("record", "rec"):
            _paint_record(p, s)
        elif n in ("mute", "silence"):
            _paint_mute(p, s)
        elif n in ("solo",):
            _paint_solo(p, s)
        elif n in ("monitor", "input"):
            _paint_monitor(p, s)
        elif n in ("io", "routing"):
            _paint_io(p, s)
        elif n in ("power", "onoff", "enable"):
            _paint_power(p, s)
        elif n in ("close", "x", "remove"):
            _paint_close(p, s)
        elif n in ("plus", "add"):
            _paint_plus(p, s)
        else:
            # fallback: small dot
            pen = QPen(_PY_BLUE)
            pen.setWidthF(max(1.2, s * 0.12))
            p.setPen(pen)
            p.drawPoint(int(s * 0.5), int(s * 0.5))
    finally:
        p.end()

    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def _paint_arrow(p: QPainter, s: int, *, up: bool) -> None:
    # blue filled arrow + green accent line
    margin = s * 0.18
    cx = s * 0.5
    top = margin if up else s - margin
    bot = s - margin if up else margin
    w = s * 0.46

    poly = QPolygonF([
        QPointF(cx, top),
        QPointF(cx - w * 0.5, bot),
        QPointF(cx + w * 0.5, bot),
    ])

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_PY_BLUE)
    p.drawPolygon(poly)

    # accent spine
    pen = QPen(_QT_GREEN)
    pen.setWidthF(max(1.4, s * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    if up:
        p.drawLine(QPointF(cx, s * 0.30), QPointF(cx, s * 0.72))
    else:
        p.drawLine(QPointF(cx, s * 0.28), QPointF(cx, s * 0.70))


def _paint_power(p: QPainter, s: int) -> None:
    # blue circle + green bar
    r = s * 0.34
    rect = QRectF(s * 0.5 - r, s * 0.5 - r, 2 * r, 2 * r)

    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.4, s * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)

    pen2 = QPen(_QT_GREEN)
    pen2.setWidthF(max(1.6, s * 0.11))
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.5, s * 0.18), QPointF(s * 0.5, s * 0.52))


def _paint_close(p: QPainter, s: int) -> None:
    # blue X with green shadow
    w = max(1.6, s * 0.12)
    pad = s * 0.22

    pen_g = QPen(_QT_GREEN)
    pen_g.setWidthF(w)
    pen_g.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen_g)
    p.drawLine(QPointF(pad + 0.8, pad + 0.8), QPointF(s - pad + 0.8, s - pad + 0.8))
    p.drawLine(QPointF(s - pad + 0.8, pad + 0.8), QPointF(pad + 0.8, s - pad + 0.8))

    pen = QPen(_PY_BLUE)
    pen.setWidthF(w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(pad, pad), QPointF(s - pad, s - pad))
    p.drawLine(QPointF(s - pad, pad), QPointF(pad, s - pad))


def _paint_plus(p: QPainter, s: int) -> None:
    w = max(1.6, s * 0.12)
    pad = s * 0.24

    pen = QPen(_QT_GREEN)
    pen.setWidthF(w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, pad), QPointF(s * 0.5, s - pad))
    p.drawLine(QPointF(pad, s * 0.5), QPointF(s - pad, s * 0.5))

    # blue outline hint
    pen2 = QPen(_PY_BLUE)
    pen2.setWidthF(max(1.0, w * 0.65))
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.5, pad + 0.9), QPointF(s * 0.5, s - pad + 0.9))
    p.drawLine(QPointF(pad + 0.9, s * 0.5), QPointF(s - pad + 0.9, s * 0.5))


def _paint_record(p: QPainter, s: int) -> None:
    # circle (blue) with inner dot (green)
    r = s * 0.34
    rect = QRectF(s * 0.5 - r, s * 0.5 - r, 2 * r, 2 * r)
    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.4, s * 0.10))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_QT_GREEN)
    rr = s * 0.16
    p.drawEllipse(QRectF(s * 0.5 - rr, s * 0.5 - rr, 2 * rr, 2 * rr))


def _paint_mute(p: QPainter, s: int) -> None:
    # speaker-ish trapezoid + X
    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.3, s * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    x0 = s * 0.20
    y0 = s * 0.38
    w = s * 0.18
    h = s * 0.24
    p.drawRect(QRectF(x0, y0, w, h))
    poly = QPolygonF([
        QPointF(x0 + w, y0),
        QPointF(s * 0.58, s * 0.26),
        QPointF(s * 0.58, s * 0.74),
        QPointF(x0 + w, y0 + h),
    ])
    p.drawPolygon(poly)

    # X (green)
    pen2 = QPen(_QT_GREEN)
    pen2.setWidthF(max(1.4, s * 0.11))
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    a = QPointF(s * 0.66, s * 0.34)
    b = QPointF(s * 0.84, s * 0.66)
    c = QPointF(s * 0.84, s * 0.34)
    d = QPointF(s * 0.66, s * 0.66)
    p.drawLine(a, b)
    p.drawLine(c, d)


def _paint_solo(p: QPainter, s: int) -> None:
    # simple circle ring with inner dot (solo)
    r = s * 0.34
    rect = QRectF(s * 0.5 - r, s * 0.5 - r, 2 * r, 2 * r)
    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.4, s * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_QT_GREEN)
    rr = s * 0.10
    p.drawEllipse(QRectF(s * 0.5 - rr, s * 0.5 - rr, 2 * rr, 2 * rr))


def _paint_monitor(p: QPainter, s: int) -> None:
    # "I" style bar + small input dot
    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.6, s * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.40, s * 0.24), QPointF(s * 0.40, s * 0.76))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_QT_GREEN)
    rr = s * 0.10
    p.drawEllipse(QRectF(s * 0.68 - rr, s * 0.5 - rr, 2 * rr, 2 * rr))


def _paint_io(p: QPainter, s: int) -> None:
    # two arrows left/right
    pen = QPen(_PY_BLUE)
    pen.setWidthF(max(1.4, s * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # left arrow
    p.drawLine(QPointF(s * 0.62, s * 0.34), QPointF(s * 0.34, s * 0.34))
    p.drawLine(QPointF(s * 0.34, s * 0.34), QPointF(s * 0.42, s * 0.28))
    p.drawLine(QPointF(s * 0.34, s * 0.34), QPointF(s * 0.42, s * 0.40))

    # right arrow (green)
    pen2 = QPen(_QT_GREEN)
    pen2.setWidthF(max(1.4, s * 0.10))
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.38, s * 0.66), QPointF(s * 0.66, s * 0.66))
    p.drawLine(QPointF(s * 0.66, s * 0.66), QPointF(s * 0.58, s * 0.60))
    p.drawLine(QPointF(s * 0.66, s * 0.66), QPointF(s * 0.58, s * 0.72))
