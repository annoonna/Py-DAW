"""Automation-Ready Widgets (v0.0.20.89).

Smart widgets that natively support automation and modulation.
Inspired by Bitwig Studio's modulation visualization.

Features:
- AutomatedWidgetMixin: Base mixin for any widget to become automation-ready
  - Right-click context menu: "Show Automation in Arranger"
  - parameter_id binding to AutomationManager
  - Modulation offset visualization
- AutomatedKnob: QDial replacement with Bitwig-style modulation ring
  - Static base value indicator
  - Colored ring showing modulation offset
  - Shift+Drag for fine adjustment
  - Mouse wheel support
- AutomatedSlider: QSlider replacement with modulation overlay

Thread Safety:
- Widget only talks to AutomationManager (GUI thread)
- AutomationManager bridges to RTParamStore (audio thread)
- Zero direct audio-thread access from widgets

Usage:
    knob = AutomatedKnob(automation_manager, "trk:abc:vol", "Volume", 0.0, 1.0, 0.8)
    # knob.value_changed.connect(my_handler)
    # Right-click → "Show Automation in Arranger" → automation_manager.request_show_automation
"""
from __future__ import annotations

import math
from typing import Any, Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QConicalGradient,
    QRadialGradient, QFontMetrics, QMouseEvent, QWheelEvent,
    QPaintEvent, QAction,
)
from PyQt6.QtWidgets import QWidget, QMenu, QVBoxLayout, QLabel, QSizePolicy


class AutomatedWidgetMixin:
    """Mixin that makes any QWidget automation-ready.

    Provides:
    - parameter_id + automation_manager binding
    - Right-click context menu with "Show Automation in Arranger"
    - Modulation offset tracking
    - Value synchronization (widget ↔ engine)

    Usage: class MyKnob(QWidget, AutomatedWidgetMixin): ...
    """

    _automation_manager = None  # type: Any
    _parameter_id: str = ""
    _track_id: str = ""
    _modulation_offset: float = 0.0
    _automation_active: bool = False

    def init_automation(
        self,
        automation_manager: Any,
        parameter_id: str,
        track_id: str = "",
    ) -> None:
        """Call this in __init__ after super().__init__()."""
        self._automation_manager = automation_manager
        self._parameter_id = parameter_id
        self._track_id = track_id

        # Set context menu policy
        if hasattr(self, "setContextMenuPolicy"):
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_automation_context_menu)

    def _show_automation_context_menu(self, pos) -> None:
        """Global right-click context menu for automation."""
        menu = QMenu()

        # Show Automation in Arranger
        a_show = menu.addAction("🎛 Show Automation in Arranger")
        a_show.triggered.connect(self._on_show_automation)

        menu.addSeparator()

        # Add Modulator (placeholder)
        a_mod = menu.addAction("🔄 Add Modulator (LFO)…")
        a_mod.setEnabled(False)  # Phase 2

        a_env = menu.addAction("📈 Add Modulator (Envelope)…")
        a_env.setEnabled(False)  # Phase 2

        menu.addSeparator()

        # Reset to default
        a_reset = menu.addAction("↩ Reset to Default")
        a_reset.triggered.connect(self._on_reset_default)

        # Copy/Paste automation
        a_copy = menu.addAction("📋 Copy Automation")
        a_copy.setEnabled(False)  # Phase 2

        a_paste = menu.addAction("📋 Paste Automation")
        a_paste.setEnabled(False)  # Phase 2

        menu.exec(self.mapToGlobal(pos) if hasattr(self, "mapToGlobal") else pos)

    def _on_show_automation(self) -> None:
        if self._automation_manager and self._parameter_id:
            self._automation_manager.request_show_automation.emit(self._parameter_id)

    def _on_reset_default(self) -> None:
        if self._automation_manager and self._parameter_id:
            param = self._automation_manager.get_parameter(self._parameter_id)
            if param:
                param.set_value(param.default_val)
                param.set_automation_value(None)

    def set_modulation_offset(self, offset: float) -> None:
        """Update the displayed modulation offset (Bitwig ring)."""
        self._modulation_offset = offset
        if hasattr(self, "update"):
            self.update()

    def set_automation_active(self, active: bool) -> None:
        """Visual indicator: automation is currently overriding this parameter."""
        self._automation_active = active
        if hasattr(self, "update"):
            self.update()


class AutomatedKnob(QWidget, AutomatedWidgetMixin):
    """Bitwig-style rotary knob with modulation ring.

    Visual design:
    - Dark circular knob body
    - White/cyan arc showing current value
    - Colored ring (orange/purple) showing modulation offset
    - Static notch showing base value when automation is active
    - Value label below

    Interaction:
    - Click+Drag up/down to change value
    - Shift+Drag for fine adjustment (10x precision)
    - Mouse wheel to increment/decrement
    - Double-click to enter value manually
    - Right-click for automation context menu
    """

    value_changed = pyqtSignal(float)  # normalized 0..1

    # Arc geometry constants
    ARC_START = 225  # degrees (bottom-left)
    ARC_SPAN = 270   # total arc degrees

    # Colors
    COLOR_BG = QColor(40, 40, 45)
    COLOR_TRACK = QColor(60, 60, 65)
    COLOR_VALUE = QColor(0, 191, 255)  # deep sky blue
    COLOR_MOD_POS = QColor(255, 140, 0)  # orange for positive modulation
    COLOR_MOD_NEG = QColor(160, 80, 255)  # purple for negative modulation
    COLOR_AUTOMATION = QColor(255, 60, 60)  # red notch when automation active
    COLOR_NOTCH = QColor(220, 220, 220)
    COLOR_LABEL = QColor(180, 180, 180)

    def __init__(
        self,
        automation_manager: Any = None,
        parameter_id: str = "",
        label: str = "",
        min_val: float = 0.0,
        max_val: float = 1.0,
        default_val: float = 0.0,
        track_id: str = "",
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._label = label
        self._min_val = min_val
        self._max_val = max_val
        self._default_val = default_val
        self._value = default_val  # normalized internally
        self._drag_start_y = 0.0
        self._drag_start_val = 0.0
        self._dragging = False

        self.setMinimumSize(48, 60)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(56, 72)
        self.setMouseTracking(True)

        if automation_manager:
            self.init_automation(automation_manager, parameter_id, track_id)

    # --- Value access ---

    def value(self) -> float:
        """Current value in user range."""
        return self._value

    def normalized_value(self) -> float:
        """Current value as 0..1."""
        span = self._max_val - self._min_val
        if span <= 0:
            return 0.0
        return (self._value - self._min_val) / span

    def set_value_external(self, value: float) -> None:
        """Set value from outside (automation playback, etc.) without emitting signal."""
        self._value = max(self._min_val, min(self._max_val, float(value)))
        self.update()

    def setValue(self, value: float) -> None:
        """Set value and emit signal."""
        old = self._value
        self._value = max(self._min_val, min(self._max_val, float(value)))
        if abs(self._value - old) > 1e-9:
            self.value_changed.emit(self._value)
            self.update()

    # --- Mouse events ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_y = event.position().y()
            self._drag_start_val = self._value
            self.setCursor(Qt.CursorShape.BlankCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            dy = self._drag_start_y - event.position().y()
            sensitivity = 0.002 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.01
            span = self._max_val - self._min_val
            new_val = self._drag_start_val + dy * sensitivity * span
            self.setValue(new_val)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click resets to default."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._default_val)
            event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        step = 0.001 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.01
        span = self._max_val - self._min_val
        if delta > 0:
            self.setValue(self._value + step * span)
        elif delta < 0:
            self.setValue(self._value - step * span)
        event.accept()

    # --- Paint ---

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        knob_size = min(w, h - 16) - 4  # leave space for label
        cx = w / 2.0
        cy = (h - 16) / 2.0
        radius = knob_size / 2.0
        pen_width = 3.0

        # Knob body (dark circle)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self.COLOR_BG))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Track arc (background)
        arc_rect = QRectF(cx - radius + pen_width, cy - radius + pen_width,
                          (radius - pen_width) * 2, (radius - pen_width) * 2)
        p.setPen(QPen(self.COLOR_TRACK, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, int(self.ARC_START * 16), int(self.ARC_SPAN * 16))

        # Value arc
        norm = self.normalized_value()
        value_span = norm * self.ARC_SPAN
        p.setPen(QPen(self.COLOR_VALUE, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, int(self.ARC_START * 16), int(-value_span * 16))

        # Modulation ring (Bitwig-style colored overlay)
        if abs(self._modulation_offset) > 0.001:
            span = self._max_val - self._min_val
            mod_norm = self._modulation_offset / span if span > 0 else 0.0
            mod_span_deg = mod_norm * self.ARC_SPAN

            # Arc starts where value arc ends
            mod_start = self.ARC_START - value_span
            color = self.COLOR_MOD_POS if mod_norm > 0 else self.COLOR_MOD_NEG
            mod_pen = QPen(color, pen_width + 1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            mod_pen.setColor(QColor(color.red(), color.green(), color.blue(), 160))
            p.setPen(mod_pen)
            p.drawArc(arc_rect, int(mod_start * 16), int(-mod_span_deg * 16))

        # Value notch (white line pointing to current value)
        angle_rad = math.radians(self.ARC_START - value_span)
        notch_inner = radius - pen_width - 6
        notch_outer = radius - pen_width - 1
        nx1 = cx + notch_inner * math.cos(angle_rad)
        ny1 = cy - notch_inner * math.sin(angle_rad)
        nx2 = cx + notch_outer * math.cos(angle_rad)
        ny2 = cy - notch_outer * math.sin(angle_rad)
        notch_color = self.COLOR_AUTOMATION if self._automation_active else self.COLOR_NOTCH
        p.setPen(QPen(notch_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(nx1, ny1), QPointF(nx2, ny2))

        # Label
        p.setPen(QPen(self.COLOR_LABEL))
        font = p.font()
        font.setPointSize(7)
        p.setFont(font)
        label_rect = QRectF(0, h - 14, w, 14)
        display_text = self._label if self._label else ""
        p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, display_text)

        p.end()


class AutomatedSlider(QWidget, AutomatedWidgetMixin):
    """Automation-ready slider with modulation overlay.

    Horizontal or vertical slider with:
    - Value track + modulation overlay
    - Right-click automation context menu
    - Shift+Drag for fine adjustment
    """

    value_changed = pyqtSignal(float)

    COLOR_BG = QColor(50, 50, 55)
    COLOR_TRACK = QColor(70, 70, 75)
    COLOR_FILL = QColor(0, 191, 255)
    COLOR_MOD = QColor(255, 140, 0, 120)
    COLOR_THUMB = QColor(200, 200, 210)

    def __init__(
        self,
        automation_manager: Any = None,
        parameter_id: str = "",
        min_val: float = 0.0,
        max_val: float = 1.0,
        default_val: float = 0.0,
        track_id: str = "",
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._min_val = min_val
        self._max_val = max_val
        self._value = default_val
        self._orientation = orientation
        self._dragging = False
        self._drag_start = 0.0
        self._drag_start_val = 0.0

        if orientation == Qt.Orientation.Horizontal:
            self.setMinimumSize(80, 20)
            self.setFixedHeight(22)
        else:
            self.setMinimumSize(20, 80)
            self.setFixedWidth(22)

        if automation_manager:
            self.init_automation(automation_manager, parameter_id, track_id)

    def value(self) -> float:
        return self._value

    def normalized_value(self) -> float:
        span = self._max_val - self._min_val
        if span <= 0:
            return 0.0
        return (self._value - self._min_val) / span

    def setValue(self, value: float) -> None:
        old = self._value
        self._value = max(self._min_val, min(self._max_val, float(value)))
        if abs(self._value - old) > 1e-9:
            self.value_changed.emit(self._value)
            self.update()

    def set_value_external(self, value: float) -> None:
        self._value = max(self._min_val, min(self._max_val, float(value)))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            if self._orientation == Qt.Orientation.Horizontal:
                self._drag_start = event.position().x()
            else:
                self._drag_start = event.position().y()
            self._drag_start_val = self._value
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            if self._orientation == Qt.Orientation.Horizontal:
                delta = event.position().x() - self._drag_start
                total = max(1, self.width())
            else:
                delta = self._drag_start - event.position().y()
                total = max(1, self.height())
            sensitivity = 0.1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            span = self._max_val - self._min_val
            self.setValue(self._drag_start_val + (delta / total) * span * sensitivity)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        step = 0.001 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.01
        span = self._max_val - self._min_val
        self.setValue(self._value + (1 if delta > 0 else -1) * step * span)
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        margin = 2
        norm = self.normalized_value()

        if self._orientation == Qt.Orientation.Horizontal:
            # Background track
            track_rect = QRectF(margin, h / 2 - 3, w - 2 * margin, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.COLOR_TRACK))
            p.drawRoundedRect(track_rect, 3, 3)

            # Value fill
            fill_w = norm * (w - 2 * margin)
            fill_rect = QRectF(margin, h / 2 - 3, fill_w, 6)
            p.setBrush(QBrush(self.COLOR_FILL))
            p.drawRoundedRect(fill_rect, 3, 3)

            # Modulation overlay
            if abs(self._modulation_offset) > 0.001:
                span = self._max_val - self._min_val
                mod_w = (self._modulation_offset / span) * (w - 2 * margin) if span > 0 else 0
                mod_rect = QRectF(margin + fill_w, h / 2 - 3, mod_w, 6)
                p.setBrush(QBrush(self.COLOR_MOD))
                p.drawRoundedRect(mod_rect, 3, 3)

            # Thumb
            thumb_x = margin + fill_w
            p.setBrush(QBrush(self.COLOR_THUMB))
            p.drawEllipse(QPointF(thumb_x, h / 2), 5, 5)
        else:
            # Vertical
            track_rect = QRectF(w / 2 - 3, margin, 6, h - 2 * margin)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.COLOR_TRACK))
            p.drawRoundedRect(track_rect, 3, 3)

            fill_h = norm * (h - 2 * margin)
            fill_rect = QRectF(w / 2 - 3, h - margin - fill_h, 6, fill_h)
            p.setBrush(QBrush(self.COLOR_FILL))
            p.drawRoundedRect(fill_rect, 3, 3)

            thumb_y = h - margin - fill_h
            p.setBrush(QBrush(self.COLOR_THUMB))
            p.drawEllipse(QPointF(w / 2, thumb_y), 5, 5)

        p.end()
