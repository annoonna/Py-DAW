"""NotationPalette - professionelle notation input bar (MVP).

Goal
----
Provide a **safe, optional** UI module for classical composition workflows:
- Select note value (1/1 .. 1/64)
- Dotted option
- Rests toggle
- Accidentals (sharp/flat/natural)
- Ornaments (trill - MVP as marker)
- "Editor Notes" (sticky notes) anchored to a beat position

This module is designed to be **non-breaking**:
- It does not change existing rendering unless the host view connects it.
- It exposes a small dataclass state and signals.

Used by:
- :class:`pydaw.ui.notation.notation_view.NotationWidget`

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QToolButton,
    QLabel,
    QButtonGroup,
    QMenu,
)

from pydaw.ui.scale_menu_button import ScaleMenuButton


# Mapping: note fraction -> beats (timeline assumes quarter note == 1 beat)
_NOTE_TO_BEATS = {
    "1/1": 4.0,
    "1/2": 2.0,
    "1/4": 1.0,
    "1/8": 0.5,
    "1/16": 0.25,
    "1/32": 0.125,
    "1/64": 0.0625,
}


# Optional symbol hints (fonts may not support them; used only in tooltips).
_SYMBOL_HINTS = {
    "1/1": "𝅝",
    "1/2": "𝅗𝅥",
    "1/4": "♩",
    "1/8": "♪",
    "1/16": "𝅘𝅥𝅯",
    "1/32": "𝅘𝅥𝅰",
    "1/64": "𝅘𝅥𝅱",
}


@dataclass
class NotationInputState:
    """Current input state selected by the user."""
    note_value: str = "1/16"
    dotted: bool = False
    is_rest: bool = False
    accidental: int = 0  # -1 flat, 0 none/natural, +1 sharp
    ornament: str = ""   # "trill" (MVP) or ""

    def duration_beats(self) -> float:
        base = float(_NOTE_TO_BEATS.get(self.note_value, 0.25))
        return base * (1.5 if self.dotted else 1.0)


class NotationPalette(QWidget):
    """A compact notation input palette (toolbar-like)."""

    state_changed = pyqtSignal(object)  # NotationInputState

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._state = NotationInputState()

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)

        lbl = QLabel("Notation:")
        lbl.setStyleSheet("opacity: 0.8;")
        row.addWidget(lbl)

        # Note value buttons
        self._grp = QButtonGroup(self)
        self._btn_by_frac = {}

        self._grp.setExclusive(True)

        _fractions = ["1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]
        for i, frac in enumerate(_fractions, start=1):
            b = QToolButton()
            b.setText(frac)
            b.setCheckable(True)
            sym = _SYMBOL_HINTS.get(frac, "")
            hint = f" {sym}" if sym else ""
            b.setToolTip(f"Notenwert {frac}{hint} (Shortcut: Alt+{i})")
            if frac == self._state.note_value:
                b.setChecked(True)
            self._grp.addButton(b)
            self._btn_by_frac[frac] = b
            row.addWidget(b)

        self._grp.buttonClicked.connect(self._on_note_value_clicked)

        # Dotted
        self._btn_dot = QToolButton()
        self._btn_dot.setText("·")  # dot
        self._btn_dot.setCheckable(True)
        self._btn_dot.setToolTip("Punktiert (×1.5)")
        self._btn_dot.clicked.connect(self._on_dot_toggled)
        row.addWidget(self._btn_dot)

        # Rest
        self._btn_rest = QToolButton()
        self._btn_rest.setText("Rest")
        self._btn_rest.setCheckable(True)
        self._btn_rest.setToolTip("Pause setzen (als Notations-Markierung, MVP)")
        self._btn_rest.clicked.connect(self._on_rest_toggled)
        row.addWidget(self._btn_rest)

        row.addSpacing(8)

        # Accidentals: ♭ ♮ ♯ — toggle behavior (click again = reset to natural)
        self._btn_flat = QToolButton()
        self._btn_flat.setText("b")
        self._btn_flat.setCheckable(True)
        self._btn_flat.setToolTip("Vorzeichen: Be (♭)\nOder: Alt+Klick im Notensystem")
        self._btn_flat.clicked.connect(lambda: self._toggle_accidental(-1))
        row.addWidget(self._btn_flat)

        self._btn_nat = QToolButton()
        self._btn_nat.setText("♮")
        self._btn_nat.setCheckable(True)
        self._btn_nat.setToolTip("Vorzeichen: Auflöser (♮)\nSetzt Vorzeichen auf Natürlich zurück")
        self._btn_nat.clicked.connect(lambda: self._set_accidental(0))
        row.addWidget(self._btn_nat)

        self._btn_sharp = QToolButton()
        self._btn_sharp.setText("#")
        self._btn_sharp.setCheckable(True)
        self._btn_sharp.setToolTip("Vorzeichen: Kreuz (♯)\nOder: Shift+Klick im Notensystem")
        self._btn_sharp.clicked.connect(lambda: self._toggle_accidental(+1))
        row.addWidget(self._btn_sharp)

        # keep accidental toggles in sync
        self._sync_accidental_buttons()

        row.addSpacing(8)

        # Ornaments menu (MVP)
        self._btn_orn = QToolButton()
        self._btn_orn.setText("Orn")
        self._btn_orn.setToolTip("Barocke Ornamente (MVP)")
        self._btn_orn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self._btn_orn)
        act_none = m.addAction("Kein Ornament")
        act_trill = m.addAction("Triller (tr)")
        act_none.triggered.connect(lambda: self._set_ornament(""))
        act_trill.triggered.connect(lambda: self._set_ornament("trill"))
        self._btn_orn.setMenu(m)
        row.addWidget(self._btn_orn)

        # Scale Lock (shared with Piano Roll)
        row.addSpacing(10)
        self._scale_btn = ScaleMenuButton(self)
        self._scale_btn.setToolTip(
            "Scale Lock: Noten werden auf Skala beschränkt.\n"
            "Modus: Snap (anpass...), Reject (verwerfen)."
        )
        row.addWidget(self._scale_btn)

        row.addStretch(1)

        # Editor note quick button (the view decides where to anchor; typically click-position)
        self._btn_note = QToolButton()
        self._btn_note.setText("🗒")
        self._btn_note.setToolTip("Editor-Notiz hinzufügen (Ctrl+Rechtsklick im Notationsfeld ist auch möglich)")
        self._btn_note.setEnabled(False)  # enabled when view supports it
        row.addWidget(self._btn_note)

        # Keyboard shortcuts (professionelle quick entry)
        self._setup_shortcuts()


    def enable_editor_notes_button(self, enabled: bool) -> None:
        self._btn_note.setEnabled(bool(enabled))

    def editor_notes_button(self) -> QToolButton:
        return self._btn_note

    def state(self) -> NotationInputState:
        return self._state

    # ---------------- internals ----------------

    def _emit(self) -> None:
        try:
            self.state_changed.emit(self._state)
        except Exception:
            pass

    def _on_note_value_clicked(self, btn: QToolButton) -> None:
        try:
            val = str(btn.text()).strip()
        except Exception:
            val = "1/16"
        if val in _NOTE_TO_BEATS:
            self._state.note_value = val
        self._emit()

    def _on_dot_toggled(self) -> None:
        self._state.dotted = bool(self._btn_dot.isChecked())
        self._emit()

    def _on_rest_toggled(self) -> None:
        self._state.is_rest = bool(self._btn_rest.isChecked())
        self._emit()

    def _set_accidental(self, acc: int) -> None:
        self._state.accidental = int(acc)
        self._sync_accidental_buttons()
        self._emit()

    def _toggle_accidental(self, acc: int) -> None:
        """Toggle accidental: if same value is already set, reset to 0 (natural)."""
        if self._state.accidental == int(acc):
            self._state.accidental = 0
        else:
            self._state.accidental = int(acc)
        self._sync_accidental_buttons()
        self._emit()

    def _sync_accidental_buttons(self) -> None:
        # Only one active at a time, but keep natural as "0" indicator
        a = int(self._state.accidental)
        self._btn_flat.setChecked(a == -1)
        self._btn_sharp.setChecked(a == +1)
        self._btn_nat.setChecked(a == 0)

    def _set_ornament(self, o: str) -> None:
        self._state.ornament = str(o or "")
        self._emit()

    def _setup_shortcuts(self) -> None:
        # Note values: Alt+1..Alt+7
        mapping = [
            ("Alt+1", "1/1"),
            ("Alt+2", "1/2"),
            ("Alt+3", "1/4"),
            ("Alt+4", "1/8"),
            ("Alt+5", "1/16"),
            ("Alt+6", "1/32"),
            ("Alt+7", "1/64"),
        ]
        for seq, frac in mapping:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(lambda f=frac: self._set_note_value(f))
            # Metadata for Hilfe → Arbeitsmappe (Shortcuts-Liste)
            try:
                sc.setObjectName(f"shortcut_notation_note_value_{frac.replace('/', '_')}")
                sc.setProperty("pydaw_desc", f"Notation: Notenwert setzen ({frac})")
            except Exception:
                pass

        sc_dot = QShortcut(QKeySequence("Alt+."), self)
        sc_dot.activated.connect(lambda: self._btn_dot.toggle())
        try:
            sc_dot.setObjectName("shortcut_notation_dotted")
            sc_dot.setProperty("pydaw_desc", "Notation: Punktierung an/aus")
        except Exception:
            pass

        sc_rest = QShortcut(QKeySequence("Alt+R"), self)
        sc_rest.activated.connect(lambda: self._btn_rest.toggle())
        try:
            sc_rest.setObjectName("shortcut_notation_rest")
            sc_rest.setProperty("pydaw_desc", "Notation: Pause-Modus an/aus")
        except Exception:
            pass

    def _set_note_value(self, frac: str) -> None:
        b = self._btn_by_frac.get(str(frac))
        if b is None:
            return
        try:
            b.setChecked(True)
        except Exception:
            pass
        self._state.note_value = str(frac)
        self._emit()
