# -*- coding: utf-8 -*-
"""Bitwig-Style Audio-FX Widgets for PyDAW Device Panel.

v0.0.20.105 — 14 neue Audio-Effekte (UI-Widgets + Projekt-Persistenz).

Jeder Effekt: Parameter-UI → debounced Projekt-Persistenz → RT-Params.
Matching: Bitwig Studio Screenshots 1:1.

Kein Eingriff in bestehende Widgets / Instrumente / Core.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QDial, QSlider, QDoubleSpinBox, QSpinBox, QComboBox,
    QCheckBox, QPushButton, QGroupBox, QMenu,
)


# ═══════════════════════════════════════════════════════════
#  Base — gemeinsame Plumbing für alle Audio-FX
# ═══════════════════════════════════════════════════════════

def _find_track(project: Any, track_id: str):
    try:
        for t in getattr(project, "tracks", []) or []:
            if getattr(t, "id", "") == track_id:
                return t
    except Exception:
        pass
    return None


def _get_device_params(services: Any, track_id: str, device_id: str):
    """Finde das params-dict des Devices im Projekt."""
    ps = getattr(services, "project", None)
    ctx = getattr(ps, "ctx", None) if ps else None
    p = getattr(ctx, "project", None) if ctx else getattr(ps, "project", None) if ps else None
    t = _find_track(p, track_id) if p else None
    if t is None:
        return None
    chain = getattr(t, "audio_fx_chain", None)
    if not isinstance(chain, dict):
        return None
    devs = chain.get("devices", []) or []
    dev = next((d for d in devs if isinstance(d, dict)
                and str(d.get("id", "")) == device_id), None)
    if dev is None:
        return None
    params = dev.get("params")
    if not isinstance(params, dict):
        params = {}
        dev["params"] = params
    return params


class _AudioFxBase(QWidget):
    """Basis für alle Audio-FX mit Debounce + Projekt-Persistenz + Automation."""

    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._restoring = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._on_debounce_flush)

    def _params(self):
        return _get_device_params(self._services, self._track_id, self._device_id)

    def _schedule_save(self):
        if not self._restoring:
            self._debounce.start()

    def _on_debounce_flush(self):
        """Save → Sync RT params (emit kommt aus _save_to_project)."""
        self._save_to_project()
        self._sync_all_params_to_rt()

    def _rt_set(self, param_name: str, value: float):
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae else None
        if rt is None:
            return
        key = f"afx:{self._track_id}:{self._device_id}:{param_name}"
        try:
            rt.set_param(key, value)
        except Exception:
            pass

    def _emit_updated(self):
        ps = getattr(self._services, "project", None)
        try:
            if ps and hasattr(ps, "project_updated"):
                ps.project_updated.emit()
        except Exception:
            pass
        # Rebuild FX maps so the engine picks up param changes
        ae = getattr(self._services, "audio_engine", None)
        try:
            if ae and hasattr(ae, "rebuild_fx_maps"):
                ctx = getattr(ps, "ctx", None) if ps else None
                proj = getattr(ctx, "project", None) if ctx else None
                if proj:
                    ae.rebuild_fx_maps(proj)
        except Exception:
            pass

    def _save_to_project(self):
        pass  # Override in subclass

    def _sync_all_params_to_rt(self):
        """Push ALLE params aus dem Projekt-dict in den RT-Store.
        
        Wird nach jedem _save_to_project automatisch aufgerufen,
        damit die DSP-Prozessoren die aktuellen Werte lesen können."""
        p = self._params()
        if not p:
            return
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae else None
        if rt is None:
            return
        prefix = f"afx:{self._track_id}:{self._device_id}"
        try:
            for key, val in p.items():
                if isinstance(val, (int, float)):
                    rt.set_param(f"{prefix}:{key}", float(val))
        except Exception:
            pass

    # ──── Automation Manager Access ────

    def _get_automation_manager(self):
        return getattr(self._services, "automation_manager", None) if self._services else None

    # ──── Automation Right-Click for any widget ────

    def _install_automation_menu(self, widget: QWidget, param_name: str):
        """Installiert Rechtsklick-Kontextmenü mit 'Show Automation in Arranger' auf einem Widget."""
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        param_id = f"afx:{self._track_id}:{self._device_id}:{param_name}"
        widget.customContextMenuRequested.connect(
            lambda pos, pid=param_id, w=widget: self._show_param_automation_menu(w, pos, pid))

    def _show_param_automation_menu(self, widget: QWidget, pos, param_id: str):
        """v0.0.20.568: Unified context menu — Show Automation + MIDI Learn + Reset."""
        am = self._get_automation_manager()
        menu = QMenu(self)

        # Show Automation
        a_show = menu.addAction("Show Automation in Arranger")
        if am is None or not param_id:
            a_show.setEnabled(False)

        menu.addSeparator()

        # MIDI Learn
        a_midi_learn = None
        a_midi_remove = None
        cc_info = getattr(widget, '_midi_cc_mapping', None)
        if cc_info is not None:
            ch_show, cc_show = cc_info
            menu.addAction(f'🎹 Mapped: CC{cc_show} ch{ch_show}').setEnabled(False)
            a_midi_remove = menu.addAction('🎹 MIDI Mapping entfernen')
        else:
            a_midi_learn = menu.addAction('🎹 MIDI Learn')
            if am is None:
                a_midi_learn.setEnabled(False)

        menu.addSeparator()
        a_mod = menu.addAction("Add Modulator (LFO/ENV) — coming soon")
        a_mod.setEnabled(False)
        menu.addSeparator()
        a_reset = menu.addAction("Reset to Default")

        try:
            chosen = menu.exec(widget.mapToGlobal(pos))
        except Exception:
            return
        if chosen is None:
            return
        if chosen == a_show and am is not None:
            self._request_show_automation(param_id)
        elif chosen == a_reset:
            self._reset_param(param_id)
        elif chosen == a_midi_learn and am is not None:
            self._start_midi_learn(widget, param_id, am)
        elif chosen == a_midi_remove:
            self._remove_midi_mapping(widget, am)

    def _start_midi_learn(self, widget: QWidget, param_id: str, am) -> None:
        """v0.0.20.568: Start MIDI Learn for a widget — same flow as CompactKnob."""
        try:
            # Cancel any previous learn
            try:
                midi_svc = getattr(self._services, "midi", None) if self._services else None
                if midi_svc is not None and hasattr(midi_svc, "cancel_learn"):
                    midi_svc.cancel_learn()
            except Exception:
                pass
            widget._pydaw_param_id = str(param_id)
            am._midi_learn_knob = widget
            try:
                widget.setStyleSheet('border: 2px solid #ff6060;')
            except Exception:
                pass
            try:
                from PyQt6.QtWidgets import QApplication
                for w in QApplication.topLevelWidgets():
                    sb = getattr(w, 'statusBar', None)
                    if callable(sb):
                        sb().showMessage('MIDI Learn aktiv: bewege jetzt einen CC-Regler am Controller.', 10000)
                        break
            except Exception:
                pass
        except Exception:
            pass

    def _remove_midi_mapping(self, widget: QWidget, am) -> None:
        """v0.0.20.568: Remove MIDI CC mapping from a widget."""
        cc_map = getattr(widget, '_midi_cc_mapping', None)
        if cc_map is not None:
            try:
                ch, cc = cc_map
                fast_map = getattr(am, '_cc_fast_map', None)
                if isinstance(fast_map, dict):
                    fast_map.pop((ch, cc), None)
            except Exception:
                pass
            widget._midi_cc_mapping = None
            try:
                widget.setStyleSheet('')
            except Exception:
                pass

    def _request_show_automation(self, param_id: str):
        am = self._get_automation_manager()
        if am and hasattr(am, "request_show_automation"):
            try:
                am.request_show_automation.emit(param_id)
            except Exception:
                pass

    def _reset_param(self, param_id: str):
        am = self._get_automation_manager()
        if am is None:
            return
        try:
            param = am.get_parameter(param_id)
            if param:
                param.set_value(param.default_val)
                param.set_automation_value(None)
        except Exception:
            pass

    # ──── UI Helpers ────

    def _knob(self, label: str, lo: int = 0, hi: int = 100, val: int = 50,
              size: int = 46, param_name: str = ""):
        """Erstelle Knob (QDial) + Labels + Rechtsklick-Automation.
        
        Gibt (dial, lbl_value, layout) zurück.
        Wenn param_name gesetzt: Rechtsklick → Show Automation."""
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        dial = QDial()
        dial.setNotchesVisible(True)
        dial.setRange(lo, hi)
        dial.setValue(val)
        dial.setFixedSize(size, size)
        lv = QLabel(str(val))
        lv.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lv.setStyleSheet("font-size:10px; color:#e0e0e0;")
        ln = QLabel(label)
        ln.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ln.setStyleSheet("font-size:10px; color:#999;")
        col.addWidget(dial, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(lv, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(ln, 0, Qt.AlignmentFlag.AlignHCenter)
        # Automation-Rechtsklick installieren
        pn = param_name or label.lower().replace(" ", "_").replace(".", "")
        self._install_automation_menu(dial, pn)
        return dial, lv, col


# ═══════════════════════════════════════════════════════════
#  1.  EQ-5  —  5-Band Parametric EQ
# ═══════════════════════════════════════════════════════════

class EQ5FxWidget(_AudioFxBase):
    """5-Band Parametric EQ (Bitwig EQ-5 style).
    
    Bild: 5 farbige Bänder (rot/gelb/grün/blau/lila), je Gain/Freq/Q.
    Global: Amount + Shift + Output."""

    _COLORS = ["#e04040", "#e0c040", "#40c840", "#4080e0", "#c040e0"]
    _FREQ_DEFAULTS = [80.0, 400.0, 1310.0, 3600.0, 12000.0]

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._bands = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        grid = QGridLayout()
        grid.setSpacing(3)

        # Band number headers
        for i in range(5):
            lbl = QLabel(f"  {i+1}  ")
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setStyleSheet(f"color:{self._COLORS[i]}; font-weight:bold;")
            grid.addWidget(lbl, 0, i)

        # Gain dials (row 1)
        for i in range(5):
            d, lv, c = self._knob("dB", -240, 240, 0, 34)
            grid.addLayout(c, 1, i)
            self._bands.append({"g_dial": d, "g_lbl": lv})
            d.valueChanged.connect(
                lambda v, idx=i, l=lv: (
                    l.setText(f"{v/10:.1f}"),
                    self._rt_set(f"b{idx}_g", v / 10.0),
                    self._schedule_save()))

        # Freq spinboxes (row 2)
        for i in range(5):
            spn = QDoubleSpinBox()
            spn.setRange(20, 20000)
            spn.setValue(self._FREQ_DEFAULTS[i])
            spn.setSuffix(" Hz")
            spn.setDecimals(0)
            spn.setMaximumWidth(76)
            spn.setStyleSheet(f"color:{self._COLORS[i]};")
            grid.addWidget(spn, 2, i)
            self._bands[i]["f_spn"] = spn
            spn.valueChanged.connect(lambda _: self._schedule_save())

        # Q spinboxes (row 3)
        for i in range(5):
            spn = QDoubleSpinBox()
            spn.setRange(0.10, 18.0)
            spn.setValue(0.71)
            spn.setDecimals(2)
            spn.setMaximumWidth(64)
            grid.addWidget(spn, 3, i)
            self._bands[i]["q_spn"] = spn
            spn.valueChanged.connect(lambda _: self._schedule_save())

        root.addLayout(grid)

        # Global: Amount, Shift, Output
        gbl = QHBoxLayout()
        gbl.setSpacing(6)
        gbl.addStretch(1)
        for name, lo, hi, val in [("Amount", 0, 100, 100), ("Shift", -100, 100, 0), ("Output", -240, 120, 0)]:
            d, lv, c = self._knob(name, lo, hi, val, 36)
            gbl.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            d.valueChanged.connect(lambda v, l=lv: (l.setText(str(v)), self._schedule_save()))
        root.addLayout(gbl)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            for i in range(5):
                b = self._bands[i]
                b["g_dial"].setValue(int(p.get(f"b{i}_g10", 0)))
                b["f_spn"].setValue(float(p.get(f"b{i}_f", self._FREQ_DEFAULTS[i])))
                b["q_spn"].setValue(float(p.get(f"b{i}_q", 0.71)))
            self.d_amount.setValue(int(p.get("amount", 100)))
            self.d_shift.setValue(int(p.get("shift", 0)))
            self.d_output.setValue(int(p.get("output10", 0)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        for i in range(5):
            b = self._bands[i]
            p[f"b{i}_g10"] = b["g_dial"].value()
            p[f"b{i}_f"] = b["f_spn"].value()
            p[f"b{i}_q"] = b["q_spn"].value()
        p["amount"] = self.d_amount.value()
        p["shift"] = self.d_shift.value()
        p["output10"] = self.d_output.value()
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  2.  DELAY-2  —  Stereo Delay
# ═══════════════════════════════════════════════════════════

class Delay2FxWidget(_AudioFxBase):
    """Stereo Delay (Bitwig DELAY-2 style).
    
    Bild: LEFT/RIGHT Sektionen mit Source, Sync-Grid, Time,
    Crossfeed + Feedback.  Rechts: Detune, Rate, Width, Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # L / R sections
        lr = QHBoxLayout()
        for ch in ("L", "R"):
            g = QGroupBox(ch)
            gl = QVBoxLayout(g)
            gl.setSpacing(3)
            spn_t = QDoubleSpinBox()
            spn_t.setRange(0.001, 4.0)
            spn_t.setValue(1.0)
            spn_t.setSuffix(" s")
            spn_t.setDecimals(3)
            gl.addWidget(spn_t)
            setattr(self, f"t_{ch}", spn_t)

            hr = QHBoxLayout()
            d_fb, _, c_fb = self._knob("Feedback", 0, 100, 30, 32)
            d_cf, _, c_cf = self._knob("Crossfeed", 0, 100, 0, 32)
            hr.addLayout(c_fb)
            hr.addLayout(c_cf)
            gl.addLayout(hr)
            setattr(self, f"fb_{ch}", d_fb)
            setattr(self, f"cf_{ch}", d_cf)
            lr.addWidget(g)
        root.addLayout(lr)

        # Detune / Rate / Width / Mix
        bot = QHBoxLayout()
        bot.setSpacing(6)
        for name, lo, hi, val in [("Detune", 0, 100, 0), ("Rate", 0, 100, 50),
                                   ("Width", 0, 100, 50), ("Mix", 0, 100, 30)]:
            d, lv, c = self._knob(name, lo, hi, val, 38)
            bot.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            d.valueChanged.connect(lambda v, l=lv, n=name.lower(): (
                l.setText(f"{v}%"), self._rt_set(n, v/100), self._schedule_save()))
        root.addLayout(bot)

        for w_name in ("t_L", "t_R", "fb_L", "fb_R", "cf_L", "cf_R"):
            getattr(self, w_name).valueChanged.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.t_L.setValue(float(p.get("time_l", 1.0)))
            self.t_R.setValue(float(p.get("time_r", 1.0)))
            self.fb_L.setValue(int(p.get("fb_l", 30)))
            self.fb_R.setValue(int(p.get("fb_r", 30)))
            self.cf_L.setValue(int(p.get("cf_l", 0)))
            self.cf_R.setValue(int(p.get("cf_r", 0)))
            self.d_detune.setValue(int(p.get("detune", 0)))
            self.d_rate.setValue(int(p.get("rate", 50)))
            self.d_width.setValue(int(p.get("width", 50)))
            self.d_mix.setValue(int(p.get("mix", 30)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(time_l=self.t_L.value(), time_r=self.t_R.value(),
                 fb_l=self.fb_L.value(), fb_r=self.fb_R.value(),
                 cf_l=self.cf_L.value(), cf_r=self.cf_R.value(),
                 detune=self.d_detune.value(), rate=self.d_rate.value(),
                 width=self.d_width.value(), mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  3.  REVERB
# ═══════════════════════════════════════════════════════════

class ReverbFxWidget(_AudioFxBase):
    """Reverb (Bitwig REVERB style).
    
    Bild: Early (Room/Hall), Size, Pre-delay.
    Knobs: Diffusion, Buildup, Decay, Late Mix.
    Rechts: Tank FX, Wet FX, Width, Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Top: Early / Size / Pre-delay
        top = QHBoxLayout()
        ev = QVBoxLayout()
        ev.addWidget(QLabel("Early"))
        self.cmb_early = QComboBox()
        self.cmb_early.addItems(["Room", "Hall"])
        ev.addWidget(self.cmb_early)
        top.addLayout(ev)

        for name, lo, hi, val, suf in [("Size", 1, 1000, 993, " %"), ("Pre-delay", 0, 2000, 40, " ms")]:
            sv = QVBoxLayout()
            sv.addWidget(QLabel(name))
            spn = QDoubleSpinBox()
            spn.setRange(lo/10.0, hi/10.0)
            spn.setValue(val/10.0)
            spn.setSuffix(suf)
            spn.setDecimals(1)
            sv.addWidget(spn)
            top.addLayout(sv)
            setattr(self, f"spn_{name.lower().replace('-','')}", spn)
            spn.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(top)

        # Main knobs
        kr = QHBoxLayout()
        kr.setSpacing(4)
        for name, lo, hi, val in [("Diffusion", 0, 100, 50), ("Buildup", 0, 100, 73),
                                   ("Decay", 1, 500, 126), ("Late Mix", 0, 100, 72)]:
            d, lv, c = self._knob(name, lo, hi, val, 42)
            kr.addLayout(c)
            setattr(self, f"d_{name.lower().replace(' ','_')}", d)
            if name == "Decay":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v/100:.2f}s"), self._schedule_save()))
            else:
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}%"), self._schedule_save()))
        root.addLayout(kr)

        # Width + Mix
        bot = QHBoxLayout()
        bot.addStretch(1)
        for name, val in [("Width", 50), ("Mix", 50)]:
            d, lv, c = self._knob(name, 0, 100, val, 40)
            bot.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            d.valueChanged.connect(lambda v, l=lv, n=name.lower(): (
                l.setText(f"{v}%"), self._rt_set(n, v/100), self._schedule_save()))
        root.addLayout(bot)

        self.cmb_early.currentIndexChanged.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.cmb_early.setCurrentText(str(p.get("early", "Room")))
            self.spn_size.setValue(float(p.get("size", 99.3)))
            self.spn_predelay.setValue(float(p.get("predelay", 4.0)))
            self.d_diffusion.setValue(int(p.get("diffusion", 50)))
            self.d_buildup.setValue(int(p.get("buildup", 73)))
            self.d_decay.setValue(int(p.get("decay", 126)))
            self.d_late_mix.setValue(int(p.get("late_mix", 72)))
            self.d_width.setValue(int(p.get("width", 50)))
            self.d_mix.setValue(int(p.get("mix", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(early=self.cmb_early.currentText(), size=self.spn_size.value(),
                 predelay=self.spn_predelay.value(), diffusion=self.d_diffusion.value(),
                 buildup=self.d_buildup.value(), decay=self.d_decay.value(),
                 late_mix=self.d_late_mix.value(), width=self.d_width.value(),
                 mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  4.  COMB  —  Kammfilter
# ═══════════════════════════════════════════════════════════

class CombFxWidget(_AudioFxBase):
    """Comb Filter (Bitwig COMB style).
    
    Bild: Freq (267 Hz), Feedback, Mix.  Oben: kleines Frequenzdiagramm."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(10)
        for name, lo, hi, val, fmt in [("Freq", 20, 2000, 267, "{} Hz"),
                                        ("Feedback", -100, 100, 0, "{}%"),
                                        ("Mix", 0, 100, 50, "{}%")]:
            d, lv, c = self._knob(name, lo, hi, val, 48)
            root.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            d.valueChanged.connect(lambda v, l=lv, f=fmt, n=name.lower(): (
                l.setText(f.format(v)), self._rt_set(n, v/(100 if n != "freq" else 1)),
                self._schedule_save()))
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_freq.setValue(int(p.get("freq", 267)))
            self.d_feedback.setValue(int(p.get("feedback", 0)))
            self.d_mix.setValue(int(p.get("mix", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(freq=self.d_freq.value(), feedback=self.d_feedback.value(),
                 mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  5.  COMPRESSOR
# ═══════════════════════════════════════════════════════════

class CompressorFxWidget(_AudioFxBase):
    """Compressor (Bitwig COMPRESSOR style).
    
    Bild: Metering + Makeup Toggle.
    Knobs: Input, Thresh, Ratio, Attack, Release, Output."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.chk_makeup = QCheckBox("Makeup")
        root.addWidget(self.chk_makeup)
        self.chk_makeup.toggled.connect(lambda _: self._schedule_save())

        kr = QHBoxLayout()
        kr.setSpacing(4)
        for name, lo, hi, val in [("Input", -240, 240, 0), ("Thresh", -600, 0, -200),
                                   ("Ratio", 10, 200, 40), ("Attack", 1, 500, 10),
                                   ("Release", 10, 2000, 200), ("Output", -240, 240, 0)]:
            d, lv, c = self._knob(name, lo, hi, val, 38)
            kr.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            if name in ("Input", "Thresh", "Output"):
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v/10:.1f}dB"), self._schedule_save()))
            elif name == "Ratio":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v/10:.1f}:1"), self._schedule_save()))
            elif name == "Attack":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}ms"), self._schedule_save()))
            else:
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}ms"), self._schedule_save()))
        root.addLayout(kr)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_input.setValue(int(p.get("input", 0)))
            self.d_thresh.setValue(int(p.get("thresh", -200)))
            self.d_ratio.setValue(int(p.get("ratio", 40)))
            self.d_attack.setValue(int(p.get("attack", 10)))
            self.d_release.setValue(int(p.get("release", 200)))
            self.d_output.setValue(int(p.get("output", 0)))
            self.chk_makeup.setChecked(bool(p.get("makeup", False)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(input=self.d_input.value(), thresh=self.d_thresh.value(),
                 ratio=self.d_ratio.value(), attack=self.d_attack.value(),
                 release=self.d_release.value(), output=self.d_output.value(),
                 makeup=self.chk_makeup.isChecked())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  6.  FILTER+  —  Drive + Filter + LFO
# ═══════════════════════════════════════════════════════════

class FilterPlusFxWidget(_AudioFxBase):
    """Filter+ (Bitwig FILTER+ style).
    
    Bild: Heat / Drive, Filter Type (Low-pass MG etc.), Freq, Res.
    LFO: Shape, Rate.  Routing: Pre/Post FX.  Mix."""

    _FTYPES = ["Low-pass", "High-pass", "Band-pass", "Notch",
               "Low-pass MG", "High-pass MG"]
    _SHAPES = ["Sine", "Triangle", "Square", "Saw", "S&H"]

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Drive + Filter type
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Drive"))
        self.spn_drv = QDoubleSpinBox()
        self.spn_drv.setRange(-12, 36)
        self.spn_drv.setValue(8.0)
        self.spn_drv.setSuffix(" dB")
        r1.addWidget(self.spn_drv)
        self.cmb_ft = QComboBox()
        self.cmb_ft.addItems(self._FTYPES)
        self.cmb_ft.setCurrentText("Low-pass MG")
        r1.addWidget(self.cmb_ft)
        root.addLayout(r1)

        # Freq + Res
        r2 = QHBoxLayout()
        d_f, lv_f, c_f = self._knob("Freq", 20, 20000, 1050, 48)
        d_r, lv_r, c_r = self._knob("Resonance", 0, 100, 25, 48)
        self.d_freq, self.d_res = d_f, d_r
        d_f.valueChanged.connect(lambda v, l=lv_f: (l.setText(f"{v}Hz"), self._schedule_save()))
        d_r.valueChanged.connect(lambda v, l=lv_r: (l.setText(f"{v}%"), self._schedule_save()))
        r2.addLayout(c_f)
        r2.addLayout(c_r)
        root.addLayout(r2)

        # LFO
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("LFO"))
        self.cmb_lfo = QComboBox()
        self.cmb_lfo.addItems(self._SHAPES)
        r3.addWidget(self.cmb_lfo)
        self.spn_rate = QDoubleSpinBox()
        self.spn_rate.setRange(0.01, 50)
        self.spn_rate.setValue(1.0)
        self.spn_rate.setSuffix(" Hz")
        r3.addWidget(self.spn_rate)
        root.addLayout(r3)

        # Pre/Post + Mix
        r4 = QHBoxLayout()
        self.cmb_route = QComboBox()
        self.cmb_route.addItems(["Pre FX", "Post FX"])
        r4.addWidget(self.cmb_route)
        d_m, lv_m, c_m = self._knob("Mix", 0, 100, 100, 42)
        self.d_mix = d_m
        d_m.valueChanged.connect(lambda v, l=lv_m: (
            l.setText(f"{v}%"), self._rt_set("mix", v/100), self._schedule_save()))
        r4.addLayout(c_m)
        root.addLayout(r4)

        for w in (self.spn_drv, self.spn_rate):
            w.valueChanged.connect(lambda _: self._schedule_save())
        for w in (self.cmb_ft, self.cmb_lfo, self.cmb_route):
            w.currentIndexChanged.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.spn_drv.setValue(float(p.get("drive_db", 8.0)))
            self.cmb_ft.setCurrentText(str(p.get("filter_type", "Low-pass MG")))
            self.d_freq.setValue(int(p.get("freq", 1050)))
            self.d_res.setValue(int(p.get("res", 25)))
            self.cmb_lfo.setCurrentText(str(p.get("lfo_shape", "Sine")))
            self.spn_rate.setValue(float(p.get("lfo_rate", 1.0)))
            self.cmb_route.setCurrentText(str(p.get("routing", "Pre FX")))
            self.d_mix.setValue(int(p.get("mix", 100)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(drive_db=self.spn_drv.value(), filter_type=self.cmb_ft.currentText(),
                 freq=self.d_freq.value(), res=self.d_res.value(),
                 lfo_shape=self.cmb_lfo.currentText(), lfo_rate=self.spn_rate.value(),
                 routing=self.cmb_route.currentText(), mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  7.  DISTORTION+  —  Erweiterter Verzerrer
# ═══════════════════════════════════════════════════════════

class DistortionPlusFxWidget(_AudioFxBase):
    """Distortion+ (Bitwig DISTORTION style).
    
    Bild: Pre EQ (Freq/Gain/Q), Post Cuts (Lo/Hi).
    Knobs: Drive, Symmetry, DC, Slew.
    Rechts: Wet FX, Width, Wet Gain, Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Drive / Symm / DC / Slew
        r1 = QHBoxLayout()
        r1.setSpacing(4)
        for name, lo, hi, val in [("Drive", 0, 100, 25), ("Symm.", -100, 100, 0),
                                   ("DC", -100, 100, 0), ("Slew", 0, 100, 100)]:
            d, lv, c = self._knob(name, lo, hi, val, 40)
            r1.addLayout(c)
            setattr(self, f"d_{name.lower().replace('.','')}", d)
            d.valueChanged.connect(lambda v, l=lv: (l.setText(str(v)), self._schedule_save()))
        root.addLayout(r1)

        # Pre EQ
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Pre EQ"))
        for name, lo, hi, val, suf in [("Freq", 20, 20000, 932, " Hz"),
                                         ("Gain", -24, 24, 16.7, " dB"),
                                         ("Q", 0.1, 18, 1.48, "")]:
            spn = QDoubleSpinBox()
            spn.setRange(lo, hi)
            spn.setValue(val)
            spn.setSuffix(suf)
            spn.setDecimals(1 if name != "Q" else 2)
            spn.setMaximumWidth(80)
            r2.addWidget(spn)
            setattr(self, f"pre_{name.lower()}", spn)
            spn.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(r2)

        # Post Cuts
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Post Cuts"))
        for name, lo, hi, val, suf in [("Lo", 20, 5000, 233, " Hz"),
                                         ("Hi", 500, 20000, 5340, " Hz")]:
            spn = QDoubleSpinBox()
            spn.setRange(lo, hi)
            spn.setValue(val)
            spn.setSuffix(suf)
            spn.setDecimals(0)
            spn.setMaximumWidth(88)
            r3.addWidget(spn)
            setattr(self, f"post_{name.lower()}", spn)
            spn.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(r3)

        # Width / Wet Gain / Mix
        r4 = QHBoxLayout()
        r4.setSpacing(6)
        for name, lo, hi, val in [("Width", 0, 100, 50), ("Wet Gain", 0, 200, 100), ("Mix", 0, 100, 100)]:
            d, lv, c = self._knob(name, lo, hi, val, 38)
            r4.addLayout(c)
            setattr(self, f"d_{name.lower().replace(' ','_')}", d)
            d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}%"), self._schedule_save()))
        root.addLayout(r4)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_drive.setValue(int(p.get("drive", 25)))
            self.d_symm.setValue(int(p.get("symm", 0)))
            self.d_dc.setValue(int(p.get("dc", 0)))
            self.d_slew.setValue(int(p.get("slew", 100)))
            self.pre_freq.setValue(float(p.get("pre_f", 932)))
            self.pre_gain.setValue(float(p.get("pre_g", 16.7)))
            self.pre_q.setValue(float(p.get("pre_q", 1.48)))
            self.post_lo.setValue(float(p.get("post_lo", 233)))
            self.post_hi.setValue(float(p.get("post_hi", 5340)))
            self.d_width.setValue(int(p.get("width", 50)))
            self.d_wet_gain.setValue(int(p.get("wet_gain", 100)))
            self.d_mix.setValue(int(p.get("mix", 100)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(drive=self.d_drive.value(), symm=self.d_symm.value(),
                 dc=self.d_dc.value(), slew=self.d_slew.value(),
                 pre_f=self.pre_freq.value(), pre_g=self.pre_gain.value(),
                 pre_q=self.pre_q.value(), post_lo=self.post_lo.value(),
                 post_hi=self.post_hi.value(), width=self.d_width.value(),
                 wet_gain=self.d_wet_gain.value(), mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  8.  DYNAMICS  —  Kompressor/Gate Hybrid
# ═══════════════════════════════════════════════════════════

class DynamicsFxWidget(_AudioFxBase):
    """Dynamics (Bitwig DYNAMICS style).
    
    Bild: Transfer-Kurve, Peak/RMS toggle.
    Ratio+Knee (Hi + Lo), Lo/Hi Threshold, Attack, Release, Output.
    Sidechain Input."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Peak/RMS
        det = QHBoxLayout()
        self.btn_peak = QPushButton("Peak")
        self.btn_peak.setCheckable(True)
        self.btn_peak.setChecked(True)
        self.btn_rms = QPushButton("RMS")
        self.btn_rms.setCheckable(True)
        det.addWidget(self.btn_peak)
        det.addWidget(self.btn_rms)
        det.addStretch(1)
        root.addLayout(det)
        self.btn_peak.clicked.connect(lambda: (self.btn_rms.setChecked(False), self.btn_peak.setChecked(True), self._schedule_save()))
        self.btn_rms.clicked.connect(lambda: (self.btn_peak.setChecked(False), self.btn_rms.setChecked(True), self._schedule_save()))

        # Hi: Ratio + Knee  |  Lo: Ratio + Knee
        r1 = QHBoxLayout()
        r1.setSpacing(3)
        for prefix, label in [("hi", "Hi"), ("lo", "Lo")]:
            for name, lo, hi, val in [(f"Ratio", 10, 200, 10), (f"Knee", 0, 100, 50)]:
                d, lv, c = self._knob(f"{label} {name}", lo, hi, val, 32)
                r1.addLayout(c)
                setattr(self, f"d_{prefix}_{name.lower()}", d)
                d.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(r1)

        # Thresh + Timing + Output
        r2 = QHBoxLayout()
        r2.setSpacing(3)
        for name, lo, hi, val in [("Lo Thresh", -600, 0, -400), ("Hi Thresh", -600, 0, -100),
                                   ("Attack", 1, 500, 10), ("Release", 10, 2000, 200),
                                   ("Output", -240, 240, 0)]:
            d, lv, c = self._knob(name, lo, hi, val, 32)
            r2.addLayout(c)
            setattr(self, f"d_{name.lower().replace(' ','_')}", d)
            d.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(r2)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.btn_peak.setChecked(p.get("mode", "peak") == "peak")
            self.btn_rms.setChecked(p.get("mode", "peak") == "rms")
            self.d_hi_ratio.setValue(int(p.get("hi_ratio", 10)))
            self.d_hi_knee.setValue(int(p.get("hi_knee", 50)))
            self.d_lo_ratio.setValue(int(p.get("lo_ratio", 10)))
            self.d_lo_knee.setValue(int(p.get("lo_knee", 50)))
            self.d_lo_thresh.setValue(int(p.get("lo_thresh", -400)))
            self.d_hi_thresh.setValue(int(p.get("hi_thresh", -100)))
            self.d_attack.setValue(int(p.get("attack", 10)))
            self.d_release.setValue(int(p.get("release", 200)))
            self.d_output.setValue(int(p.get("output", 0)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(mode="rms" if self.btn_rms.isChecked() else "peak",
                 hi_ratio=self.d_hi_ratio.value(), hi_knee=self.d_hi_knee.value(),
                 lo_ratio=self.d_lo_ratio.value(), lo_knee=self.d_lo_knee.value(),
                 lo_thresh=self.d_lo_thresh.value(), hi_thresh=self.d_hi_thresh.value(),
                 attack=self.d_attack.value(), release=self.d_release.value(),
                 output=self.d_output.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  9.  FLANGER
# ═══════════════════════════════════════════════════════════

class FlangerFxWidget(_AudioFxBase):
    """Flanger (Bitwig FLANGER style).
    
    Bild: LFO Wellenform + Rate, Wet FX, Wide toggle.
    Knobs: Time, Feedback, Width, Mix."""

    _SHAPES = ["Sine", "Triangle", "Square", "Saw", "S&H"]

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        r1 = QHBoxLayout()
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems(self._SHAPES)
        r1.addWidget(self.cmb_shape)
        self.spn_rate = QDoubleSpinBox()
        self.spn_rate.setRange(0.01, 20)
        self.spn_rate.setValue(0.44)
        self.spn_rate.setSuffix(" Hz")
        r1.addWidget(self.spn_rate)
        self.chk_wide = QCheckBox("Wide")
        r1.addWidget(self.chk_wide)
        root.addLayout(r1)

        kr = QHBoxLayout()
        kr.setSpacing(6)
        for name, lo, hi, val in [("Time", 1, 100, 50), ("Feedback", -100, 100, 0),
                                   ("Width", 0, 100, 50), ("Mix", 0, 100, 50)]:
            d, lv, c = self._knob(name, lo, hi, val, 42)
            kr.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            d.valueChanged.connect(lambda v, l=lv: (l.setText(str(v)), self._schedule_save()))
        root.addLayout(kr)

        self.cmb_shape.currentIndexChanged.connect(lambda _: self._schedule_save())
        self.spn_rate.valueChanged.connect(lambda _: self._schedule_save())
        self.chk_wide.toggled.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.cmb_shape.setCurrentText(str(p.get("shape", "Sine")))
            self.spn_rate.setValue(float(p.get("rate", 0.44)))
            self.chk_wide.setChecked(bool(p.get("wide", False)))
            self.d_time.setValue(int(p.get("time", 50)))
            self.d_feedback.setValue(int(p.get("feedback", 0)))
            self.d_width.setValue(int(p.get("width", 50)))
            self.d_mix.setValue(int(p.get("mix", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(shape=self.cmb_shape.currentText(), rate=self.spn_rate.value(),
                 wide=self.chk_wide.isChecked(), time=self.d_time.value(),
                 feedback=self.d_feedback.value(), width=self.d_width.value(),
                 mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  10. PITCH SHIFTER
# ═══════════════════════════════════════════════════════════

class PitchShifterFxWidget(_AudioFxBase):
    """Pitch Shifter (Bitwig PITCH SHIFTER style).
    
    Bild: Grain Knob, Semitone Slider (0.00 st), Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(10)

        d_g, lv_g, c_g = self._knob("Grain", 1, 100, 50, 48)
        self.d_grain = d_g
        d_g.valueChanged.connect(lambda v, l=lv_g: (l.setText(str(v)), self._schedule_save()))
        root.addLayout(c_g)

        sv = QVBoxLayout()
        sv.addWidget(QLabel("Pitch"))
        self.spn_st = QDoubleSpinBox()
        self.spn_st.setRange(-24, 24)
        self.spn_st.setValue(0)
        self.spn_st.setSingleStep(0.01)
        self.spn_st.setSuffix(" st")
        self.spn_st.setDecimals(2)
        sv.addWidget(self.spn_st)
        self.spn_st.valueChanged.connect(lambda _: self._schedule_save())
        root.addLayout(sv)

        d_m, lv_m, c_m = self._knob("Mix", 0, 100, 100, 48)
        self.d_mix = d_m
        d_m.valueChanged.connect(lambda v, l=lv_m: (
            l.setText(f"{v}%"), self._rt_set("mix", v/100), self._schedule_save()))
        root.addLayout(c_m)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_grain.setValue(int(p.get("grain", 50)))
            self.spn_st.setValue(float(p.get("semi", 0)))
            self.d_mix.setValue(int(p.get("mix", 100)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(grain=self.d_grain.value(), semi=self.spn_st.value(),
                 mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  11. TREMOLO
# ═══════════════════════════════════════════════════════════

class TremoloFxWidget(_AudioFxBase):
    """Tremolo (Bitwig TREMOLO style).
    
    Bild: Rate Knob, 6 LFO Wellenformen (Symbole), Depth Knob."""

    _WAVES = ["Sine", "Triangle", "Square", "Saw Up", "Saw Down", "S&H"]

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(8)

        d_r, lv_r, c_r = self._knob("Rate", 1, 2000, 316, 48)
        self.d_rate = d_r
        d_r.valueChanged.connect(lambda v, l=lv_r: (l.setText(f"{v/100:.2f}Hz"), self._schedule_save()))
        root.addLayout(c_r)

        wv = QVBoxLayout()
        wv.addWidget(QLabel("Shape"))
        self.cmb_wave = QComboBox()
        self.cmb_wave.addItems(self._WAVES)
        wv.addWidget(self.cmb_wave)
        self.cmb_wave.currentIndexChanged.connect(lambda _: self._schedule_save())
        root.addLayout(wv)

        d_d, lv_d, c_d = self._knob("Depth", 0, 100, 50, 48)
        self.d_depth = d_d
        d_d.valueChanged.connect(lambda v, l=lv_d: (
            l.setText(f"{v}%"), self._rt_set("depth", v/100), self._schedule_save()))
        root.addLayout(c_d)
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_rate.setValue(int(p.get("rate", 316)))
            self.cmb_wave.setCurrentText(str(p.get("wave", "Sine")))
            self.d_depth.setValue(int(p.get("depth", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(rate=self.d_rate.value(), wave=self.cmb_wave.currentText(),
                 depth=self.d_depth.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  12. PEAK LIMITER
# ═══════════════════════════════════════════════════════════

class PeakLimiterFxWidget(_AudioFxBase):
    """Peak Limiter (Bitwig PEAK LIMITER style).
    
    Bild: Meter, Input Knob, Release Knob, Ceiling Knob."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(10)
        for name, lo, hi, val, unit in [("Input", -120, 240, 0, "dB"),
                                         ("Release", 10, 2000, 300, "ms"),
                                         ("Ceiling", -240, 0, 0, "dB")]:
            d, lv, c = self._knob(name, lo, hi, val, 48)
            root.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            if unit == "dB":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v/10:.1f}dB"), self._schedule_save()))
            else:
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}ms"), self._schedule_save()))
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.d_input.setValue(int(p.get("input", 0)))
            self.d_release.setValue(int(p.get("release", 300)))
            self.d_ceiling.setValue(int(p.get("ceiling", 0)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(input=self.d_input.value(), release=self.d_release.value(),
                 ceiling=self.d_ceiling.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  13. CHORUS
# ═══════════════════════════════════════════════════════════

class ChorusFxWidget(_AudioFxBase):
    """Chorus (Bitwig CHORUS style).
    
    Bild: Delay Time, Wet FX / Wide toggle.
    Knobs: Rate, Phase, Width (∞), Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Delay"))
        self.spn_delay = QDoubleSpinBox()
        self.spn_delay.setRange(0.1, 50)
        self.spn_delay.setValue(14.5)
        self.spn_delay.setSuffix(" ms")
        r1.addWidget(self.spn_delay)
        self.chk_wide = QCheckBox("Wide")
        r1.addWidget(self.chk_wide)
        root.addLayout(r1)

        kr = QHBoxLayout()
        kr.setSpacing(6)
        for name, lo, hi, val in [("Rate", 1, 1000, 31), ("Phase", 0, 360, 160),
                                   ("Width", 0, 100, 50), ("Mix", 0, 100, 50)]:
            d, lv, c = self._knob(name, lo, hi, val, 42)
            kr.addLayout(c)
            setattr(self, f"d_{name.lower()}", d)
            if name == "Rate":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v/100:.2f}Hz"), self._schedule_save()))
            elif name == "Phase":
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}°"), self._schedule_save()))
            else:
                d.valueChanged.connect(lambda v, l=lv: (l.setText(f"{v}%"), self._schedule_save()))
        root.addLayout(kr)

        self.spn_delay.valueChanged.connect(lambda _: self._schedule_save())
        self.chk_wide.toggled.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.spn_delay.setValue(float(p.get("delay", 14.5)))
            self.chk_wide.setChecked(bool(p.get("wide", False)))
            self.d_rate.setValue(int(p.get("rate", 31)))
            self.d_phase.setValue(int(p.get("phase", 160)))
            self.d_width.setValue(int(p.get("width", 50)))
            self.d_mix.setValue(int(p.get("mix", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(delay=self.spn_delay.value(), wide=self.chk_wide.isChecked(),
                 rate=self.d_rate.value(), phase=self.d_phase.value(),
                 width=self.d_width.value(), mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  14. XY FX  —  XY-Pad Effekt-Controller
# ═══════════════════════════════════════════════════════════

class XYFxWidget(_AudioFxBase):
    """XY FX (Bitwig XY FX style).
    
    Bild: XY Pad mit 4 Ecken (A/B/C/D), Post FX.
    Knobs: X, Y, Wet Gain, Mix."""

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        root.addWidget(QLabel("XY FX — Morph zwischen 4 Effekt-Slots"))

        r1 = QHBoxLayout()
        self.cmb_route = QComboBox()
        self.cmb_route.addItems(["Pre FX", "Post FX"])
        r1.addWidget(self.cmb_route)
        r1.addStretch(1)
        root.addLayout(r1)

        kr = QHBoxLayout()
        kr.setSpacing(8)
        for name, lo, hi, val in [("X", 0, 100, 50), ("Y", 0, 100, 50),
                                   ("Wet Gain", 0, 200, 100), ("Mix", 0, 100, 100)]:
            d, lv, c = self._knob(name, lo, hi, val, 42)
            kr.addLayout(c)
            setattr(self, f"d_{name.lower().replace(' ','_')}", d)
            d.valueChanged.connect(lambda v, l=lv, n=name.lower().replace(' ','_'): (
                l.setText(f"{v}%"), self._rt_set(n, v/100), self._schedule_save()))
        root.addLayout(kr)

        self.cmb_route.currentIndexChanged.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.cmb_route.setCurrentText(str(p.get("routing", "Post FX")))
            self.d_x.setValue(int(p.get("x", 50)))
            self.d_y.setValue(int(p.get("y", 50)))
            self.d_wet_gain.setValue(int(p.get("wet_gain", 100)))
            self.d_mix.setValue(int(p.get("mix", 100)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(routing=self.cmb_route.currentText(),
                 x=self.d_x.value(), y=self.d_y.value(),
                 wet_gain=self.d_wet_gain.value(), mix=self.d_mix.value())
        self._emit_updated()


# ═══════════════════════════════════════════════════════════
#  15. DE-ESSER
# ═══════════════════════════════════════════════════════════

class DeEsserFxWidget(_AudioFxBase):
    """De-Esser (Bitwig DE-ESSER style).
    
    Bild: Freq Knob, Filter Type, Monitor toggle, Amount Knob."""

    _FTYPES = ["Low-pass", "High-pass", "Band-pass"]

    def __init__(self, services, track_id, device_id, parent=None):
        super().__init__(services, track_id, device_id, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Filter"))
        self.cmb_ft = QComboBox()
        self.cmb_ft.addItems(self._FTYPES)
        self.cmb_ft.setCurrentText("High-pass")
        r1.addWidget(self.cmb_ft)
        self.chk_mon = QCheckBox("Monitor")
        r1.addWidget(self.chk_mon)
        root.addLayout(r1)

        kr = QHBoxLayout()
        kr.setSpacing(10)
        d_f, lv_f, c_f = self._knob("Freq", 200, 16000, 4980, 48)
        self.d_freq = d_f
        d_f.valueChanged.connect(lambda v, l=lv_f: (
            l.setText(f"{v}Hz" if v < 1000 else f"{v/1000:.1f}kHz"), self._schedule_save()))
        kr.addLayout(c_f)

        d_a, lv_a, c_a = self._knob("Amount", 0, 100, 50, 48)
        self.d_amount = d_a
        d_a.valueChanged.connect(lambda v, l=lv_a: (l.setText(f"{v}%"), self._schedule_save()))
        kr.addLayout(c_a)
        root.addLayout(kr)

        self.cmb_ft.currentIndexChanged.connect(lambda _: self._schedule_save())
        self.chk_mon.toggled.connect(lambda _: self._schedule_save())
        self._load()

    def _load(self):
        p = self._params()
        if not p:
            return
        self._restoring = True
        try:
            self.cmb_ft.setCurrentText(str(p.get("filter", "High-pass")))
            self.chk_mon.setChecked(bool(p.get("monitor", False)))
            self.d_freq.setValue(int(p.get("freq", 4980)))
            self.d_amount.setValue(int(p.get("amount", 50)))
        except Exception:
            pass
        finally:
            self._restoring = False

    def _save_to_project(self):
        p = self._params()
        if not p:
            return
        p.update(filter=self.cmb_ft.currentText(), monitor=self.chk_mon.isChecked(),
                 freq=self.d_freq.value(), amount=self.d_amount.value())
        self._emit_updated()
