# -*- coding: utf-8 -*-
"""Effects Browser (Note-FX + Audio-FX) — drag into the Device Chain.

Bitwig/Ableton rule:
- Browser entries are templates.
- Drop creates a new instance on the selected track.

Mime payload:
    application/x-pydaw-plugin  (JSON bytes)
    {"kind":"note_fx|audio_fx|instrument", "plugin_id":"...", "name":"..."}

Phase 4.5 (UI-only, safe):
- ⭐ one-click Favorite toggling directly in the list (left star hitbox)
- Favorites/Recents stay in sync via prefs_changed
- All Qt signal handlers are exception-safe (PyQt6 may abort on uncaught slot exceptions)
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QLineEdit, QTabWidget, QMenu
)

from .fx_specs import get_note_fx, get_audio_fx, FxSpec
from .device_prefs import DevicePrefs

# v0.0.20.531: Import containers
try:
    from .fx_specs import get_containers as _get_containers
except ImportError:
    def _get_containers():
        return []

_MIME = "application/x-pydaw-plugin"


class _StarDragList(QListWidget):
    """Drag list with a star toggle hitbox on the left side (x < 18px)."""

    def __init__(self, kind: str, on_toggle_fav=None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self.kind = str(kind)
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
                                    self._on_toggle_fav(self.kind, pid, name)
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
            md.setData(_MIME, json.dumps({"kind": self.kind, "plugin_id": pid, "name": name}).encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            return


class EffectsBrowserWidget(QWidget):
    prefs_changed = pyqtSignal()

    def __init__(
        self,
        on_add_note_fx: Optional[Callable[[str], None]] = None,
        on_add_audio_fx: Optional[Callable[[str], None]] = None,
        get_add_scope: Optional[Callable[[str], tuple[str, str]]] = None,
        parent=None
    ):
        super().__init__(parent)
        self._on_add_note = on_add_note_fx
        self._on_add_audio = on_add_audio_fx
        self._get_add_scope = get_add_scope
        self._note_specs = list(get_note_fx() or [])
        self._audio_specs = list(get_audio_fx() or [])
        self._build()

    # ---- safety ----
    def _safe(self, fn, *a, **k):  # noqa: ANN001
        try:
            return fn(*a, **k)
        except Exception:
            return None

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QLabel("Effects")
        header.setObjectName("effectsBrowserTitle")

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # --- Note-FX tab
        note_tab = QWidget()
        v1 = QVBoxLayout(note_tab)
        v1.setContentsMargins(0, 0, 0, 0)
        v1.setSpacing(6)

        row1 = QHBoxLayout()
        self.search_note = QLineEdit()
        self.search_note.setPlaceholderText("Suchen… (Note-FX)")
        self.search_note.textChanged.connect(lambda _t: self._safe(self._refilter_note))
        self.btn_add_note = QPushButton("Add")
        self.btn_add_note.clicked.connect(lambda _=False: self._safe(self._add_note_selected))
        self._scope_badge_note = QLabel("")
        self._scope_badge_note.setStyleSheet("padding:2px 8px; border:1px solid rgba(255,185,110,120); border-radius:9px; color:#ffd7a3; background:rgba(255,185,110,20); font-weight:600;")
        row1.addWidget(self.search_note, 1)
        row1.addWidget(self._scope_badge_note, 0)
        row1.addWidget(self.btn_add_note, 0)

        self.list_note = _StarDragList("note_fx", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_note.itemDoubleClicked.connect(lambda _it: self._safe(self._add_note_selected))
        self.list_note.customContextMenuRequested.connect(lambda pos: self._safe(self._show_context_menu, self.list_note, pos))

        hint1 = QLabel("Tipp: ⭐ links klicken = Favorite. Drag&Drop oder Doppelklick → Add.")
        hint1.setStyleSheet("color:#9a9a9a;")

        v1.addLayout(row1)
        v1.addWidget(self.list_note, 1)
        v1.addWidget(hint1)

        # --- Audio-FX tab
        audio_tab = QWidget()
        v2 = QVBoxLayout(audio_tab)
        v2.setContentsMargins(0, 0, 0, 0)
        v2.setSpacing(6)

        row2 = QHBoxLayout()
        self.search_audio = QLineEdit()
        self.search_audio.setPlaceholderText("Suchen… (Audio-FX)")
        self.search_audio.textChanged.connect(lambda _t: self._safe(self._refilter_audio))
        self.btn_add_audio = QPushButton("Add")
        self.btn_add_audio.clicked.connect(lambda _=False: self._safe(self._add_audio_selected))
        self._scope_badge_audio = QLabel("")
        self._scope_badge_audio.setStyleSheet("padding:2px 8px; border:1px solid rgba(255,185,110,120); border-radius:9px; color:#ffd7a3; background:rgba(255,185,110,20); font-weight:600;")
        row2.addWidget(self.search_audio, 1)
        row2.addWidget(self._scope_badge_audio, 0)
        row2.addWidget(self.btn_add_audio, 0)

        self.list_audio = _StarDragList("audio_fx", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_audio.itemDoubleClicked.connect(lambda _it: self._safe(self._add_audio_selected))
        self.list_audio.customContextMenuRequested.connect(lambda pos: self._safe(self._show_context_menu, self.list_audio, pos))

        hint2 = QLabel("Tipp: ⭐ links klicken = Favorite. Drag&Drop oder Doppelklick → Add.")
        hint2.setStyleSheet("color:#9a9a9a;")

        v2.addLayout(row2)
        v2.addWidget(self.list_audio, 1)
        v2.addWidget(hint2)

        self.tabs.addTab(note_tab, "🎹 Note-FX")
        self.tabs.addTab(audio_tab, "🎚️ Audio-FX")
        try:
            self.tabs.currentChanged.connect(lambda _i: self._safe(self._update_scope_badges))
        except Exception:
            pass

        root.addWidget(header)
        root.addWidget(self.tabs, 1)

        self._refilter_note()
        self._refilter_audio()
        self._update_scope_badges()


    def _scope_info(self, kind: str) -> tuple[str, str]:
        try:
            if callable(self._get_add_scope):
                return self._get_add_scope(str(kind or ""))
        except Exception:
            pass
        return ("Ziel: Spur", "Browser-Add / Doppelklick / Drag&Drop wirkt auf die aktive Spur.")

    def _update_scope_badges(self) -> None:
        try:
            short, tip = self._scope_info("note_fx")
            self._scope_badge_note.setText(str(short or "Ziel: Spur"))
            self._scope_badge_note.setToolTip(str(tip or ""))
        except Exception:
            pass
        try:
            short, tip = self._scope_info("audio_fx")
            self._scope_badge_audio.setText(str(short or "Ziel: Spur"))
            self._scope_badge_audio.setToolTip(str(tip or ""))
        except Exception:
            pass

    def refresh_scope_badge(self) -> None:
        self._safe(self._update_scope_badges)

    # ---- favorites ----
    def _toggle_favorite(self, kind: str, plugin_id: str, name: str) -> None:
        try:
            prefs = DevicePrefs.load()
            prefs.toggle_favorite(str(kind), str(plugin_id), str(name))
            prefs.save()
            # refresh lists (so stars update)
            self._refilter_note()
            self._refilter_audio()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass

    def _show_context_menu(self, lst: QListWidget, pos) -> None:  # noqa: ANN001
        try:
            it = lst.itemAt(pos)
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return
            pid = str(payload.get("plugin_id") or "")
            name = str(payload.get("name") or "")
            kind = str(payload.get("kind") or "")
            if not pid or not kind:
                return
            fav = bool(payload.get("favorite"))
            m = QMenu(self)
            a = m.addAction("⭐ Remove from Favorites" if fav else "⭐ Add to Favorites")
            a.triggered.connect(lambda _=False: self._safe(self._toggle_favorite, kind, pid, name))
            m.exec(lst.mapToGlobal(pos))
        except Exception:
            pass

    # ---- filtering ----
    def _refilter_note(self) -> None:
        try:
            prefs = DevicePrefs.load()
        except Exception:
            prefs = None
        q = (self.search_note.text() or "").strip().lower()
        self.list_note.clear()
        for s in self._note_specs:
            try:
                pid = str(s.plugin_id or "")
                name = str(s.name or pid)
                if not pid:
                    continue
                hay = f"{name} {pid}".lower()
                if q and q not in hay:
                    continue
                fav = bool(prefs and prefs.is_favorite("note_fx", pid))
                star = "★" if fav else "☆"
                it = QListWidgetItem(f"{star}  {name}   —   {pid}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": "note_fx", "plugin_id": pid, "name": name, "favorite": fav})
                self.list_note.addItem(it)
            except Exception:
                continue
        self.btn_add_note.setEnabled(self.list_note.count() > 0)
        self._update_scope_badges()

    def _refilter_audio(self) -> None:
        try:
            prefs = DevicePrefs.load()
        except Exception:
            prefs = None
        q = (self.search_audio.text() or "").strip().lower()
        self.list_audio.clear()
        # v0.0.20.531: Container entries at top
        try:
            for cs in (_get_containers() or []):
                pid = str(getattr(cs, "plugin_id", "") or "")
                name = str(getattr(cs, "name", "") or pid)
                if not pid:
                    continue
                hay = f"{name} {pid} container layer chain".lower()
                if q and q not in hay:
                    continue
                it = QListWidgetItem(f"📦  {name}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": "container", "plugin_id": pid, "name": name, "favorite": False})
                try:
                    it.setForeground(Qt.GlobalColor.cyan)
                except Exception:
                    pass
                self.list_audio.addItem(it)
        except Exception:
            pass
        for s in self._audio_specs:
            try:
                pid = str(s.plugin_id or "")
                name = str(s.name or pid)
                if not pid:
                    continue
                hay = f"{name} {pid}".lower()
                if q and q not in hay:
                    continue
                fav = bool(prefs and prefs.is_favorite("audio_fx", pid))
                star = "★" if fav else "☆"
                it = QListWidgetItem(f"{star}  {name}   —   {pid}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": "audio_fx", "plugin_id": pid, "name": name, "favorite": fav})
                self.list_audio.addItem(it)
            except Exception:
                continue
        self.btn_add_audio.setEnabled(self.list_audio.count() > 0)
        self._update_scope_badges()

    # ---- add ----
    def _add_note_selected(self) -> None:
        if self._on_add_note is None:
            return
        it = self.list_note.currentItem()
        if it is None and self.list_note.count() > 0:
            it = self.list_note.item(0)
        if it is None:
            return
        payload = it.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict):
            return
        pid = str(payload.get("plugin_id") or "")
        name = str(payload.get("name") or "")
        if not pid:
            return
        # Phase 4: update Recents (UI-only, per-user)
        try:
            prefs = DevicePrefs.load()
            prefs.add_recent("note_fx", pid, name)
            prefs.save()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._on_add_note(pid)
        except Exception:
            pass

    def _add_audio_selected(self) -> None:
        if self._on_add_audio is None:
            return
        it = self.list_audio.currentItem()
        if it is None and self.list_audio.count() > 0:
            it = self.list_audio.item(0)
        if it is None:
            return
        payload = it.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict):
            return
        pid = str(payload.get("plugin_id") or "")
        name = str(payload.get("name") or "")
        kind = str(payload.get("kind") or "audio_fx")
        if not pid:
            return
        # v0.0.20.531: Container entries use special callback
        if kind == "container":
            try:
                cb = getattr(self, "_on_add_container", None)
                if callable(cb):
                    cb(pid)
                    return
                # Fallback: route through generic audio_fx callback
                self._on_add_audio(pid)
            except Exception:
                pass
            return
        # Phase 4: update Recents (UI-only, per-user)
        try:
            prefs = DevicePrefs.load()
            prefs.add_recent("audio_fx", pid, name)
            prefs.save()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._on_add_audio(pid)
        except Exception:
            pass
