from __future__ import annotations

from pydaw.notation.qt_compat import QWidget, QHBoxLayout, QPushButton, QLabel, QSpinBox, QCheckBox
from pydaw.notation.qt_compat import Qt


class TransportBar(QWidget):
    """DAW-ähnlicher Transportbereich (Play/Stop/Loop/Cursor).

    Der Playback-Thread existiert weiterhin im ScaleBrowser (PlaybackWorker).
    Die TransportBar steuert diesen Thread und setzt den Playhead im ScoreView.
    """

    def __init__(self, score_view, scale_browser, parent=None):
        super().__init__(parent)
        self.score = score_view
        self.scale = scale_browser

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(8)

        # Transport buttons
        self.btn_home = QPushButton("⏮")
        self.btn_back = QPushButton("⏪")
        self.btn_play = QPushButton("▶")
        self.btn_stop = QPushButton("⏹")
        self.btn_fwd = QPushButton("⏩")

        for b in (self.btn_home, self.btn_back, self.btn_play, self.btn_stop, self.btn_fwd):
            b.setFixedWidth(44)
            b.setFocusPolicy(Qt.NoFocus)

        row.addWidget(self.btn_home)
        row.addWidget(self.btn_back)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_stop)
        row.addWidget(self.btn_fwd)

        row.addSpacing(10)

        # Loop
        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setChecked(bool(getattr(self.scale, "loop").isChecked()))
        self.btn_loop_a = QPushButton("A")
        self.btn_loop_b = QPushButton("B")
        self.btn_loop_clear = QPushButton("✖")
        for b in (self.btn_loop_a, self.btn_loop_b, self.btn_loop_clear):
            b.setFixedWidth(36)
            b.setFocusPolicy(Qt.NoFocus)

        row.addWidget(self.chk_loop)
        row.addWidget(self.btn_loop_a)
        row.addWidget(self.btn_loop_b)
        row.addWidget(self.btn_loop_clear)

        self.lbl_loop = QLabel("Loop: –")
        self.lbl_loop.setMinimumWidth(160)
        row.addWidget(self.lbl_loop)

        self.lbl_scale = QLabel("Skala: –")
        self.lbl_scale.setMinimumWidth(220)
        row.addWidget(self.lbl_scale)

        row.addStretch(1)

        # Tempo
        row.addWidget(QLabel("Tempo"))
        self.tempo = QSpinBox()
        self.tempo.setRange(20, 400)
        try:
            self.tempo.setValue(int(self.scale.tempo.value()))
        except Exception:
            self.tempo.setValue(120)
        self.tempo.setFixedWidth(80)
        row.addWidget(self.tempo)

        # Position display
        self.lbl_pos = QLabel("Beat: 0.00 | 00:00.0")
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_pos.setMinimumWidth(180)
        row.addWidget(self.lbl_pos)

        # Wiring
        self.btn_home.clicked.connect(self._go_home)
        self.btn_back.clicked.connect(self._step_back)
        self.btn_fwd.clicked.connect(self._step_fwd)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)

        self.chk_loop.toggled.connect(self._set_loop_enabled)
        self.btn_loop_a.clicked.connect(self._set_loop_a)
        self.btn_loop_b.clicked.connect(self._set_loop_b)
        self.btn_loop_clear.clicked.connect(self._clear_loop)

        self.tempo.valueChanged.connect(self._tempo_to_slider)
        self.scale.tempo.valueChanged.connect(self._slider_to_tempo)

        self.score.playheadChanged.connect(self._update_pos)

        try:
            self.scale.system_box.currentTextChanged.connect(lambda _=None: self.refresh_scale_label())
            self.scale.scale_box.currentTextChanged.connect(lambda _=None: self.refresh_scale_label())
        except Exception:
            pass

        # Init
        self._update_loop_label()
        self._update_pos(self.score.get_playhead_beat())
        self.refresh_scale_label()

    def refresh_scale_label(self):
        try:
            sys = self.scale.system_box.currentText()
            sc = self.scale.scale_box.currentText()
            if sys and sc:
                self.lbl_scale.setText(f"Skala: {sc} ({sys})")
            elif sc:
                self.lbl_scale.setText(f"Skala: {sc}")
            else:
                self.lbl_scale.setText("Skala: –")
        except Exception:
            self.lbl_scale.setText("Skala: –")

    # ---------- Tempo sync ----------
    def _tempo_to_slider(self, v: int):
        try:
            self.scale.tempo.setValue(int(v))
        except Exception:
            pass

    def _slider_to_tempo(self, v: int):
        try:
            if int(self.tempo.value()) != int(v):
                self.tempo.blockSignals(True)
                self.tempo.setValue(int(v))
                self.tempo.blockSignals(False)
        except Exception:
            pass

    # ---------- Transport ----------
    def _go_home(self):
        self.score.set_playhead_beat(0.0, ensure_visible=True)

    def _step_back(self):
        step = max(0.03125, float(getattr(self.score, "quantize_step", 0.25)))
        self.score.move_playhead(-step)

    def _step_fwd(self):
        step = max(0.03125, float(getattr(self.score, "quantize_step", 0.25)))
        self.score.move_playhead(step)

    def _stop(self):
        try:
            self.scale.stop_all()
        except Exception:
            pass

    def _toggle_play(self):
        # DAW-Style: Play/Stop
        try:
            w = getattr(self.scale, "worker", None)
            if w is not None and getattr(w, "isRunning", lambda: False)():
                self.scale.stop_all()
            else:
                self.scale.play_sequence()
        except Exception:
            pass

    # ---------- Loop ----------
    def _set_loop_enabled(self, enabled: bool):
        try:
            self.scale.loop.setChecked(bool(enabled))
        except Exception:
            pass
        self._update_loop_label()

    def _set_loop_a(self):
        self.score.set_loop_a()
        self._update_loop_label()

    def _set_loop_b(self):
        self.score.set_loop_b()
        self._update_loop_label()

    def _clear_loop(self):
        self.score.loop_a_beat = None
        self.score.loop_b_beat = None
        self._update_loop_label()

    def _update_loop_label(self):
        rng = self.score.get_loop_range()
        if rng is None:
            self.lbl_loop.setText("Loop: –")
        else:
            a, b = rng
            self.lbl_loop.setText(f"Loop: {a:.2f} → {b:.2f}")

    # ---------- Position display ----------
    def _update_pos(self, beat: float):
        try:
            bpm = int(self.tempo.value())
        except Exception:
            bpm = 120
        sec = float(beat) * (60.0 / max(1, bpm))
        m = int(sec // 60)
        s = sec - m * 60
        self.lbl_pos.setText(f"Beat: {float(beat):.2f} | {m:02d}:{s:04.1f}")
