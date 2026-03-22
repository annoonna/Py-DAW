# -*- coding: utf-8 -*-
"""Bach Orgel Instrument Widget.

Features (MVP but fully integrated):
- New instrument for Browser/DevicePanel (`chrono.bach_orgel`)
- Pull-source audio engine + SamplerRegistry routing (PianoRoll/Notation preview)
- Right-click automation on all organ knobs (via CompactKnob)
- Track-local persistence (`track.instrument_state['bach_orgel']`)
- Presets (Gottesdienst, Plenum, Flöte, Meditation, etc.)

The UI intentionally lives in its own module/package so other instruments remain untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QComboBox,
    QSizePolicy,
    QMenu,
)

from pydaw.plugins.sampler.ui_widgets import CompactKnob
from .bach_orgel_engine import BachOrgelEngine


class _Section(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName('bachSection')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.title = QLabel(title)
        self.title.setObjectName('bachSectionTitle')
        lay.addWidget(self.title)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        lay.addLayout(self.body, 1)


class BachOrgelWidget(QWidget):
    PLUGIN_STATE_KEY = 'bach_orgel'

    PRESETS: Dict[str, dict] = {
        # v104: Alle Presets wärmer abgestimmt — weniger Obertöne, weniger Drive,
        # weniger Reed, mit Air-Parameter für Pfeifen-Realismus
        'Gottesdienst': {
            'instr': 'organ', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.18, 'stop8': 0.88, 'stop4': 0.50, 'stop2': 0.16,
            'reed': 0.04, 'click': 0.02, 'drv': 0.02,
            'trem_depth': 0.04, 'trem_rate': 3.4,
            'fx_drv': 0.04, 'fx_lvl': 0.82, 'gain': 0.65, 'mix': 0.14,
            'cut': 0.68, 'res': 0.15, 'attack': 0.03, 'release': 0.40,
            'env_amt': 0.42, 'env': 0.65, 'dec': 0.20, 'accent': 0.16,
            'air': 0.06, 'tune': 0.0,
        },
        'Barock Plenum': {
            'instr': 'choral', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.22, 'stop8': 0.92, 'stop4': 0.62, 'stop2': 0.28,
            'reed': 0.08, 'click': 0.02, 'drv': 0.02,
            'trem_depth': 0.05, 'trem_rate': 4.6,
            'fx_drv': 0.03, 'fx_lvl': 0.82, 'gain': 0.68, 'mix': 0.20,
            'cut': 0.74, 'res': 0.18, 'attack': 0.025, 'release': 0.32,
            'env_amt': 0.48, 'env': 0.72, 'dec': 0.18, 'accent': 0.22,
            'air': 0.07, 'tune': 0.0,
        },
        'Flöte': {
            'instr': 'flute', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.04, 'stop8': 0.85, 'stop4': 0.18, 'stop2': 0.06,
            'reed': 0.01, 'click': 0.01, 'drv': 0.01,
            'trem_depth': 0.10, 'trem_rate': 5.2,
            'fx_drv': 0.02, 'fx_lvl': 0.80, 'gain': 0.62, 'mix': 0.08,
            'cut': 0.62, 'res': 0.12, 'attack': 0.05, 'release': 0.50,
            'env_amt': 0.38, 'env': 0.52, 'dec': 0.22, 'accent': 0.10,
            'air': 0.10, 'tune': 0.0,
        },
        "Prinzipal 8'": {
            'instr': 'organ', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.00, 'stop8': 1.00, 'stop4': 0.00, 'stop2': 0.00,
            'reed': 0.00, 'click': 0.02, 'drv': 0.01,
            'trem_depth': 0.00, 'trem_rate': 4.0,
            'fx_drv': 0.01, 'fx_lvl': 0.84, 'gain': 0.65, 'mix': 0.03,
            'cut': 0.60, 'res': 0.12, 'attack': 0.03, 'release': 0.35,
            'env_amt': 0.35, 'env': 0.55, 'dec': 0.15, 'accent': 0.08,
            'air': 0.05, 'tune': 0.0,
        },
        'Oktaven': {
            'instr': 'organ', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.06, 'stop8': 0.72, 'stop4': 0.60, 'stop2': 0.38,
            'reed': 0.03, 'click': 0.02, 'drv': 0.02,
            'trem_depth': 0.02, 'trem_rate': 4.8,
            'fx_drv': 0.02, 'fx_lvl': 0.80, 'gain': 0.62, 'mix': 0.14,
            'cut': 0.72, 'res': 0.16, 'attack': 0.025, 'release': 0.28,
            'env_amt': 0.45, 'env': 0.68, 'dec': 0.18, 'accent': 0.18,
            'air': 0.06, 'tune': 0.0,
        },
        'Meditation': {
            'instr': 'flute', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.18, 'stop8': 0.60, 'stop4': 0.10, 'stop2': 0.03,
            'reed': 0.00, 'click': 0.01, 'drv': 0.00,
            'trem_depth': 0.15, 'trem_rate': 2.8,
            'fx_drv': 0.00, 'fx_lvl': 0.76, 'gain': 0.52, 'mix': 0.12,
            'cut': 0.50, 'res': 0.10, 'attack': 0.10, 'release': 0.75,
            'env_amt': 0.38, 'env': 0.48, 'dec': 0.25, 'accent': 0.08,
            'air': 0.12, 'tune': 0.0,
        },
        'Clear': {
            'instr': 'organ', 'wave': 'sine', 'voicing': 'warm',
            'stop16': 0.0, 'stop8': 0.0, 'stop4': 0.0, 'stop2': 0.0,
            'reed': 0.0, 'click': 0.0, 'drv': 0.0,
            'trem_depth': 0.0, 'trem_rate': 4.0,
            'fx_drv': 0.0, 'fx_lvl': 0.8, 'gain': 0.6, 'mix': 0.0,
            'cut': 0.7, 'res': 0.15, 'attack': 0.03, 'release': 0.3,
            'env_amt': 0.4, 'env': 0.6, 'dec': 0.2, 'accent': 0.12,
            'air': 0.0, 'tune': 0.0,
        },
    }

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
        self.engine = BachOrgelEngine(target_sr=sr)

        self._pull_name: Optional[str] = None
        def _pull(frames: int, sr: int, _eng=self.engine):
            return _eng.pull(frames, sr)
        _pull._pydaw_track_id = lambda: (self.track_id or '')  # type: ignore[attr-defined]
        self._pull_fn = _pull

        self._knobs: dict[str, CompactKnob] = {}
        self._preset_combo_signal_ready = False
        self._preset_quick_buttons: list[QPushButton] = []
        self._preset_compact_menu_btn: Optional[QPushButton] = None
        self._preset_compact_menu: Optional[QMenu] = None
        self._preset_row_widget: Optional[QWidget] = None
        self._preset_quick_wrap_widget: Optional[QWidget] = None
        self._preset_quick_grid: Optional[QGridLayout] = None

        self._build_ui()
        self._apply_styles()
        # initial defaults
        self._apply_preset('Gottesdienst', persist=False)

    # ---------------- integration lifecycle
    def set_track_context(self, track_id: str) -> None:
        self.track_id = str(track_id or '')
        # SamplerRegistry registration for PianoRoll/Notation preview + playback
        try:
            if self.track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                reg = get_sampler_registry()
                if not reg.has_sampler(self.track_id):
                    reg.register(self.track_id, self.engine, self)
        except Exception:
            pass
        # Pull source registration (track fader/VU aware)
        try:
            if self.audio_engine is not None and self._pull_name is None and self.track_id:
                self._pull_name = f"bach_orgel:{self.track_id}:{id(self) & 0xFFFF:04x}"
                self.audio_engine.register_pull_source(self._pull_name, self._pull_fn)
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass

        self._restore_instrument_state()
        self._setup_automation()

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
                reg = get_sampler_registry()
                reg.unregister(self.track_id)
        except Exception:
            pass
        try:
            self.engine.stop_all()
        except Exception:
            pass

    # ---------------- project state helpers
    def _get_track_obj(self):
        try:
            ctx = getattr(self.project_service, 'ctx', None)
            proj = getattr(ctx, 'project', None) if ctx is not None else None
            if proj is None:
                return None
            for t in getattr(proj, 'tracks', []) or []:
                if str(getattr(t, 'id', '')) == str(self.track_id or ''):
                    return t
        except Exception:
            return None
        return None

    def _persist_instrument_state(self) -> None:
        if self._restoring_state:
            return
        trk = self._get_track_obj()
        if trk is None:
            return
        try:
            if getattr(trk, 'instrument_state', None) is None:
                trk.instrument_state = {}
            state = self.engine.export_state()
            state['ui'] = {
                'preset_combo': self.cmb_preset.currentText() if hasattr(self, 'cmb_preset') else '',
                'instr': self.cmb_instr.currentText() if hasattr(self, 'cmb_instr') else '',
                'wave': self.cmb_wave.currentText() if hasattr(self, 'cmb_wave') else '',
                'voicing': self.cmb_voicing.currentText() if hasattr(self, 'cmb_voicing') else '',
            }
            trk.instrument_state[self.PLUGIN_STATE_KEY] = state
        except Exception:
            pass

    def _restore_instrument_state(self) -> None:
        trk = self._get_track_obj()
        if trk is None:
            return
        try:
            ist = getattr(trk, 'instrument_state', {}) or {}
        except Exception:
            ist = {}
        st = ist.get(self.PLUGIN_STATE_KEY)
        if not isinstance(st, dict):
            return
        self._restoring_state = True
        try:
            # engine first
            self.engine.import_state(st)
            params = (st.get('params', {}) or {}) if isinstance(st.get('params', {}), dict) else {}
            for key, k in self._knobs.items():
                src_key = 'trem_rate' if key == 'tremr' else ('trem_depth' if key == 'tremd' else key)
                if src_key not in params:
                    continue
                try:
                    k.setValueExternal(self._param_to_knob_value(src_key, params[src_key]))
                except Exception:
                    pass
            ui = st.get('ui', {}) or {}
            if hasattr(self, 'cmb_instr'):
                try:
                    txt = str(ui.get('instr') or self.engine.get_param('instr', 'organ'))
                    if txt:
                        self.cmb_instr.setCurrentText(txt)
                except Exception:
                    pass
            if hasattr(self, 'cmb_wave'):
                try:
                    txt = str(ui.get('wave') or self.engine.get_param('wave', 'sine'))
                    if txt:
                        self.cmb_wave.setCurrentText(txt)
                except Exception:
                    pass
            if hasattr(self, 'cmb_voicing'):
                try:
                    txt = str(ui.get('voicing') or self.engine.get_param('voicing', 'warm'))
                    if txt:
                        self.cmb_voicing.setCurrentText(txt)
                except Exception:
                    pass
            # preset combo is informational; keep if known
            try:
                pname = str((ui.get('preset_combo') if isinstance(ui, dict) else '') or st.get('preset_name') or '')
                if pname and pname in [self.cmb_preset.itemText(i) for i in range(self.cmb_preset.count())]:
                    self.cmb_preset.setCurrentText(pname)
            except Exception:
                pass
            self._sync_engine_from_ui(persist=False)
        finally:
            self._restoring_state = False

    # ---------------- automation
    def _setup_automation(self) -> None:
        try:
            if self._automation_setup_done:
                return
            mgr = getattr(self, 'automation_manager', None)
            tid = str(getattr(self, 'track_id', '') or '')
            if mgr is None or not tid:
                return
            self._automation_setup_done = True
            self._automation_pid_to_engine = {}

            label_map = {
                'tempo': 'Bach Orgel Tremolo Rate',
                'cut': 'Bach Orgel Cut',
                'res': 'Bach Orgel Resonance',
                'attack': 'Bach Orgel Attack',
                'env_amt': 'Bach Orgel Env Amount',
                'tune': 'Bach Orgel Tune',
                'env': 'Bach Orgel Env',
                'dec': 'Bach Orgel Decay',
                'release': 'Bach Orgel Release',
                'accent': 'Bach Orgel Accent',
                'fx_drv': 'Bach Orgel FX Drive',
                'fx_lvl': 'Bach Orgel FX Level',
                "stop16": "Bach Orgel 16'",
                "stop8": "Bach Orgel 8'",
                "stop4": "Bach Orgel 4'",
                "stop2": "Bach Orgel 2'",
                'gain': 'Bach Orgel Gain',
                'mix': 'Bach Orgel Mix',
                'reed': 'Bach Orgel Reed',
                'click': 'Bach Orgel Click',
                'drv': 'Bach Orgel Drive',
                'tremr': 'Bach Orgel Tremolo Rate 2',
                'tremd': 'Bach Orgel Tremolo Depth',
            }

            for key, knob in self._knobs.items():
                pid = self._automation_pid(key, tid)
                self._automation_pid_to_engine[pid] = (lambda v, kk=key: self._apply_automation_value_to_engine(kk, float(v), persist=False))
                try:
                    knob.bind_automation(
                        mgr,
                        pid,
                        name=label_map.get(key, f'Bach Orgel {key}'),
                        track_id=tid,
                        minimum=0.0,
                        maximum=100.0,
                        default=float(knob.value()),
                    )
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
        except Exception:
            pass

    def _automation_pid(self, key: str, track_id: str | None = None) -> str:
        tid = str(track_id if track_id is not None else (self.track_id or ''))
        return f'trk:{tid}:bach_orgel:{key}'

    def _on_automation_parameter_changed(self, parameter_id: str, value: float) -> None:
        try:
            fn = self._automation_pid_to_engine.get(str(parameter_id))
            if fn is None:
                return
            fn(float(value))
        except Exception:
            pass

    # ---------------- ui build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        try:
            top.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass

        # Mindestbreiten verhindern, dass Beschriftungen/Drawbars im Device-Panel
        # unleserlich zusammengedrückt werden. Die Device-Chain scrollt horizontal,
        # daher darf dieses Instrument eine größere bevorzugte Breite anfordern.
        section_min_w = {
            'tempo': 72,
            'syn': 228,
            'ctrl': 162,
            'fx': 118,
            'org': 760,
            'io': 72,
        }

        # TEMPO
        sec_tempo = _Section('TEMPO')
        row = QHBoxLayout(); row.addStretch(1)
        self._knobs['tempo'] = CompactKnob('', 45)
        row.addWidget(self._knobs['tempo'])
        row.addStretch(1)
        sec_tempo.body.addLayout(row)
        sec_tempo.setMinimumWidth(section_min_w['tempo'])
        top.addWidget(sec_tempo, 0)

        # Synthesis
        sec_syn = _Section('Synthesis')
        grid_syn = QGridLayout()
        grid_syn.setHorizontalSpacing(4)
        grid_syn.setVerticalSpacing(4)
        synth_knobs = [
            ('cut', 'CUT', 78), ('res', 'RES', 25), ('attack', 'ATTACK', 8), ('env_amt', 'ENV AMT', 55), ('tune', 'TUNE', 50),
            ('env', 'ENV', 70), ('dec', 'DEC', 20), ('release', 'RELEASE', 30), ('accent', 'ACCENT', 25),
        ]
        for idx, (key, title, init) in enumerate(synth_knobs):
            k = CompactKnob(title, init)
            self._knobs[key] = k
            r = 0 if idx < 5 else 1
            c = idx if idx < 5 else idx - 5
            grid_syn.addWidget(k, r, c)
        sec_syn.body.addLayout(grid_syn)
        sec_syn.setMinimumWidth(section_min_w['syn'])
        top.addWidget(sec_syn, 0)

        # Control
        sec_ctrl = _Section('Control')
        ctrl_grid = QGridLayout()
        ctrl_grid.setHorizontalSpacing(8)
        ctrl_grid.setVerticalSpacing(8)
        ctrl_grid.addWidget(QLabel('INSTR:'), 0, 0)
        self.cmb_instr = QComboBox(); self.cmb_instr.addItems(['organ', 'choral', 'flute', 'bass'])
        ctrl_grid.addWidget(self.cmb_instr, 0, 1)
        ctrl_grid.addWidget(QLabel('WAVE:'), 1, 0)
        self.cmb_wave = QComboBox(); self.cmb_wave.addItems(['sine', 'triangle', 'square', 'saw', 'noise'])
        ctrl_grid.addWidget(self.cmb_wave, 1, 1)
        ctrl_grid.addWidget(QLabel('VOICING:'), 2, 0)
        self.cmb_voicing = QComboBox(); self.cmb_voicing.addItems(['warm', 'clean'])
        self.cmb_voicing.setToolTip('warm = weicher/originaler Orgelklang, clean = offener Klang')
        self.cmb_instr.setMinimumWidth(86)
        self.cmb_wave.setMinimumWidth(86)
        self.cmb_voicing.setMinimumWidth(86)
        ctrl_grid.addWidget(self.cmb_voicing, 2, 1)
        sec_ctrl.body.addLayout(ctrl_grid)
        sec_ctrl.body.addStretch(1)
        sec_ctrl.setMinimumWidth(section_min_w['ctrl'])
        top.addWidget(sec_ctrl, 0)

        # Effects
        sec_fx = _Section('Effects')
        grid_fx = QGridLayout(); grid_fx.setHorizontalSpacing(8)
        self._knobs['fx_drv'] = CompactKnob('DRV', 18)
        self._knobs['fx_lvl'] = CompactKnob('LVL', 82)
        grid_fx.addWidget(self._knobs['fx_drv'], 0, 0)
        grid_fx.addWidget(self._knobs['fx_lvl'], 0, 1)
        sec_fx.body.addLayout(grid_fx)
        sec_fx.body.addStretch(1)
        sec_fx.setMinimumWidth(section_min_w['fx'])
        top.addWidget(sec_fx, 0)

        # Bachs Orgel main block
        sec_org = _Section('Bachs Orgel')
        grid_org = QGridLayout(); grid_org.setHorizontalSpacing(4); grid_org.setVerticalSpacing(4)
        org_knobs = [
            ('stop16', "16'", 20), ('stop8', "8'", 90), ('stop4', "4'", 65), ('stop2', "2'", 25), ('gain', 'GAIN', 65),
            ('mix', 'MIX', 20), ('reed', 'REED', 10), ('click', 'CLICK', 6), ('drv', 'DRV', 10),
            ('tremr', 'TREMR', 45), ('tremd', 'TREMD', 8),
        ]
        for idx, (key, title, init) in enumerate(org_knobs):
            k = CompactKnob(title, init)
            self._knobs[key] = k
            r = idx // 5
            c = idx % 5
            grid_org.addWidget(k, r, c)
        sec_org.body.addLayout(grid_org)

        self._preset_row_widget = QWidget()
        preset_row = QHBoxLayout(self._preset_row_widget); preset_row.setSpacing(6)
        try:
            preset_row.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.cmb_preset = QComboBox()
        self.cmb_preset.setMinimumWidth(140)
        for name in self.PRESETS.keys():
            self.cmb_preset.addItem(name)
        preset_row.addWidget(self.cmb_preset, 0)

        self._preset_quick_wrap_widget = QWidget()
        self._preset_quick_grid = QGridLayout(self._preset_quick_wrap_widget)
        self._preset_quick_grid.setContentsMargins(0, 0, 0, 0)
        self._preset_quick_grid.setHorizontalSpacing(6)
        self._preset_quick_grid.setVerticalSpacing(4)
        preset_row.addWidget(self._preset_quick_wrap_widget, 1)

        self._preset_quick_buttons = []
        for label, pname in [
            ("Prin 8'", "Prinzipal 8'"),
            ('Octaves', 'Oktaven'),
            ('Flute', 'Flöte'),
            ('Plenum', 'Barock Plenum'),
            ('Gottesdienst', 'Gottesdienst'),
            ('Clear', 'Clear'),
        ]:
            btn = QPushButton(label)
            btn.setProperty('preset_name', pname)
            btn.clicked.connect(lambda _=False, pn=pname: self._apply_preset(pn, persist=True))
            self._preset_quick_buttons.append(btn)

        self._preset_compact_menu_btn = QPushButton('Presets ▾')
        self._preset_compact_menu_btn.setToolTip('Preset-Schnellauswahl (kompakt bei sehr kleiner Breite)')
        self._preset_compact_menu = QMenu(self._preset_compact_menu_btn)
        for _label, pname in [
            ("Prin 8'", "Prinzipal 8'"),
            ('Octaves', 'Oktaven'),
            ('Flute', 'Flöte'),
            ('Plenum', 'Barock Plenum'),
            ('Gottesdienst', 'Gottesdienst'),
            ('Clear', 'Clear'),
        ]:
            act = self._preset_compact_menu.addAction(pname)
            act.triggered.connect(lambda _checked=False, pn=pname: self._apply_preset(pn, persist=True))
        self._preset_compact_menu_btn.setMenu(self._preset_compact_menu)
        self._preset_compact_menu_btn.hide()
        preset_row.addWidget(self._preset_compact_menu_btn, 0)
        sec_org.body.addWidget(self._preset_row_widget)
        sec_org.setMinimumWidth(section_min_w['org'])
        top.addWidget(sec_org, 0)

        # I/O stub section (visual parity + future routing)
        sec_io = _Section('I/O')
        io_box = QVBoxLayout()
        io_box.setSpacing(12)
        self.lbl_in = QLabel('IN: •')
        self.lbl_out = QLabel('OUT: •')
        self.lbl_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_out.setAlignment(Qt.AlignmentFlag.AlignCenter)
        io_box.addStretch(1)
        io_box.addWidget(self.lbl_in)
        io_box.addWidget(self.lbl_out)
        io_box.addStretch(1)
        sec_io.body.addLayout(io_box)
        sec_io.setMinimumWidth(section_min_w['io'])
        top.addWidget(sec_io, 0)

        top.addStretch(1)
        root.addLayout(top)

        # bottom device utility buttons (nur Randomize bleibt gewünscht)
        bottom = QHBoxLayout(); bottom.setSpacing(8)
        self.btn_rnd = QPushButton('RND')
        bottom.addStretch(1)
        bottom.addWidget(self.btn_rnd)
        root.addLayout(bottom)

        # connections
        for key, knob in self._knobs.items():
            knob.valueChanged.connect(lambda _v, kk=key: self._on_knob_changed(kk))

        self.cmb_instr.currentTextChanged.connect(self._on_combo_changed)
        self.cmb_wave.currentTextChanged.connect(self._on_combo_changed)
        self.cmb_voicing.currentTextChanged.connect(self._on_combo_changed)
        self.cmb_preset.currentTextChanged.connect(self._on_preset_combo_changed)
        self._preset_combo_signal_ready = True

        self.btn_rnd.clicked.connect(self._randomize_gently)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_preset_row_mode()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            self._update_preset_row_mode()
        except Exception:
            pass

    def _relayout_preset_quick_buttons(self, max_width: int) -> None:
        """Preset-Schnellbuttons in ein einfaches Wrap-Grid umlegen (UI-only)."""
        try:
            grid = getattr(self, '_preset_quick_grid', None)
            buttons = list(getattr(self, '_preset_quick_buttons', []) or [])
            if grid is None or not buttons:
                return

            while grid.count():
                item = grid.takeAt(0)
                try:
                    w = item.widget()
                    if w is not None:
                        w.setParent(self._preset_quick_wrap_widget)
                except Exception:
                    pass

            spacing = int(grid.horizontalSpacing() if grid.horizontalSpacing() >= 0 else 6)
            usable = max(int(max_width or 0), 120)
            row = 0
            col = 0
            row_w = 0

            for btn in buttons:
                bw = int(max(btn.minimumSizeHint().width(), btn.sizeHint().width()))
                need = bw if col == 0 else (spacing + bw)
                if col > 0 and (row_w + need) > usable:
                    row += 1
                    col = 0
                    row_w = 0
                    need = bw
                grid.addWidget(btn, row, col)
                row_w += need
                col += 1
        except Exception:
            pass

    def _update_preset_row_mode(self) -> None:
        """Responsive Preset-Leiste: zuerst Wrap-Layout, erst bei extremer Enge Kompaktmenü."""
        try:
            row_widget = getattr(self, '_preset_row_widget', None)
            combo = getattr(self, 'cmb_preset', None)
            quick_wrap = getattr(self, '_preset_quick_wrap_widget', None)
            quick_buttons = list(getattr(self, '_preset_quick_buttons', []) or [])
            compact_btn = getattr(self, '_preset_compact_menu_btn', None)
            if row_widget is None or combo is None or quick_wrap is None or compact_btn is None or not quick_buttons:
                return

            avail_w = int(row_widget.width() or 0)
            if avail_w <= 0:
                return

            spacing = 6
            combo_w = int(max(combo.minimumSizeHint().width(), combo.sizeHint().width()))
            compact_w = int(max(compact_btn.minimumSizeHint().width(), compact_btn.sizeHint().width()))
            min_btn_w = min(int(max(b.minimumSizeHint().width(), b.sizeHint().width())) for b in quick_buttons)
            full_quick_w = sum(int(max(b.minimumSizeHint().width(), b.sizeHint().width())) for b in quick_buttons)
            full_quick_w += spacing * max(0, len(quick_buttons) - 1)

            slack = 18
            quick_area_w = max(0, avail_w - combo_w - spacing - compact_w - slack)
            wrap_viable_w = max(min_btn_w, 96)
            compact_mode = quick_area_w < wrap_viable_w

            if compact_mode:
                quick_wrap.hide()
                compact_btn.show()
                for b in quick_buttons:
                    b.hide()
            else:
                quick_wrap.show()
                compact_btn.hide()
                for b in quick_buttons:
                    b.show()
                wide_quick_area_w = max(0, avail_w - combo_w - spacing - slack)
                target_quick_w = min(full_quick_w, wide_quick_area_w)
                self._relayout_preset_quick_buttons(target_quick_w)

            try:
                row_widget.updateGeometry()
            except Exception:
                pass
        except Exception:
            pass

    def minimumSizeHint(self):  # noqa: N802
        # Breite so wählen, dass die Bachs-Orgel-Sektion und Drawbars lesbar bleiben.
        # Die Device-Chain hat horizontales Scrolling; daher lieber breiter als gequetscht.
        return QSize(1520, 250)

    def sizeHint(self):  # noqa: N802
        return QSize(1680, 280)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #e0e0e0; }
            #bachSection {
                background: #344b63;
                border: 1px solid #f08a17;
                border-radius: 6px;
            }
            #bachSectionTitle {
                color: #ffb031;
                font-weight: 700;
                padding-left: 2px;
            }
            QLabel { color: #e0e0e0; }
            QComboBox {
                background: #24384d;
                border: 1px solid #f08a17;
                border-radius: 4px;
                padding: 2px 6px;
                min-height: 22px;
            }
            QPushButton {
                background: #e7e7e7;
                color: #111;
                border: 1px solid #b8b8b8;
                border-radius: 4px;
                padding: 4px 10px;
                min-height: 20px;
            }
            QPushButton:hover { border-color: #8a8a8a; }
            QPushButton:checked {
                background: #2bbf6a;
                color: white;
                border-color: #249b57;
            }
            """
        )

    # ---------------- UI events
    def _on_knob_changed(self, key: str) -> None:
        self._apply_automation_value_to_engine(key, float(self._knobs[key].value()), persist=False)
        self._persist_instrument_state()

    def _on_combo_changed(self, _text: str) -> None:
        self._sync_engine_from_ui(persist=True)

    def _on_preset_combo_changed(self, name: str) -> None:
        if not self._preset_combo_signal_ready:
            return
        # Combo selection actively applies preset; button selection also updates combo.
        self._apply_preset(str(name or ''), persist=True)

    def _preview_chord(self) -> None:
        try:
            for p in (48, 55, 60, 64):  # C major-ish organ spread
                _loop_btn = getattr(self, 'btn_loop', None)
                _is_loop = bool(getattr(_loop_btn, 'isChecked', lambda: False)())
                self.engine.trigger_note(p, velocity=110, duration_ms=900 if _is_loop else 420)
            if self.audio_engine is not None:
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass

    def _all_notes_off(self) -> None:
        try:
            self.engine.all_notes_off()
        except Exception:
            pass

    def _randomize_gently(self) -> None:
        import random
        keys = ['stop16', 'stop8', 'stop4', 'stop2', 'reed', 'click', 'drv', 'mix', 'cut', 'res', 'tremd']
        for k in keys:
            try:
                cur = self._knobs[k].value()
                delta = random.randint(-12, 12)
                self._knobs[k].setValue(max(0, min(100, cur + delta)))
            except Exception:
                continue
        try:
            self._persist_instrument_state()
        except Exception:
            pass

    # ---------------- preset + param mapping
    def _apply_preset(self, name: str, *, persist: bool) -> None:
        data = self.PRESETS.get(str(name), None)
        if not isinstance(data, dict):
            return
        self._restoring_state = True
        try:
            # combos first
            instr = str(data.get('instr', self.cmb_instr.currentText()))
            wave = str(data.get('wave', self.cmb_wave.currentText()))
            voicing = str(data.get('voicing', getattr(self, 'cmb_voicing', None).currentText() if hasattr(self, 'cmb_voicing') else 'warm'))
            if instr:
                self.cmb_instr.setCurrentText(instr)
            if wave:
                self.cmb_wave.setCurrentText(wave)
            if hasattr(self, 'cmb_voicing') and voicing:
                self.cmb_voicing.setCurrentText(voicing)
            # knobs
            for key, knob in self._knobs.items():
                if key == 'tremr':
                    # mirror actual trem_rate
                    src = 'trem_rate'
                elif key == 'tremd':
                    src = 'trem_depth'
                else:
                    src = key
                if src not in data:
                    continue
                knob.setValueExternal(self._param_to_knob_value(src, data[src]))
            # sync engine from all controls
            self.engine.set_preset_name(str(name))
            try:
                self.cmb_preset.blockSignals(True)
                self.cmb_preset.setCurrentText(str(name))
            finally:
                try:
                    self.cmb_preset.blockSignals(False)
                except Exception:
                    pass
            self._sync_engine_from_ui(persist=False)
        finally:
            self._restoring_state = False
        if persist:
            self._persist_instrument_state()

    def _sync_engine_from_ui(self, *, persist: bool) -> None:
        try:
            self.engine.set_param('instr', self.cmb_instr.currentText())
            self.engine.set_param('wave', self.cmb_wave.currentText())
            if hasattr(self, 'cmb_voicing'):
                self.engine.set_param('voicing', self.cmb_voicing.currentText())
            for key, knob in self._knobs.items():
                self._apply_automation_value_to_engine(key, float(knob.value()), persist=False)
        except Exception:
            pass
        if persist:
            self._persist_instrument_state()

    def _apply_automation_value_to_engine(self, key: str, ui_value: float, *, persist: bool) -> None:
        # ui_value is 0..100 from CompactKnob / AutomationManager
        v = max(0.0, min(100.0, float(ui_value)))
        # mirror TremR/TremD to actual engine params
        if key == 'tremr':
            self.engine.set_param('trem_rate', 0.25 + (v / 100.0) * 9.75)
        elif key == 'tremd':
            self.engine.set_param('trem_depth', v / 100.0)
        elif key == 'tune':
            self.engine.set_param('tune', ((v - 50.0) / 50.0) * 12.0)
        elif key in ('tempo',):
            self.engine.set_param('tempo', v / 100.0)
        elif key in ('fx_drv', 'fx_lvl', 'cut', 'res', 'attack', 'env_amt', 'env', 'dec', 'release', 'accent',
                     'stop16', 'stop8', 'stop4', 'stop2', 'gain', 'mix', 'reed', 'click', 'drv'):
            self.engine.set_param(key, v / 100.0)
        else:
            # safe fallback
            self.engine.set_param(key, v / 100.0)
        if persist:
            self._persist_instrument_state()

    def _param_to_knob_value(self, key: str, param_value) -> int:
        try:
            fv = float(param_value)
        except Exception:
            fv = 0.0
        if key in ('trem_rate',):
            return int(max(0, min(100, round(((fv - 0.25) / 9.75) * 100.0))))
        if key in ('trem_depth',):
            return int(max(0, min(100, round(fv * 100.0))))
        if key == 'tune':
            return int(max(0, min(100, round((fv / 12.0) * 50.0 + 50.0))))
        return int(max(0, min(100, round(fv * 100.0))))
