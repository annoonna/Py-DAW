# -*- coding: utf-8 -*-
"""ComputerKeyboardMidi (v0.0.20.609)

Bitwig-Style Computer Keyboard MIDI input.
Maps QWERTY keys to MIDI notes and injects them into MidiManager
via inject_message(source='computer_keyboard').

Layout (Bitwig/Ableton standard — 2 rows, chromatic):
  Lower row (Z-M):  C  D  E  F  G  A  B  C+1
  Upper row (Q-U):   C# D# _  F# G# A# _  C#+1
  (with black-key sharps on the row above)

Actually using Bitwig's exact mapping:
  Row 1 (white): A=C, S=D, D=E, F=F, G=G, H=A, J=B, K=C+1, L=D+1
  Row 2 (black): W=C#, E=D#, T=F#, Y=G#, U=A#
  Z-row shifts octave down, number row has extra sharps.

Octave shift: Z/X (Bitwig: Z=oct down, X=oct up)
Velocity: fixed 100 (like Bitwig default)
"""

from __future__ import annotations

from typing import Optional, Dict, Set

from PySide6.QtCore import QObject, Qt, QEvent, Signal


# Bitwig-style MIDI mapping (semitone offset from base octave C)
# Two layouts supported: QWERTY (international) and QWERTZ (German/Austrian/Swiss)
#
# The difference: Y and Z are physically swapped.
# On QWERTZ: physical upper-row key between T and U sends Key_Z (not Key_Y)
#            physical bottom-row key left of X sends Key_Y (not Key_Z)
#
# We auto-detect via system locale. German (de_*) → QWERTZ, else → QWERTY.

def _detect_qwertz() -> bool:
    """Auto-detect QWERTZ keyboard layout from system locale/env."""
    qwertz_prefixes = ("de", "at", "ch", "cs", "hu", "hr", "sl", "sk")
    # 1. Check environment variables (most reliable on Linux)
    try:
        import os
        for var in ("LANG", "LC_ALL", "LANGUAGE", "LC_MESSAGES"):
            val = str(os.environ.get(var, "")).lower()
            for prefix in qwertz_prefixes:
                if val.startswith(prefix + "_") or val.startswith(prefix + "."):
                    return True
    except Exception:
        pass
    # 2. Python locale (modern API, fallback)
    try:
        import locale
        for getter in (locale.getlocale, locale.getdefaultlocale):
            try:
                result = getter()
                lang = str(result[0] or "").lower() if result else ""
                for prefix in qwertz_prefixes:
                    if lang.startswith(prefix + "_"):
                        return True
            except Exception:
                continue
    except Exception:
        pass
    return False

_IS_QWERTZ = _detect_qwertz()

# Base mapping (shared keys that don't change between layouts)
_KEY_MAP_BASE: Dict[int, int] = {
    # White keys (middle alpha row: A-L) — same on both layouts
    Qt.Key.Key_A: 0,   # C
    Qt.Key.Key_S: 2,   # D
    Qt.Key.Key_D: 4,   # E
    Qt.Key.Key_F: 5,   # F
    Qt.Key.Key_G: 7,   # G
    Qt.Key.Key_H: 9,   # A
    Qt.Key.Key_J: 11,  # B
    Qt.Key.Key_K: 12,  # C+1
    Qt.Key.Key_L: 14,  # D+1

    # Black keys (upper row) — W, E, T, U are the same
    Qt.Key.Key_W: 1,   # C#
    Qt.Key.Key_E: 3,   # D#
    Qt.Key.Key_T: 6,   # F#
    Qt.Key.Key_U: 10,  # A#
    Qt.Key.Key_O: 13,  # C#+1
    Qt.Key.Key_P: 15,  # D#+1

    # Low octave (bottom row) — X, C, V, B, N, M are the same
    Qt.Key.Key_X: -10,  # D-1
    Qt.Key.Key_C: -8,   # E-1
    Qt.Key.Key_V: -7,   # F-1
    Qt.Key.Key_B: -5,   # G-1
    Qt.Key.Key_N: -3,   # A-1
    Qt.Key.Key_M: -1,   # B-1
}

# Y/Z differ between layouts:
# QWERTZ (German): Z is on upper row (black key G#), Y is on bottom row (low C)
# QWERTY (English): Y is on upper row (black key G#), Z is on bottom row (low C)
if _IS_QWERTZ:
    _KEY_MAP_BASE[Qt.Key.Key_Z] = 8    # Z on upper row → G# (black key)
    _KEY_MAP_BASE[Qt.Key.Key_Y] = -12  # Y on bottom row → C-1 (low octave)
else:
    _KEY_MAP_BASE[Qt.Key.Key_Y] = 8    # Y on upper row → G# (black key)
    _KEY_MAP_BASE[Qt.Key.Key_Z] = -12  # Z on bottom row → C-1 (low octave)

_KEY_MAP: Dict[int, int] = _KEY_MAP_BASE


class ComputerKeyboardMidi(QObject):
    """Captures QWERTY key events and injects MIDI notes into MidiManager.

    Install as event filter on QApplication. Only active when enabled.
    Respects focus: does NOT capture when a QLineEdit/QTextEdit/QSpinBox has focus.
    """

    # Emitted when octave changes (for UI display)
    octave_changed = Signal(int)
    # Emitted when enabled/disabled
    enabled_changed = Signal(bool)
    # v0.0.20.610: Emitted on key press/release for overlay highlighting
    key_pressed = Signal(int)   # Qt key code
    key_released = Signal(int)  # Qt key code

    def __init__(self, midi_manager=None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._midi_manager = midi_manager
        self._enabled: bool = False
        self._base_octave: int = 4  # C4 = middle C (MIDI 60)
        self._velocity: int = 100
        self._held_keys: Set[int] = set()  # Qt key codes currently pressed

    # ---- public API ----

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        if not self._enabled:
            self._release_all()
        try:
            self.enabled_changed.emit(self._enabled)
        except Exception:
            pass

    def toggle(self) -> bool:
        self.set_enabled(not self._enabled)
        return self._enabled

    @property
    def base_octave(self) -> int:
        return self._base_octave

    def set_base_octave(self, octave: int) -> None:
        self._release_all()
        self._base_octave = max(0, min(8, int(octave)))
        try:
            self.octave_changed.emit(self._base_octave)
        except Exception:
            pass

    def octave_up(self) -> None:
        self.set_base_octave(self._base_octave + 1)

    def octave_down(self) -> None:
        self.set_base_octave(self._base_octave - 1)

    def set_midi_manager(self, mm) -> None:
        self._release_all()
        self._midi_manager = mm

    # ---- QObject event filter ----

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if not self._enabled:
            return False

        etype = event.type()
        if etype not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False

        # Don't capture when text-input widgets have focus
        try:
            from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
                return False
        except Exception:
            pass

        # Ignore auto-repeat (held key)
        if event.isAutoRepeat():
            return False

        key = event.key()

        # Octave shift: comma/period (like Bitwig: , = oct down, . = oct up)
        if etype == QEvent.Type.KeyPress:
            if key == Qt.Key.Key_Comma:
                self.octave_down()
                return True
            if key == Qt.Key.Key_Period:
                self.octave_up()
                return True

        # MIDI note mapping
        semitone = _KEY_MAP.get(key)
        if semitone is None:
            return False

        midi_note = (self._base_octave * 12) + semitone
        if midi_note < 0 or midi_note > 127:
            return False

        if etype == QEvent.Type.KeyPress:
            if key not in self._held_keys:
                self._held_keys.add(key)
                self._send_note_on(midi_note, self._velocity)
                try:
                    self.key_pressed.emit(key)
                except Exception:
                    pass
            return True
        elif etype == QEvent.Type.KeyRelease:
            if key in self._held_keys:
                self._held_keys.discard(key)
                self._send_note_off(midi_note)
                try:
                    self.key_released.emit(key)
                except Exception:
                    pass
            return True

        return False

    # ---- internal ----

    def _send_note_on(self, note: int, velocity: int) -> None:
        mm = self._midi_manager
        if mm is None:
            return
        try:
            import mido  # type: ignore
            msg = mido.Message("note_on", note=int(note), velocity=int(velocity), channel=0)
            mm.inject_message(msg, source="computer_keyboard")
        except ImportError:
            # mido not available — create a minimal duck-type message
            mm.inject_message(
                _FakeMsg("note_on", int(note), int(velocity), 0),
                source="computer_keyboard",
            )
        except Exception:
            pass

    def _send_note_off(self, note: int) -> None:
        mm = self._midi_manager
        if mm is None:
            return
        try:
            import mido  # type: ignore
            msg = mido.Message("note_off", note=int(note), velocity=0, channel=0)
            mm.inject_message(msg, source="computer_keyboard")
        except ImportError:
            mm.inject_message(
                _FakeMsg("note_off", int(note), 0, 0),
                source="computer_keyboard",
            )
        except Exception:
            pass

    def _release_all(self) -> None:
        """Release all held notes (panic)."""
        held = list(self._held_keys)
        self._held_keys.clear()
        for key in held:
            semitone = _KEY_MAP.get(key)
            if semitone is not None:
                midi_note = (self._base_octave * 12) + semitone
                if 0 <= midi_note <= 127:
                    self._send_note_off(midi_note)


class _FakeMsg:
    """Minimal MIDI message duck-type when mido is not installed."""

    def __init__(self, mtype: str, note: int, velocity: int, channel: int):
        self.type = mtype
        self.note = note
        self.velocity = velocity
        self.channel = channel

    def __str__(self) -> str:
        return f"{self.type} note={self.note} vel={self.velocity} ch={self.channel}"
