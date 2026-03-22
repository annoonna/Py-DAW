# -*- coding: utf-8 -*-
"""Device-Rack widgets for Note-FX + Audio-FX (Bitwig/Ableton style).

Goal:
- FX are visible as modules in the bottom Device panel.
- Each module owns a tiny MVP parameter UI (no right-browser editor needed).

This file intentionally stays lightweight — no heavy dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer, QSignalBlocker, QThread, pyqtSignal, QProcess, QSocketNotifier
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QDial, QSlider, QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout, QFileDialog, QMessageBox, QMenu
)

try:
    # Optional widgets used by some devices (keep imports resilient).
    from PyQt6.QtWidgets import QScrollArea
except Exception:  # pragma: no cover
    QScrollArea = None


def _find_track(project: Any, track_id: str):
    try:
        for t in getattr(project, "tracks", []) or []:
            if getattr(t, "id", "") == track_id:
                return t
    except Exception:
        pass
    return None


def _get_automation_manager(services: Any):
    try:
        return getattr(services, "automation_manager", None) if services is not None else None
    except Exception:
        return None


def _qt_is_deleted(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        from PyQt6 import sip  # type: ignore
        return bool(sip.isdeleted(obj))
    except Exception:
        try:
            import sip  # type: ignore
            return bool(sip.isdeleted(obj))
        except Exception:
            return False


def _qt_widgets_alive(*objs: Any) -> bool:
    try:
        return all(not _qt_is_deleted(obj) for obj in objs)
    except Exception:
        return False


def _register_automatable_param(services: Any, track_id: str, parameter_id: str, name: str,
                                min_val: float, max_val: float, default_val: float):
    am = _get_automation_manager(services)
    if am is None:
        return None
    try:
        # Safe override: some embedded/device-local FX (e.g. Pro Drum slot FX)
        # need a dedicated RT parameter prefix, but should still appear under the
        # owning track in the Arranger automation UI.
        ui_track_id = str(getattr(services, 'automation_track_id', '') or track_id or "")
    except Exception:
        ui_track_id = str(track_id or "")
    try:
        return am.register_parameter(
            str(parameter_id),
            str(name),
            min_val=float(min_val),
            max_val=float(max_val),
            default_val=float(default_val),
            track_id=ui_track_id,
        )
    except Exception:
        return None


def _install_automation_menu(parent: QWidget, widget: QWidget, parameter_id: str, default_getter):
    try:
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    except Exception:
        return

    def _find_midi_svc():
        """Auto-discover MidiMappingService from widget hierarchy."""
        try:
            w = parent
            for _ in range(50):
                w = w.window() if callable(getattr(w, "window", None)) else None
                if w is None:
                    break
                services = getattr(w, "services", None)
                if services is not None:
                    return getattr(services, "midi_mapping", None)
                if w == (w.window() if callable(getattr(w, "window", None)) else None):
                    break
        except Exception:
            pass
        return None

    def _get_track_id() -> str:
        """Extract track_id from parameter_id.

        Supported formats:
          trk:<track_id>:<rest>           — instrument/sampler params
          afx:<track_id>:<device_id>:<p>  — audio FX params (Gain, EQ, etc.)
          afxchain:<track_id>:<rest>      — FX chain container params
        """
        if parameter_id and ":" in parameter_id:
            parts = parameter_id.split(":")
            if len(parts) >= 2 and parts[0] in ("trk", "afx", "afxchain"):
                return parts[1]
        return ""

    # v0.0.20.399 — Purple indicator for MIDI-mapped widgets
    _PURPLE_STYLE = "border: 2px solid #a855f7; border-radius: 3px;"
    _original_style = None

    def _update_mapped_indicator():
        """Apply or remove purple border based on MIDI mapping status."""
        nonlocal _original_style
        try:
            midi_svc = _find_midi_svc()
            _track_id = _get_track_id()
            if midi_svc and _track_id and parameter_id:
                existing = midi_svc.get_mapping_for_param(_track_id, parameter_id)
                if existing:
                    if _original_style is None:
                        try:
                            _original_style = widget.styleSheet() or ""
                        except Exception:
                            _original_style = ""
                    try:
                        current = widget.styleSheet() or ""
                        if "#a855f7" not in current:
                            widget.setStyleSheet(current + " " + _PURPLE_STYLE if current else _PURPLE_STYLE)
                    except Exception:
                        pass
                else:
                    if _original_style is not None:
                        try:
                            widget.setStyleSheet(_original_style)
                        except Exception:
                            pass
                        _original_style = None
        except Exception:
            pass

    # Connect to mapping_changed signal for live updates
    try:
        midi_svc = _find_midi_svc()
        if midi_svc is not None and hasattr(midi_svc, "mapping_changed"):
            midi_svc.mapping_changed.connect(_update_mapped_indicator)
    except Exception:
        pass

    # Initial check
    try:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, _update_mapped_indicator)
    except Exception:
        pass

    # v0.0.20.433: Generic CC re-registration from _persistent_cc_map.
    # When DevicePanel rebuilds (project_updated), old widgets die.
    # Re-register new widgets so MIDI CC still reaches them.
    try:
        am = _get_automation_manager(getattr(parent, '_services', None))
        if am is not None and parameter_id:
            persistent = getattr(am, '_persistent_cc_map', None)
            if persistent and str(parameter_id) in persistent:
                saved_cc = persistent[str(parameter_id)]
                cc_listeners = getattr(am, '_midi_cc_listeners', None)
                if cc_listeners is None:
                    am._midi_cc_listeners = {}
                    cc_listeners = am._midi_cc_listeners
                cc_listeners[saved_cc] = widget
                widget._midi_cc_mapping = saved_cc
                widget._pydaw_param_id = str(parameter_id)
    except Exception:
        pass

    def _show_menu(pos):
        try:
            am = _get_automation_manager(getattr(parent, '_services', None))
            menu = QMenu(parent)

            # Show Automation
            act_show = menu.addAction('Show Automation in Arranger')
            if am is None or not parameter_id:
                act_show.setEnabled(False)

            # v0.0.20.419: Unified MIDI Learn — uses the SAME fast AutomationManager
            # path as CompactKnob. CC → widget.setValue() directly, no bridge needed.
            menu.addSeparator()
            act_midi_learn = None
            act_midi_remove = None
            cc_info = getattr(widget, '_midi_cc_mapping', None)
            if cc_info is not None:
                ch_show, cc_show = cc_info
                menu.addAction(f'🎹 Mapped: CC{cc_show} ch{ch_show}').setEnabled(False)
                act_midi_remove = menu.addAction('🎹 MIDI Mapping entfernen')
            else:
                act_midi_learn = menu.addAction('🎹 MIDI Learn')
                if am is None:
                    act_midi_learn.setEnabled(False)
            menu.addSeparator()

            act_mod = menu.addAction('Add Modulator (LFO/ENV) — coming soon')
            try:
                act_mod.setEnabled(False)
            except Exception:
                pass
            menu.addSeparator()
            act_reset = menu.addAction('Reset to Default')

            chosen = menu.exec(widget.mapToGlobal(pos))
            if chosen is None:
                return
            if chosen == act_show and am is not None:
                try:
                    am.request_show_automation.emit(str(parameter_id))
                except Exception:
                    pass
            elif chosen == act_reset:
                try:
                    param = am.get_parameter(str(parameter_id)) if am else None
                except Exception:
                    param = None
                try:
                    dv = float(default_getter())
                except Exception:
                    dv = 0.0
                try:
                    if param is not None:
                        param.set_value(dv)
                        param.set_automation_value(None)
                except Exception:
                    pass
            elif chosen == act_midi_learn and am is not None:
                # v0.0.20.423: Same path as CompactKnob._start_midi_learn()
                try:
                    try:
                        midi_svc = _find_midi_svc()
                        if midi_svc is not None:
                            midi_svc.cancel_learn()
                    except Exception:
                        pass
                    # Tag widget with parameter_id so we can persist CC mapping after learn
                    widget._pydaw_param_id = str(parameter_id)
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
            elif chosen == act_midi_remove:
                # Remove from AutomationManager fast path
                cc_map = getattr(widget, '_midi_cc_mapping', None)
                if cc_map is not None:
                    try:
                        cc_listeners = getattr(am, '_midi_cc_listeners', {})
                        cc_listeners.pop(cc_map, None)
                    except Exception:
                        pass
                    widget._midi_cc_mapping = None
                # v0.0.20.423: Remove from persistent registry
                try:
                    persistent = getattr(am, '_persistent_cc_map', None)
                    if persistent and parameter_id:
                        persistent.pop(str(parameter_id), None)
                except Exception:
                    pass
                # Also remove from MidiMappingService
                try:
                    midi_svc = _find_midi_svc()
                    _track_id = _get_track_id()
                    if midi_svc and _track_id:
                        midi_svc.remove_mappings_for_param(_track_id, parameter_id)
                except Exception:
                    pass
                try:
                    widget.setStyleSheet('')
                except Exception:
                    pass
        except Exception:
            pass

    try:
        widget.customContextMenuRequested.connect(_show_menu)
    except Exception:
        pass


class AudioChainContainerWidget(QWidget):
    """CHAIN container device: Wet Gain + Mix (per track)."""

    def __init__(self, services: Any, track_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._flush_to_project)
        self._automation_param = None
        self._automation_connected = False
        self._ui_sync_timer = QTimer(self)
        self._ui_sync_timer.setInterval(50)
        self._ui_sync_timer.timeout.connect(self._sync_from_rt)
        try:
            self.destroyed.connect(self._disconnect_automation)
        except Exception:
            pass
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(12)

        # Wet Gain (0..200%)
        self.dial_wet = QDial()
        self.dial_wet.setNotchesVisible(True)
        self.dial_wet.setRange(0, 200)
        self.dial_wet.setValue(100)

        col_w = QVBoxLayout()
        col_w.addWidget(QLabel("Wet Gain"), 0, Qt.AlignmentFlag.AlignHCenter)
        col_w.addWidget(self.dial_wet, 1)
        self.lbl_wet = QLabel("100%")
        self.lbl_wet.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col_w.addWidget(self.lbl_wet)

        # Mix (0..100%)
        self.dial_mix = QDial()
        self.dial_mix.setNotchesVisible(True)
        self.dial_mix.setRange(0, 100)
        self.dial_mix.setValue(100)

        col_m = QVBoxLayout()
        col_m.addWidget(QLabel("Mix"), 0, Qt.AlignmentFlag.AlignHCenter)
        col_m.addWidget(self.dial_mix, 1)
        self.lbl_mix = QLabel("100%")
        self.lbl_mix.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col_m.addWidget(self.lbl_mix)

        row.addLayout(col_w, 1)
        row.addLayout(col_m, 1)

        root.addLayout(row)

        self.dial_wet.valueChanged.connect(self._on_change)
        self.dial_mix.valueChanged.connect(self._on_change)

        # v0.0.20.250: CHAIN wet/mix are automatable too (also for embedded slot FX).
        try:
            _install_automation_menu(self, self.dial_wet, self._key_wet(), lambda: 1.0)
            _install_automation_menu(self, self.lbl_wet, self._key_wet(), lambda: 1.0)
            _install_automation_menu(self, self.dial_mix, self._key_mix(), lambda: 1.0)
            _install_automation_menu(self, self.lbl_mix, self._key_mix(), lambda: 1.0)
            self._bind_automation()
        except Exception:
            pass

        self.refresh_from_project()
        try:
            self._ui_sync_timer.start()
        except Exception:
            pass

    def _rt(self):
        ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
        return getattr(ae, "rt_params", None) if ae is not None else None

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _disconnect_automation(self, *_args) -> None:
        am = _get_automation_manager(self._services)
        if am is not None and self._automation_connected:
            try:
                am.parameter_changed.disconnect(self._on_automation_changed)
            except Exception:
                pass
        self._automation_connected = False

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _apply_ui_value(self, key: str, value: float) -> None:
        try:
            if key == self._key_wet():
                v = max(0.0, min(2.0, float(value)))
                with QSignalBlocker(self.dial_wet):
                    self.dial_wet.setValue(int(round(v * 100.0)))
                self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            elif key == self._key_mix():
                v = max(0.0, min(1.0, float(value)))
                with QSignalBlocker(self.dial_mix):
                    self.dial_mix.setValue(int(round(v * 100.0)))
                self.lbl_mix.setText(f"{self.dial_mix.value()}%")
        except Exception:
            pass

    def _sync_from_rt(self) -> None:
        try:
            if not self.isVisible():
                return
        except Exception:
            pass
        rt = self._rt()
        if rt is None:
            return
        try:
            self._apply_ui_value(self._key_wet(), float(rt.get_target(self._key_wet(), float(self.dial_wet.value()) / 100.0)))
            self._apply_ui_value(self._key_mix(), float(rt.get_target(self._key_mix(), float(self.dial_mix.value()) / 100.0)))
        except Exception:
            pass

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        try:
            pid = str(parameter_id)
            if pid == self._key_wet() or pid == self._key_mix():
                self._apply_ui_value(pid, float(value))
        except RuntimeError:
            self._disconnect_automation()

    def refresh_from_project(self) -> None:
        project = getattr(self._services, "project", None)
        proj = getattr(project, "ctx", None)
        p = getattr(proj, "project", None) if proj is not None else getattr(project, "project", None)
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        wet = float(chain.get("wet_gain", 1.0) or 1.0)
        mix = float(chain.get("mix", 1.0) or 1.0)
        self.dial_wet.blockSignals(True)
        self.dial_mix.blockSignals(True)
        try:
            self.dial_wet.setValue(int(max(0, min(200, round(wet * 100.0)))))
            self.dial_mix.setValue(int(max(0, min(100, round(mix * 100.0)))))
        finally:
            self.dial_wet.blockSignals(False)
            self.dial_mix.blockSignals(False)
        self.lbl_wet.setText(f"{self.dial_wet.value()}%")
        self.lbl_mix.setText(f"{self.dial_mix.value()}%")

    def _on_change(self, *_args) -> None:
        self.lbl_wet.setText(f"{self.dial_wet.value()}%")
        self.lbl_mix.setText(f"{self.dial_mix.value()}%")
        # realtime params
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae is not None else None
        tid = self._track_id
        wet = float(self.dial_wet.value()) / 100.0
        mix = float(self.dial_mix.value()) / 100.0
        try:
            if rt is not None:
                rt.set_param(self._key_wet(), wet)
                rt.set_param(self._key_mix(), mix)
        except Exception:
            pass
        try:
            p = (self._automation_param or {}).get("wet") if isinstance(self._automation_param, dict) else None
            if p is not None:
                p.set_value(float(wet))
            p = (self._automation_param or {}).get("mix") if isinstance(self._automation_param, dict) else None
            if p is not None:
                p.set_value(float(mix))
        except Exception:
            pass
        # persist (debounced)
        self._debounce.start()

        # Update output selector (if plugin has multiple audio outs)
        try:
            self._update_output_selector()
        except Exception:
            pass


    def _flush_to_project(self) -> None:
        project_service = getattr(self._services, "project", None)
        if project_service is None:
            return
        ctx = getattr(project_service, "ctx", None)
        p = getattr(ctx, "project", None) if ctx is not None else getattr(project_service, "project", None)
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        chain["wet_gain"] = float(self.dial_wet.value()) / 100.0
        chain["mix"] = float(self.dial_mix.value()) / 100.0
        try:
            # notify UI; avoid "changed" spam
            if hasattr(project_service, "project_updated"):
                project_service.project_updated.emit()
        except Exception:
            pass




class GainFxWidget(QWidget):
    """Gain audio FX module: Gain (dB) -> RTParam gain linear."""

    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._flush_to_project)
        self._automation_param = None
        self._automation_connected = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(6)

        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setRange(-600, 240)  # -60..+24 dB * 10
        self.spn = QDoubleSpinBox()
        self.spn.setRange(-60.0, 24.0)
        self.spn.setSingleStep(0.1)
        self.spn.setDecimals(1)
        self.spn.setSuffix(" dB")
        self.spn.setMaximumWidth(110)

        row.addWidget(QLabel("Gain"), 0)
        row.addWidget(self.sld, 1)
        row.addWidget(self.spn, 0)
        root.addLayout(row)

        self.sld.valueChanged.connect(self._on_slider)
        self.spn.valueChanged.connect(self._on_spin)
        _install_automation_menu(self, self.sld, self._key(), lambda: 0.0)
        _install_automation_menu(self, self.spn, self._key(), lambda: 0.0)

        # v0.0.20.423: Fast CC handler on slider (like CompactKnob.handle_midi_cc)
        _gain_widget_ref = self
        def _sld_handle_midi_cc(val_0_127: int) -> None:
            try:
                scaled = -600 + (int(val_0_127) / 127.0) * 840
                iv = int(round(scaled))
                db = float(iv) / 10.0
                _gain_widget_ref.sld.blockSignals(True)
                _gain_widget_ref.spn.blockSignals(True)
                try:
                    _gain_widget_ref.sld.setValue(iv)
                    _gain_widget_ref.spn.setValue(db)
                finally:
                    _gain_widget_ref.sld.blockSignals(False)
                    _gain_widget_ref.spn.blockSignals(False)
                _gain_widget_ref._apply_rt(db)
                _gain_widget_ref._debounce.start()
            except Exception:
                pass
        self.sld.handle_midi_cc = _sld_handle_midi_cc

        # v0.0.20.423: Re-register CC mapping if one existed before widget rebuild.
        # When project_updated fires, DevicePanel destroys and recreates this widget.
        # The old slider in cc_listeners is dead. We must re-register the new slider.
        try:
            pid = self._key()
            am = _get_automation_manager(self._services)
            if am is not None:
                persistent = getattr(am, '_persistent_cc_map', None)
                if persistent and pid in persistent:
                    saved_cc = persistent[pid]
                    cc_listeners = getattr(am, '_midi_cc_listeners', None)
                    if cc_listeners is None:
                        am._midi_cc_listeners = {}
                        cc_listeners = am._midi_cc_listeners
                    cc_listeners[saved_cc] = self.sld
                    self.sld._midi_cc_mapping = saved_cc
                    self.sld._pydaw_param_id = pid
        except Exception:
            pass

        self.refresh_from_project()
        self._bind_automation()

    def _key(self) -> str:
        return f"afx:{self._track_id}:{self._device_id}:gain"

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        try:
            pid = str(parameter_id)
            if pid == self._key_wet():
                v = max(0.0, min(2.0, float(value)))
                self.dial_wet.blockSignals(True)
                try:
                    self.dial_wet.setValue(int(round(v * 100.0)))
                finally:
                    self.dial_wet.blockSignals(False)
                self.lbl_wet.setText(f"{self.dial_wet.value()}%")
                self._on_change()
            elif pid == self._key_mix():
                v = max(0.0, min(1.0, float(value)))
                self.dial_mix.blockSignals(True)
                try:
                    self.dial_mix.setValue(int(round(v * 100.0)))
                finally:
                    self.dial_mix.blockSignals(False)
                self.lbl_mix.setText(f"{self.dial_mix.value()}%")
                self._on_change()
        except RuntimeError:
            self._disconnect_automation()

    def refresh_from_project(self) -> None:
        project_service = getattr(self._services, "project", None)
        ctx = getattr(project_service, "ctx", None) if project_service is not None else None
        p = getattr(ctx, "project", None) if ctx is not None else None
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == self._device_id), None)
        if dev is None:
            return
        params = dev.get("params", {}) if isinstance(dev.get("params"), dict) else {}
        db = float(params.get("gain_db", 0.0) or 0.0)
        self.sld.blockSignals(True)
        self.spn.blockSignals(True)
        try:
            self.sld.setValue(int(round(db * 10.0)))
            self.spn.setValue(db)
        finally:
            self.sld.blockSignals(False)
            self.spn.blockSignals(False)

    def _bind_automation(self) -> None:
        self._automation_param = _register_automatable_param(
            self._services, self._track_id, self._key(), "Gain", -60.0, 24.0, float(self.spn.value())
        )
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        if str(parameter_id) != self._key():
            return
        db = float(max(-60.0, min(24.0, float(value))))
        try:
            sld = getattr(self, "sld", None)
            spn = getattr(self, "spn", None)
            if sld is None or spn is None:
                return
            sld.blockSignals(True)
            spn.blockSignals(True)
            try:
                sld.setValue(int(round(db * 10.0)))
                spn.setValue(db)
            finally:
                try:
                    sld.blockSignals(False)
                    spn.blockSignals(False)
                except RuntimeError:
                    return
        except RuntimeError:
            return
        self._apply_rt(db)
        try:
            self._debounce.start()
        except RuntimeError:
            return

    def _apply_rt(self, db: float) -> None:
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae is not None else None
        if rt is None:
            return
        # linear
        g = float(10.0 ** (max(-120.0, min(24.0, float(db))) / 20.0))
        try:
            rt.set_param(self._key(), g)
        except Exception:
            pass

    def _on_slider(self, v: int) -> None:
        db = float(v) / 10.0
        self.spn.blockSignals(True)
        try:
            self.spn.setValue(db)
        finally:
            self.spn.blockSignals(False)
        self._apply_rt(db)
        try:
            if self._automation_param is not None:
                self._automation_param.set_value(float(db))
        except Exception:
            pass
        self._debounce.start()

    def _on_spin(self, db: float) -> None:
        self.sld.blockSignals(True)
        try:
            self.sld.setValue(int(round(float(db) * 10.0)))
        finally:
            self.sld.blockSignals(False)
        self._apply_rt(float(db))
        try:
            if self._automation_param is not None:
                self._automation_param.set_value(float(db))
        except Exception:
            pass
        self._debounce.start()

    def _flush_to_project(self) -> None:
        project_service = getattr(self._services, "project", None)
        ctx = getattr(project_service, "ctx", None) if project_service is not None else None
        p = getattr(ctx, "project", None) if ctx is not None else None
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == self._device_id), None)
        if dev is None:
            return
        params = dev.get("params", {})
        if not isinstance(params, dict):
            params = {}
            dev["params"] = params
        db = float(self.spn.value())
        params["gain_db"] = db
        params["gain"] = float(10.0 ** (db / 20.0))
        try:
            if hasattr(project_service, "project_updated"):
                project_service.project_updated.emit()
        except Exception:
            pass


class DistortionFxWidget(QWidget):
    """Simple distortion module (drive + mix)."""

    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._flush_to_project)
        self._automation_params = {}
        self._automation_connected = False
        try:
            self.destroyed.connect(self._disconnect_automation)
        except Exception:
            pass
        self._build()

    def _disconnect_automation(self, *_args) -> None:
        am = _get_automation_manager(self._services)
        if am is not None and self._automation_connected:
            try:
                am.parameter_changed.disconnect(self._on_automation_changed)
            except Exception:
                pass
        self._automation_connected = False

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Drive
        row1 = QHBoxLayout()
        self.sld_drive = QSlider(Qt.Orientation.Horizontal)
        self.sld_drive.setRange(0, 100)
        self.spn_drive = QDoubleSpinBox()
        self.spn_drive.setRange(0.0, 1.0)
        self.spn_drive.setSingleStep(0.01)
        self.spn_drive.setDecimals(2)
        self.spn_drive.setMaximumWidth(90)
        row1.addWidget(QLabel("Drive"), 0)
        row1.addWidget(self.sld_drive, 1)
        row1.addWidget(self.spn_drive, 0)
        root.addLayout(row1)

        # Mix
        row2 = QHBoxLayout()
        self.sld_mix = QSlider(Qt.Orientation.Horizontal)
        self.sld_mix.setRange(0, 100)
        self.spn_mix = QDoubleSpinBox()
        self.spn_mix.setRange(0.0, 1.0)
        self.spn_mix.setSingleStep(0.01)
        self.spn_mix.setDecimals(2)
        self.spn_mix.setMaximumWidth(90)
        row2.addWidget(QLabel("Mix"), 0)
        row2.addWidget(self.sld_mix, 1)
        row2.addWidget(self.spn_mix, 0)
        root.addLayout(row2)

        self.sld_drive.valueChanged.connect(self._on_drive_slider)
        self.spn_drive.valueChanged.connect(self._on_drive_spin)
        self.sld_mix.valueChanged.connect(self._on_mix_slider)
        self.spn_mix.valueChanged.connect(self._on_mix_spin)
        _install_automation_menu(self, self.sld_drive, self._key_drive(), lambda: 0.25)
        _install_automation_menu(self, self.spn_drive, self._key_drive(), lambda: 0.25)
        _install_automation_menu(self, self.sld_mix, self._key_mix(), lambda: 1.0)
        _install_automation_menu(self, self.spn_mix, self._key_mix(), lambda: 1.0)

        self.refresh_from_project()
        self._bind_automation()

    def _key_drive(self) -> str:
        return f"afx:{self._track_id}:{self._device_id}:drive"

    def _key_mix(self) -> str:
        return f"afx:{self._track_id}:{self._device_id}:mix"

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        project_service = getattr(self._services, "project", None)
        ctx = getattr(project_service, "ctx", None) if project_service is not None else None
        p = getattr(ctx, "project", None) if ctx is not None else None
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == self._device_id), None)
        if dev is None:
            return
        params = dev.get("params", {}) if isinstance(dev.get("params"), dict) else {}
        drive = float(params.get("drive", 0.25) or 0.25)
        mix = float(params.get("mix", 1.0) or 1.0)

        self.sld_drive.blockSignals(True); self.spn_drive.blockSignals(True)
        self.sld_mix.blockSignals(True); self.spn_mix.blockSignals(True)
        try:
            self.sld_drive.setValue(int(round(max(0.0, min(1.0, drive)) * 100.0)))
            self.spn_drive.setValue(max(0.0, min(1.0, drive)))
            self.sld_mix.setValue(int(round(max(0.0, min(1.0, mix)) * 100.0)))
            self.spn_mix.setValue(max(0.0, min(1.0, mix)))
        finally:
            self.sld_drive.blockSignals(False); self.spn_drive.blockSignals(False)
            self.sld_mix.blockSignals(False); self.spn_mix.blockSignals(False)

        # ensure RT keys exist
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae is not None else None
        try:
            if rt is not None:
                rt.ensure(self._key_drive(), drive)
                rt.ensure(self._key_mix(), mix)
        except Exception:
            pass

    def _bind_automation(self) -> None:
        self._automation_params["drive"] = _register_automatable_param(
            self._services, self._track_id, self._key_drive(), "Drive", 0.0, 1.0, float(self.spn_drive.value())
        )
        self._automation_params["mix"] = _register_automatable_param(
            self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.spn_mix.value())
        )
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        if not _qt_widgets_alive(self, getattr(self, "sld_drive", None), getattr(self, "spn_drive", None), getattr(self, "sld_mix", None), getattr(self, "spn_mix", None)):
            self._disconnect_automation()
            return
        pid = str(parameter_id)
        x = float(max(0.0, min(1.0, float(value))))
        if pid == self._key_drive():
            try:
                self.sld_drive.blockSignals(True); self.spn_drive.blockSignals(True)
                self.sld_drive.setValue(int(round(x * 100.0)))
                self.spn_drive.setValue(x)
            finally:
                try:
                    if _qt_widgets_alive(self.sld_drive, self.spn_drive):
                        self.sld_drive.blockSignals(False); self.spn_drive.blockSignals(False)
                except Exception:
                    pass
            self._apply_rt()
            self._debounce.start()
        elif pid == self._key_mix():
            try:
                self.sld_mix.blockSignals(True); self.spn_mix.blockSignals(True)
                self.sld_mix.setValue(int(round(x * 100.0)))
                self.spn_mix.setValue(x)
            finally:
                try:
                    if _qt_widgets_alive(self.sld_mix, self.spn_mix):
                        self.sld_mix.blockSignals(False); self.spn_mix.blockSignals(False)
                except Exception:
                    pass
            self._apply_rt()
            self._debounce.start()

    def _apply_rt(self) -> None:
        ae = getattr(self._services, "audio_engine", None)
        rt = getattr(ae, "rt_params", None) if ae is not None else None
        if rt is None:
            return
        try:
            rt.set_param(self._key_drive(), float(self.spn_drive.value()))
            rt.set_param(self._key_mix(), float(self.spn_mix.value()))
        except Exception:
            pass

    def _on_drive_slider(self, v: int) -> None:
        x = float(v) / 100.0
        self.spn_drive.blockSignals(True)
        try:
            self.spn_drive.setValue(x)
        finally:
            self.spn_drive.blockSignals(False)
        self._apply_rt()
        try:
            p = self._automation_params.get("drive")
            if p is not None:
                p.set_value(float(x))
        except Exception:
            pass
        self._debounce.start()

    def _on_drive_spin(self, x: float) -> None:
        self.sld_drive.blockSignals(True)
        try:
            self.sld_drive.setValue(int(round(max(0.0, min(1.0, float(x))) * 100.0)))
        finally:
            self.sld_drive.blockSignals(False)
        self._apply_rt()
        try:
            p = self._automation_params.get("drive")
            if p is not None:
                p.set_value(float(x))
        except Exception:
            pass
        self._debounce.start()

    def _on_mix_slider(self, v: int) -> None:
        x = float(v) / 100.0
        self.spn_mix.blockSignals(True)
        try:
            self.spn_mix.setValue(x)
        finally:
            self.spn_mix.blockSignals(False)
        self._apply_rt()
        try:
            p = self._automation_params.get("mix")
            if p is not None:
                p.set_value(float(x))
        except Exception:
            pass
        self._debounce.start()

    def _on_mix_spin(self, x: float) -> None:
        self.sld_mix.blockSignals(True)
        try:
            self.sld_mix.setValue(int(round(max(0.0, min(1.0, float(x))) * 100.0)))
        finally:
            self.sld_mix.blockSignals(False)
        self._apply_rt()
        try:
            p = self._automation_params.get("mix")
            if p is not None:
                p.set_value(float(x))
        except Exception:
            pass
        self._debounce.start()

    def _flush_to_project(self) -> None:
        project_service = getattr(self._services, "project", None)
        ctx = getattr(project_service, "ctx", None) if project_service is not None else None
        p = getattr(ctx, "project", None) if ctx is not None else None
        t = _find_track(p, self._track_id) if p is not None else None
        if t is None:
            return
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == self._device_id), None)
        if dev is None:
            return
        params = dev.get("params", {})
        if not isinstance(params, dict):
            params = {}
            dev["params"] = params
        params["drive"] = float(self.spn_drive.value())
        params["mix"] = float(self.spn_mix.value())
        try:
            if hasattr(project_service, "project_updated"):
                project_service.project_updated.emit()
        except Exception:
            pass


# --- NOTE-FX: small module UIs (MVP)

def _get_project_and_track(services: Any, track_id: str):
    ps = getattr(services, "project", None) if services is not None else None
    ctx = getattr(ps, "ctx", None) if ps is not None else None
    p = getattr(ctx, "project", None) if ctx is not None else None
    t = _find_track(p, track_id) if p is not None else None
    return ps, p, t


def _find_note_fx_dev(services: Any, track_id: str, device_id: str):
    ps, p, t = _get_project_and_track(services, track_id)
    if t is None:
        return None, None
    chain = getattr(t, "note_fx_chain", None)
    if not isinstance(chain, dict):
        return None, None
    devs = chain.get("devices", []) or []
    dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == str(device_id)), None)
    if dev is None:
        return None, None
    params = dev.get("params", {})
    if not isinstance(params, dict):
        params = {}
        dev["params"] = params
    return dev, params


def _find_audio_fx_dev(services: Any, track_id: str, device_id: str):
    ps, p, t = _get_project_and_track(services, track_id)
    if t is None:
        return None, None
    chain = getattr(t, "audio_fx_chain", None)
    if not isinstance(chain, dict):
        return None, None
    devs = chain.get("devices", []) or []
    dev = next((d for d in devs if isinstance(d, dict) and str(d.get("id","")) == str(device_id)), None)
    if dev is None:
        return None, None
    params = dev.get("params", {})
    if not isinstance(params, dict):
        params = {}
        dev["params"] = params
    return dev, params


class Lv2AudioFxWidget(QWidget):
    """Generic LV2 Audio-FX parameter widget (MVP).

    - Reads LV2 control ports via lilv (optional dependency).
    - Writes to RTParamStore (smooth) and persists values into device params.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, plugin_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._plugin_id = str(plugin_id or "")
        self._uri = ""
        if self._plugin_id.startswith("ext.lv2:"):
            self._uri = self._plugin_id.split(":", 1)[1]

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._flush_to_project)

        self._controls = []
        self._rows = {}  # symbol -> (slider, spin, info)
        self._automation_params = {}
        self._automation_connected = False

        # v0.0.20.538: UI sync timer — polls RT store to update sliders during automation
        self._ui_sync_timer = QTimer(self)
        self._ui_sync_timer.setInterval(60)
        self._ui_sync_timer.timeout.connect(self._sync_from_rt)

        self._build()

    def _rt(self):
        ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
        return getattr(ae, "rt_params", None) if ae is not None else None

    def _key(self, symbol: str) -> str:
        return f"afx:{self._track_id}:{self._device_id}:lv2:{symbol}"

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        top = QHBoxLayout()
        lab = QLabel("LV2")
        lab.setStyleSheet("font-weight: 600;")
        top.addWidget(lab, 0)
        self._lbl_uri = QLabel(self._uri or "(unknown URI)")
        self._lbl_uri.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl_uri.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        top.addWidget(self._lbl_uri, 1)
        root.addLayout(top)

        # availability / hint
        self._lbl_hint = QLabel("")
        self._lbl_hint.setWordWrap(True)
        self._lbl_hint.setStyleSheet("color: #b0b7c3; font-size: 11px;")
        root.addWidget(self._lbl_hint)

        # LV2 DSP status + quick action (SAFE): helps diagnose "UI works but no sound"
        self._row_status = QHBoxLayout()
        self._row_status.setContentsMargins(0, 0, 0, 0)
        self._row_status.setSpacing(6)
        self._lbl_dsp = QLabel("")
        self._lbl_dsp.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        self._row_status.addWidget(self._lbl_dsp, 1)
        self._btn_audition = QPushButton("Audition")
        self._btn_audition.setToolTip("Make the LV2 effect clearly audible (heuristic: bypass off / wet on).")
        self._btn_audition.clicked.connect(self._audition_make_obvious)
        self._btn_audition.setVisible(True)
        self._row_status.addWidget(self._btn_audition, 0)

        # Output selection (SAFE): some LV2 plugins expose multiple audio outs (dry taps, monitor, wet).
        # If the host copies back the wrong pair, the effect can sound like no change.
        self._cmb_out = QComboBox()
        self._cmb_out.setToolTip("Select which LV2 audio output pair is used for playback (debug).")
        self._cmb_out.setVisible(False)
        self._cmb_out.currentIndexChanged.connect(self._on_out_sel_changed)
        self._row_status.addWidget(self._cmb_out, 0)

        self._btn_rebuild = QPushButton("Rebuild FX")
        self._btn_rebuild.setToolTip("Rebuild per-track Audio-FX maps (safe).")
        self._btn_rebuild.clicked.connect(self._safe_rebuild_fx_maps)
        self._btn_rebuild.setVisible(False)
        self._row_status.addWidget(self._btn_rebuild, 0)
        root.addLayout(self._row_status)

        # ── v0.0.20.652: Preset Browser ──────────────────────────────────────
        try:
            from pydaw.ui.preset_browser_widget import PresetBrowserWidget
            self._preset_browser = PresetBrowserWidget(
                plugin_type="lv2",
                plugin_id=self._plugin_id,
                device_id=self._device_id,
                track_id=self._track_id,
                get_state_fn=None,   # LV2 state save/restore not yet wired
                set_state_fn=None,
                get_params_fn=self._get_current_param_values_for_preset,
                parent=self,
            )
            root.addWidget(self._preset_browser)
        except Exception:
            self._preset_browser = None

        # search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search parameter…")
        self._search.textChanged.connect(self._apply_filter)
        root.addWidget(self._search)

        # scroll
        if QScrollArea is None:
            self._scroll = None
            self._body = QWidget()
            self._body_l = QVBoxLayout(self._body)
            self._body_l.setContentsMargins(0, 0, 0, 0)
            self._body_l.setSpacing(3)
            root.addWidget(self._body, 1)
        else:
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            self._body = QWidget()
            self._body_l = QVBoxLayout(self._body)
            self._body_l.setContentsMargins(0, 0, 0, 0)
            self._body_l.setSpacing(3)
            self._scroll.setWidget(self._body)
            root.addWidget(self._scroll, 1)

        self._load_controls_and_build_rows()
        self.refresh_from_project()
        try:
            self._ui_sync_timer.start()
        except Exception:
            pass

        # v0.0.20.526: Connect AutomationManager.parameter_changed → slider follow
        try:
            am = _get_automation_manager(self._services)
            if am is not None and hasattr(am, "parameter_changed"):
                am.parameter_changed.connect(self._on_automation_param_changed)
        except Exception:
            pass

    def _on_automation_param_changed(self, parameter_id: str, value: float) -> None:
        """Update slider/spinbox when automation plays back a value (v0.0.20.526)."""
        try:
            pid = str(parameter_id or "")
            prefix = f"afx:{self._track_id}:{self._device_id}:lv2:"
            if not pid.startswith(prefix):
                return
            symbol = pid[len(prefix):]
            row_data = self._rows.get(symbol)
            if row_data is None:
                return
            sld, spn, info = row_data
            val = float(value)
            mn = float(info.get("minimum", 0.0)) if isinstance(info, dict) else 0.0
            mx = float(info.get("maximum", 1.0)) if isinstance(info, dict) else 1.0
            from PyQt6.QtCore import QSignalBlocker
            if sld is not None and hasattr(sld, 'setValue'):
                if mx > mn:
                    sld_val = int((val - mn) / (mx - mn) * 1000.0)
                    sld_val = max(0, min(1000, sld_val))
                else:
                    sld_val = 0
                with QSignalBlocker(sld):
                    sld.setValue(sld_val)
            if spn is not None:
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            rt = self._rt()
            if rt is not None:
                key = self._key(symbol)
                try:
                    if hasattr(rt, "set_smooth"):
                        rt.set_smooth(key, float(val))
                    elif hasattr(rt, "set_param"):
                        rt.set_param(key, float(val))
                except Exception:
                    pass
        except Exception:
            pass

    def _sync_from_rt(self) -> None:
        """v0.0.20.538: Poll RT store to update sliders during automation playback."""
        rt = self._rt()
        if rt is None:
            return
        try:
            from PyQt6.QtCore import QSignalBlocker
            for sym, row_data in self._rows.items():
                try:
                    _row, sld, spn, (mn, mx, df) = row_data
                    if _row is not None and not _row.isVisible():
                        continue
                except (ValueError, TypeError):
                    continue
                key = self._key(sym)
                try:
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, df))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, df))
                    else:
                        continue
                    val = max(mn, min(mx, val))
                    if sld is not None and isinstance(sld, QSlider):
                        rng = mx - mn
                        sld_val = int((val - mn) / max(1e-9, rng) * 1000.0)
                        with QSignalBlocker(sld):
                            sld.setValue(max(0, min(1000, sld_val)))
                    if spn is not None:
                        with QSignalBlocker(spn):
                            spn.setValue(val)
                except Exception:
                    continue
        except Exception:
            pass

    def _dsp_is_active(self) -> bool:
        """Best-effort check if this LV2 FX is compiled into the audio thread.

        If python-lilv is available but the plugin instance fails to instantiate
        (missing required features, broken bundle, etc.), ChainFx will skip it.
        Then users see controls but hear no effect.
        """
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            fx_map = getattr(ae, "_track_audio_fx_map", None) if ae is not None else None
            if not isinstance(fx_map, dict):
                return False
            chain = fx_map.get(str(self._track_id))
            devs = getattr(chain, "devices", None)
            if not isinstance(devs, list):
                return False
            for fx in devs:
                try:
                    if str(getattr(fx, "device_id", "")) == str(self._device_id):
                        # We only care that *some* DSP object exists for this device id.
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _get_runtime_fx(self):
        # Return the Lv2Fx object from the audio thread map (best-effort).
        try:
            ae = getattr(self._services, 'audio_engine', None) if self._services is not None else None
            fx_map = getattr(ae, '_track_audio_fx_map', None) if ae is not None else None
            if not isinstance(fx_map, dict):
                return None
            chain = fx_map.get(str(self._track_id))
            devs = getattr(chain, 'devices', None)
            if not isinstance(devs, list):
                return None
            for fx in devs:
                try:
                    if str(getattr(fx, 'device_id', '')) == str(self._device_id):
                        return fx
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _update_output_selector(self) -> None:
        # Populate output selector for plugins with >2 audio outputs.
        try:
            cmb = getattr(self, '_cmb_out', None)
            if cmb is None:
                return
            fx = self._get_runtime_fx()
            if fx is None or not hasattr(fx, 'get_output_options'):
                cmb.setVisible(False)
                return
            try:
                opts = list(fx.get_output_options() or [])
            except Exception:
                opts = []
            if len(opts) <= 2:
                cmb.setVisible(False)
                return

            pairs = []
            n = len(opts)
            for i in range(0, n, 2):
                a = i
                b = i + 1 if (i + 1) < n else i
                ma = opts[a]
                mb = opts[b]
                la = (str(ma.get('symbol') or ma.get('name') or '')).strip()
                lb = (str(mb.get('symbol') or mb.get('name') or '')).strip()
                label = f"Out {a}/{b}: {la or 'L'} | {lb or 'R'}"
                pairs.append((label, [a, b]))

            try:
                cur = list(fx.get_output_selection() or [])
            except Exception:
                cur = [0, 1]
            try:
                auto = list(fx.get_auto_output_selection() or [])
            except Exception:
                auto = [0, 1]

            from PyQt6.QtCore import QSignalBlocker
            with QSignalBlocker(cmb):
                cmb.clear()
                cmb.addItem(f"Auto ({auto[0]}/{auto[1]})", ['auto'])
                for label, sel in pairs:
                    cmb.addItem(label, sel)

                sel_key = [int(cur[0]), int(cur[1] if len(cur) > 1 else cur[0])]
                idx_match = -1
                for j in range(cmb.count()):
                    data = cmb.itemData(j)
                    if isinstance(data, list) and data and data[0] == 'auto':
                        continue
                    if isinstance(data, list) and len(data) >= 2:
                        if [int(data[0]), int(data[1])] == sel_key:
                            idx_match = j
                            break
                cmb.setCurrentIndex(idx_match if idx_match >= 0 else 0)

            cmb.setVisible(True)
        except Exception:
            try:
                self._cmb_out.setVisible(False)
            except Exception:
                pass

    def _on_out_sel_changed(self, idx: int) -> None:
        # Apply output selection to the runtime Lv2Fx and persist into project params.
        try:
            cmb = getattr(self, '_cmb_out', None)
            if cmb is None or idx < 0:
                return
            data = cmb.itemData(int(idx))
            fx = self._get_runtime_fx()
            if fx is None:
                return

            if isinstance(data, list) and data and data[0] == 'auto':
                try:
                    sel = list(getattr(fx, 'get_auto_output_selection')() or [0, 1])
                except Exception:
                    sel = [0, 1]
                try:
                    if hasattr(fx, 'set_output_selection'):
                        fx.set_output_selection(sel)
                except Exception:
                    pass
                try:
                    _dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
                    if params is not None:
                        params.pop('__out_sel', None)
                except Exception:
                    pass
                try:
                    ps = getattr(self._services, 'project', None) if self._services is not None else None
                    if ps is not None and hasattr(ps, 'project_changed'):
                        ps.project_changed.emit()
                except Exception:
                    pass
                return

            if not (isinstance(data, list) and len(data) >= 2):
                return
            sel = [int(data[0]), int(data[1])]
            try:
                if hasattr(fx, 'set_output_selection'):
                    fx.set_output_selection(sel)
            except Exception:
                pass

            try:
                _dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
                if params is not None:
                    params['__out_sel'] = sel
            except Exception:
                pass
            try:
                ps = getattr(self._services, 'project', None) if self._services is not None else None
                if ps is not None and hasattr(ps, 'project_changed'):
                    ps.project_changed.emit()
            except Exception:
                pass
        except Exception:
            return

    def _safe_rebuild_fx_maps(self) -> None:
        """Rebuild FX maps from current project snapshot (SAFE UI action)."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            if ae is None or not hasattr(ae, "rebuild_fx_maps"):
                return
            _ps, proj, _t = _get_project_and_track(self._services, self._track_id)
            if proj is None:
                return
            ae.rebuild_fx_maps(proj)
        except Exception:
            return
        # Refresh DSP status label/button after rebuild
        try:
            self._update_dsp_status()
        except Exception:
            pass


    def _audition_make_obvious(self) -> None:
        """Make the LV2 effect clearly audible (best-effort).

        Many LV2 plugins ship with subtle defaults or start in BYPASS.
        This applies simple heuristics (BYPASS->off, WET/MIX->max, etc.).
        """
        try:
            for c in (self._controls or []):
                sym = str(getattr(c, 'symbol', '') or '')
                if not sym or sym not in self._rows:
                    continue
                _row, sld, spn, (mn, mx, _df) = self._rows[sym]
                nm = str(getattr(c, 'name', '') or '')
                key = (sym + ' ' + nm).lower()

                target = None

                if 'bypass' in key:
                    target = mn
                elif ('dry/wet' in key) or ('dry_wet' in key) or ('drywet' in key):
                    # more wet (common convention: 0=dry, 1=wet)
                    target = mx
                elif ('wet_dry' in key) or ('wetdry' in key):
                    # more wet (some plugins use wet->dry fader)
                    target = mn
                elif (('mix' in key) or ('wet' in key)) and ('wet_dry' not in key and 'dry_wet' not in key):
                    target = mx
                elif ('dry' in key) and ('wet_dry' not in key and 'dry_wet' not in key):
                    target = mn
                elif 'feedback' in key:
                    target = mn + 0.75 * (mx - mn)
                elif 'depth' in key:
                    target = mx
                elif 'drive' in key:
                    target = mn + 0.70 * (mx - mn)
                elif ('level' in key or 'output' in key) and (mx - mn) <= 1.01:
                    target = mn + 0.85 * (mx - mn)

                if target is None:
                    continue

                try:
                    target = float(target)
                except Exception:
                    continue
                if target < mn:
                    target = mn
                if target > mx:
                    target = mx

                try:
                    pos = 0
                    if mx > mn:
                        pos = int(round(((target - mn) / (mx - mn)) * 1000.0))
                    with QSignalBlocker(sld):
                        sld.setValue(max(0, min(1000, pos)))
                    with QSignalBlocker(spn):
                        spn.setValue(float(target))
                except Exception:
                    pass

                self._set_value(sym, float(target))

            try:
                self._debounce.start()
            except Exception:
                pass
        except Exception:
            pass

    def _update_dsp_status(self) -> None:
        try:
            active = bool(self._dsp_is_active())
            if active:
                self._lbl_dsp.setText("DSP: ACTIVE")
                self._btn_rebuild.setVisible(False)
                try:
                    self._update_output_selector()
                except Exception:
                    pass
            else:
                # If Safe Mode blocked this plugin (probe crash/fail), show that explicitly.
                try:
                    from pydaw.audio import lv2_host
                    st, msg = lv2_host.get_probe_status(self._uri)
                    if lv2_host.safe_mode_enabled() and st == "blocked":
                        # keep short
                        short = (msg or "blocked").strip()
                        short = " ".join(short.split())
                        if len(short) > 80:
                            short = short[:77] + "…"
                        self._lbl_dsp.setText("DSP: BLOCKED (Safe Mode) — " + short)
                        self._btn_rebuild.setVisible(False)
                        return
                except Exception:
                    pass

                try:
                    self._cmb_out.setVisible(False)
                except Exception:
                    pass

                self._lbl_dsp.setText("DSP: INACTIVE (no audible effect) — try Rebuild FX")
                # Show the button only if LV2 hosting is available; otherwise user needs deps.
                try:
                    from pydaw.audio import lv2_host
                    self._btn_rebuild.setVisible(bool(lv2_host.is_available()))
                except Exception:
                    self._btn_rebuild.setVisible(True)
        except Exception:
            pass

    def _load_controls_and_build_rows(self) -> None:
        # clear
        while self._body_l.count():
            it = self._body_l.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

        self._rows.clear()
        self._controls = []

        # query LV2
        try:
            from pydaw.audio import lv2_host
            avail = False
            try:
                avail = bool(lv2_host.is_available())
            except Exception:
                avail = False

            # Always try to build a parameter UI:
            # - best: python-lilv available
            # - fallback: lv2info parsing (UI-only) when python-lilv can't be imported
            try:
                self._controls = lv2_host.describe_controls(self._uri)
            except Exception:
                self._controls = []

            if not avail:
                # show actionable hint, but still allow UI fallback rows if we found controls
                hint = lv2_host.availability_hint()
                if self._controls:
                    hint = hint + "\n(Param-UI geladen; live processing bleibt deaktiviert.)"
                self._lbl_hint.setText(hint)
            else:
                self._lbl_hint.setText("OK")
        except Exception:
            self._controls = []

        if not self._controls:
            self._lbl_hint.setText("Keine LV2 Controls gefunden (Plugin URI ok? python-lilv installiert?).")
            return
        if "avail" in locals() and avail:
            # Show Safe Mode probe status (cache-only; does not run the probe here).
            try:
                st, msg = lv2_host.get_probe_status(self._uri)
                if lv2_host.safe_mode_enabled() and st == "blocked":
                    short = (msg or "blocked").strip()
                    short = " ".join(short.split())
                    if len(short) > 90:
                        short = short[:87] + "…"
                    self._lbl_hint.setText("Controls: " + str(len(self._controls)) + " — BLOCKED (Safe Mode): " + short)
                else:
                    self._lbl_hint.setText("Controls: " + str(len(self._controls)))
            except Exception:
                self._lbl_hint.setText("Controls: " + str(len(self._controls)))

        # Update DSP status AFTER we know the host availability
        self._update_dsp_status()

        for c in self._controls:
            sym = str(getattr(c, "symbol", "") or "")
            if not sym:
                continue
            nm = str(getattr(c, "name", sym) or sym)
            mn = float(getattr(c, "minimum", 0.0))
            mx = float(getattr(c, "maximum", 1.0))
            df = float(getattr(c, "default", 0.0))
            if mx <= mn:
                mx = mn + 1.0

            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)

            lbl = QLabel(nm)
            lbl.setMinimumWidth(130)
            lbl.setToolTip(sym)

            sld = QSlider(Qt.Orientation.Horizontal)
            sld.setRange(0, 1000)

            spn = QDoubleSpinBox()
            spn.setDecimals(4)
            spn.setRange(mn, mx)
            spn.setSingleStep((mx - mn) / 200.0)
            spn.setMaximumWidth(120)

            rl.addWidget(lbl, 0)
            rl.addWidget(sld, 1)
            rl.addWidget(spn, 0)

            self._body_l.addWidget(row)

            info = (mn, mx, df)
            self._rows[sym] = (row, sld, spn, info)
            pid = self._key(sym)
            _install_automation_menu(self, lbl, pid, lambda df=df: float(df))
            _install_automation_menu(self, sld, pid, lambda df=df: float(df))
            _install_automation_menu(self, spn, pid, lambda df=df: float(df))
            self._automation_params[sym] = _register_automatable_param(
                self._services, self._track_id, pid, nm, mn, mx, df
            )

            def _map_to_val(pos: int, mn=mn, mx=mx) -> float:
                return mn + (float(pos) / 1000.0) * (mx - mn)

            def _map_to_pos(val: float, mn=mn, mx=mx) -> int:
                if mx <= mn:
                    return 0
                t = (float(val) - mn) / (mx - mn)
                if t < 0.0:
                    t = 0.0
                if t > 1.0:
                    t = 1.0
                return int(round(t * 1000.0))

            def on_slider(v: int, sym=sym):
                row, sld2, spn2, info2 = self._rows.get(sym, (None, None, None, None))
                if sld2 is None or spn2 is None:
                    return
                val = _map_to_val(int(v))
                with QSignalBlocker(spn2):
                    spn2.setValue(val)
                self._set_value(sym, float(val))

            def on_spin(val: float, sym=sym):
                row, sld2, spn2, info2 = self._rows.get(sym, (None, None, None, None))
                if sld2 is None:
                    return
                with QSignalBlocker(sld2):
                    sld2.setValue(_map_to_pos(float(val)))
                self._set_value(sym, float(val))

            sld.valueChanged.connect(on_slider)
            spn.valueChanged.connect(on_spin)

        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _apply_filter(self, text: str) -> None:
        q = str(text or "").strip().lower()
        for sym, (row, _sld, _spn, _info) in self._rows.items():
            try:
                nm = row.findChild(QLabel).text().lower() if row is not None else ""
            except Exception:
                nm = ""
            show = (not q) or (q in sym.lower()) or (q in nm)
            try:
                row.setVisible(bool(show))
            except Exception:
                pass

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        for sym, (_row, sld, spn, (mn, mx, _df)) in self._rows.items():
            if pid != self._key(sym):
                continue
            val = float(max(mn, min(mx, float(value))))
            pos = 0
            if mx > mn:
                pos = int(round(((val - mn) / (mx - mn)) * 1000.0))
            with QSignalBlocker(sld):
                sld.setValue(max(0, min(1000, pos)))
            with QSignalBlocker(spn):
                spn.setValue(val)
            self._set_value(sym, val, update_param=False)
            break

    def _set_value(self, symbol: str, value: float, update_param: bool = True) -> None:
        # RT write
        rt = self._rt()
        try:
            if rt is not None:
                rt.set_param(self._key(symbol), float(value))
        except Exception:
            pass
        if update_param:
            try:
                param = self._automation_params.get(str(symbol))
                if param is not None:
                    param.set_value(float(value))
            except Exception:
                pass
        # persist
        try:
            dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
            if params is not None:
                params[str(symbol)] = float(value)
        except Exception:
            pass
        self._debounce.start()

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
        if params is None:
            return
        rt = self._rt()

        # seed defaults
        for c in (self._controls or []):
            sym = str(getattr(c, "symbol", "") or "")
            if not sym or sym not in self._rows:
                continue
            row, sld, spn, (mn, mx, df) = self._rows[sym]
            try:
                val = float(params.get(sym, df))
            except Exception:
                val = df
            # clamp
            if val < mn:
                val = mn
            if val > mx:
                val = mx

            # UI
            try:
                # map
                pos = 0
                if mx > mn:
                    pos = int(round(((val - mn) / (mx - mn)) * 1000.0))
                with QSignalBlocker(sld):
                    sld.setValue(max(0, min(1000, pos)))
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            except Exception:
                pass

            # RT
            try:
                if rt is not None and hasattr(rt, "ensure"):
                    rt.ensure(self._key(sym), float(val))
                elif rt is not None:
                    rt.set_param(self._key(sym), float(val))
            except Exception:
                pass

    def _flush_to_project(self) -> None:
        """Notify about persisted LV2 parameter changes (SAFE).

        Important UX note:
        The DevicePanel listens to `ProjectService.project_updated` and will
        rebuild the entire device chain UI on every emission.

        LV2 plugins can expose *many* parameters. Emitting `project_updated`
        while the user drags a slider will destroy/recreate this widget and the
        controls appear to "snap back".

        For LV2 parameter tweaks we therefore only emit `project_changed`
        (dirty indicator/window title) and avoid a full device-panel rebuild.
        """
        ps = getattr(self._services, "project", None) if self._services is not None else None
        try:
            if ps is not None and hasattr(ps, "project_changed"):
                ps.project_changed.emit()
        except Exception:
            pass


class _NoteFxBase(QWidget):
    """Small helper base with debounced project writes.

    v0.0.20.568: Added _install_param_context_menu for Rechtsklick support.
    """
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._flush)

    def _emit_updated(self) -> None:
        ps = getattr(self._services, "project", None) if self._services is not None else None
        try:
            if ps is not None and hasattr(ps, "project_updated"):
                ps.project_updated.emit()
        except Exception:
            pass

    def _flush(self) -> None:
        # implemented by subclasses
        self._emit_updated()

    def _install_param_context_menu(self, widget: QWidget, param_name: str,
                                      display_name: str = "") -> None:
        """v0.0.20.568: Rechtsklick-Menü für Note-FX Parameter.
        Adds Show Automation + MIDI Learn + Reset."""
        param_id = f"nfx:{self._track_id}:{self._device_id}:{param_name}"
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, _pid=param_id, _w=widget, _dn=display_name or param_name:
                self._show_notefx_context_menu(_w, pos, _pid, _dn)
        )

    def _show_notefx_context_menu(self, widget: QWidget, pos, param_id: str,
                                    display_name: str) -> None:
        am = _get_automation_manager(self._services)
        menu = QMenu(self)

        a_show = menu.addAction(f"Show Automation in Arranger")
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
            try:
                am.request_show_automation.emit(str(param_id))
            except Exception:
                pass
        elif chosen == a_reset:
            try:
                param = am.get_parameter(str(param_id)) if am else None
                if param is not None:
                    param.set_value(param.default_val)
                    param.set_automation_value(None)
            except Exception:
                pass
        elif chosen == a_midi_learn and am is not None:
            try:
                midi_svc = getattr(self._services, "midi", None) if self._services else None
                if midi_svc is not None and hasattr(midi_svc, "cancel_learn"):
                    midi_svc.cancel_learn()
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
        elif chosen == a_midi_remove:
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


class TransposeNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(QLabel("Semitones"), 0)
        self.spn = QSpinBox(); self.spn.setRange(-24, 24); self.spn.setValue(0)
        row.addWidget(self.spn, 0)
        row.addStretch(1)
        root.addLayout(row)
        self.spn.valueChanged.connect(lambda _: self._debounce.start())
        self.refresh_from_project()
        self._install_param_context_menu(self.spn, "semitones", "Transpose Semitones")

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        val = int(params.get("semitones", 0) or 0)
        self.spn.blockSignals(True)
        try:
            self.spn.setValue(val)
        finally:
            self.spn.blockSignals(False)

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["semitones"] = int(self.spn.value())
        self._emit_updated()


class VelocityScaleNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(QLabel("Vel Scale"), 0)
        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setRange(0, 200)  # 0..2.0
        self.spn = QDoubleSpinBox()
        self.spn.setRange(0.0, 2.0)
        self.spn.setSingleStep(0.01)
        self.spn.setDecimals(2)
        self.spn.setMaximumWidth(90)
        row.addWidget(self.sld, 1)
        row.addWidget(self.spn, 0)
        root.addLayout(row)

        self.sld.valueChanged.connect(self._on_sld)
        self.spn.valueChanged.connect(self._on_spn)
        self.refresh_from_project()
        self._install_param_context_menu(self.sld, 'vel_scale', 'Velocity Scale')
        self._install_param_context_menu(self.spn, 'vel_scale_spin', 'Velocity Scale')

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        x = float(params.get("scale", 1.0) or 1.0)
        x = max(0.0, min(2.0, x))
        self.sld.blockSignals(True); self.spn.blockSignals(True)
        try:
            self.sld.setValue(int(round(x * 100.0)))
            self.spn.setValue(x)
        finally:
            self.sld.blockSignals(False); self.spn.blockSignals(False)

    def _on_sld(self, v: int) -> None:
        x = float(v) / 100.0
        self.spn.blockSignals(True)
        try:
            self.spn.setValue(x)
        finally:
            self.spn.blockSignals(False)
        self._debounce.start()

    def _on_spn(self, x: float) -> None:
        x = max(0.0, min(2.0, float(x)))
        self.sld.blockSignals(True)
        try:
            self.sld.setValue(int(round(x * 100.0)))
        finally:
            self.sld.blockSignals(False)
        self._debounce.start()

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["scale"] = float(self.spn.value())
        self._emit_updated()


class ScaleSnapNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)

        r1 = QHBoxLayout(); r1.setSpacing(6)
        r1.addWidget(QLabel("Root"), 0)
        self.cmb_root = QComboBox()
        self._roots = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        self.cmb_root.addItems(self._roots)
        r1.addWidget(self.cmb_root, 0)
        r1.addWidget(QLabel("Scale"), 0)
        self.cmb_scale = QComboBox()
        self.cmb_scale.addItems(["major","minor","dorian","phrygian","lydian","mixolydian","locrian","pentatonic","chromatic"])
        r1.addWidget(self.cmb_scale, 1)
        root.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(6)
        r2.addWidget(QLabel("Mode"), 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["nearest","down","up"])
        r2.addWidget(self.cmb_mode, 0)
        r2.addStretch(1)
        root.addLayout(r2)

        self.cmb_root.currentIndexChanged.connect(lambda _: self._debounce.start())
        self.cmb_scale.currentIndexChanged.connect(lambda _: self._debounce.start())
        self.cmb_mode.currentIndexChanged.connect(lambda _: self._debounce.start())

        self.refresh_from_project()

        self._install_param_context_menu(self.cmb_root, 'root', 'Scale Root')
        self._install_param_context_menu(self.cmb_scale, 'scale', 'Scale Type')
    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        root_pc = int(params.get("root", 0) or 0) % 12
        scale = str(params.get("scale", "major") or "major")
        mode = str(params.get("mode", "nearest") or "nearest")
        self.cmb_root.blockSignals(True); self.cmb_scale.blockSignals(True); self.cmb_mode.blockSignals(True)
        try:
            self.cmb_root.setCurrentIndex(max(0, min(11, root_pc)))
            self.cmb_scale.setCurrentText(scale if scale in [self.cmb_scale.itemText(i) for i in range(self.cmb_scale.count())] else "major")
            self.cmb_mode.setCurrentText(mode if mode in [self.cmb_mode.itemText(i) for i in range(self.cmb_mode.count())] else "nearest")
        finally:
            self.cmb_root.blockSignals(False); self.cmb_scale.blockSignals(False); self.cmb_mode.blockSignals(False)

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["root"] = int(self.cmb_root.currentIndex()) % 12
        params["scale"] = str(self.cmb_scale.currentText() or "major")
        params["mode"] = str(self.cmb_mode.currentText() or "nearest")
        self._emit_updated()


class ChordNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)

        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(QLabel("Chord"), 0)
        self.cmb = QComboBox()
        self.cmb.addItems(["maj","min","power","maj7","min7","dim","aug"])
        row.addWidget(self.cmb, 1)
        root.addLayout(row)

        self.cmb.currentIndexChanged.connect(lambda _: self._debounce.start())
        self.refresh_from_project()

        self._install_param_context_menu(self.cmb, 'chord_type', 'Chord Type')
    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        ch = str(params.get("chord", "maj") or "maj")
        self.cmb.blockSignals(True)
        try:
            self.cmb.setCurrentText(ch if ch in [self.cmb.itemText(i) for i in range(self.cmb.count())] else "maj")
        finally:
            self.cmb.blockSignals(False)

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["chord"] = str(self.cmb.currentText() or "maj")
        self._emit_updated()


class ArpNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)

        r1 = QHBoxLayout(); r1.setSpacing(6)
        r1.addWidget(QLabel("Step"), 0)
        self.cmb_step = QComboBox()
        self._steps = [0.125, 0.25, 0.5, 1.0]
        self.cmb_step.addItems([f"{s:g}" for s in self._steps])
        r1.addWidget(self.cmb_step, 0)
        r1.addWidget(QLabel("Mode"), 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["up","down","updown","random"])
        r1.addWidget(self.cmb_mode, 1)
        root.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(6)
        r2.addWidget(QLabel("Oct"), 0)
        self.spn_oct = QSpinBox(); self.spn_oct.setRange(1, 4); self.spn_oct.setValue(1)
        r2.addWidget(self.spn_oct, 0)
        r2.addWidget(QLabel("Gate"), 0)
        self.sld_gate = QSlider(Qt.Orientation.Horizontal); self.sld_gate.setRange(10, 100); self.sld_gate.setValue(90)
        self.spn_gate = QDoubleSpinBox(); self.spn_gate.setRange(0.10, 1.00); self.spn_gate.setSingleStep(0.01); self.spn_gate.setDecimals(2); self.spn_gate.setMaximumWidth(80)
        r2.addWidget(self.sld_gate, 1)
        r2.addWidget(self.spn_gate, 0)
        root.addLayout(r2)

        self.cmb_step.currentIndexChanged.connect(lambda _: self._debounce.start())
        self.cmb_mode.currentIndexChanged.connect(lambda _: self._debounce.start())
        self.spn_oct.valueChanged.connect(lambda _: self._debounce.start())
        self.sld_gate.valueChanged.connect(self._on_gate_sld)
        self.spn_gate.valueChanged.connect(self._on_gate_spn)

        self.refresh_from_project()

        self._install_param_context_menu(self.cmb_step, 'arp_step', 'Arp Step')
        self._install_param_context_menu(self.cmb_mode, 'arp_mode', 'Arp Mode')
        self._install_param_context_menu(self.spn_oct, 'arp_octaves', 'Arp Octaves')
    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        step = float(params.get("step_beats", 0.5) or 0.5)
        mode = str(params.get("mode", "up") or "up")
        octv = int(params.get("octaves", 1) or 1)
        gate = float(params.get("gate", 0.9) or 0.9)
        # normalize
        try:
            idx = min(range(len(self._steps)), key=lambda i: abs(self._steps[i] - step))
        except Exception:
            idx = 2
        gate = max(0.10, min(1.00, gate))
        self.cmb_step.blockSignals(True); self.cmb_mode.blockSignals(True)
        self.spn_oct.blockSignals(True); self.sld_gate.blockSignals(True); self.spn_gate.blockSignals(True)
        try:
            self.cmb_step.setCurrentIndex(int(idx))
            self.cmb_mode.setCurrentText(mode if mode in [self.cmb_mode.itemText(i) for i in range(self.cmb_mode.count())] else "up")
            self.spn_oct.setValue(max(1, min(4, octv)))
            self.sld_gate.setValue(int(round(gate * 100.0)))
            self.spn_gate.setValue(gate)
        finally:
            self.cmb_step.blockSignals(False); self.cmb_mode.blockSignals(False)
            self.spn_oct.blockSignals(False); self.sld_gate.blockSignals(False); self.spn_gate.blockSignals(False)

    def _on_gate_sld(self, v: int) -> None:
        x = max(0.10, min(1.00, float(v) / 100.0))
        self.spn_gate.blockSignals(True)
        try:
            self.spn_gate.setValue(x)
        finally:
            self.spn_gate.blockSignals(False)
        self._debounce.start()

    def _on_gate_spn(self, x: float) -> None:
        x = max(0.10, min(1.00, float(x)))
        self.sld_gate.blockSignals(True)
        try:
            self.sld_gate.setValue(int(round(x * 100.0)))
        finally:
            self.sld_gate.blockSignals(False)
        self._debounce.start()

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["step_beats"] = float(self._steps[int(self.cmb_step.currentIndex())]) if self.cmb_step.currentIndex() >= 0 else 0.5
        params["mode"] = str(self.cmb_mode.currentText() or "up")
        params["octaves"] = int(self.spn_oct.value())
        params["gate"] = float(self.spn_gate.value())
        self._emit_updated()


class RandomNoteFxWidget(_NoteFxBase):
    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(4)

        r1 = QHBoxLayout(); r1.setSpacing(6)
        r1.addWidget(QLabel("Pitch ±"), 0)
        self.spn_pr = QSpinBox(); self.spn_pr.setRange(0, 24); self.spn_pr.setValue(0)
        r1.addWidget(self.spn_pr, 0)
        r1.addWidget(QLabel("Vel ±"), 0)
        self.spn_vr = QSpinBox(); self.spn_vr.setRange(0, 127); self.spn_vr.setValue(0)
        r1.addWidget(self.spn_vr, 0)
        r1.addStretch(1)
        root.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(6)
        r2.addWidget(QLabel("Prob"), 0)
        self.sld_pb = QSlider(Qt.Orientation.Horizontal); self.sld_pb.setRange(0, 100); self.sld_pb.setValue(100)
        self.spn_pb = QDoubleSpinBox(); self.spn_pb.setRange(0.0, 1.0); self.spn_pb.setSingleStep(0.01); self.spn_pb.setDecimals(2); self.spn_pb.setMaximumWidth(80)
        r2.addWidget(self.sld_pb, 1)
        r2.addWidget(self.spn_pb, 0)
        root.addLayout(r2)

        self.spn_pr.valueChanged.connect(lambda _: self._debounce.start())
        self.spn_vr.valueChanged.connect(lambda _: self._debounce.start())
        self.sld_pb.valueChanged.connect(self._on_pb_sld)
        self.spn_pb.valueChanged.connect(self._on_pb_spn)

        self.refresh_from_project()

        self._install_param_context_menu(self.spn_pr, 'pitch_range', 'Pitch Range')
        self._install_param_context_menu(self.spn_vr, 'vel_range', 'Velocity Range')
        self._install_param_context_menu(self.sld_pb, 'probability', 'Probability')
    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        pr = int(params.get("pitch_range", 0) or 0)
        vr = int(params.get("vel_range", 0) or 0)
        pb = float(params.get("prob", 1.0) or 1.0)
        pr = max(0, min(24, pr))
        vr = max(0, min(127, vr))
        pb = max(0.0, min(1.0, pb))
        self.spn_pr.blockSignals(True); self.spn_vr.blockSignals(True)
        self.sld_pb.blockSignals(True); self.spn_pb.blockSignals(True)
        try:
            self.spn_pr.setValue(pr)
            self.spn_vr.setValue(vr)
            self.sld_pb.setValue(int(round(pb * 100.0)))
            self.spn_pb.setValue(pb)
        finally:
            self.spn_pr.blockSignals(False); self.spn_vr.blockSignals(False)
            self.sld_pb.blockSignals(False); self.spn_pb.blockSignals(False)

    def _on_pb_sld(self, v: int) -> None:
        x = max(0.0, min(1.0, float(v) / 100.0))
        self.spn_pb.blockSignals(True)
        try:
            self.spn_pb.setValue(x)
        finally:
            self.spn_pb.blockSignals(False)
        self._debounce.start()

    def _on_pb_spn(self, x: float) -> None:
        x = max(0.0, min(1.0, float(x)))
        self.sld_pb.blockSignals(True)
        try:
            self.sld_pb.setValue(int(round(x * 100.0)))
        finally:
            self.sld_pb.blockSignals(False)
        self._debounce.start()

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        params["pitch_range"] = int(self.spn_pr.value())
        params["vel_range"] = int(self.spn_vr.value())
        params["prob"] = float(self.spn_pb.value())
        self._emit_updated()


class AiComposerNoteFxWidget(_NoteFxBase):
    """Algorithmic MIDI composition engine (as Note-FX tool).

    Important UX constraints:
    - must never freeze the UI on load/refresh
    - must be fully visible / scrollable inside the device card

    This device does not apply processing in the audio engine yet. It is a
    *generator* UI: it writes MIDI notes into the selected clip or creates a new
    clip on the track.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, parent=None):
        super().__init__(services, track_id, device_id, parent)

        from pydaw.music.ai_composer import GENRES, CONTEXTS, FORMS, INSTRUMENT_SETUPS

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Inside the DevicePanel chain, cards don't have vertical scroll.
        # Therefore, this widget must be self-scrollable to avoid clipped UI.
        content_parent = self
        if QScrollArea is not None:
            self._scroll = QScrollArea(self)
            self._scroll.setWidgetResizable(True)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            try:
                self._scroll.verticalScrollBar().setSingleStep(18)
            except Exception:
                pass
            content = QWidget(self._scroll)
            self._scroll.setWidget(content)
            outer.addWidget(self._scroll, 1)
            content_parent = content
        else:
            self._scroll = None

        root = QVBoxLayout(content_parent)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # --- Controls
        box = QGroupBox("AI Composer — MIDI Generation")
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)
        try:
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        except Exception:
            pass

        # Genres: use editable comboboxes so *any* genre can be typed.
        self.cmb_genre_a = QComboBox()
        self.cmb_genre_a.setEditable(True)
        try:
            self.cmb_genre_a.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        except Exception:
            pass
        self.cmb_genre_a.addItems(list(GENRES) + ["Custom"])

        self.txt_genre_a = QLineEdit()
        self.txt_genre_a.setPlaceholderText("Custom Genre A …")
        self._lab_custom_a = QLabel("Custom A")

        self.cmb_genre_b = QComboBox()
        self.cmb_genre_b.setEditable(True)
        try:
            self.cmb_genre_b.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        except Exception:
            pass
        self.cmb_genre_b.addItems(list(GENRES) + ["Custom"])

        self.txt_genre_b = QLineEdit()
        self.txt_genre_b.setPlaceholderText("Custom Genre B …")
        self._lab_custom_b = QLabel("Custom B")

        self.cmb_context = QComboBox(); self.cmb_context.addItems(list(CONTEXTS))
        self.cmb_form = QComboBox(); self.cmb_form.addItems(list(FORMS))
        self.cmb_instr = QComboBox(); self.cmb_instr.addItems(list(INSTRUMENT_SETUPS))

        self.spn_bars = QSpinBox(); self.spn_bars.setRange(1, 64); self.spn_bars.setValue(8)

        # Grid in beats: 1/16=0.25, 1/8=0.5, 1/4=1.0
        self.cmb_grid = QComboBox()
        self._grid_map = {
            "1/16": 0.25,
            "1/8": 0.5,
            "1/4": 1.0,
            "1/32": 0.125,
        }
        self.cmb_grid.addItems(list(self._grid_map.keys()))

        self.spn_swing = QDoubleSpinBox(); self.spn_swing.setRange(0.0, 1.0); self.spn_swing.setDecimals(2); self.spn_swing.setSingleStep(0.01)
        self.spn_density = QDoubleSpinBox(); self.spn_density.setRange(0.0, 1.0); self.spn_density.setDecimals(2); self.spn_density.setSingleStep(0.01)
        self.spn_hybrid = QDoubleSpinBox(); self.spn_hybrid.setRange(0.0, 1.0); self.spn_hybrid.setDecimals(2); self.spn_hybrid.setSingleStep(0.01)
        self.spn_seed = QSpinBox(); self.spn_seed.setRange(0, 2_000_000_000); self.spn_seed.setValue(1)

        form.addRow("Genre A (Struktur)", self.cmb_genre_a)
        form.addRow(self._lab_custom_a, self.txt_genre_a)
        form.addRow("Genre B (Rhythm)", self.cmb_genre_b)
        form.addRow(self._lab_custom_b, self.txt_genre_b)
        form.addRow("Kontext", self.cmb_context)
        form.addRow("Form", self.cmb_form)
        form.addRow("Instrument-Setup", self.cmb_instr)
        form.addRow("Länge (Bars)", self.spn_bars)
        form.addRow("Grid", self.cmb_grid)
        form.addRow("Swing", self.spn_swing)
        form.addRow("Density", self.spn_density)
        form.addRow("Hybrid (A↔B)", self.spn_hybrid)
        form.addRow("Seed", self.spn_seed)

        root.addWidget(box)

        # --- Hint
        self.lab_hint = QLabel(
            "Tipp: Genre A steuert Harmonik/Struktur (z.B. Barock/Fuge),\n"
            "Genre B steuert Rhythmus/Energie (z.B. Hardcore/Industrial).\n"
            "\nOutput: schreibt Noten in den ausgewählten MIDI-Clip oder erstellt einen neuen Clip auf der Spur."
        )
        self.lab_hint.setWordWrap(True)
        self.lab_hint.setStyleSheet("color:#7f7f7f; font-size:11px;")
        root.addWidget(self.lab_hint)

        # --- Actions (pinned below scroll)
        row = QHBoxLayout(); row.setSpacing(6)
        self.btn_generate = QPushButton("Generate → Clip")
        self.btn_overwrite = QPushButton("Overwrite Selected Clip")
        self.btn_snapshot_save = QPushButton("Save Snapshot…")
        self.btn_snapshot_load = QPushButton("Load Snapshot…")
        row.addWidget(self.btn_generate, 0)
        row.addWidget(self.btn_overwrite, 0)
        row.addStretch(1)
        row.addWidget(self.btn_snapshot_save, 0)
        row.addWidget(self.btn_snapshot_load, 0)
        outer.addLayout(row)

        # Wire changes → params (debounced)
        self.cmb_genre_a.currentTextChanged.connect(self._on_any_change)
        self.cmb_genre_b.currentTextChanged.connect(self._on_any_change)
        self.cmb_context.currentIndexChanged.connect(lambda _=0: self._on_any_change())
        self.cmb_form.currentIndexChanged.connect(lambda _=0: self._on_any_change())
        self.cmb_instr.currentIndexChanged.connect(lambda _=0: self._on_any_change())
        self.spn_bars.valueChanged.connect(lambda _=0: self._on_any_change())
        self.cmb_grid.currentIndexChanged.connect(lambda _=0: self._on_any_change())
        self.spn_swing.valueChanged.connect(lambda _=0: self._on_any_change())
        self.spn_density.valueChanged.connect(lambda _=0: self._on_any_change())
        self.spn_hybrid.valueChanged.connect(lambda _=0: self._on_any_change())
        self.spn_seed.valueChanged.connect(lambda _=0: self._on_any_change())
        self.txt_genre_a.textChanged.connect(lambda _="": self._on_any_change())
        self.txt_genre_b.textChanged.connect(lambda _="": self._on_any_change())

        # Actions
        self.btn_generate.clicked.connect(self._on_generate_new_clip)
        self.btn_overwrite.clicked.connect(self._on_overwrite_selected)
        self.btn_snapshot_save.clicked.connect(self._on_snapshot_save)
        self.btn_snapshot_load.clicked.connect(self._on_snapshot_load)

        self.refresh_from_project()
        self._update_custom_rows()

    def _on_any_change(self) -> None:
        # Keep UI responsive: update visibility without triggering loops.
        try:
            self._update_custom_rows()
        except Exception:
            pass
        self._debounce.start()

    def _update_custom_rows(self) -> None:
        """Show custom text fields only when explicitly requested.

        This keeps the card compact (often no vertical scroll needed) while still
        supporting arbitrary genres via editable comboboxes.
        """
        try:
            a_is_custom = str(self.cmb_genre_a.currentText() or "") == "Custom"
            b_is_custom = str(self.cmb_genre_b.currentText() or "") == "Custom"
            for w in (getattr(self, '_lab_custom_a', None), getattr(self, 'txt_genre_a', None)):
                if w is not None:
                    w.setVisible(bool(a_is_custom))
            for w in (getattr(self, '_lab_custom_b', None), getattr(self, 'txt_genre_b', None)):
                if w is not None:
                    w.setVisible(bool(b_is_custom))
        except Exception:
            pass

    def _params_from_ui(self) -> dict:
        return {
            "genre_a": str(self.cmb_genre_a.currentText()),
            "genre_b": str(self.cmb_genre_b.currentText()),
            "custom_genre_a": str(self.txt_genre_a.text() or ""),
            "custom_genre_b": str(self.txt_genre_b.text() or ""),
            "context": str(self.cmb_context.currentText()),
            "form": str(self.cmb_form.currentText()),
            "instrument_setup": str(self.cmb_instr.currentText()),
            "bars": int(self.spn_bars.value()),
            "grid": float(self._grid_map.get(str(self.cmb_grid.currentText()), 0.25)),
            "swing": float(self.spn_swing.value()),
            "density": float(self.spn_density.value()),
            "hybrid": float(self.spn_hybrid.value()),
            "seed": int(self.spn_seed.value()),
        }

    def _key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _bind_automation(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        """Refresh without re-entrancy loops.

        IMPORTANT: do *not* rely on self.blockSignals(True) because it does not
        block child widget signals. Use QSignalBlocker per widget.
        """
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return

        def _set_combo_text(cmb: QComboBox, value: str) -> None:
            try:
                ix = cmb.findText(str(value))
                if ix >= 0:
                    cmb.setCurrentIndex(ix)
                else:
                    # editable combobox: allow arbitrary text
                    cmb.setCurrentText(str(value))
            except Exception:
                try:
                    cmb.setCurrentText(str(value))
                except Exception:
                    pass

        blockers = []
        try:
            blockers = [
                QSignalBlocker(self.cmb_genre_a),
                QSignalBlocker(self.txt_genre_a),
                QSignalBlocker(self.cmb_genre_b),
                QSignalBlocker(self.txt_genre_b),
                QSignalBlocker(self.cmb_context),
                QSignalBlocker(self.cmb_form),
                QSignalBlocker(self.cmb_instr),
                QSignalBlocker(self.spn_bars),
                QSignalBlocker(self.cmb_grid),
                QSignalBlocker(self.spn_swing),
                QSignalBlocker(self.spn_density),
                QSignalBlocker(self.spn_hybrid),
                QSignalBlocker(self.spn_seed),
            ]
        except Exception:
            blockers = []

        try:
            _set_combo_text(self.cmb_genre_a, str(params.get("genre_a", "Barock (Bach/Fuge)")))
            _set_combo_text(self.cmb_genre_b, str(params.get("genre_b", "Electro")))
            self.txt_genre_a.setText(str(params.get("custom_genre_a", "") or ""))
            self.txt_genre_b.setText(str(params.get("custom_genre_b", "") or ""))
            _set_combo_text(self.cmb_context, str(params.get("context", "Neutral")))
            _set_combo_text(self.cmb_form, str(params.get("form", "Mini-Fuge (Subject/Answer)")))
            _set_combo_text(self.cmb_instr, str(params.get("instrument_setup", "Kammermusik-Setup")))
            self.spn_bars.setValue(int(params.get("bars", 8) or 8))

            grid_val = float(params.get("grid", 0.25) or 0.25)
            best_k = "1/16"; best_d = 999.0
            for k, v in self._grid_map.items():
                d = abs(float(v) - grid_val)
                if d < best_d:
                    best_k, best_d = k, d
            _set_combo_text(self.cmb_grid, best_k)

            self.spn_swing.setValue(float(params.get("swing", 0.0) or 0.0))
            self.spn_density.setValue(float(params.get("density", 0.65) or 0.65))
            self.spn_hybrid.setValue(float(params.get("hybrid", 0.55) or 0.55))
            self.spn_seed.setValue(int(params.get("seed", 1) or 1))
        finally:
            blockers = []

        self._update_custom_rows()

    def _flush(self) -> None:
        dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
        if dev is None:
            return
        newp = self._params_from_ui()
        # Only emit project_updated if something actually changed.
        changed = False
        try:
            for k, v in newp.items():
                if params.get(k) != v:
                    changed = True
                    break
        except Exception:
            changed = True
        if not changed:
            return
        params.update(newp)
        self._emit_updated()

    # --- actions

    def _get_time_signature(self) -> str:
        ps = getattr(self._services, "project", None) if self._services is not None else None
        try:
            return str(getattr(ps.ctx.project, "time_signature", "4/4") or "4/4")
        except Exception:
            return "4/4"

    def _on_generate_new_clip(self) -> None:
        """Create a new MIDI clip on this track and fill it."""
        ps = getattr(self._services, "project", None) if self._services is not None else None
        if ps is None:
            return

        try:
            # Place at playhead if available, else bar 1
            transport = getattr(self._services, "transport", None) if self._services is not None else None
            start = float(getattr(transport, "current_beat", 0.0) if transport is not None else 0.0)
        except Exception:
            start = 0.0

        try:
            clip_id = ps.add_midi_clip_at(str(self._track_id), start_beats=float(start), length_beats=4.0, label="AI Clip")
        except Exception as e:
            try:
                QMessageBox.warning(self, "AI Composer", f"Konnte Clip nicht erstellen: {e}")
            except Exception:
                pass
            return

        self._render_into_clip(str(clip_id), overwrite=True)

    def _on_overwrite_selected(self) -> None:
        ps = getattr(self._services, "project", None) if self._services is not None else None
        if ps is None:
            return
        clip_id = ""
        try:
            clip_id = str(ps.active_clip_id() or "")
        except Exception:
            clip_id = str(getattr(ps, "_active_clip_id", "") or "")
        if not clip_id:
            try:
                QMessageBox.information(self, "AI Composer", "Kein Clip ausgewählt. Nutze 'Generate → Clip' oder wähle einen MIDI-Clip.")
            except Exception:
                pass
            return
        self._render_into_clip(str(clip_id), overwrite=True)

    def _render_into_clip(self, clip_id: str, *, overwrite: bool = True) -> None:
        ps = getattr(self._services, "project", None) if self._services is not None else None
        if ps is None:
            return
        try:
            from pydaw.music.ai_composer import ComposerParams, generate_clip_notes
            p = self._params_from_ui()
            params = ComposerParams(
                genre_a=str(p.get("genre_a", "Barock (Bach/Fuge)")),
                genre_b=str(p.get("genre_b", "Electro")),
                custom_genre_a=str(p.get("custom_genre_a", "")),
                custom_genre_b=str(p.get("custom_genre_b", "")),
                context=str(p.get("context", "Neutral")),
                form=str(p.get("form", "Mini-Fuge (Subject/Answer)")),
                instrument_setup=str(p.get("instrument_setup", "Kammermusik-Setup")),
                bars=int(p.get("bars", 8) or 8),
                grid=float(p.get("grid", 0.25) or 0.25),
                swing=float(p.get("swing", 0.0) or 0.0),
                density=float(p.get("density", 0.65) or 0.65),
                hybrid=float(p.get("hybrid", 0.55) or 0.55),
                seed=int(p.get("seed", 1) or 1),
            )

            ts = self._get_time_signature()
            start = 0.0
            new_notes = generate_clip_notes(start_beats=float(start), time_signature=ts, params=params)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AI Composer", f"Komposition fehlgeschlagen: {e}")
            except Exception:
                pass
            return

        try:
            before = ps.snapshot_midi_notes(str(clip_id))
        except Exception:
            before = []

        try:
            if overwrite:
                ps.set_midi_notes(str(clip_id), list(new_notes))
            else:
                cur = list(ps.get_midi_notes(str(clip_id)) or [])
                cur.extend(list(new_notes))
                ps.set_midi_notes(str(clip_id), cur)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AI Composer", f"Konnte Noten nicht schreiben: {e}")
            except Exception:
                pass
            return

        # register undo step for the MIDI note edit
        try:
            ps.commit_midi_notes_edit(str(clip_id), before=before, label="AI Composer")
        except Exception:
            # fallback: emit update
            try:
                ps.project_updated.emit()
            except Exception:
                pass

    def _on_snapshot_save(self) -> None:
        try:
            path, _ = QFileDialog.getSaveFileName(self, "AI Composer Snapshot speichern", "ai_composer_snapshot.json", "JSON (*.json)")
            if not path:
                return
            import json
            with open(str(path), "w", encoding="utf-8") as f:
                json.dump(self._params_from_ui(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            try:
                QMessageBox.warning(self, "AI Composer", f"Snapshot speichern fehlgeschlagen: {e}")
            except Exception:
                pass

    def _on_snapshot_load(self) -> None:
        try:
            path, _ = QFileDialog.getOpenFileName(self, "AI Composer Snapshot laden", "", "JSON (*.json)")
            if not path:
                return
            import json
            with open(str(path), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return

            # write into device params (single source of truth)
            dev, params = _find_note_fx_dev(self._services, self._track_id, self._device_id)
            if dev is None:
                return
            params.update({k: data.get(k) for k in data.keys()})
            self.refresh_from_project()
            self._emit_updated()
        except Exception as e:
            try:
                QMessageBox.warning(self, "AI Composer", f"Snapshot laden fehlgeschlagen: {e}")
            except Exception:
                pass


class LadspaAudioFxWidget(QWidget):
    """Generic LADSPA/DSSI Audio-FX parameter widget.

    - Reads LADSPA control ports via ctypes (ladspa_host.py).
    - Writes to RTParamStore (smooth) and persists values into device params.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, plugin_id: str, so_path: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._plugin_id = str(plugin_id or "")
        self._so_path = str(so_path or "")

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._flush_to_project)

        self._controls: list = []  # LadspaPortInfo list
        self._rows: dict = {}  # port_index -> (row_widget, slider, spin, (mn, mx, df))
        self._automation_params: dict = {}
        self._automation_connected = False
        self._ui_sync_timer = QTimer(self)
        self._ui_sync_timer.setInterval(50)
        self._ui_sync_timer.timeout.connect(self._sync_from_rt)
        try:
            self.destroyed.connect(self._disconnect_automation)
        except Exception:
            pass

        self._build()

    def _rt(self):
        ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
        return getattr(ae, "rt_params", None) if ae is not None else None

    def _disconnect_automation(self, *_args) -> None:
        am = _get_automation_manager(self._services)
        if am is not None and self._automation_connected:
            try:
                am.parameter_changed.disconnect(self._on_automation_changed)
            except Exception:
                pass
        self._automation_connected = False

    def _key(self, port_index: int) -> str:
        return f"afx:{self._track_id}:{self._device_id}:ladspa:{port_index}"

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Header
        top = QHBoxLayout()
        kind = "LADSPA" if "ladspa" in self._plugin_id.lower() else "DSSI"
        lab = QLabel(kind)
        lab.setStyleSheet("font-weight: 600;")
        top.addWidget(lab, 0)

        # Show path
        short_path = os.path.basename(self._so_path) if self._so_path else "(unknown)"
        self._lbl_path = QLabel(short_path)
        self._lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl_path.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        top.addWidget(self._lbl_path, 1)
        root.addLayout(top)

        # Status row
        self._row_status = QHBoxLayout()
        self._lbl_dsp = QLabel("")
        self._lbl_dsp.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        self._row_status.addWidget(self._lbl_dsp, 1)

        self._btn_rebuild = QPushButton("Rebuild FX")
        self._btn_rebuild.setToolTip("Rebuild per-track Audio-FX maps (safe).")
        self._btn_rebuild.clicked.connect(self._safe_rebuild_fx_maps)
        self._btn_rebuild.setVisible(False)
        self._row_status.addWidget(self._btn_rebuild, 0)
        root.addLayout(self._row_status)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search parameter…")
        self._search.textChanged.connect(self._apply_filter)
        root.addWidget(self._search)

        # Scroll area for controls
        if QScrollArea is not None:
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            self._body = QWidget()
            self._body_l = QVBoxLayout(self._body)
            self._body_l.setContentsMargins(0, 0, 0, 0)
            self._body_l.setSpacing(3)
            self._scroll.setWidget(self._body)
            root.addWidget(self._scroll, 1)
        else:
            self._scroll = None
            self._body = QWidget()
            self._body_l = QVBoxLayout(self._body)
            self._body_l.setContentsMargins(0, 0, 0, 0)
            self._body_l.setSpacing(3)
            root.addWidget(self._body, 1)

        self._load_controls_and_build_rows()
        self.refresh_from_project()
        try:
            self._ui_sync_timer.start()
        except Exception:
            pass

        # v0.0.20.526: Connect AutomationManager.parameter_changed → slider follow
        try:
            am = _get_automation_manager(self._services)
            if am is not None and hasattr(am, "parameter_changed"):
                am.parameter_changed.connect(self._on_automation_param_changed)
        except Exception:
            pass

    def _on_automation_param_changed(self, parameter_id: str, value: float) -> None:
        """Update slider/spinbox when automation plays back a value (v0.0.20.526)."""
        try:
            pid = str(parameter_id or "")
            prefix = f"afx:{self._track_id}:{self._device_id}:ladspa:"
            if not pid.startswith(prefix):
                return
            port_str = pid[len(prefix):]
            try:
                port_idx = int(port_str)
            except (ValueError, TypeError):
                return
            row_data = self._rows.get(port_idx)
            if row_data is None:
                return
            _, sld, spn, (mn, mx, df) = row_data
            val = float(value)
            from PyQt6.QtCore import QSignalBlocker
            if sld is not None and hasattr(sld, 'setValue'):
                if mx > mn:
                    sld_val = int((val - mn) / (mx - mn) * 1000.0)
                    sld_val = max(0, min(1000, sld_val))
                else:
                    sld_val = 0
                with QSignalBlocker(sld):
                    sld.setValue(sld_val)
            if spn is not None:
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            rt = self._rt()
            if rt is not None:
                key = self._key(port_idx)
                try:
                    if hasattr(rt, "set_smooth"):
                        rt.set_smooth(key, float(val))
                    elif hasattr(rt, "set_param"):
                        rt.set_param(key, float(val))
                except Exception:
                    pass
        except Exception:
            pass

    def _load_controls_and_build_rows(self) -> None:
        self._load_error = ""  # Remember error for refresh_from_project
        try:
            from pydaw.audio.ladspa_host import describe_plugin, _resolve_plugin_index

            # Step 1: resolve index
            try:
                plugin_idx = _resolve_plugin_index(self._so_path, self._plugin_id)
            except Exception as e:
                self._load_error = f"Index resolve failed: {e}"
                self._show_error_label(self._load_error)
                return

            # Step 2: describe
            try:
                info = describe_plugin(self._so_path, plugin_idx)
            except Exception as e:
                self._load_error = f"describe_plugin failed: {e}"
                self._show_error_label(self._load_error)
                return

            if info is None:
                self._load_error = f"Cannot load {os.path.basename(self._so_path)} (describe returned None)"
                self._show_error_label(self._load_error)
                return

            # Plugin name header
            if info.name:
                self._lbl_path.setText(f"{info.name} ({os.path.basename(self._so_path)})")

            # Show port summary
            n_ain = sum(1 for p in info.ports if p.is_audio and p.is_input)
            n_aout = sum(1 for p in info.ports if p.is_audio and p.is_output)
            n_cin = sum(1 for p in info.ports if p.is_control and p.is_input)
            n_cout = sum(1 for p in info.ports if p.is_control and p.is_output)

            # Gather input control ports
            self._controls = [p for p in info.ports if p.is_control and p.is_input]

            if not self._controls:
                self._lbl_dsp.setText(f"Ports: ain={n_ain} aout={n_aout} — No controllable parameters")
                return

            self._lbl_dsp.setText(f"Controls: {len(self._controls)} | Audio: {n_ain}→{n_aout}")

            for port in self._controls:
                mn = port.lower
                mx = port.upper
                df = port.default

                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(4)

                lbl = QLabel(port.name)
                lbl.setFixedWidth(120)
                lbl.setToolTip(f"Port {port.index}: {port.name} [{mn:.4g} … {mx:.4g}]")
                rl.addWidget(lbl, 0)

                sld = QSlider(Qt.Orientation.Horizontal)
                sld.setRange(0, 1000)
                rl.addWidget(sld, 1)

                spn = QDoubleSpinBox()
                spn.setDecimals(4)
                spn.setRange(float(mn), float(mx))
                spn.setSingleStep(max(0.001, (mx - mn) / 200.0))
                spn.setFixedWidth(80)
                rl.addWidget(spn, 0)

                self._body_l.addWidget(row)
                self._rows[port.index] = (row, sld, spn, (mn, mx, df))
                pid = self._key(port.index)
                _install_automation_menu(self, lbl, pid, lambda df=df: float(df))
                _install_automation_menu(self, sld, pid, lambda df=df: float(df))
                _install_automation_menu(self, spn, pid, lambda df=df: float(df))
                self._automation_params[port.index] = _register_automatable_param(
                    self._services, self._track_id, pid, getattr(port, "name", f"Port {port.index}"), mn, mx, df
                )

                # Bidirectional slider <-> spin
                def _make_slider_cb(p_idx, s, sp, lo, hi):
                    def cb(v):
                        val = lo + (v / 1000.0) * (hi - lo)
                        with QSignalBlocker(sp):
                            sp.setValue(float(val))
                        self._set_value(p_idx, float(val))
                    return cb

                def _make_spin_cb(p_idx, s, sp, lo, hi):
                    def cb(val):
                        pos = 0
                        if hi > lo:
                            pos = int(round(((val - lo) / (hi - lo)) * 1000.0))
                        with QSignalBlocker(s):
                            s.setValue(max(0, min(1000, pos)))
                        self._set_value(p_idx, float(val))
                    return cb

                sld.valueChanged.connect(_make_slider_cb(port.index, sld, spn, mn, mx))
                spn.valueChanged.connect(_make_spin_cb(port.index, sld, spn, mn, mx))

            self._body_l.addStretch(1)

            am = _get_automation_manager(self._services)
            if am is not None and not self._automation_connected:
                try:
                    am.parameter_changed.connect(self._on_automation_changed)
                    self._automation_connected = True
                except Exception:
                    self._automation_connected = False

        except Exception as e:
            import traceback
            self._load_error = f"LADSPA load error: {e}"
            traceback.print_exc()
            self._show_error_label(self._load_error)

    def _show_error_label(self, msg: str) -> None:
        """Show a visible error in the scroll body."""
        try:
            err = QLabel(msg)
            err.setWordWrap(True)
            err.setStyleSheet("color: #ff6b6b; padding: 8px;")
            self._body_l.addWidget(err)
        except Exception:
            pass

    def _apply_ui_value(self, port_index: int, value: float) -> None:
        try:
            row = self._rows.get(int(port_index))
            if not row:
                return
            _row, sld, spn, (mn, mx, _df) = row
            val = float(max(mn, min(mx, float(value))))
            pos = 0
            if mx > mn:
                pos = int(round(((val - mn) / (mx - mn)) * 1000.0))
            with QSignalBlocker(sld):
                sld.setValue(max(0, min(1000, pos)))
            with QSignalBlocker(spn):
                spn.setValue(val)
        except Exception:
            pass

    def _sync_from_rt(self) -> None:
        try:
            if not self.isVisible():
                return
        except Exception:
            pass
        rt = self._rt()
        if rt is None:
            return
        try:
            for idx, (_row, _sld, _spn, (_mn, _mx, _df)) in self._rows.items():
                key = self._key(idx)
                default_val = float(getattr(_spn, 'value', lambda: 0.0)())
                val = default_val
                try:
                    if hasattr(rt, 'get_smooth'):
                        val = float(rt.get_smooth(key, default_val))
                    elif hasattr(rt, 'get_target'):
                        val = float(rt.get_target(key, default_val))
                except Exception:
                    val = default_val
                self._apply_ui_value(idx, val)
        except Exception:
            pass

    def _on_automation_changed(self, parameter_id: str, value: float) -> None:
        try:
            pid = str(parameter_id)
            for idx in self._rows.keys():
                if pid != self._key(idx):
                    continue
                val = float(value)
                self._apply_ui_value(idx, val)
                self._set_value(idx, val, update_param=False)
                break
        except RuntimeError:
            self._disconnect_automation()

    def _set_value(self, port_index: int, value: float, update_param: bool = True) -> None:
        # RT write
        rt = self._rt()
        try:
            if rt is not None:
                rt.set_param(self._key(port_index), float(value))
        except Exception:
            pass
        if update_param:
            try:
                param = self._automation_params.get(int(port_index))
                if param is not None:
                    param.set_value(float(value))
            except Exception:
                pass
        # Persist
        try:
            dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
            if params is not None:
                params[str(port_index)] = float(value)
        except Exception:
            pass
        self._debounce.start()

    def _legacy_chain_key_wet_unused(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _legacy_chain_key_mix_unused(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _legacy_chain_bind_automation_unused(self) -> None:
        self._automation_param = {
            "wet": _register_automatable_param(self._services, self._track_id, self._key_wet(), "Wet Gain", 0.0, 2.0, float(self.dial_wet.value()) / 100.0),
            "mix": _register_automatable_param(self._services, self._track_id, self._key_mix(), "Mix", 0.0, 1.0, float(self.dial_mix.value()) / 100.0),
        }
        am = _get_automation_manager(self._services)
        if am is not None and not self._automation_connected:
            try:
                am.parameter_changed.connect(self._on_automation_changed)
                self._automation_connected = True
            except Exception:
                self._automation_connected = False

    def _legacy_chain_on_automation_changed_unused(self, parameter_id: str, value: float) -> None:
        pid = str(parameter_id)
        if pid == self._key_wet():
            v = max(0.0, min(2.0, float(value)))
            self.dial_wet.blockSignals(True)
            try:
                self.dial_wet.setValue(int(round(v * 100.0)))
            finally:
                self.dial_wet.blockSignals(False)
            self.lbl_wet.setText(f"{self.dial_wet.value()}%")
            self._on_change()
        elif pid == self._key_mix():
            v = max(0.0, min(1.0, float(value)))
            self.dial_mix.blockSignals(True)
            try:
                self.dial_mix.setValue(int(round(v * 100.0)))
            finally:
                self.dial_mix.blockSignals(False)
            self.lbl_mix.setText(f"{self.dial_mix.value()}%")
            self._on_change()

    def refresh_from_project(self) -> None:
        # If loading failed, keep the error visible
        if getattr(self, '_load_error', ''):
            self._lbl_dsp.setText(self._load_error)
            self._lbl_dsp.setStyleSheet("font-size: 11px; color: #ff6b6b;")
            return
        dev, params = _find_audio_fx_dev(self._services, self._track_id, self._device_id)
        if params is None:
            return
        rt = self._rt()

        for port in self._controls:
            idx = port.index
            if idx not in self._rows:
                continue
            _row, sld, spn, (mn, mx, df) = self._rows[idx]
            try:
                val = float(params.get(str(idx), df))
            except Exception:
                val = df
            if val < mn:
                val = mn
            if val > mx:
                val = mx

            try:
                pos = 0
                if mx > mn:
                    pos = int(round(((val - mn) / (mx - mn)) * 1000.0))
                with QSignalBlocker(sld):
                    sld.setValue(max(0, min(1000, pos)))
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            except Exception:
                pass

            try:
                if rt is not None and hasattr(rt, "ensure"):
                    rt.ensure(self._key(idx), float(val))
                elif rt is not None:
                    rt.set_param(self._key(idx), float(val))
            except Exception:
                pass

        # DSP status check
        try:
            active = self._dsp_is_active()
            if active:
                n = len(self._controls)
                self._lbl_dsp.setText(f"DSP: ACTIVE — {n} controls")
                self._btn_rebuild.setVisible(False)
            else:
                # Try to find the error from the audio engine
                err_msg = ""
                try:
                    ae = getattr(self._services, "audio_engine", None)
                    fx_map = getattr(ae, "_track_audio_fx_map", None) if ae else None
                    if isinstance(fx_map, dict):
                        chain = fx_map.get(str(self._track_id))
                        if chain is None:
                            err_msg = "no FX chain for track"
                        elif not getattr(chain, "devices", None):
                            err_msg = "chain has 0 devices"
                except Exception:
                    pass
                hint = f" ({err_msg})" if err_msg else ""
                self._lbl_dsp.setText(f"DSP: INACTIVE{hint} — try Rebuild FX")
                self._btn_rebuild.setVisible(True)
        except Exception:
            pass

    def _dsp_is_active(self) -> bool:
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            fx_map = getattr(ae, "_track_audio_fx_map", None) if ae is not None else None
            if not isinstance(fx_map, dict):
                return False
            chain = fx_map.get(str(self._track_id))
            devs = getattr(chain, "devices", None)
            if not isinstance(devs, list):
                return False
            for fx in devs:
                try:
                    if str(getattr(fx, "device_id", "")) == str(self._device_id):
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _flush_to_project(self) -> None:
        ps = getattr(self._services, "project", None) if self._services is not None else None
        try:
            if ps is not None and hasattr(ps, "project_changed"):
                ps.project_changed.emit()
        except Exception:
            pass

    def _safe_rebuild_fx_maps(self) -> None:
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            if ae is not None and hasattr(ae, "rebuild_fx_maps"):
                ps = getattr(self._services, "project", None) if self._services is not None else None
                proj = getattr(ps, "project", None) if ps is not None else None
                if proj is not None:
                    ae.rebuild_fx_maps(proj)
                    self.refresh_from_project()
        except Exception:
            pass

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for idx, (row, _sld, _spn, _info) in self._rows.items():
            try:
                port = next((p for p in self._controls if p.index == idx), None)
                name = (port.name if port else "").lower()
                row.setVisible(not text or text in name or text in str(idx))
            except Exception:
                pass


class _Vst3ParamLoader(QThread):
    """Background worker: loads VST3/VST2 plugin parameters without blocking the GUI.

    v0.0.20.368 -- Fix: describe_controls was called synchronously in Qt main-thread,
    hanging the UI for 10-60 s when a complex VST3 bundle (e.g. lsp-plugins.vst3)
    was added via the Plugin Browser.
    """
    params_ready = pyqtSignal(list)   # list[Vst3ParamInfo]
    load_failed  = pyqtSignal(str)    # error message

    def __init__(self, vst3_path: str, plugin_name: str, parent=None):
        super().__init__(parent)
        self._path = str(vst3_path or "")
        self._name = str(plugin_name or "")

    def run(self) -> None:
        try:
            from pydaw.audio.vst3_host import describe_controls
            infos = describe_controls(self._path, plugin_name=self._name)
            self.params_ready.emit(infos)
        except Exception as exc:
            self.load_failed.emit(str(exc))


class _VstInProcessEditorThread(QThread):
    """Opens a VST plugin's native editor IN-PROCESS on the audio-engine plugin instance.

    v0.0.20.379: Initial implementation.
    v0.0.20.402: Captures the editor's X11 window ID from WITHIN the thread
                 using XGetInputFocus on a SEPARATE display connection (thread-safe).
                 This is the only reliable way — by the time a QTimer fires on the
                 main thread, the user may have moved focus elsewhere.

    Protocol:
      editor_ready       — show_editor() has been called (window appearing)
      editor_wid(int)    — X11 window ID of the editor (captured from thread)
      editor_closed      — show_editor() returned (window was closed)
      editor_error(str)  — exception string
    """
    editor_ready  = pyqtSignal()
    editor_wid    = pyqtSignal(int)   # v0.0.20.402: carries the X11 window ID
    editor_closed = pyqtSignal()
    editor_error  = pyqtSignal(str)

    def __init__(self, plugin_obj: Any, window_title: str = "", parent=None):
        super().__init__(parent)
        self._plugin = plugin_obj
        self._title  = window_title

    def _capture_editor_wid(self) -> None:
        """Capture the editor's X11 window ID from this thread.

        Opens a SEPARATE X11 display connection (thread-safe — each thread
        needs its own Display*) and calls XGetInputFocus after a brief sleep.
        The JUCE window has focus right after show_editor() creates it.
        """
        import time, ctypes, sys
        time.sleep(1.5)  # JUCE window needs ~1s to appear and take focus

        try:
            x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            dpy = x11.XOpenDisplay(None)
            if not dpy:
                return

            focus_wid = ctypes.c_ulong()
            revert_to = ctypes.c_int()
            x11.XGetInputFocus.restype = None
            x11.XGetInputFocus.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int),
            ]
            x11.XGetInputFocus(dpy, ctypes.byref(focus_wid), ctypes.byref(revert_to))

            wid = focus_wid.value
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            root = x11.XDefaultRootWindow(dpy)
            x11.XCloseDisplay(dpy)

            if wid not in (0, 1, root):
                print(f"[X11-THREAD] Captured editor wid via focus: 0x{wid:x}",
                      file=sys.stderr, flush=True)
                self.editor_wid.emit(wid)
            else:
                print(f"[X11-THREAD] Focus = root/none (0x{wid:x}), trying title search...",
                      file=sys.stderr, flush=True)
                # Fallback: try title search from thread
                try:
                    from pydaw.ui.x11_window_ctl import x11_find_windows
                    for term in ["Pedalboard", self._title]:
                        if not term:
                            continue
                        wids = x11_find_windows(term)
                        if wids:
                            self.editor_wid.emit(wids[-1])
                            return
                except Exception:
                    pass
        except Exception as exc:
            import sys
            print(f"[X11-THREAD] Capture failed: {exc}", file=sys.stderr, flush=True)

    def run(self) -> None:
        try:
            show_fn = getattr(self._plugin, "show_editor", None)
            if not callable(show_fn):
                self.editor_error.emit("show_editor() nicht verfügbar für dieses Plugin")
                return
            self.editor_ready.emit()

            # Start a daemon thread to capture the window ID after JUCE creates it
            import threading
            capture_thread = threading.Thread(target=self._capture_editor_wid, daemon=True)
            capture_thread.start()

            try:
                show_fn(window_title=self._title)
            except TypeError:
                try:
                    show_fn(self._title)
                except TypeError:
                    show_fn()
            self.editor_closed.emit()
        except Exception as exc:
            self.editor_error.emit(str(exc))


# ── Persistent Pin/Shade state (class-level, keyed by plugin path) ────────
# Survives editor close/reopen within the same session.
_vst_editor_state: dict = {}  # key → {"pinned": bool, "shaded": bool}

# v0.0.20.403: Module-level registry of active editor threads.
# Survives widget destruction during track switches. Keyed by track_id:device_id.
# Entries: {"thread": QThread, "plugin_name": str, "vst3_path": str}
_active_editor_threads: dict = {}


class _Vst2EditorDialog(QWidget):
    """Native VST2 editor window with Pin (Always-on-Top) + Shade (Roll-Up).

    v0.0.20.395: Plugin draws into a child QWidget's native X11 window handle.
    v0.0.20.400: Added Sticky-Window Pin-Nadel (📌) and Window-Shade (🔽/🔼)
                 buttons in a compact toolbar. State persists per plugin path
                 within the session.

    Architecture:
        QWidget (Window)
        ├─ _toolbar  (Pin / Shade / Close controls)
        └─ _plugin_area  (QWidget with WA_NativeWindow)
               └── winId() ──► effEditOpen(handle)
                                Plugin draws its GUI here
        QTimer(30ms) ──────────► effEditIdle()
        closeEvent ────────────► effEditClose()
    """
    editor_closed_signal = pyqtSignal()

    # ── Toolbar height constant ─────────────────────────────────────────
    _TOOLBAR_H = 28

    def __init__(self, vst2_plugin: Any, title: str = "",
                 width: int = 640, height: int = 480, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._plugin = vst2_plugin
        self._editor_open = False
        self._plugin_title = title or "VST2"
        self._state_key = title  # used to look up pin/shade in _vst_editor_state

        self.setWindowTitle(f"VST2 Editor — {title}")

        # Dark background for the entire window
        self.setStyleSheet("background-color: #1a1a2e;")

        # ── Layout: toolbar + plugin area ───────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ─────────────────────────────────────────────────────
        self._toolbar = self._build_toolbar()
        root.addWidget(self._toolbar)

        # ── Plugin rendering area (child QWidget with native window) ────
        self._plugin_area = QWidget(self)
        self._plugin_area.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._plugin_area.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self._plugin_area.setStyleSheet("background-color: #1a1a2e;")
        pw, ph = max(200, width), max(150, height)
        self._plugin_area.setFixedSize(pw, ph)
        root.addWidget(self._plugin_area)

        # Total window size = toolbar + plugin area
        self._plugin_w, self._plugin_h = pw, ph
        self._shaded = False
        self.setFixedSize(pw, self._TOOLBAR_H + ph)

        # v0.0.20.409: Do NOT call editor_open here!
        # Deferred to after show() + processEvents() to avoid X11 BadWindow crash.
        self._idle_timer = None

    def deferred_editor_open(self) -> bool:
        """Call AFTER show() + processEvents(). Returns True on success.

        v0.0.20.409: Critical fix for X11 BadWindow crash on Wayland/XWayland.
        winId() is only valid after the native X11 window is actually mapped.
        """
        from PyQt6.QtWidgets import QApplication
        try:
            QApplication.processEvents()

            win_id = int(self._plugin_area.winId())
            if win_id == 0:
                raise RuntimeError("winId = 0 nach show()")

            ok = self._plugin.editor_open(win_id)
            if not ok:
                raise RuntimeError("effEditOpen fehlgeschlagen")
            self._editor_open = True

            # Re-read size after editor_open (some plugins update rect)
            try:
                w2, h2 = self._plugin.editor_get_rect()
                if w2 > 0 and h2 > 0 and (w2 != self._plugin_w or h2 != self._plugin_h):
                    self._plugin_w, self._plugin_h = w2, h2
                    self._plugin_area.setFixedSize(w2, h2)
                    self.setFixedSize(w2, self._TOOLBAR_H + h2)
            except Exception:
                pass

            # Start idle timer
            self._idle_timer = QTimer(self)
            self._idle_timer.setInterval(30)
            self._idle_timer.timeout.connect(self._on_idle)
            self._idle_timer.start()

            # Restore saved state (pin/shade)
            self._restore_state()

            import sys
            print(f"[VST2-EDITOR] Opened: {self._plugin_title} "
                  f"({self._plugin_w}x{self._plugin_h}) winId=0x{win_id:X}",
                  file=sys.stderr, flush=True)
            return True
        except Exception as exc:
            import sys
            print(f"[VST2-EDITOR] FAILED: {exc}", file=sys.stderr, flush=True)
            return False

    # ── Toolbar construction ────────────────────────────────────────────
    def _build_toolbar(self) -> QWidget:
        """Build the compact Pin/Shade/Close toolbar."""
        bar = QWidget()
        bar.setFixedHeight(self._TOOLBAR_H)
        bar.setStyleSheet(
            "QWidget { background-color: #12122a; border-bottom: 1px solid #333; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        # ── Plugin name label ───────────────────────────────────────────
        lbl = QLabel(f"🎛 {self._plugin_title}")
        lbl.setStyleSheet("color: #c8c8d4; font-size: 11px; font-weight: 600; border: none;")
        lay.addWidget(lbl, 1)

        btn_style = (
            "QPushButton { background: transparent; border: 1px solid #444; "
            "border-radius: 3px; color: #aaa; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #2a2a4a; border-color: #888; color: #eee; }"
        )
        btn_active_pin = (
            "QPushButton { background: #3a2a10; border: 1px solid #d4a020; "
            "border-radius: 3px; color: #f0c040; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #4a3a20; border-color: #e0b030; }"
        )

        # ── Pin button (📌 Always on Top) ───────────────────────────────
        self._btn_pin = QPushButton("📌")
        self._btn_pin.setToolTip(
            "Pin: Fenster bleibt im Vordergrund (Always on Top)\n"
            "Aktiviert: Fenster schwebt über der DAW"
        )
        self._btn_pin.setStyleSheet(btn_style)
        self._btn_pin.clicked.connect(self._toggle_pin)
        self._btn_pin_style_normal = btn_style
        self._btn_pin_style_active = btn_active_pin
        lay.addWidget(self._btn_pin)

        # ── Shade button (🔽 Roll-Up / 🔼 Roll-Down) ──────────────────
        self._btn_shade = QPushButton("🔽")
        self._btn_shade.setToolTip(
            "Einrollen: Fenster auf Titelleiste minimieren\n"
            "Plugin bleibt geladen — spart Platz auf dem Desktop"
        )
        self._btn_shade.setStyleSheet(btn_style)
        self._btn_shade.clicked.connect(self._toggle_shade)
        lay.addWidget(self._btn_shade)

        # ── Close button ────────────────────────────────────────────────
        btn_close = QPushButton("✕")
        btn_close.setToolTip("Editor-Fenster schließen")
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #444; "
            "border-radius: 3px; color: #cc6666; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #4a2020; border-color: #cc4444; color: #ff6666; }"
        )
        btn_close.clicked.connect(self.close)
        lay.addWidget(btn_close)

        return bar

    # ── Pin (Always on Top) ─────────────────────────────────────────────
    def _toggle_pin(self) -> None:
        """Toggle Always-on-Top via pure ctypes/libX11.

        v0.0.20.402: NICHT mehr setWindowFlags() verwenden!
        setWindowFlags() zerstört das native Fenster und erstellt es neu →
        Plugin zeichnet danach ins alte tote winId → leeres Fenster.

        Stattdessen: EWMH _NET_WM_STATE_ABOVE via x11_window_ctl.
        Das Fenster bleibt am Leben, winId ändert sich nicht.
        """
        was_pinned = getattr(self, "_is_pinned", False)
        new_pinned = not was_pinned
        self._is_pinned = new_pinned

        try:
            wid = int(self.winId())
            if wid:
                from pydaw.ui.x11_window_ctl import x11_set_above
                x11_set_above(wid, new_pinned)
        except Exception as exc:
            import sys
            print(f"[VST2-EDITOR] Pin via X11 fehlgeschlagen: {exc}",
                  file=sys.stderr, flush=True)

        self._update_pin_visual(new_pinned)
        self._save_state(pinned=new_pinned)

    def _update_pin_visual(self, pinned: bool) -> None:
        """Update pin button appearance to reflect state."""
        try:
            if pinned:
                self._btn_pin.setStyleSheet(self._btn_pin_style_active)
                self._btn_pin.setToolTip(
                    "Pin AKTIV: Fenster bleibt im Vordergrund\n"
                    "Klicken zum Deaktivieren"
                )
            else:
                self._btn_pin.setStyleSheet(self._btn_pin_style_normal)
                self._btn_pin.setToolTip(
                    "Pin: Fenster bleibt im Vordergrund (Always on Top)\n"
                    "Aktiviert: Fenster schwebt über der DAW"
                )
        except RuntimeError:
            pass

    # ── Shade (Roll-Up / Roll-Down) ─────────────────────────────────────
    def _toggle_shade(self) -> None:
        """Toggle between full view and collapsed (toolbar only)."""
        self._shaded = not self._shaded
        if self._shaded:
            # Collapse: hide plugin area, shrink window to toolbar height
            self._plugin_area.setVisible(False)
            self.setFixedSize(self._plugin_w, self._TOOLBAR_H)
            try:
                self._btn_shade.setText("🔼")
                self._btn_shade.setToolTip(
                    "Ausrollen: Plugin-Fenster wieder anzeigen"
                )
            except RuntimeError:
                pass
        else:
            # Expand: show plugin area, restore full size
            self._plugin_area.setVisible(True)
            self.setFixedSize(self._plugin_w, self._TOOLBAR_H + self._plugin_h)
            try:
                self._btn_shade.setText("🔽")
                self._btn_shade.setToolTip(
                    "Einrollen: Fenster auf Titelleiste minimieren\n"
                    "Plugin bleibt geladen — spart Platz auf dem Desktop"
                )
            except RuntimeError:
                pass

        self._save_state(shaded=self._shaded)

    # ── State persistence (per-session, keyed by plugin title) ──────────
    def _save_state(self, pinned: Optional[bool] = None,
                    shaded: Optional[bool] = None) -> None:
        """Save pin/shade state for this plugin to the class-level dict."""
        key = self._state_key
        state = _vst_editor_state.setdefault(key, {"pinned": False, "shaded": False})
        if pinned is not None:
            state["pinned"] = pinned
        if shaded is not None:
            state["shaded"] = shaded

    def _restore_state(self) -> None:
        """Restore saved pin/shade state on editor open.

        v0.0.20.402: Pin uses ctypes/libX11, NOT setWindowFlags().
        Applied after a short delay so the window is fully realized.
        """
        state = _vst_editor_state.get(self._state_key, {})
        if state.get("pinned", False):
            self._is_pinned = True
            self._update_pin_visual(True)
            # Delay: window must be fully visible before X11 can change its state
            def _apply_pin():
                try:
                    wid = int(self.winId())
                    if wid:
                        from pydaw.ui.x11_window_ctl import x11_set_above
                        x11_set_above(wid, True)
                except Exception:
                    pass
            QTimer.singleShot(300, _apply_pin)
        if state.get("shaded", False):
            self._toggle_shade()

    # ── Idle / Close / Lifecycle ────────────────────────────────────────
    def _on_idle(self) -> None:
        """Called every 30ms — plugin needs this to redraw/animate."""
        if self._plugin is not None and self._editor_open:
            try:
                self._plugin.editor_idle()
            except Exception:
                pass

    def closeEvent(self, event) -> None:
        """User closes the editor window."""
        self._close_editor()
        event.accept()

    def _close_editor(self) -> None:
        if self._editor_open and self._plugin is not None:
            try:
                self._idle_timer.stop()
            except Exception:
                pass
            try:
                self._plugin.editor_close()
            except Exception:
                pass
            self._editor_open = False
            import sys
            print("[VST2-EDITOR] Closed", file=sys.stderr, flush=True)
            try:
                self.editor_closed_signal.emit()
            except Exception:
                pass

    def __del__(self):
        self._close_editor()


# ── Unified VST Editor Container (v0.0.20.403) ────────────────────────────
# Professional Qt-wrapper approach: Instead of searching X11 windows and trying
# to manipulate foreign surfaces, we EMBED the native editor into our own Qt
# container via QWindow.fromWinId() + createWindowContainer(). This gives us
# full control over Pin, Shade, Close — works on X11 AND Wayland.

class VstEditorContainer(QWidget):
    """Unified Qt wrapper for VST2/VST3 native editor windows.

    v0.0.20.403: Replaces X11 window search with Qt reparenting.

    Architecture:
        VstEditorContainer (QWidget, Window)
        ├── _toolbar (28px)
        │   ├── 🎛 Plugin-Name
        │   ├── 📌 Pin (Always on Top)
        │   ├── 🔽 Shade (Roll-Up)
        │   └── ✕ Close
        └── _editor_host (QWidget created via createWindowContainer)
                └── QWindow.fromWinId(native_wid)
                        └── JUCE / pedalboard / VST native rendering

    Pin uses x11_set_above() on OUR container's winId() — always works
    because WE own the widget and know its ID.
    """
    editor_closed = pyqtSignal()
    _TOOLBAR_H = 28

    def __init__(self, native_wid: int, plugin_name: str = "",
                 width: int = 960, height: int = 720, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._native_wid = native_wid
        self._plugin_name = plugin_name or "VST Editor"
        self._is_pinned = False
        self._shaded = False
        self._state_key = plugin_name

        self.setWindowTitle(f"VST Editor — {self._plugin_name}")
        self.setStyleSheet("background-color: #1a1a2e;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ─────────────────────────────────────────────────────
        self._toolbar = self._build_toolbar()
        root.addWidget(self._toolbar)

        # ── Embed native window ─────────────────────────────────────────
        self._editor_host = None
        self._editor_w = max(200, width)
        self._editor_h = max(150, height)
        try:
            from PyQt6.QtGui import QWindow
            qwin = QWindow.fromWinId(native_wid)
            if qwin is not None:
                container = QWidget.createWindowContainer(qwin, self)
                container.setMinimumSize(200, 150)
                container.setFixedSize(self._editor_w, self._editor_h)
                root.addWidget(container)
                self._editor_host = container
                import sys
                print(f"[VstEditorContainer] Embedded wid=0x{native_wid:x} "
                      f"({self._editor_w}x{self._editor_h}) into Qt container",
                      file=sys.stderr, flush=True)
        except Exception as exc:
            import sys
            print(f"[VstEditorContainer] createWindowContainer failed: {exc}",
                  file=sys.stderr, flush=True)
            # Fallback: show a placeholder
            lbl = QLabel(f"Native Editor (0x{native_wid:x})\n"
                         f"Embedding fehlgeschlagen: {exc}")
            lbl.setStyleSheet("color: #ff8888; padding: 20px;")
            lbl.setWordWrap(True)
            root.addWidget(lbl)

        self.setFixedSize(self._editor_w, self._TOOLBAR_H + self._editor_h)

        # Restore saved state
        self._restore_state()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(self._TOOLBAR_H)
        bar.setStyleSheet(
            "QWidget { background-color: #12122a; border-bottom: 1px solid #333; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        lbl = QLabel(f"🎛 {self._plugin_name}")
        lbl.setStyleSheet("color: #c8c8d4; font-size: 11px; font-weight: 600; border: none;")
        lay.addWidget(lbl, 1)

        btn_style = (
            "QPushButton { background: transparent; border: 1px solid #444; "
            "border-radius: 3px; color: #aaa; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #2a2a4a; border-color: #888; color: #eee; }"
        )
        btn_active_pin = (
            "QPushButton { background: #3a2a10; border: 1px solid #d4a020; "
            "border-radius: 3px; color: #f0c040; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #4a3a20; border-color: #e0b030; }"
        )

        self._btn_pin = QPushButton("📌")
        self._btn_pin.setToolTip("Pin: Fenster bleibt im Vordergrund")
        self._btn_pin.setStyleSheet(btn_style)
        self._btn_pin.clicked.connect(self._toggle_pin)
        self._btn_pin_style_normal = btn_style
        self._btn_pin_style_active = btn_active_pin
        lay.addWidget(self._btn_pin)

        self._btn_shade = QPushButton("🔽")
        self._btn_shade.setToolTip("Einrollen: Fenster auf Titelleiste minimieren")
        self._btn_shade.setStyleSheet(btn_style)
        self._btn_shade.clicked.connect(self._toggle_shade)
        lay.addWidget(self._btn_shade)

        btn_close = QPushButton("✕")
        btn_close.setToolTip("Editor-Fenster schließen")
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #444; "
            "border-radius: 3px; color: #cc6666; font-size: 13px; padding: 0; "
            "min-width: 26px; max-width: 26px; min-height: 22px; max-height: 22px; }"
            "QPushButton:hover { background: #4a2020; border-color: #cc4444; color: #ff6666; }"
        )
        btn_close.clicked.connect(self.close)
        lay.addWidget(btn_close)

        return bar

    def _toggle_pin(self) -> None:
        """Pin via x11_set_above on OUR container's winId — always reliable."""
        self._is_pinned = not self._is_pinned
        try:
            wid = int(self.winId())
            if wid:
                from pydaw.ui.x11_window_ctl import x11_set_above
                x11_set_above(wid, self._is_pinned)
        except Exception as exc:
            import sys
            print(f"[VstEditorContainer] Pin failed: {exc}", file=sys.stderr, flush=True)

        try:
            self._btn_pin.setStyleSheet(
                self._btn_pin_style_active if self._is_pinned else self._btn_pin_style_normal
            )
            self._btn_pin.setToolTip(
                "Pin AKTIV: Fenster bleibt im Vordergrund\nKlicken zum Deaktivieren"
                if self._is_pinned else
                "Pin: Fenster bleibt im Vordergrund"
            )
        except RuntimeError:
            pass
        self._save_state(pinned=self._is_pinned)

    def _toggle_shade(self) -> None:
        """Roll-up/roll-down the editor area."""
        self._shaded = not self._shaded
        if self._editor_host is not None:
            self._editor_host.setVisible(not self._shaded)
        if self._shaded:
            self.setFixedSize(self._editor_w, self._TOOLBAR_H)
        else:
            self.setFixedSize(self._editor_w, self._TOOLBAR_H + self._editor_h)
        try:
            self._btn_shade.setText("🔼" if self._shaded else "🔽")
            self._btn_shade.setToolTip(
                "Ausrollen: Plugin-Fenster wieder anzeigen" if self._shaded else
                "Einrollen: Fenster auf Titelleiste minimieren"
            )
        except RuntimeError:
            pass
        self._save_state(shaded=self._shaded)

    def _save_state(self, pinned=None, shaded=None):
        key = self._state_key
        state = _vst_editor_state.setdefault(key, {"pinned": False, "shaded": False})
        if pinned is not None:
            state["pinned"] = pinned
        if shaded is not None:
            state["shaded"] = shaded

    def _restore_state(self):
        state = _vst_editor_state.get(self._state_key, {})
        if state.get("pinned", False):
            # Delay to let window be realized, then apply pin
            def _apply_pin():
                self._is_pinned = False  # _toggle_pin will flip to True
                self._toggle_pin()
            QTimer.singleShot(400, _apply_pin)
        if state.get("shaded", False):
            QTimer.singleShot(600, self._toggle_shade)

    def closeEvent(self, event):
        try:
            self.editor_closed.emit()
        except Exception:
            pass
        event.accept()


class Vst3AudioFxWidget(QWidget):
    """Generic VST3/VST2 Audio-FX parameter widget (via pedalboard).

    Shows all VST3 parameters as sliders/spinboxes.
    Writes values to RTParamStore and persists into device params.

    v0.0.20.363 — Initial VST3 live hosting
    """

    def __init__(self, services: Any, track_id: str, device_id: str,
                 plugin_id: str, vst3_path: str, plugin_name: str = "", parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._plugin_id = str(plugin_id or "")
        self._vst3_path = str(vst3_path or "")
        self._plugin_name = str(plugin_name or "")

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._flush_to_project)

        self._param_infos: list = []
        self._rows: dict = {}  # param_name -> (row_widget, slider, spin, (mn, mx, df))
        self._automation_params: dict = {}  # param_name -> AutomatableParameter handle
        self._prefix = f"afx:{self._track_id}:{self._device_id}:vst3:"
        self._loader = None  # _Vst3ParamLoader QThread instance (NOT parented — managed explicitly)
        self._main_thread_param_retry_done = False
        self._runtime_probe_timer = QTimer(self)
        self._runtime_probe_timer.setSingleShot(True)
        self._runtime_probe_timer.timeout.connect(self._retry_runtime_param_load)
        self._runtime_probe_attempts = 0
        self._ui_sync_timer = QTimer(self)
        self._ui_sync_timer.setInterval(60)
        self._ui_sync_timer.timeout.connect(self._sync_from_rt)
        self._lbl_state_hint = None
        self._lbl_param_source = None   # shows: runtime / async / main-thread
        self._lbl_bus_hint = None
        self._param_source: str = ""    # "runtime" | "async" | "main-thread"
        self._editor_process: Optional[QProcess] = None  # native VST editor subprocess
        self._editor_stdout_buffer: str = ""  # v0.0.20.459: buffer for partial JSON lines
        self._pending_state_blob: str = ""    # v0.0.20.460: debounced state blob
        self._state_apply_timer: Optional[QTimer] = None  # v0.0.20.460: deferred apply
        self._editor_inproc_thread: Optional[QThread] = None  # in-process editor thread (v0.0.20.379)
        self._editor_poll_timer: Optional[QTimer] = None      # polls raw_value for bi-sync
        self._editor_window_title: str = ""   # v0.0.20.402: stored for X11 pin/shade
        self._editor_shaded_x11: bool = False # v0.0.20.402: X11 minimize state
        self._editor_x11_wid: int = 0         # v0.0.20.402: detected via focus
        self._vst3_editor_container: Optional[QWidget] = None  # v0.0.20.403: Qt wrapper
        self._editor_registry_key: str = ""  # v0.0.20.403: key in _active_editor_threads

        self._build()

    def _rt(self):
        ae = getattr(self._services, "audio_engine", None) if self._services else None
        return getattr(ae, "rt_params", None) if ae else None

    def _key(self, param_name: str) -> str:
        return self._prefix + str(param_name)

    def _get_track_name(self) -> str:
        """Return the human-readable track name for this widget's track_id.

        Used to build the native editor window title.
        v0.0.20.375
        """
        try:
            ps = getattr(self._services, "project_service", None) if self._services else None
            proj = getattr(ps, "project", None) if ps else None
            if proj is None:
                return ""
            t = _find_track(proj, self._track_id)
            return str(getattr(t, "name", "") or "") if t is not None else ""
        except Exception:
            return ""

    def _send_to_editor(self, cmd: dict) -> None:
        """Write one JSON command line to the editor subprocess stdin.

        Safe no-op if no editor process is running.
        v0.0.20.375
        """
        proc = getattr(self, "_editor_process", None)
        if proc is None:
            return
        try:
            if proc.state() == QProcess.ProcessState.NotRunning:
                return
            import json as _json
            line = (_json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
            proc.write(line)
        except Exception:
            pass

    def _get_project_device(self) -> Optional[dict]:
        try:
            ps = getattr(self._services, "project_service", None) if self._services else None
            proj = getattr(ps, "project", None) if ps else None
            if proj is None:
                return None
            tracks = getattr(proj, "tracks", []) or []
            for t in tracks:
                if str(getattr(t, "id", "")) != self._track_id:
                    continue
                chain = getattr(t, "audio_fx_chain", None)
                if not isinstance(chain, dict):
                    return None
                for dev in (chain.get("devices") or []):
                    if str(dev.get("id", "")) == self._device_id:
                        return dev if isinstance(dev, dict) else None
        except Exception:
            return None
        return None

    def _update_state_hint(self) -> None:
        lbl = getattr(self, "_lbl_state_hint", None)
        if lbl is None:
            return
        dev = self._get_project_device()
        if not isinstance(dev, dict):
            lbl.setText("Preset/State: kein Projektdevice")
            lbl.setToolTip("Kein passendes VST-Device im aktuellen Projekt gefunden.")
            lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
            return
        params = dev.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        blob = str(params.get("__ext_state_b64") or "").strip()
        if blob:
            chars = len(blob)
            approx_bytes = max(0, (chars * 3) // 4)
            size_txt = f"~{approx_bytes / 1024.0:.1f} KB" if approx_bytes >= 1024 else f"~{approx_bytes} B"
            lbl.setText(f"Preset/State: eingebettet ({size_txt})")
            lbl.setToolTip(
                "Dieses Projekt enthält bereits einen eingebetteten Plugin-State-Blob "
                f"(`__ext_state_b64`, {chars} Base64-Zeichen)."
            )
            lbl.setStyleSheet("font-size: 11px; color: #7bd389;")
            return
        lbl.setText("Preset/State: kein eingebetteter Blob")
        lbl.setToolTip(
            "Noch kein eingebetteter Plugin-State-Blob im Projekt gespeichert. "
            "Der Blob wird erst nach dem Projektspeichern erzeugt."
        )
        lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")

    def _update_param_source_hint(self) -> None:
        """Update the small italic label showing how parameters were loaded.

        v0.0.20.374 — Parameter source hint (runtime / async / main-thread)
        """
        lbl = getattr(self, "_lbl_param_source", None)
        if lbl is None:
            return
        source = str(getattr(self, "_param_source", "") or "")
        if not source:
            lbl.setVisible(False)
            return
        labels = {
            "runtime":      ("⚡ Parameter: live (running instance)", "#7bd389"),
            "async":        ("⏳ Parameter: async fallback (background load)", "#e6c86e"),
            "main-thread":  ("🔄 Parameter: main-thread fallback (reload)", "#e09050"),
        }
        text, color = labels.get(source, (f"Parameter: {source}", "#9aa0a6"))
        lbl.setText(text)
        lbl.setStyleSheet(f"font-size: 10px; color: {color}; font-style: italic;")
        lbl.setVisible(True)

    # ── Native VST Editor (subprocess) ─────────────────────────────────────

    def _toggle_editor_pin(self) -> None:
        """Toggle Always-on-Top (pin) for the open editor window.

        v0.0.20.403: Three paths in priority order:
        1. VstEditorContainer (Qt wrapper) — works everywhere (X11 + Wayland)
        2. VST2 editor dialog — we own the QWidget
        3. X11 fallback — stored wid
        """
        self._editor_pinned = not self._editor_pinned
        applied = False

        # ── Path 1: VstEditorContainer (v403) — the professional way ────
        container = getattr(self, "_vst3_editor_container", None)
        if container is not None:
            try:
                container._toggle_pin()
                applied = True
            except Exception:
                pass

        # ── Path 2: VST2 editor dialog ──────────────────────────────────
        if not applied:
            vst2_dlg = getattr(self, "_vst2_editor_dialog", None)
            if vst2_dlg is not None:
                try:
                    vst2_dlg._toggle_pin()
                    applied = True
                except Exception:
                    pass

        # ── Path 3: X11 fallback — stored wid OR title search ────────────
        if not applied:
            wid = self._editor_x11_wid
            if not wid:
                # No stored wid — try title search (works when Pedalboard
                # registers in _NET_CLIENT_LIST, which it does most of the time)
                try:
                    from pydaw.ui.x11_window_ctl import x11_find_windows
                    for term in ("Pedalboard", self._plugin_name or ""):
                        if not term:
                            continue
                        found = x11_find_windows(term)
                        if found:
                            wid = found[-1]
                            self._editor_x11_wid = wid  # cache for next time
                            break
                except Exception:
                    pass
            if wid:
                try:
                    from pydaw.ui.x11_window_ctl import x11_set_above
                    applied = x11_set_above(wid, self._editor_pinned)
                except Exception:
                    pass

        # Update button visual in the widget header
        try:
            if self._editor_pinned:
                self._btn_pin.setStyleSheet(
                    "QPushButton { background: #3a2a10; border: 1px solid #d4a020; "
                    "border-radius: 4px; color: #f0c040; font-size: 13px; padding: 0; }"
                    "QPushButton:hover { background: #4a3a20; border-color: #e0b030; }"
                )
            else:
                self._btn_pin.setStyleSheet(
                    "QPushButton { background: #2a2a3a; border: 1px solid #555; "
                    "border-radius: 4px; color: #aaa; font-size: 13px; padding: 0; }"
                    "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
                )
        except RuntimeError:
            pass

        key = self._plugin_name or self._vst3_path
        _vst_editor_state.setdefault(key, {"pinned": False, "shaded": False})
        _vst_editor_state[key]["pinned"] = self._editor_pinned

    def _toggle_editor_shade(self) -> None:
        """Toggle shade (roll-up/minimize) for the open editor window.

        v0.0.20.403: Three paths in priority order:
        1. VstEditorContainer (Qt wrapper) — works everywhere
        2. VST2 editor dialog — roll-up
        3. X11 fallback — iconify/activate
        """
        applied = False

        # ── Path 1: VstEditorContainer (v403) ───────────────────────────
        container = getattr(self, "_vst3_editor_container", None)
        if container is not None:
            try:
                container._toggle_shade()
                applied = True
                shaded = getattr(container, "_shaded", False)
                try:
                    self._btn_shade.setText("🔼" if shaded else "🔽")
                except RuntimeError:
                    pass
            except Exception:
                pass

        # ── Path 2: VST2 editor dialog ──────────────────────────────────
        if not applied:
            vst2_dlg = getattr(self, "_vst2_editor_dialog", None)
            if vst2_dlg is not None:
                try:
                    vst2_dlg._toggle_shade()
                    applied = True
                    shaded = getattr(vst2_dlg, "_shaded", False)
                    try:
                        self._btn_shade.setText("🔼" if shaded else "🔽")
                    except RuntimeError:
                        pass
                except Exception:
                    pass

        # ── Path 3: X11 fallback — stored wid OR title search ────────────
        if not applied:
            wid = self._editor_x11_wid
            if not wid:
                try:
                    from pydaw.ui.x11_window_ctl import x11_find_windows
                    for term in ("Pedalboard", self._plugin_name or ""):
                        if not term:
                            continue
                        found = x11_find_windows(term)
                        if found:
                            wid = found[-1]
                            self._editor_x11_wid = wid
                            break
                except Exception:
                    pass
            if wid:
                try:
                    self._editor_shaded_x11 = not self._editor_shaded_x11
                    if self._editor_shaded_x11:
                        from pydaw.ui.x11_window_ctl import x11_iconify
                        applied = x11_iconify(wid)
                    else:
                        from pydaw.ui.x11_window_ctl import x11_activate
                        applied = x11_activate(wid)
                    if applied:
                        try:
                            self._btn_shade.setText(
                                "🔼" if self._editor_shaded_x11 else "🔽"
                            )
                        except RuntimeError:
                            pass
                except Exception:
                    pass

    # ── X11 Window Finder (pure Python, v0.0.20.402) ──────────────────────

    def _x11_find_editor_wid(self) -> int:
        """Find the X11 window ID of the native editor for this plugin.

        Strategy (v0.0.20.402):
        0. Use stored wid from snapshot diff (most reliable!)
        1. Search by title
        2. FALLBACK: non-DAW window exclusion
        """
        # ── Step 0: Use stored wid from snapshot diff ───────────────────
        if self._editor_x11_wid:
            return self._editor_x11_wid

        try:
            from pydaw.ui.x11_window_ctl import (
                x11_find_windows, x11_find_editor_candidates, x11_list_all_windows
            )
        except ImportError:
            return 0

        import os, sys

        # ── Step 1: Search by title ─────────────────────────────────────
        search_terms = []
        if self._editor_window_title:
            search_terms.append(self._editor_window_title)
        if self._plugin_name:
            search_terms.append(self._plugin_name)
        if self._vst3_path:
            basename = os.path.splitext(
                os.path.basename(self._vst3_path.split("::pydaw_plugin::")[0])
            )[0]
            if basename and basename not in search_terms:
                search_terms.append(basename)
        search_terms.append("Pedalboard")

        for term in search_terms:
            wids = x11_find_windows(term)
            if wids:
                return wids[-1]

        # ── Step 2: Fallback — any non-DAW window ──────────────────────
        # JUCE/pedalboard often creates windows with EMPTY titles.
        # If we have an active editor (thread or process running), take
        # the first non-DAW window as the editor.
        has_editor = (
            (getattr(self, "_editor_inproc_thread", None) is not None
             and self._editor_inproc_thread.isRunning())
            or (getattr(self, "_editor_process", None) is not None)
            or (getattr(self, "_vst2_editor_dialog", None) is not None)
        )

        if has_editor:
            candidates = x11_find_editor_candidates(exclude_title="Py DAW")
            if candidates:
                wid, title, wm_class = candidates[-1]  # most recent
                print(f"[X11] Fallback: using non-DAW window 0x{wid:x} "
                      f"title='{title}' class='{wm_class}'",
                      file=sys.stderr, flush=True)
                return wid

        # ── Debug output ────────────────────────────────────────────────
        print(f"[X11] WARN: No editor window found. Searched: {search_terms}",
              file=sys.stderr, flush=True)
        try:
            all_wins = x11_list_all_windows()
            print(f"[X11] All {len(all_wins)} managed windows:",
                  file=sys.stderr, flush=True)
            for wid, title, wm_class in all_wins:
                print(f"[X11]   0x{wid:x} = '{title}' class='{wm_class}'",
                      file=sys.stderr, flush=True)
        except Exception:
            pass
        return 0

    def _toggle_native_editor(self) -> None:
        """Open or close the native VST editor.

        v0.0.20.379 — Strategy:
        1. PRIMARY: In-process QThread — calls show_editor() on the SAME Vst3Fx plugin
           instance that processes audio.  This makes the native editor's meters/analysers
           receive the live audio signal (spectrum, VU, etc.).
        2. FALLBACK: QProcess subprocess (original approach) — used when the Vst3Fx
           instance is not accessible (e.g. engine not yet built).

        Closing: works for both modes.
        """
        # ── Close if already open (either mode) ──────────────────────────
        # v0.0.20.395: Check VST2 editor dialog first
        vst2_dlg = getattr(self, "_vst2_editor_dialog", None)
        if vst2_dlg is not None:
            try:
                vst2_dlg.close()
                vst2_dlg.deleteLater()
            except Exception:
                pass
            self._vst2_editor_dialog = None
            self._on_inproc_editor_closed()
            return

        ip = getattr(self, "_editor_inproc_thread", None)
        if ip is not None and ip.isRunning():
            ip.requestInterruption()
            try:
                # send quit via the plugin's own quit mechanism if possible
                plugin = getattr(ip, "_plugin", None)
                if plugin is not None:
                    try:
                        plugin.show_editor.__func__   # check callable
                    except Exception:
                        pass
            except Exception:
                pass
            ip.quit()
            ip.wait(1000)
            self._on_inproc_editor_closed()
            return

        proc = getattr(self, "_editor_process", None)
        if proc is not None and proc.state() != QProcess.ProcessState.NotRunning:
            try:
                proc.kill()
                proc.waitForFinished(1000)
            except Exception:
                pass
            self._on_editor_process_finished(-1, QProcess.ExitStatus.CrashExit)
            return

        # ── Try in-process first ─────────────────────────────────────────
        # v0.0.20.395: Check if this is a VST2 plugin — use native X11 editor
        if self._vst3_path and self._vst3_path.endswith(".so") and not self._vst3_path.endswith(".vst3"):
            self._launch_vst2_x11_editor()
            return

        vst3_fx = self._get_vst3_fx_instance()
        if vst3_fx is not None:
            self._launch_editor_inprocess(vst3_fx)
        else:
            # Fallback: subprocess
            self._launch_editor_process()

    def _get_vst3_fx_instance(self) -> Optional[Any]:
        """Find the live Vst3Fx instance for this widget's track_id + device_id.

        Navigates: services.audio_engine._track_audio_fx_map[track_id].devices
        Returns None if not found or engine not ready.

        v0.0.20.379
        """
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            if ae is None:
                return None
            fx_map = getattr(ae, "_track_audio_fx_map", None)
            if not fx_map:
                return None
            chain = fx_map.get(self._track_id)
            if chain is None:
                return None
            devices = getattr(chain, "devices", []) or []
            for dev in devices:
                if str(getattr(dev, "device_id", "")) == str(self._device_id):
                    plugin_obj = getattr(dev, "_plugin", None)
                    if plugin_obj is not None and callable(getattr(plugin_obj, "show_editor", None)):
                        return dev
            return None
        except Exception:
            return None

    def _launch_vst2_x11_editor(self) -> None:
        """Open native VST2 editor via X11/Qt embedding.

        v0.0.20.395: Uses effEditOpen with the QWidget's native window handle.
        The plugin draws its GUI directly into our Qt window.
        """
        import os

        # Close existing editor dialog if open
        existing = getattr(self, "_vst2_editor_dialog", None)
        if existing is not None:
            try:
                existing.close()
                existing.deleteLater()
            except Exception:
                pass
            self._vst2_editor_dialog = None
            self._on_inproc_editor_closed()
            return

        # Find the VST2 plugin instance
        vst2_plugin = self._get_vst2_plugin_instance()
        if vst2_plugin is None:
            self._show_editor_error(
                "VST2 Plugin-Instanz nicht gefunden.\n"
                "Das Plugin muss erst geladen sein (Play drücken oder Projekt öffnen)."
            )
            return

        if not vst2_plugin.has_editor:
            self._show_editor_error("Dieses VST2 Plugin hat keinen nativen Editor.")
            return

        # Get preferred size
        w, h = vst2_plugin.editor_get_rect()

        # Create editor dialog
        plugin_name = vst2_plugin.get_effect_name() or os.path.basename(self._vst3_path)
        try:
            dialog = _Vst2EditorDialog(vst2_plugin, plugin_name, w, h, parent=None)
            dialog.editor_closed_signal.connect(self._on_vst2_editor_closed)
            self._vst2_editor_dialog = dialog

            # v0.0.20.409: show() FIRST, then deferred_editor_open()
            # This avoids X11 BadWindow crash on Wayland/XWayland.
            dialog.show()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            ok = dialog.deferred_editor_open()
            if not ok:
                dialog.close()
                dialog.deleteLater()
                self._vst2_editor_dialog = None
                self._show_editor_error(
                    "VST2 Editor: effEditOpen fehlgeschlagen.\n"
                    "Wayland-Tipp: Starte mit QT_QPA_PLATFORM=xcb"
                )
                return

            # Sync pin/shade button visuals with dialog state
            key = plugin_name
            state = _vst_editor_state.get(key, {})
            self._editor_pinned = state.get("pinned", False)
            if self._editor_pinned:
                try:
                    self._btn_pin.setStyleSheet(
                        "QPushButton { background: #3a2a10; border: 1px solid #d4a020; "
                        "border-radius: 4px; color: #f0c040; font-size: 13px; padding: 0; }"
                        "QPushButton:hover { background: #4a3a20; border-color: #e0b030; }"
                    )
                except RuntimeError:
                    pass
            if state.get("shaded", False):
                try:
                    self._btn_shade.setText("🔼")
                except RuntimeError:
                    pass

            # Update button
            btn = getattr(self, "_btn_editor", None)
            if btn is not None:
                btn.setText("✕ Editor schließen")
                btn.setStyleSheet(
                    "QPushButton { background: #2a3a2a; border: 1px solid #4a804a; "
                    "border-radius: 4px; color: #90d490; font-size: 11px; padding: 0 6px; }"
                    "QPushButton:hover { background: #3a4a3a; }"
                )
        except Exception as exc:
            self._show_editor_error(f"VST2 Editor konnte nicht geöffnet werden:\n\n{exc}")

    def _on_vst2_editor_closed(self) -> None:
        """Called when the VST2 editor dialog is closed."""
        self._vst2_editor_dialog = None
        self._on_inproc_editor_closed()

        # Sync params back from plugin to UI
        try:
            vst2_plugin = self._get_vst2_plugin_instance()
            if vst2_plugin is not None:
                for i, info in enumerate(self._param_infos if hasattr(self, '_param_infos') else []):
                    val = vst2_plugin.get_parameter(i)
                    if info.name in self._rows:
                        self._apply_param_from_editor(info.name, val)
        except Exception:
            pass

    def _get_vst2_plugin_instance(self) -> "Any":
        """Find the live _Vst2Plugin instance for this widget's track."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            if ae is None:
                return None

            # Check instrument engines first
            inst_engines = getattr(ae, "_vst_instrument_engines", None)
            if isinstance(inst_engines, dict):
                engine = inst_engines.get(str(self._track_id))
                if engine is not None:
                    plugin = getattr(engine, "_plugin", None)
                    if plugin is not None and hasattr(plugin, "editor_open"):
                        return plugin

            # Check FX chain
            fx_map = getattr(ae, "_track_audio_fx_map", None)
            if fx_map:
                chain = fx_map.get(str(self._track_id))
                if chain is not None:
                    for dev in getattr(chain, "devices", []):
                        if str(getattr(dev, "device_id", "")) == str(self._device_id):
                            plugin = getattr(dev, "_plugin", None)
                            if plugin is not None and hasattr(plugin, "editor_open"):
                                return plugin
        except Exception:
            pass
        return None

    def _launch_editor_inprocess(self, vst3_fx: Any) -> None:
        """Launch native editor in-process via _VstInProcessEditorThread.

        The editor thread calls show_editor() on vst3_fx._plugin — the SAME plugin
        instance used by _apply_rt_params() / process_inplace(), so meters see live audio.

        v0.0.20.379
        """
        import os
        btn = getattr(self, "_btn_editor", None)
        try:
            if btn is not None:
                btn.setText("⏳ Editor…")
                btn.setEnabled(False)
        except RuntimeError:
            pass

        plugin_obj = vst3_fx._plugin

        # Window title
        disp_plugin = self._plugin_name or os.path.splitext(
            os.path.basename(self._vst3_path.split("::pydaw_plugin::")[0])
        )[0] or "VST3"
        track_name = self._get_track_name()
        parts = [disp_plugin]
        if track_name:
            parts.append(f"[{track_name}]")
        parts.append("— Py_DAW")
        window_title = "  ".join(parts)
        self._editor_window_title = window_title  # v0.0.20.402

        thread = _VstInProcessEditorThread(plugin_obj, window_title, parent=None)
        thread.editor_ready.connect(self._on_inproc_editor_ready)
        thread.editor_wid.connect(self._on_inproc_editor_wid)  # v0.0.20.402
        thread.editor_closed.connect(self._on_inproc_editor_closed)
        thread.editor_error.connect(self._on_inproc_editor_error)
        self._editor_inproc_thread = thread

        # v0.0.20.403: Register in module-level dict so thread survives widget destruction
        editor_key = f"{getattr(self, '_track_id', '')}:{getattr(self, '_device_id', '')}"
        _active_editor_threads[editor_key] = {
            "thread": thread,
            "plugin_name": self._plugin_name,
            "vst3_path": self._vst3_path,
        }
        self._editor_registry_key = editor_key

        # Start param poll timer (80ms) for bidirectional sync
        poll = QTimer(self)
        poll.setInterval(80)
        poll.timeout.connect(lambda: self._poll_inproc_params(vst3_fx))
        self._editor_poll_timer = poll

        # v0.0.20.402: Reset detected wid before new editor opens
        self._editor_x11_wid = 0

        thread.start()

    def _on_inproc_editor_ready(self) -> None:
        """Native editor window is opening (in-process mode).

        v0.0.20.402: Just updates the UI button. Window ID detection is now
        handled by _on_inproc_editor_wid (signal from the editor thread itself).
        """
        btn = getattr(self, "_btn_editor", None)
        try:
            if btn is not None:
                btn.setText("✕ Editor schließen")
                btn.setEnabled(True)
                btn.setStyleSheet(
                    "QPushButton { background: #2a3a2a; border: 1px solid #4a804a; "
                    "border-radius: 4px; color: #90d490; font-size: 11px; padding: 0 6px; }"
                    "QPushButton:hover { background: #3a4a3a; }"
                )
        except RuntimeError:
            pass
        poll = getattr(self, "_editor_poll_timer", None)
        if poll is not None:
            poll.start()

    def _on_inproc_editor_wid(self, wid: int) -> None:
        """Received the X11 window ID of the editor from the editor thread.

        v0.0.20.403: Creates a VstEditorContainer (Qt wrapper) and embeds the
        native editor via QWindow.fromWinId + createWindowContainer.
        No more X11 window search needed for Pin/Shade — we OWN the container.
        """
        self._editor_x11_wid = wid
        import sys, os
        print(f"[VstEditorContainer] Editor wid captured: 0x{wid:x}",
              file=sys.stderr, flush=True)

        # Build plugin display name
        plugin_name = self._plugin_name or ""
        if not plugin_name and self._vst3_path:
            plugin_name = os.path.splitext(
                os.path.basename(self._vst3_path.split("::pydaw_plugin::")[0])
            )[0]
        plugin_name = plugin_name or "VST3"

        # Create the Qt wrapper container
        try:
            container = VstEditorContainer(
                native_wid=wid,
                plugin_name=plugin_name,
                width=960, height=720,
                parent=None,  # standalone window
            )
            container.editor_closed.connect(self._on_vst3_container_closed)
            self._vst3_editor_container = container
            container.show()
        except Exception as exc:
            print(f"[VstEditorContainer] Creation failed: {exc}",
                  file=sys.stderr, flush=True)

    def _on_vst3_container_closed(self) -> None:
        """Called when user closes the VstEditorContainer."""
        self._vst3_editor_container = None
        # Close the actual editor (kill the show_editor thread)
        ip = getattr(self, "_editor_inproc_thread", None)
        if ip is not None and ip.isRunning():
            ip.requestInterruption()
            ip.quit()
            ip.wait(1000)

    def _on_inproc_editor_closed(self) -> None:
        """Native editor window was closed (in-process mode)."""
        poll = getattr(self, "_editor_poll_timer", None)
        if poll is not None:
            try:
                poll.stop()
            except Exception:
                pass
        self._editor_poll_timer = None
        self._editor_inproc_thread = None
        # v0.0.20.403: Remove from module-level registry
        key = getattr(self, "_editor_registry_key", "")
        if key:
            _active_editor_threads.pop(key, None)
        self._editor_shaded_x11 = False  # v0.0.20.402: reset X11 shade state
        self._editor_x11_wid = 0          # v0.0.20.402: reset detected wid
        # v0.0.20.403: Close the Qt wrapper container if open
        container = getattr(self, "_vst3_editor_container", None)
        if container is not None:
            try:
                container.close()
                container.deleteLater()
            except Exception:
                pass
            self._vst3_editor_container = None
        btn = getattr(self, "_btn_editor", None)
        try:
            if btn is not None:
                btn.setText("🎛 Editor")
                btn.setEnabled(True)
                btn.setStyleSheet(
                    "QPushButton { background: #2a2a3a; border: 1px solid #555; "
                    "border-radius: 4px; color: #c8c8d4; font-size: 11px; padding: 0 6px; }"
                    "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
                    "QPushButton:disabled { color: #666; border-color: #444; }"
                )
        except RuntimeError:
            pass
        # Reset shade button when editor closes
        try:
            btn_shade = getattr(self, "_btn_shade", None)
            if btn_shade is not None:
                btn_shade.setText("🔽")
        except RuntimeError:
            pass

    def _on_inproc_editor_error(self, msg: str) -> None:
        """In-process editor failed — fall back to subprocess."""
        self._on_inproc_editor_closed()
        # Fallback: try subprocess
        self._launch_editor_process()

    def _poll_inproc_params(self, vst3_fx: Any) -> None:
        """Poll raw_value from live plugin and sync to RTParamStore + UI sliders.

        Called every 80ms by _editor_poll_timer while the in-process editor is open.
        This implements bidirectional sync: native editor knob changes → PyDAW sliders.

        v0.0.20.379
        """
        try:
            plugin = vst3_fx._plugin
            pb_params = plugin.parameters
        except Exception:
            return
        for name, param in pb_params.items():
            try:
                val = float(param.raw_value)
                row_data = self._rows.get(name)
                if row_data is None:
                    continue
                _, ctrl, spn, (mn, mx, _df) = row_data
                # Compare to current RT value to avoid redundant updates
                rt = self._rt()
                key = self._key(name)
                cur = mn
                if rt is not None:
                    try:
                        cur = float(rt.get_smooth(key, mn) if hasattr(rt, "get_smooth")
                                    else rt.get_param(key, mn))
                    except Exception:
                        cur = mn
                if abs(val - cur) > 1e-5:
                    self._apply_param_from_editor(name, val)
            except Exception:
                continue

    def _launch_editor_process(self) -> None:
        """Spawn vst_gui_process.py as a QProcess for the native VST editor.

        v0.0.20.376 — split_plugin_reference() löst das kombinierte
        PyDAW-Referenzformat (/path/to.vst3::pydaw_plugin::Name) in den
        echten Dateipfad + Plugin-Namen auf, bevor wir es an pedalboard übergeben.
        Separate stdout/stderr channels für stdin-Schreiben.
        """
        import sys, os

        btn = getattr(self, "_btn_editor", None)
        if btn is not None:
            btn.setText("⏳ Editor…")
            btn.setEnabled(False)

        helper_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "audio", "vst_gui_process.py"
        )

        if not os.path.isfile(helper_path):
            self._show_editor_error(f"Helper nicht gefunden: {helper_path}")
            return

        # ── Pfad splitten: kombiniertes PyDAW-Format → echter Dateipfad + Name ──
        # _vst3_path kann sein:
        #   /usr/lib/vst3/foo.vst3                       (einfaches Plugin)
        #   /usr/lib/vst3/foo.vst3::pydaw_plugin::Bar    (Sub-Plugin in Bundle)
        try:
            from pydaw.audio.vst3_host import split_plugin_reference
            real_path, ref_name = split_plugin_reference(self._vst3_path)
        except Exception:
            real_path, ref_name = self._vst3_path, ""

        # Expliziter _plugin_name überschreibt den extrahierten ref_name
        plugin_name_for_editor = self._plugin_name or ref_name

        proc = QProcess()  # v0.0.20.403: parent=None so it survives widget destruction
        # SeparateChannels so we can write JSON commands to stdin
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        # v0.0.20.397 — Wayland Auto-Fix: force XCB for native VST editors
        try:
            from PyQt6.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            sess = (os.environ.get("XDG_SESSION_TYPE", "") or "").lower()
            has_wayland = bool(os.environ.get("WAYLAND_DISPLAY", ""))
            qpa = (os.environ.get("QT_QPA_PLATFORM", "") or "").lower()
            if (sess == "wayland") or has_wayland or qpa.startswith("wayland"):
                env.insert("QT_QPA_PLATFORM", "xcb")
            proc.setProcessEnvironment(env)
        except Exception:
            pass

        proc.readyReadStandardOutput.connect(self._on_editor_stdout)
        proc.finished.connect(self._on_editor_process_finished)
        proc.errorOccurred.connect(self._on_editor_process_error)

        # Build window title: "PluginName  [TrackName]  — Py_DAW"
        disp_plugin = plugin_name_for_editor or os.path.splitext(
            os.path.basename(real_path or "")
        )[0] or "VST3"
        track_name = self._get_track_name()
        title_parts = [disp_plugin]
        if track_name:
            title_parts.append(f"[{track_name}]")
        title_parts.append("— Py_DAW")
        window_title = "  ".join(title_parts)
        self._editor_window_title = window_title  # v0.0.20.402

        # Übergabe: echter Dateipfad als pos. Arg 1, Plugin-Name als pos. Arg 2
        args = [helper_path, real_path]
        if plugin_name_for_editor:
            args.append(plugin_name_for_editor)
        args += ["--title", window_title]
        if track_name:
            args += ["--track", track_name]

        proc.start(sys.executable, args)
        self._editor_process = proc

        # v0.0.20.403: Store in module-level registry to prevent GC on widget destruction
        editor_key = f"{getattr(self, '_track_id', '')}:{getattr(self, '_device_id', '')}"
        _active_editor_threads[editor_key] = {
            "process": proc,
            "plugin_name": self._plugin_name,
            "vst3_path": self._vst3_path,
        }
        self._editor_registry_key = editor_key

    def _on_editor_stdout(self) -> None:
        """Parse JSON event lines from the editor subprocess.

        Handles:
        - "ready"  → button state + initial param sync from subprocess
        - "param"  → bidirectional sync: apply to RTParamStore + update slider UI
        - "state"  → full state blob transfer for preset sync
        - "error"  → show warning dialog
        - "closed" → cleanup (also triggered by process finished signal)

        v0.0.20.459 — Line buffering for large state blobs (Surge XT preset
        state can be 500KB+ base64 in a single JSON line)
        """
        import json, sys
        proc = self._editor_process
        if proc is None:
            return
        try:
            raw = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        except Exception:
            return

        # Append to buffer and process complete lines
        self._editor_stdout_buffer += raw
        lines = self._editor_stdout_buffer.split("\n")
        # Keep last element (might be incomplete)
        self._editor_stdout_buffer = lines[-1]
        complete_lines = lines[:-1]

        for line in complete_lines:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except Exception:
                continue
            event = evt.get("event", "")
            if event == "ready":
                btn = getattr(self, "_btn_editor", None)
                if btn is not None:
                    try:
                        btn.setText("✕ Editor schließen")
                        btn.setEnabled(True)
                        btn.setStyleSheet(
                            "QPushButton { background: #2a3a2a; border: 1px solid #4a804a; "
                            "border-radius: 4px; color: #90d490; font-size: 11px; padding: 0 6px; }"
                            "QPushButton:hover { background: #3a4a3a; }"
                        )
                    except RuntimeError:
                        pass
                # Apply initial params from subprocess snapshot
                for p in (evt.get("params") or []):
                    try:
                        self._apply_param_from_editor(str(p["name"]), float(p["value"]))
                    except Exception:
                        pass

            elif event == "param":
                # Native editor changed a param — apply to RT store + update slider
                try:
                    name = str(evt.get("name", ""))
                    value = float(evt.get("value", 0.0))
                    if name:
                        self._apply_param_from_editor(name, value)
                except Exception:
                    pass

            elif event == "state":
                # v0.0.20.460: Debounced state blob from editor (preset change)
                # Store latest blob, apply after 500ms delay to avoid rapid re-applies
                try:
                    blob_b64 = str(evt.get("blob", ""))
                    if blob_b64:
                        self._pending_state_blob = blob_b64
                        if self._state_apply_timer is None:
                            self._state_apply_timer = QTimer(self)
                            self._state_apply_timer.setSingleShot(True)
                            self._state_apply_timer.timeout.connect(self._deferred_apply_state)
                        # Restart timer — only the LAST blob within 500ms gets applied
                        self._state_apply_timer.start(500)
                except Exception:
                    pass

            elif event == "error":
                msg = str(evt.get("msg", "Unbekannter Fehler"))
                self._show_editor_error(msg)

    def _apply_param_from_editor(self, name: str, value: float) -> None:
        """Apply a parameter value arriving from the native editor subprocess.

        Writes to RTParamStore and updates the matching slider/spinbox/checkbox
        in the UI — with signal blocking to prevent an echo back to the editor.

        v0.0.20.375
        """
        # ── RTParamStore ────────────────────────────────────────────────────
        rt = self._rt()
        if rt is not None:
            key = self._key(name)
            try:
                if hasattr(rt, "set_smooth"):
                    rt.set_smooth(key, value)
                elif hasattr(rt, "set_param"):
                    rt.set_param(key, value)
            except Exception:
                pass

        # ── UI slider / spinbox / checkbox ──────────────────────────────────
        row_data = self._rows.get(name)
        if row_data is None:
            return
        try:
            _, ctrl, spn, (mn, mx, _df) = row_data
            clamped = max(float(mn), min(float(mx), value))
            if isinstance(ctrl, QCheckBox):
                with QSignalBlocker(ctrl):
                    ctrl.setChecked(clamped >= 0.5)
            elif isinstance(ctrl, QSlider):
                sld_val = int((clamped - mn) / max(1e-9, mx - mn) * 1000.0)
                with QSignalBlocker(ctrl):
                    ctrl.setValue(sld_val)
                if spn is not None:
                    with QSignalBlocker(spn):
                        spn.setValue(clamped)
        except Exception:
            pass

        # Schedule project persist
        try:
            self._debounce.start()
        except Exception:
            pass

    def _deferred_apply_state(self) -> None:
        """Apply the pending state blob after debounce delay.

        v0.0.20.460: Runs 500ms after last state event. Only applies the
        LATEST blob (multiple rapid preset changes → single apply).
        Uses a background thread to avoid blocking the Qt main thread.
        """
        import sys
        blob = self._pending_state_blob
        self._pending_state_blob = ""
        if not blob:
            return
        print(f"[VST3-PRESET] Deferred apply: {len(blob)} chars b64",
              file=sys.stderr, flush=True)
        self._apply_state_blob_from_editor(blob)

    def _apply_state_blob_from_editor(self, blob_b64: str) -> None:
        """Apply a full plugin state blob from the editor subprocess.

        v0.0.20.458: When the editor detects a preset change (state hash differs),
        it sends the full raw_state as base64. We apply it to the audio engine's
        LIVE plugin instance so the sound actually changes.
        """
        import sys
        try:
            import base64
            raw = base64.b64decode(blob_b64)
        except Exception as e:
            print(f"[VST3] State blob decode error: {e}", file=sys.stderr, flush=True)
            return

        # Find the live plugin instance in the audio engine
        try:
            ae = self._services.audio_engine if hasattr(self._services, "audio_engine") else None
            if ae is None:
                return

            # Check instrument engines first (Surge XT, Dexed, etc.)
            engines = getattr(ae, "_vst_instrument_engines", {})
            engine = engines.get(self._track_id)
            if engine is not None:
                plugin = getattr(engine, "_plugin", None)
                if plugin is not None:
                    try:
                        setattr(plugin, "raw_state", raw)
                        print(f"[VST3] Applied editor state blob to instrument engine "
                              f"(track={self._track_id}, {len(raw)} bytes)",
                              file=sys.stderr, flush=True)
                        return
                    except Exception as e:
                        print(f"[VST3] Failed to apply state blob to instrument: {e}",
                              file=sys.stderr, flush=True)

            # Check FX chain (for audio effects)
            fx_map = getattr(ae, "_track_audio_fx_map", {})
            chain_fx = fx_map.get(self._track_id) if fx_map else None
            if chain_fx is not None:
                for dev in getattr(chain_fx, "devices", []):
                    if str(getattr(dev, "device_id", "")) == self._device_id:
                        plugin = getattr(dev, "_plugin", None)
                        if plugin is not None:
                            try:
                                setattr(plugin, "raw_state", raw)
                                print(f"[VST3] Applied editor state blob to FX device "
                                      f"(track={self._track_id}, dev={self._device_id}, {len(raw)} bytes)",
                                      file=sys.stderr, flush=True)
                                return
                            except Exception as e:
                                print(f"[VST3] Failed to apply state to FX: {e}",
                                      file=sys.stderr, flush=True)
                        break
        except Exception as e:
            print(f"[VST3] State blob apply error: {e}", file=sys.stderr, flush=True)

    def _on_editor_process_finished(self, code: int, status) -> None:
        """Reset button after editor subprocess exits.

        v0.0.20.377 — guard against RuntimeError when the widget (and its
        _btn_editor child) was already destroyed before the QProcess signal fires.
        This happens when the FX chain panel is closed while an editor is open.
        """
        self._editor_process = None
        self._editor_stdout_buffer = ""  # v0.0.20.459: reset line buffer
        # v0.0.20.403: Remove from module-level registry
        key = getattr(self, "_editor_registry_key", "")
        if key:
            _active_editor_threads.pop(key, None)
        btn = getattr(self, "_btn_editor", None)
        if btn is None:
            return
        try:
            # sip.isdeleted() is the canonical check; fall back to a setAttribute
            # probe which raises RuntimeError if the underlying C++ object is gone.
            btn.setText("🎛 Editor")
            btn.setEnabled(True)
            btn.setStyleSheet(
                "QPushButton { background: #2a2a3a; border: 1px solid #555; "
                "border-radius: 4px; color: #c8c8d4; font-size: 11px; padding: 0 6px; }"
                "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
                "QPushButton:disabled { color: #666; border-color: #444; }"
            )
        except RuntimeError:
            # Widget already deleted — nothing to update
            pass

    def _on_editor_process_error(self, error) -> None:
        """Handle QProcess launch errors.

        v0.0.20.377 — guard _show_editor_error too; widget may be gone.
        """
        try:
            self._show_editor_error(f"Prozess-Fehler: {error}")
        except RuntimeError:
            pass
        self._on_editor_process_finished(-1, None)

    def _show_editor_error(self, msg: str) -> None:
        """Display a short toast-style status message for editor errors."""
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "VST Editor",
                f"Nativer Editor konnte nicht geöffnet werden:\n\n{msg}\n\n"
                "Tipp: Stelle sicher dass pedalboard installiert ist\n"
                "und das Plugin show_editor() unterstützt (X11/macOS/Windows)."
            )
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        """Gracefully shut down editor + loader threads when widget is closed.

        v0.0.20.379 — Also handles _VstInProcessEditorThread cleanup.
        v0.0.20.381 — FIX: Also stops _Vst3ParamLoader QThread to prevent
        'QThread: Destroyed while thread is still running' fatal abort.
        """
        # ── Async param loader thread (v0.0.20.381 fix) ──────────────────
        loader = getattr(self, "_loader", None)
        if loader is not None:
            try:
                if loader.isRunning():
                    loader.quit()
                    if not loader.wait(1000):
                        loader.terminate()
                        loader.wait(500)
            except Exception:
                pass
            self._loader = None

        # ── In-process editor thread ─────────────────────────────────────
        poll = getattr(self, "_editor_poll_timer", None)
        if poll is not None:
            try:
                poll.stop()
            except Exception:
                pass
        ip = getattr(self, "_editor_inproc_thread", None)
        if ip is not None:
            try:
                ip.quit()
                ip.wait(500)
            except Exception:
                pass
            self._editor_inproc_thread = None

        # ── VST2 native editor dialog (v0.0.20.395) ──────────────────────
        vst2_dlg = getattr(self, "_vst2_editor_dialog", None)
        if vst2_dlg is not None:
            try:
                vst2_dlg.close()
                vst2_dlg.deleteLater()
            except Exception:
                pass
            self._vst2_editor_dialog = None

        # ── Subprocess editor ────────────────────────────────────────────
        proc = getattr(self, "_editor_process", None)
        if proc is not None:
            try:
                proc.readyReadStandardOutput.disconnect()
                proc.finished.disconnect()
                proc.errorOccurred.disconnect()
            except Exception:
                pass
            try:
                proc.terminate()
                if not proc.waitForFinished(500):
                    proc.kill()
                    proc.waitForFinished(500)
            except Exception:
                pass
            self._editor_process = None
        super().closeEvent(event)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── Header ──
        top = QHBoxLayout()
        is_vst2 = "vst2" in self._plugin_id.lower()
        kind_label = QLabel("VST2" if is_vst2 else "VST3")
        kind_label.setStyleSheet("font-weight: 600; color: #e6c86e;")
        top.addWidget(kind_label, 0)

        short_path = os.path.basename(self._vst3_path) if self._vst3_path else "(unknown)"
        self._lbl_path = QLabel(short_path)
        self._lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl_path.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        top.addWidget(self._lbl_path, 1)

        # ── "Open Native Editor" button ──────────────────────────────────────
        self._btn_editor = QPushButton("🎛 Editor")
        self._btn_editor.setToolTip(
            "Natives Plugin-Fenster öffnen (pedalboard show_editor)\n"
            "Das Fenster läuft in einem eigenen Prozess — Audio bleibt stabil."
        )
        self._btn_editor.setFixedHeight(22)
        self._btn_editor.setStyleSheet(
            "QPushButton { background: #2a2a3a; border: 1px solid #555; "
            "border-radius: 4px; color: #c8c8d4; font-size: 11px; padding: 0 6px; }"
            "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
            "QPushButton:disabled { color: #666; border-color: #444; }"
        )
        self._btn_editor.clicked.connect(self._toggle_native_editor)
        top.addWidget(self._btn_editor, 0)

        # ── Pin button (📌 Always on Top for open editor window) ─────────
        self._btn_pin = QPushButton("📌")
        self._btn_pin.setToolTip(
            "Pin: Editor-Fenster bleibt im Vordergrund\n"
            "(Always on Top — auch wenn DAW den Fokus hat)"
        )
        self._btn_pin.setFixedHeight(22)
        self._btn_pin.setFixedWidth(28)
        self._btn_pin.setStyleSheet(
            "QPushButton { background: #2a2a3a; border: 1px solid #555; "
            "border-radius: 4px; color: #aaa; font-size: 13px; padding: 0; }"
            "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
            "QPushButton:disabled { color: #666; border-color: #444; }"
        )
        self._btn_pin.clicked.connect(self._toggle_editor_pin)
        self._editor_pinned = False
        top.addWidget(self._btn_pin, 0)

        # ── Shade button (🔽 Roll-Up for open editor window) ─────────────
        self._btn_shade = QPushButton("🔽")
        self._btn_shade.setToolTip(
            "Einrollen: Editor-Fenster auf Titelleiste minimieren\n"
            "Plugin bleibt geladen — spart Desktop-Platz"
        )
        self._btn_shade.setFixedHeight(22)
        self._btn_shade.setFixedWidth(28)
        self._btn_shade.setStyleSheet(
            "QPushButton { background: #2a2a3a; border: 1px solid #555; "
            "border-radius: 4px; color: #aaa; font-size: 13px; padding: 0; }"
            "QPushButton:hover { background: #3a3a5a; border-color: #9090cc; }"
            "QPushButton:disabled { color: #666; border-color: #444; }"
        )
        self._btn_shade.clicked.connect(self._toggle_editor_shade)
        top.addWidget(self._btn_shade, 0)

        root.addLayout(top)

        # ── Status row ──
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        root.addWidget(self._lbl_status)

        self._lbl_bus_hint = QLabel("")
        self._lbl_bus_hint.setStyleSheet("font-size: 10px; color: #89dceb; font-style: italic;")
        self._lbl_bus_hint.setVisible(False)
        root.addWidget(self._lbl_bus_hint)

        # ── Param source hint (runtime / async / main-thread) ─────────────
        self._lbl_param_source = QLabel("")
        self._lbl_param_source.setStyleSheet("font-size: 10px; color: #6a7080; font-style: italic;")
        self._lbl_param_source.setVisible(False)
        root.addWidget(self._lbl_param_source)

        self._lbl_state_hint = QLabel("")
        self._lbl_state_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        root.addWidget(self._lbl_state_hint)
        self._update_state_hint()

        # ── v0.0.20.652: Preset Browser ──────────────────────────────────────
        try:
            from pydaw.ui.preset_browser_widget import PresetBrowserWidget
            self._preset_browser = PresetBrowserWidget(
                plugin_type="vst3" if "vst3" in self._plugin_id.lower() else "vst2",
                plugin_id=self._plugin_id,
                device_id=self._device_id,
                track_id=self._track_id,
                get_state_fn=self._get_state_b64_for_preset,
                set_state_fn=self._set_state_b64_from_preset,
                get_params_fn=self._get_current_param_values,
                vst3_path=self._vst3_path,
                parent=self,
            )
            self._preset_browser.preset_loaded.connect(self._on_preset_browser_loaded)
            root.addWidget(self._preset_browser)
        except Exception:
            self._preset_browser = None

        # ── Search ──
        self._search = QLineEdit()
        self._search.setPlaceholderText("Parameter suchen…")
        self._search.textChanged.connect(self._apply_filter)
        root.addWidget(self._search)

        # ── Scroll area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._body = QWidget()
        self._body_l = QVBoxLayout(self._body)
        self._body_l.setContentsMargins(0, 0, 0, 0)
        self._body_l.setSpacing(3)
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        self._load_controls_and_build_rows()
        # Note: refresh_from_project() and _ui_sync_timer.start() are now called
        # inside _on_params_loaded() after the async load completes.

        # v0.0.20.525: Connect AutomationManager.parameter_changed → slider follow
        # This makes VST sliders move with drawn automation curves during playback.
        try:
            am = _get_automation_manager(self._services)
            if am is not None and hasattr(am, "parameter_changed"):
                am.parameter_changed.connect(self._on_automation_param_changed)
        except Exception:
            pass

    def _on_automation_param_changed(self, parameter_id: str, value: float) -> None:
        """Update slider/spinbox when automation plays back a value.

        v0.0.20.525: Makes VST2/VST3 sliders follow drawn automation curves.
        Only reacts to parameter_ids that match our prefix (this widget's track+device).
        """
        try:
            pid = str(parameter_id or "")
            if not pid.startswith(self._prefix):
                return
            param_name = pid[len(self._prefix):]
            row_data = self._rows.get(param_name)
            if row_data is None:
                return
            _, widget, spn, (mn, mx, df) = row_data
            if widget is None:
                return
            val = float(value)
            # Update slider + spinbox without re-triggering callbacks
            from PyQt6.QtCore import QSignalBlocker
            if hasattr(widget, 'setValue') and hasattr(widget, 'maximum'):
                # QSlider (range 0-1000)
                if mx > mn:
                    sld_val = int((val - mn) / (mx - mn) * 1000.0)
                    sld_val = max(0, min(1000, sld_val))
                else:
                    sld_val = 0
                with QSignalBlocker(widget):
                    widget.setValue(sld_val)
            elif hasattr(widget, 'setChecked'):
                # QCheckBox
                with QSignalBlocker(widget):
                    widget.setChecked(val >= 0.5)
            if spn is not None:
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            # Also push to RT store for audio-thread
            rt = self._rt()
            if rt is not None:
                key = self._key(param_name)
                try:
                    if hasattr(rt, "set_smooth"):
                        rt.set_smooth(key, float(val))
                    elif hasattr(rt, "set_param"):
                        rt.set_param(key, float(val))
                except Exception:
                    pass
        except Exception:
            pass

    def _load_controls_and_build_rows(self) -> None:
        """Load VST parameter infos with a safe priority order.

        Reihenfolge:
        1. Bereits laufende DSP-Instanz im Audio-Engine-FX-Map wiederverwenden
           (schnell, kein zweiter Plugin-Load, kein Thread-Problem).
        2. Kurz auf den Rebuild warten, falls das Device gerade frisch eingefügt wurde.
        3. Erst danach auf den asynchronen Loader zurückfallen.
        """
        # ── Check availability ──
        try:
            from pydaw.audio.vst3_host import is_available
        except Exception as e:
            self._lbl_status.setText(f"vst3_host import failed: {e}")
            return

        if not is_available():
            self._lbl_status.setText("pedalboard nicht installiert — pip install pedalboard")
            return

        if not self._vst3_path:
            self._lbl_status.setText("Kein Plugin-Pfad")
            return

        infos = self._get_runtime_param_infos()
        if infos:
            self._param_source = "runtime"
            self._on_params_loaded(infos)
            return

        self._runtime_probe_attempts = 0
        self._lbl_status.setText("Warte auf laufende Plugin-Instanz…")
        self._runtime_probe_timer.start(120)

    def _on_load_failed(self, msg: str) -> None:
        text = str(msg or "").strip()
        try:
            if (not self._main_thread_param_retry_done) and ("main thread" in text.lower()):
                self._main_thread_param_retry_done = True
                self._lbl_status.setText("Main-Thread-Reload für Plugin-Parameter…")
                QTimer.singleShot(0, self._load_params_on_main_thread)
                return
            self._lbl_status.setText(f"Laden fehlgeschlagen: {text}")
        except Exception:
            pass

    def _on_loader_finished(self) -> None:
        """Clean up loader QThread after it finishes (v0.0.20.381).

        Since the loader is created without parent (to avoid Qt auto-destroy crash),
        we must explicitly schedule its deletion when it completes.
        """
        try:
            loader = self._loader
            if loader is not None:
                loader.deleteLater()
        except Exception:
            pass

    def _load_params_on_main_thread(self) -> None:
        try:
            from pydaw.audio.vst3_host import describe_controls
            infos = describe_controls(self._vst3_path, plugin_name=self._plugin_name)
            self._param_source = "main-thread"; self._on_params_loaded(list(infos or []))
        except Exception as exc:
            self._on_load_failed(str(exc))

    def _get_runtime_fx(self):
        """Best-effort access to the compiled VST FX object for this device."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            fx_map = getattr(ae, "_track_audio_fx_map", None) if ae is not None else None
            if not isinstance(fx_map, dict):
                return None
            chain = fx_map.get(str(self._track_id))
            devs = getattr(chain, "devices", None)
            if not isinstance(devs, list):
                return None
            for fx in devs:
                try:
                    if str(getattr(fx, "device_id", "")) == str(self._device_id):
                        return fx
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _get_runtime_param_infos(self) -> list:
        """Reuse parameter metadata from the already loaded DSP instance when possible.

        v0.0.20.384: Also checks _vst_instrument_engines for VST instruments.
        v0.0.20.558: Also checks layer engine keys (device_id = "tid:ilayer:N").
        """
        # Try FX chain first (effects)
        fx = self._get_runtime_fx()
        if fx is not None:
            try:
                getter = getattr(fx, "get_param_infos", None)
                infos = getter() if callable(getter) else []
                if infos:
                    return list(infos)
            except Exception:
                pass

        # Try instrument engines (VST instruments like Surge XT)
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            inst_engines = getattr(ae, "_vst_instrument_engines", None) if ae is not None else None
            if isinstance(inst_engines, dict):
                # Check by track_id (normal instruments)
                engine = inst_engines.get(str(self._track_id))
                if engine is not None:
                    getter = getattr(engine, "get_param_infos", None)
                    infos = getter() if callable(getter) else []
                    if infos:
                        return list(infos)
                # v0.0.20.558: Check by device_id (layer engines: "tid:ilayer:N")
                engine = inst_engines.get(str(self._device_id))
                if engine is not None:
                    getter = getattr(engine, "get_param_infos", None)
                    infos = getter() if callable(getter) else []
                    if infos:
                        return list(infos)
        except Exception:
            pass

        return []

    def _get_runtime_vst_host(self):
        """Return the already running VST host object (FX or instrument) for this widget.

        v0.0.20.558: Also checks layer engine keys for instrument layers.
        """
        fx = self._get_runtime_fx()
        if fx is not None:
            return fx
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services is not None else None
            inst_engines = getattr(ae, "_vst_instrument_engines", None) if ae is not None else None
            if isinstance(inst_engines, dict):
                # Check by track_id (normal instruments)
                engine = inst_engines.get(str(self._track_id))
                if engine is not None and not getattr(engine, "_is_layer_dispatcher", False):
                    return engine
                # v0.0.20.558: Check by device_id (layer engines: "tid:ilayer:N")
                engine = inst_engines.get(str(self._device_id))
                if engine is not None:
                    return engine
        except Exception:
            pass
        return None

    def _update_bus_hint(self) -> None:
        lbl = getattr(self, "_lbl_bus_hint", None)
        if lbl is None:
            return
        host = self._get_runtime_vst_host()
        if host is None:
            lbl.setVisible(False)
            return
        in_ch = out_ch = 0
        try:
            getter = getattr(host, "get_main_bus_layout", None)
            if callable(getter):
                in_ch, out_ch = getter()
            else:
                in_ch = int(getattr(host, "_input_channels", 0) or 0)
                out_ch = int(getattr(host, "_output_channels", 0) or 0)
        except Exception:
            in_ch = out_ch = 0
        in_ch = max(0, int(in_ch or 0))
        out_ch = max(0, int(out_ch or 0))
        if in_ch <= 0 and out_ch <= 0:
            lbl.setVisible(False)
            return
        text = f"Main-Bus: {in_ch}→{out_ch}"
        lbl.setText(text)
        lbl.setToolTip(
            "Erkannte Hauptbus-Kanalzahl des bereits laufenden externen VST-Hosts.\n"
            f"Input: {in_ch} Kanal/Kanäle, Output: {out_ch} Kanal/Kanäle."
        )
        lbl.setStyleSheet("font-size: 10px; color: #89dceb; font-style: italic;")
        lbl.setVisible(True)

    def _retry_runtime_param_load(self) -> None:
        infos = self._get_runtime_param_infos()
        if infos:
            self._param_source = "runtime"
            self._on_params_loaded(infos)
            return
        self._runtime_probe_attempts += 1
        # v0.0.20.384: Instrument engines need more time (Surge XT loads ~2s)
        if self._runtime_probe_attempts < 20:
            self._lbl_status.setText("Warte auf laufende Plugin-Instanz…")
            self._runtime_probe_timer.start(250)
            return
        self._start_async_param_loader()

    def _start_async_param_loader(self) -> None:
        try:
            if self._loader is not None and self._loader.isRunning():
                return
        except Exception:
            pass
        self._main_thread_param_retry_done = False
        self._lbl_status.setText("Lade Plugin-Parameter…")
        # v0.0.20.381: Create WITHOUT parent to avoid Qt auto-destroy crash
        # when widget is deleted while thread is still running.
        self._loader = _Vst3ParamLoader(self._vst3_path, self._plugin_name, parent=None)
        self._loader.params_ready.connect(self._on_params_loaded)
        self._loader.load_failed.connect(self._on_load_failed)
        self._loader.finished.connect(self._on_loader_finished)
        self._param_source = "async"
        self._loader.start()

    def _on_params_loaded(self, infos: list) -> None:
        """Called in main thread after background/runtime parameter discovery."""
        try:
            self._runtime_probe_timer.stop()
        except Exception:
            pass
        if not infos:
            self._lbl_status.setText("Keine Parameter gefunden (kein Audio-FX?)")
            self._update_bus_hint()
            self._update_state_hint()
            return
        if self._rows:
            self._update_bus_hint()
            self._update_state_hint()
            return
        self._param_infos = list(infos)
        self._lbl_status.setText(f"{len(self._param_infos)} Parameter")
        self._build_rows_from_infos()
        self._update_bus_hint()
        self._update_param_source_hint()
        self.refresh_from_project()
        try:
            self._ui_sync_timer.start()
        except Exception:
            pass

    def _build_rows_from_infos(self) -> None:
        """Build slider/checkbox rows from self._param_infos.

        v0.0.20.387: Shows first 30 params immediately for all plugins.
        Additional params (>30) are built on-demand via search field.
        """
        # Always show first 30 params immediately
        initial_batch = self._param_infos[:30]
        self._build_rows_batch(initial_batch)

        if len(self._param_infos) > 30:
            # Register RT keys for remaining params without building widgets
            self._register_rt_params_only()
            self._lbl_status.setText(
                f"{len(self._param_infos)} Parameter (zeige 30 — Suchfeld für mehr)"
            )

    def _register_rt_params_only(self) -> None:
        """Register RT param keys without building widgets (for lazy mode)."""
        rt = self._rt()
        if rt is None:
            return
        for info in self._param_infos:
            key = self._key(info.name)
            try:
                if hasattr(rt, "ensure"):
                    rt.ensure(key, float(info.default))
            except Exception:
                pass

    def _build_rows_batch(self, infos_to_build: list) -> None:
        """Build widget rows for a list of param infos. Used by both immediate and lazy paths."""
        for info in infos_to_build:
            if info.name in self._rows:
                continue  # Already built

            mn = float(info.minimum)
            mx = float(info.maximum)
            df = float(info.default)
            if mx <= mn:
                mx = mn + 1.0

            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)

            lbl = QLabel(info.name)
            lbl.setFixedWidth(130)
            lbl.setToolTip(f"{info.name}: [{mn:.4g} … {mx:.4g}] {info.units}")
            rl.addWidget(lbl, 0)

            if info.is_boolean:
                chk = QCheckBox()
                chk.setChecked(df >= 0.5)
                rl.addWidget(chk, 1)
                self._rows[info.name] = (row, chk, None, (mn, mx, df))

                def _make_chk_cb(name, lo, hi):
                    def cb(state):
                        val = hi if state else lo
                        rt = self._rt()
                        if rt is not None:
                            key = self._key(name)
                            try:
                                if hasattr(rt, "set_smooth"):
                                    rt.set_smooth(key, val)
                                elif hasattr(rt, "set_param"):
                                    rt.set_param(key, val)
                            except Exception:
                                pass
                        self._send_to_editor({"cmd": "set_param", "name": name, "value": val})
                        try:
                            self._debounce.start()
                        except Exception:
                            pass
                    return cb
                chk.stateChanged.connect(_make_chk_cb(info.name, mn, mx))
                chk_param_key = self._key(info.name)
                _install_automation_menu(self, lbl, chk_param_key, lambda dv=df: float(dv))
                _install_automation_menu(self, chk, chk_param_key, lambda dv=df: float(dv))
                try:
                    self._automation_params[info.name] = _register_automatable_param(
                        self._services, self._track_id, chk_param_key,
                        str(info.name), float(mn), float(mx), float(df)
                    )
                except Exception:
                    pass

            else:
                sld = QSlider(Qt.Orientation.Horizontal)
                sld.setRange(0, 1000)
                rl.addWidget(sld, 1)

                spn = QDoubleSpinBox()
                spn.setDecimals(4 if not info.is_integer else 0)
                spn.setRange(float(mn), float(mx))
                spn.setSingleStep(max(0.001, (mx - mn) / 200.0))
                spn.setFixedWidth(80)
                if info.units:
                    spn.setSuffix(f" {info.units}")
                rl.addWidget(spn, 0)

                self._rows[info.name] = (row, sld, spn, (mn, mx, df))

                def _make_sld_cb(name, s, sp, lo, hi):
                    def cb(v):
                        val = lo + (v / 1000.0) * (hi - lo)
                        with QSignalBlocker(sp):
                            sp.setValue(float(val))
                        rt = self._rt()
                        if rt is not None:
                            key = self._key(name)
                            try:
                                if hasattr(rt, "set_smooth"):
                                    rt.set_smooth(key, val)
                                elif hasattr(rt, "set_param"):
                                    rt.set_param(key, val)
                            except Exception:
                                pass
                        self._send_to_editor({"cmd": "set_param", "name": name, "value": val})
                        try:
                            self._debounce.start()
                        except Exception:
                            pass
                    return cb

                def _make_spn_cb(name, s, sp, lo, hi):
                    def cb(val):
                        sld_val = int((val - lo) / max(1e-9, hi - lo) * 1000.0)
                        with QSignalBlocker(s):
                            s.setValue(sld_val)
                        rt = self._rt()
                        if rt is not None:
                            key = self._key(name)
                            try:
                                if hasattr(rt, "set_smooth"):
                                    rt.set_smooth(key, float(val))
                                elif hasattr(rt, "set_param"):
                                    rt.set_param(key, float(val))
                            except Exception:
                                pass
                        self._send_to_editor({"cmd": "set_param", "name": name, "value": float(val)})
                        try:
                            self._debounce.start()
                        except Exception:
                            pass
                    return cb

                sld.valueChanged.connect(_make_sld_cb(info.name, sld, spn, mn, mx))
                spn.valueChanged.connect(_make_spn_cb(info.name, sld, spn, mn, mx))

                param_key = self._key(info.name)
                _install_automation_menu(self, lbl, param_key, lambda dv=df: float(dv))
                _install_automation_menu(self, sld, param_key, lambda dv=df: float(dv))
                _install_automation_menu(self, spn, param_key, lambda dv=df: float(dv))
                try:
                    self._automation_params[info.name] = _register_automatable_param(
                        self._services, self._track_id, param_key,
                        str(info.name), float(mn), float(mx), float(df)
                    )
                except Exception:
                    pass

            self._body_l.addWidget(row)

    def _apply_filter(self, text: str) -> None:
        """Filter visible rows. For large plugins, builds matching rows on demand.

        v0.0.20.386: Lazy building — only creates widget rows for params that match
        the search text, up to 60 at a time. Prevents 775-widget freeze.
        """
        t = text.strip().lower()

        # For large plugins with lazy mode: build matching rows on demand
        if len(self._param_infos) > 30 and t:
            matching = [info for info in self._param_infos if t in info.name.lower()]
            # Build rows for matches that don't exist yet (max 60)
            to_build = [info for info in matching[:60] if info.name not in self._rows]
            if to_build:
                self._build_rows_batch(to_build)

        # Show/hide existing rows
        visible_count = 0
        for name, row_data in self._rows.items():
            row_widget = row_data[0]
            try:
                matches = (t == "" or t in name.lower())
                if matches and visible_count < 60:
                    row_widget.setVisible(True)
                    visible_count += 1
                else:
                    row_widget.setVisible(False)
            except Exception:
                pass

        # Update status for large plugins
        if len(self._param_infos) > 30:
            if t:
                total_matches = sum(1 for info in self._param_infos if t in info.name.lower())
                shown = min(visible_count, 60)
                self._lbl_status.setText(f"{total_matches} Treffer / {len(self._param_infos)} Parameter (zeige {shown})")
            else:
                self._lbl_status.setText(f"{len(self._param_infos)} Parameter (zeige 30 — Suchfeld für mehr)")

    def _sync_from_rt(self) -> None:
        rt = self._rt()
        if rt is None:
            return
        for name, row_data in self._rows.items():
            row_widget, ctrl, spn, (mn, mx, df) = row_data
            # v0.0.20.386: Skip hidden rows (performance for 775-param plugins)
            try:
                if not row_widget.isVisible():
                    continue
            except Exception:
                pass
            key = self._key(name)
            try:
                if hasattr(rt, "get_smooth"):
                    val = float(rt.get_smooth(key, df))
                elif hasattr(rt, "get_param"):
                    val = float(rt.get_param(key, df))
                else:
                    continue
                val = max(mn, min(mx, val))
                if isinstance(ctrl, QCheckBox):
                    with QSignalBlocker(ctrl):
                        ctrl.setChecked(val >= 0.5)
                elif isinstance(ctrl, QSlider):
                    sld_val = int((val - mn) / max(1e-9, mx - mn) * 1000.0)
                    with QSignalBlocker(ctrl):
                        ctrl.setValue(sld_val)
                    if spn is not None:
                        with QSignalBlocker(spn):
                            spn.setValue(val)
            except Exception:
                continue

    def refresh_from_project(self) -> None:
        """Load saved parameter values from project device params."""
        try:
            ps = getattr(self._services, "project_service", None) if self._services else None
            proj = getattr(ps, "project", None) if ps else None
            if proj is None:
                return
            tracks = getattr(proj, "tracks", []) or []
            for t in tracks:
                if str(getattr(t, "id", "")) != self._track_id:
                    continue
                chain = getattr(t, "audio_fx_chain", None)
                if not isinstance(chain, dict):
                    return
                for dev in (chain.get("devices") or []):
                    if str(dev.get("id", "")) != self._device_id:
                        continue
                    saved = dev.get("params", {}) or {}
                    self._update_state_hint()
                    for name, row_data in self._rows.items():
                        if name not in saved:
                            continue
                        row_widget, ctrl, spn, (mn, mx, df) = row_data
                        try:
                            val = float(saved[name])
                            val = max(mn, min(mx, val))
                            if isinstance(ctrl, QCheckBox):
                                with QSignalBlocker(ctrl):
                                    ctrl.setChecked(val >= 0.5)
                            elif isinstance(ctrl, QSlider):
                                sld_val = int((val - mn) / max(1e-9, mx - mn) * 1000.0)
                                with QSignalBlocker(ctrl):
                                    ctrl.setValue(sld_val)
                                if spn is not None:
                                    with QSignalBlocker(spn):
                                        spn.setValue(val)
                        except Exception:
                            continue
                    return
        except Exception:
            pass

    # ── v0.0.20.652: Preset Browser callbacks ──────────────────────────────

    def _get_state_b64_for_preset(self) -> str:
        """Get the current plugin state as Base64 for preset saving / A/B capture."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            if ae is not None:
                # Try instrument engines
                engines = getattr(ae, "_vst_instrument_engines", {})
                engine = engines.get(self._track_id)
                if engine is not None:
                    try:
                        b64 = engine.get_raw_state_b64()
                        if b64:
                            return b64
                    except Exception:
                        pass
                # Try FX chain
                fx_map = getattr(ae, "_track_audio_fx_map", {})
                chain_fx = fx_map.get(self._track_id) if fx_map else None
                if chain_fx is not None:
                    for dev in getattr(chain_fx, "devices", []):
                        if str(getattr(dev, "device_id", "")) == self._device_id:
                            try:
                                b64 = dev.get_raw_state_b64()
                                if b64:
                                    return b64
                            except Exception:
                                pass
            # Fallback: project data
            dev = self._get_project_device()
            if isinstance(dev, dict):
                params = dev.get("params") or {}
                return str(params.get("__ext_state_b64") or "")
        except Exception:
            pass
        return ""

    def _set_state_b64_from_preset(self, state_b64: str) -> bool:
        """Apply a Base64 state blob to the live plugin."""
        if not state_b64:
            return False
        try:
            self._apply_state_blob_from_editor(state_b64)
            dev = self._get_project_device()
            if isinstance(dev, dict):
                if not isinstance(dev.get("params"), dict):
                    dev["params"] = {}
                dev["params"]["__ext_state_b64"] = state_b64
            QTimer.singleShot(150, self._sync_from_rt_once)
            self._update_state_hint()
            return True
        except Exception:
            return False

    def _get_current_param_values(self) -> dict:
        """Get current parameter values from UI sliders."""
        result = {}
        try:
            for name, row_data in self._rows.items():
                row_widget, ctrl, spn, (mn, mx, df) = row_data
                if isinstance(ctrl, QCheckBox):
                    result[name] = mx if ctrl.isChecked() else mn
                elif spn is not None:
                    result[name] = spn.value()
        except Exception:
            pass
        return result

    def _sync_from_rt_once(self) -> None:
        """One-shot sync of all sliders from RT store (after preset load)."""
        try:
            self._sync_from_rt()
        except Exception:
            pass

    def _on_preset_browser_loaded(self, preset_name: str) -> None:
        """Called when the preset browser loads a preset."""
        try:
            self._lbl_status.setText(f"Preset: {preset_name}")
            self._lbl_status.setStyleSheet("font-size: 11px; color: #7bd389;")
            QTimer.singleShot(200, self._sync_from_rt_once)
            self._update_state_hint()
        except Exception:
            pass

    def _flush_to_project(self) -> None:
        """Persist current values to project device params."""
        try:
            ps = getattr(self._services, "project_service", None) if self._services else None
            proj = getattr(ps, "project", None) if ps else None
            if proj is None:
                return
            tracks = getattr(proj, "tracks", []) or []
            for t in tracks:
                if str(getattr(t, "id", "")) != self._track_id:
                    continue
                chain = getattr(t, "audio_fx_chain", None)
                if not isinstance(chain, dict):
                    return
                for dev in (chain.get("devices") or []):
                    if str(dev.get("id", "")) != self._device_id:
                        continue
                    if not isinstance(dev.get("params"), dict):
                        dev["params"] = {}
                    for name, row_data in self._rows.items():
                        row_widget, ctrl, spn, (mn, mx, df) = row_data
                        try:
                            if isinstance(ctrl, QCheckBox):
                                val = mx if ctrl.isChecked() else mn
                            elif spn is not None:
                                val = spn.value()
                            else:
                                continue
                            dev["params"][name] = float(val)
                        except Exception:
                            continue
                    self._update_state_hint()
                    # v0.0.20.652: Notify preset browser of param change for undo
                    try:
                        pb = getattr(self, "_preset_browser", None)
                        if pb is not None:
                            pb.notify_param_changed()
                    except Exception:
                        pass
                    try:
                        if hasattr(ps, "mark_dirty"):
                            ps.mark_dirty()
                    except Exception:
                        pass
                    return
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# CLAP Audio-FX Widget (v0.0.20.457)
# ═══════════════════════════════════════════════════════════════════════════════

class ClapAudioFxWidget(QWidget):
    """Generic CLAP Audio-FX parameter widget (via ctypes host).

    Shows all CLAP parameters as sliders/spinboxes.
    Writes values to RTParamStore and persists into device params.
    Supports native CLAP GUI embedding via clap.gui extension.

    v0.0.20.458 — CLAP live hosting + Editor + Mono/Stereo bridging
    """

    def __init__(self, services: Any, track_id: str, device_id: str,
                 plugin_id: str, clap_ref: str, clap_plugin_id: str = "", parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = str(track_id or "")
        self._device_id = str(device_id or "")
        self._plugin_id = str(plugin_id or "")
        self._clap_ref = str(clap_ref or "")
        self._clap_plugin_id = str(clap_plugin_id or "")

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._flush_to_project)

        self._param_infos: list = []
        self._rows: dict = {}
        self._automation_params: dict = {}  # param_name -> AutomatableParameter handle
        self._prefix = f"afx:{self._track_id}:{self._device_id}:clap:"
        # v0.0.20.538: UI sync timer — polls RT store to update sliders during automation
        self._ui_sync_timer = QTimer(self)
        self._ui_sync_timer.setInterval(60)
        self._ui_sync_timer.timeout.connect(self._sync_from_rt)
        self._editor_window = None  # QWidget for native GUI embedding
        self._editor_gui_container = None  # container for plugin GUI inside editor
        self._has_gui = False
        self._next_param_index = 0
        self._initial_param_batch = 30
        self._param_load_more_batch = 60
        self._runtime_probe_attempts = 0
        self._live_plugin_cache = None
        self._live_plugin_cache_source = ""
        self._last_find_log_key = None
        self._editor_pump = QTimer(self)
        self._editor_pump.setInterval(16)
        self._editor_pump.timeout.connect(self._pump_editor_gui)
        self._editor_prime_frames = 0
        self._editor_open_pending = False
        self._editor_deferred_timer = QTimer(self)
        self._editor_deferred_timer.setSingleShot(True)
        self._editor_deferred_timer.timeout.connect(self._open_editor_deferred)
        self._runtime_probe_timer = QTimer(self)
        self._runtime_probe_timer.setSingleShot(True)
        self._runtime_probe_timer.timeout.connect(self._retry_runtime_param_load)

        self._editor_fd_notifiers: dict = {}  # (fd, flag) -> QSocketNotifier
        self._editor_gui_timers: dict = {}  # timer_id -> QTimer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header row with name + editor button
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr = QLabel(f"🔌 CLAP: {self._clap_plugin_id or os.path.basename(self._clap_ref)}")
        hdr.setStyleSheet("color:#4fc3f7; font-weight:bold; font-size:11px;")
        hdr_row.addWidget(hdr, 1)

        self._btn_editor = QPushButton("🎛 Editor")
        self._btn_editor.setFixedHeight(22)
        self._btn_editor.setFixedWidth(80)
        self._btn_editor.setToolTip("Nativen CLAP-Editor öffnen (Plugin-GUI)")
        self._btn_editor.setVisible(False)  # shown only if plugin has GUI
        self._btn_editor.clicked.connect(self._toggle_editor)
        hdr_row.addWidget(self._btn_editor)
        layout.addLayout(hdr_row)

        # v0.0.20.652: Unified Preset Browser (replaces old v0.0.20.569 row)
        try:
            from pydaw.ui.preset_browser_widget import PresetBrowserWidget
            self._preset_browser = PresetBrowserWidget(
                plugin_type="clap",
                plugin_id=self._clap_plugin_id or self._clap_ref,
                device_id=self._device_id,
                track_id=self._track_id,
                get_state_fn=self._get_state_b64_for_preset,
                set_state_fn=self._set_state_b64_from_preset,
                get_params_fn=self._get_current_param_values_for_preset,
                parent=self,
            )
            layout.addWidget(self._preset_browser)
        except Exception:
            self._preset_browser = None
        # Legacy compat: create hidden preset combo so old methods don't crash
        self._preset_combo = QComboBox()
        self._preset_combo.setVisible(False)

        self._status = QLabel("Lade Parameter…")
        self._status.setStyleSheet("color:#888; font-size:10px; font-style:italic;")
        layout.addWidget(self._status)

        self._search = QLineEdit()
        self._search.setPlaceholderText("CLAP-Parameter suchen…")
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._btn_more = QPushButton("Mehr Parameter laden")
        self._btn_more.setFixedHeight(22)
        self._btn_more.clicked.connect(self._load_more_rows)
        self._btn_more.setVisible(False)
        layout.addWidget(self._btn_more)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setMaximumHeight(400)
        self._params_container = QWidget()
        self._params_layout = QVBoxLayout(self._params_container)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._params_layout.setSpacing(1)
        self._params_layout.addStretch(1)
        self._scroll_area.setWidget(self._params_container)
        layout.addWidget(self._scroll_area)

        # Load parameters in background via QTimer to not block init
        QTimer.singleShot(50, self._load_params)
        # v0.0.20.653: Old v569 preset scan removed — unified PresetBrowserWidget handles refresh

        # v0.0.20.526: Connect AutomationManager.parameter_changed → slider follow
        try:
            am = _get_automation_manager(self._services)
            if am is not None and hasattr(am, "parameter_changed"):
                am.parameter_changed.connect(self._on_automation_param_changed)
        except Exception:
            pass
        # v0.0.20.538: Start RT sync timer for continuous automation following
        try:
            self._ui_sync_timer.start()
        except Exception:
            pass

    def _sync_from_rt(self) -> None:
        """v0.0.20.538: Poll RT store to update CLAP sliders during automation playback."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            rt = getattr(ae, "rt_params", None) if ae else None
            if rt is None:
                return
            from PyQt6.QtCore import QSignalBlocker
            for name, row_data in self._rows.items():
                try:
                    _row, ctrl, spn, (mn, mx, df) = row_data
                    if _row is not None and not _row.isVisible():
                        continue
                except (ValueError, TypeError):
                    continue
                key = self._prefix + name
                try:
                    if hasattr(rt, "get_smooth"):
                        val = float(rt.get_smooth(key, df))
                    elif hasattr(rt, "get_param"):
                        val = float(rt.get_param(key, df))
                    else:
                        continue
                    val = max(mn, min(mx, val))
                    if isinstance(ctrl, QCheckBox):
                        with QSignalBlocker(ctrl):
                            ctrl.setChecked(val >= 0.5)
                    elif isinstance(ctrl, QSlider):
                        sld_val = int((val - mn) / max(1e-9, mx - mn) * 1000.0)
                        with QSignalBlocker(ctrl):
                            ctrl.setValue(max(0, min(1000, sld_val)))
                        if spn is not None:
                            with QSignalBlocker(spn):
                                spn.setValue(val)
                except Exception:
                    continue
        except Exception:
            pass

    def _on_automation_param_changed(self, parameter_id: str, value: float) -> None:
        """Update slider/spinbox when automation plays back a value (v0.0.20.526)."""
        try:
            pid = str(parameter_id or "")
            if not pid.startswith(self._prefix):
                return
            param_name = pid[len(self._prefix):]
            row_data = self._rows.get(param_name)
            if row_data is None:
                return
            _, ctrl, spn, (mn, mx, df) = row_data
            val = float(value)
            from PyQt6.QtCore import QSignalBlocker
            if ctrl is not None and hasattr(ctrl, 'setValue') and hasattr(ctrl, 'maximum'):
                if mx > mn:
                    sld_val = int((val - mn) / (mx - mn) * 1000.0)
                    sld_val = max(0, min(1000, sld_val))
                else:
                    sld_val = 0
                with QSignalBlocker(ctrl):
                    ctrl.setValue(sld_val)
            elif ctrl is not None and hasattr(ctrl, 'setChecked'):
                with QSignalBlocker(ctrl):
                    ctrl.setChecked(val >= 0.5)
            if spn is not None:
                with QSignalBlocker(spn):
                    spn.setValue(float(val))
            rt_store = getattr(getattr(self._services, "audio_engine", None), "rt_params", None) if self._services else None
            if rt_store is not None:
                key = self._prefix + param_name
                try:
                    if hasattr(rt_store, "set_smooth"):
                        rt_store.set_smooth(key, float(val))
                    elif hasattr(rt_store, "set_param"):
                        rt_store.set_param(key, float(val))
                except Exception:
                    pass
        except Exception:
            pass

    def _load_params(self) -> None:
        infos = self._get_runtime_param_infos()
        if infos:
            self._param_infos = list(infos)
            self._on_params_loaded(self._param_infos, source="runtime")
        else:
            self._runtime_probe_attempts = 0
            self._status.setText("Warte auf laufende CLAP-Instanz…")
            self._runtime_probe_timer.start(180)

        # Check for native GUI support via live audio engine FX instance
        QTimer.singleShot(200, self._check_gui_support)

    def _retry_runtime_param_load(self) -> None:
        infos = self._get_runtime_param_infos()
        if infos:
            self._param_infos = list(infos)
            self._on_params_loaded(self._param_infos, source="runtime")
            return
        self._runtime_probe_attempts += 1
        if self._runtime_probe_attempts < 8:
            self._status.setText("Warte auf laufende CLAP-Instanz…")
            self._runtime_probe_timer.start(220)
            return
        self._fallback_describe_controls()

    def _fallback_describe_controls(self) -> None:
        try:
            from pydaw.audio.clap_host import describe_controls, split_plugin_reference
            clap_path, clap_pid = split_plugin_reference(self._clap_ref)
            if not clap_pid:
                clap_pid = self._clap_plugin_id
            if not clap_path:
                self._status.setText("Kein CLAP-Pfad gefunden")
                return
            infos = list(describe_controls(clap_path, clap_pid) or [])
            self._param_infos = infos
            self._on_params_loaded(infos, source="describe")
        except Exception as e:
            self._status.setText(f"CLAP Fehler: {e}")

    def _get_runtime_param_infos(self) -> list:
        """Reuse metadata from the already-loaded live CLAP engine when possible.

        v0.0.20.558: Also checks layer engine keys (device_id = "tid:ilayer:N").
        """
        try:
            ae = getattr(self._services, "audio_engine", None)
            if ae is None:
                return []

            fx_map = getattr(ae, "_track_audio_fx_map", None)
            if isinstance(fx_map, dict):
                chain_fx = fx_map.get(self._track_id)
                if chain_fx is not None:
                    for dev in getattr(chain_fx, "devices", []):
                        try:
                            if str(getattr(dev, "device_id", "") or "") == self._device_id:
                                getter = getattr(dev, "get_param_infos", None)
                                infos = getter() if callable(getter) else []
                                if infos:
                                    return list(infos)
                        except Exception:
                            continue

            inst_map = getattr(ae, "_vst_instrument_engines", None)
            if isinstance(inst_map, dict):
                # Check by track_id (normal instruments)
                engine = inst_map.get(self._track_id)
                if engine is not None and not getattr(engine, "_is_layer_dispatcher", False):
                    getter = getattr(engine, "get_param_infos", None)
                    infos = getter() if callable(getter) else []
                    if infos:
                        return list(infos)
                # v0.0.20.558: Check by device_id (layer engines: "tid:ilayer:N")
                engine = inst_map.get(self._device_id)
                if engine is not None:
                    getter = getattr(engine, "get_param_infos", None)
                    infos = getter() if callable(getter) else []
                    if infos:
                        return list(infos)
        except Exception:
            pass
        return []

    def _param_key(self, param_name: str) -> str:
        return self._prefix + str(param_name or "")

    def _on_params_loaded(self, infos: list, *, source: str = "") -> None:
        try:
            self._runtime_probe_timer.stop()
        except Exception:
            pass
        self._param_infos = list(infos or [])
        self._param_source = str(source or getattr(self, "_param_source", ""))
        self._next_param_index = 0
        if not self._param_infos:
            src = f" via {source}" if source else ""
            self._status.setText(f"CLAP geladen (0 Parameter{src})")
            self._btn_more.setVisible(False)
            return
        self._build_initial_rows()
        self._update_param_status(source=self._param_source)

    def _log_clap_find_once(self, key: str, message: str) -> None:
        try:
            if self._last_find_log_key == key:
                return
            self._last_find_log_key = key
            print(message, file=__import__("sys").stderr, flush=True)
        except Exception:
            pass

    def _invalidate_live_clap_plugin_cache(self) -> None:
        self._live_plugin_cache = None
        self._live_plugin_cache_source = ""

    def _find_live_clap_plugin(self, *, use_cache: bool = True, quiet: bool = False):
        """Find the live _ClapPlugin instance from FX chain OR instrument engines.

        v0.0.20.467: Cache successful lookups per widget and throttle diagnostics.
        That avoids repeated map walks and log spam during editor pumping and
        parameter polling, while keeping a forced-refresh path for rebuild cases.
        """
        try:
            if use_cache and self._live_plugin_cache is not None:
                return self._live_plugin_cache

            ae = getattr(self._services, "audio_engine", None)
            if ae is None:
                self._invalidate_live_clap_plugin_cache()
                if not quiet:
                    self._log_clap_find_once(
                        "no-audio-engine",
                        "[CLAP-FIND] No audio_engine in services",
                    )
                return None

            # 1) Search FX chain devices
            fx_map = getattr(ae, "_track_audio_fx_map", None)
            if fx_map:
                chain_fx = fx_map.get(self._track_id)
                if chain_fx is not None:
                    for dev in getattr(chain_fx, "devices", []):
                        if str(getattr(dev, "device_id", "")) == self._device_id and hasattr(dev, "get_plugin"):
                            plugin = dev.get_plugin()
                            if plugin is not None:
                                self._live_plugin_cache = plugin
                                self._live_plugin_cache_source = "fx"
                                if not quiet:
                                    self._log_clap_find_once(
                                        f"fx:{self._device_id}",
                                        f"[CLAP-FIND] Found FX plugin for {self._device_id}",
                                    )
                                return plugin

            # 2) Search instrument engines (CLAP instruments are keyed by track_id)
            inst_map = getattr(ae, "_vst_instrument_engines", None)
            if inst_map:
                # Normal instrument (by track_id)
                engine = inst_map.get(self._track_id)
                if engine is not None and not getattr(engine, "_is_layer_dispatcher", False):
                    if hasattr(engine, "get_plugin"):
                        plugin = engine.get_plugin()
                        if plugin is not None:
                            self._live_plugin_cache = plugin
                            self._live_plugin_cache_source = "instrument"
                            if not quiet:
                                self._log_clap_find_once(
                                    f"instrument:{self._track_id}",
                                    f"[CLAP-FIND] Found INSTRUMENT plugin for track={self._track_id}",
                                )
                            return plugin
                # v0.0.20.558: Layer engine (by device_id = "tid:ilayer:N")
                engine = inst_map.get(self._device_id)
                if engine is not None and hasattr(engine, "get_plugin"):
                    plugin = engine.get_plugin()
                    if plugin is not None:
                        self._live_plugin_cache = plugin
                        self._live_plugin_cache_source = "layer"
                        if not quiet:
                            self._log_clap_find_once(
                                f"layer:{self._device_id}",
                                f"[CLAP-FIND] Found LAYER plugin for device={self._device_id}",
                            )
                        return plugin

            self._invalidate_live_clap_plugin_cache()
            if not quiet:
                self._log_clap_find_once(
                    f"miss:{self._track_id}:{self._device_id}",
                    f"[CLAP-FIND] No live CLAP plugin found (track={self._track_id}, device={self._device_id})",
                )
            return None
        except Exception as exc:
            self._invalidate_live_clap_plugin_cache()
            if not quiet:
                self._log_clap_find_once(
                    f"error:{type(exc).__name__}:{exc}",
                    f"[CLAP-FIND] Exception: {exc}",
                )
            return None

    def _build_initial_rows(self) -> None:
        self._register_rt_params_only()
        initial = self._param_infos[:self._initial_param_batch]
        self._next_param_index = len(initial)
        self._build_rows(initial)
        self._btn_more.setVisible(self._next_param_index < len(self._param_infos))

    def _register_rt_params_only(self) -> None:
        rt = self._get_rt_params()
        if rt is None:
            return
        for info in self._param_infos:
            try:
                mn = float(getattr(info, "min_value", 0.0))
                mx = float(getattr(info, "max_value", 1.0))
                df = float(getattr(info, "default_value", mn))
                rng = max(mx - mn, 1e-9)
                norm = (df - mn) / rng
                if hasattr(rt, "ensure"):
                    rt.ensure(self._prefix + str(getattr(info, "name", "") or ""), norm)
            except Exception:
                continue

    def _load_more_rows(self) -> None:
        if self._next_param_index >= len(self._param_infos):
            self._btn_more.setVisible(False)
            return
        end = min(len(self._param_infos), self._next_param_index + self._param_load_more_batch)
        self._build_rows(self._param_infos[self._next_param_index:end])
        self._next_param_index = end
        self._btn_more.setVisible(self._next_param_index < len(self._param_infos))
        self._update_param_status(source=getattr(self, "_param_source", ""))
        self._apply_filter(self._search.text())

    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().lower()
        if query:
            matches = [
                info for info in self._param_infos
                if query in str(getattr(info, "name", "") or "").lower()
            ]
            if matches:
                limit = min(len(matches), 120)
                self._build_rows(matches[:limit])
        for name, (row, *_rest) in self._rows.items():
            try:
                visible = (not query) or (query in str(name).lower())
                row.setVisible(visible)
            except Exception:
                pass

    def _update_param_status(self, *, source: str = "") -> None:
        if not source:
            source = str(getattr(self, "_param_source", "") or "")
        total = len(self._param_infos)
        built = len(self._rows)
        if total <= 0:
            self._status.setText("CLAP geladen (0 Parameter)")
            return
        suffix = f" | Quelle: {source}" if source else ""
        if built < total:
            self._status.setText(f"CLAP: {total} Parameter (zeige {built}){suffix}")
        else:
            self._status.setText(f"CLAP: {total} Parameter{suffix}")

    def _clear_editor_async_sources(self) -> None:
        try:
            notifiers = list(getattr(self, "_editor_fd_notifiers", {}).values())
        except Exception:
            notifiers = []
        for notifier in notifiers:
            try:
                notifier.setEnabled(False)
                notifier.deleteLater()
            except Exception:
                pass
        self._editor_fd_notifiers = {}

        try:
            timers = list(getattr(self, "_editor_gui_timers", {}).values())
        except Exception:
            timers = []
        for timer in timers:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        self._editor_gui_timers = {}

    def _sync_editor_async_sources(self, plugin) -> None:
        if plugin is None:
            self._clear_editor_async_sources()
            return

        try:
            fd_map = plugin.get_registered_gui_fds()
        except Exception:
            fd_map = {}
        try:
            timer_map = plugin.get_registered_gui_timers()
        except Exception:
            timer_map = {}

        desired_fd_keys = set()
        flag_specs = []
        try:
            flag_specs.append((1, QSocketNotifier.Type.Read))
        except Exception:
            pass
        try:
            flag_specs.append((2, QSocketNotifier.Type.Write))
        except Exception:
            pass
        try:
            flag_specs.append((4, QSocketNotifier.Type.Exception))
        except Exception:
            pass

        for fd, flags in list(fd_map.items()):
            try:
                fd_i = int(fd)
                flags_i = int(flags)
            except Exception:
                continue
            for bit, qt_type in flag_specs:
                key = (fd_i, bit)
                if flags_i & bit:
                    desired_fd_keys.add(key)
                    if key not in self._editor_fd_notifiers:
                        try:
                            notifier = QSocketNotifier(fd_i, qt_type, self)
                            notifier.activated.connect(lambda _ignored=None, fd=fd_i, bit=bit: self._on_editor_fd_event(fd, bit))
                            self._editor_fd_notifiers[key] = notifier
                        except Exception:
                            continue

        for key, notifier in list(self._editor_fd_notifiers.items()):
            if key not in desired_fd_keys:
                try:
                    notifier.setEnabled(False)
                    notifier.deleteLater()
                except Exception:
                    pass
                self._editor_fd_notifiers.pop(key, None)

        desired_timer_ids = {int(k): int(v) for k, v in list(timer_map.items())}
        for timer_id, period_ms in desired_timer_ids.items():
            timer = self._editor_gui_timers.get(timer_id)
            if timer is None:
                try:
                    timer = QTimer(self)
                    timer.setTimerType(Qt.TimerType.PreciseTimer)
                    timer.timeout.connect(lambda tid=timer_id: self._on_editor_gui_timer(tid))
                    self._editor_gui_timers[timer_id] = timer
                except Exception:
                    continue
            try:
                period = max(1, int(period_ms))
                if timer.interval() != period:
                    timer.setInterval(period)
                if not timer.isActive():
                    timer.start()
            except Exception:
                pass

        for timer_id, timer in list(self._editor_gui_timers.items()):
            if timer_id not in desired_timer_ids:
                try:
                    timer.stop()
                    timer.deleteLater()
                except Exception:
                    pass
                self._editor_gui_timers.pop(timer_id, None)

    def _on_editor_fd_event(self, fd: int, flags: int) -> None:
        plugin = self._find_live_clap_plugin(quiet=True)
        if plugin is None:
            plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
        if plugin is None:
            return
        try:
            plugin.dispatch_gui_fd(int(fd), int(flags))
        except Exception:
            pass
        try:
            plugin.pump_main_thread(force=True, max_calls=6)
        except Exception:
            pass
        try:
            self._sync_editor_async_sources(plugin)
        except Exception:
            pass

    def _on_editor_gui_timer(self, timer_id: int) -> None:
        plugin = self._find_live_clap_plugin(quiet=True)
        if plugin is None:
            plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
        if plugin is None:
            return
        try:
            plugin.dispatch_gui_timer(int(timer_id))
        except Exception:
            pass
        try:
            plugin.pump_main_thread(force=True, max_calls=6)
        except Exception:
            pass
        try:
            self._sync_editor_async_sources(plugin)
        except Exception:
            pass

    def _pump_editor_gui(self) -> None:
        if self._editor_window is None:
            self._editor_pump.stop()
            self._editor_prime_frames = 0
            return
        plugin = self._find_live_clap_plugin(quiet=True)
        if plugin is None:
            plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
        if plugin is None:
            self._clear_editor_async_sources()
            self._editor_pump.stop()
            self._editor_prime_frames = 0
            return
        try:
            self._sync_editor_async_sources(plugin)
        except Exception:
            pass
        force = self._editor_prime_frames > 0
        try:
            # Keep a lightweight background pump alive while the editor window is
            # open.  Prime phase stays fast for bootstrap; afterwards the timer
            # drops to a very slow cadence so late request_callback() bursts from
            # the plugin still get serviced without affecting general UI/audio
            # performance when the editor is merely sitting open.
            target_interval = 16 if force else 120
            if self._editor_pump.interval() != target_interval:
                self._editor_pump.setInterval(target_interval)
            plugin.pump_main_thread(force=force, max_calls=4 if force else 2)
        except Exception:
            pass
        try:
            requested = plugin.take_requested_gui_size()
            if requested and self._editor_gui_container is not None and self._editor_window is not None:
                w, h = requested
                if w > 32 and h > 32:
                    self._editor_gui_container.setFixedSize(w, h)
                    self._editor_window.setFixedSize(w, h + 28)
                    try:
                        plugin.set_gui_size(w, h)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            visible_req = plugin.take_requested_gui_visibility()
            if visible_req is not None and self._editor_window is not None:
                if bool(visible_req):
                    if not self._editor_window.isVisible():
                        self._editor_window.show()
                    self._editor_window.raise_()
                    self._editor_window.activateWindow()
                elif self._editor_window.isVisible():
                    self._editor_window.hide()
        except Exception:
            pass
        if self._editor_prime_frames > 0:
            self._editor_prime_frames -= 1

    def _check_gui_support(self) -> None:
        """Check if the live CLAP plugin supports a native GUI.

        v0.0.20.463: Added debug output + retry logic.
        Audio engine may still be loading when this fires.
        """
        import sys
        self._gui_check_count = getattr(self, "_gui_check_count", 0) + 1
        try:
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is not None:
                has = plugin.has_gui()
                print(f"[CLAP-GUI] Plugin found, has_gui={has} (attempt {self._gui_check_count})",
                      file=sys.stderr, flush=True)
                if has:
                    self._has_gui = True
                    self._btn_editor.setVisible(True)
                    self._status.setText(
                        self._status.text() + " | 🎛 Editor verfügbar"
                    )
                    return
            else:
                print(f"[CLAP-GUI] No plugin yet (attempt {self._gui_check_count})",
                      file=sys.stderr, flush=True)

            # Retry up to 5 times with increasing delay
            if self._gui_check_count < 5:
                QTimer.singleShot(500 * self._gui_check_count, self._check_gui_support)
        except Exception as exc:
            print(f"[CLAP-GUI] check error: {exc}", file=sys.stderr, flush=True)

    # ── v0.0.20.652: Unified Preset Browser callbacks ──

    def _get_state_b64_for_preset(self) -> str:
        """Get current CLAP plugin state as Base64 for preset browser."""
        try:
            import base64
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is None:
                return ""
            if not plugin.has_state():
                return ""
            data = plugin.get_state()
            if data:
                return base64.b64encode(data).decode("ascii")
        except Exception:
            pass
        return ""

    def _set_state_b64_from_preset(self, state_b64: str) -> bool:
        """Apply a Base64 state blob to the running CLAP plugin."""
        if not state_b64:
            return False
        try:
            import base64
            data = base64.b64decode(state_b64)
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is None:
                return False
            if not plugin.has_state():
                return False
            ok = plugin.set_state(data)
            if ok:
                QTimer.singleShot(100, self._sync_sliders_from_plugin)
            return ok
        except Exception:
            return False

    def _get_current_param_values_for_preset(self) -> dict:
        """Get current parameter values from CLAP UI sliders."""
        result = {}
        try:
            for name, row_data in self._rows.items():
                _row, ctrl, spn, (mn, mx, df) = row_data
                if isinstance(ctrl, QCheckBox):
                    result[name] = mx if ctrl.isChecked() else mn
                elif spn is not None:
                    result[name] = spn.value()
        except Exception:
            pass
        return result

    # ── v0.0.20.569: CLAP Preset Browser ──

    def _preset_dir(self) -> str:
        """Return the preset directory for this plugin."""
        from pathlib import Path
        safe_id = self._clap_plugin_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        if not safe_id:
            safe_id = os.path.basename(self._clap_ref).replace(".clap", "")
        d = Path.home() / ".config" / "ChronoScaleStudio" / "clap_presets" / safe_id
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _refresh_presets(self) -> None:
        """Scan preset directory and update combo box."""
        try:
            combo = self._preset_combo
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(kein Preset)")

            preset_dir = self._preset_dir()
            presets = sorted(
                f for f in os.listdir(preset_dir)
                if f.endswith(".clap_preset")
            )
            for p in presets:
                name = p.replace(".clap_preset", "")
                combo.addItem(name)

            # Restore selection
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        except Exception:
            try:
                self._preset_combo.blockSignals(False)
            except Exception:
                pass

    def _on_preset_selected(self, index: int) -> None:
        """Load the selected preset into the running plugin."""
        if index <= 0:
            return
        try:
            name = self._preset_combo.currentText()
            if not name or name == "(kein Preset)":
                return
            preset_path = os.path.join(self._preset_dir(), f"{name}.clap_preset")
            if not os.path.isfile(preset_path):
                return
            data = open(preset_path, "rb").read()
            if not data:
                return

            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is None:
                self._status.setText("Preset: Kein live CLAP-Plugin gefunden")
                return
            if not plugin.has_state():
                self._status.setText("Preset: Plugin unterstützt kein clap.state")
                return

            ok = plugin.set_state(data)
            if ok:
                self._status.setText(f"Preset '{name}' geladen ✓")
                # Refresh UI sliders from new state
                QTimer.singleShot(100, self._sync_sliders_from_plugin)
            else:
                self._status.setText(f"Preset '{name}' laden fehlgeschlagen")
        except Exception as e:
            self._status.setText(f"Preset-Fehler: {e}")

    def _save_preset(self) -> None:
        """Save current plugin state as a named preset."""
        try:
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is None:
                self._status.setText("Preset speichern: Kein live Plugin")
                return
            if not plugin.has_state():
                self._status.setText("Plugin unterstützt kein clap.state — Presets nicht möglich")
                return

            data = plugin.get_state()
            if not data:
                self._status.setText("Preset: get_state lieferte keine Daten")
                return

            from PyQt6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(
                self, "CLAP Preset speichern",
                "Preset-Name:",
                text=f"Preset {len(os.listdir(self._preset_dir())) + 1}"
            )
            if not ok or not name.strip():
                return
            name = name.strip()
            # Sanitize filename
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
            if not safe_name:
                safe_name = "preset"

            preset_path = os.path.join(self._preset_dir(), f"{safe_name}.clap_preset")
            with open(preset_path, "wb") as f:
                f.write(data)

            self._status.setText(f"Preset '{safe_name}' gespeichert ✓ ({len(data)} bytes)")
            self._refresh_presets()
            # Select the new preset
            idx = self._preset_combo.findText(safe_name)
            if idx >= 0:
                self._preset_combo.blockSignals(True)
                self._preset_combo.setCurrentIndex(idx)
                self._preset_combo.blockSignals(False)
        except Exception as e:
            self._status.setText(f"Preset speichern fehlgeschlagen: {e}")

    def _delete_preset(self) -> None:
        """Delete the currently selected preset file."""
        try:
            name = self._preset_combo.currentText()
            if not name or name == "(kein Preset)":
                return
            preset_path = os.path.join(self._preset_dir(), f"{name}.clap_preset")
            if os.path.isfile(preset_path):
                os.remove(preset_path)
                self._status.setText(f"Preset '{name}' gelöscht")
                self._refresh_presets()
        except Exception as e:
            self._status.setText(f"Löschen fehlgeschlagen: {e}")

    def _sync_sliders_from_plugin(self) -> None:
        """After loading a preset, refresh all UI sliders from the plugin's current param values."""
        try:
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                return
            for name, row_data in self._rows.items():
                row_widget, ctrl, spn, (mn, mx, df) = row_data
                try:
                    # Read current value from plugin
                    val = plugin.get_param_value(name) if hasattr(plugin, "get_param_value") else None
                    if val is None:
                        continue
                    val = max(mn, min(mx, float(val)))
                    if isinstance(ctrl, QCheckBox):
                        with QSignalBlocker(ctrl):
                            ctrl.setChecked(val >= 0.5)
                    elif isinstance(ctrl, QSlider):
                        sld_val = int((val - mn) / max(1e-9, mx - mn) * 1000.0)
                        with QSignalBlocker(ctrl):
                            ctrl.setValue(sld_val)
                        if spn is not None:
                            with QSignalBlocker(spn):
                                spn.setValue(val)
                except Exception:
                    continue
        except Exception:
            pass

    def _toggle_editor(self) -> None:
        """Toggle the native CLAP GUI editor window."""
        import sys
        print(f"[CLAP-EDITOR] _toggle_editor called (has_gui={self._has_gui}, "
              f"track={self._track_id}, device={self._device_id})",
              file=sys.stderr, flush=True)
        if self._editor_window is not None or self._editor_open_pending:
            self._close_editor()
            return

        plugin = self._find_live_clap_plugin(quiet=True)
        if plugin is None:
            plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
        if plugin is None:
            self._status.setText("Editor: Kein live CLAP-Plugin gefunden")
            print("[CLAP-EDITOR] No live plugin found!", file=sys.stderr, flush=True)
            return
        if not plugin.has_gui():
            self._status.setText("Editor: Plugin hat keine GUI")
            print("[CLAP-EDITOR] Plugin has no GUI support!", file=sys.stderr, flush=True)
            return

        try:
            title = self._clap_plugin_id or os.path.basename(self._clap_ref)

            # Create editor window with custom title bar (Pin + Roll + Close)
            self._editor_window = QWidget(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            self._editor_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            self._editor_window.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self._editor_pinned = False
            self._editor_rolled = False
            self._editor_drag_pos = None

            outer = QVBoxLayout(self._editor_window)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            # Custom title bar (like VST2 Editor)
            title_bar = QWidget()
            title_bar.setFixedHeight(28)
            title_bar.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                "stop:0 #3a3a4a, stop:1 #2a2a3a); "
                "border-bottom: 1px solid #555;"
            )
            tb_layout = QHBoxLayout(title_bar)
            tb_layout.setContentsMargins(6, 0, 4, 0)
            tb_layout.setSpacing(4)

            lbl_icon = QLabel("🔌")
            lbl_icon.setStyleSheet("color:#4fc3f7; font-size:12px;")
            tb_layout.addWidget(lbl_icon)

            lbl_title = QLabel(f"CLAP Editor — {title}")
            lbl_title.setStyleSheet("color:#ddd; font-size:11px; font-weight:bold;")
            tb_layout.addWidget(lbl_title, 1)

            btn_pin = QPushButton("📌")
            btn_pin.setFixedSize(24, 22)
            btn_pin.setToolTip("Immer im Vordergrund (Pin)")
            btn_pin.setStyleSheet("background:transparent; border:none; font-size:13px;")
            btn_pin.clicked.connect(lambda: self._toggle_editor_pin(btn_pin))
            tb_layout.addWidget(btn_pin)

            btn_roll = QPushButton("🔺")
            btn_roll.setFixedSize(24, 22)
            btn_roll.setToolTip("Editor ein-/ausrollen")
            btn_roll.setStyleSheet("background:transparent; border:none; font-size:13px;")
            btn_roll.clicked.connect(lambda: self._toggle_editor_roll(btn_roll))
            tb_layout.addWidget(btn_roll)

            btn_close = QPushButton("✕")
            btn_close.setFixedSize(24, 22)
            btn_close.setToolTip("Editor schließen")
            btn_close.setStyleSheet(
                "background:#c62828; color:white; border:none; border-radius:3px; "
                "font-size:12px; font-weight:bold;"
            )
            btn_close.clicked.connect(self._close_editor)
            tb_layout.addWidget(btn_close)

            outer.addWidget(title_bar)

            def _title_press(event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._editor_drag_pos = event.globalPosition().toPoint() - self._editor_window.frameGeometry().topLeft()
            def _title_move(event):
                if self._editor_drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
                    self._editor_window.move(event.globalPosition().toPoint() - self._editor_drag_pos)
            def _title_release(event):
                self._editor_drag_pos = None
            title_bar.mousePressEvent = _title_press
            title_bar.mouseMoveEvent = _title_move
            title_bar.mouseReleaseEvent = _title_release

            self._editor_gui_container = QWidget()
            self._editor_gui_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self._editor_gui_container.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
            self._editor_gui_container.setMinimumSize(200, 100)
            outer.addWidget(self._editor_gui_container, 1)

            # First show the host window, then defer CLAP create_gui() until Qt/X11 has
            # processed the native mapping. This mirrors the safe VST2 flow and avoids
            # calling set_parent() on an unmapped/unstable X11 child handle.
            self._editor_window.show()
            try:
                self._editor_window.raise_()
                self._editor_window.activateWindow()
            except Exception:
                pass
            self._btn_editor.setText("… Editor")
            self._btn_editor.setStyleSheet("background:#455a64; color:white;")
            self._editor_open_pending = True
            self._editor_deferred_timer.start(0)
        except Exception as e:
            import traceback
            self._status.setText(f"Editor Fehler: {e}")
            print(f"[CLAP-EDITOR] Exception in _toggle_editor: {e}",
                  file=__import__("sys").stderr, flush=True)
            traceback.print_exc(file=__import__("sys").stderr)
            if self._editor_window:
                try:
                    self._editor_window.close()
                except Exception:
                    pass
                self._editor_window = None
                self._editor_gui_container = None
            self._editor_open_pending = False

    def _open_editor_deferred(self) -> None:
        import sys
        from PyQt6.QtWidgets import QApplication

        if self._editor_window is None or self._editor_gui_container is None:
            self._editor_open_pending = False
            return

        plugin = self._find_live_clap_plugin(quiet=True)
        if plugin is None:
            plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
        if plugin is None:
            self._editor_open_pending = False
            self._status.setText("Editor: Kein live CLAP-Plugin gefunden")
            self._close_editor()
            return

        try:
            QApplication.processEvents()
            self._editor_gui_container.show()
            QApplication.processEvents()
            container_id = int(self._editor_gui_container.winId())
            print(f"[CLAP-EDITOR] Deferred container X11 winId = 0x{container_id:x}",
                  file=sys.stderr, flush=True)
            if container_id == 0:
                raise RuntimeError("CLAP container winId = 0")

            ok, w, h = plugin.create_gui(container_id)
            print(f"[CLAP-EDITOR] create_gui result: ok={ok}, w={w}, h={h}",
                  file=sys.stderr, flush=True)
            if not ok:
                # v0.0.20.570: If create failed (maybe GUI still alive from previous),
                # destroy and retry once
                try:
                    plugin.destroy_gui()
                except Exception:
                    pass
                ok, w, h = plugin.create_gui(container_id)
                print(f"[CLAP-EDITOR] create_gui retry: ok={ok}, w={w}, h={h}",
                      file=sys.stderr, flush=True)
                if not ok:
                    raise RuntimeError("create_gui fehlgeschlagen (auch nach destroy+retry)")

            if w > 0 and h > 0:
                self._editor_gui_container.setFixedSize(w, h)
                self._editor_window.setFixedSize(w, h + 28)
                try:
                    plugin.set_gui_size(w, h)
                except Exception:
                    pass
            self._editor_gui_container.updateGeometry()
            self._editor_gui_container.update()
            QApplication.processEvents()

            self._editor_prime_frames = 120
            self._editor_pump.setInterval(16)
            self._editor_pump.start()
            try:
                plugin.pump_main_thread(force=True, max_calls=8)
            except Exception:
                pass
            try:
                self._sync_editor_async_sources(plugin)
            except Exception:
                pass
            try:
                self._editor_window.raise_()
                self._editor_window.activateWindow()
            except Exception:
                pass
            self._btn_editor.setText("✕ Editor")
            self._btn_editor.setStyleSheet("background:#2e7d32; color:white;")
            self._editor_open_pending = False
            title = self._clap_plugin_id or os.path.basename(self._clap_ref)
            print(f"[CLAP] Editor opened: {title} ({w}x{h})",
                  file=sys.stderr, flush=True)
        except Exception as e:
            import traceback
            self._editor_open_pending = False
            self._status.setText(f"Editor Fehler: {e}")
            print(f"[CLAP-EDITOR] Deferred open failed: {e}",
                  file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            self._close_editor()

    def _toggle_editor_pin(self, btn) -> None:
        """Toggle always-on-top for editor window via x11_set_above().

        v0.0.20.463: CRITICAL FIX — replaced setWindowFlags() with
        x11_set_above() (ctypes/libX11).  setWindowFlags() causes X11
        re-parenting which *destroys* the embedded CLAP plugin GUI.
        Same pattern as _Vst2EditorDialog._toggle_pin (v0.0.20.402).
        """
        if self._editor_window is None:
            return
        self._editor_pinned = not self._editor_pinned
        try:
            wid = int(self._editor_window.winId())
            from pydaw.ui.x11_window_ctl import x11_set_above
            x11_set_above(wid, self._editor_pinned)
        except Exception as exc:
            print(f"[CLAP-EDITOR] Pin via x11_set_above fehlgeschlagen: {exc}",
                  file=__import__("sys").stderr, flush=True)
        if self._editor_pinned:
            btn.setStyleSheet(
                "background:#ff8f00; border:none; font-size:13px; border-radius:3px;"
            )
            btn.setToolTip("Pin AKTIV: Fenster bleibt im Vordergrund\nKlicken zum Deaktivieren")
        else:
            btn.setStyleSheet("background:transparent; border:none; font-size:13px;")
            btn.setToolTip("Immer im Vordergrund (Pin)")

    def _toggle_editor_roll(self, btn) -> None:
        """Roll/unroll editor window (hide/show plugin GUI, keep title bar).

        v0.0.20.463: Save original window geometry before rolling up
        and restore it precisely on unroll.  Avoids losing the plugin
        GUI size when sizeHint()/minimumHeight() return stale values.
        """
        if self._editor_window is None or self._editor_gui_container is None:
            return
        self._editor_rolled = not self._editor_rolled
        if self._editor_rolled:
            # Save original size before hiding
            self._saved_gui_width = self._editor_window.width()
            self._saved_gui_height = self._editor_window.height()
            self._editor_gui_container.hide()
            # Allow resize then set collapsed height
            self._editor_window.setMinimumSize(self._saved_gui_width, 28)
            self._editor_window.setMaximumSize(self._saved_gui_width, 28)
            self._editor_window.resize(self._saved_gui_width, 28)
            btn.setText("🔻")
            btn.setToolTip("Editor ausrollen (GUI eingeblendet)")
        else:
            self._editor_gui_container.show()
            w = getattr(self, "_saved_gui_width", 400)
            h = getattr(self, "_saved_gui_height", 300)
            if h < 56:
                h = self._editor_gui_container.minimumHeight() + 28
            self._editor_window.setMinimumSize(w, h)
            self._editor_window.setMaximumSize(w, h)
            self._editor_window.resize(w, h)
            btn.setText("🔺")
            btn.setToolTip("Editor einrollen (nur Titelleiste)")

    def _close_editor(self, _=False) -> None:
        """Close the native CLAP GUI editor.
        
        v0.0.20.570: Accepts optional bool arg from QPushButton.clicked signal.
        """
        self._editor_deferred_timer.stop()
        self._editor_open_pending = False
        self._editor_pump.stop()
        self._editor_prime_frames = 0
        self._clear_editor_async_sources()
        try:
            plugin = self._find_live_clap_plugin(quiet=True)
            if plugin is None:
                plugin = self._find_live_clap_plugin(use_cache=False, quiet=True)
            if plugin is not None:
                plugin.destroy_gui()
        except Exception:
            pass
        self._invalidate_live_clap_plugin_cache()
        if self._editor_window is not None:
            try:
                self._editor_window.close()
            except Exception:
                pass
            self._editor_window = None
        self._editor_gui_container = None
        self._btn_editor.setText("🎛 Editor")
        self._btn_editor.setStyleSheet("")

    def _build_rows(self, infos: list) -> None:
        """Build slider/spinbox rows for each CLAP parameter."""
        for info in infos:
            try:
                name = str(getattr(info, "name", "") or "")
                if not name or name in self._rows:
                    continue
                mn = float(getattr(info, "min_value", 0.0))
                mx = float(getattr(info, "max_value", 1.0))
                df = float(getattr(info, "default_value", mn))
                rng = max(mx - mn, 1e-9)
                is_stepped = bool(getattr(info, "is_stepped", False))

                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(4)

                lbl = QLabel(name)
                lbl.setFixedWidth(140)
                lbl.setStyleSheet("color:#ccc; font-size:10px;")
                lbl.setToolTip(f"{name}\nRange: {mn:.2f} – {mx:.2f}\nDefault: {df:.2f}")
                rl.addWidget(lbl)

                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setMinimum(0)
                slider.setMaximum(1000)
                norm = (df - mn) / rng
                slider.setValue(int(norm * 1000))
                rl.addWidget(slider, 1)

                spin = QDoubleSpinBox()
                spin.setDecimals(3 if not is_stepped else 0)
                spin.setRange(mn, mx)
                spin.setValue(df)
                spin.setFixedWidth(70)
                rl.addWidget(spin)

                try:
                    self._params_layout.insertWidget(max(0, self._params_layout.count() - 1), row)
                except Exception:
                    self._params_layout.addWidget(row)
                self._rows[name] = (row, slider, spin, (mn, mx, df))

                # Connect signals
                slider.valueChanged.connect(
                    lambda v, _n=name, _mn=mn, _rng=rng, _sp=spin: self._on_slider(_n, v, _mn, _rng, _sp)
                )
                spin.valueChanged.connect(
                    lambda v, _n=name, _mn=mn, _rng=rng, _sl=slider: self._on_spin(_n, v, _mn, _rng, _sl)
                )

                # v0.0.20.466: parity with LV2/LADSPA/DSSI/VST — CLAP rows now expose
                # the unified automation + MIDI Learn context menu without eagerly
                # building more widgets than before.  Registration happens only for
                # rows that are actually materialized by the lazy UI.
                try:
                    param_key = self._param_key(name)
                    _install_automation_menu(self, lbl, param_key, lambda df=df: float(df))
                    _install_automation_menu(self, slider, param_key, lambda df=df: float(df))
                    _install_automation_menu(self, spin, param_key, lambda df=df: float(df))
                    self._automation_params[name] = _register_automatable_param(
                        self._services,
                        self._track_id,
                        param_key,
                        str(name),
                        float(mn),
                        float(mx),
                        float(df),
                    )
                except Exception:
                    pass

                # Init RT store
                try:
                    rt = self._get_rt_params()
                    if rt and hasattr(rt, "ensure"):
                        rt.ensure(self._prefix + name, norm)
                except Exception:
                    pass

            except Exception:
                continue

        # Restore from project state
        self._restore_from_project()
        self._update_param_status()

    def _on_slider(self, name: str, value: int, mn: float, rng: float, spin: QDoubleSpinBox) -> None:
        try:
            norm = value / 1000.0
            real = mn + norm * rng
            spin.blockSignals(True)
            spin.setValue(real)
            spin.blockSignals(False)
            rt = self._get_rt_params()
            if rt:
                if hasattr(rt, "set_smooth"):
                    rt.set_smooth(self._prefix + name, norm)
                elif hasattr(rt, "set_param"):
                    rt.set_param(self._prefix + name, norm)
            self._debounce.start()
        except Exception:
            pass

    def _on_spin(self, name: str, value: float, mn: float, rng: float, slider: QSlider) -> None:
        try:
            norm = (value - mn) / rng
            norm = max(0.0, min(1.0, norm))
            slider.blockSignals(True)
            slider.setValue(int(norm * 1000))
            slider.blockSignals(False)
            rt = self._get_rt_params()
            if rt:
                if hasattr(rt, "set_smooth"):
                    rt.set_smooth(self._prefix + name, norm)
                elif hasattr(rt, "set_param"):
                    rt.set_param(self._prefix + name, norm)
            self._debounce.start()
        except Exception:
            pass

    def _flush_to_project(self) -> None:
        """Persist current param values to project JSON."""
        try:
            ps = getattr(self._services, "project_service", None)
            if ps is None:
                return
            proj = getattr(ps, "project", None)
            if proj is None:
                return
            for t in getattr(proj, "tracks", []):
                if str(getattr(t, "id", "")) != self._track_id:
                    continue
                chain = getattr(t, "audio_fx_chain", None)
                if not isinstance(chain, dict):
                    continue
                for dev in chain.get("devices", []):
                    if str(dev.get("id", "")) != self._device_id:
                        continue
                    params = dev.setdefault("params", {})
                    for name, (_, slider, spin, (mn, mx, df)) in self._rows.items():
                        try:
                            params[name] = float(spin.value())
                        except Exception:
                            pass
                    # v0.0.20.653: Notify preset browser of param change for undo
                    try:
                        pb = getattr(self, "_preset_browser", None)
                        if pb is not None:
                            pb.notify_param_changed()
                    except Exception:
                        pass
                    try:
                        ps.mark_dirty()
                    except Exception:
                        pass
                    return
        except Exception:
            pass

    def _restore_from_project(self) -> None:
        """Restore param values from project JSON."""
        try:
            ps = getattr(self._services, "project_service", None)
            if ps is None:
                return
            proj = getattr(ps, "project", None)
            if proj is None:
                return
            for t in getattr(proj, "tracks", []):
                if str(getattr(t, "id", "")) != self._track_id:
                    continue
                chain = getattr(t, "audio_fx_chain", None)
                if not isinstance(chain, dict):
                    continue
                for dev in chain.get("devices", []):
                    if str(dev.get("id", "")) != self._device_id:
                        continue
                    params = dev.get("params", {})
                    if not isinstance(params, dict):
                        continue
                    for name, (_, slider, spin, (mn, mx, df)) in self._rows.items():
                        val = params.get(name)
                        if val is not None:
                            try:
                                v = float(val)
                                rng = max(mx - mn, 1e-9)
                                norm = (v - mn) / rng
                                spin.blockSignals(True)
                                spin.setValue(v)
                                spin.blockSignals(False)
                                slider.blockSignals(True)
                                slider.setValue(int(norm * 1000))
                                slider.blockSignals(False)
                                rt = self._get_rt_params()
                                if rt and hasattr(rt, "set_smooth"):
                                    rt.set_smooth(self._prefix + name, norm)
                            except Exception:
                                pass
                    return
        except Exception:
            pass

    def _get_rt_params(self) -> Any:
        try:
            ae = getattr(self._services, "audio_engine", None)
            if ae is not None:
                return getattr(ae, "rt_params", None)
        except Exception:
            pass
        return None

    def closeEvent(self, event) -> None:
        """Clean up editor window on widget close."""
        try:
            self._runtime_probe_timer.stop()
        except Exception:
            pass
        self._close_editor()
        super().closeEvent(event)


def make_audio_fx_widget(services: Any, track_id: str, device: dict) -> Optional[QWidget]:
    pid_raw = str(device.get("plugin_id") or device.get("type") or "")
    pid = pid_raw.strip()
    pid_norm = pid.lower()
    did = str(device.get("id") or "")
    if not did:
        return None
    if pid == "chrono.fx.gain":
        return GainFxWidget(services, track_id, did)
    if pid == "chrono.fx.distortion":
        return DistortionFxWidget(services, track_id, did)
    # ── v105: Bitwig-Style Audio-FX ──────────────────────────────
    try:
        from pydaw.ui.fx_audio_widgets import (
            EQ5FxWidget, Delay2FxWidget, ReverbFxWidget, CombFxWidget,
            CompressorFxWidget, FilterPlusFxWidget, DistortionPlusFxWidget,
            DynamicsFxWidget, FlangerFxWidget, PitchShifterFxWidget,
            TremoloFxWidget, PeakLimiterFxWidget, ChorusFxWidget,
            XYFxWidget, DeEsserFxWidget,
        )
        _NEW_FX = {
            "chrono.fx.eq5": EQ5FxWidget,
            "chrono.fx.delay2": Delay2FxWidget,
            "chrono.fx.reverb": ReverbFxWidget,
            "chrono.fx.comb": CombFxWidget,
            "chrono.fx.compressor": CompressorFxWidget,
            "chrono.fx.filter_plus": FilterPlusFxWidget,
            "chrono.fx.distortion_plus": DistortionPlusFxWidget,
            "chrono.fx.dynamics": DynamicsFxWidget,
            "chrono.fx.flanger": FlangerFxWidget,
            "chrono.fx.pitch_shifter": PitchShifterFxWidget,
            "chrono.fx.tremolo": TremoloFxWidget,
            "chrono.fx.peak_limiter": PeakLimiterFxWidget,
            "chrono.fx.chorus": ChorusFxWidget,
            "chrono.fx.xy_fx": XYFxWidget,
            "chrono.fx.de_esser": DeEsserFxWidget,
        }
        cls = _NEW_FX.get(pid)
        if cls is not None:
            return cls(services, track_id, did)
    except Exception:
        pass
    if pid_norm.startswith("ext.lv2:"):
        # Normalize whitespace/case but keep exact URI part
        uri = pid.split(":", 1)[1] if ":" in pid else ""
        return Lv2AudioFxWidget(services, track_id, did, f"ext.lv2:{uri}")
    if pid_norm.startswith("ext.ladspa:") or pid_norm.startswith("ext.dssi:"):
        so_path = pid.split(":", 1)[1] if ":" in pid else ""
        return LadspaAudioFxWidget(services, track_id, did, pid, so_path)
    if pid_norm.startswith("ext.vst3:") or pid_norm.startswith("ext.vst2:"):
        params = device.get("params") if isinstance(device, dict) else {}
        if not isinstance(params, dict):
            params = {}
        vst_ref = pid.split(":", 1)[1] if ":" in pid else ""
        vst_ref = str(params.get("__ext_ref") or vst_ref)
        vst_plugin_name = str(params.get("__ext_plugin_name") or "")
        return Vst3AudioFxWidget(services, track_id, did, pid, vst_ref, vst_plugin_name)
    if pid_norm.startswith("ext.clap:"):
        params = device.get("params") if isinstance(device, dict) else {}
        if not isinstance(params, dict):
            params = {}
        clap_ref = pid.split(":", 1)[1] if ":" in pid else ""
        clap_ref = str(params.get("__ext_ref") or clap_ref)
        clap_plugin_id = str(params.get("__ext_plugin_name") or "")
        return ClapAudioFxWidget(services, track_id, did, pid, clap_ref, clap_plugin_id)
    # v0.0.20.530: Device Containers
    if pid == "chrono.container.fx_layer":
        return _FxLayerContainerWidget(services, track_id, did, device)
    if pid == "chrono.container.chain":
        return _ChainContainerWidget(services, track_id, did, device)
    # v0.0.20.536: Instrument Layer Container
    if pid == "chrono.container.instrument_layer":
        return _InstrumentLayerContainerWidget(services, track_id, did, device)
    # unknown FX: show placeholder label
    lab = QLabel(f"{pid}\n(no UI yet)")
    lab.setWordWrap(True)
    return lab


def make_note_fx_widget(services: Any, track_id: str, device: dict) -> Optional[QWidget]:
    pid = str(device.get("plugin_id") or device.get("type") or "")
    did = str(device.get("id") or "")
    if not did:
        return None
    if pid == "chrono.note_fx.transpose":
        return TransposeNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.velocity_scale":
        return VelocityScaleNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.scale_snap":
        return ScaleSnapNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.chord":
        return ChordNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.arp":
        return ArpNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.random":
        return RandomNoteFxWidget(services, track_id, did)
    if pid == "chrono.note_fx.ai_composer":
        return AiComposerNoteFxWidget(services, track_id, did)
    # Others: show placeholder for forward compatibility
    lab = QLabel(f"{pid}\n(MVP UI missing)")
    lab.setWordWrap(True)
    return lab


# ── v0.0.20.530: Device Container Widgets ──────────────────────────────

class _FxLayerContainerWidget(QWidget):
    """UI widget for an FX Layer container — expandable layers with device mini-cards.

    v0.0.20.532: Layer-Expand — click on layer header toggles device list.
    Per-layer: Volume slider, Enable/Disable, Add FX, Remove device.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, device: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = track_id
        self._device_id = device_id
        self._device = device
        self._expanded_layers: set = set()  # indices of expanded layers

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        # Header
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(4)
        header = QLabel("⧉ FX Layer (Parallel)")
        header.setStyleSheet("font-size: 10px; font-weight: bold; color: #4fc3f7;")
        hdr_row.addWidget(header, 1)
        # v0.0.20.541: Preset save/load
        btn_save = QPushButton("💾")
        btn_save.setFixedSize(20, 18)
        btn_save.setStyleSheet("font-size: 9px; border: none;")
        btn_save.setToolTip("Container-Preset speichern")
        btn_save.clicked.connect(lambda _=False: _save_container_preset(self._device, self))
        hdr_row.addWidget(btn_save)
        btn_load = QPushButton("📂")
        btn_load.setFixedSize(20, 18)
        btn_load.setStyleSheet("font-size: 9px; border: none;")
        btn_load.setToolTip("Container-Preset laden")
        btn_load.clicked.connect(lambda _=False: self._load_preset())
        hdr_row.addWidget(btn_load)
        lay.addLayout(hdr_row)

        # Mix slider
        mix_row = QHBoxLayout()
        mix_row.setSpacing(4)
        mix_lbl = QLabel("Mix:")
        mix_lbl.setStyleSheet("font-size: 9px;")
        mix_row.addWidget(mix_lbl)
        self._mix_slider = QSlider(Qt.Orientation.Horizontal)
        self._mix_slider.setRange(0, 100)
        params = device.get("params", {}) if isinstance(device.get("params"), dict) else {}
        self._mix_slider.setValue(int(float(params.get("mix", 1.0)) * 100))
        self._mix_slider.setFixedHeight(16)
        self._mix_slider.setToolTip("Container Mix (0% = Dry, 100% = Wet)")
        self._mix_slider.valueChanged.connect(self._on_mix_changed)
        mix_row.addWidget(self._mix_slider)
        self._mix_label = QLabel(f"{self._mix_slider.value()}%")
        self._mix_label.setStyleSheet("font-size: 9px; min-width: 30px;")
        mix_row.addWidget(self._mix_label)
        lay.addLayout(mix_row)

        # Layer area
        self._layer_area = QVBoxLayout()
        self._layer_area.setSpacing(2)
        lay.addLayout(self._layer_area)
        self._rebuild_layers()

        # Add Layer button
        btn_add = QPushButton("+ Layer")
        btn_add.setFixedHeight(20)
        btn_add.setStyleSheet("font-size: 8px;")
        btn_add.setToolTip("Neuen leeren Layer hinzufügen (max 8)")
        btn_add.clicked.connect(self._add_layer)
        lay.addWidget(btn_add)

    def _rebuild_layers(self) -> None:
        """Rebuild the layer list UI."""
        try:
            # Clear existing
            while self._layer_area.count():
                item = self._layer_area.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
                elif item.layout():
                    _clear_layout(item.layout())

            layers = self._device.get("layers", []) or []
            if not layers:
                hint = QLabel("Keine Layer — klicke '+ Layer'")
                hint.setStyleSheet("font-size: 8px; color: #666; font-style: italic;")
                self._layer_area.addWidget(hint)
                return

            for i, layer in enumerate(layers):
                if not isinstance(layer, dict):
                    continue
                frame = QFrame()
                frame.setFrameShape(QFrame.Shape.StyledPanel)
                frame.setStyleSheet("QFrame { border: 1px solid #3a3a3a; border-radius: 3px; padding: 2px; }")
                frame_lay = QVBoxLayout(frame)
                frame_lay.setContentsMargins(3, 2, 3, 2)
                frame_lay.setSpacing(2)

                name = str(layer.get("name", f"Layer {i+1}"))
                enabled = bool(layer.get("enabled", True))
                devs = layer.get("devices", []) or []
                n_devs = len([d for d in devs if isinstance(d, dict)])
                vol = float(layer.get("volume", 1.0))
                is_expanded = i in self._expanded_layers

                # Layer header row — clickable to expand
                hdr = QHBoxLayout()
                hdr.setSpacing(3)

                expand_icon = "▼" if is_expanded else "▶"
                btn_expand = QPushButton(f"{expand_icon} {name}")
                btn_expand.setFixedHeight(18)
                btn_expand.setStyleSheet(
                    f"font-size: 9px; text-align: left; padding: 0 4px; border: none; "
                    f"color: {'#4fc3f7' if enabled else '#666'}; font-weight: bold;"
                )
                btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_expand.setToolTip(f"Klick: Layer auf-/zuklappen | {n_devs} Devices, Vol {int(vol*100)}%")
                btn_expand.clicked.connect(lambda _=False, _i=i: self._toggle_expand(_i))
                hdr.addWidget(btn_expand, 1)

                # Volume mini-slider
                vol_sld = QSlider(Qt.Orientation.Horizontal)
                vol_sld.setRange(0, 100)
                vol_sld.setValue(int(vol * 100))
                vol_sld.setFixedSize(50, 14)
                vol_sld.setToolTip(f"Layer Volume: {int(vol*100)}%")
                vol_sld.valueChanged.connect(lambda v, _i=i: self._on_layer_vol(v, _i))
                hdr.addWidget(vol_sld)

                # Enable toggle
                btn_en = QPushButton("●" if enabled else "○")
                btn_en.setFixedSize(18, 18)
                btn_en.setStyleSheet(f"font-size: 10px; border: none; color: {'#4fc3f7' if enabled else '#555'};")
                btn_en.setToolTip("Layer Ein/Aus")
                btn_en.clicked.connect(lambda _=False, _i=i: self._toggle_layer_enabled(_i))
                hdr.addWidget(btn_en)

                # Remove layer
                btn_rm = QPushButton("×")
                btn_rm.setFixedSize(18, 18)
                btn_rm.setStyleSheet("font-size: 11px; border: none; color: #c66;")
                btn_rm.setToolTip("Layer entfernen")
                btn_rm.clicked.connect(lambda _=False, _i=i: self._remove_layer(_i))
                hdr.addWidget(btn_rm)

                count_lbl = QLabel(f"{n_devs}")
                count_lbl.setStyleSheet("font-size: 8px; color: #888; min-width: 14px;")
                count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hdr.addWidget(count_lbl)

                frame_lay.addLayout(hdr)

                # Expanded: show devices + add button
                if is_expanded:
                    devs_list = [d for d in devs if isinstance(d, dict)]
                    if devs_list:
                        for j, dev in enumerate(devs_list):
                            d_name = str(dev.get("name") or dev.get("plugin_id") or f"FX {j+1}")
                            d_enabled = bool(dev.get("enabled", True))
                            d_row = QHBoxLayout()
                            d_row.setSpacing(2)
                            d_status = "●" if d_enabled else "○"
                            d_color = "#8be" if d_enabled else "#555"
                            d_lbl = QLabel(f"    {d_status} {d_name}")
                            d_lbl.setStyleSheet(f"font-size: 8px; color: {d_color};")
                            d_row.addWidget(d_lbl, 1)

                            d_btn_en = QPushButton("⏻")
                            d_btn_en.setFixedSize(16, 16)
                            d_btn_en.setStyleSheet(f"font-size: 8px; border: none; color: {d_color};")
                            d_btn_en.setToolTip("Device Ein/Aus")
                            d_btn_en.clicked.connect(lambda _=False, _i=i, _j=j: self._toggle_device_enabled(_i, _j))
                            d_row.addWidget(d_btn_en)

                            # v0.0.20.534: Reorder buttons
                            if j > 0:
                                d_btn_up = QPushButton("▲")
                                d_btn_up.setFixedSize(14, 14)
                                d_btn_up.setStyleSheet("font-size: 7px; border: none; color: #8be;")
                                d_btn_up.setToolTip("Device nach oben")
                                d_btn_up.clicked.connect(lambda _=False, _i=i, _j=j: self._move_device(_i, _j, -1))
                                d_row.addWidget(d_btn_up)
                            if j < len(devs_list) - 1:
                                d_btn_dn = QPushButton("▼")
                                d_btn_dn.setFixedSize(14, 14)
                                d_btn_dn.setStyleSheet("font-size: 7px; border: none; color: #8be;")
                                d_btn_dn.setToolTip("Device nach unten")
                                d_btn_dn.clicked.connect(lambda _=False, _i=i, _j=j: self._move_device(_i, _j, +1))
                                d_row.addWidget(d_btn_dn)

                            d_btn_rm = QPushButton("×")
                            d_btn_rm.setFixedSize(16, 16)
                            d_btn_rm.setStyleSheet("font-size: 9px; border: none; color: #c66;")
                            d_btn_rm.setToolTip("Device entfernen")
                            d_btn_rm.clicked.connect(lambda _=False, _i=i, _j=j: self._remove_device(_i, _j))
                            d_row.addWidget(d_btn_rm)

                            frame_lay.addLayout(d_row)
                    else:
                        empty_lbl = QLabel("    (leer)")
                        empty_lbl.setStyleSheet("font-size: 8px; color: #555; font-style: italic;")
                        frame_lay.addWidget(empty_lbl)

                    # Add FX to this layer
                    btn_add_fx = QPushButton(f"+ FX → {name}")
                    btn_add_fx.setFixedHeight(18)
                    btn_add_fx.setStyleSheet("font-size: 8px; color: #4fc3f7;")
                    btn_add_fx.setToolTip(f"Audio-FX in {name} einfügen")
                    btn_add_fx.clicked.connect(lambda _=False, _i=i, _btn=btn_add_fx: self._show_add_fx_menu(_i, _btn))
                    frame_lay.addWidget(btn_add_fx)

                    # v0.0.20.562: Zoom into layer
                    btn_zoom = QPushButton(f"🔍 {name} öffnen → FX bearbeiten")
                    btn_zoom.setFixedHeight(20)
                    btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_zoom.setStyleSheet(
                        "QPushButton { font-size: 9px; color: #80deea; text-align: left; "
                        "padding: 2px 8px; border: 1px solid #4fc3f7; border-radius: 3px; "
                        "background: rgba(79,195,247,20); }"
                        "QPushButton:hover { background: rgba(79,195,247,60); color: #fff; }"
                    )
                    btn_zoom.clicked.connect(
                        lambda _=False, _i=i, _name=name: self._zoom_into_fx_layer(_i, _name)
                    )
                    frame_lay.addWidget(btn_zoom)

                self._layer_area.addWidget(frame)
        except Exception:
            pass

    def _toggle_expand(self, layer_index: int) -> None:
        if layer_index in self._expanded_layers:
            self._expanded_layers.discard(layer_index)
        else:
            self._expanded_layers.add(layer_index)
        self._rebuild_layers()

    def _on_layer_vol(self, val: int, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index]["volume"] = float(val) / 100.0
        except Exception:
            pass

    def _toggle_layer_enabled(self, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index]["enabled"] = not bool(layers[layer_index].get("enabled", True))
                self._emit_update()
        except Exception:
            pass

    def _remove_layer(self, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers.pop(layer_index)
                self._expanded_layers.discard(layer_index)
                # Shift expanded indices
                self._expanded_layers = {(x - 1 if x > layer_index else x) for x in self._expanded_layers if x != layer_index}
                self._emit_update()
        except Exception:
            pass

    def _toggle_device_enabled(self, layer_index: int, device_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                if 0 <= device_index < len(devs) and isinstance(devs[device_index], dict):
                    devs[device_index]["enabled"] = not bool(devs[device_index].get("enabled", True))
                    self._emit_update()
        except Exception:
            pass

    def _remove_device(self, layer_index: int, device_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                if 0 <= device_index < len(devs):
                    devs.pop(device_index)
                    self._emit_update()
        except Exception:
            pass

    def _move_device(self, layer_index: int, device_index: int, direction: int) -> None:
        """v0.0.20.534: Move device up (-1) or down (+1) within a layer."""
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                new_idx = device_index + direction
                if 0 <= device_index < len(devs) and 0 <= new_idx < len(devs):
                    devs[device_index], devs[new_idx] = devs[new_idx], devs[device_index]
                    self._emit_update()
        except Exception:
            pass

    def _show_add_fx_menu(self, layer_index: int, anchor: QWidget) -> None:
        """v0.0.20.567: Show popup with ALL FX (built-in + external)."""
        try:
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 10px; }")
            fx_actions = _build_container_fx_menu(menu)
            if not fx_actions:
                menu.addAction("(keine FX verfügbar)").setEnabled(False)
            chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
            if chosen is None:
                return
            for a, pid, name in fx_actions:
                if chosen == a:
                    self._add_fx_to_layer(layer_index, pid, name)
                    break
        except Exception:
            pass

    def _add_fx_to_layer(self, layer_index: int, plugin_id: str, name: str = "") -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                from pydaw.model.project import new_id
                devs = layers[layer_index].setdefault("devices", [])
                devs.append({
                    "id": new_id("afx"),
                    "plugin_id": plugin_id,
                    "name": name or plugin_id.split(".")[-1],
                    "enabled": True,
                    "params": {},
                })
                if layer_index not in self._expanded_layers:
                    self._expanded_layers.add(layer_index)
                self._emit_update()
        except Exception:
            pass

    def _on_mix_changed(self, val: int) -> None:
        try:
            self._mix_label.setText(f"{val}%")
            params = self._device.get("params", {})
            if isinstance(params, dict):
                params["mix"] = float(val) / 100.0
            am = getattr(self._services, "automation_manager", None) if self._services else None
            if am is not None:
                rt = getattr(am, "_rt_params", None)
                if rt is not None and hasattr(rt, "set_target"):
                    rt.set_target(f"afx:{self._track_id}:{self._device_id}:layer_mix", float(val) / 100.0)
        except Exception:
            pass

    def _add_layer(self) -> None:
        try:
            layers = self._device.get("layers", [])
            if not isinstance(layers, list):
                layers = []
                self._device["layers"] = layers
            n = len(layers) + 1
            if n > 8:
                return
            layers.append({"name": f"Layer {n}", "enabled": True, "volume": 1.0, "devices": []})
            self._emit_update()
        except Exception:
            pass

    def _load_preset(self) -> None:
        """v0.0.20.541: Load a container preset from JSON file."""
        try:
            data = _load_container_preset(self)
            if data is None:
                return
            # Merge preset data into current device
            if "layers" in data:
                self._device["layers"] = data["layers"]
            if "params" in data and isinstance(data["params"], dict):
                self._device.setdefault("params", {}).update(data["params"])
            self._expanded_layers.clear()
            self._rebuild_layers()
            self._emit_update()
        except Exception:
            pass

    def _zoom_into_fx_layer(self, layer_index: int, layer_name: str = "") -> None:
        """v0.0.20.562: Zoom into FX layer — DevicePanel shows full FX cards."""
        try:
            w = self.parentWidget()
            panel = None
            for _ in range(20):
                if w is None:
                    break
                if hasattr(w, "zoom_into_fx_layer"):
                    panel = w
                    break
                w = w.parentWidget()
            if panel is not None:
                panel.zoom_into_fx_layer(
                    self._track_id, self._device_id,
                    layer_index, layer_name or f"Layer {layer_index + 1}"
                )
        except Exception:
            import traceback
            traceback.print_exc()

    def _emit_update(self) -> None:
        try:
            proj_svc = getattr(self._services, "project", None) if self._services else None
            if proj_svc is not None and hasattr(proj_svc, "_emit_updated"):
                proj_svc._emit_updated()
        except Exception:
            pass


class _ChainContainerWidget(QWidget):
    """UI widget for a Chain container — expandable device list with add/remove/enable.

    v0.0.20.532: Full device management inside the chain.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, device: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = track_id
        self._device_id = device_id
        self._device = device

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        # Header
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(4)
        header = QLabel("⟐ Chain (Seriell)")
        header.setStyleSheet("font-size: 10px; font-weight: bold; color: #ffb74d;")
        hdr_row.addWidget(header, 1)
        btn_save = QPushButton("💾")
        btn_save.setFixedSize(20, 18)
        btn_save.setStyleSheet("font-size: 9px; border: none;")
        btn_save.setToolTip("Container-Preset speichern")
        btn_save.clicked.connect(lambda _=False: _save_container_preset(self._device, self))
        hdr_row.addWidget(btn_save)
        btn_load = QPushButton("📂")
        btn_load.setFixedSize(20, 18)
        btn_load.setStyleSheet("font-size: 9px; border: none;")
        btn_load.setToolTip("Container-Preset laden")
        btn_load.clicked.connect(lambda _=False: self._load_preset())
        hdr_row.addWidget(btn_load)
        lay.addLayout(hdr_row)

        # Mix slider
        mix_row = QHBoxLayout()
        mix_row.setSpacing(4)
        mix_lbl = QLabel("Mix:")
        mix_lbl.setStyleSheet("font-size: 9px;")
        mix_row.addWidget(mix_lbl)
        self._mix_slider = QSlider(Qt.Orientation.Horizontal)
        self._mix_slider.setRange(0, 100)
        params = device.get("params", {}) if isinstance(device.get("params"), dict) else {}
        self._mix_slider.setValue(int(float(params.get("mix", 1.0)) * 100))
        self._mix_slider.setFixedHeight(16)
        self._mix_slider.setToolTip("Sub-Chain Mix (0% = Dry/Bypass, 100% = Wet)")
        self._mix_slider.valueChanged.connect(self._on_mix_changed)
        mix_row.addWidget(self._mix_slider)
        self._mix_label = QLabel(f"{self._mix_slider.value()}%")
        self._mix_label.setStyleSheet("font-size: 9px; min-width: 30px;")
        mix_row.addWidget(self._mix_label)
        lay.addLayout(mix_row)

        # Device area
        self._dev_area = QVBoxLayout()
        self._dev_area.setSpacing(2)
        lay.addLayout(self._dev_area)
        self._rebuild_devices()

        # Add FX button
        btn_add = QPushButton("+ FX → Chain")
        btn_add.setFixedHeight(20)
        btn_add.setStyleSheet("font-size: 8px; color: #ffb74d;")
        btn_add.setToolTip("Audio-FX in diese Sub-Chain einfügen")
        btn_add.clicked.connect(lambda _=False: self._show_add_fx_menu(btn_add))
        lay.addWidget(btn_add)

    def _rebuild_devices(self) -> None:
        try:
            while self._dev_area.count():
                item = self._dev_area.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
                elif item.layout():
                    _clear_layout(item.layout())

            devs = self._device.get("devices", []) or []
            devs = [d for d in devs if isinstance(d, dict)]

            if not devs:
                hint = QLabel("Leere Chain — klicke '+ FX → Chain'")
                hint.setStyleSheet("font-size: 8px; color: #666; font-style: italic;")
                self._dev_area.addWidget(hint)
                return

            for j, dev in enumerate(devs):
                d_name = str(dev.get("name") or dev.get("plugin_id") or f"FX {j+1}")
                d_enabled = bool(dev.get("enabled", True))
                d_row = QHBoxLayout()
                d_row.setSpacing(2)

                d_status = "●" if d_enabled else "○"
                d_color = "#ffb74d" if d_enabled else "#555"
                d_lbl = QLabel(f"  {d_status} {j+1}. {d_name}")
                d_lbl.setStyleSheet(f"font-size: 9px; color: {d_color};")
                d_row.addWidget(d_lbl, 1)

                d_btn_en = QPushButton("⏻")
                d_btn_en.setFixedSize(16, 16)
                d_btn_en.setStyleSheet(f"font-size: 8px; border: none; color: {d_color};")
                d_btn_en.setToolTip("Device Ein/Aus")
                d_btn_en.clicked.connect(lambda _=False, _j=j: self._toggle_device_enabled(_j))
                d_row.addWidget(d_btn_en)

                # v0.0.20.534: Reorder buttons
                if j > 0:
                    d_btn_up = QPushButton("▲")
                    d_btn_up.setFixedSize(14, 14)
                    d_btn_up.setStyleSheet("font-size: 7px; border: none; color: #ffb74d;")
                    d_btn_up.setToolTip("Device nach oben")
                    d_btn_up.clicked.connect(lambda _=False, _j=j: self._move_device(_j, -1))
                    d_row.addWidget(d_btn_up)
                if j < len(devs) - 1:
                    d_btn_dn = QPushButton("▼")
                    d_btn_dn.setFixedSize(14, 14)
                    d_btn_dn.setStyleSheet("font-size: 7px; border: none; color: #ffb74d;")
                    d_btn_dn.setToolTip("Device nach unten")
                    d_btn_dn.clicked.connect(lambda _=False, _j=j: self._move_device(_j, +1))
                    d_row.addWidget(d_btn_dn)

                d_btn_rm = QPushButton("×")
                d_btn_rm.setFixedSize(16, 16)
                d_btn_rm.setStyleSheet("font-size: 9px; border: none; color: #c66;")
                d_btn_rm.setToolTip("Device entfernen")
                d_btn_rm.clicked.connect(lambda _=False, _j=j: self._remove_device(_j))
                d_row.addWidget(d_btn_rm)

                self._dev_area.addLayout(d_row)

            # v0.0.20.562: Zoom into chain
            btn_zoom = QPushButton("🔍 Chain öffnen → FX bearbeiten")
            btn_zoom.setFixedHeight(20)
            btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_zoom.setStyleSheet(
                "QPushButton { font-size: 9px; color: #ffe0b2; text-align: left; "
                "padding: 2px 8px; border: 1px solid #ffb74d; border-radius: 3px; "
                "background: rgba(255,183,77,20); }"
                "QPushButton:hover { background: rgba(255,183,77,60); color: #fff; }"
            )
            btn_zoom.clicked.connect(lambda _=False: self._zoom_into_chain())
            self._dev_area.addWidget(btn_zoom)
        except Exception:
            pass

    def _toggle_device_enabled(self, device_index: int) -> None:
        try:
            devs = self._device.get("devices", []) or []
            if 0 <= device_index < len(devs) and isinstance(devs[device_index], dict):
                devs[device_index]["enabled"] = not bool(devs[device_index].get("enabled", True))
                self._emit_update()
        except Exception:
            pass

    def _remove_device(self, device_index: int) -> None:
        try:
            devs = self._device.get("devices", []) or []
            if 0 <= device_index < len(devs):
                devs.pop(device_index)
                self._emit_update()
        except Exception:
            pass

    def _move_device(self, device_index: int, direction: int) -> None:
        """v0.0.20.534: Move device up (-1) or down (+1) within the chain."""
        try:
            devs = self._device.get("devices", []) or []
            new_idx = device_index + direction
            if 0 <= device_index < len(devs) and 0 <= new_idx < len(devs):
                devs[device_index], devs[new_idx] = devs[new_idx], devs[device_index]
                self._emit_update()
        except Exception:
            pass

    def _show_add_fx_menu(self, anchor: QWidget) -> None:
        """v0.0.20.567: Show popup with ALL FX (built-in + external)."""
        try:
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 10px; }")
            fx_actions = _build_container_fx_menu(menu)
            if not fx_actions:
                menu.addAction("(keine FX verfügbar)").setEnabled(False)
            chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
            if chosen is None:
                return
            for a, pid, name in fx_actions:
                if chosen == a:
                    self._add_fx(pid, name)
                    break
        except Exception:
            pass

    def _add_fx(self, plugin_id: str, name: str = "") -> None:
        try:
            from pydaw.model.project import new_id
            devs = self._device.setdefault("devices", [])
            devs.append({
                "id": new_id("afx"),
                "plugin_id": plugin_id,
                "name": name or plugin_id.split(".")[-1],
                "enabled": True,
                "params": {},
            })
            self._emit_update()
        except Exception:
            pass

    def _on_mix_changed(self, val: int) -> None:
        try:
            self._mix_label.setText(f"{val}%")
            params = self._device.get("params", {})
            if isinstance(params, dict):
                params["mix"] = float(val) / 100.0
            am = getattr(self._services, "automation_manager", None) if self._services else None
            if am is not None:
                rt = getattr(am, "_rt_params", None)
                if rt is not None and hasattr(rt, "set_target"):
                    rt.set_target(f"afx:{self._track_id}:{self._device_id}:chain_mix", float(val) / 100.0)
        except Exception:
            pass

    def _load_preset(self) -> None:
        """v0.0.20.541: Load a container preset from JSON file."""
        try:
            data = _load_container_preset(self)
            if data is None:
                return
            if "devices" in data:
                self._device["devices"] = data["devices"]
            if "params" in data and isinstance(data["params"], dict):
                self._device.setdefault("params", {}).update(data["params"])
            self._rebuild_devices()
            self._emit_update()
        except Exception:
            pass

    def _zoom_into_chain(self) -> None:
        """v0.0.20.562: Zoom into chain — DevicePanel shows full FX cards."""
        try:
            w = self.parentWidget()
            panel = None
            for _ in range(20):
                if w is None:
                    break
                if hasattr(w, "zoom_into_chain"):
                    panel = w
                    break
                w = w.parentWidget()
            if panel is not None:
                panel.zoom_into_chain(self._track_id, self._device_id)
        except Exception:
            import traceback
            traceback.print_exc()

    def _emit_update(self) -> None:
        try:
            proj_svc = getattr(self._services, "project", None) if self._services else None
            if proj_svc is not None and hasattr(proj_svc, "_emit_updated"):
                proj_svc._emit_updated()
        except Exception:
            pass


def _build_container_fx_menu(menu) -> list:
    """v0.0.20.567: Build a complete FX menu with Built-in + External plugins.

    Shared by FxLayerContainerWidget, ChainContainerWidget,
    InstrumentLayerContainerWidget. Returns list of (QAction, plugin_id, name).
    """
    actions = []

    # Built-in FX
    try:
        from .fx_specs import get_audio_fx
        for spec in (get_audio_fx() or []):
            name = str(getattr(spec, "name", "") or "")
            pid = str(getattr(spec, "plugin_id", "") or "")
            if name and pid:
                a = menu.addAction(f"  🔊 {name}")
                actions.append((a, pid, name))
    except Exception:
        pass

    # External plugins from scanner cache
    try:
        from pydaw.services import plugin_scanner
        cache = plugin_scanner.load_cache() or {}
        _labels = {"lv2": "LV2", "ladspa": "LADSPA", "dssi": "DSSI",
                    "vst2": "VST2", "vst3": "VST3", "clap": "CLAP"}
        for kind in ("vst3", "clap", "vst2", "lv2", "dssi", "ladspa"):
            plugins = cache.get(kind, []) or []
            fx_plugins = [p for p in plugins if not getattr(p, "is_instrument", False)]
            if not fx_plugins:
                continue
            label = _labels.get(kind, kind.upper())
            sub = menu.addMenu(f"🔌 {label} ({len(fx_plugins)})")
            sub.setStyleSheet("QMenu { font-size: 10px; }")
            if len(fx_plugins) > 40:
                for s in range(0, len(fx_plugins), 40):
                    chunk = fx_plugins[s:s + 40]
                    fn = str(getattr(chunk[0], "name", "?") or "?")[:12]
                    ln = str(getattr(chunk[-1], "name", "?") or "?")[:12]
                    csub = sub.addMenu(f"{fn} … {ln}")
                    csub.setStyleSheet("QMenu { font-size: 10px; }")
                    for p in chunk:
                        pn = str(getattr(p, "name", "") or "")
                        pp = str(getattr(p, "plugin_id", "") or "")
                        if pn and pp:
                            a = csub.addAction(f"  {pn}")
                            actions.append((a, f"ext.{kind}:{pp}", pn))
            else:
                for p in fx_plugins:
                    pn = str(getattr(p, "name", "") or "")
                    pp = str(getattr(p, "plugin_id", "") or "")
                    if pn and pp:
                        a = sub.addAction(f"  {pn}")
                        actions.append((a, f"ext.{kind}:{pp}", pn))
    except Exception:
        pass

    return actions


def _clear_layout(layout) -> None:
    """Recursively clear a QLayout."""
    try:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                _clear_layout(item.layout())
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# v0.0.20.536: Instrument Layer Container Widget
# ═══════════════════════════════════════════════════════════════════════════════

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _midi_note_name(note: int) -> str:
    """v0.0.20.540: Convert MIDI note number (0-127) to name like C4, F#2."""
    try:
        n = int(note)
        octave = (n // 12) - 2
        return f"{_NOTE_NAMES[n % 12]}{octave}"
    except Exception:
        return str(note)


class _InstrumentLayerContainerWidget(QWidget):
    """UI widget for an Instrument Layer (Stack) container.

    Phase 1: Data model + UI with instrument assignment per layer,
    volume/enable/remove per layer, and per-layer FX adding.
    Audio engine treats this as an FxLayerContainer (parallel processing).
    Multi-instrument MIDI dispatch is Phase 2.
    """

    def __init__(self, services: Any, track_id: str, device_id: str, device: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._track_id = track_id
        self._device_id = device_id
        self._device = device
        # v0.0.20.546: All layers expanded by default so instrument picker is visible
        _n_layers = len(device.get("layers", []) or [])
        self._expanded_layers: set = set(range(_n_layers))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        # Header
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(4)
        header = QLabel("🎹 Instrument Layer (Stack)")
        header.setStyleSheet("font-size: 11px; font-weight: bold; color: #ce93d8;")
        hdr_row.addWidget(header, 1)
        btn_save = QPushButton("💾")
        btn_save.setFixedSize(20, 18)
        btn_save.setStyleSheet("font-size: 9px; border: none;")
        btn_save.setToolTip("Container-Preset speichern")
        btn_save.clicked.connect(lambda _=False: _save_container_preset(self._device, self))
        hdr_row.addWidget(btn_save)
        btn_load = QPushButton("📂")
        btn_load.setFixedSize(20, 18)
        btn_load.setStyleSheet("font-size: 9px; border: none;")
        btn_load.setToolTip("Container-Preset laden")
        btn_load.clicked.connect(lambda _=False: self._load_preset())
        hdr_row.addWidget(btn_load)
        lay.addLayout(hdr_row)

        # Mix slider
        mix_row = QHBoxLayout()
        mix_row.setSpacing(4)
        mix_lbl = QLabel("Mix:")
        mix_lbl.setStyleSheet("font-size: 9px;")
        mix_row.addWidget(mix_lbl)
        self._mix_slider = QSlider(Qt.Orientation.Horizontal)
        self._mix_slider.setRange(0, 100)
        params = device.get("params", {}) if isinstance(device.get("params"), dict) else {}
        self._mix_slider.setValue(int(float(params.get("mix", 1.0)) * 100))
        self._mix_slider.setFixedHeight(16)
        self._mix_slider.setToolTip("Container Mix (0% = Dry, 100% = Wet)")
        self._mix_slider.valueChanged.connect(self._on_mix_changed)
        mix_row.addWidget(self._mix_slider)
        self._mix_label = QLabel(f"{self._mix_slider.value()}%")
        self._mix_label.setStyleSheet("font-size: 9px; min-width: 30px;")
        mix_row.addWidget(self._mix_label)
        lay.addLayout(mix_row)

        # Layer area
        self._layer_area = QVBoxLayout()
        self._layer_area.setSpacing(2)
        lay.addLayout(self._layer_area)
        self._rebuild_layers()

        # Add Layer button
        btn_add = QPushButton("+ Instrument Layer")
        btn_add.setFixedHeight(20)
        btn_add.setStyleSheet("font-size: 8px; color: #ce93d8;")
        btn_add.setToolTip("Neuen Instrument-Layer hinzufügen (max 8)")
        btn_add.clicked.connect(lambda _=False: self._add_layer())
        lay.addWidget(btn_add)

    def _rebuild_layers(self) -> None:
        """Rebuild the layer list UI. Instrument picker always visible."""
        # Clear
        try:
            while self._layer_area.count():
                item = self._layer_area.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
                elif item.layout():
                    _clear_layout(item.layout())
        except Exception:
            pass

        layers = self._device.get("layers", []) or []
        if not layers:
            try:
                hint = QLabel("Keine Layer — klicke '+ Instrument Layer'")
                hint.setStyleSheet("font-size: 10px; color: #999; font-style: italic;")
                self._layer_area.addWidget(hint)
            except Exception:
                pass
            return

        for i, layer in enumerate(layers):
            if not isinstance(layer, dict):
                continue
            try:
                self._build_one_layer(i, layer)
            except Exception:
                import traceback
                traceback.print_exc()

    def _build_one_layer(self, i: int, layer: dict) -> None:
        """Build UI for a single layer — instrument picker always visible."""
        name = str(layer.get("name", f"Layer {i+1}"))
        enabled = bool(layer.get("enabled", True))
        instrument = str(layer.get("instrument", "") or "")
        instrument_name = str(layer.get("instrument_name", "") or instrument or "(kein Instrument)")
        vol = float(layer.get("volume", 1.0))

        # Container frame
        container = QWidget()
        v_lay = QVBoxLayout(container)
        v_lay.setContentsMargins(2, 2, 2, 2)
        v_lay.setSpacing(3)

        # Row 1: Name + Volume + Enable + Remove
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        lbl_name = QLabel(f"🎹 {name}")
        lbl_name.setStyleSheet(
            f"font-size: 11px; font-weight: bold; "
            f"color: {'#e1bee7' if enabled else '#777'}; "
            f"padding: 2px 4px; background: rgba(126,87,194,40); "
            f"border-radius: 3px;"
        )
        row1.addWidget(lbl_name)

        vol_sld = QSlider(Qt.Orientation.Horizontal)
        vol_sld.setRange(0, 100)
        vol_sld.setValue(int(vol * 100))
        vol_sld.setFixedSize(50, 16)
        vol_sld.setToolTip(f"Layer Volume: {int(vol*100)}%")
        vol_sld.valueChanged.connect(lambda v, _i=i: self._on_layer_vol(v, _i))
        row1.addWidget(vol_sld)

        btn_en = QPushButton("●" if enabled else "○")
        btn_en.setFixedSize(22, 22)
        btn_en.setStyleSheet(f"font-size: 12px; border: none; color: {'#ce93d8' if enabled else '#555'};")
        btn_en.setToolTip("Layer Ein/Aus")
        btn_en.clicked.connect(lambda _=False, _i=i: self._toggle_layer_enabled(_i))
        row1.addWidget(btn_en)

        btn_rm = QPushButton("×")
        btn_rm.setFixedSize(22, 22)
        btn_rm.setStyleSheet("font-size: 12px; border: none; color: #e57373;")
        btn_rm.setToolTip("Layer entfernen")
        btn_rm.clicked.connect(lambda _=False, _i=i: self._remove_layer(_i))
        row1.addWidget(btn_rm)

        v_lay.addLayout(row1)

        # Row 2: Instrument Picker — ALWAYS visible, big and obvious
        btn_pick = QPushButton(f"🎹 Instrument wählen: {instrument_name}")
        btn_pick.setMinimumHeight(28)
        btn_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pick.setStyleSheet(
            "QPushButton { font-size: 11px; color: #fff; text-align: left; "
            "padding: 4px 10px; border: 2px solid #ab47bc; border-radius: 4px; "
            "background: rgba(171, 71, 188, 60); }"
            "QPushButton:hover { background: rgba(171, 71, 188, 100); }"
        )
        btn_pick.setToolTip("Klick: Instrument für diesen Layer auswählen\n(Built-in, VST3, CLAP, VST2, LV2, SF2)")
        btn_pick.clicked.connect(lambda _=False, _i=i, _btn=btn_pick: self._show_instrument_picker(_i, _btn))
        v_lay.addWidget(btn_pick)

        # v0.0.20.554: Zoom into layer button (Bitwig-style)
        if instrument:
            btn_zoom = QPushButton(f"🔍 {name} öffnen → Instrument bearbeiten")
            btn_zoom.setMinimumHeight(24)
            btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_zoom.setStyleSheet(
                "QPushButton { font-size: 10px; color: #e1bee7; text-align: left; "
                "padding: 3px 10px; border: 1px solid #7e57c2; border-radius: 3px; "
                "background: rgba(126, 87, 194, 30); }"
                "QPushButton:hover { background: rgba(126, 87, 194, 70); color: #fff; }"
            )
            btn_zoom.setToolTip(
                "Bitwig-Stil: In diesen Layer reinzoomen.\n"
                "Zeigt das Instrument-Widget + FX-Chain im Device-Panel.\n"
                "← Zurück-Button bringt dich zurück."
            )
            btn_zoom.clicked.connect(
                lambda _=False, _i=i, _name=name: self._zoom_into_layer(_i, _name)
            )
            v_lay.addWidget(btn_zoom)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #5a4a6a;")
        sep.setFixedHeight(1)
        v_lay.addWidget(sep)

        self._layer_area.addWidget(container)

    def _show_instrument_picker(self, layer_index: int, anchor: QWidget) -> None:
        """Show popup menu to select an instrument for this layer."""
        try:
            from PyQt6.QtGui import QCursor
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 11px; min-width: 200px; }")
            all_actions: list = []

            # --- Built-in instruments ---
            menu.addSection("🎹 Built-in")
            try:
                from .fx_specs import get_instruments
                for spec in (get_instruments() or []):
                    name = str(getattr(spec, "name", "") or "")
                    pid = str(getattr(spec, "plugin_id", "") or "")
                    if name and pid:
                        a = menu.addAction(f"  🎹 {name}")
                        all_actions.append((a, pid, name))
            except Exception as e:
                print(f"[INST-PICKER] Built-in load error: {e}", flush=True)

            # --- External instruments from plugin cache ---
            try:
                from pydaw.services import plugin_scanner
                cache = plugin_scanner.load_cache() or {}
                _format_labels = {
                    "lv2": "🔌 LV2", "ladspa": "🔌 LADSPA", "dssi": "🔌 DSSI",
                    "vst2": "🔌 VST2", "vst3": "🔌 VST3", "clap": "🔌 CLAP",
                }
                for kind in ("vst3", "clap", "vst2", "lv2", "dssi", "ladspa"):
                    plugins = cache.get(kind, []) or []
                    instruments = [p for p in plugins if getattr(p, "is_instrument", False)]
                    if not instruments:
                        continue
                    label = _format_labels.get(kind, kind.upper())
                    sub = menu.addMenu(f"{label} ({len(instruments)})")
                    sub.setStyleSheet("QMenu { font-size: 11px; }")
                    for p in instruments[:50]:
                        p_name = str(getattr(p, "name", "") or "")
                        p_pid = str(getattr(p, "plugin_id", "") or "")
                        if p_name and p_pid:
                            ext_pid = f"ext.{kind}:{p_pid}"
                            a = sub.addAction(f"  {p_name}")
                            all_actions.append((a, ext_pid, p_name))
                    if len(instruments) > 50:
                        sub.addAction(f"  ... und {len(instruments) - 50} weitere").setEnabled(False)
            except Exception as e:
                print(f"[INST-PICKER] Cache load error: {e}", flush=True)

            if not all_actions:
                menu.addAction("(keine Instrumente verfügbar — Rescan im Plugin-Browser?)").setEnabled(False)

            # Use QCursor.pos() — robust even if anchor widget was rebuilt
            chosen = menu.exec(QCursor.pos())
            if chosen is None:
                return
            for a, pid, name in all_actions:
                if chosen == a:
                    self._set_layer_instrument(layer_index, pid, name)
                    break
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _set_layer_instrument(self, layer_index: int, plugin_id: str, name: str) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index]["instrument"] = plugin_id
                layers[layer_index]["instrument_name"] = name
                # v0.0.20.543: SF2 needs a file path
                if plugin_id == "chrono.sf2":
                    try:
                        from PyQt6.QtWidgets import QFileDialog
                        sf2_path, _ = QFileDialog.getOpenFileName(
                            self, "SF2 Soundfont auswählen", "",
                            "SF2 Soundfonts (*.sf2 *.SF2);;Alle Dateien (*)"
                        )
                        if sf2_path:
                            layers[layer_index]["sf2_path"] = sf2_path
                            layers[layer_index]["instrument_name"] = f"SF2: {Path(sf2_path).stem}"
                        else:
                            # User cancelled — revert
                            layers[layer_index]["instrument"] = ""
                            layers[layer_index]["instrument_name"] = ""
                    except Exception:
                        pass
                self._rebuild_layers()
                self._emit_update()
        except Exception:
            pass

    def _zoom_into_layer(self, layer_index: int, layer_name: str = "") -> None:
        """v0.0.20.554: Bitwig-style zoom into a layer — DevicePanel shows layer content."""
        try:
            # Find the DevicePanel by walking up the widget tree
            w = self.parentWidget()
            panel = None
            for _ in range(20):
                if w is None:
                    break
                if hasattr(w, "zoom_into_layer"):
                    panel = w
                    break
                w = w.parentWidget()
            if panel is None:
                # Try through services
                if self._services and hasattr(self._services, "device_panel"):
                    panel = getattr(self._services, "device_panel", None)
            if panel is not None:
                panel.zoom_into_layer(
                    self._track_id, self._device_id,
                    layer_index, layer_name or f"Layer {layer_index + 1}"
                )
            else:
                print("[INST-LAYER] DevicePanel not found for zoom!", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _set_layer_range(self, layer_index: int, key: str, value: int) -> None:
        """v0.0.20.540: Set velocity/key range value for a layer."""
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index][key] = max(0, min(127, int(value)))
        except Exception:
            pass

    def _toggle_expand(self, layer_index: int) -> None:
        if layer_index in self._expanded_layers:
            self._expanded_layers.discard(layer_index)
        else:
            self._expanded_layers.add(layer_index)
        self._rebuild_layers()

    def _on_layer_vol(self, val: int, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index]["volume"] = float(val) / 100.0
        except Exception:
            pass

    def _toggle_layer_enabled(self, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers[layer_index]["enabled"] = not bool(layers[layer_index].get("enabled", True))
                self._rebuild_layers()
                self._emit_update()
        except Exception:
            pass

    def _remove_layer(self, layer_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                layers.pop(layer_index)
                self._expanded_layers.discard(layer_index)
                self._expanded_layers = {(x - 1 if x > layer_index else x) for x in self._expanded_layers if x != layer_index}
                self._rebuild_layers()
                self._emit_update()
        except Exception:
            pass

    def _toggle_device_enabled(self, layer_index: int, device_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                if 0 <= device_index < len(devs) and isinstance(devs[device_index], dict):
                    devs[device_index]["enabled"] = not bool(devs[device_index].get("enabled", True))
                    self._rebuild_layers()
                    self._emit_update()
        except Exception:
            pass

    def _remove_device(self, layer_index: int, device_index: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                if 0 <= device_index < len(devs):
                    devs.pop(device_index)
                    self._rebuild_layers()
                    self._emit_update()
        except Exception:
            pass

    def _move_device(self, layer_index: int, device_index: int, direction: int) -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                devs = layers[layer_index].get("devices", []) or []
                new_idx = device_index + direction
                if 0 <= device_index < len(devs) and 0 <= new_idx < len(devs):
                    devs[device_index], devs[new_idx] = devs[new_idx], devs[device_index]
                    self._rebuild_layers()
                    self._emit_update()
        except Exception:
            pass

    def _show_add_fx_menu(self, layer_index: int, anchor: QWidget) -> None:
        """v0.0.20.567: Show popup with ALL FX (built-in + external)."""
        try:
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 10px; }")
            fx_actions = _build_container_fx_menu(menu)
            if not fx_actions:
                menu.addAction("(keine FX verfügbar)").setEnabled(False)
            chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
            if chosen is None:
                return
            for a, pid, name in fx_actions:
                if chosen == a:
                    self._add_fx_to_layer(layer_index, pid, name)
                    break
        except Exception:
            pass

    def _add_fx_to_layer(self, layer_index: int, plugin_id: str, name: str = "") -> None:
        try:
            layers = self._device.get("layers", []) or []
            if 0 <= layer_index < len(layers):
                from pydaw.model.project import new_id
                devs = layers[layer_index].setdefault("devices", [])
                devs.append({
                    "id": new_id("afx"),
                    "plugin_id": plugin_id,
                    "name": name or plugin_id.split(".")[-1],
                    "enabled": True,
                    "params": {},
                })
                if layer_index not in self._expanded_layers:
                    self._expanded_layers.add(layer_index)
                self._rebuild_layers()
                self._emit_update()
        except Exception:
            pass

    def _on_mix_changed(self, val: int) -> None:
        try:
            self._mix_label.setText(f"{val}%")
            params = self._device.get("params", {})
            if isinstance(params, dict):
                params["mix"] = float(val) / 100.0
            am = getattr(self._services, "automation_manager", None) if self._services else None
            if am is not None:
                rt = getattr(am, "_rt_params", None)
                if rt is not None and hasattr(rt, "set_target"):
                    rt.set_target(f"afx:{self._track_id}:{self._device_id}:layer_mix", float(val) / 100.0)
        except Exception:
            pass

    def _add_layer(self) -> None:
        try:
            layers = self._device.get("layers", [])
            if not isinstance(layers, list):
                layers = []
                self._device["layers"] = layers
            n = len(layers) + 1
            if n > 8:
                return
            layers.append({
                "name": f"Layer {n}",
                "enabled": True,
                "volume": 1.0,
                "instrument": "",
                "instrument_name": "",
                "devices": [],
            })
            self._rebuild_layers()
            self._emit_update()
        except Exception:
            pass

    def _load_preset(self) -> None:
        """v0.0.20.541: Load a container preset from JSON file."""
        try:
            data = _load_container_preset(self)
            if data is None:
                return
            if "layers" in data:
                self._device["layers"] = data["layers"]
            if "params" in data and isinstance(data["params"], dict):
                self._device.setdefault("params", {}).update(data["params"])
            self._expanded_layers.clear()
            self._rebuild_layers()
            self._emit_update()
        except Exception:
            pass

    def _emit_update(self) -> None:
        try:
            proj_svc = getattr(self._services, "project", None) if self._services else None
            if proj_svc is not None and hasattr(proj_svc, "_emit_updated"):
                proj_svc._emit_updated()
        except Exception:
            pass
        # v0.0.20.551: Trigger audio engine rebuild so instrument engines
        # get created/destroyed when layer instruments change.
        # Deferred by 100ms so project data is committed first.
        try:
            QTimer.singleShot(100, self._rebuild_audio_engine)
        except Exception:
            pass

    def _rebuild_audio_engine(self) -> None:
        """Trigger audio engine rebuild for instrument layer changes."""
        try:
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            if ae is None or not hasattr(ae, "rebuild_fx_maps"):
                return
            # Get project snapshot — required by rebuild_fx_maps()
            proj_svc = getattr(self._services, "project", None) if self._services else None
            project = None
            if proj_svc is not None:
                ctx = getattr(proj_svc, "ctx", None)
                if ctx is not None:
                    project = getattr(ctx, "project", None)
            if project is None:
                project = getattr(proj_svc, "project", None) if proj_svc else None
            if project is None:
                print("[INST-LAYER] No project snapshot for rebuild!", flush=True)
                return
            ae.rebuild_fx_maps(project)
            print("[INST-LAYER] Audio engine rebuild triggered ✓", flush=True)
        except Exception as e:
            import traceback
            print(f"[INST-LAYER] Audio engine rebuild failed: {e}", flush=True)
            traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# v0.0.20.541: Container Preset Save/Load
# ═══════════════════════════════════════════════════════════════════════════════

def _container_presets_dir() -> Path:
    """Return the container presets directory, creating it if needed."""
    try:
        d = Path(os.path.expanduser("~/.config/ChronoScaleStudio/container_presets"))
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        return Path(".")


def _save_container_preset(device: dict, parent: QWidget) -> bool:
    """Show a save dialog and write the container device dict as JSON preset."""
    try:
        import json as _json
        from PyQt6.QtWidgets import QFileDialog
        d = _container_presets_dir()
        name = str(device.get("name") or device.get("plugin_id") or "container")
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "preset"
        path, _ = QFileDialog.getSaveFileName(
            parent, "Container-Preset speichern", str(d / f"{safe_name}.json"),
            "JSON Preset (*.json);;Alle Dateien (*)"
        )
        if not path:
            return False
        # Deep copy to avoid modifying the live device
        import copy
        preset = copy.deepcopy(device)
        # Remove runtime-only keys
        for k in ("_compiled", "_rt_handle"):
            preset.pop(k, None)
        Path(path).write_text(_json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _load_container_preset(parent: QWidget) -> Optional[dict]:
    """Show a load dialog and return the container device dict from a JSON preset."""
    try:
        import json as _json
        from PyQt6.QtWidgets import QFileDialog
        d = _container_presets_dir()
        path, _ = QFileDialog.getOpenFileName(
            parent, "Container-Preset laden", str(d),
            "JSON Preset (*.json);;Alle Dateien (*)"
        )
        if not path:
            return None
        data = _json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None
