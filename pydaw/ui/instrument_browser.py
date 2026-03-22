# -*- coding: utf-8 -*-
"""Instrument Browser tab (Pro-DAW-Style).

Lists available internal instruments (Python plugins) and lets the user add them to the device chain.

Phase 4.5 (UI-only, safe):
- ⭐ one-click Favorite toggling directly in the list (left star hitbox)
- Recents update remains unchanged
- All Qt signal handlers are exception-safe (PyQt6 may abort on uncaught slot exceptions)
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QMenu,
)

from pydaw.plugins.registry import get_instruments, InstrumentSpec
from .device_prefs import DevicePrefs

_MIME = "application/x-pydaw-plugin"


class _StarDragInstrumentList(QListWidget):
    """Drag list with a star toggle hitbox on the left side (x < 18px)."""

    def __init__(self, on_toggle_fav=None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self._on_toggle_fav = on_toggle_fav
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def mousePressEvent(self, event):  # noqa: N802, ANN001
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                try:
                    pos = event.position().toPoint()
                except Exception:
                    pos = event.pos()
                if pos.x() < 18:
                    it = self.itemAt(pos)
                    if it is not None and self._on_toggle_fav is not None:
                        self.setCurrentItem(it)
                        payload = it.data(Qt.ItemDataRole.UserRole) or {}
                        if isinstance(payload, dict):
                            pid = str(payload.get("plugin_id") or "")
                            name = str(payload.get("name") or "")
                            if pid:
                                try:
                                    self._on_toggle_fav(pid, name)
                                except Exception:
                                    pass
                                event.accept()
                                return
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def startDrag(self, supportedActions):  # noqa: N802, ANN001
        try:
            it = self.currentItem()
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return
            pid = str(payload.get("plugin_id") or "")
            name = str(payload.get("name") or it.text() or "")
            if not pid:
                return
            md = QMimeData()
            md.setData(_MIME, json.dumps({"kind": "instrument", "plugin_id": pid, "name": name}).encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            return


class InstrumentBrowserWidget(QWidget):
    prefs_changed = Signal()

    def __init__(self, on_add_instrument: Optional[Callable[[str], None]] = None, get_add_scope: Optional[Callable[[str], tuple[str, str]]] = None, parent=None):
        super().__init__(parent)
        self._on_add = on_add_instrument
        self._get_add_scope = get_add_scope
        self._items: list[InstrumentSpec] = []
        self._build()

    # ---- safety ----
    def _safe(self, fn, *a, **k):  # noqa: ANN001
        try:
            return fn(*a, **k)
        except Exception:
            return None

    # ---- UI ----
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("Instruments")
        header.setObjectName("instrumentBrowserTitle")

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen…")
        self.search.textChanged.connect(lambda _t: self._safe(self._refilter))

        self.btn_add = QPushButton("Add to Device")
        self.btn_add.clicked.connect(lambda _=False: self._safe(self._add_selected))

        self._scope_badge = QLabel("")
        self._scope_badge.setStyleSheet("padding:2px 8px; border:1px solid rgba(255,185,110,120); border-radius:9px; color:#ffd7a3; background:rgba(255,185,110,20); font-weight:600;")

        row.addWidget(self.search, 1)
        row.addWidget(self._scope_badge, 0)
        row.addWidget(self.btn_add, 0)

        self.list = _StarDragInstrumentList(on_toggle_fav=lambda pid, name: self._safe(self._toggle_favorite, pid, name))
        self.list.itemDoubleClicked.connect(lambda _it: self._safe(self._add_selected))
        self.list.customContextMenuRequested.connect(lambda pos: self._safe(self._show_context_menu, pos))

        hint = QLabel("Tipp: ⭐ links klicken = Favorite. Doppelklick oder 'Add to Device'. Drag&Drop in die Device-Chain.")
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        hint.setStyleSheet("color: #9a9a9a;")

        layout.addWidget(header)
        layout.addLayout(row)
        layout.addWidget(self.list, 1)
        layout.addWidget(hint)

        self.reload()
        self._update_scope_badge()


    def _update_scope_badge(self) -> None:
        try:
            if callable(self._get_add_scope):
                short, tip = self._get_add_scope("instrument")
            else:
                short, tip = ("Ziel: Spur", "Instrumente werden auf die aktive Spur hinzugefügt.")
            self._scope_badge.setText(str(short or "Ziel: Spur"))
            self._scope_badge.setToolTip(str(tip or ""))
        except Exception:
            try:
                self._scope_badge.setText("Ziel: Spur")
            except Exception:
                pass

    def refresh_scope_badge(self) -> None:
        self._safe(self._update_scope_badge)

    # ---- data ----
    def reload(self) -> None:
        self._items = list(get_instruments() or [])
        self._refilter()

    def _refilter(self) -> None:
        try:
            prefs = DevicePrefs.load()
        except Exception:
            prefs = None
        q = (self.search.text() or "").strip().lower()
        self.list.clear()

        for spec in self._items:
            try:
                pid = str(spec.plugin_id or "")
                if not pid:
                    continue
                name = str(spec.name or pid)
                cat = str(getattr(spec, "category", "") or "")
                desc = str(getattr(spec, "description", "") or "")
                hay = f"{name} {getattr(spec,'vendor','')} {cat} {desc} {pid}".lower()
                if q and q not in hay:
                    continue

                fav = bool(prefs and prefs.is_favorite("instrument", pid))
                star = "★" if fav else "☆"
                label = f"{star}  {name}   —   {cat or 'Instrument'}"
                it = QListWidgetItem(label)
                it.setData(Qt.ItemDataRole.UserRole, {"plugin_id": pid, "name": name, "favorite": fav})
                if desc:
                    it.setToolTip(desc)
                self.list.addItem(it)
            except Exception:
                continue

        self.btn_add.setEnabled(self.list.count() > 0)
        self._update_scope_badge()

    # ---- favorites ----
    def _toggle_favorite(self, plugin_id: str, name: str) -> None:
        try:
            prefs = DevicePrefs.load()
            prefs.toggle_favorite("instrument", str(plugin_id), str(name))
            prefs.save()
            self._refilter()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass

    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        try:
            it = self.list.itemAt(pos)
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return
            pid = str(payload.get("plugin_id") or "")
            name = str(payload.get("name") or "")
            if not pid:
                return
            fav = bool(payload.get("favorite"))
            m = QMenu(self)
            a = m.addAction("⭐ Remove from Favorites" if fav else "⭐ Add to Favorites")
            a.triggered.connect(lambda _=False: self._safe(self._toggle_favorite, pid, name))
            m.exec(self.list.mapToGlobal(pos))
        except Exception:
            pass

    # ---- add ----
    def _add_selected(self) -> None:
        if self._on_add is None:
            return
        it = self.list.currentItem()
        if it is None and self.list.count() > 0:
            it = self.list.item(0)
        if it is None:
            return

        payload = it.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict):
            return
        pid = str(payload.get("plugin_id") or "")
        name = str(payload.get("name") or "")
        if not pid:
            return

        # Phase 4: update Recents (UI-only, per-user) before inserting
        try:
            prefs = DevicePrefs.load()
            prefs.add_recent("instrument", pid, name)
            prefs.save()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass

        try:
            self._on_add(pid)
        except Exception:
            pass
