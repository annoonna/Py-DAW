# -*- coding: utf-8 -*-
"""Plugin Blacklist Dialog — View and manage blacklisted plugins.

v0.0.20.725: Shows crash-blacklisted plugins with details and un-blacklist option.

Integrates with pydaw.services.plugin_probe persistent blacklist.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

_log = logging.getLogger(__name__)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    )
    _QT = True
except ImportError:
    _QT = False


def _format_time(ts: float) -> str:
    """Format timestamp as human-readable string."""
    if ts <= 0:
        return "—"
    try:
        import datetime
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(int(ts))


if _QT:
    class PluginBlacklistDialog(QDialog):
        """Dialog showing all blacklisted (crash-prone) plugins.

        Users can select entries and un-blacklist them for re-probing.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Plugin-Blacklist — Crash-Isolierung")
            self.setMinimumSize(700, 400)
            self._build_ui()
            self._load_data()

        def _build_ui(self):
            layout = QVBoxLayout(self)

            # Header
            header = QLabel(
                "Diese Plugins wurden beim Laden als abgestürzt erkannt und automatisch "
                "blockiert. Du kannst einzelne Plugins entsperren — sie werden beim "
                "nächsten Laden erneut geprobt."
            )
            header.setWordWrap(True)
            header.setStyleSheet("color: #aaa; margin-bottom: 8px;")
            layout.addWidget(header)

            # Tree
            self._tree = QTreeWidget()
            self._tree.setHeaderLabels([
                "Plugin", "Typ", "Grund", "Crashes", "Letzter Crash"
            ])
            self._tree.setRootIsDecorated(False)
            self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            self._tree.setAlternatingRowColors(True)
            try:
                hdr = self._tree.header()
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
                hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
                hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            except Exception:
                pass
            layout.addWidget(self._tree)

            # Status
            self._lbl_status = QLabel("")
            self._lbl_status.setStyleSheet("color: #888;")
            layout.addWidget(self._lbl_status)

            # Buttons
            btn_row = QHBoxLayout()

            self._btn_unblock = QPushButton("Auswahl entsperren")
            self._btn_unblock.setToolTip(
                "Ausgewählte Plugins werden beim nächsten Laden erneut geprobt"
            )
            self._btn_unblock.clicked.connect(self._on_unblock)
            btn_row.addWidget(self._btn_unblock)

            self._btn_clear_all = QPushButton("Alle entsperren")
            self._btn_clear_all.setToolTip(
                "Gesamte Blacklist leeren — alle Plugins werden erneut geprobt"
            )
            self._btn_clear_all.clicked.connect(self._on_clear_all)
            btn_row.addWidget(self._btn_clear_all)

            btn_row.addStretch()

            btn_close = QPushButton("Schließen")
            btn_close.clicked.connect(self.accept)
            btn_row.addWidget(btn_close)

            layout.addLayout(btn_row)

        def _load_data(self):
            """Load blacklist data into tree."""
            self._tree.clear()
            try:
                from pydaw.services.plugin_probe import get_blacklist
                blacklist = get_blacklist()
            except ImportError:
                self._lbl_status.setText("Plugin-Probe-Modul nicht verfügbar")
                return

            if not blacklist:
                self._lbl_status.setText("Keine geblacklisteten Plugins")
                self._btn_unblock.setEnabled(False)
                self._btn_clear_all.setEnabled(False)
                return

            for cache_key, entry in blacklist.items():
                if entry.user_override:
                    continue  # Skip user-cleared entries

                item = QTreeWidgetItem()
                # Column 0: Plugin name/path
                display_name = entry.plugin_name or entry.plugin_path.split("/")[-1]
                item.setText(0, display_name)
                item.setToolTip(0, entry.plugin_path)

                # Column 1: Type
                item.setText(1, entry.plugin_type.upper())

                # Column 2: Reason
                item.setText(2, entry.reason)

                # Column 3: Crash count
                item.setText(3, str(entry.crash_count))
                if entry.crash_count >= 3:
                    item.setForeground(3, Qt.GlobalColor.red)

                # Column 4: Last crash
                item.setText(4, _format_time(entry.last_crash))

                # Store cache key for un-blacklist
                item.setData(0, Qt.ItemDataRole.UserRole, cache_key)
                item.setData(1, Qt.ItemDataRole.UserRole, entry.plugin_path)
                item.setData(2, Qt.ItemDataRole.UserRole, entry.plugin_type)
                item.setData(3, Qt.ItemDataRole.UserRole, entry.plugin_name)

                self._tree.addTopLevelItem(item)

            count = self._tree.topLevelItemCount()
            self._lbl_status.setText(f"{count} Plugin(s) geblacklistet")
            self._btn_unblock.setEnabled(count > 0)
            self._btn_clear_all.setEnabled(count > 0)

        def _on_unblock(self):
            """Un-blacklist selected plugins."""
            items = self._tree.selectedItems()
            if not items:
                return

            try:
                from pydaw.services.plugin_probe import clear_blacklist_entry
            except ImportError:
                return

            count = 0
            for item in items:
                path = item.data(1, Qt.ItemDataRole.UserRole) or ""
                ptype = item.data(2, Qt.ItemDataRole.UserRole) or "vst3"
                pname = item.data(3, Qt.ItemDataRole.UserRole) or ""
                if clear_blacklist_entry(path, ptype, pname):
                    count += 1

            if count > 0:
                self._load_data()  # Refresh
                self._lbl_status.setText(
                    f"{count} Plugin(s) entsperrt — werden beim nächsten Laden erneut geprobt"
                )

        def _on_clear_all(self):
            """Clear entire blacklist."""
            reply = QMessageBox.question(
                self,
                "Blacklist leeren",
                "Wirklich ALLE geblacklisteten Plugins entsperren?\n\n"
                "Crash-anfällige Plugins werden beim nächsten Laden erneut geprobt "
                "und ggf. wieder blockiert.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            try:
                from pydaw.services.plugin_probe import clear_blacklist
                clear_blacklist()
            except ImportError:
                return

            self._load_data()
            self._lbl_status.setText("Blacklist geleert — alle Plugins werden erneut geprobt")
