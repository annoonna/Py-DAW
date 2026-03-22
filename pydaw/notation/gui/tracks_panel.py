
# ChronoScaleStudio – Tracks Panel (Spuren: Treble/Bass, Mute/Solo)
from __future__ import annotations

from pydaw.notation.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QToolButton
)
from pydaw.notation.qt_compat import Qt, Signal


class TrackRow(QWidget):
    muteChanged = Signal(int, bool)
    soloChanged = Signal(int, bool)
    clicked = Signal(int)

    def __init__(self, track):
        super().__init__()
        self.track = track

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        self.lbl = QLabel(f"{track.clef_symbol}  {track.name}")
        self.lbl.setMinimumWidth(160)

        self.btn_m = QToolButton()
        self.btn_m.setText("M")
        self.btn_m.setCheckable(True)
        self.btn_m.setChecked(bool(track.mute))
        self.btn_m.setToolTip("Mute")

        self.btn_s = QToolButton()
        self.btn_s.setText("S")
        self.btn_s.setCheckable(True)
        self.btn_s.setChecked(bool(track.solo))
        self.btn_s.setToolTip("Solo")

        lay.addWidget(self.lbl, 1)
        lay.addWidget(self.btn_m, 0)
        lay.addWidget(self.btn_s, 0)

        self.btn_m.toggled.connect(lambda v: self.muteChanged.emit(track.id, bool(v)))
        self.btn_s.toggled.connect(lambda v: self.soloChanged.emit(track.id, bool(v)))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.track.id)
        return super().mousePressEvent(e)

    def refresh(self, track):
        self.track = track
        self.lbl.setText(f"{track.clef_symbol}  {track.name}")
        self.btn_m.blockSignals(True)
        self.btn_s.blockSignals(True)
        self.btn_m.setChecked(bool(track.mute))
        self.btn_s.setChecked(bool(track.solo))
        self.btn_m.blockSignals(False)
        self.btn_s.blockSignals(False)


class TracksPanel(QWidget):
    trackSelected = Signal(int)

    def __init__(self, score_view):
        super().__init__()
        self.score = score_view

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Add buttons
        row = QHBoxLayout()
        self.btn_add_treble = QPushButton("+ 𝄞")
        self.btn_add_bass = QPushButton("+ 𝄢")
        self.btn_add_treble.setToolTip("Neue Spur (Violinschlüssel)")
        self.btn_add_bass.setToolTip("Neue Spur (Bassschlüssel)")
        row.addWidget(self.btn_add_treble)
        row.addWidget(self.btn_add_bass)
        root.addLayout(row)

        # List
        self.list = QListWidget()
        self.list.setSpacing(2)
        root.addWidget(self.list, 1)

        self.btn_add_treble.clicked.connect(lambda: self._add("treble"))
        self.btn_add_bass.clicked.connect(lambda: self._add("bass"))

        self.refresh()

    def _add(self, clef: str):
        tr = self.score.sequence.add_track(clef=clef, name=None)
        self.score.set_active_track(tr.id)
        self.refresh()
        self.score.redraw_events()
        self.trackSelected.emit(tr.id)

    def refresh(self):
        self.list.clear()
        for tr in self.score.sequence.tracks:
            item = QListWidgetItem()
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            w = TrackRow(tr)
            w.muteChanged.connect(self._on_mute)
            w.soloChanged.connect(self._on_solo)
            w.clicked.connect(self._on_clicked)

            item.setSizeHint(w.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, w)

    def _on_mute(self, track_id: int, mute: bool):
        self.score.sequence.set_track_mute(track_id, mute)
        self.score.redraw_events()

    def _on_solo(self, track_id: int, solo: bool):
        self.score.sequence.set_track_solo(track_id, solo)
        self.score.redraw_events()

    def _on_clicked(self, track_id: int):
        self.score.set_active_track(track_id)
        self.trackSelected.emit(track_id)

