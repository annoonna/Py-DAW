"""Project settings dialog (v0.0.13).

Central place for musical project settings:
- BPM
- Time signature
- Grid/Snap division

This is a GUI settings layer only; audio engine routing remains separate.
"""

from __future__ import annotations

import re
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QPushButton,
    QMessageBox,
    QFormLayout,
)

_TS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def normalize_ts(text: str) -> str:
    m = _TS_RE.match(text or "")
    if not m:
        return ""
    num = int(m.group(1))
    den = int(m.group(2))
    if num <= 0 or den <= 0:
        return ""
    return f"{num}/{den}"


class ProjectSettingsDialog(QDialog):
    def __init__(self, bpm: float, time_signature: str, snap_division: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Settings")
        self.setModal(True)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        layout.addLayout(form)

        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(20, 300)
        self.spin_bpm.setValue(int(round(float(bpm))))
        self.spin_bpm.setSuffix(" BPM")
        form.addRow(QLabel("Tempo:"), self.spin_bpm)

        self.cmb_ts = QComboBox()
        self.cmb_ts.setEditable(True)
        self.cmb_ts.addItems(["4/4", "3/4", "2/4", "6/8", "5/4", "7/8"])
        self.cmb_ts.setCurrentText(str(time_signature or "4/4"))
        form.addRow(QLabel("Time Signature:"), self.cmb_ts)

        self.cmb_grid = QComboBox()
        self.cmb_grid.addItems(["1/4", "1/8", "1/16", "1/32", "1/64"])
        self.cmb_grid.setCurrentText(snap_division if snap_division in ["1/4","1/8","1/16","1/32","1/64"] else "1/16")
        form.addRow(QLabel("Grid/Snap:"), self.cmb_grid)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_ok = QPushButton("OK")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept)

    def _accept(self) -> None:
        ts = normalize_ts(self.cmb_ts.currentText())
        if not ts:
            QMessageBox.warning(self, "Project Settings", "Ungültige Time Signature. Beispiel: 4/4 oder 6/8.")
            return
        self.cmb_ts.setCurrentText(ts)
        self.accept()

    def values(self) -> tuple[float, str, str]:
        bpm = float(self.spin_bpm.value())
        ts = normalize_ts(self.cmb_ts.currentText()) or "4/4"
        grid = str(self.cmb_grid.currentText())
        return bpm, ts, grid
