"""Project Browser Widget (v0.0.20.77) — Browse into project files.

Ableton-style project browser: shows .pydaw.json files and lets users
peek inside to see tracks/clips without fully loading the project.
Users can drag individual tracks from a closed project into the current one.

Usage:
  - Shows project files in recent/chosen directories
  - Click to peek: shows tracks + clips summary
  - Drag a track row into the arranger to import it
  - Double-click to open the full project in a new tab
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QPushButton,
    QFileDialog,
    QHeaderView,
    QSizePolicy,
    QToolButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag, QColor

from pydaw.services.project_tab_service import ProjectTabService


class ProjectBrowserWidget(QWidget):
    """File browser that shows .pydaw.json project files.

    Allows peeking inside projects and dragging tracks/clips into
    the current project without opening the source project fully.
    """

    # Signals
    request_open_in_tab = pyqtSignal(str)           # path (to open project in new tab)
    request_import_tracks = pyqtSignal(str, list)    # path, list of track_ids
    status_message = pyqtSignal(str)

    def __init__(
        self,
        tab_service: ProjectTabService | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._tab_service = tab_service
        self._current_dir: Optional[Path] = None
        self._peeked_data: Optional[Dict[str, Any]] = None
        self._peeked_path: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with folder selection
        header = QHBoxLayout()
        self._lbl_dir = QLabel("Projekt-Ordner:")
        self._lbl_dir.setStyleSheet("color: #AAA; font-size: 10px;")
        header.addWidget(self._lbl_dir, 1)

        btn_choose = QToolButton()
        btn_choose.setText("📁")
        btn_choose.setToolTip("Ordner wählen")
        btn_choose.setAutoRaise(True)
        btn_choose.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_choose.clicked.connect(self._choose_directory)
        header.addWidget(btn_choose)

        btn_refresh = QToolButton()
        btn_refresh.setText("🔄")
        btn_refresh.setToolTip("Aktualisieren")
        btn_refresh.setAutoRaise(True)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh)
        header.addWidget(btn_refresh)

        layout.addLayout(header)

        # Project file tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Typ", "Details"])
        self._tree.setColumnCount(3)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background: #1E1E1E;
                color: #CCC;
                border: 1px solid #333;
                font-size: 11px;
            }
            QTreeWidget::item:selected {
                background: #2A4A6A;
            }
            QTreeWidget::item:hover {
                background: #2A2A3A;
            }
        """)

        try:
            hdr = self._tree.header()
            hdr.setStretchLastSection(True)
            hdr.resizeSection(0, 180)
            hdr.resizeSection(1, 60)
        except Exception:
            pass

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setDragEnabled(True)

        layout.addWidget(self._tree, 1)

        # Info panel (shows peeked project details)
        self._info_label = QLabel("Klicke auf eine Projektdatei zum Vorschauen.")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("""
            QLabel {
                color: #888;
                background: #1A1A1A;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
                font-size: 10px;
            }
        """)
        self._info_label.setMaximumHeight(80)
        layout.addWidget(self._info_label)

        # Action buttons
        btn_row = QHBoxLayout()
        self._btn_open_tab = QPushButton("In neuem Tab öffnen")
        self._btn_open_tab.setEnabled(False)
        self._btn_open_tab.clicked.connect(self._on_open_in_tab)
        self._btn_open_tab.setStyleSheet("""
            QPushButton {
                background: #2A4A6A;
                color: #DDD;
                border: 1px solid #3A5A7A;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover { background: #3A5A8A; }
            QPushButton:disabled { background: #222; color: #555; border-color: #333; }
        """)
        btn_row.addWidget(self._btn_open_tab)

        self._btn_import = QPushButton("Tracks importieren")
        self._btn_import.setEnabled(False)
        self._btn_import.setToolTip("Ausgewählte Tracks in das aktive Projekt importieren")
        self._btn_import.clicked.connect(self._on_import_tracks)
        self._btn_import.setStyleSheet(self._btn_open_tab.styleSheet())
        btn_row.addWidget(self._btn_import)

        layout.addLayout(btn_row)

    # --- Directory scanning ---

    def set_directory(self, path: Path) -> None:
        """Set the directory to scan for project files."""
        self._current_dir = path
        self._lbl_dir.setText(f"📁 {path.name}/")
        self._lbl_dir.setToolTip(str(path))
        self._scan_directory(path)

    def _choose_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Projekt-Ordner wählen", str(self._current_dir or Path.home())
        )
        if path:
            self.set_directory(Path(path))

    def _refresh(self) -> None:
        if self._current_dir:
            self._scan_directory(self._current_dir)

    def _scan_directory(self, root: Path) -> None:
        """Scan directory for .pydaw.json files and populate tree."""
        self._tree.clear()
        self._peeked_data = None
        self._peeked_path = None
        self._btn_open_tab.setEnabled(False)
        self._btn_import.setEnabled(False)

        if not root.is_dir():
            return

        try:
            # Find .pydaw.json files (max 2 levels deep)
            project_files: List[Path] = []
            for pattern in ("*.pydaw.json", "**/*.pydaw.json"):
                for p in root.glob(pattern):
                    if p.is_file() and p not in project_files:
                        project_files.append(p)
                    if len(project_files) >= 100:
                        break
                if len(project_files) >= 100:
                    break

            project_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            for pf in project_files[:50]:
                rel = pf.relative_to(root) if pf.is_relative_to(root) else pf
                item = QTreeWidgetItem()
                item.setText(0, pf.stem.replace(".pydaw", ""))
                item.setText(1, "Projekt")
                item.setText(2, str(rel.parent) if str(rel.parent) != "." else "")
                item.setData(0, Qt.ItemDataRole.UserRole, str(pf))
                item.setData(0, Qt.ItemDataRole.UserRole + 1, "project")
                item.setForeground(0, QColor("#8AC"))
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self._tree.addTopLevelItem(item)

        except Exception as exc:
            self.status_message.emit(f"Fehler beim Scannen: {exc}")

    # --- Peeking into projects ---

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Click on a project file → peek inside."""
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        path_str = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "project" and path_str:
            self._peek_project(Path(path_str), item)
        elif item_type == "track":
            # Track selected inside a peeked project
            self._btn_import.setEnabled(True)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Double-click on project → open in new tab."""
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        path_str = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "project" and path_str:
            self.request_open_in_tab.emit(path_str)

    def _peek_project(self, path: Path, parent_item: QTreeWidgetItem) -> None:
        """Load project metadata and show tracks/clips as child items."""
        # Clear existing children
        parent_item.takeChildren()

        data = ProjectTabService.peek_project(path)
        if not data:
            self._info_label.setText(f"Konnte {path.name} nicht lesen.")
            return

        self._peeked_data = data
        self._peeked_path = path
        self._btn_open_tab.setEnabled(True)

        # Show info
        self._info_label.setText(
            f"📋 {data['name']} | {data['bpm']} BPM | {data['time_signature']} | "
            f"{data['track_count']} Tracks, {data['clip_count']} Clips | "
            f"v{data['version']}"
        )

        # Add track children
        for t in data.get("tracks", []):
            kind = t.get("kind", "?")
            plugin = t.get("plugin_type") or ""
            sf2 = Path(t.get("sf2_path") or "").name if t.get("sf2_path") else ""

            child = QTreeWidgetItem()
            child.setText(0, t.get("name", "Track"))
            child.setText(1, kind)
            detail_parts = []
            if plugin:
                detail_parts.append(plugin)
            if sf2:
                detail_parts.append(sf2)
            child.setText(2, " | ".join(detail_parts))
            child.setData(0, Qt.ItemDataRole.UserRole, str(path))
            child.setData(0, Qt.ItemDataRole.UserRole + 1, "track")
            child.setData(0, Qt.ItemDataRole.UserRole + 2, t.get("id", ""))

            # Color by kind
            colors = {"master": "#FA8", "instrument": "#8CF", "audio": "#8F8", "bus": "#FC8"}
            child.setForeground(0, QColor(colors.get(kind, "#CCC")))

            parent_item.addChild(child)

        parent_item.setExpanded(True)

    # --- Actions ---

    def _on_open_in_tab(self) -> None:
        if self._peeked_path:
            self.request_open_in_tab.emit(str(self._peeked_path))

    def _on_import_tracks(self) -> None:
        """Import selected track(s) from peeked project into active project."""
        if not self._peeked_path:
            return

        selected = self._tree.selectedItems()
        track_ids = []
        for item in selected:
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "track":
                tid = item.data(0, Qt.ItemDataRole.UserRole + 2)
                if tid:
                    track_ids.append(tid)

        if track_ids:
            self.request_import_tracks.emit(str(self._peeked_path), track_ids)
        else:
            self.status_message.emit("Bitte wähle einen oder mehrere Tracks aus.")
