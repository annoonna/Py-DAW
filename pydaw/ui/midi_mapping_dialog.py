"""MIDI Mapping dialog (v0.0.20.397).

Universal MIDI Learn / Controller Mapping dialog.
Shows ALL mappable parameters (tracks, devices, instruments, transport).

Features:
- Tree-structured parameter browser grouped by track
- Search filter
- MIDI Learn with visual feedback
- Remove / Clear mappings
- Mapping list with CC number, channel, target info
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QComboBox, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QSplitter, QGroupBox,
)
from PyQt6.QtCore import Qt

from pydaw.services.project_service import ProjectService
from pydaw.services.midi_mapping_service import (
    MidiMappingService, MappingTarget, discover_mappable_params,
)


class MidiMappingDialog(QDialog):
    def __init__(self, project: ProjectService, mapping: MidiMappingService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎛️ MIDI Controller Mapping")
        self.setModal(True)
        self.setMinimumSize(800, 600)

        self.project = project
        self.mapping = mapping

        layout = QVBoxLayout(self)

        # ── Active Mappings ──
        grp_mappings = QGroupBox("Aktive Mappings")
        ml = QVBoxLayout(grp_mappings)

        self.lst = QListWidget()
        self.lst.setStyleSheet("QListWidget { font-family: monospace; }")
        ml.addWidget(self.lst, 1)

        btn_row = QHBoxLayout()
        self.btn_remove = QPushButton("Mapping entfernen")
        self.btn_remove.clicked.connect(self._remove)
        self.btn_clear_all = QPushButton("Alle entfernen")
        self.btn_clear_all.clicked.connect(self._clear_all)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_clear_all)
        btn_row.addStretch(1)
        ml.addLayout(btn_row)

        layout.addWidget(grp_mappings)

        # ── Parameter Browser + Learn ──
        grp_learn = QGroupBox("MIDI Learn — Parameter auswählen und Controller bewegen")
        ll = QVBoxLayout(grp_learn)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Suche:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Parameter filtern…")
        self.search.textChanged.connect(self._on_search)
        search_row.addWidget(self.search, 1)
        ll.addLayout(search_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Parameter", "Typ"])
        self.tree.setColumnWidth(0, 400)
        self.tree.setAlternatingRowColors(True)
        ll.addWidget(self.tree, 1)

        learn_row = QHBoxLayout()
        self.btn_learn = QPushButton("🎓 MIDI Learn starten")
        self.btn_learn.setStyleSheet(
            "QPushButton { background: #2a3a4a; border: 1px solid #4a8aca; "
            "border-radius: 4px; color: #90c4f0; font-size: 12px; padding: 4px 12px; }"
            "QPushButton:hover { background: #3a4a5a; }"
            "QPushButton:disabled { background: #1a2a3a; color: #555; }"
        )
        self.btn_learn.clicked.connect(self._learn)
        self.btn_cancel_learn = QPushButton("Abbrechen")
        self.btn_cancel_learn.clicked.connect(self._cancel_learn)
        self.btn_cancel_learn.setEnabled(False)

        self._learn_status = QLabel("")
        self._learn_status.setStyleSheet("color: #ffaa44; font-weight: bold;")

        learn_row.addWidget(self.btn_learn)
        learn_row.addWidget(self.btn_cancel_learn)
        learn_row.addWidget(self._learn_status, 1)
        ll.addLayout(learn_row)

        layout.addWidget(grp_learn)

        # ── OK/Close ──
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("Schließen")
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)

        # Signals
        try:
            self.project.project_updated.connect(self._refresh_mappings)
        except Exception:
            pass
        try:
            self.mapping.learn_completed.connect(self._on_learn_completed)
        except Exception:
            pass
        try:
            self.mapping.mapping_changed.connect(self._refresh_mappings)
        except Exception:
            pass

        self._refresh_mappings()
        self._build_param_tree()

    def _refresh_mappings(self) -> None:
        """Reload the active mappings list."""
        try:
            self.lst.clear()
            for m in self.mapping.mappings():
                if m.get("type") == "cc":
                    cc = m.get("control", "?")
                    ch = m.get("channel", 0)
                    param = m.get("param", "?")
                    tid = m.get("track_id", "")
                    toggle = " [Toggle]" if m.get("is_toggle") else ""
                    # Find track name
                    tname = tid
                    try:
                        for t in self.project.ctx.project.tracks:
                            if t.id == tid:
                                tname = t.name or tid
                                break
                    except Exception:
                        pass
                    if tid == "__transport__":
                        tname = "Transport"
                    item = QListWidgetItem(
                        f"CC{cc:>3}  ch{ch}  →  {tname} / {param}{toggle}"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, m)
                else:
                    item = QListWidgetItem(str(m))
                self.lst.addItem(item)

            learning = self.mapping.is_learning()
            self.btn_learn.setEnabled(not learning)
            self.btn_cancel_learn.setEnabled(learning)
            if not learning:
                self._learn_status.setText("")
        except Exception:
            pass

    def _build_param_tree(self, filter_text: str = "") -> None:
        """Build the parameter tree from project model."""
        try:
            self.tree.clear()
            q = filter_text.strip().lower()

            groups = discover_mappable_params(self.project)

            for track_id, track_name, params in groups:
                if not params:
                    continue

                # Filter
                filtered_params = []
                for pkey, plabel, pmin, pmax, ptoggle in params:
                    hay = f"{track_name} {plabel} {pkey}".lower()
                    if q and q not in hay:
                        continue
                    filtered_params.append((pkey, plabel, pmin, pmax, ptoggle))

                if not filtered_params:
                    continue

                track_item = QTreeWidgetItem([track_name, ""])
                track_item.setExpanded(bool(q))  # auto-expand when searching

                for pkey, plabel, pmin, pmax, ptoggle in filtered_params:
                    ptype = "Toggle" if ptoggle else f"{pmin:.1f}..{pmax:.1f}"
                    # Check if already mapped
                    existing = self.mapping.get_mapping_for_param(track_id, pkey)
                    mapped_hint = f" [CC{existing.get('control', '?')}]" if existing else ""

                    child = QTreeWidgetItem([f"{plabel}{mapped_hint}", ptype])
                    child.setData(0, Qt.ItemDataRole.UserRole, {
                        "track_id": track_id,
                        "param": pkey,
                        "label": plabel,
                        "min_val": pmin,
                        "max_val": pmax,
                        "is_toggle": ptoggle,
                    })
                    track_item.addChild(child)

                self.tree.addTopLevelItem(track_item)

            # Expand first few
            for i in range(min(3, self.tree.topLevelItemCount())):
                self.tree.topLevelItem(i).setExpanded(True)

        except Exception:
            pass

    def _on_search(self, text: str) -> None:
        try:
            self._build_param_tree(text)
        except Exception:
            pass

    def _learn(self) -> None:
        """Start MIDI Learn for the selected parameter."""
        try:
            item = self.tree.currentItem()
            if item is None or item.childCount() > 0:
                QMessageBox.information(
                    self, "MIDI Learn",
                    "Bitte wähle einen Parameter im Baum aus."
                )
                return

            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                return

            track_id = str(data.get("track_id", ""))
            param = str(data.get("param", ""))
            min_val = float(data.get("min_val", 0.0))
            max_val = float(data.get("max_val", 1.0))
            is_toggle = bool(data.get("is_toggle", False))
            label = str(data.get("label", param))

            target = MappingTarget(
                track_id=track_id,
                param=param,
                min_val=min_val,
                max_val=max_val,
                is_toggle=is_toggle,
            )
            self.mapping.start_learn(target)
            self._learn_status.setText(f"⏳ Warte auf CC-Controller für: {label}")
            self.btn_learn.setEnabled(False)
            self.btn_cancel_learn.setEnabled(True)
        except Exception:
            pass

    def _cancel_learn(self) -> None:
        try:
            self.mapping.cancel_learn()
            self._learn_status.setText("")
            self.btn_learn.setEnabled(True)
            self.btn_cancel_learn.setEnabled(False)
        except Exception:
            pass

    def _on_learn_completed(self) -> None:
        try:
            self._learn_status.setText("✅ Mapping erfolgreich!")
            self.btn_learn.setEnabled(True)
            self.btn_cancel_learn.setEnabled(False)
            self._refresh_mappings()
            self._build_param_tree(self.search.text() or "")
        except Exception:
            pass

    def _remove(self) -> None:
        try:
            row = self.lst.currentRow()
            if row >= 0:
                self.mapping.remove_mapping(row)
                self._refresh_mappings()
                self._build_param_tree(self.search.text() or "")
        except Exception:
            pass

    def _clear_all(self) -> None:
        try:
            count = len(self.mapping.mappings())
            if count == 0:
                return
            reply = QMessageBox.question(
                self, "MIDI Mapping",
                f"Alle {count} Mappings wirklich entfernen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.project.ctx.project.midi_mappings = []
                self.project.project_updated.emit()
                try:
                    self.mapping.mapping_changed.emit()
                except Exception:
                    pass
                self._refresh_mappings()
                self._build_param_tree(self.search.text() or "")
        except Exception:
            pass
