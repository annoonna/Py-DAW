from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QToolButton,
    QSizePolicy, QDoubleSpinBox, QCheckBox,
)

from .python_logo_button import PythonLogoButton


class ToolBarPanel(QWidget):
    """Tool row (below transport): Werkzeug / Grid + Follow/Loop.

    The Python badge is still owned here so its animation settings stay in one
    place, but MainWindow may reparent the button into the status strip for a
    calmer overall layout.

    Safety notes:
    - purely visual / layout-oriented changes
    - no transport/audio logic altered
    - combo sizes are widened so 1/16 and 1/32 stay readable
    """

    # Emitted when loop fields change: (enabled, start_beat, end_beat)
    loop_changed = Signal(bool, float, float)
    # Emitted when Follow toggle changes
    follow_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolBarPanel")

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(1)

        self._py_anim_enabled: bool = True
        self._py_orange: bool = False

        self._py_anim_timer = QTimer(self)
        self._py_anim_timer.setInterval(120_000)
        self._py_anim_timer.setSingleShot(True)
        self._py_anim_timer.timeout.connect(self._on_py_anim_timeout)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        combo_style = (
            "QComboBox {"
            " background: #2A2A2A; color: #F0F0F0; border: 1px solid #343434;"
            " border-radius: 6px; padding: 2px 12px 2px 10px; min-height: 28px; font-size: 13px; font-weight: 600; }"
            "QComboBox::drop-down {"
            " subcontrol-origin: padding; subcontrol-position: top right;"
            " width: 24px; border-left: 1px solid #343434; }"
            "QComboBox::down-arrow { width: 14px; height: 14px; }"
            "QComboBox QAbstractItemView { font-size: 13px; padding: 6px; }"
        )

        self.cmb_tool = QComboBox()
        self.cmb_tool.addItems(["Zeiger", "Pencil", "Eraser", "Knife"])
        self.cmb_tool.setToolTip("Werkzeug")
        self.cmb_tool.setFixedWidth(110)
        self.cmb_tool.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_tool.setStyleSheet(combo_style)

        self.cmb_grid = QComboBox()
        self.cmb_grid.addItems(["1/4", "1/8", "1/16", "1/32"])
        self.cmb_grid.setToolTip("Grid/Snap")
        self.cmb_grid.setFixedWidth(92)
        self.cmb_grid.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_grid.setStyleSheet(combo_style)

        # v0.0.20.439: Follow Playhead toggle
        self.btn_follow = QToolButton()
        self.btn_follow.setText("▶ Follow")
        self.btn_follow.setCheckable(True)
        self.btn_follow.setChecked(True)
        self.btn_follow.setAutoRaise(True)
        self.btn_follow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_follow.setToolTip("Arranger scrollt mit dem Playhead (Bitwig-Style)")
        self.btn_follow.setStyleSheet(
            "QToolButton { color: #aaa; padding: 2px 8px; font-size: 11px; }"
            "QToolButton:checked { color: #fff; background: #3a6fa0; border-radius: 3px; }"
        )
        self.btn_follow.toggled.connect(lambda c: self.follow_changed.emit(c))

        # v0.0.20.439: Loop range fields — compact
        _spn_style = (
            "QDoubleSpinBox { background: #2a2a30; color: #ddd; border: 1px solid #555;"
            " border-radius: 2px; padding: 1px 2px; font-size: 11px; }"
        )
        self.chk_loop = QCheckBox("L")
        self.chk_loop.setStyleSheet("color: #BBBBBB; font-size: 11px;")
        self.chk_loop.setToolTip("Loop-Region Ein/Aus")

        self.spn_loop_start = QDoubleSpinBox()
        self.spn_loop_start.setRange(1.0, 9999.0)
        self.spn_loop_start.setValue(1.0)
        self.spn_loop_start.setDecimals(0)
        self.spn_loop_start.setMaximumWidth(48)
        self.spn_loop_start.setToolTip("Loop Start (Bar)")
        self.spn_loop_start.setStyleSheet(_spn_style)

        lbl_bis = QLabel("–")
        lbl_bis.setStyleSheet("color: #666; font-size: 11px;")
        lbl_bis.setFixedWidth(8)

        self.spn_loop_end = QDoubleSpinBox()
        self.spn_loop_end.setRange(1.0, 9999.0)
        self.spn_loop_end.setValue(5.0)
        self.spn_loop_end.setDecimals(0)
        self.spn_loop_end.setMaximumWidth(48)
        self.spn_loop_end.setToolTip("Loop Ende (Bar)")
        self.spn_loop_end.setStyleSheet(_spn_style)

        # Wire loop field changes
        self.chk_loop.toggled.connect(self._emit_loop)
        self.spn_loop_start.valueChanged.connect(self._emit_loop)
        self.spn_loop_end.valueChanged.connect(self._emit_loop)

        # Backward compat: btn_auto alias (some code references it for sync)
        self.btn_auto = self.btn_follow

        # --- Python logo button ---
        self.btn_python = PythonLogoButton()
        self.btn_python.setObjectName("pythonLogoBtn")
        self.btn_python.setText("")

        # Left controls
        layout.addWidget(self.cmb_tool)
        layout.addWidget(self.cmb_grid)
        layout.addSpacing(10)

        # Right-side controls
        layout.addWidget(self.btn_follow)
        layout.addSpacing(6)
        layout.addWidget(self.chk_loop)
        layout.addWidget(self.spn_loop_start)
        layout.addWidget(lbl_bis)
        layout.addWidget(self.spn_loop_end)
        layout.addSpacing(6)
        layout.addWidget(self.btn_python)

        # v0.0.20.663: Responsive widget groups
        # Tier 1 (<480px): hide loop range spinboxes
        # Tier 2 (<350px): additionally hide Follow button + Loop checkbox
        self._responsive_tier1 = [self.spn_loop_start, lbl_bis,
                                  self.spn_loop_end]
        self._responsive_tier2 = [self.btn_follow, self.chk_loop]

        self._sync_python_btn_size()

    def _emit_loop(self) -> None:
        """Emit loop_changed with current values (bars → beats, 4 beats/bar)."""
        try:
            enabled = self.chk_loop.isChecked()
            start_beat = max(0.0, (self.spn_loop_start.value() - 1.0) * 4.0)
            end_beat = max(start_beat + 1.0, (self.spn_loop_end.value() - 1.0) * 4.0)
            self.loop_changed.emit(enabled, start_beat, end_beat)
        except Exception:
            pass

    def set_loop_from_transport(self, enabled: bool, start_beat: float, end_beat: float) -> None:
        """Update loop fields from transport (without re-emitting)."""
        self.chk_loop.blockSignals(True)
        self.spn_loop_start.blockSignals(True)
        self.spn_loop_end.blockSignals(True)
        try:
            self.chk_loop.setChecked(bool(enabled))
            self.spn_loop_start.setValue(1.0 + float(start_beat) / 4.0)
            self.spn_loop_end.setValue(1.0 + float(end_beat) / 4.0)
        finally:
            self.chk_loop.blockSignals(False)
            self.spn_loop_start.blockSignals(False)
            self.spn_loop_end.blockSignals(False)

    # ---------------- Python logo animation ----------------

    def python_logo_animation_enabled(self) -> bool:
        return bool(self._py_anim_enabled)

    def set_python_logo_animation_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._py_anim_enabled = enabled

        if not enabled:
            try:
                self._py_anim_timer.stop()
            except Exception:
                pass
            self._py_orange = False
            try:
                self.btn_python.reset_default_colors()
            except Exception:
                pass
            return

        self._py_orange = False
        try:
            self.btn_python.reset_default_colors()
        except Exception:
            pass
        if self._py_anim_timer.isActive():
            self._py_anim_timer.stop()
        self._py_anim_timer.start()

    def _on_py_anim_timeout(self) -> None:
        if not self._py_anim_enabled:
            return
        self._py_orange = True
        try:
            self.btn_python.set_orange()
        except Exception:
            pass

    # ---------------- Sizing ----------------

    def _sync_python_btn_size(self) -> None:
        # Keep the Python badge clearly readable in the compact top bar.
        try:
            h = max(28, min(34, int(self.height()) - 4))
            self.btn_python.setFixedSize(h, h)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_python_btn_size()
        # v0.0.20.663: Responsive Verdichtung
        try:
            w = self.width()
            # Tier 1: Loop range — hide below 480px
            show_t1 = w >= 480
            for widget in self._responsive_tier1:
                widget.setVisible(show_t1)
            # Tier 2: Follow + Loop checkbox — hide below 350px
            show_t2 = w >= 350
            for widget in self._responsive_tier2:
                widget.setVisible(show_t2)
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self._py_anim_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
