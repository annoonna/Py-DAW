# -*- coding: utf-8 -*-
"""TouchKeyboardWidget (v0.0.20.609)

Bitwig-Style On-Screen Touch Keyboard.
A clickable piano keyboard that injects MIDI notes via MidiManager.inject_message()
with source='touch_keyboard'.

Can be toggled via menu or docked in the bottom panel.
"""

from __future__ import annotations

from typing import Optional, Set

from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpinBox, QToolButton


# Piano key layout constants
_WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]  # semitones for C D E F G A B
_BLACK_KEYS = [1, 3, 6, 8, 10]         # C# D# F# G# A#
_BLACK_POSITIONS = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}  # semitone → white-key-gap index


class TouchKeyboardWidget(QWidget):
    """On-screen piano keyboard — click/touch to play notes."""

    # Emitted for external consumers (status bar etc.)
    note_played = pyqtSignal(int, int)  # pitch, velocity

    def __init__(self, midi_manager=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._midi_manager = midi_manager
        self._base_octave: int = 3
        self._num_octaves: int = 3
        self._velocity: int = 100
        self._held_notes: Set[int] = set()
        self._hover_note: int = -1

        self.setMinimumHeight(60)
        self.setMaximumHeight(100)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Build toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 0)
        toolbar.setSpacing(4)

        lbl = QLabel("🎹")
        lbl.setStyleSheet("font-size: 14px;")
        toolbar.addWidget(lbl)

        lbl_oct = QLabel("Oct:")
        lbl_oct.setStyleSheet("font-size: 10px; color: #aaa;")
        toolbar.addWidget(lbl_oct)

        self._spn_oct = QSpinBox()
        self._spn_oct.setRange(0, 7)
        self._spn_oct.setValue(self._base_octave)
        self._spn_oct.setFixedWidth(46)
        self._spn_oct.setFixedHeight(20)
        self._spn_oct.setStyleSheet("font-size: 10px;")
        self._spn_oct.valueChanged.connect(self._on_octave_changed)
        toolbar.addWidget(self._spn_oct)

        lbl_vel = QLabel("Vel:")
        lbl_vel.setStyleSheet("font-size: 10px; color: #aaa;")
        toolbar.addWidget(lbl_vel)

        self._spn_vel = QSpinBox()
        self._spn_vel.setRange(1, 127)
        self._spn_vel.setValue(self._velocity)
        self._spn_vel.setFixedWidth(46)
        self._spn_vel.setFixedHeight(20)
        self._spn_vel.setStyleSheet("font-size: 10px;")
        self._spn_vel.valueChanged.connect(lambda v: setattr(self, '_velocity', max(1, min(127, v))))
        toolbar.addWidget(self._spn_vel)

        toolbar.addStretch()

        # Layout: toolbar on top, keys below (painted)
        from PyQt6.QtWidgets import QVBoxLayout
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        tb_widget = QWidget()
        tb_widget.setLayout(toolbar)
        tb_widget.setFixedHeight(24)
        main_lay.addWidget(tb_widget)
        main_lay.addStretch()  # piano keys are painted in remaining space

    def set_midi_manager(self, mm) -> None:
        self._release_all()
        self._midi_manager = mm

    def _on_octave_changed(self, v: int) -> None:
        self._release_all()
        self._base_octave = max(0, min(7, v))

    # ---- geometry helpers ----

    def _keys_rect(self) -> QRect:
        """Return the rect for the piano keys area (below toolbar)."""
        return QRect(0, 24, self.width(), self.height() - 24)

    def _white_key_width(self) -> float:
        total_whites = self._num_octaves * 7 + 1  # +1 for final C
        return max(8.0, self._keys_rect().width() / total_whites)

    def _note_at_pos(self, x: int, y: int) -> int:
        """Return MIDI note at pixel position, or -1."""
        kr = self._keys_rect()
        if y < kr.top() or y > kr.bottom() or x < kr.left() or x > kr.right():
            return -1

        wkw = self._white_key_width()
        bkw = wkw * 0.6
        bkh = kr.height() * 0.6

        # Check black keys first (they're on top)
        if y < kr.top() + bkh:
            for octave in range(self._num_octaves):
                for semitone, gap_idx in _BLACK_POSITIONS.items():
                    # Black key position: between white keys gap_idx and gap_idx+1
                    white_idx = octave * 7 + gap_idx
                    bx = kr.left() + (white_idx + 1) * wkw - bkw / 2
                    if bx <= x <= bx + bkw:
                        midi_note = (self._base_octave + octave) * 12 + semitone
                        if 0 <= midi_note <= 127:
                            return midi_note

        # White keys
        white_idx = int((x - kr.left()) / wkw)
        octave = white_idx // 7
        key_in_octave = white_idx % 7
        if octave >= self._num_octaves:
            # Last key = C of next octave
            midi_note = (self._base_octave + self._num_octaves) * 12
            return midi_note if 0 <= midi_note <= 127 else -1
        if key_in_octave < len(_WHITE_KEYS):
            semitone = _WHITE_KEYS[key_in_octave]
            midi_note = (self._base_octave + octave) * 12 + semitone
            if 0 <= midi_note <= 127:
                return midi_note
        return -1

    # ---- painting ----

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        kr = self._keys_rect()
        wkw = self._white_key_width()
        bkw = wkw * 0.6
        bkh = kr.height() * 0.6

        total_whites = self._num_octaves * 7 + 1

        # Draw white keys
        for i in range(total_whites):
            x = kr.left() + i * wkw
            octave = i // 7
            key_in_octave = i % 7
            if octave < self._num_octaves and key_in_octave < len(_WHITE_KEYS):
                midi_note = (self._base_octave + octave) * 12 + _WHITE_KEYS[key_in_octave]
            elif octave >= self._num_octaves:
                midi_note = (self._base_octave + self._num_octaves) * 12
            else:
                midi_note = -1

            if midi_note in self._held_notes:
                p.setBrush(QColor("#e77d22"))  # orange = pressed
            elif midi_note == self._hover_note:
                p.setBrush(QColor("#ddd"))
            else:
                p.setBrush(QColor("#f0f0f0"))
            p.setPen(QPen(QColor("#555"), 0.5))
            p.drawRect(int(x), kr.top(), int(wkw - 1), kr.height())

            # C label
            if key_in_octave == 0 and octave <= self._num_octaves:
                oct_num = self._base_octave + octave
                p.setPen(QColor("#999"))
                p.drawText(int(x + 2), kr.bottom() - 3, f"C{oct_num}")

        # Draw black keys
        for octave in range(self._num_octaves):
            for semitone, gap_idx in _BLACK_POSITIONS.items():
                white_idx = octave * 7 + gap_idx
                bx = kr.left() + (white_idx + 1) * wkw - bkw / 2
                midi_note = (self._base_octave + octave) * 12 + semitone

                if midi_note in self._held_notes:
                    p.setBrush(QColor("#e77d22"))
                elif midi_note == self._hover_note:
                    p.setBrush(QColor("#444"))
                else:
                    p.setBrush(QColor("#222"))
                p.setPen(QPen(QColor("#111"), 0.5))
                p.drawRect(int(bx), kr.top(), int(bkw), int(bkh))

        p.end()

    # ---- mouse events ----

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        note = self._note_at_pos(int(ev.position().x()), int(ev.position().y()))
        if note >= 0:
            self._note_on(note)
        ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._release_all()
        ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        note = self._note_at_pos(int(ev.position().x()), int(ev.position().y()))
        if note != self._hover_note:
            self._hover_note = note
            self.update()
        # Drag-play: if mouse is pressed, trigger new notes
        if ev.buttons() & Qt.MouseButton.LeftButton:
            if note >= 0 and note not in self._held_notes:
                self._release_all()
                self._note_on(note)
        ev.accept()

    def leaveEvent(self, ev) -> None:  # noqa: N802
        self._hover_note = -1
        self.update()

    # ---- MIDI ----

    def _note_on(self, note: int) -> None:
        if note in self._held_notes:
            return
        self._held_notes.add(note)
        self.update()
        try:
            self.note_played.emit(note, self._velocity)
        except Exception:
            pass

        mm = self._midi_manager
        if mm is None:
            return
        try:
            import mido  # type: ignore
            msg = mido.Message("note_on", note=int(note), velocity=int(self._velocity), channel=0)
            mm.inject_message(msg, source="touch_keyboard")
        except ImportError:
            from pydaw.services.computer_keyboard_midi import _FakeMsg
            mm.inject_message(_FakeMsg("note_on", int(note), int(self._velocity), 0), source="touch_keyboard")
        except Exception:
            pass

    def _note_off(self, note: int) -> None:
        if note not in self._held_notes:
            return
        self._held_notes.discard(note)
        self.update()

        mm = self._midi_manager
        if mm is None:
            return
        try:
            import mido  # type: ignore
            msg = mido.Message("note_off", note=int(note), velocity=0, channel=0)
            mm.inject_message(msg, source="touch_keyboard")
        except ImportError:
            from pydaw.services.computer_keyboard_midi import _FakeMsg
            mm.inject_message(_FakeMsg("note_off", int(note), 0, 0), source="touch_keyboard")
        except Exception:
            pass

    def _release_all(self) -> None:
        for note in list(self._held_notes):
            self._note_off(note)
        self._held_notes.clear()
        self.update()
