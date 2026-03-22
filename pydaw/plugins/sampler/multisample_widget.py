# -*- coding: utf-8 -*-
"""Multi-Sample Mapping Editor Widget — Visual Key×Velocity Zone Editor.

v0.0.20.656 — AP7 Phase 7A

Features:
- Visual 2D grid: X = MIDI Key (0-127), Y = Velocity (0-127)
- Zones drawn as colored rectangles
- Click to select, drag edges to resize
- Zone inspector panel for per-zone DSP (Filter, ADSR, Mod Matrix)
- Drag&Drop samples onto grid to create zones
- Auto-mapping buttons (Chromatic, Drum)
- Sample start/end/loop point editor
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QMimeData
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QMouseEvent, QPaintEvent, QWheelEvent, QDragEnterEvent, QDropEvent,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QScrollArea, QSplitter, QFrame,
    QSizePolicy, QFileDialog, QMenu, QSlider, QCheckBox,
    QTabWidget,
)

from .multisample_model import (
    SampleZone, MultiSampleMap, ZoneEnvelope, ZoneFilter,
    ZoneLFO, ModulationSlot, LoopPoints,
    midi_note_name, note_name_to_midi, next_zone_color,
    ZONE_COLORS,
)
from .audio_io import SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)

_NOTE_NAMES_SHORT = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_AUDIO_FILTER = "Audio files ({});;All files (*)".format(
    " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
)


class ZoneMapCanvas(QWidget):
    """2D canvas showing key (X) × velocity (Y) zone rectangles."""

    zone_selected = pyqtSignal(str)  # zone_id
    zone_resized = pyqtSignal(str)   # zone_id after resize
    drop_files = pyqtSignal(list, int, int)  # files, note, velocity

    def __init__(self, sample_map: MultiSampleMap, parent: QWidget = None):
        super().__init__(parent)
        self._map = sample_map
        self._selected_zone_id: str = ""
        self._hovered_zone_id: str = ""

        # View
        self._key_start = 24   # visible key range
        self._key_end = 96
        self._vel_start = 0
        self._vel_end = 127

        # Interaction
        self._dragging: bool = False
        self._drag_edge: str = ""  # "left", "right", "top", "bottom", ""
        self._drag_zone_id: str = ""

        self.setMinimumHeight(200)
        self.setMinimumWidth(400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_map(self, sample_map: MultiSampleMap) -> None:
        self._map = sample_map
        self.update()

    def set_selected(self, zone_id: str) -> None:
        self._selected_zone_id = zone_id
        self.update()

    def _key_range(self) -> int:
        return max(1, self._key_end - self._key_start)

    def _vel_range(self) -> int:
        return max(1, self._vel_end - self._vel_start)

    def _note_to_x(self, note: int) -> float:
        w = float(self.width())
        return ((note - self._key_start) / self._key_range()) * w

    def _vel_to_y(self, vel: int) -> float:
        h = float(self.height())
        # Velocity 127 at top, 0 at bottom
        return (1.0 - (vel - self._vel_start) / self._vel_range()) * h

    def _x_to_note(self, x: float) -> int:
        w = float(self.width())
        if w < 1:
            return 60
        return int(self._key_start + (x / w) * self._key_range())

    def _y_to_vel(self, y: float) -> int:
        h = float(self.height())
        if h < 1:
            return 64
        return int(self._vel_start + (1.0 - y / h) * self._vel_range())

    def paintEvent(self, event: QPaintEvent) -> None:
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()

            # Background
            p.fillRect(0, 0, w, h, QColor("#1a1a2e"))

            # Grid lines — octave markers
            p.setPen(QPen(QColor("#2a2a44"), 1))
            for note in range(0, 128):
                if note < self._key_start or note > self._key_end:
                    continue
                x = self._note_to_x(note)
                if note % 12 == 0:
                    p.setPen(QPen(QColor("#3a3a5e"), 1))
                    p.drawLine(int(x), 0, int(x), h)
                    # Octave label
                    p.setPen(QPen(QColor("#666688"), 1))
                    font = p.font()
                    font.setPointSize(7)
                    p.setFont(font)
                    p.drawText(int(x) + 2, h - 3, f"C{note // 12 - 1}")
                elif note % 12 in (2, 4, 5, 7, 9, 11):
                    p.setPen(QPen(QColor("#22223a"), 1))
                    p.drawLine(int(x), 0, int(x), h)

            # Black keys shading
            for note in range(self._key_start, self._key_end + 1):
                if note % 12 in (1, 3, 6, 8, 10):
                    x1 = self._note_to_x(note)
                    x2 = self._note_to_x(note + 1)
                    p.fillRect(QRectF(x1, 0, x2 - x1, h), QColor(0, 0, 0, 25))

            # Velocity grid lines
            for vel in range(0, 128, 16):
                y = self._vel_to_y(vel)
                p.setPen(QPen(QColor("#2a2a44"), 1))
                p.drawLine(0, int(y), w, int(y))

            # Draw zones
            for zone in self._map.zones:
                self._draw_zone(p, zone)

            p.end()
        except Exception:
            pass

    def _draw_zone(self, p: QPainter, zone: SampleZone) -> None:
        x1 = self._note_to_x(zone.key_low)
        x2 = self._note_to_x(zone.key_high + 1)
        y1 = self._vel_to_y(zone.velocity_high + 1)
        y2 = self._vel_to_y(zone.velocity_low)

        color = QColor(zone.color)
        is_selected = zone.zone_id == self._selected_zone_id
        is_hovered = zone.zone_id == self._hovered_zone_id

        # Fill
        fill_color = QColor(color)
        fill_color.setAlpha(80 if not is_selected else 120)
        p.fillRect(QRectF(x1, y1, x2 - x1, y2 - y1), fill_color)

        # Border
        border_width = 2 if is_selected else (1.5 if is_hovered else 1)
        border_color = QColor(color)
        border_color.setAlpha(255 if is_selected else 180)
        p.setPen(QPen(border_color, border_width))
        p.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

        # Root note marker
        rx = self._note_to_x(zone.root_note)
        rw = self._note_to_x(zone.root_note + 1) - rx
        root_color = QColor(color)
        root_color.setAlpha(160)
        p.fillRect(QRectF(rx, y1, rw, y2 - y1), root_color)

        # Label
        rect = QRectF(x1 + 2, y1 + 2, x2 - x1 - 4, y2 - y1 - 4)
        if rect.width() > 20 and rect.height() > 12:
            p.setPen(QPen(QColor("#ffffff"), 1))
            font = p.font()
            font.setPointSize(7)
            p.setFont(font)
            label = zone.name or midi_note_name(zone.root_note)
            p.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position()
                zone_id, edge = self._hit_test(pos.x(), pos.y())
                if zone_id:
                    self._selected_zone_id = zone_id
                    self.zone_selected.emit(zone_id)
                    if edge:
                        self._dragging = True
                        self._drag_edge = edge
                        self._drag_zone_id = zone_id
                else:
                    self._selected_zone_id = ""
                    self.zone_selected.emit("")
                self.update()
            elif event.button() == Qt.MouseButton.RightButton:
                self._show_context_menu(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        try:
            pos = event.position()
            if self._dragging and self._drag_zone_id:
                zone = self._map.get_zone(self._drag_zone_id)
                if zone:
                    note = max(0, min(127, self._x_to_note(pos.x())))
                    vel = max(0, min(127, self._y_to_vel(pos.y())))
                    if self._drag_edge == "left":
                        zone.key_low = min(note, zone.key_high - 1)
                    elif self._drag_edge == "right":
                        zone.key_high = max(note, zone.key_low + 1)
                    elif self._drag_edge == "top":
                        zone.velocity_high = max(vel, zone.velocity_low + 1)
                    elif self._drag_edge == "bottom":
                        zone.velocity_low = min(vel, zone.velocity_high - 1)
                    self.update()
            else:
                zone_id, edge = self._hit_test(pos.x(), pos.y())
                if edge:
                    if edge in ("left", "right"):
                        self.setCursor(Qt.CursorShape.SizeHorCursor)
                    else:
                        self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif zone_id:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                old_hover = self._hovered_zone_id
                self._hovered_zone_id = zone_id or ""
                if old_hover != self._hovered_zone_id:
                    self.update()
        except Exception:
            pass

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        try:
            if self._dragging and self._drag_zone_id:
                self.zone_resized.emit(self._drag_zone_id)
            self._dragging = False
            self._drag_edge = ""
            self._drag_zone_id = ""
            self.setCursor(Qt.CursorShape.ArrowCursor)
        except Exception:
            pass

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom key range with mouse wheel."""
        try:
            delta = event.angleDelta().y()
            zoom_amount = 4 if delta > 0 else -4
            mid = (self._key_start + self._key_end) // 2
            new_start = max(0, self._key_start + zoom_amount)
            new_end = min(127, self._key_end - zoom_amount)
            if new_end - new_start >= 12:
                self._key_start = new_start
                self._key_end = new_end
                self.update()
        except Exception:
            pass

    def _hit_test(self, mx: float, my: float) -> tuple:
        """Returns (zone_id, edge) or ("", "")."""
        edge_threshold = 6.0
        # Reverse order so topmost zone is selected first
        for zone in reversed(self._map.zones):
            x1 = self._note_to_x(zone.key_low)
            x2 = self._note_to_x(zone.key_high + 1)
            y1 = self._vel_to_y(zone.velocity_high + 1)
            y2 = self._vel_to_y(zone.velocity_low)

            if x1 <= mx <= x2 and y1 <= my <= y2:
                # Check edges
                if abs(mx - x1) < edge_threshold:
                    return (zone.zone_id, "left")
                if abs(mx - x2) < edge_threshold:
                    return (zone.zone_id, "right")
                if abs(my - y1) < edge_threshold:
                    return (zone.zone_id, "top")
                if abs(my - y2) < edge_threshold:
                    return (zone.zone_id, "bottom")
                return (zone.zone_id, "")
        return ("", "")

    def _show_context_menu(self, event: QMouseEvent) -> None:
        """Context menu on right click."""
        try:
            pos = event.position()
            note = max(0, min(127, self._x_to_note(pos.x())))
            vel = max(0, min(127, self._y_to_vel(pos.y())))

            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background: #2a2a3e; color: #ddd; }")

            zone_id, _ = self._hit_test(pos.x(), pos.y())
            if zone_id:
                zone = self._map.get_zone(zone_id)
                if zone:
                    act_dup = menu.addAction(f"Duplicate '{zone.name or 'Zone'}'")
                    act_dup.triggered.connect(lambda: self._duplicate_zone(zone_id))
                    act_del = menu.addAction(f"Delete '{zone.name or 'Zone'}'")
                    act_del.triggered.connect(lambda: self._delete_zone(zone_id))
                    menu.addSeparator()

            act_add = menu.addAction(f"Add Zone at {midi_note_name(note)} vel={vel}")
            act_add.triggered.connect(lambda: self._add_zone_at(note, vel))

            menu.exec(event.globalPosition().toPoint())
        except Exception:
            pass

    def _add_zone_at(self, note: int, vel: int) -> None:
        """Add an empty zone at the given note/velocity."""
        zone = SampleZone(
            name=f"Zone {midi_note_name(note)}",
            root_note=note,
            key_low=max(0, note - 2),
            key_high=min(127, note + 2),
            velocity_low=max(0, vel - 30),
            velocity_high=min(127, vel + 30),
            color=next_zone_color(len(self._map.zones)),
        )
        self._map.add_zone(zone)
        self._selected_zone_id = zone.zone_id
        self.zone_selected.emit(zone.zone_id)
        self.update()

    def _duplicate_zone(self, zone_id: str) -> None:
        new = self._map.duplicate_zone(zone_id)
        if new:
            self._selected_zone_id = new.zone_id
            self.zone_selected.emit(new.zone_id)
            self.update()

    def _delete_zone(self, zone_id: str) -> None:
        self._map.remove_zone(zone_id)
        if self._selected_zone_id == zone_id:
            self._selected_zone_id = ""
            self.zone_selected.emit("")
        self.update()

    # ---- Drag & Drop ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        try:
            md = event.mimeData()
            if md and md.hasUrls():
                for u in md.urls():
                    if Path(u.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
                        event.acceptProposedAction()
                        return
            event.ignore()
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    def dragMoveEvent(self, event) -> None:
        try:
            event.acceptProposedAction()
        except Exception:
            pass

    def dropEvent(self, event: QDropEvent) -> None:
        try:
            md = event.mimeData()
            if not (md and md.hasUrls()):
                event.ignore()
                return
            files = []
            for u in md.urls():
                fp = u.toLocalFile()
                if Path(fp).suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(fp)
            if files:
                pos = event.position()
                note = max(0, min(127, self._x_to_note(pos.x())))
                vel = max(0, min(127, self._y_to_vel(pos.y())))
                self.drop_files.emit(files, note, vel)
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass


class ZoneInspector(QWidget):
    """Inspector panel for editing properties of the selected zone."""

    zone_changed = pyqtSignal(str)  # zone_id

    def __init__(self, sample_map: MultiSampleMap, parent: QWidget = None):
        super().__init__(parent)
        self._map = sample_map
        self._current_zone_id: str = ""
        self._updating: bool = False
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.lbl_title = QLabel("No Zone Selected")
        self.lbl_title.setStyleSheet("color:#e0e0e0;font-weight:bold;font-size:10px;")
        root.addWidget(self.lbl_title)

        # Tabs for different sections
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:1px solid #333; background:#1e1e2e; }
            QTabBar::tab { background:#252535; color:#aaa; padding:4px 8px; min-width:50px; }
            QTabBar::tab:selected { background:#333355; color:#fff; }
        """)

        # Tab 1: Mapping
        self.tab_map = QWidget()
        self._build_mapping_tab(self.tab_map)
        self.tabs.addTab(self.tab_map, "Map")

        # Tab 2: Envelope
        self.tab_env = QWidget()
        self._build_env_tab(self.tab_env)
        self.tabs.addTab(self.tab_env, "Env")

        # Tab 3: Filter
        self.tab_filt = QWidget()
        self._build_filter_tab(self.tab_filt)
        self.tabs.addTab(self.tab_filt, "Filter")

        # Tab 4: Modulation
        self.tab_mod = QWidget()
        self._build_mod_tab(self.tab_mod)
        self.tabs.addTab(self.tab_mod, "Mod")

        # Tab 5: Sample / Loop
        self.tab_sample = QWidget()
        self._build_sample_tab(self.tab_sample)
        self.tabs.addTab(self.tab_sample, "Sample")

        root.addWidget(self.tabs, 1)

    def _make_spin(self, lo: int, hi: int, val: int = 0) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setFixedHeight(22)
        s.setStyleSheet("QSpinBox{background:#252535;color:#ccc;border:1px solid #444;}")
        return s

    def _make_dspin(self, lo: float, hi: float, val: float = 0.0,
                    decimals: int = 3, step: float = 0.01) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setDecimals(decimals)
        s.setSingleStep(step)
        s.setFixedHeight(22)
        s.setStyleSheet("QDoubleSpinBox{background:#252535;color:#ccc;border:1px solid #444;}")
        return s

    def _build_mapping_tab(self, parent: QWidget) -> None:
        layout = QGridLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        row = 0

        lbl_s = "color:#999;font-size:8px;"

        # Sample path
        layout.addWidget(QLabel("Sample:"), row, 0)
        self.lbl_sample = QLabel("—")
        self.lbl_sample.setStyleSheet("color:#88aacc;font-size:8px;")
        self.lbl_sample.setWordWrap(True)
        layout.addWidget(self.lbl_sample, row, 1, 1, 2)
        self.btn_load_sample = QPushButton("Load")
        self.btn_load_sample.setFixedHeight(20)
        self.btn_load_sample.setFixedWidth(50)
        self.btn_load_sample.clicked.connect(self._load_sample_for_zone)
        layout.addWidget(self.btn_load_sample, row, 3)
        row += 1

        # Key range
        lbl = QLabel("Key Range:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_key_low = self._make_spin(0, 127, 0)
        self.sp_key_high = self._make_spin(0, 127, 127)
        layout.addWidget(self.sp_key_low, row, 1)
        layout.addWidget(QLabel("–"), row, 2)
        layout.addWidget(self.sp_key_high, row, 3)
        row += 1

        # Root note
        lbl = QLabel("Root Note:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_root = self._make_spin(0, 127, 60)
        layout.addWidget(self.sp_root, row, 1)
        row += 1

        # Velocity range
        lbl = QLabel("Velocity:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_vel_low = self._make_spin(0, 127, 0)
        self.sp_vel_high = self._make_spin(0, 127, 127)
        layout.addWidget(self.sp_vel_low, row, 1)
        layout.addWidget(QLabel("–"), row, 2)
        layout.addWidget(self.sp_vel_high, row, 3)
        row += 1

        # Gain + Pan
        lbl = QLabel("Gain:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_gain = self._make_dspin(0.0, 2.0, 0.8, 2, 0.05)
        layout.addWidget(self.sp_gain, row, 1)
        lbl = QLabel("Pan:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 2)
        self.sp_pan = self._make_dspin(-1.0, 1.0, 0.0, 2, 0.05)
        layout.addWidget(self.sp_pan, row, 3)
        row += 1

        # Tune
        lbl = QLabel("Tune Semi:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_tune_semi = self._make_dspin(-24.0, 24.0, 0.0, 1, 1.0)
        layout.addWidget(self.sp_tune_semi, row, 1)
        lbl = QLabel("Cents:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 2)
        self.sp_tune_cents = self._make_dspin(-100.0, 100.0, 0.0, 1, 1.0)
        layout.addWidget(self.sp_tune_cents, row, 3)
        row += 1

        # RR Group
        lbl = QLabel("RR Group:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_rr = self._make_spin(0, 16, 0)
        layout.addWidget(self.sp_rr, row, 1)
        row += 1

        layout.setRowStretch(row, 1)

        # Wire
        for sp, attr in [
            (self.sp_key_low, "key_low"), (self.sp_key_high, "key_high"),
            (self.sp_root, "root_note"), (self.sp_vel_low, "velocity_low"),
            (self.sp_vel_high, "velocity_high"), (self.sp_rr, "rr_group"),
        ]:
            sp.valueChanged.connect(lambda v, a=attr: self._set_zone_int(a, v))
        for sp, attr in [
            (self.sp_gain, "gain"), (self.sp_pan, "pan"),
            (self.sp_tune_semi, "tune_semitones"), (self.sp_tune_cents, "tune_cents"),
        ]:
            sp.valueChanged.connect(lambda v, a=attr: self._set_zone_float(a, v))

    def _build_env_tab(self, parent: QWidget) -> None:
        layout = QGridLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        lbl_s = "color:#999;font-size:8px;"
        row = 0

        layout.addWidget(QLabel("Amp Envelope"), row, 0, 1, 4)
        row += 1

        self.sp_amp_a = self._make_dspin(0.001, 5.0, 0.005, 3, 0.005)
        self.sp_amp_h = self._make_dspin(0.0, 5.0, 0.0, 3, 0.01)
        self.sp_amp_d = self._make_dspin(0.001, 5.0, 0.15, 3, 0.01)
        self.sp_amp_s = self._make_dspin(0.0, 1.0, 1.0, 2, 0.05)
        self.sp_amp_r = self._make_dspin(0.001, 10.0, 0.20, 3, 0.01)

        for lbl_text, sp in [("A:", self.sp_amp_a), ("H:", self.sp_amp_h),
                              ("D:", self.sp_amp_d), ("S:", self.sp_amp_s),
                              ("R:", self.sp_amp_r)]:
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(lbl_s)
            layout.addWidget(lbl, row, 0)
            layout.addWidget(sp, row, 1, 1, 3)
            row += 1

        # Wire
        self.sp_amp_a.valueChanged.connect(lambda v: self._set_env("amp_envelope", "attack", v))
        self.sp_amp_h.valueChanged.connect(lambda v: self._set_env("amp_envelope", "hold", v))
        self.sp_amp_d.valueChanged.connect(lambda v: self._set_env("amp_envelope", "decay", v))
        self.sp_amp_s.valueChanged.connect(lambda v: self._set_env("amp_envelope", "sustain", v))
        self.sp_amp_r.valueChanged.connect(lambda v: self._set_env("amp_envelope", "release", v))

        layout.setRowStretch(row, 1)

    def _build_filter_tab(self, parent: QWidget) -> None:
        layout = QGridLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        lbl_s = "color:#999;font-size:8px;"
        row = 0

        lbl = QLabel("Type:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.cb_filt_type = QComboBox()
        self.cb_filt_type.addItems(["off", "lp", "hp", "bp"])
        self.cb_filt_type.setFixedHeight(22)
        layout.addWidget(self.cb_filt_type, row, 1, 1, 3)
        row += 1

        lbl = QLabel("Cutoff:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_filt_cutoff = self._make_dspin(20.0, 20000.0, 8000.0, 0, 100.0)
        layout.addWidget(self.sp_filt_cutoff, row, 1, 1, 3)
        row += 1

        lbl = QLabel("Reso:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_filt_reso = self._make_dspin(0.25, 12.0, 0.707, 2, 0.1)
        layout.addWidget(self.sp_filt_reso, row, 1, 1, 3)
        row += 1

        lbl = QLabel("Env Amt:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_filt_env = self._make_dspin(-1.0, 1.0, 0.0, 2, 0.05)
        layout.addWidget(self.sp_filt_env, row, 1, 1, 3)
        row += 1

        # Wire
        self.cb_filt_type.currentTextChanged.connect(
            lambda t: self._set_filter_attr("filter_type", t))
        self.sp_filt_cutoff.valueChanged.connect(
            lambda v: self._set_filter_attr("cutoff_hz", v))
        self.sp_filt_reso.valueChanged.connect(
            lambda v: self._set_filter_attr("resonance", v))
        self.sp_filt_env.valueChanged.connect(
            lambda v: self._set_filter_attr("env_amount", v))

        layout.setRowStretch(row, 1)

    def _build_mod_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # LFO 1
        grp1 = QGroupBox("LFO 1")
        grp1.setStyleSheet("QGroupBox{color:#aaa;font-size:8px;border:1px solid #444;margin-top:8px;}"
                           "QGroupBox::title{padding:0 4px;}")
        g1 = QGridLayout(grp1)
        g1.setSpacing(2)
        g1.addWidget(QLabel("Rate:"), 0, 0)
        self.sp_lfo1_rate = self._make_dspin(0.01, 50.0, 1.0, 2, 0.1)
        g1.addWidget(self.sp_lfo1_rate, 0, 1)
        g1.addWidget(QLabel("Shape:"), 0, 2)
        self.cb_lfo1_shape = QComboBox()
        self.cb_lfo1_shape.addItems(["sine", "triangle", "square", "saw", "random"])
        self.cb_lfo1_shape.setFixedHeight(22)
        g1.addWidget(self.cb_lfo1_shape, 0, 3)
        layout.addWidget(grp1)

        # Mod Slots
        grp_mod = QGroupBox("Mod Matrix (4 slots)")
        grp_mod.setStyleSheet("QGroupBox{color:#aaa;font-size:8px;border:1px solid #444;margin-top:8px;}"
                              "QGroupBox::title{padding:0 4px;}")
        gm = QGridLayout(grp_mod)
        gm.setSpacing(2)

        sources = ["none", "lfo1", "lfo2", "env_amp", "env_filter", "velocity", "key_track"]
        dests = ["none", "pitch", "filter_cutoff", "amp", "pan"]

        self._mod_combos: list = []
        for i in range(4):
            lbl = QLabel(f"#{i+1}")
            lbl.setStyleSheet("color:#888;font-size:7px;")
            gm.addWidget(lbl, i, 0)
            cb_src = QComboBox()
            cb_src.addItems(sources)
            cb_src.setFixedHeight(20)
            gm.addWidget(cb_src, i, 1)
            gm.addWidget(QLabel("→"), i, 2)
            cb_dst = QComboBox()
            cb_dst.addItems(dests)
            cb_dst.setFixedHeight(20)
            gm.addWidget(cb_dst, i, 3)
            sp_amt = self._make_dspin(-1.0, 1.0, 0.0, 2, 0.05)
            gm.addWidget(sp_amt, i, 4)
            self._mod_combos.append((cb_src, cb_dst, sp_amt))

            idx = i
            cb_src.currentTextChanged.connect(lambda t, ii=idx: self._set_mod_slot(ii, "source", t))
            cb_dst.currentTextChanged.connect(lambda t, ii=idx: self._set_mod_slot(ii, "destination", t))
            sp_amt.valueChanged.connect(lambda v, ii=idx: self._set_mod_slot(ii, "amount", v))

        layout.addWidget(grp_mod)

        # Wire LFO
        self.sp_lfo1_rate.valueChanged.connect(lambda v: self._set_lfo("lfo1", "rate_hz", v))
        self.cb_lfo1_shape.currentTextChanged.connect(lambda t: self._set_lfo("lfo1", "shape", t))

        layout.addStretch(1)

    def _build_sample_tab(self, parent: QWidget) -> None:
        layout = QGridLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        lbl_s = "color:#999;font-size:8px;"
        row = 0

        lbl = QLabel("Start:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_sample_start = self._make_dspin(0.0, 1.0, 0.0, 3, 0.01)
        layout.addWidget(self.sp_sample_start, row, 1, 1, 3)
        row += 1

        lbl = QLabel("End:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_sample_end = self._make_dspin(0.0, 1.0, 1.0, 3, 0.01)
        layout.addWidget(self.sp_sample_end, row, 1, 1, 3)
        row += 1

        self.chk_loop = QCheckBox("Loop Enabled")
        self.chk_loop.setStyleSheet("color:#aaa;font-size:8px;")
        layout.addWidget(self.chk_loop, row, 0, 1, 4)
        row += 1

        lbl = QLabel("Loop Start:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_loop_start = self._make_dspin(0.0, 1.0, 0.0, 3, 0.01)
        layout.addWidget(self.sp_loop_start, row, 1, 1, 3)
        row += 1

        lbl = QLabel("Loop End:")
        lbl.setStyleSheet(lbl_s)
        layout.addWidget(lbl, row, 0)
        self.sp_loop_end = self._make_dspin(0.0, 1.0, 1.0, 3, 0.01)
        layout.addWidget(self.sp_loop_end, row, 1, 1, 3)
        row += 1

        # Wire
        self.sp_sample_start.valueChanged.connect(lambda v: self._set_zone_float("sample_start", v))
        self.sp_sample_end.valueChanged.connect(lambda v: self._set_zone_float("sample_end", v))
        self.chk_loop.toggled.connect(self._toggle_loop)
        self.sp_loop_start.valueChanged.connect(self._loop_start_changed)
        self.sp_loop_end.valueChanged.connect(self._loop_end_changed)

        layout.setRowStretch(row, 1)

    # ---- Zone property setters ----

    def _get_zone(self) -> Optional[SampleZone]:
        if not self._current_zone_id:
            return None
        return self._map.get_zone(self._current_zone_id)

    def _set_zone_int(self, attr: str, value: int) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            setattr(zone, attr, int(value))
            self.zone_changed.emit(zone.zone_id)

    def _set_zone_float(self, attr: str, value: float) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            setattr(zone, attr, float(value))
            self.zone_changed.emit(zone.zone_id)

    def _set_env(self, env_attr: str, param: str, value: float) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            env = getattr(zone, env_attr, None)
            if env:
                setattr(env, param, float(value))
                self.zone_changed.emit(zone.zone_id)

    def _set_filter_attr(self, attr: str, value) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            if isinstance(value, str):
                setattr(zone.filter, attr, value)
            else:
                setattr(zone.filter, attr, float(value))
            self.zone_changed.emit(zone.zone_id)

    def _set_lfo(self, lfo_name: str, attr: str, value) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            lfo = getattr(zone, lfo_name, None)
            if lfo:
                if isinstance(value, str):
                    setattr(lfo, attr, value)
                else:
                    setattr(lfo, attr, float(value))
                self.zone_changed.emit(zone.zone_id)

    def _set_mod_slot(self, idx: int, attr: str, value) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone and idx < len(zone.mod_slots):
            if isinstance(value, str):
                setattr(zone.mod_slots[idx], attr, value)
            else:
                setattr(zone.mod_slots[idx], attr, float(value))
            self.zone_changed.emit(zone.zone_id)

    def _toggle_loop(self, checked: bool) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            zone.loop.enabled = bool(checked)
            self.zone_changed.emit(zone.zone_id)

    def _loop_start_changed(self, v: float) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            zone.loop.start_norm = float(v)
            self.zone_changed.emit(zone.zone_id)

    def _loop_end_changed(self, v: float) -> None:
        if self._updating:
            return
        zone = self._get_zone()
        if zone:
            zone.loop.end_norm = float(v)
            self.zone_changed.emit(zone.zone_id)

    def _load_sample_for_zone(self) -> None:
        zone = self._get_zone()
        if not zone:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Sample", "", _AUDIO_FILTER)
        if path:
            zone.sample_path = path
            zone.name = Path(path).stem
            self.lbl_sample.setText(Path(path).name)
            self.zone_changed.emit(zone.zone_id)

    # ---- Update from selection ----

    def set_zone(self, zone_id: str) -> None:
        """Load zone properties into inspector."""
        self._current_zone_id = zone_id
        zone = self._get_zone()
        if not zone:
            self.lbl_title.setText("No Zone Selected")
            return

        self._updating = True
        try:
            self.lbl_title.setText(f"Zone: {zone.name or zone.zone_id[:8]}")
            self.lbl_sample.setText(Path(zone.sample_path).name if zone.sample_path else "—")

            self.sp_key_low.setValue(zone.key_low)
            self.sp_key_high.setValue(zone.key_high)
            self.sp_root.setValue(zone.root_note)
            self.sp_vel_low.setValue(zone.velocity_low)
            self.sp_vel_high.setValue(zone.velocity_high)
            self.sp_gain.setValue(zone.gain)
            self.sp_pan.setValue(zone.pan)
            self.sp_tune_semi.setValue(zone.tune_semitones)
            self.sp_tune_cents.setValue(zone.tune_cents)
            self.sp_rr.setValue(zone.rr_group)

            # Envelope
            env = zone.amp_envelope
            self.sp_amp_a.setValue(env.attack)
            self.sp_amp_h.setValue(env.hold)
            self.sp_amp_d.setValue(env.decay)
            self.sp_amp_s.setValue(env.sustain)
            self.sp_amp_r.setValue(env.release)

            # Filter
            idx = self.cb_filt_type.findText(zone.filter.filter_type)
            if idx >= 0:
                self.cb_filt_type.setCurrentIndex(idx)
            self.sp_filt_cutoff.setValue(zone.filter.cutoff_hz)
            self.sp_filt_reso.setValue(zone.filter.resonance)
            self.sp_filt_env.setValue(zone.filter.env_amount)

            # LFO
            self.sp_lfo1_rate.setValue(zone.lfo1.rate_hz)
            idx = self.cb_lfo1_shape.findText(zone.lfo1.shape)
            if idx >= 0:
                self.cb_lfo1_shape.setCurrentIndex(idx)

            # Mod matrix
            for i, (cb_src, cb_dst, sp_amt) in enumerate(self._mod_combos):
                if i < len(zone.mod_slots):
                    slot = zone.mod_slots[i]
                    idx = cb_src.findText(slot.source)
                    if idx >= 0:
                        cb_src.setCurrentIndex(idx)
                    idx = cb_dst.findText(slot.destination)
                    if idx >= 0:
                        cb_dst.setCurrentIndex(idx)
                    sp_amt.setValue(slot.amount)

            # Sample
            self.sp_sample_start.setValue(zone.sample_start)
            self.sp_sample_end.setValue(zone.sample_end)
            self.chk_loop.setChecked(zone.loop.enabled)
            self.sp_loop_start.setValue(zone.loop.start_norm)
            self.sp_loop_end.setValue(zone.loop.end_norm)
        finally:
            self._updating = False


class MultiSampleEditorWidget(QWidget):
    """Complete Multi-Sample Mapping Editor.

    Combines ZoneMapCanvas + ZoneInspector + toolbar with auto-mapping buttons.
    """

    map_changed = pyqtSignal()  # emitted on any change

    def __init__(self, sample_map: MultiSampleMap = None, parent: QWidget = None):
        super().__init__(parent)
        self._map = sample_map or MultiSampleMap()
        self.setObjectName("multiSampleEditor")
        self._build_ui()
        self._wire()

    def set_map(self, sample_map: MultiSampleMap) -> None:
        self._map = sample_map
        self.canvas.set_map(sample_map)
        self.inspector._map = sample_map
        self.canvas.update()

    def get_map(self) -> MultiSampleMap:
        return self._map

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(4)

        self.btn_add_zone = QPushButton("+ Zone")
        self.btn_add_zone.setFixedHeight(24)
        self.btn_add_zone.setToolTip("Add empty zone")
        tb.addWidget(self.btn_add_zone)

        self.btn_load_samples = QPushButton("Load Samples…")
        self.btn_load_samples.setFixedHeight(24)
        tb.addWidget(self.btn_load_samples)

        self.cb_auto_map = QComboBox()
        self.cb_auto_map.addItems(["Auto-Map: Chromatic", "Auto-Map: Drum",
                                   "Auto-Map: Velocity Layers", "Auto-Map: Round Robin"])
        self.cb_auto_map.setFixedHeight(24)
        tb.addWidget(self.cb_auto_map)

        self.btn_auto_map = QPushButton("Apply")
        self.btn_auto_map.setFixedHeight(24)
        self.btn_auto_map.setFixedWidth(60)
        tb.addWidget(self.btn_auto_map)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.setStyleSheet("color:#cc4444;")
        tb.addWidget(self.btn_clear)

        self.lbl_info = QLabel("0 zones")
        self.lbl_info.setStyleSheet("color:#888;font-size:8px;")
        tb.addWidget(self.lbl_info)

        tb.addStretch(1)
        root.addLayout(tb)

        # Main area: Canvas + Inspector
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle{background:#333;width:3px;}")

        self.canvas = ZoneMapCanvas(self._map)
        splitter.addWidget(self.canvas)

        self.inspector = ZoneInspector(self._map)
        splitter.addWidget(self.inspector)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

    def _wire(self) -> None:
        self.canvas.zone_selected.connect(self._on_zone_selected)
        self.canvas.zone_resized.connect(self._on_zone_changed)
        self.canvas.drop_files.connect(self._on_drop_files)
        self.inspector.zone_changed.connect(self._on_zone_changed)

        self.btn_add_zone.clicked.connect(self._add_empty_zone)
        self.btn_load_samples.clicked.connect(self._load_samples_dialog)
        self.btn_auto_map.clicked.connect(self._apply_auto_map)
        self.btn_clear.clicked.connect(self._clear_all)

    def _on_zone_selected(self, zone_id: str) -> None:
        self.inspector.set_zone(zone_id)

    def _on_zone_changed(self, zone_id: str) -> None:
        self.canvas.update()
        self._update_info()
        self.map_changed.emit()

    def _update_info(self) -> None:
        n = len(self._map.zones)
        self.lbl_info.setText(f"{n} zone{'s' if n != 1 else ''}")

    def _add_empty_zone(self) -> None:
        zone = SampleZone(
            name=f"Zone {len(self._map.zones) + 1}",
            root_note=60,
            key_low=48,
            key_high=72,
            color=next_zone_color(len(self._map.zones)),
        )
        self._map.add_zone(zone)
        self.canvas.set_selected(zone.zone_id)
        self.inspector.set_zone(zone.zone_id)
        self.canvas.update()
        self._update_info()
        self.map_changed.emit()

    def _load_samples_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Load Samples", "", _AUDIO_FILTER)
        if files:
            self._import_files(files)

    def _import_files(self, files: List[str], start_note: int = 60) -> None:
        """Import files using currently selected auto-map mode."""
        from .auto_mapping import (
            auto_map_chromatic, auto_map_drum,
            auto_map_velocity_layers, auto_map_round_robin,
        )
        mode = self.cb_auto_map.currentIndex()
        if mode == 0:
            new_map = auto_map_chromatic(files, root_note=start_note)
        elif mode == 1:
            new_map = auto_map_drum(files)
        elif mode == 2:
            new_map = auto_map_velocity_layers(files, note=start_note)
        elif mode == 3:
            new_map = auto_map_round_robin(files, note=start_note)
        else:
            new_map = auto_map_chromatic(files, root_note=start_note)

        # Merge into existing map
        for zone in new_map.zones:
            zone.color = next_zone_color(len(self._map.zones))
            self._map.add_zone(zone)

        self.canvas.update()
        self._update_info()
        self.map_changed.emit()

    def _apply_auto_map(self) -> None:
        """Re-apply auto-map to existing zones' sample files."""
        files = [z.sample_path for z in self._map.zones if z.sample_path]
        if not files:
            return
        self._map.clear()
        self._import_files(files)

    def _clear_all(self) -> None:
        self._map.clear()
        self.canvas.set_selected("")
        self.inspector.set_zone("")
        self.canvas.update()
        self._update_info()
        self.map_changed.emit()

    def _on_drop_files(self, files: list, note: int, vel: int) -> None:
        """Handle files dropped onto the canvas."""
        if len(files) == 1:
            # Single file: create zone at drop location
            zone = SampleZone(
                name=Path(files[0]).stem,
                sample_path=files[0],
                root_note=note,
                key_low=max(0, note - 2),
                key_high=min(127, note + 2),
                velocity_low=max(0, vel - 30),
                velocity_high=min(127, vel + 30),
                color=next_zone_color(len(self._map.zones)),
            )
            self._map.add_zone(zone)
            self.canvas.set_selected(zone.zone_id)
            self.inspector.set_zone(zone.zone_id)
            self.canvas.update()
            self._update_info()
            self.map_changed.emit()
        else:
            # Multiple files: use auto-map
            self._import_files(files, start_note=note)


__all__ = ["MultiSampleEditorWidget", "ZoneMapCanvas", "ZoneInspector"]
