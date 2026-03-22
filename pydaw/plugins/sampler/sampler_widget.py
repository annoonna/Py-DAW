# -*- coding: utf-8 -*-
"""Pro Audio Sampler — compact Pro-DAW-Style device widget (PyQt6).

v0.0.19.7.55 — Complete rewrite:
- Compact horizontal layout matching Pro-DAW device panel height (~200-240px)
- Per-track binding via track_id property
- Multi-format audio: WAV, MP3, FLAC, OGG, AIFF, M4A, WV
- QPainter knobs (no QDial, smaller footprint)
- Waveform strip 40-60px
- All controls visible without scrolling
"""
from __future__ import annotations

from pathlib import Path
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QComboBox,
    QSlider, QMessageBox, QFileDialog, QCheckBox,
    QSizePolicy, QFrame,
)

from .sampler_engine import ProSamplerEngine
from .ui_widgets import CompactKnob, WaveformDisplay
from .audio_io import SUPPORTED_EXTENSIONS

_AUDIO_FILTER = "Audio files ({});;All files (*)".format(
    " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
)


class SamplerWidget(QWidget):
    """Compact Pro-DAW-Style sampler device."""

    # Emitted when this sampler wants to signal something to the device panel
    status_message = Signal(str)

    def __init__(self, project_service=None, audio_engine=None, automation_manager=None, parent=None):
        super().__init__(parent)
        self.setObjectName("proAudioSamplerWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(0)
        self.setAcceptDrops(True)

        self.project_service = project_service
        self.audio_engine = audio_engine
        self.automation_manager = automation_manager
        self._automation_setup_done: bool = False
        self._automation_mgr_connected: bool = False
        self._automation_pid_to_engine: dict[str, callable] = {}

        self._track_id: str = ""

        # Persistente Sample-Referenz (über Projekt-Media-ID)
        self._sample_media_id: str = ""
        self._restoring_state: bool = False

        # IMPORTANT: do NOT hard-code 48k. If the user's audio settings run at
        # 44.1k, the sampler would output silence because pull() checked
        # sr==target_sr. We derive the SR from the current AudioEngine config.
        sr = 48000
        try:
            if self.audio_engine is not None:
                sr = int(self.audio_engine.get_effective_sample_rate())
        except Exception:
            sr = 48000

        self.engine = ProSamplerEngine(target_sr=sr)
        self._pull_name = f"sampler:{uuid.uuid4().hex[:8]}"

        self._build_ui()
        self._wire()
        self._register_audio()

    @property
    def track_id(self) -> str:
        return self._track_id

    @track_id.setter
    def track_id(self, tid: str):
        self._track_id = str(tid or "")
        # v0.0.20.43: Auto-register in sampler registry when track_id is assigned
        if self._track_id:
            try:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                registry = get_sampler_registry()
                if not registry.has_sampler(self._track_id):
                    registry.register(self._track_id, self.engine, self)
            except Exception:
                pass
    
    def set_track_context(self, track_id: str) -> None:
        """Unified API (v0.0.20.46+) + Instrument-State Restore.

        Beim Binden an einen Track werden gespeicherte Sampler-States (Sample +
        Parameter) aus dem Projekt wieder hergestellt.
        """
        self.track_id = track_id
        self._restore_instrument_state()
        self._setup_automation()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        # --- Top bar: title + load + play/loop
        top = QHBoxLayout()
        top.setSpacing(6)

        self.lbl_file = QLabel("Drop audio or 'Load Sample'")
        self.lbl_file.setStyleSheet("color:#bdbdbd;font-size:9px;")
        self.lbl_file.setMinimumWidth(80)
        top.addWidget(self.lbl_file, 1)

        self.btn_load = QPushButton("Load Sample")
        self.btn_load.setFixedHeight(22)
        self.btn_load.setMaximumWidth(120)
        top.addWidget(self.btn_load)

        self.btn_play = QPushButton("PLAY")
        self.btn_play.setCheckable(True)
        self.btn_play.setFixedHeight(22)
        self.btn_play.setMaximumWidth(60)
        top.addWidget(self.btn_play)

        self.chk_loop = QCheckBox("LOOP")
        self.chk_loop.setStyleSheet("color:#ccc;font-size:9px;")
        top.addWidget(self.chk_loop)

        root.addLayout(top)

        # --- Waveform strip (40-60px)
        self.wave = WaveformDisplay(self.engine)
        root.addWidget(self.wave)

        # --- Main control row: Pitch | Filters | AHDSR | Output
        row = QHBoxLayout()
        row.setSpacing(8)

        # -- Pitch Modulation section
        row.addWidget(self._make_section("Pitch", [
            ("Glide", 5), ("Speed", 3), ("Repitch", 35),
            ("Cycles", 0), ("Textures", 10), ("Grain", 0),
        ]))

        # -- Filter section
        filt_w = QWidget()
        filt_l = QVBoxLayout(filt_w)
        filt_l.setContentsMargins(4, 2, 4, 2)
        filt_l.setSpacing(2)

        filt_top = QHBoxLayout()
        filt_top.setSpacing(4)
        lbl_ft = QLabel("Filter")
        lbl_ft.setStyleSheet("color:#aaa;font-size:8px;")
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["Off", "LP", "HP", "BP"])
        self.cb_filter.setFixedHeight(20)
        self.cb_filter.setMaximumWidth(60)
        filt_top.addWidget(lbl_ft)
        filt_top.addWidget(self.cb_filter)
        filt_l.addLayout(filt_top)

        filt_knobs = QHBoxLayout()
        filt_knobs.setSpacing(2)
        self.k_cutoff = CompactKnob("Cutoff", 68)
        self.k_res = CompactKnob("Reso", 60)
        self.k_drive = CompactKnob("Drive", 0)
        for k in (self.k_cutoff, self.k_res, self.k_drive):
            filt_knobs.addWidget(k)
        filt_l.addLayout(filt_knobs)

        fx_knobs = QHBoxLayout()
        fx_knobs.setSpacing(2)
        self.k_chorus = CompactKnob("Chorus", 0)
        self.k_reverb = CompactKnob("Reverb", 0)
        self.k_delay = CompactKnob("Delay", 0)
        self.k_dist = CompactKnob("Dist", 0)
        for k in (self.k_chorus, self.k_reverb, self.k_delay, self.k_dist):
            fx_knobs.addWidget(k)
        filt_l.addLayout(fx_knobs)

        row.addWidget(filt_w)

        # -- AHDSR section
        row.addWidget(self._make_section("AHDSR", [
            ("A", 2), ("H", 0), ("D", 15), ("S", 100), ("R", 20),
        ]))

        # -- Output section
        row.addWidget(self._make_section("Output", [
            ("Vol", 80), ("Pan", 50),
        ]))

        root.addLayout(row)

        # --- Position / Loop sliders (compact)
        sliders = QHBoxLayout()
        sliders.setSpacing(8)
        self.s_pos = self._mini_slider("Position", 0)
        self.s_ls = self._mini_slider("Loop Start", 0)
        self.s_le = self._mini_slider("Loop End", 100)
        sliders.addWidget(QLabel("Position"))
        sliders.addWidget(self.s_pos, 1)
        sliders.addWidget(QLabel("Loop Start"))
        sliders.addWidget(self.s_ls, 1)
        sliders.addWidget(QLabel("Loop End"))
        sliders.addWidget(self.s_le, 1)

        # Style the slider labels
        for w in (sliders.itemAt(i).widget() for i in range(sliders.count()) if sliders.itemAt(i).widget() and isinstance(sliders.itemAt(i).widget(), QLabel)):
            w.setStyleSheet("color:#999;font-size:8px;")

        root.addLayout(sliders)

    def _make_section(self, title: str, knobs: list[tuple[str, int]]) -> QWidget:
        """Create a compact vertical section with title + knob grid."""
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 2, 4, 2)
        vl.setSpacing(2)

        lbl = QLabel(title)
        lbl.setStyleSheet("color:#e060e0;font-size:8px;font-weight:bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(lbl)

        # Arrange knobs in rows of 3
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)
        knob_widgets = []
        for idx, (name, init) in enumerate(knobs):
            k = CompactKnob(name, init)
            grid.addWidget(k, idx // 3, idx % 3)
            knob_widgets.append(k)
            setattr(self, f"k_{name.lower().replace(' ', '_')}", k)
        vl.addLayout(grid)

        return w

    def _mini_slider(self, tooltip: str, init: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(init)
        s.setToolTip(tooltip)
        s.setFixedHeight(16)
        return s

    # ------------------------------------------------------------------ Wiring
    def _wire(self) -> None:
        self.btn_load.clicked.connect(self._load_dialog)
        self.btn_play.toggled.connect(self._toggle_play)
        self.chk_loop.toggled.connect(self._toggle_loop)

        # Knob → engine mappings
        self.k_vol.valueChanged.connect(lambda v: self.engine.set_master(gain=v / 100.0))
        self.k_pan.valueChanged.connect(lambda v: self.engine.set_master(pan=(v - 50.0) / 50.0))

        self.k_repitch.valueChanged.connect(lambda v: self.engine.set_repitch(0.25 + (v / 100.0) * 3.75))
        self.k_glide.valueChanged.connect(lambda v: self.engine.set_glide(v / 100.0))
        self.k_speed.valueChanged.connect(lambda v: self.engine.set_lfo(rate_hz=0.05 + (v / 100.0) * 19.95))
        self.k_cycles.valueChanged.connect(lambda v: self.engine.set_lfo(depth=(v / 100.0) * 0.20))
        self.k_textures.valueChanged.connect(lambda v: self.engine.set_textures(v / 100.0))
        self.k_grain.valueChanged.connect(lambda v: self.engine.set_grain(v / 100.0))

        self.cb_filter.currentIndexChanged.connect(self._filter_type_changed)
        self.k_cutoff.valueChanged.connect(self._cutoff_changed)
        self.k_res.valueChanged.connect(lambda v: self.engine.set_filter(q=0.25 + (v / 100.0) * 11.75))
        self.k_drive.valueChanged.connect(lambda v: self.engine.set_drive(1.0 + (v / 100.0) * 19.0))

        self.k_chorus.valueChanged.connect(lambda v: self.engine.set_fx(chorus_mix=v / 100.0))
        self.k_delay.valueChanged.connect(lambda v: self.engine.set_fx(delay_mix=v / 100.0))
        self.k_reverb.valueChanged.connect(lambda v: self.engine.set_fx(reverb_mix=v / 100.0))
        self.k_dist.valueChanged.connect(lambda v: self.engine.set_distortion(v / 100.0))

        self.k_a.valueChanged.connect(lambda v: self.engine.set_env(a=0.001 + (v / 100.0) * 4.999))
        self.k_h.valueChanged.connect(lambda v: self.engine.set_env(h=(v / 100.0) * 5.0))
        self.k_d.valueChanged.connect(lambda v: self.engine.set_env(d=0.001 + (v / 100.0) * 4.999))
        self.k_s.valueChanged.connect(lambda v: self.engine.set_env(s=v / 100.0))
        self.k_r.valueChanged.connect(lambda v: self.engine.set_env(r=0.001 + (v / 100.0) * 9.999))

        self.s_pos.valueChanged.connect(self._pos_changed)
        self.s_ls.valueChanged.connect(self._loop_slider_changed)
        self.s_le.valueChanged.connect(self._loop_slider_changed)

        # Note preview from ProjectService
        if self.project_service is not None:
            sig = getattr(self.project_service, "note_preview", None)
            if sig is not None:
                try:
                    sig.connect(self._on_note_preview)
                except Exception:
                    pass



    # ---------------- Automation (v0.0.20.90)
    def _setup_automation(self) -> None:
        """Register sampler parameters and enable right-click automation on all knobs.

        Design goals:
        - Keep existing engine intact (no direct GUI → audio-thread writes).
        - Knobs only set base values on the AutomatableParameter.
        - Automation playback (parameter_changed) applies values to the engine and updates knobs externally.
        """
        try:
            if self._automation_setup_done:
                return
            mgr = getattr(self, 'automation_manager', None)
            tid = str(getattr(self, '_track_id', '') or '')
            if mgr is None or not tid:
                return

            self._automation_setup_done = True
            self._automation_pid_to_engine = {}

            # Helper: safe disconnect all existing engine-wiring from knobs
            def _disconnect_knob(k):
                try:
                    k.valueChanged.disconnect()
                except Exception:
                    pass

            # Map UI-space (0..100) to engine setters
            def pid(key: str) -> str:
                return f"trk:{tid}:sampler:{key}"

            # Output
            self._automation_pid_to_engine[pid('out_gain')] = lambda v: self.engine.set_master(gain=float(v) / 100.0)
            self._automation_pid_to_engine[pid('out_pan')] = lambda v: self.engine.set_master(pan=(float(v) - 50.0) / 50.0)

            # Pitch / modulation
            self._automation_pid_to_engine[pid('repitch')] = lambda v: self.engine.set_repitch(0.25 + (float(v) / 100.0) * 3.75)
            self._automation_pid_to_engine[pid('glide')] = lambda v: self.engine.set_glide(float(v) / 100.0)
            self._automation_pid_to_engine[pid('lfo_rate')] = lambda v: self.engine.set_lfo(rate_hz=0.05 + (float(v) / 100.0) * 19.95)
            self._automation_pid_to_engine[pid('lfo_depth')] = lambda v: self.engine.set_lfo(depth=(float(v) / 100.0) * 0.20)
            self._automation_pid_to_engine[pid('textures')] = lambda v: self.engine.set_textures(float(v) / 100.0)
            self._automation_pid_to_engine[pid('grain')] = lambda v: self.engine.set_grain(float(v) / 100.0)

            # Filter / drive
            self._automation_pid_to_engine[pid('cutoff')] = lambda v: self._cutoff_changed(int(round(float(v))))
            self._automation_pid_to_engine[pid('res')] = lambda v: self.engine.set_filter(q=0.25 + (float(v) / 100.0) * 11.75)
            self._automation_pid_to_engine[pid('drive')] = lambda v: self.engine.set_drive(1.0 + (float(v) / 100.0) * 19.0)

            # FX
            self._automation_pid_to_engine[pid('chorus')] = lambda v: self.engine.set_fx(chorus_mix=float(v) / 100.0)
            self._automation_pid_to_engine[pid('delay')] = lambda v: self.engine.set_fx(delay_mix=float(v) / 100.0)
            self._automation_pid_to_engine[pid('reverb')] = lambda v: self.engine.set_fx(reverb_mix=float(v) / 100.0)
            self._automation_pid_to_engine[pid('dist')] = lambda v: self.engine.set_distortion(float(v) / 100.0)

            # Env
            self._automation_pid_to_engine[pid('env_a')] = lambda v: self.engine.set_env(a=0.001 + (float(v) / 100.0) * 4.999)
            self._automation_pid_to_engine[pid('env_h')] = lambda v: self.engine.set_env(h=(float(v) / 100.0) * 5.0)
            self._automation_pid_to_engine[pid('env_d')] = lambda v: self.engine.set_env(d=0.001 + (float(v) / 100.0) * 4.999)
            self._automation_pid_to_engine[pid('env_s')] = lambda v: self.engine.set_env(s=float(v) / 100.0)
            self._automation_pid_to_engine[pid('env_r')] = lambda v: self.engine.set_env(r=0.001 + (float(v) / 100.0) * 9.999)

            # Disconnect legacy engine-wiring (we apply via AutomationManager)
            knob_map = [
                (self.k_vol, pid('out_gain'), 'Sampler Output Gain'),
                (self.k_pan, pid('out_pan'), 'Sampler Output Pan'),
                (self.k_repitch, pid('repitch'), 'Sampler Repitch'),
                (self.k_glide, pid('glide'), 'Sampler Glide'),
                (self.k_speed, pid('lfo_rate'), 'Sampler LFO Rate'),
                (self.k_cycles, pid('lfo_depth'), 'Sampler LFO Depth'),
                (self.k_textures, pid('textures'), 'Sampler Textures'),
                (self.k_grain, pid('grain'), 'Sampler Grain'),
                (self.k_cutoff, pid('cutoff'), 'Sampler Filter Cutoff'),
                (self.k_res, pid('res'), 'Sampler Filter Resonance'),
                (self.k_drive, pid('drive'), 'Sampler Drive'),
                (self.k_chorus, pid('chorus'), 'Sampler Chorus Mix'),
                (self.k_delay, pid('delay'), 'Sampler Delay Mix'),
                (self.k_reverb, pid('reverb'), 'Sampler Reverb Mix'),
                (self.k_dist, pid('dist'), 'Sampler Distortion'),
                (self.k_a, pid('env_a'), 'Sampler Env Attack'),
                (self.k_h, pid('env_h'), 'Sampler Env Hold'),
                (self.k_d, pid('env_d'), 'Sampler Env Decay'),
                (self.k_s, pid('env_s'), 'Sampler Env Sustain'),
                (self.k_r, pid('env_r'), 'Sampler Env Release'),
            ]

            for knob, pid_full, pname in knob_map:
                _disconnect_knob(knob)
                try:
                    knob.bind_automation(mgr, pid_full, name=pname, track_id=tid, default=float(knob.value()))
                except Exception:
                    pass
                # Persist instrument state on manual edits (external updates block signals)
                try:
                    knob.valueChanged.connect(lambda _v=0: self._persist_instrument_state())
                except Exception:
                    pass

            # v0.0.20.436: Re-wire direct engine connections as FAILSAFE.
            # The automation signal chain (knob → set_value → _notify → parameter_changed
            # → _on_automation_parameter_changed → engine) should work, but if it doesn't
            # (e.g. _automation_param is None, signal coalescing, etc.), the knobs would
            # be completely dead. Adding the direct connections back ensures the engine
            # ALWAYS responds to knob changes, regardless of automation system state.
            try:
                self.k_vol.valueChanged.connect(lambda v: self.engine.set_master(gain=v / 100.0))
                self.k_pan.valueChanged.connect(lambda v: self.engine.set_master(pan=(v - 50.0) / 50.0))
                self.k_repitch.valueChanged.connect(lambda v: self.engine.set_repitch(0.25 + (v / 100.0) * 3.75))
                self.k_glide.valueChanged.connect(lambda v: self.engine.set_glide(v / 100.0))
                self.k_speed.valueChanged.connect(lambda v: self.engine.set_lfo(rate_hz=0.05 + (v / 100.0) * 19.95))
                self.k_cycles.valueChanged.connect(lambda v: self.engine.set_lfo(depth=(v / 100.0) * 0.20))
                self.k_textures.valueChanged.connect(lambda v: self.engine.set_textures(v / 100.0))
                self.k_grain.valueChanged.connect(lambda v: self.engine.set_grain(v / 100.0))
                self.k_cutoff.valueChanged.connect(self._cutoff_changed)
                self.k_res.valueChanged.connect(lambda v: self.engine.set_filter(q=0.25 + (v / 100.0) * 11.75))
                self.k_drive.valueChanged.connect(lambda v: self.engine.set_drive(1.0 + (v / 100.0) * 19.0))
                self.k_chorus.valueChanged.connect(lambda v: self.engine.set_fx(chorus_mix=v / 100.0))
                self.k_delay.valueChanged.connect(lambda v: self.engine.set_fx(delay_mix=v / 100.0))
                self.k_reverb.valueChanged.connect(lambda v: self.engine.set_fx(reverb_mix=v / 100.0))
                self.k_dist.valueChanged.connect(lambda v: self.engine.set_distortion(v / 100.0))
                self.k_a.valueChanged.connect(lambda v: self.engine.set_env(a=0.001 + (v / 100.0) * 4.999))
                self.k_h.valueChanged.connect(lambda v: self.engine.set_env(h=(v / 100.0) * 5.0))
                self.k_d.valueChanged.connect(lambda v: self.engine.set_env(d=0.001 + (v / 100.0) * 4.999))
                self.k_s.valueChanged.connect(lambda v: self.engine.set_env(s=v / 100.0))
                self.k_r.valueChanged.connect(lambda v: self.engine.set_env(r=0.001 + (v / 100.0) * 9.999))
            except Exception:
                pass

            # Connect engine apply once
            if not self._automation_mgr_connected:
                try:
                    mgr.parameter_changed.connect(self._on_automation_parameter_changed)
                    self._automation_mgr_connected = True
                except Exception:
                    self._automation_mgr_connected = False

        except Exception:
            pass

    def _on_automation_parameter_changed(self, parameter_id: str, value: float) -> None:
        """AutomationManager → engine setters."""
        try:
            fn = self._automation_pid_to_engine.get(str(parameter_id))
            if fn is None:
                return
            fn(float(value))
        except Exception:
            pass
    def _register_audio(self):
        """Register this sampler as a pull-source and tag it with track-id metadata
        so Live/Preview mode can apply track faders (vol/pan/mute/solo) in the engine.
        """
        if self.audio_engine is None:
            return

        try:
            # Wrap pull so we can attach metadata (bound methods can't reliably hold attrs)
            if not hasattr(self, "_pull_fn") or self._pull_fn is None:
                def _pull(frames: int, sr: int, _eng=self.engine):
                    return _eng.pull(frames, sr)

                # Dynamic getter: track_id can be assigned after widget creation
                _pull._pydaw_track_id = (lambda: getattr(self, "_track_id", ""))

                self._pull_fn = _pull

            # Register via modern API when available
            if hasattr(self.audio_engine, "register_pull_source"):
                self.audio_engine.register_pull_source(self._pull_name, self._pull_fn)
            elif hasattr(self.audio_engine, "add_source"):
                # Legacy fallback (no per-track fader support in this path)
                self.audio_engine.add_source(self.engine, name=self._pull_name)

            # Ensure preview output is alive (sounddevice stream)
            try:
                self.audio_engine.ensure_preview_output()
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------ Interactions
    def _filter_type_changed(self, idx: int):
        mapping = {0: "off", 1: "lp", 2: "hp", 3: "bp"}
        self.engine.set_filter(ftype=mapping.get(idx, "off"))

    def _cutoff_changed(self, v: int):
        cutoff = 20.0 * (1000.0 ** (v / 100.0))
        self.engine.set_filter(cutoff_hz=cutoff)

    def _pos_changed(self, v: int):
        """v0.0.20.42: Position slider sets sample start position (Pro-DAW-like).
        Notes will start playing from this position in the sample."""
        try:
            with self.engine._lock:
                self.engine.state.start_position = float(v / 100.0)
        except Exception:
            pass

    def _loop_slider_changed(self, _=None):
        ls, le = self.s_ls.value() / 100.0, self.s_le.value() / 100.0
        if le <= ls:
            le = min(1.0, ls + 0.01)
            self.s_le.blockSignals(True)
            self.s_le.setValue(int(le * 100))
            self.s_le.blockSignals(False)
        self.engine.set_loop_norm(ls, le)

    def _toggle_loop(self, checked: bool):
        self.engine.set_loop_enabled(bool(checked))
        if checked:
            self._loop_slider_changed()

    def _toggle_play(self, checked: bool):
        try:
            if checked:
                self.engine.toggle_play()
                self.btn_play.setText("STOP")
            else:
                self.engine.stop_play()
                self.btn_play.setText("PLAY")
        except Exception:
            self.btn_play.setChecked(False)
            self.btn_play.setText("PLAY")

    def _load_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Audio File", str(Path.home()), _AUDIO_FILTER
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str, *, _skip_import: bool = False) -> None:
        p = Path(path)
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            QMessageBox.information(
                self,
                "Sampler",
                f"Nicht unterstützt: {ext}\nErlaubt: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )
            return

        # Wenn möglich: Sample ins Projekt (media/) importieren, damit
        # es beim Speichern/Reload garantiert wieder da ist.
        load_path = str(p)
        media_id = ""
        if (not _skip_import) and (self.project_service is not None) and self._track_id:
            try:
                load_path, media_id = self.project_service.import_audio_to_project(
                    self._track_id, p, label=p.stem
                )
            except Exception:
                load_path = str(p)
                media_id = ""

        ok = self.wave.load_wav_file(str(load_path), engine=self.engine)
        if ok:
            lp = Path(load_path)
            if media_id:
                self._sample_media_id = str(media_id)
            self.lbl_file.setText(f"✓ {lp.name}")
            self.lbl_file.setToolTip(str(load_path))
            if self.audio_engine is not None:
                try:
                    self.audio_engine.ensure_preview_output()
                except Exception:
                    pass
            self._persist_instrument_state()
        else:
            QMessageBox.warning(self, "Sampler", f"Konnte '{p.name}' nicht laden.")

    def _on_note_preview(self, pitch: int, velocity: int, duration_ms: int):
        """v0.0.20.43: Respond to note_preview regardless of visibility.
        The sampler should play notes even when the Device panel is not shown
        (e.g., when user is in Piano Roll or Notation view).

        Note: The registry path in main_window._on_note_preview_routed is the
        primary routing mechanism. This direct connection is a fallback that
        ensures the sampler plays even if registry wiring fails.
        """
        if self.engine.samples is None:
            return
        # Only respond if this sampler is for the currently selected track
        # (prevents all samplers from playing simultaneously)
        try:
            if self._track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                registry = get_sampler_registry()
                # If registry knows about us, let it handle routing (avoid double-trigger)
                if registry.has_sampler(self._track_id):
                    return  # Registry path in main_window handles this
        except Exception:
            pass
        # Fallback: direct trigger (no registry)
        self.engine.trigger_note(int(pitch), int(velocity), int(duration_ms))
        if self.audio_engine is not None:
            try:
                self.audio_engine.ensure_preview_output()
            except Exception:
                pass

    # ------------------------------------------------------------------ Persist/Restore
    def _get_track_obj(self):
        try:
            ctx = getattr(self.project_service, "ctx", None)
            if ctx is None or getattr(ctx, "project", None) is None:
                return None
            for t in ctx.project.tracks:
                if getattr(t, "id", "") == self._track_id:
                    return t
        except Exception:
            return None
        return None

    def _find_media_path(self, media_id: str) -> str:
        try:
            ctx = getattr(self.project_service, "ctx", None)
            if ctx is None or getattr(ctx, "project", None) is None:
                return ""
            for m in ctx.project.media:
                if getattr(m, "id", "") == str(media_id):
                    return str(getattr(m, "path", ""))
        except Exception:
            return ""
        return ""

    def _persist_instrument_state(self) -> None:
        if self._restoring_state:
            return
        trk = self._get_track_obj()
        if trk is None:
            return
        try:
            st = {
                "sample_media_id": str(self._sample_media_id or ""),
                "sample_path": str(getattr(self.wave, "path", "") or ""),
                "engine": self.engine.export_state(),
            }
            if getattr(trk, "instrument_state", None) is None:
                trk.instrument_state = {}
            trk.instrument_state["sampler"] = st
        except Exception:
            pass

    def _restore_instrument_state(self) -> None:
        trk = self._get_track_obj()
        if trk is None:
            return
        ist = getattr(trk, "instrument_state", {}) or {}
        st = ist.get("sampler")
        if not isinstance(st, dict):
            return
        self._restoring_state = True
        try:
            eng = st.get("engine")
            if isinstance(eng, dict):
                try:
                    self.engine.import_state(eng)
                except Exception:
                    pass

            # v0.0.20.75: Try multiple paths to find the sample
            mid = str(st.get("sample_media_id") or "")
            sample_path = ""
            
            # 1. Try media_id first (most reliable - project-relative)
            if mid:
                sample_path = self._find_media_path(mid)
                if sample_path:
                    self._sample_media_id = mid
            
            # 2. Try sample_path from state
            if not sample_path:
                sample_path = str(st.get("sample_path") or "")
            
            # 3. Try sample_name from engine state (fallback)
            if not sample_path and isinstance(eng, dict):
                sample_path = str(eng.get("sample_name") or "")
            
            # Load if path exists
            if sample_path and Path(sample_path).exists():
                self._load_file(sample_path, _skip_import=True)

            self._sync_ui_from_engine()
        finally:
            self._restoring_state = False

    def _sync_ui_from_engine(self) -> None:
        s = getattr(self.engine, "state", None)
        if s is None:
            return
        def _set_value(widget, value: int):
            try:
                widget.blockSignals(True)
                widget.setValue(int(value))
            finally:
                try:
                    widget.blockSignals(False)
                except Exception:
                    pass

        def _set_checked(widget, value: bool):
            try:
                widget.blockSignals(True)
                widget.setChecked(bool(value))
            finally:
                try:
                    widget.blockSignals(False)
                except Exception:
                    pass

        try:
            _set_value(self.k_vol, round(float(s.gain) * 100.0))
            _set_value(self.k_pan, round(float(s.pan) * 50.0 + 50.0))
        except Exception:
            pass

        try:
            ft = str(getattr(s, "filter_type", "lowpass"))
            self.cmb_filter.blockSignals(True)
            i = self.cmb_filter.findText(ft)
            if i >= 0:
                self.cmb_filter.setCurrentIndex(i)
            self.cmb_filter.blockSignals(False)
        except Exception:
            try:
                self.cmb_filter.blockSignals(False)
            except Exception:
                pass

        try:
            import math
            cutoff = float(getattr(s, "cutoff_hz", 8000.0))
            v = 0
            if cutoff > 0:
                v = int(round((math.log(cutoff / 20.0, 1000.0)) * 100.0))
            v = max(0, min(100, v))
            _set_value(self.k_cut, v)
            q = float(getattr(s, "q", 0.707))
            _set_value(self.k_res, round(((q - 0.25) / 11.75) * 100.0))
            drv = float(getattr(s, "drive", 1.0))
            _set_value(self.k_drive, round(((drv - 1.0) / 19.0) * 100.0))
        except Exception:
            pass

        for w, attr in [
            (self.k_dist, "dist_mix"),
            (self.k_chorus, "chorus_mix"),
            (self.k_delay, "delay_mix"),
            (self.k_reverb, "reverb_mix"),
        ]:
            try:
                _set_value(w, round(float(getattr(s, attr, 0.0)) * 100.0))
            except Exception:
                pass

        # Noise / Bitcrush
        try:
            _set_value(self.k_noise, round(float(getattr(s, "noise_mix", 0.0)) * 100.0))
        except Exception:
            pass
        try:
            _set_value(self.k_bits, round(float(getattr(s, "bitcrush", 0.0)) * 100.0))
        except Exception:
            pass

        try:
            a = float(getattr(s, "a", 0.01))
            d = float(getattr(s, "d", 0.15))
            r = float(getattr(s, "r", 0.20))
            sus = float(getattr(s, "s", 1.0))
            _set_value(self.k_a, round(((a - 0.001) / 4.999) * 100.0))
            _set_value(self.k_d, round(((d - 0.001) / 4.999) * 100.0))
            _set_value(self.k_s, round(sus * 100.0))
            _set_value(self.k_r, round(((r - 0.001) / 9.999) * 100.0))
        except Exception:
            pass

        try:
            _set_checked(self.chk_loop, bool(getattr(s, "loop_enabled", False)))
            _set_value(self.s_pos, round(float(getattr(s, "start_position", 0.0)) * 100.0))
            _set_value(self.s_ls, round(float(getattr(s, "loop_start", 0.0)) * 100.0))
            _set_value(self.s_le, round(float(getattr(s, "loop_end", 1.0)) * 100.0))
        except Exception:
            pass

        # v0.0.20.397: Sync repitch, glide, speed knobs
        try:
            rp = float(getattr(s, "repitch_ratio", 1.0))
            _set_value(self.k_repitch, round(((rp - 0.25) / 3.75) * 100.0))
        except Exception:
            pass
        try:
            gl = float(getattr(s, "glide_sec", 0.02))
            _set_value(self.k_glide, round((gl / 1.0) * 100.0))
        except Exception:
            pass
        try:
            sp = float(getattr(s, "lfo_rate_hz", 0.8))
            _set_value(self.k_speed, round(((sp - 0.05) / 19.95) * 100.0))
        except Exception:
            pass

    # ------------------------------------------------------------------ DnD
    def dragEnterEvent(self, e):
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = e.mimeData()
            if md and md.hasUrls():
                for u in md.urls():
                    ext = Path(u.toLocalFile()).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        e.acceptProposedAction()
                        return
            e.ignore()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass

    def dragMoveEvent(self, e):
        # IMPORTANT: Must accept dragMoveEvent too, otherwise dropEvent won't fire.
        try:
            md = e.mimeData()
            if md and md.hasUrls():
                for u in md.urls():
                    ext = Path(u.toLocalFile()).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        e.acceptProposedAction()
                        return
            e.ignore()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass

    def dropEvent(self, e):
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = e.mimeData()
            if not (md and md.hasUrls()):
                e.ignore(); return
            for u in md.urls():
                fp = u.toLocalFile()
                if Path(fp).suffix.lower() in SUPPORTED_EXTENSIONS:
                    try:
                        self._load_file(fp)
                        e.acceptProposedAction()
                    except Exception:
                        try:
                            e.ignore()
                        except Exception:
                            pass
                    return
            e.ignore()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass

    # ------------------------------------------------------------------ Lifecycle
    def shutdown(self):
        if self.audio_engine is not None:
            try:
                self.audio_engine.unregister_pull_source(self._pull_name)
            except Exception:
                pass
        # Unregister from global sampler registry (avoid stale track routing)
        try:
            if self._track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                reg = get_sampler_registry()
                reg.unregister(self._track_id)
        except Exception:
            pass
