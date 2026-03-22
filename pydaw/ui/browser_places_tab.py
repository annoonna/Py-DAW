"""Visible Browser Places tab (Bitwig-style quick access, UI-only, safe)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel, QPushButton, QHBoxLayout

from .browser_places_prefs import BrowserPlacesPrefs


class BrowserPlacesTab(QWidget):
    def __init__(self, get_quick_dirs: Callable[[], dict[str, str]], get_current_path: Callable[[], str], on_open_path: Callable[[str], None], parent=None):
        super().__init__(parent)
        self._get_quick_dirs = get_quick_dirs
        self._get_current_path = get_current_path
        self._on_open_path = on_open_path
        self._prefs = BrowserPlacesPrefs.load()
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        lay.addWidget(QLabel("⭐ Orte / Favoriten"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open_item)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton("Öffnen")
        self.btn_add = QPushButton("⭐ Aktuellen Browser-Pfad merken")
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_add, 1)
        lay.addLayout(row)

        self.btn_open.clicked.connect(self._open_current_item)
        self.btn_add.clicked.connect(self.add_current_place)

    def reload(self) -> None:
        try:
            self.list.clear()
            q = self._get_quick_dirs() or {}
            builtins = [
                ("🏠 Home", q.get("home", str(Path.home())), False),
                ("🎛 Samples", q.get("samples", str(Path.home())), False),
                ("🎼 SF2", q.get("sf2", str(Path.home())), False),
                ("📥 Downloads", q.get("downloads", str(Path.home())), False),
                ("🎵 Music", q.get("music", str(Path.home())), False),
            ]
            for label, path_str, removable in builtins:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, str(path_str))
                item.setData(Qt.ItemDataRole.UserRole + 1, bool(removable))
                self.list.addItem(item)
            for it in self._prefs.places:
                path_str = str(it.get("path") or "")
                label = str(it.get("label") or Path(path_str).name or path_str)
                item = QListWidgetItem(f"⭐ {label}")
                item.setToolTip(path_str)
                item.setData(Qt.ItemDataRole.UserRole, path_str)
                item.setData(Qt.ItemDataRole.UserRole + 1, True)
                self.list.addItem(item)
        except Exception:
            pass

    def add_current_place(self) -> None:
        try:
            cur = str(self._get_current_path() or "").strip()
            if not cur:
                return
            label = Path(cur).name or cur
            if self._prefs.add_place(label, cur):
                self._prefs.save()
                self.reload()
        except Exception:
            pass

    def _open_current_item(self) -> None:
        try:
            self._open_item(self.list.currentItem())
        except Exception:
            pass

    def _open_item(self, item) -> None:  # noqa: ANN001
        try:
            if item is None:
                return
            path_str = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if path_str:
                self._on_open_path(path_str)
        except Exception:
            pass
