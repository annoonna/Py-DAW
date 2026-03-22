"""Clip Slot Loop Editor - Pro-DAW-Style Loop Management.

Ermöglicht das Festlegen von Loop-Bereichen direkt im Slot:
- Loop Start/End per Klick und Drag
- Offset-Marker
- Visuelle Timeline
- Sample-accurate Loop-Punkte
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QWidget,
    QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QMouseEvent

if TYPE_CHECKING:
    from pydaw.model.project import AudioClip, MidiClip


class LoopTimelineWidget(QWidget):
    """Interactive Timeline für Loop-Bereich Festlegung."""
    
    loop_changed = pyqtSignal(float, float, float)  # start, end, offset
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(600, 100)
        self.setMouseTracking(True)
        
        # Loop-Parameter (in Beats)
        self.clip_length = 4.0
        self.loop_start = 0.0
        self.loop_end = 4.0
        self.offset = 0.0
        
        # Interaktion
        self._dragging: str | None = None  # 'start', 'end', 'offset', None
        self._hover: str | None = None
        
    def set_clip_length(self, beats: float) -> None:
        """Clip-Länge setzen."""
        self.clip_length = max(0.25, float(beats))
        self.loop_end = min(self.loop_end, self.clip_length)
        self.update()
        
    def set_loop_params(self, start: float, end: float, offset: float) -> None:
        """Loop-Parameter setzen."""
        self.loop_start = max(0.0, min(start, self.clip_length))
        self.loop_end = max(self.loop_start, min(end, self.clip_length))
        self.offset = max(0.0, min(offset, self.loop_end - self.loop_start))
        self.update()
        
    def _beat_to_x(self, beat: float) -> float:
        """Beat-Position zu X-Koordinate."""
        margin = 40
        width = self.width() - 2 * margin
        return margin + (beat / max(0.001, self.clip_length)) * width
        
    def _x_to_beat(self, x: float) -> float:
        """X-Koordinate zu Beat-Position."""
        margin = 40
        width = self.width() - 2 * margin
        beat = ((x - margin) / max(1, width)) * self.clip_length
        return max(0.0, min(self.clip_length, beat))
        
    def paintEvent(self, event):  # noqa: ANN001
        """Zeichne Timeline mit Loop-Region."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        margin = 40
        y_center = self.height() // 2
        
        # Hintergrund
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        
        # Timeline-Linie
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.drawLine(int(margin), y_center, int(self.width() - margin), y_center)
        
        # Beat-Markers
        for beat in range(int(self.clip_length) + 1):
            x = self._beat_to_x(float(beat))
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            painter.drawLine(int(x), y_center - 10, int(x), y_center + 10)
            painter.drawText(int(x) - 10, y_center + 30, f"{beat}")
            
        # Loop-Region Highlight
        loop_start_x = self._beat_to_x(self.loop_start)
        loop_end_x = self._beat_to_x(self.loop_end)
        
        painter.fillRect(
            QRectF(loop_start_x, y_center - 20, loop_end_x - loop_start_x, 40),
            QColor(70, 130, 180, 80)  # Pro-DAW-Blue, transparent
        )
        
        # Loop Start Marker
        color_start = QColor(0, 200, 0) if self._hover == 'start' else QColor(0, 160, 0)
        painter.setBrush(QBrush(color_start))
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRect(QRectF(loop_start_x - 5, y_center - 25, 10, 50))
        painter.drawText(int(loop_start_x) - 20, y_center - 30, "START")
        
        # Loop End Marker
        color_end = QColor(200, 0, 0) if self._hover == 'end' else QColor(160, 0, 0)
        painter.setBrush(QBrush(color_end))
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRect(QRectF(loop_end_x - 5, y_center - 25, 10, 50))
        painter.drawText(int(loop_end_x) - 20, y_center - 30, "END")
        
        # Offset Marker
        if self.offset > 0.0:
            offset_x = loop_start_x + (loop_end_x - loop_start_x) * (self.offset / max(0.001, self.loop_end - self.loop_start))
            color_offset = QColor(255, 200, 0) if self._hover == 'offset' else QColor(200, 150, 0)
            painter.setBrush(QBrush(color_offset))
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawEllipse(QPointF(offset_x, y_center), 6, 6)
            painter.drawText(int(offset_x) - 25, y_center + 50, "OFFSET")
            
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle Klick auf Marker."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
            
        x = event.position().x()
        y_center = self.height() // 2
        
        loop_start_x = self._beat_to_x(self.loop_start)
        loop_end_x = self._beat_to_x(self.loop_end)
        
        # Check Start Marker
        if abs(x - loop_start_x) < 10 and abs(event.position().y() - y_center) < 30:
            self._dragging = 'start'
            return
            
        # Check End Marker
        if abs(x - loop_end_x) < 10 and abs(event.position().y() - y_center) < 30:
            self._dragging = 'end'
            return
            
        # Check Offset Marker
        if self.offset > 0.0:
            offset_x = loop_start_x + (loop_end_x - loop_start_x) * (self.offset / max(0.001, self.loop_end - self.loop_start))
            if abs(x - offset_x) < 10 and abs(event.position().y() - y_center) < 10:
                self._dragging = 'offset'
                return
                
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle Drag und Hover."""
        x = event.position().x()
        y_center = self.height() // 2
        
        if self._dragging:
            beat = self._x_to_beat(x)
            
            if self._dragging == 'start':
                self.loop_start = max(0.0, min(beat, self.loop_end - 0.25))
            elif self._dragging == 'end':
                self.loop_end = max(self.loop_start + 0.25, min(beat, self.clip_length))
            elif self._dragging == 'offset':
                loop_length = self.loop_end - self.loop_start
                relative_pos = (beat - self.loop_start) / max(0.001, loop_length)
                self.offset = max(0.0, min(relative_pos * loop_length, loop_length))
                
            self.update()
            self.loop_changed.emit(self.loop_start, self.loop_end, self.offset)
        else:
            # Hover-Detection
            loop_start_x = self._beat_to_x(self.loop_start)
            loop_end_x = self._beat_to_x(self.loop_end)
            
            old_hover = self._hover
            self._hover = None
            
            if abs(x - loop_start_x) < 10 and abs(event.position().y() - y_center) < 30:
                self._hover = 'start'
            elif abs(x - loop_end_x) < 10 and abs(event.position().y() - y_center) < 30:
                self._hover = 'end'
            elif self.offset > 0.0:
                offset_x = loop_start_x + (loop_end_x - loop_start_x) * (self.offset / max(0.001, self.loop_end - self.loop_start))
                if abs(x - offset_x) < 10 and abs(event.position().y() - y_center) < 10:
                    self._hover = 'offset'
                    
            if old_hover != self._hover:
                self.update()
                
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle Drag-Ende."""
        if self._dragging:
            self._dragging = None
            self.loop_changed.emit(self.loop_start, self.loop_end, self.offset)


class ClipSlotLoopEditor(QDialog):
    """Dialog zum Editieren von Loop-Parametern eines Slots.
    
    Features:
    - Visuelle Timeline mit Drag-Markern
    - Präzise Zahlenwerte-Eingabe
    - Real-time Preview (optional)
    - Snap-to-Grid Option
    """
    
    def __init__(
        self,
        clip: AudioClip | MidiClip,
        parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.clip = clip
        self.setWindowTitle(f"Loop Editor: {clip.label}")
        self.setModal(True)
        self.resize(700, 400)
        
        self._build_ui()
        self._load_clip_params()
        
    def _build_ui(self) -> None:
        """UI aufbauen."""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel(f"<h2>Loop-Editor: {self.clip.label}</h2>")
        layout.addWidget(header)
        
        # Timeline
        timeline_group = QGroupBox("Loop-Region (Drag die Marker)")
        timeline_layout = QVBoxLayout(timeline_group)
        
        self.timeline = LoopTimelineWidget()
        self.timeline.loop_changed.connect(self._timeline_changed)
        timeline_layout.addWidget(self.timeline)
        
        layout.addWidget(timeline_group)
        
        # Präzise Werte
        values_group = QGroupBox("Präzise Werte (Beats)")
        values_layout = QHBoxLayout(values_group)
        
        values_layout.addWidget(QLabel("Loop Start:"))
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, 999.0)
        self.spin_start.setDecimals(3)
        self.spin_start.setSingleStep(0.25)
        self.spin_start.valueChanged.connect(self._values_changed)
        values_layout.addWidget(self.spin_start)
        
        values_layout.addWidget(QLabel("Loop End:"))
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.0, 999.0)
        self.spin_end.setDecimals(3)
        self.spin_end.setSingleStep(0.25)
        self.spin_end.valueChanged.connect(self._values_changed)
        values_layout.addWidget(self.spin_end)
        
        values_layout.addWidget(QLabel("Offset:"))
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 999.0)
        self.spin_offset.setDecimals(3)
        self.spin_offset.setSingleStep(0.25)
        self.spin_offset.valueChanged.connect(self._values_changed)
        values_layout.addWidget(self.spin_offset)
        
        layout.addWidget(values_group)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self._reset)
        buttons.addWidget(btn_reset)
        
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_ok.setDefault(True)
        buttons.addWidget(btn_ok)
        
        layout.addLayout(buttons)
        
    def _load_clip_params(self) -> None:
        """Lade aktuelle Clip-Parameter."""
        # Clip-Länge ermitteln
        if hasattr(self.clip, 'length_beats'):
            clip_length = float(self.clip.length_beats)
        elif hasattr(self.clip, 'duration_beats'):
            clip_length = float(self.clip.duration_beats)
        else:
            clip_length = 4.0  # Default
            
        # Loop-Parameter laden
        loop_start = float(getattr(self.clip, 'loop_start', 0.0))
        loop_end = float(getattr(self.clip, 'loop_end', clip_length))
        offset = float(getattr(self.clip, 'offset', 0.0))
        
        # Timeline konfigurieren
        self.timeline.set_clip_length(clip_length)
        self.timeline.set_loop_params(loop_start, loop_end, offset)
        
        # SpinBoxen setzen (ohne Signal-Trigger)
        self.spin_start.blockSignals(True)
        self.spin_end.blockSignals(True)
        self.spin_offset.blockSignals(True)
        
        self.spin_start.setValue(loop_start)
        self.spin_end.setValue(loop_end)
        self.spin_offset.setValue(offset)
        
        self.spin_start.blockSignals(False)
        self.spin_end.blockSignals(False)
        self.spin_offset.blockSignals(False)
        
    def _timeline_changed(self, start: float, end: float, offset: float) -> None:
        """Timeline wurde geändert -> SpinBoxen updaten."""
        self.spin_start.blockSignals(True)
        self.spin_end.blockSignals(True)
        self.spin_offset.blockSignals(True)
        
        self.spin_start.setValue(start)
        self.spin_end.setValue(end)
        self.spin_offset.setValue(offset)
        
        self.spin_start.blockSignals(False)
        self.spin_end.blockSignals(False)
        self.spin_offset.blockSignals(False)
        
    def _values_changed(self) -> None:
        """SpinBox-Werte geändert -> Timeline updaten."""
        start = self.spin_start.value()
        end = self.spin_end.value()
        offset = self.spin_offset.value()
        
        self.timeline.set_loop_params(start, end, offset)
        
    def _reset(self) -> None:
        """Reset auf Default-Werte."""
        clip_length = self.timeline.clip_length
        self.timeline.set_loop_params(0.0, clip_length, 0.0)
        self._timeline_changed(0.0, clip_length, 0.0)
        
    def get_loop_params(self) -> tuple[float, float, float]:
        """Aktuelle Loop-Parameter zurückgeben."""
        return (
            self.spin_start.value(),
            self.spin_end.value(),
            self.spin_offset.value()
        )
