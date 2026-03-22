"""Notation editor (WIP)

Goal for this stage:
- Provide a *stable* integrated notation view (no subprocess, no heavy port) that behaves like the Piano Roll:
  - Fast, no GUI freeze on tab switch
  - Basic tools: Select / Pencil / Erase
  - Simple staff rendering and note items

This is intentionally minimal and is meant to be iterated into a full notation engine later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QAction
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolButton,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QMenu,
)


class Tool(str, Enum):
    SELECT = "select"
    PENCIL = "pencil"
    ERASE = "erase"


@dataclass
class NoteModel:
    x: float
    y: float
    w: float = 20.0
    h: float = 10.0


class NoteItem(QGraphicsRectItem):
    """Simple note representation."""

    def __init__(self, model: NoteModel):
        super().__init__(QRectF(model.x, model.y, model.w, model.h))
        self.model = model
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)


class StaffView(QGraphicsView):
    request_delete_selected = pyqtSignal()
    request_delete_item = pyqtSignal(object)
    request_add_note = pyqtSignal(QPointF)

    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._tool: Tool = Tool.SELECT

    def set_tool(self, tool: Tool):
        self._tool = tool
        # Rubberband only for select
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == Tool.SELECT
            else QGraphicsView.DragMode.NoDrag
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._tool == Tool.PENCIL:
                self.request_add_note.emit(self.mapToScene(event.pos()))
                event.accept()
                return
            if self._tool == Tool.ERASE:
                item = self.itemAt(event.pos())
                if isinstance(item, NoteItem):
                    self.request_delete_item.emit(item)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_del = QAction("Löschen", self)
        act_del.triggered.connect(lambda: self.request_delete_selected.emit())
        menu.addAction(act_del)
        menu.exec(event.globalPos())


class NotationEditor(QWidget):
    """Lightweight integrated notation editor.

    Later iterations will connect this to the project model (clips/notes) and real engraving.
    """

    def __init__(self, project_service=None, transport=None):
        super().__init__()
        self._project_service = project_service
        self._transport = transport

        self._tool: Tool = Tool.SELECT
        self._notes: List[NoteItem] = []

        self.scene = QGraphicsScene(self)
        self.view = StaffView(self.scene)
        self.view.request_add_note.connect(self._on_add_note)
        self.view.request_delete_selected.connect(self._on_delete_selected)
        self.view.request_delete_item.connect(self._on_delete_item)

        self._build_ui()
        self._draw_staff()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # toolbar (minimal)
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_select = QToolButton()
        self.btn_select.setText("Select")
        self.btn_select.setCheckable(True)

        self.btn_pencil = QToolButton()
        self.btn_pencil.setText("Pencil")
        self.btn_pencil.setCheckable(True)

        self.btn_erase = QToolButton()
        self.btn_erase.setText("Erase")
        self.btn_erase.setCheckable(True)

        self.btn_select.clicked.connect(lambda: self.set_tool(Tool.SELECT))
        self.btn_pencil.clicked.connect(lambda: self.set_tool(Tool.PENCIL))
        self.btn_erase.clicked.connect(lambda: self.set_tool(Tool.ERASE))

        bar.addWidget(self.btn_select)
        bar.addWidget(self.btn_pencil)
        bar.addWidget(self.btn_erase)
        bar.addStretch(1)

        hint = QLabel("Notation (WIP) – stabiler integrierter Editor (kein Experimentell/Subprocess).")
        hint.setStyleSheet("color: #AAAAAA;")
        bar.addWidget(hint)

        root.addLayout(bar)
        root.addWidget(self.view, 1)

        self.set_tool(Tool.SELECT)

    def set_tool(self, tool: Tool):
        self._tool = tool
        self.btn_select.setChecked(tool == Tool.SELECT)
        self.btn_pencil.setChecked(tool == Tool.PENCIL)
        self.btn_erase.setChecked(tool == Tool.ERASE)
        self.view.set_tool(tool)

    # ---------- drawing ----------

    def _draw_staff(self):
        # big canvas to avoid frequent scene resizing
        self.scene.clear()

        width = 5000
        height = 1200

        # background rect (for easy scrolling)
        bg = QGraphicsRectItem(QRectF(0, 0, width, height))
        bg.setPen(QPen(Qt.GlobalColor.transparent))
        self.scene.addItem(bg)

        # staff lines (centered)
        center_y = height / 2
        staff_gap = 12
        pen = QPen(Qt.GlobalColor.darkGray)
        for i in range(5):
            y = center_y + (i - 2) * staff_gap
            self.scene.addLine(0, y, width, y, pen)

        # simple bar/grid lines (visual only)
        grid_pen = QPen(Qt.GlobalColor.gray)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        for x in range(0, width, 100):
            self.scene.addLine(x, 0, x, height, grid_pen)

        # re-add notes
        for n in self._notes:
            self.scene.addItem(n)

        # fit initial view
        self.view.setSceneRect(QRectF(0, 0, width, height))

    def _snap_point(self, p: QPointF) -> QPointF:
        # snap to 10 px grid (x) and staff gap/2 (y)
        x = round(p.x() / 10) * 10
        # approximate to 6 px increments
        y = round(p.y() / 6) * 6
        return QPointF(float(x), float(y))

    # ---------- note ops ----------

    def _on_add_note(self, p: QPointF):
        p = self._snap_point(p)
        model = NoteModel(x=float(p.x()), y=float(p.y()))
        item = NoteItem(model)
        pen = QPen(Qt.GlobalColor.white)
        item.setPen(pen)
        self.scene.addItem(item)
        self._notes.append(item)

    def _on_delete_selected(self):
        for item in list(self.scene.selectedItems()):
            if isinstance(item, NoteItem):
                self._on_delete_item(item)

    def _on_delete_item(self, item):
        try:
            self.scene.removeItem(item)
        except Exception:
            pass
        if item in self._notes:
            self._notes.remove(item)
