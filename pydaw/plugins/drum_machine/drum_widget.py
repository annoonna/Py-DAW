# -*- coding: utf-8 -*-
"""DrumMachineWidget (Pro-DAW-Style Device Panel).

Phase 1 focus:
- Visible, testable skeleton (UI + basic audio wiring)
- 16 pad grid (drag&drop samples onto pads)
- Per-slot local sampler params (Gain/Pan/Tune + basic filter)
- Pattern Generator (rule-based placeholder; later AI/Magenta)

Integration:
- When inserted into a track's device chain, this widget registers a pull-source
  in AudioEngine and tags it with _pydaw_track_id so track faders + VU meters work.
- Note preview from PianoRoll/Notation is routed via existing SamplerRegistry
  by exposing engine.trigger_note().
"""

from __future__ import annotations

import logging
import random
import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QPoint, QMimeData, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QFrame,
    QFileDialog,
    QComboBox,
    QSpinBox,
    QSlider,
    QCheckBox,
    QToolButton,
    QMenu,
    QMessageBox,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QDoubleSpinBox,
    QScrollArea,
    QInputDialog,
)
from PySide6.QtGui import QDrag, QCursor


from pydaw.plugins.sampler.ui_widgets import CompactKnob, WaveformDisplay
from pydaw.model.project import new_id
from pydaw.ui.fx_specs import get_audio_fx, get_note_fx
from pydaw.ui.fx_device_widgets import make_audio_fx_widget, make_note_fx_widget, AudioChainContainerWidget
from .drum_engine import DrumMachineEngine
from . import sample_tools as st


log = logging.getLogger(__name__)

AUDIO_EXTS = "Audio Files (*.wav *.flac *.ogg *.mp3 *.aif *.aiff);;All Files (*)"


def _note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    m = int(midi)
    n = names[m % 12]
    o = (m // 12) - 1  # MIDI standard: C4=60 -> 4
    return f"{n}{o}"


class DrumPadButton(QPushButton):
    """Pad button with drag&drop sample loading."""

    sample_dropped = Signal(int, str)  # slot_idx, path

    def __init__(self, slot_idx: int, text: str, parent=None):
        super().__init__(text, parent)
        self.slot_idx = int(slot_idx)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(72, 44)
        self.setMaximumWidth(120)

    def dragEnterEvent(self, e):
        try:
            if e.mimeData().hasUrls():
                e.acceptProposedAction()
                return
        except Exception:
            pass
        e.ignore()

    def dropEvent(self, e):
        try:
            urls = e.mimeData().urls()
            if not urls:
                e.ignore()
                return
            p = Path(urls[0].toLocalFile())
            if not p.exists():
                e.ignore()
                return
            self.sample_dropped.emit(self.slot_idx, str(p))
            e.acceptProposedAction()
        except Exception:
            e.ignore()


class SlotFxRackDialog(QDialog):
    """Per-slot FX rack dialog (safe, no DAW-core changes)."""

    def __init__(self, engine, persist_cb=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slot FX Rack")
        self.engine = engine
        self.persist_cb = persist_cb
        self._guard = False

        lay = QVBoxLayout(self)
        form = QFormLayout()

        # EQ5
        self.chk_eq = QCheckBox("Enable EQ5")
        self.eq1 = QDoubleSpinBox(); self.eq1.setRange(-24.0, 24.0); self.eq1.setSingleStep(0.5)
        self.eq2 = QDoubleSpinBox(); self.eq2.setRange(-24.0, 24.0); self.eq2.setSingleStep(0.5)
        self.eq3 = QDoubleSpinBox(); self.eq3.setRange(-24.0, 24.0); self.eq3.setSingleStep(0.5)
        self.eq4 = QDoubleSpinBox(); self.eq4.setRange(-24.0, 24.0); self.eq4.setSingleStep(0.5)
        self.eq5 = QDoubleSpinBox(); self.eq5.setRange(-24.0, 24.0); self.eq5.setSingleStep(0.5)
        form.addRow(self.chk_eq)
        form.addRow("EQ1 Low (80Hz) dB", self.eq1)
        form.addRow("EQ2 LowMid (250Hz) dB", self.eq2)
        form.addRow("EQ3 Mid (1kHz) dB", self.eq3)
        form.addRow("EQ4 HighMid (4kHz) dB", self.eq4)
        form.addRow("EQ5 High (12kHz) dB", self.eq5)

        # Distortion
        self.dist = QDoubleSpinBox(); self.dist.setRange(0.0, 1.0); self.dist.setSingleStep(0.01)
        form.addRow("Distortion Mix", self.dist)

        # Delay
        self.delay_mix = QDoubleSpinBox(); self.delay_mix.setRange(0.0, 1.0); self.delay_mix.setSingleStep(0.01)
        self.delay_time = QDoubleSpinBox(); self.delay_time.setRange(0.05, 1.8); self.delay_time.setSingleStep(0.01)
        self.delay_fb = QDoubleSpinBox(); self.delay_fb.setRange(0.0, 0.95); self.delay_fb.setSingleStep(0.01)
        form.addRow("Delay Mix", self.delay_mix)
        form.addRow("Delay Time (sec)", self.delay_time)
        form.addRow("Delay Feedback", self.delay_fb)

        # Reverb / Chorus
        self.reverb = QDoubleSpinBox(); self.reverb.setRange(0.0, 1.0); self.reverb.setSingleStep(0.01)
        self.chorus = QDoubleSpinBox(); self.chorus.setRange(0.0, 1.0); self.chorus.setSingleStep(0.01)
        form.addRow("Reverb Mix", self.reverb)
        form.addRow("Chorus Mix", self.chorus)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.btn_reset = QPushButton("Reset FX")
        btns.addButton(self.btn_reset, QDialogButtonBox.ButtonRole.ActionRole)
        btns.rejected.connect(self.reject)
        self.btn_reset.clicked.connect(self._reset_fx)
        lay.addWidget(btns)

        self._load_from_engine()

        for w in [
            self.chk_eq, self.eq1, self.eq2, self.eq3, self.eq4, self.eq5,
            self.dist, self.delay_mix, self.delay_time, self.delay_fb,
            self.reverb, self.chorus,
        ]:
            try:
                if isinstance(w, QCheckBox):
                    w.toggled.connect(lambda _v=False: self._apply())
                else:
                    w.valueChanged.connect(lambda _v=0.0: self._apply())
            except Exception:
                pass

    def _load_from_engine(self) -> None:
        try:
            st = getattr(self.engine, "state", None)
            if st is None:
                return
            self._guard = True
            self.chk_eq.setChecked(bool(getattr(st, "eq_enabled", False)))
            self.eq1.setValue(float(getattr(st, "eq1_db", 0.0)))
            self.eq2.setValue(float(getattr(st, "eq2_db", 0.0)))
            self.eq3.setValue(float(getattr(st, "eq3_db", 0.0)))
            self.eq4.setValue(float(getattr(st, "eq4_db", 0.0)))
            self.eq5.setValue(float(getattr(st, "eq5_db", 0.0)))
            self.dist.setValue(float(getattr(st, "dist_mix", 0.0)))
            self.delay_mix.setValue(float(getattr(st, "delay_mix", 0.0)))
            self.delay_time.setValue(float(getattr(st, "delay_time_sec", 0.35)))
            self.delay_fb.setValue(float(getattr(st, "delay_fb", 0.35)))
            self.reverb.setValue(float(getattr(st, "reverb_mix", 0.0)))
            self.chorus.setValue(float(getattr(st, "chorus_mix", 0.0)))
        except Exception:
            pass
        finally:
            self._guard = False

    def _apply(self) -> None:
        if self._guard:
            return
        try:
            try:
                self.engine.set_eq5(
                    enabled=bool(self.chk_eq.isChecked()),
                    b1_db=float(self.eq1.value()),
                    b2_db=float(self.eq2.value()),
                    b3_db=float(self.eq3.value()),
                    b4_db=float(self.eq4.value()),
                    b5_db=float(self.eq5.value()),
                )
            except Exception:
                pass
            try:
                self.engine.set_distortion(float(self.dist.value()))
            except Exception:
                pass
            try:
                self.engine.set_fx(
                    chorus_mix=float(self.chorus.value()),
                    delay_mix=float(self.delay_mix.value()),
                    reverb_mix=float(self.reverb.value()),
                )
            except Exception:
                pass
            try:
                self.engine.set_delay_params(time_sec=float(self.delay_time.value()), fb=float(self.delay_fb.value()))
            except Exception:
                pass
            if callable(self.persist_cb):
                try:
                    self.persist_cb()
                except Exception:
                    pass
        except Exception:
            pass

    def _reset_fx(self) -> None:
        try:
            self._guard = True
            self.chk_eq.setChecked(False)
            for w in [self.eq1, self.eq2, self.eq3, self.eq4, self.eq5]:
                w.setValue(0.0)
            self.dist.setValue(0.0)
            self.delay_mix.setValue(0.0)
            self.delay_time.setValue(0.35)
            self.delay_fb.setValue(0.35)
            self.reverb.setValue(0.0)
            self.chorus.setValue(0.0)
        except Exception:
            pass
        finally:
            self._guard = False
        self._apply()


_MIME_PLUGIN = "application/x-pydaw-plugin"
_MIME_SFX_REORDER = "application/x-pydaw-slotfx-reorder"
_MIME_NFX_REORDER = "application/x-pydaw-notefx-reorder"


class _SlotFxSignal:
    """Tiny signal-like helper used by slot-FX widgets (no real project service)."""

    def __init__(self, on_emit=None):
        self._on_emit = on_emit

    def emit(self, *args, **kwargs):  # noqa: ANN002, ANN003
        try:
            if callable(self._on_emit):
                self._on_emit()
        except Exception:
            pass


class _SlotFxDummyAudioEngine:
    """Expose rt_params but never rebuild global track fx maps (safe!)."""

    def __init__(self, rt_params):
        self.rt_params = rt_params

    def rebuild_fx_maps(self, *_args, **_kwargs):
        return


class _SlotFxDummyProject:
    def __init__(self, track_obj):
        self.tracks = [track_obj]


class _SlotFxDummyCtx:
    def __init__(self, proj):
        self.project = proj


class _SlotFxDummyProjectService:
    """Minimal project_service facade expected by fx widgets."""

    def __init__(self, track_obj, on_updated=None):
        self.ctx = _SlotFxDummyCtx(_SlotFxDummyProject(track_obj))
        self.project_updated = _SlotFxSignal(on_emit=on_updated)


class _SlotFxServices:
    """Services facade for reusing existing Track Audio-FX widgets per slot."""

    def __init__(self, track_obj, rt_params, on_updated=None, automation_manager=None, automation_track_id: str = ""):
        self.project = _SlotFxDummyProjectService(track_obj, on_updated=on_updated)
        self.audio_engine = _SlotFxDummyAudioEngine(rt_params)
        # Safe: FX widgets may expose automation menus. They still use their own
        # RT parameter ids, but should appear under the owning drum track.
        self.automation_manager = automation_manager
        self.automation_track_id = str(automation_track_id or getattr(track_obj, 'id', '') or '')



class _NoteFxServices:
    """Services facade for NOTE-FX widgets (Track.note_fx_chain).

    NOTE-FX widgets only require services.project (ctx + project_updated).
    We intentionally do NOT expose audio_engine here to avoid side-effects.
    """

    def __init__(self, track_obj, on_updated=None):
        self.project = _SlotFxDummyProjectService(track_obj, on_updated=on_updated)

class _SlotFxDragHandle(QToolButton):
    """Small drag handle used to reorder slot-FX cards (internal move)."""

    def __init__(self, device_id: str, parent=None):
        super().__init__(parent)
        self._device_id = str(device_id or '')
        self._press_pos: QPoint | None = None
        self.setText('≡')
        self.setToolTip('Drag to reorder')
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedWidth(18)

    def mousePressEvent(self, e):  # noqa: N802, ANN001
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                try:
                    self._press_pos = e.position().toPoint()
                except Exception:
                    self._press_pos = e.pos()
        except Exception:
            self._press_pos = None
        try:
            super().mousePressEvent(e)
        except Exception:
            pass

    def mouseMoveEvent(self, e):  # noqa: N802, ANN001
        try:
            if self._press_pos is None:
                return super().mouseMoveEvent(e)
            try:
                pos = e.position().toPoint()
            except Exception:
                pos = e.pos()
            try:
                if (pos - self._press_pos).manhattanLength() < 6:
                    return
            except Exception:
                pass
            drag = QDrag(self)
            md = QMimeData()
            payload = json.dumps({"device_id": self._device_id}).encode('utf-8')
            md.setData(_MIME_SFX_REORDER, payload)
            drag.setMimeData(md)
            try:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            except Exception:
                pass
            drag.exec(Qt.DropAction.MoveAction)
        except Exception:
            pass
        finally:
            self._press_pos = None
            try:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            except Exception:
                pass

class SlotFxDeviceCard(QFrame):
    """A collapsible device card for per-slot FX (Power/Move/Remove + inline params)."""

    def __init__(self, services, fx_track_id: str, device: dict, *,
                 on_remove=None, on_move=None, on_toggle=None, parent=None):
        super().__init__(parent)
        self.setObjectName('slotFxDeviceCard')
        self._services = services
        self._fx_track_id = str(fx_track_id or '')
        self._device = device
        self._on_remove = on_remove
        self._on_move = on_move
        self._on_toggle = on_toggle
        self._expanded = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet('#slotFxDeviceCard{border:1px solid #2a2a2a;border-radius:8px;background:#101010;}')

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)

        self.btn_expand = QToolButton(self)
        self.btn_expand.setText('▸')
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.clicked.connect(self._toggle_expand)

        self.btn_drag = _SlotFxDragHandle(str(self._device.get('id') or ''), self)

        self.btn_power = QToolButton(self)
        self.btn_power.setCheckable(True)
        self.btn_power.setText('⏻')
        self.btn_power.setToolTip('Bypass (Enable/Disable)')
        self.btn_power.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_power.toggled.connect(self._on_power_toggled)

        name = str(self._device.get('name') or self._device.get('plugin_id') or 'FX')
        self.lbl = QLabel(name)
        self.lbl.setStyleSheet('color:#e0e0e0; font-weight:600;')

        self.btn_up = QToolButton(self)
        self.btn_up.setText('▲')
        self.btn_up.setToolTip('Move up')
        self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up.clicked.connect(lambda _=False: self._safe_move(-1))

        self.btn_down = QToolButton(self)
        self.btn_down.setText('▼')
        self.btn_down.setToolTip('Move down')
        self.btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down.clicked.connect(lambda _=False: self._safe_move(+1))

        self.btn_del = QToolButton(self)
        self.btn_del.setText('✕')
        self.btn_del.setToolTip('Remove')
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(self._safe_remove)

        hdr.addWidget(self.btn_expand, 0)
        hdr.addWidget(self.btn_drag, 0)
        hdr.addWidget(self.btn_power, 0)
        hdr.addWidget(self.lbl, 1)
        hdr.addWidget(self.btn_up, 0)
        hdr.addWidget(self.btn_down, 0)
        hdr.addWidget(self.btn_del, 0)

        root.addLayout(hdr)

        # Body (params)
        self.body = QWidget(self)
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(4, 4, 4, 4)
        self.body_l.setSpacing(4)
        self.body.setVisible(False)
        root.addWidget(self.body)

        # initial states
        # SAFE: avoid emitting toggled() during card construction.
        # Otherwise every UI rebuild re-triggers on_toggle -> slot FX rebuild ->
        # _rebuild_ui() again, which can spiral into repeated LADSPA rebuilds / UI lockups.
        try:
            with QSignalBlocker(self.btn_power):
                self.btn_power.setChecked(bool(self._device.get('enabled', True)))
        except Exception:
            self.btn_power.setChecked(bool(self._device.get('enabled', True)))

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self.btn_expand.setText('▾' if self._expanded else '▸')
        if self._expanded and self.body_l.count() == 0:
            # build inner widget lazily
            try:
                inner = make_audio_fx_widget(self._services, self._fx_track_id, self._device)
            except Exception:
                inner = QLabel('(FX UI failed)')
                inner.setStyleSheet('color:#a0a0a0;')
            if inner is None:
                inner = QLabel('(No UI)')
                inner.setStyleSheet('color:#a0a0a0;')
            self.body_l.addWidget(inner)
        self.body.setVisible(self._expanded)

    def _safe_remove(self):
        try:
            if callable(self._on_remove):
                self._on_remove(str(self._device.get('id') or ''))
        except Exception:
            pass

    def _safe_move(self, delta: int):
        try:
            if callable(self._on_move):
                self._on_move(str(self._device.get('id') or ''), int(delta))
        except Exception:
            pass

    def _on_power_toggled(self, checked: bool):
        try:
            self._device['enabled'] = bool(checked)
        except Exception:
            pass
        try:
            if callable(self._on_toggle):
                self._on_toggle(str(self._device.get('id') or ''), bool(checked))
        except Exception:
            pass

    # ---- Reorder UX: allow dragging the whole card (not only the ≡ handle) ----
    def mousePressEvent(self, e):  # noqa: N802, ANN001
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                # Don't start reorder-drag when interacting with controls
                try:
                    pos = e.position().toPoint()
                except Exception:
                    pos = e.pos()
                w = None
                try:
                    w = self.childAt(pos)
                except Exception:
                    w = None
                try:
                    if w is not None:
                        if w.inherits("QAbstractButton") or w.inherits("QAbstractSlider") or w.inherits("QAbstractSpinBox") or w.inherits("QComboBox") or w.inherits("QLineEdit"):
                            self._drag_press_pos = None
                        else:
                            self._drag_press_pos = pos
                    else:
                        self._drag_press_pos = pos
                except Exception:
                    self._drag_press_pos = pos
        except Exception:
            self._drag_press_pos = None
        try:
            super().mousePressEvent(e)
        except Exception:
            pass

    def mouseMoveEvent(self, e):  # noqa: N802, ANN001
        try:
            if getattr(self, "_drag_press_pos", None) is None:
                return super().mouseMoveEvent(e)
            try:
                pos = e.position().toPoint()
            except Exception:
                pos = e.pos()
            try:
                if (pos - self._drag_press_pos).manhattanLength() < 6:
                    return
            except Exception:
                pass
            did = str(self._device.get("id") or "")
            if not did:
                return
            drag = QDrag(self)
            md = QMimeData()
            md.setData(_MIME_SFX_REORDER, json.dumps({"device_id": did}).encode("utf-8"))
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.MoveAction)
        except Exception:
            pass
        finally:
            try:
                self._drag_press_pos = None
            except Exception:
                pass



class SlotFxInlineRack(QFrame):
    """Unlimited per-slot FX chain rack (Drag&Drop from Browser + inline params).

    Key principle (safe):
    - No DAW core changes
    - DSP uses existing numpy-based fx_chain/FX processors, compiled per slot
    - UI reuses existing Track Audio-FX widgets via a dummy services wrapper
    """

    def __init__(self, persist_cb=None, rebuild_cb=None, status_cb=None, note_fx_cb=None, parent=None):
        super().__init__(parent)
        self.setObjectName('slotFxRackInline')
        self.setAcceptDrops(True)
        try:
            self.setProperty('pydaw_exclusive_drop_target', True)
        except Exception:
            pass
        self._persist_cb = persist_cb
        self._rebuild_cb = rebuild_cb
        self._status_cb = status_cb
        self._note_fx_cb = note_fx_cb


        self._slot = None
        self._fx_track_id = ''
        self._rt_params = None
        self._services = None
        self._track_obj = None

        # cache: plugin_id -> name
        self._fx_name = {s.plugin_id: s.name for s in (get_audio_fx() or [])}

        root = QVBoxLayout(self)
        # Compact density (Bitwig/Ableton feel) — UI-only.
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        # Default collapsed to reduce scrolling; auto-expands on drag enter.
        self._expanded = False
        self.btn_toggle_fx = QToolButton(self)
        self.btn_toggle_fx.setText('▸')
        self.btn_toggle_fx.setToolTip('Slot‑FX ein/ausklappen')
        self.btn_toggle_fx.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_fx.clicked.connect(self._toggle_fx_body)
        self.lbl_title = QLabel('Slot FX')
        self.lbl_title.setStyleSheet('color:#bbb; font-weight:600;')
        self.lbl_hint = QLabel('Drag&Drop Audio‑FX aus Browser hierher (unlimited)')
        self.lbl_hint.setStyleSheet('color:#8a8a8a;')

        self.btn_preset = QToolButton(self)
        self.btn_preset.setText('Preset')
        self.btn_preset.setToolTip('Save/Load Slot‑FX Preset')
        self.btn_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._preset_menu = QMenu(self.btn_preset)
        act_save = self._preset_menu.addAction('Save Preset…')
        act_save.triggered.connect(self._save_preset)
        act_load = self._preset_menu.addAction('Load Preset…')
        act_load.triggered.connect(self._load_preset)
        self._preset_menu.addSeparator()
        act_clear = self._preset_menu.addAction('Clear Slot FX')
        act_clear.triggered.connect(self._clear_chain)
        self.btn_preset.setMenu(self._preset_menu)
        self.btn_add = QToolButton(self)
        self.btn_add.setText('＋')
        self.btn_add.setToolTip('FX hinzufügen')
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self.btn_add)
        for spec in (get_audio_fx() or []):
            act = self._menu.addAction(spec.name)
            act.triggered.connect(lambda _=False, pid=spec.plugin_id: self._add_device(pid))
        self.btn_add.setMenu(self._menu)

        top.addWidget(self.btn_toggle_fx, 0)
        top.addWidget(self.lbl_title, 0)
        top.addWidget(self.lbl_hint, 1)
        top.addWidget(self.btn_preset, 0)
        top.addWidget(self.btn_add, 0)
        root.addLayout(top)

        # CHAIN container (mix/wet gain)
        self.chain_container = None
        self.chain_host = QWidget(self)
        self.chain_lay = QVBoxLayout(self.chain_host)
        self.chain_lay.setContentsMargins(0, 0, 0, 0)
        self.chain_lay.setSpacing(2)
        root.addWidget(self.chain_host)
        try:
            self.chain_host.setVisible(bool(self._expanded))
        except Exception:
            pass

        # device cards list
        self.scroll = QScrollArea(self) if QScrollArea is not None else None
        if self.scroll is not None:
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            # Smaller scroll region: cards are collapsible; keep footprint compact.
            self.scroll.setMinimumHeight(100)
            self.scroll.setMaximumHeight(180)
            self._cards_host = QWidget()
            self._cards_lay = QVBoxLayout(self._cards_host)
            self._cards_lay.setContentsMargins(0, 0, 0, 0)
            self._cards_lay.setSpacing(4)
            self._cards_lay.addStretch(1)
            self.scroll.setWidget(self._cards_host)
            # Drag&Drop needs to work even over the scroll viewport (safe forwarding)
            try:
                self.scroll.setAcceptDrops(True)
            except Exception:
                pass
            try:
                vp = self.scroll.viewport()
                if vp is not None:
                    vp.setAcceptDrops(True)
                    vp.installEventFilter(self)
            except Exception:
                pass
            try:
                self.scroll.installEventFilter(self)
            except Exception:
                pass
            root.addWidget(self.scroll, 1)
        else:
            self._cards_host = QWidget(self)
            self._cards_lay = QVBoxLayout(self._cards_host)
            self._cards_lay.setContentsMargins(0, 0, 0, 0)
            self._cards_lay.setSpacing(4)
            self._cards_lay.addStretch(1)
            root.addWidget(self._cards_host, 1)

        # initial collapsed state must also hide the scroll/card host
        try:
            if self.scroll is not None:
                self.scroll.setVisible(bool(self._expanded))
            else:
                self._cards_host.setVisible(bool(self._expanded))
        except Exception:
            pass

        # Visible insert indicator (cyan) like in the main DevicePanel
        self._drop_line = QFrame(self._cards_host)
        try:
            self._drop_line.setFixedHeight(2)
            self._drop_line.setStyleSheet("background-color:#4fc3f7; border-radius:1px;")
        except Exception:
            pass
        try:
            self._drop_line.hide()
        except Exception:
            pass
        self._last_drop_index = -1

        self._set_drag_visual(False)

    # ---- API ----
    def set_slot(self, slot, track_id: str, rt_params, automation_manager=None):  # noqa: ANN001
        """Bind to current DrumSlot."""
        self._slot = slot
        self._rt_params = rt_params
        try:
            self._fx_track_id = slot.fx_id(str(track_id or '')) if slot is not None else ''
        except Exception:
            self._fx_track_id = str(track_id or '')

        # Ensure chain exists
        try:
            st = getattr(slot, 'state', None)
            if st is not None and not isinstance(getattr(st, 'audio_fx_chain', None), dict):
                st.audio_fx_chain = {"type":"chain","enabled":True,"mix":1.0,"wet_gain":1.0,"devices":[]}
        except Exception:
            pass

        # Build dummy services with a dummy track sharing the chain dict
        try:
            class _Track:
                pass
            tr = _Track()
            tr.id = self._fx_track_id
            tr.audio_fx_chain = getattr(slot.state, 'audio_fx_chain', {"type":"chain","devices":[]})
            self._track_obj = tr
            self._services = _SlotFxServices(
                tr,
                rt_params,
                on_updated=self._on_inner_updated,
                automation_manager=automation_manager,
                automation_track_id=str(track_id or ''),
            )
        except Exception:
            self._services = None
            self._track_obj = None

        self._rebuild_ui()

    # ---- persistence hooks ----
    def _on_inner_updated(self):
        # Called when embedded FX widgets saved params
        self._safe_persist()
        # No rebuild needed for param-only changes

    def _safe_status(self, msg: str) -> None:
        try:
            if callable(self._status_cb):
                self._status_cb(str(msg))
        except Exception:
            pass

    def _safe_persist(self) -> None:
        try:
            if callable(self._persist_cb):
                self._persist_cb()
        except Exception:
            pass

    def _safe_rebuild(self):
        try:
            if self._slot is None:
                return
            if callable(self._rebuild_cb):
                self._rebuild_cb(int(getattr(self._slot.state, 'index', 0)))
        except Exception:
            pass

    # ---- UI build ----
    def _clear_cards(self):
        try:
            # remove all except stretch
            while self._cards_lay.count() > 1:
                it = self._cards_lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
        except Exception:
            pass

    def _rebuild_ui(self):
        self._set_drag_visual(False)
        self._clear_cards()

        if self._slot is None or self._services is None:
            return

        # CHAIN controls
        try:
            # clear existing
            while self.chain_lay.count():
                it = self.chain_lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
        except Exception:
            pass
        try:
            self.chain_container = AudioChainContainerWidget(self._services, self._fx_track_id)
            self.chain_lay.addWidget(self.chain_container)
            # Compact the CHAIN dials inside the inline rack (UI-only).
            try:
                if hasattr(self.chain_container, 'dial_wet'):
                    self.chain_container.dial_wet.setNotchesVisible(False)
                    self.chain_container.dial_wet.setFixedSize(44, 44)
                if hasattr(self.chain_container, 'dial_mix'):
                    self.chain_container.dial_mix.setNotchesVisible(False)
                    self.chain_container.dial_mix.setFixedSize(44, 44)
                # slightly smaller label font inside this container only
                self.chain_container.setStyleSheet('QLabel{font-size:10px; color:#cfcfcf;}')
            except Exception:
                pass
        except Exception:
            self.chain_container = None

        chain = getattr(self._slot.state, 'audio_fx_chain', None)
        devs = []
        if isinstance(chain, dict):
            devs = chain.get('devices', []) or []
        if not isinstance(devs, list):
            devs = []

        # Add cards
        for dev in devs:
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get('plugin_id') or dev.get('type') or '')
            dev.setdefault('name', self._fx_name.get(pid, pid))
            card = SlotFxDeviceCard(
                self._services, self._fx_track_id, dev,
                on_remove=self._remove_device,
                on_move=self._move_device,
                on_toggle=self._toggle_device,
                parent=self._cards_host
            )
            self._cards_lay.insertWidget(self._cards_lay.count() - 1, card)

    # ---- structural ops ----
    def _ensure_chain(self) -> dict:
        if self._slot is None:
            return {"type":"chain","enabled":True,"mix":1.0,"wet_gain":1.0,"devices":[]}
        ch = getattr(self._slot.state, 'audio_fx_chain', None)
        if not isinstance(ch, dict):
            ch = {"type":"chain","enabled":True,"mix":1.0,"wet_gain":1.0,"devices":[]}
            self._slot.state.audio_fx_chain = ch
        devs = ch.get('devices', None)
        if not isinstance(devs, list):
            ch['devices'] = []
        return ch

    def _add_device(self, plugin_id: str, insert_index: int = -1):
        if self._slot is None:
            return
        ch = self._ensure_chain()
        devs = ch.get('devices', [])
        if not isinstance(devs, list):
            devs = []
            ch['devices'] = devs
        did = new_id('sfx')
        # defaults from catalog
        defaults = {}
        try:
            for s in (get_audio_fx() or []):
                if s.plugin_id == plugin_id:
                    defaults = dict(s.defaults or {})
                    break
        except Exception:
            defaults = {}
        dev = {
            'plugin_id': str(plugin_id),
            'id': did,
            'enabled': True,
            'params': defaults,
            'name': self._fx_name.get(str(plugin_id), str(plugin_id)),
        }
        try:
            ii = int(insert_index)
        except Exception:
            ii = -1
        if ii < 0 or ii > len(devs):
            devs.append(dev)
        else:
            devs.insert(ii, dev)
        self._safe_persist()
        self._safe_rebuild()
        self._rebuild_ui()

    def _remove_device(self, device_id: str):
        if self._slot is None:
            return
        ch = self._ensure_chain()
        devs = ch.get('devices', []) or []
        ch['devices'] = [d for d in devs if not (isinstance(d, dict) and str(d.get('id','')) == str(device_id))]
        self._safe_persist()
        self._safe_rebuild()
        self._rebuild_ui()

    def _move_device(self, device_id: str, delta: int):
        if self._slot is None:
            return
        ch = self._ensure_chain()
        devs = ch.get('devices', []) or []
        if not isinstance(devs, list) or len(devs) < 2:
            return
        idx = next((i for i,d in enumerate(devs) if isinstance(d, dict) and str(d.get('id','')) == str(device_id)), None)
        if idx is None:
            return
        ni = max(0, min(len(devs)-1, idx + int(delta)))
        if ni == idx:
            return
        devs.insert(ni, devs.pop(idx))
        ch['devices'] = devs
        self._safe_persist()
        self._safe_rebuild()
        self._rebuild_ui()

    def _toggle_device(self, device_id: str, enabled: bool):
        # enabled already stored in dict by card
        self._safe_persist()
        self._safe_rebuild()

    def _clear_chain(self):
        try:
            if self._slot is None:
                return
            ch = self._ensure_chain()
            ch['devices'] = []
            self._safe_persist()
            self._safe_rebuild()
            self._rebuild_ui()
            self._safe_status('Slot FX cleared')
        except Exception:
            pass

    def _preset_base_dir(self) -> Path:
        try:
            base = Path.home() / '.cache' / 'ChronoScaleStudio' / 'slot_fx_presets'
            base.mkdir(parents=True, exist_ok=True)
            return base
        except Exception:
            return Path('.')

    def _save_preset(self):
        try:
            if self._slot is None:
                return
            ch = self._ensure_chain()
            data = {
                "format": "chronoscale_slot_fx_preset",
                "version": 1,
                "chain": ch,
            }
            default_name = 'slot_fx_preset.json'
            try:
                idx = int(getattr(getattr(self._slot, 'state', None), 'index', 0)) + 1
                default_name = f'slot{idx:02d}_slot_fx.json'
            except Exception:
                pass
            # UI-only: ask for preset name + tags (safe metadata)
            try:
                base = str(default_name).replace('.json','')
                base = base.replace('_slot_fx','').replace('_slotfx','')
                name, ok = QInputDialog.getText(self, 'Slot‑FX Preset', 'Preset name:', text=base)
                if not ok or not str(name).strip():
                    return
                tags_txt, ok2 = QInputDialog.getText(self, 'Slot‑FX Preset', 'Tags (comma separated):', text='')
                tags = []
                try:
                    if ok2 and str(tags_txt).strip():
                        tags = [t.strip() for t in str(tags_txt).split(',') if t.strip()]
                except Exception:
                    tags = []
                safe = re.sub(r'[^A-Za-z0-9 _\-]+', '_', str(name).strip())
                safe = re.sub(r'\s+', '_', safe).strip('_') or 'slot_fx_preset'
                default_name = f'{safe}.json'
                data['meta'] = {'name': str(name).strip(), 'tags': tags, 'created': datetime.now().isoformat(timespec='seconds')}
            except Exception:
                pass
            default_path = str(self._preset_base_dir() / default_name)
            fn, _flt = QFileDialog.getSaveFileName(self, 'Save Slot‑FX Preset', default_path, 'JSON (*.json)')
            if not fn:
                return
            Path(fn).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            self._safe_status(f'Preset saved: {Path(fn).name}')
        except Exception:
            pass

    def _load_preset(self):
        try:
            if self._slot is None:
                return
            default_path = str(self._preset_base_dir())
            fn, _flt = QFileDialog.getOpenFileName(self, 'Load Slot‑FX Preset', default_path, 'JSON (*.json)')
            if not fn:
                return
            raw = Path(fn).read_text(encoding='utf-8', errors='ignore')
            data = json.loads(raw)

            meta = data.get('meta') if isinstance(data, dict) else None
            chain = None
            if isinstance(data, dict) and 'chain' in data:
                chain = data.get('chain')
            elif isinstance(data, dict) and data.get('type') == 'chain':
                chain = data
            if not isinstance(chain, dict):
                self._safe_status('Preset invalid (no chain)')
                return

            # Validate + normalize devices
            known = {s.plugin_id for s in (get_audio_fx() or [])}
            devs_in = chain.get('devices', []) or []
            devs_out = []
            skipped = 0
            for d in devs_in:
                if not isinstance(d, dict):
                    continue
                pid = str(d.get('plugin_id') or d.get('type') or '')
                if pid not in known:
                    skipped += 1
                    continue
                devs_out.append({
                    "plugin_id": pid,
                    "id": new_id('sfx'),
                    "enabled": bool(d.get('enabled', True)),
                    "params": dict(d.get('params') or {}),
                    "name": self._fx_name.get(pid, pid),
                })

            ch = self._ensure_chain()
            # update in-place to keep references stable (safe!)
            ch.clear()
            ch.update({
                "type": "chain",
                "enabled": bool(chain.get('enabled', True)),
                "mix": float(chain.get('mix', 1.0)),
                "wet_gain": float(chain.get('wet_gain', 1.0)),
                "devices": devs_out,
            })

            # keep dummy track in sync
            try:
                if self._track_obj is not None:
                    self._track_obj.audio_fx_chain = ch
            except Exception:
                pass

            self._safe_persist()
            self._safe_rebuild()
            self._rebuild_ui()
            msg = f'Preset loaded: {Path(fn).name}'
            try:
                if isinstance(meta, dict) and str(meta.get('name') or '').strip():
                    msg = f"Preset loaded: {str(meta.get('name')).strip()}"
                    tags = meta.get('tags') if isinstance(meta.get('tags'), list) else []
                    if tags:
                        msg += "  [" + ", ".join([str(t) for t in tags]) + "]"
            except Exception:
                pass
            if skipped:
                msg += f' (skipped {skipped} unknown FX)'
            self._safe_status(msg)
        except Exception:
            pass

    def _drop_index_from_event(self, e) -> int:  # noqa: ANN001
        try:
            # Prefer global cursor position (works even when the drop event is delivered
            # to the QScrollArea viewport instead of this widget).
            try:
                gp = QCursor.pos()
                lp = self._cards_host.mapFromGlobal(gp)
                y = int(lp.y())
            except Exception:
                try:
                    pos = e.position().toPoint()
                except Exception:
                    pos = e.pos()
                # map to cards host
                lp = self._cards_host.mapFrom(self, pos)
                y = int(lp.y())
            # widgets excluding final stretch
            widgets = []
            for i in range(max(0, self._cards_lay.count() - 1)):
                it = self._cards_lay.itemAt(i)
                w = it.widget() if it is not None else None
                if w is not None:
                    widgets.append(w)
            if not widgets:
                return 0
            for idx, w in enumerate(widgets):
                try:
                    cy = int(w.geometry().center().y())
                except Exception:
                    cy = 0
                if y < cy:
                    return idx
            return len(widgets)
        except Exception:
            return 0

    def _move_device_to_index(self, device_id: str, target_index: int):
        try:
            if self._slot is None:
                return
            ch = self._ensure_chain()
            devs = ch.get('devices', []) or []
            if not isinstance(devs, list) or len(devs) < 2:
                return
            src = next((i for i, d in enumerate(devs) if isinstance(d, dict) and str(d.get('id', '')) == str(device_id)), None)
            if src is None:
                return
            ti = max(0, min(len(devs), int(target_index)))
            dev = devs.pop(src)
            if ti > src:
                ti -= 1
            ti = max(0, min(len(devs), ti))
            devs.insert(ti, dev)
            ch['devices'] = devs
            self._safe_persist()
            self._safe_rebuild()
            self._rebuild_ui()
        except Exception:
            pass
    # ---- Drag&Drop from EffectsBrowser ----
    def _set_drag_visual(self, active: bool) -> None:
        try:
            if active:
                self.setStyleSheet('#slotFxRackInline{border:1px dashed #e060e0;background:#0f0f0f;border-radius:8px;}')
            else:
                self.setStyleSheet('#slotFxRackInline{border:1px solid #232323;background:#0f0f0f;border-radius:8px;}')
        except Exception:
            pass

    def _hide_drop_line(self) -> None:
        try:
            if getattr(self, "_drop_line", None) is not None:
                self._drop_line.hide()
        except Exception:
            pass
        try:
            self._last_drop_index = -1
        except Exception:
            pass

    def _show_drop_line_at_index(self, idx: int) -> None:
        """Show a cyan insert line for the given device index (0..n)."""
        try:
            if getattr(self, "_drop_line", None) is None:
                return
            # widgets excluding final stretch
            widgets = []
            for i in range(max(0, self._cards_lay.count() - 1)):
                it = self._cards_lay.itemAt(i)
                w = it.widget() if it is not None else None
                if w is not None:
                    widgets.append(w)

            if not widgets:
                y = 4
            else:
                ii = max(0, min(len(widgets), int(idx)))
                if ii >= len(widgets):
                    y = int(widgets[-1].geometry().bottom() + 6)
                else:
                    y = int(widgets[ii].geometry().top() - 3)

            w = int(self._cards_host.width())
            if w <= 10:
                w = 10
            self._drop_line.setGeometry(0, max(0, y), w, 2)
            self._drop_line.raise_()
            self._drop_line.show()
            self._last_drop_index = int(idx)
        except Exception:
            pass


    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        """Forward Drag&Drop events from the QScrollArea viewport to this rack.

        Qt sends drag events to the viewport widget. Without forwarding, drops can
        appear to "not work" when hovering over the card list. This keeps behavior
        stable without touching any core logic.
        """
        try:
            et = event.type()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop, QEvent.Type.DragLeave):
                # forward to our handlers
                if et == QEvent.Type.DragEnter:
                    self.dragEnterEvent(event)
                    return bool(event.isAccepted())
                if et == QEvent.Type.DragMove:
                    self.dragMoveEvent(event)
                    return bool(event.isAccepted())
                if et == QEvent.Type.Drop:
                    self.dropEvent(event)
                    return bool(event.isAccepted())
                if et == QEvent.Type.DragLeave:
                    self.dragLeaveEvent(event)
                    return bool(event.isAccepted())
        except Exception:
            pass
        return False

    def dragMoveEvent(self, e):  # noqa: N802, ANN001
        try:
            md = e.mimeData()
            if md is not None and md.hasFormat(_MIME_SFX_REORDER):
                e.acceptProposedAction()
                try:
                    self._show_drop_line_at_index(self._drop_index_from_event(e))
                except Exception:
                    pass
                return

            if md is not None and md.hasFormat(_MIME_PLUGIN):
                raw = bytes(md.data(_MIME_PLUGIN))
                payload = json.loads(raw.decode('utf-8', 'ignore'))
                kind = str(payload.get('kind') or '')
                if kind in ('audio_fx', 'note_fx'):
                    e.acceptProposedAction()
                    try:
                        self._show_drop_line_at_index(self._drop_index_from_event(e))
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        e.ignore()


    def dragEnterEvent(self, e):  # noqa: N802, ANN001
        try:
            # auto-expand when user drags FX onto a collapsed rack (UX-only)
            try:
                if not bool(getattr(self, '_expanded', True)):
                    self._expanded = True
                    try:
                        self.btn_toggle_fx.setText('▾')
                    except Exception:
                        pass
                    try:
                        self.chain_host.setVisible(True)
                    except Exception:
                        pass
                    try:
                        if self.scroll is not None:
                            self.scroll.setVisible(True)
                        else:
                            self._cards_host.setVisible(True)
                    except Exception:
                        pass
            except Exception:
                pass
            md = e.mimeData()
            if md is not None and md.hasFormat(_MIME_SFX_REORDER):
                e.acceptProposedAction()
                self._set_drag_visual(True)
                try:
                    self._show_drop_line_at_index(self._drop_index_from_event(e))
                except Exception:
                    pass
                return

            if md is not None and md.hasFormat(_MIME_PLUGIN):
                raw = bytes(md.data(_MIME_PLUGIN))
                payload = json.loads(raw.decode('utf-8', 'ignore'))
                if isinstance(payload, dict):
                    kind = str(payload.get('kind') or '')
                    if kind == 'audio_fx' or (kind == 'note_fx' and callable(self._note_fx_cb)):
                        e.acceptProposedAction()
                        self._set_drag_visual(True)
                        try:
                            self._show_drop_line_at_index(self._drop_index_from_event(e))
                        except Exception:
                            pass
                        return
        except Exception:
            pass
        e.ignore()


    def dragLeaveEvent(self, e):  # noqa: N802, ANN001
        try:
            self._set_drag_visual(False)
            try:
                self._hide_drop_line()
            except Exception:
                pass
        except Exception:
            pass
        try:
            super().dragLeaveEvent(e)
        except Exception:
            pass

    def dropEvent(self, e):  # noqa: N802, ANN001
        try:
            self._set_drag_visual(False)
            try:
                self._hide_drop_line()
            except Exception:
                pass
            md = e.mimeData()
            # Reorder (dragging an existing card)
            if md is not None and md.hasFormat(_MIME_SFX_REORDER):
                raw = bytes(md.data(_MIME_SFX_REORDER))
                payload = json.loads(raw.decode('utf-8', 'ignore'))
                if isinstance(payload, dict):
                    did = str(payload.get('device_id') or '')
                    if did:
                        ti = self._drop_index_from_event(e)
                        self._move_device_to_index(did, ti)
                        e.acceptProposedAction()
                        return

            if md is None or not md.hasFormat(_MIME_PLUGIN):
                e.ignore()
                return
            raw = bytes(md.data(_MIME_PLUGIN))
            payload = json.loads(raw.decode('utf-8', 'ignore'))
            if not isinstance(payload, dict):
                e.ignore()
                return
            kind = str(payload.get('kind') or '')
            pid = str(payload.get('plugin_id') or '')
            if not pid:
                e.ignore()
                return
            if kind == 'audio_fx':
                ti = self._drop_index_from_event(e)
                self._add_device(pid, insert_index=ti)
                e.acceptProposedAction()
                return
            if kind == 'note_fx' and callable(self._note_fx_cb):
                try:
                    self._note_fx_cb(pid)
                except Exception:
                    pass
                try:
                    self._safe_status(f"Note‑FX added: {pid}")
                except Exception:
                    pass
                e.acceptProposedAction()
                return
            e.ignore()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass




    def _toggle_fx_body(self) -> None:
        # Collapse/expand the Slot-FX rack body (UI-only)
        try:
            self._expanded = not bool(getattr(self, '_expanded', True))
        except Exception:
            self._expanded = True
        try:
            self.btn_toggle_fx.setText('▾' if self._expanded else '▸')
        except Exception:
            pass
        try:
            self.chain_host.setVisible(bool(self._expanded))
        except Exception:
            pass
        try:
            if self.scroll is not None:
                self.scroll.setVisible(bool(self._expanded))
            else:
                self._cards_host.setVisible(bool(self._expanded))
        except Exception:
            pass


class NoteFxDeviceCard(QFrame):
    """Collapsible NOTE-FX device card with inline parameter UI."""

    def __init__(
        self,
        services_cb,
        device: dict,
        *,
        on_remove=None,
        on_move=None,
        on_toggle=None,
        on_expand=None,
        expanded: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName('noteFxDeviceCard')
        self._services_cb = services_cb
        self._device = device
        self._on_remove = on_remove
        self._on_move = on_move
        self._on_toggle = on_toggle
        self._on_expand = on_expand
        # Compact-by-default (Bitwig/Ableton style): header always visible, params on demand.
        self._expanded = bool(expanded)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet('#noteFxDeviceCard{border:1px solid #262626;border-radius:8px;background:#0f0f0f;}')

        root = QVBoxLayout(self)
        # Smaller density: reduces scrolling without touching core.
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(3)

        hdr = QHBoxLayout(); hdr.setSpacing(6)

        self.btn_expand = QToolButton(self)
        self.btn_expand.setText('▾' if self._expanded else '▸')
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.clicked.connect(self._toggle_expand)

        self.btn_power = QToolButton(self)
        self.btn_power.setCheckable(True)
        self.btn_power.setText('⏻')
        self.btn_power.setToolTip('Bypass (Enable/Disable)')
        self.btn_power.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_power.toggled.connect(self._on_power_toggled)

        name = str(self._device.get('name') or self._device.get('plugin_id') or 'Note‑FX')
        self.lbl = QLabel(name)
        self.lbl.setStyleSheet('color:#e0e0e0; font-weight:600;')

        self.btn_up = QToolButton(self); self.btn_up.setText('▲'); self.btn_up.setToolTip('Move up'); self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dn = QToolButton(self); self.btn_dn.setText('▼'); self.btn_dn.setToolTip('Move down'); self.btn_dn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_x = QToolButton(self); self.btn_x.setText('✕'); self.btn_x.setToolTip('Remove'); self.btn_x.setCursor(Qt.CursorShape.PointingHandCursor)

        did = str(self._device.get('id') or '')
        self.btn_up.clicked.connect(lambda _=False, did=did: self._safe_move(did, -1))
        self.btn_dn.clicked.connect(lambda _=False, did=did: self._safe_move(did, +1))
        self.btn_x.clicked.connect(lambda _=False, did=did: self._safe_remove(did))

        hdr.addWidget(self.btn_expand, 0)
        hdr.addWidget(self.btn_power, 0)
        hdr.addWidget(self.lbl, 1)
        hdr.addWidget(self.btn_up, 0)
        hdr.addWidget(self.btn_dn, 0)
        hdr.addWidget(self.btn_x, 0)
        root.addLayout(hdr)

        self.body = QWidget(self)
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(2, 2, 2, 2)
        self.body_l.setSpacing(3)
        root.addWidget(self.body)

        self.btn_power.setChecked(bool(self._device.get('enabled', True)))
        self.body.setVisible(bool(self._expanded))
        if self._expanded:
            self._ensure_inner()

    def set_expanded(self, expanded: bool, *, notify: bool = False) -> None:
        """Set expanded state (safe) and optionally notify strip for smart-collapse."""
        try:
            self._expanded = bool(expanded)
            self.btn_expand.setText('▾' if self._expanded else '▸')
            if self._expanded:
                self._ensure_inner()
            self.body.setVisible(bool(self._expanded))
        except Exception:
            pass
        if notify:
            try:
                if callable(self._on_expand):
                    self._on_expand(str(self._device.get('id') or ''), bool(self._expanded))
            except Exception:
                pass

    def _services_and_track(self):
        try:
            if callable(self._services_cb):
                return self._services_cb()
        except Exception:
            pass
        return (None, '')

    def _ensure_inner(self):
        if self.body_l.count() > 0:
            return
        services, track_id = self._services_and_track()
        if services is None or not str(track_id or ''):
            lab = QLabel('(Note‑FX UI unavailable)')
            lab.setStyleSheet('color:#9a9a9a;')
            self.body_l.addWidget(lab)
            return
        try:
            inner = make_note_fx_widget(services, str(track_id), self._device)
        except Exception:
            inner = QLabel('(Note‑FX UI failed)')
            inner.setStyleSheet('color:#9a9a9a;')
        if inner is None:
            inner = QLabel('(No UI)')
            inner.setStyleSheet('color:#9a9a9a;')
        self.body_l.addWidget(inner)
        try:
            if hasattr(inner, 'refresh_from_project'):
                inner.refresh_from_project()
        except Exception:
            pass

    def _toggle_expand(self):
        try:
            self._expanded = not bool(self._expanded)
        except Exception:
            self._expanded = False
        self.btn_expand.setText('▾' if self._expanded else '▸')
        if self._expanded:
            self._ensure_inner()
        self.body.setVisible(bool(self._expanded))
        try:
            if callable(self._on_expand):
                self._on_expand(str(self._device.get('id') or ''), bool(self._expanded))
        except Exception:
            pass

    def mousePressEvent(self, e):  # noqa: N802, ANN001
        # Start reorder drag when user drags the card (safe; ignores interactive widgets)
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                try:
                    pos = e.position().toPoint()
                except Exception:
                    pos = e.pos()
                w = None
                try:
                    w = self.childAt(pos)
                except Exception:
                    w = None
                try:
                    if w is not None:
                        if w.inherits('QAbstractButton') or w.inherits('QAbstractSlider') or w.inherits('QAbstractSpinBox') or w.inherits('QComboBox') or w.inherits('QLineEdit'):
                            self._drag_press_pos = None
                        else:
                            self._drag_press_pos = pos
                    else:
                        self._drag_press_pos = pos
                except Exception:
                    self._drag_press_pos = pos
        except Exception:
            self._drag_press_pos = None
        try:
            super().mousePressEvent(e)
        except Exception:
            pass

    def mouseMoveEvent(self, e):  # noqa: N802, ANN001
        try:
            if getattr(self, '_drag_press_pos', None) is None:
                return super().mouseMoveEvent(e)
            try:
                pos = e.position().toPoint()
            except Exception:
                pos = e.pos()
            try:
                if (pos - self._drag_press_pos).manhattanLength() < 6:
                    return
            except Exception:
                pass
            did = str(self._device.get('id') or '')
            if not did:
                return
            drag = QDrag(self)
            md = QMimeData()
            md.setData(_MIME_NFX_REORDER, json.dumps({'device_id': did}).encode('utf-8'))
            drag.setMimeData(md)
            drag.exec(Qt.DropAction.MoveAction)
        except Exception:
            pass
        finally:
            try:
                self._drag_press_pos = None
            except Exception:
                pass

    def _safe_remove(self, device_id: str):
        try:
            if callable(self._on_remove):
                self._on_remove(str(device_id))
        except Exception:
            pass

    def _safe_move(self, device_id: str, delta: int):
        try:
            if callable(self._on_move):
                self._on_move(str(device_id), int(delta))
        except Exception:
            pass

    def _on_power_toggled(self, checked: bool):
        try:
            self._device['enabled'] = bool(checked)
        except Exception:
            pass
        try:
            if callable(self._on_toggle):
                self._on_toggle(str(self._device.get('id') or ''), bool(checked))
        except Exception:
            pass

class NoteFxInlineStrip(QFrame):
    """Compact collapsible NOTE-FX strip (Track-level), Bitwig-like.

    Safe rules:
    - Touches only Track.note_fx_chain dict (already persisted in project)
    - UI-only: no audio engine refactors
    - Accepts drag&drop from EffectsBrowser (kind: note_fx)
    - Accepts drag-reorder of existing NOTE-FX cards
    """

    def __init__(self, get_track_cb=None, status_cb=None, parent=None):  # noqa: ANN001
        super().__init__(parent)
        self.setObjectName("noteFxInlineStrip")
        try:
            self.setProperty("pydaw_exclusive_drop_target", True)
        except Exception:
            pass
        try:
            self.setAcceptDrops(True)
        except Exception:
            pass

        self._get_track_cb = get_track_cb
        self._status_cb = status_cb

        # UI-only state (not saved): which NOTE-FX card is expanded.
        # Smart rule: keep only one card expanded at a time.
        self._expanded_ids: set[str] = set()
        self._cards_by_id: dict[str, NoteFxDeviceCard] = {}

        self._expanded = False
        self._fx_name = {s.plugin_id: s.name for s in (get_note_fx() or [])}

        self._services = None
        self._services_track_id = ""

        root = QVBoxLayout(self)
        # Compact density to avoid excessive scrolling.
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(4)

        self.btn_toggle = QToolButton(self)
        self.btn_toggle.setText("▸")
        self.btn_toggle.setToolTip("Note‑FX ein/ausklappen")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._toggle)

        self.lbl_title = QLabel("Note‑FX")
        self.lbl_title.setStyleSheet("color:#bbb; font-weight:600;")

        self.lbl_count = QLabel("(0)")
        self.lbl_count.setStyleSheet("color:#8a8a8a;")

        self.btn_add = QToolButton(self)
        self.btn_add.setText("＋")
        self.btn_add.setToolTip("Note‑FX hinzufügen")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self.btn_add)
        for spec in (get_note_fx() or []):
            act = self._menu.addAction(spec.name)
            act.triggered.connect(lambda _=False, pid=spec.plugin_id: self._add(pid, insert_index=-1))
        self.btn_add.setMenu(self._menu)

        # Presets (per track NOTE-FX chain) — Save/Load like Slot-FX.
        self.btn_preset = QToolButton(self)
        self.btn_preset.setText('Preset')
        self.btn_preset.setToolTip('Save/Load Note‑FX Preset')
        self.btn_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._preset_menu = QMenu(self.btn_preset)
        act_save = self._preset_menu.addAction('Save Preset…')
        act_save.triggered.connect(self._save_preset)
        act_load = self._preset_menu.addAction('Load Preset…')
        act_load.triggered.connect(self._load_preset)
        self._preset_menu.addSeparator()
        act_clear = self._preset_menu.addAction('Clear Note‑FX')
        act_clear.triggered.connect(self._clear_chain)
        self.btn_preset.setMenu(self._preset_menu)

        hdr.addWidget(self.btn_toggle, 0)
        hdr.addWidget(self.lbl_title, 0)
        hdr.addWidget(self.lbl_count, 0)
        hdr.addStretch(1)
        hdr.addWidget(self.btn_preset, 0)
        hdr.addWidget(self.btn_add, 0)
        root.addLayout(hdr)

        # Body list (collapsed by default)
        self.body = QWidget(self)
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)

        self.scroll = QScrollArea(self.body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMinimumHeight(60)
        self.scroll.setMaximumHeight(160)

        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self.scroll.setWidget(self._host)

        bl.addWidget(self.scroll, 1)
        root.addWidget(self.body, 1)

        # insert indicator line
        self._drop_line = QFrame(self._host)
        try:
            self._drop_line.setFixedHeight(2)
            self._drop_line.setStyleSheet("background-color:#4fc3f7; border-radius:1px;")
            self._drop_line.hide()
        except Exception:
            pass

        self._apply_collapsed()

        # Forward drag events from viewport
        try:
            vp = self.scroll.viewport()
            if vp is not None:
                vp.setAcceptDrops(True)
                vp.installEventFilter(self)
        except Exception:
            pass
        try:
            self.scroll.setAcceptDrops(True)
            self.scroll.installEventFilter(self)
        except Exception:
            pass

        self.refresh()

    def _status(self, msg: str) -> None:
        try:
            if callable(self._status_cb):
                self._status_cb(str(msg))
        except Exception:
            pass

    def _toggle(self) -> None:
        self._expanded = not bool(self._expanded)
        self._apply_collapsed()

    def _apply_collapsed(self) -> None:
        try:
            self.body.setVisible(bool(self._expanded))
            self.btn_toggle.setText("▾" if self._expanded else "▸")
        except Exception:
            pass

    def _get_track(self):
        try:
            if callable(self._get_track_cb):
                return self._get_track_cb()
        except Exception:
            pass
        return None

    def _emit_project_updated(self) -> None:
        try:
            par = self.parent()
            ps = getattr(par, "project_service", None)
            if ps is not None and hasattr(ps, "project_updated"):
                ps.project_updated.emit()
        except Exception:
            pass

    def _services_for_note_fx(self):
        trk = self._get_track()
        if trk is None:
            return (None, "")
        tid = str(getattr(trk, "id", "") or "")
        if not tid:
            return (None, "")
        try:
            if self._services is None or str(self._services_track_id) != tid:
                self._services_track_id = tid
                self._services = _NoteFxServices(trk, on_updated=self._emit_project_updated)
        except Exception:
            self._services = _NoteFxServices(trk, on_updated=self._emit_project_updated)
            self._services_track_id = tid
        return (self._services, tid)

    def _ensure_chain(self) -> dict:
        trk = self._get_track()
        if trk is None:
            return {"devices": []}
        ch = getattr(trk, "note_fx_chain", None)
        if not isinstance(ch, dict):
            ch = {"devices": []}
            trk.note_fx_chain = ch
        devs = ch.get("devices", None)
        if not isinstance(devs, list):
            ch["devices"] = []
        return ch

    def _make_row(self, dev: dict, *, expanded: bool = False) -> QWidget:
        return NoteFxDeviceCard(
            services_cb=self._services_for_note_fx,
            device=dev,
            on_remove=self._remove,
            on_move=self._move,
            on_toggle=self._toggle_enabled,
            on_expand=self._on_card_expand,
            expanded=bool(expanded),
            parent=self._host,
        )

    def refresh(self) -> None:
        try:
            while self._lay.count() > 1:
                it = self._lay.takeAt(0)
                w = it.widget() if it is not None else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
        except Exception:
            pass

        ch = self._ensure_chain()
        devs = ch.get("devices", []) or []
        if not isinstance(devs, list):
            devs = []
        try:
            self.lbl_count.setText(f"({len(devs)})")
        except Exception:
            pass

        # reset card map
        try:
            self._cards_by_id = {}
        except Exception:
            pass

        # smart expand: if exactly one NOTE-FX, expand it; otherwise keep compact.
        try:
            ids_now = {str(d.get('id') or '') for d in devs if isinstance(d, dict)}
            self._expanded_ids = {i for i in (self._expanded_ids or set()) if i in ids_now}
            if not self._expanded_ids and len(ids_now) == 1:
                self._expanded_ids = {next(iter(ids_now))}
        except Exception:
            pass

        for d in devs:
            if not isinstance(d, dict):
                continue
            did = str(d.get('id') or '')
            exp = bool(did and did in (self._expanded_ids or set()))
            card = self._make_row(d, expanded=exp)
            try:
                if did:
                    self._cards_by_id[did] = card
            except Exception:
                pass
            self._lay.insertWidget(self._lay.count() - 1, card)

        try:
            if len(devs) == 0:
                self._expanded = False
                try:
                    self._expanded_ids = set()
                except Exception:
                    pass
                self._apply_collapsed()
        except Exception:
            pass

    def _add(self, plugin_id: str, insert_index: int = -1) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            pid = str(plugin_id or "").strip()
            if not pid:
                return
            ch = self._ensure_chain()
            devs = ch.get("devices", []) or []
            if not isinstance(devs, list):
                devs = []
            defaults = {}
            name = self._fx_name.get(pid, pid)
            try:
                for s in (get_note_fx() or []):
                    if str(s.plugin_id) == pid:
                        defaults = dict(s.defaults or {})
                        name = str(s.name or pid)
                        break
            except Exception:
                pass
            dev = {"plugin_id": pid, "id": new_id("nfx"), "enabled": True, "params": defaults, "name": name}
            try:
                ii = int(insert_index)
            except Exception:
                ii = -1
            if ii < 0 or ii > len(devs):
                devs.append(dev)
            else:
                devs.insert(ii, dev)
            ch["devices"] = devs
            trk.note_fx_chain = ch
            self._emit_project_updated()
            self._status(f"Note‑FX added: {name}")
            # Smart: focus/expand the newly created device card.
            try:
                self._expanded_ids = {str(dev.get('id') or '')}
            except Exception:
                pass
            try:
                self._expanded = True
                self._apply_collapsed()
            except Exception:
                pass
            self.refresh()
        except Exception:
            pass

    def _remove(self, device_id: str) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            devs = ch.get("devices", []) or []
            ch["devices"] = [d for d in devs if not (isinstance(d, dict) and str(d.get("id", "")) == str(device_id))]
            trk.note_fx_chain = ch
            self._emit_project_updated()
            self.refresh()
        except Exception:
            pass

    def _move(self, device_id: str, delta: int) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            devs = ch.get("devices", []) or []
            if not isinstance(devs, list) or len(devs) < 2:
                return
            idx = next((i for i, d in enumerate(devs) if isinstance(d, dict) and str(d.get("id", "")) == str(device_id)), None)
            if idx is None:
                return
            ni = max(0, min(len(devs) - 1, idx + int(delta)))
            if ni == idx:
                return
            devs.insert(ni, devs.pop(idx))
            ch["devices"] = devs
            trk.note_fx_chain = ch
            self._emit_project_updated()
            self.refresh()
        except Exception:
            pass

    def _move_to_index(self, device_id: str, new_index: int) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            devs = ch.get("devices", []) or []
            if not isinstance(devs, list) or len(devs) < 2:
                return
            idx = next((i for i, d in enumerate(devs) if isinstance(d, dict) and str(d.get("id", "")) == str(device_id)), None)
            if idx is None:
                return
            ni = max(0, min(len(devs) - 1, int(new_index)))
            if ni == idx:
                return
            devs.insert(ni, devs.pop(idx))
            ch["devices"] = devs
            trk.note_fx_chain = ch
            self._emit_project_updated()
            self.refresh()
        except Exception:
            pass

    def _toggle_enabled(self, device_id: str, enabled: bool) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            devs = ch.get("devices", []) or []
            for d in devs:
                if isinstance(d, dict) and str(d.get("id", "")) == str(device_id):
                    d["enabled"] = bool(enabled)
            ch["devices"] = devs
            trk.note_fx_chain = ch
            self._emit_project_updated()
        except Exception:
            pass

    # ---- Smart card expand/collapse (UI-only) ----
    def _on_card_expand(self, device_id: str, expanded: bool) -> None:
        """Keep NOTE-FX UI compact: only one expanded card at a time."""
        did = str(device_id or '')
        if not did:
            return
        if expanded:
            try:
                self._expanded_ids = {did}
            except Exception:
                pass
            # collapse others without rebuilding
            try:
                for oid, card in (self._cards_by_id or {}).items():
                    if oid != did and hasattr(card, 'set_expanded'):
                        card.set_expanded(False, notify=False)
            except Exception:
                pass
        else:
            try:
                if did in (self._expanded_ids or set()):
                    self._expanded_ids.discard(did)
            except Exception:
                pass

    # ---- Presets (per track NOTE-FX chain) ----
    def _preset_base_dir(self) -> Path:
        try:
            base = Path.home() / '.cache' / 'ChronoScaleStudio' / 'note_fx_presets'
            base.mkdir(parents=True, exist_ok=True)
            return base
        except Exception:
            return Path('.')

    def _save_preset(self) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            data = {
                'format': 'chronoscale_note_fx_preset',
                'version': 1,
                'chain': ch,
            }
            default_name = 'note_fx_preset.json'
            try:
                name, ok = QInputDialog.getText(self, 'Note‑FX Preset', 'Preset name:', text='note_fx')
                if not ok or not str(name).strip():
                    return
                tags_txt, ok2 = QInputDialog.getText(self, 'Note‑FX Preset', 'Tags (comma separated):', text='')
                tags = []
                try:
                    if ok2 and str(tags_txt).strip():
                        tags = [t.strip() for t in str(tags_txt).split(',') if t.strip()]
                except Exception:
                    tags = []
                safe = re.sub(r'[^A-Za-z0-9 _\-]+', '_', str(name).strip())
                safe = re.sub(r'\s+', '_', safe).strip('_') or 'note_fx_preset'
                default_name = f'{safe}.json'
                data['meta'] = {'name': str(name).strip(), 'tags': tags, 'created': datetime.now().isoformat(timespec='seconds')}
            except Exception:
                pass
            default_path = str(self._preset_base_dir() / default_name)
            fn, _flt = QFileDialog.getSaveFileName(self, 'Save Note‑FX Preset', default_path, 'JSON (*.json)')
            if not fn:
                return
            Path(fn).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            self._status(f'Preset saved: {Path(fn).name}')
        except Exception:
            pass

    def _load_preset(self) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            default_path = str(self._preset_base_dir())
            fn, _flt = QFileDialog.getOpenFileName(self, 'Load Note‑FX Preset', default_path, 'JSON (*.json)')
            if not fn:
                return
            raw = Path(fn).read_text(encoding='utf-8', errors='ignore')
            data = json.loads(raw)
            meta = data.get('meta') if isinstance(data, dict) else None
            chain = data.get('chain') if isinstance(data, dict) else None
            if not isinstance(chain, dict):
                self._status('Preset invalid (no chain)')
                return
            known = {s.plugin_id for s in (get_note_fx() or [])}
            devs_in = chain.get('devices', []) or []
            devs_out = []
            skipped = 0
            for d in devs_in:
                if not isinstance(d, dict):
                    continue
                pid = str(d.get('plugin_id') or d.get('type') or '')
                if pid not in known:
                    skipped += 1
                    continue
                devs_out.append({
                    'plugin_id': pid,
                    'id': new_id('nfx'),
                    'enabled': bool(d.get('enabled', True)),
                    'params': dict(d.get('params') or {}),
                    'name': self._fx_name.get(pid, pid),
                })

            ch = self._ensure_chain()
            # update in-place to keep references stable (safe)
            ch.clear()
            ch.update({
                'type': 'chain',
                'enabled': bool(chain.get('enabled', True)),
                'devices': devs_out,
            })
            trk.note_fx_chain = ch
            self._emit_project_updated()

            # compact: collapse all cards, but keep strip expanded if it now has devices
            try:
                self._expanded_ids = set()
            except Exception:
                pass
            if devs_out:
                self._expanded = True
                self._apply_collapsed()
            self.refresh()

            msg = f'Preset loaded: {Path(fn).name}'
            try:
                if isinstance(meta, dict) and str(meta.get('name') or '').strip():
                    msg = f"Preset loaded: {str(meta.get('name')).strip()}"
                    tags = meta.get('tags') if isinstance(meta.get('tags'), list) else []
                    if tags:
                        msg += '  [' + ', '.join([str(t) for t in tags]) + ']'
            except Exception:
                pass
            if skipped:
                msg += f' (skipped {skipped} unknown FX)'
            self._status(msg)
        except Exception:
            pass

    def _clear_chain(self) -> None:
        try:
            trk = self._get_track()
            if trk is None:
                return
            ch = self._ensure_chain()
            ch['devices'] = []
            trk.note_fx_chain = ch
            self._emit_project_updated()
            try:
                self._expanded_ids = set()
            except Exception:
                pass
            self.refresh()
            self._status('Note‑FX cleared')
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        try:
            et = event.type()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop, QEvent.Type.DragLeave):
                if et == QEvent.Type.DragEnter:
                    self.dragEnterEvent(event); return bool(event.isAccepted())
                if et == QEvent.Type.DragMove:
                    self.dragMoveEvent(event); return bool(event.isAccepted())
                if et == QEvent.Type.Drop:
                    self.dropEvent(event); return bool(event.isAccepted())
                if et == QEvent.Type.DragLeave:
                    self.dragLeaveEvent(event); return bool(event.isAccepted())
        except Exception:
            pass
        return False

    def _drop_index_from_event(self, e) -> int:  # noqa: ANN001
        try:
            gp = QCursor.pos()
            lp = self._host.mapFromGlobal(gp)
            y = int(lp.y())
            widgets = []
            for i in range(max(0, self._lay.count() - 1)):
                it = self._lay.itemAt(i)
                w = it.widget() if it is not None else None
                if w is not None:
                    widgets.append(w)
            if not widgets:
                return 0
            for idx, w in enumerate(widgets):
                if y < int(w.geometry().center().y()):
                    return idx
            return len(widgets)
        except Exception:
            return 0

    def _show_drop_line(self, idx: int) -> None:
        try:
            widgets = []
            for i in range(max(0, self._lay.count() - 1)):
                it = self._lay.itemAt(i)
                w = it.widget() if it is not None else None
                if w is not None:
                    widgets.append(w)
            if not widgets:
                y = 4
            else:
                ii = max(0, min(len(widgets), int(idx)))
                if ii >= len(widgets):
                    y = int(widgets[-1].geometry().bottom() + 6)
                else:
                    y = int(widgets[ii].geometry().top() - 3)
            ww = int(self._host.width())
            self._drop_line.setGeometry(0, max(0, y), max(10, ww), 2)
            self._drop_line.raise_()
            self._drop_line.show()
        except Exception:
            pass

    def _hide_drop_line(self) -> None:
        try:
            self._drop_line.hide()
        except Exception:
            pass

    def dragEnterEvent(self, e):  # noqa: N802, ANN001
        try:
            md = e.mimeData()
            if md is not None and md.hasFormat(_MIME_NFX_REORDER):
                e.acceptProposedAction()
                self._show_drop_line(self._drop_index_from_event(e))
                return
            if md is not None and md.hasFormat(_MIME_PLUGIN):
                raw = bytes(md.data(_MIME_PLUGIN))
                payload = json.loads(raw.decode("utf-8", "ignore"))
                if isinstance(payload, dict) and str(payload.get("kind") or "") == "note_fx":
                    e.acceptProposedAction()
                    self._show_drop_line(self._drop_index_from_event(e))
                    return
        except Exception:
            pass
        e.ignore()

    def dragMoveEvent(self, e):  # noqa: N802, ANN001
        try:
            md = e.mimeData()
            if md is None:
                e.ignore(); return
            if md.hasFormat(_MIME_NFX_REORDER):
                e.acceptProposedAction()
                self._show_drop_line(self._drop_index_from_event(e))
                return
            if md.hasFormat(_MIME_PLUGIN):
                raw = bytes(md.data(_MIME_PLUGIN))
                payload = json.loads(raw.decode("utf-8", "ignore"))
                if not (isinstance(payload, dict) and str(payload.get("kind") or "") == "note_fx"):
                    e.ignore(); return
                e.acceptProposedAction()
                self._show_drop_line(self._drop_index_from_event(e))
                return
        except Exception:
            pass
        e.ignore()

    def dragLeaveEvent(self, e):  # noqa: N802, ANN001
        try:
            self._hide_drop_line()
        except Exception:
            pass
        try:
            super().dragLeaveEvent(e)
        except Exception:
            pass

    def dropEvent(self, e):  # noqa: N802, ANN001
        try:
            self._hide_drop_line()
            md = e.mimeData()
            if md is None:
                e.ignore(); return
            if md.hasFormat(_MIME_NFX_REORDER):
                raw = bytes(md.data(_MIME_NFX_REORDER))
                payload = json.loads(raw.decode("utf-8", "ignore"))
                if isinstance(payload, dict):
                    did = str(payload.get("device_id") or "")
                    if did:
                        self._move_to_index(did, self._drop_index_from_event(e))
                        e.acceptProposedAction()
                        return
            if not md.hasFormat(_MIME_PLUGIN):
                e.ignore(); return
            raw = bytes(md.data(_MIME_PLUGIN))
            payload = json.loads(raw.decode("utf-8", "ignore"))
            if not (isinstance(payload, dict) and str(payload.get("kind") or "") == "note_fx"):
                e.ignore(); return
            pid = str(payload.get("plugin_id") or "")
            if not pid:
                e.ignore(); return
            self._add(pid, insert_index=self._drop_index_from_event(e))
            e.acceptProposedAction()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass
class DrumMachineWidget(QWidget):
    """Drum Machine device widget."""

    def __init__(self, project_service=None, audio_engine=None, automation_manager=None, parent=None):
        super().__init__(parent)
        self.project_service = project_service
        self.audio_engine = audio_engine
        self.automation_manager = automation_manager
        self._automation_setup_done: bool = False
        self._automation_mgr_connected: bool = False
        self._automation_pid_to_engine: dict[str, callable] = {}
        self._slot_param_ids: dict[int, dict[str, str]] = {}


        self.track_id: Optional[str] = None
        self._slot_media_ids: dict[int, str] = {}
        self._restoring_state: bool = False

        # IMPORTANT: do NOT hard-code 48k. If the user's audio settings run at
        # 44.1k, the drum engine would output silence because pull() checked
        # sr==target_sr.
        sr = 48000
        try:
            if self.audio_engine is not None:
                sr = int(self.audio_engine.get_effective_sample_rate())
        except Exception:
            sr = 48000

        self.engine = DrumMachineEngine(slots=16, base_note=36, target_sr=sr)

        # Pull-source wiring
        self._pull_name: Optional[str] = None
        # Wrap pull so we can attach metadata (bound methods can't reliably hold attrs)
        def _pull(frames: int, sr: int, _eng=self.engine):
            return _eng.pull(frames, sr)

        # Tag for track faders/VU (AudioEngine reads this dynamically)
        _pull._pydaw_track_id = lambda: (self.track_id or "")  # type: ignore[attr-defined]
        self._pull_fn = _pull

        self._selected_slot: int = 0

        # Generator UI state (kept small + deterministic)
        self._gen_seed_mode: str = "Random"  # "Random" or numeric string
        self._smart_assign_enabled: bool = True

        self._build_ui()
        self._apply_styles()

    # ---------------- Device lifecycle
    def set_track_context(self, track_id: str) -> None:
        self.track_id = str(track_id)
        # Bind per-slot FX context (uses AudioEngine RTParamStore)
        try:
            rt = getattr(self.audio_engine, "rt_params", None) if self.audio_engine is not None else None
            if rt is not None:
                self.engine.set_fx_context(self.track_id, rt)
        except Exception:
            pass
        # Register this engine as the instrument preview backend for this track
        # (PianoRoll/Notation note preview routes through SamplerRegistry).
        try:
            if self.track_id:
                from pydaw.plugins.sampler.sampler_registry import get_sampler_registry
                reg = get_sampler_registry()
                if not reg.has_sampler(self.track_id):
                    reg.register(self.track_id, self.engine, self)
        except Exception:
            pass
        # Register pull source once we know the track binding
        try:
            if self.audio_engine is not None and self._pull_name is None:
                self._pull_name = f"drum:{self.track_id}:{id(self) & 0xFFFF:04x}"
                # v0.0.20.654: Check Track.plugin_output_count for multi-output mode
                _output_count = 1
                try:
                    ps = getattr(self, "project_service", None) or (
                        getattr(self.audio_engine, "_project_service", None))
                    if ps is None:
                        # Try via services bridge
                        _svc = getattr(self, "_services", None)
                        ps = getattr(_svc, "project_service", _svc) if _svc else None
                    proj = getattr(ps, "project", None) if ps else None
                    if proj is not None:
                        for _t in getattr(proj, "tracks", []) or []:
                            if str(getattr(_t, "id", "")) == self.track_id:
                                _oc = int(getattr(_t, "plugin_output_count", 0) or 0)
                                if _oc >= 2:
                                    _output_count = _oc
                                    self.engine.set_multi_output(True, _oc)
                                break
                except Exception:
                    pass
                self._pull_fn._pydaw_output_count = _output_count  # type: ignore[attr-defined]
                self.audio_engine.register_pull_source(self._pull_name, self._pull_fn)
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass

        # Restore persisted drum state (samples + params)
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


    # ---------------- Persist/Restore (Projekt-State)
    def _get_track_obj(self):
        try:
            ctx = getattr(self.project_service, 'ctx', None)
            if ctx is None or getattr(ctx, 'project', None) is None:
                return None
            for t in ctx.project.tracks:
                if getattr(t, 'id', '') == str(self.track_id):
                    return t
        except Exception:
            return None
        return None


    
    # ---------------- Note-FX (Track) helper (safe, engine already supports Track.note_fx_chain)
    def _add_note_fx_to_track(self, plugin_id: str, insert_index: int = -1) -> bool:
        try:
            trk = self._get_track_obj()
            if trk is None:
                return False
            pid = str(plugin_id or '').strip()
            if not pid:
                return False
            chain = getattr(trk, 'note_fx_chain', None)
            if not isinstance(chain, dict):
                chain = {"devices": []}
                trk.note_fx_chain = chain
            devs = chain.get("devices", [])
            if not isinstance(devs, list):
                devs = []
                chain["devices"] = devs

            # defaults + display name
            defaults = {}
            name = pid
            try:
                for s in (get_note_fx() or []):
                    if str(s.plugin_id) == pid:
                        defaults = dict(s.defaults or {})
                        name = str(s.name or pid)
                        break
            except Exception:
                pass

            dev = {
                "plugin_id": pid,
                "id": new_id("nfx"),
                "enabled": True,
                "params": defaults,
                "name": name,
            }
            try:
                ii = int(insert_index)
            except Exception:
                ii = -1
            if ii < 0 or ii > len(devs):
                devs.append(dev)
            else:
                devs.insert(ii, dev)

            chain["devices"] = devs
            trk.note_fx_chain = chain

            try:
                if self.project_service is not None and hasattr(self.project_service, "project_updated"):
                    self.project_service.project_updated.emit()
            except Exception:
                pass
            try:
                self._status(f"Note‑FX added: {name}")
            except Exception:
                pass
            try:
                if getattr(self, 'note_fx_strip', None) is not None:
                    self.note_fx_strip.refresh()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _project_root_dir(self) -> Path | None:
        """Project root folder (where the .pydaw.json lives)."""
        try:
            ctx = getattr(self.project_service, 'ctx', None)
            p = getattr(ctx, 'path', None)
            if p:
                return Path(p).parent
        except Exception:
            pass
        return None

    def _find_media_by_filename(self, filename: str) -> tuple[str, str]:
        """Best-effort: find a media item by filename (used as fallback restore)."""
        fn = str(filename or '').strip()
        if not fn:
            return ('', '')
        try:
            ctx = getattr(self.project_service, 'ctx', None)
            if ctx is None or getattr(ctx, 'project', None) is None:
                return ('', '')
            root = self._project_root_dir()
            for m in ctx.project.media:
                p = str(getattr(m, 'path', '') or '')
                if not p:
                    continue
                pp = Path(p)
                if not pp.is_absolute() and root is not None:
                    pp = (root / pp).resolve()
                if pp.name == fn and pp.exists():
                    return (str(pp), str(getattr(m, 'id', '') or ''))
        except Exception:
            return ('', '')
        return ('', '')

    def _find_media_path(self, media_id: str) -> str:
        """Return an absolute path for a media id (works even if paths are still relative)."""
        try:
            ctx = getattr(self.project_service, 'ctx', None)
            if ctx is None or getattr(ctx, 'project', None) is None:
                return ''
            root = self._project_root_dir()
            for m in ctx.project.media:
                if getattr(m, 'id', '') == str(media_id):
                    p = str(getattr(m, 'path', '') or '')
                    if not p:
                        return ''
                    pp = Path(p)
                    if not pp.is_absolute() and root is not None:
                        pp = (root / pp).resolve()
                    return str(pp)
        except Exception:
            return ''
        return ''

    def _persist_instrument_state(self) -> None:
        if self._restoring_state:
            return
        trk = self._get_track_obj()
        if trk is None:
            if self.track_id:
                log.warning("DrumMachine._persist: no track object for %s", self.track_id)
            return
        try:
            st = self.engine.export_state()
            for slot in st.get('slots', []):
                try:
                    idx = int(slot.get('index', -1))
                except Exception:
                    continue

                sp = str(slot.get('sample_path') or '')
                mid = str(self._slot_media_ids.get(idx, '') or '')

                # Late-import safeguard: if a sample was loaded before we had a track_id/media import,
                # import it now so it will be packaged with the project.
                if sp and (not mid) and (self.project_service is not None) and self.track_id:
                    try:
                        load_path, media_id = self.project_service.import_audio_to_project(
                            str(self.track_id), Path(sp), label=Path(sp).stem
                        )
                        if media_id:
                            mid = str(media_id)
                            self._slot_media_ids[idx] = mid
                        if load_path and Path(load_path).exists():
                            # Reload into slot so engine/state points to the project-local copy.
                            try:
                                self.engine.slots[idx].load_sample(str(load_path))
                            except Exception:
                                pass
                            slot['sample_path'] = str(load_path)
                            if isinstance(slot.get('sampler'), dict):
                                slot['sampler']['sample_name'] = str(load_path)
                    except Exception:
                        pass

                # Canonical: persist media id and normalize sample_path to the media item's path.
                if mid:
                    slot['sample_media_id'] = mid
                    mp = self._find_media_path(mid)
                    if mp:
                        slot['sample_path'] = mp
                        if isinstance(slot.get('sampler'), dict):
                            slot['sampler']['sample_name'] = mp
            if getattr(trk, 'instrument_state', None) is None:
                trk.instrument_state = {}

            # Persist generator UI state (safe, backward compatible)
            try:
                st['generator'] = self._export_generator_state()
            except Exception:
                pass
            trk.instrument_state['drum_machine'] = st
            # Invalidate restore guard so next restore sees the new state
            self._last_restored_hash = None
            # Log what we saved
            saved_samples = [(s.get('index'), s.get('sample_path', '')) for s in st.get('slots', []) if s.get('sample_path')]
            log.info("DrumMachine._persist: track=%s, saved %d slots with samples: %s",
                     self.track_id, len(saved_samples), saved_samples)
        except Exception as exc:
            log.error("DrumMachine._persist failed: %s", exc)

    def _rebuild_slot_fx(self, slot_index: int) -> None:
        """Rebuild compiled per-slot FX chain after structural edits (safe)."""
        try:
            if self.engine is None:
                return
            idx = int(slot_index)
            if not (0 <= idx < len(getattr(self.engine, 'slots', []) or [])):
                return
            slot = self.engine.slots[idx]
            rt_params = getattr(getattr(self, 'audio_engine', None), 'rt_params', None)
            slot.rebuild_slot_fx(str(self.track_id or ''), rt_params)
            # Keep the selected inline rack visuals/status in sync after rebuild.
            try:
                if int(getattr(self, '_selected_slot', -1)) == idx and getattr(self, 'fx_inline', None) is not None:
                    self.fx_inline._rebuild_ui()
            except Exception:
                pass
            try:
                self._status(f'Slot FX rebuilt: Pad {idx+1}')
            except Exception:
                pass
        except Exception:
            pass


    def _restore_instrument_state(self) -> None:
        trk = self._get_track_obj()
        if trk is None:
            if self.track_id:
                log.warning("DrumMachine._restore: no track object for %s", self.track_id)
            return
        ist = getattr(trk, 'instrument_state', {}) or {}
        st = ist.get('drum_machine')
        if not isinstance(st, dict):
            log.debug("DrumMachine._restore: no drum_machine state found for track %s (ist keys: %s)",
                     self.track_id, list(ist.keys()) if ist else '(empty)')
            return

        # Guard: skip if we already restored this exact state
        import json
        try:
            state_hash = hash(json.dumps(st, sort_keys=True, default=str))
        except Exception:
            state_hash = id(st)
        if getattr(self, '_last_restored_hash', None) == state_hash:
            return
        self._last_restored_hash = state_hash

        log.info("DrumMachine._restore: restoring state for track %s, %d slots",
                 self.track_id, len(st.get('slots', [])))
        self._restoring_state = True
        try:
            # Restore generator UI (do this early, but without triggering persistence)
            try:
                gen = st.get('generator') if isinstance(st, dict) else None
                if isinstance(gen, dict):
                    self._import_generator_state(gen)
            except Exception:
                pass
            st2 = {k: v for k, v in st.items()}
            slots = []
            for slot in st.get('slots', []):
                sd = dict(slot)                # v0.0.20.194: Robust sample restore (packaged + relocations safe)
                sample_path = ""
                root = self._project_root_dir()

                def _resolve_candidate(val: str) -> str:
                    v = str(val or '').strip()
                    if not v:
                        return ''
                    pth = Path(v)
                    if (not pth.is_absolute()) and (root is not None):
                        pth = (root / pth).resolve()
                    return str(pth)

                # 1) Try media_id first (project-packaged, most reliable)
                mid = str(sd.get('sample_media_id') or '')
                if mid:
                    p = self._find_media_path(mid)
                    if p:
                        pp = Path(p)
                        if pp.exists():
                            sample_path = str(pp)
                            idx0 = sd.get('index')
                            if isinstance(idx0, int):
                                self._slot_media_ids[idx0] = mid
                        else:
                            log.warning("DrumMachine._restore: slot %s media_id %s path missing: %s",
                                        sd.get('index'), mid, p)

                # 2) Try sample_path from state (supports relative paths)
                if not sample_path:
                    sp_raw = str(sd.get('sample_path') or '')
                    sp = _resolve_candidate(sp_raw)
                    if sp and Path(sp).exists():
                        sample_path = sp
                    elif sp_raw:
                        log.warning("DrumMachine._restore: slot %s sample_path does not exist: %s",
                                    sd.get('index'), sp)

                # 3) Try sample_name from nested sampler engine state (fallback)
                if not sample_path:
                    sampler_state = sd.get('sampler')
                    if isinstance(sampler_state, dict):
                        sn_raw = str(sampler_state.get('sample_name') or '')
                        sn = _resolve_candidate(sn_raw)
                        if sn and Path(sn).exists():
                            sample_path = sn
                        elif sn_raw:
                            log.warning("DrumMachine._restore: slot %s sampler.sample_name does not exist: %s",
                                        sd.get('index'), sn)

                # 4) Fallback: match by filename in project media (handles packaging relocations)
                if not sample_path:
                    wanted = ""
                    try:
                        wanted = Path(str(sd.get('sample_path') or '') or str((sd.get('sampler') or {}).get('sample_name') or '')).name
                    except Exception:
                        wanted = ""
                    if wanted:
                        mp, mid2 = self._find_media_by_filename(wanted)
                        if mp and Path(mp).exists():
                            sample_path = mp
                            if mid2:
                                idx0 = sd.get('index')
                                if isinstance(idx0, int):
                                    self._slot_media_ids[idx0] = mid2
                                sd['sample_media_id'] = mid2

                # Update sd with resolved path
                if sample_path:
                    sd['sample_path'] = sample_path
                    if isinstance(sd.get('sampler'), dict):
                        sd['sampler']['sample_name'] = sample_path
                    log.info("DrumMachine._restore: slot %s -> %s", sd.get('index'), sample_path)
                else:
                    has_any = bool(sd.get('sample_media_id') or sd.get('sample_path') or (sd.get('sampler') or {}).get('sample_name'))
                    if has_any:
                        log.warning("DrumMachine._restore: slot %s has references but none exist!", sd.get('index'))

                slots.append(sd)
            st2['slots'] = slots
            try:
                self.engine.import_state(st2)
            except Exception as exc:
                log.error("DrumMachine._restore: engine.import_state failed: %s", exc)
            self._refresh_pad_labels()
            self._refresh_slot_editor()
        finally:
            self._restoring_state = False

    def _import_and_load_sample(self, idx: int, path: str) -> bool:
        """Importiert Sample nach media/ (falls möglich) und lädt es in Slot."""
        slot = self.engine.slots[idx]
        load_path = path
        media_id = ''
        if (self.project_service is not None) and self.track_id:
            try:
                load_path, media_id = self.project_service.import_audio_to_project(
                    str(self.track_id), Path(path), label=Path(path).stem
                )
                log.info("DrumMachine._import: slot %d imported to media: %s (media_id=%s)", idx, load_path, media_id)
            except Exception as exc:
                log.warning("DrumMachine._import: slot %d import_audio_to_project failed: %s, using original: %s", idx, exc, path)
                load_path = path
                media_id = ''
        else:
            log.warning("DrumMachine._import: no project_service or track_id, loading directly: %s", path)
        ok = slot.load_sample(str(load_path))
        if ok and media_id:
            self._slot_media_ids[idx] = str(media_id)
        log.info("DrumMachine._import: slot %d load_sample=%s, path=%s", idx, ok, load_path)
        return ok
    # ---------------- UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)

        # Pads
        pad_frame = QFrame()
        pad_frame.setObjectName("padFrame")
        pad_layout = QVBoxLayout(pad_frame)
        pad_layout.setContentsMargins(4, 4, 4, 4)
        pad_layout.setSpacing(4)

        # v0.0.20.656: Pad Bank Navigation (A/B/C/D = 4×16 = 64 pads)
        bank_row = QHBoxLayout()
        bank_row.setSpacing(2)
        self._pad_bank = 0  # 0=A, 1=B, 2=C, 3=D
        self._bank_buttons: list[QPushButton] = []
        for bi, lbl in enumerate(["A", "B", "C", "D"]):
            bb = QPushButton(lbl)
            bb.setCheckable(True)
            bb.setChecked(bi == 0)
            bb.setFixedSize(28, 20)
            bb.setStyleSheet("QPushButton{font-size:8px;} QPushButton:checked{background:#e060e0;color:#fff;}")
            bb.clicked.connect(lambda _=False, b=bi: self._switch_pad_bank(b))
            bank_row.addWidget(bb)
            self._bank_buttons.append(bb)
        lbl_bank = QLabel("Bank")
        lbl_bank.setStyleSheet("color:#999;font-size:7px;")
        bank_row.addWidget(lbl_bank)
        bank_row.addStretch(1)
        pad_layout.addLayout(bank_row)

        pad_grid = QGridLayout()
        pad_grid.setContentsMargins(0, 0, 0, 0)
        pad_grid.setHorizontalSpacing(4)
        pad_grid.setVerticalSpacing(4)

        self.pads: list[DrumPadButton] = []
        for i, slot in enumerate(self.engine.slots[:16]):
            note = self.engine.base_note + i
            label = f"{i+1}\n{slot.state.name}\n{_note_name(note)}"
            b = DrumPadButton(i, label)
            b.clicked.connect(lambda _=False, idx=i: self._select_slot(idx))
            b.sample_dropped.connect(self._on_pad_sample_dropped)
            b.pressed.connect(lambda idx=i: self._preview_slot(idx))
            self.pads.append(b)
            r, c = divmod(i, 4)
            pad_grid.addWidget(b, r, c)

        pad_layout.addLayout(pad_grid)

        top.addWidget(pad_frame, 0)

        # Editor + AI
        right = QVBoxLayout()
        right.setSpacing(6)

        # --- Drum Pattern Generator (AI-like, but lightweight + deterministic)
        ai_box = QFrame()
        ai_box.setObjectName("aiBox")
        ai_l = QGridLayout(ai_box)
        ai_l.setContentsMargins(6, 6, 6, 6)
        ai_l.setHorizontalSpacing(8)
        ai_l.setVerticalSpacing(6)

        # Reuse the broad genre/context lists from AI Composer (editable = "alle Genres")
        try:
            from pydaw.music.ai_composer import GENRES as _GENRES, CONTEXTS as _CONTEXTS
            genres = list(_GENRES)
            contexts = list(_CONTEXTS)
        except Exception:
            genres = [
                "Classic", "80s Pop", "Punk", "Electro", "Electro-Punk",
                "Hip-Hop", "R&B", "Industrial", "Hardcore", "Drum & Bass",
                "Metal", "Trash Metal", "Gottesdienst",
            ]
            contexts = ["Neutral", "Gottesdienst", "Hofmusik", "Schlossmusik", "Club"]

        self.cmb_genre_a = QComboBox(); self.cmb_genre_a.setEditable(True)
        self.cmb_genre_a.addItems(genres)
        self.cmb_genre_a.setCurrentText("Electro")

        self.cmb_genre_b = QComboBox(); self.cmb_genre_b.setEditable(True)
        self.cmb_genre_b.addItems(genres)
        self.cmb_genre_b.setCurrentText("Hardcore")

        self.sld_hybrid = QSlider(Qt.Orientation.Horizontal)
        self.sld_hybrid.setRange(0, 100)
        self.sld_hybrid.setValue(35)

        self.cmb_context = QComboBox()
        self.cmb_context.addItems(contexts)
        self.cmb_context.setCurrentText("Neutral")

        self.cmb_grid = QComboBox()
        self.cmb_grid.addItems(["1/8", "1/16", "1/32"])
        self.cmb_grid.setCurrentText("1/16")

        self.sld_swing = QSlider(Qt.Orientation.Horizontal)
        self.sld_swing.setRange(0, 100)
        self.sld_swing.setValue(0)

        self.sld_density = QSlider(Qt.Orientation.Horizontal)
        self.sld_density.setRange(0, 100)
        self.sld_density.setValue(65)

        self.sld_intensity = QSlider(Qt.Orientation.Horizontal)
        self.sld_intensity.setRange(0, 100)
        self.sld_intensity.setValue(55)

        self.spn_bars = QSpinBox()
        self.spn_bars.setRange(1, 64)
        self.spn_bars.setValue(1)

        self.chk_smart_assign = QCheckBox("Smart-Assign Samples")
        self.chk_smart_assign.setChecked(True)

        self.btn_random = QPushButton("Random")
        self.btn_generate = QPushButton("Generate → Clip")

        self.btn_random.clicked.connect(self._randomize_style)
        self.btn_generate.clicked.connect(self._generate_to_clip)

        # Row 0
        ai_l.addWidget(QLabel("Genre A"), 0, 0)
        ai_l.addWidget(self.cmb_genre_a, 0, 1)
        ai_l.addWidget(QLabel("Genre B"), 0, 2)
        ai_l.addWidget(self.cmb_genre_b, 0, 3)
        ai_l.addWidget(QLabel("Mix"), 0, 4)
        ai_l.addWidget(self.sld_hybrid, 0, 5)

        # Row 1
        ai_l.addWidget(QLabel("Kontext"), 1, 0)
        ai_l.addWidget(self.cmb_context, 1, 1)
        ai_l.addWidget(QLabel("Grid"), 1, 2)
        ai_l.addWidget(self.cmb_grid, 1, 3)
        ai_l.addWidget(QLabel("Bars"), 1, 4)
        ai_l.addWidget(self.spn_bars, 1, 5)

        # Row 2
        ai_l.addWidget(QLabel("Swing"), 2, 0)
        ai_l.addWidget(self.sld_swing, 2, 1)
        ai_l.addWidget(QLabel("Density"), 2, 2)
        ai_l.addWidget(self.sld_density, 2, 3)
        ai_l.addWidget(QLabel("Intensity"), 2, 4)
        ai_l.addWidget(self.sld_intensity, 2, 5)

        # Row 3
        ai_l.addWidget(self.chk_smart_assign, 3, 0, 1, 2)
        ai_l.addWidget(self.btn_random, 3, 4)
        ai_l.addWidget(self.btn_generate, 3, 5)

        self.chk_smart_assign.toggled.connect(self._on_smart_assign_toggled)

        # Persist generator UI changes (so project save/load is reproducible)
        try:
            for w in [
                self.cmb_genre_a, self.cmb_genre_b, self.cmb_context, self.cmb_grid,
            ]:
                w.currentTextChanged.connect(lambda _t="": self._on_generator_ui_changed())
            for w in [
                self.sld_hybrid, self.sld_swing, self.sld_density, self.sld_intensity,
            ]:
                w.valueChanged.connect(lambda _v=0: self._on_generator_ui_changed())
            self.spn_bars.valueChanged.connect(lambda _v=0: self._on_generator_ui_changed())
            self.chk_smart_assign.toggled.connect(lambda _v=False: self._on_generator_ui_changed())
        except Exception:
            pass

        right.addWidget(ai_box)

        # --- Slot editor
        edit_box = QFrame()
        edit_box.setObjectName("editBox")
        edit_l = QVBoxLayout(edit_box)
        edit_l.setContentsMargins(6, 6, 6, 6)
        edit_l.setSpacing(6)

        self.lbl_slot = QLabel("Slot 1")
        self.lbl_file = QLabel("No sample")
        self.lbl_file.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        file_row = QHBoxLayout()
        self.btn_load = QPushButton("Load")
        self.btn_clear = QPushButton("Clear")
        self.btn_load.clicked.connect(self._load_sample_dialog)
        self.btn_clear.clicked.connect(self._clear_sample)
        file_row.addWidget(self.lbl_slot)
        file_row.addSpacing(8)
        file_row.addWidget(self.lbl_file, 1)
        file_row.addWidget(self.btn_load)
        file_row.addWidget(self.btn_clear)

        edit_l.addLayout(file_row)

        # Sample Tools (triangle menu) — safe offline operations (non-destructive)
        tools_row = QHBoxLayout()
        tools_row.setContentsMargins(0, 0, 0, 0)
        tools_row.setSpacing(6)
        lbl_tools = QLabel("Sample")
        lbl_tools.setStyleSheet("color:#9a9a9a;")
        self.btn_sample_tools = QToolButton()
        self.btn_sample_tools.setText("▾")
        self.btn_sample_tools.setToolTip("Sample Tools")
        self.btn_sample_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sample_tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu_sample_tools = self._build_sample_tools_menu()
        self.btn_sample_tools.setMenu(self._menu_sample_tools)
        tools_row.addWidget(lbl_tools)
        tools_row.addStretch(1)
        tools_row.addWidget(self.btn_sample_tools)
        edit_l.addLayout(tools_row)

        # Region Start/End (per slot)
        region_row = QHBoxLayout()
        region_row.setContentsMargins(0, 0, 0, 0)
        region_row.setSpacing(6)
        self.kn_start = CompactKnob("Start", 0)
        self.kn_end = CompactKnob("End", 100)
        region_row.addWidget(self.kn_start)
        region_row.addWidget(self.kn_end)
        region_row.addStretch(1)
        edit_l.addLayout(region_row)

        self.kn_start.valueChanged.connect(lambda v: self._slot_set_start(v))
        self.kn_end.valueChanged.connect(lambda v: self._slot_set_end(v))

        self.wave = WaveformDisplay(self.engine.slots[0].engine)
        edit_l.addWidget(self.wave)

        knobs = QHBoxLayout()
        knobs.setSpacing(6)
        self.kn_gain = CompactKnob("Gain", 80)
        self.kn_pan = CompactKnob("Pan", 50)
        self.kn_tune = CompactKnob("Tune", 50)
        self.kn_cut = CompactKnob("Cut", 100)
        self.kn_res = CompactKnob("Res", 20)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["off", "lowpass", "highpass", "bandpass"])

        knobs.addWidget(self.kn_gain)
        knobs.addWidget(self.kn_pan)
        knobs.addWidget(self.kn_tune)
        knobs.addWidget(self.cmb_filter)
        knobs.addWidget(self.kn_cut)
        knobs.addWidget(self.kn_res)

        # v0.0.20.656: Choke Group selector (0 = off, 1-8 = mutual exclusion)
        lbl_choke = QLabel("Choke:")
        lbl_choke.setStyleSheet("color:#999;font-size:8px;")
        self.sp_choke = QSpinBox()
        self.sp_choke.setRange(0, 8)
        self.sp_choke.setValue(0)
        self.sp_choke.setFixedWidth(42)
        self.sp_choke.setFixedHeight(22)
        self.sp_choke.setToolTip("Choke Group (0=off, 1-8=mutual exclusion, e.g. Hi-Hat Open/Closed)")
        self.sp_choke.valueChanged.connect(self._slot_set_choke_group)
        knobs.addWidget(lbl_choke)
        knobs.addWidget(self.sp_choke)

        knobs.addStretch(1)

        edit_l.addLayout(knobs)

        # Track NOTE-FX (Bitwig-like: before instrument) — collapsible strip
        self.note_fx_strip = NoteFxInlineStrip(get_track_cb=self._get_track_obj, status_cb=self._status, parent=self)
        edit_l.addWidget(self.note_fx_strip)

        fx_row = QHBoxLayout()
        fx_row.setContentsMargins(0, 0, 0, 0)
        fx_row.setSpacing(8)
        lbl_fx = QLabel("FX")
        lbl_fx.setStyleSheet("color:#9a9a9a;")
        self.lbl_fx_chain = QLabel("(none)")
        self.lbl_fx_chain.setStyleSheet("color:#cfcfcf;")
        self.btn_fx_rack = QPushButton("Details…")
        self.btn_fx_rack.clicked.connect(self._open_fx_rack_dialog)
        fx_row.addWidget(lbl_fx)
        fx_row.addWidget(self.lbl_fx_chain, 1)
        fx_row.addWidget(self.btn_fx_rack)
        edit_l.addLayout(fx_row)

        self.fx_inline = SlotFxInlineRack(persist_cb=self._persist_instrument_state, rebuild_cb=self._rebuild_slot_fx, status_cb=self._status, note_fx_cb=self._add_note_fx_to_track, parent=self)
        edit_l.addWidget(self.fx_inline)

        # Connect knobs
        self.kn_gain.valueChanged.connect(lambda v: self._slot_set_gain(v))
        self.kn_pan.valueChanged.connect(lambda v: self._slot_set_pan(v))
        self.kn_tune.valueChanged.connect(lambda v: self._slot_set_tune(v))
        self.kn_cut.valueChanged.connect(lambda v: self._slot_set_cut(v))
        self.kn_res.valueChanged.connect(lambda v: self._slot_set_res(v))
        self.cmb_filter.currentTextChanged.connect(lambda t: self._slot_set_filter(t))

        right.addWidget(edit_box, 1)

        top.addLayout(right, 1)
        root.addLayout(top)

        self._select_slot(0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            #padFrame {background:#141414;border:1px solid #232323;border-radius:6px;}
            #aiBox {background:#101010;border:1px solid #232323;border-radius:6px;}
            #editBox {background:#101010;border:1px solid #232323;border-radius:6px;}
            QPushButton {background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:6px;color:#ddd;}
            QPushButton:hover {border:1px solid #3a3a3a;}
            QPushButton:pressed {background:#151515;}
            QToolButton {background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:4px;color:#ddd;}
            QToolButton:hover {border:1px solid #3a3a3a;}
            QToolButton:pressed {background:#151515;}
            QLabel {color:#cfcfcf;}
            QComboBox {background:#151515;border:1px solid #2a2a2a;border-radius:4px;padding:2px;color:#ddd;}
            QSpinBox {background:#151515;border:1px solid #2a2a2a;border-radius:4px;padding:2px;color:#ddd;}
            """
        )

    # ---------------- Pad actions
    def _select_slot(self, idx: int) -> None:
        """Select a pad. idx is VISUAL index (0-15) within current bank."""
        bank_offset = int(getattr(self, "_pad_bank", 0) or 0) * 16
        engine_idx = bank_offset + int(max(0, min(15, idx)))
        # Ensure engine has enough slots
        if engine_idx >= len(self.engine.slots):
            try:
                self.engine.expand_slots(engine_idx + 1)
            except Exception:
                pass
        if engine_idx >= len(self.engine.slots):
            engine_idx = int(max(0, min(len(self.engine.slots) - 1, idx)))
        self._selected_slot = engine_idx
        for i, b in enumerate(self.pads):
            if i == int(idx):
                b.setStyleSheet("border:2px solid #e060e0;")
            else:
                b.setStyleSheet("")
        self._refresh_slot_editor()

    def _preview_slot(self, idx: int) -> None:
        """Preview a pad. idx is VISUAL index (0-15) within current bank."""
        try:
            bank_offset = int(getattr(self, "_pad_bank", 0) or 0) * 16
            engine_idx = bank_offset + int(idx)
            if engine_idx >= len(self.engine.slots):
                try:
                    self.engine.expand_slots(engine_idx + 1)
                except Exception:
                    return
            pitch = self.engine.base_note + engine_idx
            self.engine.trigger_note(pitch, velocity=110, duration_ms=None)
            if self.audio_engine is not None:
                self.audio_engine.ensure_preview_output()
        except Exception:
            pass

    def _switch_pad_bank(self, bank: int) -> None:
        """v0.0.20.656: Switch pad bank (0=A, 1=B, 2=C, 3=D)."""
        try:
            bank = int(max(0, min(3, bank)))
            self._pad_bank = bank
            # Expand engine if needed
            needed = (bank + 1) * 16
            if needed > len(self.engine.slots):
                self.engine.expand_slots(needed)
            # Update bank button states
            for i, bb in enumerate(self._bank_buttons):
                bb.setChecked(i == bank)
            # Refresh pad labels
            self._refresh_pad_labels()
            # Select first pad in new bank
            self._select_slot(0)
        except Exception:
            pass
            pass

    def _on_pad_sample_dropped(self, idx: int, path: str) -> None:
        # v0.0.20.656: Map visual pad index to engine slot index via bank offset
        bank_offset = int(getattr(self, "_pad_bank", 0) or 0) * 16
        idx = bank_offset + int(idx)
        # Expand engine if needed
        if idx >= len(self.engine.slots):
            try:
                self.engine.expand_slots(idx + 1)
            except Exception:
                pass
        if idx >= len(self.engine.slots):
            return
        log.info("DrumMachine: sample dropped on pad %d: %s", idx, path)
        # Smart-Assign is useful for bulk filling (kick/snare/hat keywords).
        # But when the user drops directly onto a specific pad, that is an
        # explicit intent and must be respected. Otherwise it feels "broken"
        # (e.g. dropping on FX2 ends up in FX1).
        #
        # Safe rule:
        # - For direct pad-drop, only smart-assign if the target pad is empty
        #   AND it is within the classic drum slots (0..7). FX/ride/crash/etc.
        #   (>=8) are treated as explicit destination.
        if self._smart_assign_enabled and (0 <= idx <= 7):
            try:
                if not self.engine.slots[idx].state.sample_path:
                    target_idx = self._resolve_target_slot_for_sample(idx, path)
                    if target_idx != idx:
                        try:
                            self._status(
                                f"Smart-Assign: {Path(path).name} → Slot {target_idx+1} ({self.engine.slots[target_idx].state.name})"
                            )
                        except Exception:
                            pass
                        idx = int(target_idx)
            except Exception:
                pass
        ok = False
        try:
            ok = self._import_and_load_sample(idx, path)
        except Exception as exc:
            log.error("DrumMachine: _import_and_load_sample failed for pad %d: %s", idx, exc)
            ok = False
        if ok:
            self._update_pad_text(idx)
            if idx == self._selected_slot:
                self._refresh_slot_editor()
            self._persist_instrument_state()
        else:
            self._status(f"Sample konnte nicht geladen werden: {Path(path).name}")

    def _update_pad_text(self, idx: int) -> None:
        """Update pad button text. idx = engine slot index."""
        bank_offset = int(getattr(self, "_pad_bank", 0) or 0) * 16
        visual_idx = int(idx) - bank_offset
        if not (0 <= visual_idx < len(self.pads)):
            return  # Not visible in current bank
        if int(idx) >= len(self.engine.slots):
            return
        slot = self.engine.slots[int(idx)]
        note = self.engine.base_note + int(idx)
        base = f"{idx+1}\n{slot.state.name}\n{_note_name(note)}"
        if slot.state.sample_path:
            base += f"\n{Path(slot.state.sample_path).stem[:10]}"
        self.pads[visual_idx].setText(base)

    # ---------------- Slot editor
    def _current_slot(self):
        return self.engine.slots[int(self._selected_slot)]

    def _refresh_slot_editor(self) -> None:
        slot = self._current_slot()
        self.lbl_slot.setText(f"Slot {slot.state.index+1} — {slot.state.name}  ({_note_name(self.engine.base_note + slot.state.index)})")
        self.lbl_file.setText(Path(slot.state.sample_path).name if slot.state.sample_path else "No sample")

        # Rebind waveform display to selected slot engine
        try:
            self.wave.engine = slot.engine
        except Exception:
            pass
        try:
            if slot.engine.samples is not None:
                self.wave.samples = slot.engine.samples
        except Exception:
            pass

        # Update knobs from engine state.
        # IMPORTANT (safe): use external updates so we do NOT seed automation parameters
        # (otherwise slot changes can copy values across slots).
        try:
            st = slot.engine.state
            self.kn_gain.setValueExternal(int(float(getattr(st, "gain", 0.8)) * 100))
            pan = float(getattr(st, "pan", 0.0))
            self.kn_pan.setValueExternal(int((pan + 1.0) * 50))

            # tune knob is semitone offset mapped around 50
            # we store tune in root_note offset concept: compute current ratio -> semitones
            root = int(getattr(slot.engine, "root_note", self.engine.base_note + slot.state.index))
            # ratio is derived at trigger time; here we keep as knob state only.
            self.kn_tune.setValueExternal(int(getattr(self, "_tune_knob_cache", {}).get(slot.state.index, 50)))

            ftype = str(getattr(st, "filter_type", "off"))
            if ftype not in ("off", "lowpass", "highpass", "bandpass"):
                ftype = "off"
            try:
                with QSignalBlocker(self.cmb_filter):
                    self.cmb_filter.setCurrentText(ftype)
            except Exception:
                try:
                    self.cmb_filter.setCurrentText(ftype)
                except Exception:
                    pass

            cutoff = float(getattr(st, "cutoff_hz", 8000.0))
            # map 20..20000 -> 0..100 (log-ish)
            cut01 = (max(20.0, min(20000.0, cutoff)) - 20.0) / (20000.0 - 20.0)
            self.kn_cut.setValueExternal(int(cut01 * 100))

            q = float(getattr(st, "q", 0.707))
            q01 = (max(0.25, min(12.0, q)) - 0.25) / (12.0 - 0.25)
            self.kn_res.setValueExternal(int(q01 * 100))

            sp = float(getattr(st, "start_position", 0.0))
            ep = float(getattr(st, "end_position", 1.0))
            self.kn_start.setValueExternal(int(max(0.0, min(1.0, sp)) * 100))
            self.kn_end.setValueExternal(int(max(0.0, min(1.0, ep)) * 100))
        except Exception:
            pass

        # v0.0.20.656: Sync choke group spinbox
        try:
            choke = int(getattr(slot.state, "choke_group", 0) or 0)
            self.sp_choke.blockSignals(True)
            self.sp_choke.setValue(choke)
            self.sp_choke.blockSignals(False)
        except Exception:
            try:
                self.sp_choke.blockSignals(False)
            except Exception:
                pass

        try:
            st = slot.engine.state
            parts = []
            if bool(getattr(st, "eq_enabled", False)):
                parts.append("EQ5")
            if float(getattr(st, "dist_mix", 0.0)) > 0.0001:
                parts.append("Dist")
            if float(getattr(st, "delay_mix", 0.0)) > 0.0001:
                parts.append("Delay")
            if float(getattr(st, "reverb_mix", 0.0)) > 0.0001:
                parts.append("Reverb")
            if float(getattr(st, "chorus_mix", 0.0)) > 0.0001:
                parts.append("Chorus")
            if str(getattr(st, "filter_type", "off")) != "off":
                parts.append("Filter")
            self.lbl_fx_chain.setText(" + ".join(parts) if parts else "(none)")
        except Exception:
            try:
                self.lbl_fx_chain.setText("(none)")
            except Exception:
                pass

        try:
            if hasattr(self, 'fx_inline') and self.fx_inline is not None:
                self.fx_inline.set_slot(
                    slot,
                    self.track_id or "",
                    getattr(getattr(self, "audio_engine", None), "rt_params", None),
                    automation_manager=getattr(self, 'automation_manager', None),
                )
        except Exception:
            pass

        # v0.0.20.207: Now retarget automation bindings to the selected slot.
        # MUST happen after the external knob refresh.
        try:
            self._bind_editor_knobs_to_selected_slot()
        except Exception:
            pass

    def _load_sample_dialog(self) -> None:
        slot = self._current_slot()
        path, _ = QFileDialog.getOpenFileName(self, "Load sample", "", AUDIO_EXTS)
        if not path:
            return
        target_idx = self._resolve_target_slot_for_sample(slot.state.index, path)
        if target_idx != slot.state.index:
            try:
                self._status(f"Smart-Assign: {Path(path).name} → Slot {target_idx+1} ({self.engine.slots[target_idx].state.name})")
            except Exception:
                pass
        ok = self._import_and_load_sample(int(target_idx), path)
        if ok:
            # If smart-assign moved the sample, follow it so user sees the correct slot editor.
            try:
                self._select_slot(int(target_idx))
            except Exception:
                pass
            self._update_pad_text(int(target_idx))
            # Refresh waveform from engine
            try:
                self.wave.samples = self.engine.slots[int(target_idx)].engine.samples
            except Exception:
                pass
            self.lbl_file.setText(Path(path).name)
            self._persist_instrument_state()
        else:
            self._status("Sample load failed")

    # Qt clicked()/triggered() often forwards a boolean argument.
    # Keep this slot tolerant to extra args (safe; avoids TypeError in signal dispatch).
    def _clear_sample(self, *_args, **_kwargs) -> None:
        slot = self._current_slot()
        slot.clear_sample()
        self._update_pad_text(slot.state.index)
        self._refresh_slot_editor()
        self._persist_instrument_state()

    def _open_fx_rack_dialog(self) -> None:
        try:
            slot = self._current_slot()
            dlg = SlotFxRackDialog(slot.engine, persist_cb=self._persist_instrument_state, parent=self)
            dlg.exec()
            self._refresh_slot_editor()
        except Exception:
            pass





    # ---------------- Sample Tools (triangle menu)
    def _build_sample_tools_menu(self) -> QMenu:
        m = QMenu(self)

        a_trim = m.addAction("Trim Silence…")
        a_trim.triggered.connect(self._sample_trim_dialog)

        a_norm = m.addAction("Normalize (Peak)…")
        a_norm.triggered.connect(self._sample_normalize_dialog)

        a_dc = m.addAction("DC Remove")
        a_dc.triggered.connect(self._sample_dc_remove)

        a_fade = m.addAction("Fade In/Out…")
        a_fade.triggered.connect(self._sample_fade_dialog)

        a_rev = m.addAction("Reverse")
        a_rev.triggered.connect(self._sample_reverse)

        a_pitch = m.addAction("Pitch Envelope… (Bezier)")
        a_pitch.triggered.connect(self._sample_pitch_env_dialog)

        m.addSeparator()

        a_tr = m.addAction("Transient Shaper…")
        a_tr.triggered.connect(self._sample_transient_dialog)

        m.addSeparator()

        a_slice = m.addAction("Slice to Pads…")
        a_slice.triggered.connect(self._sample_slice_dialog)

        return m

    def _require_current_sample(self) -> Optional[str]:
        """Return sample path for current slot or show a friendly warning."""
        try:
            slot = self._current_slot()
            sp = str(slot.state.sample_path or "")
            if sp and Path(sp).exists():
                return sp
        except Exception:
            pass
        QMessageBox.information(self, "No sample", "Dieser Slot hat noch kein Sample geladen.")
        return None

    def _slot_target_sr(self, idx: int) -> int:
        try:
            return int(self.engine.slots[int(idx)].engine.target_sr)
        except Exception:
            return 48000

    def _store_processed_audio(self, idx: int, data, sr: int, suffix: str) -> tuple[str, str]:
        """Write processed audio to a new WAV file and import into project media when possible."""
        idx = int(idx)
        sr = int(sr)
        media_id = ""
        # Prefer project import → keeps everything inside <project>/media and persists via media_id.
        if (self.project_service is not None) and self.track_id:
            tmp = None
            try:
                tmp = st.render_to_temp_wav(data, sr, suffix=f"drum_{idx+1}_{suffix}")
                load_path, media_id = self.project_service.import_audio_to_project(
                    str(self.track_id), Path(tmp), label=f"drum_{idx+1}_{suffix}"
                )
                if load_path and Path(load_path).exists():
                    return str(load_path), str(media_id or "")
            except Exception as exc:
                log.warning("SampleTools: import to project failed (%s). Falling back to local write.", exc)
            finally:
                try:
                    if tmp is not None and Path(tmp).exists():
                        Path(tmp).unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:
                    pass

        # Fallback: write next to original (non-destructive, still visible on disk)
        try:
            orig = Path(self.engine.slots[idx].state.sample_path or Path.cwd() / f"slot{idx+1}.wav")
        except Exception:
            orig = Path.cwd() / f"slot{idx+1}.wav"
        dest = st.unique_path_near(orig, f"{suffix}")
        st.write_wav16(dest, data, sr)
        return str(dest), ""

    def _load_sample_into_slot(self, idx: int, path: str, media_id: str = "") -> None:
        idx = int(idx)
        ok = bool(self.engine.slots[idx].load_sample(str(path)))
        if not ok:
            QMessageBox.warning(self, "Load failed", f"Konnte Sample nicht laden:\n{path}")
            return
        if media_id:
            self._slot_media_ids[idx] = str(media_id)

        self._update_pad_text(idx)
        # If this is the selected slot, refresh editor display (wave + knobs + filename)
        if int(getattr(self, "_selected_slot", idx)) == idx:
            self._refresh_slot_editor()
        self._persist_instrument_state()

    def _apply_op_to_current(self, op_name: str, *, suffix: str, op_func, **kwargs) -> None:
        sp = self._require_current_sample()
        if not sp:
            return
        slot = self._current_slot()
        idx = int(slot.state.index)
        target_sr = self._slot_target_sr(idx)
        try:
            data, sr = st.load_for_engine(sp, target_sr)
            out = op_func(data, sr=sr, **kwargs) if "sr" in op_func.__code__.co_varnames else op_func(data, **kwargs)
            load_path, media_id = self._store_processed_audio(idx, out, sr, suffix=suffix)
            self._load_sample_into_slot(idx, load_path, media_id)
            self._status(f"{op_name}: {Path(load_path).name}")
        except Exception as exc:
            log.exception("SampleTools op failed: %s", exc)
            QMessageBox.warning(self, "Sample Tools", f"Aktion fehlgeschlagen:\n{exc}")

    # ---- individual actions
    def _sample_trim_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return

        d = QDialog(self)
        d.setWindowTitle("Trim Silence")
        form = QFormLayout(d)

        thr = QDoubleSpinBox()
        thr.setRange(-80.0, -6.0)
        thr.setSingleStep(1.0)
        thr.setValue(-45.0)
        thr.setSuffix(" dB")

        pad = QDoubleSpinBox()
        pad.setRange(0.0, 200.0)
        pad.setSingleStep(1.0)
        pad.setValue(5.0)
        pad.setSuffix(" ms")

        form.addRow("Threshold:", thr)
        form.addRow("Padding:", pad)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_op_to_current(
            "Trim Silence",
            suffix="trim",
            op_func=lambda data, sr: st.trim_silence(data, sr, threshold_db=float(thr.value()), pad_ms=float(pad.value())),
        )

    def _sample_normalize_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return

        d = QDialog(self)
        d.setWindowTitle("Normalize (Peak)")
        form = QFormLayout(d)

        target = QDoubleSpinBox()
        target.setRange(-12.0, -0.01)
        target.setSingleStep(0.1)
        target.setValue(-0.2)
        target.setSuffix(" dB")

        form.addRow("Target Peak:", target)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_op_to_current(
            "Normalize",
            suffix="norm",
            op_func=lambda data: st.normalize_peak(data, target_db=float(target.value())),
        )

    def _sample_dc_remove(self) -> None:
        self._apply_op_to_current(
            "DC Remove",
            suffix="dc",
            op_func=lambda data: st.dc_remove(data),
        )

    def _sample_fade_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return

        d = QDialog(self)
        d.setWindowTitle("Fade In/Out")
        form = QFormLayout(d)

        fi = QDoubleSpinBox()
        fi.setRange(0.0, 500.0)
        fi.setSingleStep(1.0)
        fi.setValue(5.0)
        fi.setSuffix(" ms")

        fo = QDoubleSpinBox()
        fo.setRange(0.0, 2000.0)
        fo.setSingleStep(1.0)
        fo.setValue(15.0)
        fo.setSuffix(" ms")

        form.addRow("Fade In:", fi)
        form.addRow("Fade Out:", fo)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_op_to_current(
            "Fade In/Out",
            suffix="fade",
            op_func=lambda data, sr: st.fade_in_out(data, sr, fade_in_ms=float(fi.value()), fade_out_ms=float(fo.value())),
        )

    def _sample_reverse(self) -> None:
        self._apply_op_to_current(
            "Reverse",
            suffix="rev",
            op_func=lambda data: st.reverse_audio(data),
        )

    def _sample_pitch_env_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return

        d = QDialog(self)
        d.setWindowTitle("Pitch Envelope (Bezier) — Safe Offline")
        form = QFormLayout(d)

        s0 = QDoubleSpinBox(); s0.setRange(-24.0, 24.0); s0.setSingleStep(0.5); s0.setValue(0.0); s0.setSuffix(" st")
        s1 = QDoubleSpinBox(); s1.setRange(-24.0, 24.0); s1.setSingleStep(0.5); s1.setValue(0.0); s1.setSuffix(" st")
        y1 = QDoubleSpinBox(); y1.setRange(0.0, 1.0); y1.setSingleStep(0.05); y1.setValue(0.25)
        y2 = QDoubleSpinBox(); y2.setRange(0.0, 1.0); y2.setSingleStep(0.05); y2.setValue(0.75)

        form.addRow("Start Pitch:", s0)
        form.addRow("End Pitch:", s1)
        form.addRow("Bezier Y1 (0..1):", y1)
        form.addRow("Bezier Y2 (0..1):", y2)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_op_to_current(
            "Pitch Envelope",
            suffix="pitchenv",
            op_func=lambda data, sr: st.pitch_envelope_bezier(
                data,
                sr,
                start_semitones=float(s0.value()),
                end_semitones=float(s1.value()),
                y1=float(y1.value()),
                y2=float(y2.value()),
            ),
        )

    def _sample_transient_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return

        d = QDialog(self)
        d.setWindowTitle("Transient Shaper (Safe)")
        form = QFormLayout(d)

        win = QDoubleSpinBox()
        win.setRange(5.0, 100.0)
        win.setSingleStep(1.0)
        win.setValue(20.0)
        win.setSuffix(" ms")

        tg = QDoubleSpinBox()
        tg.setRange(-12.0, 12.0)
        tg.setSingleStep(0.5)
        tg.setValue(6.0)
        tg.setSuffix(" dB")

        sg = QDoubleSpinBox()
        sg.setRange(-12.0, 12.0)
        sg.setSingleStep(0.5)
        sg.setValue(0.0)
        sg.setSuffix(" dB")

        form.addRow("Window:", win)
        form.addRow("Transient Gain:", tg)
        form.addRow("Sustain Gain:", sg)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_op_to_current(
            "Transient Shaper",
            suffix="transient",
            op_func=lambda data, sr: st.transient_shaper(
                data, sr, window_ms=float(win.value()), transient_db=float(tg.value()), sustain_db=float(sg.value())
            ),
        )

    def _sample_slice_dialog(self) -> None:
        sp = self._require_current_sample()
        if not sp:
            return
        slot = self._current_slot()
        src_idx = int(slot.state.index)

        d = QDialog(self)
        d.setWindowTitle("Slice to Pads")
        form = QFormLayout(d)

        mode = QComboBox()
        mode.addItems(["transient", "equal"])

        nsl = QSpinBox()
        nsl.setRange(2, 16)
        nsl.setValue(8)

        start = QSpinBox()
        start.setRange(1, 16)
        # default: next pad, but stay in range
        start.setValue(min(16, src_idx + 1))

        overwrite = QCheckBox("Overwrite existing pads (sonst nur freie Pads)")
        overwrite.setChecked(False)

        form.addRow("Mode:", mode)
        form.addRow("Slices:", nsl)
        form.addRow("Start Pad:", start)
        form.addRow("", overwrite)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)

        if d.exec() != QDialog.DialogCode.Accepted:
            return

        self._slice_to_pads(
            src_idx=src_idx,
            slices=int(nsl.value()),
            start_pad=int(start.value()) - 1,
            mode=str(mode.currentText()),
            overwrite=bool(overwrite.isChecked()),
        )

    def _slice_to_pads(self, *, src_idx: int, slices: int, start_pad: int, mode: str, overwrite: bool) -> None:
        sp = self._require_current_sample()
        if not sp:
            return
        src_idx = int(src_idx)
        slices = int(max(1, min(16, slices)))
        start_pad = int(max(0, min(15, start_pad)))

        # Confirm overwrite (once) if needed
        if overwrite:
            ok = QMessageBox.question(
                self,
                "Overwrite pads?",
                "Slicing kann bestehende Pads überschreiben.\nFortfahren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

        target_sr = self._slot_target_sr(src_idx)
        try:
            data, sr = st.load_for_engine(sp, target_sr)

            if str(mode).lower().startswith("trans"):
                parts = st.slice_transient(data, sr, slices=slices)
                # fallback if not enough parts
                if len(parts) < 2:
                    parts = st.slice_equal(data, slices=slices)
            else:
                parts = st.slice_equal(data, slices=slices)

            # place into pads
            used = 0
            pad = start_pad
            for i, part in enumerate(parts):
                # find next target index
                if overwrite:
                    tgt = pad
                    pad += 1
                else:
                    # find next free pad starting at pad
                    tgt = None
                    for j in range(pad, 16):
                        if not str(self.engine.slots[j].state.sample_path or ""):
                            tgt = j
                            pad = j + 1
                            break
                    if tgt is None:
                        break

                if tgt is None or tgt < 0 or tgt > 15:
                    break

                # store slice as a new sample
                load_path, media_id = self._store_processed_audio(tgt, part, sr, suffix=f"slice_{i+1:02d}")
                self._load_sample_into_slot(tgt, load_path, media_id)
                used += 1

                if pad >= 16:
                    break

            self._status(f"Slice: {used} Pads befüllt ({mode})")
        except Exception as exc:
            log.exception("Slice failed: %s", exc)
            QMessageBox.warning(self, "Slice to Pads", f"Slicing fehlgeschlagen:\n{exc}")

    # ---------------- Automation (v0.0.20.90)
    def _setup_automation(self) -> None:
        """Register per-slot drum parameters + enable right-click automation on editor knobs."""
        try:
            if self._automation_setup_done:
                return
            mgr = getattr(self, 'automation_manager', None)
            tid = str(getattr(self, 'track_id', '') or '')
            if mgr is None or not tid:
                return

            self._automation_setup_done = True
            self._automation_pid_to_engine = {}
            self._slot_param_ids = {}

            def _pid(slot_idx: int, key: str) -> str:
                return f"trk:{tid}:drum:{int(slot_idx)}:{key}"

            # Build ids + engine mapping for all slots
            for i, slot in enumerate(getattr(self.engine, 'slots', []) or []):
                i = int(i)
                self._slot_param_ids[i] = {
                    'gain': _pid(i, 'gain'),
                    'pan': _pid(i, 'pan'),
                    'tune': _pid(i, 'tune'),
                    'cut': _pid(i, 'cut'),
                    'res': _pid(i, 'res'),
                }

                # apply functions (value is in UI-space 0..100)
                self._automation_pid_to_engine[self._slot_param_ids[i]['gain']] = (lambda v, ii=i: self._apply_slot_gain(ii, v))
                self._automation_pid_to_engine[self._slot_param_ids[i]['pan']] = (lambda v, ii=i: self._apply_slot_pan(ii, v))
                self._automation_pid_to_engine[self._slot_param_ids[i]['tune']] = (lambda v, ii=i: self._apply_slot_tune(ii, v))
                self._automation_pid_to_engine[self._slot_param_ids[i]['cut']] = (lambda v, ii=i: self._apply_slot_cut(ii, v))
                self._automation_pid_to_engine[self._slot_param_ids[i]['res']] = (lambda v, ii=i: self._apply_slot_res(ii, v))

                # Register parameters so they appear in the Arranger automation combobox
                try:
                    # defaults derived from current engine state
                    # gain/pan are accessible via ProSamplerEngine.state
                    st = getattr(slot.engine, 'state', None)
                    gain = float(getattr(st, 'master_gain', 1.0)) if st is not None else 1.0
                    pan = float(getattr(st, 'master_pan', 0.0)) if st is not None else 0.0
                    default_gain = max(0.0, min(100.0, gain * 100.0))
                    default_pan = max(0.0, min(100.0, (pan + 1.0) * 50.0))
                except Exception:
                    default_gain, default_pan = 80.0, 50.0

                # Tune defaults: use cached knob value if present
                cache = getattr(self, '_tune_knob_cache', {}) or {}
                default_tune = float(cache.get(i, 50))

                # Cut/Res defaults from engine filter state
                try:
                    st = getattr(slot.engine, 'state', None)
                    cutoff = float(getattr(st, 'cutoff_hz', 8000.0)) if st is not None else 8000.0
                    cut01 = (max(20.0, min(20000.0, cutoff)) - 20.0) / (20000.0 - 20.0)
                    default_cut = cut01 * 100.0
                    q = float(getattr(st, 'q', 0.707)) if st is not None else 0.707
                    q01 = (max(0.25, min(12.0, q)) - 0.25) / (12.0 - 0.25)
                    default_res = q01 * 100.0
                except Exception:
                    default_cut, default_res = 100.0, 20.0

                # Register with readable names
                mgr.register_parameter(self._slot_param_ids[i]['gain'], f"Drum S{i+1} Gain", 0.0, 100.0, float(default_gain), track_id=tid)
                mgr.register_parameter(self._slot_param_ids[i]['pan'], f"Drum S{i+1} Pan", 0.0, 100.0, float(default_pan), track_id=tid)
                mgr.register_parameter(self._slot_param_ids[i]['tune'], f"Drum S{i+1} Tune", 0.0, 100.0, float(default_tune), track_id=tid)
                mgr.register_parameter(self._slot_param_ids[i]['cut'], f"Drum S{i+1} Cutoff", 0.0, 100.0, float(default_cut), track_id=tid)
                mgr.register_parameter(self._slot_param_ids[i]['res'], f"Drum S{i+1} Resonance", 0.0, 100.0, float(default_res), track_id=tid)

            # Disconnect legacy engine wiring from editor knobs (we apply via AutomationManager)
            for k in [getattr(self, 'kn_gain', None), getattr(self, 'kn_pan', None), getattr(self, 'kn_tune', None), getattr(self, 'kn_cut', None), getattr(self, 'kn_res', None)]:
                if k is None:
                    continue
                try:
                    k.valueChanged.disconnect()
                except Exception:
                    pass
                try:
                    k.valueChanged.connect(lambda _v=0: self._persist_instrument_state())
                except Exception:
                    pass

            # v0.0.20.437: Re-wire direct engine connections as FAILSAFE.
            # Same fix as Sampler: automation signal chain may not always deliver,
            # so keep the direct knob→engine path alive.
            try:
                self.kn_gain.valueChanged.connect(lambda v: self._slot_set_gain(v))
                self.kn_pan.valueChanged.connect(lambda v: self._slot_set_pan(v))
                self.kn_tune.valueChanged.connect(lambda v: self._slot_set_tune(v))
                self.kn_cut.valueChanged.connect(lambda v: self._slot_set_cut(v))
                self.kn_res.valueChanged.connect(lambda v: self._slot_set_res(v))
            except Exception:
                pass

            # Bind editor knobs to the currently selected slot ids (right-click targets)
            self._bind_editor_knobs_to_selected_slot()

            if not self._automation_mgr_connected:
                try:
                    mgr.parameter_changed.connect(self._on_automation_parameter_changed)
                    self._automation_mgr_connected = True
                except Exception:
                    self._automation_mgr_connected = False

        except Exception:
            pass

    def _bind_editor_knobs_to_selected_slot(self) -> None:
        """Rebind editor knobs to the selected slot so right-click automation maps correctly.

        v0.0.20.207 FIX (safe):
        - bind_automation() seeds the parameter with the current knob value.
          If called before the UI refresh, this can accidentally copy values
          from the previously selected slot into the new slot (user report:
          "alle Regler reagieren gleich").
        - Therefore we bind ONCE, then only retarget via set_automation_target().
        """
        try:
            mgr = getattr(self, 'automation_manager', None)
            tid = str(getattr(self, 'track_id', '') or '')
            if mgr is None or not tid:
                return
            slot_idx = int(getattr(self, '_selected_slot', 0) or 0)
            ids = (self._slot_param_ids or {}).get(slot_idx)
            if not ids:
                return

            # Defaults from engine state (stable per slot)
            try:
                slot = self.engine.slots[int(slot_idx)]
                st = slot.engine.state
                d_gain = float(getattr(st, 'gain', 0.8)) * 100.0
                d_pan = (float(getattr(st, 'pan', 0.0)) + 1.0) * 50.0
                d_tune = float((getattr(self, "_tune_knob_cache", {}) or {}).get(int(slot_idx), 50))
                cutoff = float(getattr(st, 'cutoff_hz', 8000.0))
                cut01 = (max(20.0, min(20000.0, cutoff)) - 20.0) / (20000.0 - 20.0)
                d_cut = float(cut01 * 100.0)
                q = float(getattr(st, 'q', 0.707))
                q01 = (max(0.25, min(12.0, q)) - 0.25) / (12.0 - 0.25)
                d_res = float(q01 * 100.0)
            except Exception:
                d_gain, d_pan, d_tune, d_cut, d_res = 80.0, 50.0, 50.0, 100.0, 20.0

            if not bool(getattr(self, '_editor_knobs_automation_bound', False)):
                # First bind installs context menu + connects to AutomationManager.
                try:
                    self.kn_gain.bind_automation(mgr, ids['gain'], name=f"Drum S{slot_idx+1} Gain", track_id=tid, default=float(d_gain))
                    self.kn_pan.bind_automation(mgr, ids['pan'], name=f"Drum S{slot_idx+1} Pan", track_id=tid, default=float(d_pan))
                    self.kn_tune.bind_automation(mgr, ids['tune'], name=f"Drum S{slot_idx+1} Tune", track_id=tid, default=float(d_tune))
                    self.kn_cut.bind_automation(mgr, ids['cut'], name=f"Drum S{slot_idx+1} Cutoff", track_id=tid, default=float(d_cut))
                    self.kn_res.bind_automation(mgr, ids['res'], name=f"Drum S{slot_idx+1} Resonance", track_id=tid, default=float(d_res))
                    self._editor_knobs_automation_bound = True
                except Exception:
                    pass
            else:
                # Retarget only (no seeding).
                try:
                    self.kn_gain.set_automation_target(ids['gain'], default=float(d_gain))
                    self.kn_pan.set_automation_target(ids['pan'], default=float(d_pan))
                    self.kn_tune.set_automation_target(ids['tune'], default=float(d_tune))
                    self.kn_cut.set_automation_target(ids['cut'], default=float(d_cut))
                    self.kn_res.set_automation_target(ids['res'], default=float(d_res))
                except Exception:
                    pass
        except Exception:
            pass

    # Engine apply helpers (no persistence; used by automation playback)
    def _apply_slot_gain(self, slot_idx: int, v: float) -> None:
        try:
            slot = self.engine.slots[int(slot_idx)]
            slot.engine.set_master(gain=float(v) / 100.0)
        except Exception:
            pass

    def _apply_slot_pan(self, slot_idx: int, v: float) -> None:
        try:
            slot = self.engine.slots[int(slot_idx)]
            pan = (float(v) / 50.0) - 1.0
            slot.engine.set_master(pan=pan)
        except Exception:
            pass

    def _apply_slot_tune(self, slot_idx: int, v: float) -> None:
        try:
            i = int(slot_idx)
            slot = self.engine.slots[i]
            semis = int(round(((int(v) - 50) / 50.0) * 24.0))
            base_pitch = int(self.engine.base_note) + i
            slot.engine.set_root(int(base_pitch - semis))
            cache = getattr(self, '_tune_knob_cache', None)
            if cache is None:
                cache = {}
                setattr(self, '_tune_knob_cache', cache)
            cache[i] = int(round(v))
        except Exception:
            pass

    def _apply_slot_cut(self, slot_idx: int, v: float) -> None:
        try:
            slot = self.engine.slots[int(slot_idx)]
            cut = 20.0 + (float(v) / 100.0) * (20000.0 - 20.0)
            slot.engine.set_filter(cutoff_hz=cut)
        except Exception:
            pass

    def _apply_slot_res(self, slot_idx: int, v: float) -> None:
        try:
            slot = self.engine.slots[int(slot_idx)]
            q = 0.25 + (float(v) / 100.0) * (12.0 - 0.25)
            slot.engine.set_filter(q=q)
        except Exception:
            pass

    def _on_automation_parameter_changed(self, parameter_id: str, value: float) -> None:
        try:
            pid = str(parameter_id)
            fn = (self._automation_pid_to_engine or {}).get(pid)
            if fn is None:
                return
            val = float(value)
            fn(val)

            # Keep the visible editor knobs in sync for the currently selected slot.
            try:
                slot_idx = int(getattr(self, '_selected_slot', 0) or 0)
                ids = (self._slot_param_ids or {}).get(slot_idx) or {}
                if pid == str(ids.get('gain', '')) and getattr(self, 'kn_gain', None) is not None:
                    self.kn_gain.setValueExternal(int(round(val)))
                elif pid == str(ids.get('pan', '')) and getattr(self, 'kn_pan', None) is not None:
                    self.kn_pan.setValueExternal(int(round(val)))
                elif pid == str(ids.get('tune', '')) and getattr(self, 'kn_tune', None) is not None:
                    self.kn_tune.setValueExternal(int(round(val)))
                elif pid == str(ids.get('cut', '')) and getattr(self, 'kn_cut', None) is not None:
                    self.kn_cut.setValueExternal(int(round(val)))
                elif pid == str(ids.get('res', '')) and getattr(self, 'kn_res', None) is not None:
                    self.kn_res.setValueExternal(int(round(val)))
            except Exception:
                pass
        except Exception:
            pass
    # ---------------- Param setters (selected slot)
    def _slot_set_gain(self, v: int) -> None:
        slot = self._current_slot()
        try:
            slot.engine.set_master(gain=float(v) / 100.0)
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_pan(self, v: int) -> None:
        slot = self._current_slot()
        try:
            pan = (float(v) / 50.0) - 1.0
            slot.engine.set_master(pan=pan)
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_tune(self, v: int) -> None:
        # Store as semitone offset in [-24..+24]
        slot = self._current_slot()
        semis = int(round(((int(v) - 50) / 50.0) * 24.0))
        # IMPORTANT: DrumMachineEngine triggers notes using a stable per-pad root
        # and shifts the trigger pitch by tune_semitones.
        try:
            slot.state.tune_semitones = int(semis)
        except Exception:
            pass
        # Cache for refresh
        cache = getattr(self, "_tune_knob_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_tune_knob_cache", cache)
        cache[slot.state.index] = int(v)
        self._persist_instrument_state()

    def _slot_set_filter(self, ftype: str) -> None:
        slot = self._current_slot()
        try:
            slot.engine.set_filter(ftype=str(ftype))
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_cut(self, v: int) -> None:
        slot = self._current_slot()
        try:
            cut = 20.0 + (float(v) / 100.0) * (20000.0 - 20.0)
            slot.engine.set_filter(cutoff_hz=cut)
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_res(self, v: int) -> None:
        slot = self._current_slot()
        try:
            q = 0.25 + (float(v) / 100.0) * (12.0 - 0.25)
            slot.engine.set_filter(q=q)
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_choke_group(self, v: int) -> None:
        """v0.0.20.656: Set choke group for current slot (0=off, 1-8=mutual exclusion)."""
        slot = self._current_slot()
        try:
            slot.state.choke_group = int(max(0, min(8, v)))
        except Exception:
            pass
        self._persist_instrument_state()

    def _slot_set_start(self, v: int) -> None:
        slot = self._current_slot()
        try:
            slot.engine.set_region_norm(start=float(v) / 100.0, end=None)
        except Exception:
            try:
                slot.engine.state.start_position = float(v) / 100.0
            except Exception:
                pass
        self._persist_instrument_state()

    def _slot_set_end(self, v: int) -> None:
        slot = self._current_slot()
        try:
            slot.engine.set_region_norm(start=None, end=float(v) / 100.0)
        except Exception:
            try:
                slot.engine.state.end_position = float(v) / 100.0
            except Exception:
                pass
        self._persist_instrument_state()

    # ---------------- AI Pattern (placeholder)        self._persist_instrument_state()

    def _randomize_style(self) -> None:
        try:
            # Pick two genres + random mix
            a = random.randint(0, self.cmb_genre_a.count() - 1)
            b = random.randint(0, self.cmb_genre_b.count() - 1)
            self.cmb_genre_a.setCurrentIndex(a)
            self.cmb_genre_b.setCurrentIndex(b)
            self.sld_hybrid.setValue(random.randint(0, 100))
            self.cmb_context.setCurrentIndex(random.randint(0, max(0, self.cmb_context.count() - 1)))
            self.cmb_grid.setCurrentText(random.choice(["1/16", "1/16", "1/32", "1/8"]))
            self.sld_swing.setValue(random.choice([0, 0, 10, 20, 35, 55]))
            self.sld_density.setValue(random.randint(35, 95))
            self.sld_intensity.setValue(random.randint(25, 95))
            self.spn_bars.setValue(random.choice([1, 1, 2, 4, 8]))
        except Exception:
            pass

    def _generate_to_clip(self) -> None:
        if self.project_service is None:
            self._status("ProjectService fehlt – Pattern nicht möglich.")
            return
        try:
            clip_id = str(self.project_service.active_clip_id() or "")
        except Exception:
            clip_id = ""
        if not clip_id:
            self._status("Kein aktiver MIDI-Clip (Tip: Clip auswählen oder im Launcher doppelklicken).")
            return

        clip = None
        try:
            clip = self.project_service.get_clip(clip_id)
        except Exception:
            clip = None
        if clip is None or str(getattr(clip, "kind", "")) != "midi":
            self._status("Aktiver Clip ist kein MIDI-Clip.")
            return

        bars = int(self.spn_bars.value())
        genre_a = str(getattr(self, 'cmb_genre_a', None).currentText() if hasattr(self, 'cmb_genre_a') else "Electro")
        genre_b = str(getattr(self, 'cmb_genre_b', None).currentText() if hasattr(self, 'cmb_genre_b') else "Hardcore")
        hybrid = float(getattr(self, 'sld_hybrid', None).value() if hasattr(self, 'sld_hybrid') else 35) / 100.0
        context = str(getattr(self, 'cmb_context', None).currentText() if hasattr(self, 'cmb_context') else "Neutral")
        grid = str(getattr(self, 'cmb_grid', None).currentText() if hasattr(self, 'cmb_grid') else "1/16")
        swing = float(getattr(self, 'sld_swing', None).value() if hasattr(self, 'sld_swing') else 0) / 100.0
        density = float(getattr(self, 'sld_density', None).value() if hasattr(self, 'sld_density') else 65) / 100.0
        intensity = float(self.sld_intensity.value()) / 100.0

        notes = self._make_pattern(
            genre_a=genre_a,
            genre_b=genre_b,
            hybrid=hybrid,
            context=context,
            grid=grid,
            swing=swing,
            density=density,
            intensity=intensity,
            bars=bars,
        )
        try:
            before = self.project_service.snapshot_midi_notes(clip_id)
        except Exception:
            before = []

        try:
            self.project_service.set_midi_notes(clip_id, notes)
            self.project_service.commit_midi_notes_edit(clip_id, before, f"Drum Pattern: {genre_a}×{genre_b}")
            self._status(f"Pattern geschrieben: {genre_a}×{genre_b} ({bars} bar)")
        except Exception as e:
            self._status(f"Pattern schreiben fehlgeschlagen: {e}")

    def _make_pattern(
        self,
        *,
        genre_a: str,
        genre_b: str,
        hybrid: float,
        context: str,
        grid: str,
        swing: float,
        density: float,
        intensity: float,
        bars: int = 1,
    ):
        """Return list[MidiNote] for a genre-hybrid drum pattern.

        Important: We keep the canonical pitch mapping (C2=Kick, C#2=Snare, ...) so
        PianoRoll/Notation stay consistent. The 'Smart-Assign' feature ensures samples
        are loaded into the correct slots.
        """
        try:
            from pydaw.music.ai_drummer import DrumParams, generate_drum_notes
            params = DrumParams(
                genre_a=str(genre_a or "Electro"),
                genre_b=str(genre_b or "Hardcore"),
                hybrid=float(hybrid),
                context=str(context or "Neutral"),
                bars=int(bars),
                grid=str(grid or "1/16"),
                swing=float(swing),
                density=float(density),
                intensity=float(intensity),
                seed=str(getattr(self, '_gen_seed_mode', 'Random') or 'Random'),
            )
            return generate_drum_notes(params=params, base_note=int(self.engine.base_note), time_signature="4/4")
        except Exception:
            # Fallback: empty pattern
            return []

    # ---------------- helpers

    def _refresh_pad_labels(self) -> None:
        """Refresh all pad texts (safe helper used by restore)."""
        try:
            for i in range(len(self.engine.slots)):
                self._update_pad_text(i)
        except Exception:
            pass

    def _on_smart_assign_toggled(self, checked: bool) -> None:
        self._smart_assign_enabled = bool(checked)

    def _on_generator_ui_changed(self) -> None:
        # Avoid re-entrancy during restore.
        try:
            if bool(getattr(self, '_restoring_state', False)):
                return
        except Exception:
            return
        # Best-effort persist (lightweight)
        try:
            self._persist_instrument_state()
        except Exception:
            pass

    def _export_generator_state(self) -> dict:
        """Persist the generator UI values into the project (track.instrument_state).

        Backward compatible: older projects simply won't have this key.
        """
        try:
            return {
                "genre_a": str(getattr(self, 'cmb_genre_a', None).currentText()) if hasattr(self, 'cmb_genre_a') else "",
                "genre_b": str(getattr(self, 'cmb_genre_b', None).currentText()) if hasattr(self, 'cmb_genre_b') else "",
                "hybrid": float(getattr(self, 'sld_hybrid', None).value() if hasattr(self, 'sld_hybrid') else 35) / 100.0,
                "context": str(getattr(self, 'cmb_context', None).currentText()) if hasattr(self, 'cmb_context') else "Neutral",
                "grid": str(getattr(self, 'cmb_grid', None).currentText()) if hasattr(self, 'cmb_grid') else "1/16",
                "swing": float(getattr(self, 'sld_swing', None).value() if hasattr(self, 'sld_swing') else 0) / 100.0,
                "density": float(getattr(self, 'sld_density', None).value() if hasattr(self, 'sld_density') else 65) / 100.0,
                "intensity": float(getattr(self, 'sld_intensity', None).value() if hasattr(self, 'sld_intensity') else 55) / 100.0,
                "bars": int(getattr(self, 'spn_bars', None).value() if hasattr(self, 'spn_bars') else 1),
                "smart_assign": bool(getattr(self, 'chk_smart_assign', None).isChecked() if hasattr(self, 'chk_smart_assign') else True),
                "seed": str(getattr(self, '_gen_seed_mode', 'Random') or 'Random'),
            }
        except Exception:
            return {"seed": "Random"}

    def _import_generator_state(self, gen: dict) -> None:
        """Apply persisted generator values back to UI without triggering loops."""
        if not isinstance(gen, dict):
            return
        # Avoid persistence during restore
        try:
            blockers = []
            for w in [
                getattr(self, 'cmb_genre_a', None),
                getattr(self, 'cmb_genre_b', None),
                getattr(self, 'sld_hybrid', None),
                getattr(self, 'cmb_context', None),
                getattr(self, 'cmb_grid', None),
                getattr(self, 'sld_swing', None),
                getattr(self, 'sld_density', None),
                getattr(self, 'sld_intensity', None),
                getattr(self, 'spn_bars', None),
                getattr(self, 'chk_smart_assign', None),
            ]:
                if w is not None:
                    try:
                        blockers.append(QSignalBlocker(w))
                    except Exception:
                        pass

            if hasattr(self, 'cmb_genre_a') and gen.get('genre_a'):
                self.cmb_genre_a.setCurrentText(str(gen.get('genre_a')))
            if hasattr(self, 'cmb_genre_b') and gen.get('genre_b'):
                self.cmb_genre_b.setCurrentText(str(gen.get('genre_b')))
            if hasattr(self, 'sld_hybrid'):
                self.sld_hybrid.setValue(int(float(gen.get('hybrid', 0.35)) * 100.0))
            if hasattr(self, 'cmb_context') and gen.get('context'):
                self.cmb_context.setCurrentText(str(gen.get('context')))
            if hasattr(self, 'cmb_grid') and gen.get('grid'):
                self.cmb_grid.setCurrentText(str(gen.get('grid')))
            if hasattr(self, 'sld_swing'):
                self.sld_swing.setValue(int(float(gen.get('swing', 0.0)) * 100.0))
            if hasattr(self, 'sld_density'):
                self.sld_density.setValue(int(float(gen.get('density', 0.65)) * 100.0))
            if hasattr(self, 'sld_intensity'):
                self.sld_intensity.setValue(int(float(gen.get('intensity', 0.55)) * 100.0))
            if hasattr(self, 'spn_bars'):
                self.spn_bars.setValue(int(gen.get('bars', 1)))
            if hasattr(self, 'chk_smart_assign'):
                self.chk_smart_assign.setChecked(bool(gen.get('smart_assign', True)))
                self._smart_assign_enabled = bool(gen.get('smart_assign', True))
            self._gen_seed_mode = str(gen.get('seed', 'Random') or 'Random')
        except Exception:
            pass

    def _resolve_target_slot_for_sample(self, requested_idx: int, path: str) -> int:
        """Return the slot index to load this sample into.

        Canonical mapping is fixed (Kick=Slot1/C2, Snare=Slot2/C#2, ...). To prevent
        the classic "HiHat plays Kick" issue, we optionally smart-route the sample
        into the most likely slot *based on filename keywords*.
        """
        try:
            if not bool(getattr(self, '_smart_assign_enabled', True)):
                return int(requested_idx)
            # During restore we must never reshuffle.
            if bool(getattr(self, '_restoring_state', False)):
                return int(requested_idx)

            fn = Path(str(path)).name.lower()
            # Quick accept: if user drops on the canonical slot by name, don't move.
            try:
                slot_name = str(self.engine.slots[int(requested_idx)].state.name).lower()
            except Exception:
                slot_name = ""

            # Role keywords → canonical slot index
            roles = {
                0: ["kick", "bd", "bassdrum"],
                1: ["snare", "sd"],
                2: ["chat", "closed hat", "closedhat", "hhc", "chh", "hihat_closed", "closed"],
                3: ["ohat", "open hat", "openhat", "hho", "ohh", "hihat_open", "open"],
                4: ["clap"],
                5: ["tom"],
                6: ["perc", "percussion", "shaker", "conga", "bongo", "cowbell"],
                7: ["rim", "rimshot", "stick"],
                10: ["ride"],
                11: ["crash"],
                8: ["fx1", "fx"],
                9: ["fx2"],
            }

            best_idx = int(requested_idx)
            best_score = 0

            def _score(idx: int, keys: list[str]) -> int:
                s = 0
                for k in keys:
                    kk = str(k).strip().lower()
                    if not kk:
                        continue
                    if kk in fn:
                        s += 3
                    if kk in slot_name:
                        s += 2
                return s

            for idx, keys in roles.items():
                sc = _score(int(idx), list(keys))
                if sc > best_score:
                    best_score = sc
                    best_idx = int(idx)

            # Only re-route on clear matches; otherwise respect the user's choice.
            if best_score >= 3 and 0 <= best_idx < len(self.engine.slots):
                return int(best_idx)
            return int(requested_idx)
        except Exception:
            return int(requested_idx)

    def _status(self, msg: str) -> None:
        # Best-effort: route to ProjectService.status (shows in statusbar)
        try:
            if self.project_service is not None and hasattr(self.project_service, "status"):
                self.project_service.status.emit(str(msg))
                return
        except Exception:
            pass

