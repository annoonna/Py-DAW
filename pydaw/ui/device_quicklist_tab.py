# -*- coding: utf-8 -*-
"""Browser Quick Tabs: ⭐ Favorites / 🕘 Recents (UI-only, safe).

Goal (Phase 4):
- Expose the same Favorites/Recents concept that exists in Track-Header ▾ menus
  directly inside the right Browser.
- Completely additive: no existing tabs/shortcuts/workflows are changed.

Implementation notes:
- Uses per-user prefs JSON (DevicePrefs) stored in ~/.cache/ChronoScaleStudio/device_prefs.json
- Provides optional Drag&Drop via the same MIME payload used by other browser tabs.
- All Qt signal handlers are exception-safe (PyQt6 may abort on uncaught slot exceptions).
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
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

from .device_prefs import DevicePrefs


_MIME = "application/x-pydaw-plugin"


class _DragQuickList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def startDrag(self, supportedActions):  # noqa: N802
        try:
            it = self.currentItem()
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return
            # do not drag section headers
            if payload.get("_section"):
                return
            md = QMimeData()
            md.setData(_MIME, json.dumps(payload).encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            return


class _StarDragQuickList(_DragQuickList):
    """QuickList with a left star hitbox (x < 18px) to toggle favorites."""

    def __init__(self, on_toggle_fav=None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self._on_toggle_fav = on_toggle_fav

    def mousePressEvent(self, event):  # noqa: N802, ANN001
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._on_toggle_fav is not None:
                try:
                    pos = event.position().toPoint()
                except Exception:
                    pos = event.pos()
                if pos.x() < 18:
                    it = self.itemAt(pos)
                    if it is not None:
                        payload = it.data(Qt.ItemDataRole.UserRole) or {}
                        if isinstance(payload, dict) and not payload.get("_section"):
                            kind = str(payload.get("kind") or "")
                            pid = str(payload.get("plugin_id") or "")
                            name = str(payload.get("name") or "")
                            if pid:
                                try:
                                    self._on_toggle_fav(kind, pid, name)
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


class DeviceQuickListWidget(QWidget):
    """A small browser tab that shows Favorites or Recents."""

    prefs_changed = pyqtSignal()

    def __init__(
        self,
        mode: str,
        on_add_instrument: Optional[Callable[[str], None]] = None,
        on_add_note_fx: Optional[Callable[[str], None]] = None,
        on_add_audio_fx: Optional[Callable[[str], None]] = None,
        get_add_scope: Optional[Callable[[str], tuple[str, str]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._mode = str(mode or "").lower()  # 'favorites' | 'recents'
        self._on_add_instrument = on_add_instrument
        self._on_add_note_fx = on_add_note_fx
        self._on_add_audio_fx = on_add_audio_fx
        self._get_add_scope = get_add_scope
        self._prefs: Optional[DevicePrefs] = None
        self._build()

    # ---- safety helpers ----
    def _safe(self, fn, *a, **k):  # noqa: ANN001
        try:
            return fn(*a, **k)
        except Exception:
            return None

    def _load_prefs(self) -> DevicePrefs:
        self._prefs = DevicePrefs.load()
        return self._prefs

    # ---- UI ----
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Header row
        h = QHBoxLayout()
        title = "⭐ Favorites" if self._mode == "favorites" else "🕘 Recents"
        self._lbl = QLabel(title)
        self._lbl.setStyleSheet("font-weight:600; color:#eaeaea;")
        h.addWidget(self._lbl, 0)
        h.addStretch(1)

        self._btn_clear = None
        if self._mode == "recents":
            self._btn_clear = QPushButton("Clear")
            self._btn_clear.setToolTip("Alle Recents löschen")
            self._btn_clear.clicked.connect(lambda _=False: self._safe(self._clear_recents_all))
            h.addWidget(self._btn_clear, 0)

        root.addLayout(h)

        # Search row
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen…")
        self.search.textChanged.connect(lambda _t: self._safe(self.reload))
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(lambda _=False: self._safe(self._add_selected))
        self._scope_badge = QLabel("")
        self._scope_badge.setStyleSheet("padding:2px 8px; border:1px solid rgba(255,185,110,120); border-radius:9px; color:#ffd7a3; background:rgba(255,185,110,20); font-weight:600;")
        row.addWidget(self.search, 1)
        row.addWidget(self._scope_badge, 0)
        row.addWidget(self.btn_add, 0)
        root.addLayout(row)

        # List
        self.list = _StarDragQuickList(on_toggle_fav=lambda kind, pid, name: self._safe(self._toggle_favorite, kind, pid, name))
        self.list.itemDoubleClicked.connect(lambda _it: self._safe(self._add_selected))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(lambda _pos: self._safe(self._show_context_menu, _pos))
        try:
            self.list.itemSelectionChanged.connect(lambda: self._safe(self._update_scope_badge))
        except Exception:
            pass
        root.addWidget(self.list, 1)

        hint = QLabel("Tipp: ⭐ links klicken = Favorite. Doppelklick / Add oder Drag&Drop in die Device-Chain.")
        hint.setStyleSheet("color:#9a9a9a;")
        root.addWidget(hint)

        self.reload()
        self._update_scope_badge()


    def _scope_kind(self) -> str:
        try:
            it = self.list.currentItem() if hasattr(self, "list") else None
            if it is None:
                for i in range(self.list.count()):
                    cand = self.list.item(i)
                    payload = cand.data(Qt.ItemDataRole.UserRole) or {}
                    if isinstance(payload, dict) and not payload.get("_section"):
                        it = cand
                        break
            payload = it.data(Qt.ItemDataRole.UserRole) or {} if it is not None else {}
            if isinstance(payload, dict) and not payload.get("_section"):
                return str(payload.get("kind") or "")
        except Exception:
            pass
        return ""

    def _update_scope_badge(self) -> None:
        try:
            kind = self._scope_kind()
            if callable(self._get_add_scope):
                short, tip = self._get_add_scope(kind)
            else:
                short, tip = ("Ziel: Spur", "Browser-Add / Doppelklick / Drag&Drop wirkt auf die aktive Spur.")
            self._scope_badge.setText(str(short or "Ziel: Spur"))
            self._scope_badge.setToolTip(str(tip or ""))
        except Exception:
            pass

    def refresh_scope_badge(self) -> None:
        self._safe(self._update_scope_badge)

    # ---- data → list ----
    def reload(self) -> None:
        prefs = self._load_prefs()
        q = (self.search.text() or "").strip().lower()

        self.list.clear()

        bucket = prefs.favorites if self._mode == "favorites" else prefs.recents

        sections = [
            ("instrument", "🎹 Instruments"),
            ("note_fx", "🎛️ Note-FX"),
            ("audio_fx", "🎚️ Audio-FX"),
            # v0.0.20.397 — External plugin favorites (Plugins Browser tab)
            ("ext_lv2", "🔌 LV2 Plugins"),
            ("ext_ladspa", "🔌 LADSPA Plugins"),
            ("ext_dssi", "🔌 DSSI Plugins"),
            ("ext_vst2", "🔌 VST2 Plugins"),
            ("ext_vst3", "🔌 VST3 Plugins"),
        ]

        any_item = False

        # v0.0.20.399 — Heuristic instrument/effect classification for icons
        _KNOWN_INSTRUMENTS_LC = {
            "helm", "surge xt", "dexed", "vital", "ob-xd", "obxd", "zynaddsubfx",
            "yoshimi", "amsynth", "synthv1", "padthv1", "drumkv1", "samplv1",
            "odin2", "monique", "cardinal", "pianoteq", "kontakt",
            "sfizz", "linuxsampler", "fluidsynth", "wolpertinger",
            "jackass", "oxevst",
        }
        _EFFECT_KEYWORDS_LC = {
            "effect", "filter", "compressor", "reverb", "delay", "eq ",
            "chorus", "distort", "limiter", "phaser", "flanger", "gate",
            "autogain", "de-esser", "saturator", "amplifier", "balance",
            " mono", " stereo", "analyzer", "analyser", "meter", "counter",
        }

        def _type_icon(kind: str, name: str, pid: str) -> str:
            """Return 🎹 for instruments, 🎚️ for effects, based on kind + name heuristics."""
            if kind == "instrument":
                return "🎹"
            if kind in ("note_fx", "audio_fx"):
                return "🎚️"
            # ext_* plugins: use name heuristics
            nl = (name or "").lower().strip()
            pl = (pid or "").lower()
            haystack = f"{nl} {pl}"
            # Check effect keywords first
            for kw in _EFFECT_KEYWORDS_LC:
                if kw in haystack:
                    return "🎚️"
            # Check known instruments
            for inst in _KNOWN_INSTRUMENTS_LC:
                if inst in haystack:
                    return "🎹"
            # Default: plugin icon
            return "🔌"

        for kind, label in sections:
            entries = list(bucket.get(kind, []) or [])
            if not entries:
                continue

            # section header
            sec = QListWidgetItem(label)
            sec.setFlags(Qt.ItemFlag.NoItemFlags)
            sec.setData(Qt.ItemDataRole.UserRole, {"_section": True})
            self.list.addItem(sec)

            for e in entries:
                name = str(getattr(e, "name", "") or "")
                pid = str(getattr(e, "plugin_id", "") or "")
                if not pid:
                    continue
                hay = f"{name} {pid} {kind}".lower()
                if q and q not in hay:
                    continue
                fav = True if self._mode == "favorites" else bool(prefs.is_favorite(kind, pid))
                star = "★" if fav else "☆"
                icon = _type_icon(kind, name, pid)
                it = QListWidgetItem(f"{star}  {icon} {name}   —   {pid}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": kind, "plugin_id": pid, "name": name, "favorite": fav})
                self.list.addItem(it)
                any_item = True

        self.btn_add.setEnabled(any_item)
        self._update_scope_badge()
        if self._btn_clear is not None:
            self._btn_clear.setEnabled(True)

    # ---- actions ----
    def _add_selected(self) -> None:
        it = self.list.currentItem()
        if it is None:
            # pick first non-section
            for i in range(self.list.count()):
                cand = self.list.item(i)
                payload = cand.data(Qt.ItemDataRole.UserRole) or {}
                if isinstance(payload, dict) and not payload.get("_section"):
                    it = cand
                    break
        if it is None:
            return

        payload = it.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict) or payload.get("_section"):
            return

        kind = str(payload.get("kind") or "")
        pid = str(payload.get("plugin_id") or "")
        name = str(payload.get("name") or "")
        if not pid:
            return

        # bump recent on use
        try:
            prefs = self._load_prefs()
            prefs.add_recent(kind, pid, name)
            prefs.save()
            self.prefs_changed.emit()
        except Exception:
            pass

        if kind == "instrument" and self._on_add_instrument is not None:
            self._on_add_instrument(pid)
        elif kind == "note_fx" and self._on_add_note_fx is not None:
            self._on_add_note_fx(pid)
        elif kind == "audio_fx" and self._on_add_audio_fx is not None:
            self._on_add_audio_fx(pid)
        elif kind.startswith("ext_") and self._on_add_audio_fx is not None:
            # v0.0.20.410 — External plugins: convert kind+pid to proper device plugin_id
            # kind "ext_vst2" + pid "/usr/lib/vst/Dexed.so" → "ext.vst2:/usr/lib/vst/Dexed.so"
            ext_kind = kind.replace("ext_", "")  # "vst2", "vst3", "lv2", etc.
            device_pid = f"ext.{ext_kind}:{pid}"
            self._on_add_audio_fx(device_pid)

    def _clear_recents_all(self) -> None:
        prefs = self._load_prefs()
        for k in ("instrument", "note_fx", "audio_fx",
                   "ext_lv2", "ext_ladspa", "ext_dssi", "ext_vst2", "ext_vst3"):
            prefs.clear_recents(k)
        prefs.save()
        self.reload()
        try:
            self.prefs_changed.emit()
        except Exception:
            pass

    def _toggle_favorite(self, kind: str, pid: str, name: str) -> None:
        prefs = self._load_prefs()
        prefs.toggle_favorite(kind, pid, name)
        prefs.save()
        self.reload()
        try:
            self.prefs_changed.emit()
        except Exception:
            pass

    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        it = self.list.itemAt(pos)
        if it is None:
            return
        payload = it.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict) or payload.get("_section"):
            return

        kind = str(payload.get("kind") or "")
        pid = str(payload.get("plugin_id") or "")
        name = str(payload.get("name") or "")
        if not pid:
            return

        m = QMenu(self)
        if self._mode == "favorites":
            a = m.addAction("⭐ Remove from Favorites")
        else:
            a = m.addAction("⭐ Toggle Favorite")

        a.triggered.connect(lambda _=False: self._safe(self._toggle_favorite, kind, pid, name))

        m.exec(self.list.mapToGlobal(pos))
