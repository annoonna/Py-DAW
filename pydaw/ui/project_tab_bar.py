"""Multi-Project Tab Bar (v0.0.20.87) -- Bitwig-Style project tabs.

Displays open projects as tabs at the top of the main window.
Only the active tab's project uses the audio engine.

Features:
  - Tab per open project (name + dirty indicator colored dot)
  - Middle-click or 'x' button to close tab
  - '+' button for new project
  - Double-click tab to rename
  - Drag tabs to reorder (v0.0.20.78)
  - v0.0.20.79: Dirty indicator as colored dot icon (orange) instead of text bullet
  - v0.0.20.87: Drag-over-tab auto-switch (Bitwig/Ableton-style)
    When dragging tracks/clips over an inactive tab, the tab auto-activates
    after 500ms hover delay so you can drop on that tab's arranger canvas.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QTabBar,
    QToolButton,
    QMenu,
    QInputDialog,
    QMessageBox,
    QFileDialog,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QMouseEvent, QIcon, QPixmap, QPainter, QColor, QBrush

from pydaw.services.project_tab_service import ProjectTabService
from pydaw.ui.cross_project_drag import MIME_CROSS_PROJECT

log = logging.getLogger(__name__)


class DragSwitchTabBar(QTabBar):
    """QTabBar subclass that auto-switches tabs when dragging over them.

    Bitwig/Ableton-style: hover a drag over an inactive tab for 500ms
    and the tab activates automatically so you can drop on the arranger.

    Accepts any drag with MIME_CROSS_PROJECT or file URLs.
    Does NOT consume the drop -- the drop goes to the ArrangerCanvas below.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        # Timer for delayed tab switch (500ms hover)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(500)
        self._hover_timer.timeout.connect(self._activate_hovered_tab)
        self._hover_tab_idx: int = -1

    def _activate_hovered_tab(self) -> None:
        """Called by timer: switch to the tab the user is hovering over."""
        try:
            idx = int(self._hover_tab_idx)
            if idx >= 0 and idx != self.currentIndex() and idx < self.count():
                log.info("DragSwitchTabBar: auto-switching to tab %d", idx)
                self.setCurrentIndex(idx)
        except Exception:
            # Never allow timer slots to raise (PyQt6 may abort on unhandled exceptions).
            try:
                log.exception("DragSwitchTabBar._activate_hovered_tab failed")
            except Exception:
                pass
            log.info("DragSwitchTabBar: auto-switching to tab %d", idx)
            self.setCurrentIndex(idx)

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001
        try:
            md = event.mimeData()
            if md and (md.hasFormat(MIME_CROSS_PROJECT) or md.hasUrls()):
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception:
            log.exception("DragSwitchTabBar.dragEnterEvent failed")
            try:
                event.ignore()
            except Exception:
                pass

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001
        try:
            md = event.mimeData()
            if not md or not (md.hasFormat(MIME_CROSS_PROJECT) or md.hasUrls()):
                event.ignore()
                return

            event.acceptProposedAction()
            pos = event.position().toPoint()
            idx = self.tabAt(pos)

            if idx >= 0 and idx != self.currentIndex():
                # Hovering over a different tab -- start/restart timer
                if idx != self._hover_tab_idx:
                    self._hover_tab_idx = idx
                    self._hover_timer.start()
            else:
                # Hovering over current tab or outside tabs -- cancel timer
                self._hover_timer.stop()
                self._hover_tab_idx = -1
        except Exception:
            log.exception("DragSwitchTabBar.dragMoveEvent failed")

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001
        try:
            self._hover_timer.stop()
            self._hover_tab_idx = -1
        except Exception:
            pass
        try:
            super().dragLeaveEvent(event)
        except Exception:
            pass

    def dropEvent(self, event) -> None:  # noqa: ANN001
        """We don't consume the drop -- ignore so the canvas underneath gets it."""
        try:
            self._hover_timer.stop()
            self._hover_tab_idx = -1
            event.ignore()
        except Exception:
            pass


class ProjectTabBar(QWidget):
    """Compact tab bar for switching between open projects.

    Sits at the top of the MainWindow, above the transport toolbar.
    Emits signals that MainWindow connects to for project switching.

    v0.0.20.79: Dirty state shown as colored dot icon instead of text bullet.
    v0.0.20.87: Uses DragSwitchTabBar for drag-over tab auto-switching.
    """

    # Signals for MainWindow integration
    request_switch_tab = Signal(int)          # tab index
    request_new_project = Signal()            # new empty project
    request_open_project = Signal()           # open file dialog
    request_close_tab = Signal(int)           # tab index
    request_save_tab = Signal(int)            # tab index
    request_save_tab_as = Signal(int)         # tab index
    request_rename_tab = Signal(int, str)     # tab index, new name
    request_rust_badge_clicked = Signal()

    # Cache dirty dot icons so they're only generated once
    _dirty_icon: QIcon | None = None
    _clean_icon: QIcon | None = None

    @classmethod
    def _get_dirty_icon(cls) -> QIcon:
        """Create a small orange dot QIcon for dirty state (cached)."""
        if cls._dirty_icon is None:
            px = QPixmap(12, 12)
            px.fill(QColor(0, 0, 0, 0))  # transparent background
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 160, 40)))  # orange
            p.drawEllipse(2, 2, 8, 8)
            p.end()
            cls._dirty_icon = QIcon(px)
        return cls._dirty_icon

    @classmethod
    def _get_clean_icon(cls) -> QIcon:
        """Empty transparent icon for clean state (cached)."""
        if cls._clean_icon is None:
            px = QPixmap(12, 12)
            px.fill(QColor(0, 0, 0, 0))
            cls._clean_icon = QIcon(px)
        return cls._clean_icon

    def __init__(
        self,
        tab_service: ProjectTabService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = tab_service
        self._setup_ui()
        self._connect_service()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 6, 0)
        layout.setSpacing(4)

        # Tab bar -- v0.0.20.87: DragSwitchTabBar for drag-over auto-switch
        self._tab_bar = DragSwitchTabBar()
        self._tab_bar.setObjectName("projectTabBar")
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setMovable(True)  # v0.0.20.78: drag-reorder enabled
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)

        # Make tabs compact
        self._tab_bar.setStyleSheet("""
            QTabBar::tab {
                background: #2A2A2A;
                color: #AAA;
                border: 1px solid #333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 4px 12px 4px 8px;
                min-width: 80px;
                max-width: 200px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3A3A3A;
                color: #FFF;
                border-color: #555;
            }
            QTabBar::tab:hover:!selected {
                background: #333;
                color: #DDD;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
                padding: 2px;
            }
        """)

        # Signals
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tab_bar.tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self._tab_bar.tabMoved.connect(self._on_tab_moved)

        # Context menu on tabs
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.customContextMenuRequested.connect(self._on_tab_context_menu)

        layout.addWidget(self._tab_bar, 1)

        # '+' button for new project
        self._btn_new = QToolButton()
        self._btn_new.setText("+")
        self._btn_new.setToolTip("Neues Projekt in neuem Tab (Ctrl+T)")
        self._btn_new.setObjectName("projectTabNewBtn")
        self._btn_new.setAutoRaise(True)
        self._btn_new.setFixedSize(28, 24)
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new.setStyleSheet("""
            QToolButton {
                background: #2A2A2A;
                color: #AAA;
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #3A3A3A;
                color: #FFF;
            }
        """)
        self._btn_new.clicked.connect(self.request_new_project.emit)
        layout.addWidget(self._btn_new, 0)

        # Open button
        self._btn_open = QToolButton()
        self._btn_open.setText("\U0001f4c2")
        self._btn_open.setToolTip("Projekt oeffnen in neuem Tab (Ctrl+Shift+O)")
        self._btn_open.setObjectName("projectTabOpenBtn")
        self._btn_open.setAutoRaise(True)
        self._btn_open.setFixedSize(28, 24)
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.setStyleSheet("""
            QToolButton {
                background: #2A2A2A;
                color: #AAA;
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 14px;
            }
            QToolButton:hover {
                background: #3A3A3A;
                color: #FFF;
            }
        """)
        self._btn_open.clicked.connect(self.request_open_project.emit)
        layout.addWidget(self._btn_open, 0)

        # v0.0.20.647: Rust badge moved into the centered tool row branding slot
        # so the project-tab toolbar stays cleaner and the badge is easier to spot.

        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _connect_service(self) -> None:
        """Connect to ProjectTabService signals."""
        self._service.tab_added.connect(self._on_service_tab_added)
        self._service.tab_removed.connect(self._on_service_tab_removed)
        self._service.tab_switched.connect(self._on_service_tab_switched)
        self._service.tab_renamed.connect(self._on_service_tab_renamed)
        self._service.tab_dirty_changed.connect(self._on_service_dirty_changed)

    # --- Service signal handlers ---

    def _on_service_tab_added(self, idx: int) -> None:
        tab = self._service.tab_at(idx)
        if tab:
            label = tab.display_name
            self._tab_bar.blockSignals(True)
            self._tab_bar.insertTab(idx, label)
            # v0.0.20.79: set initial icon
            icon = self._get_dirty_icon() if tab.dirty else self._get_clean_icon()
            self._tab_bar.setTabIcon(idx, icon)
            self._tab_bar.blockSignals(False)

    def _on_service_tab_removed(self, idx: int) -> None:
        self._tab_bar.blockSignals(True)
        self._tab_bar.removeTab(idx)
        self._tab_bar.blockSignals(False)

    def _on_service_tab_switched(self, old_idx: int, new_idx: int) -> None:
        self._tab_bar.blockSignals(True)
        self._tab_bar.setCurrentIndex(new_idx)
        self._tab_bar.blockSignals(False)

    def _on_service_tab_renamed(self, idx: int, name: str) -> None:
        if 0 <= idx < self._tab_bar.count():
            self._tab_bar.setTabText(idx, name)
            # v0.0.20.79: refresh dirty icon
            tab = self._service.tab_at(idx)
            dirty = tab.dirty if tab else False
            icon = self._get_dirty_icon() if dirty else self._get_clean_icon()
            self._tab_bar.setTabIcon(idx, icon)

    def _on_service_dirty_changed(self, idx: int, dirty: bool) -> None:
        if 0 <= idx < self._tab_bar.count():
            tab = self._service.tab_at(idx)
            name = tab.display_name if tab else ""
            # v0.0.20.79: colored dot icon instead of text bullet prefix
            self._tab_bar.setTabText(idx, name)
            icon = self._get_dirty_icon() if dirty else self._get_clean_icon()
            self._tab_bar.setTabIcon(idx, icon)

    # --- UI event handlers ---

    def _on_tab_changed(self, idx: int) -> None:
        """User clicked a different tab."""
        if idx >= 0:
            self.request_switch_tab.emit(idx)

    def _on_tab_close_requested(self, idx: int) -> None:
        """User clicked close button on a tab."""
        self.request_close_tab.emit(idx)

    def _on_tab_moved(self, from_idx: int, to_idx: int) -> None:
        """User dragged a tab to a new position -- sync the service."""
        try:
            self._service.move_tab(from_idx, to_idx)
        except Exception:
            pass

    def _on_tab_double_clicked(self, idx: int) -> None:
        """User double-clicked a tab -- rename it."""
        if idx < 0:
            return
        tab = self._service.tab_at(idx)
        if not tab:
            return
        new_name, ok = QInputDialog.getText(
            self, "Projekt umbenennen", "Neuer Name:",
            text=tab.display_name,
        )
        if ok and new_name.strip():
            self.request_rename_tab.emit(idx, new_name.strip())

    def _on_tab_context_menu(self, pos) -> None:
        """Right-click context menu on a tab."""
        idx = self._tab_bar.tabAt(pos)
        if idx < 0:
            return

        menu = QMenu(self)
        tab = self._service.tab_at(idx)
        name = tab.display_name if tab else f"Tab {idx + 1}"

        act_save = menu.addAction(f"Speichern ({name})")
        act_save_as = menu.addAction("Speichern unter...")
        menu.addSeparator()
        act_rename = menu.addAction("Umbenennen...")
        menu.addSeparator()
        act_close = menu.addAction("Tab schliessen")
        act_close_others = menu.addAction("Andere Tabs schliessen")

        chosen = menu.exec(self._tab_bar.mapToGlobal(pos))

        if chosen == act_save:
            self.request_save_tab.emit(idx)
        elif chosen == act_save_as:
            self.request_save_tab_as.emit(idx)
        elif chosen == act_rename:
            self._on_tab_double_clicked(idx)
        elif chosen == act_close:
            self.request_close_tab.emit(idx)
        elif chosen == act_close_others:
            # Close all except selected
            for i in reversed(range(self._service.count)):
                if i != idx:
                    self.request_close_tab.emit(i)

    # --- Public API ---

    def update_all_labels(self) -> None:
        """Refresh all tab labels from service state."""
        for i in range(self._service.count):
            tab = self._service.tab_at(i)
            if tab:
                name = tab.display_name
                if i < self._tab_bar.count():
                    self._tab_bar.setTabText(i, name)
                    # v0.0.20.79: colored dot icon
                    icon = self._get_dirty_icon() if tab.dirty else self._get_clean_icon()
                    self._tab_bar.setTabIcon(i, icon)
