"""Color helpers for notation.

Implements Task 10 (Velocity → Color Mapping) and
Pitch-Class Color + Note Name Display (v0.0.20.451).

Goal
----
Give notes in the NotationView:
- velocity-dependent brightness
- pitch-class-dependent color (Klangfarbe / synesthetic color wheel)
- note name inside the notehead (C, D, E, F, G, A, H)
"""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtGui import QColor


# Keep the base palette consistent with the PianoRoll.
BASE_NOTE_COLOR = QColor(120, 190, 255)  # blue-ish
SELECT_NOTE_COLOR = QColor(255, 185, 110)  # warm/orange


# ── Pitch-Class Color Wheel (Klangfarbe, v0.0.20.451) ─────────
# Chromatic color wheel inspired by Scriabin/synesthetic tradition.
# Each pitch class gets a distinct hue so notes are visually identifiable.
# Colors are chosen to be readable on white background with good contrast.

_PITCH_CLASS_COLORS: dict[int, tuple[int, int, int]] = {
    0:  (220, 50, 50),     # C  = Rot (Grundton-Feeling)
    1:  (210, 85, 45),     # C# = Rot-Orange
    2:  (215, 140, 30),    # D  = Orange
    3:  (190, 170, 25),    # D# = Gelb-Orange
    4:  (160, 180, 30),    # E  = Gelb-Grün
    5:  (60, 170, 60),     # F  = Grün
    6:  (40, 160, 120),    # F# = Grün-Türkis
    7:  (40, 150, 180),    # G  = Türkis/Cyan
    8:  (50, 110, 200),    # G# = Blau
    9:  (80, 70, 190),     # A  = Indigo
    10: (140, 60, 180),    # A#/Bb = Violett
    11: (180, 50, 140),    # B/H = Pink/Magenta
}

# German note names with sharps as -is (Cis, Dis, Fis, Gis, Ais)
_NOTE_NAMES_DE: dict[int, str] = {
    0: "C", 1: "Cis", 2: "D", 3: "Dis", 4: "E", 5: "F",
    6: "Fis", 7: "G", 8: "Gis", 9: "A", 10: "B", 11: "H",
}

# Compact names for inside noteheads (short, fits in ellipse)
_NOTE_NAMES_SHORT: dict[int, str] = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "Bb", 11: "B",
}


def pitch_class_color(pitch: int, *, selected: bool = False, velocity: int = 100) -> QColor:
    """Return a QColor based on pitch class (0=C .. 11=B).

    Velocity modulates brightness (darker at low velocity).
    Selection overrides to the warm selection color.
    """
    if selected:
        return velocity_to_color(velocity, selected=True)

    pc = int(pitch) % 12
    r, g, b = _PITCH_CLASS_COLORS.get(pc, (120, 190, 255))

    # Velocity brightness modulation (subtle)
    vel = _clamp_velocity(velocity)
    t = float(vel) / 127.0
    bright = 0.55 + t * 0.45  # range 0.55 .. 1.0
    r = int(min(255, r * bright))
    g = int(min(255, g * bright))
    b = int(min(255, b * bright))

    return QColor(r, g, b)


def pitch_class_outline(pitch: int, *, selected: bool = False, velocity: int = 100) -> QColor:
    """Outline color for pitch-class colored notes."""
    if selected:
        return QColor(0, 0, 0)
    fill = pitch_class_color(pitch, selected=False, velocity=velocity)
    return fill.darker(150)


def pitch_class_text_color(pitch: int) -> QColor:
    """High-contrast text color for note name inside the notehead.

    Returns white for dark fills, dark for light fills.
    """
    pc = int(pitch) % 12
    r, g, b = _PITCH_CLASS_COLORS.get(pc, (120, 190, 255))
    # Luminance check (perceived brightness)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 140:
        return QColor(255, 255, 255, 230)  # white text on dark fills
    else:
        return QColor(20, 20, 20, 230)  # dark text on light fills


def note_name(pitch: int, *, german: bool = True, with_octave: bool = True) -> str:
    """Return the note name for a MIDI pitch.

    german=True: C, Cis, D, Dis, E, F, Fis, G, Gis, A, B, H
    german=False: C, C#, D, D#, E, F, F#, G, G#, A, Bb, B
    with_octave=True: appends octave number (e.g. C4, Dis3, H-1)
    """
    pc = int(pitch) % 12
    octave = (int(pitch) // 12) - 1  # MIDI: C4 = 60, octave = 4
    if german:
        nn = _NOTE_NAMES_DE.get(pc, "?")
    else:
        nn = _NOTE_NAMES_SHORT.get(pc, "?")
    if with_octave:
        return f"{nn}{octave}"
    return nn


def _clamp_velocity(v: int | float | None) -> int:
    try:
        vv = int(v) if v is not None else 100
    except Exception:
        vv = 100
    return max(1, min(127, vv))


@lru_cache(maxsize=256)
def velocity_to_color(velocity: int, *, selected: bool = False) -> QColor:
    """Map MIDI velocity (1..127) to a QColor.

    Strategy:
    - Use the PianoRoll base hue.
    - Adjust saturation and value (HSV) with velocity.
    - If selected: use the selection base color but still keep subtle
      velocity variation so soft notes don't look identical.
    """

    vel = _clamp_velocity(velocity)
    t = float(vel) / 127.0

    base = QColor(SELECT_NOTE_COLOR if selected else BASE_NOTE_COLOR)
    h, _s, _v, _a = base.getHsv()

    # Velocity modulation: low velocity -> darker/desaturated,
    # high velocity -> saturated/bright.
    # Values tuned to still read well on a white background.
    new_s = int(60 + t * 195)  # 60..255
    new_v = int(90 + t * 165)  # 90..255

    out = QColor(base)
    out.setHsv(h, max(0, min(255, new_s)), max(0, min(255, new_v)), 255)
    return out


@lru_cache(maxsize=256)
def velocity_to_outline(velocity: int, *, selected: bool = False) -> QColor:
    """Outline color for a note head.

    Slightly darker than the fill. Selection uses a stronger outline.
    """

    fill = velocity_to_color(velocity, selected=selected)
    if selected:
        return QColor(0, 0, 0)
    return QColor(fill).darker(160)
