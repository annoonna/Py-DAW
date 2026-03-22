"""Arranger view container (v0.0.19.2.2)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QSplitter,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QToolButton,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent

from pydaw.services.project_service import ProjectService
from .track_list import TrackListWidget
from .arranger_canvas import ArrangerCanvas
from .clip_launcher_overlay import ClipLauncherOverlay


class ArrangerView(QWidget):
    clip_activated = pyqtSignal(str)
    clip_selected = pyqtSignal(str)

    request_rename_clip = pyqtSignal(str)
    request_duplicate_clip = pyqtSignal(str)
    request_delete_clip = pyqtSignal(str)
    
    # Status messages from keyboard shortcuts (v0.0.19.7.0)
    status_message = pyqtSignal(str, int)  # (message, timeout_ms)

    # Visible horizontal range in beats (used by other editors)
    view_range_changed = pyqtSignal(float, float)

    # Drag&Drop overlay import (file_path, track_id, start_beats, slot_key)
    request_import_audio_file = pyqtSignal(str, str, float, str)

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: Zoom controls
        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 4)
        header.setSpacing(6)

        lbl = QLabel("Arranger")
        header.addWidget(lbl)
        header.addStretch(1)

        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("-")
        self.btn_zoom_out.setToolTip("Zoom out (Mausrad)")

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.setToolTip("Zoom in (Mausrad)")

        self.lbl_zoom = QLabel("")
        self.lbl_zoom.setMinimumWidth(100)

        header.addWidget(self.btn_zoom_out)
        header.addWidget(self.btn_zoom_in)
        header.addWidget(self.lbl_zoom)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tracks = TrackListWidget(self.project)
        splitter.addWidget(self.tracks)
        splitter.setStretchFactor(0, 0)

        self.canvas = ArrangerCanvas(self.project)
        self.canvas.clip_selected.connect(self.clip_selected.emit)
        self.canvas.clip_activated.connect(self.clip_activated.emit)
        self.canvas.request_rename_clip.connect(self.request_rename_clip.emit)
        self.canvas.request_duplicate_clip.connect(self.request_duplicate_clip.emit)
        self.canvas.request_delete_clip.connect(self.request_delete_clip.emit)
        self.canvas.status_message.connect(self.status_message.emit)  # Keyboard shortcuts (v0.0.19.7.0)

        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        self.canvas.zoom_changed.connect(lambda ppb: self.lbl_zoom.setText(f"Zoom: {ppb:.0f}px/beat"))
        self.lbl_zoom.setText(f"Zoom: {float(getattr(self.canvas, 'pixels_per_beat', 80.0)):.0f}px/beat")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.canvas)

        # Clip-Launcher Overlay (shown during Browser drag)
        self.clip_overlay = ClipLauncherOverlay(self.project, parent=self.scroll.viewport())
        self.clip_overlay.setGeometry(self.scroll.viewport().rect())
        self.clip_overlay.request_import_audio.connect(self.request_import_audio_file.emit)
        self.scroll.viewport().installEventFilter(self)

        # Keep other editors in sync with horizontal scrolling / zoom.
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda _v: self._emit_view_range())
        try:
            self.canvas.zoom_changed.connect(lambda _ppb: self._emit_view_range())
        except Exception:
            pass

        splitter.addWidget(self.scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])

        layout.addWidget(splitter, 1)

        self._emit_view_range()

    def visible_range_beats(self) -> tuple[float, float]:
        if not hasattr(self, "scroll"):
            return (0.0, 0.0)
        bar = self.scroll.horizontalScrollBar()
        start_px = float(bar.value())
        end_px = start_px + float(self.scroll.viewport().width())
        ppb = float(getattr(self.canvas, "pixels_per_beat", 80.0))
        start_beat = max(0.0, start_px / ppb)
        end_beat = max(start_beat, end_px / ppb)
        return (start_beat, end_beat)

    def _emit_view_range(self) -> None:
        a, b = self.visible_range_beats()
        self.view_range_changed.emit(a, b)

    def set_transport(self, transport) -> None:
        """Forward transport to the overlay (playhead snap)."""
        try:
            self.clip_overlay.set_transport(transport)
        except Exception:
            pass

    def activate_clip_overlay(self, drag_label: str = "") -> None:
        try:
            self.clip_overlay.setGeometry(self.scroll.viewport().rect())
            self.clip_overlay.activate(drag_label)
        except Exception:
            pass

    def deactivate_clip_overlay(self) -> None:
        try:
            self.clip_overlay.deactivate()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: ANN001
        if hasattr(self, "scroll") and obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            try:
                self.clip_overlay.setGeometry(self.scroll.viewport().rect())
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):  # noqa: ANN001
        super().resizeEvent(event)
        self._emit_view_range()
