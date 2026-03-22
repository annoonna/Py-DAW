"""MIDI Settings dialog (v0.0.20.406) — Multi-Device Support.

Zeigt alle verfügbaren MIDI-Inputs als Checkbox-Liste.
Mehrere Geräte können gleichzeitig verbunden werden.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt

from pydaw.services.midi_service import MidiService


class MidiSettingsDialog(QDialog):
    def __init__(self, midi: MidiService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MIDI Settings")
        self.setModal(True)
        self.midi = midi
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("MIDI Inputs (Mehrfachauswahl möglich):"))
        self.lst = QListWidget()
        self.lst.setMinimumHeight(200)
        layout.addWidget(self.lst, 1)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_apply = QPushButton("Verbinden")
        self.btn_disconnect_all = QPushButton("Alle trennen")
        row.addWidget(self.btn_refresh)
        row.addStretch(1)
        row.addWidget(self.btn_disconnect_all)
        row.addWidget(self.btn_apply)
        layout.addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self.status_label)

        row2 = QHBoxLayout()
        row2.addStretch(1)
        self.btn_ok = QPushButton("OK")
        row2.addWidget(self.btn_ok)
        layout.addLayout(row2)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_disconnect_all.clicked.connect(self._disconnect_all)

        self.refresh()

    def refresh(self) -> None:
        self.lst.clear()
        ins = self.midi.list_inputs()
        connected = set(self.midi.connected_inputs())

        if not ins:
            self.lst.addItem("(keine MIDI Inputs gefunden)")
            self.lst.setEnabled(False)
            self._update_status(connected)
            return

        self.lst.setEnabled(True)
        for name in ins:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if name in connected:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.lst.addItem(item)

        self._update_status(connected)

    def _update_status(self, connected) -> None:
        n = len(connected)
        if n == 0:
            self.status_label.setText("Kein MIDI-Gerät verbunden.")
        elif n == 1:
            self.status_label.setText(f"1 Gerät verbunden: {list(connected)[0]}")
        else:
            self.status_label.setText(f"{n} Geräte verbunden.")

    def _apply(self) -> None:
        """Connect checked devices, disconnect unchecked ones."""
        if not self.lst.isEnabled():
            return

        connected = set(self.midi.connected_inputs())
        wanted = set()

        for i in range(self.lst.count()):
            item = self.lst.item(i)
            if item is None:
                continue
            name = item.text()
            if item.checkState() == Qt.CheckState.Checked:
                wanted.add(name)

        # Disconnect devices no longer wanted
        for name in connected - wanted:
            self.midi.disconnect_input(name)

        # Connect newly wanted devices
        for name in wanted - connected:
            self.midi.connect_input(name)

        self.refresh()

    def _disconnect_all(self) -> None:
        self.midi.disconnect_input()
        self.refresh()
