"""Fusion Widget — PyQt6 UI for the ChronoScale Fusion synthesizer.

v0.0.20.574: Phase 3 — Full UI with:
  - OSC/FLT/ENV module dropdown selectors
  - Dynamic parameter knobs per module
  - Sub oscillator, Noise, HP, Global controls
  - FEG (Filter Envelope) section
  - Preset management (Save/Load)
  - Automation + MIDI Learn on all knobs (via CompactKnob)
  - Pull-source registration for live MIDI preview

Interface: project_service, audio_engine, automation_manager (same as BachOrgel/AETERNA)
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QPushButton, QFrame, QSlider, QSpinBox, QMenu,
    QFileDialog, QInputDialog, QSizePolicy,
)

from pydaw.plugins.sampler.ui_widgets import CompactKnob
from .fusion_engine import FusionEngine


# ═══════════════════════════════════════════════════════════
#  Module display names + available types
# ═══════════════════════════════════════════════════════════

_OSC_TYPES = [
    ("sine", "Sine"),
    ("triangle", "Triangle"),
    ("pulse", "Pulse"),
    ("saw", "Saw"),
    ("union", "Union"),
    ("phase-1", "Phase-1"),
    ("swarm", "Swarm"),
    ("bite", "Bite"),
    ("wavetable", "Wavetable"),
    ("scrawl", "Scrawl ✏️"),
]

_FLT_TYPES = [
    ("svf", "SVF"),
    ("ladder", "Low-pass LD"),
    ("comb", "Comb"),
]

_ENV_TYPES = [
    ("adsr", "ADSR"),
    ("ar", "AR"),
    ("ad", "AD"),
    ("pluck", "Pluck"),
]

# Per-oscillator additional params (beyond base pitch/octave)
_OSC_EXTRA_PARAMS = {
    "sine":     [("skew", "Skew", -100, 100, 0), ("fold", "Fold", 0, 100, 0)],
    "triangle": [("skew", "Skew", -100, 100, 0), ("fold", "Fold", 0, 100, 0)],
    "pulse":    [("width", "Width", 1, 99, 50)],
    "saw":      [],
    "union":    [("shape", "Shape", -100, 100, 0), ("sub_level", "Sub", 0, 100, 0)],
    "phase-1":  [("algorithm", "Algo", 0, 4, 0), ("amount", "Amount", 0, 100, 50),
                 ("feedback", "FB", 0, 100, 0)],
    "swarm":    [("voices", "Voices", 1, 8, 8), ("spread", "Spread", 0, 100, 50)],
    "bite":     [("mode", "Mode", 0, 3, 0), ("ratio_b", "Ratio", 50, 1600, 100),
                 ("mix_a", "Mix A", 0, 100, 100), ("mix_b", "Mix B", 0, 100, 0),
                 ("mix_rm", "Ring", 0, 100, 0)],
    "wavetable": [("index", "Index", 0, 100, 0),
                  ("unison_mode", "Uni Mode", 0, 3, 0),
                  ("unison_voices", "Uni Vox", 1, 16, 1),
                  ("unison_spread", "Uni Sprd", 0, 100, 50)],
    "scrawl":   [("smooth", "Smooth", 0, 1, 1)],
}

_FLT_EXTRA_PARAMS = {
    "svf":    [("mode", "Mode", 0, 2, 0)],
    "ladder": [],
    "comb":   [("feedback", "FB", -100, 100, 50), ("damp_freq", "Damp", 200, 20000, 8000)],
}

_ENV_EXTRA_PARAMS = {
    "adsr":  [("model", "Model", 0, 2, 0)],
    "ar":    [("curve", "Curve", -100, 100, 0)],
    "ad":    [("loop", "Loop", 0, 1, 0)],
    "pluck": [("brightness", "Bright", 0, 100, 50)],
}


class FusionWidget(QWidget):
    """ChronoScale Fusion synthesizer UI."""

    PLUGIN_STATE_KEY = "fusion"

    def __init__(self, project_service=None, audio_engine=None,
                 automation_manager=None, parent=None):
        super().__init__(parent)
        self.project_service = project_service
        self.audio_engine = audio_engine
        self.automation_manager = automation_manager

        self.track_id: Optional[str] = None
        self._restoring_state = False
        self._automation_setup_done = False
        self._automation_mgr_connected = False
        self._automation_pid_to_engine: dict[str, callable] = {}
        self._state_persist_timer = QTimer(self)
        self._state_persist_timer.setSingleShot(True)
        self._state_persist_timer.setInterval(120)
        self._state_persist_timer.timeout.connect(self._persist_instrument_state)

        # v0.0.20.580: Fusion-only MIDI-CC UI coalescing.
        # Incoming CC floods should not repaint/update the full widget tree
        # hundreds of times per second. We queue the latest CC value per knob
        # and apply it on a ~60 Hz timer without touching CompactKnob globally.
        self._midi_cc_flush_timer = QTimer(self)
        self._midi_cc_flush_timer.setSingleShot(True)
        self._midi_cc_flush_timer.setInterval(16)
        self._midi_cc_flush_timer.timeout.connect(self._flush_coalesced_midi_cc_updates)
        self._pending_midi_cc_values: dict[int, tuple[CompactKnob, int]] = {}

        # DSP engine
        sr = 48000
        try:
            if self.audio_engine is not None:
                sr = int(self.audio_engine.get_effective_sample_rate())
        except Exception:
            sr = 48000
        self.engine = FusionEngine(target_sr=sr)

        # Pull source
        self._pull_name: Optional[str] = None
        def _pull(frames: int, sr: int, _eng=self.engine):
            return _eng.pull(frames, sr)
        _pull._pydaw_track_id = lambda: (self.track_id or '')
        self._pull_fn = _pull

        # UI state
        self._knobs: dict[str, CompactKnob] = {}
        self._osc_dynamic_keys: set[str] = set()
        self._flt_dynamic_keys: set[str] = set()
        self._env_dynamic_keys: set[str] = set()
        self._osc_extra_container: Optional[QWidget] = None
        self._flt_extra_container: Optional[QWidget] = None
        self._env_extra_container: Optional[QWidget] = None
        self._current_osc = "sine"
        self._current_flt = "svf"
        self._current_env = "adsr"

        self._build_ui()
        self._apply_styles()

    # ════════════════════════════════════════════════
    #  Lifecycle
    # ════════════════════════════════════════════════

    def set_track_context(self, track_id: str) -> None:
        self.track_id = str(track_id or '')
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
                self._pull_name = f"fusion:{self.track_id}:{id(self) & 0xFFFF:04x}"
                self.audio_engine.register_pull_source(self._pull_name, self._pull_fn)
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass
        self._restore_instrument_state()
        self._setup_automation()

    def shutdown(self) -> None:
        try:
            if self._midi_cc_flush_timer.isActive():
                self._midi_cc_flush_timer.stop()
                self._flush_coalesced_midi_cc_updates()
        except Exception:
            pass
        try:
            if self._state_persist_timer.isActive():
                self._state_persist_timer.stop()
                self._persist_instrument_state()
        except Exception:
            pass
        try:
            if self.audio_engine is not None and self._pull_name is not None:
                self.audio_engine.unregister_pull_source(self._pull_name)
        except Exception:
            pass
        self._pull_name = None
        try:
            if self.track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                reg = get_sampler_registry()
                reg.unregister(self.track_id)
        except Exception:
            pass
        try:
            self.engine.all_notes_off()
        except Exception:
            pass

    # ════════════════════════════════════════════════
    #  UI Construction
    # ════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        # ── Top row: OSC | FLT | ENV selectors ──
        top = QHBoxLayout()
        top.setSpacing(8)

        # OSC Section
        osc_frame = self._section_frame("OSC", "#FFB74D")
        osc_lay = QVBoxLayout(osc_frame)
        osc_lay.setContentsMargins(6, 4, 6, 4)
        osc_lay.setSpacing(3)
        self._cmb_osc = QComboBox()
        for key, name in _OSC_TYPES:
            self._cmb_osc.addItem(name, key)
        self._cmb_osc.currentIndexChanged.connect(self._on_osc_changed)
        osc_lay.addWidget(self._cmb_osc)

        # OSC base knobs
        osc_base = QHBoxLayout()
        self._knobs["osc.pitch_st"] = self._make_knob("Pitch", -7, 7, 0)
        osc_base.addWidget(self._knobs["osc.pitch_st"])
        self._knobs["osc.phase_mod"] = self._make_knob("PM", 0, 100, 0)
        osc_base.addWidget(self._knobs["osc.phase_mod"])
        self._knobs["osc.detune_stereo"] = self._make_knob("Detune", -100, 100, 0)
        osc_base.addWidget(self._knobs["osc.detune_stereo"])
        osc_lay.addLayout(osc_base)

        # OSC extra params (dynamic)
        self._osc_extra_container = QWidget()
        self._osc_extra_layout = QHBoxLayout(self._osc_extra_container)
        self._osc_extra_layout.setContentsMargins(0, 0, 0, 0)
        self._osc_extra_layout.setSpacing(2)
        osc_lay.addWidget(self._osc_extra_container)
        top.addWidget(osc_frame, 2)

        # FLT Section
        flt_frame = self._section_frame("FILTER", "#4FC3F7")
        flt_lay = QVBoxLayout(flt_frame)
        flt_lay.setContentsMargins(6, 4, 6, 4)
        flt_lay.setSpacing(3)
        self._cmb_flt = QComboBox()
        for key, name in _FLT_TYPES:
            self._cmb_flt.addItem(name, key)
        self._cmb_flt.currentIndexChanged.connect(self._on_flt_changed)
        flt_lay.addWidget(self._cmb_flt)

        flt_base = QHBoxLayout()
        self._knobs["flt.cutoff"] = self._make_knob("Cutoff", 0, 100, 80)
        flt_base.addWidget(self._knobs["flt.cutoff"])
        self._knobs["flt.resonance"] = self._make_knob("Reso", 0, 100, 0)
        flt_base.addWidget(self._knobs["flt.resonance"])
        self._knobs["flt.drive"] = self._make_knob("Drive", 0, 100, 0)
        flt_base.addWidget(self._knobs["flt.drive"])
        self._knobs["flt.env_amount"] = self._make_knob("Env", -100, 100, 50)
        flt_base.addWidget(self._knobs["flt.env_amount"])
        flt_lay.addLayout(flt_base)

        self._flt_extra_container = QWidget()
        self._flt_extra_layout = QHBoxLayout(self._flt_extra_container)
        self._flt_extra_layout.setContentsMargins(0, 0, 0, 0)
        self._flt_extra_layout.setSpacing(2)
        flt_lay.addWidget(self._flt_extra_container)
        top.addWidget(flt_frame, 2)

        # ENV Section
        env_frame = self._section_frame("AMP ENV", "#81C784")
        env_lay = QVBoxLayout(env_frame)
        env_lay.setContentsMargins(6, 4, 6, 4)
        env_lay.setSpacing(3)
        self._cmb_env = QComboBox()
        for key, name in _ENV_TYPES:
            self._cmb_env.addItem(name, key)
        self._cmb_env.currentIndexChanged.connect(self._on_env_changed)
        env_lay.addWidget(self._cmb_env)

        env_base = QHBoxLayout()
        self._knobs["aeg.attack"] = self._make_knob("A", 0, 100, 2)
        env_base.addWidget(self._knobs["aeg.attack"])
        self._knobs["aeg.decay"] = self._make_knob("D", 0, 100, 20)
        env_base.addWidget(self._knobs["aeg.decay"])
        self._knobs["aeg.sustain"] = self._make_knob("S", 0, 100, 70)
        env_base.addWidget(self._knobs["aeg.sustain"])
        self._knobs["aeg.release"] = self._make_knob("R", 0, 100, 30)
        env_base.addWidget(self._knobs["aeg.release"])
        env_lay.addLayout(env_base)

        self._env_extra_container = QWidget()
        self._env_extra_layout = QHBoxLayout(self._env_extra_container)
        self._env_extra_layout.setContentsMargins(0, 0, 0, 0)
        self._env_extra_layout.setSpacing(2)
        env_lay.addWidget(self._env_extra_container)
        top.addWidget(env_frame, 2)

        root.addLayout(top)

        # ── Scrawl/Wavetable editor area (hidden unless active) ──
        self._editor_area = QWidget()
        self._editor_area.setVisible(False)
        self._editor_area_layout = QVBoxLayout(self._editor_area)
        self._editor_area_layout.setContentsMargins(0, 0, 0, 0)
        self._editor_area_layout.setSpacing(0)
        root.addWidget(self._editor_area)

        # Scrawl editor (lazy-created on first use)
        self._scrawl_editor = None
        # Wavetable loader (lazy-created on first use)
        self._wt_loader = None

        # ── Middle row: SUB | NOISE | FEG | Global ──
        mid = QHBoxLayout()
        mid.setSpacing(6)

        # Sub Oscillator
        sub_frame = self._section_frame("SUB", "#9E9E9E")
        sub_lay = QHBoxLayout(sub_frame)
        sub_lay.setContentsMargins(4, 4, 4, 4)
        self._knobs["sub_level"] = self._make_knob("Level", 0, 100, 0)
        sub_lay.addWidget(self._knobs["sub_level"])
        self._knobs["sub_width"] = self._make_knob("Width", 1, 99, 50)
        sub_lay.addWidget(self._knobs["sub_width"])
        mid.addWidget(sub_frame, 1)

        # Noise
        noise_frame = self._section_frame("NOISE", "#9E9E9E")
        noise_lay = QHBoxLayout(noise_frame)
        noise_lay.setContentsMargins(4, 4, 4, 4)
        self._knobs["noise_level"] = self._make_knob("Level", 0, 100, 0)
        noise_lay.addWidget(self._knobs["noise_level"])
        mid.addWidget(noise_frame, 1)

        # FEG (Filter Envelope)
        feg_frame = self._section_frame("FEG", "#CE93D8")
        feg_lay = QHBoxLayout(feg_frame)
        feg_lay.setContentsMargins(4, 4, 4, 4)
        for p, label, default in [("feg.attack", "A", 2), ("feg.decay", "D", 30),
                                   ("feg.sustain", "S", 50), ("feg.release", "R", 50)]:
            self._knobs[p] = self._make_knob(label, 0, 100, default)
            feg_lay.addWidget(self._knobs[p])
        mid.addWidget(feg_frame, 2)

        # Global
        global_frame = self._section_frame("OUTPUT", "#607D8B")
        global_lay = QHBoxLayout(global_frame)
        global_lay.setContentsMargins(4, 4, 4, 4)
        self._knobs["gain"] = self._make_knob("Gain", 0, 100, 50)
        global_lay.addWidget(self._knobs["gain"])
        self._knobs["pan"] = self._make_knob("Pan", -100, 100, 0)
        global_lay.addWidget(self._knobs["pan"])
        self._knobs["output"] = self._make_knob("Out", 0, 100, 50)
        global_lay.addWidget(self._knobs["output"])
        mid.addWidget(global_frame, 1)

        root.addLayout(mid)

        # ── Bottom row: Presets ──
        preset_row = QHBoxLayout()
        self._preset_combo = QComboBox()
        self._preset_combo.addItem("(Init)")
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self._preset_combo, 1)

        btn_save = QPushButton("💾")
        btn_save.setFixedSize(28, 24)
        btn_save.setToolTip("Preset speichern")
        btn_save.clicked.connect(self._save_preset)
        preset_row.addWidget(btn_save)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedSize(28, 24)
        btn_refresh.setToolTip("Presets aktualisieren")
        btn_refresh.clicked.connect(self._refresh_presets)
        preset_row.addWidget(btn_refresh)

        btn_rnd = QPushButton("RND")
        btn_rnd.setFixedSize(40, 24)
        btn_rnd.setToolTip("Zufällige Parameter")
        btn_rnd.clicked.connect(self._randomize)
        preset_row.addWidget(btn_rnd)

        root.addLayout(preset_row)

        # Init extra param areas
        self._rebuild_osc_extras()
        self._rebuild_flt_extras()
        self._rebuild_env_extras()

        # Wire all knobs to engine
        for key, knob in self._knobs.items():
            knob.valueChanged.connect(lambda _v, _k=key: self._on_knob_changed(_k))

        QTimer.singleShot(100, self._refresh_presets)

    # ════════════════════════════════════════════════
    #  Helpers
    # ════════════════════════════════════════════════

    def _section_frame(self, title: str, color: str) -> QFrame:
        f = QFrame()
        f.setObjectName(f"fusion_section_{title.lower().replace(' ', '_')}")
        f.setFrameShape(QFrame.Shape.StyledPanel)
        f.setStyleSheet(
            f"QFrame#{f.objectName()} {{ border: 1px solid {color}; "
            f"border-radius: 4px; }}"
        )
        return f

    def _make_knob(self, title: str, lo: int = 0, hi: int = 100,
                    default: int = 50) -> CompactKnob:
        k = CompactKnob(title)
        try:
            k.setRange(int(lo), int(hi))
        except Exception:
            pass
        k.setValue(int(default))
        self._install_midi_cc_coalescing(k)
        return k

    def _bind_knob_automation(self, key: str, knob: CompactKnob) -> None:
        try:
            mgr = self.automation_manager
            tid = self.track_id or ''
            if mgr is None or not tid or knob is None:
                return
            pid = f'trk:{tid}:fusion:{key}'
            if getattr(knob, '_parameter_id', '') == pid:
                return
            lo = float(knob.minimum())
            hi = float(knob.maximum())
            knob.bind_automation(
                mgr, pid,
                name=f'Fusion {key}',
                track_id=tid,
                minimum=lo,
                maximum=hi,
                default=float(knob.value()),
            )
        except Exception:
            pass

    def _install_midi_cc_coalescing(self, knob: CompactKnob) -> None:
        """Fusion-only CC throttling without changing CompactKnob globally."""
        try:
            if knob is None or getattr(knob, '_fusion_cc_coalescing_installed', False):
                return
            original = getattr(knob, 'handle_midi_cc', None)
            if not callable(original):
                return
            knob._fusion_cc_coalescing_installed = True
            knob._fusion_original_handle_midi_cc = original

            def _queued_handle_midi_cc(value_0_127: int, _knob=knob, _self=self) -> None:
                _self._queue_coalesced_midi_cc_update(_knob, value_0_127)

            knob.handle_midi_cc = _queued_handle_midi_cc
        except Exception:
            pass

    def _queue_coalesced_midi_cc_update(self, knob: CompactKnob, value_0_127: int) -> None:
        try:
            knob_id = id(knob)
            self._pending_midi_cc_values[knob_id] = (_knob := knob, int(value_0_127))
            if not self._midi_cc_flush_timer.isActive():
                self._midi_cc_flush_timer.start()
        except Exception:
            try:
                original = getattr(knob, '_fusion_original_handle_midi_cc', None)
                if callable(original):
                    original(int(value_0_127))
            except Exception:
                pass

    def _drop_coalesced_midi_cc_update(self, knob: CompactKnob | None) -> None:
        try:
            if knob is None:
                return
            self._pending_midi_cc_values.pop(id(knob), None)
        except Exception:
            pass

    def _flush_coalesced_midi_cc_updates(self) -> None:
        try:
            pending = list(self._pending_midi_cc_values.values())
            self._pending_midi_cc_values.clear()
            for knob, value_0_127 in pending:
                try:
                    original = getattr(knob, '_fusion_original_handle_midi_cc', None)
                    if callable(original):
                        original(int(value_0_127))
                except Exception:
                    pass
        finally:
            try:
                if self._pending_midi_cc_values and not self._midi_cc_flush_timer.isActive():
                    self._midi_cc_flush_timer.start()
            except Exception:
                pass

    # ════════════════════════════════════════════════
    #  Module Switching
    # ════════════════════════════════════════════════

    def _on_osc_changed(self, idx: int) -> None:
        key = self._cmb_osc.currentData()
        if key and key != self._current_osc:
            self._current_osc = key
            self.engine.set_oscillator(key)
            self._rebuild_osc_extras()
            self._persist_instrument_state()

    def _on_flt_changed(self, idx: int) -> None:
        key = self._cmb_flt.currentData()
        if key and key != self._current_flt:
            self._current_flt = key
            self.engine.set_filter(key)
            self._rebuild_flt_extras()
            self._persist_instrument_state()

    def _on_env_changed(self, idx: int) -> None:
        key = self._cmb_env.currentData()
        if key and key != self._current_env:
            self._current_env = key
            self.engine.set_envelope(key)
            self._rebuild_env_extras()
            self._persist_instrument_state()

    def _rebuild_osc_extras(self) -> None:
        for key in list(self._osc_dynamic_keys):
            old = self._knobs.pop(key, None)
            self._drop_coalesced_midi_cc_update(old)
            try:
                if old is not None and hasattr(old, '_remove_midi_cc_listener'):
                    old._remove_midi_cc_listener()
            except Exception:
                pass
        self._osc_dynamic_keys.clear()
        self._clear_layout(self._osc_extra_layout)
        params = _OSC_EXTRA_PARAMS.get(self._current_osc, [])
        for pname, label, lo, hi, default in params:
            key = f"osc.{pname}"
            k = self._make_knob(label, lo, hi, default)
            self._knobs[key] = k
            self._osc_dynamic_keys.add(key)
            k.valueChanged.connect(lambda _v, _k=key: self._on_knob_changed(_k))
            self._bind_knob_automation(key, k)
            self._osc_extra_layout.addWidget(k)

        # v0.0.20.576: Show/hide Scrawl editor or Wavetable loader
        self._clear_layout(self._editor_area_layout)
        if self._scrawl_editor is not None:
            self._scrawl_editor.setParent(None)
            self._scrawl_editor = None
        if self._wt_loader is not None:
            self._wt_loader.setParent(None)
            self._wt_loader = None

        if self._current_osc == "scrawl":
            try:
                from .scrawl_editor import ScrawlEditorWidget
                self._scrawl_editor = ScrawlEditorWidget()
                self._scrawl_editor.waveform_changed.connect(self._on_scrawl_points_changed)
                self._editor_area_layout.addWidget(self._scrawl_editor)
                self._editor_area.setVisible(True)
                # Sync initial waveform display
                self._sync_scrawl_display()
            except Exception as exc:
                import sys
                print(f"[Fusion] Scrawl editor failed: {exc}", file=sys.stderr)
                self._editor_area.setVisible(False)

        elif self._current_osc == "wavetable":
            try:
                wt_row = QWidget()
                wt_lay = QHBoxLayout(wt_row)
                wt_lay.setContentsMargins(4, 2, 4, 2)
                wt_lay.setSpacing(4)
                lbl = QLabel("📂")
                lbl.setStyleSheet("font-size: 14px;")
                wt_lay.addWidget(lbl)
                self._wt_name_label = QLabel("(Default Sine→Saw)")
                self._wt_name_label.setStyleSheet("color: #FFB74D; font-size: 10px;")
                wt_lay.addWidget(self._wt_name_label, 1)
                btn_load = QPushButton("Load .wt / .wav")
                btn_load.setFixedHeight(22)
                btn_load.setStyleSheet(
                    "font-size: 9px; padding: 2px 8px; border: 1px solid #FFB74D; "
                    "border-radius: 3px; color: #FFB74D;"
                )
                btn_load.clicked.connect(self._load_wavetable_file)
                wt_lay.addWidget(btn_load)
                self._wt_loader = wt_row
                self._editor_area_layout.addWidget(wt_row)
                self._editor_area.setVisible(True)
            except Exception:
                self._editor_area.setVisible(False)
        else:
            self._editor_area.setVisible(False)

    def _on_scrawl_points_changed(self, points: list) -> None:
        """Called when user draws/edits in the Scrawl canvas."""
        try:
            smooth = self._scrawl_editor.is_smooth() if self._scrawl_editor else True
            self._apply_scrawl_state(points, smooth, sync_editor=False)
            if not self._restoring_state:
                self._schedule_persist_instrument_state()
        except Exception:
            pass

    def _apply_scrawl_state(self, points: list | None, smooth: bool = True,
                             sync_editor: bool = True) -> None:
        """Apply Scrawl waveform state to engine, active voices and optional editor."""
        try:
            normalized = []
            for item in (points or []):
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                normalized.append((float(item[0]), float(item[1])))
            self.engine._scrawl_points = normalized
            self.engine._scrawl_smooth = bool(smooth)

            table_source = None
            for v in getattr(self.engine, '_voices', []):
                osc = getattr(v, 'osc', None)
                if hasattr(osc, 'set_points'):
                    try:
                        osc.set_points(normalized)
                        osc.set_param("smooth", 1.0 if smooth else 0.0)
                        table_source = osc
                    except Exception:
                        pass

            if sync_editor and self._scrawl_editor is not None:
                try:
                    self._scrawl_editor.blockSignals(True)
                    self._scrawl_editor.set_points(normalized)
                    chk = getattr(self._scrawl_editor, '_chk_smooth', None)
                    if chk is not None:
                        chk.blockSignals(True)
                        chk.setChecked(bool(smooth))
                        chk.blockSignals(False)
                finally:
                    try:
                        self._scrawl_editor.blockSignals(False)
                    except Exception:
                        pass

                try:
                    if table_source is None:
                        from .oscillators.scrawl import ScrawlOscillator
                        table_source = ScrawlOscillator()
                        if normalized:
                            table_source.set_points(normalized)
                        table_source.set_param("smooth", 1.0 if smooth else 0.0)
                    tbl = table_source.get_table_for_display(256)
                    if tbl is not None:
                        self._scrawl_editor.set_display_table(tbl)
                except Exception:
                    pass
        except Exception:
            pass

    def _sync_scrawl_display(self) -> None:
        """Sync Scrawl editor display with engine state."""
        try:
            if self._scrawl_editor is None:
                return
            if getattr(self.engine, '_scrawl_points', None):
                self._apply_scrawl_state(
                    self.engine._scrawl_points,
                    getattr(self.engine, '_scrawl_smooth', True),
                    sync_editor=True,
                )
                return
            for v in self.engine._voices:
                osc = v.osc
                if hasattr(osc, 'get_points'):
                    pts = osc.get_points()
                    self._apply_scrawl_state(
                        pts,
                        bool(getattr(self.engine, '_scrawl_smooth', True)),
                        sync_editor=True,
                    )
                    return
            # No active voice — create a temp oscillator for defaults
            from .oscillators.scrawl import ScrawlOscillator
            tmp = ScrawlOscillator()
            self._apply_scrawl_state(
                tmp.get_points(),
                bool(getattr(self.engine, '_scrawl_smooth', True)),
                sync_editor=True,
            )
        except Exception:
            pass

    def _load_wavetable_file(self) -> None:
        """Open file dialog to load a .wt or .wav wavetable."""
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "Wavetable laden",
                os.path.expanduser("~"),
                "Wavetable Files (*.wt *.wav);;All Files (*)"
            )
            if not path:
                return
            loaded = False
            # Load into engine's wavetable
            for v in self.engine._voices:
                osc = v.osc
                if hasattr(osc, 'load_file'):
                    ok = osc.load_file(path)
                    if ok:
                        loaded = True
                        if hasattr(self, '_wt_name_label'):
                            self._wt_name_label.setText(osc.get_table_name())
                    break
            # Store path so new voices can load it too
            self.engine._wt_file_path = path if loaded or os.path.isfile(path) else ""
            if self.engine._wt_file_path and not self._restoring_state:
                self._schedule_persist_instrument_state()
        except Exception:
            pass

    def _rebuild_flt_extras(self) -> None:
        for key in list(self._flt_dynamic_keys):
            old = self._knobs.pop(key, None)
            self._drop_coalesced_midi_cc_update(old)
            try:
                if old is not None and hasattr(old, '_remove_midi_cc_listener'):
                    old._remove_midi_cc_listener()
            except Exception:
                pass
        self._flt_dynamic_keys.clear()
        self._clear_layout(self._flt_extra_layout)
        params = _FLT_EXTRA_PARAMS.get(self._current_flt, [])
        for pname, label, lo, hi, default in params:
            key = f"flt.{pname}"
            k = self._make_knob(label, lo, hi, default)
            self._knobs[key] = k
            self._flt_dynamic_keys.add(key)
            k.valueChanged.connect(lambda _v, _k=key: self._on_knob_changed(_k))
            self._bind_knob_automation(key, k)
            self._flt_extra_layout.addWidget(k)

    def _rebuild_env_extras(self) -> None:
        for key in list(self._env_dynamic_keys):
            old = self._knobs.pop(key, None)
            self._drop_coalesced_midi_cc_update(old)
            try:
                if old is not None and hasattr(old, '_remove_midi_cc_listener'):
                    old._remove_midi_cc_listener()
            except Exception:
                pass
        self._env_dynamic_keys.clear()
        self._clear_layout(self._env_extra_layout)
        params = _ENV_EXTRA_PARAMS.get(self._current_env, [])
        for pname, label, lo, hi, default in params:
            key = f"aeg.{pname}"
            k = self._make_knob(label, lo, hi, default)
            self._knobs[key] = k
            self._env_dynamic_keys.add(key)
            k.valueChanged.connect(lambda _v, _k=key: self._on_knob_changed(_k))
            self._bind_knob_automation(key, k)
            self._env_extra_layout.addWidget(k)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ════════════════════════════════════════════════
    #  Knob → Engine
    # ════════════════════════════════════════════════

    def _on_knob_changed(self, key: str) -> None:
        knob = self._knobs.get(key)
        if knob is None:
            return
        raw = float(knob.value())

        # Scale knob values to engine ranges
        if key == "flt.cutoff":
            val = 20.0 + (raw / 100.0) ** 2.0 * 19980.0  # exponential scaling
        elif key == "flt.resonance":
            val = raw / 100.0
        elif key == "flt.drive":
            val = raw / 100.0
        elif key == "flt.env_amount":
            val = raw / 100.0  # -1..+1 from knob -100..+100
        elif key.startswith("flt."):
            pname = key.split(".", 1)[1]
            if pname == "mode":
                val = float(int(raw))
            elif pname == "feedback":
                val = raw / 100.0
            elif pname == "damp_freq":
                val = raw
            else:
                val = raw / 100.0
        elif key.startswith("aeg.") or key.startswith("feg."):
            pname = key.split(".", 1)[1]
            if pname in ("attack", "decay", "release"):
                val = (raw / 100.0) ** 2.0 * 10.0  # 0..10s exponential
            elif pname == "sustain":
                val = raw / 100.0
            elif pname == "vel_amount":
                val = raw / 100.0
            elif pname == "model":
                val = float(int(raw))
            elif pname == "loop":
                val = float(int(raw))
            elif pname == "brightness":
                val = raw / 100.0
            elif pname == "curve":
                val = raw / 100.0
            else:
                val = raw / 100.0
        elif key.startswith("osc."):
            pname = key.split(".", 1)[1]
            if pname == "pitch_st":
                val = raw
            elif pname == "phase_mod":
                val = raw / 100.0
            elif pname == "detune_stereo":
                val = raw
            elif pname == "algorithm":
                val = float(int(raw))
            elif pname == "amount":
                val = raw / 100.0
            elif pname == "feedback":
                val = raw / 100.0
            elif pname == "width":
                val = raw / 100.0
            elif pname == "shape":
                val = raw / 100.0
            elif pname == "spread":
                val = raw / 100.0
            elif pname == "voices":
                val = float(int(raw))
            elif pname == "mode":
                val = float(int(raw))
            elif pname == "index":
                val = raw / 100.0
            elif pname == "unison_mode":
                val = float(int(raw))
            elif pname == "unison_voices":
                val = float(int(raw))
            elif pname == "unison_spread":
                val = raw / 100.0
            elif pname == "smooth":
                val = float(int(raw))
            elif pname == "ratio_b":
                val = raw / 100.0
            elif pname in ("mix_a", "mix_b", "mix_rm", "sub_level", "skew", "fold"):
                val = raw / 100.0
            else:
                val = raw / 100.0
        elif key == "sub_level":
            val = raw / 100.0
        elif key == "sub_width":
            val = raw / 100.0
        elif key == "noise_level":
            val = raw / 100.0
        elif key == "gain":
            val = raw / 50.0  # 0..2.0
        elif key == "pan":
            val = raw / 100.0
        elif key == "output":
            val = raw / 50.0
        else:
            val = raw / 100.0

        self.engine.set_param(key, val)
        if not self._restoring_state:
            self._schedule_persist_instrument_state()

    def _capture_state_snapshot(self, *, flush_pending_midi_cc: bool = True) -> dict[str, Any]:
        """Return the current Fusion UI/engine state as a JSON-safe dict.

        v0.0.20.582: before we snapshot the state we optionally flush any
        Fusion-only queued MIDI-CC updates, so preset/project saves cannot miss
        the last coalesced knob move when the user saves during controller
        activity.
        """
        if flush_pending_midi_cc:
            try:
                if self._midi_cc_flush_timer.isActive():
                    self._midi_cc_flush_timer.stop()
                if self._pending_midi_cc_values:
                    self._flush_coalesced_midi_cc_updates()
            except Exception:
                pass
        return {
            "osc_type": self._current_osc,
            "flt_type": self._current_flt,
            "env_type": self._current_env,
            "knobs": {k: int(v.value()) for k, v in self._knobs.items()},
            "scrawl_points": [list(p) for p in getattr(self.engine, '_scrawl_points', [])],
            "scrawl_smooth": bool(getattr(self.engine, '_scrawl_smooth', True)),
            "wt_file_path": str(getattr(self.engine, '_wt_file_path', '') or ''),
        }

    # ════════════════════════════════════════════════
    #  State Persistence
    # ════════════════════════════════════════════════

    def _schedule_persist_instrument_state(self) -> None:
        """Coalesce rapid knob/MIDI updates into one project-state write.

        v0.0.20.579: Fusion-only GUI hotfix. Bach Orgel and other instruments
        stay untouched. Engine parameters still update immediately; only the
        expensive project/UI update path is debounced.
        """
        if self._restoring_state:
            return
        try:
            self._state_persist_timer.start()
        except Exception:
            self._persist_instrument_state()

    def _persist_instrument_state(self) -> None:
        if self._restoring_state:
            return
        try:
            ps = self.project_service
            if ps is None or not self.track_id:
                return
            proj = getattr(getattr(ps, 'ctx', None), 'project', None) if ps else None
            if proj is None:
                return
            trk = next((t for t in proj.tracks if t.id == self.track_id), None)
            if trk is None:
                return

            state = self._capture_state_snapshot()
            if not isinstance(getattr(trk, 'instrument_state', None), dict):
                trk.instrument_state = {}
            trk.instrument_state[self.PLUGIN_STATE_KEY] = state

            # v0.0.20.584: Do NOT call ps._emit_updated() here!
            # That triggers project_updated → 15+ UI panels do full refresh
            # (Arranger, Mixer, ClipLauncher, PianoRoll, TrackList, etc.)
            # just because a single Fusion knob moved.
            # The instrument_state is already persisted in the track object;
            # the global UI does not need to know about synth parameter changes.
        except Exception:
            pass

    def _restore_instrument_state(self) -> None:
        try:
            ps = self.project_service
            if ps is None or not self.track_id:
                return
            proj = getattr(getattr(ps, 'ctx', None), 'project', None) if ps else None
            if proj is None:
                return
            trk = next((t for t in proj.tracks if t.id == self.track_id), None)
            if trk is None:
                return
            ist = getattr(trk, 'instrument_state', None) or {}
            state = ist.get(self.PLUGIN_STATE_KEY)
            if not isinstance(state, dict):
                return

            self._restoring_state = True
            try:
                # Restore module types
                osc = state.get("osc_type", "sine")
                flt = state.get("flt_type", "svf")
                env = state.get("env_type", "adsr")

                idx = next((i for i, (k, _) in enumerate(_OSC_TYPES) if k == osc), 0)
                self._cmb_osc.setCurrentIndex(idx)
                self._current_osc = osc
                self.engine.set_oscillator(osc)
                self._rebuild_osc_extras()

                idx = next((i for i, (k, _) in enumerate(_FLT_TYPES) if k == flt), 0)
                self._cmb_flt.setCurrentIndex(idx)
                self._current_flt = flt
                self.engine.set_filter(flt)
                self._rebuild_flt_extras()

                idx = next((i for i, (k, _) in enumerate(_ENV_TYPES) if k == env), 0)
                self._cmb_env.setCurrentIndex(idx)
                self._current_env = env
                self.engine.set_envelope(env)
                self._rebuild_env_extras()

                # Restore knob values
                knobs_state = state.get("knobs", {})
                for k, v in knobs_state.items():
                    knob = self._knobs.get(k)
                    if knob is not None:
                        knob.blockSignals(True)
                        try:
                            knob.setValue(int(v))
                        finally:
                            knob.blockSignals(False)
                        # Push to engine
                        self._on_knob_changed(k)

                # Restore oscillator-specific extended state
                wt_file_path = str(state.get("wt_file_path", "") or "")
                self.engine._wt_file_path = wt_file_path if os.path.isfile(wt_file_path) else ""
                if self._current_osc == "wavetable" and hasattr(self, '_wt_name_label'):
                    self._wt_name_label.setText(os.path.basename(self.engine._wt_file_path) if self.engine._wt_file_path else "(Default Sine→Saw)")

                if self._current_osc == "scrawl":
                    self._apply_scrawl_state(
                        state.get("scrawl_points", []),
                        bool(state.get("scrawl_smooth", True)),
                        sync_editor=True,
                    )
            finally:
                self._restoring_state = False
        except Exception:
            self._restoring_state = False

    # ════════════════════════════════════════════════
    #  Automation
    # ════════════════════════════════════════════════

    def _setup_automation(self) -> None:
        try:
            if self._automation_setup_done:
                return
            mgr = self.automation_manager
            tid = self.track_id or ''
            if mgr is None or not tid:
                return
            self._automation_setup_done = True

            for key, knob in self._knobs.items():
                self._bind_knob_automation(key, knob)

            if not self._automation_mgr_connected:
                try:
                    mgr.parameter_changed.connect(self._on_automation_parameter_changed)
                    self._automation_mgr_connected = True
                except Exception:
                    pass
        except Exception:
            pass

    def _on_automation_parameter_changed(self, parameter_id: str, value: float) -> None:
        try:
            prefix = f'trk:{self.track_id or ""}:fusion:'
            if not str(parameter_id).startswith(prefix):
                return
            key = str(parameter_id)[len(prefix):]
            knob = self._knobs.get(key)
            if knob is not None:
                knob.blockSignals(True)
                try:
                    knob.setValue(int(round(float(value))))
                finally:
                    knob.blockSignals(False)
                self._on_knob_changed(key)
        except Exception:
            pass

    # ════════════════════════════════════════════════
    #  Presets
    # ════════════════════════════════════════════════

    def _preset_dir(self) -> str:
        d = Path.home() / ".config" / "ChronoScaleStudio" / "fusion_presets"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _refresh_presets(self) -> None:
        try:
            combo = self._preset_combo
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(Init)")
            d = self._preset_dir()
            for f in sorted(os.listdir(d)):
                if f.endswith(".json"):
                    combo.addItem(f.replace(".json", ""))
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        except Exception:
            try:
                self._preset_combo.blockSignals(False)
            except Exception:
                pass

    def _on_preset_selected(self, idx: int) -> None:
        if idx <= 0:
            return
        try:
            name = self._preset_combo.currentText()
            path = os.path.join(self._preset_dir(), f"{name}.json")
            if not os.path.isfile(path):
                return
            with open(path, "r") as f:
                state = json.load(f)
            self._apply_state(state)
        except Exception:
            pass

    def _save_preset(self) -> None:
        try:
            name, ok = QInputDialog.getText(
                self, "Fusion Preset speichern", "Preset-Name:",
                text=f"Preset {len(os.listdir(self._preset_dir())) + 1}"
            )
            if not ok or not name.strip():
                return
            safe = "".join(c for c in name if c.isalnum() or c in " _-").strip() or "preset"
            state = self._capture_state_snapshot()
            path = os.path.join(self._preset_dir(), f"{safe}.json")
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
            self._refresh_presets()
        except Exception:
            pass

    def _apply_state(self, state: dict) -> None:
        self._restoring_state = True
        try:
            osc = state.get("osc_type", self._current_osc)
            flt = state.get("flt_type", self._current_flt)
            env = state.get("env_type", self._current_env)

            idx = next((i for i, (k, _) in enumerate(_OSC_TYPES) if k == osc), -1)
            if idx >= 0:
                self._cmb_osc.setCurrentIndex(idx)
            idx = next((i for i, (k, _) in enumerate(_FLT_TYPES) if k == flt), -1)
            if idx >= 0:
                self._cmb_flt.setCurrentIndex(idx)
            idx = next((i for i, (k, _) in enumerate(_ENV_TYPES) if k == env), -1)
            if idx >= 0:
                self._cmb_env.setCurrentIndex(idx)

            knobs = state.get("knobs", {})
            for k, v in knobs.items():
                knob = self._knobs.get(k)
                if knob is not None:
                    knob.setValue(int(v))

            wt_file_path = str(state.get("wt_file_path", "") or "")
            self.engine._wt_file_path = wt_file_path if os.path.isfile(wt_file_path) else ""
            if self._current_osc == "wavetable" and hasattr(self, '_wt_name_label'):
                self._wt_name_label.setText(os.path.basename(self.engine._wt_file_path) if self.engine._wt_file_path else "(Default Sine→Saw)")

            if self._current_osc == "scrawl":
                self._apply_scrawl_state(
                    state.get("scrawl_points", []),
                    bool(state.get("scrawl_smooth", True)),
                    sync_editor=True,
                )
        finally:
            self._restoring_state = False
            self._persist_instrument_state()

    def _randomize(self) -> None:
        import random
        for key, knob in self._knobs.items():
            try:
                knob.setValue(random.randint(int(knob.minimum()), int(knob.maximum())))
            except Exception:
                knob.setValue(random.randint(0, 100))
        # Random module types
        self._cmb_osc.setCurrentIndex(random.randint(0, self._cmb_osc.count() - 1))
        self._cmb_flt.setCurrentIndex(random.randint(0, self._cmb_flt.count() - 1))
        self._cmb_env.setCurrentIndex(random.randint(0, self._cmb_env.count() - 1))

    # ════════════════════════════════════════════════
    #  Styling
    # ════════════════════════════════════════════════

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QComboBox { font-size: 11px; padding: 2px 6px;
                        border: 1px solid #555; border-radius: 3px;
                        background: #2a2a3a; color: #eee; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #2a2a3a; color: #eee;
                                          selection-background-color: #7e57c2; }
            QPushButton { font-size: 10px; padding: 2px 6px;
                          border: 1px solid #555; border-radius: 3px;
                          background: #333; color: #ccc; }
            QPushButton:hover { background: #444; color: #fff; }
        """)
