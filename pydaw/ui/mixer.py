"""Mixer Panel — Pro-DAW-Style vertical fader strips (v0.0.20.14).

Features:
- Vertical fader strips (90px wide) with VU meters
- Mute / Solo buttons per track
- Pan knob (horizontal slider)
- Volume fader (vertical, 0-127 → 0.0-1.0, logarithmic dB display)
- Automation mode selector
- All parameters routed through RTParamStore + HybridRingBuffer for click-free real-time audio
- Per-track params via lock-free ParamRingBuffer (v0.0.20.14)
- Track rename via double-click
- Add/Remove track buttons
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSlider, QComboBox, QPushButton, QSizePolicy, QMenu, QInputDialog,
    QDial, QDialog, QGridLayout, QCheckBox, QDialogButtonBox,
)

from pydaw.services.project_service import ProjectService

# v0.0.20.21: Professional VU Meter
try:
    from pydaw.ui.widgets.vu_meter import VUMeterWidget
    VU_METER_AVAILABLE = True
except ImportError:
    VU_METER_AVAILABLE = False


# ---- VU Meter Widget (Legacy - kept for backward compatibility)

class _VUMeter(QWidget):
    """Stereo VU meter — 8px wide, gradient fill, peak hold."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(10)
        self.setMinimumHeight(60)
        self._peak_l = 0.0
        self._peak_r = 0.0
        self._hold_l = 0.0
        self._hold_r = 0.0

    def set_levels(self, left: float, right: float) -> None:
        self._peak_l = max(0.0, min(1.0, left))
        self._peak_r = max(0.0, min(1.0, right))
        self._hold_l = max(self._hold_l * 0.92, self._peak_l)
        self._hold_r = max(self._hold_r * 0.92, self._peak_r)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w = self.width()
        h = self.height()
        half = w // 2

        # Background
        p.fillRect(0, 0, w, h, QColor(30, 30, 30))

        for i, (peak, hold) in enumerate(
            [(self._peak_l, self._hold_l), (self._peak_r, self._hold_r)]
        ):
            x = 0 if i == 0 else half
            bar_h = int(peak * h)
            if bar_h > 0:
                grad = QLinearGradient(0, h, 0, 0)
                grad.setColorAt(0.0, QColor(0, 200, 80))
                grad.setColorAt(0.65, QColor(220, 220, 0))
                grad.setColorAt(1.0, QColor(255, 40, 40))
                p.fillRect(x, h - bar_h, half, bar_h, grad)

            # Peak hold line
            hold_y = h - int(hold * h)
            p.setPen(QPen(QColor(255, 255, 255, 180), 1))
            p.drawLine(x, hold_y, x + half - 1, hold_y)

        p.end()


# ---- v0.0.20.640: Routing Overlay (AP5 Phase 5A — visual send routing lines)

class _RoutingOverlay(QWidget):
    """Transparent overlay that draws bezier routing lines between mixer strips.

    Shows which tracks send to which FX/Return tracks. Lines are color-coded
    per FX track and drawn as smooth curves with opacity proportional to send amount.
    v0.0.20.641: Also draws sidechain routing lines (orange dashed).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._routes: list = []  # list of (src_x, src_y, dst_x, dst_y, amount, color_idx)
        self._sc_routes: list = []  # v0.0.20.641: sidechain routes (src_x, src_y, dst_x, dst_y)

    def set_routes(self, routes: list, sc_routes: list | None = None) -> None:
        """Set routing data and repaint.

        Args:
            routes: list of (src_center_x, src_bottom_y, dst_center_x, dst_top_y, amount, fx_index)
            sc_routes: list of (src_center_x, src_y, dst_center_x, dst_y) — sidechain connections
        """
        self._routes = list(routes)
        self._sc_routes = list(sc_routes) if sc_routes else []
        self.update()

    def paintEvent(self, event) -> None:
        if not self._routes and not self._sc_routes:
            return
        try:
            from PyQt6.QtGui import QPainterPath
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            colors = [
                QColor(80, 200, 120),   # green
                QColor(80, 150, 220),   # blue
                QColor(220, 170, 60),   # gold
                QColor(180, 100, 200),  # purple
                QColor(220, 120, 80),   # orange
                QColor(100, 200, 200),  # cyan
                QColor(200, 80, 120),   # pink
                QColor(160, 180, 80),   # lime
            ]

            # Draw send routes (solid lines)
            for route in self._routes:
                try:
                    sx, sy, dx, dy, amount, ci = route
                    col = QColor(colors[int(ci) % len(colors)])
                    alpha = max(40, min(200, int(float(amount) * 200)))
                    col.setAlpha(alpha)

                    pen = QPen(col)
                    pen.setWidth(max(1, min(3, int(float(amount) * 3))))
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    p.setPen(pen)

                    # Bezier curve from source bottom to dest top
                    path = QPainterPath()
                    path.moveTo(float(sx), float(sy))
                    mid_y = (float(sy) + float(dy)) / 2.0
                    path.cubicTo(float(sx), mid_y, float(dx), mid_y, float(dx), float(dy))
                    p.drawPath(path)

                    # Small circle at destination
                    p.setBrush(col)
                    p.drawEllipse(int(dx) - 3, int(dy) - 3, 6, 6)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                except Exception:
                    continue

            # v0.0.20.641: Draw sidechain routes (orange dashed lines)
            for sc_route in self._sc_routes:
                try:
                    sx, sy, dx, dy = sc_route
                    col = QColor(255, 153, 0, 160)  # orange
                    pen = QPen(col)
                    pen.setWidth(2)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen)

                    path = QPainterPath()
                    path.moveTo(float(sx), float(sy))
                    mid_y = (float(sy) + float(dy)) / 2.0
                    path.cubicTo(float(sx), mid_y, float(dx), mid_y, float(dx), float(dy))
                    p.drawPath(path)

                    # Diamond marker at destination
                    p.setBrush(col)
                    cx, cy = int(dx), int(dy)
                    diamond = QPainterPath()
                    diamond.moveTo(cx, cy - 4)
                    diamond.lineTo(cx + 4, cy)
                    diamond.lineTo(cx, cy + 4)
                    diamond.lineTo(cx - 4, cy)
                    diamond.closeSubpath()
                    p.drawPath(diamond)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                except Exception:
                    continue

            p.end()
        except Exception:
            pass


# ---- Mixer Strip

class _MixerStrip(QFrame):
    """Single vertical mixer strip (90px wide)."""

    def __init__(self, project: ProjectService, track_id: str,
                 audio_engine=None, rt_params=None, hybrid_bridge=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.track_id = track_id
        self.audio_engine = audio_engine
        self.rt_params = rt_params
        self.hybrid_bridge = hybrid_bridge  # v0.0.20.14: lock-free per-track ring

        # v0.0.20.28: Fallback to AudioEngine's HybridEngineBridge when not passed in.
        if self.hybrid_bridge is None and self.audio_engine is not None:
            try:
                hb = getattr(self.audio_engine, "_hybrid_bridge", None)
                if hb is None:
                    hb = getattr(self.audio_engine, "hybrid_bridge", None)
                if hb is not None:
                    self.hybrid_bridge = hb
            except Exception:
                pass

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(92)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        # Track name (click to rename)
        self.lbl_name = QLabel("")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setMaximumHeight(32)
        self.lbl_name.setStyleSheet(
            "QLabel { font-size: 10px; padding: 2px; }"
            "QLabel:hover { background: #444; border-radius: 3px; }"
        )
        self.lbl_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_name.mouseDoubleClickEvent = lambda ev: self._rename_track()
        lay.addWidget(self.lbl_name)

        # v0.0.20.704: Sandbox crash indicator badge (P6A — Mixer)
        self._crash_badge = None
        try:
            from pydaw.ui.crash_indicator_widget import (
                CrashIndicatorBadge, CrashState,
            )
            self._crash_badge = CrashIndicatorBadge(
                track_id=track_id, slot_id="fx_chain", parent=self)
            self._crash_badge.setFixedHeight(16)
            lay.addWidget(self._crash_badge)
        except Exception:
            pass
        self._sandbox_crashed = False

        # Automation mode
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["off", "read", "write"])
        self.cmb_mode.setFixedHeight(22)
        self.cmb_mode.setStyleSheet("font-size: 9px;")
        self.cmb_mode.currentTextChanged.connect(self._on_mode)
        lay.addWidget(self.cmb_mode)

        # v0.0.20.636: Input Routing ComboBox (AP2 Phase 2B)
        self.cmb_input = QComboBox()
        self.cmb_input.setFixedHeight(20)
        self.cmb_input.setStyleSheet("font-size: 8px; padding: 0 2px;")
        self.cmb_input.setToolTip("Input: Stereo pair for recording")
        self._populate_input_routing()
        self.cmb_input.currentIndexChanged.connect(self._on_input_pair_changed)
        lay.addWidget(self.cmb_input)

        # v0.0.20.641: Channel Config (Mono/Stereo) (AP5 Phase 5C)
        self._ch_row = QHBoxLayout()
        self._ch_row.setContentsMargins(0, 0, 0, 0)
        self._ch_row.setSpacing(1)
        self._ch_lbl = QLabel("Ch")
        self._ch_lbl.setStyleSheet("font-size: 7px; color: #888;")
        self._ch_lbl.setFixedWidth(14)
        self._ch_row.addWidget(self._ch_lbl)
        self.cmb_channel = QComboBox()
        self.cmb_channel.setFixedHeight(18)
        self.cmb_channel.setStyleSheet("font-size: 7px; padding: 0 1px;")
        self.cmb_channel.addItem("St", "stereo")
        self.cmb_channel.addItem("Mo", "mono")
        self.cmb_channel.setToolTip("Channel: Stereo / Mono")
        self.cmb_channel.currentIndexChanged.connect(self._on_channel_config_changed)
        self._ch_row.addWidget(self.cmb_channel, 1)
        # Output target
        self.cmb_output = QComboBox()
        self.cmb_output.setFixedHeight(18)
        self.cmb_output.setStyleSheet("font-size: 7px; padding: 0 1px;")
        self.cmb_output.setToolTip("Output: Where audio goes (Master or Group/Bus)")
        self.cmb_output.currentIndexChanged.connect(self._on_output_target_changed)
        self._ch_row.addWidget(self.cmb_output, 1)
        self._ch_widget = QWidget()
        self._ch_widget.setLayout(self._ch_row)
        self._ch_widget.setFixedHeight(20)
        lay.addWidget(self._ch_widget)

        # Pan slider (horizontal)
        self.sld_pan = QSlider(Qt.Orientation.Horizontal)
        self.sld_pan.setRange(-100, 100)
        self.sld_pan.setValue(0)
        self.sld_pan.setFixedHeight(18)
        self.sld_pan.setToolTip("Pan: L ← → R")
        self.sld_pan.valueChanged.connect(self._on_pan)
        lay.addWidget(self.sld_pan)

        # v0.0.20.521: Send knobs with thin scrollbar + numbered FX labels
        self._send_knobs: dict[str, QDial] = {}  # fx_track_id -> QDial
        self._send_labels: dict[str, QLabel] = {}
        self._send_inner = QWidget()
        self._send_layout = QVBoxLayout(self._send_inner)
        self._send_layout.setContentsMargins(0, 0, 0, 0)
        self._send_layout.setSpacing(0)
        self._send_scroll = QScrollArea()
        self._send_scroll.setWidget(self._send_inner)
        self._send_scroll.setWidgetResizable(True)
        self._send_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._send_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._send_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._send_scroll.setFixedHeight(80)
        self._send_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #666; border-radius: 3px; min-height: 16px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        lay.addWidget(self._send_scroll)

        # v0.0.20.641: Sidechain source selector (AP5 Phase 5B)
        self._sc_row = QHBoxLayout()
        self._sc_row.setContentsMargins(0, 0, 0, 0)
        self._sc_row.setSpacing(2)
        self._sc_lbl = QLabel("SC")
        self._sc_lbl.setStyleSheet("font-size: 8px; color: #f90; font-weight: bold;")
        self._sc_lbl.setFixedWidth(16)
        self._sc_lbl.setToolTip("Sidechain Source")
        self._sc_row.addWidget(self._sc_lbl)
        self.cmb_sidechain = QComboBox()
        self.cmb_sidechain.setFixedHeight(18)
        self.cmb_sidechain.setStyleSheet("font-size: 8px; padding: 0 2px;")
        self.cmb_sidechain.setToolTip("Sidechain: Which track feeds the key signal for compressor/gate")
        self.cmb_sidechain.currentIndexChanged.connect(self._on_sidechain_changed)
        self._sc_row.addWidget(self.cmb_sidechain, 1)
        self._sc_widget = QWidget()
        self._sc_widget.setLayout(self._sc_row)
        self._sc_widget.setFixedHeight(22)
        lay.addWidget(self._sc_widget)

        # Fader + VU area
        fader_row = QHBoxLayout()
        fader_row.setSpacing(2)

        self.sld_vol = QSlider(Qt.Orientation.Vertical)
        self.sld_vol.setRange(0, 127)
        self.sld_vol.setValue(100)
        self.sld_vol.setMinimumHeight(80)
        self.sld_vol.setToolTip("Volume fader")
        self.sld_vol.valueChanged.connect(self._on_vol)
        fader_row.addWidget(self.sld_vol, 1)

        # VU Meter (v0.0.20.21: New professional widget if available)
        if VU_METER_AVAILABLE:
            self.vu = VUMeterWidget()
        else:
            self.vu = _VUMeter()
        fader_row.addWidget(self.vu, 0)

        lay.addLayout(fader_row, 1)

        # dB label
        self.lbl_db = QLabel("0.0 dB")
        self.lbl_db.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_db.setStyleSheet("font-size: 9px; color: #aaa;")
        lay.addWidget(self.lbl_db)

        # Mute / Solo buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)

        self.btn_mute = QPushButton("M")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(34, 22)
        self.btn_mute.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: bold; }"
            "QPushButton:checked { background: #c44; color: white; }"
        )
        self.btn_mute.toggled.connect(self._on_mute)
        btn_row.addWidget(self.btn_mute)

        self.btn_solo = QPushButton("S")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setFixedSize(34, 22)
        self.btn_solo.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: bold; }"
            "QPushButton:checked { background: #cc4; color: black; }"
        )
        self.btn_solo.toggled.connect(self._on_solo)
        btn_row.addWidget(self.btn_solo)

        # v0.0.20.632: Record-Arm button (AP2 Phase 2A)
        self.btn_rec_arm = QPushButton("R")
        self.btn_rec_arm.setCheckable(True)
        self.btn_rec_arm.setFixedSize(34, 22)
        self.btn_rec_arm.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: bold; }"
            "QPushButton:checked { background: #e33; color: white; border: 1px solid #f66; }"
        )
        self.btn_rec_arm.setToolTip("Record Arm (R)")
        self.btn_rec_arm.toggled.connect(self._on_rec_arm)
        btn_row.addWidget(self.btn_rec_arm)

        lay.addLayout(btn_row)

        self.refresh_from_model()
        
        # v0.0.20.584: VU meter updates are now driven by a SINGLE timer
        # in MixerPanel (instead of N individual timers per strip).
        # This reduces timer callback overhead from N*30fps to 1*30fps.
        self._track_idx = None  # Will be set by MixerPanel

    # ---- Model sync

    def _track(self):
        return next(
            (t for t in self.project.ctx.project.tracks
             if t.id == self.track_id), None)

    def refresh_from_model(self) -> None:
        t = self._track()
        if not t:
            return

        self.lbl_name.setText(f"{t.name}")
        self.lbl_name.setToolTip(f"{t.name} [{t.kind}]")

        self.cmb_mode.blockSignals(True)
        self.cmb_mode.setCurrentText(getattr(t, "automation_mode", "off"))
        self.cmb_mode.blockSignals(False)

        # Volume: 0.0-1.0 → 0-127
        vol = float(getattr(t, "volume", 0.8))
        self.sld_vol.blockSignals(True)
        self.sld_vol.setValue(int(round(vol * 127.0)))
        self.sld_vol.blockSignals(False)

        # Pan: -1.0..+1.0 → -100..+100
        pan = float(getattr(t, "pan", 0.0))
        self.sld_pan.blockSignals(True)
        self.sld_pan.setValue(int(round(pan * 100.0)))
        self.sld_pan.blockSignals(False)

        # Mute / Solo
        self.btn_mute.blockSignals(True)
        self.btn_mute.setChecked(bool(getattr(t, "muted", False)))
        self.btn_mute.blockSignals(False)

        self.btn_solo.blockSignals(True)
        self.btn_solo.setChecked(bool(getattr(t, "solo", False)))
        self.btn_solo.blockSignals(False)

        # v0.0.20.632: Record-Arm sync
        self.btn_rec_arm.blockSignals(True)
        self.btn_rec_arm.setChecked(bool(getattr(t, "record_arm", False)))
        self.btn_rec_arm.blockSignals(False)

        # v0.0.20.636: Input pair sync (AP2 Phase 2B)
        input_pair = max(1, int(getattr(t, "input_pair", 1) or 1))
        self.cmb_input.blockSignals(True)
        idx = max(0, input_pair - 1)
        if idx < self.cmb_input.count():
            self.cmb_input.setCurrentIndex(idx)
        self.cmb_input.blockSignals(False)

        self._update_db_label(vol)
        self._sync_rt_params()
        self._rebuild_send_knobs()
        self._rebuild_sidechain_combo()
        self._rebuild_channel_output()

    # ---- v0.0.20.704: Sandbox crash indicator (P6A — Mixer) -----

    def set_sandbox_state(self, state_name: str, error_msg: str = "",
                          crash_count: int = 0) -> None:
        """Update the sandbox crash state on this mixer strip.

        Args:
            state_name: one of "hidden", "running", "crashed",
                        "restarting", "disabled"
            error_msg:  crash error message (for tooltip)
            crash_count: number of crashes
        """
        try:
            from pydaw.ui.crash_indicator_widget import CrashState
            _MAP = {
                "hidden": CrashState.HIDDEN,
                "running": CrashState.RUNNING,
                "crashed": CrashState.CRASHED,
                "restarting": CrashState.RESTARTING,
                "disabled": CrashState.DISABLED,
            }
            st = _MAP.get(str(state_name).lower(), CrashState.HIDDEN)
        except Exception:
            return

        # Update badge
        if self._crash_badge is not None:
            try:
                self._crash_badge.set_state(st, error_msg, crash_count)
            except Exception:
                pass

        # Red border when crashed, green when running, none when hidden
        is_crashed = (state_name == "crashed")
        if is_crashed != self._sandbox_crashed:
            self._sandbox_crashed = is_crashed
            try:
                if is_crashed:
                    self.setStyleSheet(
                        "_MixerStrip { border: 2px solid #ff5722; "
                        "border-radius: 4px; }"
                    )
                else:
                    self.setStyleSheet("")
            except Exception:
                pass

    # ---- Channel Config + Output Routing (v0.0.20.641 AP5 Phase 5C)

    def _rebuild_channel_output(self) -> None:
        """Rebuild channel config and output target combos."""
        try:
            t = self._track()
            if not t:
                return
            track_kind = str(getattr(t, "kind", "") or "")
            # Master doesn't need output routing
            if track_kind == "master":
                self._ch_widget.setVisible(False)
                return
            self._ch_widget.setVisible(True)

            # Channel config
            ch = str(getattr(t, "channel_config", "stereo") or "stereo")
            self.cmb_channel.blockSignals(True)
            self.cmb_channel.setCurrentIndex(1 if ch == "mono" else 0)
            self.cmb_channel.blockSignals(False)

            # Output target
            current_out = str(getattr(t, "output_target_id", "") or "")
            self.cmb_output.blockSignals(True)
            self.cmb_output.clear()
            self.cmb_output.addItem("→M", "")  # Master
            sel_idx = 0
            for trk in self.project.ctx.project.tracks:
                tk = str(getattr(trk, "kind", "") or "")
                tid_other = str(getattr(trk, "id", "") or "")
                if tid_other == self.track_id:
                    continue
                if tk in ("group", "bus"):
                    n = str(getattr(trk, "name", "") or "")
                    self.cmb_output.addItem(f"→{n[:6]}", tid_other)
                    if tid_other == current_out:
                        sel_idx = self.cmb_output.count() - 1
            self.cmb_output.setCurrentIndex(sel_idx)
            self.cmb_output.blockSignals(False)
        except Exception:
            pass

    def _on_channel_config_changed(self, index: int) -> None:
        try:
            t = self._track()
            if not t:
                return
            t.channel_config = "mono" if index == 1 else "stereo"
            self.project.mark_dirty()
            try:
                self.project.project_updated.emit()
            except Exception:
                pass
        except Exception:
            pass

    def _on_output_target_changed(self, index: int) -> None:
        try:
            t = self._track()
            if not t:
                return
            t.output_target_id = str(self.cmb_output.itemData(index) or "")
            self.project.mark_dirty()
            try:
                self.project.project_updated.emit()
            except Exception:
                pass
        except Exception:
            pass

    # ---- Sidechain routing (v0.0.20.641 AP5 Phase 5B)

    def _rebuild_sidechain_combo(self) -> None:
        """Rebuild sidechain source ComboBox to list all other tracks.

        The sidechain key signal is typically a Kick drum feeding a
        compressor on the Bass track (classic sidechain pumping).
        """
        try:
            t = self._track()
            if not t:
                return
            track_kind = str(getattr(t, "kind", "") or "")
            # Master tracks don't need sidechain input
            if track_kind == "master":
                self._sc_widget.setVisible(False)
                return
            self._sc_widget.setVisible(True)

            current_sc = str(getattr(t, "sidechain_source_id", "") or "")
            self.cmb_sidechain.blockSignals(True)
            self.cmb_sidechain.clear()
            self.cmb_sidechain.addItem("— None —", "")

            # List all other tracks as possible sidechain sources
            selected_idx = 0
            for i, trk in enumerate(self.project.ctx.project.tracks):
                tid = str(getattr(trk, "id", "") or "")
                if tid == self.track_id:
                    continue  # can't sidechain from yourself
                name = str(getattr(trk, "name", "") or f"Track {i}")
                kind = str(getattr(trk, "kind", "") or "")
                label = f"{name}"
                if kind:
                    label = f"{name} [{kind[0].upper()}]"
                self.cmb_sidechain.addItem(label, tid)
                if tid == current_sc:
                    selected_idx = self.cmb_sidechain.count() - 1

            self.cmb_sidechain.setCurrentIndex(selected_idx)
            self.cmb_sidechain.blockSignals(False)

            # Visual indicator: highlight SC label if active
            if current_sc:
                self._sc_lbl.setStyleSheet("font-size: 8px; color: #f90; font-weight: bold; background: #432; border-radius: 2px;")
            else:
                self._sc_lbl.setStyleSheet("font-size: 8px; color: #666; font-weight: bold;")
        except Exception:
            pass

    def _on_sidechain_changed(self, index: int) -> None:
        """Handle sidechain source ComboBox change."""
        try:
            t = self._track()
            if not t:
                return
            source_id = str(self.cmb_sidechain.itemData(index) or "")
            t.sidechain_source_id = source_id
            self.project.mark_dirty()
            try:
                self.project.project_updated.emit()
            except Exception:
                pass
        except Exception:
            pass

    # ---- Send knobs (v0.0.20.518 Bitwig-style)

    def _rebuild_send_knobs(self) -> None:
        """Rebuild send knobs to match current FX tracks in project.

        v0.0.20.519: Compact Bitwig-style layout — each send is one tiny row:
        [3-char label] [20px knob] all stacked vertically in minimal space.
        """
        try:
            t = self._track()
            if not t:
                return
            track_kind = str(getattr(t, "kind", "") or "")
            # FX and master tracks don't show sends (they ARE the receive end)
            if track_kind in ("fx", "master"):
                self._send_scroll.setVisible(False)
                return

            fx_tracks = list(self.project.get_fx_tracks()) if hasattr(self.project, "get_fx_tracks") else []
            if not fx_tracks:
                self._send_scroll.setVisible(False)
                return

            self._send_scroll.setVisible(True)
            sends = {str(s.get("target_track_id", "")): s for s in list(getattr(t, "sends", []) or []) if isinstance(s, dict)}

            # Remove knobs for deleted FX tracks
            fx_ids = {str(getattr(fx, "id", "")) for fx in fx_tracks}
            for fid in list(self._send_knobs.keys()):
                if fid not in fx_ids:
                    try:
                        self._send_knobs.pop(fid).deleteLater()
                    except Exception:
                        pass
                    try:
                        self._send_labels.pop(fid).deleteLater()
                    except Exception:
                        pass

            # Clear layout
            while self._send_layout.count():
                item = self._send_layout.takeAt(0)
                # Don't delete widgets — we reuse them

            # Add/update knobs for each FX track — compact horizontal rows
            for fx_num, fx_trk in enumerate(fx_tracks, 1):
                fid = str(getattr(fx_trk, "id", ""))
                raw_name = str(getattr(fx_trk, "name", "FX"))
                # Short label with number for quick identification
                short = f"{raw_name[:3]}{fx_num}" if len(fx_tracks) > 1 else raw_name[:5]
                amount = float(sends.get(fid, {}).get("amount", 0.0) if fid in sends else 0.0)
                is_pre = bool(sends.get(fid, {}).get("pre_fader", False) if fid in sends else False)

                if fid not in self._send_knobs:
                    knob = QDial()
                    knob.setRange(0, 100)
                    knob.setFixedSize(22, 22)
                    knob.setNotchesVisible(False)
                    knob.setWrapping(False)
                    knob.setStyleSheet(
                        "QDial { background: transparent; }"
                    )
                    knob.valueChanged.connect(lambda val, _fid=fid: self._on_send(val, _fid))
                    # v0.0.20.527: Right-click Pre/Post toggle (Bitwig-style)
                    knob.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    knob.customContextMenuRequested.connect(lambda pos, _fid=fid, _knob=knob: self._on_send_context_menu(_knob, _fid, pos))
                    self._send_knobs[fid] = knob

                    lbl = QLabel(short)
                    lbl.setFixedHeight(14)
                    lbl.setFixedWidth(38)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self._send_labels[fid] = lbl

                # v0.0.20.528: Register send as automatable parameter
                self._register_send_automation(fid, raw_name, fx_num)

                knob = self._send_knobs[fid]
                lbl = self._send_labels[fid]

                # v0.0.20.529: Tag knob with param_id for MIDI Learn CC recording
                knob._pydaw_param_id = f"trk:{self.track_id}:send:{fid}"

                # Update values
                knob.blockSignals(True)
                knob.setValue(int(round(amount * 100.0)))
                knob.blockSignals(False)
                lbl.setText(short)
                pct = int(round(amount * 100.0))
                pre_post = "Pre-Fader" if is_pre else "Post-Fader"
                knob.setToolTip(f"Send {fx_num} → {raw_name} ({pct}%)\n{pre_post}\nRechtsklick: Pre/Post")

                # Color: yellow=post, blue=pre (Bitwig-style)
                color = "#6af" if is_pre else "#fa3"
                active = amount > 0.001
                lbl.setStyleSheet(
                    f"font-size: 8px; color: {color if active else '#555'}; padding: 0; margin: 0;"
                )

                # Build compact row: [label][knob]
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(2)
                row.addWidget(lbl)
                row.addWidget(knob)
                row.addStretch(1)
                self._send_layout.addLayout(row)

        except Exception:
            pass

    def _on_send(self, val: int, fx_track_id: str) -> None:
        """Handle send knob change."""
        try:
            amount = float(val) / 100.0
            t = self._track()
            if not t:
                return
            if amount > 0.001:
                self.project.add_send(self.track_id, fx_track_id, amount=amount)
            else:
                self.project.remove_send(self.track_id, fx_track_id)
        except Exception:
            pass

    def _on_send_context_menu(self, knob: QDial, fx_track_id: str, pos) -> None:
        """v0.0.20.527+528+529: Right-click context menu on Send knob."""
        try:
            t = self._track()
            if not t:
                return
            sends = {str(s.get("target_track_id", "")): s for s in list(getattr(t, "sends", []) or []) if isinstance(s, dict)}
            current_send = sends.get(fx_track_id, {})
            is_pre = bool(current_send.get("pre_fader", False))
            has_send = fx_track_id in sends and float(current_send.get("amount", 0)) > 0.001

            # Find FX track name
            fx_name = "FX"
            try:
                fx_trk = next((ft for ft in self.project.ctx.project.tracks if str(getattr(ft, "id", "")) == fx_track_id), None)
                if fx_trk:
                    fx_name = str(getattr(fx_trk, "name", "FX"))
            except Exception:
                pass

            am = getattr(self.project, "automation_manager", None)

            menu = QMenu(knob)
            menu.setStyleSheet("QMenu { font-size: 10px; }")

            # v0.0.20.528: Show Automation in Arranger
            param_id = f"trk:{self.track_id}:send:{fx_track_id}"
            a_auto = menu.addAction("📈 Automation im Arranger zeigen")

            # v0.0.20.529: MIDI Learn
            has_mapping = bool(getattr(knob, "_midi_cc_mapping", None))
            if has_mapping:
                cc_info = getattr(knob, "_midi_cc_mapping", (0, 0))
                a_learn = menu.addAction(f"🎛 MIDI Learn (CC {cc_info[1]})")
                a_unlearn = menu.addAction("🚫 MIDI Learn zurücksetzen")
            else:
                a_learn = menu.addAction("🎛 MIDI Learn")
                a_unlearn = None

            menu.addSeparator()

            # Pre/Post toggle
            toggle_label = "Auf Pre-Fader umschalten" if not is_pre else "Auf Post-Fader umschalten"
            toggle_icon = "🔵" if not is_pre else "🟡"
            a_toggle = menu.addAction(f"{toggle_icon} {toggle_label}")
            a_toggle.setEnabled(has_send)

            menu.addSeparator()

            # Send amount shortcuts
            a_50 = menu.addAction("50%")
            a_100 = menu.addAction("100%")

            menu.addSeparator()

            # Remove send
            a_remove = menu.addAction("❌ Send entfernen")
            a_remove.setEnabled(has_send)

            chosen = menu.exec(knob.mapToGlobal(pos))
            if chosen is None:
                return

            if chosen == a_auto:
                if am is not None and hasattr(am, "request_show_automation"):
                    am.request_show_automation.emit(param_id)
            elif chosen == a_learn:
                self._start_send_midi_learn(knob, fx_track_id)
            elif a_unlearn is not None and chosen == a_unlearn:
                self._reset_send_midi_learn(knob, fx_track_id)
            elif chosen == a_toggle:
                if hasattr(self.project, "toggle_send_pre_fader"):
                    self.project.toggle_send_pre_fader(self.track_id, fx_track_id)
                else:
                    amt = float(current_send.get("amount", 0.5))
                    self.project.add_send(self.track_id, fx_track_id, amount=amt, pre_fader=not is_pre)
            elif chosen == a_50:
                self.project.add_send(self.track_id, fx_track_id, amount=0.5, pre_fader=is_pre)
            elif chosen == a_100:
                self.project.add_send(self.track_id, fx_track_id, amount=1.0, pre_fader=is_pre)
            elif chosen == a_remove:
                self.project.remove_send(self.track_id, fx_track_id)
        except Exception:
            pass

    # ---- MIDI Learn for Send knobs (v0.0.20.529)

    def _start_send_midi_learn(self, knob: QDial, fx_track_id: str) -> None:
        """Enter MIDI Learn mode: next CC assigns to this send knob."""
        try:
            am = getattr(self.project, "automation_manager", None)
            if am is None:
                return
            # Visual feedback: red border while waiting for CC
            knob.setStyleSheet("QDial { background: transparent; border: 2px solid #cc3333; border-radius: 11px; }")
            # Set learn target — AutomationManager.handle_midi_message() picks it up
            am._midi_learn_knob = knob
        except Exception:
            pass

    def _reset_send_midi_learn(self, knob: QDial, fx_track_id: str) -> None:
        """Remove MIDI CC mapping from this send knob."""
        try:
            am = getattr(self.project, "automation_manager", None)
            if am is None:
                return
            mapping = getattr(knob, "_midi_cc_mapping", None)
            if mapping:
                # Remove from live listeners
                cc_listeners = getattr(am, "_midi_cc_listeners", None)
                if cc_listeners and mapping in cc_listeners:
                    del cc_listeners[mapping]
                # Remove from persistent registry
                pid = getattr(knob, "_pydaw_param_id", "")
                persistent = getattr(am, "_persistent_cc_map", None)
                if persistent and pid in persistent:
                    del persistent[pid]
                knob._midi_cc_mapping = None
            # Reset visual
            knob.setStyleSheet("QDial { background: transparent; }")
        except Exception:
            pass

    # ---- Send automation (v0.0.20.528)

    _send_automation_connected: set = None  # type: ignore  # lazy init

    def _register_send_automation(self, fx_track_id: str, fx_name: str, fx_num: int) -> None:
        """Register a send amount as automatable parameter in AutomationManager."""
        try:
            am = getattr(self.project, "automation_manager", None)
            if am is None:
                return
            param_id = f"trk:{self.track_id}:send:{fx_track_id}"
            am.register_parameter(
                param_id,
                f"Send {fx_num} → {fx_name}",
                min_val=0.0,
                max_val=1.0,
                default_val=0.0,
                track_id=self.track_id,
            )
            # Connect parameter_changed once per strip to update knob during playback
            if self._send_automation_connected is None:
                self._send_automation_connected = set()
                try:
                    am.parameter_changed.connect(self._on_send_automation_changed)
                except Exception:
                    pass

            # v0.0.20.529: Re-register CC mapping from persistent registry (survives widget rebuild)
            knob = self._send_knobs.get(fx_track_id)
            if knob is not None:
                persistent = getattr(am, '_persistent_cc_map', None)
                if persistent and param_id in persistent:
                    saved_cc = persistent[param_id]
                    cc_listeners = getattr(am, '_midi_cc_listeners', None)
                    if cc_listeners is None:
                        am._midi_cc_listeners = {}
                        cc_listeners = am._midi_cc_listeners
                    cc_listeners[saved_cc] = knob
                    knob._midi_cc_mapping = saved_cc
        except Exception:
            pass

    def _on_send_automation_changed(self, parameter_id: str, value: float) -> None:
        """Update send knob when automation plays back a send parameter."""
        try:
            # Only handle send params for this track: "trk:{self.track_id}:send:{fx_id}"
            prefix = f"trk:{self.track_id}:send:"
            if not parameter_id.startswith(prefix):
                return
            fx_id = parameter_id[len(prefix):]
            knob = self._send_knobs.get(fx_id)
            if knob is None:
                return
            knob.blockSignals(True)
            knob.setValue(int(round(float(value) * 100.0)))
            knob.blockSignals(False)
        except Exception:
            pass

    # ---- RT param sync

    def _sync_rt_params(self) -> None:
        """Push current values into RTParamStore + HybridBridge for real-time audio."""
        t = self._track()
        if not t:
            return
        vol = float(getattr(t, "volume", 0.8))
        pan = float(getattr(t, "pan", 0.0))

        # Master track → master params
        if getattr(t, "kind", "") == "master":
            if self.audio_engine:
                self.audio_engine.set_master_volume(vol)
                self.audio_engine.set_master_pan(pan)
            if self.rt_params:
                self.rt_params.set_param("master:vol", vol)
                self.rt_params.set_param("master:pan", pan)
        else:
            # NEW v0.0.20.37: Write to atomic dicts (LIKE MASTER!)
            if self.audio_engine and hasattr(self.audio_engine, 'set_track_volume'):
                try:
                    self.audio_engine.set_track_volume(self.track_id, vol)
                    self.audio_engine.set_track_pan(self.track_id, pan)
                    self.audio_engine.set_track_mute(self.track_id, bool(getattr(t, "muted", False)))
                    self.audio_engine.set_track_solo(self.track_id, bool(getattr(t, "solo", False)))
                except Exception:
                    pass
            # Legacy: Per-track RT params
            if self.rt_params:
                self.rt_params.set_track_vol(self.track_id, vol)
                self.rt_params.set_track_pan(self.track_id, pan)
                self.rt_params.set_track_mute(
                    self.track_id, bool(getattr(t, "muted", False)))
                self.rt_params.set_track_solo(
                    self.track_id, bool(getattr(t, "solo", False)))
            # v0.0.20.14: Per-track via lock-free ring buffer
            if self.hybrid_bridge:
                try:
                    self.hybrid_bridge.set_track_volume(self.track_id, vol)
                    self.hybrid_bridge.set_track_pan(self.track_id, pan)
                    self.hybrid_bridge.set_track_mute(
                        self.track_id, bool(getattr(t, "muted", False)))
                    self.hybrid_bridge.set_track_solo(
                        self.track_id, bool(getattr(t, "solo", False)))
                except Exception:
                    pass

    # ---- UI callbacks

    def _on_vol(self, v: int) -> None:
        t = self._track()
        if not t:
            return
        vol = max(0.0, min(1.0, float(v) / 127.0))
        t.volume = vol
        self._update_db_label(vol)

        # Live RT param update
        if getattr(t, "kind", "") == "master":
            if self.audio_engine:
                self.audio_engine.set_master_volume(vol)
            if self.rt_params:
                self.rt_params.set_param("master:vol", vol)
        else:
            # NEW v0.0.20.33: Write to atomic dict (additional channel, SAFE!)
            if self.audio_engine and hasattr(self.audio_engine, 'set_track_volume'):
                try:
                    self.audio_engine.set_track_volume(self.track_id, vol)
                except Exception:
                    pass
            # Legacy channels (keep for compatibility)
            if self.rt_params:
                self.rt_params.set_track_vol(self.track_id, vol)
            # v0.0.20.14: lock-free ring
            if self.hybrid_bridge:
                try:
                    self.hybrid_bridge.set_track_volume(self.track_id, vol)
                except Exception:
                    pass
        # No project_updated during drag (performance)

    def _on_pan(self, v: int) -> None:
        t = self._track()
        if not t:
            return
        pan = max(-1.0, min(1.0, float(v) / 100.0))
        t.pan = pan

        if getattr(t, "kind", "") == "master":
            if self.audio_engine:
                self.audio_engine.set_master_pan(pan)
            if self.rt_params:
                self.rt_params.set_param("master:pan", pan)
        else:
            # NEW v0.0.20.33: Write to atomic dict (SAFE!)
            if self.audio_engine and hasattr(self.audio_engine, 'set_track_pan'):
                try:
                    self.audio_engine.set_track_pan(self.track_id, pan)
                except Exception:
                    pass
            # Legacy channels
            if self.rt_params:
                self.rt_params.set_track_pan(self.track_id, pan)
            # v0.0.20.14: lock-free ring
            if self.hybrid_bridge:
                try:
                    self.hybrid_bridge.set_track_pan(self.track_id, pan)
                except Exception:
                    pass

    def _on_mute(self, checked: bool) -> None:
        t = self._track()
        if not t:
            return
        t.muted = bool(checked)
        # NEW v0.0.20.33: Write to atomic dict (SAFE!)
        if self.audio_engine and hasattr(self.audio_engine, 'set_track_mute'):
            try:
                self.audio_engine.set_track_mute(self.track_id, checked)
            except Exception:
                pass
        # Legacy channels
        if self.rt_params:
            self.rt_params.set_track_mute(self.track_id, checked)
        # v0.0.20.14: lock-free ring
        if self.hybrid_bridge:
            try:
                self.hybrid_bridge.set_track_mute(self.track_id, checked)
            except Exception:
                pass

    def _on_solo(self, checked: bool) -> None:
        t = self._track()
        if not t:
            return
        t.solo = bool(checked)
        # NEW v0.0.20.33: Write to atomic dict (SAFE!)
        if self.audio_engine and hasattr(self.audio_engine, 'set_track_solo'):
            try:
                self.audio_engine.set_track_solo(self.track_id, checked)
            except Exception:
                pass
        # Legacy channels
        if self.rt_params:
            self.rt_params.set_track_solo(self.track_id, checked)
        # v0.0.20.14: lock-free ring
        if self.hybrid_bridge:
            try:
                self.hybrid_bridge.set_track_solo(self.track_id, checked)
            except Exception:
                pass

    # ---- v0.0.20.636: Input Routing (AP2 Phase 2B) ----

    def _populate_input_routing(self) -> None:
        """Populate input routing ComboBox with available stereo pairs."""
        self.cmb_input.blockSignals(True)
        self.cmb_input.clear()
        # Default pairs — will be refined if RecordingService provides more
        max_pairs = 8  # reasonable default
        try:
            # Try to get actual input count from recording service
            main_win = self.window()
            rec = getattr(getattr(main_win, 'services', None), 'recording', None)
            if rec is not None:
                max_pairs = max(1, rec.get_stereo_pair_count())
        except Exception:
            pass
        for i in range(max_pairs):
            self.cmb_input.addItem(f"In {i*2+1}/{i*2+2}")
        # Sync with model
        t = self._track()
        if t:
            idx = max(0, int(getattr(t, 'input_pair', 1) or 1) - 1)
            if idx < self.cmb_input.count():
                self.cmb_input.setCurrentIndex(idx)
        self.cmb_input.blockSignals(False)

    def _on_input_pair_changed(self, index: int) -> None:
        """Handle input pair selection change (v0.0.20.636)."""
        t = self._track()
        if not t:
            return
        pair = index + 1  # 1-based
        t.input_pair = pair

    def _on_rec_arm(self, checked: bool) -> None:
        """Toggle record-arm for this track.

        v0.0.20.636: Multi-track — multiple tracks can be armed simultaneously.
        """
        t = self._track()
        if not t:
            return
        t.record_arm = bool(checked)
        # Visual feedback: tint strip background when armed
        try:
            if checked:
                self.setStyleSheet("QFrame { border-left: 3px solid #e33; }")
            else:
                self.setStyleSheet("")
        except Exception:
            pass

    def _on_mode(self, mode: str) -> None:
        t = self._track()
        if not t:
            return
        t.automation_mode = str(mode)
        self.project.project_updated.emit()

    def _rename_track(self) -> None:
        t = self._track()
        if not t or t.kind == "master":
            return
        new_name, ok = QInputDialog.getText(
            self, "Track umbenennen",
            f"Neuer Name für '{t.name}':", text=t.name)
        if ok and new_name.strip():
            try:
                self.project.rename_track(t.id, new_name.strip())
            except Exception:
                pass

    # ── v0.0.20.655: Right-click context menu on mixer strip ─────────────

    def contextMenuEvent(self, event) -> None:
        """Right-click context menu for the mixer strip.

        v0.0.20.655: Multi-Output for Drum Machine tracks + Collapse/Expand.
        """
        try:
            t = self._track()
            if t is None or t.kind == "master":
                return super().contextMenuEvent(event)

            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 10px; }")

            # Rename
            menu.addAction("✏️ Umbenennen", self._rename_track)

            # Multi-Output (only for Drum Machine tracks)
            is_drum = self._is_drum_machine_track(t)
            if is_drum:
                oc = int(getattr(t, "plugin_output_count", 0) or 0)
                if oc < 2:
                    menu.addSeparator()
                    menu.addAction("🎛 Multi-Output aktivieren (16 Pads)", self._enable_multi_output)
                else:
                    menu.addSeparator()
                    menu.addAction("🔇 Multi-Output deaktivieren", self._disable_multi_output)

            # Collapse/Expand child tracks
            has_children = self._has_multi_output_children(t)
            if has_children:
                collapsed = getattr(self, "_children_collapsed", False)
                if collapsed:
                    menu.addAction("📂 Pad-Kanäle einblenden", self._expand_children)
                else:
                    menu.addAction("📁 Pad-Kanäle ausblenden", self._collapse_children)

            menu.exec(event.globalPos())
        except Exception:
            pass

    def _is_drum_machine_track(self, t) -> bool:
        """Check if this track hosts a Pro Drum Machine instrument."""
        try:
            pt = str(getattr(t, "plugin_type", "") or "")
            if pt in ("drum_machine", "chrono.pro_drum_machine"):
                return True
            ist = getattr(t, "instrument_state", None) or {}
            if isinstance(ist, dict) and "drum_machine" in ist:
                return True
        except Exception:
            pass
        return False

    def _has_multi_output_children(self, t) -> bool:
        """Check if this track has multi-output child tracks."""
        try:
            routing = getattr(t, "plugin_output_routing", None)
            return bool(isinstance(routing, dict) and routing)
        except Exception:
            return False

    def _enable_multi_output(self) -> None:
        """Create 16 child tracks for Drum Machine multi-output.

        v0.0.20.655: Creates child tracks named "Kick", "Snare", etc.
        Sets Track.plugin_output_count=16, plugin_output_routing={1: child1, 2: child2, ...}.
        Child tracks get track_group_id = parent track id.
        """
        try:
            t = self._track()
            if t is None:
                return
            parent_tid = str(t.id)

            pad_names = [
                "Kick", "Snare", "CHat", "OHat",
                "Clap", "Tom", "Perc", "Rim",
                "FX1", "FX2", "Ride", "Crash",
                "Pad13", "Pad14", "Pad15", "Pad16",
            ]

            # Create 16 child tracks (output 0 = parent, outputs 1-15 = children)
            # We create 15 child tracks for outputs 1..15; output 0 stays on parent
            routing = {}
            parent_name = str(getattr(t, "name", "Drum") or "Drum")
            for i in range(1, 16):
                child_name = f"{parent_name}: {pad_names[i]}" if i < len(pad_names) else f"{parent_name}: Pad{i+1}"
                try:
                    child = self.project.add_track(
                        "audio",
                        name=child_name,
                        insert_after_track_id=parent_tid,
                        group_id=parent_tid,
                        group_name=parent_name,
                    )
                    routing[i] = str(child.id)
                except Exception:
                    continue

            # Set multi-output fields on parent track
            t.plugin_output_count = 16
            t.plugin_output_routing = routing

            # Rebuild audio engine routing
            try:
                ae = self.audio_engine
                if ae is not None and hasattr(ae, "rebuild_fx_maps"):
                    ae.rebuild_fx_maps(self.project.ctx.project)
            except Exception:
                pass

            self.project.project_updated.emit()
        except Exception:
            pass

    def _disable_multi_output(self) -> None:
        """Remove multi-output child tracks and reset to stereo."""
        try:
            t = self._track()
            if t is None:
                return

            # Remove child tracks
            routing = getattr(t, "plugin_output_routing", {}) or {}
            for out_idx, child_tid in dict(routing).items():
                try:
                    self.project.delete_track(str(child_tid))
                except Exception:
                    continue

            # Reset multi-output fields
            t.plugin_output_count = 0
            t.plugin_output_routing = {}

            try:
                ae = self.audio_engine
                if ae is not None and hasattr(ae, "rebuild_fx_maps"):
                    ae.rebuild_fx_maps(self.project.ctx.project)
            except Exception:
                pass

            self.project.project_updated.emit()
        except Exception:
            pass

    def _collapse_children(self) -> None:
        """Hide multi-output child tracks in the mixer (UI-only, Collapse)."""
        try:
            self._children_collapsed = True
            self._set_children_visible(False)
        except Exception:
            pass

    def _expand_children(self) -> None:
        """Show multi-output child tracks in the mixer (UI-only, Expand)."""
        try:
            self._children_collapsed = False
            self._set_children_visible(True)
        except Exception:
            pass

    def _set_children_visible(self, visible: bool) -> None:
        """Toggle visibility of child mixer strips.

        v0.0.20.655: Finds the MixerPanel parent and hides/shows child strips.
        """
        try:
            t = self._track()
            if t is None:
                return
            routing = getattr(t, "plugin_output_routing", {}) or {}
            child_ids = set(str(v) for v in routing.values())
            if not child_ids:
                return

            # Find parent MixerPanel
            panel = self.parent()
            while panel is not None and not isinstance(panel, MixerPanel):
                panel = panel.parent()
            if panel is None or not hasattr(panel, "_strips"):
                return

            for cid in child_ids:
                strip = panel._strips.get(cid)
                if strip is not None:
                    strip.setVisible(visible)
        except Exception:
            pass

    def _update_db_label(self, vol: float) -> None:
        if vol <= 0.001:
            self.lbl_db.setText("-∞ dB")
        else:
            db = 20.0 * math.log10(max(1e-10, vol))
            self.lbl_db.setText(f"{db:+.1f} dB")
    
    def _update_vu_meter(self) -> None:
        """Update VU meter (30 FPS, GUI thread).

        v0.0.20.41: Direct peak path (most reliable) + fallback chain.
        Sources (in priority order):
        1. AudioEngine._direct_peaks (written directly from audio callback)
        2. HybridEngineBridge → TrackMeterRing
        3. HybridEngineBridge → read_track_peak() / read_master_peak()
        4. AudioEngine.read_track_peak() / read_master_peak()
        """
        try:
            t = self._track()
            if t is None:
                return

            is_master = str(getattr(t, "kind", "")) == "master"
            l, r = 0.0, 0.0
            got_data = False

            # --- Source 1: Direct peaks (v0.0.20.41 — most reliable)
            ae = self.audio_engine
            if ae is not None and hasattr(ae, "read_direct_track_peak"):
                try:
                    if is_master:
                        l, r = ae.read_master_peak()
                        got_data = (l > 0.0001 or r > 0.0001)
                    else:
                        l, r = ae.read_direct_track_peak(self.track_id)
                        got_data = (l > 0.0001 or r > 0.0001)
                except Exception:
                    pass

            # --- Source 2: Hybrid bridge (fallback)
            if not got_data:
                hb = self.hybrid_bridge
                if hb is not None:
                    try:
                        if is_master:
                            l, r = hb.read_master_peak()
                            got_data = True
                        elif self._track_idx is not None:
                            cb = getattr(hb, "callback", None)
                            if cb is not None:
                                meter = cb.get_track_meter(int(self._track_idx))
                                l, r = meter.read_and_decay()
                                got_data = True
                    except Exception:
                        pass

                    # Source 3: Bridge-level read_track_peak
                    if not got_data and not is_master:
                        try:
                            l, r = hb.read_track_peak(self.track_id)
                            got_data = True
                        except Exception:
                            pass

            # --- Source 4: AudioEngine helper (legacy / non-hybrid)
            if not got_data:
                if ae is not None:
                    try:
                        if is_master and hasattr(ae, "read_master_peak"):
                            l, r = ae.read_master_peak()
                            got_data = True
                        elif hasattr(ae, "read_track_peak"):
                            l, r = ae.read_track_peak(self.track_id)
                            got_data = True
                    except Exception:
                        pass

            if got_data:
                self.vu.set_levels(float(l), float(r))

        except Exception:
            # Fail silently - never break UI update loop
            pass


# ---- Mixer Panel

class MixerPanel(QWidget):
    """Pro-DAW-Style horizontal scrolling mixer with vertical fader strips."""

    def __init__(self, project: ProjectService, audio_engine=None,
                 rt_params=None, hybrid_bridge=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.audio_engine = audio_engine
        self.rt_params = rt_params
        self.hybrid_bridge = hybrid_bridge  # v0.0.20.14

        # v0.0.20.28: Auto-wire HybridEngineBridge from AudioEngine when not explicitly provided.
        if self.hybrid_bridge is None and self.audio_engine is not None:
            try:
                hb = getattr(self.audio_engine, "_hybrid_bridge", None)
                if hb is None:
                    hb = getattr(self.audio_engine, "hybrid_bridge", None)
                if hb is not None:
                    self.hybrid_bridge = hb
            except Exception:
                pass
        self._strips: dict[str, _MixerStrip] = {}

        self._build_ui()
        self.project.project_updated.connect(self.refresh)
        self.refresh()

        # v0.0.20.584: Single VU meter timer for ALL strips (replaces N per-strip timers).
        # At 10 tracks the old design fired 300 callbacks/s, now it's just 30/s total.
        self._vu_timer = QTimer(self)
        self._vu_timer.setInterval(33)  # 30 FPS
        self._vu_timer.timeout.connect(self._tick_all_vu_meters)
        if self.isVisible():
            self._vu_timer.start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(6)
        lbl = QLabel("MIXER")
        lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        header.addWidget(lbl)

        self.btn_add = QPushButton("+ Add")
        self.btn_add.setFixedWidth(70)
        self.btn_add.clicked.connect(self._show_add_menu)
        header.addWidget(self.btn_add)

        self.btn_remove = QPushButton("− Remove")
        self.btn_remove.setFixedWidth(80)
        self.btn_remove.clicked.connect(self._remove_selected_track)
        header.addWidget(self.btn_remove)

        # v0.0.20.641: Sidechain Routing Matrix button (AP5 Phase 5B)
        self.btn_sc_matrix = QPushButton("SC Matrix")
        self.btn_sc_matrix.setFixedWidth(80)
        self.btn_sc_matrix.setToolTip("Sidechain Routing Matrix — Overview aller Sidechain-Verbindungen")
        self.btn_sc_matrix.setStyleSheet(
            "QPushButton { font-size: 9px; color: #f90; }"
            "QPushButton:hover { background: #432; }"
        )
        self.btn_sc_matrix.clicked.connect(self._show_sc_matrix)
        header.addWidget(self.btn_sc_matrix)

        # v0.0.20.641: Patchbay Routing Overview button (AP5 Phase 5C)
        self.btn_patchbay = QPushButton("Patchbay")
        self.btn_patchbay.setFixedWidth(80)
        self.btn_patchbay.setToolTip("Patchbay — Routing Overview (Output, Sends, Sidechain, Channel)")
        self.btn_patchbay.setStyleSheet(
            "QPushButton { font-size: 9px; color: #8cf; }"
            "QPushButton:hover { background: #234; }"
        )
        self.btn_patchbay.clicked.connect(self._show_patchbay)
        header.addWidget(self.btn_patchbay)

        header.addStretch(1)
        layout.addLayout(header)

        # Scroll area with horizontal strip layout
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)

        self.inner = QWidget()
        self.inner_layout = QHBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(2)
        self.inner_layout.addStretch(1)
        self.scroll.setWidget(self.inner)

        # v0.0.20.640: Routing overlay (visual send lines)
        self._routing_overlay = _RoutingOverlay(self.inner)
        self._routing_overlay.setGeometry(0, 0, 4000, 600)  # resized in refresh
        self._routing_overlay.raise_()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _show_add_menu(self) -> None:
        menu = QMenu(self)
        a_audio = menu.addAction("Audio-Spur")
        a_inst = menu.addAction("Instrumenten-Spur")
        a_bus = menu.addAction("FX/Bus-Spur")
        menu.addSeparator()
        a_fx = menu.addAction("FX-Spur (Return)")
        action = menu.exec(
            self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft()))
        if action == a_audio:
            self.project.add_track("audio")
        elif action == a_inst:
            self.project.add_track("instrument")
        elif action == a_bus:
            self.project.add_track("bus")
        elif action == a_fx:
            self.project.add_track("fx")

    def _remove_selected_track(self) -> None:
        tid = getattr(self.project, "selected_track_id", "") or ""
        if not tid:
            return
        trk = next(
            (t for t in self.project.ctx.project.tracks
             if t.id == tid), None)
        if trk and getattr(trk, "kind", "") == "master":
            return
        try:
            self.project.delete_track(tid)
        except Exception:
            pass

    def _show_sc_matrix(self) -> None:
        """v0.0.20.641: Open the Sidechain Routing Matrix dialog (AP5 Phase 5B)."""
        try:
            dlg = SidechainRoutingMatrix(self.project, self)
            dlg.exec()
        except Exception:
            pass

    def _show_patchbay(self) -> None:
        """v0.0.20.641: Open the Patchbay Routing Overview dialog (AP5 Phase 5C)."""
        try:
            dlg = PatchbayDialog(self.project, self)
            dlg.exec()
        except Exception:
            pass

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._remove_selected_track()
            event.accept()
            return
        super().keyPressEvent(event)

    def refresh(self) -> None:
        existing_ids = {t.id for t in self.project.ctx.project.tracks}

        # v0.0.20.25: Keep HybridEngineBridge track indices aligned with project order
        if self.hybrid_bridge is not None and hasattr(self.hybrid_bridge, "set_track_index_map"):
            try:
                mapping = {t.id: int(i) for i, t in enumerate(self.project.ctx.project.tracks)}
                self.hybrid_bridge.set_track_index_map(mapping)
            except Exception:
                pass

        # Remove strips for deleted tracks
        for tid in list(self._strips.keys()):
            if tid not in existing_ids:
                w = self._strips.pop(tid)
                w.deleteLater()

        # Clear layout completely
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            w = item.widget()
            if w and not isinstance(w, _MixerStrip):
                w.deleteLater()
            elif w:
                w.setParent(None)

        # v0.0.20.571: Bitwig-style layout — Normal tracks left, FX+Master right
        normal_tracks = []  # instrument, audio, bus, group
        fx_tracks = []      # fx (return)
        master_track = None

        for trk in self.project.ctx.project.tracks:
            kind = str(getattr(trk, "kind", "") or "")
            if kind == "master":
                master_track = trk
            elif kind == "fx":
                fx_tracks.append(trk)
            else:
                normal_tracks.append(trk)

        # Rebuild strips in Bitwig order
        all_ordered = normal_tracks + fx_tracks + ([master_track] if master_track else [])

        for track_idx_orig, trk in enumerate(self.project.ctx.project.tracks):
            strip = self._strips.get(trk.id)
            if strip is None:
                strip = _MixerStrip(
                    self.project, trk.id, self.audio_engine,
                    self.rt_params, self.hybrid_bridge)
                self._strips[trk.id] = strip

            if self.hybrid_bridge is not None and hasattr(self.hybrid_bridge, "get_track_idx"):
                try:
                    strip._track_idx = int(self.hybrid_bridge.get_track_idx(trk.id))
                except Exception:
                    strip._track_idx = track_idx_orig
            else:
                strip._track_idx = track_idx_orig

            strip.refresh_from_model()

        # Add normal tracks (left side)
        for trk in normal_tracks:
            strip = self._strips.get(trk.id)
            if strip is not None:
                self.inner_layout.addWidget(strip)

        # Add visual separator if there are FX or master tracks
        if fx_tracks or master_track:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("color: #555; background: #555; max-width: 2px;")
            sep.setFixedWidth(2)
            self.inner_layout.addWidget(sep)

        # Add FX tracks (right side)
        for trk in fx_tracks:
            strip = self._strips.get(trk.id)
            if strip is not None:
                self.inner_layout.addWidget(strip)

        # Master always last (rightmost)
        if master_track is not None:
            strip = self._strips.get(master_track.id)
            if strip is not None:
                self.inner_layout.addWidget(strip)

        self.inner_layout.addStretch(1)

        # v0.0.20.640: Update routing overlay (AP5 Phase 5A)
        try:
            self._update_routing_overlay()
        except Exception:
            pass

        # v0.0.20.655: Restore collapse state for multi-output child tracks
        try:
            self._restore_collapse_states()
        except Exception:
            pass

    # v0.0.20.655: Multi-output child track collapse/expand persistence

    def _restore_collapse_states(self) -> None:
        """After refresh, re-hide child strips whose parent is in collapsed state."""
        try:
            for tid, strip in self._strips.items():
                if not getattr(strip, "_children_collapsed", False):
                    continue
                # This strip is a parent with collapsed children
                try:
                    t = strip._track()
                    if t is None:
                        continue
                    routing = getattr(t, "plugin_output_routing", {}) or {}
                    for child_tid in routing.values():
                        child_strip = self._strips.get(str(child_tid))
                        if child_strip is not None:
                            child_strip.setVisible(False)
                except Exception:
                    continue
        except Exception:
            pass

    # v0.0.20.584: Centralized VU metering (single timer for all strips)

    def _tick_all_vu_meters(self) -> None:
        """Update VU meters for all strips in one callback (~30 FPS).

        Replaces N individual QTimers (one per strip) with a single iteration.
        At 10 tracks: 300 callbacks/s → 30/s. At 20 tracks: 600 → 30.
        """
        try:
            for strip in self._strips.values():
                try:
                    strip._update_vu_meter()
                except Exception:
                    pass
        except Exception:
            pass

    def _update_routing_overlay(self) -> None:
        """v0.0.20.640: Calculate routing lines and update the overlay widget."""
        overlay = getattr(self, '_routing_overlay', None)
        if not overlay:
            return
        try:
            # Resize overlay to match inner widget
            overlay.setGeometry(0, 0,
                                max(self.inner.width(), 2000),
                                max(self.inner.height(), 400))
            overlay.raise_()

            routes = []
            fx_tracks = list(self.project.get_fx_tracks()) if hasattr(self.project, 'get_fx_tracks') else []
            fx_ids = [str(getattr(ft, 'id', '')) for ft in fx_tracks]

            for tid, strip in self._strips.items():
                if not strip.isVisible():
                    continue
                trk = next((t for t in self.project.ctx.project.tracks
                            if str(getattr(t, 'id', '')) == tid), None)
                if not trk:
                    continue
                sends = list(getattr(trk, 'sends', []) or [])
                if not sends:
                    continue

                # Source position: center-bottom of strip
                src_pos = strip.mapTo(self.inner, strip.rect().center())
                sx = float(src_pos.x())
                sy = float(strip.mapTo(self.inner, strip.rect().bottomLeft()).y()) - 10

                for s in sends:
                    if not isinstance(s, dict):
                        continue
                    target_id = str(s.get('target_track_id', ''))
                    amount = float(s.get('amount', 0))
                    if amount < 0.01 or not target_id:
                        continue

                    target_strip = self._strips.get(target_id)
                    if not target_strip or not target_strip.isVisible():
                        continue

                    # Dest position: center-top of target strip
                    dst_pos = target_strip.mapTo(self.inner, target_strip.rect().center())
                    dx = float(dst_pos.x())
                    dy = float(target_strip.mapTo(self.inner, target_strip.rect().topLeft()).y()) + 10

                    ci = fx_ids.index(target_id) if target_id in fx_ids else 0
                    routes.append((sx, sy, dx, dy, amount, ci))

            # v0.0.20.641: Collect sidechain routes (AP5 Phase 5B)
            sc_routes = []
            for tid, strip in self._strips.items():
                if not strip.isVisible():
                    continue
                trk = next((t for t in self.project.ctx.project.tracks
                            if str(getattr(t, 'id', '')) == tid), None)
                if not trk:
                    continue
                sc_src = str(getattr(trk, 'sidechain_source_id', '') or '')
                if not sc_src:
                    continue
                src_strip = self._strips.get(sc_src)
                if not src_strip or not src_strip.isVisible():
                    continue
                # Source: center of sidechain source strip
                s_pos = src_strip.mapTo(self.inner, src_strip.rect().center())
                s_x = float(s_pos.x())
                s_y = float(src_strip.mapTo(self.inner, src_strip.rect().bottomLeft()).y()) - 20
                # Dest: center-top of destination strip
                d_pos = strip.mapTo(self.inner, strip.rect().center())
                d_x = float(d_pos.x())
                d_y = float(strip.mapTo(self.inner, strip.rect().topLeft()).y()) + 20
                sc_routes.append((s_x, s_y, d_x, d_y))

            overlay.set_routes(routes, sc_routes)
        except Exception:
            overlay.set_routes([], [])

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        try:
            if not self._vu_timer.isActive():
                self._vu_timer.start()
        except Exception:
            pass

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        try:
            if self._vu_timer.isActive():
                self._vu_timer.stop()
        except Exception:
            pass


# ---- v0.0.20.641: Sidechain Routing Matrix Dialog (AP5 Phase 5B)

class SidechainRoutingMatrix(QDialog):
    """Grid-style overview of all sidechain connections in the project.

    Rows = destination tracks (tracks that RECEIVE a sidechain key signal).
    Columns = source tracks (tracks that PROVIDE the key signal).
    A checked cell means: source column feeds sidechain to destination row.
    Only one source per destination is allowed (radio-style — checking one unchecks others).
    """

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Sidechain Routing Matrix")
        self.setMinimumSize(500, 400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        info = QLabel("Rows = Destination (receives sidechain)  •  Columns = Source (provides key signal)")
        info.setStyleSheet("font-size: 9px; color: #aaa;")
        info.setWordWrap(True)
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll, 1)

        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(2)
        scroll.setWidget(grid_widget)

        tracks = list(self.project.ctx.project.tracks)
        # Filter out master track from destinations (master doesn't need sidechain)
        dest_tracks = [t for t in tracks if str(getattr(t, "kind", "")) != "master"]
        src_tracks = tracks  # any track can be a source

        self._checks: dict[tuple[str, str], QCheckBox] = {}  # (dest_id, src_id) -> checkbox

        # Header row: source track names (columns)
        self._grid.addWidget(QLabel(""), 0, 0)  # empty corner
        for col, src in enumerate(src_tracks):
            lbl = QLabel(str(getattr(src, "name", f"T{col}")))
            lbl.setStyleSheet("font-size: 8px; font-weight: bold; color: #ccc;")
            lbl.setToolTip(f"{getattr(src, 'name', '')} [{getattr(src, 'kind', '')}]")
            lbl.setMaximumWidth(60)
            lbl.setWordWrap(True)
            self._grid.addWidget(lbl, 0, col + 1, Qt.AlignmentFlag.AlignCenter)

        # Rows: destination tracks
        for row, dest in enumerate(dest_tracks):
            dest_id = str(getattr(dest, "id", ""))
            dest_name = str(getattr(dest, "name", f"Track {row}"))
            dest_kind = str(getattr(dest, "kind", ""))
            current_sc = str(getattr(dest, "sidechain_source_id", "") or "")

            lbl = QLabel(f"{dest_name}")
            lbl.setStyleSheet("font-size: 8px; font-weight: bold; color: #f90;" if current_sc else "font-size: 8px; color: #aaa;")
            lbl.setToolTip(f"{dest_name} [{dest_kind}]")
            lbl.setMaximumWidth(80)
            lbl.setWordWrap(True)
            self._grid.addWidget(lbl, row + 1, 0)

            for col, src in enumerate(src_tracks):
                src_id = str(getattr(src, "id", ""))
                if src_id == dest_id:
                    # Can't sidechain from self — grey placeholder
                    placeholder = QLabel("—")
                    placeholder.setStyleSheet("font-size: 8px; color: #444;")
                    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._grid.addWidget(placeholder, row + 1, col + 1, Qt.AlignmentFlag.AlignCenter)
                    continue

                cb = QCheckBox()
                cb.setChecked(current_sc == src_id)
                cb.setToolTip(f"SC: {getattr(src, 'name', '')} → {dest_name}")
                cb.setStyleSheet(
                    "QCheckBox { spacing: 0; }"
                    "QCheckBox::indicator { width: 14px; height: 14px; }"
                    "QCheckBox::indicator:checked { background: #f90; border: 1px solid #fc0; border-radius: 2px; }"
                    "QCheckBox::indicator:unchecked { background: #333; border: 1px solid #555; border-radius: 2px; }"
                )
                cb.toggled.connect(lambda checked, _did=dest_id, _sid=src_id: self._on_toggle(_did, _sid, checked))
                self._checks[(dest_id, src_id)] = cb
                self._grid.addWidget(cb, row + 1, col + 1, Qt.AlignmentFlag.AlignCenter)

        # Button box
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    def _on_toggle(self, dest_id: str, src_id: str, checked: bool) -> None:
        """Handle checkbox toggle — radio-style: only one source per dest."""
        try:
            # Find the destination track
            trk = next((t for t in self.project.ctx.project.tracks
                        if str(getattr(t, "id", "")) == dest_id), None)
            if not trk:
                return

            if checked:
                # Uncheck all other sources for this destination
                for (did, sid), cb in self._checks.items():
                    if did == dest_id and sid != src_id:
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
                trk.sidechain_source_id = src_id
            else:
                # Unchecking = remove sidechain
                trk.sidechain_source_id = ""

            self.project.mark_dirty()
            try:
                self.project.project_updated.emit()
            except Exception:
                pass
        except Exception:
            pass


# ---- v0.0.20.641: Patchbay Routing Dialog (AP5 Phase 5C)

class PatchbayDialog(QDialog):
    """Comprehensive routing overview — shows all connections in the project.

    Like Cubase MixConsole Routing or Reaper's Routing Matrix.
    Displays: Output routing, Sends, Sidechain, Channel config per track.
    """

    def __init__(self, project: ProjectService, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Patchbay — Routing Overview")
        self.setMinimumSize(700, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        info = QLabel("Routing Overview — Output, Sends, Sidechain, Channel Config")
        info.setStyleSheet("font-size: 10px; font-weight: bold; color: #ccc;")
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll, 1)

        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(4)
        scroll.setWidget(grid_widget)

        tracks = list(self.project.ctx.project.tracks)

        # Column headers
        headers = ["Track", "Type", "Ch", "Output →", "Sends", "Sidechain ←"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet("font-size: 9px; font-weight: bold; color: #aaa; padding: 2px;")
            self._grid.addWidget(lbl, 0, col)

        self._combos_output: dict[str, QComboBox] = {}
        self._combos_channel: dict[str, QComboBox] = {}
        self._combos_sc: dict[str, QComboBox] = {}

        # Collect valid output targets (group + master)
        output_targets = []
        for t in tracks:
            kind = str(getattr(t, "kind", ""))
            if kind in ("master", "group", "bus"):
                output_targets.append(t)

        for row, trk in enumerate(tracks):
            tid = str(getattr(trk, "id", ""))
            name = str(getattr(trk, "name", f"T{row}"))
            kind = str(getattr(trk, "kind", ""))

            # Track name
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px;")
            self._grid.addWidget(lbl_name, row + 1, 0)

            # Track type
            lbl_kind = QLabel(kind.upper()[:5])
            lbl_kind.setStyleSheet("font-size: 8px; color: #888; padding: 2px;")
            self._grid.addWidget(lbl_kind, row + 1, 1)

            # Channel config (mono/stereo)
            cmb_ch = QComboBox()
            cmb_ch.setFixedHeight(20)
            cmb_ch.setStyleSheet("font-size: 8px;")
            cmb_ch.addItem("Stereo", "stereo")
            cmb_ch.addItem("Mono", "mono")
            current_ch = str(getattr(trk, "channel_config", "stereo") or "stereo")
            cmb_ch.setCurrentIndex(1 if current_ch == "mono" else 0)
            cmb_ch.currentIndexChanged.connect(lambda idx, _tid=tid: self._on_channel_changed(_tid, idx))
            self._combos_channel[tid] = cmb_ch
            self._grid.addWidget(cmb_ch, row + 1, 2)

            # Output target
            cmb_out = QComboBox()
            cmb_out.setFixedHeight(20)
            cmb_out.setStyleSheet("font-size: 8px;")
            cmb_out.addItem("Master", "")
            current_out = str(getattr(trk, "output_target_id", "") or "")
            sel_idx = 0
            for ot in output_targets:
                ot_id = str(getattr(ot, "id", ""))
                if ot_id == tid:
                    continue  # can't route to self
                ot_name = str(getattr(ot, "name", ""))
                ot_kind = str(getattr(ot, "kind", ""))
                if ot_kind == "master":
                    continue  # "Master" is already the default entry
                cmb_out.addItem(f"{ot_name} [{ot_kind[0].upper()}]", ot_id)
                if ot_id == current_out:
                    sel_idx = cmb_out.count() - 1
            if kind == "master":
                cmb_out.setEnabled(False)
            cmb_out.setCurrentIndex(sel_idx)
            cmb_out.currentIndexChanged.connect(lambda idx, _tid=tid, _cmb=cmb_out: self._on_output_changed(_tid, _cmb))
            self._combos_output[tid] = cmb_out
            self._grid.addWidget(cmb_out, row + 1, 3)

            # Sends summary (read-only label)
            sends = list(getattr(trk, "sends", []) or [])
            send_strs = []
            for s in sends:
                if not isinstance(s, dict):
                    continue
                tgt = str(s.get("target_track_id", ""))
                amt = float(s.get("amount", 0))
                if amt > 0.01 and tgt:
                    tgt_name = next((str(getattr(x, "name", "?")) for x in tracks
                                     if str(getattr(x, "id", "")) == tgt), "?")
                    pre = "pre" if s.get("pre_fader") else "post"
                    send_strs.append(f"{tgt_name}({int(amt*100)}%,{pre})")
            lbl_sends = QLabel(", ".join(send_strs) if send_strs else "—")
            lbl_sends.setStyleSheet("font-size: 8px; color: #6c6;" if send_strs else "font-size: 8px; color: #555;")
            lbl_sends.setWordWrap(True)
            lbl_sends.setMaximumWidth(200)
            self._grid.addWidget(lbl_sends, row + 1, 4)

            # Sidechain source
            cmb_sc = QComboBox()
            cmb_sc.setFixedHeight(20)
            cmb_sc.setStyleSheet("font-size: 8px;")
            cmb_sc.addItem("— None —", "")
            current_sc = str(getattr(trk, "sidechain_source_id", "") or "")
            sc_sel = 0
            for st_trk in tracks:
                st_id = str(getattr(st_trk, "id", ""))
                if st_id == tid:
                    continue
                st_name = str(getattr(st_trk, "name", ""))
                cmb_sc.addItem(st_name, st_id)
                if st_id == current_sc:
                    sc_sel = cmb_sc.count() - 1
            if kind == "master":
                cmb_sc.setEnabled(False)
            cmb_sc.setCurrentIndex(sc_sel)
            cmb_sc.currentIndexChanged.connect(lambda idx, _tid=tid, _cmb=cmb_sc: self._on_sc_changed(_tid, _cmb))
            self._combos_sc[tid] = cmb_sc
            self._grid.addWidget(cmb_sc, row + 1, 5)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    def _on_channel_changed(self, tid: str, idx: int) -> None:
        try:
            trk = next((t for t in self.project.ctx.project.tracks
                        if str(getattr(t, "id", "")) == tid), None)
            if trk:
                trk.channel_config = "mono" if idx == 1 else "stereo"
                self.project.mark_dirty()
                try:
                    self.project.project_updated.emit()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_output_changed(self, tid: str, cmb: QComboBox) -> None:
        try:
            trk = next((t for t in self.project.ctx.project.tracks
                        if str(getattr(t, "id", "")) == tid), None)
            if trk:
                trk.output_target_id = str(cmb.currentData() or "")
                self.project.mark_dirty()
                try:
                    self.project.project_updated.emit()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_sc_changed(self, tid: str, cmb: QComboBox) -> None:
        try:
            trk = next((t for t in self.project.ctx.project.tracks
                        if str(getattr(t, "id", "")) == tid), None)
            if trk:
                trk.sidechain_source_id = str(cmb.currentData() or "")
                self.project.mark_dirty()
                try:
                    self.project.project_updated.emit()
                except Exception:
                    pass
        except Exception:
            pass


# ---- Library Panel (placeholder — kept for compatibility)

class LibraryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Bibliothek/Browser (Platzhalter)"))
        layout.addWidget(QLabel(
            "Hier kommen später: Samples, Plugins, Presets, Medienpool…"))
        layout.addStretch(1)
