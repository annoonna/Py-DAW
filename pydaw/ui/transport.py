"""Transport panel widgets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QCheckBox,
    QSpinBox,
    QComboBox,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt



class TransportPanel(QWidget):
    bpm_changed = Signal(float)

    play_clicked = Signal()
    stop_clicked = Signal()
    rew_clicked = Signal()
    ff_clicked = Signal()
    record_clicked = Signal(bool)

    loop_toggled = Signal(bool)
    punch_toggled = Signal(bool)
    pre_roll_changed = Signal(int)
    post_roll_changed = Signal(int)

    time_signature_changed = Signal(str)
    metronome_toggled = Signal(bool)
    count_in_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.btn_rew = QPushButton("⏮")
        self.btn_ff = QPushButton("⏭")
        self.btn_play = QPushButton("▶")
        self.btn_stop = QPushButton("■")
        self.btn_rec = QPushButton("●")
        self.btn_loop = QPushButton("⟲")

        for b in (self.btn_rew, self.btn_ff, self.btn_play, self.btn_stop, self.btn_rec, self.btn_loop):
            b.setFixedSize(36, 28)

        layout.addWidget(self.btn_rew)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_rec)
        layout.addWidget(self.btn_loop)
        layout.addWidget(self.btn_ff)

        layout.addSpacing(6)

        self.lbl_time = QLabel("00:00.000 | Beat 0.00")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.lbl_time.setMinimumWidth(168)
        self.lbl_time.setMaximumWidth(190)
        self.lbl_time.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.lbl_time.setToolTip("Aktuelle Zeit und Beat-Position")
        layout.addWidget(self.lbl_time)

        layout.addSpacing(4)

        self.bpm = QSpinBox()
        self.bpm.setRange(20, 300)
        self.bpm.setValue(120)
        self.bpm.setSuffix(" BPM")
        self.bpm.setFixedWidth(92)
        self.bpm.setToolTip("Projekt-Tempo in BPM")
        layout.addWidget(self.bpm)

        lbl_ts = QLabel("TS")
        lbl_ts.setToolTip("Taktart")
        layout.addWidget(lbl_ts)

        self.cmb_ts = QComboBox()
        self.cmb_ts.setEditable(True)
        self.cmb_ts.addItems(["4/4", "3/4", "2/4", "6/8", "5/4", "7/8"])
        self.cmb_ts.setCurrentText("4/4")
        self.cmb_ts.setFixedWidth(72)
        self.cmb_ts.setToolTip("Taktart")
        layout.addWidget(self.cmb_ts)

        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setToolTip("Loop-Wiedergabe")
        layout.addWidget(self.chk_loop)

        self.chk_met = QCheckBox("Metro")
        self.chk_met.setToolTip("Metronom Ein/Aus")
        layout.addWidget(self.chk_met)

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self.chk_punch = QCheckBox("Punch")
        self.chk_punch.setToolTip("Punch In/Out: Record only within the punch region")
        layout.addWidget(self.chk_punch)

        lbl_pre = QLabel("Pre")
        lbl_pre.setToolTip("Angabe in Takten")
        layout.addWidget(lbl_pre)
        self.spin_pre_roll = QSpinBox()
        self.spin_pre_roll.setRange(0, 8)
        self.spin_pre_roll.setValue(0)
        self.spin_pre_roll.setToolTip("Pre-Roll: Takte vor dem Punch-In abspielen")
        self.spin_pre_roll.setFixedWidth(58)
        layout.addWidget(self.spin_pre_roll)

        lbl_post = QLabel("Post")
        lbl_post.setToolTip("Angabe in Takten")
        layout.addWidget(lbl_post)
        self.spin_post_roll = QSpinBox()
        self.spin_post_roll.setRange(0, 8)
        self.spin_post_roll.setValue(0)
        self.spin_post_roll.setToolTip("Post-Roll: Takte nach dem Punch-Out abspielen")
        self.spin_post_roll.setFixedWidth(58)
        layout.addWidget(self.spin_post_roll)

        lbl_count_in = QLabel("Count-In")
        lbl_count_in.setToolTip("Angabe in Takten")
        layout.addWidget(lbl_count_in)
        self.spin_countin = QSpinBox()
        self.spin_countin.setRange(0, 8)
        self.spin_countin.setValue(0)
        self.spin_countin.setToolTip("Count-In vor der Aufnahme (in Takten)")
        self.spin_countin.setFixedWidth(58)
        layout.addWidget(self.spin_countin)

        layout.addSpacing(10)
        layout.addStretch(1)

        # v0.0.20.663: Responsive widget groups — hidden on narrow widths
        # Tier 1 (<700px): hide Pre/Post/Count-In
        # Tier 2 (<520px): additionally hide Punch, TS, Loop/Metro checkboxes
        self._responsive_tier1 = [lbl_pre, self.spin_pre_roll,
                                  lbl_post, self.spin_post_roll,
                                  lbl_count_in, self.spin_countin]
        self._responsive_tier2 = [self.chk_punch, lbl_ts, self.cmb_ts,
                                  self.chk_loop, self.chk_met]

        # wiring
        self.bpm.valueChanged.connect(lambda v: self.bpm_changed.emit(float(v)))
        self.cmb_ts.currentTextChanged.connect(lambda t: self.time_signature_changed.emit(str(t)))
        self.chk_loop.toggled.connect(self.loop_toggled.emit)
        self.chk_met.toggled.connect(self.metronome_toggled.emit)
        self.chk_punch.toggled.connect(self.punch_toggled.emit)
        self.spin_pre_roll.valueChanged.connect(lambda v: self.pre_roll_changed.emit(int(v)))
        self.spin_post_roll.valueChanged.connect(lambda v: self.post_roll_changed.emit(int(v)))
        self.spin_countin.valueChanged.connect(lambda v: self.count_in_changed.emit(int(v)))

        self.btn_play.clicked.connect(self.play_clicked.emit)
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        self.btn_rew.clicked.connect(self.rew_clicked.emit)
        self.btn_ff.clicked.connect(self.ff_clicked.emit)

        self._rec_on = False
        self.btn_rec.setCheckable(True)
        self.btn_rec.toggled.connect(self.record_clicked.emit)

    def set_time(self, beat: float, bpm: float) -> None:
        # placeholder conversion of beats to seconds
        secs = float(beat) * 60.0 / max(1.0, float(bpm))
        mm = int(secs // 60)
        ss = secs - mm * 60
        self.lbl_time.setText(f"{mm:02d}:{ss:06.3f} | Beat {beat:0.2f}")

    def set_time_signature(self, ts: str) -> None:
        ts = str(ts or "4/4")
        if self.cmb_ts.currentText() != ts:
            self.cmb_ts.blockSignals(True)
            self.cmb_ts.setCurrentText(ts)
            self.cmb_ts.blockSignals(False)

    def set_bpm(self, bpm: float | int) -> None:
        """Update BPM UI without emitting bpm_changed.

        PyQt6 is configured to abort the whole process on uncaught slot
        exceptions on some setups. We therefore avoid AttributeErrors by
        providing a stable API used by MainWindow (project open sync).
        """
        try:
            v = int(round(float(bpm)))
        except Exception:
            v = 120
        v = max(20, min(300, v))
        if int(self.bpm.value()) != int(v):
            self.bpm.blockSignals(True)
            self.bpm.setValue(int(v))
            self.bpm.blockSignals(False)

    def set_punch(self, enabled: bool) -> None:
        """Update Punch checkbox without emitting signal."""
        enabled = bool(enabled)
        if self.chk_punch.isChecked() != enabled:
            self.chk_punch.blockSignals(True)
            self.chk_punch.setChecked(enabled)
            self.chk_punch.blockSignals(False)

    def set_pre_roll(self, bars: int) -> None:
        """Update Pre-Roll spinbox without emitting signal."""
        bars = max(0, min(8, int(bars)))
        if self.spin_pre_roll.value() != bars:
            self.spin_pre_roll.blockSignals(True)
            self.spin_pre_roll.setValue(bars)
            self.spin_pre_roll.blockSignals(False)

    def set_post_roll(self, bars: int) -> None:
        """Update Post-Roll spinbox without emitting signal."""
        bars = max(0, min(8, int(bars)))
        if self.spin_post_roll.value() != bars:
            self.spin_post_roll.blockSignals(True)
            self.spin_post_roll.setValue(bars)
            self.spin_post_roll.blockSignals(False)

    # ---- v0.0.20.663: Responsive Verdichtung ----

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Hide secondary controls when the panel is too narrow.

        Tier thresholds are intentionally generous so that essential
        transport buttons (Play/Stop/Rec) and BPM always remain visible.
        Purely visual — no signals are disconnected and hidden widgets
        keep their values.
        """
        super().resizeEvent(event)
        try:
            w = self.width()
            # Tier 1: Pre/Post/Count-In — hide below 700px
            show_t1 = w >= 700
            for widget in self._responsive_tier1:
                widget.setVisible(show_t1)
            # Tier 2: Punch/TS/Loop/Metro — hide below 520px
            show_t2 = w >= 520
            for widget in self._responsive_tier2:
                widget.setVisible(show_t2)
        except Exception:
            pass
