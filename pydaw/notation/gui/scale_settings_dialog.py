from __future__ import annotations

from pydaw.notation.qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QDialogButtonBox
)

from pydaw.notation.scales.database import SCALE_DB


class ScaleSettingsDialog(QDialog):
    """Dialog zur Auswahl von System und Skala.

    Der Browser-Block unten wurde bewusst aus dem Hauptlayout entfernt, um die Oberfläche
    DAW-typisch aufzuräumen. Die Auswahl bleibt über diesen Dialog vollständig steuerbar.
    """

    def __init__(self, scale_browser, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System & Skala")
        self.setMinimumWidth(420)
        self.scale = scale_browser

        root = QVBoxLayout(self)

        # System
        row_sys = QHBoxLayout()
        row_sys.addWidget(QLabel("System:"))
        self.system_box = QComboBox()
        self.system_box.addItems(SCALE_DB.list_systems())
        row_sys.addWidget(self.system_box, 1)
        root.addLayout(row_sys)

        # Skala
        row_scale = QHBoxLayout()
        row_scale.addWidget(QLabel("Skala:"))
        self.scale_box = QComboBox()
        row_scale.addWidget(self.scale_box, 1)
        root.addLayout(row_scale)

        # Actions
        row_btn = QHBoxLayout()
        self.btn_play_scale = QPushButton("▶ Skala abspielen")
        row_btn.addWidget(self.btn_play_scale)
        row_btn.addStretch(1)
        root.addLayout(row_btn)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        root.addWidget(bb)

        # Init from current hidden browser state
        try:
            cur_sys = self.scale.system_box.currentText()
        except Exception:
            cur_sys = ""
        if cur_sys:
            idx = self.system_box.findText(cur_sys)
            if idx >= 0:
                self.system_box.setCurrentIndex(idx)
        self._reload_scales(self.system_box.currentText())
        try:
            cur_scale = self.scale.scale_box.currentText()
            idx2 = self.scale_box.findText(cur_scale)
            if idx2 >= 0:
                self.scale_box.setCurrentIndex(idx2)
        except Exception:
            pass

        # Wiring
        self.system_box.currentTextChanged.connect(self._reload_scales)
        self.btn_play_scale.clicked.connect(self._play_scale)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

    def _reload_scales(self, system: str):
        self.scale_box.clear()
        self.scale_box.addItems(SCALE_DB.list_scales(system))

    def _play_scale(self):
        # Apply selection to backend and play
        self._apply_to_backend()
        try:
            self.scale.play_scale_notes()
        except Exception:
            pass

    def _apply_to_backend(self):
        # Update hidden backend widgets (single source of truth)
        try:
            sys = self.system_box.currentText()
            if sys:
                self.scale.system_box.setCurrentText(sys)
                self.scale.update_scales(sys)
        except Exception:
            pass
        try:
            sc = self.scale_box.currentText()
            if sc:
                self.scale.scale_box.setCurrentText(sc)
        except Exception:
            pass

    def accept(self):
        self._apply_to_backend()
        super().accept()
