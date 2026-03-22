"""Clip Launcher Inspector Panel (Bitwig-Style "ZELLE" / Cell Properties).

v0.0.20.147:
- Per-clip launcher properties inspector (like Bitwig's left sidebar)
- Shows when a launcher clip is selected
- Sections: ZELLE (Cell), LAUNCHER-CLIP, Quantization, Next Action, 
  Audio Event, Expressions
- All changes are non-destructive and saved to the Clip model
- Wired to ClipContextService for slot selection broadcast

Architecture:
- ClipLauncherInspector is a QWidget that sits in a QDockWidget or
  embedded in the ClipLauncherPanel layout
- It observes clip_context.active_slot_changed and refreshes
- All edits go through ProjectService for undo/redo compatibility
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QFrame, QScrollArea, QGroupBox, QGridLayout, QToolButton,
    QSizePolicy, QSlider,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QFont

if TYPE_CHECKING:
    from pydaw.services.project_service import ProjectService
    from pydaw.services.clip_context_service import ClipContextService
    from pydaw.model.project import Clip

log = logging.getLogger(__name__)

# ── Bitwig-style color palette for launcher clips ──
LAUNCHER_COLORS = [
    "#E04040", "#E07040", "#E0A040", "#E0D040",
    "#80D040", "#40D080", "#40D0D0", "#4080D0",
    "#6060D0", "#9040D0", "#D040D0", "#D04080",
    "#808080", "#A0A0A0", "#C08060", "#60C0A0",
]


class ColorPadWidget(QWidget):
    """Mini color picker grid (4x4) like Bitwig's clip color selector."""
    color_changed = Signal(int)  # color index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = 0
        self.setFixedHeight(52)
        self.setMinimumWidth(100)

    def set_color_index(self, idx: int) -> None:
        self._selected = max(0, min(15, int(idx)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            cols = 8
            rows = 2
            w = self.width()
            h = self.height()
            cw = max(8, w // cols)
            ch = max(8, h // rows)
            for i, color_hex in enumerate(LAUNCHER_COLORS):
                r = i // cols
                c = i % cols
                x = c * cw
                y = r * ch
                color = QColor(color_hex)
                p.setBrush(color)
                if i == self._selected:
                    p.setPen(Qt.GlobalColor.white)
                    p.drawRoundedRect(x + 1, y + 1, cw - 2, ch - 2, 3, 3)
                else:
                    p.setPen(Qt.GlobalColor.transparent)
                    p.drawRoundedRect(x + 2, y + 2, cw - 4, ch - 4, 2, 2)
        finally:
            p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            cols = 8
            cw = max(8, self.width() // cols)
            ch = max(8, self.height() // 2)
            c = int(event.position().x()) // cw
            r = int(event.position().y()) // ch
            idx = r * cols + c
            if 0 <= idx < 16:
                self._selected = idx
                self.color_changed.emit(idx)
                self.update()


class _SectionHeader(QLabel):
    """Styled section header like Bitwig's inspector sections."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "QLabel { color: #AAA; font-size: 10px; font-weight: bold; "
            "padding: 4px 0 2px 0; border-bottom: 1px solid #444; }"
        )


class _ParamRow(QWidget):
    """Label + widget on one row, compact like Bitwig inspector."""
    def __init__(self, label: str, widget: QWidget, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(70)
        lbl.setStyleSheet("QLabel { color: #BBB; font-size: 10px; }")
        lay.addWidget(lbl)
        lay.addWidget(widget, 1)


class ClipLauncherInspector(QWidget):
    """Bitwig-Style ZELLE (Cell) Inspector for Clip Launcher slots.

    Displays and edits per-clip launcher properties:
    - Clip name, color
    - Time signature, Start/Stop, Loop params
    - Per-clip quantization (Main/ALT)
    - Playback mode, Release action, Next Action
    - Audio event params (Stretch, Grains, etc.)
    - Expressions (Volume, Pan, Pitch)

    Connects to ClipContextService.active_slot_changed for selection tracking.
    """

    def __init__(
        self,
        project: 'ProjectService',
        clip_context: Optional['ClipContextService'] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._project = project
        self._clip_context = clip_context
        self._current_clip_id: str = ""
        self._current_scene_idx: int | None = None
        self._current_track_id: str = ""
        self._updating = False  # guard against signal loops

        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._build_ui()
        self._wire_signals()

    # ═══════════════════════════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Allow horizontal scrolling if the user shrinks the inspector very small.
        # (Primary UX is to resize the inspector via splitter.)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumWidth(0)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        root.addWidget(scroll, 1)

        content = QWidget()
        self._lay = QVBoxLayout(content)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(2)
        scroll.setWidget(content)

        # ── Section: ZELLE ──
        self._lay.addWidget(_SectionHeader("ZELLE"))

        self.lbl_stopp_aufnahme = QCheckBox("Stopp/Aufnahmeschalter")
        self.lbl_stopp_aufnahme.setStyleSheet("QCheckBox { color: #BBB; font-size: 10px; }")
        self._lay.addWidget(self.lbl_stopp_aufnahme)

        # ── Section: LAUNCHER-CLIP ──
        self._lay.addWidget(_SectionHeader("LAUNCHER-CLIP"))

        
        # Clip name + preview (Bitwig-style small play button)
        clip_row = QHBoxLayout()
        clip_row.setContentsMargins(0, 0, 0, 0)
        clip_row.setSpacing(4)

        self.lbl_clip_name = QLabel("—")
        self.lbl_clip_name.setStyleSheet(
            "QLabel { color: #FFF; font-size: 11px; font-weight: bold; padding: 2px; }"
        )
        clip_row.addWidget(self.lbl_clip_name, 1)

        self.btn_preview = QToolButton()
        self.btn_preview.setText("▶")
        self.btn_preview.setAutoRaise(True)
        self.btn_preview.setFixedSize(22, 22)
        self.btn_preview.setToolTip("Clip abspielen (Preview)")
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        clip_row.addWidget(self.btn_preview)

        self._lay.addLayout(clip_row)

        self.color_pad = ColorPadWidget()
        self._lay.addWidget(self.color_pad)

        # Takt (Time signature)
        self.cmb_takt = QComboBox()
        self.cmb_takt.addItems(["4/4", "3/4", "6/8", "5/4", "7/8", "2/4"])
        self._lay.addWidget(_ParamRow("Takt", self.cmb_takt))

        # Start position
        self.lbl_start = QLabel("1.1.1.00")
        self.lbl_start.setStyleSheet("QLabel { color: #FF8C00; font-size: 10px; font-weight: bold; }")
        self._lay.addWidget(_ParamRow("Start", self.lbl_start))

        # Stop position
        self.lbl_stop = QLabel("1.2.1.00")
        self.lbl_stop.setStyleSheet("QLabel { color: #BBB; font-size: 10px; }")
        self._lay.addWidget(_ParamRow("Stopp", self.lbl_stop))

        # ── Loop section (Bitwig-Style) ──
        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setChecked(True)
        self.chk_loop.setStyleSheet("QCheckBox { color: #FF8C00; font-size: 10px; font-weight: bold; }")
        self._lay.addWidget(self.chk_loop)

        # v0.0.20.591: Editable loop start (Bitwig: loop region within clip)
        self.spn_loop_start = QDoubleSpinBox()
        self.spn_loop_start.setRange(0.0, 999.0)
        self.spn_loop_start.setDecimals(1)
        self.spn_loop_start.setValue(0.0)
        self.spn_loop_start.setSuffix(" beats")
        self.spn_loop_start.setStyleSheet("QDoubleSpinBox { color: #FF8C00; }")
        self._lay.addWidget(_ParamRow("Loop Start", self.spn_loop_start))

        # v0.0.20.591: Loop length controls loop_end_beats (NOT clip length)
        self.spn_loop_length = QDoubleSpinBox()
        self.spn_loop_length.setRange(0.25, 999.0)
        self.spn_loop_length.setDecimals(1)
        self.spn_loop_length.setValue(4.0)
        self.spn_loop_length.setSuffix(" beats")
        self.spn_loop_length.setStyleSheet("QDoubleSpinBox { color: #FF8C00; }")
        self._lay.addWidget(_ParamRow("Loop Länge", self.spn_loop_length))

        # Clip total length (separate from loop)
        self.spn_clip_length = QDoubleSpinBox()
        self.spn_clip_length.setRange(0.25, 999.0)
        self.spn_clip_length.setDecimals(1)
        self.spn_clip_length.setValue(16.0)
        self.spn_clip_length.setSuffix(" beats")
        self._lay.addWidget(_ParamRow("Länge", self.spn_clip_length))

        self.spn_fade = QDoubleSpinBox()
        self.spn_fade.setRange(0.0, 10.0)
        self.spn_fade.setDecimals(2)
        self.spn_fade.setValue(0.08)
        self._lay.addWidget(_ParamRow("Fade", self.spn_fade))

        # Mute
        self.chk_mute = QCheckBox("M")
        self.chk_mute.setStyleSheet("QCheckBox { color: #BBB; font-size: 10px; }")
        self._lay.addWidget(_ParamRow("Mute", self.chk_mute))

        # ── Shuffle / Accent ──
        self.chk_shuffle = QCheckBox("Shuffle")
        self.chk_shuffle.setStyleSheet("QCheckBox { color: #FF8C00; font-size: 10px; }")
        self._lay.addWidget(self.chk_shuffle)

        self.spn_accent = QDoubleSpinBox()
        self.spn_accent.setRange(0.0, 100.0)
        self.spn_accent.setDecimals(2)
        self.spn_accent.setValue(0.0)
        self.spn_accent.setSuffix(" %")
        self._lay.addWidget(_ParamRow("Akzent", self.spn_accent))

        # ── Startwert (Seed) ──
        self.cmb_seed = QComboBox()
        self.cmb_seed.addItems(["Random", "1", "2", "3", "4", "5", "6", "7", "8"])
        self.cmb_seed.setEditable(True)
        self._lay.addWidget(_ParamRow("Startwert", self.cmb_seed))

        # ═══ QUANTIZATION: Main / ALT ═══
        self._lay.addWidget(_SectionHeader("QUANTISIERUNG"))

        # Main/ALT tabs
        quant_tabs = QHBoxLayout()
        self.btn_main_q = QPushButton("Main")
        self.btn_main_q.setCheckable(True)
        self.btn_main_q.setChecked(True)
        self.btn_main_q.setFixedHeight(22)
        self.btn_alt_q = QPushButton("ALT")
        self.btn_alt_q.setCheckable(True)
        self.btn_alt_q.setFixedHeight(22)
        quant_tabs.addWidget(self.btn_main_q)
        quant_tabs.addWidget(self.btn_alt_q)
        self._lay.addLayout(quant_tabs)

        # Start-Q (per-clip quantize)
        self.cmb_start_q = QComboBox()
        self.cmb_start_q.addItems([
            "Projekteinstellung verwenden",
            "Aus", "8 Takte", "4 Takte", "2 Takte", "1 Takt",
            "1/2 Noten", "1/4 Noten", "1/8 Noten", "1/16 Noten",
        ])
        self._lay.addWidget(_ParamRow("Start-Q", self.cmb_start_q))

        # Wiedergabe (Playback mode)
        self.cmb_playback = QComboBox()
        self.cmb_playback.addItems([
            "Projekteinstellung verwenden",
            "Trigger ab Start",
            "Legato vom Clip (oder Start)",
            "Legato vom Clip (oder Projekt)",
            "Legato vom Projekt",
        ])
        self._lay.addWidget(_ParamRow("Wiedergabe", self.cmb_playback))

        # Release action
        self.cmb_release = QComboBox()
        self.cmb_release.addItems([
            "Projekteinstellung verwenden",
            "Fortsetzen",
            "Stopp",
            "Zurück",
            "Nächste Aktion",
        ])
        self._lay.addWidget(_ParamRow("Release", self.cmb_release))

        # v0.0.20.604: Crossfade (ms) for Legato transitions
        self.spn_crossfade = QSpinBox()
        self.spn_crossfade.setRange(0, 500)
        self.spn_crossfade.setValue(10)
        self.spn_crossfade.setSuffix(" ms")
        self._lay.addWidget(_ParamRow("Crossfade", self.spn_crossfade))

        # Q auf Loop
        self.cmb_q_loop = QComboBox()
        self.cmb_q_loop.addItems(["Auf Loop quan...", "Aus"])
        self._lay.addWidget(_ParamRow("Q auf Loop", self.cmb_q_loop))

        # ═══ NÄCHSTE AKTION (Next Action) ═══
        self._lay.addWidget(_SectionHeader("NÄCHSTE AKTION"))

        self.cmb_next_action = QComboBox()
        self.cmb_next_action.addItems([
            "Stopp",
            "Zum Arrangement zurückkehren",
            "Zum zuletzt gespielten Clip zurückkehren",
            "Nächsten abspielen",
            "Vorherigen abspielen",
            "Ersten abspielen",
            "Letzten abspielen",
            "Zufälligen abspielen",
            "Anderen abspielen",
            "Round-robin",
            "Ersten im aktuellen Block abspielen",
            "Letzten im aktuellen Block abspielen",
            "Zufälligen im aktuellen Block abspielen",
        ])
        self._lay.addWidget(self.cmb_next_action)

        # Repeat count
        repeat_row = QHBoxLayout()
        self.spn_repeat = QSpinBox()
        self.spn_repeat.setRange(1, 999)
        self.spn_repeat.setValue(1)
        self.spn_repeat.setPrefix("x")
        repeat_row.addWidget(self.spn_repeat)
        self.lbl_repeat_pos = QLabel("0.1.0.00")
        self.lbl_repeat_pos.setStyleSheet("QLabel { color: #BBB; font-size: 10px; }")
        repeat_row.addWidget(self.lbl_repeat_pos)
        self._lay.addLayout(repeat_row)

        # v0.0.20.604: Action B (Ableton-style dual follow actions)
        self.cmb_next_action_b = QComboBox()
        self.cmb_next_action_b.addItems([
            "Stopp", "Nächsten abspielen", "Vorherigen abspielen",
            "Ersten abspielen", "Letzten abspielen", "Zufälligen abspielen",
            "Anderen abspielen", "Round-robin",
        ])
        self._lay.addWidget(_ParamRow("Aktion B", self.cmb_next_action_b))

        # Probability slider (% for Action A)
        prob_row = QHBoxLayout()
        self.spn_probability = QSpinBox()
        self.spn_probability.setRange(0, 100)
        self.spn_probability.setValue(100)
        self.spn_probability.setSuffix("% A")
        prob_row.addWidget(self.spn_probability)
        lbl_prob = QLabel("← A | B →")
        lbl_prob.setStyleSheet("color: #888; font-size: 9px;")
        prob_row.addWidget(lbl_prob)
        self._lay.addLayout(prob_row)

        # ═══ AUDIO-EVENT (shown for audio clips) ═══
        self._lay.addWidget(_SectionHeader("AUDIO-EVENT"))

        self.lbl_event_length = QLabel("0.0.1.12")
        self.lbl_event_length.setStyleSheet("QLabel { color: #BBB; font-size: 10px; }")
        self._lay.addWidget(_ParamRow("Länge", self.lbl_event_length))

        self.chk_event_mute = QCheckBox("M")
        self._lay.addWidget(_ParamRow("Mute", self.chk_event_mute))

        # Audio Events / Comping buttons
        btn_row = QHBoxLayout()
        self.btn_audio_events = QPushButton("Audio Events")
        self.btn_audio_events.setStyleSheet(
            "QPushButton { background: #E04040; color: white; border-radius: 3px; "
            "font-size: 10px; padding: 3px 8px; }"
        )
        self.btn_comping = QPushButton("Comping")
        self.btn_comping.setStyleSheet(
            "QPushButton { background: #555; color: #BBB; border-radius: 3px; "
            "font-size: 10px; padding: 3px 8px; }"
        )
        btn_row.addWidget(self.btn_audio_events)
        btn_row.addWidget(self.btn_comping)
        self._lay.addLayout(btn_row)

        # Stretch / Onsets buttons
        stretch_row = QHBoxLayout()
        self.btn_stretch = QPushButton("Stretch")
        self.btn_stretch.setStyleSheet(
            "QPushButton { background: #555; color: #BBB; border-radius: 3px; "
            "font-size: 10px; padding: 3px 8px; }"
        )
        self.btn_onsets = QPushButton("Onsets")
        self.btn_onsets.setStyleSheet(
            "QPushButton { background: #555; color: #BBB; border-radius: 3px; "
            "font-size: 10px; padding: 3px 8px; }"
        )
        stretch_row.addWidget(self.btn_stretch)
        stretch_row.addWidget(self.btn_onsets)
        self._lay.addLayout(stretch_row)

        # Modus (Stretch mode)
        self.cmb_modus = QComboBox()
        self.cmb_modus.addItems(["Stretch", "Repitch", "Slice", "Raw"])
        self._lay.addWidget(_ParamRow("Modus", self.cmb_modus))

        # Tempo
        self.spn_tempo = QDoubleSpinBox()
        self.spn_tempo.setRange(20.0, 999.0)
        self.spn_tempo.setDecimals(2)
        self.spn_tempo.setValue(110.0)
        self._lay.addWidget(_ParamRow("Tempo", self.spn_tempo))

        # Param buttons row (Gain/Pan/Pitch/Formant)
        param_btn_row = QHBoxLayout()
        for name in ["Gain", "Pan", "Pitch", "Formant"]:
            btn = QPushButton(name)
            btn.setFixedHeight(20)
            btn.setStyleSheet(
                "QPushButton { background: #444; color: #BBB; border-radius: 2px; "
                "font-size: 9px; padding: 2px 4px; }"
            )
            param_btn_row.addWidget(btn)
        self._lay.addLayout(param_btn_row)

        # ═══ EXPRESSIONS ═══
        self._lay.addWidget(_SectionHeader("EXPRESSIONS"))

        # Lautstärke (Volume)
        vol_row = QHBoxLayout()
        vol_row.setSpacing(4)
        self.spn_volume_db = QDoubleSpinBox()
        self.spn_volume_db.setRange(-60.0, 12.0)
        self.spn_volume_db.setDecimals(1)
        self.spn_volume_db.setValue(0.0)
        self.spn_volume_db.setSuffix(" dB")
        vol_row.addWidget(QLabel("Lautstärke"))
        vol_row.addWidget(self.spn_volume_db, 1)
        # +/- buttons
        for delta, label in [(-6, "-6"), (-1, "-1"), (1, "+1"), (6, "+6")]:
            btn = QPushButton(label)
            btn.setFixedSize(28, 20)
            btn.setStyleSheet(
                "QPushButton { background: #555; color: #FF8C00; border-radius: 2px; "
                "font-size: 9px; }"
            )
            btn.clicked.connect(lambda _, d=delta: self._adjust_volume(d))
            vol_row.addWidget(btn)
        self._lay.addLayout(vol_row)

        # Panorama
        pan_row = QHBoxLayout()
        pan_row.setSpacing(4)
        self.spn_pan = QDoubleSpinBox()
        self.spn_pan.setRange(-100.0, 100.0)
        self.spn_pan.setDecimals(2)
        self.spn_pan.setValue(0.0)
        self.spn_pan.setSuffix(" %")
        pan_row.addWidget(QLabel("Panorama"))
        pan_row.addWidget(self.spn_pan, 1)
        self._lay.addLayout(pan_row)

        # Tonhöhe (Pitch)
        pitch_row = QHBoxLayout()
        pitch_row.setSpacing(4)
        self.spn_pitch = QDoubleSpinBox()
        self.spn_pitch.setRange(-48.0, 48.0)
        self.spn_pitch.setDecimals(2)
        self.spn_pitch.setValue(0.0)
        pitch_row.addWidget(QLabel("Tonhöhe"))
        pitch_row.addWidget(self.spn_pitch, 1)
        # +/- semitone buttons
        for delta, label in [(-12, "-12"), (-1, "-1"), (1, "+1"), (12, "+12")]:
            btn = QPushButton(label)
            btn.setFixedSize(28, 20)
            btn.setStyleSheet(
                "QPushButton { background: #555; color: #FF8C00; border-radius: 2px; "
                "font-size: 9px; }"
            )
            btn.clicked.connect(lambda _, d=delta: self._adjust_pitch(d))
            pitch_row.addWidget(btn)
        self._lay.addLayout(pitch_row)

        # ── Create auto-fades checkbox ──
        self.chk_auto_fades = QCheckBox("Create auto-fades")
        self.chk_auto_fades.setChecked(True)
        self.chk_auto_fades.setStyleSheet("QCheckBox { color: #80D040; font-size: 10px; }")
        self._lay.addWidget(self.chk_auto_fades)

        # ── Stretch ──
        self._lay.addStretch(1)

        # ── Empty state label ──
        self.lbl_empty = QLabel("Kein Clip ausgewählt")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("QLabel { color: #666; font-size: 12px; padding: 40px; }")

    # ═══════════════════════════════════════════════════════════
    #  WIRING
    # ═══════════════════════════════════════════════════════════

    def _wire_signals(self) -> None:
        # ClipContext selection
        if self._clip_context:
            self._clip_context.active_slot_changed.connect(self._on_slot_changed)

        # Project updates
        try:
            self._project.project_updated.connect(self._refresh_from_model)
        except Exception:
            pass

        # Main/ALT toggle
        self.btn_main_q.clicked.connect(lambda: self._set_quant_tab("Main"))
        self.btn_alt_q.clicked.connect(lambda: self._set_quant_tab("ALT"))

        # Edit signals → write to model
        self.color_pad.color_changed.connect(self._on_color_changed)
        self.chk_mute.toggled.connect(self._on_mute_changed)
        self.chk_loop.toggled.connect(self._on_loop_changed)
        self.spn_loop_start.valueChanged.connect(self._on_loop_start_changed)
        self.spn_loop_length.valueChanged.connect(self._on_loop_length_changed)
        self.spn_clip_length.valueChanged.connect(self._on_clip_length_changed)
        self.spn_fade.valueChanged.connect(self._on_fade_changed)
        self.cmb_start_q.currentTextChanged.connect(self._on_start_q_changed)
        self.cmb_playback.currentTextChanged.connect(self._on_playback_changed)
        self.cmb_release.currentTextChanged.connect(self._on_release_changed)
        self.cmb_next_action.currentTextChanged.connect(self._on_next_action_changed)
        self.spn_repeat.valueChanged.connect(self._on_repeat_changed)
        # v0.0.20.604: New controls
        self.cmb_next_action_b.currentTextChanged.connect(lambda t: self._write_clip_attr('launcher_next_action_b', t))
        self.spn_probability.valueChanged.connect(lambda v: self._write_clip_attr('launcher_next_action_probability', int(v)))
        self.spn_crossfade.valueChanged.connect(lambda v: self._write_clip_attr('launcher_crossfade_ms', float(v)))
        self.spn_volume_db.valueChanged.connect(self._on_volume_changed)
        self.spn_pan.valueChanged.connect(self._on_pan_changed)
        self.spn_pitch.valueChanged.connect(self._on_pitch_changed)
        self.spn_accent.valueChanged.connect(self._on_accent_changed)
        self.cmb_seed.currentTextChanged.connect(self._on_seed_changed)
        self.chk_shuffle.toggled.connect(self._on_shuffle_changed)
        self.cmb_q_loop.currentTextChanged.connect(self._on_q_loop_changed)
        self.spn_tempo.valueChanged.connect(self._on_tempo_changed)

    # ═══════════════════════════════════════════════════════════
    #  SLOT SELECTION
    # ═══════════════════════════════════════════════════════════

    def _on_slot_changed(self, scene_idx: int, track_id: str, clip_id: str) -> None:
        self._current_scene_idx = int(scene_idx) if scene_idx is not None else None
        self._current_track_id = str(track_id)
        self._current_clip_id = str(clip_id)
        self._refresh_from_model()

    def set_clip(self, clip_id: str) -> None:
        """Programmatic clip selection (e.g. from ClipLauncherPanel click)."""
        self._current_clip_id = str(clip_id)
        self._refresh_from_model()

    def _on_preview_clicked(self) -> None:
        """Preview the currently selected launcher slot (safe, optional).

        Uses ProjectService.cliplauncher_launch_immediate so it cannot break transport logic.
        """
        if not self._current_clip_id:
            return
        if self._current_scene_idx is None or not self._current_track_id:
            return
        slot_key = f"scene:{int(self._current_scene_idx)}:track:{self._current_track_id}"
        try:
            self._project.cliplauncher_launch_immediate(slot_key)
        except Exception:
            pass

    def _get_clip(self) -> Optional['Clip']:
        if not self._current_clip_id:
            return None
        try:
            return next(
                (c for c in self._project.ctx.project.clips
                 if str(c.id) == self._current_clip_id),
                None,
            )
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════
    #  REFRESH FROM MODEL
    # ═══════════════════════════════════════════════════════════

    def _refresh_from_model(self) -> None:
        clip = self._get_clip()
        if clip is None:
            self.lbl_clip_name.setText("—")
            return

        self._updating = True
        try:
            self.lbl_clip_name.setText(str(getattr(clip, 'label', '') or 'Clip'))
            self.color_pad.set_color_index(int(getattr(clip, 'launcher_color', 0) or 0))

            # Time sig
            ts = str(getattr(self._project.ctx.project, 'time_signature', '4/4') or '4/4')
            idx = self.cmb_takt.findText(ts)
            if idx >= 0:
                self.cmb_takt.setCurrentIndex(idx)

            # Start/Stop/Loop
            start_b = float(getattr(clip, 'start_beats', 0.0) or 0.0)
            length_b = float(getattr(clip, 'length_beats', 4.0) or 4.0)
            self.lbl_start.setText(self._beats_to_bbs(start_b))
            self.lbl_stop.setText(self._beats_to_bbs(start_b + length_b))

            loop_s = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
            loop_e = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
            has_loop = loop_e > loop_s + 0.01
            self.chk_loop.setChecked(has_loop)

            # v0.0.20.591: Editable loop start + loop length (separate from clip length)
            self.spn_loop_start.setValue(loop_s)
            loop_len = max(0.25, loop_e - loop_s) if has_loop else length_b
            self.spn_loop_length.setValue(loop_len)
            self.spn_clip_length.setValue(length_b)

            # Enable/disable loop spinboxes based on checkbox
            self.spn_loop_start.setEnabled(has_loop)
            self.spn_loop_length.setEnabled(has_loop)

            self.spn_fade.setValue(float(getattr(clip, 'fade_in_beats', 0.08) or 0.08))
            self.chk_mute.setChecked(bool(getattr(clip, 'muted', False)))

            # Shuffle/Accent
            self.spn_accent.setValue(float(getattr(clip, 'launcher_accent', 0.0) or 0.0) * 100.0)
            self.chk_shuffle.setChecked(float(getattr(clip, 'launcher_shuffle', 0.0) or 0.0) > 0.01)

            # Seed
            seed = str(getattr(clip, 'launcher_seed', 'Random') or 'Random')
            self.cmb_seed.setCurrentText(seed)

            # Quantization
            sq = str(getattr(clip, 'launcher_start_quantize', 'Project') or 'Project')
            self._set_combo_safe(self.cmb_start_q, self._q_to_display(sq))

            pb = str(getattr(clip, 'launcher_playback_mode', 'Trigger ab Start') or 'Trigger ab Start')
            self._set_combo_safe(self.cmb_playback, pb if pb != 'Project' else 'Projekteinstellung verwenden')

            rel = str(getattr(clip, 'launcher_release_action', 'Stopp') or 'Stopp')
            self._set_combo_safe(self.cmb_release, rel if rel != 'Project' else 'Projekteinstellung verwenden')

            q_loop = bool(getattr(clip, 'launcher_q_on_loop', True))
            self.cmb_q_loop.setCurrentIndex(0 if q_loop else 1)

            # Next action
            na = str(getattr(clip, 'launcher_next_action', 'Stopp') or 'Stopp')
            self._set_combo_safe(self.cmb_next_action, na)
            self.spn_repeat.setValue(int(getattr(clip, 'launcher_next_action_count', 1) or 1))
            # v0.0.20.604: Action B + Probability + Crossfade
            na_b = str(getattr(clip, 'launcher_next_action_b', 'Stopp') or 'Stopp')
            self._set_combo_safe(self.cmb_next_action_b, na_b)
            self.spn_probability.setValue(int(getattr(clip, 'launcher_next_action_probability', 100) or 100))
            self.spn_crossfade.setValue(int(getattr(clip, 'launcher_crossfade_ms', 10) or 10))

            # Audio params
            self.spn_volume_db.setValue(self._gain_to_db(float(getattr(clip, 'gain', 1.0) or 1.0)))
            self.spn_pan.setValue(float(getattr(clip, 'pan', 0.0) or 0.0) * 100.0)
            self.spn_pitch.setValue(float(getattr(clip, 'pitch', 0.0) or 0.0))

            # Tempo
            src_bpm = getattr(clip, 'source_bpm', None)
            if src_bpm and float(src_bpm) > 0:
                self.spn_tempo.setValue(float(src_bpm))
            else:
                self.spn_tempo.setValue(float(getattr(self._project.ctx.project, 'bpm', 120.0) or 120.0))

            # Event length
            events = list(getattr(clip, 'audio_events', []) or [])
            if events:
                ev = events[0]
                el = float(getattr(ev, 'length_beats', 0.0) or 0.0)
                self.lbl_event_length.setText(self._beats_to_bbs(el))
        finally:
            self._updating = False

    # ═══════════════════════════════════════════════════════════
    #  EDIT HANDLERS (write to model)
    # ═══════════════════════════════════════════════════════════

    def _write_clip_attr(self, attr: str, value) -> None:
        if self._updating:
            return
        clip = self._get_clip()
        if clip is None:
            return
        try:
            setattr(clip, attr, value)
            self._project.project_updated.emit()
        except Exception as e:
            log.warning("Inspector write error: %s", e)

    def _on_color_changed(self, idx: int) -> None:
        self._write_clip_attr('launcher_color', int(idx))

    def _on_mute_changed(self, checked: bool) -> None:
        self._write_clip_attr('muted', bool(checked))

    def _on_loop_changed(self, checked: bool) -> None:
        clip = self._get_clip()
        if clip is None or self._updating:
            return
        if checked:
            # Enable loop: default to full clip length
            length = float(getattr(clip, 'length_beats', 4.0) or 4.0)
            clip.loop_start_beats = 0.0
            clip.loop_end_beats = max(0.25, length)
        else:
            # Disable loop
            clip.loop_start_beats = 0.0
            clip.loop_end_beats = 0.0
        # v0.0.20.591: Enable/disable loop spinboxes
        try:
            self.spn_loop_start.setEnabled(checked)
            self.spn_loop_length.setEnabled(checked)
        except Exception:
            pass
        self._project.project_updated.emit()

    def _on_loop_start_changed(self, val: float) -> None:
        """v0.0.20.591: Set loop start position (Bitwig-style loop region)."""
        clip = self._get_clip()
        if clip is None or self._updating:
            return
        clip.loop_start_beats = max(0.0, float(val))
        # Keep loop end at least 0.25 beats after start
        if clip.loop_end_beats <= clip.loop_start_beats + 0.01:
            clip.loop_end_beats = clip.loop_start_beats + max(0.25, float(self.spn_loop_length.value()))
        self._project.project_updated.emit()

    def _on_loop_length_changed(self, val: float) -> None:
        """v0.0.20.591: Set loop length → writes loop_end_beats (NOT clip length)."""
        clip = self._get_clip()
        if clip is None or self._updating:
            return
        loop_start = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
        clip.loop_end_beats = loop_start + max(0.25, float(val))
        self._project.project_updated.emit()

    def _on_clip_length_changed(self, val: float) -> None:
        """v0.0.20.591: Set clip total length (separate from loop region)."""
        self._write_clip_attr('length_beats', max(0.25, float(val)))

    def _on_fade_changed(self, val: float) -> None:
        self._write_clip_attr('fade_in_beats', float(val))
        self._write_clip_attr('fade_out_beats', float(val))

    def _on_start_q_changed(self, text: str) -> None:
        self._write_clip_attr('launcher_start_quantize', self._display_to_q(text))

    def _on_playback_changed(self, text: str) -> None:
        val = text if text != "Projekteinstellung verwenden" else "Project"
        self._write_clip_attr('launcher_playback_mode', val)

    def _on_release_changed(self, text: str) -> None:
        val = text if text != "Projekteinstellung verwenden" else "Project"
        self._write_clip_attr('launcher_release_action', val)

    def _on_q_loop_changed(self, text: str) -> None:
        self._write_clip_attr('launcher_q_on_loop', text != "Aus")

    def _on_next_action_changed(self, text: str) -> None:
        self._write_clip_attr('launcher_next_action', text)

    def _on_repeat_changed(self, val: int) -> None:
        self._write_clip_attr('launcher_next_action_count', int(val))

    def _on_volume_changed(self, db: float) -> None:
        self._write_clip_attr('gain', self._db_to_gain(float(db)))

    def _on_pan_changed(self, pct: float) -> None:
        self._write_clip_attr('pan', float(pct) / 100.0)

    def _on_pitch_changed(self, st: float) -> None:
        self._write_clip_attr('pitch', float(st))

    def _on_accent_changed(self, pct: float) -> None:
        self._write_clip_attr('launcher_accent', float(pct) / 100.0)

    def _on_seed_changed(self, text: str) -> None:
        self._write_clip_attr('launcher_seed', str(text))

    def _on_shuffle_changed(self, checked: bool) -> None:
        self._write_clip_attr('launcher_shuffle', 0.5 if checked else 0.0)

    def _on_tempo_changed(self, val: float) -> None:
        self._write_clip_attr('source_bpm', float(val))

    def _adjust_volume(self, delta_db: float) -> None:
        if self._updating:
            return
        self.spn_volume_db.setValue(self.spn_volume_db.value() + delta_db)

    def _adjust_pitch(self, delta_st: float) -> None:
        if self._updating:
            return
        self.spn_pitch.setValue(self.spn_pitch.value() + delta_st)

    # ═══════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════

    def _set_quant_tab(self, tab: str) -> None:
        is_main = (tab == "Main")
        self.btn_main_q.setChecked(is_main)
        self.btn_alt_q.setChecked(not is_main)
        # TODO: switch displayed values between Main/ALT

    def _set_combo_safe(self, combo: QComboBox, text: str) -> None:
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _beats_to_bbs(self, beats: float) -> str:
        """Convert beats to Bitwig-style Bar.Beat.Sub.Tick display."""
        try:
            ts = str(getattr(self._project.ctx.project, 'time_signature', '4/4') or '4/4')
            num_s, den_s = ts.split('/')
            num = int(num_s)
            den = int(den_s)
            bpb = float(num) * (4.0 / float(den))
        except Exception:
            bpb = 4.0

        bar = int(beats / bpb) + 1
        beat_in_bar = int(beats % bpb) + 1
        sub = int((beats % 1.0) * 100)
        return f"{bar}.{beat_in_bar}.{sub:02d}"

    @staticmethod
    def _gain_to_db(gain: float) -> float:
        if gain <= 0.0:
            return -60.0
        import math
        return 20.0 * math.log10(float(gain))

    @staticmethod
    def _db_to_gain(db: float) -> float:
        if db <= -60.0:
            return 0.0
        return 10.0 ** (float(db) / 20.0)

    @staticmethod
    def _q_to_display(q: str) -> str:
        mapping = {
            "Project": "Projekteinstellung verwenden",
            "Off": "Aus",
            "8 Bar": "8 Takte", "4 Bar": "4 Takte", "2 Bar": "2 Takte",
            "1 Bar": "1 Takt",
            "1/2": "1/2 Noten", "1/4": "1/4 Noten",
            "1/8": "1/8 Noten", "1/16": "1/16 Noten",
        }
        return mapping.get(q, q)

    @staticmethod
    def _display_to_q(display: str) -> str:
        mapping = {
            "Projekteinstellung verwenden": "Project",
            "Aus": "Off",
            "8 Takte": "8 Bar", "4 Takte": "4 Bar", "2 Takte": "2 Bar",
            "1 Takt": "1 Bar",
            "1/2 Noten": "1/2", "1/4 Noten": "1/4",
            "1/8 Noten": "1/8", "1/16 Noten": "1/16",
        }
        return mapping.get(display, display)
