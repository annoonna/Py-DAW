# ChronoScaleStudio – Notations-Toolbox (Dock)
# Separate Werkzeugpalette: Notenlänge, Pausen, Haltebögen, Quantisierung, Velocity, Master-Volume.

from __future__ import annotations

from pydaw.notation.qt_compat import (
    QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QGridLayout, QRadioButton, QButtonGroup,
    QLabel, QComboBox, QCheckBox, QDial, QPushButton, QSpinBox, QToolButton
)
from pydaw.notation.qt_compat import Qt, QSize
from pydaw.notation.qt_compat import QIcon, QPixmap, QPainter, QPen


class NotationToolbox(QWidget):
    def _make_move_icon(self) -> QIcon:
        """Kleines 4-Wege-Verschiebe-Icon (ohne externe Assets)."""
        size = 18
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.palette().text().color())
        pen.setWidth(2)
        p.setPen(pen)

        c = size / 2.0
        m = 3
        # Kreuz
        p.drawLine(m, c, size - m, c)
        p.drawLine(c, m, c, size - m)

        # Pfeilspitzen
        # links
        p.drawLine(m, c, m + 4, c - 3)
        p.drawLine(m, c, m + 4, c + 3)
        # rechts
        p.drawLine(size - m, c, size - m - 4, c - 3)
        p.drawLine(size - m, c, size - m - 4, c + 3)
        # oben
        p.drawLine(c, m, c - 3, m + 4)
        p.drawLine(c, m, c + 3, m + 4)
        # unten
        p.drawLine(c, size - m, c - 3, size - m - 4)
        p.drawLine(c, size - m, c + 3, size - m - 4)

        p.end()
        return QIcon(pm)

    def __init__(self, score_view, open_automation_editor_cb=None):
        super().__init__()
        self.score = score_view
        self.open_automation_editor_cb = open_automation_editor_cb

        root = QVBoxLayout(self)

        # -------- Werkzeugmodus --------
        tool_box = QGroupBox("Werkzeug")
        tool_layout = QVBoxLayout(tool_box)

        # Schnellzugriff: Verschieben-Icon (zentral fürs Bearbeiten)
        icon_row = QHBoxLayout()
        self.btn_move = QToolButton()
        self.btn_move.setIcon(self._make_move_icon())
        self.btn_move.setIconSize(QSize(18, 18))
        self.btn_move.setText("Verschieben")
        self.btn_move.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_move.setCheckable(True)
        self.btn_move.clicked.connect(lambda: self._set_tool_mode("select"))
        icon_row.addWidget(self.btn_move)
        icon_row.addStretch(1)
        tool_layout.addLayout(icon_row)

        self.tool_group = QButtonGroup(self)
        self.rb_note = QRadioButton("Note zeichnen")
        self.rb_rest = QRadioButton("Pause zeichnen")
        self.rb_select = QRadioButton("Verschieben")
        self.rb_tie = QRadioButton("Haltebogen (Toggle)")
        self.rb_erase = QRadioButton("Radierer (löschen)")

        for i, rb in enumerate([self.rb_note, self.rb_rest, self.rb_select, self.rb_tie, self.rb_erase]):
            self.tool_group.addButton(rb, i)
            tool_layout.addWidget(rb)

        self.rb_note.setChecked(True)
        self.tool_group.idClicked.connect(self._on_tool_changed)

        # -------- Notenlänge --------
        len_box = QGroupBox("Notenlänge (Beats)")
        len_layout = QVBoxLayout(len_box)
        self.len_group = QButtonGroup(self)

        self.lengths = [
            ("Ganze", 4.0),
            ("Halbe", 2.0),
            ("Viertel", 1.0),
            ("Achtel", 0.5),
            ("16tel", 0.25),
            ("32tel", 0.125),
        ]

        for idx, (name, beats) in enumerate(self.lengths):
            rb = QRadioButton(f"{name} ({beats:g})")
            self.len_group.addButton(rb, idx)
            len_layout.addWidget(rb)
            if beats == 1.0:
                rb.setChecked(True)

        self.len_group.idClicked.connect(self._on_length_changed)

        # -------- Quantisierung --------
        q_box = QGroupBox("Quantisierung")
        q_layout = QVBoxLayout(q_box)

        self.snap_cb = QCheckBox("Snap/Grid aktiv")
        self.snap_cb.setChecked(True)
        self.snap_cb.toggled.connect(lambda v: self.score.set_snap(v))
        q_layout.addWidget(self.snap_cb)

        self.quant = QComboBox()
        self.quant_steps = [
            ("Beat/1 (Viertel)", 1.0),
            ("Beat/2 (Achtel)", 0.5),
            ("Beat/4 (16tel)", 0.25),
            ("Beat/8 (32tel)", 0.125),
            ("Beat/16 (64tel)", 0.0625),
        ]
        for label, val in self.quant_steps:
            self.quant.addItem(label, val)
        self.quant.setCurrentIndex(2)  # Beat/4 (16tel)
        self.quant.currentIndexChanged.connect(self._on_quant_changed)
        q_layout.addWidget(QLabel("Step"))
        q_layout.addWidget(self.quant)

        
        # -------- Bearbeiten (Nudges) --------
        edit_box = QGroupBox("Bearbeiten (Nudge)")
        e_layout = QGridLayout(edit_box)

        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")
        btn_left = QPushButton("←")
        btn_right = QPushButton("→")

        btn_up.setToolTip("Ausgewählte Note: Pitch +1")
        btn_down.setToolTip("Ausgewählte Note: Pitch -1")
        btn_left.setToolTip("Ausgewähltes Event: Start -Step (Quant)")
        btn_right.setToolTip("Ausgewähltes Event: Start +Step (Quant)")

        # Layout wie ein D-Pad
        e_layout.addWidget(btn_up, 0, 1)
        e_layout.addWidget(btn_left, 1, 0)
        e_layout.addWidget(btn_right, 1, 2)
        e_layout.addWidget(btn_down, 2, 1)

        btn_left.clicked.connect(self.score.nudge_left)
        btn_right.clicked.connect(self.score.nudge_right)
        btn_up.clicked.connect(self.score.nudge_up)
        btn_down.clicked.connect(self.score.nudge_down)

        # Hinweis auf Rechtsklick-Menü
        hint = QLabel("Tipp: Rechtsklick in der Notenansicht öffnet das Toolbox-Menü.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        e_layout.addWidget(hint, 3, 0, 1, 3)

        # -------- Drehregler --------
        dial_box = QGroupBox("Drehregler")
        dial_layout = QVBoxLayout(dial_box)

        # Velocity
        vel_row = QHBoxLayout()
        vel_row.addWidget(QLabel("Velocity"))
        self.vel_dial = QDial()
        self.vel_dial.setNotchesVisible(True)
        self.vel_dial.setRange(1, 127)
        self.vel_dial.setValue(90)
        self.vel_dial.valueChanged.connect(lambda v: self.score.set_velocity(v))
        vel_row.addWidget(self.vel_dial)
        dial_layout.addLayout(vel_row)

        # Master Volume
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Master"))
        self.vol_dial = QDial()
        self.vol_dial.setNotchesVisible(True)
        self.vol_dial.setRange(0, 127)
        self.vol_dial.setValue(self.score.get_master_volume())
        self.vol_dial.valueChanged.connect(lambda v: self.score.set_master_volume(v))
        vol_row.addWidget(self.vol_dial)
        dial_layout.addLayout(vol_row)

        
        # -------- Zoom --------
        zoom_box = QGroupBox("Ansicht (Zoom)")
        z_layout = QHBoxLayout(zoom_box)

        self.zoom_out_btn = QPushButton("−")
        self.zoom_in_btn = QPushButton("+")
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_label = QLabel(f"{int(self.score.get_zoom()*100)}%")

        self.zoom_out_btn.setToolTip("Zoom verkleinern (Mausrad runter)")
        self.zoom_in_btn.setToolTip("Zoom vergrößern (Mausrad hoch)")
        self.zoom_reset_btn.setToolTip("Zoom zurücksetzen")

        self.zoom_out_btn.clicked.connect(self.score.zoom_out)
        self.zoom_in_btn.clicked.connect(self.score.zoom_in)
        self.zoom_reset_btn.clicked.connect(self.score.zoom_reset)

        z_layout.addWidget(self.zoom_out_btn)
        z_layout.addWidget(self.zoom_in_btn)
        z_layout.addWidget(self.zoom_reset_btn)
        z_layout.addStretch(1)
        z_layout.addWidget(QLabel("Aktuell:"))
        z_layout.addWidget(self.zoom_label)

        # Live-Update, auch bei Mausrad-Zoom
        try:
            self.score.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{int(z*100)}%"))
        except Exception:
            pass

        # -------- Länge der Timeline --------
        tl_box = QGroupBox("Timeline")
        tl_layout = QHBoxLayout(tl_box)
        tl_layout.addWidget(QLabel("Beats anzeigen"))
        self.beats_spin = QSpinBox()
        self.beats_spin.setRange(4, 128)
        self.beats_spin.setValue(16)
        self.beats_spin.valueChanged.connect(lambda v: self.score.set_total_beats(v))
        tl_layout.addWidget(self.beats_spin)

        # -------- Aktionen --------
        actions = QGroupBox("Aktionen")
        a_layout = QVBoxLayout(actions)
        btn_clear = QPushButton("Alles löschen")
        btn_clear.clicked.connect(self.score.clear_all)
        a_layout.addWidget(btn_clear)

        btn_auto = QPushButton("Automationen… (Volume)")
        btn_auto.clicked.connect(self._open_automation_editor)
        a_layout.addWidget(btn_auto)

        root.addWidget(tool_box)
        root.addWidget(len_box)
        root.addWidget(q_box)
        root.addWidget(edit_box)
        root.addWidget(dial_box)
        root.addWidget(zoom_box)
        root.addWidget(tl_box)
        root.addWidget(actions)
        root.addStretch(1)

        # Init ScoreView from UI
        self._apply_initial_state()

    def _apply_initial_state(self):
        self.score.set_mode("note")
        try:
            self.btn_move.setChecked(False)
        except Exception:
            pass
        self.score.set_duration(1.0)
        self.score.set_quantize_step(0.25)
        self.score.set_snap(True)
        self.score.set_velocity(self.vel_dial.value())
        self.score.set_master_volume(self.vol_dial.value())

    def _set_tool_mode(self, mode: str):
        """Setzt den Werkzeugmodus zentral und hält UI-Elemente synchron."""
        self.score.set_mode(mode)

        # RadioButtons spiegeln den Modus
        m = {
            "note": self.rb_note,
            "rest": self.rb_rest,
            "select": self.rb_select,
            "tie": self.rb_tie,
            "erase": self.rb_erase,
        }
        rb = m.get(mode)
        if rb is not None:
            rb.setChecked(True)

        # Icon-Button-Status
        try:
            self.btn_move.setChecked(mode == "select")
        except Exception:
            pass

    def _on_tool_changed(self, tool_id: int):
        modes = {
            0: "note",
            1: "rest",
            2: "select",
            3: "tie",
            4: "erase",
        }
        mode = modes.get(tool_id, "note")
        self.score.set_mode(mode)
        try:
            self.btn_move.setChecked(mode == "select")
        except Exception:
            pass

    def _on_length_changed(self, idx: int):
        beats = float(self.lengths[idx][1])
        self.score.set_duration(beats)

    def _on_quant_changed(self, idx: int):
        step = float(self.quant.currentData())
        self.score.set_quantize_step(step)

    def _open_automation_editor(self):
        if callable(self.open_automation_editor_cb):
            self.open_automation_editor_cb()
