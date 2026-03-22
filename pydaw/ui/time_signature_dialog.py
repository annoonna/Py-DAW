"""Time Signature dialog (v0.0.12)."""

from __future__ import annotations

import re
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox

_TS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def normalize_ts(text: str) -> str:
    m = _TS_RE.match(text or "")
    if not m:
        return ""
    num = int(m.group(1))
    den = int(m.group(2))
    if num <= 0 or den <= 0:
        return ""
    # allow common denominators; keep open but prevent absurd 0
    return f"{num}/{den}"


class TimeSignatureDialog(QDialog):
    def __init__(self, current: str = "4/4", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Time Signature")
        self.setModal(True)

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Time Signature (z. B. 4/4, 3/4, 6/8):"))
        layout.addLayout(row)

        self.cmb = QComboBox()
        self.cmb.setEditable(True)
        self.cmb.addItems(["4/4", "3/4", "2/4", "6/8", "5/4", "7/8"])
        self.cmb.setCurrentText(str(current or "4/4"))
        layout.addWidget(self.cmb)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Abbrechen")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept)

    def _accept(self) -> None:
        ts = normalize_ts(self.cmb.currentText())
        if not ts:
            QMessageBox.warning(self, "Time Signature", "Ungültiges Format. Beispiel: 4/4 oder 6/8.")
            return
        self.cmb.setCurrentText(ts)
        self.accept()

    def value(self) -> str:
        ts = normalize_ts(self.cmb.currentText())
        return ts or "4/4"
