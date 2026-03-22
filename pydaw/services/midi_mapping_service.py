"""MIDI Mapping service (v0.0.20.397).

Universal MIDI Learn / Controller Mapping for ALL DAW parameters:
- Track Volume, Pan, Mute, Solo
- FX Device parameters (any slider/knob in the device chain)
- Instrument parameters (AETERNA, Sampler, etc.)
- Plugin parameters (VST3, LV2, LADSPA)
- Transport controls (Play, Stop, Record, BPM)

Features:
- MIDI Learn: move any CC controller → automatically assigns to target
- Persisted in Project.midi_mappings (project-portable)
- RTParamStore integration for click-free audio parameter changes
- Automation Write mode support

This is intentionally modular and safe: it never blocks the GUI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any, List, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from pydaw.services.project_service import ProjectService
from pydaw.services.transport_service import TransportService


@dataclass
class MappingTarget:
    track_id: str
    param: str  # "volume"|"pan"|"mute"|"solo"|"device:<dev_id>:<p>"|"instrument:<p>"|"transport:<action>"
    min_val: float = 0.0
    max_val: float = 1.0
    is_toggle: bool = False  # True for mute/solo/bypass


# ── Param Discovery ─────────────────────────────────────────────────────────

_TRACK_PARAMS = [
    ("volume",  "Volume",   0.0, 1.0, False),
    ("pan",     "Pan",     -1.0, 1.0, False),
    ("mute",    "Mute",     0.0, 1.0, True),
    ("solo",    "Solo",     0.0, 1.0, True),
]

_TRANSPORT_PARAMS = [
    ("transport:play_stop",  "Play / Stop",  0.0, 1.0, True),
    ("transport:record",     "Record",       0.0, 1.0, True),
    ("transport:bpm",        "BPM",         20.0, 300.0, False),
]


def discover_mappable_params(project_service: ProjectService) -> List[Tuple[str, str, List[Tuple[str, str, float, float, bool]]]]:
    """Return all mappable parameters grouped by track.

    Returns: [(track_id, track_name, [(param_key, label, min, max, is_toggle), ...])]
    """
    result = []

    # Global transport params
    transport_params = [(p[0], p[1], p[2], p[3], p[4]) for p in _TRANSPORT_PARAMS]
    result.append(("__transport__", "🎛️ Transport", transport_params))

    try:
        tracks = project_service.ctx.project.tracks or []
    except Exception:
        return result

    for trk in tracks:
        try:
            tid = str(trk.id)
            tname = str(trk.name or tid)
            kind = str(getattr(trk, "kind", ""))
            params = []

            # Standard track params
            for pkey, plabel, pmin, pmax, ptoggle in _TRACK_PARAMS:
                params.append((pkey, plabel, pmin, pmax, ptoggle))

            # Note-FX chain devices
            try:
                nfx_chain = getattr(trk, "note_fx_chain", {}) or {}
                for i, dev in enumerate(nfx_chain.get("devices", []) or []):
                    dev_id = str(dev.get("id") or dev.get("plugin_id") or f"nfx_{i}")
                    dev_name = str(dev.get("name") or dev.get("plugin_id") or f"NoteFX {i}")
                    dev_params = dev.get("params", {}) or {}
                    for pname, pval in dev_params.items():
                        if pname.startswith("_"):
                            continue
                        try:
                            float(pval)
                        except (TypeError, ValueError):
                            continue
                        pkey = f"device:{dev_id}:{pname}"
                        params.append((pkey, f"{dev_name} → {pname}", 0.0, 1.0, False))
            except Exception:
                pass

            # Audio-FX chain devices
            try:
                afx_chain = getattr(trk, "audio_fx_chain", {}) or {}
                for i, dev in enumerate(afx_chain.get("devices", []) or []):
                    dev_id = str(dev.get("id") or dev.get("plugin_id") or f"afx_{i}")
                    dev_name = str(dev.get("name") or dev.get("plugin_id") or f"AudioFX {i}")
                    dev_params = dev.get("params", {}) or {}
                    for pname, pval in dev_params.items():
                        if pname.startswith("_"):
                            continue
                        try:
                            float(pval)
                        except (TypeError, ValueError):
                            continue
                        pkey = f"device:{dev_id}:{pname}"
                        params.append((pkey, f"{dev_name} → {pname}", 0.0, 1.0, False))
            except Exception:
                pass

            kind_emoji = {"instrument": "🎹", "audio": "🔊", "bus": "🔀", "master": "🔈"}.get(kind, "🎵")
            result.append((tid, f"{kind_emoji} {tname}", params))
        except Exception:
            continue

    return result


class MidiMappingService(QObject):
    """Universal MIDI CC mapping service.

    v0.0.20.397 — Extended to support ALL DAW parameters.
    """

    status = pyqtSignal(str)
    mapping_changed = pyqtSignal()
    learn_started = pyqtSignal(str)
    learn_completed = pyqtSignal()
    value_applied = pyqtSignal(str, str, float)  # track_id, param, value

    def __init__(
        self,
        project: ProjectService,
        transport: TransportService,
        status_cb: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.project = project
        self.transport = transport
        self._status = status_cb or (lambda _m: None)
        self._learn_target: Optional[MappingTarget] = None
        self._audio_engine = None
        self._automation_manager = None  # v0.0.20.431: Bridge to AutomationManager

        # v0.0.20.432: Touch/Latch mode state
        # _touch_active[track_id] = True means CC is currently being moved
        self._touch_active: Dict[str, bool] = {}
        # _latch_values[track_id] = {param: last_value} for latch hold
        self._latch_values: Dict[str, Dict[str, float]] = {}

        # v0.0.20.412: Throttle project_updated emissions to prevent GUI freeze
        # from high-rate CC messages (controllers send 30-120 msgs/sec).
        self._ui_dirty = False
        from PyQt6.QtCore import QTimer
        self._ui_throttle = QTimer(self)
        self._ui_throttle.setInterval(100)  # max 10 UI updates/sec
        self._ui_throttle.timeout.connect(self._flush_ui_update)
        self._ui_throttle.start()

        # v0.0.20.432: Touch timeout (500ms of no CC → stop writing)
        self._touch_timer = QTimer(self)
        self._touch_timer.setInterval(500)
        self._touch_timer.setSingleShot(True)
        self._touch_timer.timeout.connect(self._on_touch_timeout)

        # v0.0.20.432: Latch timer (write last value every 100ms while latched)
        self._latch_timer = QTimer(self)
        self._latch_timer.setInterval(100)
        self._latch_timer.timeout.connect(self._on_latch_tick)

    def set_audio_engine(self, engine) -> None:
        """Inject audio engine reference for RT parameter access."""
        self._audio_engine = engine

    def set_automation_manager(self, manager) -> None:
        """Inject AutomationManager for unified automation write (v0.0.20.431)."""
        self._automation_manager = manager

    def _flush_ui_update(self) -> None:
        """Called by throttle timer — emit project_updated only if dirty."""
        if self._ui_dirty:
            self._ui_dirty = False
            try:
                self.project.project_updated.emit()
            except Exception:
                pass

    # ── Touch/Latch helpers (v0.0.20.432) ──

    def _should_write_automation(self, trk, track_id: str, param: str, value: float) -> bool:
        """Determine if an automation point should be recorded for this param change.

        Modes:
        - off/read: never record
        - write: always record
        - touch: record while CC is active (reset timer on each CC)
        - latch: record + keep latching last value until transport stops

        Returns True if a point should be written now.
        """
        mode = getattr(trk, "automation_mode", "off")

        if mode == "off" or mode == "read":
            return False

        if mode == "write":
            return True

        if mode == "touch":
            # Mark this track as touch-active, restart timeout
            self._touch_active[track_id] = True
            try:
                self._touch_timer.start()  # restart 500ms timer
            except Exception:
                pass
            return True

        if mode == "latch":
            # Store last value for continuous writing, start latch timer
            if track_id not in self._latch_values:
                self._latch_values[track_id] = {}
            self._latch_values[track_id][param] = float(value)
            try:
                if not self._latch_timer.isActive():
                    self._latch_timer.start()
            except Exception:
                pass
            return True

        return False

    def _on_touch_timeout(self) -> None:
        """v0.0.20.432: Touch mode — 500ms since last CC, stop writing."""
        self._touch_active.clear()
        # v0.0.20.440: Auto-thin recorded lanes
        self._auto_thin_lanes()
        self._status("Touch: Release — Automation Write gestoppt")

    def _on_latch_tick(self) -> None:
        """v0.0.20.432: Latch mode — write last values at current beat position."""
        try:
            playing = getattr(self.transport, "playing", False)
            if not playing:
                self._latch_values.clear()
                self._latch_timer.stop()
                # v0.0.20.440: Auto-thin recorded lanes
                self._auto_thin_lanes()
                self._status("Latch: Transport gestoppt — Latch beendet")
                return

            for track_id, params in list(self._latch_values.items()):
                trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
                if not trk or getattr(trk, "automation_mode", "off") != "latch":
                    continue
                for param, value in params.items():
                    self._write_automation_point(track_id, param, float(value))
        except Exception:
            pass

    def _auto_thin_lanes(self) -> None:
        """v0.0.20.440: Trigger auto-thinning on AutomationManager after recording."""
        am = self._automation_manager
        if am is not None:
            try:
                removed = am.thin_recorded_lanes()
                if removed > 0:
                    self._status(f"Auto-Thin: {removed} redundante Punkte entfernt")
            except Exception:
                pass

    # --- mapping list (persisted)

    def mappings(self) -> List[Dict[str, Any]]:
        return list(self.project.ctx.project.midi_mappings or [])

    def add_mapping(self, channel: int, control: int, target: MappingTarget) -> None:
        m = {
            "type": "cc",
            "channel": int(channel),
            "control": int(control),
            "track_id": str(target.track_id),
            "param": str(target.param),
            "min_val": float(target.min_val),
            "max_val": float(target.max_val),
            "is_toggle": bool(target.is_toggle),
        }
        lst = self.project.ctx.project.midi_mappings or []
        lst = [x for x in lst if not (
            x.get("type") == "cc"
            and x.get("channel") == m["channel"]
            and x.get("control") == m["control"]
            and x.get("track_id") == m["track_id"]
            and x.get("param") == m["param"]
        )]
        lst.append(m)
        self.project.ctx.project.midi_mappings = lst
        self.project.project_updated.emit()
        try:
            self.mapping_changed.emit()
        except Exception:
            pass
        self._status(f"MIDI Mapping: CC{control} ch{channel} → {target.param}")

    def remove_mapping(self, idx: int) -> None:
        lst = self.project.ctx.project.midi_mappings or []
        if 0 <= idx < len(lst):
            removed = lst.pop(idx)
            self.project.ctx.project.midi_mappings = lst
            self.project.project_updated.emit()
            try:
                self.mapping_changed.emit()
            except Exception:
                pass
            self._status(f"MIDI Mapping entfernt: {removed}")

    def remove_mappings_for_param(self, track_id: str, param: str) -> None:
        lst = self.project.ctx.project.midi_mappings or []
        before = len(lst)
        lst = [x for x in lst if not (x.get("track_id") == track_id and x.get("param") == param)]
        if len(lst) < before:
            self.project.ctx.project.midi_mappings = lst
            self.project.project_updated.emit()
            try:
                self.mapping_changed.emit()
            except Exception:
                pass

    def get_mapping_for_param(self, track_id: str, param: str) -> Optional[Dict[str, Any]]:
        for m in (self.project.ctx.project.midi_mappings or []):
            if m.get("track_id") == track_id and m.get("param") == param:
                return m
        return None

    # --- learn

    def start_learn(self, target: MappingTarget) -> None:
        self._learn_target = target
        msg = f"MIDI Learn aktiv: bewege einen Controller für {target.param}"
        self._status(msg)
        try:
            self.learn_started.emit(msg)
        except Exception:
            pass

    def cancel_learn(self) -> None:
        self._learn_target = None
        self._status("MIDI Learn beendet.")

    def is_learning(self) -> bool:
        return self._learn_target is not None

    # --- apply incoming message

    def handle_mido_message(self, msg) -> None:  # noqa: ANN001
        try:
            mtype = getattr(msg, "type", "")
        except Exception:
            return
        if mtype != "control_change":
            return

        ch = int(getattr(msg, "channel", 0))
        cc = int(getattr(msg, "control", 0))
        val = int(getattr(msg, "value", 0))

        # learn mode
        if self._learn_target is not None:
            tgt = self._learn_target
            self._learn_target = None
            self.add_mapping(ch, cc, tgt)
            try:
                self.learn_completed.emit()
            except Exception:
                pass
            return

        # apply mappings
        mapped = False
        for m in (self.project.ctx.project.midi_mappings or []):
            if m.get("type") != "cc":
                continue
            if int(m.get("channel", -1)) != ch:
                continue
            if int(m.get("control", -1)) != cc:
                continue

            track_id = str(m.get("track_id", ""))
            param = str(m.get("param", ""))
            min_val = float(m.get("min_val", 0.0))
            max_val = float(m.get("max_val", 1.0))
            is_toggle = bool(m.get("is_toggle", False))

            if not param:
                continue

            # Normalize CC → param value
            if is_toggle:
                f = 1.0 if val >= 64 else 0.0
            else:
                f = min_val + (val / 127.0) * (max_val - min_val)
                f = max(min_val, min(max_val, f))

            if self._apply_param(track_id, param, float(f), is_toggle):
                mapped = True

        if mapped:
            # v0.0.20.412: Don't emit immediately — set dirty flag, timer flushes it
            self._ui_dirty = True

    def _apply_param(self, track_id: str, param: str, value: float, is_toggle: bool) -> bool:
        try:
            # ── Transport ──
            if param.startswith("transport:"):
                return self._apply_transport(param, value)

            if not track_id:
                return False

            trk = next((t for t in self.project.ctx.project.tracks if t.id == track_id), None)
            if not trk:
                return False

            if param == "volume":
                f = max(0.0, min(1.0, value))
                trk.volume = float(f)
                self._rt_set_track_vol(track_id, f)
                try:
                    self.value_applied.emit(track_id, param, f)
                except Exception:
                    pass
                # v0.0.20.432: Universal write/touch/latch
                if self._should_write_automation(trk, track_id, param, f):
                    self._write_automation_point(track_id, param, float(f))
                return True

            if param == "pan":
                f = max(-1.0, min(1.0, value))
                trk.pan = float(f)
                self._rt_set_track_pan(track_id, f)
                try:
                    self.value_applied.emit(track_id, param, f)
                except Exception:
                    pass
                # v0.0.20.432: Universal write/touch/latch
                if self._should_write_automation(trk, track_id, param, f):
                    self._write_automation_point(track_id, param, float(f))
                return True

            if param == "mute":
                trk.muted = bool(value >= 0.5)
                self._rt_set_track_mute(track_id, trk.muted)
                try:
                    self.value_applied.emit(track_id, param, 1.0 if trk.muted else 0.0)
                except Exception:
                    pass
                return True

            if param == "solo":
                trk.solo = bool(value >= 0.5)
                self._rt_set_track_solo(track_id, trk.solo)
                try:
                    self.value_applied.emit(track_id, param, 1.0 if trk.solo else 0.0)
                except Exception:
                    pass
                return True

            # ── Device params ──
            if param.startswith("device:"):
                parts = param.split(":", 2)
                if len(parts) >= 3:
                    return self._apply_device_param(trk, track_id, parts[1], parts[2], value)

            # ── Audio-FX params (afx:{tid}:{did}:{p}) ──
            # v0.0.20.415: Write RT directly for instant audio response,
            # AND emit value_applied for UI slider update via bridge.
            if param.startswith("afx:") or param.startswith("afxchain:"):
                # Immediate RT write (audio hears change instantly)
                try:
                    parts = param.rsplit(":", 1)
                    pname = parts[-1] if len(parts) >= 2 else ""
                    if pname == "gain":
                        # dB → linear conversion
                        rt_val = float(10.0 ** (max(-120.0, min(24.0, value)) / 20.0))
                    else:
                        rt_val = float(value)
                    self._rt_set_param(param, rt_val)
                except Exception:
                    pass
                # UI slider update via bridge
                try:
                    self.value_applied.emit(track_id, param, value)
                except Exception:
                    pass
                # v0.0.20.432: Universal write/touch/latch
                if self._should_write_automation(trk, track_id, param, float(value)):
                    self._write_automation_point(track_id, param, float(value))
                return True

            # ── Instrument params ──
            if param.startswith("instrument:"):
                pname = param.split(":", 1)[1] if ":" in param else ""
                if pname:
                    inst_state = getattr(trk, "instrument_state", {}) or {}
                    inst_state[pname] = float(value)
                    trk.instrument_state = inst_state
                    self._rt_set_param(f"trk:{track_id}:inst:{pname}", value)
                    try:
                        self.value_applied.emit(track_id, param, value)
                    except Exception:
                        pass
                    return True

            # Automation write (generic catch-all for unmatched params)
            # v0.0.20.432: Universal write/touch/latch
            if self._should_write_automation(trk, track_id, param, float(value)):
                self._write_automation_point(track_id, param, float(value))

            return False
        except Exception:
            return False

    def _apply_device_param(self, trk, track_id: str, dev_id: str, pname: str, value: float) -> bool:
        try:
            for chain_attr in ("note_fx_chain", "audio_fx_chain"):
                chain = getattr(trk, chain_attr, {}) or {}
                devices = chain.get("devices", []) or []
                for dev in devices:
                    did = str(dev.get("id") or dev.get("plugin_id") or "")
                    if did != dev_id:
                        continue
                    params = dev.get("params", {}) or {}
                    if pname in params:
                        try:
                            params[pname] = float(value)
                            dev["params"] = params
                        except Exception:
                            pass
                        rt_key = f"trk:{track_id}:{did}:{pname}"
                        self._rt_set_param(rt_key, value)
                        try:
                            self.value_applied.emit(track_id, f"device:{dev_id}:{pname}", value)
                        except Exception:
                            pass
                        # v0.0.20.432: Universal write/touch/latch
                        if self._should_write_automation(trk, track_id, f"device:{dev_id}:{pname}", float(value)):
                            self._write_automation_point(track_id, f"device:{dev_id}:{pname}", float(value))
                        return True
            return False
        except Exception:
            return False

    def _apply_transport(self, param: str, value: float) -> bool:
        try:
            if param == "transport:play_stop" and value >= 0.5:
                try:
                    self.transport.toggle_play()
                except Exception:
                    pass
                return True
            if param == "transport:record" and value >= 0.5:
                try:
                    self.transport.toggle_record()
                except Exception:
                    pass
                return True
            if param == "transport:bpm":
                bpm = max(20.0, min(300.0, value))
                try:
                    self.transport.set_bpm(bpm)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False

    # ── RT helpers ──

    def _rt_store(self):
        try:
            ae = self._audio_engine
            if ae is not None:
                return getattr(ae, "rt_params", None) or getattr(ae, "_rt_params", None)
        except Exception:
            pass
        return None

    def _rt_set_param(self, key: str, value: float) -> None:
        try:
            store = self._rt_store()
            if store is not None:
                store.set_param(key, float(value))
        except Exception:
            pass

    def _rt_set_track_vol(self, track_id: str, vol: float) -> None:
        try:
            store = self._rt_store()
            if store is not None:
                store.set_track_vol(track_id, float(vol))
        except Exception:
            pass

    def _rt_set_track_pan(self, track_id: str, pan: float) -> None:
        try:
            store = self._rt_store()
            if store is not None:
                store.set_track_pan(track_id, float(pan))
        except Exception:
            pass

    def _rt_set_track_mute(self, track_id: str, muted: bool) -> None:
        try:
            store = self._rt_store()
            if store is not None:
                store.set_track_mute(track_id, bool(muted))
        except Exception:
            pass

    def _rt_set_track_solo(self, track_id: str, solo: bool) -> None:
        try:
            store = self._rt_store()
            if store is not None:
                store.set_track_solo(track_id, bool(solo))
        except Exception:
            pass

    def _write_automation_point(self, track_id: str, param: str, value: float) -> None:
        """Write an automation point at the current transport position.

        v0.0.20.435: PERFORMANCE FIX — no sort (beats are monotonic during playback),
        throttled UI emit (via AutomationManager._cc_ui_dirty_pids), skip legacy store.
        """
        beat = float(getattr(self.transport, "current_beat", 0.0))

        # ── Write to AutomationManager (PRIMARY — this is what the UI reads) ──
        am = self._automation_manager
        if am is not None:
            try:
                from pydaw.audio.automatable_parameter import BreakPoint, CurveType
                if param.startswith("afx:") or param.startswith("afxchain:") or param.startswith("device:"):
                    pid = f"trk:{track_id}:{param}"
                else:
                    pid = f"trk:{track_id}:{param}"
                lane = am.get_or_create_lane(pid, track_id=track_id, param_name=param)
                bp = BreakPoint(beat=beat, value=float(value), curve_type=CurveType.LINEAR)
                lane.points.append(bp)
                # v0.0.20.435: NO sort — beats are monotonically increasing during playback.
                # Cap points to prevent unbounded growth
                if len(lane.points) > 4000:
                    lane.points = lane.points[-3000:]
                # v0.0.20.435: Throttled UI notification via dirty set
                dirty = getattr(am, '_cc_ui_dirty_pids', None)
                if dirty is not None:
                    dirty.add(pid)
                else:
                    try:
                        am.lane_data_changed.emit(pid)
                    except Exception:
                        pass
                # v0.0.20.440: Track for auto-thinning on stop
                rec = getattr(am, '_recorded_lane_pids', None)
                if rec is None:
                    am._recorded_lane_pids = set()
                    rec = am._recorded_lane_pids
                rec.add(pid)
            except Exception:
                pass

        # v0.0.20.435: Skip legacy store write during recording for performance.
        # Legacy store is synced on project save.
