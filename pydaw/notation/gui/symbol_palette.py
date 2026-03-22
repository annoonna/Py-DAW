"""ChronoScaleStudio – Symbol Palette (ohne PNG-Assets)

Diese Palette ist bewusst **ohne** externe Bilddateien gebaut.
Die Symbole werden mit QPainter gezeichnet, damit das Projekt
"eine Wahrheit" bleibt und später sehr leicht erweiterbar ist.

Die Palette steuert primär den Editor (ScoreView):
 - Werkzeug: Note / Pause / Select / Tie / Erase
 - Länge: ganze/halbe/...
 - Punktierung: 0/1/2
 - Vorzeichen-Offset (für Neueingaben): none / ♮ / ♯ / ♭
 - Edit-Aktionen: Split / Glue / Quantize / Humanize / Transpose
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydaw.notation.qt_compat import Qt, QSize, Signal
from pydaw.notation.qt_compat import QPainter, QPen, QBrush, QPixmap, QAction
from pydaw.notation.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QToolButton, QButtonGroup, QGroupBox, QWidgetAction
)


def _icon_from_paint(size: int, paint_fn) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    paint_fn(p, size)
    p.end()
    return pm


def _paint_note(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(QBrush(Qt.white))
    # head
    p.drawEllipse(int(size*0.25), int(size*0.45), int(size*0.28), int(size*0.20))
    # stem
    p.drawLine(int(size*0.53), int(size*0.48), int(size*0.53), int(size*0.15))


def _paint_rest(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    # simple "zig" rest
    p.drawLine(int(size*0.30), int(size*0.25), int(size*0.55), int(size*0.35))
    p.drawLine(int(size*0.55), int(size*0.35), int(size*0.35), int(size*0.55))
    p.drawLine(int(size*0.35), int(size*0.55), int(size*0.60), int(size*0.70))


def _paint_move(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    c = size / 2.0
    m = 3
    p.drawLine(m, c, size - m, c)
    p.drawLine(c, m, c, size - m)
    # arrow tips
    p.drawLine(m, c, m + 4, c - 3)
    p.drawLine(m, c, m + 4, c + 3)
    p.drawLine(size - m, c, size - m - 4, c - 3)
    p.drawLine(size - m, c, size - m - 4, c + 3)
    p.drawLine(c, m, c - 3, m + 4)
    p.drawLine(c, m, c + 3, m + 4)
    p.drawLine(c, size - m, c - 3, size - m - 4)
    p.drawLine(c, size - m, c + 3, size - m - 4)


def _paint_tie(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(int(size*0.18), int(size*0.45), int(size*0.64), int(size*0.30), 0, 180*16)


def _paint_erase(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(int(size*0.22), int(size*0.35), int(size*0.56), int(size*0.30))
    p.drawLine(int(size*0.28), int(size*0.32), int(size*0.40), int(size*0.22))
    p.drawLine(int(size*0.78), int(size*0.32), int(size*0.66), int(size*0.22))


def _paint_sharp(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    x1 = int(size*0.38)
    x2 = int(size*0.62)
    p.drawLine(x1, int(size*0.20), x1, int(size*0.80))
    p.drawLine(x2, int(size*0.20), x2, int(size*0.80))
    p.drawLine(int(size*0.28), int(size*0.40), int(size*0.72), int(size*0.35))
    p.drawLine(int(size*0.28), int(size*0.62), int(size*0.72), int(size*0.57))


def _paint_flat(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    x = int(size*0.45)
    p.drawLine(x, int(size*0.20), x, int(size*0.80))
    p.drawArc(int(size*0.40), int(size*0.40), int(size*0.35), int(size*0.30), 90*16, -180*16)


def _paint_natural(p: QPainter, size: int):
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    p.drawLine(int(size*0.42), int(size*0.20), int(size*0.42), int(size*0.80))
    p.drawLine(int(size*0.58), int(size*0.20), int(size*0.58), int(size*0.80))
    p.drawLine(int(size*0.42), int(size*0.35), int(size*0.58), int(size*0.30))
    p.drawLine(int(size*0.42), int(size*0.65), int(size*0.58), int(size*0.60))


def _paint_dot(p: QPainter, size: int):
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(Qt.white))
    p.drawEllipse(int(size*0.44), int(size*0.44), int(size*0.12), int(size*0.12))


@dataclass
class PaletteState:
    tool_mode: str = "note"      # note|rest|select|tie|erase
    dots: int = 0                # 0..2
    accidental: int = 0          # -1 flat, 0 none, +1 sharp, 2 natural (special)


class SymbolPaletteWidget(QWidget):
    """Großer Notenblock (Palette) – kann als Dock oder im Kontextmenü laufen."""

    toolModeRequested = Signal(str)
    durationRequested = Signal(float)
    dotsRequested = Signal(int)
    accidentalRequested = Signal(int)

    splitRequested = Signal()
    glueRequested = Signal()
    quantizeRequested = Signal(bool)   # affect_duration
    humanizeRequested = Signal()
    transposeRequested = Signal(int)   # semitones

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self.compact = bool(compact)
        self.state = PaletteState()
        self._build_ui()

    def _btn(self, text: str, pm: Optional[QPixmap] = None, tip: str = "") -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if not self.compact else Qt.ToolButtonIconOnly)
        if pm is not None:
            b.setIcon(pm)
            b.setIconSize(QSize(18, 18))
        if tip:
            b.setToolTip(tip)
        b.setAutoRaise(True)
        b.setCheckable(True)
        return b

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Tools
        gb_tools = QGroupBox("Werkzeug" if not self.compact else "")
        l_tools = QGridLayout(gb_tools)
        l_tools.setContentsMargins(6, 6, 6, 6)

        size = 18
        icons = {
            "note": _icon_from_paint(size, _paint_note),
            "rest": _icon_from_paint(size, _paint_rest),
            "select": _icon_from_paint(size, _paint_move),
            "tie": _icon_from_paint(size, _paint_tie),
            "erase": _icon_from_paint(size, _paint_erase),
        }

        self.bg_tools = QButtonGroup(self)
        self.bg_tools.setExclusive(True)
        self.btn_note = self._btn("Note", icons["note"], "Noten setzen")
        self.btn_rest = self._btn("Pause", icons["rest"], "Pausen setzen")
        self.btn_sel = self._btn("Move", icons["select"], "Select/Move/Resize")
        self.btn_tie = self._btn("Tie", icons["tie"], "Haltebogen togglen")
        self.btn_erase = self._btn("Erase", icons["erase"], "Löschen")

        for i, b in enumerate([self.btn_note, self.btn_rest, self.btn_sel, self.btn_tie, self.btn_erase]):
            self.bg_tools.addButton(b, i)
        self.btn_note.setChecked(True)

        l_tools.addWidget(self.btn_note, 0, 0)
        l_tools.addWidget(self.btn_rest, 0, 1)
        l_tools.addWidget(self.btn_sel, 1, 0)
        l_tools.addWidget(self.btn_tie, 1, 1)
        l_tools.addWidget(self.btn_erase, 2, 0, 1, 2)

        self.btn_note.clicked.connect(lambda: self.toolModeRequested.emit("note"))
        self.btn_rest.clicked.connect(lambda: self.toolModeRequested.emit("rest"))
        self.btn_sel.clicked.connect(lambda: self.toolModeRequested.emit("select"))
        self.btn_tie.clicked.connect(lambda: self.toolModeRequested.emit("tie"))
        self.btn_erase.clicked.connect(lambda: self.toolModeRequested.emit("erase"))

        # Length
        gb_len = QGroupBox("Notenlänge")
        l_len = QGridLayout(gb_len)
        l_len.setContentsMargins(6, 6, 6, 6)
        self.bg_len = QButtonGroup(self)
        self.bg_len.setExclusive(True)

        lengths = [
            ("1", 1.0), ("1/2", 0.5), ("1/4", 0.25), ("1/8", 0.125),
            ("2", 2.0), ("4", 4.0)
        ]
        self.len_buttons = []
        for idx, (lbl, beats) in enumerate(lengths):
            b = QToolButton()
            b.setText(lbl)
            b.setCheckable(True)
            b.setAutoRaise(True)
            self.bg_len.addButton(b, idx)
            self.len_buttons.append((b, beats))
            r = idx // 3
            c = idx % 3
            l_len.addWidget(b, r, c)
            b.clicked.connect(lambda _=False, v=beats: self.durationRequested.emit(float(v)))
        # default Viertel
        for b, beats in self.len_buttons:
            if abs(beats - 1.0) < 1e-9:
                b.setChecked(True)
                break

        # Dots + Accidentals
        gb_mod = QGroupBox("Mod" if self.compact else "Punktierung / Vorzeichen")
        l_mod = QGridLayout(gb_mod)
        l_mod.setContentsMargins(6, 6, 6, 6)

        # dots
        self.bg_dots = QButtonGroup(self)
        self.bg_dots.setExclusive(True)
        dot_icon = _icon_from_paint(size, _paint_dot)
        self.btn_dot0 = self._btn("0", None, "Keine Punktierung")
        self.btn_dot1 = self._btn("·", dot_icon, "Punktiert")
        self.btn_dot2 = self._btn("··", dot_icon, "Doppelt punktiert")
        for i, b in enumerate([self.btn_dot0, self.btn_dot1, self.btn_dot2]):
            self.bg_dots.addButton(b, i)
        self.btn_dot0.setChecked(True)
        self.btn_dot0.clicked.connect(lambda: self.dotsRequested.emit(0))
        self.btn_dot1.clicked.connect(lambda: self.dotsRequested.emit(1))
        self.btn_dot2.clicked.connect(lambda: self.dotsRequested.emit(2))

        # accidentals
        self.bg_acc = QButtonGroup(self)
        self.bg_acc.setExclusive(True)
        self.btn_acc_none = self._btn("∅", None, "Kein Vorzeichen")
        self.btn_acc_nat = self._btn("♮", _icon_from_paint(size, _paint_natural), "Natural")
        self.btn_acc_sh = self._btn("♯", _icon_from_paint(size, _paint_sharp), "Sharp")
        self.btn_acc_fl = self._btn("♭", _icon_from_paint(size, _paint_flat), "Flat")
        for i, b in enumerate([self.btn_acc_none, self.btn_acc_nat, self.btn_acc_sh, self.btn_acc_fl]):
            self.bg_acc.addButton(b, i)
        self.btn_acc_none.setChecked(True)

        self.btn_acc_none.clicked.connect(lambda: self.accidentalRequested.emit(0))
        self.btn_acc_nat.clicked.connect(lambda: self.accidentalRequested.emit(2))
        self.btn_acc_sh.clicked.connect(lambda: self.accidentalRequested.emit(1))
        self.btn_acc_fl.clicked.connect(lambda: self.accidentalRequested.emit(-1))

        l_mod.addWidget(QLabel("Dots"), 0, 0)
        l_mod.addWidget(self.btn_dot0, 0, 1)
        l_mod.addWidget(self.btn_dot1, 0, 2)
        l_mod.addWidget(self.btn_dot2, 0, 3)

        l_mod.addWidget(QLabel("Acc"), 1, 0)
        l_mod.addWidget(self.btn_acc_none, 1, 1)
        l_mod.addWidget(self.btn_acc_nat, 1, 2)
        l_mod.addWidget(self.btn_acc_sh, 1, 3)
        l_mod.addWidget(self.btn_acc_fl, 1, 4)

        # Edit tools
        gb_edit = QGroupBox("Edit-Tools")
        l_edit = QGridLayout(gb_edit)
        l_edit.setContentsMargins(6, 6, 6, 6)

        def abtn(txt, tip):
            b = QToolButton(); b.setText(txt); b.setAutoRaise(True); b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setToolTip(tip)
            return b

        b_split = abtn("Split", "Split am Playhead")
        b_glue = abtn("Glue", "Selektierte Events zusammenfügen")
        b_qs = abtn("Quantize", "Quantize Start")
        b_qd = abtn("Quantize+Len", "Quantize Start + Länge")
        b_hum = abtn("Humanize", "Humanize Timing/Velocity")
        b_tn = abtn("-1", "Transpose -1")
        b_tp = abtn("+1", "Transpose +1")
        b_to = abtn("+12", "Transpose +12")
        b_tm = abtn("-12", "Transpose -12")

        l_edit.addWidget(b_split, 0, 0)
        l_edit.addWidget(b_glue, 0, 1)
        l_edit.addWidget(b_qs, 1, 0)
        l_edit.addWidget(b_qd, 1, 1)
        l_edit.addWidget(b_hum, 2, 0, 1, 2)
        l_edit.addWidget(b_tm, 3, 0)
        l_edit.addWidget(b_tn, 3, 1)
        l_edit.addWidget(b_tp, 4, 0)
        l_edit.addWidget(b_to, 4, 1)

        b_split.clicked.connect(self.splitRequested.emit)
        b_glue.clicked.connect(self.glueRequested.emit)
        b_qs.clicked.connect(lambda: self.quantizeRequested.emit(False))
        b_qd.clicked.connect(lambda: self.quantizeRequested.emit(True))
        b_hum.clicked.connect(self.humanizeRequested.emit)
        b_tn.clicked.connect(lambda: self.transposeRequested.emit(-1))
        b_tp.clicked.connect(lambda: self.transposeRequested.emit(+1))
        b_tm.clicked.connect(lambda: self.transposeRequested.emit(-12))
        b_to.clicked.connect(lambda: self.transposeRequested.emit(+12))

        root.addWidget(gb_tools)
        root.addWidget(gb_len)
        root.addWidget(gb_mod)
        root.addWidget(gb_edit)
        root.addStretch(1)


def add_symbol_palette_to_menu(menu, view, *, compact: bool = True) -> QAction:
    """Hilfsfunktion: Palette als WidgetAction in ein Menü einhängen."""
    w = SymbolPaletteWidget(compact=compact)
    # wiring
    w.toolModeRequested.connect(view.set_mode)
    w.durationRequested.connect(view.set_duration)
    w.dotsRequested.connect(view.set_dots)
    w.accidentalRequested.connect(view.set_accidental)
    # ScoreView nutzt die *selected*-Methoden – wir verdrahten darauf.
    if hasattr(view, "split_selected_at_playhead"):
        w.splitRequested.connect(view.split_selected_at_playhead)
    if hasattr(view, "glue_selected"):
        w.glueRequested.connect(view.glue_selected)
    if hasattr(view, "quantize_selected"):
        w.quantizeRequested.connect(view.quantize_selected)
    if hasattr(view, "humanize_selected"):
        w.humanizeRequested.connect(view.humanize_selected)
    if hasattr(view, "transpose_selected"):
        w.transposeRequested.connect(view.transpose_selected)

    act = QWidgetAction(menu)
    act.setDefaultWidget(w)
    menu.addAction(act)
    return act
