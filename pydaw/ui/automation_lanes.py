"""Automation lanes (v0.0.15).

v0.0.15:
- Interactive lane editor (placeholder, but editable):
  - Click to add point
  - Drag to move point
  - Right-click to delete nearest point
- Per-track automation mode: Off / Read / Write
- Parameter selection: Volume / Pan (placeholder params)
- Data persists into Project.automation_lanes (dict)

Schema:
  automation_lanes[track_id][param] = [{"beat": float, "value": float}, ...]
"""

from __future__ import annotations

import math
from typing import Dict, Any, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QToolButton,
    QMenu,
)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush

from pydaw.services.project_service import ProjectService


def _snap_beats_from_div(division: str) -> float:
    mapping = {
        "1/4": 1.0,
        "1/8": 0.5,
        "1/16": 0.25,
        "1/32": 0.125,
        "1/64": 0.0625,
    }
    return mapping.get(str(division), 0.25)


class _AutomationCurveEditor(QWidget):
    """Simple editable curve editor.

    X axis is beats in a fixed visible range (placeholder).
    Y axis is 0..1 for volume or -1..1 for pan.
    """

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

        self.track_id: str = ""
        self.param: str = "volume"

        self.total_beats_visible = 64.0  # placeholder range

        # View range (beats) used to keep automation editing in sync with the
        # arranger timeline/zoom. By default we show [0 .. total_beats_visible].
        self._view_start_beat = 0.0
        self._view_end_beat = float(self.total_beats_visible)

        self._drag_idx: Optional[int] = None

    # --- data helpers

    def _get_points(self) -> List[Dict[str, Any]]:
        lanes = self.project.ctx.project.automation_lanes or {}
        tlanes = lanes.get(self.track_id, {}) if self.track_id else {}
        pts = list(tlanes.get(self.param, []))
        # normalize
        out = []
        for p in pts:
            try:
                out.append({"beat": float(p.get("beat", 0.0)), "value": float(p.get("value", 0.0))})
            except Exception:
                continue
        out.sort(key=lambda p: p["beat"])
        return out

    def _set_points(self, pts: List[Dict[str, Any]]) -> None:
        lanes = self.project.ctx.project.automation_lanes or {}
        tlanes = dict(lanes.get(self.track_id, {}) if self.track_id else {})
        tlanes[self.param] = pts
        lanes[self.track_id] = tlanes
        self.project.ctx.project.automation_lanes = lanes
        self.project.project_updated.emit()

    # --- coordinate mapping

    def set_view_range(self, start_beat: float, end_beat: float) -> None:
        """Set the visible beat range.

        This is used by MainWindow/Arranger to keep the automation editor
        aligned with the arrangement's current horizontal scroll/zoom.
        """
        s = float(start_beat)
        e = float(end_beat)
        if e <= s:
            return
        self._view_start_beat = max(0.0, s)
        # Ensure a non-zero span to avoid division by zero.
        self._view_end_beat = max(self._view_start_beat + 0.25, e)
        self.update()

    def _px_to_beat(self, x: float) -> float:
        w = max(1.0, float(self.width() - 16))
        span = max(1e-9, float(self._view_end_beat - self._view_start_beat))
        b = float(self._view_start_beat) + ((x - 8.0) / w) * span
        return max(0.0, b)

    def _beat_to_px(self, beat: float) -> float:
        w = max(1.0, float(self.width() - 16))
        span = max(1e-9, float(self._view_end_beat - self._view_start_beat))
        rel = (float(beat) - float(self._view_start_beat)) / span
        return 8.0 + rel * w

    def _px_to_value(self, y: float) -> float:
        h = max(1.0, float(self.height() - 16))
        t = 1.0 - max(0.0, min(1.0, (y - 8.0) / h))
        if self.param == "pan":
            return (t * 2.0) - 1.0
        return t

    def _value_to_px(self, value: float) -> float:
        h = max(1.0, float(self.height() - 16))
        if self.param == "pan":
            t = (float(value) + 1.0) / 2.0
        else:
            t = float(value)
        t = max(0.0, min(1.0, t))
        return 8.0 + (1.0 - t) * h

    def _hit_test(self, pos: QPointF, pts: List[Dict[str, Any]]) -> Optional[int]:
        for i, p in enumerate(pts):
            x = self._beat_to_px(p["beat"])
            y = self._value_to_px(p["value"])
            r = QRectF(x - 6, y - 6, 12, 12)
            if r.contains(pos):
                return i
        return None

    # --- events

    def mousePressEvent(self, event):  # noqa: ANN001
        if not self.track_id:
            return
        pts = self._get_points()
        pos = event.position()

        if event.button() == Qt.MouseButton.RightButton:
            idx = self._hit_test(pos, pts)
            if idx is None and pts:
                # delete nearest
                best = None
                best_d = 1e9
                for i, p in enumerate(pts):
                    dx = self._beat_to_px(p["beat"]) - pos.x()
                    dy = self._value_to_px(p["value"]) - pos.y()
                    d = dx*dx + dy*dy
                    if d < best_d:
                        best_d = d
                        best = i
                idx = best
            if idx is not None:
                pts.pop(idx)
                self._set_points(pts)
                self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_test(pos, pts)
            if idx is not None:
                self._drag_idx = idx
                return

            # add point
            beat = self._px_to_beat(pos.x())
            snap = _snap_beats_from_div(getattr(self.project.ctx.project, "snap_division", "1/16"))
            if snap > 0:
                beat = round(beat / snap) * snap
            val = self._px_to_value(pos.y())

            pts.append({"beat": float(beat), "value": float(val)})
            pts.sort(key=lambda p: p["beat"])
            self._set_points(pts)
            self.update()
            return

    def mouseMoveEvent(self, event):  # noqa: ANN001
        if self._drag_idx is None or not self.track_id:
            return
        pts = self._get_points()
        if not (0 <= self._drag_idx < len(pts)):
            self._drag_idx = None
            return
        pos = event.position()
        beat = self._px_to_beat(pos.x())
        snap = _snap_beats_from_div(getattr(self.project.ctx.project, "snap_division", "1/16"))
        if snap > 0:
            beat = round(beat / snap) * snap
        val = self._px_to_value(pos.y())

        pts[self._drag_idx]["beat"] = float(beat)
        pts[self._drag_idx]["value"] = float(val)
        pts.sort(key=lambda p: p["beat"])
        # drag index changes after sort; just stop dragging if order changed heavily
        self._set_points(pts)
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        self._drag_idx = None

    # --- paint

    def paintEvent(self, event):  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().window())

        # grid
        p.setPen(QPen(self.palette().mid().color()))
        for x in range(8, self.width(), 40):
            p.drawLine(x, 8, x, self.height() - 8)
        for y in range(8, self.height(), 20):
            p.drawLine(8, y, self.width() - 8, y)

        # border
        p.setPen(QPen(self.palette().dark().color()))
        p.drawRect(self.rect().adjusted(6, 6, -6, -6))

        if not self.track_id:
            p.setPen(QPen(self.palette().text().color()))
            p.drawText(12, 22, "Keine Spur ausgewählt.")
            p.end()
            return

        pts = self._get_points()

        # curve
        if len(pts) >= 2:
            p.setPen(QPen(self.palette().highlight().color()))
            for a, b in zip(pts[:-1], pts[1:]):
                p.drawLine(
                    int(self._beat_to_px(a["beat"])),
                    int(self._value_to_px(a["value"])),
                    int(self._beat_to_px(b["beat"])),
                    int(self._value_to_px(b["value"])),
                )

        # points
        p.setPen(QPen(self.palette().text().color()))
        p.setBrush(QBrush(self.palette().highlight().color()))
        for pt in pts:
            x = self._beat_to_px(pt["beat"])
            y = self._value_to_px(pt["value"])
            p.drawEllipse(QPointF(x, y), 4.0, 4.0)

        p.setPen(QPen(self.palette().text().color()))
        p.drawText(12, 22, f"Automation: {self.param} | Punkte: {len(pts)} | Rechtsklick löscht")
        p.end()


class AutomationLanePanel(QWidget):
    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        left = QVBoxLayout()
        left.addWidget(QLabel("Automation Lanes"))

        self.lst = QListWidget()
        left.addWidget(self.lst, 1)

        # track mode
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["off", "read", "write", "touch", "latch"])
        left.addWidget(QLabel("Mode:"))
        left.addWidget(self.cmb_mode)

        # param
        self.cmb_param = QComboBox()
        self.cmb_param.addItems(["volume", "pan"])
        left.addWidget(QLabel("Param:"))
        left.addWidget(self.cmb_param)

        # clear action
        self.btn_more = QToolButton()
        self.btn_more.setText("⋯")
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_more)
        a_clear = menu.addAction("Lane leeren")
        self.btn_more.setMenu(menu)
        left.addWidget(self.btn_more)

        layout.addLayout(left, 1)

        right = QVBoxLayout()
        self.lbl = QLabel("Lane Editor")
        right.addWidget(self.lbl)
        self.editor = _AutomationCurveEditor(project)
        right.addWidget(self.editor, 1)
        layout.addLayout(right, 3)

        self.lst.currentItemChanged.connect(self._on_track_selected)
        self.cmb_mode.currentTextChanged.connect(self._on_mode_changed)
        self.cmb_param.currentTextChanged.connect(self._on_param_changed)
        a_clear.triggered.connect(self._clear_lane)

        self._refreshing = False
        self.project.project_updated.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        cur_tid = self._selected_track_id()
        self._refreshing = True
        self.lst.blockSignals(True)
        self.lst.clear()
        for t in self.project.ctx.project.tracks:
            it = QListWidgetItem(f"{t.name} [{t.kind}]")
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            self.lst.addItem(it)
            if cur_tid and t.id == cur_tid:
                self.lst.setCurrentItem(it)
        self.lst.blockSignals(False)
        self._refreshing = False

        # update editor and mode
        tid = self._selected_track_id()
        self.editor.track_id = tid
        if tid:
            trk = next((t for t in self.project.ctx.project.tracks if t.id == tid), None)
            if trk:
                self.cmb_mode.blockSignals(True)
                self.cmb_mode.setCurrentText(getattr(trk, "automation_mode", "off"))
                self.cmb_mode.blockSignals(False)
        self._on_param_changed(self.cmb_param.currentText())
        self.editor.update()

    def _selected_track_id(self) -> str:
        it = self.lst.currentItem()
        if not it:
            return ""
        return str(it.data(Qt.ItemDataRole.UserRole) or "")

    def _on_track_selected(self, cur, prev):  # noqa: ANN001
        if bool(getattr(self, '_refreshing', False)):
            return
        tid = self._selected_track_id()
        self.editor.track_id = tid
        trk = next((t for t in self.project.ctx.project.tracks if t.id == tid), None)
        if trk:
            self.cmb_mode.blockSignals(True)
            self.cmb_mode.setCurrentText(getattr(trk, "automation_mode", "off"))
            self.cmb_mode.blockSignals(False)
        self.editor.update()

    def _on_mode_changed(self, mode: str) -> None:
        tid = self._selected_track_id()
        if not tid:
            return
        trk = next((t for t in self.project.ctx.project.tracks if t.id == tid), None)
        if not trk:
            return
        trk.automation_mode = str(mode)
        self.project.project_updated.emit()
        self.project.status.emit(f"Automation Mode: {trk.name} = {mode}")

    def _on_param_changed(self, param: str) -> None:
        self.editor.param = str(param)
        self.editor.update()

    def _clear_lane(self) -> None:
        tid = self._selected_track_id()
        if not tid:
            return
        param = str(self.cmb_param.currentText())
        lanes = self.project.ctx.project.automation_lanes or {}
        tlanes = dict(lanes.get(tid, {}))
        tlanes[param] = []
        lanes[tid] = tlanes
        self.project.ctx.project.automation_lanes = lanes
        self.project.project_updated.emit()
        self.editor.update()

    # --- external synchronization ---
    def set_playhead(self, beat: float) -> None:
        self.editor.set_playhead(float(beat))

    def set_view_range(self, start_beat: float, end_beat: float) -> None:
        self.editor.set_view_range(float(start_beat), float(end_beat))
