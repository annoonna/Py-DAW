"""Arranger view: track list + scrollable canvas + automation panel.

v0.0.19.7.39:
- Drag&Drop Overlay Clip-Launcher Grid (from Browser Sample drag)
- Overlay accepts drops ONLY while active to avoid collisions with Arranger logic

v0.0.20.86:
- TrackList: Drag&Drop support for cross-project track transfer
  Drag a track from one project tab's TrackList to another tab's ArrangerCanvas.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QLabel,
    QToolButton,
    QComboBox,
    QAbstractItemView,
    QMenu,
    QWidgetAction,
    QLineEdit,
    QInputDialog,
    QApplication,
    QFrame,
    QToolTip,
)
from PySide6.QtCore import Qt, Signal, QEvent, QMimeData, QObject, QPoint
from PySide6.QtGui import QDrag

from pydaw.ui.cross_project_drag import MIME_CROSS_PROJECT, create_track_drag_data
from pydaw.ui.smartdrop_rules import evaluate_plugin_drop_target

MIME_TRACKLIST_REORDER = "application/x-pydaw-tracklist-reorder"
MIME_PLUGIN_DRAG_PREVIEW = "application/x-pydaw-plugin"


class ArrangerTrackListWidget(QListWidget):
    """QListWidget with safe in-place reorder support for arranger tracks.

    Keeps the existing cross-project drag MIME intact and only intercepts
    same-widget drops that carry our internal reorder MIME payload.
    """

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        try:
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
        except Exception:
            pass

    def dragEnterEvent(self, event):  # noqa: ANN001
        try:
            md = event.mimeData()
            if md and md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                blocked_message = ""
                getattr(self._owner, "_handle_plugin_hover_drag_move", lambda *_a, **_k: None)(event.position(), md)
                event.acceptProposedAction()
                return
            if event.source() is self and md and md.hasFormat(MIME_TRACKLIST_REORDER):
                raw = bytes(md.data(MIME_TRACKLIST_REORDER)).decode("utf-8")
                getattr(self._owner, "_handle_internal_reorder_drag_move", lambda *_a, **_k: None)(raw, event.position())
                event.setDropAction(Qt.DropAction.MoveAction)
                event.accept()
                return
        except Exception:
            log.exception("ArrangerTrackListWidget.dragEnterEvent failed")
        try:
            super().dragEnterEvent(event)
        except Exception:
            pass

    def dragMoveEvent(self, event):  # noqa: ANN001
        try:
            md = event.mimeData()
            if md and md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                getattr(self._owner, "_handle_plugin_hover_drag_move", lambda *_a, **_k: None)(event.position(), md)
                event.acceptProposedAction()
                return
            if event.source() is self and md and md.hasFormat(MIME_TRACKLIST_REORDER):
                raw = bytes(md.data(MIME_TRACKLIST_REORDER)).decode("utf-8")
                getattr(self._owner, "_handle_internal_reorder_drag_move", lambda *_a, **_k: None)(raw, event.position())
                event.setDropAction(Qt.DropAction.MoveAction)
                event.accept()
                return
        except Exception:
            log.exception("ArrangerTrackListWidget.dragMoveEvent failed")
        try:
            super().dragMoveEvent(event)
        except Exception:
            pass

    def dragLeaveEvent(self, event):  # noqa: ANN001
        try:
            getattr(self._owner, "_clear_internal_reorder_drop_marker", lambda: None)()
            getattr(self._owner, "_clear_plugin_hover_marker", lambda: None)()
        except Exception:
            log.exception("ArrangerTrackListWidget.dragLeaveEvent failed")
        try:
            super().dragLeaveEvent(event)
        except Exception:
            pass

    def dropEvent(self, event):  # noqa: ANN001
        try:
            md = event.mimeData()
            if md and md.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                info = getattr(self._owner, "_parse_plugin_hover_info", lambda *_a, **_k: None)(md)
                try:
                    pt = event.position().toPoint() if hasattr(event.position(), "toPoint") else event.position()
                except Exception:
                    pt = event.position()
                item = None
                try:
                    item = self.itemAt(pt)
                except Exception:
                    item = None
                handled = False
                if info is not None and item is not None and not bool(getattr(self._owner, "_is_group_header_item", lambda *_a, **_k: False)(item)):
                    track_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
                    track = getattr(self._owner, "_track_by_id", lambda *_a, **_k: None)(track_id)
                    track_kind = str(getattr(track, "kind", "") or "")
                    device_kind, _name = info
                    info = getattr(self._owner, "_plugin_drop_target_info", lambda *_a, **_k: {})(track, device_kind) or {}
                    label = str(info.get("label") or "")
                    actionable = bool(info.get("actionable"))
                    blocked_message = str(info.get("blocked_message") or "")
                    target_kind = str(info.get("target_kind") or "")
                    try:
                        raw = bytes(md.data(MIME_PLUGIN_DRAG_PREVIEW)).decode("utf-8", "ignore")
                        payload = json.loads(raw) if raw else {}
                        if not isinstance(payload, dict):
                            payload = {}
                    except Exception:
                        payload = {}
                    if track_id and actionable:
                        try:
                            if device_kind == "instrument":
                                getattr(self._owner, "request_smartdrop_instrument_to_track").emit(track_id, dict(payload))
                            else:
                                getattr(self._owner, "request_smartdrop_fx_to_track").emit(track_id, dict(payload))
                            handled = True
                            event.acceptProposedAction()
                        except Exception:
                            handled = False
                    elif track_id and device_kind == "instrument" and target_kind == "audio":
                        try:
                            getattr(self._owner, "request_smartdrop_instrument_morph_guard").emit(track_id, dict(payload))
                            handled = True
                        except Exception:
                            handled = False
                if (not handled) and blocked_message:
                    try:
                        getattr(self._owner, "status_message").emit(blocked_message, 3600)
                    except Exception:
                        pass
                getattr(self._owner, "_clear_plugin_hover_marker", lambda: None)()
                if not handled:
                    try:
                        event.ignore()
                    except Exception:
                        pass
                return
            if event.source() is self and md and md.hasFormat(MIME_TRACKLIST_REORDER):
                raw = bytes(md.data(MIME_TRACKLIST_REORDER)).decode("utf-8")
                handled = bool(getattr(self._owner, "_handle_internal_reorder_drop", lambda *_a, **_k: False)(raw, event.position()))
                getattr(self._owner, "_clear_internal_reorder_drop_marker", lambda: None)()
                if handled:
                    event.setDropAction(Qt.DropAction.MoveAction)
                    event.accept()
                else:
                    event.ignore()
                return
        except Exception:
            log.exception("ArrangerTrackListWidget.dropEvent failed")
            try:
                event.ignore()
            except Exception:
                pass
            return
        try:
            super().dropEvent(event)
        except Exception:
            pass
        try:
            getattr(self._owner, "_clear_internal_reorder_drop_marker", lambda: None)()
            getattr(self._owner, "_clear_plugin_hover_marker", lambda: None)()
        except Exception:
            pass


from pydaw.services.project_service import ProjectService
from .arranger_canvas import ArrangerCanvas
from .automation_lanes import AutomationLanePanel
# v0.0.20.89: Enhanced Automation Editor (Bezier + FX params)
try:
    from .automation_editor import EnhancedAutomationLanePanel
    _HAS_ENHANCED_AUTOMATION = True
except ImportError:
    _HAS_ENHANCED_AUTOMATION = False
from .clip_launcher_overlay import ClipLauncherOverlay

log = logging.getLogger(__name__)


class _RowGestureFilter(QObject):
    """Safe gesture filter for row widgets/labels.

    Used for two lightweight UX features only:
    - group-header mouse drag as whole block
    - double-click rename on track/group names

    It observes mouse gestures but otherwise leaves the normal Qt selection and
    context-menu behaviour intact.
    """

    def __init__(self, parent=None, *, drag_cb=None, double_click_cb=None):
        super().__init__(parent)
        self._drag_cb = drag_cb
        self._double_click_cb = double_click_cb
        self._press_pos = None
        self._drag_started = False

    @staticmethod
    def _event_point(event):  # noqa: ANN001
        try:
            pt = event.position()
            return pt.toPoint() if hasattr(pt, "toPoint") else pt
        except Exception:
            return None

    def eventFilter(self, obj, event):  # noqa: ANN001
        try:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                self._press_pos = self._event_point(event)
                self._drag_started = False
                return False
            if et == QEvent.Type.MouseMove and self._drag_cb is not None and not self._drag_started:
                buttons = getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)()
                if buttons & Qt.MouseButton.LeftButton and self._press_pos is not None:
                    cur = self._event_point(event)
                    if cur is not None and (cur - self._press_pos).manhattanLength() >= int(QApplication.startDragDistance()):
                        self._drag_started = True
                        try:
                            self._drag_cb()
                        except Exception:
                            pass
                        return True
                return False
            if et == QEvent.Type.MouseButtonRelease:
                self._press_pos = None
                self._drag_started = False
                return False
            if et == QEvent.Type.MouseButtonDblClick and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                self._press_pos = None
                self._drag_started = False
                if self._double_click_cb is not None:
                    try:
                        self._double_click_cb()
                    except Exception:
                        pass
                    return True
        except Exception:
            pass
        return False


class TrackList(QWidget):
    track_selected = Signal(str)
    selected_track_changed = Signal(str)  # compatibility alias
    status_message = Signal(str, int)

    # Phase 2 (Track-Header ▾): request helpers (handled by MainWindow)
    request_open_browser_tab = Signal(str, str)  # track_id, tab_key ('instruments'|'effects'|'samples')
    request_show_device_panel = Signal(str)      # track_id
    # Phase 3: Track-Header ▾ → 1-click insert into device chains
    request_add_device = Signal(str, str, str)   # track_id, kind ('instrument'|'note_fx'|'audio_fx'), plugin_id
    request_smartdrop_instrument_to_track = Signal(str, dict)  # track_id, payload
    request_smartdrop_fx_to_track = Signal(str, dict)  # track_id, payload
    request_smartdrop_instrument_morph_guard = Signal(str, dict)  # track_id, payload (non-mutating preview/validate/apply stub)

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self._tab_service = None  # v0.0.20.86: for cross-project drag
        self._midi_manager = None  # v0.0.20.608: Bitwig-style MIDI input routing
        self._device_prefs = None
        self._refreshing_list = False
        self._collapsed_group_ids: set[str] = set()
        self._row_gesture_filters: list[QObject] = []
        self._drop_marker_line = None
        self._drop_marker_state = None
        self._plugin_hover_track_id = ""
        self._plugin_hover_kind = ""
        self._plugin_hover_label = ""
        self._plugin_hover_hint_text = ""
        self._plugin_hover_hint_visible = False
        self._plugin_hover_actionable = False
        self._base_list_tooltip = ""
        self._track_row_widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list = ArrangerTrackListWidget(self)
        # v0.0.20.86: Enable drag for cross-project track transfer
        self.list.setDragEnabled(True)
        self.list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # Override startDrag to provide custom MIME data
        # (defensive: never crash startup if method is missing due to stale caches or edits)
        try:
            fn = getattr(self, "_start_drag", None)
            if callable(fn):
                self.list.startDrag = fn
        except Exception:
            pass
        layout.addWidget(self.list, 1)
        try:
            self.list.keyPressEvent = self._on_list_key_press
        except Exception:
            pass
        self.list.setToolTip(
            "Tracks auswählen: Klick / Shift / Ctrl\n"
            "Rechtsklick: Track-/Gruppenmenü\n"
            "▲/▼: Spur oder Gruppe direkt verschieben\n"
            "Maus-Drag in der TrackList: Spur(en) direkt neu anordnen\n"
            "Maus-Drag am Gruppenkopf: ganze Gruppe als Block verschieben\n"
            "Drop-Markierung zeigt das Einfügeziel beim Maus-Drag\n"
            "Doppelklick auf Namen: umbenennen\n"
            "Ctrl+G: ausgewählte Spuren gruppieren\n"
            "Ctrl+Shift+G: Gruppierung aufheben"
        )
        self._base_list_tooltip = str(self.list.toolTip() or "")
        self._init_drop_marker()
        try:
            self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.list.customContextMenuRequested.connect(lambda pos: self._safe_ui_call(self._on_context_menu_requested, pos))
        except Exception:
            pass
        # Safety: PyQt6 may abort the whole process (SIGABRT) if a slot raises.
        # Always route through _safe_ui_call.
        try:
            self.list.currentItemChanged.connect(lambda cur, prev: self._safe_ui_call(self._on_sel, cur, prev))
        except Exception:
            self.list.currentItemChanged.connect(self._on_sel)

        try:
            self.project.project_updated.connect(lambda: self._safe_ui_call(self.refresh))
        except Exception:
            self.project.project_updated.connect(self.refresh)
        self.refresh()


    def _init_drop_marker(self) -> None:
        try:
            line = QFrame(self.list.viewport())
            line.setObjectName("pydawTrackDropMarker")
            line.setFrameShape(QFrame.Shape.NoFrame)
            line.setFixedHeight(3)
            line.setStyleSheet(
                "QFrame#pydawTrackDropMarker { "
                "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(0,220,255,0.10), stop:0.5 rgba(0,220,255,0.95), stop:1 rgba(0,220,255,0.10)); "
                "border: 1px solid rgba(110,245,255,0.95); border-radius: 1px; }"
            )
            line.hide()
            line.raise_()
            self._drop_marker_line = line
        except Exception:
            self._drop_marker_line = None

    def _clear_internal_reorder_drop_marker(self) -> None:
        try:
            self._drop_marker_state = None
            if self._drop_marker_line is not None:
                self._drop_marker_line.hide()
        except Exception:
            pass

    def _show_internal_reorder_drop_marker(self, y: int) -> None:
        try:
            if self._drop_marker_line is None:
                return
            vp = self.list.viewport()
            width = max(24, int(vp.width()) - 8)
            yy = max(0, min(int(y), max(0, int(vp.height()) - int(self._drop_marker_line.height()))))
            self._drop_marker_line.setGeometry(4, yy, width, int(self._drop_marker_line.height()))
            self._drop_marker_line.raise_()
            self._drop_marker_line.show()
        except Exception:
            pass

    def _parse_plugin_hover_info(self, mime_data) -> tuple[str, str] | None:  # noqa: ANN001
        try:
            if mime_data is None or not mime_data.hasFormat(MIME_PLUGIN_DRAG_PREVIEW):
                return None
            raw = bytes(mime_data.data(MIME_PLUGIN_DRAG_PREVIEW)).decode("utf-8", "ignore")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                return None
            params = payload.get("params") or {}
            device_kind = str(payload.get("device_kind") or payload.get("kind") or "").strip().lower()
            if device_kind not in ("instrument", "audio_fx", "note_fx"):
                is_inst = bool(payload.get("is_instrument"))
                if isinstance(params, dict):
                    is_inst = is_inst or bool(params.get("__ext_is_instrument"))
                device_kind = "instrument" if is_inst else "audio_fx"
            name = str(payload.get("name") or "").strip()
            if not name:
                name = "Device"
            return device_kind, name
        except Exception:
            return None

    def _track_by_id(self, track_id: str):
        try:
            return next((t for t in self.project.ctx.project.tracks if str(getattr(t, "id", "") or "") == str(track_id or "")), None)
        except Exception:
            return None

    def _plugin_drop_target_info(self, track, device_kind: str) -> dict:  # noqa: ANN001
        try:
            project_obj = getattr(getattr(self.project, "ctx", None), "project", None)
            return dict(evaluate_plugin_drop_target(project_obj, track, device_kind) or {})
        except Exception:
            return {}

    def _plugin_drop_target_state(self, track, device_kind: str) -> tuple[str, bool]:  # noqa: ANN001
        try:
            info = self._plugin_drop_target_info(track, device_kind)
            return str(info.get("label") or ""), bool(info.get("actionable"))
        except Exception:
            return "", False

    def _plugin_hover_hint_message(self) -> str:
        base = str(self._plugin_hover_label or "").strip()
        if not base:
            return ""
        if bool(getattr(self, "_plugin_hover_actionable", False)):
            return base
        return f"{base} · Nur Preview — SmartDrop folgt später"

    def _plugin_hover_global_pos(self, pos=None):  # noqa: ANN001
        try:
            if pos is None:
                return None
            if hasattr(pos, "toPoint"):
                qpt = pos.toPoint()
            else:
                qpt = QPoint(int(float(pos.x())), int(float(pos.y())))
            return self.list.viewport().mapToGlobal(qpt + QPoint(18, 24))
        except Exception:
            return None

    def _sync_plugin_hover_hint(self, pos=None) -> None:  # noqa: ANN001
        text = self._plugin_hover_hint_message()
        try:
            self.list.setToolTip(text or self._base_list_tooltip)
        except Exception:
            pass
        if not text:
            try:
                if self._plugin_hover_hint_text or self._plugin_hover_hint_visible:
                    self.status_message.emit("", 1)
            except Exception:
                pass
            try:
                QToolTip.hideText()
            except Exception:
                pass
            self._plugin_hover_hint_text = ""
            self._plugin_hover_hint_visible = False
            return
        try:
            if text != self._plugin_hover_hint_text:
                self.status_message.emit(text, 1800)
        except Exception:
            pass
        try:
            global_pos = self._plugin_hover_global_pos(pos)
            if global_pos is not None and (text != self._plugin_hover_hint_text or not self._plugin_hover_hint_visible):
                QToolTip.showText(global_pos, text, self.list.viewport())
                self._plugin_hover_hint_visible = True
        except Exception:
            pass
        self._plugin_hover_hint_text = text

    def _clear_plugin_hover_marker(self) -> None:
        try:
            self._plugin_hover_track_id = ""
            self._plugin_hover_kind = ""
            self._plugin_hover_label = ""
            self._plugin_hover_actionable = False
            for row in list((self._track_row_widgets or {}).values()):
                try:
                    row.setStyleSheet(
                        "QWidget#pydawTrackRow { border: 1px solid transparent; border-radius: 6px; background: transparent; }"
                    )
                except Exception:
                    pass
            self._sync_plugin_hover_hint()
        except Exception:
            pass

    def _handle_plugin_hover_drag_move(self, pos, mime_data) -> None:  # noqa: ANN001
        info = self._parse_plugin_hover_info(mime_data)
        if info is None:
            self._clear_plugin_hover_marker()
            return
        try:
            pt = pos.toPoint() if hasattr(pos, "toPoint") else pos
        except Exception:
            pt = pos
        try:
            item = self.list.itemAt(pt)
        except Exception:
            item = None
        if item is None or self._is_group_header_item(item):
            self._clear_plugin_hover_marker()
            return
        track_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not track_id:
            self._clear_plugin_hover_marker()
            return
        device_kind, _name = info
        track = self._track_by_id(track_id)
        if track is None:
            self._clear_plugin_hover_marker()
            return
        label, actionable = self._plugin_drop_target_state(track, device_kind)
        if track_id == self._plugin_hover_track_id and device_kind == self._plugin_hover_kind and label == self._plugin_hover_label and actionable == self._plugin_hover_actionable:
            self._sync_plugin_hover_hint(pos)
            return
        self._plugin_hover_track_id = track_id
        self._plugin_hover_kind = device_kind
        self._plugin_hover_label = label
        self._plugin_hover_actionable = actionable
        for tid, row in list((self._track_row_widgets or {}).items()):
            try:
                if str(tid) == track_id:
                    bg_alpha = 42 if device_kind == "instrument" else 26
                    border_alpha = 242 if device_kind == "instrument" else 198
                    row.setStyleSheet(
                        "QWidget#pydawTrackRow { "
                        f"background: rgba(0,229,255,{bg_alpha}); "
                        f"border: 1px solid rgba(110,245,255,{border_alpha}); "
                        "border-radius: 6px; }"
                    )
                else:
                    row.setStyleSheet(
                        "QWidget#pydawTrackRow { border: 1px solid transparent; border-radius: 6px; background: transparent; }"
                    )
            except Exception:
                pass
        self._sync_plugin_hover_hint(pos)

    def _handle_internal_reorder_drag_move(self, raw_payload: str, pos) -> None:  # noqa: ANN001
        try:
            payload = json.loads(str(raw_payload or "{}"))
        except Exception:
            payload = {}
        moving_ids = {str(tid) for tid in (payload.get("track_ids", []) or []) if str(tid)}
        before_track_id = self._drop_before_track_id_for_pos(pos, moving_ids)
        if before_track_id is None:
            self._clear_internal_reorder_drop_marker()
            return
        try:
            pt = pos.toPoint() if hasattr(pos, "toPoint") else pos
        except Exception:
            pt = pos
        try:
            item = self.list.itemAt(pt)
        except Exception:
            item = None
        y = 0
        if item is None:
            if self.list.count() <= 0:
                y = 2
            else:
                last_item = self.list.item(self.list.count() - 1)
                rect = self.list.visualItemRect(last_item)
                y = int(rect.bottom() - 1)
        else:
            rect = self.list.visualItemRect(item)
            try:
                py = float(pos.y() if hasattr(pos, "y") else pt.y())
                lower_half = py > float(rect.top() + (rect.height() / 2.0))
            except Exception:
                lower_half = False
            y = int(rect.bottom() - 1 if lower_half else rect.top())
            if self._is_group_header_item(item):
                gid = str(item.data(self._group_header_role()) or "")
                member_ids = [str(getattr(t, "id", "") or "") for t in self._group_members(gid)]
                if member_ids and set(member_ids).issubset(moving_ids):
                    self._clear_internal_reorder_drop_marker()
                    return
        state = (int(y), str(before_track_id or ""))
        if state == self._drop_marker_state:
            return
        self._drop_marker_state = state
        self._show_internal_reorder_drop_marker(int(y))

    # --- safety: PyQt6 may abort on uncaught slot exceptions (SIGABRT) ---
    def _safe_ui_call(self, fn, *args, **kwargs):  # noqa: ANN001
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    # --- Phase 3: Favorites/Recents (UI-only; per-user cache) ---
    def _prefs(self):  # noqa: ANN001
        if self._device_prefs is None:
            try:
                from .device_prefs import DevicePrefs
                self._device_prefs = DevicePrefs.load()
            except Exception:
                self._device_prefs = None
        return self._device_prefs

    def _prefs_add_recent(self, kind: str, plugin_id: str, name: str) -> None:
        p = self._prefs()
        if p is None:
            return
        try:
            p.add_recent(kind, plugin_id, name)
            p.save()
        except Exception:
            pass

    def _prefs_toggle_favorite(self, kind: str, plugin_id: str, name: str) -> bool:
        p = self._prefs()
        if p is None:
            return False
        try:
            now = bool(p.toggle_favorite(kind, plugin_id, name))
            p.save()
            return now
        except Exception:
            return False

    def _prefs_get(self, bucket: str, kind: str):  # noqa: ANN001
        p = self._prefs()
        if p is None:
            return []
        try:
            b = getattr(p, bucket, {}) or {}
            return list(b.get(kind, []) or [])
        except Exception:
            return []

    def _prefs_clear_recents(self, kinds: list[str]) -> None:
        p = self._prefs()
        if p is None:
            return
        try:
            for k in kinds:
                p.clear_recents(k)
            p.save()
        except Exception:
            pass

    def _emit_add_device(self, track_id: str, kind: str, plugin_id: str, name: str) -> None:
        self._prefs_add_recent(kind, plugin_id, name)
        try:
            self.request_add_device.emit(str(track_id), str(kind), str(plugin_id))
        except Exception:
            pass

    def _bind_row_gestures(self, widgets, *, drag_cb=None, double_click_cb=None) -> None:  # noqa: ANN001
        for w in list(widgets or []):
            if w is None:
                continue
            try:
                filt = _RowGestureFilter(
                    w,
                    drag_cb=(lambda _cb=drag_cb: self._safe_ui_call(_cb)) if callable(drag_cb) else None,
                    double_click_cb=(lambda _cb=double_click_cb: self._safe_ui_call(_cb)) if callable(double_click_cb) else None,
                )
                w.installEventFilter(filt)
                self._row_gesture_filters.append(filt)
            except Exception:
                pass

    def _attach_searchable_device_menu(self, menu: QMenu, *, track_id: str, title: str, kind: str, items: list[tuple[str, str]]) -> None:
        """Attach a submenu with search + filtered device list.

        Wayland safety:
        - Embedding a QLineEdit into a QMenu (QWidgetAction) can be flaky on some Wayland/Qt combos.
          If we detect Wayland, we use a tiny input dialog instead.

        IMPORTANT: This function must never raise (PyQt6 can SIGABRT on uncaught slot exceptions).
        """
        import os

        sub = menu.addMenu(title)
        state = {"acts": [], "q": ""}

        def _clear_actions() -> None:
            for a in list(state["acts"]):
                try:
                    sub.removeAction(a)
                except Exception:
                    pass
            state["acts"] = []

        def repop() -> None:
            try:
                _clear_actions()
                q = str(state.get("q") or "").strip().lower()
                shown = 0
                for it in list(items or []):
                    try:
                        name, pid = it
                    except Exception:
                        continue
                    hay = f"{name} {pid}".lower()
                    if q and q not in hay:
                        continue
                    act = sub.addAction(str(name))
                    act.triggered.connect(
                        lambda _=False, _tid=str(track_id), _pid=str(pid), _name=str(name): self._safe_ui_call(
                            self._emit_add_device, _tid, kind, _pid, _name
                        )
                    )
                    state["acts"].append(act)
                    shown += 1
                    if shown >= 30:
                        break

                if shown == 0:
                    act = sub.addAction("(keine Treffer)")
                    act.setEnabled(False)
                    state["acts"].append(act)
            except Exception:
                try:
                    _clear_actions()
                    act = sub.addAction("(Fehler beim Laden)")
                    act.setEnabled(False)
                    state["acts"].append(act)
                except Exception:
                    pass

        def _safe_repop(*_a) -> None:
            try:
                repop()
            except Exception:
                pass

        # Detect Wayland
        qpa = (os.environ.get("QT_QPA_PLATFORM", "") or "").lower()
        sess = (os.environ.get("XDG_SESSION_TYPE", "") or "").lower()
        is_wayland = (sess == "wayland") or ("WAYLAND_DISPLAY" in os.environ) or qpa.startswith("wayland")

        if is_wayland:
            # No embedded text input; use Search… dialog.
            act_search = sub.addAction("Search…")
            act_clear = sub.addAction("Clear Search")
            sub.addSeparator()

            def ask_search() -> None:
                try:
                    from PySide6.QtWidgets import QInputDialog
                    txt, ok = QInputDialog.getText(self, "Search", "Filter:", text=str(state.get("q") or ""))
                    if ok:
                        state["q"] = str(txt or "")
                        repop()
                except Exception:
                    pass

            def clear_search() -> None:
                try:
                    state["q"] = ""
                    repop()
                except Exception:
                    pass

            try:
                act_search.triggered.connect(lambda _=False: self._safe_ui_call(ask_search))
                act_clear.triggered.connect(lambda _=False: self._safe_ui_call(clear_search))
                sub.aboutToShow.connect(_safe_repop)
            except Exception:
                pass

            _safe_repop()
            return

        # Non-Wayland: embed QLineEdit into menu
        try:
            w = QWidget(sub)
            lay = QHBoxLayout(w)
            lay.setContentsMargins(8, 6, 8, 6)
            edt = QLineEdit(w)
            edt.setPlaceholderText("Suchen…")
            lay.addWidget(edt, 1)
            wa = QWidgetAction(sub)
            wa.setDefaultWidget(w)
            sub.addAction(wa)
            sub.addSeparator()

            def _set_q_from_edt() -> None:
                state["q"] = (edt.text() or "")

            def _safe_repop_from_edt(*_a) -> None:
                try:
                    _set_q_from_edt()
                    repop()
                except Exception:
                    pass

            sub.aboutToShow.connect(_safe_repop_from_edt)
            edt.textChanged.connect(_safe_repop_from_edt)
            _safe_repop_from_edt()
        except Exception:
            # Fallback: no search box
            try:
                sub.aboutToShow.connect(_safe_repop)
            except Exception:
                pass
            _safe_repop()

    # --- v0.0.20.86: Cross-Project Drag Support ---

    def set_tab_service(self, tab_service) -> None:
        """Wire the ProjectTabService for cross-project drag data."""
        self._tab_service = tab_service

    def set_midi_manager(self, midi_manager) -> None:
        """Wire the MidiManager for MIDI input routing dropdown (v0.0.20.608)."""
        self._midi_manager = midi_manager

    def _source_tab_index(self) -> int:
        try:
            if self._tab_service is not None:
                return int(getattr(self._tab_service, "active_index", 0) or 0)
        except Exception:
            pass
        return 0

    def _create_track_drag_mime(self, track_ids: list[str]) -> QMimeData | None:
        ids = [str(tid) for tid in (track_ids or []) if str(tid)]
        if not ids:
            return None
        src_idx = self._source_tab_index()
        try:
            mime = create_track_drag_data(
                source_tab_index=src_idx,
                track_ids=ids,
                include_clips=True,
                include_device_chains=True,
            )
        except Exception:
            return None
        try:
            mime.setData(
                MIME_TRACKLIST_REORDER,
                json.dumps({
                    "track_ids": ids,
                    "source_tab_index": int(src_idx),
                }).encode("utf-8"),
            )
        except Exception:
            pass
        return mime

    def _start_drag_for_track_ids(self, track_ids: list[str]) -> None:
        ids = [str(tid) for tid in (track_ids or []) if str(tid)]
        if not ids:
            return
        mime = self._create_track_drag_mime(ids)
        if mime is None:
            return
        drag = QDrag(self.list)
        drag.setMimeData(mime)
        log.info("TrackList: starting drag with %d track(s)", len(ids))
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

    def _start_group_drag(self, group_id: str) -> None:
        members = self._group_members(group_id)
        ids = [str(getattr(t, "id", "") or "") for t in members if str(getattr(t, "id", "") or "")]
        if len(ids) < 2:
            return
        try:
            self.select_tracks(ids, primary_track_id=str(ids[0] if ids else ""))
        except Exception:
            pass
        self._start_drag_for_track_ids(ids)

    def _start_drag(self, supported_actions) -> None:
        """Custom startDrag: keeps cross-project drag and adds safe local reorder MIME."""
        try:
            selected_items = self.list.selectedItems()
            if not selected_items:
                cur = self.list.currentItem()
                if self._is_group_header_item(cur):
                    gid = str(cur.data(self._group_header_role()) or "")
                    if gid:
                        self._start_group_drag(gid)
                return

            track_ids = []
            for item in selected_items:
                if self._is_group_header_item(item):
                    gid = str(item.data(self._group_header_role()) or "")
                    track_ids.extend(str(getattr(t, "id", "") or "") for t in self._group_members(gid))
                    continue
                tid = str(item.data(Qt.ItemDataRole.UserRole) or "")
                if tid:
                    track_ids.append(tid)

            deduped = []
            seen = set()
            for tid in track_ids:
                if tid and tid not in seen:
                    deduped.append(str(tid))
                    seen.add(str(tid))
            self._start_drag_for_track_ids(deduped)
        except Exception:
            log.exception("TrackList._start_drag failed")

    def _group_header_role(self):
        return int(Qt.ItemDataRole.UserRole) + 1

    def _group_members(self, group_id: str) -> list:
        gid = str(group_id or "")
        if not gid:
            return []
        try:
            return [
                t for t in (self.project.ctx.project.tracks or [])
                if str(getattr(t, "track_group_id", "") or "") == gid
                and str(getattr(t, "kind", "") or "") not in ("master", "group")
            ]
        except Exception:
            return []

    def _is_group_header_item(self, item) -> bool:  # noqa: ANN001
        if item is None:
            return False
        try:
            return bool(item.data(self._group_header_role()))
        except Exception:
            return False

    def _selected_track_ids_internal(self) -> list[str]:
        out: list[str] = []
        try:
            for it in (self.list.selectedItems() or []):
                if self._is_group_header_item(it):
                    continue
                tid = str(it.data(Qt.ItemDataRole.UserRole) or "")
                if tid:
                    out.append(tid)
        except Exception:
            pass
        return out

    def select_track(self, track_id: str) -> None:
        self.select_tracks([str(track_id or "")], primary_track_id=str(track_id or ""))

    def select_tracks(self, track_ids: list[str], *, primary_track_id: str = "") -> None:
        ids = [str(x) for x in (track_ids or []) if str(x)]
        wanted = set(ids)
        if not wanted:
            return
        primary = str(primary_track_id or (ids[0] if ids else ""))
        current_item = None
        try:
            self.list.blockSignals(True)
            self.list.clearSelection()
            for i in range(self.list.count()):
                it = self.list.item(i)
                if self._is_group_header_item(it):
                    continue
                tid = str(it.data(Qt.ItemDataRole.UserRole) or "")
                if tid in wanted:
                    try:
                        it.setSelected(True)
                    except Exception:
                        pass
                    if current_item is None or tid == primary:
                        current_item = it
            self.list.blockSignals(False)
            if current_item is not None:
                try:
                    self.list.setCurrentItem(current_item)
                except Exception:
                    pass
        except Exception:
            try:
                self.list.blockSignals(False)
            except Exception:
                pass

    def _select_group_members(self, group_id: str) -> None:
        members = self._group_members(group_id)
        ids = [str(getattr(t, "id", "") or "") for t in members]
        primary = ids[0] if ids else ""
        self.select_tracks(ids, primary_track_id=primary)

    def _rename_track_from_row(self, item, track_id: str) -> None:  # noqa: ANN001
        try:
            if item is not None:
                self._select_item_safe(item)
        except Exception:
            pass
        self._rename_track_dialog(str(track_id or ""))

    def _rename_group_from_header(self, group_id: str) -> None:
        gid = str(group_id or "")
        if not gid:
            return
        try:
            self._select_group_members(gid)
        except Exception:
            pass
        self._rename_group_dialog(gid)

    def _sync_collapsed_groups_from_project(self) -> None:
        try:
            raw = list(getattr(self.project.ctx.project, "arranger_collapsed_group_ids", []) or [])
        except Exception:
            raw = []
        valid = {
            str(getattr(t, "track_group_id", "") or "")
            for t in (self.project.ctx.project.tracks or [])
            if str(getattr(t, "track_group_id", "") or "")
        }
        self._collapsed_group_ids = {str(gid) for gid in raw if str(gid) in valid}

    def _persist_collapsed_groups(self) -> None:
        ids = sorted(str(gid) for gid in (self._collapsed_group_ids or set()) if str(gid))
        if hasattr(self.project, "set_arranger_collapsed_group_ids"):
            self._safe_ui_call(self.project.set_arranger_collapsed_group_ids, ids)
        else:
            try:
                self.project.ctx.project.arranger_collapsed_group_ids = ids
                self.project.project_updated.emit()
            except Exception:
                pass

    def _group_is_collapsed(self, group_id: str) -> bool:
        return str(group_id or "") in self._collapsed_group_ids

    def _toggle_group_collapsed(self, group_id: str) -> None:
        gid = str(group_id or "")
        if not gid:
            return
        self._sync_collapsed_groups_from_project()
        if gid in self._collapsed_group_ids:
            self._collapsed_group_ids.discard(gid)
        else:
            self._collapsed_group_ids.add(gid)
        self._persist_collapsed_groups()
        self.refresh()

    def _rename_track_dialog(self, track_id: str) -> None:
        tid = str(track_id or "")
        if not tid:
            return
        trk = next((t for t in (self.project.ctx.project.tracks or []) if str(getattr(t, "id", "") or "") == tid), None)
        if trk is None or str(getattr(trk, "kind", "") or "") == "master":
            return
        current_name = str(getattr(trk, "name", "") or "Track")
        new_name, ok = QInputDialog.getText(self, "Track umbenennen", "Neuer Name:", text=current_name)
        if not ok:
            return
        new_name = str(new_name or "").strip()
        if not new_name or new_name == current_name:
            return
        self._safe_ui_call(self.project.rename_track, tid, new_name)

    def _rename_group_dialog(self, group_id: str) -> None:
        members = self._group_members(group_id)
        if len(members) < 2:
            return
        current_name = str(getattr(members[0], "track_group_name", "") or "Gruppe")
        new_name, ok = QInputDialog.getText(self, "Gruppe umbenennen", "Neuer Gruppenname:", text=current_name)
        if not ok:
            return
        new_name = str(new_name or "").strip()
        if not new_name:
            return
        ids = [str(getattr(t, "id", "") or "") for t in members]
        try:
            self.project.group_tracks(ids, group_name=new_name)
        except Exception:
            pass

    def _add_track_after(self, kind: str, after_track_id: str = "") -> None:
        self._safe_ui_call(self.project.add_track, str(kind or "audio"), insert_after_track_id=str(after_track_id or ""))

    def _add_track_into_group(self, kind: str, group_id: str) -> None:
        members = self._group_members(group_id)
        if not members:
            self._safe_ui_call(self.project.add_track, str(kind or "audio"))
            return
        after_track_id = str(getattr(members[-1], "id", "") or "")
        grp_name = str(getattr(members[0], "track_group_name", "") or "Gruppe")
        self._safe_ui_call(
            self.project.add_track,
            str(kind or "audio"),
            insert_after_track_id=after_track_id,
            group_id=str(group_id or ""),
            group_name=grp_name,
        )
        if self._group_is_collapsed(group_id):
            self._sync_collapsed_groups_from_project()

    def _move_track_relative(self, track_id: str, delta: int) -> None:
        if not track_id:
            return
        self._safe_ui_call(self.project.move_track, str(track_id), int(delta))

    def _move_group_relative(self, group_id: str, delta: int) -> None:
        gid = str(group_id or "")
        if not gid:
            return
        self._safe_ui_call(self.project.move_group_block, gid, int(delta))

    def _drop_before_track_id_for_pos(self, pos, moving_track_ids: set[str]) -> str | None:  # noqa: ANN001
        try:
            pt = pos.toPoint() if hasattr(pos, "toPoint") else pos
        except Exception:
            pt = pos
        item = None
        try:
            item = self.list.itemAt(pt)
        except Exception:
            item = None

        tracks = [
            t for t in (self.project.ctx.project.tracks or [])
            if str(getattr(t, "kind", "") or "") != "master"
        ]
        moving_ids = {str(tid) for tid in (moving_track_ids or set()) if str(tid)}

        if item is None:
            return ""

        try:
            rect = self.list.visualItemRect(item)
            py = float(pos.y() if hasattr(pos, "y") else pt.y())
            lower_half = py > float(rect.top() + (rect.height() / 2.0))
        except Exception:
            lower_half = False

        if self._is_group_header_item(item):
            gid = str(item.data(self._group_header_role()) or "")
            members = self._group_members(gid)
            member_ids = [str(getattr(t, "id", "") or "") for t in members]
            if not member_ids:
                return ""
            if set(member_ids).issubset(moving_ids):
                return None
            if not lower_half:
                first_id = str(member_ids[0] or "")
                return None if first_id in moving_ids else first_id
            try:
                last_idx = max(i for i, t in enumerate(tracks) if str(getattr(t, "id", "") or "") in set(member_ids))
            except ValueError:
                return ""
            for t in tracks[last_idx + 1:]:
                tid = str(getattr(t, "id", "") or "")
                if tid and tid not in moving_ids:
                    return tid
            return ""

        tid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not tid:
            return ""
        if tid in moving_ids:
            return None
        if not lower_half:
            return tid
        try:
            idx = next(i for i, t in enumerate(tracks) if str(getattr(t, "id", "") or "") == tid)
        except StopIteration:
            return ""
        for t in tracks[idx + 1:]:
            next_id = str(getattr(t, "id", "") or "")
            if next_id and next_id not in moving_ids:
                return next_id
        return ""

    def _handle_internal_reorder_drop(self, raw_payload: str, pos) -> bool:  # noqa: ANN001
        try:
            payload = json.loads(str(raw_payload or "{}"))
        except Exception:
            payload = {}
        ids = [str(tid) for tid in (payload.get("track_ids", []) or []) if str(tid)]
        if not ids:
            return False
        if len(ids) == 1 and self._is_group_header_item(self.list.currentItem()):
            return False
        before_track_id = self._drop_before_track_id_for_pos(pos, set(ids))
        if before_track_id is None:
            return False
        if hasattr(self.project, "move_tracks_block"):
            self._safe_ui_call(self.project.move_tracks_block, ids, str(before_track_id or ""))
            return True
        return False

    def _build_add_track_menu(self, *, parent=None, after_track_id: str = "", group_id: str = "") -> QMenu:
        menu = QMenu(parent or self)
        a_add_inst_track = menu.addAction("Instrumentenspur hinzufügen")
        a_add_audio_track = menu.addAction("Audiospur hinzufügen")
        a_add_bus_track = menu.addAction("Bus-Spur hinzufügen")
        menu.addSeparator()
        a_add_fx_track = menu.addAction("FX-Spur (Return) hinzufügen")
        if str(group_id or ""):
            a_add_inst_track.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._add_track_into_group, "instrument", gid))
            a_add_audio_track.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._add_track_into_group, "audio", gid))
            a_add_bus_track.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._add_track_into_group, "bus", gid))
            a_add_fx_track.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._add_track_into_group, "fx", gid))
        elif str(after_track_id or ""):
            a_add_inst_track.triggered.connect(lambda _=False, tid=str(after_track_id): self._safe_ui_call(self._add_track_after, "instrument", tid))
            a_add_audio_track.triggered.connect(lambda _=False, tid=str(after_track_id): self._safe_ui_call(self._add_track_after, "audio", tid))
            a_add_bus_track.triggered.connect(lambda _=False, tid=str(after_track_id): self._safe_ui_call(self._add_track_after, "bus", tid))
            a_add_fx_track.triggered.connect(lambda _=False, tid=str(after_track_id): self._safe_ui_call(self._add_track_after, "fx", tid))
        else:
            a_add_inst_track.triggered.connect(lambda _=False: self._safe_ui_call(self.project.add_track, "instrument"))
            a_add_audio_track.triggered.connect(lambda _=False: self._safe_ui_call(self.project.add_track, "audio"))
            a_add_bus_track.triggered.connect(lambda _=False: self._safe_ui_call(self.project.add_track, "bus"))
            a_add_fx_track.triggered.connect(lambda _=False: self._safe_ui_call(self.project.add_track, "fx"))
        return menu

    def _build_group_header_menu(self, group_id: str, *, parent=None) -> QMenu:
        menu = QMenu(parent or self)
        members = self._group_members(group_id)
        grp_name = str(getattr(members[0], "track_group_name", "") or "Gruppe") if members else "Gruppe"
        try:
            menu.addSection(f"Gruppe: {grp_name}")
        except Exception:
            pass
        m_add_track = menu.addMenu("Spur zur Gruppe hinzufügen")
        for act in self._build_add_track_menu(parent=menu, group_id=str(group_id or "")).actions():
            m_add_track.addAction(act)

        a_toggle = menu.addAction("Gruppe ausklappen" if self._group_is_collapsed(group_id) else "Gruppe einklappen")
        a_select = menu.addAction("Gruppenmitglieder auswählen")
        a_move_up = menu.addAction("Gruppe nach oben")
        a_move_down = menu.addAction("Gruppe nach unten")
        a_rename = menu.addAction("Gruppe umbenennen…")
        a_ungroup = menu.addAction("Gruppe auflösen")
        ids = [str(getattr(t, "id", "") or "") for t in members]
        a_toggle.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._toggle_group_collapsed, gid))
        a_select.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._select_group_members, gid))
        a_move_up.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._move_group_relative, gid, -1))
        a_move_down.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._move_group_relative, gid, 1))
        a_rename.triggered.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._rename_group_dialog, gid))
        a_ungroup.triggered.connect(lambda _=False, _ids=list(ids): self._safe_ui_call(self.project.ungroup_tracks, _ids))
        return menu

    def _build_track_menu(self, t, it=None, *, parent=None) -> QMenu:  # noqa: ANN001
        menu = QMenu(parent or self)
        try:
            menu.addSection(f"Track: {t.name}")
        except Exception:
            pass

        m_add_track = menu.addMenu("Neue Spur darunter hinzufügen")
        for act in self._build_add_track_menu(parent=menu, after_track_id=str(getattr(t, "id", "") or "")).actions():
            m_add_track.addAction(act)

        # --- Routing (audio/bus) ---
        if t.kind in ("audio", "bus"):
            try:
                import os
                in_ch = int(os.environ.get("PYDAW_JACK_IN", "2"))
                out_ch = int(os.environ.get("PYDAW_JACK_OUT", "2"))
            except Exception:
                in_ch, out_ch = 2, 2
            in_pairs = max(1, in_ch // 2)
            out_pairs = max(1, out_ch // 2)
            m_route = menu.addMenu("Routing")

            m_in = m_route.addMenu("Input Pair")
            try:
                cur_in_menu = max(1, int(getattr(t, "input_pair", 1) or 1))
            except Exception:
                cur_in_menu = 1
            for pair in range(1, in_pairs + 1):
                act = m_in.addAction(f"Stereo {pair}")
                act.setCheckable(True)
                act.setChecked(pair == cur_in_menu)
                act.triggered.connect(lambda _=False, tid=t.id, _pair=pair: self._safe_ui_call(self.project.set_track_input_pair, tid, _pair))

            m_out = m_route.addMenu("Output Pair")
            try:
                cur_out_menu = max(1, int(getattr(t, "output_pair", 1) or 1))
            except Exception:
                cur_out_menu = 1
            for pair in range(1, out_pairs + 1):
                act = m_out.addAction(f"Out {pair}")
                act.setCheckable(True)
                act.setChecked(pair == cur_out_menu)
                act.triggered.connect(lambda _=False, tid=t.id, _pair=pair: self._safe_ui_call(self.project.set_track_output_pair, tid, _pair))

        # --- Quick state ---
        menu.addSeparator()
        a_mon = menu.addAction("Monitoring (I)")
        a_mon.setCheckable(True)
        a_mon.setChecked(bool(getattr(t, "monitor", False)))
        a_mon.triggered.connect(lambda checked, tid=t.id: self._safe_ui_call(self.project.set_track_monitor, tid, bool(checked)))

        a_arm = menu.addAction("Record Arm (R)")
        a_arm.setCheckable(True)
        a_arm.setChecked(bool(getattr(t, "record_arm", False)))
        a_arm.triggered.connect(lambda checked, tid=t.id: self._safe_ui_call(self.project.set_track_record_arm, tid, bool(checked)))

        a_mute = menu.addAction("Mute (M)")
        a_mute.setCheckable(True)
        a_mute.setChecked(bool(getattr(t, "muted", False)))
        a_mute.triggered.connect(lambda checked, tid=t.id: self._safe_ui_call(self.project.set_track_muted, tid, bool(checked)))

        a_solo = menu.addAction("Solo (S)")
        a_solo.setCheckable(True)
        a_solo.setChecked(bool(getattr(t, "solo", False)))
        a_solo.triggered.connect(lambda checked, tid=t.id: self._safe_ui_call(self.project.set_track_solo, tid, bool(checked)))

        # --- Devices / Browser ---
        menu.addSeparator()
        m_dev = menu.addMenu("Devices")
        try:
            try:
                m_dev.addSection("Quick Insert")
            except Exception:
                pass

            relevant_kinds = ["audio_fx"]
            if t.kind == "instrument":
                relevant_kinds = ["instrument", "note_fx", "audio_fx"]

            m_fav = m_dev.addMenu("⭐ Favorites")
            fav_any = False
            for k in relevant_kinds:
                favs = self._prefs_get("favorites", k)
                if not favs:
                    continue
                fav_any = True
                try:
                    m_fav.addSection({"instrument": "Instruments", "note_fx": "Note-FX", "audio_fx": "Audio-FX"}.get(k, k))
                except Exception:
                    pass
                for e in favs:
                    name = getattr(e, "name", "") or getattr(e, "plugin_id", "")
                    pid = getattr(e, "plugin_id", "")
                    act = m_fav.addAction(name)
                    act.triggered.connect(lambda _=False, _k=k, _pid=pid, _name=name, _tid=t.id: self._emit_add_device(str(_tid), _k, _pid, _name))
            if not fav_any:
                a = m_fav.addAction("(keine Favorites)")
                a.setEnabled(False)

            m_fav.addSeparator()
            m_add_from_rec = m_fav.addMenu("⭐ Add/Remove from Recents")
            for k in relevant_kinds:
                subk = m_add_from_rec.addMenu({"instrument": "Instruments", "note_fx": "Note-FX", "audio_fx": "Audio-FX"}.get(k, k))
                recs = self._prefs_get("recents", k)
                if not recs:
                    a = subk.addAction("(keine Recents)")
                    a.setEnabled(False)
                    continue
                for e in recs:
                    name = getattr(e, "name", "") or getattr(e, "plugin_id", "")
                    pid = getattr(e, "plugin_id", "")
                    act = subk.addAction(name)
                    act.setCheckable(True)
                    try:
                        p = self._prefs()
                        act.setChecked(bool(p and p.is_favorite(k, pid)))
                    except Exception:
                        pass
                    act.triggered.connect(lambda _checked=False, _k=k, _pid=pid, _name=name: self._prefs_toggle_favorite(_k, _pid, _name))

            m_rec = m_dev.addMenu("🕘 Recents")
            rec_any = False
            for k in relevant_kinds:
                recs = self._prefs_get("recents", k)
                if not recs:
                    continue
                rec_any = True
                try:
                    m_rec.addSection({"instrument": "Instruments", "note_fx": "Note-FX", "audio_fx": "Audio-FX"}.get(k, k))
                except Exception:
                    pass
                for e in recs:
                    name = getattr(e, "name", "") or getattr(e, "plugin_id", "")
                    pid = getattr(e, "plugin_id", "")
                    act = m_rec.addAction(name)
                    act.triggered.connect(lambda _=False, _k=k, _pid=pid, _name=name, _tid=t.id: self._emit_add_device(str(_tid), _k, _pid, _name))
            if not rec_any:
                a = m_rec.addAction("(keine Recents)")
                a.setEnabled(False)
            else:
                m_rec.addSeparator()
                a_clear = m_rec.addAction("Clear Recents")
                a_clear.triggered.connect(lambda _=False, _kinds=list(relevant_kinds): self._prefs_clear_recents(_kinds))

            try:
                m_dev.addSeparator()
            except Exception:
                pass

            if "instrument" in relevant_kinds:
                try:
                    from pydaw.plugins.registry import get_instruments
                    inst_items = []
                    for spec in get_instruments():
                        nm = f"{spec.name} — {getattr(spec, 'category', '')}".strip(" —")
                        inst_items.append((nm, str(spec.plugin_id)))
                except Exception:
                    inst_items = []
                self._attach_searchable_device_menu(m_dev, track_id=str(t.id), title="Add Instrument…", kind="instrument", items=inst_items)

            if "note_fx" in relevant_kinds:
                try:
                    from .fx_specs import get_note_fx
                    nf_items = [(f"{s.name} — {s.plugin_id}", str(s.plugin_id)) for s in get_note_fx()]
                except Exception:
                    nf_items = []
                self._attach_searchable_device_menu(m_dev, track_id=str(t.id), title="Add Note-FX…", kind="note_fx", items=nf_items)

            if "audio_fx" in relevant_kinds:
                try:
                    from .fx_specs import get_audio_fx
                    af_items = [(f"{s.name} — {s.plugin_id}", str(s.plugin_id)) for s in get_audio_fx()]
                except Exception:
                    af_items = []
                self._attach_searchable_device_menu(m_dev, track_id=str(t.id), title="Add Audio-FX…", kind="audio_fx", items=af_items)

            try:
                m_dev.addSection("Browser")
            except Exception:
                m_dev.addSeparator()
            a_add_instr = m_dev.addAction("Open Instruments (Browser)")
            a_add_fx = m_dev.addAction("Open Effects (Browser)")
            a_show_dev = m_dev.addAction("Device Panel zeigen")

            a_add_instr.triggered.connect(lambda _=False, tid=t.id: self.request_open_browser_tab.emit(str(tid), "instruments"))
            a_add_fx.triggered.connect(lambda _=False, tid=t.id: self.request_open_browser_tab.emit(str(tid), "effects"))
            a_show_dev.triggered.connect(lambda _=False, tid=t.id: self.request_show_device_panel.emit(str(tid)))

        except Exception:
            a_add_instr = m_dev.addAction("Add Instrument… (Browser)")
            a_add_fx = m_dev.addAction("Add FX… (Browser)")
            a_show_dev = m_dev.addAction("Device Panel zeigen")
            a_add_instr.triggered.connect(lambda _=False, tid=t.id: self.request_open_browser_tab.emit(str(tid), "instruments"))
            a_add_fx.triggered.connect(lambda _=False, tid=t.id: self.request_open_browser_tab.emit(str(tid), "effects"))
            a_show_dev.triggered.connect(lambda _=False, tid=t.id: self.request_show_device_panel.emit(str(tid)))

        if t.kind != "master":
            menu.addSeparator()
            m_group = menu.addMenu("Gruppierung")
            selected_ids = [tid for tid in self._selected_track_ids_internal() if tid]
            if str(t.id) not in selected_ids:
                selected_ids = [str(t.id)]
            non_master_selected = []
            try:
                for tid in selected_ids:
                    trk = next((tt for tt in (self.project.ctx.project.tracks or []) if str(getattr(tt, 'id', '')) == str(tid)), None)
                    if trk is not None and str(getattr(trk, 'kind', '')) != 'master':
                        non_master_selected.append(str(tid))
            except Exception:
                non_master_selected = [str(t.id)]
            a_group_sel = m_group.addAction("Auswahl gruppieren (Ctrl+G)")
            a_group_sel.setEnabled(len(non_master_selected) >= 2)
            a_group_sel.triggered.connect(lambda _=False, _ids=list(non_master_selected): self._safe_ui_call(self.project.group_tracks, _ids))

            group_id = str(getattr(t, "track_group_id", "") or "")
            members = self._group_members(group_id) if group_id else []
            if len(members) >= 2:
                a_select_group = m_group.addAction("Gruppenmitglieder auswählen")
                a_select_group.triggered.connect(lambda _=False, gid=group_id: self._safe_ui_call(self._select_group_members, gid))
                a_rename_group = m_group.addAction("Gruppe umbenennen…")
                a_rename_group.triggered.connect(lambda _=False, gid=group_id: self._safe_ui_call(self._rename_group_dialog, gid))
                a_ungroup = m_group.addAction("Gruppe auflösen (Ctrl+Shift+G)")
                member_ids = [str(getattr(mt, "id", "") or "") for mt in members]
                a_ungroup.triggered.connect(lambda _=False, _ids=list(member_ids): self._safe_ui_call(self.project.ungroup_tracks, _ids))
            elif non_master_selected:
                grouped_sel = [
                    tid for tid in non_master_selected
                    if any(str(getattr(tt, 'id', '')) == str(tid) and (str(getattr(tt, 'track_group_id', '') or '') or str(getattr(tt, 'track_group_name', '') or '')) for tt in (self.project.ctx.project.tracks or []))
                ]
                if grouped_sel:
                    a_ungroup_sel = m_group.addAction("Auswahl entgruppieren")
                    a_ungroup_sel.triggered.connect(lambda _=False, _ids=list(grouped_sel): self._safe_ui_call(self.project.ungroup_tracks, _ids))

        if t.kind != "master":
            menu.addSeparator()
            a_move_up = menu.addAction("Spur nach oben")
            a_move_down = menu.addAction("Spur nach unten")
            a_move_up.triggered.connect(lambda _=False, tid=t.id: self._safe_ui_call(self._move_track_relative, str(tid), -1))
            a_move_down.triggered.connect(lambda _=False, tid=t.id: self._safe_ui_call(self._move_track_relative, str(tid), 1))
            group_id = str(getattr(t, "track_group_id", "") or "")
            if group_id:
                m_add_to_group = menu.addMenu("In diese Gruppe hinzufügen")
                for act in self._build_add_track_menu(parent=menu, group_id=group_id).actions():
                    m_add_to_group.addAction(act)
        menu.addSeparator()
        a_rename = menu.addAction("Umbenennen…")
        a_delete = None
        if t.kind != "master":
            a_delete = menu.addAction("Track löschen")

        a_rename.triggered.connect(lambda _=False, tid=t.id: self._safe_ui_call(self._rename_track_dialog, str(tid)))
        if a_delete is not None:
            a_delete.triggered.connect(lambda _=False, tid=t.id: self._safe_ui_call(self.project.delete_track, str(tid)))
        return menu

    def _render_group_header_row(self, group_id: str, group_name: str, member_count: int):
        it = QListWidgetItem()
        it.setData(Qt.ItemDataRole.UserRole, "")
        it.setData(self._group_header_role(), str(group_id or ""))
        try:
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        except Exception:
            pass

        row = QWidget()
        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(lambda pos, gid=str(group_id), w=row: self._safe_ui_call(self._show_group_header_menu_global, gid, w.mapToGlobal(pos)))
        try:
            row.setToolTip("Gruppenkopf – Rechtsklick = Gruppenmenü, Maus-Drag = ganze Gruppe verschieben, Doppelklick = Gruppe umbenennen")
        except Exception:
            pass
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        collapsed = self._group_is_collapsed(group_id)
        arrow = "▸" if collapsed else "▾"

        btn_fold = QToolButton()
        btn_fold.setText(arrow)
        btn_fold.setAutoRaise(True)
        btn_fold.setToolTip("Gruppe ein-/ausklappen")
        btn_fold.clicked.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._toggle_group_collapsed, gid))

        btn_up = QToolButton()
        btn_up.setAutoRaise(True)
        btn_up.setFixedWidth(20)
        btn_up.setToolTip("Gruppe nach oben verschieben")
        btn_up.clicked.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._move_group_relative, gid, -1))
        btn_down = QToolButton()
        btn_down.setAutoRaise(True)
        btn_down.setFixedWidth(20)
        btn_down.setToolTip("Gruppe nach unten verschieben")
        btn_down.clicked.connect(lambda _=False, gid=str(group_id): self._safe_ui_call(self._move_group_relative, gid, 1))
        try:
            from .chrono_icons import icon as _ic
            btn_up.setIcon(_ic("up", 14))
            btn_up.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn_up.setText("")
            btn_down.setIcon(_ic("down", 14))
            btn_down.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn_down.setText("")
        except Exception:
            btn_up.setText("▲")
            btn_down.setText("▼")

        title = QLabel(str(group_name))
        title.setStyleSheet("color:#f6d39d; font-weight:700;")
        cnt = QLabel(f"{int(member_count)} Tracks")
        cnt.setStyleSheet(
            "QLabel { color: #e8d8ba; background: rgba(255,185,110,0.10); border: 1px solid rgba(255,185,110,0.26); border-radius: 6px; padding: 1px 6px; }"
        )
        title.setToolTip("Gruppenkopf – Rechtsklick = Gruppenmenü, Maus-Drag = ganze Gruppe verschieben, Doppelklick = Gruppe umbenennen")
        cnt.setToolTip("Gruppenkopf – Rechtsklick = Gruppenmenü, Maus-Drag = ganze Gruppe verschieben, Doppelklick = Gruppe umbenennen")
        try:
            btn_fold.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn_fold.customContextMenuRequested.connect(lambda pos, gid=str(group_id), ww=btn_fold: self._safe_ui_call(self._show_group_header_menu_global, gid, ww.mapToGlobal(pos)))
        except Exception:
            pass
        for w in (title, cnt):
            try:
                w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                w.customContextMenuRequested.connect(lambda pos, gid=str(group_id), ww=w: self._safe_ui_call(self._show_group_header_menu_global, gid, ww.mapToGlobal(pos)))
            except Exception:
                pass
        self._bind_row_gestures(
            [row, title, cnt],
            drag_cb=lambda gid=str(group_id): self._start_group_drag(gid),
            double_click_cb=lambda gid=str(group_id): self._rename_group_from_header(gid),
        )
        lay.addWidget(btn_fold, 0)
        lay.addWidget(title, 1)
        lay.addWidget(cnt, 0)
        lay.addWidget(btn_up, 0)
        lay.addWidget(btn_down, 0)
        it.setSizeHint(row.sizeHint())
        self.list.addItem(it)
        self.list.setItemWidget(it, row)

    def _show_group_header_menu_global(self, group_id: str, global_pos) -> None:  # noqa: ANN001
        menu = self._build_group_header_menu(group_id, parent=self)
        try:
            menu.exec(global_pos)
        except Exception:
            pass

    def _show_track_context_menu_global(self, track_id: str, item, global_pos) -> None:  # noqa: ANN001
        trk = next((t for t in (self.project.ctx.project.tracks or []) if str(getattr(t, "id", "") or "") == str(track_id)), None)
        if trk is None:
            return
        try:
            if item is not None and not self._is_group_header_item(item):
                sel_items = list(self.list.selectedItems() or [])
                if item not in sel_items:
                    self.select_track(str(track_id))
                else:
                    self.list.setCurrentItem(item)
        except Exception:
            pass
        menu = self._build_track_menu(trk, item, parent=self)
        try:
            menu.exec(global_pos)
        except Exception:
            pass

    def _on_context_menu_requested(self, pos) -> None:  # noqa: ANN001
        try:
            item = self.list.itemAt(pos)
        except Exception:
            item = None
        if item is None:
            try:
                menu = self._build_add_track_menu(parent=self)
                menu.exec(self.list.viewport().mapToGlobal(pos))
            except Exception:
                pass
            return
        if self._is_group_header_item(item):
            gid = str(item.data(self._group_header_role()) or "")
            if gid:
                self._show_group_header_menu_global(gid, self.list.viewport().mapToGlobal(pos))
            return
        track_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if track_id:
            self._show_track_context_menu_global(track_id, item, self.list.viewport().mapToGlobal(pos))

    def refresh(self) -> None:
        self._sync_collapsed_groups_from_project()
        self._clear_internal_reorder_drop_marker()
        cur_id = self.selected_track_id()
        self._refreshing_list = True
        self._row_gesture_filters = []
        self._track_row_widgets = {}
        self.list.blockSignals(True)
        self.list.clear()

        rendered_groups: set[str] = set()
        tracks = list(self.project.ctx.project.tracks or [])

        def _add_track_row(t, *, indented: bool = False) -> None:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, t.id)

            row = QWidget()
            row.setObjectName("pydawTrackRow")
            row.setStyleSheet("QWidget#pydawTrackRow { border: 1px solid transparent; border-radius: 6px; background: transparent; }")
            row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            try:
                row.setToolTip("Track-Zeile – Rechtsklick = Track-Menü, Doppelklick auf Namen = umbenennen")
            except Exception:
                pass
            lay = QHBoxLayout(row)
            lay.setContentsMargins(18 if indented else 6, 2, 6, 2)
            lay.setSpacing(6)

            lbl = QLabel(("↳ " if indented else "") + str(t.name))
            lbl.setMinimumWidth(90)
            lbl.setStyleSheet("color: #e6e6e6;")
            lay.addWidget(lbl, 1)

            grp_name = str(getattr(t, "track_group_name", "") or "").strip()
            if grp_name:
                grp_badge = QLabel(grp_name)
                grp_badge.setToolTip(f"Spurgruppe: {grp_name}")
                grp_badge.setStyleSheet(
                    "QLabel { color: #f6d39d; background: rgba(255,185,110,0.12); border: 1px solid rgba(255,185,110,0.45); "
                    "border-radius: 6px; padding: 1px 6px; }"
                )
                lay.addWidget(grp_badge)
            else:
                grp_badge = None

            if t.kind in ("audio", "bus"):
                try:
                    import os
                    in_ch = int(os.environ.get("PYDAW_JACK_IN", "2"))
                    out_ch = int(os.environ.get("PYDAW_JACK_OUT", "2"))
                except Exception:
                    in_ch, out_ch = 2, 2

                in_pairs = max(1, in_ch // 2)
                out_pairs = max(1, out_ch // 2)

                cb_in = QComboBox()
                for i in range(1, in_pairs + 1):
                    cb_in.addItem(f"Stereo {i}")
                try:
                    cur_in = max(1, int(getattr(t, "input_pair", 1) or 1))
                except Exception:
                    cur_in = 1
                cb_in.setCurrentIndex(max(0, min(in_pairs - 1, cur_in - 1)))
                cb_in.setToolTip("Input (Stereo-Paar) für Monitoring/Recording")
                cb_in.currentIndexChanged.connect(lambda idx, tid=t.id: self._safe_ui_call(self.project.set_track_input_pair, tid, int(idx) + 1))
                cb_in.setFixedWidth(90)

                cb_out = QComboBox()
                for i in range(1, out_pairs + 1):
                    cb_out.addItem(f"Out {i}")
                try:
                    cur_out = max(1, int(getattr(t, "output_pair", 1) or 1))
                except Exception:
                    cur_out = 1
                cb_out.setCurrentIndex(max(0, min(out_pairs - 1, cur_out - 1)))
                cb_out.setToolTip("Output (Stereo-Paar) – vorbereitet für Submix/Click")
                cb_out.currentIndexChanged.connect(lambda idx, tid=t.id: self._safe_ui_call(self.project.set_track_output_pair, tid, int(idx) + 1))
                cb_out.setFixedWidth(76)

                btn_i = QToolButton()
                btn_i.setText("I")
                btn_i.setCheckable(True)
                btn_i.setChecked(bool(getattr(t, "monitor", False)))
                btn_i.setToolTip("Input Monitoring")
                btn_i.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self.project.set_track_monitor, tid, not self._track_mon(tid)))
                btn_i.setFixedWidth(26)
                btn_i.setAutoRaise(True)

                try:
                    from .chrono_icons import icon as _ic
                    btn_i.setIcon(_ic("monitor", 14))
                    btn_i.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    btn_i.setText("")
                    btn_i.setAccessibleName("I")
                except Exception:
                    pass

                lay.addWidget(cb_in)
                lay.addWidget(cb_out)
                lay.addWidget(btn_i)

            btn_m = QToolButton()
            btn_m.setText("M")
            btn_m.setCheckable(True)
            btn_m.setChecked(bool(getattr(t, "muted", False)))
            btn_m.setToolTip("Mute")
            btn_m.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self.project.set_track_muted, tid, not self._track_muted(tid)))

            btn_s = QToolButton()
            btn_s.setText("S")
            btn_s.setCheckable(True)
            btn_s.setChecked(bool(getattr(t, "solo", False)))
            btn_s.setToolTip("Solo")
            btn_s.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self.project.set_track_solo, tid, not self._track_solo(tid)))

            btn_r = QToolButton()
            btn_r.setText("R")
            btn_r.setCheckable(True)
            btn_r.setChecked(bool(getattr(t, "record_arm", False)))
            btn_r.setToolTip("Record Arm")
            btn_r.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self.project.set_track_record_arm, tid, not self._track_arm(tid)))

            try:
                from .chrono_icons import icon as _ic
                for btn, name, txt in ((btn_m, "mute", "M"), (btn_s, "solo", "S"), (btn_r, "rec", "R")):
                    try:
                        btn.setIcon(_ic(name, 14))
                        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                        btn.setText("")
                        btn.setAccessibleName(txt)
                    except Exception:
                        pass
            except Exception:
                pass

            for b in (btn_m, btn_s, btn_r):
                b.setFixedWidth(26)
                b.setAutoRaise(True)

            lay.addWidget(btn_m)
            lay.addWidget(btn_s)
            lay.addWidget(btn_r)

            # v0.0.20.608: Bitwig-Style MIDI Input Routing Dropdown
            # Shows current MIDI input source; click opens categorized menu
            # (NOTE INPUTS: No input / All ins / Computer Keyboard / controllers)
            # (TRACKS: other tracks for MIDI-through routing)
            btn_midi_in = QToolButton()
            btn_midi_in.setAutoRaise(True)
            btn_midi_in.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            btn_midi_in.setFixedHeight(22)
            btn_midi_in.setMinimumWidth(60)
            btn_midi_in.setMaximumWidth(100)
            btn_midi_in.setStyleSheet(
                "QToolButton { font-size: 9px; color: #ccc; padding: 1px 4px; }"
                "QToolButton:hover { background: #444; border-radius: 3px; }"
                "QToolButton::menu-indicator { width: 0px; }"  # hide default arrow
            )
            # Determine effective MIDI input for display
            effective_mi = self._get_effective_midi_input(t)
            btn_midi_in.setText(self._midi_input_display_text(effective_mi))
            btn_midi_in.setToolTip(f"MIDI Input: {effective_mi}")
            # Build and attach the menu (will be rebuilt on click for fresh device list)
            btn_midi_in.setMenu(self._build_midi_input_menu(t.id, btn_midi_in))
            lay.addWidget(btn_midi_in)

            # v0.0.20.609: MIDI Channel Filter (Bitwig-Style: Omni / Ch 1-16)
            cmb_ch = QComboBox()
            cmb_ch.addItem("Omni")  # index 0 = -1 (all channels)
            for ch_num in range(1, 17):
                cmb_ch.addItem(f"Ch {ch_num}")
            ch_filt = int(getattr(t, "midi_channel_filter", -1) or -1)
            cmb_ch.setCurrentIndex(0 if ch_filt < 0 else min(16, ch_filt + 1))
            cmb_ch.setFixedWidth(52)
            cmb_ch.setFixedHeight(22)
            cmb_ch.setStyleSheet("font-size: 9px;")
            cmb_ch.setToolTip("MIDI Channel Filter (Omni = alle Kanäle)")
            cmb_ch.currentIndexChanged.connect(
                lambda idx, tid=t.id: self._safe_ui_call(
                    self.project.set_track_midi_channel_filter, tid, -1 if idx == 0 else idx - 1
                )
            )
            lay.addWidget(cmb_ch)

            # v0.0.20.608: Output routing label (Bitwig-style "→ Master")
            # For now, show group or master target as static label
            out_label = self._get_output_label(t)
            lbl_out = QLabel(f"→ {out_label}")
            lbl_out.setStyleSheet("font-size: 9px; color: #888; padding: 0 2px;")
            lbl_out.setFixedWidth(60)
            lbl_out.setToolTip(f"Output: {out_label}")
            lay.addWidget(lbl_out)

            btn_up = QToolButton()
            btn_up.setAutoRaise(True)
            btn_up.setFixedWidth(20)
            btn_up.setToolTip("Spur nach oben verschieben")
            btn_up.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self._move_track_relative, str(tid), -1))
            btn_down = QToolButton()
            btn_down.setAutoRaise(True)
            btn_down.setFixedWidth(20)
            btn_down.setToolTip("Spur nach unten verschieben")
            btn_down.clicked.connect(lambda _=False, tid=t.id: self._safe_ui_call(self._move_track_relative, str(tid), 1))
            try:
                from .chrono_icons import icon as _ic
                btn_up.setIcon(_ic("up", 14))
                btn_up.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn_up.setText("")
                btn_down.setIcon(_ic("down", 14))
                btn_down.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn_down.setText("")
            except Exception:
                btn_up.setText("▲")
                btn_down.setText("▼")
            if str(getattr(t, "kind", "") or "") == "master":
                btn_up.setEnabled(False)
                btn_down.setEnabled(False)

            lay.addWidget(btn_up)
            lay.addWidget(btn_down)

            btn_menu = QToolButton()
            btn_menu.setText("▾")
            btn_menu.setToolTip("Track-Menü (Routing / Gruppierung / Devices)")
            btn_menu.setAutoRaise(True)
            btn_menu.setFixedWidth(24)
            btn_menu.pressed.connect(lambda _it=it: self._safe_ui_call(self._select_item_safe, _it))
            btn_menu.setMenu(self._build_track_menu(t, it, parent=btn_menu))
            btn_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            lay.addWidget(btn_menu)

            ctx_targets = [row, lbl]
            if grp_badge is not None:
                ctx_targets.append(grp_badge)
            for w in ctx_targets:
                try:
                    w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    w.customContextMenuRequested.connect(lambda pos, tid=t.id, _it=it, ww=w: self._safe_ui_call(self._show_track_context_menu_global, tid, _it, ww.mapToGlobal(pos)))
                except Exception:
                    pass

            self._bind_row_gestures(
                [row, lbl, grp_badge],
                double_click_cb=lambda _it=it, tid=t.id: self._rename_track_from_row(_it, str(tid)),
            )

            it.setSizeHint(row.sizeHint())
            self.list.addItem(it)
            self.list.setItemWidget(it, row)
            self._track_row_widgets[str(t.id)] = row
            if cur_id and t.id == cur_id and self.list.currentItem() is not it:
                self.list.setCurrentItem(it)

        for t in tracks:
            if str(getattr(t, "kind", "") or "") == "master":
                _add_track_row(t, indented=False)
                continue
            # v0.0.20.357: Skip group-bus tracks — they are shown via the group header
            if str(getattr(t, "kind", "") or "") == "group":
                continue
            gid = str(getattr(t, "track_group_id", "") or "")
            if gid:
                members = self._group_members(gid)
                if len(members) >= 2:
                    if gid in rendered_groups:
                        continue
                    rendered_groups.add(gid)
                    grp_name = str(getattr(t, "track_group_name", "") or "Gruppe")
                    self._render_group_header_row(gid, grp_name, len(members))
                    if not self._group_is_collapsed(gid):
                        for mt in members:
                            _add_track_row(mt, indented=True)
                    continue
            _add_track_row(t, indented=False)

        if self.list.currentItem() is None and self.list.count() > 0:
            try:
                for i in range(self.list.count()):
                    it = self.list.item(i)
                    if not self._is_group_header_item(it):
                        self.list.setCurrentItem(it)
                        break
            except Exception:
                pass
        self.list.blockSignals(False)
        self._refreshing_list = False
        self._clear_internal_reorder_drop_marker()
        self._clear_plugin_hover_marker()

    def _track_muted(self, track_id: str) -> bool:
        trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
        return bool(getattr(trk, "muted", False))

    def _track_solo(self, track_id: str) -> bool:
        trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
        return bool(getattr(trk, "solo", False))

    def _track_arm(self, track_id: str) -> bool:
        trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
        return bool(getattr(trk, "record_arm", False))

    def _track_mon(self, track_id: str) -> bool:
        trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
        return bool(getattr(trk, "monitor", False))

    # ---------- v0.0.20.608: MIDI Input Routing Helpers (Bitwig-Style) ----------

    def _get_effective_midi_input(self, track) -> str:
        """Return the effective MIDI input for display (resolving auto-default)."""
        try:
            if hasattr(self.project, "get_track_effective_midi_input"):
                return str(self.project.get_track_effective_midi_input(str(track.id)))
        except Exception:
            pass
        # Inline fallback
        raw = str(getattr(track, "midi_input", "") or "")
        if raw:
            return raw
        kind = str(getattr(track, "kind", "") or "")
        plugin = str(getattr(track, "plugin_type", "") or "")
        sf2 = str(getattr(track, "sf2_path", "") or "")
        if kind == "instrument" or plugin or sf2:
            return "All ins"
        return "No input"

    def _midi_input_display_text(self, effective: str) -> str:
        """Short display text for the MIDI input button (max ~12 chars)."""
        if effective == "No input":
            return "No input"
        if effective == "All ins":
            return "All ins"
        if effective == "Computer Keyboard":
            return "Comp. KB"
        if effective == "Touch Keyboard":
            return "Touch KB"
        if effective == "OSC - OSC":
            return "OSC"
        if effective.startswith("track:"):
            # Show track name if possible
            tid = effective[6:]
            trk = next((t for t in self.project.ctx.project.tracks if t.id == tid), None)
            if trk:
                name = str(getattr(trk, "name", tid) or tid)
                return name[:12]
            return tid[:10]
        # Specific MIDI port — truncate
        return effective[:12] if len(effective) > 12 else effective

    def _get_output_label(self, track) -> str:
        """Return output routing label for display (group name or 'Master')."""
        gid = str(getattr(track, "track_group_id", "") or "")
        if gid:
            gname = str(getattr(track, "track_group_name", "") or "")
            if gname:
                return gname[:8]
            return "Group"
        kind = str(getattr(track, "kind", "") or "")
        if kind == "master":
            return "Studio"
        return "Master"

    def _build_midi_input_menu(self, track_id: str, btn: "QToolButton") -> "QMenu":
        """Build categorized popup menu for MIDI input selection (Bitwig-Style).

        Categories:
        - NOTE INPUTS: No input, All ins, Computer Keyboard, + connected controllers
        - TRACKS: other tracks for MIDI-through routing
        """
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(btn)
        menu.setStyleSheet(
            "QMenu { background: #2a2a2a; color: #ddd; border: 1px solid #555; font-size: 11px; }"
            "QMenu::item { padding: 4px 16px; }"
            "QMenu::item:selected { background: #e77d22; color: white; }"
            "QMenu::separator { height: 1px; background: #444; margin: 4px 8px; }"
        )

        # --- Section: NOTE INPUTS ---
        lbl_note = QAction("NOTE INPUTS", menu)
        lbl_note.setEnabled(False)
        f = lbl_note.font()
        f.setBold(True)
        lbl_note.setFont(f)
        menu.addAction(lbl_note)

        # Static entries
        for label in ("No input", "All ins", "Computer Keyboard", "Touch Keyboard", "OSC - OSC"):
            a = menu.addAction(f"  {label}")
            a.triggered.connect(
                lambda _=False, tid=track_id, val=label, b=btn:
                    self._on_midi_input_selected(tid, val, b)
            )

        # Dynamic: connected MIDI controllers
        midi_ports: list[str] = []
        try:
            if self._midi_manager is not None:
                midi_ports = list(self._midi_manager.connected_inputs() or [])
        except Exception:
            pass
        if not midi_ports:
            # Also try to list all available (even if not connected)
            try:
                if self._midi_manager is not None:
                    midi_ports = list(self._midi_manager.list_inputs() or [])
            except Exception:
                pass

        if midi_ports:
            menu.addSeparator()
            for port in midi_ports:
                a = menu.addAction(f"  🎹 {port}")
                a.triggered.connect(
                    lambda _=False, tid=track_id, val=port, b=btn:
                        self._on_midi_input_selected(tid, val, b)
                )

        # "Add MIDI Controller" submenu placeholder
        menu.addSeparator()
        sub_add = menu.addMenu("  Add MIDI Controller")
        avail = []
        try:
            if self._midi_manager is not None:
                connected = set(self._midi_manager.connected_inputs() or [])
                avail = [p for p in (self._midi_manager.list_inputs() or []) if p not in connected]
        except Exception:
            pass
        if avail:
            for port in avail:
                a = sub_add.addAction(port)
                a.triggered.connect(
                    lambda _=False, p=port: self._connect_midi_controller(p)
                )
        else:
            na = sub_add.addAction("(keine verfügbar)")
            na.setEnabled(False)

        # --- Section: TRACKS ---
        menu.addSeparator()
        lbl_tracks = QAction("TRACKS", menu)
        lbl_tracks.setEnabled(False)
        f2 = lbl_tracks.font()
        f2.setBold(True)
        lbl_tracks.setFont(f2)
        menu.addAction(lbl_tracks)

        try:
            for t in self.project.ctx.project.tracks:
                tid_other = str(getattr(t, "id", "") or "")
                if tid_other == track_id:
                    continue  # Don't route to self
                kind = str(getattr(t, "kind", "") or "")
                if kind == "master":
                    continue
                name = str(getattr(t, "name", "") or tid_other)
                a = menu.addAction(f"  ♪ {name}")
                a.triggered.connect(
                    lambda _=False, tid=track_id, val=f"track:{tid_other}", b=btn:
                        self._on_midi_input_selected(tid, val, b)
                )
        except Exception:
            pass

        return menu

    def _on_midi_input_selected(self, track_id: str, value: str, btn: "QToolButton") -> None:
        """Handle MIDI input selection from the dropdown menu."""
        try:
            self.project.set_track_midi_input(str(track_id), str(value))
        except Exception:
            pass
        # Update button text
        try:
            btn.setText(self._midi_input_display_text(value))
            btn.setToolTip(f"MIDI Input: {value}")
        except Exception:
            pass

    def _connect_midi_controller(self, port_name: str) -> None:
        """Connect a new MIDI controller via MidiManager."""
        try:
            if self._midi_manager is not None:
                self._midi_manager.connect_input(str(port_name))
        except Exception:
            pass

    def selected_track_ids(self) -> list[str]:
        return self._selected_track_ids_internal()

    def _on_list_key_press(self, event) -> None:  # noqa: ANN001
        try:
            mods = event.modifiers()
            if (mods & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_G:
                ids = [tid for tid in self.selected_track_ids() if tid]
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    if hasattr(self.project, 'ungroup_tracks') and ids:
                        self._safe_ui_call(self.project.ungroup_tracks, ids)
                        event.accept()
                        return
                else:
                    if hasattr(self.project, 'group_tracks') and len(ids) >= 2:
                        self._safe_ui_call(self.project.group_tracks, ids)
                        event.accept()
                        return
        except Exception:
            pass
        QListWidget.keyPressEvent(self.list, event)

    def _on_sel(self, cur, prev):  # noqa: ANN001
        if bool(getattr(self, '_refreshing_list', False)):
            return
        if not cur:
            self.track_selected.emit("")
            return
        # v0.0.20.357: When a group header is selected, emit the real group-bus
        # track ID so the DevicePanel shows the group's own device chain.
        if self._is_group_header_item(cur):
            gid = str(cur.data(self._group_header_role()) or "")
            if gid:
                try:
                    group_track = next(
                        (t for t in (self.project.ctx.project.tracks or [])
                         if str(getattr(t, 'id', '')) == gid
                         and str(getattr(t, 'kind', '')) == 'group'),
                        None
                    )
                    if group_track is not None:
                        self.track_selected.emit(str(group_track.id))
                        self.selected_track_changed.emit(str(group_track.id))
                        return
                except Exception:
                    pass
            self.track_selected.emit("")
            return
        tid = str(cur.data(Qt.ItemDataRole.UserRole) or "")
        self.track_selected.emit(tid)
        self.selected_track_changed.emit(tid)

    def selected_track_id(self) -> str:
        it = self.list.currentItem()
        if not it:
            return ""
        # v0.0.20.357: If a group header is selected and there's a real group track,
        # return the group track's ID.
        if self._is_group_header_item(it):
            gid = str(it.data(self._group_header_role()) or "")
            if gid:
                try:
                    gt = next(
                        (t for t in (self.project.ctx.project.tracks or [])
                         if str(getattr(t, 'id', '')) == gid
                         and str(getattr(t, 'kind', '')) == 'group'),
                        None
                    )
                    if gt is not None:
                        return str(gt.id)
                except Exception:
                    pass
            return ""
        return str(it.data(Qt.ItemDataRole.UserRole) or "")

    def _select_item_safe(self, item) -> None:  # noqa: ANN001
        try:
            if item is None:
                return
            self.list.setCurrentItem(item)
        except Exception:
            pass

    def _begin_rename_item(self, item) -> None:  # noqa: ANN001
        try:
            if item is None or self._is_group_header_item(item):
                return
            tid = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if tid:
                self._rename_track_dialog(tid)
        except Exception:
            pass


class ArrangerView(QWidget):
    clip_activated = Signal(str)
    clip_selected = Signal(str)
    request_rename_clip = Signal(str)
    request_duplicate_clip = Signal(str)
    request_delete_clip = Signal(str)
    status_message = Signal(str, int)  # (message, timeout_ms) - v0.0.19.7.0
    view_range_changed = Signal(float, float)  # start_beat, end_beat

    # Drag&Drop Overlay import: (file_path, track_id, start_beats, slot_key)
    request_import_audio_file = Signal(str, str, float, str)

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self._transport = None

        # Outer layout hosts a *horizontal splitter* so the user can resize/collapse
        # the TrackList and the Arranger view (Pro-DAW-like). This fixes the UX issue
        # where the left track area was not resizable at all.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hsplit = QSplitter(Qt.Orientation.Horizontal)
        hsplit.setChildrenCollapsible(True)
        try:
            hsplit.setHandleWidth(6)
        except Exception:
            pass

        # Left side: Tracklist (collapsible)
        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(0, 0, 0, 0)
        left_panel.setSpacing(4)

        self.tracks = TrackList(project)
        # Allow shrinking almost to zero (user requested)
        try:
            self.tracks.setMinimumWidth(0)
        except Exception:
            pass
        left_panel.addWidget(self.tracks, 1)

        left_container = QWidget()
        left_container.setLayout(left_panel)
        try:
            left_container.setMinimumWidth(0)
        except Exception:
            pass

        # Right side: canvas (scrollable) + automation panel in a vertical splitter
        right = QSplitter(Qt.Orientation.Vertical)

        self.canvas = ArrangerCanvas(project)
        self.canvas.clip_activated.connect(self.clip_activated.emit)
        self.canvas.clip_selected.connect(self.clip_selected.emit)
        self.canvas.request_rename_clip.connect(self.request_rename_clip.emit)
        self.canvas.request_duplicate_clip.connect(self.request_duplicate_clip.emit)
        self.canvas.request_delete_clip.connect(self.request_delete_clip.emit)
        self.canvas.status_message.connect(self.status_message.emit)  # Keyboard shortcuts (v0.0.19.7.0)
        self.tracks.status_message.connect(self.status_message.emit)

        # v0.0.20.607: Stable sizeHint prevents main window from growing
        # when canvas resizes (e.g. on loop toggle / clip changes)
        class _StableScrollArea(QScrollArea):
            def sizeHint(self):
                from PySide6.QtCore import QSize
                return QSize(400, 200)
            def minimumSizeHint(self):
                from PySide6.QtCore import QSize
                return QSize(0, 0)

        self.scroll = _StableScrollArea()
        # Canvas liefert eine dynamische Mindestgröße; dadurch können
        # horizontale/vertikale Scrollbars zuverlässig erscheinen.
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidget(self.canvas)
        # v0.0.20.98: Enable mouse tracking on viewport so hover events
        # reach the canvas for ruler magnifier cursor (Bitwig-style zoom).
        try:
            self.scroll.setMouseTracking(True)
            self.scroll.viewport().setMouseTracking(True)
        except Exception:
            pass

        # Clip-Launcher Overlay (shown during Browser drag)
        self.clip_overlay = ClipLauncherOverlay(self.project, transport=None, parent=self.scroll.viewport())
        self.clip_overlay.setGeometry(self.scroll.viewport().rect())
        self.clip_overlay.request_import_audio.connect(self.request_import_audio_file.emit)
        self.scroll.viewport().installEventFilter(self)

        right.addWidget(self.scroll)

        # sync view range (scroll/zoom) to downstream editors (automation, etc.)
        try:
            self.scroll.horizontalScrollBar().valueChanged.connect(lambda _v: self._emit_view_range())
            self.canvas.zoom_changed.connect(lambda _ppb: self._emit_view_range())
        except Exception:
            pass

        self.automation = AutomationLanePanel(project)
        # v0.0.20.89: Enhanced Automation Editor (Bezier + FX params + AutomationManager)
        self._enhanced_automation = None
        self._automation_manager = None
        right.addWidget(self.automation)
        right.setStretchFactor(0, 4)
        right.setStretchFactor(1, 1)

        # Assemble horizontal splitter
        hsplit.addWidget(left_container)
        hsplit.addWidget(right)
        hsplit.setStretchFactor(0, 0)
        hsplit.setStretchFactor(1, 1)
        try:
            hsplit.setCollapsible(0, True)
            hsplit.setCollapsible(1, False)
        except Exception:
            pass
        try:
            # Default: readable TrackList, big arranger
            hsplit.setSizes([240, 1200])
        except Exception:
            pass

        outer.addWidget(hsplit, 1)
        self._emit_view_range()

    # ---- overlay helpers

    def set_transport(self, transport) -> None:
        self._transport = transport
        try:
            self.clip_overlay.set_transport(transport)
        except Exception:
            pass

    def set_tab_service(self, tab_service) -> None:
        """Wire ProjectTabService to canvas + track list for cross-project D&D."""
        try:
            self.canvas.set_tab_service(tab_service)
        except Exception:
            pass
        try:
            self.tracks.set_tab_service(tab_service)
        except Exception:
            pass

    def set_midi_manager(self, midi_manager) -> None:
        """Wire MidiManager to track list for MIDI input routing dropdown (v0.0.20.608)."""
        try:
            self.tracks.set_midi_manager(midi_manager)
        except Exception:
            pass

    def set_automation_manager(self, automation_manager) -> None:
        """Wire AutomationManager for enhanced Bezier automation editor (v0.0.20.89)."""
        self._automation_manager = automation_manager
        if _HAS_ENHANCED_AUTOMATION and automation_manager is not None:
            try:
                self._enhanced_automation = EnhancedAutomationLanePanel(
                    automation_manager, self.project, parent=self
                )
                # Find the right splitter and replace the old panel
                # The old panel's parent is a vertical QSplitter
                splitter = self.automation.parentWidget()
                if splitter is not None and hasattr(splitter, 'replaceWidget'):
                    idx = splitter.indexOf(self.automation)
                    if idx >= 0:
                        splitter.replaceWidget(idx, self._enhanced_automation)
                        self.automation.hide()
                        self._enhanced_automation.setVisible(self.automation.isVisible())
                else:
                    # Fallback: just add alongside
                    self._enhanced_automation.hide()
            except Exception:
                self._enhanced_automation = None

    def activate_clip_overlay(self, drag_label: str = "") -> None:
        try:
            self.clip_overlay.setGeometry(self.scroll.viewport().rect())
            self.clip_overlay.activate(str(drag_label or ""))
        except Exception:
            pass

    def deactivate_clip_overlay(self) -> None:
        try:
            self.clip_overlay.deactivate()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: ANN001
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            try:
                self.clip_overlay.setGeometry(self.scroll.viewport().rect())
            except Exception:
                pass
        return super().eventFilter(obj, event)

    # ---- view range

    def visible_range_beats(self) -> tuple[float, float]:
        try:
            ppb = float(getattr(self.canvas, "pixels_per_beat", 80.0)) or 80.0
            x0 = float(self.scroll.horizontalScrollBar().value())
            w = float(self.scroll.viewport().width())
            start = max(0.0, x0 / ppb)
            end = max(start + 0.25, (x0 + w) / ppb)
            return (start, end)
        except Exception:
            return (0.0, 0.0)

    def _emit_view_range(self) -> None:
        """Emit currently visible beat range based on scroll position + zoom."""
        try:
            a, b = self.visible_range_beats()
            self.view_range_changed.emit(a, b)
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: ANN001
        super().resizeEvent(event)
        self._emit_view_range()

    def set_automation_visible(self, visible: bool) -> None:
        if self._enhanced_automation is not None:
            self._enhanced_automation.setVisible(bool(visible))
        else:
            self.automation.setVisible(bool(visible))

    def set_snap_division(self, division: str) -> None:
        # map division string to beats (quarter-beat unit)
        div = str(division)
        mapping = {
            "1/4": 1.0,
            "1/8": 0.5,
            "1/16": 0.25,
            "1/32": 0.125,
            "1/64": 0.0625,
        }
        self.canvas.snap_beats = mapping.get(div, 0.25)
        self.canvas.update()
