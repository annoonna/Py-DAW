"""Clef Dialog + Clef Data Model (v0.0.20.447).

Provides:
- ``ClefType`` enum with all standard clefs
- ``CLEF_REGISTRY`` dict with rendering + music-theory metadata
- ``ClefDialog`` — visual picker (arrow-buttons, live preview, tooltips)

Design: Safe, no external dependencies, all rendering via QPainter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, pyqtSlot
from PyQt6.QtGui import QFont, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QToolButton,
    QWidget,
)


# ── Clef Types ──────────────────────────────────────────────────

class ClefType(str, Enum):
    TREBLE = "treble"
    BASS = "bass"
    ALTO = "alto"
    TENOR = "tenor"
    SOPRANO = "soprano"
    MEZZO_SOPRANO = "mezzo_soprano"
    BARITONE_C = "baritone_c"
    BARITONE_F = "baritone_f"
    TREBLE_8VA = "treble_8va"
    TREBLE_8VB = "treble_8vb"
    BASS_8VA = "bass_8va"
    BASS_8VB = "bass_8vb"


@dataclass(frozen=True)
class ClefInfo:
    """Metadata for a single clef type."""

    name: str              # Display name (deutsch)
    symbol: str            # Unicode glyph for rendering
    ref_pitch: int         # MIDI pitch of the reference note
    ref_line: int          # Staff line (0=bottom, 4=top) where ref_pitch sits
    octave_shift: int      # 0 normal, +1 = 8va, -1 = 8vb
    tooltip: str           # Ausführlicher Tooltip (deutsch)


# ── Registry ────────────────────────────────────────────────────

CLEF_REGISTRY: dict[str, ClefInfo] = {
    ClefType.TREBLE: ClefInfo(
        name="Violinschlüssel (G)",
        symbol="𝄞",
        ref_pitch=67,  # G4
        ref_line=1,    # Linie 2 von unten (index 1)
        octave_shift=0,
        tooltip=(
            "Violinschlüssel / G-Schlüssel (Treble Clef)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄞\n"
            "Referenz-Note: G4 (MIDI 67)\n"
            "Referenz-Linie: Linie 2 von unten\n\n"
            "Der häufigste Schlüssel. Wird für hohe Instrumente\n"
            "und Stimmen verwendet: Violine, Flöte, Oboe,\n"
            "Klarinette, Trompete, Sopran, Alt, Tenor.\n"
            "Die Spirale des Schlüssels umkreist die G-Linie."
        ),
    ),
    ClefType.BASS: ClefInfo(
        name="Bassschlüssel (F)",
        symbol="𝄢",
        ref_pitch=53,  # F3
        ref_line=3,    # Linie 4 von unten (index 3)
        octave_shift=0,
        tooltip=(
            "Bassschlüssel / F-Schlüssel (Bass Clef)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄢\n"
            "Referenz-Note: F3 (MIDI 53)\n"
            "Referenz-Linie: Linie 4 von unten\n\n"
            "Für tiefe Instrumente und Stimmen: Cello,\n"
            "Kontrabass, Fagott, Posaune, Tuba, Bass.\n"
            "Die zwei Punkte des Schlüssels flankieren die F-Linie."
        ),
    ),
    ClefType.ALTO: ClefInfo(
        name="Altschlüssel (C3)",
        symbol="𝄡",
        ref_pitch=60,  # C4 (Middle C)
        ref_line=2,    # Mittlere Linie (index 2)
        octave_shift=0,
        tooltip=(
            "Altschlüssel / C-Schlüssel auf Linie 3 (Alto Clef)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄡\n"
            "Referenz-Note: C4 / Mittleres C (MIDI 60)\n"
            "Referenz-Linie: Mittlere Linie (Linie 3)\n\n"
            "Hauptsächlich für Bratsche (Viola) verwendet.\n"
            "Der Schlüssel zeigt an, wo das mittlere C liegt.\n"
            "Die Symmetrieachse des Schlüssels sitzt auf Linie 3."
        ),
    ),
    ClefType.TENOR: ClefInfo(
        name="Tenorschlüssel (C4)",
        symbol="𝄡",
        ref_pitch=60,  # C4
        ref_line=3,    # Linie 4 von unten (index 3)
        octave_shift=0,
        tooltip=(
            "Tenorschlüssel / C-Schlüssel auf Linie 4 (Tenor Clef)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄡\n"
            "Referenz-Note: C4 / Mittleres C (MIDI 60)\n"
            "Referenz-Linie: Linie 4 von unten\n\n"
            "Für hohe Lagen von Cello, Fagott, Posaune.\n"
            "Vermeidet zu viele Hilfslinien im oberen Register.\n"
            "Gleicher Schlüssel wie Alt, aber auf Linie 4 verschoben."
        ),
    ),
    ClefType.SOPRANO: ClefInfo(
        name="Sopranschlüssel (C1)",
        symbol="𝄡",
        ref_pitch=60,  # C4
        ref_line=0,    # Linie 1 von unten (unterste Linie, index 0)
        octave_shift=0,
        tooltip=(
            "Sopranschlüssel / C-Schlüssel auf Linie 1 (Soprano Clef)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄡\n"
            "Referenz-Note: C4 / Mittleres C (MIDI 60)\n"
            "Referenz-Linie: Linie 1 von unten (unterste Linie)\n\n"
            "Historischer Schlüssel, heute selten verwendet.\n"
            "War in der Barockzeit für Sopranstimmen üblich.\n"
            "Findet sich noch in älteren Partituren (Bach, Händel)."
        ),
    ),
    ClefType.MEZZO_SOPRANO: ClefInfo(
        name="Mezzosopranschlüssel (C2)",
        symbol="𝄡",
        ref_pitch=60,  # C4
        ref_line=1,    # Linie 2 von unten (index 1)
        octave_shift=0,
        tooltip=(
            "Mezzosopranschlüssel / C-Schlüssel auf Linie 2\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄡\n"
            "Referenz-Note: C4 / Mittleres C (MIDI 60)\n"
            "Referenz-Linie: Linie 2 von unten\n\n"
            "Historischer Schlüssel, heute sehr selten.\n"
            "War für Mezzosopran-Stimmen in der Barockzeit.\n"
            "Mittleres C liegt auf der zweiten Linie von unten."
        ),
    ),
    ClefType.BARITONE_C: ClefInfo(
        name="Baritonschlüssel (C5)",
        symbol="𝄡",
        ref_pitch=60,  # C4
        ref_line=4,    # Linie 5 von unten (oberste Linie, index 4)
        octave_shift=0,
        tooltip=(
            "Baritonschlüssel / C-Schlüssel auf Linie 5\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄡\n"
            "Referenz-Note: C4 / Mittleres C (MIDI 60)\n"
            "Referenz-Linie: Linie 5 (oberste Linie)\n\n"
            "Historischer Schlüssel für Bariton-Stimmen.\n"
            "Heute extrem selten, durch Bassschlüssel ersetzt.\n"
            "Mittleres C auf der obersten Linie."
        ),
    ),
    ClefType.BARITONE_F: ClefInfo(
        name="Baritonschlüssel (F3)",
        symbol="𝄢",
        ref_pitch=53,  # F3
        ref_line=2,    # Mittlere Linie (index 2)
        octave_shift=0,
        tooltip=(
            "Baritonschlüssel / F-Schlüssel auf Linie 3\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄢\n"
            "Referenz-Note: F3 (MIDI 53)\n"
            "Referenz-Linie: Mittlere Linie (Linie 3)\n\n"
            "Variante des Bassschlüssels auf Linie 3.\n"
            "Ergibt die gleichen Tonhöhen wie C5-Baritonschlüssel.\n"
            "Heute durch den normalen Bassschlüssel ersetzt."
        ),
    ),
    ClefType.TREBLE_8VA: ClefInfo(
        name="Violinschlüssel 8va (Oktave höher)",
        symbol="𝄞⁸↑",
        ref_pitch=67 + 12,  # G5
        ref_line=1,
        octave_shift=+1,
        tooltip=(
            "Violinschlüssel mit 8va (eine Oktave höher)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄞⁸\n"
            "Referenz-Note: G5 (MIDI 79) — eine Oktave über G4\n"
            "Referenz-Linie: Linie 2 von unten (wie Violin)\n\n"
            "Alle Noten erklingen eine Oktave höher als notiert.\n"
            "Für Piccolo, Glockenspiel, oder sehr hohe Passagen.\n"
            "Kleine '8' über dem Schlüssel zeigt die Oktavierung."
        ),
    ),
    ClefType.TREBLE_8VB: ClefInfo(
        name="Violinschlüssel 8vb (Oktave tiefer)",
        symbol="𝄞₈↓",
        ref_pitch=67 - 12,  # G3
        ref_line=1,
        octave_shift=-1,
        tooltip=(
            "Violinschlüssel mit 8vb (eine Oktave tiefer)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄞₈\n"
            "Referenz-Note: G3 (MIDI 55) — eine Oktave unter G4\n"
            "Referenz-Linie: Linie 2 von unten (wie Violin)\n\n"
            "Alle Noten erklingen eine Oktave tiefer als notiert.\n"
            "Häufig für Tenor-Stimme, Gitarre (klingt 8vb!).\n"
            "Kleine '8' unter dem Schlüssel zeigt die Oktavierung."
        ),
    ),
    ClefType.BASS_8VA: ClefInfo(
        name="Bassschlüssel 8va (Oktave höher)",
        symbol="𝄢⁸↑",
        ref_pitch=53 + 12,  # F4
        ref_line=3,
        octave_shift=+1,
        tooltip=(
            "Bassschlüssel mit 8va (eine Oktave höher)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄢⁸\n"
            "Referenz-Note: F4 (MIDI 65)\n"
            "Referenz-Linie: Linie 4 von unten (wie Bass)\n\n"
            "Selten verwendet. Alle Noten eine Oktave höher."
        ),
    ),
    ClefType.BASS_8VB: ClefInfo(
        name="Bassschlüssel 8vb (Oktave tiefer)",
        symbol="𝄢₈↓",
        ref_pitch=53 - 12,  # F2
        ref_line=3,
        octave_shift=-1,
        tooltip=(
            "Bassschlüssel mit 8vb (eine Oktave tiefer)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Unicode: 𝄢₈\n"
            "Referenz-Note: F2 (MIDI 41)\n"
            "Referenz-Linie: Linie 4 von unten (wie Bass)\n\n"
            "Für Kontrabass, Sub-Bass. Alle Noten eine Oktave tiefer.\n"
            "Kleine '8' unter dem Schlüssel."
        ),
    ),
}

# Ordered list for dialog navigation
CLEF_ORDER: list[str] = [
    ClefType.TREBLE,
    ClefType.BASS,
    ClefType.ALTO,
    ClefType.TENOR,
    ClefType.SOPRANO,
    ClefType.MEZZO_SOPRANO,
    ClefType.BARITONE_C,
    ClefType.BARITONE_F,
    ClefType.TREBLE_8VA,
    ClefType.TREBLE_8VB,
    ClefType.BASS_8VA,
    ClefType.BASS_8VB,
]


def get_clef(clef_type: str) -> ClefInfo:
    """Safe lookup with treble fallback."""
    key = str(clef_type)
    # Handle both "treble" and "ClefType.TREBLE" formats
    if key in CLEF_REGISTRY:
        return CLEF_REGISTRY[key]
    # Try extracting .value if it's an enum
    if hasattr(clef_type, 'value'):
        key = str(clef_type.value)
        if key in CLEF_REGISTRY:
            return CLEF_REGISTRY[key]
    # Try matching by iterating
    for k, v in CLEF_REGISTRY.items():
        kv = str(k.value) if hasattr(k, 'value') else str(k)
        if kv == key or str(k) == key:
            return v
    return CLEF_REGISTRY[ClefType.TREBLE]


# ── Pitch ↔ Staff-Line Mapping ─────────────────────────────────

def pitch_to_staff_line(pitch: int, clef_type: str = "treble") -> int:
    """Convert MIDI pitch to staff line position for any clef.

    Returns a half-step offset from the bottom staff line (0).
    Positive = higher, negative = below staff (ledger lines).

    This replaces the old hardcoded treble-only mapping.
    """
    info = get_clef(clef_type)

    # Diatonic step table: pitch class → diatonic index (C=0..B=6)
    _pc_to_diat = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]

    ref_p = int(info.ref_pitch)
    ref_l = int(info.ref_line)  # staff line index 0..4

    # Convert ref_line (0=bottom, 4=top) to half-step units from bottom
    ref_halfsteps = ref_l * 2

    # Diatonic distance between pitch and ref_pitch
    p = int(pitch)
    p_oct = (p // 12) - 1
    p_pc = p % 12
    p_diat = p_oct * 7 + _pc_to_diat[p_pc]

    r_oct = (ref_p // 12) - 1
    r_pc = ref_p % 12
    r_diat = r_oct * 7 + _pc_to_diat[r_pc]

    diat_diff = p_diat - r_diat

    return ref_halfsteps + diat_diff


# ── Clef Preview Widget ────────────────────────────────────────

class _ClefPreview(QWidget):
    """Small preview widget that draws a staff with the clef symbol."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clef_type: str = ClefType.TREBLE
        self.setMinimumSize(200, 120)
        self.setMaximumSize(300, 160)

    def set_clef(self, clef_type: str) -> None:
        self._clef_type = str(clef_type)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Background
            p.fillRect(self.rect(), QColor(245, 245, 248))

            w = self.width()
            h = self.height()
            y_off = h // 2 - 20
            line_dist = 10
            margin = 30

            # Draw staff
            pen = QPen(QColor(60, 60, 70))
            pen.setWidth(1)
            p.setPen(pen)
            for i in range(5):
                y = y_off + i * line_dist
                p.drawLine(margin, y, w - margin, y)

            # Draw clef
            info = get_clef(self._clef_type)
            clef_x = margin + 15
            # Position clef symbol on its reference line
            ref_y = y_off + (4 - info.ref_line) * line_dist

            font = QFont("Serif", 28)
            p.setFont(font)
            p.setPen(QPen(QColor(30, 30, 40)))

            # The unicode music symbols need vertical adjustment
            base_sym = info.symbol.rstrip("⁸₈↑↓")
            p.drawText(int(clef_x - 10), int(ref_y + 12), base_sym)

            # Octave indicator
            if info.octave_shift != 0:
                small_font = QFont("Sans", 8)
                p.setFont(small_font)
                p.setPen(QPen(QColor(80, 80, 200)))
                label = "8va" if info.octave_shift > 0 else "8vb"
                oy = ref_y - 22 if info.octave_shift > 0 else ref_y + 22
                p.drawText(int(clef_x - 6), int(oy), label)

            # Reference note indicator (small dot on ref line)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(200, 60, 60, 120))
            p.drawEllipse(int(clef_x + 50), int(ref_y - 3), 6, 6)
            p.setPen(QPen(QColor(160, 50, 50)))
            small = QFont("Sans", 7)
            p.setFont(small)
            note_names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
            rp = info.ref_pitch
            nn = note_names[rp % 12] + str((rp // 12) - 1)
            p.drawText(int(clef_x + 60), int(ref_y + 4), nn)

            p.end()
        except Exception:
            pass


# ── Clef Dialog ─────────────────────────────────────────────────

class ClefDialog(QDialog):
    """Dialog for selecting a clef type with live preview."""

    def __init__(self, current_clef: str = "treble", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schlüssel")
        self.setMinimumWidth(380)

        self._clef_index = 0
        for i, ct in enumerate(CLEF_ORDER):
            if str(ct.value if hasattr(ct, 'value') else ct) == str(current_clef):
                self._clef_index = i
                break

        root = QVBoxLayout(self)

        # ── Clef group ──
        clef_group = QGroupBox("Schlüssel")
        clef_lay = QVBoxLayout(clef_group)

        # Navigation: ◀ [ComboBox] ▶
        nav = QHBoxLayout()

        self._btn_prev = QToolButton()
        self._btn_prev.setText("◀")
        self._btn_prev.setFixedSize(40, 34)

        self._clef_combo = QComboBox()
        for ct in CLEF_ORDER:
            info = CLEF_REGISTRY.get(ct, None)
            if info:
                self._clef_combo.addItem(f"{info.symbol}  {info.name}")
        self._clef_combo.setCurrentIndex(self._clef_index)
        self._clef_combo.setMinimumWidth(220)

        self._btn_next = QToolButton()
        self._btn_next.setText("▶")
        self._btn_next.setFixedSize(40, 34)

        nav.addWidget(self._btn_prev)
        nav.addWidget(self._clef_combo, 1)
        nav.addWidget(self._btn_next)
        clef_lay.addLayout(nav)

        # Preview
        self._preview = _ClefPreview()
        clef_lay.addWidget(self._preview)

        # Name + Info
        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = self._name_label.font()
        f.setPointSize(11)
        f.setBold(True)
        self._name_label.setFont(f)
        clef_lay.addWidget(self._name_label)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #999; font-size: 9pt;")
        clef_lay.addWidget(self._info_label)

        root.addWidget(clef_group)

        # ── Transposition group ──
        trans_group = QGroupBox("Vorhandene Noten folgen Schlüsseländerung")
        trans_lay = QVBoxLayout(trans_group)
        self._rb_keep = QRadioButton("Aktuelle Tonhöhen beibehalten")
        self._rb_keep.setChecked(True)
        self._rb_transpose = QRadioButton("In die richtige Oktave transponieren")
        bg = QButtonGroup(self)
        bg.addButton(self._rb_keep)
        bg.addButton(self._rb_transpose)
        trans_lay.addWidget(self._rb_keep)
        trans_lay.addWidget(self._rb_transpose)
        root.addWidget(trans_group)

        # ── OK / Cancel ──
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

        # ── Wire everything DIRECTLY (no signal trust issues) ──
        # Combo: when user picks from dropdown
        self._clef_combo.activated.connect(self._combo_picked)
        # Buttons: direct method calls
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)

        # Initial display
        self._do_update()

    def _do_update(self) -> None:
        """Read combo index → update preview + labels. Called DIRECTLY, no signals."""
        idx = self._clef_combo.currentIndex()
        if idx < 0 or idx >= len(CLEF_ORDER):
            idx = 0
        self._clef_index = idx
        ct = CLEF_ORDER[idx]
        ct_str = str(ct.value if hasattr(ct, 'value') else ct)
        info = get_clef(ct_str)

        # Update preview widget
        self._preview.set_clef(ct_str)
        self._preview.update()
        self._preview.repaint()

        # Update labels
        self._name_label.setText(info.name)
        lines = info.tooltip.split("\n")
        desc = [l for l in lines if not l.startswith("━") and l.strip()]
        self._info_label.setText("\n".join(desc[:6]))
        self._preview.setToolTip(info.tooltip)
        self._name_label.setToolTip(info.tooltip)

    def _combo_picked(self, idx: int) -> None:
        """User selected from dropdown."""
        self._do_update()

    def _go_prev(self) -> None:
        """◀ button."""
        idx = (self._clef_combo.currentIndex() - 1) % self._clef_combo.count()
        self._clef_combo.setCurrentIndex(idx)
        self._do_update()

    def _go_next(self) -> None:
        """▶ button."""
        idx = (self._clef_combo.currentIndex() + 1) % self._clef_combo.count()
        self._clef_combo.setCurrentIndex(idx)
        self._do_update()

    def selected_clef(self) -> str:
        idx = self._clef_combo.currentIndex()
        if 0 <= idx < len(CLEF_ORDER):
            ct = CLEF_ORDER[idx]
            return str(ct.value if hasattr(ct, 'value') else ct)
        return "treble"

    def should_transpose(self) -> bool:
        return bool(self._rb_transpose.isChecked())
