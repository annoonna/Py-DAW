# -*- coding: utf-8 -*-
"""Plugins Browser (LV2/LADSPA/DSSI/VST).

SAFE / NON-DESTRUCTIVE
----------------------
This widget lists external plugins installed on the system.
Discovery stays UI-only; live hosting happens later in the device chain.

Features:
- Tabs per plugin type
- Search + "Only Favorites"
- ⭐ Favorites (stored in existing device_prefs.json, under ext_* keys)
- Cache + async rescan
- Context menu (copy id/path, open folder)
- Paths dialog (QSettings overrides)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QMimeData, QThread, Signal, QObject, QUrl
from PySide6.QtGui import QDrag, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QListWidget, QListWidgetItem, QMenu, QCheckBox, QMessageBox
)

from .device_prefs import DevicePrefs
from .plugin_paths_dialog import PluginPathsDialog
from ..services import plugin_scanner

# NOTE:
# We intentionally use the **existing** device DnD mime so the DevicePanel
# can accept drops without any risky refactors.
_MIME = "application/x-pydaw-plugin"

# Legacy/Reserved (kept for future): a dedicated ext-plugin mime.
_MIME_EXT = "application/x-pydaw-ext-plugin"




def _external_device_kind(ext_payload: dict) -> str:
    """Return the semantic device kind for an external plugin entry.

    Safe foundation for future SmartDrop work: we keep the existing insert path
    unchanged, but carry the instrument/effect capability alongside the drag/add
    payload so targets can make better decisions later without re-probing.
    """
    try:
        return "instrument" if bool(ext_payload.get("is_instrument", False)) else "audio_fx"
    except Exception:
        return "audio_fx"


def _build_external_device_payload(ext_payload: dict) -> Optional[dict]:
    try:
        if not isinstance(ext_payload, dict):
            return None
        ext_id = str(ext_payload.get("plugin_id") or "")
        name = str(ext_payload.get("name") or "")
        ext_kind = str(ext_payload.get("kind") or "")
        path = str(ext_payload.get("path") or "")
        plugin_name = str(ext_payload.get("plugin_name") or "")
        is_inst = bool(ext_payload.get("is_instrument", False))
        if not ext_id:
            return None
        dev_pid = f"ext.{ext_kind}:{ext_id}" if ext_kind else f"ext:{ext_id}"
        params = {
            "__ext_kind": ext_kind,
            "__ext_id": ext_id,
            "__ext_ref": ext_id,
            "__ext_path": path,
            "__ext_is_instrument": is_inst,
        }
        if plugin_name:
            params["__ext_plugin_name"] = plugin_name
        return {
            # Keep the existing safe insert path unchanged for now.
            "kind": "audio_fx",
            # Semantic role for future SmartDrop/target-side decisions.
            "device_kind": _external_device_kind(ext_payload),
            "plugin_id": dev_pid,
            "name": name,
            "params": params,
            "is_instrument": is_inst,
        }
    except Exception:
        return None

class _StarDragList(QListWidget):
    """List with a left-star hitbox for favorites + drag payload."""

    def __init__(self, kind_key: str, on_toggle_fav=None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self.kind_key = str(kind_key)
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
                                    self._on_toggle_fav(self.kind_key, pid, name)
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
            device_payload = _build_external_device_payload(payload)
            if not isinstance(device_payload, dict):
                return
            md = QMimeData()
            md.setData(_MIME, json.dumps(device_payload).encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            return


class _ScanWorker(QObject):
    finished = Signal(dict)
    status = Signal(str)

    def __init__(self, extra_paths: Dict[str, List[str]]):
        super().__init__()
        self._extra_paths = extra_paths

    def run(self) -> None:
        try:
            self.status.emit("Scanning plugins…")
        except Exception:
            pass
        try:
            res = plugin_scanner.scan_all(self._extra_paths)
        except Exception:
            res = {}
        try:
            try:
                plugin_scanner.save_cache(res)
            except Exception:
                pass
            self.finished.emit(res)
        except Exception:
            pass


class PluginsBrowserWidget(QWidget):
    prefs_changed = Signal()

    def __init__(self, on_add_audio_fx=None, get_add_scope: Optional[Callable[[str], tuple[str, str]]] = None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self._on_add_audio_fx = on_add_audio_fx
        self._get_add_scope = get_add_scope
        self._data: Dict[str, List[plugin_scanner.ExtPlugin]] = {}
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ScanWorker] = None
        self._build()
        self._load_cache_fast()
        if not self._data or not plugin_scanner.cache_is_fresh(max_age_seconds=3600 * 4):
            self.rescan(async_=True)
        else:
            total = sum(len(v) for v in self._data.values())
            self._set_status(
                f"Cache geladen: {total} Plugins. Klicke 'Rescan' um den Plugin-Scan zu aktualisieren."
            )

    def _safe(self, fn, *a, **k):  # noqa: ANN001
        try:
            return fn(*a, **k)
        except Exception:
            return None

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QLabel("Plugins")
        header.setObjectName("pluginsBrowserTitle")

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen… (LV2 / LADSPA / DSSI / VST)")
        self.search.textChanged.connect(lambda _t: self._safe(self._refilter_all))

        self.only_favs = QCheckBox("Only Favorites")
        self.only_favs.stateChanged.connect(lambda _v: self._safe(self._refilter_all))

        # v0.0.20.406: Instrument/Effect filter
        from PySide6.QtWidgets import QComboBox
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "🎹 Instruments", "🔊 Effects"])
        self.type_filter.setCurrentIndex(0)
        self.type_filter.currentIndexChanged.connect(lambda _i: self._safe(self._refilter_all))

        self.btn_add = QPushButton("Add to Device")
        self.btn_add.clicked.connect(lambda _=False: self._safe(self._add_selected))

        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.clicked.connect(lambda _=False: self._safe(self.rescan, True))

        self.btn_paths = QPushButton("Paths…")
        self.btn_paths.clicked.connect(lambda _=False: self._safe(self._open_paths_dialog))

        self._scope_badge = QLabel("")
        self._scope_badge.setStyleSheet(
            "padding:2px 8px; border:1px solid rgba(255,185,110,120); border-radius:9px; "
            "color:#ffd7a3; background:rgba(255,185,110,20); font-weight:600;"
        )

        row.addWidget(self.search, 1)
        row.addWidget(self.type_filter, 0)
        row.addWidget(self.only_favs, 0)
        row.addWidget(self._scope_badge, 0)
        row.addWidget(self.btn_add, 0)
        row.addWidget(self.btn_rescan, 0)
        row.addWidget(self.btn_paths, 0)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        self.list_lv2 = _StarDragList("ext_lv2", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_ladspa = _StarDragList("ext_ladspa", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_dssi = _StarDragList("ext_dssi", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_vst2 = _StarDragList("ext_vst2", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_vst3 = _StarDragList("ext_vst3", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))
        self.list_clap = _StarDragList("ext_clap", on_toggle_fav=lambda k, pid, nm: self._safe(self._toggle_favorite, k, pid, nm))

        for lst in (self.list_lv2, self.list_ladspa, self.list_dssi, self.list_vst2, self.list_vst3, self.list_clap):
            lst.itemDoubleClicked.connect(lambda _it, _lst=lst: self._safe(self._add_selected, _lst))
            lst.customContextMenuRequested.connect(lambda pos, _lst=lst: self._safe(self._context_menu, _lst, pos))
            try:
                lst.itemSelectionChanged.connect(lambda _lst=lst: self._safe(self._update_scope_badge))
            except Exception:
                pass

        self.tabs.addTab(self.list_lv2, "LV2")
        self.tabs.addTab(self.list_ladspa, "LADSPA")
        self.tabs.addTab(self.list_dssi, "DSSI")
        self.tabs.addTab(self.list_vst2, "VST2")
        self.tabs.addTab(self.list_vst3, "VST3")
        self.tabs.addTab(self.list_clap, "CLAP")
        try:
            self.tabs.currentChanged.connect(lambda _i: self._safe(self._update_scope_badge))
        except Exception:
            pass

        self.status = QLabel("")
        self.status.setStyleSheet("color:#9a9a9a;")
        self.status.setWordWrap(True)
        self._set_status(
            "Hinweis: Externe Plugins können direkt in die Audio-FX Device-Chain eingefügt werden. "
            "LV2 benötigt python-lilv, VST2/VST3 benötigen pedalboard. "
            "Mehrfach-Bundles werden bei verfügbarem pedalboard als einzelne Plugin-Varianten angezeigt."
        )

        root.addWidget(header)
        root.addLayout(row)
        root.addWidget(self.tabs, 1)
        root.addWidget(self.status)

    def _current_payload(self) -> Optional[dict]:
        try:
            lst = self.tabs.currentWidget()
            if not isinstance(lst, QListWidget):
                return None
            it = lst.currentItem()
            if it is None:
                for i in range(lst.count()):
                    cand = lst.item(i)
                    payload = cand.data(Qt.ItemDataRole.UserRole) or {}
                    if isinstance(payload, dict):
                        return payload
                return None
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _update_scope_badge(self) -> None:
        try:
            payload = self._current_payload() or {}
            semantic_kind = _external_device_kind(payload)
            if callable(self._get_add_scope):
                short, tip = self._get_add_scope(semantic_kind)
            else:
                short, tip = ("Ziel: Spur", "Browser-Add / Doppelklick / Drag&Drop wirkt auf die aktive Spur.")
            if semantic_kind == "instrument":
                tip = (str(tip or "") + "\nExterne Instrumente bleiben im aktuellen Safe-Pfad, tragen aber jetzt ihre Instrument-Metadaten für spätere SmartDrop-Ziele mit.").strip()
            self._scope_badge.setText(str(short or "Ziel: Spur"))
            self._scope_badge.setToolTip(str(tip or ""))
        except Exception:
            try:
                self._scope_badge.setText("Ziel: Spur")
                self._scope_badge.setToolTip("")
            except Exception:
                pass

    def refresh_scope_badge(self) -> None:
        self._safe(self._update_scope_badge)

    def _set_status(self, text: str) -> None:
        try:
            self.status.setText(str(text))
        except Exception:
            pass

    def _load_cache_fast(self) -> None:
        try:
            cached = plugin_scanner.load_cache() or {}
        except Exception:
            cached = {}
        if cached:
            self._data = cached
            self._refilter_all()
            total = sum(len(v) for v in cached.values())
            self._set_status(f"Cache geladen: {total} Plugins. (Rescan aktualisiert)")
            self._update_scope_badge()

    def _gather_extra_paths(self) -> Dict[str, List[str]]:
        from PySide6.QtCore import QSettings
        from ..core.settings import SettingsKeys

        s = QSettings(SettingsKeys.organization, SettingsKeys.application)
        out: Dict[str, List[str]] = {}
        for kind in ("lv2", "ladspa", "dssi", "vst2", "vst3", "clap"):
            key = f"plugins/paths/{kind}"
            val = s.value(key, [])
            paths: List[str] = []
            if isinstance(val, (list, tuple)):
                paths = [str(x) for x in val if str(x).strip()]
            elif isinstance(val, str) and val.strip():
                paths = [val.strip()]
            if paths:
                out[kind] = paths
        return out

    def rescan(self, async_: bool = True) -> None:
        try:
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait(200)
        except Exception:
            pass
        self._thread = None
        self._worker = None

        extra = self._gather_extra_paths()

        if not async_:
            try:
                self._set_status("Scanning plugins…")
                res = plugin_scanner.scan_all(extra)
                try:
                    plugin_scanner.save_cache(res)
                except Exception:
                    pass
                self._on_scan_finished(res)
            except Exception:
                self._set_status("Scan fehlgeschlagen.")
            return

        try:
            self.btn_rescan.setEnabled(False)
        except Exception:
            pass

        t = QThread(self)
        w = _ScanWorker(extra)
        w.moveToThread(t)
        t.started.connect(w.run)
        w.finished.connect(self._on_scan_finished)
        w.status.connect(lambda msg: self._set_status(msg))
        w.finished.connect(lambda _res: self._safe(self._cleanup_thread))
        t.start()

        self._thread = t
        self._worker = w

    def _cleanup_thread(self) -> None:
        try:
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait(500)
        except Exception:
            pass
        try:
            if self._worker is not None:
                self._worker.deleteLater()
        except Exception:
            pass
        try:
            if self._thread is not None:
                self._thread.deleteLater()
        except Exception:
            pass
        self._thread = None
        self._worker = None
        try:
            self.btn_rescan.setEnabled(True)
        except Exception:
            pass

    def _on_scan_finished(self, res: dict) -> None:
        try:
            data: Dict[str, List[plugin_scanner.ExtPlugin]] = {}
            for k, arr in (res or {}).items():
                if isinstance(arr, list):
                    data[str(k)] = [x for x in arr if isinstance(x, plugin_scanner.ExtPlugin)]
            self._data = data
            self._refilter_all()
            total = sum(len(v) for v in data.values())
            # LV2 hosting availability hint (safe)
            lv2_hint = "LV2 Host: unbekannt"
            try:
                from pydaw.audio import lv2_host
                if lv2_host.is_available():
                    lv2_hint = "LV2 Host: OK (Audio‑FX live)"
                else:
                    lv2_hint = "LV2 Host: " + str(lv2_host.availability_hint())
            except Exception:
                pass

            clap_hint = ""
            try:
                from pydaw.audio import clap_host
                clap_hint = clap_host.availability_hint()
            except Exception:
                clap_hint = "CLAP Host: unbekannt"

            self._set_status(
                f"Scan fertig: {total} Plugins (LV2 {len(data.get('lv2', []))}, "
                f"LADSPA {len(data.get('ladspa', []))}, DSSI {len(data.get('dssi', []))}, "
                f"VST2 {len(data.get('vst2', []))}, VST3 {len(data.get('vst3', []))}, "
                f"CLAP {len(data.get('clap', []))}). "
                f"{lv2_hint}. {clap_hint}. "
                "VST2/VST3 über pedalboard/ctypes; LV2 über python-lilv; LADSPA/DSSI live; CLAP über ctypes."
            )

            # v0.0.20.718: Also trigger Rust-native scanner if engine is connected.
            # This is purely additive — Python scan results are untouched.
            self._trigger_rust_scan_if_available()

        except Exception:
            self._set_status("Scan fertig (mit Fehlern).")

    # -- v0.0.20.718: Rust Plugin Scanner Integration (P7) -----------------

    def _trigger_rust_scan_if_available(self) -> None:
        """Connect to Rust engine if available, trigger scan, show status.

        v0.0.20.725: Actually triggers ScanPlugins + wires result handler.
        Results are merged into the Python scan data (additive, no duplicates).
        """
        try:
            import os
            from pydaw.services.rust_engine_bridge import RustEngineBridge
            if not RustEngineBridge.is_enabled():
                return
            bridge = RustEngineBridge.instance()

            # If not connected, try to connect to an already-running engine
            if not bridge.is_connected:
                socket_path = "/tmp/pydaw_engine.sock"
                if os.path.exists(socket_path):
                    connected = bridge._connect()
                    if not connected:
                        current = self.status.text() or ""
                        if "\n🦀" not in current:
                            self._set_status(
                                current +
                                "\n🦀 Rust Engine: Socket vorhanden, Verbindung fehlgeschlagen."
                            )
                        return

            if bridge.is_connected:
                # Wire up result handler (safe — multiple connects are OK)
                try:
                    bridge.plugin_scan_result.connect(
                        self._on_rust_scan_result,
                        type=Qt.ConnectionType.UniqueConnection,
                    )
                except Exception:
                    pass  # Already connected or Qt error

                # Trigger scan
                try:
                    bridge.scan_plugins()
                    current = self.status.text() or ""
                    if "\n🦀" not in current:
                        self._set_status(
                            current +
                            "\n🦀 Rust Engine: ✅ Verbunden — Scan gestartet…"
                        )
                except Exception:
                    current = self.status.text() or ""
                    if "\n🦀" not in current:
                        self._set_status(
                            current +
                            "\n🦀 Rust Engine: ✅ Verbunden (Scan konnte nicht gestartet werden)."
                        )
        except Exception:
            pass

    def _on_rust_scan_result(self, plugins: list, scan_time_ms: int,
                              errors: list) -> None:
        """Handle Rust scanner results — merge into browser data + update status.

        v0.0.20.725: Actually merges Rust-found plugins into browser display.
        Rust results are ADDITIVE — they supplement the Python scan, not replace it.
        Duplicates (same path) are skipped.
        """
        try:
            n = len(plugins) if plugins else 0
            n_vst3 = sum(1 for p in (plugins or [])
                         if isinstance(p, dict) and p.get("format") == "vst3")
            n_clap = sum(1 for p in (plugins or [])
                         if isinstance(p, dict) and p.get("format") == "clap")
            n_lv2 = sum(1 for p in (plugins or [])
                        if isinstance(p, dict) and p.get("format") == "lv2")
            n_err = len(errors) if errors else 0

            # Merge Rust results into Python data (additive)
            n_added = 0
            for p in (plugins or []):
                if not isinstance(p, dict):
                    continue
                try:
                    fmt = str(p.get("format", ""))
                    name = str(p.get("name", ""))
                    path = str(p.get("path", ""))
                    pid = str(p.get("plugin_id", "")) or path
                    is_inst = bool(p.get("is_instrument", False))

                    if fmt not in self._data:
                        self._data[fmt] = []

                    # Check for duplicates (by path)
                    existing_paths = {ep.path for ep in self._data.get(fmt, [])}
                    existing_pids = {ep.plugin_id for ep in self._data.get(fmt, [])}
                    if path in existing_paths or pid in existing_pids:
                        continue

                    from pydaw.services.plugin_scanner import ExtPlugin
                    self._data[fmt].append(ExtPlugin(
                        kind=fmt,
                        plugin_id=pid,
                        name=name or pid,
                        path=path,
                        is_instrument=is_inst,
                    ))
                    n_added += 1
                except Exception:
                    continue

            if n_added > 0:
                self._refilter_all()

            # Update status
            current = self.status.text() or ""
            rust_info = (
                f"\n🦀 Rust Scanner: {n} Plugins "
                f"(VST3 {n_vst3}, CLAP {n_clap}, LV2 {n_lv2}) "
                f"in {scan_time_ms}ms"
            )
            if n_added > 0:
                rust_info += f" — {n_added} neue hinzugefügt"
            if n_err > 0:
                rust_info += f" — {n_err} Fehler"
            rust_info += "."

            # Remove old Rust info if present
            if "\n🦀 Rust Scanner:" in current:
                current = current.split("\n🦀 Rust Scanner:")[0]
            if "\n🦀 Rust Engine:" in current:
                current = current.split("\n🦀 Rust Engine:")[0]

            self._set_status(current + rust_info)
        except Exception:
            pass

    def _toggle_favorite(self, kind_key: str, plugin_id: str, name: str) -> None:
        try:
            prefs = DevicePrefs.load()
            prefs.toggle_favorite(str(kind_key), str(plugin_id), str(name))
            prefs.save()
            self._refilter_all()
            try:
                self.prefs_changed.emit()
            except Exception:
                pass
        except Exception:
            pass

    def _add_selected(self, lst: Optional[QListWidget] = None) -> None:
        try:
            lst = lst or self.tabs.currentWidget()
            if not isinstance(lst, QListWidget):
                return
            it = lst.currentItem()
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return

            # v0.0.20.725: Warn if plugin is blacklisted
            if payload.get("blacklisted"):
                try:
                    from PySide6.QtWidgets import QMessageBox
                    reply = QMessageBox.warning(
                        self,
                        "Plugin geblacklistet",
                        f"Das Plugin \"{payload.get('name', '?')}\" hat beim letzten "
                        f"Laden die DAW zum Absturz gebracht und wurde blockiert.\n\n"
                        f"Trotzdem laden? (Kann zum Absturz führen!)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        self._set_status("Plugin-Einfügung abgebrochen (blacklisted)")
                        return
                    # User wants to try anyway — clear from blacklist
                    try:
                        from pydaw.services.plugin_probe import clear_blacklist_entry
                        _path = str(payload.get("path") or payload.get("plugin_id") or "")
                        _kind = str(payload.get("kind") or "vst3")
                        _pname = str(payload.get("plugin_name") or "")
                        _pid = str(payload.get("plugin_id") or "")
                        clear_blacklist_entry(_path, _kind, _pname, _pid)
                    except Exception:
                        pass
                except ImportError:
                    pass

            kind_key = str(payload.get("kind_key") or "")
            ext_id = str(payload.get("plugin_id") or "")
            name = str(payload.get("name") or "")
            if not ext_id:
                return
            prefs = DevicePrefs.load()
            prefs.add_recent(kind_key or "ext", ext_id, name)
            prefs.save()

            device_payload = _build_external_device_payload(payload) or {}
            dev_pid = str(device_payload.get("plugin_id") or "")
            params = dict(device_payload.get("params") or {})
            ext_kind = str(payload.get("kind") or "")
            device_kind = str(device_payload.get("device_kind") or "audio_fx")

            # Keep current safe insert path. The semantic role is carried in the
            # payload (`device_kind` / `__ext_is_instrument`) for future SmartDrop
            # target logic and for avoiding extra host re-probes.
            if self._on_add_audio_fx is not None:
                try:
                    self._on_add_audio_fx(dev_pid, name, params)
                    role = "Instrument" if device_kind == "instrument" else "Effect"
                    msg = f"Added to Device: {name} — {role}"
                    if ext_kind == "lv2":
                        try:
                            from pydaw.audio import lv2_host
                            if lv2_host.is_available():
                                msg += " — LV2 live OK"
                            else:
                                msg += " — LV2 no-op (python-lilv fehlt)"
                        except Exception:
                            msg += " — LV2 (Status unbekannt)"
                    elif ext_kind in ("ladspa", "dssi"):
                        msg += f" — {ext_kind.upper()} live OK"
                    elif ext_kind in ("vst3", "vst2"):
                        try:
                            from pydaw.audio import vst3_host
                            if vst3_host.is_available():
                                msg += f" — {ext_kind.upper()} live OK ({vst3_host.availability_hint()})"
                            else:
                                msg += f" — {ext_kind.upper()} no-op ({vst3_host.availability_hint()})"
                        except Exception:
                            msg += f" — {ext_kind.upper()} (Status unbekannt)"
                    elif ext_kind == "clap":
                        try:
                            from pydaw.audio import clap_host
                            msg += f" — CLAP live OK ({clap_host.availability_hint()})"
                        except Exception:
                            msg += " — CLAP (Status unbekannt)"
                    else:
                        msg += " — Status unbekannt"
                    self._set_status(msg)
                    return
                except TypeError:
                    # Backward compatible: callback might only accept (plugin_id)
                    try:
                        self._on_add_audio_fx(dev_pid)
                        role = "Instrument" if device_kind == "instrument" else "Effect"
                        msg = f"Added to Device: {name} — {role}"
                        if ext_kind == "lv2":
                            try:
                                from pydaw.audio import lv2_host
                                if lv2_host.is_available():
                                    msg += " — LV2 live OK"
                                else:
                                    msg += " — LV2 no-op (python-lilv fehlt)"
                            except Exception:
                                msg += " — LV2 (Status unbekannt)"
                        elif ext_kind in ("ladspa", "dssi"):
                            msg += f" — {ext_kind.upper()} live OK"
                        elif ext_kind in ("vst3", "vst2"):
                            try:
                                from pydaw.audio import vst3_host
                                if vst3_host.is_available():
                                    msg += f" — {ext_kind.upper()} live OK"
                                else:
                                    msg += f" — {ext_kind.upper()} no-op ({vst3_host.availability_hint()})"
                            except Exception:
                                msg += f" — {ext_kind.upper()} (Status unbekannt)"
                        elif ext_kind == "clap":
                            try:
                                from pydaw.audio import clap_host
                                msg += f" — CLAP live OK ({clap_host.availability_hint()})"
                            except Exception:
                                msg += " — CLAP (Status unbekannt)"
                        else:
                            msg += " — Status unbekannt"
                        self._set_status(msg)
                        return
                    except Exception:
                        pass
                except Exception:
                    pass

            role = "Instrument" if device_kind == "instrument" else "Effekt"
            self._set_status(f"Ausgewählt: {name} — {role}")
        except Exception:
            pass

    def _context_menu(self, lst: QListWidget, pos) -> None:  # noqa: ANN001
        try:
            it = lst.itemAt(pos)
            if it is None:
                return
            payload = it.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(payload, dict):
                return
            pid = str(payload.get("plugin_id") or "")
            name = str(payload.get("name") or "")
            kind_key = str(payload.get("kind_key") or "")
            path = str(payload.get("path") or "")
            if not pid:
                return

            prefs = DevicePrefs.load()
            fav = bool(prefs.is_favorite(kind_key, pid))

            m = QMenu(self)

            a_add = m.addAction("Add to Device")
            a_add.triggered.connect(lambda _=False: self._safe(self._add_selected, lst))
            m.addSeparator()

            a_fav = m.addAction("⭐ Remove from Favorites" if fav else "⭐ Add to Favorites")
            a_fav.triggered.connect(lambda _=False: self._safe(self._toggle_favorite, kind_key, pid, name))
            m.addSeparator()
            a_copy_id = m.addAction("Copy ID")
            a_copy_id.triggered.connect(lambda _=False: self._safe(self._copy_to_clipboard, pid))

            # Offline debug helper (LV2 only): render an audio file through this plugin.
            if str(payload.get("kind") or "") == "lv2":
                try:
                    from PySide6.QtWidgets import QFileDialog
                    a_off = m.addAction("Offline: Render WAV through LV2…")
                    def _do_offline(_=False, _pid=pid, _name=name):
                        try:
                            from pydaw.audio.lv2_host import offline_process_wav_subprocess
                        except Exception:
                            try:
                                QMessageBox.information(self, "LV2", "LV2 Hosting ist nicht verfügbar.")
                            except Exception:
                                pass
                            return
                        try:
                            uri = str(_pid)
                            if not uri:
                                return
                            in_path, _ = QFileDialog.getOpenFileName(
                                self, "Input Audio wählen", str(Path.home()),
                                "Audio (*.wav *.flac *.ogg *.aiff *.aif);;All (*.*)"
                            )
                            if not in_path:
                                return
                            p_in = Path(in_path)
                            out_suggest = str(p_in.with_name(p_in.stem + f"_{_name or 'lv2'}_out.wav"))
                            out_path, _ = QFileDialog.getSaveFileName(self, "Output WAV speichern", out_suggest, "WAV (*.wav)")
                            if not out_path:
                                return
                            ok, msg = offline_process_wav_subprocess(uri=uri, in_path=in_path, out_path=out_path)
                            if ok:
                                QMessageBox.information(self, "LV2 Offline Render", f"OK: {Path(out_path).name}")
                            else:
                                QMessageBox.warning(self, "LV2 Offline Render", str(msg))
                        except Exception as e:
                            try:
                                QMessageBox.warning(self, "LV2 Offline Render", str(e))
                            except Exception:
                                pass
                    a_off.triggered.connect(_do_offline)
                    m.addSeparator()
                except Exception:
                    pass
            if path:
                a_copy_path = m.addAction("Copy Path")
                a_copy_path.triggered.connect(lambda _=False: self._safe(self._copy_to_clipboard, path))
                a_open = m.addAction("Open in File Manager")
                a_open.triggered.connect(lambda _=False: self._safe(self._open_in_file_manager, path))
            m.exec(lst.mapToGlobal(pos))
        except Exception:
            pass

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            QGuiApplication.clipboard().setText(str(text))
            self._set_status("Copied to clipboard.")
        except Exception:
            pass

    def _open_in_file_manager(self, path: str) -> None:
        try:
            p = Path(path)
            if p.is_file():
                p = p.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        except Exception:
            pass

    def _open_paths_dialog(self) -> None:
        try:
            dlg = PluginPathsDialog(self)
            if dlg.exec():
                self.rescan(async_=True)
        except Exception:
            QMessageBox.information(self, "Plugins", "Paths dialog failed.")

    def _refilter_all(self) -> None:
        q = (self.search.text() or "").strip().lower()
        only_favs = bool(self.only_favs.isChecked())
        # v0.0.20.406: Instrument/Effect filter (0=All, 1=Instruments, 2=Effects)
        type_idx = int(self.type_filter.currentIndex()) if hasattr(self, 'type_filter') else 0
        try:
            prefs = DevicePrefs.load()
        except Exception:
            prefs = None

        # v0.0.20.725: Load blacklist for badge display
        _bl_check = None
        try:
            from pydaw.services.plugin_probe import is_blacklisted as _bl_check_fn
            _bl_check = _bl_check_fn
        except ImportError:
            pass

        def fill(lst: _StarDragList, kind: str, kind_key: str) -> None:
            lst.clear()
            arr = self._data.get(kind, []) or []
            for p in arr:
                try:
                    pid = str(p.plugin_id)
                    path = str(p.path or "")
                    plugin_name = ""
                    if kind in ("vst3", "vst2"):
                        try:
                            from pydaw.audio.vst3_host import split_plugin_reference
                            dec_path, dec_name = split_plugin_reference(pid)
                            if dec_path and not path:
                                path = dec_path
                            plugin_name = dec_name
                        except Exception:
                            plugin_name = ""
                    elif kind == "clap":
                        try:
                            from pydaw.audio.clap_host import split_plugin_reference as clap_split
                            dec_path, dec_name = clap_split(pid)
                            if dec_path and not path:
                                path = dec_path
                            plugin_name = dec_name
                        except Exception:
                            plugin_name = ""
                    name = str(p.name or plugin_name or pid)
                    shown_id = path or pid
                    if os.path.sep in shown_id:
                        try:
                            shown_id = Path(shown_id).name
                        except Exception:
                            pass
                    hay = f"{name} {plugin_name} {pid} {path}".lower()
                    if q and q not in hay:
                        continue
                    # v0.0.20.406: Instrument/Effect type filter
                    is_inst = bool(getattr(p, "is_instrument", False))
                    if type_idx == 1 and not is_inst:
                        continue  # Only instruments
                    if type_idx == 2 and is_inst:
                        continue  # Only effects
                    fav = bool(prefs and prefs.is_favorite(kind_key, pid))
                    if only_favs and not fav:
                        continue
                    star = "★" if fav else "☆"
                    # v0.0.20.406: Instrument/Effect icon
                    is_inst = bool(getattr(p, "is_instrument", False))
                    type_icon = "🎹" if is_inst else "🔊"

                    # v0.0.20.725: Blacklist badge
                    _is_bl = False
                    if _bl_check is not None:
                        try:
                            _is_bl = _bl_check(path or pid, kind, plugin_name, pid)
                        except Exception:
                            pass

                    if _is_bl:
                        label = f"💀 {star} {type_icon} {name}   —   {shown_id}  [BLACKLISTED]"
                    else:
                        label = f"{star} {type_icon} {name}   —   {shown_id}"

                    it = QListWidgetItem(label)
                    it.setData(
                        Qt.ItemDataRole.UserRole,
                        {
                            "kind": kind,
                            "kind_key": kind_key,
                            "plugin_id": pid,
                            "name": name,
                            "path": path,
                            "plugin_name": plugin_name,
                            "favorite": fav,
                            "is_instrument": is_inst,
                            "blacklisted": _is_bl,
                        },
                    )

                    # v0.0.20.725: Dim blacklisted plugins
                    if _is_bl:
                        try:
                            from PySide6.QtGui import QColor
                            it.setForeground(QColor(120, 120, 120))
                        except Exception:
                            pass

                    lst.addItem(it)
                except Exception:
                    continue

        fill(self.list_lv2, "lv2", "ext_lv2")
        fill(self.list_ladspa, "ladspa", "ext_ladspa")
        fill(self.list_dssi, "dssi", "ext_dssi")
        fill(self.list_vst2, "vst2", "ext_vst2")
        fill(self.list_vst3, "vst3", "ext_vst3")
        fill(self.list_clap, "clap", "ext_clap")
        self._update_scope_badge()
