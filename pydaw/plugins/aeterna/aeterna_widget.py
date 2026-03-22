# -*- coding: utf-8 -*-
"""AETERNA widget — safe browser/device integration for the new flagship synth."""
from __future__ import annotations

import hashlib
import random
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QMimeData, QPoint, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QDrag, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QSizePolicy, QPlainTextEdit,
    QToolButton, QMenu, QSpinBox, QDoubleSpinBox, QMessageBox, QFileDialog, QSlider
)

FORMULA_TOKEN_MIME = "application/x-aeterna-formula-token"
MOD_SOURCE_TOKEN_MIME = "application/x-aeterna-mod-source"

MOD_SOURCE_LABELS = {
    "off": "Off",
    "lfo1": "LFO1",
    "lfo2": "LFO2",
    "mseg": "MSEG",
    "chaos": "Chaos",
    "env": "ENV",
    "vel": "VEL",
}

MOD_SOURCE_HINTS = {
    "lfo1": "zyklische Bewegung für Vibrato/Sweeps",
    "lfo2": "langsamere Schwebung und Atem",
    "mseg": "gezeichnete Form für präzise Bewegungen",
    "chaos": "organische kontrollierte Unruhe",
    "env": "anschlagsnahe Kontur / Hüllkurven-Impuls",
    "vel": "spielabhängig über Anschlagstärke",
}
FORMULA_HELP_TOKENS = (
    ("LFO1", "lfo1"),
    ("LFO2", "lfo2"),
    ("MSEG", "mseg"),
    ("CHAOS", "chaos_src"),
    ("ENV", "env"),
    ("VEL", "$VEL"),
    ("NOTE", "$NOTE"),
    ("T_REM", "$T_REM"),
    ("GLITCH", "$GLITCH"),
    ("rand(t)", "rand(t)"),
)
FORMULA_HELP_SNIPPETS = (
    ("morph x lfo1", "(1.0 + 0.35*lfo1)"),
    ("fm by lfo2", "sin(phase*(1.0 + 0.25*lfo2))"),
    ("shape by mseg", "sin(phase + 0.6*mseg)"),
    ("chaos bend", "tanh(phase + chaos_src)"),
    ("env carve", "(0.78 + 0.22*env) * sin(phase*(1.0 + 0.14*lfo1))"),
    ("brown walk", "0.78*sin(phase + 0.12*chaos_src) + 0.16*cos(phase*0.5 + d)"),
    ("coherent cloud", "0.74*sin(phase + 0.18*mseg) + 0.14*cos(note_hz*0.0005 + lfo2) + 0.08*chaos_src"),
    ("logistic glass", "tanh(sin(phase*(1.0 + 0.16*chaos_src)) + 0.18*cos(phase*0.5 + env))"),
    ("tent lattice", "0.68*sin(phase + 0.10*mseg) + 0.18*abs(sin(phase*0.5 + chaos_src)) + 0.10*cos(note_hz*0.0003 + d)"),
    ("pink bloom", "(0.82 + 0.12*env) * (0.66*sin(phase + 0.08*lfo2) + 0.18*cos(phase*0.25 + motion) + 0.10*mseg)"),
    ("lorenz breath", "tanh(0.72*sin(phase + 0.16*lfo1) + 0.22*cos(phase*0.5 + chaos_src) + 0.10*env)"),
    ("sample hold veil", "0.70*sin(phase + 0.14*mseg) + 0.20*tanh(chaos_src + 0.10*lfo2) + 0.08*cos(phase*2.0 + d)"),
    ("harmonic lattice", "0.60*sin(phase) + 0.22*sin(phase*2.0 + 0.10*lfo1) + 0.12*cos(phase*3.0 + 0.08*mseg)"),
    ("env swell", "(0.52 + 0.48*env) * cos(note_hz*0.00045 + mseg) + 0.12*lfo2"),
    ("velocity glass", "(0.35 + 0.65*vel) * sin(note_hz*0.0008 + 0.6*lfo2) + 0.10*env"),
    ("coherent veil", "0.48*cos(note_hz*0.00035 + mseg) + 0.22*env + 0.12*chaos_src"),
    ("modal drift", "(0.84 + 0.10*env) * (sin(phase + 0.10*lfo2) + 0.18*cos(note_hz*0.0004 + mseg) + 0.08*chaos_src)"),
    ("vel-note-rem", "exp(-t * $VEL) * sin($NOTE * log(1 + 1/(abs($T_REM) + 0.0001)) * t)"),
    ("glitch rand", "exp(-t * $VEL) * sin($NOTE * log(1 + 1/(abs($T_REM) + 0.0001)) * t) + (rand(t) * $GLITCH)"),
)
FORMULA_ONBOARDING_PRESETS = (
    ("Warm Start", "Sanfter Einstieg mit leichter LFO-Bewegung", "sin(phase*(1.0 + 0.18*lfo1))"),
    ("Sakral", "Ruhiger sakraler Raum mit MSEG-Atmung", "(sin(phase*(1.0+0.10*mseg)) + 0.24*sin(phase*0.5 + lfo2)) * (0.86 + 0.12*env)"),
    ("Organisch", "Weiche lebendige Bewegung ohne Kratzen", "(0.82*sin(phase + 0.18*mseg) + 0.16*sin(phase*2.0 + 0.08*lfo1)) * (0.90 + 0.08*env)"),
    ("Drone", "Lang getragener klarer Grundton mit wenig Rauheit", "(0.88*sin(phase + 0.06*lfo2) + 0.12*sin(phase*0.5 + 0.10*mseg)) * (0.94 + 0.05*env)"),
    ("Chaos", "Etwas lebendiger mit Chaos-Quelle und Web-Gefühl", "tanh(sin(phase*(1.0 + 0.22*lfo1)) + 0.35*chaos_src + 0.16*mseg)"),
    ("Harmonic", "Mehr Oberton-Gitter statt reiner Phase", "0.60*sin(phase) + 0.22*sin(phase*2.0 + 0.10*lfo1) + 0.12*cos(phase*3.0 + 0.08*mseg)"),
    ("Pink Bloom", "Luftige weichere Wolke mit env/lfo/motion", "(0.82 + 0.12*env) * (0.66*sin(phase + 0.08*lfo2) + 0.18*cos(phase*0.25 + motion) + 0.10*mseg)"),
    ("Glitch", "Nur lokal, für experimentelle Textur", "exp(-t * $VEL) * sin($NOTE * log(1 + 1/(abs($T_REM) + 0.0001)) * t) + (rand(t) * $GLITCH)"),
)

WEB_TEMPLATE_PRESETS = (
    ("Langsam", "Ruhige sakrale Bewegung mit viel Raum", {"mod1_source": "lfo2", "mod1_target": "space", "mod1_amount": 18, "mod2_source": "mseg", "mod2_target": "cathedral", "mod2_amount": 24, "lfo1_rate": 14, "lfo2_rate": 8, "mseg_rate": 18}),
    ("Lebendig", "Etwas mehr Atem und hörbare Bewegung", {"mod1_source": "lfo1", "mod1_target": "motion", "mod1_amount": 28, "mod2_source": "mseg", "mod2_target": "tone", "mod2_amount": 18, "lfo1_rate": 26, "lfo2_rate": 12, "mseg_rate": 22}),
    ("Organisch", "Weiche organische Schwebung ohne Härte", {"mod1_source": "chaos", "mod1_target": "drift", "mod1_amount": 16, "mod2_source": "lfo2", "mod2_target": "morph", "mod2_amount": 20, "lfo1_rate": 18, "lfo2_rate": 10, "mseg_rate": 20}),
    ("Sakral", "Kathedraler Atem für klare Bach-nahe Flächen", {"mod1_source": "mseg", "mod1_target": "cathedral", "mod1_amount": 30, "mod2_source": "lfo2", "mod2_target": "space", "mod2_amount": 22, "lfo1_rate": 16, "lfo2_rate": 9, "mseg_rate": 24}),
)

WEB_TEMPLATE_INTENSITY_FACTORS = {
    "sanft": 0.72,
    "mittel": 1.00,
    "präsent": 1.28,
}

WEB_TEMPLATE_BASELINE = {
    "mod1_source": "off",
    "mod1_target": "off",
    "mod2_source": "off",
    "mod2_target": "off",
    "mod1_amount": 20,
    "mod2_amount": 22,
    "lfo1_rate": 22,
    "lfo2_rate": 10,
    "mseg_rate": 24,
}

FAMILY_TONES = {
    "overview": {"accent": "#86b7ff", "bg": "rgba(134,183,255,0.14)", "border": "rgba(134,183,255,0.30)"},
    "core": {"accent": "#7fb3ff", "bg": "rgba(127,179,255,0.14)", "border": "rgba(127,179,255,0.30)"},
    "space": {"accent": "#8fe388", "bg": "rgba(143,227,136,0.14)", "border": "rgba(143,227,136,0.30)"},
    "mod": {"accent": "#ffd27f", "bg": "rgba(255,210,127,0.14)", "border": "rgba(255,210,127,0.30)"},
    "flow": {"accent": "#9bb0d6", "bg": "rgba(155,176,214,0.13)", "border": "rgba(155,176,214,0.28)"},
    "future": {"accent": "#a2adc2", "bg": "rgba(162,173,194,0.12)", "border": "rgba(162,173,194,0.24)"},
    "filter": {"accent": "#f5be63", "bg": "rgba(245,190,99,0.15)", "border": "rgba(245,190,99,0.32)"},
    "voice": {"accent": "#7fd6ff", "bg": "rgba(127,214,255,0.15)", "border": "rgba(127,214,255,0.32)"},
    "aeg": {"accent": "#77e0c0", "bg": "rgba(119,224,192,0.15)", "border": "rgba(119,224,192,0.30)"},
    "feg": {"accent": "#c596ff", "bg": "rgba(197,150,255,0.16)", "border": "rgba(197,150,255,0.32)"},
    "layer": {"accent": "#8de3ba", "bg": "rgba(141,227,186,0.15)", "border": "rgba(141,227,186,0.30)"},
    "noise": {"accent": "#ff9acb", "bg": "rgba(255,154,203,0.15)", "border": "rgba(255,154,203,0.30)"},
    "timbre": {"accent": "#ffb37f", "bg": "rgba(255,179,127,0.16)", "border": "rgba(255,179,127,0.30)"},
    "drive": {"accent": "#ff7f7f", "bg": "rgba(255,127,127,0.16)", "border": "rgba(255,127,127,0.30)"},
}


AETERNA_AUTOMATION_READY = {
    "morph": {"group": "Klang", "hint": "große Klang-Sweeps und Formwechsel"},
    "tone": {"group": "Klang", "hint": "hell ↔ dunkel musikalisch formen"},
    "gain": {"group": "Klang", "hint": "sanfte Lautheitsfahrten und Builds"},
    "release": {"group": "Klang", "hint": "getragenes Ausklingen verlängern oder straffen"},
    "space": {"group": "Raum/Bewegung", "hint": "Raumweite öffnen und schließen"},
    "motion": {"group": "Raum/Bewegung", "hint": "mehr oder weniger innere Bewegung"},
    "cathedral": {"group": "Raum/Bewegung", "hint": "sakrale Weite dosieren"},
    "drift": {"group": "Raum/Bewegung", "hint": "organisches Treiben langsam führen"},
    "chaos": {"group": "Modulation", "hint": "kontrollierte Unruhe und Lebendigkeit"},
    "lfo1_rate": {"group": "Modulation", "hint": "lebendige Pulsrate schneller oder ruhiger fahren"},
    "lfo2_rate": {"group": "Modulation", "hint": "langsame Schwebung und Atemtempo"},
    "lfo3_rate": {"group": "Modulation", "hint": "Saw-LFO Rate für Sweeps und Rampen"},
    "lfo4_rate": {"group": "Modulation", "hint": "Sample & Hold Rate für zufällige Sprünge"},
    "mseg_rate": {"group": "Modulation", "hint": "gestufte Bewegungsgeschwindigkeit formen"},
    "mod1_amount": {"group": "Web", "hint": "Tiefe von Web A fahren"},
    "mod2_amount": {"group": "Web", "hint": "Tiefe von Web B fahren"},
    "mod3_amount": {"group": "Web", "hint": "Tiefe von Web C fahren"},
    "mod4_amount": {"group": "Web", "hint": "Tiefe von Web D fahren"},
    "mod5_amount": {"group": "Web", "hint": "Tiefe von Web E fahren"},
    "mod6_amount": {"group": "Web", "hint": "Tiefe von Web F fahren"},
    "mod7_amount": {"group": "Web", "hint": "Tiefe von Web G fahren"},
    "mod8_amount": {"group": "Web", "hint": "Tiefe von Web H fahren"},
    "filter_cutoff": {"group": "Filter", "hint": "Frequenzfenster musikalisch öffnen und schließen"},
    "filter_resonance": {"group": "Filter", "hint": "Resonanz/Schärfe kontrolliert aufbauen"},
    "pan": {"group": "Voice", "hint": "stereoposition kontrolliert führen"},
    "glide": {"group": "Voice", "hint": "portamento zwischen Noten verlängern oder straffen"},
    "stereo_spread": {"group": "Voice", "hint": "stereobreite und Schwebung öffnen"},
    "aeg_attack": {"group": "AEG", "hint": "einschwingzeit des Lautstärkeverlaufs"},
    "aeg_decay": {"group": "AEG", "hint": "abfallzeit bis zum Sustain"},
    "aeg_sustain": {"group": "AEG", "hint": "haltepegel während gehaltener Noten"},
    "aeg_release": {"group": "AEG", "hint": "ausklangzeit nach Note-Off"},
    "feg_attack": {"group": "FEG", "hint": "wie schnell das Filter öffnet"},
    "feg_decay": {"group": "FEG", "hint": "abfall des Filterimpulses"},
    "feg_sustain": {"group": "FEG", "hint": "gehaltener Filterpegel"},
    "feg_release": {"group": "FEG", "hint": "Filterausklang nach Note-Off"},
    "feg_amount": {"group": "FEG", "hint": "wie stark die Filterhüllkurve auf Cutoff/Resonanz wirkt"},
    "unison_mix": {"group": "Layer", "hint": "wie breit und chorisch die zusätzlichen Stimmen beigemischt werden"},
    "unison_detune": {"group": "Layer", "hint": "wie weit die Unison-Stimmen gegeneinander verstimmt sind"},
    "sub_level": {"group": "Layer", "hint": "wie viel Fundament aus dem Sub-Oszillator dazukommt"},
    "noise_level": {"group": "Layer", "hint": "wie viel Rauschen dem Klangkörper beigemischt wird"},
    "noise_color": {"group": "Layer", "hint": "dunkles bis helles Rauschspektrum formen"},
    "pitch": {"group": "Pitch/Timbre", "hint": "globale Tonhöhe des AETERNA-Körpers musikalisch biegen"},
    "shape": {"group": "Pitch/Timbre", "hint": "Wellenform von sine/tri bis saw/square morphen"},
    "pulse_width": {"group": "Pitch/Timbre", "hint": "Pulsbreite und Vokalcharakter des Rechtecks formen"},
    "drive": {"group": "Drive/Feedback", "hint": "Sättigung und Biss des Klangkerns steuern"},
    "feedback": {"group": "Drive/Feedback", "hint": "interne Rückkopplung kontrolliert aufbauen"},
}

AETERNA_WORLD_STYLE_GROUPS = {
    "Sakral/Historisch": (
        "Gregorianik", "Kirchenmusik", "Gospel", "Barock (Bach/Fuge)", "Renaissance", "Madrigal",
        "Orgelchoral", "Motette", "Cantus Firmus", "Passion", "Hofmusik", "Schlossmusik",
    ),
    "Klassik/Film/Ambient": (
        "Klassik", "Romantik", "Impressionismus", "Minimal Music", "Neoklassik", "Filmmusik",
        "Ambient", "Drone", "Cinematic", "Meditativ", "Celesta", "Chamber Strings",
    ),
    "Folk/World": (
        "Celtic", "Nordic", "Balkan", "Klezmer", "Flamenco", "Fado", "Tango", "Bossa Nova",
        "Samba", "Mariachi", "Bluegrass", "Appalachian Folk", "Anden", "Gnawa", "Afrobeat",
        "Highlife", "Makossa", "Raga", "Qawwali", "Gamelan", "Tuvan", "Arabesque", "Persisch",
        "Anatolisch", "Balearic", "Latin", "Reggae", "Ska", "Dub", "World",
    ),
    "Jazz/Blues/Soul": (
        "Jazz", "Bebop", "Cool Jazz", "Modal Jazz", "Fusion", "Blues", "Soul", "R&B",
        "Neo Soul", "Funk", "Disco", "Gospel Soul",
    ),
    "Pop/Rock/Metal": (
        "Pop", "Synthpop", "Rock", "Prog Rock", "Punk", "Shoegaze", "Post Rock", "Grunge",
        "Metal", "Doom Metal", "Black Metal", "Death Metal", "Prog Metal", "Industrial Rock",
    ),
    "Club/Electronic": (
        "Lo-Fi", "Downtempo", "Trip-Hop", "House", "Deep House", "Techno", "Detroit Techno",
        "Trance", "Synthwave", "Electro", "Electro-Punk", "Industrial", "EBM", "Hardcore",
        "Drum & Bass", "Jungle", "Dubstep", "IDM", "Glitch", "Chiptune", "Vaporwave",
    ),
    "Dunkel/Experiment": (
        "Dark Ambient", "Noir", "Ritual", "Experimental", "Noise", "Kosmisch", "Berlin School",
        "Psychedelic", "Occult", "Frozen Choir", "Crystal Motion",
    ),
}

AETERNA_WORLD_STYLES = tuple(dict.fromkeys(
    [style for styles in AETERNA_WORLD_STYLE_GROUPS.values() for style in styles] + ["Custom"]
))

AETERNA_COMPOSER_FORMS = (
    "Motiv/Sequenz",
    "2-stimmiger Kontrapunkt",
    "Mini-Fuge (Subject/Answer)",
    "Pad/Drone + Melodie",
    "Lead + Arp + Pad",
    "Bass + Lead",
)

AETERNA_COMPOSER_CONTEXTS = (
    "Neutral",
    "Gottesdienst",
    "Hofmusik",
    "Schlossmusik",
    "Kammermusik",
    "Nacht",
    "Kathedrale",
    "Studio",
    "Club",
    "Meditation",
)

AETERNA_COMPOSER_GRID_MAP = {
    "1/8": 0.5,
    "1/16": 0.25,
    "1/32": 0.125,
}

AETERNA_COMPOSER_PHRASE_PROFILES = (
    "Sehr getragen",
    "Getragen",
    "Ausgewogen",
    "Belebt",
    "Sehr belebt",
)

AETERNA_COMPOSER_DENSITY_PROFILES = (
    "Luftig",
    "Offen",
    "Mittel",
    "Dicht",
    "Schimmernd",
)

AETERNA_COMPOSER_PHRASE_FACTORS = {
    "Sehr getragen": {"melody_keep": 0.78, "melody_len": 1.55, "bass_len": 1.45, "pad_len": 1.55, "arp_step_mul": 2.0, "lead_keep": 0.40, "density_mul": 0.86},
    "Getragen": {"melody_keep": 0.86, "melody_len": 1.28, "bass_len": 1.22, "pad_len": 1.32, "arp_step_mul": 1.5, "lead_keep": 0.52, "density_mul": 0.94},
    "Ausgewogen": {"melody_keep": 1.00, "melody_len": 1.00, "bass_len": 1.00, "pad_len": 1.00, "arp_step_mul": 1.0, "lead_keep": 0.62, "density_mul": 1.00},
    "Belebt": {"melody_keep": 1.08, "melody_len": 0.84, "bass_len": 0.88, "pad_len": 0.92, "arp_step_mul": 0.75, "lead_keep": 0.76, "density_mul": 1.08},
    "Sehr belebt": {"melody_keep": 1.18, "melody_len": 0.68, "bass_len": 0.78, "pad_len": 0.84, "arp_step_mul": 0.5, "lead_keep": 0.88, "density_mul": 1.18},
}

AETERNA_COMPOSER_DENSITY_FACTORS = {
    "Luftig": 0.72,
    "Offen": 0.88,
    "Mittel": 1.00,
    "Dicht": 1.16,
    "Schimmernd": 1.28,
}

AETERNA_ARP_PATTERNS = (
    "up", "down", "chords", "up down", "up/down2", "up/down3", "random", "flow",
    "up+in", "down+in", "blossom up", "blossom down",
    "low&up", "low&down", "hi&down", "hi&up",
)
AETERNA_ARP_RATES = ("1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64")
AETERNA_ARP_RATE_BEATS = {"1/1": 4.0, "1/2": 2.0, "1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125, "1/64": 0.0625}
AETERNA_ARP_NOTE_TYPES = (
    ("Straight", 1.0),
    ("Dotted", 1.5),
    ("Triplets", (2.0 / 3.0)),
)
AETERNA_ARP_CHORDS = {
    "Major Triad": (0, 4, 7, 12),
    "Minor Triad": (0, 3, 7, 12),
    "Sus2": (0, 2, 7, 12),
    "Sus4": (0, 5, 7, 12),
    "Power": (0, 7, 12, 19),
    "Maj7": (0, 4, 7, 11, 12),
    "Min7": (0, 3, 7, 10, 12),
}
AETERNA_ARP_DEFAULT_STEPS = tuple(
    {"transpose": 0, "skip": False, "velocity": 100, "gate": 100}
    for _ in range(16)
)


class _FormulaTokenButton(QPushButton):
    def __init__(self, label: str, token: str, insert_callback, parent=None):
        super().__init__(label, parent)
        self._token = str(token)
        self._insert_callback = insert_callback
        self._drag_start = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMinimumHeight(28)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 8:
            return super().mouseMoveEvent(event)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(FORMULA_TOKEN_MIME, self._token.encode("utf-8"))
        mime.setText(self._token)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event):
        moved = (event.position().toPoint() - self._drag_start).manhattanLength()
        if event.button() == Qt.MouseButton.LeftButton and moved < 8 and callable(self._insert_callback):
            try:
                self._insert_callback(self._token)
            except Exception:
                pass
        super().mouseReleaseEvent(event)


class _FormulaLineEdit(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.setTabChangesFocus(True)
        self.setMinimumHeight(86)
        self.setMaximumHeight(150)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, value: str) -> None:
        self.setPlainText(str(value or ""))

    def insert(self, value: str) -> None:
        self.insertPlainText(str(value or ""))

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md and (md.hasFormat(FORMULA_TOKEN_MIME) or md.hasText()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md and (md.hasFormat(FORMULA_TOKEN_MIME) or md.hasText()):
            try:
                self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            except Exception:
                pass
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        token = ""
        if md:
            if md.hasFormat(FORMULA_TOKEN_MIME):
                try:
                    token = bytes(md.data(FORMULA_TOKEN_MIME)).decode("utf-8")
                except Exception:
                    token = ""
            elif md.hasText():
                token = str(md.text() or "")
        token = str(token or "").strip()
        if token:
            try:
                self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            except Exception:
                pass
            self.insertPlainText(str(token))
            event.acceptProposedAction()
            return
        super().dropEvent(event)

from pydaw.plugins.sampler.ui_widgets import CompactKnob
from .aeterna_engine import (
    AeternaEngine, DEFAULT_FORMULA, AETERNA_STATE_SCHEMA_VERSION, AETERNA_PRESET_SCHEMA_VERSION, MSEG_SEGMENT_FORMS,
    MSEG_SNAP_DIVISIONS, MSEG_Y_QUANTIZE_LEVELS,
    MSEG_RANDOMIZE_AMOUNTS, MSEG_JITTER_AMOUNTS, MSEG_BLEND_AMOUNTS,
    MSEG_TILT_AMOUNTS, MSEG_SKEW_AMOUNTS,
    MSEG_RANGE_CLAMP_LEVELS, MSEG_DEADBAND_LEVELS, MSEG_MICRO_SMOOTH_LEVELS,
    MSEG_SOFTCLIP_DRIVE_LEVELS, MSEG_CENTER_EDGE_LEVELS,
)

MSEG_MORPH_AMOUNTS = ("25", "50", "75", "100")
MSEG_MACRO_LABELS = (("humanize_soft", "Humanize soft"), ("humanize_medium", "Humanize medium"), ("recenter", "Recenter"), ("flatten_peaks", "Flatten Peaks"))


class _ScopeWidget(QWidget):
    def __init__(self, engine: AeternaEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setMinimumHeight(84)
        self.setMaximumHeight(120)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.fillRect(r, QColor('#171b22'))
        p.setPen(QColor(42, 48, 59))
        for frac in (0.25, 0.5, 0.75):
            y = r.top() + r.height() * frac
            p.drawLine(r.left(), int(y), r.right(), int(y))
        p.setPen(QColor(64, 78, 98))
        p.drawRect(r)
        data = self.engine.get_scope_buffer()
        if data is None or len(data) < 2:
            return
        path = QPainterPath()
        mid = r.center().y()
        amp = max(6.0, r.height() * 0.42)
        for i, sample in enumerate(data):
            x = r.left() + (i / max(1, len(data) - 1)) * r.width()
            y = mid - float(sample) * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(QColor('#d7e3ff'), 1.4))
        p.drawPath(path)
        p.setPen(QPen(QColor('#5a6d88'), 1.0, Qt.PenStyle.DashLine))
        p.drawLine(r.left(), int(mid), r.right(), int(mid))


class _ModPreviewWidget(QWidget):
    def __init__(self, engine: AeternaEngine, on_mseg_changed=None, on_selection_changed=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._on_mseg_changed = on_mseg_changed
        self._on_selection_changed = on_selection_changed
        self._view = "mseg"
        self._phase = 0.0
        self._show_web_a = True
        self._show_web_b = True
        self._drag_point_index: int | None = None
        self._hover_point_index: int | None = None
        self._selected_point_index: int | None = None
        self._selected_segment_index: int | None = None
        self.setMinimumHeight(220)
        self.setMinimumWidth(420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_view(self, view: str) -> None:
        self._view = str(view or "mseg").lower()
        self.update()

    def view(self) -> str:
        return self._view

    def set_overlay_visibility(self, show_web_a: bool | None = None, show_web_b: bool | None = None) -> None:
        if show_web_a is not None:
            self._show_web_a = bool(show_web_a)
        if show_web_b is not None:
            self._show_web_b = bool(show_web_b)
        self.update()

    def overlay_visibility(self) -> tuple[bool, bool]:
        return self._show_web_a, self._show_web_b

    def advance_phase(self, dt_sec: float = 0.06) -> None:
        try:
            rate_key = {"lfo1": "lfo1_rate", "lfo2": "lfo2_rate", "mseg": "mseg_rate", "chaos": "mseg_rate"}.get(self._view, "mseg_rate")
            rate = float(self.engine.get_param(rate_key, 0.24) or 0.24)
        except Exception:
            rate = 0.24
        speed = 0.15 + rate * (0.85 if self._view != "chaos" else 0.65)
        self._phase = (self._phase + max(0.001, float(dt_sec)) * speed) % 1.0
        self.update()

    def _plot_rect(self):
        return self.rect().adjusted(8, 8, -8, -8)

    def _mseg_segment_forms(self) -> list[str]:
        try:
            forms = self.engine.get_mseg_segment_forms()
        except Exception:
            forms = []
        return [str(it or "linear").lower() for it in forms]

    def _set_mseg_segment_form(self, seg_idx: int, form: str) -> bool:
        pts = self._mseg_points()
        forms = self._mseg_segment_forms()
        if len(pts) < 2:
            return False
        if not (0 <= int(seg_idx) < len(pts) - 1):
            return False
        form = str(form or "linear").lower()
        if form not in MSEG_SEGMENT_FORMS:
            form = "linear"
        while len(forms) < len(pts) - 1:
            forms.append("linear")
        forms[int(seg_idx)] = form
        try:
            self.engine.set_mseg_segment_forms(forms, save_history=False)
        except Exception:
            return False
        self._selected_segment_index = int(seg_idx)
        self.update()
        self._notify_mseg_changed()
        return True

    def selected_segment(self) -> int | None:
        return self._selected_segment_index

    def _segment_for_selected_point(self, idx: int | None, points: list[tuple[float, float]]) -> int | None:
        if idx is None or len(points) < 2:
            return None
        idx = int(idx)
        if idx <= 0:
            return 0
        if idx >= len(points) - 1:
            return len(points) - 2
        return idx

    def _mseg_points(self) -> list[tuple[float, float]]:
        try:
            pts = self.engine.get_mseg_points()
        except Exception:
            pts = []
        return [tuple(pt) for pt in pts]

    def _point_to_canvas(self, pt: tuple[float, float], r) -> tuple[float, float]:
        x = r.left() + float(pt[0]) * r.width()
        y = r.bottom() - ((float(pt[1]) * 0.5 + 0.5) * r.height())
        return x, y

    def _canvas_to_point(self, x: float, y: float, r, idx: int, points: list[tuple[float, float]]) -> tuple[float, float]:
        xn = 0.0 if r.width() <= 1 else (float(x) - r.left()) / max(1.0, float(r.width()))
        yn = 0.0 if r.height() <= 1 else (r.bottom() - float(y)) / max(1.0, float(r.height()))
        xn = max(0.0, min(1.0, xn))
        yv = max(-1.0, min(1.0, (yn - 0.5) * 2.0))
        if idx <= 0:
            xn = 0.0
        elif idx >= len(points) - 1:
            xn = 1.0
        else:
            prev_x = float(points[idx - 1][0]) + 0.02
            next_x = float(points[idx + 1][0]) - 0.02
            xn = max(prev_x, min(next_x, xn))
        return xn, yv

    def _hit_test_point(self, pos) -> int | None:
        if self._view != "mseg":
            return None
        r = self._plot_rect()
        pts = self._mseg_points()
        best = None
        best_dist = 999999.0
        for idx, pt in enumerate(pts):
            px, py = self._point_to_canvas(pt, r)
            dist = ((float(pos.x()) - px) ** 2 + (float(pos.y()) - py) ** 2) ** 0.5
            if dist <= 11.0 and dist < best_dist:
                best = idx
                best_dist = dist
        return best

    def _select_point(self, idx: int | None) -> None:
        self._selected_point_index = None if idx is None else int(idx)
        pts = self._mseg_points()
        self._selected_segment_index = self._segment_for_selected_point(self._selected_point_index, pts)
        self._notify_selection_changed()
        self.update()

    def selected_point(self) -> int | None:
        return self._selected_point_index

    def _notify_selection_changed(self) -> None:
        if callable(self._on_selection_changed):
            try:
                self._on_selection_changed()
            except Exception:
                pass

    def _notify_mseg_changed(self) -> None:
        if callable(self._on_mseg_changed):
            try:
                self._on_mseg_changed()
            except Exception:
                pass

    def _insert_mseg_point_at(self, pos) -> bool:
        if self._view != "mseg":
            return False
        r = self._plot_rect()
        pts = self._mseg_points()
        if len(pts) < 2:
            return False
        x, y = self._canvas_to_point(pos.x(), pos.y(), r, 1, pts)
        insert_at = None
        for idx in range(1, len(pts)):
            if x < float(pts[idx][0]):
                insert_at = idx
                break
        if insert_at is None:
            insert_at = len(pts) - 1
        prev_x = float(pts[insert_at - 1][0])
        next_x = float(pts[insert_at][0])
        if (x - prev_x) < 0.03 or (next_x - x) < 0.03:
            x = (prev_x + next_x) * 0.5
        pts.insert(insert_at, (x, y))
        try:
            self.engine.set_mseg_points(pts)
        except Exception:
            return False
        forms = self._mseg_segment_forms()
        seg_idx = max(0, insert_at - 1)
        inherit_form = forms[seg_idx] if 0 <= seg_idx < len(forms) else "linear"
        forms.insert(insert_at, inherit_form)
        try:
            self.engine.set_mseg_segment_forms(forms, save_history=False)
        except Exception:
            pass
        self._selected_point_index = int(insert_at)
        self._selected_segment_index = self._segment_for_selected_point(insert_at, pts)
        self._hover_point_index = int(insert_at)
        self._notify_selection_changed()
        self._notify_mseg_changed()
        self.update()
        return True

    def _delete_selected_mseg_point(self) -> bool:
        pts = self._mseg_points()
        idx = self._selected_point_index
        if idx is None or len(pts) <= 2:
            return False
        idx = int(idx)
        if idx <= 0 or idx >= len(pts) - 1:
            return False
        del pts[idx]
        forms = self._mseg_segment_forms()
        remove_seg = min(max(0, idx - 1), max(0, len(forms) - 1))
        if forms:
            del forms[remove_seg]
        try:
            self.engine.set_mseg_points(pts)
            self.engine.set_mseg_segment_forms(forms, save_history=False)
        except Exception:
            return False
        new_idx = min(idx, len(pts) - 2)
        self._selected_point_index = new_idx if new_idx > 0 else None
        self._selected_segment_index = self._segment_for_selected_point(self._selected_point_index, pts)
        self._hover_point_index = self._selected_point_index
        self._notify_selection_changed()
        self._notify_mseg_changed()
        self.update()
        return True

    def mousePressEvent(self, event):
        if self._view == "mseg":
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if event.button() == Qt.MouseButton.LeftButton:
                hit = self._hit_test_point(event.position())
                if hit is not None:
                    try:
                        self.engine.push_mseg_history()
                    except Exception:
                        pass
                    self._drag_point_index = int(hit)
                    self._hover_point_index = int(hit)
                    self._selected_point_index = int(hit)
                    self._selected_segment_index = self._segment_for_selected_point(hit, self._mseg_points())
                    self._notify_selection_changed()
                    self.update()
                    event.accept()
                    return
            elif event.button() == Qt.MouseButton.RightButton:
                hit = self._hit_test_point(event.position())
                if hit is not None:
                    self._selected_point_index = int(hit)
                    self._notify_selection_changed()
                    if self._delete_selected_mseg_point():
                        event.accept()
                        return
                    self.update()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._view == "mseg":
            if self._drag_point_index is not None:
                pts = self._mseg_points()
                idx = int(self._drag_point_index)
                if 0 <= idx < len(pts):
                    r = self._plot_rect()
                    pts[idx] = self._canvas_to_point(event.position().x(), event.position().y(), r, idx, pts)
                    try:
                        self.engine.set_mseg_points(pts, save_history=False)
                    except Exception:
                        pass
                    self._hover_point_index = idx
                    self._selected_point_index = idx
                    self._selected_segment_index = self._segment_for_selected_point(idx, pts)
                    self._notify_selection_changed()
                    self._notify_mseg_changed()
                    self.update()
                    event.accept()
                    return
            else:
                hover = self._hit_test_point(event.position())
                if hover != self._hover_point_index:
                    self._hover_point_index = hover
                    self.update()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._view == "mseg" and event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test_point(event.position())
            if hit is None and self._insert_mseg_point_at(event.position()):
                event.accept()
                return
            if hit is not None:
                self._selected_point_index = int(hit)
                self._selected_segment_index = self._segment_for_selected_point(hit, self._mseg_points())
                self._notify_selection_changed()
                self.update()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if self._view == "mseg" and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._delete_selected_mseg_point():
                event.accept()
                return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_point_index is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_point_index = None
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._drag_point_index is None and self._hover_point_index is not None:
            self._hover_point_index = None
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._plot_rect()
        p.fillRect(r, QColor('#151922'))
        p.setPen(QColor(36, 42, 54))
        for frac in (0.2, 0.4, 0.6, 0.8):
            y = r.top() + r.height() * frac
            p.drawLine(r.left(), int(y), r.right(), int(y))
        for frac in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875):
            x = r.left() + r.width() * frac
            p.drawLine(int(x), r.top(), int(x), r.bottom())
        p.setPen(QColor(72, 82, 99))
        p.drawRect(r)

        data = self.engine.get_mod_preview_data(self._view, 384)
        mseg_forms = self._mseg_segment_forms() if self._view == "mseg" else []
        if data is not None and len(data) > 1:
            path = QPainterPath()
            for i, sample in enumerate(data):
                x = r.left() + (i / max(1, len(data) - 1)) * r.width()
                y = r.bottom() - ((float(sample) * 0.5 + 0.5) * r.height())
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            color_map = {"mseg": QColor('#d7e3ff'), "lfo1": QColor('#8fe388'), "lfo2": QColor('#ffd27f'), "chaos": QColor('#ff9a9a')}
            p.setPen(QPen(color_map.get(self._view, QColor('#d7e3ff')), 1.8))
            p.drawPath(path)

        if self._view == "mseg":
            pts = self._mseg_points()
            if pts:
                p.setPen(QPen(QColor('#73b6ff'), 1.0, Qt.PenStyle.DotLine))
                for pt in pts:
                    px, py = self._point_to_canvas(pt, r)
                    p.drawLine(int(px), r.top(), int(px), r.bottom())
                for seg_idx in range(max(0, len(pts) - 1)):
                    x0, y0 = self._point_to_canvas(pts[seg_idx], r)
                    x1, y1 = self._point_to_canvas(pts[seg_idx + 1], r)
                    seg_form = mseg_forms[seg_idx] if seg_idx < len(mseg_forms) else "linear"
                    seg_color = QColor('#5fe0b3') if seg_form == "smooth" else QColor('#9aa7bc')
                    seg_width = 2.2 if seg_idx == self._selected_segment_index else 1.2
                    p.setPen(QPen(seg_color, seg_width, Qt.PenStyle.SolidLine if seg_idx == self._selected_segment_index else Qt.PenStyle.DotLine))
                    p.drawLine(int(x0), int(y0), int(x1), int(y1))
                for idx, pt in enumerate(pts):
                    px, py = self._point_to_canvas(pt, r)
                    is_hot = idx in (self._hover_point_index, self._drag_point_index)
                    is_selected = idx == self._selected_point_index
                    radius = 6 if is_selected else (5 if is_hot else 4)
                    fill = QColor('#ffffff') if is_selected else (QColor('#dff1ff') if is_hot else QColor('#8fc2ff'))
                    if idx in (0, len(pts) - 1):
                        fill = QColor('#ffe3a6') if is_selected else (QColor('#ffd27f') if is_hot else QColor('#f3be63'))
                    p.setPen(QPen(QColor('#0e1117'), 1.0))
                    p.setBrush(fill)
                    p.drawEllipse(int(px - radius), int(py - radius), radius * 2, radius * 2)

        overlay_specs = []
        if self._show_web_a:
            overlay_specs.append((self.engine.get_web_overlay_data(1, 384), QColor('#8fc2ff'), 'Web A'))
        if self._show_web_b:
            overlay_specs.append((self.engine.get_web_overlay_data(2, 384), QColor('#ff95d0'), 'Web B'))
        legend_y = r.top() + 28
        for info, color, label_name in overlay_specs:
            samples = info.get('data') if isinstance(info, dict) else None
            if samples is None or len(samples) <= 1:
                continue
            path = QPainterPath()
            for i, sample in enumerate(samples):
                x = r.left() + (i / max(1, len(samples) - 1)) * r.width()
                y = r.bottom() - ((float(sample) * 0.5 + 0.5) * r.height())
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(color, 1.15, Qt.PenStyle.DashLine))
            p.drawPath(path)
            src = str(info.get('source', 'off') or 'off').upper()
            tgt = str(info.get('target', 'off') or 'off').upper()
            amt = int(round(float(info.get('amount', 0.0) or 0.0) * 100.0))
            p.setPen(color)
            p.drawText(r.adjusted(10, legend_y - r.top(), -10, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, f"{label_name}: {src} → {tgt} ({amt}%)")
            legend_y += 16

        p.setPen(QPen(QColor('#5a6d88'), 1.0, Qt.PenStyle.DashLine))
        mid = r.top() + r.height() * 0.5
        p.drawLine(r.left(), int(mid), r.right(), int(mid))

        phase_x = r.left() + self._phase * r.width()
        p.setPen(QPen(QColor('#7fb3ff'), 1.1, Qt.PenStyle.DashLine))
        p.drawLine(int(phase_x), r.top(), int(phase_x), r.bottom())

        label = {"mseg": "MSEG", "lfo1": "LFO1", "lfo2": "LFO2", "chaos": "CHAOS"}.get(self._view, self._view.upper())
        p.setPen(QColor('#c8d0e3'))
        p.drawText(r.adjusted(10, 8, -10, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, f"Preview: {label}")
        p.setPen(QColor('#7e8897'))
        if self._view == "mseg":
            sel = self._selected_point_index
            pts = self._mseg_points()
            seg = self._selected_segment_index
            seg_form = mseg_forms[seg] if seg is not None and 0 <= seg < len(mseg_forms) else "-"
            if sel is not None and 0 <= sel < len(pts):
                hint = f"MSEG lokal: Doppelklick Punkt • Rechtsklick/Entf löschen • Segment {seg_form} • Punkt #{sel+1} x={pts[sel][0]:.2f} y={pts[sel][1]:.2f}"
            else:
                hint = "MSEG lokal: Punkte/Segmente/Shapes • Snap/Quantize • Randomize/Jitter • Slots/Blend • Tilt/Skew • Phase/Symmetry/Slope. Endpunkte bleiben geschützt."
        else:
            hint = "Read-only, lokal im AETERNA-Widget"
        p.drawText(r.adjusted(10, 8, -10, -8), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, hint)


class _ModSourceChip(QPushButton):
    def __init__(self, source_key: str, label: str, parent=None):
        super().__init__(label, parent)
        self._source_key = str(source_key or "off")
        self._drag_start = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 8:
            super().mouseMoveEvent(event)
            return
        try:
            md = QMimeData()
            md.setData(MOD_SOURCE_TOKEN_MIME, self._source_key.encode("utf-8"))
            md.setText(self._source_key)
            drag = QDrag(self)
            drag.setMimeData(md)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            self.setCursor(Qt.CursorShape.OpenHandCursor)


class _ModDropTargetButton(QPushButton):
    def __init__(self, target_key: str, label: str, drop_callback=None, parent=None):
        super().__init__(label, parent)
        self._target_key = str(target_key or "off")
        self._drop_callback = drop_callback
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md and (md.hasFormat(MOD_SOURCE_TOKEN_MIME) or md.hasText()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md and (md.hasFormat(MOD_SOURCE_TOKEN_MIME) or md.hasText()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        source = ""
        if md:
            if md.hasFormat(MOD_SOURCE_TOKEN_MIME):
                try:
                    source = bytes(md.data(MOD_SOURCE_TOKEN_MIME)).decode("utf-8")
                except Exception:
                    source = ""
            elif md.hasText():
                source = str(md.text() or "")
        source = str(source or "").strip().lower()
        if source:
            try:
                if callable(self._drop_callback):
                    self._drop_callback(source, self._target_key)
            except Exception:
                pass
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class _Section(QFrame):
    expandedChanged = pyqtSignal(bool)

    def __init__(self, title: str, parent=None, *, expanded: bool = True):
        super().__init__(parent)
        self._title = str(title or "")
        self.setObjectName("aeternaSection")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self.btn_toggle = QToolButton(self)
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(bool(expanded))
        self.btn_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.btn_toggle.setToolTip("Bereich ein-/ausklappen")
        title_lab = QLabel(self._title)
        title_lab.setObjectName("aeternaSectionTitle")
        header.addWidget(self.btn_toggle)
        header.addWidget(title_lab, 1)
        lay.addLayout(header)
        self.body_widget = QWidget(self)
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        lay.addWidget(self.body_widget, 1)
        self.body_widget.setVisible(bool(expanded))
        self.btn_toggle.toggled.connect(self.set_expanded)

    def section_title(self) -> str:
        return self._title

    def is_expanded(self) -> bool:
        return bool(self.btn_toggle.isChecked())

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        try:
            self.btn_toggle.blockSignals(True)
            self.btn_toggle.setChecked(expanded)
        finally:
            self.btn_toggle.blockSignals(False)
        self.btn_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.body_widget.setVisible(expanded)
        self.expandedChanged.emit(expanded)

    def set_collapsed(self, collapsed: bool) -> None:
        self.set_expanded(not bool(collapsed))


class _SignalFlowDiagram(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = {}
        self.setMinimumHeight(176)
        self.setObjectName("aeternaSignalFlowDiagram")

    def set_state(self, state: dict) -> None:
        self._state = dict(state or {})
        self.update()

    def _tone(self, key: str, role: str, fallback: str) -> QColor:
        info = FAMILY_TONES.get(str(key or ""), {})
        return QColor(str(info.get(role) or fallback))

    def _draw_stage(self, painter: QPainter, x: int, y: int, w: int, h: int, title: str, body: str, tone: str, *, active: bool = True) -> None:
        bg = self._tone(tone, "bg", "rgba(255,255,255,0.08)")
        border = self._tone(tone, "border", "rgba(255,255,255,0.18)")
        accent = self._tone(tone, "accent", "#d8deee")
        if not active:
            bg.setAlpha(max(28, bg.alpha() // 2))
            border.setAlpha(max(38, border.alpha() // 2))
            accent = QColor("#8c97aa")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(x, y, w, h, 10, 10)
        painter.setPen(QPen(border, 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(x, y, w, h, 10, 10)
        painter.setPen(QPen(accent, 2.4))
        painter.drawLine(x + 10, y + 10, x + w - 10, y + 10)
        painter.setPen(accent)
        title_font = painter.font()
        title_font.setPointSize(max(9, title_font.pointSize()))
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(x + 10, y + 14, w - 20, 20, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), str(title or ""))
        body_font = painter.font()
        body_font.setBold(False)
        body_font.setPointSize(max(9, body_font.pointSize()))
        painter.setFont(body_font)
        painter.setPen(QColor("#d8deee") if active else QColor("#a0a8b9"))
        painter.drawText(x + 10, y + 38, w - 20, h - 46, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), str(body or ""))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(6, 6, -6, -6)
        p.fillRect(rect, QColor('#151a22'))
        top_h = 62
        gap = 8
        cols = 6
        w = max(70, int((rect.width() - (gap * (cols - 1))) / cols))
        y_top = rect.top() + 8
        x_positions = [rect.left() + i * (w + gap) for i in range(cols)]
        stages = [
            ("CORE", "Morph\nTone • Gain", "core"),
            ("FILTER", str(self._state.get("filter_type") or "LP 24") + "\nCut / Res", "filter"),
            ("TIMBRE", "Pitch • Shape\nPulse Width", "timbre"),
            ("LAYER", "Unison • Sub\nNoise", "layer"),
            ("DRIVE", "Drive\nFeedback", "drive"),
            ("SPACE", "Space • Motion\nCathedral • Drift", "space"),
        ]
        centers = []
        for i, (title, body, tone) in enumerate(stages):
            x = x_positions[i]
            self._draw_stage(p, x, y_top, w, top_h, title, body, tone, active=True)
            centers.append((x + w // 2, y_top + top_h // 2))
        p.setPen(QPen(QColor('#7388a8'), 2.0))
        for i in range(len(centers) - 1):
            x0 = x_positions[i] + w
            x1 = x_positions[i + 1]
            y = y_top + top_h // 2
            p.drawLine(x0 + 2, y, x1 - 8, y)
            p.drawLine(x1 - 14, y - 4, x1 - 8, y)
            p.drawLine(x1 - 14, y + 4, x1 - 8, y)

        mod_x = rect.left() + 4
        mod_y = y_top + top_h + 28
        mod_w = max(170, int(rect.width() * 0.28))
        mod_h = 56
        self._draw_stage(p, mod_x, mod_y, mod_w, mod_h, "MOD SOURCES", "LFO1 • LFO2 • MSEG\nChaos • ENV • VEL", "mod", active=True)
        web_w = max(132, int(rect.width() * 0.18))
        web_gap = 12
        web_a_x = mod_x + mod_w + 28
        web_b_x = web_a_x + web_w + web_gap
        target_x = web_b_x + web_w + 18
        target_w = max(180, rect.right() - target_x)
        slot_a = str(self._state.get("slot_a") or "frei")
        slot_b = str(self._state.get("slot_b") or "frei")
        self._draw_stage(p, web_a_x, mod_y, web_w, mod_h, "WEB A", slot_a, "core", active=slot_a.lower() != "frei")
        self._draw_stage(p, web_b_x, mod_y, web_w, mod_h, "WEB B", slot_b, "voice", active=slot_b.lower() != "frei")
        self._draw_stage(p, target_x, mod_y, target_w, mod_h, "ACTIVE TARGETS", str(self._state.get("targets") or "keine aktiven Ziele"), "flow", active=True)

        mod_center_y = mod_y + mod_h // 2
        for x in (web_a_x, web_b_x):
            p.setPen(QPen(QColor('#90a7ca'), 1.7, Qt.PenStyle.DashLine))
            p.drawLine(mod_x + mod_w, mod_center_y, x - 8, mod_center_y)
            p.drawLine(x - 14, mod_center_y - 4, x - 8, mod_center_y)
            p.drawLine(x - 14, mod_center_y + 4, x - 8, mod_center_y)
        p.setPen(QPen(QColor('#8fa7c9'), 1.7, Qt.PenStyle.DashLine))
        p.drawLine(web_a_x + web_w, mod_center_y, target_x - 8, mod_center_y)
        p.drawLine(web_b_x + web_w, mod_center_y, target_x - 8, mod_center_y)
        p.drawLine(target_x - 14, mod_center_y - 4, target_x - 8, mod_center_y)
        p.drawLine(target_x - 14, mod_center_y + 4, target_x - 8, mod_center_y)

        p.setPen(QColor('#98a6bb'))
        p.drawText(rect.adjusted(10, rect.height() - 18, -10, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom), str(self._state.get("footer") or "Signalfluss lokal visualisiert – ohne Core-Umbau"))


class _WavetablePreviewWidget(QWidget):
    """Compact wavetable waveform preview — shows interpolated frame at current position."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)

    def paintEvent(self, _event):
        try:
            import numpy as np
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.rect().adjusted(2, 2, -2, -2)
            w, h = rect.width(), rect.height()
            if w < 10 or h < 10:
                p.end()
                return

            # Background
            p.fillRect(rect, QColor('#1a1d23'))
            p.setPen(QPen(QColor('#2a2e38'), 1))
            p.drawRect(rect)

            # Center line
            cy = rect.y() + h // 2
            p.setPen(QPen(QColor('#333844'), 1, Qt.PenStyle.DashLine))
            p.drawLine(rect.x(), cy, rect.x() + w, cy)

            # Get waveform data
            frame_data = self._engine.get_wavetable_interpolated_frame()
            if frame_data is None or len(frame_data) < 2:
                p.setPen(QColor('#556677'))
                p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "No Wavetable")
                p.end()
                return

            # Downsample to widget width
            n = len(frame_data)
            step = max(1, n // w)
            samples = frame_data[::step][:w]
            points_count = len(samples)

            # Draw waveform
            path = QPainterPath()
            for i, s in enumerate(samples):
                x = rect.x() + (i / max(1, points_count - 1)) * w
                y = cy - float(s) * (h * 0.42)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            p.setPen(QPen(QColor('#5dade2'), 1.5))
            p.drawPath(path)

            # Label
            info = self._engine.get_wavetable_info()
            pos_text = f"Pos: {info.get('position', 0.0):.2f}  Frames: {info.get('num_frames', 0)}"
            p.setPen(QColor('#7f8c9b'))
            p.drawText(rect.adjusted(4, 2, -4, -2), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft), pos_text)

            p.end()
        except Exception:
            pass


class AeternaWidget(QWidget):
    PLUGIN_STATE_KEY = "aeterna"
    UI_STATE_SCHEMA_VERSION = 13

    def __init__(self, project_service=None, audio_engine=None, automation_manager=None, parent=None):
        super().__init__(parent)
        self.project_service = project_service
        self.audio_engine = audio_engine
        self.automation_manager = automation_manager
        self.track_id: Optional[str] = None
        self._restoring_state = False
        self._automation_setup_done = False
        self._automation_mgr_connected = False
        self._automation_pid_to_engine: dict[str, callable] = {}
        sr = 48000
        try:
            if self.audio_engine is not None:
                sr = int(self.audio_engine.get_effective_sample_rate())
        except Exception:
            sr = 48000
        self.engine = AeternaEngine(target_sr=sr)
        self._pull_name: Optional[str] = None

        def _pull(frames: int, sr: int, _eng=self.engine):
            return _eng.pull(frames, sr)
        _pull._pydaw_track_id = lambda: (self.track_id or "")  # type: ignore[attr-defined]
        self._pull_fn = _pull

        self._knobs: dict[str, CompactKnob] = {}
        self._knob_meter_labels: dict[str, QLabel] = {}
        self._combo_params: dict[str, QComboBox] = {}
        self._mseg_toolbar_rows: dict[int, list[QWidget]] = {}
        self._perf_init_started = time.perf_counter()
        self._last_deferred_refresh_ms = 0.0
        self._last_deferred_refresh_reason = "init"
        self._deferred_ui_refresh_stage = -1
        self._deferred_ui_refresh_pending = False
        self._deferred_refresh_timer = QTimer(self)
        self._deferred_refresh_timer.setSingleShot(True)
        self._deferred_refresh_timer.timeout.connect(self._run_deferred_ui_refresh_stage)
        self._mseg_advanced_visible = False
        self._preset_ab_slots: dict[str, dict] = {}
        self._preset_ab_compare_active = False
        self._formula_last_loaded_example_title = ""
        self._formula_last_loaded_example_text = ""
        self._formula_last_applied_text = str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA)
        self._formula_status_note = "Init geladen"
        self._formula_internal_change = False
        self._sections: dict[str, _Section] = {}
        self._mod_drop_slot_cursor = 1
        self._mod_last_assignment_note = "Drag Quelle → Ziel • bis zu 8 Slots (Web A–H)."
        self._macro_readability_note = "Makro A/B lokal lesbarer gruppiert"
        self._local_snapshots: dict[str, dict] = {}
        self._snapshot_last_action_note = "Zuletzt: noch kein lokaler Snapshot-Vorgang"
        self._snapshot_slot_labels: dict[str, QLabel] = {}
        self._composer_last_summary = "AETERNA Composer bereit"
        self._perf_build_ui_ms = 0.0
        self._perf_restore_ms = 0.0
        self._perf_ready_ms = 0.0
        self._perf_refresh_started = self._perf_init_started
        self._perf_last_scope = "init"
        self._scope_timer = QTimer(self)
        self._scope_timer.setInterval(60)
        self._scope_timer.timeout.connect(self._tick_scope)
        self._layer_toggle_defaults = {"unison_mix": 12, "sub_level": 10, "noise_level": 4}
        self._layer_toggle_memory = dict(self._layer_toggle_defaults)
        self._knob_mod_profiles: dict[str, dict] = {}
        self._arp_last_summary = "Arp A bereit"
        self._arp_live_status_note = "ARP Live: aus"
        self._aeterna_refresh_emit_pending = False
        self._arp_live_sync_busy = False
        self.setUpdatesEnabled(False)
        try:
            self._build_ui()
            self._apply_styles()
            self._set_mod_view("mseg", persist=False)
            self._apply_preset("Kathedrale", persist=False)
        finally:
            self.setUpdatesEnabled(True)
        self._perf_build_ui_ms = (time.perf_counter() - self._perf_init_started) * 1000.0
        self._perf_ready_ms = self._perf_build_ui_ms
        self._update_perf_status()
        self._scope_timer.start()
        self._schedule_deferred_ui_refresh(reason="init", delay_ms=0, restart=True)

    # -------- lifecycle
    def set_track_context(self, track_id: str) -> None:
        self.track_id = str(track_id or "")
        try:
            if self.track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                reg = get_sampler_registry()
                if not reg.has_sampler(self.track_id):
                    reg.register(self.track_id, self.engine, self)
        except Exception:
            pass
        try:
            if self.audio_engine is not None and self._pull_name is None and self.track_id:
                self._pull_name = f"aeterna:{self.track_id}:{id(self) & 0xFFFF:04x}"
                self.audio_engine.register_pull_source(self._pull_name, self._pull_fn)
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass
        self._restore_instrument_state()
        self._setup_automation()
        self._wire_knob_midi_learn()  # v0.0.20.424
        self._update_macro_ab_readability()
        self._update_formula_status()
        self._update_formula_info_line()
        self._schedule_deferred_ui_refresh(reason="track-context", delay_ms=0, restart=True)
        self._update_arp_live_status()
        try:
            if self._arp_live_enabled():
                self._sync_live_arp_device(persist=False)
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            if self.audio_engine is not None and self._pull_name is not None:
                self.audio_engine.unregister_pull_source(self._pull_name)
        except Exception:
            pass
        self._pull_name = None
        try:
            if self.track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                get_sampler_registry().unregister(self.track_id)
        except Exception:
            pass
        try:
            self.engine.stop_all()
        except Exception:
            pass

    # -------- project state
    def _get_track_obj(self):
        try:
            ctx = getattr(self.project_service, "ctx", None)
            proj = getattr(ctx, "project", None) if ctx is not None else None
            if proj is None:
                return None
            for t in getattr(proj, "tracks", []) or []:
                if str(getattr(t, "id", "")) == str(self.track_id or ""):
                    return t
        except Exception:
            return None
        return None

    def _track_note_fx_chain(self, ensure: bool = False):
        trk = self._get_track_obj()
        if trk is None:
            return None
        chain = getattr(trk, "note_fx_chain", None)
        if isinstance(chain, dict):
            if ensure and not isinstance(chain.get("devices"), list):
                chain["devices"] = []
            return chain
        if ensure:
            trk.note_fx_chain = {"devices": []}
            return trk.note_fx_chain
        return None

    def _find_aeterna_live_arp_device(self, create: bool = False):
        chain = self._track_note_fx_chain(ensure=create)
        if not isinstance(chain, dict):
            return None
        devices = chain.get("devices", []) or []
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if str(dev.get("plugin_id") or "") != "chrono.note_fx.arp":
                continue
            params = dev.get("params") if isinstance(dev.get("params"), dict) else {}
            if str(params.get("aeterna_owner") or "") == "arp_a":
                return dev
        if not create:
            return None
        dev = {
            "id": f"aet_arp_{hashlib.md5(str(self.track_id or 'aeterna').encode('utf-8')).hexdigest()[:8]}",
            "plugin_id": "chrono.note_fx.arp",
            "name": "AETERNA Arp A",
            "enabled": False,
            "params": {"aeterna_owner": "arp_a", "source": "aeterna", "step_beats": 0.25, "mode": "up", "octaves": 1, "gate": 0.9},
        }
        chain.setdefault("devices", []).append(dev)
        return dev

    def _arp_live_enabled(self) -> bool:
        try:
            return bool(getattr(self, "chk_arp_live_enabled", None) and self.chk_arp_live_enabled.isChecked())
        except Exception:
            return False

    def _aeterna_live_arp_params_from_ui(self) -> dict:
        p = self._arp_params_from_ui()
        avg_gate = 100.0
        try:
            steps = list(p.get("step_data") or [])
            visible = max(1, min(16, int(p.get("steps", 16) or 16)))
            gates = [float((st or {}).get("gate", 100) or 100) for st in steps[:visible] if isinstance(st, dict)]
            if gates:
                avg_gate = sum(gates) / float(len(gates))
        except Exception:
            avg_gate = 100.0
        base_rate = float(AETERNA_ARP_RATE_BEATS.get(str(p.get("rate") or "1/16"), 0.25))
        base_rate *= float(self._arp_note_type_factor())
        return {
            "aeterna_owner": "arp_a",
            "source": "aeterna",
            "step_beats": max(0.0625, min(4.0, base_rate)),
            "mode": str(p.get("pattern") or "up"),
            "octaves": 1,
            "gate": max(0.10, min(4.0, float(avg_gate) / 100.0)),
            "note_type": str(p.get("note_type") or "Straight").lower(),
            "shuffle_enabled": bool(p.get("shuffle_enabled", False)),
            "shuffle_steps": int(max(1, min(16, int(p.get("shuffle_steps", 16) or 16)))),
            "seed": int(p.get("seed") or self._arp_hash_seed()),
            "step_data": list(p.get("step_data") or []),
        }

    def _emit_project_refresh_from_aeterna(self) -> None:
        ps = self.project_service
        if ps is None:
            return
        if bool(getattr(self, '_aeterna_refresh_emit_pending', False)):
            return
        self._aeterna_refresh_emit_pending = True

        def _emit_later() -> None:
            try:
                try:
                    ps.project_updated.emit()
                except Exception:
                    pass
                try:
                    ps.project_changed.emit()
                except Exception:
                    pass
            finally:
                self._aeterna_refresh_emit_pending = False

        try:
            QTimer.singleShot(0, _emit_later)
        except Exception:
            self._aeterna_refresh_emit_pending = False
            try:
                ps.project_updated.emit()
            except Exception:
                pass

    def _sync_live_arp_device(self, persist: bool = True) -> None:
        if self.project_service is None or not self.track_id:
            return
        if bool(getattr(self, '_arp_live_sync_busy', False)):
            return
        self._arp_live_sync_busy = True
        try:
            dev = self._find_aeterna_live_arp_device(create=True)
            if not isinstance(dev, dict):
                return
            old_enabled = bool(dev.get("enabled", False))
            old_params = dict(dev.get("params") or {}) if isinstance(dev.get("params"), dict) else {}
            params = dict(old_params)
            params.update(self._aeterna_live_arp_params_from_ui())
            enabled = bool(self._arp_live_enabled())
            changed = (old_enabled != enabled) or (params != old_params) or (str(dev.get('name') or '') != 'AETERNA Arp A')
            dev["params"] = params
            dev["name"] = "AETERNA Arp A"
            dev["enabled"] = enabled
            self._arp_live_status_note = "ARP Live: an" if enabled else "ARP Live: aus"
            self._update_arp_live_status()
            if changed and not self._restoring_state:
                self._emit_project_refresh_from_aeterna()
            if persist and not self._restoring_state:
                self._persist_instrument_state()
        finally:
            self._arp_live_sync_busy = False

    def _set_arp_live_enabled(self, enabled: bool, persist: bool = True) -> None:
        enabled = bool(enabled)
        current_enabled = False
        if hasattr(self, "chk_arp_live_enabled"):
            try:
                current_enabled = bool(self.chk_arp_live_enabled.isChecked())
                self.chk_arp_live_enabled.blockSignals(True)
                if current_enabled != enabled:
                    self.chk_arp_live_enabled.setChecked(enabled)
            finally:
                self.chk_arp_live_enabled.blockSignals(False)
        if current_enabled == enabled and str(getattr(self, '_arp_live_status_note', '') or '') == ("ARP Live: an" if enabled else "ARP Live: aus"):
            return
        self._arp_live_status_note = "ARP Live: an" if enabled else "ARP Live: aus"
        self._update_arp_live_status()
        self._sync_live_arp_device(persist=persist)

    def _update_arp_live_status(self) -> None:
        note = str(getattr(self, "_arp_live_status_note", "ARP Live: aus") or "ARP Live: aus")
        if hasattr(self, "lbl_arp_live_status"):
            self.lbl_arp_live_status.setText(note)
        if hasattr(self, "btn_arp_sync_live"):
            self.btn_arp_sync_live.setText("Live ARP aktiv" if self._arp_live_enabled() else "Live ARP aus")

    def _automation_label_map(self) -> dict[str, str]:
        return {
            "morph": "AETERNA Morph",
            "chaos": "AETERNA Chaos",
            "drift": "AETERNA Drift",
            "tone": "AETERNA Tone",
            "release": "AETERNA Release",
            "gain": "AETERNA Gain",
            "space": "AETERNA Space",
            "motion": "AETERNA Motion",
            "cathedral": "AETERNA Cathedral",
            "lfo1_rate": "AETERNA LFO1 Rate",
            "lfo2_rate": "AETERNA LFO2 Rate",
            "mseg_rate": "AETERNA MSEG Rate",
            "mod1_amount": "AETERNA Web A",
            "mod2_amount": "AETERNA Web B",
            "filter_cutoff": "AETERNA Filter Cutoff",
            "filter_resonance": "AETERNA Filter Resonance",
            "pan": "AETERNA Pan",
            "glide": "AETERNA Glide",
            "stereo_spread": "AETERNA Stereo Spread",
            "aeg_attack": "AETERNA AEG Attack",
            "aeg_decay": "AETERNA AEG Decay",
            "aeg_sustain": "AETERNA AEG Sustain",
            "aeg_release": "AETERNA AEG Release",
            "feg_attack": "AETERNA FEG Attack",
            "feg_decay": "AETERNA FEG Decay",
            "feg_sustain": "AETERNA FEG Sustain",
            "feg_release": "AETERNA FEG Release",
            "feg_amount": "AETERNA FEG Amount",
            "unison_mix": "AETERNA Unison Mix",
            "unison_detune": "AETERNA Unison Detune",
            "sub_level": "AETERNA Sub Level",
            "noise_level": "AETERNA Noise Level",
            "noise_color": "AETERNA Noise Color",
            "pitch": "AETERNA Pitch",
            "shape": "AETERNA Shape",
            "pulse_width": "AETERNA Pulse Width",
            "drive": "AETERNA Drive",
            "feedback": "AETERNA Feedback",
        }

    def _automation_target_specs(self) -> list[dict]:
        tid = str(self.track_id or "")
        label_map = self._automation_label_map()
        specs = []
        for key in self._knobs.keys():
            specs.append({
                "key": str(key),
                "pid": self._automation_pid(key, tid),
                "name": label_map.get(key, f"AETERNA {key}"),
            })
        return specs

    def _automation_ready_spec(self, key: str) -> dict[str, str]:
        spec = AETERNA_AUTOMATION_READY.get(str(key), {})
        if isinstance(spec, dict):
            return {str(k): str(v) for k, v in spec.items()}
        return {}

    def _automation_ready_label(self, key: str) -> str:
        return self._automation_label_map().get(str(key), f"AETERNA {key}").replace("AETERNA ", "")

    def _automation_ready_tooltip(self, key: str) -> str:
        spec = self._automation_ready_spec(key)
        label = self._automation_ready_label(key)
        group = spec.get("group", "AETERNA")
        hint = spec.get("hint", "stabiler Zielparameter")
        return (
            f"{label}\n"
            f"Automation-sicher • {group}\n"
            f"Musikalisch: {hint}\n"
            "Klick öffnet direkt die passende Lane im Arranger."
        )

    def _refresh_knob_automation_tooltip(self, key: str) -> None:
        knob = self._knobs.get(str(key))
        if knob is None:
            return
        spec = self._automation_ready_spec(key)
        label = self._automation_ready_label(key)
        hint = spec.get("hint", "stabiler Zielparameter")
        knob.setToolTip(
            f"{label}: {int(knob.value())}%\n"
            f"Automation-sicher • {hint}\n"
            f"Mini-Meter: {self._family_meter([str(key)], 8)} • aktive Mod-Badges: {self._knob_active_mod_badges(str(key))}\n"
            f"{self._knob_profile_hint(str(key))}\n"
            "Rechtsklick → Show Automation in Arranger / Add Modulator"
        )

    def _refresh_all_knob_automation_tooltips(self) -> None:
        for key in self._knobs.keys():
            self._refresh_knob_automation_tooltip(str(key))
        self._update_all_knob_mini_meters()

    def _update_automation_quick_status(self, active_key: str = "") -> None:
        if not hasattr(self, "lbl_automation_quick_status"):
            return
        total = len(AETERNA_AUTOMATION_READY)
        key = str(active_key or "")
        spec = self._automation_ready_spec(key)
        if key and spec:
            self.lbl_automation_quick_status.setText(
                f"Automation-Fokus: {self._automation_ready_label(key)} • {spec.get('group', 'AETERNA')} • {spec.get('hint', 'stabiler Zielparameter')}"
            )
        else:
            self.lbl_automation_quick_status.setText(
                f"Schnellzugriff: {total} stabile Ziele • Klick öffnet direkt die passende AETERNA-Automation-Lane im Arranger."
            )

    def _open_automation_lane_for_key(self, key: str) -> None:
        key = str(key or "")
        spec = self._automation_ready_spec(key)
        if not spec:
            return
        mgr = getattr(self, "automation_manager", None)
        tid = str(self.track_id or "")
        if mgr is None or not tid:
            if hasattr(self, "lbl_automation_quick_status"):
                self.lbl_automation_quick_status.setText(
                    f"{self._automation_ready_label(key)}: Lane kann lokal erst mit gültigem Track-Kontext geöffnet werden."
                )
            return
        try:
            mgr.request_show_automation.emit(self._automation_pid(key, tid))
        except Exception:
            pass
        self._update_automation_quick_status(key)

    def _assign_mod_source_to_target_slot(self, source: str, target: str, slot: int, *, remember: bool = True, amount: int | None = None, polarity: str | None = None) -> None:
        source = str(source or "off").strip().lower()
        target = str(target or "off").strip().lower()
        if source not in set(self.engine.get_mod_sources()) or target not in set(self.engine.get_mod_targets()):
            return
        try:
            slot_i = 1 if int(slot) == 1 else 2
            if slot_i == 1:
                self.cmb_mod1_source.setCurrentText(source)
                self.cmb_mod1_target.setCurrentText(target)
                knob = self._knobs.get("mod1_amount")
            else:
                self.cmb_mod2_source.setCurrentText(source)
                self.cmb_mod2_target.setCurrentText(target)
                knob = self._knobs.get("mod2_amount")
            default_amount = int(amount) if amount is not None else (16 if source in {"env", "vel"} else 28 if source == "mseg" else 18 if source == "chaos" else 20)
            if knob is not None:
                knob.setValue(max(0, min(100, default_amount)))
            if polarity:
                self._set_mod_polarity(slot_i, str(polarity), persist=False)
            self._mod_last_assignment_note = (
                f"{MOD_SOURCE_LABELS.get(source, source.upper())} → {self._automation_ready_label(target)} "
                f"liegt jetzt auf Slot {'A' if slot_i == 1 else 'B'}."
            )
            if remember:
                self._knob_mod_profiles[str(target)] = {
                    "source": source,
                    "slot": slot_i,
                    "amount": int(knob.value()) if knob is not None else default_amount,
                    "polarity": self._mod_polarity_value(slot_i),
                }
            self._update_mod_rack_card()
            self._update_signal_flow_card()
            self._update_synth_stage1_panel()
            self._refresh_knob_automation_tooltip(str(target))
            self._update_all_knob_mini_meters()
            self._persist_instrument_state()
        except Exception:
            pass

    def _show_aeterna_knob_context_menu(self, key: str, knob, pos) -> None:
        try:
            menu = QMenu(knob)
            a_show = menu.addAction("Show Automation in Arranger")

            # v0.0.20.424: MIDI Learn for AETERNA knobs (same as CompactKnob)
            menu.addSeparator()
            a_midi_learn = None
            a_midi_remove = None
            cc_map = getattr(knob, '_midi_cc_mapping', None)
            if cc_map is not None:
                ch_s, cc_s = cc_map
                menu.addAction(f"🎹 Mapped: CC{cc_s} ch{ch_s}").setEnabled(False)
                a_midi_remove = menu.addAction("🎹 MIDI Mapping entfernen")
            else:
                a_midi_learn = menu.addAction("🎹 MIDI Learn")
            menu.addSeparator()

            mod_menu = menu.addMenu("Add Modulator")
            for source_key, source_label in (("lfo1", "LFO1"), ("lfo2", "LFO2"), ("mseg", "MSEG"), ("chaos", "Chaos"), ("env", "Envelope"), ("vel", "Velocity")):
                src_menu = mod_menu.addMenu(source_label)
                for slot_i, slot_label in ((1, "to Web A"), (2, "to Web B")):
                    act = src_menu.addAction(slot_label)
                    act.triggered.connect(lambda _=False, kk=str(key), ss=source_key, slot=slot_i: self._assign_mod_source_to_target_slot(ss, kk, slot, remember=True))
            mod_menu.addSeparator()
            a_apply_saved = mod_menu.addAction("Apply saved per-knob profile")
            a_apply_saved.setEnabled(bool(self._knob_mod_profiles.get(str(key))))
            if a_apply_saved.isEnabled():
                prof = self._knob_mod_profiles.get(str(key), {})
                a_apply_saved.setText(
                    f"Apply saved profile ({MOD_SOURCE_LABELS.get(str(prof.get('source') or 'off'), 'Off')} → Web {'A' if int(prof.get('slot', 1) or 1) == 1 else 'B'})"
                )
            menu.addSeparator()
            a_reset = menu.addAction("Reset to Default")
            chosen = menu.exec(knob.mapToGlobal(pos))
            if chosen == a_show:
                self._on_show_knob_automation(str(key))
            elif chosen == a_apply_saved:
                prof = self._knob_mod_profiles.get(str(key), {})
                if prof:
                    self._assign_mod_source_to_target_slot(
                        str(prof.get("source") or "off"),
                        str(key),
                        int(prof.get("slot", 1) or 1),
                        remember=True,
                        amount=int(prof.get("amount", 20) or 20),
                        polarity=str(prof.get("polarity") or "plus"),
                    )
            elif chosen == a_reset:
                try:
                    if hasattr(knob, "_automation_param") and knob._automation_param is not None:
                        knob._automation_param.set_value(float(getattr(knob, "_default_value", knob.value())))
                        knob._automation_param.set_automation_value(None)
                except Exception:
                    pass
                try:
                    knob.setValueExternal(int(round(float(getattr(knob, "_default_value", knob.value())))))
                except Exception:
                    pass
            # v0.0.20.424: MIDI Learn / Remove handlers
            elif chosen == a_midi_learn and a_midi_learn is not None:
                try:
                    if hasattr(knob, '_start_midi_learn'):
                        knob._start_midi_learn()
                except Exception:
                    pass
            elif chosen == a_midi_remove and a_midi_remove is not None:
                try:
                    if hasattr(knob, '_remove_midi_cc_listener'):
                        knob._remove_midi_cc_listener()
                    knob._midi_cc_mapping = None
                    knob.setStyleSheet('')
                except Exception:
                    pass
        except Exception:
            pass

    def _on_show_knob_automation(self, key: str) -> None:
        try:
            self._open_automation_lane_for_key(str(key or ""))
        except Exception:
            pass

    def _install_knob_context_menu(self, key: str, knob) -> None:
        try:
            knob.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            try:
                knob.customContextMenuRequested.disconnect()
            except Exception:
                pass
            knob.customContextMenuRequested.connect(lambda pos, kk=str(key), ww=knob: self._show_aeterna_knob_context_menu(kk, ww, pos))
        except Exception:
            pass

    def _wire_knob_midi_learn(self) -> None:
        """v0.0.20.424: Ensure all AETERNA knobs can do MIDI Learn.

        bind_automation() already sets _automation_manager on each knob.
        This method is a safety net — if any knob missed it, wire it now.
        """
        try:
            mgr = getattr(self, "automation_manager", None)
            if mgr is None:
                return
            for key, knob in self._knobs.items():
                if getattr(knob, '_automation_manager', None) is None:
                    knob._automation_manager = mgr
        except Exception:
            pass

    def _knob_profile_hint(self, key: str) -> str:
        prof = self._knob_mod_profiles.get(str(key), {})
        if not prof:
            return "Mod-Profil: –"
        src = MOD_SOURCE_LABELS.get(str(prof.get("source") or "off"), str(prof.get("source") or "off").upper())
        slot = "A" if int(prof.get("slot", 1) or 1) == 1 else "B"
        amount = int(prof.get("amount", 0) or 0)
        pol = "−" if str(prof.get("polarity") or "plus") == "minus" else "+"
        return f"Mod-Profil: {src} → Web {slot} {pol}{amount}%"

    def _combo_state_specs(self) -> list[tuple[str, str, str]]:
        return [
            ("cmb_mseg_shape", "mseg_shape_preset", "Default"),
            ("cmb_mseg_snap", "mseg_snap_divisions", "16"),
            ("cmb_mseg_y_quant", "mseg_y_levels", "9"),
            ("cmb_mseg_morph_shape", "mseg_morph_target", "Triangle"),
            ("cmb_mseg_morph_amount", "mseg_morph_amount", "50"),
            ("cmb_mseg_random", "mseg_random_amount", "35"),
            ("cmb_mseg_jitter", "mseg_jitter_amount", "4"),
            ("cmb_mseg_blend_a", "mseg_blend_a", "Triangle"),
            ("cmb_mseg_blend_b", "mseg_blend_b", "Cathedral Breath"),
            ("cmb_mseg_blend_amount", "mseg_blend_amount", "50"),
            ("cmb_mseg_tilt", "mseg_tilt_amount", "20"),
            ("cmb_mseg_skew", "mseg_skew_amount", "20"),
            ("cmb_mseg_slot", "mseg_slot_select", "1"),
            ("cmb_mseg_compare", "mseg_compare_target", "A"),
            ("cmb_mseg_curve", "mseg_curve_amount", "20"),
            ("cmb_mseg_pinch", "mseg_pinch_amount", "20"),
            ("cmb_mseg_range_clamp", "mseg_range_clamp", "80"),
            ("cmb_mseg_deadband", "mseg_deadband", "10"),
            ("cmb_mseg_micro_smooth", "mseg_micro_smooth", "30"),
            ("cmb_mseg_softclip", "mseg_softclip_drive", "20"),
            ("cmb_mseg_center_edge", "mseg_center_edge", "20"),
            ("cmb_mseg_phase_rotate", "mseg_phase_rotate", "10"),
            ("cmb_mseg_symmetry", "mseg_symmetry", "30"),
            ("cmb_mseg_slope", "mseg_slope", "35"),
        ]

    def _combo_by_name(self, attr_name: str):
        return getattr(self, attr_name, None)

    def _restore_signal_widgets(self) -> list[QWidget]:
        widgets: list[QWidget] = []
        attr_names = [
            "cmb_preset", "cmb_mode", "ed_formula",
            "cmb_preset_category", "cmb_preset_character", "ed_preset_note", "ed_preset_tags", "chk_preset_favorite",
            "cmb_preset_quick_filter", "cmb_web_template_intensity",
            "cmb_mod1_source", "cmb_mod1_target", "cmb_mod2_source", "cmb_mod2_target", "cmb_mod_assign_slot", "cmb_filter_type", "chk_retrigger",
            "chk_synth_preview_unison", "chk_synth_preview_sub", "chk_synth_preview_noise",
            "cmb_comp_family", "cmb_comp_style_a", "cmb_comp_style_b", "cmb_comp_context", "cmb_comp_form", "cmb_comp_phrase", "cmb_comp_density_profile",
            "spn_comp_bars", "cmb_comp_grid", "spn_comp_swing", "spn_comp_density", "spn_comp_hybrid", "spn_comp_seed",
            "chk_comp_bass", "chk_comp_melody", "chk_comp_lead", "chk_comp_pad", "chk_comp_arp",
            "cmb_arp_pattern", "cmb_arp_rate", "cmb_arp_note_type", "spn_arp_root", "cmb_arp_chord", "spn_arp_steps", "chk_arp_shuffle", "spn_arp_shuffle_steps", "spn_arp_seed", "chk_arp_live_enabled",
        ]
        for attr_name in attr_names:
            widget = getattr(self, attr_name, None)
            if isinstance(widget, QWidget):
                widgets.append(widget)
        widgets.extend([w for w in self._knobs.values() if isinstance(w, QWidget)])
        widgets.extend([w for w in self._combo_params.values() if isinstance(w, QWidget)])
        for attr_name, _key, _default in self._combo_state_specs():
            combo = self._combo_by_name(attr_name)
            if isinstance(combo, QWidget):
                widgets.append(combo)
        seen: set[int] = set()
        unique_widgets: list[QWidget] = []
        for widget in widgets:
            wid = id(widget)
            if wid in seen:
                continue
            seen.add(wid)
            unique_widgets.append(widget)
        return unique_widgets

    def _make_signal_blockers(self, widgets) -> list[QSignalBlocker]:
        blockers: list[QSignalBlocker] = []
        for widget in list(widgets or []):
            if widget is None:
                continue
            try:
                blockers.append(QSignalBlocker(widget))
            except Exception:
                pass
        return blockers

    def _rebind_button_click(self, button: QPushButton | QToolButton | None, handler=None) -> None:
        if button is None:
            return
        try:
            old_handler = getattr(button, "_aeterna_click_handler", None)
        except Exception:
            old_handler = None
        if old_handler is not None:
            try:
                button.clicked.disconnect(old_handler)
            except Exception:
                pass
        try:
            setattr(button, "_aeterna_click_handler", None)
        except Exception:
            pass
        if handler is None:
            return
        try:
            button.clicked.connect(handler)
            setattr(button, "_aeterna_click_handler", handler)
        except Exception:
            pass


    def _register_section(self, section: _Section | None) -> _Section | None:
        if section is None:
            return section
        try:
            name = str(section.section_title() or "").strip()
            if name:
                self._sections[name] = section
                section.expandedChanged.connect(lambda _expanded, nm=name: self._on_section_toggled(nm))
        except Exception:
            pass
        return section

    def _on_section_toggled(self, _name: str = "") -> None:
        try:
            self._update_signal_flow_card()
            self._update_all_knob_mini_meters()
            self._persist_instrument_state()
        except Exception:
            pass

    def _capture_section_states(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for name, section in (self._sections or {}).items():
            try:
                out[str(name)] = bool(section.is_expanded())
            except Exception:
                pass
        return out

    def _apply_section_states(self, states) -> None:
        if not isinstance(states, dict):
            return
        for name, expanded in states.items():
            section = self._sections.get(str(name))
            if section is None:
                continue
            try:
                section.set_expanded(bool(expanded))
            except Exception:
                pass

    def _mod_slot_preference(self) -> str:
        try:
            if hasattr(self, "cmb_mod_assign_slot"):
                return str(self.cmb_mod_assign_slot.currentText() or "Auto")
        except Exception:
            pass
        return "Auto"

    def _mod_polarity_value(self, slot: int) -> str:
        try:
            return str(self.engine.get_param(f"mod{int(slot)}_polarity", "plus") or "plus").strip().lower()
        except Exception:
            return "plus"

    def _mod_polarity_symbol(self, slot: int) -> str:
        return "−" if self._mod_polarity_value(slot) == "minus" else "+"

    def _mod_polarity_label(self, slot: int) -> str:
        return "invertiert" if self._mod_polarity_value(slot) == "minus" else "normal"

    def _slot_amount_bar(self, amount: int) -> str:
        try:
            pct = max(0, min(100, int(amount)))
        except Exception:
            pct = 0
        filled = int(round((pct / 100.0) * 8.0))
        filled = max(0, min(8, filled))
        return "■" * filled + "·" * (8 - filled)

    def _set_mod_polarity(self, slot: int, polarity: str, persist: bool = True) -> None:
        _slot_names = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H"}
        pol = "minus" if str(polarity or "plus").strip().lower() in {"minus", "-", "−", "inv", "invert"} else "plus"
        try:
            self.engine.set_param(f"mod{int(slot)}_polarity", pol)
            btn = getattr(self, f"btn_mod{int(slot)}_polarity", None)
            if btn is None:
                btn = getattr(self, '_extra_web_pol_btns', {}).get(int(slot))
            if btn is not None:
                btn.setText("−" if pol == "minus" else "+")
                btn.setToolTip(
                    f"Web {_slot_names.get(int(slot), '?')} Polarität\n"
                    + ("Minus = invertierte Modulation" if pol == "minus" else "Plus = normale Modulation")
                )
            self._schedule_knob_ui_refresh()
            if persist:
                self._persist_instrument_state()
        except Exception:
            pass

    def _toggle_mod_polarity(self, slot: int) -> None:
        cur = self._mod_polarity_value(slot)
        self._set_mod_polarity(slot, "minus" if cur != "minus" else "plus", persist=True)

    def _add_web_slot(self) -> None:
        """Show the next hidden Web slot (C→D→E→...→H)."""
        try:
            if self._visible_web_slots >= 8:
                return
            self._visible_web_slots += 1
            next_slot = self._visible_web_slots
            row_w = self._extra_web_rows.get(next_slot)
            if row_w is not None:
                row_w.setVisible(True)
            self._update_web_slot_buttons()
        except Exception:
            pass

    def _remove_web_slot(self) -> None:
        """Hide the last active Web slot and reset it to off."""
        try:
            if self._visible_web_slots <= 2:
                return
            slot = self._visible_web_slots
            row_w = self._extra_web_rows.get(slot)
            if row_w is not None:
                row_w.setVisible(False)
            # Reset slot to "off"
            self.engine.set_param(f"mod{slot}_source", "off")
            self.engine.set_param(f"mod{slot}_target", "off")
            self.engine.set_param(f"mod{slot}_amount", 0.0)
            cmb = self._extra_web_combos.get(slot)
            if cmb:
                cmb[0].setCurrentText("off")
                cmb[1].setCurrentText("off")
            knob = self._extra_web_knobs.get(slot)
            if knob:
                knob.setValueExternal(0) if hasattr(knob, 'setValueExternal') else knob.setValue(0)
            self._visible_web_slots -= 1
            self._update_web_slot_buttons()
            self._persist_instrument_state()
        except Exception:
            pass

    def _update_web_slot_buttons(self) -> None:
        """Update + / - button states and counter label."""
        try:
            n = int(self._visible_web_slots)
            self.btn_web_add.setEnabled(n < 8)
            self.btn_web_remove.setEnabled(n > 2)
            self.lbl_web_slot_count.setText(f"{n} / 8 Slots aktiv")
        except Exception:
            pass

    def _choose_mod_slot_for_assignment(self) -> int:
        pref = self._mod_slot_preference().strip().lower()
        if "slot a" in pref:
            return 1
        if "slot b" in pref:
            return 2
        try:
            src_a = str(self.cmb_mod1_source.currentText() or "off").lower()
            src_b = str(self.cmb_mod2_source.currentText() or "off").lower()
            if src_a == "off":
                return 1
            if src_b == "off":
                return 2
        except Exception:
            pass
        slot = 1 if int(getattr(self, "_mod_drop_slot_cursor", 1) or 1) == 1 else 2
        self._mod_drop_slot_cursor = 2 if slot == 1 else 1
        return slot

    def _clear_mod_slot(self, slot: int) -> None:
        try:
            if int(slot) == 1:
                self.cmb_mod1_source.setCurrentText("off")
                self.cmb_mod1_target.setCurrentText("off")
                self._set_mod_polarity(1, "plus", persist=False)
                if "mod1_amount" in self._knobs:
                    self._knobs["mod1_amount"].setValue(0)
            else:
                self.cmb_mod2_source.setCurrentText("off")
                self.cmb_mod2_target.setCurrentText("off")
                self._set_mod_polarity(2, "plus", persist=False)
                if "mod2_amount" in self._knobs:
                    self._knobs["mod2_amount"].setValue(0)
            self._mod_last_assignment_note = f"Slot {'A' if int(slot)==1 else 'B'} lokal geleert."
            self._update_mod_rack_card()
            self._persist_instrument_state()
        except Exception:
            pass

    def _swap_mod_slots(self) -> None:
        try:
            a = (
                self.cmb_mod1_source.currentText(),
                self.cmb_mod1_target.currentText(),
                int(self._knobs.get("mod1_amount").value() if self._knobs.get("mod1_amount") else 0),
                self._mod_polarity_value(1),
            )
            b = (
                self.cmb_mod2_source.currentText(),
                self.cmb_mod2_target.currentText(),
                int(self._knobs.get("mod2_amount").value() if self._knobs.get("mod2_amount") else 0),
                self._mod_polarity_value(2),
            )
            self.cmb_mod1_source.setCurrentText(str(b[0] or "off"))
            self.cmb_mod1_target.setCurrentText(str(b[1] or "off"))
            self.cmb_mod2_source.setCurrentText(str(a[0] or "off"))
            self.cmb_mod2_target.setCurrentText(str(a[1] or "off"))
            self._set_mod_polarity(1, str(b[3] or "plus"), persist=False)
            self._set_mod_polarity(2, str(a[3] or "plus"), persist=False)
            if self._knobs.get("mod1_amount") is not None:
                self._knobs["mod1_amount"].setValue(int(b[2]))
            if self._knobs.get("mod2_amount") is not None:
                self._knobs["mod2_amount"].setValue(int(a[2]))
            self._mod_last_assignment_note = "Slots A/B lokal getauscht."
            self._update_mod_rack_card()
            self._persist_instrument_state()
        except Exception:
            pass

    def _assign_mod_source_to_target(self, source: str, target: str) -> None:
        source = str(source or "off").strip().lower()
        target = str(target or "off").strip().lower()
        if source not in set(self.engine.get_mod_sources()) or target not in set(self.engine.get_mod_targets()):
            return
        slot = self._choose_mod_slot_for_assignment()
        try:
            if slot == 1:
                self.cmb_mod1_source.setCurrentText(source)
                self.cmb_mod1_target.setCurrentText(target)
                knob = self._knobs.get("mod1_amount")
            else:
                self.cmb_mod2_source.setCurrentText(source)
                self.cmb_mod2_target.setCurrentText(target)
                knob = self._knobs.get("mod2_amount")
            default_amount = 20
            if source in {"env", "vel"}:
                default_amount = 16
            elif source == "mseg":
                default_amount = 28
            elif source == "chaos":
                default_amount = 18
            if knob is not None and int(knob.value()) < 8:
                knob.setValue(default_amount)
            self._mod_last_assignment_note = (
                f"{MOD_SOURCE_LABELS.get(source, source.upper())} → {self._automation_ready_label(target)} "
                f"liegt jetzt auf Slot {'A' if slot == 1 else 'B'}."
            )
            self._update_mod_rack_card()
            self._persist_instrument_state()
        except Exception:
            pass

    def _mod_slot_summary(self, slot: int) -> str:
        try:
            if int(slot) == 1:
                source = str(self.cmb_mod1_source.currentText() or "off")
                target = str(self.cmb_mod1_target.currentText() or "off")
                amount = int(self._knobs.get("mod1_amount").value() if self._knobs.get("mod1_amount") else 0)
                slot_name = "A"
            else:
                source = str(self.cmb_mod2_source.currentText() or "off")
                target = str(self.cmb_mod2_target.currentText() or "off")
                amount = int(self._knobs.get("mod2_amount").value() if self._knobs.get("mod2_amount") else 0)
                slot_name = "B"
            if source == "off" or target == "off":
                return f"Slot {slot_name}: frei"
            pol = self._mod_polarity_symbol(slot)
            return (
                f"Slot {slot_name}: {MOD_SOURCE_LABELS.get(source, source.upper())} → {self._automation_ready_label(target)} "
                f"• {pol}{amount}% • {self._slot_amount_bar(amount)}"
            )
        except Exception:
            return f"Slot {slot}: –"

    def _update_mod_rack_card(self) -> None:
        try:
            if hasattr(self, "lbl_mod_rack_card"):
                self.lbl_mod_rack_card.setText(
                    "Mod Rack\n"
                    + self._mod_slot_summary(1) + "\n"
                    + self._mod_slot_summary(2) + "\n"
                    + f"Drop-Slot: {self._mod_slot_preference()} • {str(getattr(self, '_mod_last_assignment_note', '') or '').strip()}"
                )
            if hasattr(self, "lbl_mod_rack_hint"):
                self.lbl_mod_rack_hint.setText(
                    "Wie in klassischen Mod-Matrizen: Quelle ziehen → auf stabiles Ziel fallenlassen → Amount/Rate/Polarität fein dosieren. "
                    "Real vorhanden sind heute 2 Slots (Web A/B) und stabile Ziele, keine rohe globale Synth-Engine-Umschreibung."
                )
        except Exception:
            pass

    def _slot_flow_map_line(self, slot: int) -> str:
        try:
            if int(slot) == 1:
                source = str(self.cmb_mod1_source.currentText() or "off")
                target = str(self.cmb_mod1_target.currentText() or "off")
                amount = int(self._knobs.get("mod1_amount").value() if self._knobs.get("mod1_amount") else 0)
                name = "Web A"
            else:
                source = str(self.cmb_mod2_source.currentText() or "off")
                target = str(self.cmb_mod2_target.currentText() or "off")
                amount = int(self._knobs.get("mod2_amount").value() if self._knobs.get("mod2_amount") else 0)
                name = "Web B"
            if source == "off" or target == "off":
                return f"{name:<5}  frei"
            src_label = MOD_SOURCE_LABELS.get(source, source.upper())
            tgt_label = self._automation_ready_label(target)
            pol = self._mod_polarity_symbol(slot)
            return f"{src_label:<7} ──► {name} [{pol}{amount:>2}% {self._slot_amount_bar(amount)}] ──► {tgt_label}"
        except Exception:
            return f"Web {'A' if int(slot)==1 else 'B'}  –"

    def _update_signal_flow_card(self) -> None:
        if not hasattr(self, "lbl_signal_flow"):
            return
        try:
            collapsed = [name for name, sec in (self._sections or {}).items() if sec is not None and not sec.is_expanded()]
        except Exception:
            collapsed = []
        collapsed_txt = ", ".join(collapsed[:4]) if collapsed else "alles offen"
        self.lbl_signal_flow.setText(
            "Signalfluss\n"
            "Audio: Core → Filter → Pitch/Timbre → Layer → Drive/Feedback → Space\n"
            "Mod: LFO1 • LFO2 • MSEG • Chaos • ENV • VEL → Web A/B → stabile Ziele\n"
            f"Web A: {self._format_web_slot_compact(1)}\n"
            f"Web B: {self._format_web_slot_compact(2)}\n"
            f"Ansicht: eingeklappt = {collapsed_txt}"
        )
        if hasattr(self, "lbl_signal_flow_map"):
            self.lbl_signal_flow_map.setText(
                "<pre style='margin:0; font-family:monospace;'>"
                + "FLOW MAP\n"
                + self._slot_flow_map_line(1) + "\n"
                + self._slot_flow_map_line(2)
                + "</pre>"
            )
        if hasattr(self, "flow_diagram"):
            try:
                slot_targets = []
                for idx, name in ((1, "A"), (2, "B")):
                    if idx == 1:
                        src = str(self.cmb_mod1_source.currentText() or "off") if hasattr(self, "cmb_mod1_source") else "off"
                        tgt = str(self.cmb_mod1_target.currentText() or "off") if hasattr(self, "cmb_mod1_target") else "off"
                        amt = self._param_pct("mod1_amount", 20)
                    else:
                        src = str(self.cmb_mod2_source.currentText() or "off") if hasattr(self, "cmb_mod2_source") else "off"
                        tgt = str(self.cmb_mod2_target.currentText() or "off") if hasattr(self, "cmb_mod2_target") else "off"
                        amt = self._param_pct("mod2_amount", 22)
                    if src != "off" and tgt != "off":
                        slot_targets.append(f"Web {name}: {MOD_SOURCE_LABELS.get(src, src.upper())} → {self._automation_ready_label(tgt)} ({self._mod_polarity_symbol(idx)}{amt}%)")
                self.flow_diagram.set_state({
                    "filter_type": self.cmb_filter_type.currentText() if hasattr(self, "cmb_filter_type") else "LP 24",
                    "slot_a": self._format_web_slot_compact(1).replace("Web A: ", ""),
                    "slot_b": self._format_web_slot_compact(2).replace("Web B: ", ""),
                    "targets": "\n".join(slot_targets) if slot_targets else "keine aktiven Ziele",
                    "footer": f"Einklappbar • lokale Familienkarten • {collapsed_txt}",
                })
            except Exception:
                pass
        self._update_synth_stage1_panel()

    def _param_pct(self, key: str, default: int = 0) -> int:
        try:
            knob = self._knobs.get(str(key))
            if knob is not None:
                return int(knob.value())
        except Exception:
            pass
        try:
            return int(round(float(self.engine.get_param(str(key), float(default) / 100.0)) * 100.0))
        except Exception:
            return int(default)

    def _expand_section(self, name: str) -> None:
        try:
            section = self._sections.get(str(name))
            if section is None:
                return
            section.set_expanded(True)
            self._update_signal_flow_card()
            self._update_all_knob_mini_meters()
            self._persist_instrument_state()
        except Exception:
            pass

    def _format_web_slot_compact(self, slot: int) -> str:
        try:
            slot = int(slot)
            if slot == 1:
                source = str(self.cmb_mod1_source.currentText() or "off")
                target = str(self.cmb_mod1_target.currentText() or "off")
                amount = self._param_pct("mod1_amount", 20)
                name = "Web A"
            else:
                source = str(self.cmb_mod2_source.currentText() or "off")
                target = str(self.cmb_mod2_target.currentText() or "off")
                amount = self._param_pct("mod2_amount", 22)
                name = "Web B"
            if source == "off" or target == "off":
                return f"{name}: Off"
            return (
                f"{name}: {MOD_SOURCE_LABELS.get(source, source.upper())} → "
                f"{self._automation_ready_label(target)} • {self._mod_polarity_symbol(slot)}{amount}%"
            )
        except Exception:
            return f"Web {'A' if int(slot)==1 else 'B'}: –"

    def _update_synth_stage1_panel(self) -> None:
        try:
            if hasattr(self, "lbl_synth_stage1_overview"):
                self.lbl_synth_stage1_overview.setText(
                    "AETERNA Synth Panel Stage 1/2/3\n"
                    "Vorhandene stabile Parameter sind hier als lesbare Synth-Oberfläche gruppiert. "
                    "Jetzt kommen Voice- und Envelope-Familien dazu – weiter lokal in AETERNA und ohne Core-Umbau."
                )
            if hasattr(self, "lbl_synth_stage1_core"):
                self.lbl_synth_stage1_core.setText(
                    "Core Voice\n"
                    + self._synth_stage1_line("Kern", ["morph", "tone", "gain", "release"])
                    + "\n"
                    + self._synth_stage1_line("Voice", ["pan", "glide", "stereo_spread"])
                    + f"\nRetrig: {'an' if hasattr(self, 'chk_retrigger') and self.chk_retrigger.isChecked() else 'aus'}"
                )
            if hasattr(self, "lbl_synth_stage1_space"):
                self.lbl_synth_stage1_space.setText(
                    "Space / Motion\n"
                    + self._synth_stage1_line("Raum", ["space", "motion", "cathedral", "drift"])
                    + "\nFokus: Weite, Bewegung, sakraler Raum und organisches Treiben."
                )
            if hasattr(self, "lbl_synth_stage1_mod"):
                self.lbl_synth_stage1_mod.setText(
                    "Mod / Web\n"
                    + self._synth_stage1_line("Rates", ["chaos", "lfo1_rate", "lfo2_rate", "mseg_rate"])
                    + "\n"
                    + self._format_web_slot_compact(1)
                    + "\n"
                    + self._format_web_slot_compact(2)
                )
            if hasattr(self, "lbl_synth_stage1_future"):
                self.lbl_synth_stage1_future.setText(
                    "Ausbaurichtung\n"
                    "Jetzt real: Voice, AEG/FEG, Layer, Pitch/Timbre und Drive/Feedback\n"
                    "Als Nächstes: feinere UX/Visualisierung statt riskanter Core-Umbau\n"
                    "So kommen größere Familien in sicheren Blöcken statt als riskanter Alles-auf-einmal-Umbau."
                )
            if hasattr(self, "lbl_synth_stage2_filter"):
                filter_type = self.cmb_filter_type.currentText() if hasattr(self, "cmb_filter_type") else "LP 24"
                self.lbl_synth_stage2_filter.setText(
                    "Filter Stage 2\n"
                    f"Type: {filter_type}\n"
                    + self._synth_stage1_line("Filter", ["filter_cutoff", "filter_resonance", "feg_amount"])
                    + "\n" + self._family_status_line("filter", ["filter_cutoff", "filter_resonance", "feg_amount"])
                    + "\nFokus: Cutoff = Fenster • Resonance = Kante • FEG = Hüllkurvenstoß."
                )
            if hasattr(self, "lbl_synth_voice_family"):
                self.lbl_synth_voice_family.setText(
                    "Voice Family\n"
                    + self._synth_stage1_line("Voice", ["pan", "glide", "stereo_spread"])
                    + "\n" + self._family_status_line("voice", ["pan", "glide", "stereo_spread"])
                    + f"\nRetrig: {'aktiv' if hasattr(self, 'chk_retrigger') and self.chk_retrigger.isChecked() else 'flow / phase weiter'}"
                )
            if hasattr(self, "lbl_synth_aeg_family"):
                self.lbl_synth_aeg_family.setText(
                    "AEG ADSR\n"
                    + self._synth_stage1_line("Amp", ["aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release"])
                    + "\n" + self._family_status_line("aeg", ["aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release"])
                    + "\nFokus: Lautstärkehüllkurve für Attack, Haltepegel und Release."
                )
            if hasattr(self, "lbl_synth_feg_family"):
                self.lbl_synth_feg_family.setText(
                    "FEG ADSR\n"
                    + self._synth_stage1_line("Filter Env", ["feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount"])
                    + "\n" + self._family_status_line("feg", ["feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount"])
                    + "\nFokus: Cutoff-/Resonance-Bewegung per Hüllkurve."
                )

            if hasattr(self, "lbl_synth_unison_family"):
                voices = self.cmb_unison_voices.currentText() if hasattr(self, "cmb_unison_voices") else "2"
                sub_oct = self.cmb_sub_octave.currentText() if hasattr(self, "cmb_sub_octave") else "-1"
                self.lbl_synth_unison_family.setText(
                    "Unison / Sub\n"
                    + self._synth_stage1_line("Layer", ["unison_mix", "unison_detune", "sub_level"])
                    + "\n" + self._family_status_line("layer", ["unison_mix", "unison_detune", "sub_level"])
                    + f"\nVoices: {voices} • Sub Okt: {sub_oct}\nChorbreite + Fundament direkt im Layer-Block sichtbar."
                )
            if hasattr(self, "lbl_synth_noise_family"):
                voices = self.cmb_unison_voices.currentText() if hasattr(self, "cmb_unison_voices") else "2"
                sub_oct = self.cmb_sub_octave.currentText() if hasattr(self, "cmb_sub_octave") else "-1"
                self.lbl_synth_noise_family.setText(
                    "Noise / Color\n"
                    + self._synth_stage1_line("Noise", ["noise_level", "noise_color"])
                    + "\n" + self._family_status_line("noise", ["noise_level", "noise_color"])
                    + f"\nSub Okt: {sub_oct} • Unison Voices: {voices}\nNoise dunkel ↔ hell musikalisch führen."
                )
            if hasattr(self, "lbl_synth_pitch_family"):
                self.lbl_synth_pitch_family.setText(
                    "Pitch / Shape / PW\n"
                    + self._synth_stage1_line("Timbre", ["pitch", "shape", "pulse_width"])
                    + "\n" + self._family_status_line("timbre", ["pitch", "shape", "pulse_width"])
                    + "\nPitch = ±24 st • Shape = Wellenform • PW = Rechteck-Vokalität."
                )
            if hasattr(self, "lbl_synth_drive_family"):
                self.lbl_synth_drive_family.setText(
                    "Drive / Feedback\n"
                    + self._synth_stage1_line("Drive", ["drive", "feedback"])
                    + "\n" + self._family_status_line("drive", ["drive", "feedback"])
                    + "\nSättigung und interne Rückkopplung bleiben lokal in AETERNA gekapselt."
                )
            if hasattr(self, "lbl_synth_stage1_preview_hint"):
                voices = self.cmb_unison_voices.currentText() if hasattr(self, "cmb_unison_voices") else "2"
                sub_oct = self.cmb_sub_octave.currentText() if hasattr(self, "cmb_sub_octave") else "-1"
                self.lbl_synth_stage1_preview_hint.setText(
                    f"Die Layer-Schalter unten sind direkt aktiv: Unison / Sub / Noise lassen sich sofort an- und ausschalten. Aktuell: Voices {voices} • Sub Okt {sub_oct}. Weitere Familien folgen weiterhin in gekapselten lokalen Blöcken."
                )
            self._sync_layer_preview_toggles()
            self._update_all_knob_mini_meters()
        except Exception:
            pass

    def _synth_stage1_line(self, title: str, keys: list[str]) -> str:
        label_map = self._automation_label_map()
        parts = []
        for key in list(keys or []):
            parts.append(f"{label_map.get(key, key.replace('_', ' ').title()).replace('AETERNA ', '')} {self._param_pct(key)}%")
        return f"{title}: " + " • ".join(parts)

    def _family_meter(self, keys: list[str], width: int = 8) -> str:
        vals = [max(0, min(100, self._param_pct(key))) for key in list(keys or [])]
        if not vals:
            return "░" * max(4, int(width or 8))
        avg = sum(vals) / float(max(1, len(vals)))
        filled = int(round((avg / 100.0) * max(4, int(width or 8))))
        width_i = max(4, int(width or 8))
        filled = max(0, min(width_i, filled))
        return ("█" * filled) + ("░" * (width_i - filled))

    def _family_active_mod_badges(self, family_key: str) -> str:
        family_targets = {
            "filter": {"filter_cutoff", "filter_resonance", "feg_amount"},
            "voice": {"pan", "glide", "stereo_spread"},
            "aeg": {"aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release"},
            "feg": {"feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount", "filter_cutoff", "filter_resonance"},
            "layer": {"unison_mix", "unison_detune", "sub_level"},
            "noise": {"noise_level", "noise_color"},
            "timbre": {"pitch", "shape", "pulse_width"},
            "drive": {"drive", "feedback"},
        }
        targets = set(family_targets.get(str(family_key), set()))
        if not targets:
            return "Mods: –"
        badges = []
        for idx, source_attr, target_attr, amount_key in (
            (1, "cmb_mod1_source", "cmb_mod1_target", "mod1_amount"),
            (2, "cmb_mod2_source", "cmb_mod2_target", "mod2_amount"),
        ):
            source = str(getattr(self, source_attr).currentText() or "off") if hasattr(self, source_attr) else "off"
            target = str(getattr(self, target_attr).currentText() or "off") if hasattr(self, target_attr) else "off"
            if source == "off" or target == "off" or target not in targets:
                continue
            badges.append(
                f"Web {'A' if idx == 1 else 'B'}→{self._automation_ready_label(target)} {self._mod_polarity_symbol(idx)}{self._param_pct(amount_key)}%"
            )
        return "Mods: " + (" • ".join(badges) if badges else "–")

    def _family_status_line(self, family_key: str, keys: list[str]) -> str:
        meter = self._family_meter(keys)
        badges = self._family_active_mod_badges(family_key)
        return f"Aktiv {meter} • {badges}"

    def _knob_active_mod_badges(self, key: str) -> str:
        try:
            key = str(key or "").strip().lower()
            if not key:
                return "–"
            badges = []
            for idx, source_attr, target_attr, amount_key in (
                (1, "cmb_mod1_source", "cmb_mod1_target", "mod1_amount"),
                (2, "cmb_mod2_source", "cmb_mod2_target", "mod2_amount"),
            ):
                source = str(getattr(self, source_attr).currentText() or "off") if hasattr(self, source_attr) else "off"
                target = str(getattr(self, target_attr).currentText() or "off") if hasattr(self, target_attr) else "off"
                if source == "off" or target != key:
                    continue
                badges.append(f"{'A' if idx == 1 else 'B'}{self._mod_polarity_symbol(idx)}{self._param_pct(amount_key)}")
            return " • ".join(badges) if badges else "–"
        except Exception:
            return "–"

    def _knob_mini_meter_text(self, key: str, *, width: int = 6) -> str:
        pct = self._param_pct(key)
        meter = self._family_meter([str(key or "")], width=max(4, int(width or 6)))
        mods = self._knob_active_mod_badges(str(key or ""))
        return f"{meter} {pct}%\n{mods}"

    def _update_knob_mini_meter(self, key: str) -> None:
        try:
            key = str(key or "")
            lbl = self._knob_meter_labels.get(key)
            knob = self._knobs.get(key)
            if lbl is None or knob is None:
                return
            tone = str(getattr(lbl, '_aeterna_tone', 'flow') or 'flow')
            mods = self._knob_active_mod_badges(key)
            lbl.setText(self._knob_mini_meter_text(key))
            lbl.setToolTip(
                f"{self._automation_ready_label(key)}\n"
                f"Mini-Meter: {self._family_meter([key], 8)} • {self._param_pct(key)}%\n"
                f"Aktive Mod-Badges: {mods}\n"
                f"{self._knob_profile_hint(key)}"
            )
            lbl.setProperty('tone', tone)
            lbl.setProperty('modActive', mods != '–')
            try:
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)
            except Exception:
                pass
        except Exception:
            pass

    def _update_all_knob_mini_meters(self) -> None:
        for key in list(getattr(self, '_knob_meter_labels', {}).keys()):
            self._update_knob_mini_meter(str(key))

    def _add_knob_mini_meter(self, layout, row: int, col: int, key: str, tone: str) -> None:
        try:
            lbl = QLabel(self._knob_mini_meter_text(key))
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            lbl.setObjectName('aeternaKnobMiniMeter')
            lbl._aeterna_tone = str(tone or 'flow')
            lbl.setProperty('tone', str(tone or 'flow'))
            self._knob_meter_labels[str(key)] = lbl
            layout.addWidget(lbl, int(row), int(col))
        except Exception:
            pass

    def _sync_layer_preview_toggles(self) -> None:
        try:
            mapping = (
                ("chk_synth_preview_unison", "unison_mix", "Unison"),
                ("chk_synth_preview_sub", "sub_level", "Sub"),
                ("chk_synth_preview_noise", "noise_level", "Noise"),
            )
            for attr_name, key, label in mapping:
                chk = getattr(self, attr_name, None)
                if chk is None:
                    continue
                pct = self._param_pct(key, self._layer_toggle_defaults.get(key, 0))
                active = pct > 0
                try:
                    chk.blockSignals(True)
                    chk.setChecked(active)
                finally:
                    try:
                        chk.blockSignals(False)
                    except Exception:
                        pass
                chk.setToolTip(
                    f"{label} direkt umschalten. Aktuell {'aktiv' if active else 'aus'} • Level {pct}%"
                )
        except Exception:
            pass

    def _toggle_layer_feature(self, key: str, checked: bool) -> None:
        try:
            key = str(key or "")
            knob = self._knobs.get(key)
            if knob is None:
                return
            current = int(knob.value())
            if checked:
                target = current
                if target <= 0:
                    target = int(self._layer_toggle_memory.get(key, self._layer_toggle_defaults.get(key, 10)))
                    target = max(1, min(100, target))
                    knob.setValueExternal(target)
                    self.engine.set_param(key, float(target) / 100.0)
            else:
                if current > 0:
                    self._layer_toggle_memory[key] = int(current)
                knob.setValueExternal(0)
                self.engine.set_param(key, 0.0)
            self._refresh_knob_automation_tooltip(key)
            self._update_synth_stage1_panel()
            self._update_signal_flow_card()
            self._update_all_knob_mini_meters()
            self._persist_instrument_state()
            self._sync_layer_preview_toggles()
        except Exception:
            pass

    def _update_perf_status(self) -> None:
        if not hasattr(self, "lbl_perf_status"):
            return
        build_ms = float(getattr(self, "_perf_build_ui_ms", 0.0) or 0.0)
        restore_ms = float(getattr(self, "_perf_restore_ms", 0.0) or 0.0)
        refresh_ms = float(getattr(self, "_last_deferred_refresh_ms", 0.0) or 0.0)
        ready_ms = float(getattr(self, "_perf_ready_ms", 0.0) or 0.0)
        scope = str(getattr(self, "_perf_last_scope", "init") or "init")
        pending = bool(getattr(self, "_deferred_ui_refresh_pending", False))
        stage = int(getattr(self, "_deferred_ui_refresh_stage", -1) or -1)
        if pending and stage >= 0:
            stage_text = f"Phase {stage + 1}/3 läuft"
        elif ready_ms > 0.0:
            stage_text = f"bereit nach {ready_ms:.1f} ms"
        else:
            stage_text = "Messung vorbereitet"
        self.lbl_perf_status.setText(
            f"AETERNA Ladeprofil: Build {build_ms:.1f} ms • Restore {restore_ms:.1f} ms • letzter UI-Refresh {refresh_ms:.1f} ms • {scope} • {stage_text}"
        )
        if hasattr(self, "lbl_perf_hint"):
            self.lbl_perf_hint.setText(
                "Nur lokale AETERNA-Messung: sichtbar gemacht wurden Build/Restore/Staged-Refresh. Kein Core-Profiling, kein Audio-Thread-Eingriff."
            )

    def _schedule_deferred_ui_refresh(self, reason: str = "runtime", delay_ms: int = 0, restart: bool = False) -> None:
        self._last_deferred_refresh_reason = str(reason or "runtime")
        if restart or not self._deferred_ui_refresh_pending:
            self._deferred_ui_refresh_stage = 0
            self._perf_refresh_started = time.perf_counter()
            self._perf_last_scope = self._last_deferred_refresh_reason
        self._deferred_ui_refresh_pending = True
        self._update_perf_status()
        try:
            self._deferred_refresh_timer.start(max(0, int(delay_ms)))
        except Exception:
            pass

    def _run_deferred_ui_refresh_stage(self) -> None:
        stage = int(getattr(self, "_deferred_ui_refresh_stage", 0) or 0)
        started = time.perf_counter()
        try:
            if stage == 0:
                self._update_formula_status()
                self._update_formula_info_line()
                self._update_formula_mod_summary()
                self._update_macro_ab_readability()
                self._update_signal_flow_card()
            elif stage == 1:
                self._update_web_template_card()
                self._update_snapshot_card()
                self._update_composer_summary()
                self._update_mod_rack_card()
            else:
                self._update_formula_preset_link()
                self._update_preset_quicklist()
                self._update_preset_snapshot_quicklaunchs()
                self._update_phase3_summary()
                self._update_mod_rack_card()
                self._update_signal_flow_card()
                self._deferred_ui_refresh_pending = False
        finally:
            self._last_deferred_refresh_ms = (time.perf_counter() - started) * 1000.0
            if not self._deferred_ui_refresh_pending:
                self._perf_ready_ms = (time.perf_counter() - float(getattr(self, "_perf_refresh_started", time.perf_counter()))) * 1000.0
            try:
                if hasattr(self, "lbl_status"):
                    self.lbl_status.setToolTip(
                        f"AETERNA staged init aktiv • letzter UI-Refresh {self._last_deferred_refresh_ms:.1f} ms • Phase {stage + 1}/3 • {self._last_deferred_refresh_reason}"
                    )
            except Exception:
                pass
            self._update_perf_status()
        if self._deferred_ui_refresh_pending:
            self._deferred_ui_refresh_stage = min(2, stage + 1)
            try:
                self._deferred_refresh_timer.start(18 if stage == 0 else 36)
            except Exception:
                self._deferred_ui_refresh_pending = False
                self._update_perf_status()

    def _automation_target_group_map(self) -> list[tuple[str, list[str]]]:
        return [
            ("Klang", ["morph", "tone", "gain", "release"]),
            ("Raum/Bewegung", ["space", "motion", "cathedral", "drift"]),
            ("Modulation", ["chaos", "lfo1_rate", "lfo2_rate", "mseg_rate"]),
            ("Web", ["mod1_amount", "mod2_amount"]),
            ("Filter", ["filter_cutoff", "filter_resonance"]),
            ("Pitch/Timbre", ["pitch", "shape", "pulse_width"]),
            ("Drive/Feedback", ["drive", "feedback"]),
        ]

    def _automation_ready_group_map(self) -> list[tuple[str, list[str]]]:
        return [
            ("Direkt auf Knobs", ["morph", "tone", "gain", "release", "space", "motion", "cathedral", "drift", "filter_cutoff", "filter_resonance"]),
            ("Modulations-Rates", ["lfo1_rate", "lfo2_rate", "mseg_rate"]),
            ("Depth/Amounts", ["chaos", "mod1_amount", "mod2_amount", "drive", "feedback"]),
            ("Pitch/Timbre", ["pitch", "shape", "pulse_width"]),
        ]

    def _set_phase3_automation_group_labels(self, groups: list[dict]) -> None:
        labels = getattr(self, "_phase3_group_labels", {}) or {}
        label_map = self._automation_label_map()
        for title, label in labels.items():
            text = f"{title}: –"
            for grp in groups:
                if str(grp.get("title") or "") == str(title):
                    entries = [str(item.get("key") or "") for item in grp.get("entries", [])]
                    nice = ", ".join(label_map.get(x, x.replace("_", " ").title()).replace("AETERNA ", "") for x in entries[:4]) if entries else "–"
                    text = f"{title}: {nice}"
                    break
            try:
                label.setText(text)
            except Exception:
                pass

    def _update_automation_target_card(self) -> None:
        try:
            label_map = self._automation_label_map()
            if hasattr(self, "lbl_automation_target_card"):
                lines = []
                for title, keys in self._automation_target_group_map():
                    names = [label_map.get(k, f"AETERNA {k}").replace("AETERNA ", "") for k in keys]
                    lines.append(f"{title}: " + " • ".join(names))
                self.lbl_automation_target_card.setText("\n".join(lines))
            if hasattr(self, "lbl_automation_target_hint"):
                self.lbl_automation_target_hint.setText(
                    "Sicher für spätere Automation: stabile Knobs sowie Rate/Amount-Ziele. "
                    "Nicht als Ziel gedacht: flüchtige UI-Zustände oder rohe interne LFO-/Phasenwerte."
                )
            if hasattr(self, "lbl_automation_ready_card"):
                ready_lines = []
                for title, keys in self._automation_ready_group_map():
                    names = [label_map.get(k, f"AETERNA {k}").replace("AETERNA ", "") for k in keys]
                    ready_lines.append(f"{title}: " + " • ".join(names))
                self.lbl_automation_ready_card.setText("\n".join(ready_lines))
            if hasattr(self, "lbl_automation_ready_hint"):
                self.lbl_automation_ready_hint.setText(
                    "Bereits lokal freigegeben: Rechtsklick auf einen AETERNA-Knob → 'Show Automation in Arranger'. "
                    "Automation = stabile Knobs/Rate/Amount. Modulation selbst weiter über LFO/MSEG/Chaos/Formel."
                )
        except Exception:
            pass

    def _update_phase3_preset_ab_summary(self) -> None:
        try:
            if not hasattr(self, "lbl_phase3_preset_ab"):
                return
            have_a = "ja" if isinstance(self._preset_ab_slots.get("A"), dict) else "nein"
            have_b = "ja" if isinstance(self._preset_ab_slots.get("B"), dict) else "nein"
            compare = "AN" if bool(self._preset_ab_compare_active) else "aus"
            self.lbl_phase3_preset_ab.setText(f"Preset A/B: A {have_a} • B {have_b} • Compare {compare}")
        except Exception:
            pass
    def _default_preset_metadata(self, preset_name: str) -> dict:
        name = str(preset_name or self.engine.get_preset_name() or "Init Patch").strip() or "Init Patch"
        defaults = {
            "Kathedrale": {"category": "sakral", "character": "breit", "note": "weite Hallräume und ruhige Bewegung"},
            "Schloss": {"category": "ambient", "character": "hell", "note": "klarer Raum mit edler Präsenz"},
            "Terrain": {"category": "organisch", "character": "rau", "note": "erdige Bewegung und modulare Kontur"},
            "Chaos": {"category": "chaos", "character": "rau", "note": "wilde Modulation für lebendige Texturen"},
            "Orgel der Zukunft": {"category": "sakral", "character": "hell", "note": "orgelartig mit futuristischem Obertonbild"},
            "Hofmusik": {"category": "ambient", "character": "weich", "note": "dezenter, höfischer Grundklang"},
            "Wolken-Chor": {"category": "organisch", "character": "breit", "note": "choral und luftig"},
            "Experiment": {"category": "experimentell", "character": "beweglich", "note": "freies Testfeld für Formeln"},
            "Web Chapel": {"category": "sakral", "character": "beweglich", "note": "webartige Modulation mit Raumtiefe"},
            "Kristall Bach": {"category": "sakral", "character": "hell", "note": "klarer Bach-naher Glasorgelklang", "tags": ["glas", "bach", "kristall"], "favorite": True},
            "Bach Glas": {"category": "sakral", "character": "hell", "note": "fein, gläsern und chorartig", "tags": ["bach", "glas", "chor"], "favorite": True},
            "Celesta Chapel": {"category": "ambient", "character": "hell", "note": "celestaartige Kapellenfarbe mit sanftem Raum", "tags": ["celesta", "kapelle", "klar"]},
            "Choral Crystal": {"category": "sakral", "character": "breit", "note": "breiter Kristallchor mit ruhiger Bewegung", "tags": ["chor", "kristall", "sakral"]},
            "Abendmanual": {"category": "sakral", "character": "weich", "note": "sanftes Abendmanual mit langem Nachhall", "tags": ["manual", "abend", "orgel"]},
            "Init Patch": {"category": "experimentell", "character": "weich", "note": "neutraler Startpunkt"},
        }
        meta = defaults.get(name, {"category": "experimentell", "character": "weich", "note": "lokales Benutzerpreset"})
        return {
            "category": str(meta.get("category") or "experimentell"),
            "character": str(meta.get("character") or "weich"),
            "note": str(meta.get("note") or ""),
            "tags": list(meta.get("tags") or []),
            "favorite": bool(meta.get("favorite", False)),
        }

    def _preset_quick_candidates(self) -> list[str]:
        preferred = [
            "Kristall Bach", "Bach Glas", "Kathedrale", "Celesta Chapel",
            "Choral Crystal", "Abendmanual", "Orgel der Zukunft", "Web Chapel",
            "Wolken-Chor", "Schloss", "Terrain", "Chaos", "Experiment", "Init Patch",
        ]
        names = []
        try:
            if hasattr(self, "cmb_preset"):
                names = [str(self.cmb_preset.itemText(i) or "").strip() for i in range(self.cmb_preset.count())]
        except Exception:
            names = []
        ordered = []
        seen = set()
        for name in preferred + names:
            txt = str(name or "").strip()
            if not txt or txt in seen:
                continue
            seen.add(txt)
            ordered.append(txt)
        return ordered

    def _preset_matches_quick_filter(self, preset_name: str, filter_name: str) -> bool:
        name = str(preset_name or "").strip()
        flt = str(filter_name or "alle").strip().lower()
        meta = self._preset_metadata_for_display(name)
        category = str(meta.get("category") or "").strip().lower()
        character = str(meta.get("character") or "").strip().lower()
        tags = [str(t).strip().lower() for t in list(meta.get("tags") or []) if str(t).strip()]
        hay = " ".join([name.lower(), category, character] + tags)
        if flt in ("", "alle"):
            return True
        if flt == "favoriten":
            return bool(meta.get("favorite", False))
        if flt == "sakral":
            return "sakral" in hay or "kapelle" in hay or "orgel" in hay or "chor" in hay
        if flt == "kristall":
            return "kristall" in hay or "glas" in hay or "celesta" in hay or "klar" in hay
        if flt == "drone":
            return "drone" in hay or "abend" in hay or "weich" in hay or "breit" in hay
        return True

    def _preset_marker_text(self, preset_name: str, compact: bool = False) -> str:
        meta = self._preset_metadata_for_display(preset_name)
        category = str(meta.get("category") or "-").strip() or "-"
        character = str(meta.get("character") or "-").strip() or "-"
        if compact:
            category_map = {
                "sakral": "Sakral",
                "ambient": "Ambient",
                "organisch": "Organisch",
                "chaos": "Chaos",
                "experimentell": "Experiment",
                "glitch": "Glitch",
            }
            character_map = {
                "hell": "Hell",
                "weich": "Weich",
                "breit": "Breit",
                "beweglich": "Belebt",
                "dunkel": "Dunkel",
                "rau": "Rau",
            }
            category = category_map.get(category.lower(), category.title())
            character = character_map.get(character.lower(), character.title())
        return f"{category} • {character}"

    def _preset_metadata_for_display(self, preset_name: str) -> dict:
        name = str(preset_name or "").strip() or "Init Patch"
        try:
            current = str(self.cmb_preset.currentText() or "").strip() if hasattr(self, "cmb_preset") else ""
        except Exception:
            current = ""
        if name and current and name == current and hasattr(self, "cmb_preset_category"):
            try:
                return self._preset_metadata_from_ui()
            except Exception:
                pass
        return self._default_preset_metadata(name)

    def _preset_library_entries(self, filter_name: str = "Alle") -> list[dict]:
        entries: list[dict] = []
        for name in self._preset_quick_candidates():
            if not self._preset_matches_quick_filter(name, filter_name):
                continue
            meta = self._preset_metadata_for_display(name)
            entries.append({
                "name": str(name or "Init Patch").strip() or "Init Patch",
                "category": str(meta.get("category") or "experimentell").strip() or "experimentell",
                "character": str(meta.get("character") or "weich").strip() or "weich",
                "favorite": bool(meta.get("favorite", False)),
                "tags": [str(t).strip() for t in list(meta.get("tags") or []) if str(t).strip()],
            })
        return entries

    def _preset_library_group_lines(self, entries: list[dict], key: str, title: str, order: list[str], limit_groups: int = 3, limit_names: int = 3) -> list[str]:
        buckets: dict[str, list[str]] = {}
        for entry in entries:
            bucket = str(entry.get(key) or "-").strip() or "-"
            buckets.setdefault(bucket, []).append(str(entry.get("name") or "Init Patch"))
        if not buckets:
            return [f"{title}: –"]
        ordered_keys: list[str] = []
        seen: set[str] = set()
        for value in order:
            txt = str(value or "").strip()
            if txt and txt in buckets and txt not in seen:
                ordered_keys.append(txt)
                seen.add(txt)
        for value, names in sorted(buckets.items(), key=lambda item: (-len(item[1]), str(item[0]).lower())):
            if value not in seen:
                ordered_keys.append(value)
                seen.add(value)
        lines: list[str] = []
        for bucket in ordered_keys[:max(1, int(limit_groups))]:
            names = buckets.get(bucket, [])
            preview = ", ".join(names[:max(1, int(limit_names))])
            extra = " …" if len(names) > max(1, int(limit_names)) else ""
            lines.append(f"{title} {bucket} ({len(names)}): {preview}{extra}")
        return lines

    def _update_preset_library_compact(self) -> None:
        try:
            if not hasattr(self, "lbl_preset_library_compact"):
                return
            filter_name = str(self.cmb_preset_quick_filter.currentText() or "Alle") if hasattr(self, "cmb_preset_quick_filter") else "Alle"
            entries = self._preset_library_entries(filter_name)
            category_lines = self._preset_library_group_lines(
                entries,
                "category",
                "Kategorie",
                ["sakral", "ambient", "organisch", "chaos", "experimentell", "glitch"],
            )
            character_lines = self._preset_library_group_lines(
                entries,
                "character",
                "Charakter",
                ["hell", "weich", "breit", "beweglich", "dunkel", "rau"],
            )
            self.lbl_preset_library_compact.setText(
                f"Bibliothek kompakt • Filter {filter_name} • {len(entries)} Presets\n"
                + "\n".join(category_lines + character_lines)
            )
            if hasattr(self, "lbl_preset_library_focus"):
                current = str(self.cmb_preset.currentText() or "Init Patch").strip() if hasattr(self, "cmb_preset") else "Init Patch"
                meta = self._preset_metadata_for_display(current)
                hearing = self._format_hearing_tags(self._preset_hearing_tags(current), prefix="Hörbild")
                tags = ", ".join([str(t).strip() for t in list(meta.get("tags") or []) if str(t).strip()][:3]) or "ohne Tags"
                fav = "★ Favorit" if bool(meta.get("favorite", False)) else "kein Favorit"
                combo_tip = self._preset_combo_tip_line(current)
                self.lbl_preset_library_focus.setText(
                    f"Aktiv: {current} • {meta.get('category', '-')} / {meta.get('character', '-')} • {fav} • Tags: {tags} • {hearing}\n{combo_tip}"
                )
        except Exception:
            pass

    def _on_preset_quick_filter_changed(self, _text: str) -> None:
        self._update_preset_quicklist()

    def _dedupe_hearing_tags(self, tags: list[str], limit: int = 4) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            txt = str(tag or '').strip().lower()
            if not txt or txt in seen:
                continue
            seen.add(txt)
            out.append(txt)
            if len(out) >= max(1, int(limit)):
                break
        return out

    def _hearing_tags_from_text(self, *parts: str, limit: int = 4) -> list[str]:
        hay = ' '.join(str(p or '').strip().lower() for p in parts if str(p or '').strip())
        tags: list[str] = []
        if any(x in hay for x in ('sakral', 'bach', 'orgel', 'chor', 'kapelle', 'kathedrale', 'cathedral', 'chapel')):
            tags.append('sakral')
        if any(x in hay for x in ('kristall', 'glas', 'glass', 'celesta', 'crystal')):
            tags.append('kristallin')
        if any(x in hay for x in ('klar', 'hell', 'clean', 'clear', 'luftig', 'offen')):
            tags.append('klar')
        if any(x in hay for x in ('getragen', 'lang', 'abend', 'drone', 'breit', 'ruhig', 'ruhe', 'slow')):
            tags.append('getragen')
        if any(x in hay for x in ('belebt', 'lebendig', 'atem', 'beweg', 'motion', 'chaos', 'glitch', 'experiment')):
            tags.append('belebt')
        if any(x in hay for x in ('dunkel', 'warm', 'tief', 'nacht')):
            tags.append('dunkel')
        if any(x in hay for x in ('weich', 'sanft', 'soft')):
            tags.append('weich')
        if any(x in hay for x in ('organisch', 'terrain', 'wolken', 'schweb')):
            tags.append('organisch')
        if not tags:
            tags.append('klar')
        return self._dedupe_hearing_tags(tags, limit=limit)

    def _format_hearing_tags(self, tags: list[str], prefix: str = 'Hörhinweise') -> str:
        compact = self._dedupe_hearing_tags(tags)
        return f"{prefix}: {' • '.join(compact)}" if compact else f"{prefix}: neutral"

    def _preset_hearing_tags(self, preset_name: str) -> list[str]:
        name = str(preset_name or '').strip()
        meta = self._default_preset_metadata(name)
        return self._hearing_tags_from_text(
            name,
            str(meta.get('category') or ''),
            str(meta.get('character') or ''),
            str(meta.get('note') or ''),
            ' '.join(str(t) for t in list(meta.get('tags') or []) if str(t).strip()),
        )

    def _formula_suggestion_hearing_tags(self, title: str, hint: str = '', reason: str = '', preset_name: str = '') -> list[str]:
        return self._hearing_tags_from_text(title, hint, reason, preset_name)

    def _formula_link_preset_for_name(self, preset_name: str) -> dict:
        name = str(preset_name or self.engine.get_preset_name() or "Init Patch").strip() or "Init Patch"
        meta = self._preset_metadata_for_display(name)
        category = str(meta.get("category") or "").strip().lower()
        character = str(meta.get("character") or "").strip().lower()
        tags = [str(t).strip().lower() for t in list(meta.get("tags") or []) if str(t).strip()]
        note = str(meta.get("note") or "").strip().lower()
        hay = " ".join([name.lower(), category, character, note] + tags)
        title = "Warm Start"
        reason = "neutraler Start"
        if any(x in hay for x in ["chaos", "glitch", "experiment"]):
            title, reason = "Chaos", "passt zu bewegten/experimentellen Presets"
        elif any(x in hay for x in ["drone", "abend", "breit", "dunkel"]):
            title, reason = "Drone", "passt zu getragenen Flächen und Abendfarben"
        elif any(x in hay for x in ["organisch", "terrain", "wolken", "weich"]):
            title, reason = "Organisch", "passt zu weichen organischen Bewegungen"
        elif any(x in hay for x in ["sakral", "bach", "orgel", "chor", "kapelle", "kathedrale"]):
            title, reason = "Sakral", "passt zu sakralen/orgelartigen Presets"
        elif any(x in hay for x in ["kristall", "glas", "celesta", "klar", "hell"]):
            title, reason = "Warm Start", "passt zu klaren gläsernen Startklängen"
        preset_map = {t: {"title": t, "hint": h, "formula": f} for t, h, f in FORMULA_ONBOARDING_PRESETS}
        data = dict(preset_map.get(title, preset_map.get("Warm Start", {"title": "Warm Start", "hint": "", "formula": DEFAULT_FORMULA})))
        data["reason"] = reason
        data["preset_name"] = name
        return data

    def _formula_link_preset_for_current_preset(self) -> dict:
        name = str(self.cmb_preset.currentText() or self.engine.get_preset_name() or "Init Patch").strip() or "Init Patch"
        return self._formula_link_preset_for_name(name)

    def _web_template_tip_for_preset(self, preset_name: str, formula_title: str = "") -> dict:
        name = str(preset_name or "Init Patch").strip() or "Init Patch"
        meta = self._preset_metadata_for_display(name)
        category = str(meta.get("category") or "").strip().lower()
        character = str(meta.get("character") or "").strip().lower()
        note = str(meta.get("note") or "").strip().lower()
        tags = [str(t).strip().lower() for t in list(meta.get("tags") or []) if str(t).strip()]
        formula_key = str(formula_title or "").strip().lower()
        hay = " ".join([name.lower(), category, character, note, formula_key] + tags)
        template = "Langsam"
        intensity = "Mittel"
        reason = "ruhiger sicherer Start für AETERNA-Web"
        if any(x in hay for x in ["chaos", "glitch", "experiment", "lebendig", "beweglich"]):
            template, intensity, reason = "Lebendig", "Präsent", "passt zu bewegter oder experimenteller Energie"
        elif any(x in hay for x in ["organisch", "terrain", "wolken", "weich", "drift"]):
            template, intensity, reason = "Organisch", "Mittel", "passt zu weichen organischen Schwebungen"
        elif any(x in hay for x in ["sakral", "bach", "orgel", "chor", "kapelle", "kathedrale", "cathedral", "chapel"]):
            template, intensity, reason = "Sakral", "Mittel", "passt zu sakraler Weite und klaren Flächen"
        elif any(x in hay for x in ["kristall", "glas", "celesta", "klar", "hell"]):
            template, intensity, reason = "Langsam", "Sanft", "hält gläserne Presets offen und ruhig"
        elif any(x in hay for x in ["drone", "abend", "breit", "dunkel", "getragen"]):
            template, intensity, reason = "Langsam", "Mittel", "trägt lange Flächen ohne Unruhe"
        return {"title": template, "intensity": intensity, "reason": reason, "preset_name": name}

    def _preset_combo_tip_for_name(self, preset_name: str) -> dict:
        formula = self._formula_link_preset_for_name(preset_name)
        web = self._web_template_tip_for_preset(preset_name, str(formula.get("title") or ""))
        hearing = self._dedupe_hearing_tags(
            self._preset_hearing_tags(preset_name)
            + self._formula_suggestion_hearing_tags(
                str(formula.get("title") or ""),
                str(formula.get("hint") or ""),
                str(formula.get("reason") or ""),
                str(preset_name or ""),
            ),
            limit=5,
        )
        return {
            "preset_name": str(preset_name or "Init Patch").strip() or "Init Patch",
            "formula_title": str(formula.get("title") or "Warm Start"),
            "formula_reason": str(formula.get("reason") or ""),
            "web_title": str(web.get("title") or "Langsam"),
            "web_intensity": str(web.get("intensity") or "Mittel"),
            "web_reason": str(web.get("reason") or ""),
            "hearing": hearing,
        }

    def _preset_combo_tip_line(self, preset_name: str, compact: bool = False) -> str:
        combo = self._preset_combo_tip_for_name(preset_name)
        formula_title = str(combo.get("formula_title") or "Warm Start")
        web_title = str(combo.get("web_title") or "Langsam")
        intensity = str(combo.get("web_intensity") or "Mittel")
        reason = str(combo.get("web_reason") or combo.get("formula_reason") or "").strip()
        if compact:
            return f"Formel {formula_title} • Web {web_title}/{intensity}"
        return f"Startweg: Formel {formula_title} • Web {web_title}/{intensity}" + (f" — {reason}" if reason else "")

    def _load_linked_formula_preset(self) -> None:
        try:
            data = self._formula_link_preset_for_current_preset()
            self._load_formula_onboarding_preset(str(data.get("formula") or DEFAULT_FORMULA), str(data.get("title") or "Warm Start"))
            self._update_formula_preset_link()
        except Exception:
            pass

    def _update_formula_preset_link(self) -> None:
        try:
            if not hasattr(self, "lbl_formula_preset_link"):
                return
            data = self._formula_link_preset_for_current_preset()
            title = str(data.get("title") or "Warm Start")
            hint = str(data.get("hint") or "")
            reason = str(data.get("reason") or "")
            preset_name = str(data.get("preset_name") or self.cmb_preset.currentText() or "Init Patch")
            current = str(self.ed_formula.text() or "").strip() if hasattr(self, "ed_formula") else ""
            applied = str(getattr(self, "_formula_last_applied_text", "") or "").strip()
            suggested = str(data.get("formula") or "").strip()
            state = "passende Idee bereit"
            if suggested and current == suggested and current != applied:
                state = "passende Idee im Feld"
            elif suggested and applied == suggested:
                state = "passende Idee angewendet"
            elif current and current == applied:
                state = "eigene Formel angewendet"
            elif current:
                state = "eigene Formel im Feld"
            self.lbl_formula_preset_link.setText(
                f"Preset→Formel: {preset_name} → {title} • {state} • {reason}"
                + (f" — {hint}" if hint else "")
            )
            if hasattr(self, "lbl_formula_preset_hearing"):
                hearing = self._formula_suggestion_hearing_tags(title, hint, reason, preset_name)
                self.lbl_formula_preset_hearing.setText(self._format_hearing_tags(hearing))
            if hasattr(self, "btn_formula_preset_link_load"):
                self.btn_formula_preset_link_load.setText(f"{title} laden")
                hearing_txt = self._format_hearing_tags(self._formula_suggestion_hearing_tags(title, hint, reason, preset_name), prefix='Hörbild')
                self.btn_formula_preset_link_load.setToolTip(f"Passende Formelidee für Preset '{preset_name}' laden\n{hearing_txt}")
        except Exception:
            pass

    def _preset_metadata_from_ui(self) -> dict:
        tags = [t.strip() for t in str(self.ed_preset_tags.text() or "").split(",") if str(t).strip()]
        deduped = []
        seen = set()
        for tag in tags:
            low = tag.lower()
            if low in seen:
                continue
            seen.add(low)
            deduped.append(tag[:24])
            if len(deduped) >= 8:
                break
        return {
            "category": str(self.cmb_preset_category.currentText() or "experimentell"),
            "character": str(self.cmb_preset_character.currentText() or "weich"),
            "note": str(self.ed_preset_note.text() or "").strip(),
            "tags": deduped,
            "favorite": bool(self.chk_preset_favorite.isChecked()),
        }

    def _apply_preset_metadata_to_ui(self, metadata: dict | None, persist: bool = False) -> None:
        meta = metadata if isinstance(metadata, dict) else {}
        defaults = self._default_preset_metadata(self.cmb_preset.currentText())
        category = str(meta.get("category") or defaults.get("category") or "experimentell")
        character = str(meta.get("character") or defaults.get("character") or "weich")
        note = str(meta.get("note") or defaults.get("note") or "")
        tags_raw = meta.get("tags") or defaults.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if str(t).strip()]
        else:
            tags = [str(t).strip() for t in list(tags_raw or []) if str(t).strip()]
        favorite = bool(meta.get("favorite", defaults.get("favorite", False)))
        blockers = self._make_signal_blockers([
            getattr(self, "cmb_preset_category", None),
            getattr(self, "cmb_preset_character", None),
            getattr(self, "ed_preset_note", None),
            getattr(self, "ed_preset_tags", None),
            getattr(self, "chk_preset_favorite", None),
        ])
        try:
            idx = self.cmb_preset_category.findText(category)
            self.cmb_preset_category.setCurrentIndex(idx if idx >= 0 else 0)
            idx = self.cmb_preset_character.findText(character)
            self.cmb_preset_character.setCurrentIndex(idx if idx >= 0 else 0)
            self.ed_preset_note.setText(note)
            self.ed_preset_tags.setText(", ".join(tags))
            self.chk_preset_favorite.setChecked(favorite)
            self.engine.set_preset_metadata({"category": category, "character": character, "note": note, "tags": tags, "favorite": favorite})
            self._update_preset_metadata_badges()
        except Exception:
            pass
        finally:
            blockers.clear()
        if persist and not self._restoring_state:
            self._persist_instrument_state()

    def _on_preset_metadata_changed(self) -> None:
        try:
            self.engine.set_preset_metadata(self._preset_metadata_from_ui())
            self._update_preset_metadata_badges()
            self._update_phase3_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _update_preset_metadata_badges(self) -> None:
        try:
            if not hasattr(self, "lbl_preset_meta_badges"):
                return
            meta = self._preset_metadata_from_ui()
            badges = []
            if bool(meta.get("favorite", False)):
                badges.append("★ Favorit")
            category = str(meta.get("category") or "").strip()
            if category:
                badges.append(f"Kategorie: {category}")
            character = str(meta.get("character") or "").strip()
            if character:
                badges.append(f"Charakter: {character}")
            for tag in list(meta.get("tags") or [])[:4]:
                tag_txt = str(tag).strip()
                if tag_txt:
                    badges.append(f"#{tag_txt}")
            note = str(meta.get("note") or "").strip()
            if note:
                short_note = note[:44] + ("…" if len(note) > 44 else "")
                badges.append(f"Notiz: {short_note}")
            self.lbl_preset_meta_badges.setText("  •  ".join(badges) if badges else "Keine lokalen Preset-Metadaten gesetzt")
            self._update_preset_quicklist()
            self._update_preset_library_compact()
            self._update_formula_preset_link()
        except Exception:
            pass

    def _update_preset_quicklist(self) -> None:
        try:
            if not hasattr(self, "lbl_preset_quicklist"):
                return
            current = str(self.cmb_preset.currentText() or "Init Patch").strip() or "Init Patch"
            meta = self._preset_metadata_from_ui()
            fav = bool(meta.get("favorite", False))
            tags = [str(t).strip() for t in list(meta.get("tags") or []) if str(t).strip()]
            tag_preview = ", ".join(tags[:3]) if tags else "ohne Tags"
            filter_name = str(self.cmb_preset_quick_filter.currentText() or "Alle") if hasattr(self, "cmb_preset_quick_filter") else "Alle"
            candidates = [n for n in self._preset_quick_candidates() if self._preset_matches_quick_filter(n, filter_name)]
            fallback = self._preset_quick_candidates()
            visible = (candidates or fallback)[:4]
            visible_lines = []
            marker_lines = []
            for i, btn in enumerate(getattr(self, "_preset_quick_buttons", [])):
                if i < len(visible):
                    name = visible[i]
                    hearing = self._preset_hearing_tags(name)
                    display_meta = self._preset_metadata_for_display(name)
                    marker = self._preset_marker_text(name, compact=True)
                    btn.setText(name)
                    combo_tip = self._preset_combo_tip_for_name(name)
                    combo_line = self._preset_combo_tip_line(name)
                    combo_hearing = self._format_hearing_tags(list(combo_tip.get('hearing') or []), prefix='Start-Hörbild')
                    btn.setToolTip(
                        f"Lokales AETERNA-Kurzpreset: {name}\n"
                        f"Direktmarker: {marker}\n"
                        f"Kategorie: {display_meta.get('category', '-')} • Charakter: {display_meta.get('character', '-')}\n"
                        f"{self._format_hearing_tags(hearing, prefix='Hörbild')}\n"
                        f"{combo_line}\n"
                        f"{combo_hearing}"
                    )
                    btn.setEnabled(True)
                    self._rebind_button_click(btn, lambda _=False, pp=name: self._apply_preset(pp, persist=True))
                    visible_lines.append(
                        f"• [{marker}] {name} — {' • '.join(hearing)} • {self._preset_combo_tip_line(name, compact=True)}"
                    )
                    marker_lines.append(f"{name}: {marker}")
                else:
                    btn.setText("–")
                    btn.setToolTip("Kein Preset für diesen Filter")
                    btn.setEnabled(False)
            shown = "\n".join(visible_lines) if visible_lines else "• keine Treffer"
            if hasattr(self, "lbl_preset_quick_markers"):
                marker_text = " • ".join(marker_lines) if marker_lines else "keine Direktmarker aktiv"
                self.lbl_preset_quick_markers.setText(f"Direktmarker: {marker_text}")
            self.lbl_preset_quicklist.setText(
                f"Kurzliste: Filter {filter_name} • aktuell: {current}\n{shown}"
            )
            status = "Favorit" if fav else "kein Favorit"
            active_marker = self._preset_marker_text(current, compact=True)
            active_hearing = self._format_hearing_tags(self._preset_hearing_tags(current), prefix='Hörhinweise aktiv')
            self.lbl_preset_quick_status.setText(f"Aktiv: {current} • Marker: {active_marker} • {status} • Tags: {tag_preview} • {active_hearing}")
            if hasattr(self, "lbl_preset_combo_tips"):
                active_combo = self._preset_combo_tip_line(current)
                shortcut_combo = " • ".join(
                    f"{name}: {self._preset_combo_tip_line(name, compact=True)}" for name in visible[:3]
                ) or "keine lokalen Kombitipps"
                self.lbl_preset_combo_tips.setText(
                    f"Preset→Formel/Web: {active_combo}\nKurzwege: {shortcut_combo}"
                )
            self._update_preset_library_compact()
            self._update_preset_snapshot_quicklaunchs()
        except Exception:
            pass

    def _on_formula_text_changed(self) -> None:
        try:
            if not getattr(self, "_formula_internal_change", False):
                current = str(self.ed_formula.text() or "").strip()
                applied = str(getattr(self, "_formula_last_applied_text", "") or "").strip()
                loaded = str(getattr(self, "_formula_last_loaded_example_text", "") or "").strip()
                loaded_title = str(getattr(self, "_formula_last_loaded_example_title", "") or "").strip()
                if loaded and current == loaded and current != applied:
                    self._formula_status_note = f"Beispiel '{loaded_title or 'Start'}' geladen, noch nicht angewendet"
                elif current == applied:
                    self._formula_status_note = "Formel angewendet"
                elif current:
                    self._formula_status_note = "Formel manuell geändert, noch nicht angewendet"
                else:
                    self._formula_status_note = "Leeres Feld – Fallback wird beim Anwenden genutzt"
            self._update_formula_mod_summary()
            self._update_formula_info_line()
            self._update_formula_preset_link()
        except Exception:
            pass


    def _sync_engine_to_ui_from_current_state(self) -> None:
        blockers = self._make_signal_blockers(self._restore_signal_widgets())
        self.setUpdatesEnabled(False)
        try:
            self.cmb_mode.setCurrentText(str(self.engine.get_param("mode", "formula") or "formula"))
            self._formula_internal_change = True
            self.ed_formula.setText(str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA))
            self._formula_internal_change = False
            self._formula_last_applied_text = str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA)
            self._formula_status_note = "Formel angewendet"
            self._update_formula_info_line()
            self._apply_preset_metadata_to_ui(self.engine.get_preset_metadata(), persist=False)
            for key, knob in self._knobs.items():
                try:
                    knob.setValueExternal(int(round(float(self.engine.get_param(key, 0.5)) * 100.0)))
                except Exception:
                    pass
            if hasattr(self, "chk_retrigger"):
                try:
                    self.chk_retrigger.setChecked(float(self.engine.get_param("retrigger", 1.0) or 1.0) >= 0.5)
                except Exception:
                    pass
            self._refresh_all_knob_automation_tooltips()
            self._update_automation_quick_status()
            for key, combo in self._combo_params.items():
                try:
                    combo.setCurrentText(str(self.engine.get_param(key, combo.currentText())))
                except Exception:
                    pass
            self._apply_preset_metadata_to_ui(self.engine.get_preset_metadata(), persist=False)
            self._update_formula_status()
            self._update_formula_info_line()
            self._update_phase3_summary()
            self._update_mod_rack_card()
            self._update_signal_flow_card()
            self.mod_preview.update()
            self.scope.update()
            # Wavetable UI sync (v0.0.20.657)
            self._update_wt_display()
            if hasattr(self, '_wt_section') and self._wt_section is not None:
                try:
                    self._wt_section.setVisible(str(self.engine.get_param("mode", "formula")) == "wavetable")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            blockers.clear()
            self.setUpdatesEnabled(True)
        self._schedule_deferred_ui_refresh(reason="sync-current-state", delay_ms=0, restart=True)

    def _store_preset_ab_slot(self, slot: str) -> None:
        slot = str(slot or "A").upper()
        try:
            self._preset_ab_slots[slot] = self.engine.export_state()
            self._preset_ab_compare_active = False
            self._update_phase3_preset_ab_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _recall_preset_ab_slot(self, slot: str) -> None:
        slot = str(slot or "A").upper()
        state = self._preset_ab_slots.get(slot)
        if not isinstance(state, dict):
            return
        try:
            self.engine.import_state(state)
            self._preset_ab_compare_active = False
            self._sync_engine_to_ui_from_current_state()
            preset_name = str(self.engine.get_preset_name() or "")
            if preset_name:
                self.cmb_preset.setCurrentText(preset_name)
            self._update_phase3_preset_ab_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _toggle_preset_ab_compare(self) -> None:
        target = "B" if not self._preset_ab_compare_active else "A"
        if not isinstance(self._preset_ab_slots.get(target), dict):
            target = "A" if target == "B" else "B"
        if not isinstance(self._preset_ab_slots.get(target), dict):
            return
        self._preset_ab_compare_active = (target == "B")
        self._recall_preset_ab_slot(target)
        self._preset_ab_compare_active = (target == "B")
        self._update_phase3_preset_ab_summary()

    def _update_phase3_summary(self) -> None:
        try:
            if not hasattr(self, "lbl_phase3_summary"):
                return
            summary = self.engine.get_state_summary()
            self.lbl_phase3_summary.setText(
                f"State v{summary.get('state_schema_version', AETERNA_STATE_SCHEMA_VERSION)} • Preset v{summary.get('preset_schema_version', AETERNA_PRESET_SCHEMA_VERSION)} • "
                f"Mode {summary.get('mode', 'formula')} • Formel {'OK' if summary.get('formula_ok') else 'FEHLER'}"
            )
            self.lbl_phase3_preset.setText(
                f"Preset: {summary.get('preset_name', '-')} • Parameter {summary.get('param_count', 0)} • "
                f"MSEG Punkte {summary.get('mseg_point_count', 0)} / Segmente {summary.get('mseg_segment_count', 0)}"
            )
            meta = summary.get("preset_metadata") if isinstance(summary.get("preset_metadata"), dict) else {}
            self.lbl_phase3_metadata.setText(
                f"Meta: Kategorie {meta.get('category', '-')} • Charakter {meta.get('character', '-')} • Favorit {'ja' if bool(meta.get('favorite', False)) else 'nein'} • Tags {', '.join(meta.get('tags') or []) or '-'} • Notiz {meta.get('note', '-') or '-'}"
            )
            groups = self.engine.get_automation_groups()
            self.lbl_phase3_automation.setText("Automation-Ziele: klar gruppiert unten • lokal • ohne Core-Eingriff")
            self._set_phase3_automation_group_labels(groups)
            self._update_automation_target_card()
            self._update_phase3_preset_ab_summary()
            self._update_formula_mod_summary()
        except Exception:
            pass

    def _apply_init_patch(self) -> None:
        try:
            self.engine.apply_init_patch()
            self.cmb_preset.setCurrentText("Kathedrale")
            self._apply_preset_metadata_to_ui(self._default_preset_metadata("Kathedrale"), persist=False)
            self._sync_engine_to_ui_from_current_state()
            self._persist_instrument_state()
        except Exception:
            pass

    def _restore_current_preset_defaults(self) -> None:
        try:
            restored = self.engine.restore_preset_defaults(self.cmb_preset.currentText())
            if restored:
                self.cmb_preset.setCurrentText(restored)
            self._apply_preset_metadata_to_ui(self._default_preset_metadata(restored or self.cmb_preset.currentText()), persist=False)
            self._sync_engine_to_ui_from_current_state()
            self._persist_instrument_state()
        except Exception:
            pass

    def _composer_catalog_for_family(self, family: str) -> list[str]:
        fam = str(family or "").strip()
        if fam in AETERNA_WORLD_STYLE_GROUPS:
            return list(AETERNA_WORLD_STYLE_GROUPS.get(fam, ()))
        return list(AETERNA_WORLD_STYLES)

    def _preferred_composer_family_from_preset(self) -> str:
        try:
            meta = self._preset_metadata_for_display(str(self.cmb_preset.currentText() or ""))
            hay = " ".join([
                str(self.cmb_preset.currentText() or ""),
                str(meta.get("category") or ""),
                str(meta.get("character") or ""),
                str(meta.get("note") or ""),
            ]).lower()
            if any(x in hay for x in ("sakral", "bach", "chor", "orgel", "chapel", "kathedral", "kirche")):
                return "Sakral/Historisch"
            if any(x in hay for x in ("ambient", "drone", "film", "cinema", "weiche", "weich")):
                return "Klassik/Film/Ambient"
            if any(x in hay for x in ("chaos", "glitch", "noise", "ritual", "dark", "dunkel")):
                return "Dunkel/Experiment"
            if any(x in hay for x in ("kristall", "glas", "celesta", "klar")):
                return "Klassik/Film/Ambient"
        except Exception:
            pass
        return "Sakral/Historisch"

    def _roll_composer_style_mix(self) -> None:
        try:
            family = str(self.cmb_comp_family.currentText() or self._preferred_composer_family_from_preset() or "Sakral/Historisch")
            pool_a = self._composer_catalog_for_family(family) or list(AETERNA_WORLD_STYLES)
            meta = self._preset_metadata_for_display(str(self.cmb_preset.currentText() or ""))
            mood = " ".join([str(meta.get("category") or ""), str(meta.get("character") or ""), str(meta.get("note") or "")]).lower()
            if family == "Sakral/Historisch":
                pool_b = list(AETERNA_WORLD_STYLE_GROUPS.get("Klassik/Film/Ambient", ())) + ["Gregorianik", "Ambient", "Drone"]
            elif family == "Club/Electronic":
                pool_b = list(AETERNA_WORLD_STYLE_GROUPS.get("Dunkel/Experiment", ())) + ["Ambient", "IDM"]
            elif family == "Folk/World":
                pool_b = list(AETERNA_WORLD_STYLE_GROUPS.get("Klassik/Film/Ambient", ())) + ["World", "Ambient"]
            else:
                pool_b = list(AETERNA_WORLD_STYLES)
            rng = random.Random(int(self.spn_comp_seed.value()) ^ 0xA37F)
            style_a = rng.choice(pool_a) if pool_a else "Gregorianik"
            preferred = [x for x in pool_b if ("sakral" in mood and x in ("Gregorianik", "Kirchenmusik", "Gospel", "Ambient", "Drone")) or ("chaos" in mood and x in ("Glitch", "IDM", "Dark Ambient", "Experimental"))]
            style_b = rng.choice(preferred or pool_b or pool_a or ["Ambient"])
            self.cmb_comp_style_a.setCurrentText(str(style_a))
            self.cmb_comp_style_b.setCurrentText(str(style_b))
            self._update_composer_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _composer_phrase_profile(self) -> str:
        if hasattr(self, "cmb_comp_phrase"):
            return str(self.cmb_comp_phrase.currentText() or "Ausgewogen")
        return "Ausgewogen"

    def _composer_density_profile(self) -> str:
        if hasattr(self, "cmb_comp_density_profile"):
            return str(self.cmb_comp_density_profile.currentText() or "Mittel")
        return "Mittel"

    def _composer_phrase_factors(self) -> dict:
        name = self._composer_phrase_profile()
        return dict(AETERNA_COMPOSER_PHRASE_FACTORS.get(name) or AETERNA_COMPOSER_PHRASE_FACTORS["Ausgewogen"])

    def _composer_effective_density(self) -> float:
        base = float(self.spn_comp_density.value()) if hasattr(self, "spn_comp_density") else 0.62
        phrase_mul = float(self._composer_phrase_factors().get("density_mul", 1.0) or 1.0)
        profile_mul = float(AETERNA_COMPOSER_DENSITY_FACTORS.get(self._composer_density_profile(), 1.0) or 1.0)
        return max(0.05, min(1.0, base * phrase_mul * profile_mul))

    def _composer_params_from_ui(self) -> dict:
        return {
            "family": str(self.cmb_comp_family.currentText() or "Sakral/Historisch"),
            "style_a": str(self.cmb_comp_style_a.currentText() or "Gregorianik"),
            "style_b": str(self.cmb_comp_style_b.currentText() or "Ambient"),
            "context": str(self.cmb_comp_context.currentText() or "Gottesdienst"),
            "form": str(self.cmb_comp_form.currentText() or "Pad/Drone + Melodie"),
            "phrase_profile": self._composer_phrase_profile(),
            "density_profile": self._composer_density_profile(),
            "bars": int(self.spn_comp_bars.value()),
            "grid": float(AETERNA_COMPOSER_GRID_MAP.get(str(self.cmb_comp_grid.currentText() or "1/16"), 0.25)),
            "swing": float(self.spn_comp_swing.value()),
            "density": float(self.spn_comp_density.value()),
            "effective_density": float(self._composer_effective_density()),
            "hybrid": float(self.spn_comp_hybrid.value()),
            "seed": int(self.spn_comp_seed.value()),
            "parts": {
                "bass": bool(self.chk_comp_bass.isChecked()),
                "melody": bool(self.chk_comp_melody.isChecked()),
                "lead": bool(self.chk_comp_lead.isChecked()),
                "pad": bool(self.chk_comp_pad.isChecked()),
                "arp": bool(self.chk_comp_arp.isChecked()),
            },
        }

    def _composer_hash_seed(self) -> int:
        try:
            p = self._composer_params_from_ui()
            meta = self._preset_metadata_for_display(str(self.cmb_preset.currentText() or ""))
            material = "|".join([
                str(p.get("family") or ""),
                str(p.get("style_a") or ""),
                str(p.get("style_b") or ""),
                str(p.get("context") or ""),
                str(p.get("form") or ""),
                str(p.get("phrase_profile") or ""),
                str(p.get("density_profile") or ""),
                str(p.get("bars") or ""),
                str(p.get("grid") or ""),
                str(p.get("swing") or ""),
                str(p.get("density") or ""),
                str(p.get("hybrid") or ""),
                str(p.get("seed") or ""),
                str(self.cmb_preset.currentText() or ""),
                str(meta.get("category") or ""),
                str(meta.get("character") or ""),
                str(getattr(self, "_formula_last_loaded_example_title", "") or ""),
            ])
            digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
            return int(digest[:8], 16) & 0x7FFFFFFF
        except Exception:
            return 1

    def _roll_composer_seed(self) -> None:
        try:
            rng = random.Random()
            self.spn_comp_seed.setValue(int(rng.randint(1, 999999)))
            self._update_composer_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _on_comp_family_changed(self, family: str) -> None:
        try:
            fam = str(family or "Sakral/Historisch")
            pool = self._composer_catalog_for_family(fam)
            blockers = []
            try:
                from PyQt6.QtCore import QSignalBlocker
                blockers = [QSignalBlocker(self.cmb_comp_style_a), QSignalBlocker(self.cmb_comp_style_b)]
            except Exception:
                blockers = []
            current_a = str(self.cmb_comp_style_a.currentText() or "Gregorianik")
            current_b = str(self.cmb_comp_style_b.currentText() or "Ambient")
            for cmb in (self.cmb_comp_style_a, self.cmb_comp_style_b):
                cmb.clear()
                cmb.addItems(pool)
                cmb.setEditable(True)
            self.cmb_comp_style_a.setCurrentText(current_a if current_a else (pool[0] if pool else "Gregorianik"))
            self.cmb_comp_style_b.setCurrentText(current_b if current_b else (pool[min(1, len(pool)-1)] if pool else "Ambient"))
        finally:
            self._update_composer_summary()
            self._persist_instrument_state()

    def _update_composer_summary(self) -> None:
        try:
            if not hasattr(self, "lbl_comp_summary"):
                return
            p = self._composer_params_from_ui()
            parts = [name for name, enabled in (("Bass", p["parts"].get("bass")), ("Melodie", p["parts"].get("melody")), ("Lead", p["parts"].get("lead")), ("Pad", p["parts"].get("pad")), ("Arp", p["parts"].get("arp"))) if enabled]
            seed = self._composer_hash_seed()
            self._composer_last_summary = (
                f"Weltstil-Mix: {p.get('style_a')} × {p.get('style_b')} • {p.get('context')} • {p.get('form')}\n"
                f"Phrasenprofil: {p.get('phrase_profile')} • Dichteprofil: {p.get('density_profile')} • Eff.-Dichte {float(p.get('effective_density') or 0.0):.2f}\n"
                f"Rollen: {', '.join(parts) if parts else 'keine'} • Bars {p.get('bars')} • Grid {self.cmb_comp_grid.currentText()} • Seed {seed}"
            )
            self.lbl_comp_summary.setText(self._composer_last_summary)
            if hasattr(self, "lbl_comp_hint"):
                self.lbl_comp_hint.setText(
                    "Mathematischer Local Composer: deterministischer Seed + Stil-Mischung + feinere Phrasenprofile/Dichteprofile für AETERNA-taugliche Bass/Melodie/Lead/Pad/Arp-Voices. Keine Drums, kein Core-Eingriff."
                )
        except Exception:
            pass

    def _composer_time_signature(self) -> str:
        try:
            ctx = getattr(self.project_service, "ctx", None)
            proj = getattr(ctx, "project", None) if ctx is not None else None
            return str(getattr(proj, "time_signature", "4/4") or "4/4")
        except Exception:
            return "4/4"

    def _composer_bpb(self) -> float:
        try:
            from pydaw.music.ai_composer import beats_per_bar
            return float(beats_per_bar(self._composer_time_signature()))
        except Exception:
            return 4.0

    def _composer_next_start(self, track_id: str) -> float:
        try:
            ctx = getattr(self.project_service, "ctx", None)
            proj = getattr(ctx, "project", None) if ctx is not None else None
            clips = [c for c in getattr(proj, "clips", []) or [] if str(getattr(c, "track_id", "")) == str(track_id or "") and str(getattr(c, "kind", "")) == "midi"]
            if not clips:
                return 0.0
            end_b = max(float(getattr(c, "start_beats", 0.0)) + float(getattr(c, "length_beats", 0.0)) for c in clips)
            bpb = self._composer_bpb()
            if bpb <= 0.0:
                return max(0.0, end_b)
            return max(0.0, round(end_b / bpb) * bpb)
        except Exception:
            return 0.0

    def _composer_base_root(self, style_a: str, style_b: str, context: str) -> int:
        hay = " ".join([str(style_a or ""), str(style_b or ""), str(context or ""), str(self.cmb_preset.currentText() or "")]).lower()
        if any(x in hay for x in ("dark", "doom", "black metal", "death metal", "industrial", "ebm", "club", "nacht", "ritual")):
            return 57
        if any(x in hay for x in ("gregorian", "kirchen", "gospel", "gottesdienst", "kathedrale", "barock", "bach", "hofmusik", "schlossmusik")):
            return 60
        if any(x in hay for x in ("balkan", "klezmer", "arab", "pers", "anatol")):
            return 62
        return 60

    def _composer_minor_mode(self, style_a: str, style_b: str, context: str) -> bool:
        hay = " ".join([str(style_a or ""), str(style_b or ""), str(context or ""), str(self.cmb_preset.currentText() or "")]).lower()
        if any(x in hay for x in ("gregorian", "kirchen", "gospel", "gottesdienst", "barock", "bach", "hofmusik", "schlossmusik", "kathedrale")):
            return False
        return any(x in hay for x in ("dark", "doom", "metal", "industrial", "ebm", "dunkel", "nacht", "ritual", "drone", "ambient"))

    def _extract_bar_roots(self, notes, start_beats: float, bpb: float, bars: int) -> list[int]:
        roots = []
        fallback = 48
        for bi in range(max(1, int(bars))):
            bar_start = float(start_beats) + float(bi) * float(bpb)
            bar_end = bar_start + float(bpb)
            lows = [int(n.pitch) for n in notes if float(getattr(n, 'start_beats', 0.0)) >= bar_start and float(getattr(n, 'start_beats', 0.0)) < bar_end]
            if lows:
                fallback = min(lows)
            roots.append(int(fallback))
        return roots

    def _build_aeterna_composer_notes(self, start_beats: float, time_signature: str) -> list:
        from pydaw.model.midi import MidiNote
        from pydaw.music.ai_composer import ComposerParams, generate_clip_notes, beats_per_bar

        p = self._composer_params_from_ui()
        if not any(bool(v) for v in (p.get("parts") or {}).values()):
            raise ValueError("Bitte mindestens eine Voice aktivieren: Bass, Melodie, Lead, Pad oder Arp.")
        style_a = str(p.get("style_a") or "Gregorianik")
        style_b = str(p.get("style_b") or "Ambient")
        bars = max(1, int(p.get("bars") or 8))
        grid = max(0.125, float(p.get("grid") or 0.25))
        swing = max(0.0, min(0.95, float(p.get("swing") or 0.0)))
        density = max(0.05, min(1.0, float(p.get("effective_density") or p.get("density") or 0.62)))
        phrase = self._composer_phrase_factors()
        hybrid = max(0.0, min(1.0, float(p.get("hybrid") or 0.58)))
        seed = self._composer_hash_seed()
        rng = random.Random(seed)
        base_root = self._composer_base_root(style_a, style_b, str(p.get("context") or ""))
        cp = ComposerParams(
            genre_a=style_a,
            genre_b=style_b,
            custom_genre_a="",
            custom_genre_b="",
            context=str(p.get("context") or "Neutral"),
            form=str(p.get("form") or "Pad/Drone + Melodie"),
            instrument_setup="Kammermusik-Setup",
            bars=bars,
            grid=grid,
            swing=swing,
            density=density,
            hybrid=hybrid,
            seed=seed,
        )
        base_notes = list(generate_clip_notes(start_beats=float(start_beats), time_signature=str(time_signature or "4/4"), params=cp, base_root=base_root) or [])
        bpb = float(beats_per_bar(str(time_signature or "4/4")))
        minor_mode = self._composer_minor_mode(style_a, style_b, str(p.get("context") or ""))
        chord = (0, 3, 7) if minor_mode else (0, 4, 7)
        roots = self._extract_bar_roots(base_notes, float(start_beats), bpb, bars)
        out = []

        if p["parts"].get("bass", True):
            bass_gate = max(grid, float(grid) * float(phrase.get("bass_len", 1.0) or 1.0))
            for n in base_notes:
                if int(getattr(n, 'pitch', 60)) < 58:
                    if rng.random() > max(0.35, min(1.0, density + 0.08)) and (int(round(float(n.start_beats) / max(grid, 0.125))) % 2):
                        continue
                    out.append(MidiNote(pitch=int(n.pitch), start_beats=float(n.start_beats), length_beats=max(bass_gate, float(n.length_beats) * float(phrase.get("bass_len", 1.0) or 1.0)), velocity=max(44, int(n.velocity))).clamp())
            for bi, root in enumerate(roots):
                t0 = float(start_beats) + float(bi) * bpb
                out.append(MidiNote(pitch=max(24, min(54, int(root))), start_beats=t0, length_beats=max(grid * 2.0, bpb * 0.5 * float(phrase.get("bass_len", 1.0) or 1.0)), velocity=78).clamp())

        melody_pool = [n for n in base_notes if 56 <= int(getattr(n, 'pitch', 60)) <= 90]
        if p["parts"].get("melody", True):
            melody_keep = max(0.28, min(1.0, density * float(phrase.get("melody_keep", 1.0) or 1.0)))
            melody_len_mul = float(phrase.get("melody_len", 1.0) or 1.0)
            for idx, n in enumerate(melody_pool):
                if idx > 0 and rng.random() > melody_keep:
                    continue
                out.append(MidiNote(pitch=int(n.pitch), start_beats=float(n.start_beats), length_beats=max(grid, float(n.length_beats) * melody_len_mul), velocity=int(n.velocity)).clamp())

        if p["parts"].get("lead", True):
            lead_keep = max(0.24, min(1.0, float(phrase.get("lead_keep", 0.62) or 0.62) * (0.78 + density * 0.42)))
            for idx, n in enumerate(melody_pool):
                if (idx % 2) != 0 and rng.random() > lead_keep:
                    continue
                lead_pitch = int(n.pitch) + (12 if int(n.pitch) < 78 else 0)
                lead_start = float(n.start_beats) + (grid * 0.5 if rng.random() < min(0.45, 0.18 + density * 0.25) else 0.0)
                out.append(MidiNote(pitch=min(102, lead_pitch), start_beats=lead_start, length_beats=max(grid, float(n.length_beats) * 0.75 * float(phrase.get("melody_len", 1.0) or 1.0)), velocity=min(123, int(n.velocity) + 10)).clamp())

        if p["parts"].get("pad", True):
            for bi, root in enumerate(roots):
                t0 = float(start_beats) + float(bi) * bpb
                pad_root = int(root) + 12
                pad_len = max(bpb * (1.5 if density < 0.55 else 1.0) * float(phrase.get("pad_len", 1.0) or 1.0), grid * 4.0)
                for offs in chord:
                    out.append(MidiNote(pitch=max(40, min(92, pad_root + int(offs))), start_beats=t0, length_beats=pad_len, velocity=54).clamp())

        if p["parts"].get("arp", True):
            arp_step = max(0.125, grid * float(phrase.get("arp_step_mul", 1.0) or 1.0))
            arp_oct = 12 if rng.random() < 0.6 else 0
            for bi, root in enumerate(roots):
                t0 = float(start_beats) + float(bi) * bpb
                chord_tones = [max(52, min(100, int(root) + 12 + int(o))) for o in chord]
                steps = max(2, int(round((bpb / max(arp_step, 0.125)) * max(0.7, density))))
                for si in range(steps):
                    st = t0 + float(si) * arp_step
                    if st >= (t0 + bpb):
                        continue
                    if rng.random() > max(0.42, min(1.0, density + 0.1)) and (si % 2):
                        continue
                    pitch = chord_tones[si % len(chord_tones)] + (arp_oct if (si % 4) == 3 else 0)
                    out.append(MidiNote(pitch=max(52, min(108, pitch)), start_beats=st, length_beats=max(0.125, arp_step * 0.9), velocity=62 + (si % 3) * 6).clamp())
        # deterministic dedupe/sort
        dedup = {}
        for n in out:
            try:
                key = (int(n.pitch), round(float(n.start_beats), 4), round(float(n.length_beats), 4), int(n.velocity))
                dedup[key] = n.clamp()
            except Exception:
                continue
        final = list(dedup.values())
        final.sort(key=lambda n: (float(n.start_beats), int(n.pitch), -int(n.velocity)))
        return final

    def _composer_new_clip(self) -> None:
        ps = self.project_service
        if ps is None:
            return
        try:
            track_id = str(self.track_id or "")
            start = self._composer_next_start(track_id)
            length_beats = float(max(1, int(self.spn_comp_bars.value()))) * self._composer_bpb()
            label = f"AETERNA {self.cmb_comp_style_a.currentText()} × {self.cmb_comp_style_b.currentText()}"
            clip_id = ps.add_midi_clip_at(track_id, start_beats=float(start), length_beats=max(1.0, length_beats), label=label[:48])
            self._composer_render_into_clip(str(clip_id), overwrite=True)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Composer", f"Konnte MIDI-Clip nicht erzeugen: {e}")
            except Exception:
                pass

    def _composer_overwrite_active_clip(self) -> None:
        ps = self.project_service
        if ps is None:
            return
        clip_id = ""
        try:
            clip_id = str(ps.active_clip_id() or "")
        except Exception:
            clip_id = str(getattr(ps, "_active_clip_id", "") or "")
        if not clip_id:
            try:
                QMessageBox.information(self, "AETERNA Composer", "Kein aktiver MIDI-Clip ausgewählt. Nutze zuerst den Dreiecksbutton → Neuer MIDI-Clip.")
            except Exception:
                pass
            return
        try:
            ctx = getattr(ps, "ctx", None)
            proj = getattr(ctx, "project", None) if ctx is not None else None
            clip = next((c for c in getattr(proj, 'clips', []) or [] if str(getattr(c, 'id', '')) == clip_id), None)
            if clip is not None and str(getattr(clip, 'track_id', '')) != str(self.track_id or ""):
                raise ValueError("Aktiver Clip gehört nicht zur aktuellen AETERNA-Spur")
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Composer", str(e))
            except Exception:
                pass
            return
        self._composer_render_into_clip(clip_id, overwrite=True)

    def _composer_render_into_clip(self, clip_id: str, overwrite: bool = True) -> None:
        ps = self.project_service
        if ps is None or not clip_id:
            return
        try:
            notes = self._build_aeterna_composer_notes(0.0, self._composer_time_signature())
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Composer", f"Komposition fehlgeschlagen: {e}")
            except Exception:
                pass
            return
        try:
            before = ps.snapshot_midi_notes(str(clip_id))
        except Exception:
            before = []
        try:
            if overwrite:
                ps.set_midi_notes(str(clip_id), list(notes))
            else:
                cur = list(ps.get_midi_notes(str(clip_id)) or [])
                cur.extend(list(notes))
                ps.set_midi_notes(str(clip_id), cur)
            ps.commit_midi_notes_edit(str(clip_id), before=before, label="AETERNA Composer")
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Composer", f"Konnte MIDI-Noten nicht schreiben: {e}")
            except Exception:
                pass
            return

    def _arp_note_type_factor(self) -> float:
        try:
            current = str(self.cmb_arp_note_type.currentText() or "Straight")
        except Exception:
            current = "Straight"
        for label, factor in AETERNA_ARP_NOTE_TYPES:
            if str(label) == current:
                return float(factor)
        return 1.0

    def _arp_step_payload(self) -> list[dict]:
        steps = []
        for idx in range(16):
            trans = getattr(self, f"spn_arp_step_transpose_{idx}", None)
            skip = getattr(self, f"chk_arp_step_skip_{idx}", None)
            vel = getattr(self, f"spn_arp_step_velocity_{idx}", None)
            gate = getattr(self, f"spn_arp_step_gate_{idx}", None)
            steps.append({
                "transpose": int(trans.value()) if trans is not None else 0,
                "skip": bool(skip.isChecked()) if skip is not None else False,
                "velocity": int(vel.value()) if vel is not None else 100,
                "gate": int(gate.value()) if gate is not None else 100,
            })
        return steps

    def _arp_params_from_ui(self) -> dict:
        return {
            "pattern": self.cmb_arp_pattern.currentText() if hasattr(self, "cmb_arp_pattern") else "up",
            "rate": self.cmb_arp_rate.currentText() if hasattr(self, "cmb_arp_rate") else "1/16",
            "note_type": self.cmb_arp_note_type.currentText() if hasattr(self, "cmb_arp_note_type") else "Straight",
            "root": int(self.spn_arp_root.value()) if hasattr(self, "spn_arp_root") else 60,
            "chord": self.cmb_arp_chord.currentText() if hasattr(self, "cmb_arp_chord") else "Minor Triad",
            "steps": int(self.spn_arp_steps.value()) if hasattr(self, "spn_arp_steps") else 16,
            "shuffle_enabled": bool(self.chk_arp_shuffle.isChecked()) if hasattr(self, "chk_arp_shuffle") else False,
            "shuffle_steps": int(self.spn_arp_shuffle_steps.value()) if hasattr(self, "spn_arp_shuffle_steps") else 16,
            "seed": int(self.spn_arp_seed.value()) if hasattr(self, "spn_arp_seed") else 2401,
            "step_data": self._arp_step_payload(),
        }

    def _arp_hash_seed(self) -> int:
        try:
            payload = str(self._arp_params_from_ui()).encode("utf-8")
            return int(hashlib.sha1(payload).hexdigest()[:8], 16)
        except Exception:
            return 2401

    def _roll_arp_seed(self) -> None:
        try:
            if hasattr(self, "spn_arp_seed"):
                self.spn_arp_seed.setValue(random.randint(1, 999999999))
            self._update_arp_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _arp_source_pool(self) -> list[int]:
        root = int(self.spn_arp_root.value()) if hasattr(self, "spn_arp_root") else 60
        chord = str(self.cmb_arp_chord.currentText() or "Minor Triad") if hasattr(self, "cmb_arp_chord") else "Minor Triad"
        ints = list(AETERNA_ARP_CHORDS.get(chord, AETERNA_ARP_CHORDS["Minor Triad"]))
        pool = [max(0, min(127, root + int(interval))) for interval in ints]
        return sorted(dict.fromkeys(pool))

    def _arp_sequence_variant(self, name: str, pool: list[int]) -> list[int]:
        seq = sorted(dict.fromkeys(int(p) for p in (pool or []) if 0 <= int(p) <= 127))
        if not seq:
            return [60]
        down = list(reversed(seq))
        if len(seq) <= 1:
            return seq
        if name == "down":
            return down
        if name == "up down":
            return seq + down[1:-1]
        if name == "up/down2":
            return seq + [seq[-1]] + down[1:-1] + [seq[0]]
        if name == "up/down3":
            return seq + [seq[-1], seq[-1]] + down[1:-1] + [seq[0], seq[0]]
        if name == "up+in":
            return [seq[0]] + seq[1:] + seq[1:-1]
        if name == "down+in":
            return [seq[-1]] + down[1:] + down[1:-1]
        if name == "blossom up":
            mid = len(seq) // 2
            out = [seq[mid]]
            for i in range(1, len(seq)):
                if mid - i >= 0:
                    out.append(seq[mid - i])
                if mid + i < len(seq):
                    out.append(seq[mid + i])
            return out
        if name == "blossom down":
            return list(reversed(self._arp_sequence_variant("blossom up", seq)))
        if name == "low&up":
            return [v for n in seq for v in (seq[0], n)]
        if name == "low&down":
            return [v for n in down for v in (seq[0], n)]
        if name == "hi&down":
            return [v for n in down for v in (seq[-1], n)]
        if name == "hi&up":
            return [v for n in seq for v in (seq[-1], n)]
        return seq

    def _arp_pattern_events(self, pool: list[int], step_count: int, seed: int) -> list[tuple[str, object]]:
        pattern = str(self.cmb_arp_pattern.currentText() or "up") if hasattr(self, "cmb_arp_pattern") else "up"
        step_count = max(1, int(step_count or 16))
        seq = self._arp_sequence_variant(pattern, pool)
        rng = random.Random(int(seed or 0))
        if pattern == "chords":
            return [("chord", list(pool)) for _ in range(step_count)]
        if pattern == "random":
            return [("note", rng.choice(pool or [60])) for _ in range(step_count)]
        if pattern == "flow":
            cur = max(0, min(len(pool or [60]) - 1, len(pool or [60]) // 2))
            out = []
            base = pool or [60]
            for _ in range(step_count):
                out.append(("note", base[cur]))
                cur = max(0, min(len(base) - 1, cur + rng.choice([-1, 0, 1])))
            return out
        out = []
        for i in range(step_count):
            out.append(("note", seq[i % max(1, len(seq))]))
        return out

    def _build_aeterna_arp_notes(self, start_beats: float = 0.0) -> list:
        from pydaw.model.midi import MidiNote
        p = self._arp_params_from_ui()
        step_count = max(1, min(16, int(p.get("steps", 16) or 16)))
        pool = self._arp_source_pool()
        seed = int(p.get("seed") or self._arp_hash_seed())
        events = self._arp_pattern_events(pool, step_count, seed)
        base_rate = float(AETERNA_ARP_RATE_BEATS.get(str(p.get("rate") or "1/16"), 0.25))
        base_rate *= float(self._arp_note_type_factor())
        shuffle_enabled = bool(p.get("shuffle_enabled", False))
        shuffle_steps = max(1, min(16, int(p.get("shuffle_steps", 16) or 16)))
        notes = []
        for idx in range(step_count):
            step = list(p.get("step_data") or AETERNA_ARP_DEFAULT_STEPS)[idx]
            if bool(step.get("skip", False)):
                continue
            offset = float(start_beats) + (base_rate * idx)
            if shuffle_enabled and idx < shuffle_steps and (idx % 2 == 1):
                offset += base_rate * 0.18
            gate_pct = max(0.0, min(4.0, float(step.get("gate", 100) or 100) / 100.0))
            length_beats = max(0.03125, base_rate * gate_pct)
            velocity = max(1, min(127, int(step.get("velocity", 100) or 100)))
            transpose = int(step.get("transpose", 0) or 0)
            ev_kind, ev_payload = events[idx % max(1, len(events))]
            if ev_kind == "chord":
                for pitch in list(ev_payload or []):
                    notes.append(MidiNote(pitch=max(0, min(127, int(pitch) + transpose)), start_beats=offset, length_beats=length_beats, velocity=velocity).clamp())
            else:
                notes.append(MidiNote(pitch=max(0, min(127, int(ev_payload) + transpose)), start_beats=offset, length_beats=length_beats, velocity=velocity).clamp())
        notes.sort(key=lambda n: (float(n.start_beats), int(n.pitch), -int(n.velocity)))
        return notes

    def _arp_clip_length_beats(self) -> float:
        try:
            p = self._arp_params_from_ui()
            step_count = max(1, min(16, int(p.get("steps", 16) or 16)))
            base_rate = float(AETERNA_ARP_RATE_BEATS.get(str(p.get("rate") or "1/16"), 0.25))
            base_rate *= float(self._arp_note_type_factor())
            return max(1.0 / 16.0, base_rate * step_count)
        except Exception:
            return 4.0

    def _update_arp_summary(self) -> None:
        try:
            p = self._arp_params_from_ui()
            pattern = str(p.get("pattern") or "up")
            rate = str(p.get("rate") or "1/16")
            note_type = str(p.get("note_type") or "Straight")
            chord = str(p.get("chord") or "Minor Triad")
            steps = int(p.get("steps", 16) or 16)
            shuffle = "an" if bool(p.get("shuffle_enabled", False)) else "aus"
            live = "an" if self._arp_live_enabled() else "aus"
            mod_hint = " • ".join(filter(None, [self._knob_profile_hint("shape") if self._knob_mod_profiles.get("shape") else "", self._knob_profile_hint("filter_cutoff") if self._knob_mod_profiles.get("filter_cutoff") else ""])) or "Mod-Profil: –"
            self._arp_last_summary = (
                f"Arp A\nPattern: {pattern} • Rate: {rate} • Type: {note_type}\n"
                f"Root: {int(p.get('root', 60))} • Chord: {chord} • Steps: {steps} • Shuffle: {shuffle}\n"
                f"Live: {live} • Länge MIDI: {self._arp_clip_length_beats():.2f} Beats • {mod_hint}"
            )
            if hasattr(self, "lbl_arp_summary"):
                self.lbl_arp_summary.setText(self._arp_last_summary)
            if hasattr(self, "lbl_arp_hint"):
                self.lbl_arp_hint.setText(
                    "Arp A hat jetzt zwei sichere Wege: Live ARP über das vorhandene Track-Note-FX-Arp und optional ARP→MIDI zum Festschreiben. "
                    "Root/Chord bleiben für ARP→MIDI wichtig; Live ARP arbeitet auf den eingehenden Noten dieser Spur. Jeder Step hat eigenen Transpose/Skip/Velocity/Gate-Status."
                )
            self._update_arp_live_status()
            if self._arp_live_enabled() and self.track_id and not self._restoring_state:
                self._sync_live_arp_device(persist=False)
        except Exception:
            pass

    def _arp_new_clip(self) -> None:
        ps = self.project_service
        if ps is None:
            return
        try:
            track_id = str(self.track_id or "")
            start = self._composer_next_start(track_id)
            length_beats = self._arp_clip_length_beats()
            label = f"AETERNA Arp {self.cmb_arp_pattern.currentText()}"
            clip_id = ps.add_midi_clip_at(track_id, start_beats=float(start), length_beats=max(0.25, length_beats), label=label[:48])
            self._arp_render_into_clip(str(clip_id), overwrite=True)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Arp", f"Konnte MIDI-Clip nicht erzeugen: {e}")
            except Exception:
                pass

    def _arp_overwrite_active_clip(self) -> None:
        ps = self.project_service
        if ps is None:
            return
        clip_id = ""
        try:
            clip_id = str(ps.active_clip_id() or "")
        except Exception:
            clip_id = str(getattr(ps, "_active_clip_id", "") or "")
        if not clip_id:
            try:
                QMessageBox.information(self, "AETERNA Arp", "Kein aktiver MIDI-Clip ausgewählt. Nutze zuerst den Dreiecksbutton → Neuer MIDI-Clip.")
            except Exception:
                pass
            return
        self._arp_render_into_clip(clip_id, overwrite=True)

    def _arp_render_into_clip(self, clip_id: str, overwrite: bool = True) -> None:
        ps = self.project_service
        if ps is None or not clip_id:
            return
        try:
            notes = self._build_aeterna_arp_notes(0.0)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Arp", f"Arpeggio fehlgeschlagen: {e}")
            except Exception:
                pass
            return
        try:
            before = ps.snapshot_midi_notes(str(clip_id))
        except Exception:
            before = []
        try:
            if overwrite:
                ps.set_midi_notes(str(clip_id), list(notes))
            else:
                cur = list(ps.get_midi_notes(str(clip_id)) or [])
                cur.extend(list(notes))
                ps.set_midi_notes(str(clip_id), cur)
            ps.commit_midi_notes_edit(str(clip_id), before=before, label="AETERNA Arp")
        except Exception as e:
            try:
                QMessageBox.warning(self, "AETERNA Arp", f"Konnte MIDI-Noten nicht schreiben: {e}")
            except Exception:
                pass
            return

    def _persist_instrument_state(self) -> None:
        """Persist AETERNA state — throttled to max 2× per second."""
        if self._restoring_state:
            return
        import time as _time
        now = _time.monotonic()
        if now - getattr(self, '_last_persist_t', 0.0) < 0.5:
            if not getattr(self, '_persist_deferred', False):
                self._persist_deferred = True
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, self._do_persist_now)
            return
        self._do_persist_now()

    def _do_persist_now(self) -> None:
        import time as _time
        self._persist_deferred = False
        self._last_persist_t = _time.monotonic()
        if self._restoring_state:
            return
        trk = self._get_track_obj()
        if trk is None:
            return
        try:
            if getattr(trk, "instrument_state", None) is None:
                trk.instrument_state = {}
            state = self.engine.export_state()
            show_web_a, show_web_b = self.mod_preview.overlay_visibility()
            ui_state = {
                "ui_state_version": self.UI_STATE_SCHEMA_VERSION,
                "preset": self.cmb_preset.currentText(),
                "mode": self.cmb_mode.currentText(),
                "formula": self.ed_formula.text(),
                "formula_status_note": str(getattr(self, "_formula_status_note", "") or ""),
                "formula_example_title": str(getattr(self, "_formula_last_loaded_example_title", "") or ""),
                "formula_example_text": str(getattr(self, "_formula_last_loaded_example_text", "") or ""),
                "formula_applied_text": str(getattr(self, "_formula_last_applied_text", "") or ""),
                "preset_metadata": self._preset_metadata_from_ui(),
                "mod1_source": self.cmb_mod1_source.currentText(),
                "mod1_target": self.cmb_mod1_target.currentText(),
                "mod2_source": self.cmb_mod2_source.currentText(),
                "mod2_target": self.cmb_mod2_target.currentText(),
                "visible_web_slots": int(getattr(self, '_visible_web_slots', 2)),
                "mod_view": self.mod_preview.view(),
                "mod_overlay_web_a": bool(show_web_a),
                "mod_overlay_web_b": bool(show_web_b),
                "mseg_advanced_visible": bool(self._mseg_advanced_visible),
                "section_states": self._capture_section_states(),
                "mod_assign_slot_mode": self.cmb_mod_assign_slot.currentText() if hasattr(self, "cmb_mod_assign_slot") else "Auto",
                "mod_last_assignment_note": str(getattr(self, "_mod_last_assignment_note", "") or ""),
                "web_template_intensity": self.cmb_web_template_intensity.currentText() if hasattr(self, "cmb_web_template_intensity") else "Mittel",
                "active_web_template": str(getattr(self, "_active_web_template", "") or ""),
                "active_snapshot_slot": str(getattr(self, "_active_snapshot_slot", "") or ""),
                "snapshot_last_action_note": str(getattr(self, "_snapshot_last_action_note", "") or ""),
                "composer_family": self.cmb_comp_family.currentText() if hasattr(self, "cmb_comp_family") else "Sakral/Historisch",
                "composer_style_a": self.cmb_comp_style_a.currentText() if hasattr(self, "cmb_comp_style_a") else "Gregorianik",
                "composer_style_b": self.cmb_comp_style_b.currentText() if hasattr(self, "cmb_comp_style_b") else "Ambient",
                "composer_context": self.cmb_comp_context.currentText() if hasattr(self, "cmb_comp_context") else "Gottesdienst",
                "composer_form": self.cmb_comp_form.currentText() if hasattr(self, "cmb_comp_form") else "Pad/Drone + Melodie",
                "composer_phrase_profile": self.cmb_comp_phrase.currentText() if hasattr(self, "cmb_comp_phrase") else "Ausgewogen",
                "composer_density_profile": self.cmb_comp_density_profile.currentText() if hasattr(self, "cmb_comp_density_profile") else "Mittel",
                "composer_bars": int(self.spn_comp_bars.value()) if hasattr(self, "spn_comp_bars") else 8,
                "composer_grid": self.cmb_comp_grid.currentText() if hasattr(self, "cmb_comp_grid") else "1/16",
                "composer_swing": float(self.spn_comp_swing.value()) if hasattr(self, "spn_comp_swing") else 0.12,
                "composer_density": float(self.spn_comp_density.value()) if hasattr(self, "spn_comp_density") else 0.62,
                "composer_hybrid": float(self.spn_comp_hybrid.value()) if hasattr(self, "spn_comp_hybrid") else 0.58,
                "composer_seed": int(self.spn_comp_seed.value()) if hasattr(self, "spn_comp_seed") else 1,
                "composer_part_bass": bool(self.chk_comp_bass.isChecked()) if hasattr(self, "chk_comp_bass") else True,
                "composer_part_melody": bool(self.chk_comp_melody.isChecked()) if hasattr(self, "chk_comp_melody") else True,
                "composer_part_lead": bool(self.chk_comp_lead.isChecked()) if hasattr(self, "chk_comp_lead") else True,
                "composer_part_pad": bool(self.chk_comp_pad.isChecked()) if hasattr(self, "chk_comp_pad") else True,
                "composer_part_arp": bool(self.chk_comp_arp.isChecked()) if hasattr(self, "chk_comp_arp") else True,
                "arp_pattern": self.cmb_arp_pattern.currentText() if hasattr(self, "cmb_arp_pattern") else "up",
                "arp_rate": self.cmb_arp_rate.currentText() if hasattr(self, "cmb_arp_rate") else "1/16",
                "arp_note_type": self.cmb_arp_note_type.currentText() if hasattr(self, "cmb_arp_note_type") else "Straight",
                "arp_root": int(self.spn_arp_root.value()) if hasattr(self, "spn_arp_root") else 60,
                "arp_chord": self.cmb_arp_chord.currentText() if hasattr(self, "cmb_arp_chord") else "Minor Triad",
                "arp_steps": int(self.spn_arp_steps.value()) if hasattr(self, "spn_arp_steps") else 16,
                "arp_shuffle_enabled": bool(self.chk_arp_shuffle.isChecked()) if hasattr(self, "chk_arp_shuffle") else False,
                "arp_shuffle_steps": int(self.spn_arp_shuffle_steps.value()) if hasattr(self, "spn_arp_shuffle_steps") else 16,
                "arp_seed": int(self.spn_arp_seed.value()) if hasattr(self, "spn_arp_seed") else 2401,
                "arp_step_data": self._arp_step_payload() if hasattr(self, "spn_arp_seed") else list(AETERNA_ARP_DEFAULT_STEPS),
                "arp_live_enabled": bool(self._arp_live_enabled()),
                "arp_live_status_note": str(getattr(self, "_arp_live_status_note", "ARP Live: aus") or "ARP Live: aus"),
                "knob_mod_profiles": {str(k): dict(v) for k, v in (self._knob_mod_profiles or {}).items() if isinstance(v, dict)},
            }
            for attr_name, key, _default in self._combo_state_specs():
                combo = self._combo_by_name(attr_name)
                if combo is not None:
                    ui_state[key] = combo.currentText()
            state["ui"] = ui_state
            state["preset_metadata"] = self._preset_metadata_from_ui()
            self.engine.set_preset_metadata(state["preset_metadata"])
            state["state_sections"] = ["engine", "ui", "mseg_clipboard", "mseg_slots", "mseg_ab_slots", "automation_targets"]
            state["automation_targets"] = self._automation_target_specs()
            state["mseg_clipboard"] = self._serialize_mseg_payload(self._mseg_clipboard)
            state["mseg_slots"] = {str(k): self._serialize_mseg_payload(v) for k, v in (self._mseg_slots or {}).items()}
            state["mseg_ab_slots"] = {str(k): self._serialize_mseg_payload(v) for k, v in (self._mseg_ab_slots or {}).items()}
            state["local_snapshots"] = {str(k): v for k, v in (self._local_snapshots or {}).items() if isinstance(v, dict)}
            state["preset_ab_slots"] = {str(k): v for k, v in (self._preset_ab_slots or {}).items() if isinstance(v, dict)}
            state["preset_ab_compare_active"] = bool(self._preset_ab_compare_active)
            trk.instrument_state[self.PLUGIN_STATE_KEY] = state
            self._update_phase3_summary()
        except Exception:
            pass

    def _restore_instrument_state(self) -> None:
        trk = self._get_track_obj()
        if trk is None:
            return
        try:
            ist = getattr(trk, "instrument_state", None) or {}
        except Exception:
            ist = {}
        st = ist.get(self.PLUGIN_STATE_KEY)
        if not isinstance(st, dict):
            return
        restore_started = time.perf_counter()
        self._restoring_state = True
        self._perf_last_scope = "restore"
        blockers = self._make_signal_blockers(self._restore_signal_widgets())
        self.setUpdatesEnabled(False)
        try:
            self.engine.import_state(st)
            ui = st.get("ui") if isinstance(st.get("ui"), dict) else {}
            mode = str(self.engine.get_param("mode", "formula") or "formula")
            self.cmb_mode.setCurrentText(mode)
            formula = str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA)
            self._formula_internal_change = True
            self.ed_formula.setText(str(ui.get("formula") or formula))
            self._formula_internal_change = False
            self._formula_last_applied_text = str(ui.get("formula_applied_text") or formula)
            self._formula_last_loaded_example_title = str(ui.get("formula_example_title") or "")
            self._formula_last_loaded_example_text = str(ui.get("formula_example_text") or "")
            self._formula_status_note = str(ui.get("formula_status_note") or "Init geladen")
            preset_name = str(st.get("preset_name") or ui.get("preset") or "")
            if preset_name:
                for i in range(self.cmb_preset.count()):
                    if self.cmb_preset.itemText(i) == preset_name:
                        self.cmb_preset.setCurrentIndex(i)
                        break
            self._apply_preset_metadata_to_ui(self.engine.get_preset_metadata(), persist=False)
            for key, knob in self._knobs.items():
                try:
                    knob.setValueExternal(int(round(float(self.engine.get_param(key, 0.5)) * 100.0)))
                except Exception:
                    pass
            if hasattr(self, "chk_retrigger"):
                try:
                    self.chk_retrigger.setChecked(float(self.engine.get_param("retrigger", 1.0) or 1.0) >= 0.5)
                except Exception:
                    pass
            self._refresh_all_knob_automation_tooltips()
            self._update_automation_quick_status()
            for key, combo in self._combo_params.items():
                try:
                    combo.setCurrentText(str(ui.get(key) or self.engine.get_param(key, combo.currentText())))
                except Exception:
                    pass
            self._set_mod_polarity(1, self.engine.get_param("mod1_polarity", "plus"), persist=False)
            self._set_mod_polarity(2, self.engine.get_param("mod2_polarity", "plus"), persist=False)
            # Restore extra Web slots C-H visibility + polarities
            try:
                saved_slots = int(ui.get("visible_web_slots", 2) or 2)
                saved_slots = max(2, min(8, saved_slots))
                self._visible_web_slots = 2  # Reset first
                for s in range(3, saved_slots + 1):
                    self._visible_web_slots = s
                    row_w = self._extra_web_rows.get(s)
                    if row_w is not None:
                        row_w.setVisible(True)
                    self._set_mod_polarity(s, self.engine.get_param(f"mod{s}_polarity", "plus"), persist=False)
                self._update_web_slot_buttons()
            except Exception:
                pass
            self._active_web_template = str(ui.get("active_web_template") or getattr(self, "_active_web_template", "") or "")
            if hasattr(self, "cmb_web_template_intensity"):
                self.cmb_web_template_intensity.setCurrentText(str(ui.get("web_template_intensity") or "Mittel"))
            if hasattr(self, "cmb_mod_assign_slot"):
                self.cmb_mod_assign_slot.setCurrentText(str(ui.get("mod_assign_slot_mode") or "Auto"))
            self._mod_last_assignment_note = str(ui.get("mod_last_assignment_note") or getattr(self, "_mod_last_assignment_note", "") or "Drag Quelle → Ziel • bis zu 8 Slots (Web A–H).")
            advanced_visible = bool(ui.get("mseg_advanced_visible", False))
            self._mseg_clipboard = self._deserialize_mseg_payload(st.get("mseg_clipboard"))
            raw_slots = st.get("mseg_slots") if isinstance(st.get("mseg_slots"), dict) else {}
            self._mseg_slots = {str(k): self._deserialize_mseg_payload(v) for k, v in raw_slots.items() if self._deserialize_mseg_payload(v)}
            raw_ab = st.get("mseg_ab_slots") if isinstance(st.get("mseg_ab_slots"), dict) else {}
            self._mseg_ab_slots = {str(k): self._deserialize_mseg_payload(v) for k, v in raw_ab.items() if self._deserialize_mseg_payload(v)}
            raw_preset_ab = st.get("preset_ab_slots") if isinstance(st.get("preset_ab_slots"), dict) else {}
            self._preset_ab_slots = {str(k): v for k, v in raw_preset_ab.items() if isinstance(v, dict)}
            self._preset_ab_compare_active = bool(st.get("preset_ab_compare_active", False))
            raw_snapshots = st.get("local_snapshots") if isinstance(st.get("local_snapshots"), dict) else {}
            self._local_snapshots = {str(k): v for k, v in raw_snapshots.items() if isinstance(v, dict)}
            self._active_snapshot_slot = str(ui.get("active_snapshot_slot") or getattr(self, "_active_snapshot_slot", "") or "")
            self._snapshot_last_action_note = str(ui.get("snapshot_last_action_note") or getattr(self, "_snapshot_last_action_note", "") or "Zuletzt: noch kein lokaler Snapshot-Vorgang")
            if hasattr(self, "cmb_comp_family"):
                self.cmb_comp_family.setCurrentText(str(ui.get("composer_family") or "Sakral/Historisch"))
            if hasattr(self, "cmb_comp_style_a"):
                self.cmb_comp_style_a.setCurrentText(str(ui.get("composer_style_a") or "Gregorianik"))
            if hasattr(self, "cmb_comp_style_b"):
                self.cmb_comp_style_b.setCurrentText(str(ui.get("composer_style_b") or "Ambient"))
            if hasattr(self, "cmb_comp_context"):
                self.cmb_comp_context.setCurrentText(str(ui.get("composer_context") or "Gottesdienst"))
            if hasattr(self, "cmb_comp_form"):
                self.cmb_comp_form.setCurrentText(str(ui.get("composer_form") or "Pad/Drone + Melodie"))
            if hasattr(self, "cmb_comp_phrase"):
                self.cmb_comp_phrase.setCurrentText(str(ui.get("composer_phrase_profile") or "Ausgewogen"))
            if hasattr(self, "cmb_comp_density_profile"):
                self.cmb_comp_density_profile.setCurrentText(str(ui.get("composer_density_profile") or "Mittel"))
            if hasattr(self, "spn_comp_bars"):
                self.spn_comp_bars.setValue(int(ui.get("composer_bars") or 8))
            if hasattr(self, "cmb_comp_grid"):
                self.cmb_comp_grid.setCurrentText(str(ui.get("composer_grid") or "1/16"))
            if hasattr(self, "spn_comp_swing"):
                self.spn_comp_swing.setValue(float(ui.get("composer_swing") or 0.12))
            if hasattr(self, "spn_comp_density"):
                self.spn_comp_density.setValue(float(ui.get("composer_density") or 0.62))
            if hasattr(self, "spn_comp_hybrid"):
                self.spn_comp_hybrid.setValue(float(ui.get("composer_hybrid") or 0.58))
            if hasattr(self, "spn_comp_seed"):
                self.spn_comp_seed.setValue(int(ui.get("composer_seed") or 1))
            if hasattr(self, "chk_comp_bass"):
                self.chk_comp_bass.setChecked(bool(ui.get("composer_part_bass", True)))
            if hasattr(self, "chk_comp_melody"):
                self.chk_comp_melody.setChecked(bool(ui.get("composer_part_melody", True)))
            if hasattr(self, "chk_comp_lead"):
                self.chk_comp_lead.setChecked(bool(ui.get("composer_part_lead", True)))
            if hasattr(self, "chk_comp_pad"):
                self.chk_comp_pad.setChecked(bool(ui.get("composer_part_pad", True)))
            if hasattr(self, "chk_comp_arp"):
                self.chk_comp_arp.setChecked(bool(ui.get("composer_part_arp", True)))
            self._knob_mod_profiles = {str(k): dict(v) for k, v in (ui.get("knob_mod_profiles") or {}).items() if isinstance(v, dict)}
            if hasattr(self, "cmb_arp_pattern"):
                self.cmb_arp_pattern.setCurrentText(str(ui.get("arp_pattern") or "up"))
            if hasattr(self, "cmb_arp_rate"):
                self.cmb_arp_rate.setCurrentText(str(ui.get("arp_rate") or "1/16"))
            if hasattr(self, "cmb_arp_note_type"):
                self.cmb_arp_note_type.setCurrentText(str(ui.get("arp_note_type") or "Straight"))
            if hasattr(self, "spn_arp_root"):
                self.spn_arp_root.setValue(int(ui.get("arp_root") or 60))
            if hasattr(self, "cmb_arp_chord"):
                self.cmb_arp_chord.setCurrentText(str(ui.get("arp_chord") or "Minor Triad"))
            if hasattr(self, "spn_arp_steps"):
                self.spn_arp_steps.setValue(int(ui.get("arp_steps") or 16))
            if hasattr(self, "chk_arp_shuffle"):
                self.chk_arp_shuffle.setChecked(bool(ui.get("arp_shuffle_enabled", False)))
            if hasattr(self, "spn_arp_shuffle_steps"):
                self.spn_arp_shuffle_steps.setValue(int(ui.get("arp_shuffle_steps") or 16))
            if hasattr(self, "spn_arp_seed"):
                self.spn_arp_seed.setValue(int(ui.get("arp_seed") or 2401))
            self._arp_live_status_note = str(ui.get("arp_live_status_note") or getattr(self, "_arp_live_status_note", "ARP Live: aus") or "ARP Live: aus")
            if hasattr(self, "chk_arp_live_enabled"):
                try:
                    self.chk_arp_live_enabled.blockSignals(True)
                    self.chk_arp_live_enabled.setChecked(bool(ui.get("arp_live_enabled", False)))
                finally:
                    self.chk_arp_live_enabled.blockSignals(False)
            self._update_arp_live_status()
            arp_steps = list(ui.get("arp_step_data") or list(AETERNA_ARP_DEFAULT_STEPS))
            for idx in range(16):
                step = arp_steps[idx] if idx < len(arp_steps) and isinstance(arp_steps[idx], dict) else dict(AETERNA_ARP_DEFAULT_STEPS[idx])
                tr = getattr(self, f"spn_arp_step_transpose_{idx}", None)
                sk = getattr(self, f"chk_arp_step_skip_{idx}", None)
                vel = getattr(self, f"spn_arp_step_velocity_{idx}", None)
                gate = getattr(self, f"spn_arp_step_gate_{idx}", None)
                if tr is not None:
                    tr.setValue(int(step.get("transpose", 0) or 0))
                if sk is not None:
                    sk.setChecked(bool(step.get("skip", False)))
                if vel is not None:
                    vel.setValue(int(step.get("velocity", 100) or 100))
                if gate is not None:
                    gate.setValue(int(step.get("gate", 100) or 100))
            self._update_composer_summary()
            self._update_arp_summary()
            self._refresh_all_knob_automation_tooltips()
            for attr_name, key, default in self._combo_state_specs():
                combo = self._combo_by_name(attr_name)
                wanted = str(ui.get(key) or default)
                if combo is None:
                    continue
                for i in range(combo.count()):
                    if combo.itemText(i) == wanted:
                        combo.setCurrentIndex(i)
                        break
            self._set_mod_view(str(ui.get("mod_view") or "mseg"), persist=False)
            self._set_overlay_visibility(bool(ui.get("mod_overlay_web_a", True)), bool(ui.get("mod_overlay_web_b", True)), persist=False)
            self._set_mseg_advanced_visible(advanced_visible, persist=False)
            self._apply_section_states(ui.get("section_states"))
            self._update_mod_rack_card()
            self._update_signal_flow_card()
        finally:
            blockers.clear()
            self.setUpdatesEnabled(True)
            self._restoring_state = False
        self._perf_restore_ms = (time.perf_counter() - restore_started) * 1000.0
        self._update_formula_status()
        self._update_formula_info_line()
        self._update_perf_status()
        self._schedule_deferred_ui_refresh(reason="restore", delay_ms=0, restart=True)

    def _serialize_mseg_payload(self, payload):
        if not isinstance(payload, dict):
            return None
        pts = payload.get("points")
        forms = payload.get("forms")
        if not isinstance(pts, (list, tuple)) or not isinstance(forms, (list, tuple)):
            return None
        out_pts = []
        for pt in pts:
            try:
                out_pts.append([float(pt[0]), float(pt[1])])
            except Exception:
                pass
        out_forms = [str(x or "linear").lower() for x in forms]
        if len(out_pts) < 2:
            return None
        return {"points": out_pts, "forms": out_forms}

    def _deserialize_mseg_payload(self, payload):
        if not isinstance(payload, dict):
            return None
        pts = payload.get("points")
        forms = payload.get("forms")
        if not isinstance(pts, (list, tuple)) or not isinstance(forms, (list, tuple)):
            return None
        clean_pts = []
        for pt in pts:
            try:
                clean_pts.append((float(pt[0]), float(pt[1])))
            except Exception:
                pass
        clean_forms = [str(x or "linear").lower() for x in forms]
        if len(clean_pts) < 2:
            return None
        return {"points": clean_pts, "forms": clean_forms}

    def _capture_current_mseg_payload(self):
        return self._deserialize_mseg_payload({
            "points": self.engine.get_mseg_points(),
            "forms": self.engine.get_mseg_segment_forms(),
        })

    def _apply_mseg_payload(self, payload) -> bool:
        payload = self._deserialize_mseg_payload(payload)
        if not payload:
            return False
        try:
            self.engine.set_mseg_points(payload.get("points") or [])
            self.engine.set_mseg_segment_forms(payload.get("forms") or [], save_history=False)
            self.mod_preview.update()
            self._sync_segment_form_ui()
            self._notify_mseg_points_changed_and_persist()
            self._sync_point_editor_ui()
            return True
        except Exception:
            return False

    # -------- automation
    def _setup_automation(self) -> None:
        try:
            if self._automation_setup_done:
                return
            mgr = getattr(self, "automation_manager", None)
            tid = str(getattr(self, "track_id", "") or "")
            if mgr is None or not tid:
                return
            self._automation_setup_done = True
            self._automation_pid_to_engine = {}
            label_map = self._automation_label_map()
            self._apply_preset_metadata_to_ui(self.engine.get_preset_metadata(), persist=False)
            for key, knob in self._knobs.items():
                pid = self._automation_pid(key, tid)
                self._automation_pid_to_engine[pid] = (lambda v, kk=key: self._apply_automation_value_to_engine(kk, float(v), persist=False))
                try:
                    knob.bind_automation(
                        mgr, pid,
                        name=label_map.get(key, f"AETERNA {key}"),
                        track_id=tid,
                        minimum=0.0,
                        maximum=100.0,
                        default=float(knob.value()),
                    )
                    self._install_knob_context_menu(key, knob)
                    self._refresh_knob_automation_tooltip(key)
                except Exception:
                    pass
                try:
                    knob.valueChanged.connect(lambda _v=0: self._persist_instrument_state())
                except Exception:
                    pass
            if not self._automation_mgr_connected:
                try:
                    mgr.parameter_changed.connect(self._on_automation_parameter_changed)
                    self._automation_mgr_connected = True
                except Exception:
                    self._automation_mgr_connected = False
            self._refresh_all_knob_automation_tooltips()
            self._update_automation_quick_status()
            self._update_phase3_summary()
        except Exception:
            pass

    def _automation_pid(self, key: str, track_id: str | None = None) -> str:
        tid = str(track_id if track_id is not None else (self.track_id or ""))
        return f"trk:{tid}:aeterna:{key}"

    def _on_automation_parameter_changed(self, parameter_id: str, value: float) -> None:
        try:
            fn = self._automation_pid_to_engine.get(str(parameter_id))
            if fn is not None:
                fn(float(value))
        except Exception:
            pass

    # -------- UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        sec_id = self._register_section(_Section("AETERNA", expanded=True))
        self.lbl_title = QLabel("The Morphogenetic Engine")
        self.lbl_title.setObjectName("aeternaTitle")
        self.lbl_status = QLabel("FORMULA OK")
        self.lbl_status.setObjectName("aeternaStatus")
        self.lbl_desc = QLabel("Formel + Chaos + Terrain + sakrale Räume")
        self.lbl_desc.setWordWrap(True)
        sec_id.body.addWidget(self.lbl_title)
        sec_id.body.addWidget(self.lbl_status)
        sec_id.body.addWidget(self.lbl_desc)
        sec_id.setMinimumWidth(220)
        top.addWidget(sec_id, 0)

        sec_mode = self._register_section(_Section("ENGINE", expanded=True))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(list(self.engine.PRESETS.keys()))
        self.cmb_preset.currentTextChanged.connect(lambda txt: self._apply_preset(str(txt), persist=True))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["formula", "spectral", "terrain", "chaos", "wavetable"])
        self.cmb_mode.currentTextChanged.connect(lambda txt: self._set_mode(str(txt)))
        btn_rand = QPushButton("Random Math")
        btn_rand.clicked.connect(lambda _=False: self._randomize_formula())
        sec_mode.body.addWidget(QLabel("Preset"))
        sec_mode.body.addWidget(self.cmb_preset)
        sec_mode.body.addWidget(QLabel("Mode"))
        sec_mode.body.addWidget(self.cmb_mode)
        self.cmb_preset_category = QComboBox()
        self.cmb_preset_category.addItems(["sakral", "organisch", "chaos", "glitch", "ambient", "experimentell"])
        self.cmb_preset_character = QComboBox()
        self.cmb_preset_character.addItems(["weich", "hell", "dunkel", "breit", "beweglich", "rau"])
        self.ed_preset_note = QLineEdit()
        self.ed_preset_note.setPlaceholderText("kurze Notiz zum lokalen Preset")
        self.ed_preset_tags = QLineEdit()
        self.ed_preset_tags.setPlaceholderText("Tags lokal, z. B. sakral, weich, weit")
        self.chk_preset_favorite = QCheckBox("Favorit")
        self.cmb_preset_category.currentTextChanged.connect(lambda _txt: self._on_preset_metadata_changed())
        self.cmb_preset_character.currentTextChanged.connect(lambda _txt: self._on_preset_metadata_changed())
        self.ed_preset_note.editingFinished.connect(self._on_preset_metadata_changed)
        self.ed_preset_tags.editingFinished.connect(self._on_preset_metadata_changed)
        self.chk_preset_favorite.toggled.connect(lambda _checked: self._on_preset_metadata_changed())
        sec_mode.body.addWidget(QLabel("Kategorie"))
        sec_mode.body.addWidget(self.cmb_preset_category)
        sec_mode.body.addWidget(QLabel("Charakter"))
        sec_mode.body.addWidget(self.cmb_preset_character)
        sec_mode.body.addWidget(QLabel("Notiz"))
        sec_mode.body.addWidget(self.ed_preset_note)
        sec_mode.body.addWidget(QLabel("Tags"))
        sec_mode.body.addWidget(self.ed_preset_tags)
        sec_mode.body.addWidget(self.chk_preset_favorite)
        self.lbl_preset_meta_badges = QLabel("Keine lokalen Preset-Metadaten gesetzt")
        self.lbl_preset_meta_badges.setWordWrap(True)
        self.lbl_preset_meta_badges.setObjectName("aeternaMetaBadges")
        self.lbl_preset_meta_hint = QLabel("Kurzansicht: kompakte lokale Badges für Kategorie, Charakter, Favorit, Tags und Notiz.")
        self.lbl_preset_meta_hint.setWordWrap(True)
        self.lbl_preset_meta_hint.setObjectName("aeternaMetaHint")
        sec_mode.body.addWidget(QLabel("Kurzansicht"))
        sec_mode.body.addWidget(self.lbl_preset_meta_badges)
        sec_mode.body.addWidget(self.lbl_preset_meta_hint)
        self.lbl_preset_quicklist = QLabel("Kurzliste: lokale Favoriten und sakrale Startpresets direkt antippbar")
        self.lbl_preset_quicklist.setWordWrap(True)
        self.lbl_preset_quicklist.setObjectName("aeternaPresetQuicklist")
        quick_filter_row = QHBoxLayout()
        quick_filter_row.setSpacing(6)
        quick_filter_row.addWidget(QLabel("Filter"))
        self.cmb_preset_quick_filter = QComboBox()
        self.cmb_preset_quick_filter.addItems(["Alle", "Sakral", "Kristall", "Drone", "Favoriten"])
        self.cmb_preset_quick_filter.currentTextChanged.connect(self._on_preset_quick_filter_changed)
        quick_filter_row.addWidget(self.cmb_preset_quick_filter)
        quick_filter_row.addStretch(1)
        quick_fav_row = QHBoxLayout()
        quick_fav_row.setSpacing(4)
        self._preset_quick_buttons = []
        for preset_name in ["Kristall Bach", "Bach Glas", "Kathedrale", "Celesta Chapel"]:
            btn = QPushButton(preset_name)
            btn.setToolTip(f"Lokales AETERNA-Kurzpreset: {preset_name}")
            btn.clicked.connect(lambda _=False, pp=preset_name: self._apply_preset(pp, persist=True))
            self._preset_quick_buttons.append(btn)
            quick_fav_row.addWidget(btn)
        quick_fav_row.addStretch(1)
        self.lbl_preset_quick_status = QLabel("Favoriten-Kurzliste bereit")
        self.lbl_preset_quick_status.setWordWrap(True)
        self.lbl_preset_quick_markers = QLabel("Direktmarker: Kategorie/Charakter werden lokal in der Kurzliste gezeigt")
        self.lbl_preset_quick_markers.setWordWrap(True)
        self.lbl_preset_quick_markers.setObjectName("aeternaPresetQuickMarkers")
        sec_mode.body.addWidget(QLabel("Preset-Kurzliste"))
        sec_mode.body.addLayout(quick_filter_row)
        sec_mode.body.addLayout(quick_fav_row)
        sec_mode.body.addWidget(self.lbl_preset_quick_markers)
        sec_mode.body.addWidget(self.lbl_preset_quicklist)
        self.lbl_preset_combo_tips = QLabel("Preset→Formel/Web: lokale Startwege werden hier kompakt gezeigt")
        self.lbl_preset_combo_tips.setWordWrap(True)
        self.lbl_preset_combo_tips.setObjectName("aeternaPresetQuickMarkers")
        sec_mode.body.addWidget(self.lbl_preset_combo_tips)
        sec_mode.body.addWidget(self.lbl_preset_quick_status)
        self.lbl_preset_library_compact = QLabel("Bibliothek kompakt: Kategorien und Charaktere werden lokal gruppiert")
        self.lbl_preset_library_compact.setWordWrap(True)
        self.lbl_preset_library_compact.setObjectName("aeternaPresetLibraryCompact")
        self.lbl_preset_library_focus = QLabel("Aktiv: Preset-Fokus wird lokal aus Kategorie, Charakter und Hörbild abgeleitet")
        self.lbl_preset_library_focus.setWordWrap(True)
        self.lbl_preset_library_focus.setObjectName("aeternaPresetLibraryFocus")
        sec_mode.body.addWidget(QLabel("Preset-Bibliothek kompakt"))
        sec_mode.body.addWidget(self.lbl_preset_library_compact)
        sec_mode.body.addWidget(self.lbl_preset_library_focus)
        sec_mode.body.addWidget(btn_rand)
        sec_mode.setMinimumWidth(180)
        top.addWidget(sec_mode, 0)

        sec_phase3 = self._register_section(_Section("PHASE 3A SAFE", expanded=False))
        self.lbl_phase3_summary = QLabel("State v2 • Preset v1 • Mode formula • Formel OK")
        self.lbl_phase3_summary.setWordWrap(True)
        self.lbl_phase3_preset = QLabel("Preset: Kathedrale • Parameter 0 • MSEG Punkte 0 / Segmente 0")
        self.lbl_phase3_metadata = QLabel("Meta: Kategorie – • Charakter – • Notiz –")
        self.lbl_phase3_metadata.setWordWrap(True)
        self.lbl_phase3_preset.setWordWrap(True)
        self.lbl_phase3_automation = QLabel("Automation-Ziele: klar gruppiert unten • lokal • ohne Core-Eingriff")
        self.lbl_phase3_automation.setWordWrap(True)
        self.lbl_phase3_preset_ab = QLabel("Preset A/B: A nein • B nein • Compare aus")
        self.lbl_phase3_preset_ab.setWordWrap(True)
        phase3_actions = QHBoxLayout()
        self.btn_phase3_init = QPushButton("Init Patch")
        self.btn_phase3_init.clicked.connect(lambda _=False: self._apply_init_patch())
        self.btn_phase3_restore = QPushButton("Restore Preset Defaults")
        self.btn_phase3_restore.clicked.connect(lambda _=False: self._restore_current_preset_defaults())
        phase3_actions.addWidget(self.btn_phase3_init)
        phase3_actions.addWidget(self.btn_phase3_restore)
        preset_ab_actions = QGridLayout()
        preset_ab_actions.setHorizontalSpacing(6)
        preset_ab_actions.setVerticalSpacing(4)
        self.btn_phase3_store_a = QPushButton("Store A")
        self.btn_phase3_store_b = QPushButton("Store B")
        self.btn_phase3_recall_a = QPushButton("Recall A")
        self.btn_phase3_recall_b = QPushButton("Recall B")
        self.btn_phase3_compare_ab = QPushButton("Compare A/B")
        self.btn_phase3_store_a.clicked.connect(lambda _=False: self._store_preset_ab_slot("A"))
        self.btn_phase3_store_b.clicked.connect(lambda _=False: self._store_preset_ab_slot("B"))
        self.btn_phase3_recall_a.clicked.connect(lambda _=False: self._recall_preset_ab_slot("A"))
        self.btn_phase3_recall_b.clicked.connect(lambda _=False: self._recall_preset_ab_slot("B"))
        self.btn_phase3_compare_ab.clicked.connect(lambda _=False: self._toggle_preset_ab_compare())
        preset_ab_actions.addWidget(self.btn_phase3_store_a, 0, 0)
        preset_ab_actions.addWidget(self.btn_phase3_store_b, 0, 1)
        preset_ab_actions.addWidget(self.btn_phase3_recall_a, 1, 0)
        preset_ab_actions.addWidget(self.btn_phase3_recall_b, 1, 1)
        preset_ab_actions.addWidget(self.btn_phase3_compare_ab, 0, 2, 2, 1)
        automation_box = QFrame()
        automation_box.setObjectName("aeternaPhase3AutomationBox")
        automation_box_l = QVBoxLayout(automation_box)
        automation_box_l.setContentsMargins(8, 6, 8, 6)
        automation_box_l.setSpacing(4)
        self._phase3_group_labels = {}
        for title in ("Klang", "Raum/Bewegung", "Modulation", "Web"):
            lbl = QLabel(f"{title}: –")
            lbl.setWordWrap(True)
            automation_box_l.addWidget(lbl)
            self._phase3_group_labels[title] = lbl
        sec_phase3.body.addWidget(self.lbl_phase3_summary)
        sec_phase3.body.addWidget(self.lbl_phase3_preset)
        self.lbl_automation_target_card = QLabel(
            "Klang: Morph • Tone • Gain • Release\n"
            "Raum/Bewegung: Space • Motion • Cathedral • Drift\n"
            "Modulation: Chaos • LFO1 Rate • LFO2 Rate • MSEG Rate\n"
            "Web: Web A • Web B"
        )
        self.lbl_automation_target_card.setWordWrap(True)
        self.lbl_automation_target_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_automation_target_hint = QLabel(
            "Sicher für spätere Automation: stabile Knobs sowie Rate/Amount-Ziele. "
            "Nicht als Ziel gedacht: flüchtige UI-Zustände oder rohe interne LFO-/Phasenwerte."
        )
        self.lbl_automation_target_hint.setWordWrap(True)
        self.lbl_automation_target_hint.setObjectName("aeternaAutomationTargetHint")
        self.lbl_automation_ready_title = QLabel("Jetzt lokal freigegeben")
        self.lbl_automation_ready_card = QLabel(
            "Direkt auf Knobs: Morph • Tone • Gain • Release • Space • Motion • Cathedral • Drift • Filter Cutoff • Filter Resonance\n"
            "Voice/Timbre: Pan • Glide • Stereo Spread • Pitch • Shape • Pulse Width\n"
            "Depth/Amounts: Chaos • Web A • Web B • Drive • Feedback"
        )
        self.lbl_automation_ready_card.setWordWrap(True)
        self.lbl_automation_ready_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_automation_ready_hint = QLabel(
            "Bereits lokal freigegeben: Rechtsklick auf einen AETERNA-Knob → 'Show Automation in Arranger'. "
            "Automation = stabile Knobs/Rate/Amount. Modulation selbst weiter über LFO/MSEG/Chaos/Formel."
        )
        self.lbl_automation_ready_hint.setWordWrap(True)
        self.lbl_automation_ready_hint.setObjectName("aeternaAutomationTargetHint")
        self.lbl_automation_quick_title = QLabel("Automation-Schnellzugriff")
        self.lbl_automation_quick_card = QLabel(
            "Direktzugriff auf alle lokal freigegebenen stabilen AETERNA-Knobs. "
            "Klick auf einen Namen öffnet sofort die passende Lane im Arranger."
        )
        self.lbl_automation_quick_card.setWordWrap(True)
        self.lbl_automation_quick_card.setObjectName("aeternaAutomationTargetCard")
        automation_quick_grid = QGridLayout()
        automation_quick_grid.setHorizontalSpacing(6)
        automation_quick_grid.setVerticalSpacing(4)
        self._automation_quick_buttons = {}
        quick_order = [
            "morph", "tone", "gain", "release",
            "space", "motion", "cathedral", "drift",
            "filter_cutoff", "filter_resonance",
            "pan", "glide", "stereo_spread",
            "pitch", "shape", "pulse_width",
            "chaos", "lfo1_rate", "lfo2_rate", "mseg_rate",
            "mod1_amount", "mod2_amount",
            "drive", "feedback",
        ]
        for idx, key in enumerate(quick_order):
            btn = QPushButton(self._automation_ready_label(key))
            btn.setToolTip(self._automation_ready_tooltip(key))
            btn.clicked.connect(lambda _=False, kk=key: self._open_automation_lane_for_key(kk))
            automation_quick_grid.addWidget(btn, idx // 4, idx % 4)
            self._automation_quick_buttons[key] = btn
        self.lbl_automation_quick_status = QLabel(
            "Schnellzugriff: 24 stabile Ziele • Klick öffnet direkt die passende AETERNA-Automation-Lane im Arranger."
        )
        self.lbl_automation_quick_status.setWordWrap(True)
        self.lbl_automation_quick_status.setObjectName("aeternaAutomationTargetHint")
        sec_phase3.body.addWidget(self.lbl_phase3_metadata)
        sec_phase3.body.addWidget(self.lbl_phase3_automation)
        sec_phase3.body.addWidget(automation_box)
        sec_phase3.body.addWidget(self.lbl_automation_target_card)
        sec_phase3.body.addWidget(self.lbl_automation_target_hint)
        sec_phase3.body.addWidget(self.lbl_automation_ready_title)
        sec_phase3.body.addWidget(self.lbl_automation_ready_card)
        sec_phase3.body.addWidget(self.lbl_automation_ready_hint)
        sec_phase3.body.addWidget(self.lbl_automation_quick_title)
        sec_phase3.body.addWidget(self.lbl_automation_quick_card)
        sec_phase3.body.addLayout(automation_quick_grid)
        sec_phase3.body.addWidget(self.lbl_automation_quick_status)
        sec_phase3.body.addWidget(self.lbl_phase3_preset_ab)
        sec_phase3.body.addLayout(phase3_actions)
        sec_phase3.body.addLayout(preset_ab_actions)
        sec_phase3.setMinimumWidth(360)
        top.addWidget(sec_phase3, 0)

        mod_rack_sec = self._register_section(_Section("MOD RACK / FLOW (LOCAL SAFE)", expanded=True))
        mod_rack_sec.setProperty("tone", "flow")
        self.lbl_signal_flow = QLabel()
        self.lbl_signal_flow.setWordWrap(True)
        self.lbl_signal_flow.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_signal_flow, "flow")
        mod_rack_sec.body.addWidget(self.lbl_signal_flow)
        self.lbl_signal_flow_map = QLabel()
        self.lbl_signal_flow_map.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_signal_flow_map.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_signal_flow_map, "flow")
        mod_rack_sec.body.addWidget(self.lbl_signal_flow_map)
        self.flow_diagram = _SignalFlowDiagram()
        mod_rack_sec.body.addWidget(self.flow_diagram)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Quellen"))
        for src_key in ("lfo1", "lfo2", "mseg", "chaos", "env", "vel"):
            chip = _ModSourceChip(src_key, MOD_SOURCE_LABELS.get(src_key, src_key.upper()))
            chip.setToolTip(f"{MOD_SOURCE_LABELS.get(src_key, src_key.upper())}\n{MOD_SOURCE_HINTS.get(src_key, 'lokale Modulationsquelle')}\nDrag & Drop auf ein stabiles Ziel.")
            src_row.addWidget(chip)
        src_row.addStretch(1)
        mod_rack_sec.body.addLayout(src_row)

        assign_row = QHBoxLayout()
        assign_row.addWidget(QLabel("Drop-Slot"))
        self.cmb_mod_assign_slot = QComboBox()
        self.cmb_mod_assign_slot.addItems(["Auto", "Slot A", "Slot B"])
        self.cmb_mod_assign_slot.currentTextChanged.connect(lambda _t: (self._update_mod_rack_card(), self._persist_instrument_state()))
        assign_row.addWidget(self.cmb_mod_assign_slot)
        self.btn_mod_swap = QPushButton("Swap A/B")
        self.btn_mod_swap.clicked.connect(lambda _=False: self._swap_mod_slots())
        assign_row.addWidget(self.btn_mod_swap)
        self.btn_mod_clear_a = QPushButton("Clear A")
        self.btn_mod_clear_a.clicked.connect(lambda _=False: self._clear_mod_slot(1))
        assign_row.addWidget(self.btn_mod_clear_a)
        self.btn_mod_clear_b = QPushButton("Clear B")
        self.btn_mod_clear_b.clicked.connect(lambda _=False: self._clear_mod_slot(2))
        assign_row.addWidget(self.btn_mod_clear_b)
        assign_row.addStretch(1)
        mod_rack_sec.body.addLayout(assign_row)

        target_grid = QGridLayout()
        target_grid.setHorizontalSpacing(6)
        target_grid.setVerticalSpacing(6)
        for idx, (key, label) in enumerate([
            ("morph", "Morph"), ("tone", "Tone"), ("gain", "Gain"),
            ("release", "Release"), ("space", "Space"), ("motion", "Motion"),
            ("cathedral", "Cathedral"), ("drift", "Drift"), ("chaos", "Chaos"),
        ]):
            btn = _ModDropTargetButton(key, label, self._assign_mod_source_to_target)
            btn.clicked.connect(lambda _=False, kk=key: self._open_automation_lane_for_key(kk))
            btn.setToolTip(
                f"{label}\nDrop: Quelle hierher ziehen\nKlick: passende Automation-Lane öffnen\nStabiler AETERNA-Zielparameter."
            )
            target_grid.addWidget(btn, idx // 3, idx % 3)
        mod_rack_sec.body.addWidget(QLabel("Stabile Ziele (Drag & Drop / Klick = Lane)"))
        mod_rack_sec.body.addLayout(target_grid)

        self.lbl_mod_rack_card = QLabel()
        self.lbl_mod_rack_card.setWordWrap(True)
        self.lbl_mod_rack_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_mod_rack_hint = QLabel()
        self.lbl_mod_rack_hint.setWordWrap(True)
        self.lbl_mod_rack_hint.setObjectName("aeternaAutomationTargetHint")
        mod_rack_sec.body.addWidget(self.lbl_mod_rack_card)
        mod_rack_sec.body.addWidget(self.lbl_mod_rack_hint)
        root.addWidget(mod_rack_sec)

        sec_formula = self._register_section(_Section("FORMEL", expanded=True))
        self.lbl_formula_startcard = QLabel(
            "Startkarte: 1) Beispiel antippen oder Preset wählen • 2) Token per Klick einsetzen • 3) Formel im Feld anpassen • 4) Mit 'Formel anwenden' testen. Alles bleibt lokal in AETERNA."
        )
        self.lbl_formula_startcard.setWordWrap(True)
        formula_start_row = QHBoxLayout()
        formula_start_row.setSpacing(6)
        formula_start_row.addWidget(QLabel("Start"))
        self._formula_onboarding_buttons = []
        for title, hint, formula in FORMULA_ONBOARDING_PRESETS:
            btn = QPushButton(title)
            btn.setToolTip(f"{hint}\n{self._format_hearing_tags(self._formula_suggestion_hearing_tags(title, hint), prefix='Hörbild')}")
            btn.clicked.connect(lambda _=False, ff=formula, tt=title: self._load_formula_onboarding_preset(ff, tt))
            self._formula_onboarding_buttons.append(btn)
            formula_start_row.addWidget(btn)
        formula_start_row.addStretch(1)
        self.lbl_formula_onboarding_hint = QLabel("Beispiele ersetzen das Feld lokal, aber erst 'Formel anwenden' übernimmt sie in den Klang.")
        self.lbl_formula_onboarding_hint.setWordWrap(True)
        formula_preset_link_row = QHBoxLayout()
        formula_preset_link_row.setSpacing(6)
        self.lbl_formula_preset_link = QLabel("Preset→Formel: passende Idee wird lokal ermittelt")
        self.lbl_formula_preset_link.setWordWrap(True)
        self.btn_formula_preset_link_load = QPushButton("Passende Idee laden")
        self.btn_formula_preset_link_load.clicked.connect(lambda _=False: self._load_linked_formula_preset())
        formula_preset_link_row.addWidget(self.lbl_formula_preset_link, 1)
        formula_preset_link_row.addWidget(self.btn_formula_preset_link_load)
        self.lbl_formula_preset_hearing = QLabel("Hörhinweise: –")
        self.lbl_formula_preset_hearing.setWordWrap(True)
        self.lbl_formula_info = QLabel("Formelstatus: Init geladen")
        self.lbl_formula_info.setWordWrap(True)
        self.ed_formula = _FormulaLineEdit(DEFAULT_FORMULA)
        self.ed_formula.setPlaceholderText("z.B. sin(phase + m*sin(0.5*phase))")
        try:
            self.ed_formula.textChanged.connect(self._on_formula_text_changed)
        except Exception:
            pass
        btn_apply_formula = QPushButton("Formel anwenden")
        btn_apply_formula.clicked.connect(lambda _=False: self._apply_formula_from_ui())
        lbl_formula_help = QLabel("LFO/MSEG-Quellen per Klick oder Drag&Drop direkt in die Formel einsetzen. Mehrzeiliges Feld für längere Formeln, Anwenden bleibt bewusst am Button.")
        lbl_formula_help.setWordWrap(True)
        formula_token_row = QHBoxLayout()
        formula_token_row.setSpacing(6)
        formula_token_row.addWidget(QLabel("Insert"))
        self._formula_token_buttons = []
        for label, token in FORMULA_HELP_TOKENS:
            btn = _FormulaTokenButton(label, token, self._insert_formula_token)
            self._formula_token_buttons.append(btn)
            formula_token_row.addWidget(btn)
        formula_token_row.addStretch(1)
        formula_snippet_row = QHBoxLayout()
        formula_snippet_row.setSpacing(6)
        formula_snippet_row.addWidget(QLabel("Quick"))
        self.cmb_formula_snippet = QComboBox()
        for label, snippet in FORMULA_HELP_SNIPPETS:
            self.cmb_formula_snippet.addItem(label, snippet)
        self.btn_insert_formula_snippet = QPushButton("Snippet einfügen")
        self.btn_insert_formula_snippet.clicked.connect(lambda _=False: self._insert_formula_snippet())
        formula_snippet_row.addWidget(self.cmb_formula_snippet, 1)
        formula_snippet_row.addWidget(self.btn_insert_formula_snippet)
        self.lbl_formula_mod_slots = QLabel("Aktive Formelquellen: –")
        self.lbl_formula_mod_slots.setWordWrap(True)
        self.lbl_formula_mod_normalized = QLabel("Alias-Ansicht: –")
        self.lbl_formula_mod_normalized.setWordWrap(True)
        sec_formula.body.addWidget(self.lbl_formula_startcard)
        sec_formula.body.addLayout(formula_start_row)
        sec_formula.body.addWidget(self.lbl_formula_onboarding_hint)
        sec_formula.body.addLayout(formula_preset_link_row)
        sec_formula.body.addWidget(self.lbl_formula_preset_hearing)
        sec_formula.body.addWidget(self.lbl_formula_info)
        sec_formula.body.addWidget(self.ed_formula)
        sec_formula.body.addWidget(lbl_formula_help)
        sec_formula.body.addLayout(formula_token_row)
        sec_formula.body.addLayout(formula_snippet_row)
        sec_formula.body.addWidget(self.lbl_formula_mod_slots)
        sec_formula.body.addWidget(self.lbl_formula_mod_normalized)
        sec_formula.body.addWidget(btn_apply_formula)
        sec_formula.setMinimumWidth(520)
        top.addWidget(sec_formula, 1)
        root.addLayout(top)

        # ── WAVETABLE SECTION (v0.0.20.657) ──
        sec_wt = self._register_section(_Section("WAVETABLE", expanded=False))
        self._wt_section = sec_wt

        wt_table_row = QHBoxLayout()
        wt_table_row.setSpacing(4)
        self.cmb_wt_builtin = QComboBox()
        self.cmb_wt_builtin.addItems(self.engine.get_wavetable_builtin_names())
        self.cmb_wt_builtin.currentTextChanged.connect(self._on_wt_builtin_changed)
        self.btn_wt_import = QPushButton("Import .wav/.wt")
        self.btn_wt_import.clicked.connect(self._on_wt_import)
        self.lbl_wt_name = QLabel("Basic (Sine→Saw)")
        self.lbl_wt_name.setStyleSheet("font-weight: bold; color: #c8d6e5;")
        wt_table_row.addWidget(QLabel("Table"))
        wt_table_row.addWidget(self.cmb_wt_builtin, 1)
        wt_table_row.addWidget(self.btn_wt_import)
        sec_wt.body.addLayout(wt_table_row)
        sec_wt.body.addWidget(self.lbl_wt_name)

        # Waveform preview
        self._wt_preview = _WavetablePreviewWidget(self.engine)
        sec_wt.body.addWidget(self._wt_preview)

        # Position slider
        wt_pos_row = QHBoxLayout()
        wt_pos_row.setSpacing(6)
        wt_pos_row.addWidget(QLabel("Position"))
        self.sld_wt_position = QSlider(Qt.Orientation.Horizontal)
        self.sld_wt_position.setRange(0, 1000)
        self.sld_wt_position.setValue(0)
        self.sld_wt_position.valueChanged.connect(self._on_wt_position_changed)
        self.lbl_wt_position = QLabel("0.000")
        self.lbl_wt_position.setFixedWidth(44)
        wt_pos_row.addWidget(self.sld_wt_position, 1)
        wt_pos_row.addWidget(self.lbl_wt_position)
        sec_wt.body.addLayout(wt_pos_row)

        # Unison controls
        wt_uni_row = QHBoxLayout()
        wt_uni_row.setSpacing(4)
        self.cmb_wt_unison_mode = QComboBox()
        self.cmb_wt_unison_mode.addItems(["Off", "Classic", "Supersaw", "Hyper"])
        self.cmb_wt_unison_mode.currentTextChanged.connect(self._on_wt_unison_changed)
        self.spn_wt_unison_voices = QSpinBox()
        self.spn_wt_unison_voices.setRange(1, 16)
        self.spn_wt_unison_voices.setValue(1)
        self.spn_wt_unison_voices.valueChanged.connect(self._on_wt_unison_changed)
        wt_uni_row.addWidget(QLabel("Unison"))
        wt_uni_row.addWidget(self.cmb_wt_unison_mode)
        wt_uni_row.addWidget(QLabel("Voices"))
        wt_uni_row.addWidget(self.spn_wt_unison_voices)
        sec_wt.body.addLayout(wt_uni_row)

        wt_uni_row2 = QHBoxLayout()
        wt_uni_row2.setSpacing(4)
        self.sld_wt_detune = QSlider(Qt.Orientation.Horizontal)
        self.sld_wt_detune.setRange(0, 100)
        self.sld_wt_detune.setValue(20)
        self.sld_wt_detune.valueChanged.connect(self._on_wt_unison_changed)
        self.sld_wt_spread = QSlider(Qt.Orientation.Horizontal)
        self.sld_wt_spread.setRange(0, 100)
        self.sld_wt_spread.setValue(50)
        self.sld_wt_spread.valueChanged.connect(self._on_wt_unison_changed)
        self.sld_wt_width = QSlider(Qt.Orientation.Horizontal)
        self.sld_wt_width.setRange(0, 100)
        self.sld_wt_width.setValue(50)
        self.sld_wt_width.valueChanged.connect(self._on_wt_unison_changed)
        wt_uni_row2.addWidget(QLabel("Detune"))
        wt_uni_row2.addWidget(self.sld_wt_detune)
        wt_uni_row2.addWidget(QLabel("Spread"))
        wt_uni_row2.addWidget(self.sld_wt_spread)
        wt_uni_row2.addWidget(QLabel("Width"))
        wt_uni_row2.addWidget(self.sld_wt_width)
        sec_wt.body.addLayout(wt_uni_row2)

        # Frame info + FFT button
        wt_info_row = QHBoxLayout()
        wt_info_row.setSpacing(4)
        self.lbl_wt_info = QLabel("16 Frames, 2048 samples")
        self.btn_wt_normalize = QPushButton("Normalize")
        self.btn_wt_normalize.clicked.connect(self._on_wt_normalize)
        wt_info_row.addWidget(self.lbl_wt_info, 1)
        wt_info_row.addWidget(self.btn_wt_normalize)
        sec_wt.body.addLayout(wt_info_row)

        root.addWidget(sec_wt)

        sec_scope = self._register_section(_Section("SCOPE", expanded=True))
        self.scope = _ScopeWidget(self.engine)
        self.lbl_help = QLabel("Phase 3 safe UI: große lokale Modulations-Preview mit Grid, Quelle-Auswahl und Phase-Markierung. Kein globaler DAW-Core-Eingriff.")
        self.lbl_help.setWordWrap(True)
        sec_scope.body.addWidget(self.scope)
        sec_scope.body.addWidget(self.lbl_help)
        root.addWidget(sec_scope)

        comp_sec = self._register_section(_Section("AETERNA COMPOSER (LOCAL SAFE)", expanded=False))
        comp_header = QHBoxLayout()
        comp_header.setSpacing(6)
        comp_header.addWidget(QLabel("Weltstil-Katalog"))
        self.cmb_comp_family = QComboBox()
        self.cmb_comp_family.addItems(list(AETERNA_WORLD_STYLE_GROUPS.keys()))
        self.cmb_comp_family.currentTextChanged.connect(self._on_comp_family_changed)
        comp_header.addWidget(self.cmb_comp_family)
        self.btn_comp_roll = QPushButton("Style-Mix")
        self.btn_comp_roll.clicked.connect(lambda _=False: self._roll_composer_style_mix())
        comp_header.addWidget(self.btn_comp_roll)
        self.btn_comp_actions = QToolButton()
        self.btn_comp_actions.setText("▾ MIDI erzeugen")
        self.btn_comp_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        comp_menu = QMenu(self.btn_comp_actions)
        act_new = comp_menu.addAction("Neuer MIDI-Clip auf dieser AETERNA-Spur")
        act_over = comp_menu.addAction("Aktiven MIDI-Clip dieser Spur überschreiben")
        comp_menu.addSeparator()
        act_seed = comp_menu.addAction("Seed neu würfeln")
        act_mix = comp_menu.addAction("Stil-Mix neu würfeln")
        act_new.triggered.connect(self._composer_new_clip)
        act_over.triggered.connect(self._composer_overwrite_active_clip)
        act_seed.triggered.connect(self._roll_composer_seed)
        act_mix.triggered.connect(self._roll_composer_style_mix)
        self.btn_comp_actions.setMenu(comp_menu)
        comp_header.addWidget(self.btn_comp_actions)
        comp_header.addStretch(1)
        comp_sec.body.addLayout(comp_header)

        style_row = QGridLayout()
        style_row.setHorizontalSpacing(6)
        style_row.setVerticalSpacing(4)
        style_row.addWidget(QLabel("Style A"), 0, 0)
        self.cmb_comp_style_a = QComboBox()
        self.cmb_comp_style_a.setEditable(True)
        self.cmb_comp_style_a.addItems(self._composer_catalog_for_family(self._preferred_composer_family_from_preset()))
        self.cmb_comp_style_a.setCurrentText("Gregorianik")
        self.cmb_comp_style_a.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_style_a, 0, 1)
        style_row.addWidget(QLabel("Style B"), 0, 2)
        self.cmb_comp_style_b = QComboBox()
        self.cmb_comp_style_b.setEditable(True)
        self.cmb_comp_style_b.addItems(self._composer_catalog_for_family(self._preferred_composer_family_from_preset()))
        self.cmb_comp_style_b.setCurrentText("Ambient")
        self.cmb_comp_style_b.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_style_b, 0, 3)
        style_row.addWidget(QLabel("Kontext"), 1, 0)
        self.cmb_comp_context = QComboBox()
        self.cmb_comp_context.addItems(list(AETERNA_COMPOSER_CONTEXTS))
        self.cmb_comp_context.setCurrentText("Gottesdienst")
        self.cmb_comp_context.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_context, 1, 1)
        style_row.addWidget(QLabel("Form"), 1, 2)
        self.cmb_comp_form = QComboBox()
        self.cmb_comp_form.addItems(list(AETERNA_COMPOSER_FORMS))
        self.cmb_comp_form.setCurrentText("Pad/Drone + Melodie")
        self.cmb_comp_form.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_form, 1, 3)
        style_row.addWidget(QLabel("Phrase"), 2, 0)
        self.cmb_comp_phrase = QComboBox()
        self.cmb_comp_phrase.addItems(list(AETERNA_COMPOSER_PHRASE_PROFILES))
        self.cmb_comp_phrase.setCurrentText("Ausgewogen")
        self.cmb_comp_phrase.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_phrase, 2, 1)
        style_row.addWidget(QLabel("Dichteprofil"), 2, 2)
        self.cmb_comp_density_profile = QComboBox()
        self.cmb_comp_density_profile.addItems(list(AETERNA_COMPOSER_DENSITY_PROFILES))
        self.cmb_comp_density_profile.setCurrentText("Mittel")
        self.cmb_comp_density_profile.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        style_row.addWidget(self.cmb_comp_density_profile, 2, 3)
        comp_sec.body.addLayout(style_row)

        part_row = QHBoxLayout()
        part_row.setSpacing(6)
        self.chk_comp_bass = QCheckBox("Bass")
        self.chk_comp_bass.setChecked(True)
        self.chk_comp_melody = QCheckBox("Melodie")
        self.chk_comp_melody.setChecked(True)
        self.chk_comp_lead = QCheckBox("Lead")
        self.chk_comp_lead.setChecked(True)
        self.chk_comp_pad = QCheckBox("Pad")
        self.chk_comp_pad.setChecked(True)
        self.chk_comp_arp = QCheckBox("Arp")
        self.chk_comp_arp.setChecked(True)
        for chk in (self.chk_comp_bass, self.chk_comp_melody, self.chk_comp_lead, self.chk_comp_pad, self.chk_comp_arp):
            chk.toggled.connect(lambda _v=False: (self._update_composer_summary(), self._persist_instrument_state()))
            part_row.addWidget(chk)
        part_row.addStretch(1)
        comp_sec.body.addLayout(part_row)

        gen_row = QGridLayout()
        gen_row.setHorizontalSpacing(6)
        gen_row.setVerticalSpacing(4)
        gen_row.addWidget(QLabel("Bars"), 0, 0)
        self.spn_comp_bars = QSpinBox()
        self.spn_comp_bars.setRange(1, 64)
        self.spn_comp_bars.setValue(8)
        self.spn_comp_bars.valueChanged.connect(lambda _v: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.spn_comp_bars, 0, 1)
        gen_row.addWidget(QLabel("Grid"), 0, 2)
        self.cmb_comp_grid = QComboBox()
        self.cmb_comp_grid.addItems(list(AETERNA_COMPOSER_GRID_MAP.keys()))
        self.cmb_comp_grid.setCurrentText("1/16")
        self.cmb_comp_grid.currentTextChanged.connect(lambda _t: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.cmb_comp_grid, 0, 3)
        gen_row.addWidget(QLabel("Swing"), 1, 0)
        self.spn_comp_swing = QDoubleSpinBox()
        self.spn_comp_swing.setRange(0.0, 0.95)
        self.spn_comp_swing.setSingleStep(0.05)
        self.spn_comp_swing.setDecimals(2)
        self.spn_comp_swing.setValue(0.12)
        self.spn_comp_swing.valueChanged.connect(lambda _v: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.spn_comp_swing, 1, 1)
        gen_row.addWidget(QLabel("Dichte"), 1, 2)
        self.spn_comp_density = QDoubleSpinBox()
        self.spn_comp_density.setRange(0.05, 1.0)
        self.spn_comp_density.setSingleStep(0.05)
        self.spn_comp_density.setDecimals(2)
        self.spn_comp_density.setValue(0.62)
        self.spn_comp_density.valueChanged.connect(lambda _v: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.spn_comp_density, 1, 3)
        gen_row.addWidget(QLabel("Mix"), 2, 0)
        self.spn_comp_hybrid = QDoubleSpinBox()
        self.spn_comp_hybrid.setRange(0.0, 1.0)
        self.spn_comp_hybrid.setSingleStep(0.05)
        self.spn_comp_hybrid.setDecimals(2)
        self.spn_comp_hybrid.setValue(0.58)
        self.spn_comp_hybrid.valueChanged.connect(lambda _v: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.spn_comp_hybrid, 2, 1)
        gen_row.addWidget(QLabel("Seed"), 2, 2)
        self.spn_comp_seed = QSpinBox()
        self.spn_comp_seed.setRange(1, 999999999)
        self.spn_comp_seed.setValue(314159)
        self.spn_comp_seed.valueChanged.connect(lambda _v: (self._update_composer_summary(), self._persist_instrument_state()))
        gen_row.addWidget(self.spn_comp_seed, 2, 3)
        comp_sec.body.addLayout(gen_row)

        self.lbl_comp_summary = QLabel("AETERNA Composer bereit")
        self.lbl_comp_summary.setWordWrap(True)
        self.lbl_comp_summary.setObjectName("aeternaAutomationTargetCard")
        self.lbl_comp_hint = QLabel("Mathematischer Local Composer für AETERNA: Weltstil-Katalog + freie Eingabe + Bass/Melodie/Lead/Pad/Arp.")
        self.lbl_comp_hint.setWordWrap(True)
        self.lbl_comp_hint.setObjectName("aeternaAutomationTargetHint")
        self.lbl_perf_status = QLabel("AETERNA Ladeprofil: lokale Messung wird vorbereitet")
        self.lbl_perf_status.setWordWrap(True)
        self.lbl_perf_status.setObjectName("aeternaAutomationTargetCard")
        self.lbl_perf_hint = QLabel("Lokale Messung nur für AETERNA-Widget-Aufbau/Restore/Staged-Refresh.")
        self.lbl_perf_hint.setWordWrap(True)
        self.lbl_perf_hint.setObjectName("aeternaAutomationTargetHint")
        comp_sec.body.addWidget(self.lbl_comp_summary)
        comp_sec.body.addWidget(self.lbl_comp_hint)
        comp_sec.body.addWidget(self.lbl_perf_status)
        comp_sec.body.addWidget(self.lbl_perf_hint)
        root.addWidget(comp_sec)
        self.cmb_comp_family.setCurrentText(self._preferred_composer_family_from_preset())
        self._update_composer_summary()

        arp_sec = self._register_section(_Section("AETERNA ARP A (LOCAL SAFE)", expanded=False))
        arp_header = QHBoxLayout()
        arp_header.setSpacing(6)
        arp_header.addWidget(QLabel("Pattern"))
        self.cmb_arp_pattern = QComboBox()
        self.cmb_arp_pattern.addItems(list(AETERNA_ARP_PATTERNS))
        self.cmb_arp_pattern.setCurrentText("up")
        self.cmb_arp_pattern.currentTextChanged.connect(lambda _t: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_header.addWidget(self.cmb_arp_pattern)
        arp_header.addWidget(QLabel("Rate"))
        self.cmb_arp_rate = QComboBox()
        self.cmb_arp_rate.addItems(list(AETERNA_ARP_RATES))
        self.cmb_arp_rate.setCurrentText("1/16")
        self.cmb_arp_rate.currentTextChanged.connect(lambda _t: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_header.addWidget(self.cmb_arp_rate)
        arp_header.addWidget(QLabel("Type"))
        self.cmb_arp_note_type = QComboBox()
        self.cmb_arp_note_type.addItems([x[0] for x in AETERNA_ARP_NOTE_TYPES])
        self.cmb_arp_note_type.setCurrentText("Straight")
        self.cmb_arp_note_type.currentTextChanged.connect(lambda _t: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_header.addWidget(self.cmb_arp_note_type)
        self.chk_arp_live_enabled = QCheckBox("ARP Live")
        self.chk_arp_live_enabled.toggled.connect(lambda on=False: self._set_arp_live_enabled(bool(on), persist=True))
        arp_header.addWidget(self.chk_arp_live_enabled)
        self.btn_arp_sync_live = QPushButton("Live ARP aus")
        self.btn_arp_sync_live.clicked.connect(lambda _=False: self._sync_live_arp_device(persist=True))
        arp_header.addWidget(self.btn_arp_sync_live)
        self.btn_arp_actions = QToolButton()
        self.btn_arp_actions.setText("▾ ARP → MIDI")
        self.btn_arp_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        arp_menu = QMenu(self.btn_arp_actions)
        act_arp_new = arp_menu.addAction("Neuer MIDI-Clip auf dieser AETERNA-Spur")
        act_arp_over = arp_menu.addAction("Aktiven MIDI-Clip dieser Spur überschreiben")
        arp_menu.addSeparator()
        act_arp_seed = arp_menu.addAction("ARP-Seed neu würfeln")
        act_arp_new.triggered.connect(self._arp_new_clip)
        act_arp_over.triggered.connect(self._arp_overwrite_active_clip)
        act_arp_seed.triggered.connect(self._roll_arp_seed)
        self.btn_arp_actions.setMenu(arp_menu)
        arp_header.addWidget(self.btn_arp_actions)
        self.lbl_arp_live_status = QLabel("ARP Live: aus")
        self.lbl_arp_live_status.setObjectName("aeternaAutomationTargetHint")
        arp_header.addWidget(self.lbl_arp_live_status)
        arp_header.addStretch(1)
        arp_sec.body.addLayout(arp_header)

        arp_top = QGridLayout()
        arp_top.setHorizontalSpacing(6)
        arp_top.setVerticalSpacing(4)
        arp_top.addWidget(QLabel("Root"), 0, 0)
        self.spn_arp_root = QSpinBox()
        self.spn_arp_root.setRange(24, 96)
        self.spn_arp_root.setValue(60)
        self.spn_arp_root.valueChanged.connect(lambda _v: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.spn_arp_root, 0, 1)
        arp_top.addWidget(QLabel("Chord"), 0, 2)
        self.cmb_arp_chord = QComboBox()
        self.cmb_arp_chord.addItems(list(AETERNA_ARP_CHORDS.keys()))
        self.cmb_arp_chord.setCurrentText("Minor Triad")
        self.cmb_arp_chord.currentTextChanged.connect(lambda _t: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.cmb_arp_chord, 0, 3)
        arp_top.addWidget(QLabel("Steps"), 1, 0)
        self.spn_arp_steps = QSpinBox()
        self.spn_arp_steps.setRange(1, 16)
        self.spn_arp_steps.setValue(16)
        self.spn_arp_steps.valueChanged.connect(lambda _v: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.spn_arp_steps, 1, 1)
        self.chk_arp_shuffle = QCheckBox("Shuffle")
        self.chk_arp_shuffle.toggled.connect(lambda _v=False: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.chk_arp_shuffle, 1, 2)
        self.spn_arp_shuffle_steps = QSpinBox()
        self.spn_arp_shuffle_steps.setRange(1, 16)
        self.spn_arp_shuffle_steps.setValue(16)
        self.spn_arp_shuffle_steps.valueChanged.connect(lambda _v: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.spn_arp_shuffle_steps, 1, 3)
        arp_top.addWidget(QLabel("Seed"), 2, 0)
        self.spn_arp_seed = QSpinBox()
        self.spn_arp_seed.setRange(1, 999999999)
        self.spn_arp_seed.setValue(2401)
        self.spn_arp_seed.valueChanged.connect(lambda _v: (self._update_arp_summary(), self._persist_instrument_state()))
        arp_top.addWidget(self.spn_arp_seed, 2, 1)
        self.lbl_arp_summary = QLabel("Arp A bereit")
        self.lbl_arp_summary.setWordWrap(True)
        self.lbl_arp_summary.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_arp_summary, "mod")
        arp_top.addWidget(self.lbl_arp_summary, 2, 2, 1, 2)
        arp_sec.body.addLayout(arp_top)

        arp_steps_grid = QGridLayout()
        arp_steps_grid.setHorizontalSpacing(6)
        arp_steps_grid.setVerticalSpacing(6)
        for idx in range(16):
            box = QFrame()
            box.setObjectName("aeternaSection")
            box_l = QVBoxLayout(box)
            box_l.setContentsMargins(6, 6, 6, 6)
            box_l.setSpacing(4)
            lab = QLabel(f"Step {idx + 1}")
            box_l.addWidget(lab)
            tr = QSpinBox()
            tr.setRange(-24, 24)
            tr.setValue(0)
            tr.setPrefix("Tr ")
            tr.valueChanged.connect(lambda _v, i=idx: (self._update_arp_summary(), self._persist_instrument_state()))
            setattr(self, f"spn_arp_step_transpose_{idx}", tr)
            box_l.addWidget(tr)
            sk = QCheckBox("Skip")
            sk.toggled.connect(lambda _v=False, i=idx: (self._update_arp_summary(), self._persist_instrument_state()))
            setattr(self, f"chk_arp_step_skip_{idx}", sk)
            box_l.addWidget(sk)
            vel = QSpinBox()
            vel.setRange(1, 127)
            vel.setValue(100)
            vel.setPrefix("Vel ")
            vel.valueChanged.connect(lambda _v, i=idx: (self._update_arp_summary(), self._persist_instrument_state()))
            setattr(self, f"spn_arp_step_velocity_{idx}", vel)
            box_l.addWidget(vel)
            gate = QSpinBox()
            gate.setRange(0, 400)
            gate.setValue(100)
            gate.setSuffix("% Gate")
            gate.valueChanged.connect(lambda _v, i=idx: (self._update_arp_summary(), self._persist_instrument_state()))
            setattr(self, f"spn_arp_step_gate_{idx}", gate)
            box_l.addWidget(gate)
            arp_steps_grid.addWidget(box, idx // 4, idx % 4)
        arp_sec.body.addLayout(arp_steps_grid)
        self.lbl_arp_hint = QLabel("Arp A ist jetzt zweigleisig: Live ARP über das vorhandene Track-Note-FX-Arp und optional ARP→MIDI zum Festschreiben. Root/Chord gelten vor allem für ARP→MIDI; Live ARP nutzt die eingehenden Noten der Spur. Pattern, Rate, Straight/Dotted/Triplets und 16 Steps mit Transpose/Skip/Velocity/Gate bleiben lokal in AETERNA editierbar.")
        self.lbl_arp_hint.setWordWrap(True)
        self.lbl_arp_hint.setObjectName("aeternaAutomationTargetHint")
        arp_sec.body.addWidget(self.lbl_arp_hint)
        root.addWidget(arp_sec)
        self._update_arp_summary()

        sec_mod_preview = self._register_section(_Section("GROSSE MODULATIONS-PREVIEW", expanded=False))
        preview_toolbar = QGridLayout()
        preview_toolbar.setHorizontalSpacing(8)
        preview_toolbar.setVerticalSpacing(6)

        def _tb_add(row: int, col: int, widget, stretch: int = 0):
            try:
                if isinstance(widget, QLabel):
                    widget.setWordWrap(False)
                widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            except Exception:
                pass
            preview_toolbar.addWidget(widget, row, col, 1, max(1, stretch or 1))
            self._mseg_toolbar_rows.setdefault(int(row), []).append(widget)
            if row >= 4:
                try:
                    widget.setVisible(bool(self._mseg_advanced_visible))
                except Exception:
                    pass

        self._mod_view_buttons = {}
        col = 0
        for key, title in (("mseg", "MSEG"), ("lfo1", "LFO1"), ("lfo2", "LFO2"), ("chaos", "Chaos")):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setMinimumWidth(78)
            btn.clicked.connect(lambda checked=False, kk=key: self._set_mod_view(kk))
            self._mod_view_buttons[key] = btn
            _tb_add(0, col, btn)
            col += 1
        self.chk_overlay_web_a = QCheckBox("Overlay Web A")
        self.chk_overlay_web_b = QCheckBox("Overlay Web B")
        self.chk_overlay_web_a.setChecked(True)
        self.chk_overlay_web_b.setChecked(True)
        self.chk_overlay_web_a.toggled.connect(lambda checked: self._set_overlay_visibility(checked, None))
        self.chk_overlay_web_b.toggled.connect(lambda checked: self._set_overlay_visibility(None, checked))
        _tb_add(0, col, self.chk_overlay_web_a, 2); col += 2
        _tb_add(0, col, self.chk_overlay_web_b, 2); col += 2
        self.btn_toggle_mseg_advanced = QPushButton("Advanced MSEG ▸")
        self.btn_toggle_mseg_advanced.setCheckable(True)
        self.btn_toggle_mseg_advanced.clicked.connect(lambda checked=False: self._set_mseg_advanced_visible(bool(checked)))
        _tb_add(0, col, self.btn_toggle_mseg_advanced, 2); col += 2
        self.lbl_mseg_start_here = QLabel("Start hier: Shape → Apply Shape → Punkte ziehen")
        _tb_add(0, col, self.lbl_mseg_start_here, 3)

        r = 1
        _tb_add(r, 0, QLabel("Shape"))
        self.cmb_mseg_shape = QComboBox()
        self.cmb_mseg_shape.addItems(list(self.engine.get_mseg_shape_preset_names()))
        _tb_add(r, 1, self.cmb_mseg_shape, 2)
        self.btn_apply_mseg_shape = QPushButton("Apply Shape")
        self.btn_apply_mseg_shape.clicked.connect(lambda _=False: self._apply_mseg_shape_preset())
        _tb_add(r, 3, self.btn_apply_mseg_shape)
        self.btn_mseg_invert = QPushButton("Invert")
        self.btn_mseg_invert.clicked.connect(lambda _=False: self._apply_mseg_operation("invert"))
        _tb_add(r, 4, self.btn_mseg_invert)
        self.btn_mseg_mirror = QPushButton("Mirror")
        self.btn_mseg_mirror.clicked.connect(lambda _=False: self._apply_mseg_operation("mirror"))
        _tb_add(r, 5, self.btn_mseg_mirror)
        self.btn_mseg_normalize = QPushButton("Normalize")
        self.btn_mseg_normalize.clicked.connect(lambda _=False: self._apply_mseg_operation("normalize"))
        _tb_add(r, 6, self.btn_mseg_normalize)
        self.btn_reset_mseg = QPushButton("MSEG Reset")
        self.btn_reset_mseg.clicked.connect(lambda _=False: self._reset_mseg_points())
        _tb_add(r, 7, self.btn_reset_mseg)

        r = 2
        self.btn_mseg_stretch = QPushButton("Stretch")
        self.btn_mseg_stretch.clicked.connect(lambda _=False: self._apply_mseg_operation("stretch"))
        _tb_add(r, 0, self.btn_mseg_stretch)
        self.btn_mseg_compress = QPushButton("Compress")
        self.btn_mseg_compress.clicked.connect(lambda _=False: self._apply_mseg_operation("compress"))
        _tb_add(r, 1, self.btn_mseg_compress)
        _tb_add(r, 2, QLabel("Snap X"))
        self.cmb_mseg_snap = QComboBox()
        self.cmb_mseg_snap.addItems([str(v) for v in MSEG_SNAP_DIVISIONS])
        self.cmb_mseg_snap.setCurrentText("16")
        _tb_add(r, 3, self.cmb_mseg_snap)
        self.btn_mseg_snap = QPushButton("Snap")
        self.btn_mseg_snap.clicked.connect(lambda _=False: self._apply_mseg_operation("snap_x"))
        _tb_add(r, 4, self.btn_mseg_snap)
        _tb_add(r, 5, QLabel("Quant Y"))
        self.cmb_mseg_y_quant = QComboBox()
        self.cmb_mseg_y_quant.addItems([str(v) for v in MSEG_Y_QUANTIZE_LEVELS])
        self.cmb_mseg_y_quant.setCurrentText("9")
        _tb_add(r, 6, self.cmb_mseg_y_quant)
        self.btn_mseg_quant_y = QPushButton("Quantize")
        self.btn_mseg_quant_y.clicked.connect(lambda _=False: self._apply_mseg_operation("quantize_y"))
        _tb_add(r, 7, self.btn_mseg_quant_y)

        r = 3
        self.btn_mseg_smooth = QPushButton("Smooth")
        self.btn_mseg_smooth.clicked.connect(lambda _=False: self._apply_mseg_operation("smooth"))
        _tb_add(r, 0, self.btn_mseg_smooth)
        self.btn_mseg_double = QPushButton("Double")
        self.btn_mseg_double.clicked.connect(lambda _=False: self._apply_mseg_operation("double"))
        _tb_add(r, 1, self.btn_mseg_double)
        self.btn_mseg_halve = QPushButton("Halve")
        self.btn_mseg_halve.clicked.connect(lambda _=False: self._apply_mseg_operation("halve"))
        _tb_add(r, 2, self.btn_mseg_halve)
        self.btn_mseg_bias_down = QPushButton("Bias -")
        self.btn_mseg_bias_down.clicked.connect(lambda _=False: self._apply_mseg_operation("bias_down"))
        _tb_add(r, 3, self.btn_mseg_bias_down)
        self.btn_mseg_bias_up = QPushButton("Bias +")
        self.btn_mseg_bias_up.clicked.connect(lambda _=False: self._apply_mseg_operation("bias_up"))
        _tb_add(r, 4, self.btn_mseg_bias_up)
        _tb_add(r, 5, QLabel("Segment"))
        self.cmb_segment_form = QComboBox()
        self.cmb_segment_form.addItems([txt.title() for txt in MSEG_SEGMENT_FORMS])
        self.cmb_segment_form.currentTextChanged.connect(lambda txt: self._on_segment_form_changed(txt))
        _tb_add(r, 6, self.cmb_segment_form, 2)

        r = 4
        _tb_add(r, 0, QLabel("Morph →"))
        self.cmb_mseg_morph_shape = QComboBox()
        self.cmb_mseg_morph_shape.addItems(list(self.engine.get_mseg_shape_preset_names()))
        self.cmb_mseg_morph_shape.setCurrentText("Triangle")
        self.cmb_mseg_morph_shape.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 1, self.cmb_mseg_morph_shape, 2)
        self.cmb_mseg_morph_amount = QComboBox()
        self.cmb_mseg_morph_amount.addItems(list(MSEG_MORPH_AMOUNTS))
        self.cmb_mseg_morph_amount.setCurrentText("50")
        self.cmb_mseg_morph_amount.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 3, self.cmb_mseg_morph_amount)
        self.btn_mseg_morph = QPushButton("Morph")
        self.btn_mseg_morph.clicked.connect(lambda _=False: self._apply_mseg_operation("morph_shape"))
        _tb_add(r, 4, self.btn_mseg_morph)
        _tb_add(r, 5, QLabel("Rand %"))
        self.cmb_mseg_random = QComboBox()
        self.cmb_mseg_random.addItems(list(MSEG_RANDOMIZE_AMOUNTS))
        self.cmb_mseg_random.setCurrentText("35")
        self.cmb_mseg_random.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 6, self.cmb_mseg_random)
        self.btn_mseg_random = QPushButton("Randomize")
        self.btn_mseg_random.clicked.connect(lambda _=False: self._apply_mseg_operation("randomize"))
        _tb_add(r, 7, self.btn_mseg_random)

        r = 5
        _tb_add(r, 0, QLabel("Jitter"))
        self.cmb_mseg_jitter = QComboBox()
        self.cmb_mseg_jitter.addItems(list(MSEG_JITTER_AMOUNTS))
        self.cmb_mseg_jitter.setCurrentText("4")
        self.cmb_mseg_jitter.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 1, self.cmb_mseg_jitter)
        self.btn_mseg_jitter = QPushButton("Jitter")
        self.btn_mseg_jitter.clicked.connect(lambda _=False: self._apply_mseg_operation("jitter"))
        _tb_add(r, 2, self.btn_mseg_jitter)
        self.btn_mseg_undo = QPushButton("Undo")
        self.btn_mseg_undo.clicked.connect(lambda _=False: self._apply_mseg_operation("undo"))
        _tb_add(r, 3, self.btn_mseg_undo)
        self.btn_mseg_redo = QPushButton("Redo")
        self.btn_mseg_redo.clicked.connect(lambda _=False: self._apply_mseg_operation("redo"))
        _tb_add(r, 4, self.btn_mseg_redo)
        macro_col = 5
        for macro_key, macro_title in MSEG_MACRO_LABELS:
            btn = QPushButton(macro_title)
            btn.clicked.connect(lambda _=False, kk=macro_key: self._apply_mseg_operation(kk))
            _tb_add(r, macro_col, btn)
            macro_col += 1

        r = 6
        _tb_add(r, 0, QLabel("Blend A"))
        self.cmb_mseg_blend_a = QComboBox()
        self.cmb_mseg_blend_a.addItems(list(self.engine.get_mseg_shape_preset_names()))
        self.cmb_mseg_blend_a.setCurrentText("Triangle")
        self.cmb_mseg_blend_a.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 1, self.cmb_mseg_blend_a)
        _tb_add(r, 2, QLabel("Blend B"))
        self.cmb_mseg_blend_b = QComboBox()
        self.cmb_mseg_blend_b.addItems(list(self.engine.get_mseg_shape_preset_names()))
        self.cmb_mseg_blend_b.setCurrentText("Cathedral Breath")
        self.cmb_mseg_blend_b.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 3, self.cmb_mseg_blend_b)
        self.cmb_mseg_blend_amount = QComboBox()
        self.cmb_mseg_blend_amount.addItems(list(MSEG_BLEND_AMOUNTS))
        self.cmb_mseg_blend_amount.setCurrentText("50")
        self.cmb_mseg_blend_amount.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 4, self.cmb_mseg_blend_amount)
        self.btn_mseg_blend = QPushButton("Curve Blend")
        self.btn_mseg_blend.clicked.connect(lambda _=False: self._apply_mseg_operation("curve_blend"))
        _tb_add(r, 5, self.btn_mseg_blend)
        self.cmb_mseg_compare = QComboBox()
        self.cmb_mseg_compare.addItems(["A", "B"])
        self.cmb_mseg_compare.setCurrentText("A")
        self.cmb_mseg_compare.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 6, self.cmb_mseg_compare)
        self.btn_mseg_store_ab = QPushButton("Store A/B")
        self.btn_mseg_store_ab.clicked.connect(lambda _=False: self._apply_mseg_operation("store_ab"))
        _tb_add(r, 7, self.btn_mseg_store_ab)

        r = 7
        self.btn_mseg_compare_ab = QPushButton("Compare A/B")
        self.btn_mseg_compare_ab.clicked.connect(lambda _=False: self._apply_mseg_operation("compare_ab"))
        _tb_add(r, 0, self.btn_mseg_compare_ab)
        _tb_add(r, 1, QLabel("Curve %"))
        self.cmb_mseg_curve = QComboBox()
        self.cmb_mseg_curve.addItems(["10", "20", "35", "50"])
        self.cmb_mseg_curve.setCurrentText("20")
        self.cmb_mseg_curve.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 2, self.cmb_mseg_curve)
        self.btn_mseg_curve_down = QPushButton("Curve -")
        self.btn_mseg_curve_down.clicked.connect(lambda _=False: self._apply_mseg_operation("curve_down"))
        _tb_add(r, 3, self.btn_mseg_curve_down)
        self.btn_mseg_curve_up = QPushButton("Curve +")
        self.btn_mseg_curve_up.clicked.connect(lambda _=False: self._apply_mseg_operation("curve_up"))
        _tb_add(r, 4, self.btn_mseg_curve_up)
        _tb_add(r, 5, QLabel("Pinch %"))
        self.cmb_mseg_pinch = QComboBox()
        self.cmb_mseg_pinch.addItems(["10", "20", "35", "50"])
        self.cmb_mseg_pinch.setCurrentText("20")
        self.cmb_mseg_pinch.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 6, self.cmb_mseg_pinch)
        self.btn_mseg_pinch_in = QPushButton("Pinch")
        self.btn_mseg_pinch_in.clicked.connect(lambda _=False: self._apply_mseg_operation("pinch_in"))
        _tb_add(r, 7, self.btn_mseg_pinch_in)

        r = 8
        self.btn_mseg_pinch_out = QPushButton("Expand")
        self.btn_mseg_pinch_out.clicked.connect(lambda _=False: self._apply_mseg_operation("pinch_out"))
        _tb_add(r, 0, self.btn_mseg_pinch_out)
        _tb_add(r, 1, QLabel("Tilt %"))
        self.cmb_mseg_tilt = QComboBox()
        self.cmb_mseg_tilt.addItems(list(MSEG_TILT_AMOUNTS))
        self.cmb_mseg_tilt.setCurrentText("20")
        self.cmb_mseg_tilt.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 2, self.cmb_mseg_tilt)
        self.btn_mseg_tilt_down = QPushButton("Tilt -")
        self.btn_mseg_tilt_down.clicked.connect(lambda _=False: self._apply_mseg_operation("tilt_down"))
        _tb_add(r, 3, self.btn_mseg_tilt_down)
        self.btn_mseg_tilt_up = QPushButton("Tilt +")
        self.btn_mseg_tilt_up.clicked.connect(lambda _=False: self._apply_mseg_operation("tilt_up"))
        _tb_add(r, 4, self.btn_mseg_tilt_up)
        _tb_add(r, 5, QLabel("Skew %"))
        self.cmb_mseg_skew = QComboBox()
        self.cmb_mseg_skew.addItems(list(MSEG_SKEW_AMOUNTS))
        self.cmb_mseg_skew.setCurrentText("20")
        self.cmb_mseg_skew.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 6, self.cmb_mseg_skew)
        self.btn_mseg_skew_left = QPushButton("Skew <")
        self.btn_mseg_skew_left.clicked.connect(lambda _=False: self._apply_mseg_operation("skew_left"))
        _tb_add(r, 7, self.btn_mseg_skew_left)

        r = 9
        self.btn_mseg_skew_right = QPushButton("Skew >")
        self.btn_mseg_skew_right.clicked.connect(lambda _=False: self._apply_mseg_operation("skew_right"))
        _tb_add(r, 0, self.btn_mseg_skew_right)
        _tb_add(r, 1, QLabel("Slot"))
        self.cmb_mseg_slot = QComboBox()
        self.cmb_mseg_slot.addItems(["1", "2", "3", "4"])
        self.cmb_mseg_slot.setCurrentText("1")
        self.cmb_mseg_slot.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 2, self.cmb_mseg_slot)
        self.btn_mseg_copy = QPushButton("Copy")
        self.btn_mseg_copy.clicked.connect(lambda _=False: self._apply_mseg_operation("copy"))
        _tb_add(r, 3, self.btn_mseg_copy)
        self.btn_mseg_paste = QPushButton("Paste")
        self.btn_mseg_paste.clicked.connect(lambda _=False: self._apply_mseg_operation("paste"))
        _tb_add(r, 4, self.btn_mseg_paste)
        self.btn_mseg_store_slot = QPushButton("Store Slot")
        self.btn_mseg_store_slot.clicked.connect(lambda _=False: self._apply_mseg_operation("store_slot"))
        _tb_add(r, 5, self.btn_mseg_store_slot)
        self.btn_mseg_recall_slot = QPushButton("Recall Slot")
        self.btn_mseg_recall_slot.clicked.connect(lambda _=False: self._apply_mseg_operation("recall_slot"))
        _tb_add(r, 6, self.btn_mseg_recall_slot)

        r = 10
        _tb_add(r, 0, QLabel("Clamp %"))
        self.cmb_mseg_range_clamp = QComboBox()
        self.cmb_mseg_range_clamp.addItems(list(MSEG_RANGE_CLAMP_LEVELS))
        self.cmb_mseg_range_clamp.setCurrentText("80")
        self.cmb_mseg_range_clamp.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 1, self.cmb_mseg_range_clamp)
        self.btn_mseg_range_clamp = QPushButton("Range Clamp")
        self.btn_mseg_range_clamp.clicked.connect(lambda _=False: self._apply_mseg_operation("range_clamp"))
        _tb_add(r, 2, self.btn_mseg_range_clamp)
        _tb_add(r, 3, QLabel("Deadband %"))
        self.cmb_mseg_deadband = QComboBox()
        self.cmb_mseg_deadband.addItems(list(MSEG_DEADBAND_LEVELS))
        self.cmb_mseg_deadband.setCurrentText("10")
        self.cmb_mseg_deadband.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 4, self.cmb_mseg_deadband)
        self.btn_mseg_deadband = QPushButton("Deadband")
        self.btn_mseg_deadband.clicked.connect(lambda _=False: self._apply_mseg_operation("deadband"))
        _tb_add(r, 5, self.btn_mseg_deadband)
        _tb_add(r, 6, QLabel("µSmooth %"))
        self.cmb_mseg_micro_smooth = QComboBox()
        self.cmb_mseg_micro_smooth.addItems(list(MSEG_MICRO_SMOOTH_LEVELS))
        self.cmb_mseg_micro_smooth.setCurrentText("30")
        self.cmb_mseg_micro_smooth.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 7, self.cmb_mseg_micro_smooth)

        r = 11
        self.btn_mseg_micro_smooth = QPushButton("Micro-Smooth")
        self.btn_mseg_micro_smooth.clicked.connect(lambda _=False: self._apply_mseg_operation("micro_smooth"))
        _tb_add(r, 0, self.btn_mseg_micro_smooth)
        _tb_add(r, 1, QLabel("Drive %"))
        self.cmb_mseg_softclip = QComboBox()
        self.cmb_mseg_softclip.addItems(list(MSEG_SOFTCLIP_DRIVE_LEVELS))
        self.cmb_mseg_softclip.setCurrentText("20")
        self.cmb_mseg_softclip.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 2, self.cmb_mseg_softclip)
        self.btn_mseg_softclip = QPushButton("Soft-Clip")
        self.btn_mseg_softclip.clicked.connect(lambda _=False: self._apply_mseg_operation("softclip"))
        _tb_add(r, 3, self.btn_mseg_softclip)
        _tb_add(r, 4, QLabel("Center/Edge %"))
        self.cmb_mseg_center_edge = QComboBox()
        self.cmb_mseg_center_edge.addItems(list(MSEG_CENTER_EDGE_LEVELS))
        self.cmb_mseg_center_edge.setCurrentText("20")
        self.cmb_mseg_center_edge.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 5, self.cmb_mseg_center_edge)
        self.btn_mseg_center_flatten = QPushButton("Center Flatten")
        self.btn_mseg_center_flatten.clicked.connect(lambda _=False: self._apply_mseg_operation("center_flatten"))
        _tb_add(r, 6, self.btn_mseg_center_flatten)
        self.btn_mseg_edge_boost = QPushButton("Edge Boost")
        self.btn_mseg_edge_boost.clicked.connect(lambda _=False: self._apply_mseg_operation("edge_boost"))
        _tb_add(r, 7, self.btn_mseg_edge_boost)

        r = 12
        self.cmb_mseg_phase_rotate = QComboBox()
        self.cmb_mseg_phase_rotate.addItems(["5", "10", "15", "25"])
        self.cmb_mseg_phase_rotate.setCurrentText("10")
        self.cmb_mseg_phase_rotate.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 0, QLabel("Phase %"))
        _tb_add(r, 1, self.cmb_mseg_phase_rotate)
        self.btn_mseg_phase_left = QPushButton("Rotate ←")
        self.btn_mseg_phase_left.clicked.connect(lambda _=False: self._apply_mseg_operation("phase_left"))
        _tb_add(r, 2, self.btn_mseg_phase_left)
        self.btn_mseg_phase_right = QPushButton("Rotate →")
        self.btn_mseg_phase_right.clicked.connect(lambda _=False: self._apply_mseg_operation("phase_right"))
        _tb_add(r, 3, self.btn_mseg_phase_right)
        _tb_add(r, 4, QLabel("Sym %"))
        self.cmb_mseg_symmetry = QComboBox()
        self.cmb_mseg_symmetry.addItems(["15", "30", "50", "75"])
        self.cmb_mseg_symmetry.setCurrentText("30")
        self.cmb_mseg_symmetry.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 5, self.cmb_mseg_symmetry)
        self.btn_mseg_symmetry = QPushButton("Symmetry")
        self.btn_mseg_symmetry.clicked.connect(lambda _=False: self._apply_mseg_operation("symmetry"))
        _tb_add(r, 6, self.btn_mseg_symmetry)
        _tb_add(r, 7, QLabel("Readability fix: wrapped toolbar rows"))

        r = 13
        _tb_add(r, 0, QLabel("Slope %"))
        self.cmb_mseg_slope = QComboBox()
        self.cmb_mseg_slope.addItems(["20", "35", "50", "75"])
        self.cmb_mseg_slope.setCurrentText("35")
        self.cmb_mseg_slope.currentTextChanged.connect(lambda _txt: self._persist_instrument_state())
        _tb_add(r, 1, self.cmb_mseg_slope)
        self.btn_mseg_slope_limit = QPushButton("Slope Limit")
        self.btn_mseg_slope_limit.clicked.connect(lambda _=False: self._apply_mseg_operation("slope_limit"))
        _tb_add(r, 2, self.btn_mseg_slope_limit)
        preview_toolbar.setColumnStretch(8, 1)
        sec_mod_preview.body.addLayout(preview_toolbar)
        self.mod_preview = _ModPreviewWidget(self.engine, on_mseg_changed=self._on_mseg_points_changed, on_selection_changed=self._sync_point_editor_ui)
        self.mod_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sec_mod_preview.body.addWidget(self.mod_preview, 1)
        self.lbl_mod_preview_hint = QLabel("Empfohlener Start: 1) Shape wählen, 2) Apply Shape, 3) Punkte im Graph ziehen. Erweiterte Werkzeuge sind einklappbar. Alles bleibt lokal in AETERNA.")
        self.lbl_mod_preview_hint.setWordWrap(True)
        sec_mod_preview.body.addWidget(self.lbl_mod_preview_hint)
        point_row = QHBoxLayout()
        point_row.addWidget(QLabel("Selected Pt"))
        self.ed_point_x = QLineEdit()
        self.ed_point_x.setPlaceholderText("x 0.00..1.00")
        self.ed_point_x.setMaximumWidth(96)
        self.ed_point_y = QLineEdit()
        self.ed_point_y.setPlaceholderText("y -1.00..1.00")
        self.ed_point_y.setMaximumWidth(96)
        self.btn_point_apply = QPushButton("Apply XY")
        self.btn_point_apply.clicked.connect(lambda _=False: self._apply_selected_point_values())
        self.btn_point_left = QPushButton("← X")
        self.btn_point_left.clicked.connect(lambda _=False: self._nudge_selected_point("x", -0.01))
        self.btn_point_right = QPushButton("X →")
        self.btn_point_right.clicked.connect(lambda _=False: self._nudge_selected_point("x", 0.01))
        self.btn_point_down = QPushButton("↓ Y")
        self.btn_point_down.clicked.connect(lambda _=False: self._nudge_selected_point("y", -0.05))
        self.btn_point_up = QPushButton("Y ↑")
        self.btn_point_up.clicked.connect(lambda _=False: self._nudge_selected_point("y", 0.05))
        self.lbl_point_status = QLabel("Kein Punkt ausgewählt")
        self.lbl_mseg_history = QLabel("Undo 0 • Redo 0")
        point_row.addWidget(self.ed_point_x)
        point_row.addWidget(self.ed_point_y)
        point_row.addWidget(self.btn_point_apply)
        point_row.addSpacing(8)
        point_row.addWidget(self.btn_point_left)
        point_row.addWidget(self.btn_point_right)
        point_row.addWidget(self.btn_point_down)
        point_row.addWidget(self.btn_point_up)
        point_row.addSpacing(8)
        point_row.addWidget(self.lbl_point_status, 1)
        point_row.addWidget(self.lbl_mseg_history)
        sec_mod_preview.body.addLayout(point_row)
        root.addWidget(sec_mod_preview)

        sec_synth = self._register_section(_Section("AETERNA SYNTH PANEL (STAGE 1 SAFE)", expanded=True))
        sec_synth.setProperty("tone", "synth")
        self.lbl_synth_stage1_overview = QLabel(
            "AETERNA Synth Panel Stage 1\n"
            "Vorhandene stabile Parameter werden hier als klarere Synth-Oberfläche gruppiert."
        )
        self.lbl_synth_stage1_overview.setWordWrap(True)
        self.lbl_synth_stage1_overview.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage1_overview, "overview")
        sec_synth.body.addWidget(self.lbl_synth_stage1_overview)
        synth_nav = QHBoxLayout()
        synth_nav.setSpacing(6)
        for title, target in (("Engine", "ENGINE"), ("Klang", "MORPHOGENETIC CONTROLS"), ("Web", "THE WEB (LOCAL SAFE)"), ("Mod", "MOD RACK / FLOW (LOCAL SAFE)")):
            btn = QPushButton(title)
            btn.setToolTip(f"Öffnet den Bereich {target}")
            btn.clicked.connect(lambda _=False, nm=target: self._expand_section(nm))
            synth_nav.addWidget(btn)
        synth_nav.addStretch(1)
        sec_synth.body.addLayout(synth_nav)
        synth_cards = QGridLayout()
        synth_cards.setHorizontalSpacing(8)
        synth_cards.setVerticalSpacing(6)
        self.lbl_synth_stage1_core = QLabel("Core Voice")
        self.lbl_synth_stage1_core.setWordWrap(True)
        self.lbl_synth_stage1_core.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage1_core, "core")
        synth_cards.addWidget(self.lbl_synth_stage1_core, 0, 0)
        self.lbl_synth_stage1_space = QLabel("Space / Motion")
        self.lbl_synth_stage1_space.setWordWrap(True)
        self.lbl_synth_stage1_space.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage1_space, "space")
        synth_cards.addWidget(self.lbl_synth_stage1_space, 0, 1)
        self.lbl_synth_stage1_mod = QLabel("Mod / Web")
        self.lbl_synth_stage1_mod.setWordWrap(True)
        self.lbl_synth_stage1_mod.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage1_mod, "mod")
        synth_cards.addWidget(self.lbl_synth_stage1_mod, 1, 0)
        self.lbl_synth_stage1_future = QLabel("Stage 2/3 geplant")
        self.lbl_synth_stage1_future.setWordWrap(True)
        self.lbl_synth_stage1_future.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage1_future, "future")
        synth_cards.addWidget(self.lbl_synth_stage1_future, 1, 1)
        sec_synth.body.addLayout(synth_cards)
        synth_filter_grid = QGridLayout()
        synth_filter_grid.setHorizontalSpacing(6)
        synth_filter_grid.setVerticalSpacing(4)
        synth_filter_grid.addWidget(QLabel("Filter Type"), 0, 0)
        self.cmb_filter_type = QComboBox()
        self.cmb_filter_type.addItems(["LP 12", "LP 24", "HP 12", "BP", "Notch", "Comb+"])
        self.cmb_filter_type.currentTextChanged.connect(lambda txt: self._on_combo_param("filter_type", txt))
        self._combo_params["filter_type"] = self.cmb_filter_type
        synth_filter_grid.addWidget(self.cmb_filter_type, 0, 1)
        self.lbl_synth_stage2_filter = QLabel("Filter Stage 2")
        self.lbl_synth_stage2_filter.setWordWrap(True)
        self.lbl_synth_stage2_filter.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_stage2_filter, "filter")
        synth_filter_grid.addWidget(self.lbl_synth_stage2_filter, 0, 2, 2, 1)
        self._knobs["filter_cutoff"] = CompactKnob("Cutoff", 68)
        self._knobs["filter_cutoff"].valueChanged.connect(lambda v, kk="filter_cutoff": self._on_knob(kk, v))
        synth_filter_grid.addWidget(self._knobs["filter_cutoff"], 1, 0)
        self._add_knob_mini_meter(synth_filter_grid, 2, 0, "filter_cutoff", "filter")
        self._knobs["filter_resonance"] = CompactKnob("Resonance", 18)
        self._knobs["filter_resonance"].valueChanged.connect(lambda v, kk="filter_resonance": self._on_knob(kk, v))
        synth_filter_grid.addWidget(self._knobs["filter_resonance"], 1, 1)
        self._add_knob_mini_meter(synth_filter_grid, 2, 1, "filter_resonance", "filter")
        sec_synth.body.addLayout(synth_filter_grid)
        self.lbl_synth_filter_hint = QLabel(
            "Echter lokaler AETERNA-Filterblock: Cutoff/Resonance sind stabil automatisierbar, Type bleibt lokal im Instrument-State gespeichert. "
            "Filter sitzt bewusst innerhalb von AETERNA und greift nicht in den DAW-Core ein."
        )
        self.lbl_synth_filter_hint.setWordWrap(True)
        self.lbl_synth_filter_hint.setObjectName("aeternaAutomationTargetHint")
        sec_synth.body.addWidget(self.lbl_synth_filter_hint)

        synth_voice_grid = QGridLayout()
        synth_voice_grid.setHorizontalSpacing(6)
        synth_voice_grid.setVerticalSpacing(4)
        self._knobs["pan"] = CompactKnob("Pan", 50)
        self._knobs["pan"].valueChanged.connect(lambda v, kk="pan": self._on_knob(kk, v))
        synth_voice_grid.addWidget(self._knobs["pan"], 0, 0)
        self._add_knob_mini_meter(synth_voice_grid, 1, 0, "pan", "voice")
        self._knobs["glide"] = CompactKnob("Glide", 6)
        self._knobs["glide"].valueChanged.connect(lambda v, kk="glide": self._on_knob(kk, v))
        synth_voice_grid.addWidget(self._knobs["glide"], 0, 1)
        self._add_knob_mini_meter(synth_voice_grid, 1, 1, "glide", "voice")
        self._knobs["stereo_spread"] = CompactKnob("Spread", 34)
        self._knobs["stereo_spread"].valueChanged.connect(lambda v, kk="stereo_spread": self._on_knob(kk, v))
        synth_voice_grid.addWidget(self._knobs["stereo_spread"], 0, 2)
        self._add_knob_mini_meter(synth_voice_grid, 1, 2, "stereo_spread", "voice")
        self.chk_retrigger = QCheckBox("Retrig")
        self.chk_retrigger.setChecked(True)
        self.chk_retrigger.toggled.connect(lambda on=False: self._on_toggle_param("retrigger", on))
        synth_voice_grid.addWidget(self.chk_retrigger, 0, 3)
        self.lbl_synth_voice_family = QLabel("Voice Family")
        self.lbl_synth_voice_family.setWordWrap(True)
        self.lbl_synth_voice_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_voice_family, "voice")
        synth_voice_grid.addWidget(self.lbl_synth_voice_family, 0, 4, 2, 1)
        sec_synth.body.addLayout(synth_voice_grid)

        synth_aeg_grid = QGridLayout()
        synth_aeg_grid.setHorizontalSpacing(6)
        synth_aeg_grid.setVerticalSpacing(4)
        for col, (key, title, init) in enumerate((("aeg_attack", "AEG A", 10), ("aeg_decay", "AEG D", 28), ("aeg_sustain", "AEG S", 78), ("aeg_release", "AEG R", 46))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_aeg_grid.addWidget(self._knobs[key], 0, col)
            self._add_knob_mini_meter(synth_aeg_grid, 1, col, key, "aeg")
        self.lbl_synth_aeg_family = QLabel("AEG ADSR")
        self.lbl_synth_aeg_family.setWordWrap(True)
        self.lbl_synth_aeg_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_aeg_family, "aeg")
        synth_aeg_grid.addWidget(self.lbl_synth_aeg_family, 0, 4, 2, 1)
        sec_synth.body.addLayout(synth_aeg_grid)

        synth_feg_grid = QGridLayout()
        synth_feg_grid.setHorizontalSpacing(6)
        synth_feg_grid.setVerticalSpacing(4)
        for col, (key, title, init) in enumerate((("feg_attack", "FEG A", 4), ("feg_decay", "FEG D", 22), ("feg_sustain", "FEG S", 58), ("feg_release", "FEG R", 34), ("feg_amount", "FEG Amt", 26))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_feg_grid.addWidget(self._knobs[key], 0, col)
            self._add_knob_mini_meter(synth_feg_grid, 1, col, key, "feg")
        self.lbl_synth_feg_family = QLabel("FEG ADSR")
        self.lbl_synth_feg_family.setWordWrap(True)
        self.lbl_synth_feg_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_feg_family, "feg")
        synth_feg_grid.addWidget(self.lbl_synth_feg_family, 0, 5, 2, 1)
        sec_synth.body.addLayout(synth_feg_grid)


        synth_layer_grid = QGridLayout()
        synth_layer_grid.setHorizontalSpacing(6)
        synth_layer_grid.setVerticalSpacing(4)
        synth_layer_grid.addWidget(QLabel("Unison Voices"), 0, 0)
        self.cmb_unison_voices = QComboBox()
        self.cmb_unison_voices.addItems(["1", "2", "4", "6"])
        self.cmb_unison_voices.currentTextChanged.connect(lambda txt: self._on_combo_param("unison_voices", txt))
        self._combo_params["unison_voices"] = self.cmb_unison_voices
        synth_layer_grid.addWidget(self.cmb_unison_voices, 0, 1)
        synth_layer_grid.addWidget(QLabel("Sub Oktave"), 0, 2)
        self.cmb_sub_octave = QComboBox()
        self.cmb_sub_octave.addItems(["-1", "-2"])
        self.cmb_sub_octave.currentTextChanged.connect(lambda txt: self._on_combo_param("sub_octave", txt))
        self._combo_params["sub_octave"] = self.cmb_sub_octave
        synth_layer_grid.addWidget(self.cmb_sub_octave, 0, 3)
        for col, (key, title, init) in enumerate((("unison_mix", "Uni Mix", 12), ("unison_detune", "Uni Det", 18), ("sub_level", "Sub", 10))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_layer_grid.addWidget(self._knobs[key], 1, col)
            self._add_knob_mini_meter(synth_layer_grid, 2, col, key, "layer")
        self.lbl_synth_unison_family = QLabel("Unison / Sub")
        self.lbl_synth_unison_family.setWordWrap(True)
        self.lbl_synth_unison_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_unison_family, "layer")
        synth_layer_grid.addWidget(self.lbl_synth_unison_family, 0, 4, 2, 1)
        sec_synth.body.addLayout(synth_layer_grid)

        synth_noise_grid = QGridLayout()
        synth_noise_grid.setHorizontalSpacing(6)
        synth_noise_grid.setVerticalSpacing(4)
        for col, (key, title, init) in enumerate((("noise_level", "Noise", 4), ("noise_color", "Color", 34))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_noise_grid.addWidget(self._knobs[key], 0, col)
            self._add_knob_mini_meter(synth_noise_grid, 1, col, key, "noise")
        self.lbl_synth_noise_family = QLabel("Noise / Color")
        self.lbl_synth_noise_family.setWordWrap(True)
        self.lbl_synth_noise_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_noise_family, "noise")
        synth_noise_grid.addWidget(self.lbl_synth_noise_family, 0, 2, 2, 1)
        sec_synth.body.addLayout(synth_noise_grid)

        synth_pitch_grid = QGridLayout()
        synth_pitch_grid.setHorizontalSpacing(6)
        synth_pitch_grid.setVerticalSpacing(4)
        for col, (key, title, init) in enumerate((("pitch", "Pitch", 50), ("shape", "Shape", 42), ("pulse_width", "PW", 50))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_pitch_grid.addWidget(self._knobs[key], 0, col)
            self._add_knob_mini_meter(synth_pitch_grid, 1, col, key, "timbre")
        self.lbl_synth_pitch_family = QLabel("Pitch / Shape / PW")
        self.lbl_synth_pitch_family.setWordWrap(True)
        self.lbl_synth_pitch_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_pitch_family, "timbre")
        synth_pitch_grid.addWidget(self.lbl_synth_pitch_family, 0, 3, 2, 1)
        sec_synth.body.addLayout(synth_pitch_grid)

        synth_drive_grid = QGridLayout()
        synth_drive_grid.setHorizontalSpacing(6)
        synth_drive_grid.setVerticalSpacing(4)
        for col, (key, title, init) in enumerate((("drive", "Drive", 22), ("feedback", "Feedback", 4))):
            self._knobs[key] = CompactKnob(title, init)
            self._knobs[key].valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            synth_drive_grid.addWidget(self._knobs[key], 0, col)
            self._add_knob_mini_meter(synth_drive_grid, 1, col, key, "drive")
        self.lbl_synth_drive_family = QLabel("Drive / Feedback")
        self.lbl_synth_drive_family.setWordWrap(True)
        self.lbl_synth_drive_family.setObjectName("aeternaAutomationTargetCard")
        self._set_card_tone(self.lbl_synth_drive_family, "drive")
        synth_drive_grid.addWidget(self.lbl_synth_drive_family, 0, 2, 2, 1)
        sec_synth.body.addLayout(synth_drive_grid)

        synth_preview = QGridLayout()
        synth_preview.setHorizontalSpacing(6)
        synth_preview.setVerticalSpacing(4)
        synth_preview.addWidget(QLabel("Envelope"), 0, 2)
        self.cmb_synth_env_preview = QComboBox()
        self.cmb_synth_env_preview.addItems(["AEG ADSR", "FEG ADSR", "Dual ENV"])
        self.cmb_synth_env_preview.setEnabled(False)
        self.cmb_synth_env_preview.setToolTip("Vorschau für Stage 3 – noch ohne Audio-Wirkung")
        synth_preview.addWidget(self.cmb_synth_env_preview, 0, 3)
        synth_preview.addWidget(QLabel("Layer"), 1, 0)
        self.cmb_synth_layer_preview = QComboBox()
        self.cmb_synth_layer_preview.addItems(["Pitch/Shape", "Unison/Sub", "Noise/Drive"])
        self.cmb_synth_layer_preview.setEnabled(False)
        self.cmb_synth_layer_preview.setToolTip("Nur reservierter UI-Platz für spätere sichere Ausbaustufen")
        synth_preview.addWidget(self.cmb_synth_layer_preview, 1, 1)
        self.chk_synth_preview_unison = QCheckBox("Unison")
        self.chk_synth_preview_unison.toggled.connect(lambda on=False: self._toggle_layer_feature("unison_mix", on))
        self.chk_synth_preview_sub = QCheckBox("Sub")
        self.chk_synth_preview_sub.toggled.connect(lambda on=False: self._toggle_layer_feature("sub_level", on))
        self.chk_synth_preview_noise = QCheckBox("Noise")
        self.chk_synth_preview_noise.toggled.connect(lambda on=False: self._toggle_layer_feature("noise_level", on))
        synth_preview.addWidget(self.chk_synth_preview_unison, 1, 2)
        synth_preview.addWidget(self.chk_synth_preview_sub, 1, 3)
        synth_preview.addWidget(self.chk_synth_preview_noise, 1, 4)
        sec_synth.body.addLayout(synth_preview)
        self.lbl_synth_stage1_preview_hint = QLabel(
            "Layer-Schalter unten sind jetzt direkt aktiv: Unison / Sub / Noise lassen sich hier schnell an- und ausschalten. Envelope-/Layer-Familien bleiben sonst weiterhin als sichere Vorschau sichtbar."
        )
        self.lbl_synth_stage1_preview_hint.setWordWrap(True)
        self.lbl_synth_stage1_preview_hint.setObjectName("aeternaAutomationTargetHint")
        sec_synth.body.addWidget(self.lbl_synth_stage1_preview_hint)
        root.addWidget(sec_synth)

        knob_sec = self._register_section(_Section("MORPHOGENETIC CONTROLS", expanded=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        order = [
            ("morph", "Morph", 55),
            ("chaos", "Chaos", 20),
            ("drift", "Drift", 18),
            ("tone", "Tone", 52),
            ("release", "Release", 42),
            ("gain", "Gain", 56),
            ("space", "Space", 30),
            ("motion", "Motion", 30),
            ("cathedral", "Cathedral", 34),
        ]
        for i, (key, title, init) in enumerate(order):
            knob = CompactKnob(title, init)
            knob.valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            self._knobs[key] = knob
            grid.addWidget(knob, 0, i)
        knob_sec.body.addLayout(grid)
        root.addWidget(knob_sec)

        mod_sec = self._register_section(_Section("THE WEB (LOCAL SAFE)", expanded=True))
        mod_rates = QGridLayout()
        mod_rates.setHorizontalSpacing(8)
        mod_rates.setVerticalSpacing(4)
        for i, (key, title, init) in enumerate([
            ("lfo1_rate", "LFO1 Rate", 22),
            ("lfo2_rate", "LFO2 Rate", 10),
            ("lfo3_rate", "LFO3 Rate", 15),
            ("lfo4_rate", "LFO4 Rate", 8),
            ("mseg_rate", "MSEG Rate", 24),
            ("mod1_amount", "Web A", 20),
            ("mod2_amount", "Web B", 22),
        ]):
            knob = CompactKnob(title, init)
            knob.valueChanged.connect(lambda v, kk=key: self._on_knob(kk, v))
            self._knobs[key] = knob
            mod_rates.addWidget(knob, 0, i)
        mod_sec.body.addLayout(mod_rates)

        web_row1 = QHBoxLayout()
        self.cmb_mod1_source = QComboBox(); self.cmb_mod1_source.addItems(list(self.engine.get_mod_sources()))
        self.cmb_mod1_target = QComboBox(); self.cmb_mod1_target.addItems(list(self.engine.get_mod_targets()))
        self.cmb_mod1_source.currentTextChanged.connect(lambda txt: self._on_combo_param("mod1_source", txt))
        self.cmb_mod1_target.currentTextChanged.connect(lambda txt: self._on_combo_param("mod1_target", txt))
        self._combo_params["mod1_source"] = self.cmb_mod1_source
        self._combo_params["mod1_target"] = self.cmb_mod1_target
        web_row1.addWidget(QLabel("Web A"))
        web_row1.addWidget(self.cmb_mod1_source)
        web_row1.addWidget(QLabel("→"))
        web_row1.addWidget(self.cmb_mod1_target)
        web_row1.addWidget(QLabel("Pol"))
        self.btn_mod1_polarity = QPushButton("+")
        self.btn_mod1_polarity.setFixedWidth(34)
        self.btn_mod1_polarity.clicked.connect(lambda _=False: self._toggle_mod_polarity(1))
        web_row1.addWidget(self.btn_mod1_polarity)
        mod_sec.body.addLayout(web_row1)

        web_row2 = QHBoxLayout()
        self.cmb_mod2_source = QComboBox(); self.cmb_mod2_source.addItems(list(self.engine.get_mod_sources()))
        self.cmb_mod2_target = QComboBox(); self.cmb_mod2_target.addItems(list(self.engine.get_mod_targets()))
        self.cmb_mod2_source.currentTextChanged.connect(lambda txt: self._on_combo_param("mod2_source", txt))
        self.cmb_mod2_target.currentTextChanged.connect(lambda txt: self._on_combo_param("mod2_target", txt))
        self._combo_params["mod2_source"] = self.cmb_mod2_source
        self._combo_params["mod2_target"] = self.cmb_mod2_target
        web_row2.addWidget(QLabel("Web B"))
        web_row2.addWidget(self.cmb_mod2_source)
        web_row2.addWidget(QLabel("→"))
        web_row2.addWidget(self.cmb_mod2_target)
        web_row2.addWidget(QLabel("Pol"))
        self.btn_mod2_polarity = QPushButton("+")
        self.btn_mod2_polarity.setFixedWidth(34)
        self.btn_mod2_polarity.clicked.connect(lambda _=False: self._toggle_mod_polarity(2))
        web_row2.addWidget(self.btn_mod2_polarity)
        mod_sec.body.addLayout(web_row2)

        # ═══ DYNAMIC WEB SLOTS C–H (mod3–mod8) ═══
        _slot_names = {3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H"}
        _slot_colors = {3: "#5fe0b3", 4: "#ff9a9a", 5: "#ffd27f", 6: "#c596ff", 7: "#8fe388", 8: "#ff95d0"}
        self._extra_web_rows = {}   # slot_idx → QWidget container
        self._extra_web_combos = {} # slot_idx → (cmb_source, cmb_target)
        self._extra_web_knobs = {}  # slot_idx → CompactKnob for amount
        self._extra_web_pol_btns = {}
        self._visible_web_slots = 2  # start with A+B visible

        for slot_i in range(3, 9):  # Web C through H
            slot_label = f"Web {_slot_names[slot_i]}"
            row_w = QWidget()
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 2, 0, 2)
            row_lay.setSpacing(4)
            lbl = QLabel(slot_label)
            lbl.setStyleSheet(f"color: {_slot_colors.get(slot_i, '#d8deee')}; font-weight: 700;")
            cmb_src = QComboBox(); cmb_src.addItems(list(self.engine.get_mod_sources()))
            cmb_tgt = QComboBox(); cmb_tgt.addItems(list(self.engine.get_mod_targets()))
            cmb_src.currentTextChanged.connect(lambda txt, si=slot_i: self._on_combo_param(f"mod{si}_source", txt))
            cmb_tgt.currentTextChanged.connect(lambda txt, si=slot_i: self._on_combo_param(f"mod{si}_target", txt))
            self._combo_params[f"mod{slot_i}_source"] = cmb_src
            self._combo_params[f"mod{slot_i}_target"] = cmb_tgt
            knob = CompactKnob(f"Amt {_slot_names[slot_i]}", 0)
            knob.valueChanged.connect(lambda v, kk=f"mod{slot_i}_amount": self._on_knob(kk, v))
            self._knobs[f"mod{slot_i}_amount"] = knob
            pol_btn = QPushButton("+")
            pol_btn.setFixedWidth(34)
            pol_btn.setToolTip(f"Polarität Web {_slot_names[slot_i]} umschalten (+/−)")
            pol_btn.clicked.connect(lambda _=False, si=slot_i: self._toggle_mod_polarity(si))
            row_lay.addWidget(lbl)
            row_lay.addWidget(cmb_src)
            row_lay.addWidget(QLabel("→"))
            row_lay.addWidget(cmb_tgt)
            row_lay.addWidget(knob)
            row_lay.addWidget(QLabel("Pol"))
            row_lay.addWidget(pol_btn)
            row_w.setVisible(False)  # Hidden by default
            self._extra_web_rows[slot_i] = row_w
            self._extra_web_combos[slot_i] = (cmb_src, cmb_tgt)
            self._extra_web_knobs[slot_i] = knob
            self._extra_web_pol_btns[slot_i] = pol_btn
            mod_sec.body.addWidget(row_w)

        # + / - buttons for Web slots
        web_plus_minus = QHBoxLayout()
        self.btn_web_add = QPushButton("+ Web Slot")
        self.btn_web_add.setToolTip("Weiteren Modulationsweg (Web C–H) hinzufügen")
        self.btn_web_add.setStyleSheet("QPushButton { background: rgba(95,224,179,0.2); border: 1px solid rgba(95,224,179,0.4); border-radius: 6px; padding: 6px 14px; color: #5fe0b3; font-weight: 700; }")
        self.btn_web_add.clicked.connect(self._add_web_slot)
        self.btn_web_remove = QPushButton("− Web Slot")
        self.btn_web_remove.setToolTip("Letzten Modulationsweg entfernen")
        self.btn_web_remove.setStyleSheet("QPushButton { background: rgba(255,127,127,0.15); border: 1px solid rgba(255,127,127,0.35); border-radius: 6px; padding: 6px 14px; color: #ff7f7f; font-weight: 700; }")
        self.btn_web_remove.clicked.connect(self._remove_web_slot)
        self.btn_web_remove.setEnabled(False)
        self.lbl_web_slot_count = QLabel("2 / 8 Slots aktiv")
        self.lbl_web_slot_count.setStyleSheet("color: #8fa7c9; font-size: 12px;")
        web_plus_minus.addWidget(self.btn_web_add)
        web_plus_minus.addWidget(self.btn_web_remove)
        web_plus_minus.addWidget(self.lbl_web_slot_count)
        web_plus_minus.addStretch()
        mod_sec.body.addLayout(web_plus_minus)

        self.lbl_macro_ab_card = QLabel("Macro A: –\nMacro B: –")
        self.lbl_macro_ab_card.setWordWrap(True)
        self.lbl_macro_ab_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_macro_ab_hint = QLabel(
            "Lesbar gruppiert: Web A/B = sichere Makro-Wege für Source → Target mit Amount. "
            "Lieber Rate/Amount/Target steuern als rohe interne Zustände."
        )
        self.lbl_macro_ab_hint.setWordWrap(True)
        self.lbl_macro_ab_hint.setObjectName("aeternaAutomationTargetHint")
        mod_sec.body.addWidget(QLabel("Macro A/B Fokus"))
        mod_sec.body.addWidget(self.lbl_macro_ab_card)
        mod_sec.body.addWidget(self.lbl_macro_ab_hint)

        mod_sec.body.addWidget(QLabel("Web-Startvorlagen"))
        web_tpl_row = QHBoxLayout()
        self._web_template_buttons = []
        for preset_name, preset_hint, _cfg in WEB_TEMPLATE_PRESETS:
            btn = QPushButton(preset_name)
            btn.setToolTip(preset_hint)
            btn.clicked.connect(lambda _=False, n=preset_name: self._apply_web_template(str(n)))
            self._web_template_buttons.append(btn)
            web_tpl_row.addWidget(btn)
        mod_sec.body.addLayout(web_tpl_row)
        web_intensity_row = QHBoxLayout()
        web_intensity_row.addWidget(QLabel("Intensität"))
        self.cmb_web_template_intensity = QComboBox()
        self.cmb_web_template_intensity.addItems(["Sanft", "Mittel", "Präsent"])
        self.cmb_web_template_intensity.setCurrentText("Mittel")
        self.cmb_web_template_intensity.currentTextChanged.connect(self._on_web_template_intensity_changed)
        web_intensity_row.addWidget(self.cmb_web_template_intensity)
        self.btn_web_template_reset = QPushButton("Basis wiederherstellen")
        self.btn_web_template_reset.setToolTip("Setzt Web A/B, Amounts und Rate-Knobs auf sichere lokale Basiswerte zurück.")
        self.btn_web_template_reset.clicked.connect(lambda _=False: self._reset_web_template_to_baseline())
        web_intensity_row.addWidget(self.btn_web_template_reset)
        web_intensity_row.addStretch(1)
        mod_sec.body.addLayout(web_intensity_row)
        self.lbl_web_intensity_hint = QLabel(
            "Sanft = ruhiger Einstieg • Mittel = Standard • Präsent = deutlichere Bewegung. "
            "Gespeichert mit dem Projekt und lokal in AETERNA wiederhergestellt."
        )
        self.lbl_web_intensity_hint.setWordWrap(True)
        self.lbl_web_intensity_hint.setObjectName("aeternaAutomationTargetHint")
        mod_sec.body.addWidget(self.lbl_web_intensity_hint)
        self.lbl_web_template_card = QLabel("Web-Vorlage: –")
        self.lbl_web_template_card.setWordWrap(True)
        self.lbl_web_template_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_web_template_hint = QLabel(
            "Lokale sichere Startwege für Web A/B: setzen nur Quelle, Ziel, Amount und Rate-Knobs in AETERNA. "
            "Alles bleibt lokal und kann danach fein per Hand angepasst werden."
        )
        self.lbl_web_template_hint.setWordWrap(True)
        self.lbl_web_template_hint.setObjectName("aeternaAutomationTargetHint")
        mod_sec.body.addWidget(self.lbl_web_template_card)
        mod_sec.body.addWidget(self.lbl_web_template_hint)

        mod_sec.body.addWidget(QLabel("Lokale Snapshots"))
        snap_row = QGridLayout()
        self._snapshot_store_buttons = {}
        self._snapshot_recall_buttons = {}
        self._snapshot_badge_labels = {}
        self._snapshot_slot_labels = {}
        for col, slot_name in enumerate(("A", "B", "C")):
            lbl = QLabel(f"Slot {slot_name}")
            badge = QLabel("<span style='color:#8b949e; font-weight:600;'>● leer</span> <span style='color:#8b949e;'>bereit</span>")
            badge.setWordWrap(True)
            badge.setObjectName("aeternaAutomationTargetHint")
            btn_store = QPushButton(f"Store {slot_name}")
            btn_store.setToolTip(f"Speichert aktuellen lokalen Klang/Formula/Web-Zustand in Snapshot {slot_name}.")
            btn_store.clicked.connect(lambda _=False, s=slot_name: self._store_local_snapshot(s))
            btn_recall = QPushButton(f"Recall {slot_name}")
            btn_recall.setToolTip(f"Stellt Snapshot {slot_name} lokal in AETERNA wieder her.")
            btn_recall.clicked.connect(lambda _=False, s=slot_name: self._recall_local_snapshot(s))
            self._snapshot_store_buttons[slot_name] = btn_store
            self._snapshot_recall_buttons[slot_name] = btn_recall
            self._snapshot_badge_labels[slot_name] = badge
            self._snapshot_slot_labels[slot_name] = lbl
            snap_row.addWidget(lbl, 0, col)
            snap_row.addWidget(badge, 1, col)
            snap_row.addWidget(btn_store, 2, col)
            snap_row.addWidget(btn_recall, 3, col)
        mod_sec.body.addLayout(snap_row)
        self.lbl_snapshot_card = QLabel("Snapshots: noch leer")
        self.lbl_snapshot_card.setWordWrap(True)
        self.lbl_snapshot_card.setObjectName("aeternaAutomationTargetCard")
        self.lbl_snapshot_hint = QLabel(
            "Lokale Snapshots sichern nur AETERNA-Zustände für Klang, Formel und Web. "
            "Sie werden mit dem Projekt gespeichert und beim Laden wiederhergestellt."
        )
        self.lbl_snapshot_hint.setWordWrap(True)
        self.lbl_snapshot_hint.setObjectName("aeternaAutomationTargetHint")
        self.lbl_snapshot_last_action = QLabel("Zuletzt: noch kein lokaler Snapshot-Vorgang")
        self.lbl_snapshot_last_action.setWordWrap(True)
        self.lbl_snapshot_last_action.setObjectName("aeternaAutomationTargetHint")
        self.lbl_snapshot_last_action.setToolTip("Zeigt den letzten lokalen Snapshot-Schritt: Store oder Recall mit Hörbild/Formel/Web-Hinweis.")
        mod_sec.body.addWidget(self.lbl_snapshot_card)
        mod_sec.body.addWidget(self.lbl_snapshot_hint)
        mod_sec.body.addWidget(self.lbl_snapshot_last_action)
        self.lbl_snapshot_quicklaunch = QLabel("Schnellaufrufe: lokale Preset-/Snapshot-Kombis werden hier kompakt gezeigt")
        self.lbl_snapshot_quicklaunch.setWordWrap(True)
        self.lbl_snapshot_quicklaunch.setObjectName("aeternaAutomationTargetCard")
        snap_quick_row = QHBoxLayout()
        snap_quick_row.setSpacing(4)
        self._snapshot_quicklaunch_buttons = []
        for _idx in range(3):
            btn = QPushButton("–")
            btn.setEnabled(False)
            btn.setToolTip("Noch kein lokaler Schnellaufruf belegt.")
            self._snapshot_quicklaunch_buttons.append(btn)
            snap_quick_row.addWidget(btn)
        snap_quick_row.addStretch(1)
        mod_sec.body.addWidget(QLabel("Preset-/Snapshot-Schnellaufrufe"))
        mod_sec.body.addLayout(snap_quick_row)
        mod_sec.body.addWidget(self.lbl_snapshot_quicklaunch)

        self.lbl_mod_hint = QLabel("LFO1 = weich/schnell • LFO2 = Dreieck/langsam • MSEG = mehrstufige Hüllkurve • Chaos = logistischer Drift")
        self.lbl_mod_hint.setWordWrap(True)
        mod_sec.body.addWidget(self.lbl_mod_hint)
        root.addWidget(mod_sec)
        self._sync_point_editor_ui()
        self._sync_history_ui()
        self._schedule_deferred_ui_refresh(reason="build-ui", delay_ms=0, restart=True)

    def _set_mseg_advanced_visible(self, visible: bool, persist: bool = True) -> None:
        self._mseg_advanced_visible = bool(visible)
        try:
            if hasattr(self, "btn_toggle_mseg_advanced") and self.btn_toggle_mseg_advanced is not None:
                self.btn_toggle_mseg_advanced.blockSignals(True)
                self.btn_toggle_mseg_advanced.setChecked(self._mseg_advanced_visible)
                self.btn_toggle_mseg_advanced.setText("Advanced MSEG ▾" if self._mseg_advanced_visible else "Advanced MSEG ▸")
                self.btn_toggle_mseg_advanced.blockSignals(False)
        except Exception:
            pass
        for row, widgets in getattr(self, "_mseg_toolbar_rows", {}).items():
            if int(row) < 4:
                continue
            for widget in widgets or []:
                try:
                    widget.setVisible(self._mseg_advanced_visible)
                except Exception:
                    pass
        try:
            if hasattr(self, "lbl_mseg_start_here") and self.lbl_mseg_start_here is not None:
                self.lbl_mseg_start_here.setText(
                    "Start hier: Shape → Apply Shape → Punkte ziehen"
                    if not self._mseg_advanced_visible else
                    "Erweiterte Werkzeuge sichtbar — Basics bleiben oben"
                )
        except Exception:
            pass
        if persist:
            self._persist_instrument_state()

    def _sync_point_editor_ui(self) -> None:
        try:
            idx = self.mod_preview.selected_point()
        except Exception:
            idx = None
        pts = self.engine.get_mseg_points()
        enabled = idx is not None and 0 <= int(idx) < len(pts)
        widgets = [self.ed_point_x, self.ed_point_y, self.btn_point_apply, self.btn_point_left, self.btn_point_right, self.btn_point_down, self.btn_point_up]
        for w in widgets:
            try:
                w.setEnabled(enabled)
            except Exception:
                pass
        if enabled:
            x, y = pts[int(idx)]
            self.ed_point_x.setText(f"{float(x):.3f}")
            self.ed_point_y.setText(f"{float(y):.3f}")
            label = f"Punkt #{int(idx)+1}"
            if int(idx) == 0 or int(idx) == len(pts) - 1:
                label += " (Endpunkt X fixiert)"
            self.lbl_point_status.setText(label)
        else:
            self.ed_point_x.setText("")
            self.ed_point_y.setText("")
            self.lbl_point_status.setText("Kein Punkt ausgewählt")
        self._sync_history_ui()

    def _sync_history_ui(self) -> None:
        try:
            st = self.engine.get_mseg_history_status()
        except Exception:
            st = {"undo": 0, "redo": 0}
        undo_n = int(st.get("undo", 0) or 0)
        redo_n = int(st.get("redo", 0) or 0)
        self.lbl_mseg_history.setText(f"Undo {undo_n} • Redo {redo_n}")
        try:
            self.btn_mseg_undo.setEnabled(undo_n > 0)
            self.btn_mseg_redo.setEnabled(redo_n > 0)
        except Exception:
            pass

    def _apply_selected_point_values(self) -> None:
        idx = self.mod_preview.selected_point()
        pts = self.engine.get_mseg_points()
        if idx is None or not (0 <= int(idx) < len(pts)):
            return
        idx = int(idx)
        try:
            x = float((self.ed_point_x.text() or "").strip())
            y = float((self.ed_point_y.text() or "").strip())
        except Exception:
            self._sync_point_editor_ui()
            return
        x = max(0.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        if idx <= 0:
            x = 0.0
        elif idx >= len(pts) - 1:
            x = 1.0
        else:
            prev_x = float(pts[idx - 1][0]) + 0.02
            next_x = float(pts[idx + 1][0]) - 0.02
            x = max(prev_x, min(next_x, x))
        pts[idx] = (x, y)
        try:
            self.engine.set_mseg_points(pts)
            self.mod_preview._select_point(idx)
            self.mod_preview.update()
            self._notify_mseg_points_changed_and_persist()
        except Exception:
            pass
        self._sync_point_editor_ui()

    def _nudge_selected_point(self, axis: str, delta: float) -> None:
        idx = self.mod_preview.selected_point()
        pts = self.engine.get_mseg_points()
        if idx is None or not (0 <= int(idx) < len(pts)):
            return
        idx = int(idx)
        x, y = pts[idx]
        if str(axis).lower() == "x":
            if idx <= 0:
                nx = 0.0
            elif idx >= len(pts) - 1:
                nx = 1.0
            else:
                prev_x = float(pts[idx - 1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, float(x) + float(delta)))
            ny = float(y)
        else:
            nx = float(x)
            ny = max(-1.0, min(1.0, float(y) + float(delta)))
        pts[idx] = (nx, ny)
        try:
            self.engine.set_mseg_points(pts)
            self.mod_preview._select_point(idx)
            self.mod_preview.update()
            self._notify_mseg_points_changed_and_persist()
        except Exception:
            pass
        self._sync_point_editor_ui()

    def _notify_mseg_points_changed_and_persist(self) -> None:
        self._sync_segment_form_ui()
        self._sync_history_ui()
        self._persist_instrument_state()

    def _set_card_tone(self, widget: QWidget | None, tone: str) -> None:
        try:
            if widget is None:
                return
            widget.setProperty("tone", str(tone or "flow"))
        except Exception:
            pass

    def _flow_target_bucket(self, target: str) -> str:
        key = str(target or "off")
        if key in {"morph", "tone", "gain", "release", "pan", "glide", "stereo_spread"}:
            return "core"
        if key in {"filter_cutoff", "filter_resonance", "feg_amount"}:
            return "filter"
        if key in {"pitch", "shape", "pulse_width"}:
            return "timbre"
        if key in {"unison_mix", "unison_detune", "sub_level", "noise_level", "noise_color"}:
            return "layer"
        if key in {"drive", "feedback"}:
            return "drive"
        if key in {"space", "motion", "cathedral", "drift"}:
            return "space"
        return "flow"

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            # ── Sections ──
            "QFrame#aeternaSection { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #22272f, stop:1 #1c2028); "
            "  border:1px solid rgba(255,255,255,0.10); border-radius:10px; }"
            "QFrame#aeternaSection[tone=\"synth\"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1f2938, stop:1 #1a2230); "
            "  border:1px solid rgba(134,183,255,0.18); }"
            "QFrame#aeternaSection[tone=\"flow\"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1d2630, stop:1 #181f28); "
            "  border:1px solid rgba(155,176,214,0.18); }"
            # ── Titles ──
            "QLabel#aeternaSectionTitle { color:#dce4f5; font-size:14px; font-weight:700; letter-spacing:0.5px; }"
            "QLabel#aeternaTitle { color:#f4f6ff; font-size:16px; font-weight:800; }"
            "QLabel#aeternaStatus { color:#7feca5; font-weight:700; font-size:13px; }"
            # ── Cards ──
            "QLabel#aeternaAutomationTargetCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1e2430, stop:1 #1a1f28); "
            "  border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:10px 12px; color:#dce2f0; font-size:12px; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"overview\"] { background:rgba(134,183,255,0.14); border:1px solid rgba(134,183,255,0.30); border-left:4px solid #86b7ff; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"core\"] { background:rgba(127,179,255,0.14); border:1px solid rgba(127,179,255,0.30); border-left:4px solid #7fb3ff; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"space\"] { background:rgba(143,227,136,0.14); border:1px solid rgba(143,227,136,0.30); border-left:4px solid #8fe388; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"mod\"] { background:rgba(255,210,127,0.14); border:1px solid rgba(255,210,127,0.30); border-left:4px solid #ffd27f; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"future\"] { background:rgba(162,173,194,0.12); border:1px solid rgba(162,173,194,0.24); border-left:4px solid #a2adc2; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"filter\"] { background:rgba(245,190,99,0.15); border:1px solid rgba(245,190,99,0.32); border-left:4px solid #f5be63; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"voice\"] { background:rgba(127,214,255,0.15); border:1px solid rgba(127,214,255,0.32); border-left:4px solid #7fd6ff; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"aeg\"] { background:rgba(119,224,192,0.15); border:1px solid rgba(119,224,192,0.30); border-left:4px solid #77e0c0; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"feg\"] { background:rgba(197,150,255,0.16); border:1px solid rgba(197,150,255,0.32); border-left:4px solid #c596ff; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"layer\"] { background:rgba(141,227,186,0.15); border:1px solid rgba(141,227,186,0.30); border-left:4px solid #8de3ba; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"noise\"] { background:rgba(255,154,203,0.15); border:1px solid rgba(255,154,203,0.30); border-left:4px solid #ff9acb; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"timbre\"] { background:rgba(255,179,127,0.16); border:1px solid rgba(255,179,127,0.30); border-left:4px solid #ffb37f; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"drive\"] { background:rgba(255,127,127,0.16); border:1px solid rgba(255,127,127,0.30); border-left:4px solid #ff7f7f; }"
            "QLabel#aeternaAutomationTargetCard[tone=\"flow\"] { background:rgba(155,176,214,0.13); border:1px solid rgba(155,176,214,0.28); border-left:4px solid #9bb0d6; }"
            "QLabel#aeternaAutomationTargetHint { color:#8a96ad; font-size:11px; font-style:italic; }"
            # ── Family Badges ──
            "QLabel#aeternaFamilyBadge { border-radius:10px; padding:4px 10px; font-weight:700; font-size:11px; }"
            "QLabel#aeternaFamilyBadge[tone=\"core\"] { background:rgba(127,179,255,0.18); color:#d9e8ff; border:1px solid rgba(127,179,255,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"filter\"] { background:rgba(245,190,99,0.18); color:#ffe2bd; border:1px solid rgba(245,190,99,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"voice\"] { background:rgba(127,214,255,0.18); color:#d5f2ff; border:1px solid rgba(127,214,255,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"aeg\"] { background:rgba(119,224,192,0.18); color:#d6fff1; border:1px solid rgba(119,224,192,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"feg\"] { background:rgba(197,150,255,0.18); color:#f1ddff; border:1px solid rgba(197,150,255,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"layer\"] { background:rgba(141,227,186,0.18); color:#dfffee; border:1px solid rgba(141,227,186,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"timbre\"] { background:rgba(255,179,127,0.18); color:#ffe6d3; border:1px solid rgba(255,179,127,0.40); }"
            "QLabel#aeternaFamilyBadge[tone=\"drive\"] { background:rgba(255,127,127,0.18); color:#ffe1e1; border:1px solid rgba(255,127,127,0.40); }"
            # ── Knob Mini Meters ──
            "QLabel#aeternaKnobMiniMeter { font-size:10px; color:#a0adca; padding:2px 4px; border-radius:5px; "
            "  background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); }"
            "QLabel#aeternaKnobMiniMeter[modActive=\"true\"] { color:#ffe8a0; border:1px solid rgba(255,214,127,0.35); "
            "  background:rgba(255,214,127,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"filter\"] { background:rgba(245,190,99,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"voice\"] { background:rgba(127,214,255,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"aeg\"] { background:rgba(119,224,192,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"feg\"] { background:rgba(197,150,255,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"layer\"] { background:rgba(141,227,186,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"noise\"] { background:rgba(255,154,203,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"timbre\"] { background:rgba(255,179,127,0.08); }"
            "QLabel#aeternaKnobMiniMeter[tone=\"drive\"] { background:rgba(255,127,127,0.08); }"
            # ── Signal Flow Diagram ──
            "QWidget#aeternaSignalFlowDiagram { background:#131820; border:1px solid rgba(255,255,255,0.07); border-radius:10px; }"
            # ── Controls ──
            "QToolButton { min-width: 22px; min-height: 22px; border-radius:4px; }"
            "QPushButton { min-height:30px; font-size:12px; border-radius:6px; padding:4px 10px; "
            "  background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); color:#d8deee; }"
            "QPushButton:hover { background:rgba(127,179,255,0.15); border:1px solid rgba(127,179,255,0.35); }"
            "QPushButton:pressed { background:rgba(127,179,255,0.25); }"
            "QComboBox { min-height:30px; font-size:12px; border-radius:6px; padding:4px 8px; "
            "  background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); color:#d8deee; }"
            "QComboBox:hover { border:1px solid rgba(127,179,255,0.35); }"
            "QComboBox::drop-down { border:none; width:20px; }"
            "QLineEdit { min-height:30px; font-size:12px; border-radius:6px; padding:4px 8px; "
            "  background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.10); color:#d8deee; }"
            "QLineEdit:focus { border:1px solid rgba(127,179,255,0.45); background:rgba(127,179,255,0.06); }"
            "QCheckBox, QSpinBox, QDoubleSpinBox { min-height:28px; font-size:12px; }"
        )

    # -------- UI handlers
    def _on_knob(self, key: str, value: int) -> None:
        """Handle knob value change — MUST be lightweight!
        
        This fires on EVERY pixel of knob drag (~60 times/second).
        Only set_param is time-critical (audio needs it). All visual 
        card/label updates are deferred to a throttled timer so the
        GUI thread stays free for transport/playhead/audio.
        """
        try:
            self.engine.set_param(key, float(value) / 100.0)
            if key in {"unison_mix", "sub_level", "noise_level"} and int(value) > 0:
                self._layer_toggle_memory[str(key)] = int(value)
        except Exception:
            pass
        # Defer all heavy UI updates to a single throttled timer
        self._schedule_knob_ui_refresh(key)

    def _schedule_knob_ui_refresh(self, key: str = "") -> None:
        """Schedule deferred UI refresh — max ~8 times per second."""
        self._knob_refresh_pending_key = key
        if not hasattr(self, '_knob_refresh_timer'):
            from PyQt6.QtCore import QTimer
            self._knob_refresh_timer = QTimer(self)
            self._knob_refresh_timer.setSingleShot(True)
            self._knob_refresh_timer.setInterval(120)  # max ~8Hz
            self._knob_refresh_timer.timeout.connect(self._do_knob_ui_refresh)
        if not self._knob_refresh_timer.isActive():
            self._knob_refresh_timer.start()

    def _do_knob_ui_refresh(self) -> None:
        """Actually perform deferred UI updates (runs on GUI thread, throttled)."""
        try:
            key = getattr(self, '_knob_refresh_pending_key', '')
            self._refresh_knob_automation_tooltip(key)
            self._update_all_knob_mini_meters()
            self._update_signal_flow_card()
            self._update_mod_rack_card()
            self._sync_layer_preview_toggles()
            self._persist_instrument_state()
        except Exception:
            pass

    def _on_combo_param(self, key: str, value: str) -> None:
        try:
            self.engine.set_param(key, str(value or "off"))
        except Exception:
            pass
        self._schedule_knob_ui_refresh(key)

    def _on_toggle_param(self, key: str, checked: bool) -> None:
        try:
            self.engine.set_param(key, 1.0 if checked else 0.0)
        except Exception:
            pass
        self._schedule_knob_ui_refresh(key)

    def _set_mode(self, mode: str) -> None:
        try:
            self.engine.set_param("mode", str(mode or "formula"))
            # Auto-expand/collapse wavetable section
            if hasattr(self, '_wt_section') and self._wt_section is not None:
                try:
                    self._wt_section.setVisible(mode == "wavetable")
                except Exception:
                    pass
            self._persist_instrument_state()
        except Exception:
            pass

    # ── Wavetable handlers (v0.0.20.657) ──

    def _on_wt_builtin_changed(self, name: str) -> None:
        try:
            if not name:
                return
            self.engine.load_wavetable_builtin(name)
            self._update_wt_display()
            self._persist_instrument_state()
        except Exception:
            pass

    def _on_wt_import(self) -> None:
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "Wavetable importieren",
                "", "Wavetable (*.wav *.wt);;All Files (*)"
            )
            if not path:
                return
            ok = self.engine.load_wavetable_file(path)
            if ok:
                self._update_wt_display()
                self._persist_instrument_state()
            else:
                QMessageBox.warning(self, "Import", "Wavetable konnte nicht geladen werden.")
        except Exception:
            pass

    def _on_wt_position_changed(self, val: int) -> None:
        try:
            pos = val / 1000.0
            self.engine.set_param("wt_position", pos)
            if hasattr(self, 'lbl_wt_position'):
                self.lbl_wt_position.setText(f"{pos:.3f}")
            if hasattr(self, '_wt_preview'):
                self._wt_preview.update()
            self._persist_instrument_state()
        except Exception:
            pass

    def _on_wt_unison_changed(self, *_args) -> None:
        try:
            mode_name = self.cmb_wt_unison_mode.currentText() if hasattr(self, 'cmb_wt_unison_mode') else "Off"
            n_voices = self.spn_wt_unison_voices.value() if hasattr(self, 'spn_wt_unison_voices') else 1
            detune = (self.sld_wt_detune.value() / 100.0) if hasattr(self, 'sld_wt_detune') else 0.20
            spread = (self.sld_wt_spread.value() / 100.0) if hasattr(self, 'sld_wt_spread') else 0.50
            width = (self.sld_wt_width.value() / 100.0) if hasattr(self, 'sld_wt_width') else 0.50
            self.engine.set_param("wt_unison_mode", mode_name)
            self.engine.set_param("wt_unison_voices", max(0.0, min(1.0, (n_voices - 1) / 15.0)))
            self.engine.set_param("wt_unison_detune", detune)
            self.engine.set_param("wt_unison_spread", spread)
            self.engine.set_param("wt_unison_width", width)
            self.engine.sync_wavetable_unison()
            self._persist_instrument_state()
        except Exception:
            pass

    def _on_wt_normalize(self) -> None:
        try:
            self.engine.get_wavetable_bank().normalize_all()
            if hasattr(self, '_wt_preview'):
                self._wt_preview.update()
            self._persist_instrument_state()
        except Exception:
            pass

    def _update_wt_display(self) -> None:
        """Refresh all wavetable UI elements from engine state."""
        try:
            info = self.engine.get_wavetable_info()
            if hasattr(self, 'lbl_wt_name'):
                self.lbl_wt_name.setText(str(info.get("name", "—")))
            if hasattr(self, 'lbl_wt_info'):
                self.lbl_wt_info.setText(f"{info.get('num_frames', 0)} Frames, {info.get('frame_size', 0)} samples")
            if hasattr(self, 'sld_wt_position'):
                pos = float(info.get("position", 0.0))
                self.sld_wt_position.blockSignals(True)
                self.sld_wt_position.setValue(int(pos * 1000))
                self.sld_wt_position.blockSignals(False)
                if hasattr(self, 'lbl_wt_position'):
                    self.lbl_wt_position.setText(f"{pos:.3f}")
            if hasattr(self, '_wt_preview'):
                self._wt_preview.update()
        except Exception:
            pass

    def _insert_formula_token(self, token: str) -> None:
        try:
            token = str(token or "").strip()
            if not token:
                return
            self.ed_formula.insert(token)
            self.ed_formula.setFocus()
            self._persist_instrument_state()
        except Exception:
            pass

    def _insert_formula_snippet(self) -> None:
        try:
            snippet = str(self.cmb_formula_snippet.currentData() or "").strip()
            if not snippet:
                return
            self.ed_formula.insert(snippet)
            self.ed_formula.setFocus()
            self._update_formula_mod_summary()
            self._persist_instrument_state()
        except Exception:
            pass

    def _load_formula_onboarding_preset(self, formula: str, title: str = "") -> None:
        try:
            text = str(formula or "").strip() or DEFAULT_FORMULA
            self._formula_internal_change = True
            self.ed_formula.setText(text)
            self._formula_internal_change = False
            self._formula_last_loaded_example_title = str(title or "").strip()
            self._formula_last_loaded_example_text = text
            applied = str(getattr(self, "_formula_last_applied_text", "") or "").strip()
            self._formula_status_note = f"Beispiel '{self._formula_last_loaded_example_title or 'Start'}' geladen, noch nicht angewendet" if text.strip() != applied else "Formel angewendet"
            self.ed_formula.setFocus()
            self._update_formula_mod_summary()
            self._update_formula_info_line()
            self._persist_instrument_state()
        except Exception:
            self._formula_internal_change = False
            pass

    def _apply_formula_from_ui(self) -> None:
        try:
            applied = self.ed_formula.text().strip() or DEFAULT_FORMULA
            self.engine.set_param("formula", applied)
            self._formula_last_applied_text = applied
            if applied == str(getattr(self, "_formula_last_loaded_example_text", "") or "").strip() and getattr(self, "_formula_last_loaded_example_title", ""):
                self._formula_status_note = f"Beispiel '{self._formula_last_loaded_example_title}' angewendet"
            else:
                self._formula_status_note = "Formel angewendet"
            self._update_formula_status()
            self._update_formula_mod_summary()
            self._update_formula_info_line()
            self._persist_instrument_state()
        except Exception:
            pass

    def _apply_preset(self, name: str, persist: bool = True) -> None:
        try:
            self.engine.apply_preset(name)
            self.cmb_mode.setCurrentText(str(self.engine.get_param("mode", "formula")))
            self._formula_internal_change = True
            self.ed_formula.setText(str(self.engine.get_param("formula", DEFAULT_FORMULA)))
            self._formula_internal_change = False
            self._formula_last_applied_text = str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA)
            self._formula_last_loaded_example_title = ""
            self._formula_last_loaded_example_text = ""
            self._formula_status_note = f"Preset '{name}' geladen und angewendet"
            self._apply_preset_metadata_to_ui(self._default_preset_metadata(name), persist=False)
            for key, knob in self._knobs.items():
                try:
                    knob.setValueExternal(int(round(float(self.engine.get_param(key, 0.5)) * 100.0)))
                except Exception:
                    pass
            for key, combo in self._combo_params.items():
                try:
                    combo.setCurrentText(str(self.engine.get_param(key, combo.currentText())))
                except Exception:
                    pass
            self._update_formula_status()
            self._sync_segment_form_ui()
            self._update_preset_quicklist()
            self._update_preset_library_compact()
            self._update_formula_preset_link()
            self._update_composer_summary()
            self._update_synth_stage1_panel()
            if persist:
                self._persist_instrument_state()
        except Exception:
            pass

    def _randomize_formula(self) -> None:
        base_terms = [
            "sin(phase*(1.0+m))",
            "cos(phase*(0.5+c) + d)",
            "tanh(sin(phase*0.5 + x))",
            "abs(sin(phase*0.25 + motion))",
            "sin(phase + m*sin(phase*0.125))",
            "cos(phase*(2.0-c*0.5))",
            "(0.78 + 0.22*env) * sin(phase*(1.0 + 0.14*lfo1))",
            "0.74*sin(phase + 0.18*mseg) + 0.14*cos(note_hz*0.0005 + lfo2)",
            "tanh(sin(phase*(1.0 + 0.16*chaos_src)) + 0.18*cos(phase*0.5 + env))",
            "0.72*sin(phase + 0.10*motion) + 0.20*cos(phase*0.5 + d) + 0.08*chaos_src",
            "0.60*sin(phase) + 0.22*sin(phase*2.0 + 0.10*lfo1) + 0.12*cos(phase*3.0 + 0.08*mseg)",
            "(0.82 + 0.12*env) * (0.66*sin(phase + 0.08*lfo2) + 0.18*cos(phase*0.25 + motion) + 0.10*mseg)",
            "tanh(0.72*sin(phase + 0.16*lfo1) + 0.22*cos(phase*0.5 + chaos_src) + 0.10*env)",
            "0.70*sin(phase + 0.14*mseg) + 0.20*tanh(chaos_src + 0.10*lfo2) + 0.08*cos(phase*2.0 + d)",
            "(0.84 + 0.10*env) * (sin(phase + 0.10*lfo2) + 0.18*cos(note_hz*0.0004 + mseg) + 0.08*chaos_src)",
        ]
        accents = [
            "0.35*sin(phase*2.0 + d)",
            "0.22*cos(phase*3.0 + x)",
            "0.18*tanh(sin(phase*(1.0+c)))",
            "0.28*abs(sin(phase*0.5 + motion))",
            "0.16*cos(note_hz*0.0007 + lfo2)",
            "0.12*chaos_src",
            "0.10*env*cos(phase*0.25 + lfo1)",
            "0.14*sin(phase*4.0 + 0.10*mseg)",
            "0.12*cos(note_hz*0.0011 + chaos_src)",
            "0.09*(0.5 + 0.5*env)*sin(phase + motion)",
        ]
        formula = random.choice(base_terms) + random.choice([" + ", " - "]) + random.choice(accents)
        if random.random() > 0.55:
            formula = f"({formula}) * (0.72 + 0.28*cos(phase*0.125 + c))"
        self._formula_internal_change = True
        self.ed_formula.setText(formula)
        self._formula_internal_change = False
        self._formula_status_note = "Formel manuell/random geändert, noch nicht angewendet"
        self._update_formula_info_line()
        try:
            self.cmb_mode.setCurrentText(random.choice(["formula", "formula", "spectral", "terrain", "chaos"]))
            ranges = {
                "morph": (30, 88), "chaos": (4, 82), "drift": (8, 42), "tone": (36, 74),
                "release": (24, 68), "gain": (42, 62), "space": (12, 58), "motion": (8, 78),
                "cathedral": (10, 56), "lfo1_rate": (8, 62), "lfo2_rate": (4, 34),
                "mseg_rate": (8, 54), "mod1_amount": (6, 42), "mod2_amount": (6, 42),
                "filter_cutoff": (34, 86), "filter_resonance": (8, 62),
                "pan": (20, 80), "glide": (0, 42), "stereo_spread": (10, 76),
                "aeg_attack": (2, 42), "aeg_decay": (12, 58), "aeg_sustain": (45, 92), "aeg_release": (18, 74),
                "feg_attack": (0, 30), "feg_decay": (8, 50), "feg_sustain": (20, 78), "feg_release": (10, 58), "feg_amount": (0, 52),
                "unison_mix": (0, 48), "unison_detune": (6, 42), "sub_level": (0, 42),
                "noise_level": (0, 28), "noise_color": (12, 82),
                "pitch": (24, 76), "shape": (8, 92), "pulse_width": (18, 82),
                "drive": (6, 62), "feedback": (0, 34),
            }
            self._apply_preset_metadata_to_ui(self.engine.get_preset_metadata(), persist=False)
            for key, knob in self._knobs.items():
                lo, hi = ranges.get(key, (0, 100))
                knob.setValueExternal(random.randint(lo, hi))
                self.engine.set_param(key, float(knob.value()) / 100.0)
            self.cmb_mod1_source.setCurrentText(random.choice(list(self.engine.get_mod_sources())[1:]))
            self.cmb_mod2_source.setCurrentText(random.choice(list(self.engine.get_mod_sources())[1:]))
            self.cmb_mod1_target.setCurrentText(random.choice(list(self.engine.get_mod_targets())[1:]))
            self.cmb_mod2_target.setCurrentText(random.choice(list(self.engine.get_mod_targets())[1:]))
            if hasattr(self, "cmb_filter_type"):
                self.cmb_filter_type.setCurrentText(random.choice(["LP 12", "LP 24", "HP 12", "BP", "Notch", "Comb+"]))
            if hasattr(self, "cmb_unison_voices"):
                self.cmb_unison_voices.setCurrentText(random.choice(["1", "2", "4", "6"]))
            if hasattr(self, "cmb_sub_octave"):
                self.cmb_sub_octave.setCurrentText(random.choice(["-1", "-1", "-2"]))
            if hasattr(self, "chk_retrigger"):
                self.chk_retrigger.setChecked(random.choice([True, True, False]))
            self.engine.set_param("formula", formula)
        except Exception:
            pass
        self._set_mod_view(random.choice(["mseg", "lfo1", "lfo2", "chaos"]), persist=False)
        self._update_formula_status()
        self._update_formula_mod_summary()
        self._persist_instrument_state()

    def _set_mod_view(self, view: str, persist: bool = True) -> None:
        view = str(view or "mseg").lower()
        if view not in {"mseg", "lfo1", "lfo2", "chaos"}:
            view = "mseg"
        try:
            self.mod_preview.set_view(view)
            for key, btn in getattr(self, "_mod_view_buttons", {}).items():
                try:
                    btn.setChecked(key == view)
                except Exception:
                    pass
        except Exception:
            pass
        self._sync_segment_form_ui()
        if persist:
            self._persist_instrument_state()

    def _set_overlay_visibility(self, show_web_a: bool | None, show_web_b: bool | None, persist: bool = True) -> None:
        try:
            self.mod_preview.set_overlay_visibility(show_web_a, show_web_b)
            cur_a, cur_b = self.mod_preview.overlay_visibility()
            try:
                self.chk_overlay_web_a.blockSignals(True)
                self.chk_overlay_web_a.setChecked(cur_a)
            finally:
                self.chk_overlay_web_a.blockSignals(False)
            try:
                self.chk_overlay_web_b.blockSignals(True)
                self.chk_overlay_web_b.setChecked(cur_b)
            finally:
                self.chk_overlay_web_b.blockSignals(False)
        except Exception:
            pass
        if persist:
            self._persist_instrument_state()

    def _sync_segment_form_ui(self) -> None:
        try:
            seg_idx = self.mod_preview.selected_segment()
            forms = self.engine.get_mseg_segment_forms()
            value = forms[seg_idx] if seg_idx is not None and 0 <= seg_idx < len(forms) else "linear"
            self.cmb_segment_form.blockSignals(True)
            self.cmb_segment_form.setCurrentText(str(value).title())
        except Exception:
            pass
        finally:
            try:
                self.cmb_segment_form.blockSignals(False)
            except Exception:
                pass

    def _apply_mseg_shape_preset(self) -> None:
        try:
            name = self.cmb_mseg_shape.currentText() or "Default"
            if not self.engine.apply_mseg_shape_preset(name):
                return
            self.mod_preview._select_point(None)
            self.mod_preview.update()
            self._sync_segment_form_ui()
            self._persist_instrument_state()
        except Exception:
            pass

    def _store_ab_payload(self, slot_name: str) -> bool:
        payload = self._capture_current_mseg_payload()
        if not payload:
            return False
        self._mseg_ab_slots[str(slot_name or "A")] = payload
        self._persist_instrument_state()
        return True

    def _toggle_compare_ab(self) -> bool:
        slot_name = str(self.cmb_mseg_compare.currentText() or "A")
        payload = self._mseg_ab_slots.get(slot_name)
        if not payload:
            try:
                self.btn_mseg_compare_ab.setChecked(False)
            except Exception:
                pass
            return False
        if not self._mseg_compare_live:
            self._mseg_compare_backup = self._capture_current_mseg_payload()
            self._mseg_compare_live = True
            self._mseg_compare_mode = slot_name
            return self._apply_mseg_payload(payload)
        self._mseg_compare_live = False
        restore = self._mseg_compare_backup
        self._mseg_compare_backup = None
        try:
            self.btn_mseg_compare_ab.setChecked(False)
        except Exception:
            pass
        if restore:
            return self._apply_mseg_payload(restore)
        return False

    def _apply_mseg_operation(self, op: str) -> None:
        try:
            op = str(op or "").lower()
            if op == "invert":
                self.engine.invert_mseg()
            elif op == "mirror":
                self.engine.mirror_mseg()
            elif op == "normalize":
                self.engine.normalize_mseg()
            elif op == "stretch":
                self.engine.stretch_mseg(1.15)
            elif op == "compress":
                self.engine.compress_mseg(0.85)
            elif op == "snap_x":
                self.engine.snap_mseg_x(int(self.cmb_mseg_snap.currentText() or "16"))
            elif op == "quantize_y":
                self.engine.quantize_mseg_y(int(self.cmb_mseg_y_quant.currentText() or "9"))
            elif op == "smooth":
                self.engine.smooth_mseg(0.5, 1)
            elif op == "double":
                self.engine.double_mseg()
            elif op == "halve":
                self.engine.halve_mseg()
            elif op == "bias_down":
                self.engine.bias_mseg(-0.15)
            elif op == "bias_up":
                self.engine.bias_mseg(0.15)
            elif op == "morph_shape":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_morph_amount.currentText() or "50") / 100.0))
                self.engine.morph_mseg_to_shape(self.cmb_mseg_morph_shape.currentText(), amount)
            elif op == "randomize":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_random.currentText() or "35") / 100.0))
                self.engine.randomize_mseg(amount)
            elif op == "jitter":
                jitter_pct = max(0.0, min(0.12, float(self.cmb_mseg_jitter.currentText() or "4") / 100.0))
                self.engine.jitter_mseg(jitter_pct * 0.35, jitter_pct)
            elif op == "undo":
                if not self.engine.undo_mseg():
                    return
            elif op == "redo":
                if not self.engine.redo_mseg():
                    return
            elif op == "humanize_soft":
                self.engine.humanize_mseg(0.10)
            elif op == "humanize_medium":
                self.engine.humanize_mseg(0.18)
            elif op == "recenter":
                self.engine.recenter_mseg()
            elif op == "flatten_peaks":
                self.engine.flatten_peaks_mseg(0.32)
            elif op == "curve_blend":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_blend_amount.currentText() or "50") / 100.0))
                self.engine.blend_mseg_shapes(self.cmb_mseg_blend_a.currentText(), self.cmb_mseg_blend_b.currentText(), amount)
            elif op == "copy":
                self._mseg_clipboard = self._capture_current_mseg_payload()
                self._persist_instrument_state()
                return
            elif op == "paste":
                if not self._apply_mseg_payload(self._mseg_clipboard):
                    return
                return
            elif op == "store_slot":
                payload = self._capture_current_mseg_payload()
                if not payload:
                    return
                self._mseg_slots[str(self.cmb_mseg_slot.currentText() or "1")] = payload
                self._persist_instrument_state()
                return
            elif op == "recall_slot":
                payload = self._mseg_slots.get(str(self.cmb_mseg_slot.currentText() or "1"))
                if not self._apply_mseg_payload(payload):
                    return
                return
            elif op == "store_ab":
                if not self._store_ab_payload(self.cmb_mseg_compare.currentText()):
                    return
                return
            elif op == "compare_ab":
                if not self._toggle_compare_ab():
                    return
                return
            elif op == "curve_down":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_curve.currentText() or "20") / 100.0))
                self.engine.curvature_mseg(-amount)
            elif op == "curve_up":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_curve.currentText() or "20") / 100.0))
                self.engine.curvature_mseg(amount)
            elif op == "pinch_in":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_pinch.currentText() or "20") / 100.0))
                self.engine.center_pinch_mseg(amount)
            elif op == "pinch_out":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_pinch.currentText() or "20") / 100.0))
                self.engine.center_pinch_mseg(-amount)
            elif op == "tilt_down":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_tilt.currentText() or "20") / 100.0))
                self.engine.tilt_mseg(-amount)
            elif op == "tilt_up":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_tilt.currentText() or "20") / 100.0))
                self.engine.tilt_mseg(amount)
            elif op == "skew_left":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_skew.currentText() or "20") / 100.0))
                self.engine.skew_mseg(-amount)
            elif op == "skew_right":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_skew.currentText() or "20") / 100.0))
                self.engine.skew_mseg(amount)
            elif op == "range_clamp":
                amount = max(0.10, min(1.0, float(self.cmb_mseg_range_clamp.currentText() or "80") / 100.0))
                self.engine.range_clamp_mseg(amount)
            elif op == "deadband":
                amount = max(0.0, min(0.9, float(self.cmb_mseg_deadband.currentText() or "10") / 100.0))
                self.engine.deadband_mseg(amount)
            elif op == "micro_smooth":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_micro_smooth.currentText() or "30") / 100.0))
                self.engine.micro_smooth_mseg(amount)
            elif op == "softclip":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_softclip.currentText() or "20") / 100.0))
                self.engine.softclip_drive_mseg(amount)
            elif op == "center_flatten":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_center_edge.currentText() or "20") / 100.0))
                self.engine.center_flatten_mseg(amount)
            elif op == "edge_boost":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_center_edge.currentText() or "20") / 100.0))
                self.engine.edge_boost_mseg(amount)
            elif op == "phase_left":
                amount = max(0.0, min(0.5, float(self.cmb_mseg_phase_rotate.currentText() or "10") / 100.0))
                self.engine.phase_rotate_mseg(-amount)
            elif op == "phase_right":
                amount = max(0.0, min(0.5, float(self.cmb_mseg_phase_rotate.currentText() or "10") / 100.0))
                self.engine.phase_rotate_mseg(amount)
            elif op == "symmetry":
                amount = max(0.0, min(1.0, float(self.cmb_mseg_symmetry.currentText() or "30") / 100.0))
                self.engine.symmetry_mseg(amount)
            elif op == "slope_limit":
                amount = max(0.05, min(1.5, float(self.cmb_mseg_slope.currentText() or "35") / 50.0))
                self.engine.slope_limit_mseg(amount)
            else:
                return
            self.mod_preview.update()
            self._notify_mseg_points_changed_and_persist()
            self._sync_point_editor_ui()
        except Exception:
            pass

    def _on_segment_form_changed(self, txt: str) -> None:
        try:
            seg_idx = self.mod_preview.selected_segment()
            if seg_idx is None:
                seg_idx = 0
            if self.mod_preview._set_mseg_segment_form(int(seg_idx), str(txt).lower()):
                self._sync_segment_form_ui()
                self._persist_instrument_state()
        except Exception:
            pass

    def _on_mseg_points_changed(self) -> None:
        self._notify_mseg_points_changed_and_persist()
        self._sync_point_editor_ui()

    def _reset_mseg_points(self) -> None:
        try:
            self.engine.reset_mseg_points()
            self.mod_preview._select_point(None)
            self.mod_preview.update()
            self._sync_segment_form_ui()
            self._persist_instrument_state()
        except Exception:
            pass

    def _tick_scope(self) -> None:
        try:
            self.scope.update()
        except Exception:
            pass
        try:
            self.mod_preview.advance_phase(0.06)
        except Exception:
            pass

    def _macro_motion_hint(self, source: str, target: str, amount: int) -> str:
        source_l = str(source or "off").strip().lower()
        target_l = str(target or "off").strip().lower()
        if source_l == "off" or target_l == "off":
            return "noch aus – erst Quelle und Ziel wählen"
        if "lfo" in source_l:
            base = "gut für lebendige Sweeps"
        elif "mseg" in source_l:
            base = "gut für gezeichnete Verläufe"
        elif "chaos" in source_l:
            base = "gut für organische Bewegung"
        elif "env" in source_l or "vel" in source_l:
            base = "gut für spielabhängige Dynamik"
        else:
            base = "gut für stabile Modulation"
        if amount >= 65:
            intensity = "stark"
        elif amount >= 35:
            intensity = "mittel"
        elif amount > 0:
            intensity = "fein"
        else:
            intensity = "aus"
        if any(x in target_l for x in ("tone", "morph", "motion", "space", "cathedral")):
            return f"{base} • {intensity} hörbar"
        if any(x in target_l for x in ("gain", "release", "drift", "chaos")):
            return f"{base} • {intensity} eher formend"
        return f"{base} • {intensity} dosieren"

    def _update_macro_ab_readability(self) -> None:
        try:
            if not hasattr(self, "lbl_macro_ab_card"):
                return
            a_src = self.cmb_mod1_source.currentText() if hasattr(self, "cmb_mod1_source") else "off"
            a_tgt = self.cmb_mod1_target.currentText() if hasattr(self, "cmb_mod1_target") else "off"
            b_src = self.cmb_mod2_source.currentText() if hasattr(self, "cmb_mod2_source") else "off"
            b_tgt = self.cmb_mod2_target.currentText() if hasattr(self, "cmb_mod2_target") else "off"
            a_amt = int(self._knobs.get("mod1_amount").value()) if self._knobs.get("mod1_amount") is not None else 0
            b_amt = int(self._knobs.get("mod2_amount").value()) if self._knobs.get("mod2_amount") is not None else 0
            a_pol = self._mod_polarity_symbol(1)
            b_pol = self._mod_polarity_symbol(2)
            a_line = f"Macro A: {a_src or 'off'} → {a_tgt or 'off'} • {a_pol}{a_amt}% • {self._macro_motion_hint(a_src, a_tgt, a_amt)}"
            b_line = f"Macro B: {b_src or 'off'} → {b_tgt or 'off'} • {b_pol}{b_amt}% • {self._macro_motion_hint(b_src, b_tgt, b_amt)}"
            self.lbl_macro_ab_card.setText(a_line + "\n" + b_line)
            self.lbl_macro_ab_hint.setText(
                "Makro A/B lokal lesbar: erst Quelle → Ziel wählen, dann Amount dosieren. "
                "Für Automation weiter bevorzugt: Web A/Web B Amount oder Rate-Knobs."
            )
        except Exception:
            pass

    def _web_template_intensity_factor(self) -> float:
        try:
            label = str(self.cmb_web_template_intensity.currentText() or "Mittel").strip().lower()
        except Exception:
            label = "mittel"
        return float(WEB_TEMPLATE_INTENSITY_FACTORS.get(label, 1.0))

    def _scaled_web_template_config(self, cfg: dict) -> dict:
        scaled = dict(cfg or {})
        factor = self._web_template_intensity_factor()
        amount_keys = ("mod1_amount", "mod2_amount", "lfo1_rate", "lfo2_rate", "mseg_rate")
        for key in amount_keys:
            if key not in scaled:
                continue
            try:
                value = int(round(float(scaled.get(key, 0)) * factor))
            except Exception:
                value = int(scaled.get(key, 0) or 0)
            scaled[key] = max(0, min(100, value))
        return scaled

    def _web_template_config(self, name: str) -> dict:
        key = str(name or "").strip().lower()
        if key == "basis":
            return dict(WEB_TEMPLATE_BASELINE)
        for preset_name, _hint, cfg in WEB_TEMPLATE_PRESETS:
            if preset_name.strip().lower() == key:
                return self._scaled_web_template_config(cfg)
        return {}

    def _apply_web_template(self, name: str) -> None:
        try:
            cfg = self._web_template_config(name)
            if not cfg:
                return
            for key, value in cfg.items():
                if key in self._knobs and self._knobs.get(key) is not None:
                    self._knobs[key].setValue(int(value))
                elif key in self._combo_params and self._combo_params.get(key) is not None:
                    self._combo_params[key].setCurrentText(str(value))
            self._active_web_template = str(name)
            self._update_web_template_card()
            self._persist_instrument_state()
        except Exception:
            pass

    def _reset_web_template_to_baseline(self) -> None:
        try:
            self._apply_web_template("Basis")
        except Exception:
            pass

    def _on_web_template_intensity_changed(self, _label: str) -> None:
        try:
            active = self._detect_web_template_name()
            stored = str(getattr(self, "_active_web_template", "") or "").strip()
            template_name = stored if stored and stored != "Eigen" else active
            if template_name and template_name != "Eigen":
                self._apply_web_template(template_name)
            else:
                self._update_web_template_card()
                self._persist_instrument_state()
        except Exception:
            pass

    def _detect_web_template_name(self) -> str:
        try:
            current = {
                "mod1_source": self.cmb_mod1_source.currentText() if hasattr(self, "cmb_mod1_source") else "off",
                "mod1_target": self.cmb_mod1_target.currentText() if hasattr(self, "cmb_mod1_target") else "off",
                "mod2_source": self.cmb_mod2_source.currentText() if hasattr(self, "cmb_mod2_source") else "off",
                "mod2_target": self.cmb_mod2_target.currentText() if hasattr(self, "cmb_mod2_target") else "off",
                "filter_type": self.cmb_filter_type.currentText() if hasattr(self, "cmb_filter_type") else "LP 24",
                "mod1_amount": int(self._knobs.get("mod1_amount").value()) if self._knobs.get("mod1_amount") is not None else 0,
                "mod2_amount": int(self._knobs.get("mod2_amount").value()) if self._knobs.get("mod2_amount") is not None else 0,
                "filter_cutoff": int(self._knobs.get("filter_cutoff").value()) if self._knobs.get("filter_cutoff") is not None else 68,
                "filter_resonance": int(self._knobs.get("filter_resonance").value()) if self._knobs.get("filter_resonance") is not None else 18,
                "lfo1_rate": int(self._knobs.get("lfo1_rate").value()) if self._knobs.get("lfo1_rate") is not None else 0,
                "lfo2_rate": int(self._knobs.get("lfo2_rate").value()) if self._knobs.get("lfo2_rate") is not None else 0,
                "mseg_rate": int(self._knobs.get("mseg_rate").value()) if self._knobs.get("mseg_rate") is not None else 0,
            }
            if all(current.get(k) == v for k, v in WEB_TEMPLATE_BASELINE.items()):
                return "Basis"
            for preset_name, _hint, cfg in WEB_TEMPLATE_PRESETS:
                expected = self._scaled_web_template_config(cfg)
                if all(current.get(k) == v for k, v in expected.items()):
                    return preset_name
        except Exception:
            pass
        return "Eigen"

    def _update_web_template_card(self) -> None:
        try:
            if not hasattr(self, "lbl_web_template_card"):
                return
            active = self._detect_web_template_name()
            a_src = self.cmb_mod1_source.currentText() if hasattr(self, "cmb_mod1_source") else "off"
            a_tgt = self.cmb_mod1_target.currentText() if hasattr(self, "cmb_mod1_target") else "off"
            b_src = self.cmb_mod2_source.currentText() if hasattr(self, "cmb_mod2_source") else "off"
            b_tgt = self.cmb_mod2_target.currentText() if hasattr(self, "cmb_mod2_target") else "off"
            a_amt = int(self._knobs.get("mod1_amount").value()) if self._knobs.get("mod1_amount") is not None else 0
            b_amt = int(self._knobs.get("mod2_amount").value()) if self._knobs.get("mod2_amount") is not None else 0
            intensity = self.cmb_web_template_intensity.currentText() if hasattr(self, "cmb_web_template_intensity") else "Mittel"
            self.lbl_web_template_card.setText(
                f"Web-Vorlage: {active} • Intensität: {intensity}\n"
                f"A: {a_src or 'off'} → {a_tgt or 'off'} • {a_amt}%\n"
                f"B: {b_src or 'off'} → {b_tgt or 'off'} • {b_amt}%"
            )
            hint_map = {
                "Langsam": "Sehr ruhiger Start für sakrale Flächen und klare Räume.",
                "Lebendig": "Mehr hörbare Bewegung, aber weiter kontrolliert und musikalisch.",
                "Organisch": "Weich schwebend mit sanftem Drift statt hartem Zappeln.",
                "Sakral": "Raum + Kathedral-Atem für Bach-nahe, klare Flächen.",
                "Basis": "Sichere neutrale Ausgangslage: Web A/B aus, nur Grundwerte aktiv.",
                "Eigen": "Momentan manuell angepasst: gut für Feintuning nach Gefühl.",
            }
            base_hint = hint_map.get(active, "Lokale sichere Startwege für Web A/B innerhalb von AETERNA.")
            self.lbl_web_template_hint.setText(
                base_hint + " Intensität wirkt nur auf lokale Amount-/Rate-Werte und wird mit dem Projekt gespeichert."
            )
        except Exception:
            pass

    def _capture_local_snapshot(self) -> dict:
        snap = {
            "preset": self.cmb_preset.currentText() if hasattr(self, "cmb_preset") else "",
            "mode": self.cmb_mode.currentText() if hasattr(self, "cmb_mode") else "formula",
            "formula": self.ed_formula.text() if hasattr(self, "ed_formula") else str(self.engine.get_param("formula", DEFAULT_FORMULA) or DEFAULT_FORMULA),
            "formula_example_title": str(getattr(self, "_formula_last_loaded_example_title", "") or ""),
            "formula_example_text": str(getattr(self, "_formula_last_loaded_example_text", "") or ""),
            "formula_applied_text": str(getattr(self, "_formula_last_applied_text", "") or ""),
            "formula_status_note": str(getattr(self, "_formula_status_note", "") or ""),
            "web_template_intensity": self.cmb_web_template_intensity.currentText() if hasattr(self, "cmb_web_template_intensity") else "Mittel",
            "active_web_template": str(getattr(self, "_active_web_template", "") or ""),
            "knobs": {},
            "combos": {},
        }
        for key in ("morph", "chaos", "drift", "tone", "release", "gain", "space", "motion", "cathedral", "lfo1_rate", "lfo2_rate", "mseg_rate", "mod1_amount", "mod2_amount", "filter_cutoff", "filter_resonance", "pan", "glide", "stereo_spread", "aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release", "feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount", "unison_mix", "unison_detune", "sub_level", "noise_level", "noise_color"):
            knob = self._knobs.get(key)
            if knob is not None:
                try:
                    snap["knobs"][key] = int(knob.value())
                except Exception:
                    pass
        for key in ("mod1_source", "mod1_target", "mod2_source", "mod2_target", "filter_type", "unison_voices", "sub_octave",
                    "mod3_source", "mod3_target", "mod4_source", "mod4_target", "mod5_source", "mod5_target",
                    "mod6_source", "mod6_target", "mod7_source", "mod7_target", "mod8_source", "mod8_target"):
            combo = self._combo_params.get(key)
            if combo is not None:
                try:
                    snap["combos"][key] = combo.currentText()
                except Exception:
                    pass
        return snap

    def _set_snapshot_last_action(self, action: str, slot: str, snap: dict | None) -> None:
        try:
            act = str(action or "Aktion").strip() or "Aktion"
            slot_txt = str(slot or "?").strip().upper() or "?"
            if isinstance(snap, dict):
                preset = str(snap.get("preset") or "–").strip() or "–"
                mood = self._snapshot_musical_hint(snap)
                formula_hint = self._snapshot_formula_hint(snap)
                web = str(snap.get("active_web_template") or "Eigen").strip() or "Eigen"
                intensity = str(snap.get("web_template_intensity") or "Mittel").strip() or "Mittel"
                note = f"Zuletzt: {act} {slot_txt} • {preset} • {mood} • {formula_hint} • Web {web}/{intensity}"
            else:
                note = f"Zuletzt: {act} {slot_txt}"
            self._snapshot_last_action_note = note
            if hasattr(self, "lbl_snapshot_last_action") and self.lbl_snapshot_last_action is not None:
                self.lbl_snapshot_last_action.setText(note)
                self.lbl_snapshot_last_action.setToolTip(note)
        except Exception:
            pass

    def _store_local_snapshot(self, slot_name: str) -> None:
        try:
            slot = str(slot_name or "").strip().upper()
            if not slot:
                return
            self._local_snapshots[slot] = self._capture_local_snapshot()
            self._active_snapshot_slot = slot
            self._set_snapshot_last_action("Store", slot, self._local_snapshots.get(slot))
            self._update_snapshot_card()
            self._persist_instrument_state()
        except Exception:
            pass

    def _recall_local_snapshot(self, slot_name: str) -> None:
        try:
            slot = str(slot_name or "").strip().upper()
            snap = self._local_snapshots.get(slot) if isinstance(self._local_snapshots, dict) else None
            if not isinstance(snap, dict):
                return
            self._restoring_state = True
            try:
                mode = str(snap.get("mode") or "formula")
                if hasattr(self, "cmb_mode"):
                    self.cmb_mode.setCurrentText(mode)
                preset = str(snap.get("preset") or "")
                if preset and hasattr(self, "cmb_preset"):
                    self.cmb_preset.setCurrentText(preset)
                formula = str(snap.get("formula") or DEFAULT_FORMULA)
                self._formula_internal_change = True
                if hasattr(self, "ed_formula"):
                    self.ed_formula.setText(formula)
                self._formula_internal_change = False
                self._formula_last_loaded_example_title = str(snap.get("formula_example_title") or "")
                self._formula_last_loaded_example_text = str(snap.get("formula_example_text") or "")
                self._formula_last_applied_text = str(snap.get("formula_applied_text") or formula)
                self._formula_status_note = str(snap.get("formula_status_note") or "Snapshot geladen")
                if hasattr(self, "cmb_web_template_intensity"):
                    self.cmb_web_template_intensity.setCurrentText(str(snap.get("web_template_intensity") or "Mittel"))
                self._active_web_template = str(snap.get("active_web_template") or "")
                for key, value in (snap.get("knobs") or {}).items():
                    knob = self._knobs.get(str(key))
                    if knob is not None:
                        try:
                            knob.setValue(int(value))
                        except Exception:
                            pass
                for key, value in (snap.get("combos") or {}).items():
                    combo = self._combo_params.get(str(key))
                    if combo is not None:
                        try:
                            combo.setCurrentText(str(value))
                        except Exception:
                            pass
            finally:
                self._restoring_state = False
            self._active_snapshot_slot = slot
            self._set_snapshot_last_action("Recall", slot, snap)
            self._update_formula_status()
            self._update_formula_info_line()
            self._update_web_template_card()
            self._update_macro_ab_readability()
            self._update_snapshot_card()
            self._persist_instrument_state()
        except Exception:
            pass


    def _snapshot_musical_hint(self, snap: dict) -> str:
        try:
            hay = " ".join([
                str(snap.get("preset") or ""),
                str(snap.get("formula_example_title") or ""),
                str(snap.get("formula_status_note") or ""),
                str(snap.get("active_web_template") or ""),
            ]).lower()
            if any(k in hay for k in ("bach", "choral", "chapel", "kathedral", "kathedrale", "sakral", "orgel", "abendmanual")):
                return "sakral"
            if any(k in hay for k in ("crystal", "kristall", "glas", "celesta")):
                return "klar"
            if any(k in hay for k in ("drone", "organisch", "organic")):
                return "getragen"
            if any(k in hay for k in ("chaos", "glitch")):
                return "belebt"
            return "offen"
        except Exception:
            return "offen"

    def _snapshot_formula_hint(self, snap: dict) -> str:
        try:
            title = str(snap.get("formula_example_title") or "").strip()
            if title:
                return title
            if str(snap.get("formula") or "").strip():
                return "eigene Formel"
            return "Init"
        except Exception:
            return "Init"

    def _snapshot_short_name(self, slot: str, snap: dict | None) -> str:
        slot_txt = str(slot or "?").strip().upper() or "?"
        if not isinstance(snap, dict):
            return f"Slot {slot_txt}"
        preset = str(snap.get("preset") or "Init Patch").strip() or "Init Patch"
        mood = self._snapshot_musical_hint(snap)
        words = [w for w in preset.replace("_", " ").split() if w]
        if not words:
            short = "Init"
        elif len(words) == 1:
            short = words[0][:10]
        else:
            short = (words[0][:6] + "·" + words[1][:6])[:14]
        return f"Slot {slot_txt} • {short}/{mood[:6]}"

    def _snapshot_badge_palette(self, mood: str, is_active: bool) -> tuple[str, str, str, str]:
        mood_key = str(mood or "offen").strip().lower()
        mood_map = {
            "sakral": ("#b18cff", "sakral"),
            "klar": ("#7fdcff", "klar"),
            "getragen": ("#e7c77b", "getragen"),
            "belebt": ("#ffae6b", "belebt"),
            "offen": ("#9aa4b2", "offen"),
        }
        mood_color, mood_text = mood_map.get(mood_key, ("#9aa4b2", mood_key or "offen"))
        if is_active:
            return ("#57d38c", "aktiv", mood_color, mood_text)
        return ("#7aa2ff", "gefüllt", mood_color, mood_text)

    def _snapshot_badge_html(self, slot: str, snap: dict | None) -> str:
        if not isinstance(snap, dict):
            return "<span style='color:#8b949e; font-weight:600;'>● leer</span> <span style='color:#8b949e;'>bereit</span>"
        mood = self._snapshot_musical_hint(snap)
        is_active = str(getattr(self, "_active_snapshot_slot", "") or "") == str(slot or "")
        state_color, state_text, mood_color, mood_text = self._snapshot_badge_palette(mood, is_active)
        return (
            f"<span style='color:{state_color}; font-weight:600;'>● {state_text}</span> "
            f"<span style='color:{mood_color}; font-weight:600;'>• {mood_text}</span>"
        )

    def _snapshot_slot_tooltip(self, slot: str, snap: dict | None) -> str:
        if not isinstance(snap, dict):
            return f"Snapshot {slot}: leer und bereit für Klang / Formel / Web."
        preset = str(snap.get("preset") or "–").strip() or "–"
        formula_hint = self._snapshot_formula_hint(snap)
        web = str(snap.get("active_web_template") or "Eigen").strip() or "Eigen"
        intensity = str(snap.get("web_template_intensity") or "Mittel").strip() or "Mittel"
        mood = self._snapshot_musical_hint(snap)
        state_text = "aktiv" if str(getattr(self, "_active_snapshot_slot", "") or "") == str(slot or "") else "gefüllt"
        return (
            f"Snapshot {slot} • {state_text}\n"
            f"Preset: {preset}\n"
            f"Hörbild: {mood}\n"
            f"Formel: {formula_hint}\n"
            f"Web: {web}/{intensity}"
        )

    def _update_snapshot_card(self) -> None:
        try:
            if not hasattr(self, "lbl_snapshot_card"):
                return
            parts = []
            for slot in ("A", "B", "C"):
                snap = self._local_snapshots.get(slot) if isinstance(self._local_snapshots, dict) else None
                tooltip = self._snapshot_slot_tooltip(slot, snap)
                badge_label = getattr(self, "_snapshot_badge_labels", {}).get(slot)
                if badge_label is not None:
                    badge_label.setText(self._snapshot_badge_html(slot, snap))
                    badge_label.setToolTip(tooltip)
                slot_label = getattr(self, "_snapshot_slot_labels", {}).get(slot)
                if slot_label is not None:
                    slot_label.setText(self._snapshot_short_name(slot, snap))
                    slot_label.setToolTip(tooltip)
                recall_btn = getattr(self, "_snapshot_recall_buttons", {}).get(slot)
                if recall_btn is not None:
                    recall_btn.setEnabled(isinstance(snap, dict))
                    recall_btn.setToolTip(tooltip if isinstance(snap, dict) else f"Snapshot {slot} ist noch leer.")
                store_btn = getattr(self, "_snapshot_store_buttons", {}).get(slot)
                if store_btn is not None:
                    store_btn.setToolTip((tooltip + "\nNeu speichern/überschreiben.") if isinstance(snap, dict) else f"Speichert aktuellen lokalen Klang/Formula/Web-Zustand in Snapshot {slot}.")
                if isinstance(snap, dict):
                    preset = str(snap.get("preset") or "–").strip() or "–"
                    formula_hint = self._snapshot_formula_hint(snap)
                    web = str(snap.get("active_web_template") or "Eigen").strip() or "Eigen"
                    intensity = str(snap.get("web_template_intensity") or "Mittel").strip() or "Mittel"
                    mood = self._snapshot_musical_hint(snap)
                    state_label = "aktiv" if str(getattr(self, "_active_snapshot_slot", "") or "") == slot else "gefüllt"
                    active_mark = " • aktiv" if state_label == "aktiv" else ""
                    parts.append(f"{slot}: [{state_label}] {preset} · {mood} · {formula_hint} · Web {web}/{intensity}{active_mark}")
                else:
                    parts.append(f"{slot}: [leer] bereit für Klang/Formel/Web")
            self.lbl_snapshot_card.setText("Snapshots\n" + "\n".join(parts))
            if hasattr(self, "lbl_snapshot_last_action") and self.lbl_snapshot_last_action is not None:
                note = str(getattr(self, "_snapshot_last_action_note", "") or "Zuletzt: noch kein lokaler Snapshot-Vorgang")
                self.lbl_snapshot_last_action.setText(note)
                self.lbl_snapshot_last_action.setToolTip(note)
            self._update_preset_snapshot_quicklaunchs()
        except Exception:
            pass

    def _snapshot_quicklaunch_entries(self) -> list[dict]:
        entries: list[dict] = []
        try:
            if isinstance(self._local_snapshots, dict):
                for slot in ("A", "B", "C"):
                    snap = self._local_snapshots.get(slot)
                    if not isinstance(snap, dict):
                        continue
                    preset = str(snap.get("preset") or "–").strip() or "–"
                    mood = self._snapshot_musical_hint(snap)
                    formula_hint = self._snapshot_formula_hint(snap)
                    web = str(snap.get("active_web_template") or "Eigen").strip() or "Eigen"
                    intensity = str(snap.get("web_template_intensity") or "Mittel").strip() or "Mittel"
                    tooltip = self._snapshot_slot_tooltip(slot, snap)
                    entries.append({
                        "kind": "snapshot",
                        "slot": slot,
                        "title": self._snapshot_short_name(slot, snap).replace("Slot ", ""),
                        "line": f"{slot}: {preset} • {mood} • {formula_hint} • Web {web}/{intensity}",
                        "tooltip": tooltip + "\nSchnellaufruf: Recall dieses lokalen Snapshot-Slots.",
                    })
            visible_presets = []
            if hasattr(self, "cmb_preset_quick_filter"):
                filter_name = str(self.cmb_preset_quick_filter.currentText() or "Alle")
                candidates = [n for n in self._preset_quick_candidates() if self._preset_matches_quick_filter(n, filter_name)]
                visible_presets = (candidates or self._preset_quick_candidates())[:4]
            else:
                visible_presets = self._preset_quick_candidates()[:4]
            used_names = {str(entry.get("title") or "") for entry in entries}
            for name in visible_presets:
                combo_line = self._preset_combo_tip_line(name, compact=True)
                marker = self._preset_marker_text(name, compact=True)
                line = f"Preset {name} • {marker} • {combo_line}"
                title = f"Preset · {name[:16]}"
                if title in used_names:
                    continue
                tooltip = (
                    f"Lokaler Preset-Schnellaufruf: {name}\n"
                    f"Direktmarker: {marker}\n"
                    f"{self._format_hearing_tags(self._preset_hearing_tags(name), prefix='Hörbild')}\n"
                    f"{self._preset_combo_tip_line(name)}"
                )
                entries.append({
                    "kind": "preset",
                    "preset": name,
                    "title": title,
                    "line": line,
                    "tooltip": tooltip,
                })
                used_names.add(title)
                if len(entries) >= 6:
                    break
        except Exception:
            return entries
        return entries

    def _update_preset_snapshot_quicklaunchs(self) -> None:
        try:
            if not hasattr(self, "lbl_snapshot_quicklaunch"):
                return
            entries = self._snapshot_quicklaunch_entries()
            visible = entries[:3]
            lines = []
            for idx, btn in enumerate(getattr(self, "_snapshot_quicklaunch_buttons", [])):
                if idx < len(visible):
                    entry = visible[idx]
                    btn.setText(str(entry.get("title") or "–"))
                    btn.setEnabled(True)
                    btn.setToolTip(str(entry.get("tooltip") or "Lokaler Schnellaufruf"))
                    if str(entry.get("kind") or "") == "snapshot":
                        slot = str(entry.get("slot") or "")
                        self._rebind_button_click(btn, lambda _=False, s=slot: self._recall_local_snapshot(s))
                    else:
                        preset_name = str(entry.get("preset") or "")
                        self._rebind_button_click(btn, lambda _=False, pp=preset_name: self._apply_preset(pp, persist=True))
                    lines.append(f"• {entry.get('line') or ''}")
                else:
                    btn.setText("–")
                    btn.setEnabled(False)
                    btn.setToolTip("Noch kein lokaler Schnellaufruf belegt.")
                    self._rebind_button_click(btn, None)
            if lines:
                self.lbl_snapshot_quicklaunch.setText("Schnellaufrufe\n" + "\n".join(lines))
            else:
                self.lbl_snapshot_quicklaunch.setText("Schnellaufrufe: lokale Preset-/Snapshot-Kombis werden hier kompakt gezeigt")
        except Exception:
            pass

    def _update_formula_mod_summary(self) -> None:
        try:
            if not hasattr(self, "lbl_formula_mod_slots"):
                return
            info = self.engine.get_formula_mod_summary()
            active = str(info.get("active_text") or "keine Sonderquelle")
            normalized = str(info.get("normalized_formula") or "")
            if len(normalized) > 120:
                normalized = normalized[:117] + "..."
            self.lbl_formula_mod_slots.setText(f"Aktive Formelquellen: {active}")
            self.lbl_formula_mod_normalized.setText(f"Alias-Ansicht: {normalized or '–'}")
        except Exception:
            pass

    def _update_formula_status(self) -> None:
        ok = bool(self.engine.get_formula_status())
        self.lbl_status.setText("FORMULA OK" if ok else "FORMULA FALLBACK")
        self.lbl_status.setStyleSheet("color:#9ee493; font-weight:700;" if ok else "color:#ffb16b; font-weight:700;")

    def _update_formula_info_line(self) -> None:
        try:
            if not hasattr(self, "lbl_formula_info"):
                return
            current = str(self.ed_formula.text() or "").strip()
            applied = str(getattr(self, "_formula_last_applied_text", "") or "").strip()
            loaded = str(getattr(self, "_formula_last_loaded_example_text", "") or "").strip()
            loaded_title = str(getattr(self, "_formula_last_loaded_example_title", "") or "").strip()
            state_bits = []
            if loaded and current == loaded and current != applied:
                state_bits.append(f"Beispiel: {loaded_title or 'Start'}")
                state_bits.append("im Feld")
                state_bits.append("noch nicht angewendet")
            elif current == applied:
                state_bits.append("Angewendet")
                if loaded_title and applied == loaded:
                    state_bits.append(f"aus {loaded_title}")
            elif current:
                state_bits.append("Manuell geändert")
                state_bits.append("noch nicht angewendet")
            else:
                state_bits.append("Leer")
                state_bits.append("Fallback bei Anwenden")
            note = str(getattr(self, "_formula_status_note", "") or "").strip()
            line = "Formelstatus: " + " • ".join(state_bits)
            if note:
                line += f" — {note}"
            self.lbl_formula_info.setText(line)
            self._update_formula_preset_link()
        except Exception:
            pass

    def _apply_automation_value_to_engine(self, key: str, value: float, persist: bool = False) -> None:
        try:
            self.engine.set_param(key, max(0.0, min(1.0, float(value) / 100.0)))
            knob = self._knobs.get(key)
            if knob is not None:
                knob.setValueExternal(int(round(float(value))))
            self._refresh_knob_automation_tooltip(key)
            if persist:
                self._persist_instrument_state()
        except Exception:
            pass
