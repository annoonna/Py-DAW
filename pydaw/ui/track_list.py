"""Track list panel (v0.0.4).

Left side of the Arranger: track selection + quick add/remove buttons.
This is still placeholder UI; real track controls come later.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QMenu,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from pydaw.services.project_service import ProjectService
from pydaw.ui.bounce_freeze_dialog import ask_bounce_freeze_options


class TrackListWidget(QWidget):
    selected_track_changed = Signal(str)  # track_id (empty if none)

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project

        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Spuren"))

        self.btn_add = QPushButton("+")
        self.btn_add.setToolTip("Spur hinzufügen")
        self.btn_remove = QPushButton("–")
        self.btn_remove.setToolTip("Ausgewählte Spur entfernen")
        header.addWidget(self.btn_add)
        header.addWidget(self.btn_remove)

        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.keyPressEvent = self._on_list_key_press
        self.list.setToolTip(
            "Tracks umbenennen:\n"
            "• Doppelklick auf Track-Name\n"
            "• Rechtsklick → 'Umbenennen...'\n"
            "\n"
            "Tracks auswählen: Einfach klicken"
        )

        layout.addWidget(self.list, 1)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        track_id = item.data(Qt.ItemDataRole.UserRole)
        if not track_id:
            return
        trk = next((t for t in self.project.ctx.project.tracks if t.id == str(track_id)), None)
        if not trk or getattr(trk, "kind", "") == "master":
            return
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self,
            "Track umbenennen",
            f"Neuer Name für '{trk.name}':",
            text=trk.name,
        )
        if ok and new_name.strip():
            try:
                self.project.rename_track(str(track_id), new_name.strip())
            except Exception as e:
                print(f"[TrackList] Rename failed: {e}")

    def _wire(self) -> None:
        self.project.project_updated.connect(self.refresh)
        self.list.currentItemChanged.connect(self._on_selection_changed)
        self.btn_add.clicked.connect(self._open_add_menu)
        self.btn_remove.clicked.connect(self._remove_selected)

    def _track_freeze_ui_meta(self, trk) -> tuple[str, str, bool, bool]:
        suffix = ""
        tooltip = ""
        is_proxy = False
        is_frozen_source = False
        try:
            ist = getattr(trk, "instrument_state", None) or {}
            proxy = ist.get("freeze_proxy") if isinstance(ist, dict) else None
            if isinstance(proxy, dict):
                is_proxy = True
                srcs = [str(x) for x in (proxy.get("source_track_ids") or []) if str(x)]
                label = str(proxy.get("label") or "Freeze")
                suffix = "  [❄ PROXY]"
                tooltip = f"Freeze-Proxy\nLabel: {label}\nQuellen: {', '.join(srcs) if srcs else '-'}"
        except Exception:
            pass
        if not is_proxy:
            try:
                track_id = str(getattr(trk, "id", "") or "")
                proxies = []
                for other in (self.project.ctx.project.tracks or []):
                    meta = getattr(other, "instrument_state", None) or {}
                    info = meta.get("freeze_proxy") if isinstance(meta, dict) else None
                    if isinstance(info, dict) and track_id in [str(x) for x in (info.get("source_track_ids") or [])]:
                        proxies.append(str(getattr(other, "name", "") or getattr(other, "id", "") or "Proxy"))
                if proxies:
                    is_frozen_source = True
                    suffix = "  [❄ SRC]"
                    tooltip = f"Als Freeze-Quelle verwendet\nProxy-Spuren: {', '.join(proxies[:4])}"
            except Exception:
                pass
        return suffix, tooltip, is_proxy, is_frozen_source

    def refresh(self) -> None:
        current_id = self.selected_track_id()
        self._refreshing = True
        self.list.blockSignals(True)
        self.list.clear()
        for trk in self.project.ctx.project.tracks:
            suffix, freeze_tip, is_proxy, is_frozen_source = self._track_freeze_ui_meta(trk)
            item = QListWidgetItem(f"{trk.name}  [{trk.kind}]{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, trk.id)
            if trk.kind == "master":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            try:
                base_tip = f"Track: {trk.name}\nTyp: {trk.kind}"
                if freeze_tip:
                    base_tip += f"\n\n{freeze_tip}"
                item.setToolTip(base_tip)
            except Exception:
                pass
            try:
                if is_proxy:
                    item.setBackground(QColor(40, 74, 106, 90))
                elif is_frozen_source:
                    item.setBackground(QColor(82, 106, 40, 70))
            except Exception:
                pass
            self.list.addItem(item)

        if self.list.count() > 0:
            if current_id:
                for i in range(self.list.count()):
                    if str(self.list.item(i).data(Qt.ItemDataRole.UserRole) or "") == str(current_id):
                        if self.list.currentRow() != i:
                            self.list.setCurrentRow(i)
                        break
            if self.list.currentRow() < 0:
                self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._refreshing = False

    def selected_track_id(self) -> str:
        item = self.list.currentItem()
        if not item:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _on_selection_changed(self) -> None:
        if bool(getattr(self, '_refreshing', False)):
            return
        self.selected_track_changed.emit(self.selected_track_id())

    def _open_add_menu(self) -> None:
        menu = QMenu(self)
        a_audio = menu.addAction("Audio-Spur hinzufügen")
        a_inst = menu.addAction("Instrumenten-Spur hinzufügen")
        a_bus = menu.addAction("FX/Bus-Spur hinzufügen")
        action = menu.exec(self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft()))
        if action == a_audio:
            self.project.add_track("audio")
        elif action == a_inst:
            self.project.add_track("instrument")
        elif action == a_bus:
            self.project.add_track("bus")

    def _remove_selected(self) -> None:
        tid = self.selected_track_id()
        if tid:
            self.project.remove_track(tid)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        track_id = item.data(Qt.ItemDataRole.UserRole)
        if not track_id:
            return
        full_text = str(item.text() or "").strip()
        if not full_text:
            return
        if "  [" in full_text:
            name = full_text.split("  [")[0].strip()
        else:
            name = full_text.strip()
        if not name:
            return
        try:
            self.project.rename_track(str(track_id), name)
        except Exception as e:
            print(f"[TrackList] Rename failed: {e}")

    def _on_list_key_press(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            tid = self.selected_track_id()
            if tid:
                trk = next((t for t in self.project.ctx.project.tracks if t.id == tid), None)
                if trk and getattr(trk, "kind", "") != "master":
                    try:
                        self.project.delete_track(tid)
                        event.accept()
                        return
                    except Exception as e:
                        print(f"[TrackList] Delete track failed: {e}")
        elif event.key() == Qt.Key.Key_F2:
            item = self.list.currentItem()
            if item:
                self.list.editItem(item)
                event.accept()
                return
        QListWidget.keyPressEvent(self.list, event)

    def _on_context_menu(self, pos):  # noqa: ANN001
        item = self.list.itemAt(pos)
        if item is None:
            return
        track_id = item.data(Qt.ItemDataRole.UserRole)
        if not track_id:
            return
        trk = next((t for t in self.project.ctx.project.tracks if t.id == str(track_id)), None)
        if trk is None:
            return

        menu = QMenu(self)
        a_rename = menu.addAction("Umbenennen…")
        a_freeze = None
        a_freeze_dry = None
        a_unfreeze = None
        a_group_freeze = None
        if trk.kind != "master":
            menu.addSeparator()
            a_freeze = menu.addAction("Spur einfrieren / bouncen…")
            a_freeze_dry = menu.addAction("Spur bouncen (Dry)…")
            proxy = None
            try:
                ist = getattr(trk, "instrument_state", None) or {}
                proxy = ist.get("freeze_proxy") if isinstance(ist, dict) else None
            except Exception:
                proxy = None
            if isinstance(proxy, dict):
                a_unfreeze = menu.addAction("Freeze-Quellen wieder aktivieren")
            group_id = str(getattr(trk, "track_group_id", "") or "")
            if group_id:
                try:
                    grouped = [t for t in (self.project.ctx.project.tracks or []) if str(getattr(t, "track_group_id", "") or "") == group_id and str(getattr(t, "kind", "")) != "master"]
                except Exception:
                    grouped = []
                if len(grouped) >= 2:
                    grp_name = str(getattr(trk, "track_group_name", "") or "Gruppe")
                    a_group_freeze = menu.addAction(f"Gruppe einfrieren / bouncen… ({grp_name})")
            menu.addSeparator()
        a_del = None
        if trk.kind != "master":
            a_del = menu.addAction("Track löschen")

        act = menu.exec(self.list.mapToGlobal(pos))
        if act == a_rename:
            self.list.editItem(item)
            return
        if a_freeze is not None and act == a_freeze:
            try:
                opts = ask_bounce_freeze_options(
                    self,
                    title="Spur einfrieren / bouncen",
                    info_text="Erstellt sicher eine neue Audio-Proxy-Spur aus der ausgewählten Spur. Optional werden Quellspur und Instrument danach deaktiviert/stumm geschaltet.",
                    default_label="Freeze",
                    include_fx=True,
                    disable_sources=True,
                    allow_disable_sources=True,
                )
                if opts.accepted:
                    self.project.bounce_tracks_to_new_audio_track(
                        [str(track_id)],
                        include_fx=bool(opts.include_fx),
                        disable_sources=bool(opts.disable_sources),
                        label=str(opts.label or "Freeze"),
                    )
            except Exception:
                pass
            return
        if a_freeze_dry is not None and act == a_freeze_dry:
            try:
                opts = ask_bounce_freeze_options(
                    self,
                    title="Spur bouncen (Dry)",
                    info_text="Erstellt sicher eine neue Audio-Spur ohne Insert-FX. Optional kann die Quellspur danach deaktiviert/stumm geschaltet werden.",
                    default_label="Bounce Dry",
                    include_fx=False,
                    disable_sources=False,
                    allow_disable_sources=True,
                )
                if opts.accepted:
                    self.project.bounce_tracks_to_new_audio_track(
                        [str(track_id)],
                        include_fx=bool(opts.include_fx),
                        disable_sources=bool(opts.disable_sources),
                        label=str(opts.label or "Bounce Dry"),
                    )
            except Exception:
                pass
            return
        if a_unfreeze is not None and act == a_unfreeze:
            try:
                self.project.restore_frozen_source_tracks(str(track_id), mute_proxy=True)
            except Exception:
                pass
            return
        if a_group_freeze is not None and act == a_group_freeze:
            try:
                group_id = str(getattr(trk, "track_group_id", "") or "")
                tids = [str(getattr(t, "id", "") or "") for t in (self.project.ctx.project.tracks or []) if str(getattr(t, "track_group_id", "") or "") == group_id and str(getattr(t, "kind", "")) != "master"]
                if tids:
                    opts = ask_bounce_freeze_options(
                        self,
                        title="Gruppe einfrieren / bouncen",
                        info_text="Erstellt sicher eine neue Audio-Proxy-Spur aus allen Tracks der Gruppe. Optional werden die Quellspuren danach deaktiviert/stumm geschaltet.",
                        default_label="Group Freeze",
                        include_fx=True,
                        disable_sources=True,
                        allow_disable_sources=True,
                    )
                    if opts.accepted:
                        self.project.bounce_tracks_to_new_audio_track(
                            tids,
                            include_fx=bool(opts.include_fx),
                            disable_sources=bool(opts.disable_sources),
                            label=str(opts.label or "Group Freeze"),
                        )
            except Exception:
                pass
            return
        if a_del is not None and act == a_del:
            try:
                self.project.delete_track(str(track_id))
            except Exception:
                pass
            return
