# -*- coding: utf-8 -*-
"""Plugin search paths dialog (UI-only, safe).

Stores per-kind overrides in QSettings:
    plugins/paths/<kind> = QStringList

If an override exists and is non-empty, it replaces platform defaults.
If empty / unset, scanner uses platform defaults (+ env vars).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QListWidget,
    QPushButton, QFileDialog, QLabel
)

from ..core.settings import SettingsKeys
from ..services import plugin_scanner


class _PathsTab(QWidget):
    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = str(kind)
        self._build()
        self.reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color:#9a9a9a;")

        self.lst = QListWidget()

        row = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_remove = QPushButton("Remove")
        self.btn_reset = QPushButton("Reset to Defaults")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_remove)
        row.addStretch(1)
        row.addWidget(self.btn_reset)

        self.btn_add.clicked.connect(self._add)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_reset.clicked.connect(self._reset)

        root.addWidget(self.info)
        root.addWidget(self.lst, 1)
        root.addLayout(row)

    def _settings(self) -> QSettings:
        return QSettings(SettingsKeys.organization, SettingsKeys.application)

    def _key(self) -> str:
        return f"plugins/paths/{self.kind}"

    def _get_paths(self) -> List[str]:
        s = self._settings()
        val = s.value(self._key(), [])
        if isinstance(val, (list, tuple)):
            return [str(x) for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    def _set_paths(self, paths: List[str]) -> None:
        s = self._settings()
        paths = [str(p) for p in paths if str(p).strip()]
        if paths:
            s.setValue(self._key(), paths)
        else:
            s.remove(self._key())

    def reload(self) -> None:
        self.lst.clear()
        paths = self._get_paths()
        if paths:
            self.info.setText(
                "Override aktiv: diese Liste ersetzt die Default-Scan-Pfade für diesen Plugin-Typ. "
                "(Env-Variablen werden zusätzlich berücksichtigt.)"
            )
            for p in paths:
                self.lst.addItem(p)
        else:
            defs = plugin_scanner.resolve_search_paths(self.kind, extra_paths=None)
            self.info.setText(
                "Keine Overrides gesetzt → Scanner nutzt Platform-Defaults (+ Env vars).\n\nDefaults:\n" +
                "\n".join(str(x) for x in defs if x)
            )

    def _add(self) -> None:
        try:
            d = QFileDialog.getExistingDirectory(self, "Select plugin folder", os.path.expanduser("~"))
        except Exception:
            d = ""
        if not d:
            return
        p = str(Path(d))
        paths = self._get_paths()
        if p not in paths:
            paths.append(p)
            self._set_paths(paths)
        self.reload()

    def _remove(self) -> None:
        it = self.lst.currentItem()
        if it is None:
            return
        paths = self._get_paths()
        try:
            paths.remove(it.text())
        except Exception:
            pass
        self._set_paths(paths)
        self.reload()

    def _reset(self) -> None:
        self._set_paths([])
        self.reload()


class PluginPathsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugin Scan Paths")
        self.resize(720, 420)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        for kind, title in (
            ("lv2", "LV2"),
            ("ladspa", "LADSPA"),
            ("dssi", "DSSI"),
            ("vst2", "VST2"),
            ("vst3", "VST3"),
        ):
            self.tabs.addTab(_PathsTab(kind, self), title)

        hint = QLabel(
            "Tipp: Alternativ kannst du Env-Variablen setzen (LV2_PATH, LADSPA_PATH, DSSI_PATH, VST_PATH, VST3_PATH).\n"
            "Dieses Dialog-Fenster ist nur für Scan-Pfade – Hosting/Loading folgt separat."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9a9a9a;")

        row = QHBoxLayout()
        row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)

        root.addWidget(self.tabs, 1)
        root.addWidget(hint)
        root.addLayout(row)
