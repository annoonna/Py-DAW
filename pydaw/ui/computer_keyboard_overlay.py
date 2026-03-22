# -*- coding: utf-8 -*-
"""ComputerKeyboardOverlay (v0.0.20.610)

Dezentes, semi-transparentes Overlay das die QWERTY-MIDI-Belegung zeigt.
Erscheint automatisch wenn Computer Keyboard aktiv ist, verschwindet wenn aus.
Positioniert sich am unteren Rand des MainWindow, über der Statusbar.

Inspiriert von Bitwig Studio's Computer Keyboard Overlay:
- Dunkel, semi-transparent, nicht modal
- Zeigt nur die aktiven Tasten visuell
- Leuchtet bei Tastendruck kurz auf (orange)
- Verschwindet sofort beim Deaktivieren
"""

from __future__ import annotations

from typing import Optional, Set, Dict

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPaintEvent, QKeyEvent
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect


# Layout: two rows of keys
# Auto-detect QWERTZ vs QWERTY (reuse detection from computer_keyboard_midi)
def _is_qwertz() -> bool:
    """Auto-detect QWERTZ keyboard layout from system locale/env."""
    qwertz_prefixes = ("de", "at", "ch", "cs", "hu", "hr", "sl", "sk")
    try:
        import locale, os
        for var in ("LANG", "LC_ALL", "LANGUAGE", "LC_MESSAGES"):
            val = str(os.environ.get(var, "")).lower()
            for prefix in qwertz_prefixes:
                if val.startswith(prefix + "_") or val.startswith(prefix + "."):
                    return True
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

_QWERTZ = _is_qwertz()

# Upper row: black keys — Z/Y swapped on QWERTZ
_BK_KEY = "Z" if _QWERTZ else "Y"  # The key that plays G# (physically between T and U)
_ROW_UPPER = [
    ("W", "C#"), ("E", "D#"), ("", ""), ("T", "F#"), (_BK_KEY, "G#"), ("U", "A#"), ("", ""), ("O", "C#"), ("P", "D#"),
]
# Middle row: white keys (same on both layouts)
_ROW_LOWER = [
    ("A", "C"), ("S", "D"), ("D", "E"), ("F", "F"), ("G", "G"), ("H", "A"), ("J", "B"), ("K", "C"), ("L", "D"),
]
# Bottom row: low octave — Z/Y swapped on QWERTZ
_LO_KEY = "Y" if _QWERTZ else "Z"  # The key that plays C-1 (physically left of X)
_ROW_BOTTOM = [
    (_LO_KEY, "C"), ("X", "D"), ("C", "E"), ("V", "F"), ("B", "G"), ("N", "A"), ("M", "B"),
]

# Qt key codes for highlighting
_KEY_CODES: Dict[str, int] = {
    "A": Qt.Key.Key_A, "S": Qt.Key.Key_S, "D": Qt.Key.Key_D, "F": Qt.Key.Key_F,
    "G": Qt.Key.Key_G, "H": Qt.Key.Key_H, "J": Qt.Key.Key_J, "K": Qt.Key.Key_K,
    "L": Qt.Key.Key_L, "W": Qt.Key.Key_W, "E": Qt.Key.Key_E, "T": Qt.Key.Key_T,
    "Y": Qt.Key.Key_Y, "U": Qt.Key.Key_U, "O": Qt.Key.Key_O, "P": Qt.Key.Key_P,
    "Z": Qt.Key.Key_Z, "X": Qt.Key.Key_X, "C": Qt.Key.Key_C, "V": Qt.Key.Key_V,
    "B": Qt.Key.Key_B, "N": Qt.Key.Key_N, "M": Qt.Key.Key_M,
}
_CODE_TO_LETTER: Dict[int, str] = {v: k for k, v in _KEY_CODES.items()}


class ComputerKeyboardOverlay(QWidget):
    """Semi-transparent overlay showing QWERTY→MIDI key mapping."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._active_keys: Set[str] = set()  # currently pressed key letters
        self._octave: int = 4
        self._fade_keys: Dict[str, float] = {}  # letter → fade alpha (0..1)

        self.setFixedHeight(90)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.Widget)

        # Fade-out timer for released keys (brief orange glow)
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)
        self._fade_timer.timeout.connect(self._tick_fade)

        # Slide-in animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self.hide()

    # ---- public API ----

    def set_visible_animated(self, visible: bool) -> None:
        """Show/hide with a smooth fade animation."""
        if visible:
            self.show()
            self._animate_opacity(0.0, 1.0)
        else:
            self._animate_opacity(1.0, 0.0, on_done=self.hide)

    def set_octave(self, octave: int) -> None:
        self._octave = int(octave)
        self.update()

    def key_pressed(self, key_code: int) -> None:
        """Notify that a key was pressed (highlight it)."""
        letter = _CODE_TO_LETTER.get(key_code, "")
        if letter:
            self._active_keys.add(letter)
            self._fade_keys.pop(letter, None)
            self.update()

    def key_released(self, key_code: int) -> None:
        """Notify that a key was released (start fade-out glow)."""
        letter = _CODE_TO_LETTER.get(key_code, "")
        if letter:
            self._active_keys.discard(letter)
            self._fade_keys[letter] = 1.0
            if not self._fade_timer.isActive():
                self._fade_timer.start()
            self.update()

    # ---- painting ----

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background: dark semi-transparent rounded rect
        p.setBrush(QColor(30, 30, 30, 210))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(4, 0, w - 8, h - 2, 10, 10)

        # Info text on the left
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont("sans-serif", 9))
        _layout = "QWERTZ" if _QWERTZ else "QWERTY"
        p.drawText(14, 16, f"Computer Keyboard MIDI ({_layout}) — Oktave {self._octave}")
        p.setPen(QColor(120, 120, 120))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(14, 28, ",/. = Oktave −/+    Ctrl+Shift+K = Aus")

        # Key layout
        key_w = 28
        key_h = 22
        gap = 2
        start_y = 36

        # Row 1 (upper): black keys with offset
        x_off = 180
        bk_offset = int(key_w * 0.6)
        self._draw_key_row(p, _ROW_UPPER, x_off + bk_offset, start_y, key_w, key_h, gap, is_black=True)

        # Row 2 (middle): white keys
        self._draw_key_row(p, _ROW_LOWER, x_off, start_y + key_h + gap, key_w, key_h, gap, is_black=False)

        # Row 3 (bottom): low octave
        self._draw_key_row(p, _ROW_BOTTOM, x_off, start_y + 2 * (key_h + gap), key_w, key_h, gap, is_black=False)

        # Octave labels
        p.setPen(QColor(100, 100, 100))
        p.setFont(QFont("sans-serif", 7))
        p.drawText(x_off - 30, start_y + key_h + gap + 15, f"Oct {self._octave}")
        p.drawText(x_off - 30, start_y + 2 * (key_h + gap) + 15, f"Oct {self._octave - 1}")

        p.end()

    def _draw_key_row(self, p: QPainter, keys: list, x: int, y: int,
                      kw: int, kh: int, gap: int, *, is_black: bool) -> None:
        """Draw a row of keys."""
        cx = x
        for letter, note_name in keys:
            if not letter:
                cx += kw + gap
                continue

            # Determine key state
            is_pressed = letter in self._active_keys
            fade = self._fade_keys.get(letter, 0.0)

            if is_pressed:
                bg = QColor(231, 125, 34)  # Bitwig orange
                fg = QColor(255, 255, 255)
            elif fade > 0.01:
                alpha = int(fade * 180)
                bg = QColor(231, 125, 34, alpha)
                fg = QColor(255, 255, 255, int(fade * 255))
            elif is_black:
                bg = QColor(50, 50, 50)
                fg = QColor(180, 180, 180)
            else:
                bg = QColor(70, 70, 70)
                fg = QColor(200, 200, 200)

            # Key rect
            p.setBrush(bg)
            p.setPen(QPen(QColor(90, 90, 90), 0.5))
            p.drawRoundedRect(cx, y, kw, kh, 4, 4)

            # Letter (top-left, small)
            p.setPen(fg)
            p.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
            p.drawText(cx + 3, y + 11, letter)

            # Note name (bottom-center, smaller)
            note_color = QColor(fg)
            note_color.setAlpha(max(80, note_color.alpha() - 60))
            p.setPen(note_color)
            p.setFont(QFont("sans-serif", 7))
            p.drawText(cx + 3, y + kh - 3, note_name)

            cx += kw + gap

    # ---- animation helpers ----

    def _animate_opacity(self, start: float, end: float, on_done=None) -> None:
        try:
            anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
            anim.setDuration(200)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            if on_done:
                anim.finished.connect(on_done)
            anim.start()
            self._current_anim = anim  # prevent GC
        except Exception:
            self._opacity_effect.setOpacity(end)
            if end <= 0:
                self.hide()
            else:
                self.show()

    def _tick_fade(self) -> None:
        """Fade out released key highlights."""
        done = []
        for letter, alpha in self._fade_keys.items():
            alpha -= 0.12
            if alpha <= 0.01:
                done.append(letter)
            else:
                self._fade_keys[letter] = alpha
        for letter in done:
            self._fade_keys.pop(letter, None)
        if not self._fade_keys:
            self._fade_timer.stop()
        self.update()
