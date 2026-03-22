# -*- coding: utf-8 -*-
"""AETERNA engine — safe flagship synth foundation.

Goals for this integration path:
- self-contained pull-source instrument
- safe registration via SamplerRegistry
- vectorized NumPy DSP (no core engine changes)
- formula-based timbre generation + random/chaos flavours
- optional continuous micropitch support like other internal instruments
- Phase 2 safe: local LFO/MSEG modulation matrix only inside AETERNA

This remains intentionally conservative so existing playback paths stay untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ast
import math
import re
import threading
from typing import Any, Dict, List

import numpy as np

from pydaw.plugins.aeterna.wavetable import WavetableBank, UnisonEngine, BUILTIN_WAVETABLES

TWOPI = 2.0 * math.pi

_ALLOWED_FUNCS = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "tanh": np.tanh,
    "abs": np.abs,
    "sqrt": np.sqrt,
    "log": np.log,
    "log1p": np.log1p,
    "exp": np.exp,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "clip": np.clip,
    "rand": None,
    "random": None,
}
_ALLOWED_CONSTS = {
    "pi": np.pi,
    "e": np.e,
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
)

DEFAULT_FORMULA = "sin(phase + m*sin(0.5*phase)) * (0.72 + 0.28*cos(0.25*phase + c))"
AETERNA_STATE_SCHEMA_VERSION = 12
AETERNA_PRESET_SCHEMA_VERSION = 4
MAX_MOD_SLOTS = 8
MOD_SOURCE_KEYS = ("off", "lfo1", "lfo2", "lfo3", "lfo4", "mseg", "chaos", "env", "env2", "vel")
MOD_TARGET_KEYS = ("off", "morph", "chaos", "drift", "motion", "tone", "space", "cathedral", "filter_cutoff", "filter_resonance", "pan", "glide", "stereo_spread", "aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release", "feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount", "unison_mix", "unison_detune", "sub_level", "noise_level", "noise_color", "pitch", "shape", "pulse_width", "drive", "feedback", "wt_position")
_VALID_MODES = {"formula", "spectral", "terrain", "chaos", "wavetable"}
_STRING_PARAMS = {"mode", "formula", "filter_type", "unison_voices", "sub_octave", "wt_table_name", "wt_unison_mode"} | {
    f"mod{i}_{p}" for i in range(1, MAX_MOD_SLOTS + 1) for p in ("source", "target", "polarity")
}
DEFAULT_MSEG_POINTS = (
    (0.0, 0.0),
    (0.16, 1.0),
    (0.38, -0.18),
    (0.70, 0.48),
    (1.0, 0.0),
)
DEFAULT_MSEG_SEGMENT_FORMS = ("smooth", "linear", "smooth", "linear")
MSEG_SEGMENT_FORMS = ("linear", "smooth")
MSEG_SNAP_DIVISIONS = (4, 8, 16, 32)
MSEG_Y_QUANTIZE_LEVELS = (3, 5, 9, 17)
MSEG_RANDOMIZE_AMOUNTS = ("10", "20", "35", "50")
MSEG_JITTER_AMOUNTS = ("2", "4", "8", "12")
MSEG_BLEND_AMOUNTS = ("25", "50", "75")
MSEG_TILT_AMOUNTS = ("10", "20", "35")
MSEG_SKEW_AMOUNTS = ("10", "20", "35")
MSEG_RANGE_CLAMP_LEVELS = ("50", "65", "80", "90")
MSEG_DEADBAND_LEVELS = ("5", "10", "20", "30")
MSEG_MICRO_SMOOTH_LEVELS = ("15", "30", "45")
MSEG_SOFTCLIP_DRIVE_LEVELS = ("10", "20", "35", "50")
MSEG_CENTER_EDGE_LEVELS = ("10", "20", "35", "50")
MSEG_SHAPE_PRESETS = {
    "Default": {
        "points": DEFAULT_MSEG_POINTS,
        "forms": DEFAULT_MSEG_SEGMENT_FORMS,
    },
    "Ramp Up": {
        "points": ((0.0, -1.0), (1.0, 1.0)),
        "forms": ("linear",),
    },
    "Ramp Down": {
        "points": ((0.0, 1.0), (1.0, -1.0)),
        "forms": ("linear",),
    },
    "Triangle": {
        "points": ((0.0, -1.0), (0.5, 1.0), (1.0, -1.0)),
        "forms": ("linear", "linear"),
    },
    "Arch": {
        "points": ((0.0, -0.6), (0.2, 0.3), (0.5, 1.0), (0.8, 0.3), (1.0, -0.6)),
        "forms": ("smooth", "smooth", "smooth", "smooth"),
    },
    "Pulse Gate": {
        "points": ((0.0, -1.0), (0.08, 1.0), (0.18, 1.0), (0.30, -0.9), (0.52, -0.9), (0.64, 0.85), (0.76, 0.85), (1.0, -1.0)),
        "forms": ("linear", "linear", "linear", "linear", "linear", "linear", "linear"),
    },
    "Cathedral Breath": {
        "points": ((0.0, -0.2), (0.10, 0.35), (0.26, 0.82), (0.48, 0.12), (0.70, 0.92), (1.0, 0.0)),
        "forms": ("smooth", "smooth", "smooth", "smooth", "smooth"),
    },
    "Chaos Stairs": {
        "points": ((0.0, -0.8), (0.15, -0.25), (0.30, 0.65), (0.44, -0.55), (0.60, 0.9), (0.74, -0.15), (1.0, 0.55)),
        "forms": ("linear", "linear", "linear", "linear", "linear", "linear"),
    },
}


@dataclass
class AeternaVoice:
    pitch: int
    base_freq: float
    velocity: float
    phase: float = 0.0
    age_samples: int = 0
    released: bool = False
    release_age_samples: int = 0
    preview_frames_left: int | None = None
    note_on_seq: int = 0
    release_override_samples: int | None = None
    chaos_state: float = 0.617
    micropitch_curve: list = field(default_factory=list)
    micropitch_duration: int = 0
    micropitch_elapsed: int = 0
    glide_start_freq: float = 0.0
    glide_samples: int = 0
    amp_release_level: float = 1.0
    filter_release_level: float = 1.0
    feedback_sample: float = 0.0


class AeternaEngine:
    PRESETS: Dict[str, dict] = {
        "Kathedrale": {
            "mode": "formula",
            "formula": "(0.82*sin(phase + 0.42*sin(0.5*phase)) + 0.12*sin(phase*2.0 + 0.08*env)) * (0.88 + 0.10*cos(0.125*phase + c*0.25))",
            "morph": 0.48, "chaos": 0.10, "drift": 0.14, "tone": 0.68,
            "release": 0.62, "gain": 0.50, "space": 0.52, "motion": 0.22, "cathedral": 0.58,
            "lfo1_rate": 0.20, "lfo2_rate": 0.12, "mseg_rate": 0.24,
            "mod1_source": "lfo1", "mod1_target": "morph", "mod1_amount": 0.22,
            "mod2_source": "mseg", "mod2_target": "space", "mod2_amount": 0.26,
        },
        "Schloss": {
            "mode": "spectral", "formula": DEFAULT_FORMULA,
            "morph": 0.48, "chaos": 0.10, "drift": 0.24, "tone": 0.58,
            "release": 0.42, "gain": 0.58, "space": 0.34, "motion": 0.24, "cathedral": 0.38,
            "lfo1_rate": 0.16, "lfo2_rate": 0.08, "mseg_rate": 0.18,
            "mod1_source": "lfo2", "mod1_target": "tone", "mod1_amount": 0.20,
            "mod2_source": "mseg", "mod2_target": "cathedral", "mod2_amount": 0.18,
        },
        "Terrain": {
            "mode": "terrain", "formula": DEFAULT_FORMULA,
            "morph": 0.72, "chaos": 0.22, "drift": 0.16, "tone": 0.52,
            "release": 0.36, "gain": 0.56, "space": 0.28, "motion": 0.44, "cathedral": 0.24,
            "lfo1_rate": 0.30, "lfo2_rate": 0.18, "mseg_rate": 0.28,
            "mod1_source": "lfo1", "mod1_target": "motion", "mod1_amount": 0.26,
            "mod2_source": "chaos", "mod2_target": "morph", "mod2_amount": 0.14,
        },
        "Chaos": {
            "mode": "chaos",
            "formula": "sin(phase + c*4.0*sin(phase*0.25)) * tanh(sin(phase*0.5) + 0.5*cos(phase*1.5))",
            "morph": 0.78, "chaos": 0.70, "drift": 0.22, "tone": 0.50,
            "release": 0.34, "gain": 0.48, "space": 0.22, "motion": 0.66, "cathedral": 0.18,
            "lfo1_rate": 0.34, "lfo2_rate": 0.20, "mseg_rate": 0.22,
            "mod1_source": "chaos", "mod1_target": "motion", "mod1_amount": 0.28,
            "mod2_source": "lfo1", "mod2_target": "chaos", "mod2_amount": 0.18,
        },
        "Orgel der Zukunft": {
            "mode": "formula",
            "formula": "0.86*sin(phase) + 0.18*sin(phase*2.0 + 0.10*m*sin(phase*0.25)) + 0.08*sin(phase*4.0 + d*0.5)",
            "morph": 0.46, "chaos": 0.08, "drift": 0.20, "tone": 0.74,
            "release": 0.58, "gain": 0.48, "space": 0.44, "motion": 0.24, "cathedral": 0.52,
            "lfo1_rate": 0.14, "lfo2_rate": 0.06, "mseg_rate": 0.16,
            "mod1_source": "mseg", "mod1_target": "tone", "mod1_amount": 0.22,
            "mod2_source": "lfo2", "mod2_target": "space", "mod2_amount": 0.12,
        },
        "Hofmusik": {
            "mode": "spectral", "formula": DEFAULT_FORMULA,
            "morph": 0.30, "chaos": 0.05, "drift": 0.16, "tone": 0.78,
            "release": 0.50, "gain": 0.54, "space": 0.26, "motion": 0.12, "cathedral": 0.24,
            "lfo1_rate": 0.12, "lfo2_rate": 0.10, "mseg_rate": 0.20,
            "mod1_source": "lfo2", "mod1_target": "morph", "mod1_amount": 0.12,
            "mod2_source": "mseg", "mod2_target": "tone", "mod2_amount": 0.16,
        },
        "Wolken-Chor": {
            "mode": "terrain", "formula": DEFAULT_FORMULA,
            "morph": 0.80, "chaos": 0.26, "drift": 0.14, "tone": 0.54,
            "release": 0.62, "gain": 0.46, "space": 0.50, "motion": 0.52, "cathedral": 0.46,
            "lfo1_rate": 0.18, "lfo2_rate": 0.08, "mseg_rate": 0.30,
            "mod1_source": "mseg", "mod1_target": "space", "mod1_amount": 0.30,
            "mod2_source": "lfo1", "mod2_target": "motion", "mod2_amount": 0.18,
        },
        "Experiment": {
            "mode": "chaos",
            "formula": "tanh(sin(phase*(1.0+m)) + 0.5*cos(phase*(2.0+c)) + x)",
            "morph": 0.68, "chaos": 0.74, "drift": 0.28, "tone": 0.42,
            "release": 0.28, "gain": 0.44, "space": 0.20, "motion": 0.58, "cathedral": 0.14,
            "lfo1_rate": 0.40, "lfo2_rate": 0.24, "mseg_rate": 0.26,
            "mod1_source": "chaos", "mod1_target": "chaos", "mod1_amount": 0.22,
            "mod2_source": "mseg", "mod2_target": "morph", "mod2_amount": 0.18,
        },
        "Web Chapel": {
            "mode": "formula",
            "formula": "0.84*sin(phase + 0.22*sin(phase*(1.0+m*0.4))) + 0.14*cos(phase*0.5 + env)",
            "morph": 0.50, "chaos": 0.14, "drift": 0.16, "tone": 0.70,
            "release": 0.54, "gain": 0.50, "space": 0.50, "motion": 0.24, "cathedral": 0.56,
            "lfo1_rate": 0.22, "lfo2_rate": 0.14, "mseg_rate": 0.34,
            "mod1_source": "lfo1", "mod1_target": "morph", "mod1_amount": 0.24,
            "mod2_source": "mseg", "mod2_target": "cathedral", "mod2_amount": 0.28,
        },
        "Kristall Bach": {
            "mode": "formula",
            "formula": "0.90*sin(phase + 0.06*lfo1) + 0.12*sin(phase*2.0 + 0.08*mseg) + 0.05*sin(phase*4.0 + 0.03*lfo2)",
            "morph": 0.28, "chaos": 0.03, "drift": 0.10, "tone": 0.86,
            "release": 0.64, "gain": 0.46, "space": 0.42, "motion": 0.10, "cathedral": 0.62,
            "lfo1_rate": 0.10, "lfo2_rate": 0.05, "mseg_rate": 0.12,
            "mod1_source": "mseg", "mod1_target": "tone", "mod1_amount": 0.12,
            "mod2_source": "lfo2", "mod2_target": "space", "mod2_amount": 0.10,
        },
        "Bach Glas": {
            "mode": "formula",
            "formula": "0.92*sin(phase + 0.04*sin(phase*0.5 + 0.05*lfo1)) + 0.10*sin(phase*2.0 + 0.04*mseg) + 0.03*cos(phase*3.0 + env*0.2)",
            "morph": 0.22, "chaos": 0.02, "drift": 0.08, "tone": 0.90,
            "release": 0.68, "gain": 0.44, "space": 0.46, "motion": 0.08, "cathedral": 0.66,
            "lfo1_rate": 0.08, "lfo2_rate": 0.04, "mseg_rate": 0.10,
            "mod1_source": "mseg", "mod1_target": "tone", "mod1_amount": 0.10,
            "mod2_source": "lfo2", "mod2_target": "space", "mod2_amount": 0.08,
        },
        "Celesta Chapel": {
            "mode": "spectral", "formula": DEFAULT_FORMULA,
            "morph": 0.26, "chaos": 0.04, "drift": 0.12, "tone": 0.88,
            "release": 0.52, "gain": 0.48, "space": 0.40, "motion": 0.10, "cathedral": 0.54,
            "lfo1_rate": 0.10, "lfo2_rate": 0.06, "mseg_rate": 0.14,
            "mod1_source": "lfo2", "mod1_target": "tone", "mod1_amount": 0.10,
            "mod2_source": "mseg", "mod2_target": "space", "mod2_amount": 0.14,
        },
        "Choral Crystal": {
            "mode": "terrain", "formula": DEFAULT_FORMULA,
            "morph": 0.38, "chaos": 0.08, "drift": 0.10, "tone": 0.82,
            "release": 0.72, "gain": 0.44, "space": 0.58, "motion": 0.18, "cathedral": 0.62,
            "lfo1_rate": 0.12, "lfo2_rate": 0.05, "mseg_rate": 0.18,
            "mod1_source": "mseg", "mod1_target": "space", "mod1_amount": 0.18,
            "mod2_source": "lfo1", "mod2_target": "motion", "mod2_amount": 0.10,
        },
        "Abendmanual": {
            "mode": "formula",
            "formula": "0.88*sin(phase) + 0.11*sin(phase*2.0 + 0.03*lfo2) + 0.04*cos(phase*0.5 + 0.1*env)",
            "morph": 0.18, "chaos": 0.02, "drift": 0.06, "tone": 0.84,
            "release": 0.74, "gain": 0.42, "space": 0.48, "motion": 0.06, "cathedral": 0.70,
            "lfo1_rate": 0.06, "lfo2_rate": 0.03, "mseg_rate": 0.08,
            "mod1_source": "mseg", "mod1_target": "cathedral", "mod1_amount": 0.10,
            "mod2_source": "lfo2", "mod2_target": "space", "mod2_amount": 0.06,
        },
        "Wavetable Pad": {
            "mode": "wavetable", "formula": DEFAULT_FORMULA,
            "wt_position": 0.35, "wt_table_name": "Basic (Sine→Saw)",
            "morph": 0.40, "chaos": 0.06, "drift": 0.12, "tone": 0.72,
            "release": 0.58, "gain": 0.50, "space": 0.44, "motion": 0.18, "cathedral": 0.48,
            "lfo1_rate": 0.16, "lfo2_rate": 0.08, "mseg_rate": 0.20,
            "mod1_source": "lfo1", "mod1_target": "wt_position", "mod1_amount": 0.24,
            "mod2_source": "mseg", "mod2_target": "space", "mod2_amount": 0.18,
        },
        "Wavetable Lead": {
            "mode": "wavetable", "formula": DEFAULT_FORMULA,
            "wt_position": 0.60, "wt_table_name": "Harmonic Sweep",
            "morph": 0.55, "chaos": 0.10, "drift": 0.08, "tone": 0.80,
            "release": 0.30, "gain": 0.54, "space": 0.22, "motion": 0.28, "cathedral": 0.18,
            "lfo1_rate": 0.28, "lfo2_rate": 0.12, "mseg_rate": 0.24,
            "mod1_source": "lfo1", "mod1_target": "wt_position", "mod1_amount": 0.16,
            "mod2_source": "mseg", "mod2_target": "tone", "mod2_amount": 0.12,
        },
        "Wavetable Choir": {
            "mode": "wavetable", "formula": DEFAULT_FORMULA,
            "wt_position": 0.25, "wt_table_name": "Formant (Vowels)",
            "morph": 0.50, "chaos": 0.08, "drift": 0.14, "tone": 0.66,
            "release": 0.64, "gain": 0.48, "space": 0.52, "motion": 0.22, "cathedral": 0.54,
            "lfo1_rate": 0.14, "lfo2_rate": 0.06, "mseg_rate": 0.18,
            "mod1_source": "mseg", "mod1_target": "wt_position", "mod1_amount": 0.30,
            "mod2_source": "lfo2", "mod2_target": "cathedral", "mod2_amount": 0.16,
        },
    }

    def __init__(self, target_sr: int = 48000):
        self.target_sr = int(target_sr or 48000)
        self._lock = threading.RLock()
        self._voices: List[AeternaVoice] = []
        self._seq = 0
        self._formula_ok = True
        self._params: Dict[str, Any] = {
            "mode": "formula",
            "formula": DEFAULT_FORMULA,
            "morph": 0.46,
            "chaos": 0.10,
            "drift": 0.14,
            "tone": 0.70,
            "release": 0.52,
            "gain": 0.50,
            "space": 0.36,
            "motion": 0.18,
            "cathedral": 0.48,
            "attack": 0.04,
            "pan": 0.50,
            "glide": 0.06,
            "stereo_spread": 0.34,
            "retrigger": 1.00,
            "unison_mix": 0.12,
            "unison_detune": 0.18,
            "unison_voices": "2",
            "sub_level": 0.10,
            "sub_octave": "-1",
            "noise_level": 0.04,
            "noise_color": 0.34,
            "pitch": 0.50,
            "shape": 0.42,
            "pulse_width": 0.50,
            "drive": 0.28,
            "feedback": 0.08,
            "aeg_attack": 0.10,
            "aeg_decay": 0.28,
            "aeg_sustain": 0.78,
            "aeg_release": 0.46,
            "feg_attack": 0.04,
            "feg_decay": 0.22,
            "feg_sustain": 0.58,
            "feg_release": 0.34,
            "feg_amount": 0.26,
            "filter_cutoff": 0.68,
            "filter_resonance": 0.18,
            "filter_type": "LP 24",
            "unison_mix": 0.0,
            "unison_detune": 0.12,
            "unison_voices": "1",
            "sub_level": 0.0,
            "sub_octave": "-1",
            "noise_level": 0.0,
            "noise_color": 0.30,
            "lfo1_rate": 0.22,
            "lfo2_rate": 0.10,
            "lfo3_rate": 0.15,
            "lfo4_rate": 0.08,
            "mseg_rate": 0.24,
            "mod1_source": "lfo1",
            "mod1_target": "morph",
            "mod1_amount": 0.20,
            "mod1_polarity": "plus",
            "mod2_source": "mseg",
            "mod2_target": "space",
            "mod2_amount": 0.22,
            "mod2_polarity": "plus",
        }
        # Initialize mod slots 3-8 as "off" (backward compatible)
        for i in range(3, MAX_MOD_SLOTS + 1):
            self._params.setdefault(f"mod{i}_source", "off")
            self._params.setdefault(f"mod{i}_target", "off")
            self._params.setdefault(f"mod{i}_amount", 0.0)
            self._params.setdefault(f"mod{i}_polarity", "plus")
        self._preset_name = "Kathedrale"
        self._preset_metadata: Dict[str, Any] = {"category": "sakral", "character": "breit", "note": "weite Hallräume und ruhige Bewegung", "tags": ["sakral", "weit"], "favorite": False}
        self._delay_len = max(256, int(self.target_sr * 0.17))
        self._delay_l = np.zeros(self._delay_len, dtype=np.float32)
        self._delay_r = np.zeros(self._delay_len, dtype=np.float32)
        self._delay_pos = 0
        self._scope = np.zeros(256, dtype=np.float32)
        self._filter_state = {
            "l1_ic1": 0.0, "l1_ic2": 0.0, "r1_ic1": 0.0, "r1_ic2": 0.0,
            "l2_ic1": 0.0, "l2_ic2": 0.0, "r2_ic1": 0.0, "r2_ic2": 0.0,
        }
        self._comb_len = 2048
        self._comb_l = np.zeros(self._comb_len, dtype=np.float32)
        self._comb_r = np.zeros(self._comb_len, dtype=np.float32)
        self._comb_pos = 0
        self._mseg_points = [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
        self._mseg_segment_forms = list(DEFAULT_MSEG_SEGMENT_FORMS)
        self._mseg_history: list[dict] = []
        self._mseg_future: list[dict] = []
        self._mseg_history_limit = 48
        # Wavetable subsystem (v0.0.20.657)
        self._wt_bank = WavetableBank()
        self._wt_unison = UnisonEngine()
        self._params["wt_position"] = 0.0
        self._params["wt_table_name"] = "Basic (Sine→Saw)"
        self._params["wt_unison_mode"] = "Off"
        self._params["wt_unison_voices"] = 0.125  # 1..16 mapped 0..1 → int(v*15)+1
        self._params["wt_unison_detune"] = 0.20
        self._params["wt_unison_spread"] = 0.50
        self._params["wt_unison_width"] = 0.50
        self.apply_preset(self._preset_name)

    # ---------- params / preset
    def get_mod_sources(self) -> tuple[str, ...]:
        return MOD_SOURCE_KEYS

    def get_mod_targets(self) -> tuple[str, ...]:
        return MOD_TARGET_KEYS

    def get_mseg_shape_preset_names(self) -> tuple[str, ...]:
        return tuple(MSEG_SHAPE_PRESETS.keys())

    def apply_mseg_shape_preset(self, name: str, save_history: bool = True) -> bool:
        spec = MSEG_SHAPE_PRESETS.get(str(name or ""))
        if not isinstance(spec, dict):
            return False
        points = spec.get("points")
        forms = spec.get("forms")
        with self._lock:
            if save_history:
                self._push_mseg_history_locked()
            self._mseg_points = self._sanitize_mseg_points(points)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(forms, len(self._mseg_points) - 1)
        return True

    def set_param(self, key: str, value: Any) -> None:
        with self._lock:
            if key in _STRING_PARAMS:
                txt = str(value or "")
                if key.endswith("_source"):
                    txt = txt if txt in MOD_SOURCE_KEYS else "off"
                elif key.endswith("_target"):
                    txt = txt if txt in MOD_TARGET_KEYS else "off"
                elif key.endswith("_polarity"):
                    txt = "minus" if txt in {"minus", "-", "−", "inv", "invert"} else "plus"
                elif key == "mode":
                    txt = txt if txt in _VALID_MODES else "formula"
                elif key == "filter_type":
                    txt = txt if txt in {"LP 12", "LP 24", "HP 12", "BP", "Notch", "Comb+"} else "LP 24"
                elif key == "unison_voices":
                    txt = txt if txt in {"1", "2", "4", "6"} else "2"
                elif key == "sub_octave":
                    txt = txt if txt in {"-1", "-2"} else "-1"
                elif key == "wt_table_name":
                    txt = txt[:64]  # limit length
                elif key == "wt_unison_mode":
                    txt = txt if txt in {"Off", "Classic", "Supersaw", "Hyper"} else "Off"
                self._params[key] = txt
                if key == "formula":
                    self._formula_ok = self._validate_formula(self._params[key])
                    if hasattr(self, '_formula_cache'):
                        self._formula_cache.clear()
                return
            try:
                fv = float(value)
            except Exception:
                return
            self._params[key] = max(0.0, min(1.0, fv))

    def get_param(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._params.get(key, default)

    def get_formula_status(self) -> bool:
        with self._lock:
            return bool(self._formula_ok)

    def get_preset_metadata(self) -> dict:
        with self._lock:
            return dict(self._preset_metadata)

    def set_preset_metadata(self, metadata: dict | None) -> None:
        meta = metadata if isinstance(metadata, dict) else {}
        tags_raw = meta.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if str(t).strip()]
        elif isinstance(tags_raw, (list, tuple, set)):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            low = tag.lower()
            if low in seen:
                continue
            seen.add(low)
            deduped.append(tag[:24])
            if len(deduped) >= 8:
                break
        with self._lock:
            self._preset_metadata = {
                "category": str(meta.get("category") or "experimentell"),
                "character": str(meta.get("character") or "weich"),
                "note": str(meta.get("note") or "").strip(),
                "tags": deduped,
                "favorite": bool(meta.get("favorite", False)),
            }

    def apply_init_patch(self) -> None:
        init_params = {
            "mode": "formula",
            "formula": DEFAULT_FORMULA,
            "morph": 0.42,
            "chaos": 0.10,
            "drift": 0.14,
            "tone": 0.68,
            "release": 0.52,
            "gain": 0.48,
            "space": 0.34,
            "motion": 0.16,
            "cathedral": 0.42,
            "filter_cutoff": 0.68,
            "filter_resonance": 0.18,
            "filter_type": "LP 24",
            "unison_mix": 0.0,
            "unison_detune": 0.12,
            "unison_voices": "1",
            "sub_level": 0.0,
            "sub_octave": "-1",
            "noise_level": 0.0,
            "noise_color": 0.30,
            "pitch": 0.50,
            "shape": 0.42,
            "pulse_width": 0.50,
            "drive": 0.22,
            "feedback": 0.04,
            "lfo1_rate": 0.20,
            "lfo2_rate": 0.12,
            "mseg_rate": 0.24,
            "mod1_polarity": "plus",
            "mod1_source": "off",
            "mod1_target": "off",
            "mod1_amount": 0.0,
            "mod2_polarity": "plus",
            "mod2_source": "off",
            "mod2_target": "off",
            "mod2_amount": 0.0,
        }
        with self._lock:
            for k, v in init_params.items():
                if k in _STRING_PARAMS:
                    self._params[k] = str(v)
                else:
                    self._params[k] = max(0.0, min(1.0, float(v)))
            self._preset_name = "Init Patch"
            self._formula_ok = self._validate_formula(str(self._params.get("formula") or DEFAULT_FORMULA))
            self._mseg_points = [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
            self._mseg_segment_forms = list(DEFAULT_MSEG_SEGMENT_FORMS)
            self._mseg_history.clear()
            self._mseg_future.clear()

    def restore_preset_defaults(self, name: str | None = None) -> str:
        target = str(name or self.get_preset_name() or "").strip()
        if not target or target not in self.PRESETS:
            target = "Kathedrale"
        self.apply_preset(target)
        with self._lock:
            self._preset_name = str(target)
        return str(target)

    def get_automation_groups(self) -> list[dict]:
        groups = [
            {"title": "Klang", "keys": ["morph", "tone", "gain", "release"]},
            {"title": "Raum/Bewegung", "keys": ["space", "motion", "cathedral", "drift"]},
            {"title": "Voice", "keys": ["pan", "glide", "stereo_spread"]},
            {"title": "AEG", "keys": ["aeg_attack", "aeg_decay", "aeg_sustain", "aeg_release"]},
            {"title": "FEG", "keys": ["feg_attack", "feg_decay", "feg_sustain", "feg_release", "feg_amount"]},
            {"title": "Modulation", "keys": ["chaos", "lfo1_rate", "lfo2_rate", "mseg_rate"]},
            {"title": "Filter", "keys": ["filter_cutoff", "filter_resonance"]},
            {"title": "Layer", "keys": ["unison_mix", "unison_detune", "sub_level", "noise_level", "noise_color"]},
            {"title": "Pitch/Timbre", "keys": ["pitch", "shape", "pulse_width"]},
            {"title": "Drive/Feedback", "keys": ["drive", "feedback"]},
            {"title": "Wavetable", "keys": ["wt_position", "wt_unison_detune", "wt_unison_spread", "wt_unison_width"]},
            {"title": "Web", "keys": ["mod1_amount", "mod2_amount"]},
        ]
        out = []
        with self._lock:
            params = dict(self._params)
        for grp in groups:
            entries = []
            for key in grp["keys"]:
                try:
                    entries.append({"key": key, "value": float(params.get(key, 0.0) or 0.0)})
                except Exception:
                    entries.append({"key": key, "value": 0.0})
            out.append({"title": grp["title"], "entries": entries})
        return out

    def apply_preset(self, name: str) -> None:
        spec = dict(self.PRESETS.get(str(name or ""), {}))
        if not spec:
            return
        with self._lock:
            for k, v in spec.items():
                if k in _STRING_PARAMS:
                    self.set_param(k, v)
                else:
                    try:
                        self._params[k] = max(0.0, min(1.0, float(v)))
                    except Exception:
                        pass
            self._preset_name = str(name)
            self._formula_ok = self._validate_formula(str(self._params.get("formula") or DEFAULT_FORMULA))
            self._mseg_history.clear()
            self._mseg_future.clear()
            self._mseg_history.clear()
            self._mseg_future.clear()
            # Load wavetable if preset uses wavetable mode
            if str(self._params.get("mode")) == "wavetable":
                tname = str(self._params.get("wt_table_name", "Basic (Sine→Saw)") or "Basic (Sine→Saw)")
                if tname in BUILTIN_WAVETABLES:
                    self._wt_bank.load_builtin(tname)

    def set_preset_name(self, name: str) -> None:
        with self._lock:
            self._preset_name = str(name or "")

    def get_preset_name(self) -> str:
        with self._lock:
            return str(self._preset_name)

    def get_mseg_points(self) -> list[tuple[float, float]]:
        with self._lock:
            return [tuple(pt) for pt in self._mseg_points]

    def get_mseg_segment_forms(self) -> list[str]:
        with self._lock:
            return list(self._mseg_segment_forms)

    def set_mseg_points(self, points, save_history: bool = True) -> None:
        with self._lock:
            if save_history:
                self._push_mseg_history_locked()
            self._mseg_points = self._sanitize_mseg_points(points)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def set_mseg_segment_forms(self, forms, save_history: bool = True) -> None:
        with self._lock:
            if save_history:
                self._push_mseg_history_locked()
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(forms, len(self._mseg_points) - 1)

    def reset_mseg_points(self, save_history: bool = True) -> None:
        with self._lock:
            if save_history:
                self._push_mseg_history_locked()
            self._mseg_points = [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
            self._mseg_segment_forms = list(DEFAULT_MSEG_SEGMENT_FORMS)

    def invert_mseg(self) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            self._mseg_points = [(float(x), max(-1.0, min(1.0, -float(y)))) for x, y in self._mseg_points]

    def mirror_mseg(self) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = [(1.0 - float(x), float(y)) for x, y in self._mseg_points]
            pts.sort(key=lambda it: it[0])
            self._mseg_points = self._sanitize_mseg_points(pts)
            self._mseg_segment_forms = list(reversed(self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)))

    def normalize_mseg(self) -> None:
        with self._lock:
            if not self._mseg_points:
                return
            self._push_mseg_history_locked()
            ys = [float(y) for _, y in self._mseg_points]
            peak = max(max(abs(v) for v in ys), 1e-6)
            scale = 1.0 / peak
            self._mseg_points = [(float(x), max(-1.0, min(1.0, float(y) * scale))) for x, y in self._mseg_points]

    def stretch_mseg(self, factor: float = 1.15) -> None:
        self._scale_mseg_time(float(factor or 1.15))

    def compress_mseg(self, factor: float = 0.85) -> None:
        self._scale_mseg_time(float(factor or 0.85))

    def snap_mseg_x(self, divisions: int = 16) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            divisions = int(divisions or 16)
            divisions = max(2, min(128, divisions))
            out = [pts[0]]
            for idx, (x, y) in enumerate(pts[1:-1], start=1):
                nx = round(float(x) * divisions) / float(divisions)
                prev_x = float(out[-1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, nx))
                out.append((nx, float(y)))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def quantize_mseg_y(self, levels: int = 9) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            levels = int(levels or 9)
            levels = max(2, min(65, levels))
            out = []
            for x, y in pts:
                ny = round(((float(y) + 1.0) * 0.5) * (levels - 1)) / float(levels - 1)
                ny = (ny * 2.0) - 1.0
                out.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def smooth_mseg(self, amount: float = 0.5, passes: int = 1) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            amount = max(0.0, min(1.0, float(amount or 0.5)))
            passes = max(1, min(4, int(passes or 1)))
            work = [tuple(pt) for pt in pts]
            for _ in range(passes):
                nxt = [work[0]]
                for idx in range(1, len(work) - 1):
                    x, y = work[idx]
                    avg = (float(work[idx - 1][1]) + float(y) + float(work[idx + 1][1])) / 3.0
                    ny = (float(y) * (1.0 - amount)) + (avg * amount)
                    nxt.append((float(x), max(-1.0, min(1.0, ny))))
                nxt.append(work[-1])
                work = nxt
            self._mseg_points = self._sanitize_mseg_points(work)

    def double_mseg(self) -> None:
        self._remap_mseg_time(lambda pos: np.mod(np.asarray(pos, dtype=np.float64) * 2.0, 1.0), preserve_last=True)

    def halve_mseg(self) -> None:
        self._remap_mseg_time(lambda pos: np.asarray(pos, dtype=np.float64) * 0.5, preserve_last=True)

    def bias_mseg(self, amount: float = 0.15) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            amt = max(-1.0, min(1.0, float(amount or 0.0)))
            out = []
            for idx, (x, y) in enumerate(pts):
                ny = max(-1.0, min(1.0, float(y) + amt))
                if idx == 0 and len(pts) > 1:
                    ny = max(-1.0, min(1.0, ny))
                out.append((float(x), ny))
            self._mseg_points = self._sanitize_mseg_points(out)

    def morph_mseg_to_shape(self, name: str, amount: float = 0.5) -> bool:
        spec = MSEG_SHAPE_PRESETS.get(str(name or ""))
        if not isinstance(spec, dict):
            return False
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return False
            amt = max(0.0, min(1.0, float(amount or 0.5)))
            xs = np.asarray([float(x) for x, _ in pts], dtype=np.float64)
            current = self._evaluate_mseg_positions(xs, pts, self._mseg_segment_forms)
            target_points = self._sanitize_mseg_points(spec.get("points"))
            target_forms = self._sanitize_mseg_segment_forms(spec.get("forms"), len(target_points) - 1)
            target = self._evaluate_mseg_positions(xs, target_points, target_forms)
            blend = (current * (1.0 - amt)) + (target * amt)
            out = [(float(x), max(-1.0, min(1.0, float(y)))) for (x, _), y in zip(pts, blend.tolist())]
            self._mseg_points = self._sanitize_mseg_points(out)
            if amt >= 0.999:
                self._mseg_segment_forms = self._sanitize_mseg_segment_forms(target_forms, len(self._mseg_points) - 1)
        return True

    def _scale_mseg_time(self, factor: float) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            factor = max(0.25, min(2.0, float(factor)))
            out = [pts[0]]
            for idx, (x, y) in enumerate(pts[1:-1], start=1):
                nx = 0.5 + (float(x) - 0.5) * factor
                prev_x = float(out[-1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, nx))
                out.append((nx, max(-1.0, min(1.0, float(y)))))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def _remap_mseg_time(self, pos_fn, preserve_last: bool = True) -> None:
        with self._lock:
            self._push_mseg_history_locked()
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            xs = np.asarray([float(x) for x, _ in pts], dtype=np.float64)
            mapped = np.asarray(pos_fn(xs), dtype=np.float64).reshape(-1)
            if mapped.shape[0] != xs.shape[0]:
                return
            if preserve_last and mapped.size:
                mapped[-1] = 1.0
            vals = self._evaluate_mseg_positions(np.clip(mapped, 0.0, 1.0), pts, self._mseg_segment_forms)
            out = [(float(x), max(-1.0, min(1.0, float(y)))) for (x, _), y in zip(pts, vals.tolist())]
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)


    def randomize_mseg(self, amount: float = 0.35, seed: int | None = None) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(0.0, min(1.0, float(amount or 0.35)))
            rng = np.random.default_rng(seed)
            out = []
            for idx, (x, y) in enumerate(pts):
                if idx == 0 or idx == len(pts) - 1:
                    out.append((float(x), float(y)))
                    continue
                target = float(rng.uniform(-1.0, 1.0))
                ny = (float(y) * (1.0 - amt)) + (target * amt)
                out.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def jitter_mseg(self, x_amount: float = 0.04, y_amount: float = 0.12, seed: int | None = None) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            self._push_mseg_history_locked()
            xa = max(0.0, min(0.12, float(x_amount or 0.04)))
            ya = max(0.0, min(0.35, float(y_amount or 0.12)))
            rng = np.random.default_rng(seed)
            out = [pts[0]]
            for idx, (x, y) in enumerate(pts[1:-1], start=1):
                nx = float(x) + float(rng.uniform(-xa, xa))
                ny = float(y) + float(rng.uniform(-ya, ya))
                prev_x = float(out[-1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, nx))
                out.append((nx, max(-1.0, min(1.0, ny))))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def humanize_mseg(self, strength: float = 0.18, seed: int | None = None) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            self._push_mseg_history_locked()
            strength = max(0.0, min(0.45, float(strength or 0.18)))
            rng = np.random.default_rng(seed)
            out = [pts[0]]
            for idx, (x, y) in enumerate(pts[1:-1], start=1):
                nx = float(x) + float(rng.uniform(-strength * 0.15, strength * 0.15))
                ny = float(y) + float(rng.uniform(-strength, strength))
                prev_x = float(out[-1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, nx))
                out.append((nx, max(-1.0, min(1.0, ny))))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def recenter_mseg(self) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            ys = [float(y) for _, y in pts[1:-1]] if len(pts) > 2 else [float(pts[0][1]), float(pts[-1][1])]
            if not ys:
                return
            mean_y = sum(ys) / float(len(ys))
            out = []
            for idx, (x, y) in enumerate(pts):
                ny = float(y) - mean_y
                if idx in (0, len(pts) - 1):
                    ny = float(y) - (mean_y * 0.5)
                out.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def flatten_peaks_mseg(self, amount: float = 0.28) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amount = max(0.0, min(0.9, float(amount or 0.28)))
            drive = 1.0 + amount * 2.5
            mix = 0.35 + amount * 0.45
            out = []
            for x, y in pts:
                yy = float(y)
                shaped = math.tanh(yy * drive) / max(1e-9, math.tanh(drive))
                ny = (yy * (1.0 - mix)) + (shaped * mix)
                out.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def tilt_mseg(self, amount: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(-0.9, min(0.9, float(amount or 0.0)))
            out = []
            for x, y in pts:
                bias = (float(x) - 0.5) * 2.0 * amt
                ny = max(-1.0, min(1.0, float(y) + bias))
                out.append((float(x), ny))
            self._mseg_points = self._sanitize_mseg_points(out)

    def skew_mseg(self, amount: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            self._push_mseg_history_locked()
            amt = max(-0.9, min(0.9, float(amount or 0.0)))
            power = 1.0 - amt if amt < 0.0 else 1.0 / max(0.15, 1.0 - amt)
            out = [pts[0]]
            for idx, (x, y) in enumerate(pts[1:-1], start=1):
                nx = float(np.clip(float(x) ** power, 0.0, 1.0))
                prev_x = float(out[-1][0]) + 0.02
                next_x = float(pts[idx + 1][0]) - 0.02
                nx = max(prev_x, min(next_x, nx))
                out.append((nx, max(-1.0, min(1.0, float(y)))))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def curvature_mseg(self, amount: float = 0.22) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(-0.9, min(0.9, float(amount or 0.0)))
            gamma = 1.0 + (abs(amt) * 2.5)
            out = []
            for x, y in pts:
                yn = (float(y) + 1.0) * 0.5
                if amt >= 0.0:
                    shaped = yn ** gamma
                else:
                    shaped = 1.0 - ((1.0 - yn) ** gamma)
                ny = max(-1.0, min(1.0, (shaped * 2.0) - 1.0))
                out.append((float(x), ny))
            self._mseg_points = self._sanitize_mseg_points(out)

    def center_pinch_mseg(self, amount: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(-0.9, min(0.9, float(amount or 0.0)))
            out = []
            for x, y in pts:
                center_weight = 1.0 - min(1.0, abs((float(x) - 0.5) * 2.0))
                delta = center_weight * amt * 0.6
                ny = max(-1.0, min(1.0, float(y) * (1.0 - delta))) if amt >= 0.0 else max(-1.0, min(1.0, float(y) * (1.0 + abs(delta))))
                out.append((float(x), ny))
            self._mseg_points = self._sanitize_mseg_points(out)

    def range_clamp_mseg(self, limit: float = 0.8) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            lim = max(0.1, min(1.0, float(limit or 0.8)))
            self._mseg_points = [(float(x), max(-lim, min(lim, float(y)))) for x, y in pts]

    def deadband_mseg(self, threshold: float = 0.1) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            thr = max(0.0, min(0.9, float(threshold or 0.1)))
            out = []
            for x, y in pts:
                yy = float(y)
                if abs(yy) <= thr:
                    ny = 0.0
                else:
                    sign = -1.0 if yy < 0.0 else 1.0
                    scaled = (abs(yy) - thr) / max(1e-9, 1.0 - thr)
                    ny = sign * scaled
                out.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def micro_smooth_mseg(self, amount: float = 0.3) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 3:
                return
            self._push_mseg_history_locked()
            amt = max(0.0, min(1.0, float(amount or 0.3)))
            center_w = 0.14 + (amt * 0.18)
            edge_w = (1.0 - center_w) * 0.5
            out = [pts[0]]
            for idx in range(1, len(pts) - 1):
                x, y = pts[idx]
                prev_y = float(pts[idx - 1][1])
                cur_y = float(y)
                next_y = float(pts[idx + 1][1])
                avg = (prev_y * edge_w) + (cur_y * center_w) + (next_y * edge_w)
                ny = (cur_y * (1.0 - amt)) + (avg * amt)
                out.append((float(x), max(-1.0, min(1.0, ny))))
            out.append(pts[-1])
            self._mseg_points = self._sanitize_mseg_points(out)


    def softclip_drive_mseg(self, drive: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            drv = max(0.0, min(1.0, float(drive or 0.2)))
            gain = 1.0 + (drv * 3.0)
            shaped = []
            norm = math.tanh(gain) if gain > 0.0 else 1.0
            for x, y in pts:
                yy = float(y)
                ny = math.tanh(yy * gain) / max(1e-9, norm)
                shaped.append((float(x), max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(shaped)

    def center_flatten_mseg(self, amount: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(0.0, min(1.0, float(amount or 0.2)))
            out = []
            for x, y in pts:
                xx = float(x)
                yy = float(y)
                center_weight = 1.0 - min(1.0, abs((xx - 0.5) * 2.0))
                scale = 1.0 - (center_weight * amt * 0.85)
                ny = yy * scale
                out.append((xx, max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)

    def edge_boost_mseg(self, amount: float = 0.2) -> None:
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return
            self._push_mseg_history_locked()
            amt = max(0.0, min(1.0, float(amount or 0.2)))
            out = []
            for x, y in pts:
                xx = float(x)
                yy = float(y)
                edge_weight = min(1.0, abs((xx - 0.5) * 2.0))
                scale = 1.0 + (edge_weight * amt * 0.75)
                ny = yy * scale
                out.append((xx, max(-1.0, min(1.0, ny))))
            self._mseg_points = self._sanitize_mseg_points(out)


    def phase_rotate_mseg(self, amount: float = 0.125) -> None:
        amount = max(-0.95, min(0.95, float(amount)))
        if abs(amount) < 1e-6:
            return
        def _map(x: float) -> float:
            return (float(x) + amount) % 1.0
        with self._lock:
            self._push_mseg_history_locked()
            rotated = [(_map(float(x)), float(y)) for x, y in self._mseg_points]
            rotated.sort(key=lambda it: float(it[0]))
            if not rotated:
                return
            ys = [float(y) for _x, y in rotated]
            xs = [float(x) for x, _y in rotated]
            xs[0] = 0.0
            xs[-1] = 1.0
            for i in range(1, len(xs) - 1):
                xs[i] = max(xs[i - 1] + 0.02, min(xs[i + 1] - 0.02 if i + 1 < len(xs) else 0.98, xs[i]))
            self._mseg_points = self._sanitize_mseg_points(list(zip(xs, ys)))
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(self._mseg_segment_forms, len(self._mseg_points) - 1)

    def symmetry_mseg(self, amount: float = 0.2) -> None:
        amount = max(-1.0, min(1.0, float(amount)))
        with self._lock:
            self._push_mseg_history_locked()
            pts = []
            for x, y in self._mseg_points:
                xf = float(x)
                yf = float(y)
                mirror_y = float(self._evaluate_mseg_positions(np.asarray([1.0 - xf], dtype=np.float32))[0])
                if amount >= 0.0:
                    out_y = yf * (1.0 - amount) + mirror_y * amount
                else:
                    anti = -mirror_y
                    out_y = yf * (1.0 - abs(amount)) + anti * abs(amount)
                pts.append((xf, max(-1.0, min(1.0, out_y))))
            self._mseg_points = self._sanitize_mseg_points(pts)

    def slope_limit_mseg(self, limit: float = 0.6) -> None:
        limit = max(0.05, min(2.0, float(limit)))
        with self._lock:
            self._push_mseg_history_locked()
            pts = [(float(x), float(y)) for x, y in self._mseg_points]
            if len(pts) < 2:
                return
            out = [pts[0]]
            prev_x, prev_y = pts[0]
            for x, y in pts[1:]:
                dx = max(0.001, float(x) - prev_x)
                max_delta = limit * dx * 2.0
                y = max(prev_y - max_delta, min(prev_y + max_delta, float(y)))
                out.append((float(x), max(-1.0, min(1.0, y))))
                prev_x, prev_y = out[-1]
            self._mseg_points = self._sanitize_mseg_points(out)

    def blend_mseg_shapes(self, name_a: str, name_b: str, amount: float = 0.5) -> bool:
        spec_a = MSEG_SHAPE_PRESETS.get(str(name_a or ""))
        spec_b = MSEG_SHAPE_PRESETS.get(str(name_b or ""))
        if not isinstance(spec_a, dict) or not isinstance(spec_b, dict):
            return False
        with self._lock:
            pts = list(self._mseg_points)
            if len(pts) < 2:
                return False
            self._push_mseg_history_locked()
            amt = max(0.0, min(1.0, float(amount or 0.5)))
            xs = np.asarray([float(x) for x, _ in pts], dtype=np.float64)
            pts_a = self._sanitize_mseg_points(spec_a.get("points"))
            pts_b = self._sanitize_mseg_points(spec_b.get("points"))
            forms_a = self._sanitize_mseg_segment_forms(spec_a.get("forms"), len(pts_a) - 1)
            forms_b = self._sanitize_mseg_segment_forms(spec_b.get("forms"), len(pts_b) - 1)
            vals_a = self._evaluate_mseg_positions(xs, pts_a, forms_a)
            vals_b = self._evaluate_mseg_positions(xs, pts_b, forms_b)
            blend = (vals_a * (1.0 - amt)) + (vals_b * amt)
            self._mseg_points = self._sanitize_mseg_points([(float(x), max(-1.0, min(1.0, float(y)))) for (x, _), y in zip(pts, blend.tolist())])
            if amt <= 0.001:
                self._mseg_segment_forms = self._sanitize_mseg_segment_forms(forms_a, len(self._mseg_points) - 1)
            elif amt >= 0.999:
                self._mseg_segment_forms = self._sanitize_mseg_segment_forms(forms_b, len(self._mseg_points) - 1)
        return True

    def push_mseg_history(self) -> None:
        with self._lock:
            self._push_mseg_history_locked()

    def undo_mseg(self) -> bool:
        with self._lock:
            if not self._mseg_history:
                return False
            self._mseg_future.append(self._capture_mseg_state_locked())
            state = self._mseg_history.pop()
            self._restore_mseg_state_locked(state)
            return True

    def redo_mseg(self) -> bool:
        with self._lock:
            if not self._mseg_future:
                return False
            self._mseg_history.append(self._capture_mseg_state_locked())
            state = self._mseg_future.pop()
            self._restore_mseg_state_locked(state)
            return True

    def get_mseg_history_status(self) -> dict:
        with self._lock:
            return {"undo": len(self._mseg_history), "redo": len(self._mseg_future)}

    def _capture_mseg_state_locked(self) -> dict:
        return {
            "points": [tuple(pt) for pt in self._mseg_points],
            "forms": list(self._mseg_segment_forms),
        }

    def _restore_mseg_state_locked(self, state: dict) -> None:
        pts = state.get("points") if isinstance(state, dict) else None
        forms = state.get("forms") if isinstance(state, dict) else None
        self._mseg_points = self._sanitize_mseg_points(pts)
        self._mseg_segment_forms = self._sanitize_mseg_segment_forms(forms, len(self._mseg_points) - 1)

    def _push_mseg_history_locked(self) -> None:
        snap = self._capture_mseg_state_locked()
        if self._mseg_history and self._mseg_history[-1] == snap:
            return
        self._mseg_history.append(snap)
        if len(self._mseg_history) > int(self._mseg_history_limit):
            self._mseg_history = self._mseg_history[-int(self._mseg_history_limit):]
        self._mseg_future.clear()

    def _sanitize_mseg_segment_forms(self, forms, expected_count: int | None = None) -> list[str]:
        count = int(max(1, expected_count if expected_count is not None else (len(self._mseg_points) - 1)))
        cleaned: list[str] = []
        if isinstance(forms, (list, tuple)):
            for item in forms:
                txt = str(item or "linear").lower()
                cleaned.append(txt if txt in MSEG_SEGMENT_FORMS else "linear")
        while len(cleaned) < count:
            default_idx = min(len(cleaned), max(0, len(DEFAULT_MSEG_SEGMENT_FORMS) - 1))
            cleaned.append(DEFAULT_MSEG_SEGMENT_FORMS[default_idx] if default_idx < len(DEFAULT_MSEG_SEGMENT_FORMS) else "linear")
        if len(cleaned) > count:
            cleaned = cleaned[:count]
        return cleaned

    def _sanitize_mseg_points(self, points) -> list[tuple[float, float]]:
        cleaned: list[tuple[float, float]] = []
        if isinstance(points, (list, tuple)):
            for item in points:
                try:
                    if isinstance(item, dict):
                        x = float(item.get("x", 0.0))
                        y = float(item.get("y", 0.0))
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        x = float(item[0])
                        y = float(item[1])
                    else:
                        continue
                    cleaned.append((max(0.0, min(1.0, x)), max(-1.0, min(1.0, y))))
                except Exception:
                    continue
        if len(cleaned) < 2:
            return [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
        cleaned.sort(key=lambda it: it[0])
        xs_used: list[float] = []
        deduped: list[tuple[float, float]] = []
        for x, y in cleaned:
            if xs_used and abs(x - xs_used[-1]) < 1e-5:
                deduped[-1] = (x, y)
                xs_used[-1] = x
            else:
                deduped.append((x, y))
                xs_used.append(x)
        if len(deduped) < 2:
            return [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
        deduped[0] = (0.0, max(-1.0, min(1.0, deduped[0][1])))
        deduped[-1] = (1.0, max(-1.0, min(1.0, deduped[-1][1])))
        return deduped

    # ---------- note API
    def trigger_note(self, pitch: int, velocity: int = 100, duration_ms: int | None = 180) -> bool:
        ok = self.note_on(pitch, velocity)
        if not ok:
            return False
        with self._lock:
            if self._voices:
                v = self._voices[-1]
                if duration_ms is not None:
                    v.preview_frames_left = max(1, int((float(duration_ms) / 1000.0) * self.target_sr))
        return True

    def note_on(self, pitch: int, velocity: int = 100, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        try:
            p = int(pitch)
            vel = int(max(1, min(127, velocity)))
        except Exception:
            return False
        freq = 440.0 * (2.0 ** ((((float(p) + float(pitch_offset_semitones or 0.0)) - 69.0) / 12.0)))
        if not (10.0 <= freq <= 16000.0):
            return False
        with self._lock:
            self._seq += 1
            chaos_seed = 0.21 + ((p * 17 + self._seq * 7) % 61) / 100.0
            prev_voice = next((vv for vv in reversed(self._voices) if not getattr(vv, "released", False)), self._voices[-1] if self._voices else None)
            retrig = float(self._params.get("retrigger", 1.0) or 1.0) >= 0.5
            glide_amt = float(self._params.get("glide", 0.0) or 0.0)
            glide_samples = 0
            glide_start = float(freq)
            phase_init = 0.0
            if prev_voice is not None:
                if not retrig:
                    phase_init = float(getattr(prev_voice, "phase", 0.0) or 0.0)
                if glide_amt > 1e-4:
                    glide_start = float(getattr(prev_voice, "base_freq", freq) or freq)
                    glide_samples = max(0, int((0.004 + glide_amt * 0.42) * float(self.target_sr)))
            self._voices.append(AeternaVoice(
                pitch=p,
                base_freq=float(freq),
                velocity=vel / 127.0,
                phase=phase_init,
                note_on_seq=self._seq,
                chaos_state=float(min(0.91, max(0.09, chaos_seed))),
                micropitch_curve=list(micropitch_curve or []),
                micropitch_duration=max(0, int(note_duration_samples or 0)),
                micropitch_elapsed=0,
                glide_start_freq=float(glide_start),
                glide_samples=int(glide_samples),
            ))
            if len(self._voices) > 24:
                self._voices = self._voices[-24:]
        return True

    def note_off(self) -> None:
        self._release_all_voices(fast=True)

    def all_notes_off(self) -> None:
        self._release_all_voices(fast=True)

    def stop_all(self) -> None:
        with self._lock:
            self._voices.clear()
            self._delay_l[:] = 0.0
            self._delay_r[:] = 0.0
            self._delay_pos = 0

    def _release_all_voices(self, fast: bool = False) -> None:
        with self._lock:
            params = dict(self._params)
            for v in self._voices:
                if v.released:
                    continue
                try:
                    age_sec = max(0.0, float(v.age_samples) / max(1.0, float(self.target_sr)))
                    v.amp_release_level = float(self._adsr_hold_level(
                        age_sec,
                        self._adsr_time_seconds(float(params.get("aeg_attack", 0.10) or 0.10), 0.002, 1.80),
                        self._adsr_time_seconds(float(params.get("aeg_decay", 0.28) or 0.28), 0.020, 2.80),
                        float(np.clip(params.get("aeg_sustain", 0.78) or 0.78, 0.0, 1.0)),
                    ))
                    v.filter_release_level = float(self._adsr_hold_level(
                        age_sec,
                        self._adsr_time_seconds(float(params.get("feg_attack", 0.04) or 0.04), 0.001, 1.20),
                        self._adsr_time_seconds(float(params.get("feg_decay", 0.22) or 0.22), 0.010, 2.20),
                        float(np.clip(params.get("feg_sustain", 0.58) or 0.58, 0.0, 1.0)),
                    ))
                except Exception:
                    v.amp_release_level = 1.0
                    v.filter_release_level = 1.0
                v.released = True
                v.release_age_samples = 0
                if fast:
                    v.release_override_samples = self._gate_release_samples()


    def _adsr_time_seconds(self, value: float, min_s: float, max_s: float) -> float:
        v = float(np.clip(value, 0.0, 1.0))
        return float(min_s + (v * v) * (max_s - min_s))

    def _adsr_hold_level(self, age_sec: float, attack_s: float, decay_s: float, sustain: float) -> float:
        age = max(0.0, float(age_sec))
        a = max(1e-6, float(attack_s))
        d = max(1e-6, float(decay_s))
        s = float(np.clip(sustain, 0.0, 1.0))
        if age < a:
            return float(np.clip(age / a, 0.0, 1.0))
        if age < a + d:
            frac = (age - a) / d
            return float(1.0 - (1.0 - s) * np.clip(frac, 0.0, 1.0))
        return s

    def _adsr_block(self, voice: AeternaVoice, frames: int, sr: int, attack_s: float, decay_s: float, sustain: float, release_s: float, release_level: float = 1.0) -> np.ndarray:
        ages_sec = (float(voice.age_samples) + np.arange(frames, dtype=np.float64)) / max(1.0, float(sr))
        a = max(1e-6, float(attack_s))
        d = max(1e-6, float(decay_s))
        s = float(np.clip(sustain, 0.0, 1.0))
        rel = max(1e-6, float(release_s))
        env = np.empty(frames, dtype=np.float64)
        atk_mask = ages_sec < a
        env[atk_mask] = ages_sec[atk_mask] / a
        dec_mask = (~atk_mask) & (ages_sec < (a + d))
        env[dec_mask] = 1.0 - (1.0 - s) * ((ages_sec[dec_mask] - a) / d)
        sus_mask = ~(atk_mask | dec_mask)
        env[sus_mask] = s
        if getattr(voice, "released", False):
            rel_age = (float(voice.release_age_samples) + np.arange(frames, dtype=np.float64)) / max(1.0, float(sr))
            env = np.minimum(env, float(release_level)) * np.clip(1.0 - (rel_age / rel), 0.0, 1.0)
        return np.clip(env, 0.0, 1.0)

    # ---------- state IO
    def get_exportable_param_keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(str(k) for k in self._params.keys()))

    def export_preset_snapshot(self) -> dict:
        with self._lock:
            return {
                "preset_schema_version": AETERNA_PRESET_SCHEMA_VERSION,
                "preset_name": str(self._preset_name),
                "params": dict(self._params),
                "preset_metadata": dict(self._preset_metadata),
                "mseg_points": [list(pt) for pt in self._mseg_points],
                "mseg_segment_forms": list(self._mseg_segment_forms),
            }

    def get_state_summary(self) -> dict:
        with self._lock:
            return {
                "state_schema_version": AETERNA_STATE_SCHEMA_VERSION,
                "preset_schema_version": AETERNA_PRESET_SCHEMA_VERSION,
                "preset_name": str(self._preset_name),
                "mode": str(self._params.get("mode") or "formula"),
                "formula_ok": bool(self._formula_ok),
                "param_count": len(self._params),
                "mseg_point_count": len(self._mseg_points),
                "mseg_segment_count": len(self._mseg_segment_forms),
                "automation_group_count": len(self.get_automation_groups()),
                "preset_metadata": dict(self._preset_metadata),
            }

    def get_formula_mod_summary(self) -> dict:
        with self._lock:
            formula = str(self._params.get("formula") or DEFAULT_FORMULA)
        tokens = self._extract_formula_tokens(formula)
        label_map = {
            "note_hz": "$NOTE",
            "vel": "$VEL",
            "t_rem": "$T_REM",
            "glitch": "$GLITCH",
            "lfo1": "LFO1",
            "lfo2": "LFO2",
            "mseg": "MSEG",
            "chaos_src": "CHAOS",
            "env": "ENV",
            "phase": "PHASE",
        }
        labels = [label_map.get(t, t) for t in tokens]
        active = labels if labels else ["keine Sonderquelle"]
        examples = [
            "exp(-t * $VEL) * sin($NOTE * log(1 + 1/(abs($T_REM) + 0.0001)) * t)",
            "sin(PHASE if False else phase)"
        ]
        return {
            "normalized_formula": self._normalize_formula_aliases(formula),
            "active_tokens": labels,
            "active_count": len(labels),
            "active_text": " • ".join(active),
        }


    def export_state(self) -> dict:
        with self._lock:
            return {
                "state_schema_version": AETERNA_STATE_SCHEMA_VERSION,
                "params": dict(self._params),
                "preset_name": str(self._preset_name),
                "formula_ok": bool(self._formula_ok),
                "preset_metadata": dict(self._preset_metadata),
                "mseg_points": [list(pt) for pt in self._mseg_points],
                "mseg_segment_forms": list(self._mseg_segment_forms),
                "engine_snapshot": self.export_preset_snapshot(),
                "automation_groups": self.get_automation_groups(),
                "wavetable_state": self._wt_bank.export_state(),
                "wt_unison_state": self._wt_unison.export_state(),
            }

    def import_state(self, d: dict) -> None:
        if not isinstance(d, dict):
            return
        with self._lock:
            snapshot = d.get("engine_snapshot") if isinstance(d.get("engine_snapshot"), dict) else {}
            params = d.get("params")
            if not isinstance(params, dict) and isinstance(snapshot.get("params"), dict):
                params = snapshot.get("params")
            if isinstance(params, dict):
                for k, v in params.items():
                    if k in _STRING_PARAMS:
                        self.set_param(k, v)
                    else:
                        try:
                            self._params[k] = max(0.0, min(1.0, float(v)))
                        except Exception:
                            pass
            pts = d.get("mseg_points")
            if pts is None and snapshot:
                pts = snapshot.get("mseg_points")
            if pts is not None:
                self._mseg_points = self._sanitize_mseg_points(pts)
            seg_forms = d.get("mseg_segment_forms")
            if seg_forms is None and snapshot:
                seg_forms = snapshot.get("mseg_segment_forms")
            self._mseg_segment_forms = self._sanitize_mseg_segment_forms(seg_forms, len(self._mseg_points) - 1)
            self._preset_name = str(d.get("preset_name") or snapshot.get("preset_name") or self._preset_name)
            meta = d.get("preset_metadata") if isinstance(d.get("preset_metadata"), dict) else {}
            if not meta and isinstance(snapshot.get("preset_metadata"), dict):
                meta = snapshot.get("preset_metadata")
            tags_raw = meta.get("tags", self._preset_metadata.get("tags") or [])
            tags: list[str] = []
            if isinstance(tags_raw, str):
                tags = [t.strip() for t in tags_raw.split(",") if str(t).strip()]
            elif isinstance(tags_raw, (list, tuple, set)):
                tags = [str(t).strip() for t in tags_raw if str(t).strip()]
            deduped: list[str] = []
            seen: set[str] = set()
            for tag in tags:
                low = tag.lower()
                if low in seen:
                    continue
                seen.add(low)
                deduped.append(tag[:24])
                if len(deduped) >= 8:
                    break
            self._preset_metadata = {
                "category": str(meta.get("category") or self._preset_metadata.get("category") or "experimentell"),
                "character": str(meta.get("character") or self._preset_metadata.get("character") or "weich"),
                "note": str(meta.get("note") or self._preset_metadata.get("note") or "").strip(),
                "tags": deduped,
                "favorite": bool(meta.get("favorite", self._preset_metadata.get("favorite", False))),
            }
            self._formula_ok = self._validate_formula(str(self._params.get("formula") or DEFAULT_FORMULA))
            # Restore wavetable state (v0.0.20.657+)
            wt_state = d.get("wavetable_state")
            if isinstance(wt_state, dict):
                self._wt_bank.import_state(wt_state)
            elif str(self._params.get("mode")) == "wavetable":
                tname = str(self._params.get("wt_table_name", "Basic (Sine→Saw)") or "Basic (Sine→Saw)")
                self._wt_bank.load_builtin(tname)
            wtu_state = d.get("wt_unison_state")
            if isinstance(wtu_state, dict):
                self._wt_unison.import_state(wtu_state)

    # ---------- DSP
    def pull(self, frames: int, sr: int) -> np.ndarray:
        frames = int(max(0, frames))
        if frames <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        sr = int(sr or self.target_sr or 48000)
        # Lock-free: atomic reference reads (GIL-safe under CPython)
        voices = self._voices
        params = self._params
        if not voices:
            return np.zeros((frames, 2), dtype=np.float32)

        out_l = np.zeros(frames, dtype=np.float32)
        out_r = np.zeros(frames, dtype=np.float32)
        survivors: List[AeternaVoice] = []

        for voice in voices:
            block_l, block_r, alive = self._render_voice(voice, frames, sr, params)
            out_l += block_l
            out_r += block_r
            if alive:
                survivors.append(voice)

        tone = float(params.get("tone", 0.5) or 0.5)
        if tone < 0.999:
            alpha = 0.05 + tone * 0.42
            out_l = self._one_pole_lowpass(out_l, alpha)
            out_r = self._one_pole_lowpass(out_r, alpha)
        ref_voice = survivors[0] if survivors else (voices[0] if voices else None)
        filter_mod = self._compute_global_filter_mod_values(ref_voice, frames, sr, params)
        out_l, out_r = self._apply_filter(out_l, out_r, params, sr, filter_mod)
        np.tanh(out_l, out=out_l)
        np.tanh(out_r, out=out_r)
        out_l, out_r = self._apply_space(out_l, out_r, params)
        gain = 0.18 + float(params.get("gain", 0.56) or 0.56) * 0.42
        stereo = np.stack([out_l * gain, out_r * gain], axis=1).astype(np.float32, copy=False)

        mono_preview = np.clip((out_l + out_r) * 0.5, -1.0, 1.0).astype(np.float32, copy=False)
        self._update_scope(mono_preview)
        # Lock-free: atomic reference swap (GIL-safe)
        self._voices = survivors
        return stereo

    def get_scope_buffer(self) -> np.ndarray:
        with self._lock:
            return self._scope.copy()

    def get_mod_preview_data(self, source: str, points: int = 384) -> np.ndarray:
        points = int(max(32, points or 384))
        source = str(source or "mseg").lower()
        with self._lock:
            params = dict(self._params)
        t = np.linspace(0.0, 1.0, points, endpoint=False, dtype=np.float32)
        logistic = 0.5 + 0.5 * np.sin(t * TWOPI * 0.37 + 0.31)
        voice = AeternaVoice(pitch=60, base_freq=261.625565, velocity=0.9, note_on_seq=3, chaos_state=0.617)
        try:
            block = self._mod_source_block(source, voice, points, max(1, self.target_sr), t, logistic, params)
        except Exception:
            block = np.zeros(points, dtype=np.float32)
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        if block.size != points:
            block = np.resize(block, points).astype(np.float32, copy=False)
        return np.clip(block, -1.0, 1.0)

    def get_web_overlay_data(self, slot: int, points: int = 384) -> dict:
        slot = 1 if int(slot or 1) <= 1 else 2
        source_key = f"mod{slot}_source"
        target_key = f"mod{slot}_target"
        amount_key = f"mod{slot}_amount"
        with self._lock:
            source = str(self._params.get(source_key, "off") or "off")
            target = str(self._params.get(target_key, "off") or "off")
            amount = float(self._params.get(amount_key, 0.0) or 0.0)
        if source not in MOD_SOURCE_KEYS:
            source = "off"
        if target not in MOD_TARGET_KEYS:
            target = "off"
        amount = max(0.0, min(1.0, amount))
        if source == "off" or target == "off" or amount <= 0.0001:
            data = np.zeros(int(max(32, points or 384)), dtype=np.float32)
        else:
            data = self.get_mod_preview_data(source, points) * np.float32(amount)
        return {
            "slot": slot,
            "source": source,
            "target": target,
            "amount": amount,
            "data": np.clip(np.asarray(data, dtype=np.float32), -1.0, 1.0),
        }


    # ---------- wavetable API (v0.0.20.657)

    def get_wavetable_bank(self) -> 'WavetableBank':
        """Direct access to the wavetable bank for the widget."""
        return self._wt_bank

    def get_wavetable_unison(self) -> 'UnisonEngine':
        """Direct access to the unison engine for the widget."""
        return self._wt_unison

    def load_wavetable_file(self, path: str) -> bool:
        """Load a .wt or .wav wavetable file."""
        ok = self._wt_bank.load_file(path)
        if ok:
            with self._lock:
                self._params["wt_table_name"] = self._wt_bank.table_name
        return ok

    def load_wavetable_builtin(self, name: str) -> bool:
        """Load a built-in wavetable by name."""
        ok = self._wt_bank.load_builtin(name)
        if ok:
            with self._lock:
                self._params["wt_table_name"] = name
        return ok

    def get_wavetable_info(self) -> dict:
        """Get current wavetable info for the widget."""
        return {
            "name": self._wt_bank.table_name,
            "num_frames": self._wt_bank.num_frames,
            "frame_size": self._wt_bank.frame_size,
            "file_path": self._wt_bank.file_path,
            "position": float(self._params.get("wt_position", 0.0) or 0.0),
        }

    def get_wavetable_frame_data(self, frame_index: int) -> 'np.ndarray | None':
        """Get frame waveform data for visualization."""
        return self._wt_bank.get_frame_data(frame_index)

    def get_wavetable_interpolated_frame(self, position: float = -1.0) -> 'np.ndarray | None':
        """Get interpolated frame at position (or current wt_position if -1)."""
        if position < 0:
            position = float(self._params.get("wt_position", 0.0) or 0.0)
        return self._wt_bank.get_interpolated_frame(position)

    def draw_wavetable_frame(self, frame_index: int, samples: 'np.ndarray') -> bool:
        """Draw/overwrite a wavetable frame."""
        return self._wt_bank.draw_frame(frame_index, samples)

    def get_wavetable_frame_harmonics(self, frame_index: int) -> 'np.ndarray | None':
        """Get FFT harmonic amplitudes for a frame."""
        return self._wt_bank.get_frame_harmonics(frame_index)

    def set_wavetable_frame_harmonics(self, frame_index: int, harmonics: 'np.ndarray',
                                       phases: 'np.ndarray | None' = None) -> bool:
        """Set a frame from harmonic amplitudes via inverse FFT."""
        return self._wt_bank.set_frame_from_harmonics(frame_index, harmonics, phases)

    @staticmethod
    def get_wavetable_builtin_names() -> list[str]:
        """Get list of available built-in wavetable names."""
        return list(BUILTIN_WAVETABLES.keys())

    def sync_wavetable_unison(self) -> None:
        """Synchronize unison engine with current params."""
        p = self._params
        mode_name = str(p.get("wt_unison_mode", "Off") or "Off")
        mode_idx = {"Off": 0, "Classic": 1, "Supersaw": 2, "Hyper": 3}.get(mode_name, 0)
        n_voices_raw = float(p.get("wt_unison_voices", 0.0) or 0.0)
        n_voices = max(1, min(MAX_UNISON_VOICES, int(n_voices_raw * 15) + 1))
        self._wt_unison.configure(
            mode=mode_idx,
            num_voices=n_voices,
            detune=float(p.get("wt_unison_detune", 0.20) or 0.20),
            spread=float(p.get("wt_unison_spread", 0.50) or 0.50),
            width=float(p.get("wt_unison_width", 0.50) or 0.50),
        )

    def _compute_global_filter_mod_values(self, ref_voice: AeternaVoice | None, frames: int, sr: int, params: dict) -> dict[str, np.ndarray] | None:
        """Compute filter modulation. Returns None if filter is static (no mods, no FEG)."""
        feg_amount = float(params.get("feg_amount", 0.26) or 0.26)
        has_filter_mod = False
        for slot in range(1, MAX_MOD_SLOTS + 1):
            target = str(params.get(f"mod{slot}_target") or "off")
            source = str(params.get(f"mod{slot}_source") or "off")
            amount = float(params.get(f"mod{slot}_amount", 0.0) or 0.0)
            if target in ("filter_cutoff", "filter_resonance") and source != "off" and amount > 1e-4:
                has_filter_mod = True
                break
        # Skip entire computation if filter is static
        if feg_amount <= 1e-4 and not has_filter_mod:
            return None

        vals = {
            "filter_cutoff": np.full(frames, float(params.get("filter_cutoff", 0.68) or 0.68), dtype=np.float32),
            "filter_resonance": np.full(frames, float(params.get("filter_resonance", 0.18) or 0.18), dtype=np.float32),
        }
        if frames <= 0:
            return vals
        voice = ref_voice or AeternaVoice(pitch=60, base_freq=261.625565, velocity=0.9, note_on_seq=3, chaos_state=0.617)
        age_samples = max(0, int(getattr(voice, "age_samples", 0) or 0))
        t = (age_samples + np.arange(frames, dtype=np.float64)) / max(1.0, float(sr))
        logistic = self._logistic_block(voice, frames, 3.40 + float(params.get("chaos", 0.10) or 0.10) * 0.50)
        source_cache = {
            "off": np.zeros(frames, dtype=np.float64),
            "chaos": np.clip((logistic - 0.5) * 2.0, -1.0, 1.0),
        }
        if feg_amount > 1e-4:
            try:
                feg_env = self._filter_envelope(voice, frames, sr, params)
                vals["filter_cutoff"] = np.clip(vals["filter_cutoff"] + ((feg_env * 2.0 - 1.0) * feg_amount * 0.28) + (feg_env * feg_amount * 0.38), 0.0, 1.0)
                vals["filter_resonance"] = np.clip(vals["filter_resonance"] + (feg_env * feg_amount * 0.12), 0.0, 1.0)
            except Exception:
                pass
        for slot in range(1, MAX_MOD_SLOTS + 1):
            source = str(params.get(f"mod{slot}_source") or "off")
            target = str(params.get(f"mod{slot}_target") or "off")
            if target not in vals:
                continue
            amount = float(params.get(f"mod{slot}_amount", 0.0) or 0.0)
            if source == "off" or amount <= 1e-4:
                continue
            if source not in source_cache:
                source_cache[source] = self._mod_source_block(source, voice, frames, sr, t, logistic, params)
            polarity = str(params.get(f"mod{slot}_polarity") or "plus").strip().lower()
            sign = -1.0 if polarity in {"minus", "-", "−", "inv", "invert"} else 1.0
            vals[target] = np.clip(vals[target] + source_cache[source] * amount * sign, 0.0, 1.0)
        return vals

    def _apply_filter(self, left: np.ndarray, right: np.ndarray, params: dict, sr: int, mod_vals: dict[str, np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray]:
        filt_type = str(params.get("filter_type") or "LP 24")
        if filt_type not in {"LP 12", "LP 24", "HP 12", "BP", "Notch", "Comb+"}:
            filt_type = "LP 24"
        
        # Static filter path (no modulation) — use scipy C-speed if available
        if mod_vals is None:
            cutoff_val = float(params.get("filter_cutoff", 0.68) or 0.68)
            res_val = float(params.get("filter_resonance", 0.18) or 0.18)
            if cutoff_val >= 0.995 and res_val <= 0.01 and filt_type in {"LP 24", "LP 12"}:
                return left, right
            if filt_type == "Comb+":
                c = np.full(left.shape[0], cutoff_val); r = np.full(left.shape[0], res_val)
                return self._comb_process_stereo(left, right, c, r)
            # Try scipy fast path for constant coefficients
            try:
                return self._scipy_filter_stereo(left, right, cutoff_val, res_val, filt_type)
            except Exception:
                pass
            c = np.full(left.shape[0], cutoff_val, dtype=np.float64)
            r = np.full(left.shape[0], res_val, dtype=np.float64)
            return self._svf_process_mono(left, c, r, filt_type, "l"), self._svf_process_mono(right, c, r, filt_type, "r")

        cutoff = np.asarray(mod_vals.get("filter_cutoff", float(params.get("filter_cutoff", 0.68) or 0.68)), dtype=np.float64)
        resonance = np.asarray(mod_vals.get("filter_resonance", float(params.get("filter_resonance", 0.18) or 0.18)), dtype=np.float64)
        cutoff = np.clip(cutoff, 0.0, 1.0)
        resonance = np.clip(resonance, 0.0, 1.0)
        if float(np.mean(cutoff)) >= 0.995 and float(np.mean(resonance)) <= 0.01 and filt_type in {"LP 24", "LP 12"}:
            return left, right
        if filt_type == "Comb+":
            return self._comb_process_stereo(left, right, cutoff, resonance)
        out_l = self._svf_process_mono(left, cutoff, resonance, filt_type, prefix="l")
        out_r = self._svf_process_mono(right, cutoff, resonance, filt_type, prefix="r")
        return out_l, out_r

    def _scipy_filter_stereo(self, left: np.ndarray, right: np.ndarray, cutoff_val: float, res_val: float, mode: str) -> tuple[np.ndarray, np.ndarray]:
        """C-speed filter for constant coefficients using scipy."""
        from scipy.signal import sosfilt, butter
        fc = 30.0 * ((16000.0 / 30.0) ** cutoff_val)
        fc = min(fc, 0.45 * float(self.target_sr))
        nyq = float(self.target_sr) * 0.5
        wn = min(0.999, max(0.001, fc / nyq))
        if mode in ("LP 24", "LP 12"):
            order = 4 if mode == "LP 24" else 2
            sos = butter(order, wn, btype='low', output='sos')
        elif mode == "HP 12":
            sos = butter(2, wn, btype='high', output='sos')
        elif mode == "BP":
            bw = max(0.01, 0.5 - res_val * 0.45)
            low = max(0.001, wn - bw * 0.5)
            high = min(0.999, wn + bw * 0.5)
            if low >= high:
                low, high = max(0.001, wn * 0.5), min(0.999, wn * 1.5)
            sos = butter(2, [low, high], btype='band', output='sos')
        else:
            sos = butter(2, wn, btype='low', output='sos')
        ol = sosfilt(sos, left.astype(np.float64)).astype(np.float32, copy=False)
        or_ = sosfilt(sos, right.astype(np.float64)).astype(np.float32, copy=False)
        return np.tanh(ol), np.tanh(or_)

    def _svf_process_mono(self, signal: np.ndarray, cutoff, resonance, mode: str, prefix: str = "l") -> np.ndarray:
        x = np.asarray(signal, dtype=np.float32).reshape(-1)
        n = int(x.size)
        if n <= 0:
            return x.astype(np.float32, copy=False)
        cutoff_arr = np.asarray(cutoff, dtype=np.float64).reshape(-1)
        if cutoff_arr.size != n:
            cutoff_arr = np.resize(cutoff_arr, n)
        res_arr = np.asarray(resonance, dtype=np.float64).reshape(-1)
        if res_arr.size != n:
            res_arr = np.resize(res_arr, n)
        s = self._filter_state
        ic1 = float(s.get(f"{prefix}1_ic1", 0.0))
        ic2 = float(s.get(f"{prefix}1_ic2", 0.0))
        is_lp24 = mode == "LP 24"
        ic1b = float(s.get(f"{prefix}2_ic1", 0.0)) if is_lp24 else 0.0
        ic2b = float(s.get(f"{prefix}2_ic2", 0.0)) if is_lp24 else 0.0
        out = np.zeros(n, dtype=np.float32)
        # Process in 64-sample chunks (coefficients constant per chunk)
        chunk = 64
        for start in range(0, n, chunk):
            end = min(start + chunk, n)
            mid = (start + end) // 2
            fc = min(30.0 * ((16000.0 / 30.0) ** float(cutoff_arr[mid])), 0.45 * float(self.target_sr))
            g = math.tan(math.pi * fc / max(1.0, float(self.target_sr)))
            q = 0.60 + (1.0 - float(res_arr[mid])) * 11.40
            k = 1.0 / max(0.35, q)
            a1 = 1.0 / (1.0 + g * (g + k))
            a2 = g * a1
            a3 = g * a2
            for i in range(start, end):
                inp = float(x[i])
                v3 = inp - ic2
                v1 = a1 * ic1 + a2 * v3
                v2 = ic2 + a2 * ic1 + a3 * v3
                ic1 = 2.0 * v1 - ic1
                ic2 = 2.0 * v2 - ic2
                if is_lp24:
                    v3b = v2 - ic2b
                    v1b = a1 * ic1b + a2 * v3b
                    v2b = ic2b + a2 * ic1b + a3 * v3b
                    ic1b = 2.0 * v1b - ic1b
                    ic2b = 2.0 * v2b - ic2b
                    out[i] = float(v2b)
                elif mode == "HP 12":
                    out[i] = float(inp - k * v1 - v2)
                elif mode == "BP":
                    out[i] = float(v1 * (1.0 + float(res_arr[mid]) * 0.6))
                elif mode == "Notch":
                    out[i] = float(v2 + inp - k * v1 - v2)
                else:
                    out[i] = float(v2)
        s[f"{prefix}1_ic1"] = ic1
        s[f"{prefix}1_ic2"] = ic2
        if is_lp24:
            s[f"{prefix}2_ic1"] = ic1b
            s[f"{prefix}2_ic2"] = ic2b
        return np.tanh(out).astype(np.float32, copy=False)

    def _comb_process_stereo(self, left: np.ndarray, right: np.ndarray, cutoff, resonance) -> tuple[np.ndarray, np.ndarray]:
        return (
            self._comb_process_mono(left, cutoff, resonance, channel="l"),
            self._comb_process_mono(right, cutoff, resonance, channel="r"),
        )

    def _comb_process_mono(self, signal: np.ndarray, cutoff, resonance, channel: str = "l") -> np.ndarray:
        x = np.asarray(signal, dtype=np.float32).reshape(-1)
        n = int(x.size)
        if n <= 0:
            return x.astype(np.float32, copy=False)
        cutoff_arr = np.asarray(cutoff, dtype=np.float64).reshape(-1)
        if cutoff_arr.size != n:
            cutoff_arr = np.resize(cutoff_arr, n)
        res_arr = np.asarray(resonance, dtype=np.float64).reshape(-1)
        if res_arr.size != n:
            res_arr = np.resize(res_arr, n)
        buf = self._comb_l if str(channel).lower().startswith("l") else self._comb_r
        pos = int(self._comb_pos)
        avg_cutoff = float(np.mean(cutoff_arr))
        avg_res = float(np.mean(res_arr))
        delay = max(6, min(self._comb_len - 2, 18 + int((1.0 - avg_cutoff) * 180.0)))
        fb = np.float32(0.12 + avg_res * 0.76)
        indices = (np.arange(n, dtype=np.int32) + pos) % self._comb_len
        read_indices = (indices - delay) % self._comb_len
        delayed = buf[read_indices].copy()
        y = x + delayed * fb
        buf[indices] = y.astype(np.float32, copy=False)
        self._comb_pos = int((pos + n) % self._comb_len)
        return np.tanh(y).astype(np.float32, copy=False)

    def _update_scope(self, mono: np.ndarray) -> None:
        try:
            if mono.size <= 0:
                return
            target = int(self._scope.shape[0])
            step = max(1, mono.size // target)
            sampled = mono[::step][:target]
            if sampled.size < target:
                sampled = np.pad(sampled, (0, target - sampled.size), mode="edge")
            # Lock-free: atomic reference swap under GIL
            self._scope = 0.82 * self._scope + 0.18 * sampled.astype(np.float32, copy=False)
        except Exception:
            pass

    def _render_voice(self, voice: AeternaVoice, frames: int, sr: int, params: dict) -> tuple[np.ndarray, np.ndarray, bool]:
        idx = np.arange(frames, dtype=np.float64)
        t = (voice.age_samples + idx) / float(sr)
        freq = self._freq_array(voice, frames)

        base_vals = {
            "morph": float(params.get("morph", 0.5) or 0.5),
            "chaos": float(params.get("chaos", 0.2) or 0.2),
            "drift": float(params.get("drift", 0.2) or 0.2),
            "motion": float(params.get("motion", 0.3) or 0.3),
            "tone": float(params.get("tone", 0.5) or 0.5),
            "space": float(params.get("space", 0.3) or 0.3),
            "cathedral": float(params.get("cathedral", 0.34) or 0.34),
            "pan": float(params.get("pan", 0.50) or 0.50),
            "glide": float(params.get("glide", 0.06) or 0.06),
            "stereo_spread": float(params.get("stereo_spread", 0.34) or 0.34),
            "unison_mix": float(params.get("unison_mix", 0.12) or 0.12),
            "unison_detune": float(params.get("unison_detune", 0.18) or 0.18),
            "sub_level": float(params.get("sub_level", 0.10) or 0.10),
            "noise_level": float(params.get("noise_level", 0.04) or 0.04),
            "noise_color": float(params.get("noise_color", 0.34) or 0.34),
            "pitch": float(params.get("pitch", 0.50) or 0.50),
            "shape": float(params.get("shape", 0.42) or 0.42),
            "pulse_width": float(params.get("pulse_width", 0.50) or 0.50),
            "drive": float(params.get("drive", 0.28) or 0.28),
            "feedback": float(params.get("feedback", 0.08) or 0.08),
            "aeg_attack": float(params.get("aeg_attack", 0.10) or 0.10),
            "aeg_decay": float(params.get("aeg_decay", 0.28) or 0.28),
            "aeg_sustain": float(params.get("aeg_sustain", 0.78) or 0.78),
            "aeg_release": float(params.get("aeg_release", 0.46) or 0.46),
            "feg_attack": float(params.get("feg_attack", 0.04) or 0.04),
            "feg_decay": float(params.get("feg_decay", 0.22) or 0.22),
            "feg_sustain": float(params.get("feg_sustain", 0.58) or 0.58),
            "feg_release": float(params.get("feg_release", 0.34) or 0.34),
            "feg_amount": float(params.get("feg_amount", 0.26) or 0.26),
            "wt_position": float(params.get("wt_position", 0.0) or 0.0),
        }
        vel = float(voice.velocity)
        pitch_ratio = np.power(2.0, ((base_vals["pitch"] - 0.5) * 48.0) / 12.0)
        freq = freq * pitch_ratio
        phase_inc = (freq / float(sr)) * TWOPI
        phase = voice.phase + np.cumsum(phase_inc)
        phase0 = phase - phase_inc
        mode = str(params.get("mode") or "formula")
        logistic = self._logistic_block(voice, frames, 3.40 + base_vals["chaos"] * 0.50)
        mod_vals = self._compute_mod_values(voice, frames, sr, t, logistic, params, base_vals)
        morph = mod_vals["morph"]
        chaos = mod_vals["chaos"]
        drift = mod_vals["drift"]
        motion = mod_vals["motion"]
        tone_arr = mod_vals["tone"]
        env_mod = 0.2 + 0.8 * logistic

        pulse_width_arr = np.clip(mod_vals.get("pulse_width", np.full(frames, base_vals["pulse_width"], dtype=np.float64)), 0.0, 1.0)
        shape_arr = np.clip(mod_vals.get("shape", np.full(frames, base_vals["shape"], dtype=np.float64)), 0.0, 1.0)
        drive_arr = np.clip(mod_vals.get("drive", np.full(frames, base_vals["drive"], dtype=np.float64)), 0.0, 1.0)
        feedback_arr = np.clip(mod_vals.get("feedback", np.full(frames, base_vals["feedback"], dtype=np.float64)), 0.0, 1.0)
        duty = np.clip(0.10 + pulse_width_arr * 0.80 + (0.04 * np.sin(t * TWOPI * (0.06 + motion * 0.08))), 0.08, 0.92)
        # Only compute expensive polyblep oscillators for modes that use them heavily
        need_polyblep = mode in ("spectral", "terrain", "chaos")
        if need_polyblep:
            band_saw = self._polyblep_saw(freq, phase0, sr)
            band_square = self._polyblep_square(freq, phase0, sr, duty=duty)
            shape_wave = self._shape_wave(phase0, band_saw, band_square, shape_arr)
        if mode == "spectral":
            partial2 = np.sin(phase0 * (2.0 + 1.2 * morph) + 0.10 * np.sin(t * TWOPI * (0.16 + drift * 0.8)))
            partial4 = np.sin(phase0 * (4.0 + 1.6 * chaos) + 0.35 * motion * np.sin(t * TWOPI * 0.22))
            airy = np.sin(phase0 + 0.15 * np.sin(phase0 * (1.0 + morph * 0.6)))
            sig = (0.26 + 0.12 * (1.0 - morph)) * band_saw
            sig += (0.40 + 0.20 * morph) * np.sin(phase0)
            sig += (0.10 + 0.16 * morph) * partial2
            sig += (0.02 + 0.05 * (1.0 - chaos)) * partial4
            sig += 0.24 * airy
        elif mode == "terrain":
            orbit_x = phase0 * (1.0 + 0.55 * motion) + 0.65 * morph * np.sin(t * TWOPI * (0.18 + drift * 0.32))
            orbit_y = phase0 * (0.30 + 1.15 * chaos) + 0.45 * np.cos(t * TWOPI * (0.10 + motion * 0.25))
            terrain_a = np.sin(orbit_x) * np.cos(orbit_y)
            terrain_b = 0.24 * np.sin(orbit_x * 0.5 + orbit_y * 0.25)
            terrain_c = 0.16 * np.sin(np.sin(orbit_x * 0.5) + np.cos(orbit_y * (1.0 + morph * 0.5)))
            sig = 0.62 * terrain_a + terrain_b + terrain_c + 0.22 * np.sin(phase0)
            sig = 0.82 * sig + 0.10 * band_square
        elif mode == "chaos":
            fm = phase0 + (0.12 + 2.20 * chaos) * logistic
            sig = np.sin(fm) * (0.70 + 0.18 * np.sin(phase0 * (1.0 + morph * 1.1)))
            sig += 0.08 * band_square
            sig += 0.10 * np.tanh(np.sin(phase0 * (2.0 + 3.0 * chaos)) + 0.7 * logistic)
        elif mode == "wavetable":
            # Wavetable oscillator — read from WavetableBank with position modulation
            wt_pos = np.clip(mod_vals.get("wt_position", np.full(frames, base_vals["wt_position"], dtype=np.float64)), 0.0, 1.0)
            wt_phases = np.mod(phase0 / TWOPI, 1.0)  # convert radian phase to 0..1
            if isinstance(wt_pos, (float, int, np.floating)):
                sig = self._wt_bank.read_block(wt_phases, float(wt_pos))
            else:
                sig = self._wt_bank.read_block_modulated(wt_phases, wt_pos)
            # Add subtle morph animation: slight position sweep via motion
            if float(np.mean(np.asarray(motion, dtype=np.float64))) > 0.01:
                motion_offset = 0.04 * motion * np.sin(t * TWOPI * 0.08)
                wt_pos2 = np.clip(wt_pos + motion_offset, 0.0, 1.0)
                sig2 = self._wt_bank.read_block_modulated(wt_phases, np.asarray(wt_pos2, dtype=np.float64) if not isinstance(wt_pos2, np.ndarray) else wt_pos2)
                sig = sig * 0.85 + sig2 * 0.15
        else:
            # Lazy formula variables — only compute expensive sources if referenced
            formula_text = str(params.get("formula") or DEFAULT_FORMULA)
            fvars = {
                "t": t, "phase": phase0, "p": phase0, "f": freq, "note_hz": freq,
                "vel": vel, "m": morph, "c": chaos, "d": drift, "motion": motion,
                "x": logistic, "env": env_mod, "chaos_src": logistic,
                "glitch": float(np.clip(base_vals.get("chaos", 0.3) * 0.85 + base_vals.get("motion", 0.2) * 0.15, 0.0, 1.0)),
            }
            if "t_rem" in formula_text or "T_REM" in formula_text:
                fvars["t_rem"] = np.maximum(0.0, 1.0 - np.asarray(t, dtype=np.float64))
            if "lfo1" in formula_text or "LFO1" in formula_text:
                fvars["lfo1"] = self._lfo_block(frames, sr, 0.07 + float(base_vals.get("lfo1_rate", 0.2)) * 5.2, phase0=voice.phase * 0.31)
            if "lfo2" in formula_text or "LFO2" in formula_text:
                fvars["lfo2"] = self._lfo_triangle_block(frames, sr, 0.05 + float(base_vals.get("lfo2_rate", 0.12)) * 3.6, phase0=voice.phase * 0.17)
            if "mseg" in formula_text or "MSEG" in formula_text:
                fvars["mseg"] = self._mseg_block(frames, sr, 0.06 + float(base_vals.get("mseg_rate", 0.24)) * 2.5, phase0=voice.phase * 0.11)
            formula_sig = self._eval_formula(formula_text, fvars)
            sig = (0.78 * formula_sig) + ((0.08 + 0.10 * morph) * np.sin(phase0)) + ((0.01 + 0.04 * chaos) * np.sign(np.sin(phase0)))

        sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
        if need_polyblep:
            shape_mix = np.clip(0.18 + (np.abs(shape_arr - 0.5) * 0.82), 0.10, 0.72).astype(np.float32, copy=False)
            sig = (sig * (1.0 - shape_mix * 0.42)) + (shape_wave * shape_mix * 0.42)
        tone_scalar = float(np.mean(tone_arr))
        chaos_scalar = float(np.mean(np.asarray(chaos, dtype=np.float32)))
        # Skip expensive core_sine blend in chaos mode (saves 3× np.sin)
        if mode != "chaos":
            core_sine = (0.76 * np.sin(phase0 + 0.06 * np.sin(phase0 * (0.5 + 0.2 * morph)))
                         + 0.16 * np.sin(phase0 * 2.0 + 0.05 * motion)
                         + 0.05 * np.sin(phase0 * 4.0 + 0.03 * drift)).astype(np.float32, copy=False)
            purity = float(np.clip((tone_scalar - chaos_scalar * 0.35), 0.0, 1.0))
            sig = ((0.78 - 0.20 * purity) * sig) + ((0.22 + 0.20 * purity) * core_sine)

        unison_mix_arr = np.clip(mod_vals.get("unison_mix", np.full(frames, base_vals["unison_mix"], dtype=np.float64)), 0.0, 1.0)
        unison_detune_arr = np.clip(mod_vals.get("unison_detune", np.full(frames, base_vals["unison_detune"], dtype=np.float64)), 0.0, 1.0)
        sub_level_arr = np.clip(mod_vals.get("sub_level", np.full(frames, base_vals["sub_level"], dtype=np.float64)), 0.0, 1.0)
        noise_level_arr = np.clip(mod_vals.get("noise_level", np.full(frames, base_vals["noise_level"], dtype=np.float64)), 0.0, 1.0)
        noise_color_arr = np.clip(mod_vals.get("noise_color", np.full(frames, base_vals["noise_color"], dtype=np.float64)), 0.0, 1.0)
        voices_cfg = str(params.get("unison_voices") or "2")
        if voices_cfg not in {"1", "2", "4", "6"}:
            voices_cfg = "2"
        voice_offsets_map = {
            "1": (),
            "2": (-1.0, 1.0),
            "4": (-1.8, -0.65, 0.65, 1.8),
            "6": (-2.4, -1.4, -0.55, 0.55, 1.4, 2.4),
        }
        voice_offsets = voice_offsets_map.get(voices_cfg, ())
        if voice_offsets and float(np.mean(unison_mix_arr)) > 1e-4:
            detune_semi = 0.02 + (unison_detune_arr * 0.32)
            uni = np.zeros(frames, dtype=np.float64)
            denom = max(1.0, max(abs(float(o)) for o in voice_offsets))
            for off in voice_offsets:
                semi = detune_semi * (float(off) / denom)
                ratio = np.power(2.0, semi / 12.0)
                ph = phase0 * ratio + (0.21 * float(off)) + (0.07 * motion)
                comp = 0.78 * np.sin(ph) + 0.16 * np.sin(ph * (2.0 + 0.06 * morph)) + 0.06 * np.sin(ph * 0.5 + 0.03 * drift)
                uni += comp
            uni = (uni / max(1.0, float(len(voice_offsets)))).astype(np.float32, copy=False)
            uni_mix = (unison_mix_arr * 0.58).astype(np.float32, copy=False)
            sig = (sig * (1.0 - uni_mix * 0.42)) + (uni * uni_mix)

        sub_oct = str(params.get("sub_octave") or "-1")
        sub_ratio = 0.25 if sub_oct == "-2" else 0.5
        if float(np.mean(sub_level_arr)) > 1e-4:
            ph_sub = (phase0 * sub_ratio) + (0.04 * motion)
            sub_wave = (0.82 * np.sin(ph_sub) + 0.18 * np.sign(np.sin(ph_sub + 0.13 * drift))).astype(np.float32, copy=False)
            sub_gain = (sub_level_arr * (0.16 + 0.10 * (1.0 - tone_scalar))).astype(np.float32, copy=False)
            sig = sig + (sub_wave * sub_gain)

        if float(np.mean(noise_level_arr)) > 1e-4:
            seed = (int(getattr(voice, "note_on_seq", 0) or 0) * 1103515245 + int(getattr(voice, "pitch", 60) or 60) * 12345 + int(getattr(voice, "age_samples", 0) or 0)) & 0xFFFFFFFF
            rng = np.random.default_rng(seed)
            white = rng.uniform(-1.0, 1.0, frames).astype(np.float32)
            dark = self._one_pole_lowpass(white, 0.06).astype(np.float32, copy=False)
            airy = (white - self._one_pole_lowpass(white, 0.025)).astype(np.float32, copy=False)
            color = float(np.clip(np.mean(noise_color_arr), 0.0, 1.0))
            noise_sig = (((1.0 - color) * dark) + (color * (0.62 * white + 0.38 * airy))).astype(np.float32, copy=False)
            noise_gain = (noise_level_arr * (0.08 + 0.08 * color)).astype(np.float32, copy=False)
            sig = sig + (noise_sig * noise_gain)

        # Tone shaping — skip expensive lowpass when tone > 0.85 (saves 2× _one_pole_lowpass)
        if tone_scalar < 0.85:
            smooth_sig = self._one_pole_lowpass(sig.astype(np.float32, copy=False), 0.16 + tone_scalar * 0.46)
            air_sig = sig - self._one_pole_lowpass(sig.astype(np.float32, copy=False), 0.16 + tone_scalar * 0.12)
            sig = ((0.30 + 0.46 * tone_scalar) * sig) + ((1.0 - tone_scalar) * 0.84 * smooth_sig)
            sig = sig + ((0.02 + 0.08 * tone_scalar) * max(0.0, 1.0 - chaos_scalar * 0.78) * air_sig)
        if float(np.mean(feedback_arr)) > 1e-4:
            sig = self._feedback_process(voice, sig, feedback_arr)
        drive_amt = 0.72 + float(np.mean(morph)) * 0.18 + chaos_scalar * 0.06 + float(np.mean(drive_arr)) * 1.55
        sig = np.tanh(sig * drive_amt)

        env = self._envelope(voice, frames, sr, params)
        base_pan = np.clip(mod_vals.get("pan", np.full(frames, base_vals["pan"], dtype=np.float64)), 0.0, 1.0)
        spread = np.clip(mod_vals.get("stereo_spread", np.full(frames, base_vals["stereo_spread"], dtype=np.float64)), 0.0, 1.0)
        pan_center = (base_pan * 2.0) - 1.0
        spread_anim = spread * (0.18 + 0.22 * motion) * np.sin((voice.pitch % 12) * 0.7 + t * TWOPI * (0.03 + drift * 0.03))
        pan_pos = np.clip(pan_center + spread_anim, -1.0, 1.0)
        pan_l = np.sqrt(np.clip(0.5 * (1.0 - pan_pos), 0.0, 1.0))
        pan_r = np.sqrt(np.clip(0.5 * (1.0 + pan_pos), 0.0, 1.0))
        width_gain = 1.0 + spread * 0.14 * np.sin(t * TWOPI * (0.18 + drift * 0.2))
        mono = sig * env * (0.18 + 0.82 * vel)
        block_l = mono * pan_l * width_gain
        block_r = mono * pan_r * (2.0 - width_gain)

        voice.phase = float(np.fmod(phase[-1], TWOPI)) if frames else voice.phase
        voice.age_samples += frames
        voice.micropitch_elapsed += frames
        if voice.preview_frames_left is not None:
            voice.preview_frames_left -= frames
            if voice.preview_frames_left <= 0:
                voice.released = True
                voice.release_override_samples = self._gate_release_samples()
                voice.preview_frames_left = None
        if voice.released:
            voice.release_age_samples += frames
            rel = int(voice.release_override_samples or self._release_samples(sr, params))
            if voice.release_age_samples >= rel:
                return block_l, block_r, False
        return block_l.astype(np.float32, copy=False), block_r.astype(np.float32, copy=False), True

    def _compute_mod_values(self, voice: AeternaVoice, frames: int, sr: int, t: np.ndarray, logistic: np.ndarray, params: dict, base_vals: dict) -> dict:
        """Compute modulation values. Returns scalars for unmodulated params, arrays for modulated.
        
        numpy broadcasting handles scalar×array automatically, so expressions like
        `phase0 * (0.5 + 0.2 * morph)` work whether morph is float or array.
        This eliminates ~28 np.full() array allocations when only 2 params are modulated.
        """
        mod_specs = []
        for slot in range(1, MAX_MOD_SLOTS + 1):
            source = str(params.get(f"mod{slot}_source") or "off")
            target = str(params.get(f"mod{slot}_target") or "off")
            amount = float(params.get(f"mod{slot}_amount", 0.0) or 0.0)
            if source == "off" or target == "off" or amount <= 1e-4 or target not in base_vals:
                continue
            polarity = str(params.get(f"mod{slot}_polarity") or "plus").strip().lower()
            mod_specs.append((source, target, amount, polarity))

        # Start with scalar base values (no array allocation!)
        vals = dict(base_vals)  # All scalars

        if mod_specs:
            source_cache = {}
            for source, target, amount, polarity in mod_specs:
                if source not in source_cache:
                    if source == "chaos":
                        source_cache[source] = np.clip((logistic - 0.5) * 2.0, -1.0, 1.0)
                    else:
                        source_cache[source] = self._mod_source_block(source, voice, frames, sr, t, logistic, params)
                sign = -1.0 if polarity in {"minus", "-", "−", "inv", "invert"} else 1.0
                # Only modulated targets become arrays
                base = float(base_vals.get(target, 0.0))
                vals[target] = np.clip(np.float32(base) + source_cache[source] * np.float32(amount * sign), 0.0, 1.0)

        return vals

    def _mod_source_block(self, source: str, voice: AeternaVoice, frames: int, sr: int, t: np.ndarray, logistic: np.ndarray, params: dict) -> np.ndarray:
        if source == "lfo1":
            rate = 0.08 + float(params.get("lfo1_rate", 0.22) or 0.22) * 7.0
            phase = (voice.note_on_seq % 17) * 0.31
            return np.sin(t * TWOPI * rate + phase)
        if source == "lfo2":
            rate = 0.03 + float(params.get("lfo2_rate", 0.10) or 0.10) * 3.5
            frac = np.mod(t * rate + ((voice.note_on_seq * 0.137) % 1.0), 1.0)
            tri = 1.0 - 4.0 * np.abs(frac - 0.5)
            return np.clip(tri, -1.0, 1.0)
        if source == "lfo3":
            # LFO3: Saw-down (ramp) — great for filter sweeps
            rate = 0.04 + float(params.get("lfo3_rate", 0.15) or 0.15) * 5.0
            phase = (voice.note_on_seq % 23) * 0.41
            frac = np.mod(t * rate + phase, 1.0)
            return 1.0 - 2.0 * frac  # saw-down: 1 → -1
        if source == "lfo4":
            # LFO4: Sample & Hold — stepped random at rate
            rate = 0.02 + float(params.get("lfo4_rate", 0.08) or 0.08) * 4.0
            step_idx = np.floor(t * rate).astype(np.int64)
            seed = int((voice.note_on_seq * 7919 + voice.pitch * 131) % (2**31))
            rng = np.random.default_rng(seed)
            max_steps = int(np.max(step_idx)) + 2
            values = rng.uniform(-1.0, 1.0, max_steps)
            return values[np.clip(step_idx, 0, max_steps - 1)]
        if source == "mseg":
            rate = 0.05 + float(params.get("mseg_rate", 0.24) or 0.24) * 2.4
            pos = np.mod(t * rate + ((voice.note_on_seq * 0.113) % 1.0), 1.0)
            with self._lock:
                pts = list(self._mseg_points)
                seg_forms = list(self._mseg_segment_forms)
            return self._evaluate_mseg_positions(pos, pts, seg_forms)
        if source == "chaos":
            return np.clip((logistic - 0.5) * 2.0, -1.0, 1.0)
        if source == "env":
            age = (float(voice.age_samples) + np.arange(frames, dtype=np.float64)) / max(1.0, float(sr))
            attack = 0.004 + float(params.get("motion", 0.2) or 0.2) * 0.050
            decay = 0.120 + float(params.get("release", 0.5) or 0.5) * 0.600
            env = np.where(age < attack, age / max(attack, 1e-6), np.exp(-(age - attack) / max(decay, 1e-6)))
            if voice.released:
                rel_age = (float(voice.release_age_samples) + np.arange(frames, dtype=np.float64)) / max(1.0, float(sr))
                rel = 0.050 + float(params.get("release", 0.5) or 0.5) * 1.200
                env = env * np.exp(-rel_age / max(rel, 1e-6))
            return np.clip(env * 2.0 - 1.0, -1.0, 1.0)
        if source == "env2":
            # ENV2: Filter Envelope shape as bipolar mod source
            env2 = self._filter_envelope(voice, frames, sr, params)
            return np.clip(env2 * 2.0 - 1.0, -1.0, 1.0)
        if source == "vel":
            vel = np.clip(float(voice.velocity or 0.9), 0.0, 1.0)
            return np.full(frames, np.clip(vel * 2.0 - 1.0, -1.0, 1.0), dtype=np.float64)
        return np.zeros(frames, dtype=np.float64)

    def _lfo_block(self, frames: int, sr: int, rate: float, phase0: float = 0.0) -> np.ndarray:
        if frames <= 0:
            return np.zeros(0, dtype=np.float64)
        t = np.arange(frames, dtype=np.float64) / max(1.0, float(sr))
        return np.sin((t * float(rate) * TWOPI) + float(phase0))

    def _lfo_triangle_block(self, frames: int, sr: int, rate: float, phase0: float = 0.0) -> np.ndarray:
        if frames <= 0:
            return np.zeros(0, dtype=np.float64)
        t = np.arange(frames, dtype=np.float64) / max(1.0, float(sr))
        frac = np.mod((t * float(rate)) + (float(phase0) / TWOPI), 1.0)
        tri = 1.0 - 4.0 * np.abs(frac - 0.5)
        return np.clip(tri, -1.0, 1.0)

    def _mseg_block(self, frames: int, sr: int, rate: float, phase0: float = 0.0) -> np.ndarray:
        if frames <= 0:
            return np.zeros(0, dtype=np.float64)
        t = np.arange(frames, dtype=np.float64) / max(1.0, float(sr))
        pos = np.mod((t * float(rate)) + (float(phase0) / TWOPI), 1.0)
        with self._lock:
            pts = list(self._mseg_points)
            forms = list(self._mseg_segment_forms)
        return self._evaluate_mseg_positions(pos, pts, forms)

    def _smoothstep(self, x: np.ndarray) -> np.ndarray:
        x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
        return x * x * (3.0 - 2.0 * x)

    def _evaluate_mseg_positions(self, pos, points=None, segment_forms=None) -> np.ndarray:
        pos_arr = np.asarray(pos, dtype=np.float64).reshape(-1)
        pts = [tuple(pt) for pt in (points or self._mseg_points)]
        if len(pts) < 2:
            pts = [tuple(pt) for pt in DEFAULT_MSEG_POINTS]
        forms = self._sanitize_mseg_segment_forms(segment_forms, len(pts) - 1)
        xs = np.asarray([float(pt[0]) for pt in pts], dtype=np.float64)
        ys = np.asarray([float(pt[1]) for pt in pts], dtype=np.float64)
        idx = np.searchsorted(xs, pos_arr, side="right") - 1
        idx = np.clip(idx, 0, len(xs) - 2)
        x0 = xs[idx]
        x1 = xs[idx + 1]
        y0 = ys[idx]
        y1 = ys[idx + 1]
        frac = np.divide(pos_arr - x0, np.maximum(1e-9, x1 - x0))
        frac = np.clip(frac, 0.0, 1.0)
        out = y0 + (y1 - y0) * frac
        smooth_mask = np.asarray([forms[int(i)] == "smooth" for i in idx], dtype=bool)
        if np.any(smooth_mask):
            sf = self._smoothstep(frac[smooth_mask])
            out[smooth_mask] = y0[smooth_mask] + (y1[smooth_mask] - y0[smooth_mask]) * sf
        return np.clip(out, -1.0, 1.0)

    def _shape_wave(self, phase: np.ndarray, saw: np.ndarray, square: np.ndarray, shape: np.ndarray) -> np.ndarray:
        sh = np.clip(np.asarray(shape, dtype=np.float64), 0.0, 1.0)
        sine = np.sin(phase)
        tri = (2.0 / np.pi) * np.arcsin(np.sin(phase))
        out = np.empty_like(sine, dtype=np.float64)
        mask1 = sh < (1.0 / 3.0)
        if np.any(mask1):
            frac = np.clip(sh[mask1] * 3.0, 0.0, 1.0)
            out[mask1] = (sine[mask1] * (1.0 - frac)) + (tri[mask1] * frac)
        mask2 = (~mask1) & (sh < (2.0 / 3.0))
        if np.any(mask2):
            frac = np.clip((sh[mask2] - (1.0 / 3.0)) * 3.0, 0.0, 1.0)
            out[mask2] = (tri[mask2] * (1.0 - frac)) + (saw[mask2] * frac)
        mask3 = ~(mask1 | mask2)
        if np.any(mask3):
            frac = np.clip((sh[mask3] - (2.0 / 3.0)) * 3.0, 0.0, 1.0)
            out[mask3] = (saw[mask3] * (1.0 - frac)) + (square[mask3] * frac)
        return np.asarray(out, dtype=np.float32)

    def _feedback_process(self, voice: AeternaVoice, signal: np.ndarray, feedback: np.ndarray) -> np.ndarray:
        sig = np.asarray(signal, dtype=np.float32).reshape(-1)
        fb = np.clip(np.asarray(feedback, dtype=np.float32).reshape(-1), 0.0, 1.0)
        if fb.size != sig.size:
            fb = np.resize(fb, sig.size).astype(np.float32, copy=False)
        amt = fb * np.float32(0.78)
        if float(np.mean(amt)) < 1e-4:
            return sig
        prev = float(getattr(voice, "feedback_sample", 0.0) or 0.0)
        delayed = np.empty_like(sig)
        delayed[0] = np.float32(prev)
        delayed[1:] = np.tanh(sig[:-1])
        wet = np.tanh(sig + delayed * amt)
        out = sig * (1.0 - amt * np.float32(0.28)) + wet * amt * np.float32(0.36)
        voice.feedback_sample = float(np.tanh(sig[-1]))
        return out

    def _freq_array(self, voice: AeternaVoice, frames: int) -> np.ndarray:
        base = np.full(frames, float(voice.base_freq), dtype=np.float64)
        glide_from = float(getattr(voice, "glide_start_freq", voice.base_freq) or voice.base_freq)
        glide_samples = int(getattr(voice, "glide_samples", 0) or 0)
        if glide_samples > 0 and abs(glide_from - float(voice.base_freq)) > 1e-6:
            ages = voice.age_samples + np.arange(frames, dtype=np.int64)
            frac = np.clip(ages / float(max(1, glide_samples)), 0.0, 1.0)
            base = (glide_from * np.power(float(voice.base_freq) / max(1e-9, glide_from), frac)).astype(np.float64, copy=False)
        curve = list(getattr(voice, "micropitch_curve", []) or [])
        dur = int(getattr(voice, "micropitch_duration", 0) or 0)
        if len(curve) < 2 or dur <= 0:
            return base
        xs: list[float] = []
        ys: list[float] = []
        for pt in curve:
            try:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    x = float(pt[0]); y = float(pt[1])
                elif isinstance(pt, dict):
                    x = float(pt.get("x", 0.0)); y = float(pt.get("y", 0.0))
                else:
                    continue
                xs.append(min(1.0, max(0.0, x)))
                ys.append(y)
            except Exception:
                continue
        if len(xs) < 2:
            return base
        order = np.argsort(np.asarray(xs, dtype=np.float64))
        xs_arr = np.asarray(xs, dtype=np.float64)[order]
        ys_arr = np.asarray(ys, dtype=np.float64)[order]
        pos = (voice.micropitch_elapsed + np.arange(frames, dtype=np.float64)) / float(max(1, dur))
        pos = np.clip(pos, 0.0, 1.0)
        semis = np.interp(pos, xs_arr, ys_arr)
        return base * np.power(2.0, semis / 12.0)

    def _envelope(self, voice: AeternaVoice, frames: int, sr: int, params: dict) -> np.ndarray:
        attack_legacy = float(params.get("attack", 0.04) or 0.04)
        attack_s = self._adsr_time_seconds((float(params.get("aeg_attack", 0.10) or 0.10) * 0.78) + (attack_legacy * 0.22), 0.002, 1.80)
        decay_s = self._adsr_time_seconds(float(params.get("aeg_decay", 0.28) or 0.28), 0.020, 2.80)
        sustain = float(np.clip(params.get("aeg_sustain", 0.78) or 0.78, 0.0, 1.0))
        release_mix = (float(params.get("aeg_release", 0.46) or 0.46) * 0.70) + (float(params.get("release", 0.42) or 0.42) * 0.30)
        release_s = self._adsr_time_seconds(release_mix, 0.030, 4.50)
        env = self._adsr_block(voice, frames, sr, attack_s, decay_s, sustain, release_s, getattr(voice, "amp_release_level", 1.0))
        return env.astype(np.float32, copy=False)

    def _filter_envelope(self, voice: AeternaVoice, frames: int, sr: int, params: dict) -> np.ndarray:
        attack_s = self._adsr_time_seconds(float(params.get("feg_attack", 0.04) or 0.04), 0.001, 1.20)
        decay_s = self._adsr_time_seconds(float(params.get("feg_decay", 0.22) or 0.22), 0.010, 2.20)
        sustain = float(np.clip(params.get("feg_sustain", 0.58) or 0.58, 0.0, 1.0))
        release_s = self._adsr_time_seconds(float(params.get("feg_release", 0.34) or 0.34), 0.015, 3.20)
        env = self._adsr_block(voice, frames, sr, attack_s, decay_s, sustain, release_s, getattr(voice, "filter_release_level", 1.0))
        return env.astype(np.float64, copy=False)

    def _release_samples(self, sr: int, params: dict) -> int:
        rel_mix = (float(params.get("aeg_release", 0.46) or 0.46) * 0.70) + (float(params.get("release", 0.42) or 0.42) * 0.30)
        rel = self._adsr_time_seconds(rel_mix, 0.030, 4.50)
        return max(64, int(rel * sr))

    def _gate_release_samples(self) -> int:
        return max(64, int(self.target_sr * 0.035))

    def _apply_space(self, left: np.ndarray, right: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
        wet = float(params.get("space", 0.30) or 0.30)
        cathedral = float(params.get("cathedral", 0.34) or 0.34)
        if wet <= 1e-4 and cathedral <= 1e-4:
            return left, right
        frames = int(left.shape[0])
        feedback = np.float32(0.18 + cathedral * 0.55)
        blend = np.float32(wet * 0.32 + cathedral * 0.28)
        pos = self._delay_pos
        dlen = self._delay_len
        indices = (np.arange(frames, dtype=np.int32) + pos) % dlen
        dl = self._delay_l[indices].copy()
        dr = self._delay_r[indices].copy()
        self._delay_l[indices] = left.astype(np.float32, copy=False) + dr * feedback
        self._delay_r[indices] = right.astype(np.float32, copy=False) + dl * feedback
        self._delay_pos = int((pos + frames) % dlen)
        return left + dl * blend, right + dr * blend

    def _one_pole_lowpass(self, x: np.ndarray, alpha: float) -> np.ndarray:
        a = float(max(0.001, min(0.999, alpha)))
        try:
            from scipy.signal import lfilter
            return lfilter([a], [1.0, -(1.0 - a)], x).astype(x.dtype, copy=False)
        except ImportError:
            pass
        n = max(1, int(1.0 / a))
        if n >= len(x):
            return x * a
        kernel = np.full(n, 1.0 / n, dtype=np.float64)
        padded = np.concatenate([np.zeros(n - 1, dtype=x.dtype), x])
        return np.convolve(padded, kernel, mode='valid')[:len(x)].astype(x.dtype, copy=False)

    def _logistic_block(self, voice: AeternaVoice, frames: int, r: float) -> np.ndarray:
        x = float(min(0.99, max(0.01, voice.chaos_state)))
        rr = float(min(3.99, max(2.50, r)))
        seed = int((x * 1e9 + rr * 1e6) % (2**31))
        rng = np.random.default_rng(seed)
        base = rng.uniform(0.05, 0.95, frames).astype(np.float64)
        out = rr * base * (1.0 - base)
        out = np.clip(out, 0.01, 0.99)
        voice.chaos_state = float(out[-1])
        return out

    def _polyblep(self, t: np.ndarray, dt: np.ndarray) -> np.ndarray:
        out = np.zeros_like(t, dtype=np.float64)
        dt = np.clip(dt, 1e-6, 0.49)
        left = t < dt
        if np.any(left):
            x = t[left] / dt[left]
            out[left] = x + x - x * x - 1.0
        right = t > (1.0 - dt)
        if np.any(right):
            x = (t[right] - 1.0) / dt[right]
            out[right] = x * x + x + x + 1.0
        return out

    def _polyblep_saw(self, freq: np.ndarray, phase: np.ndarray, sr: int) -> np.ndarray:
        t = np.mod(phase / TWOPI, 1.0)
        dt = np.clip(freq / float(max(1, sr)), 1e-6, 0.45)
        y = (2.0 * t) - 1.0
        y -= self._polyblep(t, dt)
        return y

    def _polyblep_square(self, freq: np.ndarray, phase: np.ndarray, sr: int, duty: float | np.ndarray = 0.5) -> np.ndarray:
        t = np.mod(phase / TWOPI, 1.0)
        dt = np.clip(freq / float(max(1, sr)), 1e-6, 0.45)
        duty_arr = np.clip(np.asarray(duty, dtype=np.float64), 0.05, 0.95)
        y = np.where(t < duty_arr, 1.0, -1.0)
        y += self._polyblep(t, dt)
        t2 = np.mod(t - duty_arr, 1.0)
        y -= self._polyblep(t2, dt)
        return y

    # ---------- formula parsing
    def _normalize_formula_aliases(self, formula: str) -> str:
        txt = str(formula or DEFAULT_FORMULA)
        replacements = {
            "$NOTE": "note_hz",
            "$VEL": "vel",
            "$T_REMAINING": "t_rem",
            "$T_REM": "t_rem",
            "$GLITCH": "glitch",
            "$LFO1": "lfo1",
            "$LFO2": "lfo2",
            "$MSEG": "mseg",
            "$CHAOS": "chaos_src",
            "$ENV": "env",
            "$PHASE": "phase",
        }
        for src, dst in replacements.items():
            txt = txt.replace(src, dst)
        txt = re.sub(r"\brandom\s*\(\s*\)", "rand(t)", txt)
        txt = re.sub(r"\brandom\s*\(", "rand(", txt)
        return txt

    def _formula_rand(self, seed_like=None):
        arr = np.asarray(seed_like if seed_like is not None else 0.0, dtype=np.float64)
        val = np.sin(arr * 12.9898 + 78.233) * 43758.5453
        frac = val - np.floor(val)
        return (frac * 2.0) - 1.0

    def _extract_formula_tokens(self, formula: str) -> list[str]:
        txt = self._normalize_formula_aliases(formula).lower()
        out: list[str] = []
        for key in ("note_hz", "vel", "t_rem", "glitch", "lfo1", "lfo2", "mseg", "chaos_src", "env", "phase"):
            if re.search(rf"\b{re.escape(key)}\b", txt):
                out.append(key)
        return out

    def _validate_formula(self, formula: str) -> bool:
        try:
            normalized = self._normalize_formula_aliases(formula)
            expr = ast.parse(normalized, mode="eval")
            for node in ast.walk(expr):
                if not isinstance(node, _ALLOWED_NODES):
                    return False
                if isinstance(node, ast.Call):
                    if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                        return False
                elif isinstance(node, ast.Name):
                    if node.id not in _ALLOWED_FUNCS and node.id not in _ALLOWED_CONSTS and node.id not in {
                        "t", "phase", "p", "f", "note_hz", "vel", "m", "c", "d", "motion", "x", "env",
                        "lfo1", "lfo2", "mseg", "chaos_src", "t_rem", "glitch"
                    }:
                        return False
            return True
        except Exception:
            return False

    def _eval_formula(self, formula: str, variables: dict) -> np.ndarray:
        if not self._formula_ok:
            return np.sin(variables["phase"]).astype(np.float64, copy=False)
        normalized = self._normalize_formula_aliases(formula)
        # Cache compiled code — avoid compile()+ast.parse() per audio block
        compiled = getattr(self, '_formula_cache', {}).get(normalized)
        if compiled is None:
            if not self._validate_formula(formula):
                self._formula_ok = False
                return np.sin(variables["phase"]).astype(np.float64, copy=False)
            try:
                compiled = compile(ast.parse(normalized, mode="eval"), "<aeterna_formula>", "eval")
                if not hasattr(self, '_formula_cache'):
                    self._formula_cache = {}
                self._formula_cache[normalized] = compiled
                if len(self._formula_cache) > 16:
                    self._formula_cache.pop(next(iter(self._formula_cache)))
            except Exception:
                self._formula_ok = False
                return np.sin(variables["phase"]).astype(np.float64, copy=False)
        env = {k: v for k, v in _ALLOWED_FUNCS.items() if callable(v)}
        env["rand"] = self._formula_rand
        env.update(_ALLOWED_CONSTS)
        env.update(variables)
        try:
            out = eval(compiled, {"__builtins__": {}}, env)  # noqa: S307
            self._formula_ok = True
            return np.asarray(out, dtype=np.float64)
        except Exception:
            self._formula_ok = False
            return np.sin(variables["phase"]).astype(np.float64, copy=False)
