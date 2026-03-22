from __future__ import annotations

import json
import math
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QMessageBox,
    QStackedWidget,
)

from pydaw.model.project import new_id
from pydaw.utils.logging_setup import get_logger

log = get_logger(__name__)


def _clamp_f(x: float, lo: float, hi: float) -> float:
    try:
        x = float(x)
    except Exception:
        x = lo
    return max(lo, min(hi, x))


def _clamp_i(x: int, lo: int, hi: int) -> int:
    try:
        x = int(x)
    except Exception:
        x = lo
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------------------
# Audio FX Chain Editor
# --------------------------------------------------------------------------------------


class AudioFxChainEditor(QWidget):
    """MVP editor for Track.audio_fx_chain.

    - Always show CHAIN container (Mix + Wet Gain)
    - Add/Remove/Reorder/Enable Gain devices
    - Per-device Gain parameter UI (dB)
    - Preset save/load
    - Calls AudioEngine.rebuild_fx_maps() after structural changes
    """

    def __init__(
        self,
        project_service: Any,
        audio_engine: Any,
        *,
        show_track_label: bool = True,
        show_presets: bool = True,
        compact: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_service = project_service
        self.audio_engine = audio_engine
        self._track_id: str = ""
        self._show_track_label = bool(show_track_label)
        self._show_presets = bool(show_presets)
        self._compact = bool(compact)
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        if self._show_track_label:
            self.lbl_track = QLabel("Track: —")
            self.lbl_track.setStyleSheet("color: #bbb;")
            root.addWidget(self.lbl_track)

        # CHAIN controls
        gb_chain = QGroupBox("CHAIN (Audio-FX)")
        vb = QVBoxLayout(gb_chain)
        vb.setContentsMargins(8, 10, 8, 8)
        vb.setSpacing(6)

        row_mix = QHBoxLayout()
        row_mix.addWidget(QLabel("Mix"))
        self.sld_mix = QSlider(Qt.Orientation.Horizontal)
        self.sld_mix.setRange(0, 100)
        self.spn_mix = QDoubleSpinBox()
        self.spn_mix.setRange(0.0, 1.0)
        self.spn_mix.setSingleStep(0.01)
        self.spn_mix.setDecimals(2)
        self.spn_mix.setMaximumWidth(90)
        row_mix.addWidget(self.sld_mix, 1)
        row_mix.addWidget(self.spn_mix)
        vb.addLayout(row_mix)

        row_wg = QHBoxLayout()
        row_wg.addWidget(QLabel("Wet Gain"))
        self.sld_wet = QSlider(Qt.Orientation.Horizontal)
        self.sld_wet.setRange(0, 200)
        self.spn_wet = QDoubleSpinBox()
        self.spn_wet.setRange(0.0, 2.0)
        self.spn_wet.setSingleStep(0.01)
        self.spn_wet.setDecimals(2)
        self.spn_wet.setMaximumWidth(90)
        row_wg.addWidget(self.sld_wet, 1)
        row_wg.addWidget(self.spn_wet)
        vb.addLayout(row_wg)

        root.addWidget(gb_chain)

        # list
        self.list_devices = QListWidget()
        if self._compact:
            self.list_devices.setMaximumHeight(160)
        root.addWidget(self.list_devices, 1)

        # per-device params
        self.gb_params = QGroupBox("Device Params")
        vbp = QVBoxLayout(self.gb_params)
        vbp.setContentsMargins(8, 10, 8, 8)
        vbp.setSpacing(6)
        self.lbl_params = QLabel("Select a device to edit parameters.")
        self.lbl_params.setStyleSheet("color: #bbb;")
        vbp.addWidget(self.lbl_params)

        row_g = QHBoxLayout()
        row_g.addWidget(QLabel("Gain (dB)"))
        self.sld_gain_db = QSlider(Qt.Orientation.Horizontal)
        self.sld_gain_db.setRange(-600, 120)  # -60..+12 dB in 0.1
        self.spn_gain_db = QDoubleSpinBox()
        self.spn_gain_db.setRange(-60.0, 12.0)
        self.spn_gain_db.setSingleStep(0.1)
        self.spn_gain_db.setDecimals(1)
        self.spn_gain_db.setMaximumWidth(90)
        row_g.addWidget(self.sld_gain_db, 1)
        row_g.addWidget(self.spn_gain_db)
        vbp.addLayout(row_g)

        root.addWidget(self.gb_params)

        # actions
        row_btn = QHBoxLayout()
        self.btn_add_gain = QPushButton("+ Gain")
        self.btn_remove = QPushButton("Remove")
        self.btn_toggle = QPushButton("Enable/Disable")
        self.btn_up = QPushButton("Up")
        self.btn_down = QPushButton("Down")
        for b in (self.btn_add_gain, self.btn_remove, self.btn_toggle, self.btn_up, self.btn_down):
            b.setMinimumHeight(26)
        row_btn.addWidget(self.btn_add_gain)
        row_btn.addWidget(self.btn_remove)
        row_btn.addWidget(self.btn_toggle)
        row_btn.addWidget(self.btn_up)
        row_btn.addWidget(self.btn_down)
        row_btn.addStretch(1)
        root.addLayout(row_btn)

        if self._show_presets:
            row_p = QHBoxLayout()
            self.btn_save = QPushButton("Save Preset…")
            self.btn_load = QPushButton("Load Preset…")
            self.btn_save.setMinimumHeight(26)
            self.btn_load.setMinimumHeight(26)
            row_p.addWidget(self.btn_save)
            row_p.addWidget(self.btn_load)
            row_p.addStretch(1)
            root.addLayout(row_p)

        # wiring
        self.sld_mix.valueChanged.connect(self._on_mix_slider)
        self.spn_mix.valueChanged.connect(self._on_mix_spin)
        self.sld_wet.valueChanged.connect(self._on_wet_slider)
        self.spn_wet.valueChanged.connect(self._on_wet_spin)

        self.list_devices.itemSelectionChanged.connect(self._on_selection_changed)

        self.sld_gain_db.valueChanged.connect(self._on_gain_db_slider)
        self.spn_gain_db.valueChanged.connect(self._on_gain_db_spin)

        self.btn_add_gain.clicked.connect(self._on_add_gain)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_toggle.clicked.connect(self._on_toggle)
        self.btn_up.clicked.connect(self._on_up)
        self.btn_down.clicked.connect(self._on_down)

        if self._show_presets:
            self.btn_save.clicked.connect(self._on_save_preset)
            self.btn_load.clicked.connect(self._on_load_preset)

        try:
            self.project_service.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

        self._set_enabled(False)

    # ---------------- public

    def set_track(self, track_id: str) -> None:
        self._track_id = str(track_id or "")
        self._refresh()

    # ---------------- internals

    def _on_project_updated(self) -> None:
        if self._track_id:
            self._refresh()

    def _set_enabled(self, enabled: bool) -> None:
        self.sld_mix.setEnabled(enabled)
        self.spn_mix.setEnabled(enabled)
        self.sld_wet.setEnabled(enabled)
        self.spn_wet.setEnabled(enabled)
        self.list_devices.setEnabled(enabled)
        self.gb_params.setEnabled(enabled)
        self.btn_add_gain.setEnabled(enabled)
        if self._show_presets:
            self.btn_save.setEnabled(enabled)
            self.btn_load.setEnabled(enabled)
        self._update_buttons()
        self._update_dev_params_ui()

    def _get_track(self) -> Any:
        try:
            proj = self.project_service.ctx.project
            return proj.tracks_by_id().get(self._track_id)
        except Exception:
            return None

    def _ensure_chain(self, track: Any) -> dict:
        chain = getattr(track, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
            track.audio_fx_chain = chain
        chain.setdefault("type", "chain")
        chain.setdefault("mix", 1.0)
        chain.setdefault("wet_gain", 1.0)
        if not isinstance(chain.get("devices"), list):
            chain["devices"] = []
        return chain

    def _rt_key_mix(self) -> str:
        return f"afxchain:{self._track_id}:mix"

    def _rt_key_wet(self) -> str:
        return f"afxchain:{self._track_id}:wet_gain"

    def _rt_key_gain(self, dev_id: str) -> str:
        return f"afx:{self._track_id}:{dev_id}:gain"

    def _sync_rt_params(self, chain: dict) -> None:
        try:
            rt = getattr(self.audio_engine, "rt_params", None)
            if rt is None:
                return

            mix = float(chain.get("mix", 1.0) or 1.0)
            wet = float(chain.get("wet_gain", 1.0) or 1.0)

            if hasattr(rt, "ensure"):
                rt.ensure(self._rt_key_mix(), mix)
                rt.ensure(self._rt_key_wet(), wet)
            if hasattr(rt, "set_param"):
                rt.set_param(self._rt_key_mix(), mix)
                rt.set_param(self._rt_key_wet(), wet)

            for d in chain.get("devices", []) or []:
                if not isinstance(d, dict):
                    continue
                if str(d.get("plugin_id") or "") != "chrono.fx.gain":
                    continue
                did = str(d.get("id") or "")
                if not did:
                    continue
                params = d.get("params") if isinstance(d.get("params"), dict) else {}
                g = 1.0
                try:
                    if "gain_db" in params:
                        g = float(10.0 ** (float(params.get("gain_db", 0.0) or 0.0) / 20.0))
                    else:
                        g = float(params.get("gain", 1.0) or 1.0)
                except Exception:
                    g = 1.0

                if hasattr(rt, "ensure"):
                    rt.ensure(self._rt_key_gain(did), g)
                if hasattr(rt, "set_param"):
                    rt.set_param(self._rt_key_gain(did), g)
        except Exception:
            pass

    def _apply_structural_change(self) -> None:
        try:
            proj = self.project_service.ctx.project
        except Exception:
            proj = None

        try:
            if proj is not None:
                self.audio_engine.rebuild_fx_maps(proj)
        except Exception as e:
            log.warning("rebuild_fx_maps failed: %s", e)

        try:
            self.project_service.project_updated.emit()
        except Exception:
            pass

    def _refresh(self) -> None:
        t = self._get_track()
        if self._show_track_label:
            name = getattr(t, "name", "") if t is not None else ""
            self.lbl_track.setText(f"Track: {name or self._track_id or '—'}")

        if t is None or not self._track_id:
            self.list_devices.clear()
            self._set_enabled(False)
            return

        chain = self._ensure_chain(t)

        self._updating = True
        try:
            mix = _clamp_f(chain.get("mix", 1.0), 0.0, 1.0)
            wet = _clamp_f(chain.get("wet_gain", 1.0), 0.0, 2.0)

            self.sld_mix.setValue(int(round(mix * 100.0)))
            self.spn_mix.setValue(float(mix))
            self.sld_wet.setValue(int(round(wet * 100.0)))
            self.spn_wet.setValue(float(wet))

            self.list_devices.clear()
            it_chain = QListWidgetItem("CHAIN")
            it_chain.setData(Qt.ItemDataRole.UserRole, {"kind": "chain"})
            it_chain.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.list_devices.addItem(it_chain)

            for i, d in enumerate(chain.get("devices", []) or []):
                if not isinstance(d, dict):
                    continue
                pid = str(d.get("plugin_id") or d.get("type") or "")
                enabled = bool(d.get("enabled", True))
                name = d.get("name") or ("Gain" if pid == "chrono.fx.gain" else (pid or "Device"))
                suffix = "" if enabled else " (disabled)"
                it = QListWidgetItem(f"{name}{suffix}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": "device", "index": int(i)})
                self.list_devices.addItem(it)
        finally:
            self._updating = False

        self._sync_rt_params(chain)
        self._set_enabled(True)

    def _selected_device_index(self) -> Optional[int]:
        it = self.list_devices.currentItem()
        if it is None:
            return None
        meta = it.data(Qt.ItemDataRole.UserRole) or {}
        if meta.get("kind") != "device":
            return None
        try:
            return int(meta.get("index"))
        except Exception:
            return None

    def _update_buttons(self) -> None:
        enabled = bool(self._track_id)
        idx = self._selected_device_index()
        has_dev = idx is not None
        self.btn_remove.setEnabled(enabled and has_dev)
        self.btn_toggle.setEnabled(enabled and has_dev)
        self.btn_up.setEnabled(enabled and has_dev and idx is not None and idx > 0)

        n = 0
        try:
            t = self._get_track()
            if t is not None:
                chain = self._ensure_chain(t)
                n = len(chain.get("devices", []) or [])
        except Exception:
            n = 0
        self.btn_down.setEnabled(enabled and has_dev and idx is not None and idx < (n - 1))

    def _on_selection_changed(self) -> None:
        self._update_buttons()
        self._update_dev_params_ui()

    def _update_dev_params_ui(self) -> None:
        try:
            t = self._get_track()
            if t is None or not self._track_id:
                self.lbl_params.setText("Select a device to edit parameters.")
                self.sld_gain_db.setEnabled(False)
                self.spn_gain_db.setEnabled(False)
                return

            idx = self._selected_device_index()
            if idx is None:
                self.lbl_params.setText("Select a device to edit parameters.")
                self.sld_gain_db.setEnabled(False)
                self.spn_gain_db.setEnabled(False)
                return

            chain = self._ensure_chain(t)
            devs = chain.get("devices", []) or []
            if idx < 0 or idx >= len(devs):
                return

            d = devs[idx]
            pid = str(d.get("plugin_id") or d.get("type") or "")
            params = d.get("params") if isinstance(d.get("params"), dict) else {}

            if pid != "chrono.fx.gain":
                self.lbl_params.setText("No editable parameters for this device (MVP).")
                self.sld_gain_db.setEnabled(False)
                self.spn_gain_db.setEnabled(False)
                return

            gdb = 0.0
            try:
                if "gain_db" in params:
                    gdb = float(params.get("gain_db", 0.0) or 0.0)
                elif "gain" in params:
                    g = float(params.get("gain", 1.0) or 1.0)
                    gdb = float(20.0 * math.log10(max(1e-9, g)))
            except Exception:
                gdb = 0.0

            gdb = float(_clamp_f(gdb, -60.0, 12.0))

            self._updating = True
            try:
                self.lbl_params.setText("Gain: per-device post-instrument gain (dB).")
                self.sld_gain_db.setEnabled(True)
                self.spn_gain_db.setEnabled(True)
                self.sld_gain_db.setValue(int(round(gdb * 10.0)))
                self.spn_gain_db.setValue(float(gdb))
            finally:
                self._updating = False
        except Exception:
            pass

    # ---- chain param handlers

    def _on_mix_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_mix.setValue(float(v) / 100.0)
        finally:
            self._updating = False

    def _on_mix_spin(self, v: float) -> None:
        if self._updating:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        v = _clamp_f(v, 0.0, 1.0)
        chain["mix"] = float(v)
        self._sync_rt_params(chain)

    def _on_wet_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_wet.setValue(float(v) / 100.0)
        finally:
            self._updating = False

    def _on_wet_spin(self, v: float) -> None:
        if self._updating:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        v = _clamp_f(v, 0.0, 2.0)
        chain["wet_gain"] = float(v)
        self._sync_rt_params(chain)

    # ---- per-device gain handlers

    def _on_gain_db_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_gain_db.setValue(float(v) / 10.0)
        finally:
            self._updating = False

    def _on_gain_db_spin(self, v: float) -> None:
        if self._updating:
            return
        t = self._get_track()
        if t is None:
            return
        idx = self._selected_device_index()
        if idx is None:
            return
        chain = self._ensure_chain(t)
        devs = chain.get("devices", []) or []
        if idx < 0 or idx >= len(devs):
            return
        d = devs[idx]
        if str(d.get("plugin_id") or "") != "chrono.fx.gain":
            return

        v = float(_clamp_f(v, -60.0, 12.0))
        params = d.get("params")
        if not isinstance(params, dict):
            params = {}
            d["params"] = params
        params["gain_db"] = float(v)
        params["gain"] = float(10.0 ** (float(v) / 20.0))

        self._updating = True
        try:
            self.sld_gain_db.setValue(int(round(v * 10.0)))
        finally:
            self._updating = False

        self._sync_rt_params(chain)

    # ---- structural handlers

    def _on_add_gain(self) -> None:
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        dev_id = new_id("afx")
        chain["devices"].append(
            {
                "id": dev_id,
                "plugin_id": "chrono.fx.gain",
                "name": "Gain",
                "enabled": True,
                "params": {"gain_db": 0.0, "gain": 1.0},
            }
        )
        self._sync_rt_params(chain)
        self._apply_structural_change()
        self._refresh()

    def _on_remove(self) -> None:
        idx = self._selected_device_index()
        if idx is None:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        try:
            chain["devices"].pop(int(idx))
        except Exception:
            return
        self._apply_structural_change()
        self._refresh()

    def _on_toggle(self) -> None:
        idx = self._selected_device_index()
        if idx is None:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        try:
            d = chain["devices"][int(idx)]
            d["enabled"] = not bool(d.get("enabled", True))
        except Exception:
            return
        self._apply_structural_change()
        self._refresh()

    def _on_up(self) -> None:
        idx = self._selected_device_index()
        if idx is None or idx <= 0:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        devs = chain.get("devices", [])
        try:
            devs[idx - 1], devs[idx] = devs[idx], devs[idx - 1]
        except Exception:
            return
        self._apply_structural_change()
        self._refresh()
        try:
            self.list_devices.setCurrentRow(int(idx))  # +1 for CHAIN entry
        except Exception:
            pass

    def _on_down(self) -> None:
        idx = self._selected_device_index()
        if idx is None:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        devs = chain.get("devices", [])
        if idx >= len(devs) - 1:
            return
        devs[idx + 1], devs[idx] = devs[idx], devs[idx + 1]
        self._apply_structural_change()
        self._refresh()
        try:
            self.list_devices.setCurrentRow(int(idx) + 2)  # +1 for CHAIN, +1 moved down
        except Exception:
            pass

    # ---- presets

    def _on_save_preset(self) -> None:
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        path, _ = QFileDialog.getSaveFileName(self, "Save Audio-FX Preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(chain, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save Preset", f"Failed to save preset:\n{e}")

    def _on_load_preset(self) -> None:
        t = self._get_track()
        if t is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Audio-FX Preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "devices" not in data:
                raise ValueError("Invalid preset format")
            t.audio_fx_chain = data
            # sync + rebuild
            chain = self._ensure_chain(t)
            self._sync_rt_params(chain)
            self._apply_structural_change()
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Load Preset", f"Failed to load preset:\n{e}")


# --------------------------------------------------------------------------------------
# Note FX Chain Editor (GO: Parameter UI)
# --------------------------------------------------------------------------------------


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_SCALE_NAMES = [
    "major",
    "minor",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "locrian",
    "pentatonic",
    "chromatic",
]

_SCALE_MODES = ["nearest", "up", "down"]

_CHORD_TYPES = ["maj", "min", "power", "maj7", "min7", "dim", "aug"]

_ARP_MODES = ["up", "down", "updown", "random"]


class NoteFxChainEditor(QWidget):
    """Editor for Track.note_fx_chain (MIDI Note-FX before the instrument).

    Devices:
    - Transpose
    - VelScale
    - ScaleSnap
    - Chord
    - Arp
    - Random

    Supports:
    - Add/Remove/Reorder
    - Enable/Disable
    - Presets save/load (JSON)

    Parameter UI: full MVP for all devices (GO Note-FX Parameter UI).
    """

    def __init__(
        self,
        project_service: Any,
        audio_engine: Any = None,
        transport: Any = None,
        *,
        show_track_label: bool = True,
        show_presets: bool = True,
        compact: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_service = project_service
        self.audio_engine = audio_engine
        self.transport = transport
        self._track_id: str = ""
        self._show_track_label = bool(show_track_label)
        self._show_presets = bool(show_presets)
        self._compact = bool(compact)
        self._updating = False

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_playback_if_playing)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        if self._show_track_label:
            self.lbl_track = QLabel("Track: —")
            self.lbl_track.setStyleSheet("color: #bbb;")
            root.addWidget(self.lbl_track)

        gb = QGroupBox("CHAIN (Note-FX)")
        v = QVBoxLayout(gb)
        v.setContentsMargins(8, 10, 8, 8)
        v.setSpacing(6)
        txt = QLabel("Note-FX are processed BEFORE the instrument (MIDI stage).")
        txt.setStyleSheet("color: #bbb;")
        v.addWidget(txt)
        root.addWidget(gb)

        self.list_devices = QListWidget()
        if self._compact:
            self.list_devices.setMaximumHeight(160)
        root.addWidget(self.list_devices, 1)

        # actions
        row1 = QHBoxLayout()
        self.btn_add_transpose = QPushButton("+ Transpose")
        self.btn_add_vel = QPushButton("+ VelScale")
        self.btn_add_scale = QPushButton("+ ScaleSnap")
        self.btn_add_chord = QPushButton("+ Chord")
        self.btn_remove = QPushButton("Remove")
        self.btn_toggle = QPushButton("Enable/Disable")
        for b in (
            self.btn_add_transpose,
            self.btn_add_vel,
            self.btn_add_scale,
            self.btn_add_chord,
            self.btn_remove,
            self.btn_toggle,
        ):
            b.setMinimumHeight(26)
        row1.addWidget(self.btn_add_transpose)
        row1.addWidget(self.btn_add_vel)
        row1.addWidget(self.btn_add_scale)
        row1.addWidget(self.btn_add_chord)
        row1.addWidget(self.btn_remove)
        row1.addWidget(self.btn_toggle)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_add_arp = QPushButton("+ Arp")
        self.btn_add_random = QPushButton("+ Random")
        self.btn_up = QPushButton("Up")
        self.btn_down = QPushButton("Down")
        for b in (self.btn_add_arp, self.btn_add_random, self.btn_up, self.btn_down):
            b.setMinimumHeight(26)
        row2.addWidget(self.btn_add_arp)
        row2.addWidget(self.btn_add_random)
        row2.addWidget(self.btn_up)
        row2.addWidget(self.btn_down)
        row2.addStretch(1)
        root.addLayout(row2)

        if self._show_presets:
            rowp = QHBoxLayout()
            self.btn_save = QPushButton("Save Preset…")
            self.btn_load = QPushButton("Load Preset…")
            self.btn_save.setMinimumHeight(26)
            self.btn_load.setMinimumHeight(26)
            rowp.addWidget(self.btn_save)
            rowp.addWidget(self.btn_load)
            rowp.addStretch(1)
            root.addLayout(rowp)

        # params
        self.gb_params = QGroupBox("Device Params")
        vp = QVBoxLayout(self.gb_params)
        vp.setContentsMargins(8, 10, 8, 8)
        vp.setSpacing(6)

        self.lbl_params = QLabel("Select a device to edit parameters.")
        self.lbl_params.setStyleSheet("color: #bbb;")
        vp.addWidget(self.lbl_params)

        self.stack = QStackedWidget()
        vp.addWidget(self.stack)

        self._page_none = QWidget()
        lnone = QVBoxLayout(self._page_none)
        lnone.addWidget(QLabel("—"))
        lnone.addStretch(1)
        self.stack.addWidget(self._page_none)

        # Transpose page
        self._page_transpose = QWidget()
        lt = QVBoxLayout(self._page_transpose)
        row = QHBoxLayout()
        row.addWidget(QLabel("Semitones"))
        self.sld_semi = QSlider(Qt.Orientation.Horizontal)
        self.sld_semi.setRange(-24, 24)
        self.spn_semi = QSpinBox()
        self.spn_semi.setRange(-24, 24)
        self.spn_semi.setSingleStep(1)
        self.spn_semi.setMaximumWidth(90)
        row.addWidget(self.sld_semi, 1)
        row.addWidget(self.spn_semi)
        lt.addLayout(row)
        lt.addStretch(1)
        self.stack.addWidget(self._page_transpose)

        # VelScale page
        self._page_vel = QWidget()
        lv = QVBoxLayout(self._page_vel)
        row = QHBoxLayout()
        row.addWidget(QLabel("Velocity Scale"))
        self.sld_vel = QSlider(Qt.Orientation.Horizontal)
        self.sld_vel.setRange(0, 200)
        self.spn_vel = QDoubleSpinBox()
        self.spn_vel.setRange(0.0, 2.0)
        self.spn_vel.setSingleStep(0.01)
        self.spn_vel.setDecimals(2)
        self.spn_vel.setMaximumWidth(90)
        row.addWidget(self.sld_vel, 1)
        row.addWidget(self.spn_vel)
        lv.addLayout(row)
        lv.addStretch(1)
        self.stack.addWidget(self._page_vel)

        # ScaleSnap page
        self._page_scale = QWidget()
        ls = QVBoxLayout(self._page_scale)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Root"))
        self.cmb_root = QComboBox()
        for i, name in enumerate(_NOTE_NAMES):
            self.cmb_root.addItem(name, i)
        self.cmb_root.setMaximumWidth(120)
        r1.addWidget(self.cmb_root)
        r1.addStretch(1)
        ls.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Scale"))
        self.cmb_scale = QComboBox()
        for sname in _SCALE_NAMES:
            self.cmb_scale.addItem(sname, sname)
        self.cmb_scale.setMaximumWidth(180)
        r2.addWidget(self.cmb_scale)
        r2.addStretch(1)
        ls.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Mode"))
        self.cmb_scale_mode = QComboBox()
        for m in _SCALE_MODES:
            self.cmb_scale_mode.addItem(m, m)
        self.cmb_scale_mode.setMaximumWidth(180)
        r3.addWidget(self.cmb_scale_mode)
        r3.addStretch(1)
        ls.addLayout(r3)
        ls.addStretch(1)
        self.stack.addWidget(self._page_scale)

        # Chord page
        self._page_chord = QWidget()
        lc = QVBoxLayout(self._page_chord)
        r = QHBoxLayout()
        r.addWidget(QLabel("Chord"))
        self.cmb_chord = QComboBox()
        for c in _CHORD_TYPES:
            self.cmb_chord.addItem(c, c)
        self.cmb_chord.setMaximumWidth(180)
        r.addWidget(self.cmb_chord)
        r.addStretch(1)
        lc.addLayout(r)
        lc.addStretch(1)
        self.stack.addWidget(self._page_chord)

        # Arp page
        self._page_arp = QWidget()
        la = QVBoxLayout(self._page_arp)

        r = QHBoxLayout()
        r.addWidget(QLabel("Step (beats)"))
        self.spn_arp_step = QDoubleSpinBox()
        self.spn_arp_step.setRange(0.0625, 4.0)
        self.spn_arp_step.setSingleStep(0.0625)
        self.spn_arp_step.setDecimals(4)
        self.spn_arp_step.setMaximumWidth(120)
        r.addWidget(self.spn_arp_step)
        r.addStretch(1)
        la.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Mode"))
        self.cmb_arp_mode = QComboBox()
        for m in _ARP_MODES:
            self.cmb_arp_mode.addItem(m, m)
        self.cmb_arp_mode.setMaximumWidth(180)
        r.addWidget(self.cmb_arp_mode)
        r.addStretch(1)
        la.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Octaves"))
        self.spn_arp_oct = QSpinBox()
        self.spn_arp_oct.setRange(1, 4)
        self.spn_arp_oct.setSingleStep(1)
        self.spn_arp_oct.setMaximumWidth(120)
        r.addWidget(self.spn_arp_oct)
        r.addStretch(1)
        la.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Gate"))
        self.spn_arp_gate = QDoubleSpinBox()
        self.spn_arp_gate.setRange(0.1, 1.0)
        self.spn_arp_gate.setSingleStep(0.01)
        self.spn_arp_gate.setDecimals(2)
        self.spn_arp_gate.setMaximumWidth(120)
        r.addWidget(self.spn_arp_gate)
        r.addStretch(1)
        la.addLayout(r)

        la.addStretch(1)
        self.stack.addWidget(self._page_arp)

        # Random page
        self._page_random = QWidget()
        lr = QVBoxLayout(self._page_random)

        r = QHBoxLayout()
        r.addWidget(QLabel("Pitch Range (±semitones)"))
        self.sld_r_pitch = QSlider(Qt.Orientation.Horizontal)
        self.sld_r_pitch.setRange(0, 24)
        self.spn_r_pitch = QSpinBox()
        self.spn_r_pitch.setRange(0, 24)
        self.spn_r_pitch.setMaximumWidth(90)
        r.addWidget(self.sld_r_pitch, 1)
        r.addWidget(self.spn_r_pitch)
        lr.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Vel Range (±)"))
        self.sld_r_vel = QSlider(Qt.Orientation.Horizontal)
        self.sld_r_vel.setRange(0, 127)
        self.spn_r_vel = QSpinBox()
        self.spn_r_vel.setRange(0, 127)
        self.spn_r_vel.setMaximumWidth(90)
        r.addWidget(self.sld_r_vel, 1)
        r.addWidget(self.spn_r_vel)
        lr.addLayout(r)

        r = QHBoxLayout()
        r.addWidget(QLabel("Probability"))
        self.sld_r_prob = QSlider(Qt.Orientation.Horizontal)
        self.sld_r_prob.setRange(0, 100)
        self.spn_r_prob = QDoubleSpinBox()
        self.spn_r_prob.setRange(0.0, 1.0)
        self.spn_r_prob.setSingleStep(0.01)
        self.spn_r_prob.setDecimals(2)
        self.spn_r_prob.setMaximumWidth(90)
        r.addWidget(self.sld_r_prob, 1)
        r.addWidget(self.spn_r_prob)
        lr.addLayout(r)

        lr.addStretch(1)
        self.stack.addWidget(self._page_random)

        root.addWidget(self.gb_params)

        # wiring
        self.list_devices.itemSelectionChanged.connect(self._on_selection_changed)

        self.btn_add_transpose.clicked.connect(self._add_transpose)
        self.btn_add_vel.clicked.connect(self._add_vel)
        self.btn_add_scale.clicked.connect(self._add_scale)
        self.btn_add_chord.clicked.connect(self._add_chord)
        self.btn_add_arp.clicked.connect(self._add_arp)
        self.btn_add_random.clicked.connect(self._add_random)

        self.btn_remove.clicked.connect(self._remove)
        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_up.clicked.connect(self._up)
        self.btn_down.clicked.connect(self._down)

        if self._show_presets:
            self.btn_save.clicked.connect(self._save_preset)
            self.btn_load.clicked.connect(self._load_preset)

        # param signals
        self.sld_semi.valueChanged.connect(self._on_semi_slider)
        self.spn_semi.valueChanged.connect(self._on_semi_spin)

        self.sld_vel.valueChanged.connect(self._on_vel_slider)
        self.spn_vel.valueChanged.connect(self._on_vel_spin)

        self.cmb_root.currentIndexChanged.connect(self._on_scale_changed)
        self.cmb_scale.currentIndexChanged.connect(self._on_scale_changed)
        self.cmb_scale_mode.currentIndexChanged.connect(self._on_scale_changed)

        self.cmb_chord.currentIndexChanged.connect(self._on_chord_changed)

        self.spn_arp_step.valueChanged.connect(self._on_arp_changed)
        self.cmb_arp_mode.currentIndexChanged.connect(self._on_arp_changed)
        self.spn_arp_oct.valueChanged.connect(self._on_arp_changed)
        self.spn_arp_gate.valueChanged.connect(self._on_arp_changed)

        self.sld_r_pitch.valueChanged.connect(self._on_random_pitch_slider)
        self.spn_r_pitch.valueChanged.connect(self._on_random_pitch_spin)
        self.sld_r_vel.valueChanged.connect(self._on_random_vel_slider)
        self.spn_r_vel.valueChanged.connect(self._on_random_vel_spin)
        self.sld_r_prob.valueChanged.connect(self._on_random_prob_slider)
        self.spn_r_prob.valueChanged.connect(self._on_random_prob_spin)

        try:
            self.project_service.project_updated.connect(self._on_project_updated)
        except Exception:
            pass

        self._set_enabled(False)

    # ---- public

    def set_track(self, track_id: str) -> None:
        self._track_id = str(track_id or "")
        self._refresh()

    # ---- internals

    def _on_project_updated(self) -> None:
        if self._track_id:
            self._refresh()

    def _set_enabled(self, enabled: bool) -> None:
        self.list_devices.setEnabled(enabled)
        for b in (
            self.btn_add_transpose,
            self.btn_add_vel,
            self.btn_add_scale,
            self.btn_add_chord,
            self.btn_add_arp,
            self.btn_add_random,
        ):
            b.setEnabled(enabled)
        self.gb_params.setEnabled(enabled)
        if self._show_presets:
            self.btn_save.setEnabled(enabled)
            self.btn_load.setEnabled(enabled)
        self._update_buttons()
        self._update_params_ui()

    def _get_track(self) -> Any:
        try:
            proj = self.project_service.ctx.project
            return proj.tracks_by_id().get(self._track_id)
        except Exception:
            return None

    def _ensure_chain(self, track: Any) -> dict:
        chain = getattr(track, "note_fx_chain", None)
        if not isinstance(chain, dict):
            chain = {"type": "chain", "devices": []}
            track.note_fx_chain = chain
        chain.setdefault("type", "chain")
        if not isinstance(chain.get("devices"), list):
            chain["devices"] = []
        return chain

    def _emit_update(self) -> None:
        try:
            self.project_service.project_updated.emit()
        except Exception:
            pass

    def _schedule_restart(self) -> None:
        try:
            playing = False
            if self.transport is not None:
                playing = bool(getattr(self.transport, "is_playing", False) or getattr(self.transport, "playing", False))
            if playing and self.audio_engine is not None:
                self._restart_timer.start(200)
        except Exception:
            pass

    def _restart_playback_if_playing(self) -> None:
        try:
            if self.transport is None or self.audio_engine is None:
                return
            playing = bool(getattr(self.transport, "is_playing", False) or getattr(self.transport, "playing", False))
            if not playing:
                return
            try:
                self.audio_engine.stop()
            except Exception:
                pass
            try:
                self.audio_engine.start_arrangement_playback()
            except Exception:
                pass
        except Exception:
            pass

    def _refresh(self) -> None:
        t = self._get_track()
        if self._show_track_label:
            name = getattr(t, "name", "") if t is not None else ""
            self.lbl_track.setText(f"Track: {name or self._track_id or '—'}")

        if t is None or not self._track_id:
            self.list_devices.clear()
            self._set_enabled(False)
            return

        chain = self._ensure_chain(t)

        self._updating = True
        try:
            self.list_devices.clear()
            it_chain = QListWidgetItem("CHAIN")
            it_chain.setData(Qt.ItemDataRole.UserRole, {"kind": "chain"})
            it_chain.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.list_devices.addItem(it_chain)

            for i, d in enumerate(chain.get("devices", []) or []):
                if not isinstance(d, dict):
                    continue
                pid = str(d.get("plugin_id") or d.get("type") or "")
                enabled = bool(d.get("enabled", True))
                name = {
                    "chrono.note_fx.transpose": "Transpose",
                    "chrono.note_fx.velocity_scale": "VelScale",
                    "chrono.note_fx.scale_snap": "ScaleSnap",
                    "chrono.note_fx.chord": "Chord",
                    "chrono.note_fx.arp": "Arp",
                    "chrono.note_fx.random": "Random",
                }.get(pid, pid or "Device")
                suffix = "" if enabled else " (disabled)"
                it = QListWidgetItem(f"{name}{suffix}")
                it.setData(Qt.ItemDataRole.UserRole, {"kind": "device", "index": int(i)})
                self.list_devices.addItem(it)
        finally:
            self._updating = False

        self._set_enabled(True)

    def _sel_idx(self) -> Optional[int]:
        it = self.list_devices.currentItem()
        if it is None:
            return None
        data = it.data(Qt.ItemDataRole.UserRole) or {}
        if data.get("kind") != "device":
            return None
        try:
            return int(data.get("index"))
        except Exception:
            return None

    def _update_buttons(self) -> None:
        enabled = bool(self._track_id)
        idx = self._sel_idx()
        has = idx is not None
        self.btn_remove.setEnabled(enabled and has)
        self.btn_toggle.setEnabled(enabled and has)
        self.btn_up.setEnabled(enabled and has and idx is not None and idx > 0)
        n = 0
        try:
            t = self._get_track()
            if t is not None:
                n = len(self._ensure_chain(t).get("devices", []) or [])
        except Exception:
            n = 0
        self.btn_down.setEnabled(enabled and has and idx is not None and idx < (n - 1))

    def _on_selection_changed(self) -> None:
        self._update_buttons()
        self._update_params_ui()

    def _current_device(self) -> Optional[dict]:
        idx = self._sel_idx()
        if idx is None:
            return None
        t = self._get_track()
        if t is None:
            return None
        chain = self._ensure_chain(t)
        devs = chain.get("devices", []) or []
        if idx < 0 or idx >= len(devs):
            return None
        d = devs[idx]
        if not isinstance(d, dict):
            return None
        return d

    def _update_params_ui(self) -> None:
        d = self._current_device()
        if d is None:
            self.lbl_params.setText("Select a device to edit parameters.")
            self.stack.setCurrentIndex(0)
            return

        pid = str(d.get("plugin_id") or d.get("type") or "")
        params = d.get("params") if isinstance(d.get("params"), dict) else {}

        self._updating = True
        try:
            if pid == "chrono.note_fx.transpose":
                self.lbl_params.setText("Transpose: shifts pitches before the instrument.")
                semi = _clamp_i(params.get("semitones", 0), -24, 24)
                self.sld_semi.setValue(int(semi))
                self.spn_semi.setValue(int(semi))
                self.stack.setCurrentWidget(self._page_transpose)

            elif pid == "chrono.note_fx.velocity_scale":
                self.lbl_params.setText("VelScale: scales note velocity before the instrument.")
                sc = _clamp_f(params.get("scale", 1.0), 0.0, 2.0)
                self.sld_vel.setValue(int(round(sc * 100.0)))
                self.spn_vel.setValue(float(sc))
                self.stack.setCurrentWidget(self._page_vel)

            elif pid == "chrono.note_fx.scale_snap":
                self.lbl_params.setText("ScaleSnap: snaps pitches to a musical scale.")
                root = _clamp_i(params.get("root", 0), 0, 11)
                scale = str(params.get("scale", "major") or "major")
                mode = str(params.get("mode", "nearest") or "nearest")
                self._set_combo_data(self.cmb_root, root)
                self._set_combo_data(self.cmb_scale, scale)
                self._set_combo_data(self.cmb_scale_mode, mode)
                self.stack.setCurrentWidget(self._page_scale)

            elif pid == "chrono.note_fx.chord":
                self.lbl_params.setText("Chord: expands one note into a chord.")
                chord = str(params.get("chord", "maj") or "maj")
                if chord not in _CHORD_TYPES:
                    chord = "maj"
                self._set_combo_data(self.cmb_chord, chord)
                self.stack.setCurrentWidget(self._page_chord)

            elif pid == "chrono.note_fx.arp":
                self.lbl_params.setText("Arp: generates an arpeggio pattern (grouped by note start).")
                step = _clamp_f(params.get("step_beats", 0.5), 0.0625, 4.0)
                mode = str(params.get("mode", "up") or "up")
                octv = _clamp_i(params.get("octaves", 1), 1, 4)
                gate = _clamp_f(params.get("gate", 0.9), 0.1, 1.0)
                self.spn_arp_step.setValue(float(step))
                self._set_combo_data(self.cmb_arp_mode, mode if mode in _ARP_MODES else "up")
                self.spn_arp_oct.setValue(int(octv))
                self.spn_arp_gate.setValue(float(gate))
                self.stack.setCurrentWidget(self._page_arp)

            elif pid == "chrono.note_fx.random":
                self.lbl_params.setText("Random: randomizes pitch/velocity deterministically per note.")
                pr = _clamp_i(params.get("pitch_range", 0), 0, 24)
                vr = _clamp_i(params.get("vel_range", 0), 0, 127)
                prob = _clamp_f(params.get("prob", 1.0), 0.0, 1.0)
                self.sld_r_pitch.setValue(int(pr))
                self.spn_r_pitch.setValue(int(pr))
                self.sld_r_vel.setValue(int(vr))
                self.spn_r_vel.setValue(int(vr))
                self.sld_r_prob.setValue(int(round(prob * 100.0)))
                self.spn_r_prob.setValue(float(prob))
                self.stack.setCurrentWidget(self._page_random)

            else:
                self.lbl_params.setText("No editable parameters for this device.")
                self.stack.setCurrentIndex(0)
        finally:
            self._updating = False

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: Any) -> None:
        # selects item by userData, falls back to text
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == value:
                    combo.setCurrentIndex(i)
                    return
            # fallback: match string
            sval = str(value)
            for i in range(combo.count()):
                if str(combo.itemText(i)) == sval:
                    combo.setCurrentIndex(i)
                    return
        except Exception:
            pass

    # ---- add/remove/reorder

    def _add_transpose(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {"id": new_id("nfx"), "plugin_id": "chrono.note_fx.transpose", "name": "Transpose", "enabled": True, "params": {"semitones": 0}}
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _add_vel(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {"id": new_id("nfx"), "plugin_id": "chrono.note_fx.velocity_scale", "name": "VelScale", "enabled": True, "params": {"scale": 1.0}}
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _add_scale(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {"id": new_id("nfx"), "plugin_id": "chrono.note_fx.scale_snap", "name": "ScaleSnap", "enabled": True, "params": {"root": 0, "scale": "major", "mode": "nearest"}}
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _add_chord(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {"id": new_id("nfx"), "plugin_id": "chrono.note_fx.chord", "name": "Chord", "enabled": True, "params": {"chord": "maj"}}
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _add_arp(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {
                "id": new_id("nfx"),
                "plugin_id": "chrono.note_fx.arp",
                "name": "Arp",
                "enabled": True,
                "params": {"step_beats": 0.5, "mode": "up", "octaves": 1, "gate": 0.9},
            }
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _add_random(self) -> None:
        t = self._get_track()
        if t is None:
            return
        self._ensure_chain(t)["devices"].append(
            {
                "id": new_id("nfx"),
                "plugin_id": "chrono.note_fx.random",
                "name": "Random",
                "enabled": True,
                "params": {"pitch_range": 0, "vel_range": 0, "prob": 1.0},
            }
        )
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _remove(self) -> None:
        idx = self._sel_idx()
        if idx is None:
            return
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        try:
            chain["devices"].pop(int(idx))
        except Exception:
            return
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _toggle(self) -> None:
        d = self._current_device()
        if d is None:
            return
        d["enabled"] = not bool(d.get("enabled", True))
        self._emit_update()
        self._schedule_restart()
        self._refresh()

    def _up(self) -> None:
        idx = self._sel_idx()
        if idx is None or idx <= 0:
            return
        t = self._get_track()
        if t is None:
            return
        devs = self._ensure_chain(t).get("devices", [])
        try:
            devs[idx - 1], devs[idx] = devs[idx], devs[idx - 1]
        except Exception:
            return
        self._emit_update()
        self._schedule_restart()
        self._refresh()
        try:
            self.list_devices.setCurrentRow(int(idx))
        except Exception:
            pass

    def _down(self) -> None:
        idx = self._sel_idx()
        if idx is None:
            return
        t = self._get_track()
        if t is None:
            return
        devs = self._ensure_chain(t).get("devices", [])
        if idx >= len(devs) - 1:
            return
        devs[idx + 1], devs[idx] = devs[idx], devs[idx + 1]
        self._emit_update()
        self._schedule_restart()
        self._refresh()
        try:
            self.list_devices.setCurrentRow(int(idx) + 2)
        except Exception:
            pass

    # ---- params handlers

    def _set_param(self, key: str, value: Any) -> None:
        d = self._current_device()
        if d is None:
            return
        params = d.get("params")
        if not isinstance(params, dict):
            params = {}
            d["params"] = params
        params[key] = value
        self._emit_update()
        self._schedule_restart()

    def _on_semi_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_semi.setValue(int(v))
        finally:
            self._updating = False

    def _on_semi_spin(self, v: int) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.transpose":
            return
        semi = _clamp_i(v, -24, 24)
        self._set_param("semitones", int(semi))
        self._update_params_ui()

    def _on_vel_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_vel.setValue(float(v) / 100.0)
        finally:
            self._updating = False

    def _on_vel_spin(self, v: float) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.velocity_scale":
            return
        sc = float(_clamp_f(v, 0.0, 2.0))
        self._set_param("scale", float(sc))
        self._update_params_ui()

    def _on_scale_changed(self) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.scale_snap":
            return
        root = int(self.cmb_root.currentData())
        scale = str(self.cmb_scale.currentData() or "major")
        mode = str(self.cmb_scale_mode.currentData() or "nearest")
        params = d.get("params")
        if not isinstance(params, dict):
            params = {}
            d["params"] = params
        params["root"] = _clamp_i(root, 0, 11)
        params["scale"] = scale if scale in _SCALE_NAMES else "major"
        params["mode"] = mode if mode in _SCALE_MODES else "nearest"
        self._emit_update()
        self._schedule_restart()

    def _on_chord_changed(self) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.chord":
            return
        chord = str(self.cmb_chord.currentData() or "maj")
        if chord not in _CHORD_TYPES:
            chord = "maj"
        self._set_param("chord", chord)

    def _on_arp_changed(self) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.arp":
            return
        step = float(_clamp_f(self.spn_arp_step.value(), 0.0625, 4.0))
        mode = str(self.cmb_arp_mode.currentData() or "up")
        octv = int(_clamp_i(self.spn_arp_oct.value(), 1, 4))
        gate = float(_clamp_f(self.spn_arp_gate.value(), 0.1, 1.0))
        params = d.get("params")
        if not isinstance(params, dict):
            params = {}
            d["params"] = params
        params["step_beats"] = float(step)
        params["mode"] = mode if mode in _ARP_MODES else "up"
        params["octaves"] = int(octv)
        params["gate"] = float(gate)
        self._emit_update()
        self._schedule_restart()

    def _on_random_pitch_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_r_pitch.setValue(int(v))
        finally:
            self._updating = False

    def _on_random_pitch_spin(self, v: int) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.random":
            return
        pr = int(_clamp_i(v, 0, 24))
        self._updating = True
        try:
            self.sld_r_pitch.setValue(int(pr))
        finally:
            self._updating = False
        self._set_param("pitch_range", int(pr))

    def _on_random_vel_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_r_vel.setValue(int(v))
        finally:
            self._updating = False

    def _on_random_vel_spin(self, v: int) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.random":
            return
        vr = int(_clamp_i(v, 0, 127))
        self._updating = True
        try:
            self.sld_r_vel.setValue(int(vr))
        finally:
            self._updating = False
        self._set_param("vel_range", int(vr))

    def _on_random_prob_slider(self, v: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.spn_r_prob.setValue(float(v) / 100.0)
        finally:
            self._updating = False

    def _on_random_prob_spin(self, v: float) -> None:
        if self._updating:
            return
        d = self._current_device()
        if d is None or str(d.get("plugin_id") or "") != "chrono.note_fx.random":
            return
        prob = float(_clamp_f(v, 0.0, 1.0))
        self._updating = True
        try:
            self.sld_r_prob.setValue(int(round(prob * 100.0)))
        finally:
            self._updating = False
        self._set_param("prob", float(prob))

    # ---- presets

    def _save_preset(self) -> None:
        t = self._get_track()
        if t is None:
            return
        chain = self._ensure_chain(t)
        path, _ = QFileDialog.getSaveFileName(self, "Save Note-FX Preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(chain, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save Preset", f"Failed to save preset:\n{e}")

    def _load_preset(self) -> None:
        t = self._get_track()
        if t is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Note-FX Preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "devices" not in data:
                raise ValueError("Invalid preset format")
            t.note_fx_chain = data
            self._emit_update()
            self._schedule_restart()
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Load Preset", f"Failed to load preset:\n{e}")
