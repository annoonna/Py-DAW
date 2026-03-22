"""Automatable Parameter System (v0.0.20.89).

Unified parameter system for DAW-grade automation — inspired by JUCE AudioProcessorParameter,
Ableton Live, and Bitwig Studio.

Architecture:
- AutomatableParameter: Base class for any controllable parameter.
  Supports multiple simultaneous input sources: Manual (GUI), Timeline Automation, Modulators.
- AutomationManager: Central routing service.
  Connects parameters to lanes, modulators, and UI. Decouples widgets from the arranger.
- ModulationSource: LFO/Envelope that adds offset to a parameter (Bitwig-style).

Thread Safety:
- GUI thread sets values via set_value() / set_automation_value()
- Audio thread reads via get_effective_value() — lock-free via RTParamStore
- No direct writes from GUI into audio variables — ever

Usage:
    mgr = AutomationManager(project_service, rt_params)
    param = mgr.register_parameter("trk:abc:vol", "Volume", 0.0, 1.0, 0.8, track_id="abc")
    param.set_value(0.5)           # from GUI
    param.add_modulation(0.1)      # from LFO
    effective = param.get_effective_value()  # 0.6
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal


class CurveType(Enum):
    """Interpolation type between automation breakpoints."""
    LINEAR = "linear"
    BEZIER = "bezier"
    STEP = "step"          # discrete steps (for ComboBox / enum params)
    SMOOTH = "smooth"      # S-curve (cubic ease-in-out)
    # v0.0.20.644: Additional curve types (AP9 Phase 9C)
    LOGARITHMIC = "logarithmic"  # fast start, slow end (good for fades)
    EXPONENTIAL = "exponential"  # slow start, fast end (good for swells)
    S_CURVE = "s_curve"          # smooth sigmoid (stronger than SMOOTH)


@dataclass
class BreakPoint:
    """A single automation breakpoint on the timeline.

    beat: position in beats (quarter notes)
    value: normalized 0..1 (mapped to param range by AutomatableParameter)
    curve_type: interpolation to next point
    bezier_cx / bezier_cy: control point for Bezier curves (relative 0..1 within segment)
    """
    beat: float = 0.0
    value: float = 0.0
    curve_type: CurveType = CurveType.LINEAR
    bezier_cx: float = 0.5
    bezier_cy: float = 0.5

    def to_dict(self) -> dict:
        d = {"beat": self.beat, "value": self.value, "curve_type": self.curve_type.value}
        if self.curve_type == CurveType.BEZIER:
            d["bezier_cx"] = self.bezier_cx
            d["bezier_cy"] = self.bezier_cy
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BreakPoint":
        ct = CurveType.LINEAR
        try:
            ct = CurveType(d.get("curve_type", "linear"))
        except (ValueError, KeyError):
            pass
        return cls(
            beat=float(d.get("beat", 0.0)),
            value=float(d.get("value", 0.0)),
            curve_type=ct,
            bezier_cx=float(d.get("bezier_cx", 0.5)),
            bezier_cy=float(d.get("bezier_cy", 0.5)),
        )


@dataclass
class AutomationLane:
    """Automation data for one parameter on one track.

    Contains breakpoints sorted by beat, plus metadata.

    v0.0.20.644: Added automation_mode for Relative/Trim operation.
    Modes:
    - "absolute": Breakpoint values directly set the parameter (default, existing behavior)
    - "relative": Breakpoint values are OFFSETS added to the parameter's base value
                  (0.5 = no change, >0.5 = increase, <0.5 = decrease)
    - "trim":     Breakpoint values are MULTIPLIERS applied to the parameter's base value
                  (0.5 = half, 1.0 = no change, 2.0 = double — stored normalized as 0..1 → 0..2x)
    """
    parameter_id: str = ""
    track_id: str = ""
    param_name: str = ""
    points: List[BreakPoint] = field(default_factory=list)
    enabled: bool = True
    color: str = "#00BFFF"  # default: deep sky blue
    # v0.0.20.644: Automation mode (AP9 Phase 9B)
    automation_mode: str = "absolute"  # "absolute" | "relative" | "trim"

    def sort_points(self) -> None:
        self.points.sort(key=lambda p: p.beat)

    def thin(self, epsilon: float = 0.015) -> int:
        """Remove redundant breakpoints using Douglas-Peucker algorithm.

        v0.0.20.440: Bitwig-style auto-thinning. Reduces 500 raw CC points
        to ~30-50 clean points while preserving the curve shape within epsilon.

        Args:
            epsilon: Maximum perpendicular distance tolerance (0..1 normalized).
                     0.015 ≈ 1.5% deviation — inaudible but removes ~90% of points.

        Returns:
            Number of points removed.
        """
        pts = self.points
        if len(pts) < 3:
            return 0

        # Ensure sorted before thinning
        pts.sort(key=lambda p: p.beat)

        # Douglas-Peucker: find the point farthest from the line between first and last.
        # If it's within epsilon, all intermediate points can be removed.
        # Otherwise, split at that point and recurse.
        def _dp(start: int, end: int, keep: list) -> None:
            if end - start < 2:
                return
            # Line from pts[start] to pts[end]
            b0, v0 = pts[start].beat, pts[start].value
            b1, v1 = pts[end].beat, pts[end].value
            db = b1 - b0
            dv = v1 - v0
            line_len_sq = db * db + dv * dv

            max_dist = 0.0
            max_idx = start
            for i in range(start + 1, end):
                # Perpendicular distance from pts[i] to the line
                bi, vi = pts[i].beat, pts[i].value
                if line_len_sq < 1e-12:
                    dist = ((bi - b0) ** 2 + (vi - v0) ** 2) ** 0.5
                else:
                    # Project onto line, compute perpendicular distance
                    t = ((bi - b0) * db + (vi - v0) * dv) / line_len_sq
                    t = max(0.0, min(1.0, t))
                    proj_b = b0 + t * db
                    proj_v = v0 + t * dv
                    dist = ((bi - proj_b) ** 2 + (vi - proj_v) ** 2) ** 0.5
                if dist > max_dist:
                    max_dist = dist
                    max_idx = i

            if max_dist > epsilon:
                keep[max_idx] = True
                _dp(start, max_idx, keep)
                _dp(max_idx, end, keep)

        n_before = len(pts)
        keep = [False] * n_before
        keep[0] = True
        keep[-1] = True
        _dp(0, n_before - 1, keep)

        self.points = [pts[i] for i in range(n_before) if keep[i]]
        return n_before - len(self.points)

    def interpolate(self, beat: float) -> Optional[float]:
        """Sample-accurate interpolation at a given beat position.

        Returns None if no points exist. Supports Linear, Bezier, Step, Smooth,
        Logarithmic, Exponential, S-Curve.

        NOTE: This returns the RAW breakpoint value. For relative/trim modes,
        use apply_mode() to get the effective parameter value.
        """
        if not self.points:
            return None
        pts = self.points  # assumed sorted
        if not pts:
            return None

        # Clamp before first / after last
        if beat <= pts[0].beat:
            return pts[0].value
        if beat >= pts[-1].beat:
            return pts[-1].value

        # Find the segment
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            if p0.beat <= beat <= p1.beat:
                span = p1.beat - p0.beat
                if span <= 0:
                    return p1.value
                t = (beat - p0.beat) / span

                if p0.curve_type == CurveType.STEP:
                    return p0.value

                if p0.curve_type == CurveType.SMOOTH:
                    # Cubic ease-in-out (S-curve)
                    t = t * t * (3.0 - 2.0 * t)
                    return p0.value + t * (p1.value - p0.value)

                if p0.curve_type == CurveType.BEZIER:
                    # Quadratic Bezier through control point
                    cx = p0.bezier_cx
                    cy = p0.bezier_cy
                    # Map cx/cy to absolute values
                    ctrl_val = p0.value + cy * (p1.value - p0.value)
                    # Quadratic Bezier: B(t) = (1-t)²P0 + 2(1-t)tC + t²P1
                    one_t = 1.0 - t
                    return (one_t * one_t * p0.value +
                            2.0 * one_t * t * ctrl_val +
                            t * t * p1.value)

                # v0.0.20.644: Logarithmic (fast start, slow end)
                if p0.curve_type == CurveType.LOGARITHMIC:
                    import math as _m
                    # log curve: y = log(1 + t*k) / log(1+k), k=9 for nice shape
                    t_log = _m.log1p(t * 9.0) / _m.log(10.0)
                    return p0.value + t_log * (p1.value - p0.value)

                # v0.0.20.644: Exponential (slow start, fast end)
                if p0.curve_type == CurveType.EXPONENTIAL:
                    # exp curve: y = (e^(t*k) - 1) / (e^k - 1), k=3
                    import math as _m
                    k = 3.0
                    t_exp = (_m.exp(t * k) - 1.0) / (_m.exp(k) - 1.0)
                    return p0.value + t_exp * (p1.value - p0.value)

                # v0.0.20.644: S-Curve (stronger sigmoid)
                if p0.curve_type == CurveType.S_CURVE:
                    # Quintic S-curve: 6t⁵ - 15t⁴ + 10t³ (smoother than cubic)
                    t_s = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
                    return p0.value + t_s * (p1.value - p0.value)

                # Default: LINEAR
                return p0.value + t * (p1.value - p0.value)

        return pts[-1].value

    def apply_mode(self, raw_value: float, base_value: float,
                   param_min: float = 0.0, param_max: float = 1.0) -> float:
        """Apply the automation mode to get the effective parameter value.

        v0.0.20.644 (AP9 Phase 9B).

        Args:
            raw_value: Interpolated breakpoint value (0..1 normalized)
            base_value: Parameter's current base value (in param range)
            param_min: Parameter minimum
            param_max: Parameter maximum

        Returns:
            Effective value in parameter range
        """
        mode = self.automation_mode
        span = param_max - param_min
        if span <= 0:
            return base_value

        if mode == "relative":
            # raw_value: 0.5 = no change, 0=min offset, 1=max offset
            # Offset range: -span to +span
            offset = (raw_value - 0.5) * 2.0 * span
            return max(param_min, min(param_max, base_value + offset))

        elif mode == "trim":
            # raw_value: 0..1 maps to 0x..2x multiplier
            # 0.5 = 1.0x (no change), 0.0 = 0x, 1.0 = 2.0x
            multiplier = raw_value * 2.0
            return max(param_min, min(param_max, base_value * multiplier))

        else:
            # "absolute" (default): raw_value maps directly to param range
            return param_min + raw_value * span

    def to_dict(self) -> dict:
        return {
            "parameter_id": self.parameter_id,
            "track_id": self.track_id,
            "param_name": self.param_name,
            "points": [p.to_dict() for p in self.points],
            "enabled": self.enabled,
            "color": self.color,
            "automation_mode": self.automation_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AutomationLane":
        pts = [BreakPoint.from_dict(p) for p in d.get("points", []) if isinstance(p, dict)]
        lane = cls(
            parameter_id=str(d.get("parameter_id", "")),
            track_id=str(d.get("track_id", "")),
            param_name=str(d.get("param_name", "")),
            points=pts,
            enabled=bool(d.get("enabled", True)),
            color=str(d.get("color", "#00BFFF")),
            automation_mode=str(d.get("automation_mode", "absolute")),
        )
        lane.sort_points()
        return lane


class AutomatableParameter:
    """A single automatable parameter with multiple input sources.

    Value stack (order of priority):
    1. base_value: Set by user via GUI (manual mode)
    2. automation_value: Set by timeline automation playback (read mode)
    3. modulation_offset: Sum of all active modulators (LFO/Envelope)

    effective_value = clamp(automation_value or base_value + modulation_offset)

    Thread safety: All writes happen in GUI thread. Audio thread reads
    the final value from RTParamStore (set by AutomationManager.tick()).
    """

    def __init__(
        self,
        parameter_id: str,
        name: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        default_val: float = 0.0,
        track_id: str = "",
        display_format: str = "{:.2f}",
        unit: str = "",
        is_discrete: bool = False,
    ):
        self.parameter_id = parameter_id
        self.name = name
        self.min_val = min_val
        self.max_val = max_val
        self.default_val = default_val
        self.track_id = track_id
        self.display_format = display_format
        self.unit = unit
        self.is_discrete = is_discrete

        self._base_value = default_val
        self._automation_value: Optional[float] = None
        self._modulation_offset = 0.0
        self._modulation_sources: Dict[str, float] = {}  # source_id -> offset

        # Callbacks notified when effective value changes
        self._listeners: List[Callable[[float], None]] = []

    @property
    def base_value(self) -> float:
        return self._base_value

    def set_value(self, value: float) -> None:
        """Set base value from GUI interaction."""
        self._base_value = self._clamp(value)
        self._notify()

    def set_automation_value(self, value: Optional[float]) -> None:
        """Set from timeline automation playback. None = no automation active."""
        if value is not None:
            self._automation_value = self._clamp(value)
        else:
            self._automation_value = None
        self._notify()

    def add_modulation(self, source_id: str, offset: float) -> None:
        """Add/update a modulation source offset (Bitwig-style)."""
        self._modulation_sources[source_id] = offset
        self._recalc_modulation()

    def remove_modulation(self, source_id: str) -> None:
        """Remove a modulation source."""
        self._modulation_sources.pop(source_id, None)
        self._recalc_modulation()

    def _recalc_modulation(self) -> None:
        self._modulation_offset = sum(self._modulation_sources.values())
        self._notify()

    @property
    def modulation_offset(self) -> float:
        return self._modulation_offset

    def get_effective_value(self) -> float:
        """The final output value (base or automation + modulation)."""
        base = self._automation_value if self._automation_value is not None else self._base_value
        return self._clamp(base + self._modulation_offset)

    def get_normalized(self) -> float:
        """Effective value as 0..1 normalized."""
        span = self.max_val - self.min_val
        if span <= 0:
            return 0.0
        return (self.get_effective_value() - self.min_val) / span

    def from_normalized(self, norm: float) -> float:
        """Convert 0..1 to parameter range."""
        return self.min_val + max(0.0, min(1.0, norm)) * (self.max_val - self.min_val)

    def get_display_value(self) -> str:
        """Formatted string for UI display."""
        try:
            return self.display_format.format(self.get_effective_value()) + self.unit
        except Exception:
            return str(self.get_effective_value())

    def add_listener(self, callback: Callable[[float], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[float], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _clamp(self, value: float) -> float:
        v = max(self.min_val, min(self.max_val, float(value)))
        if self.is_discrete:
            v = round(v)
        return v

    def _notify(self) -> None:
        val = self.get_effective_value()
        for cb in self._listeners:
            try:
                cb(val)
            except Exception:
                pass


class AutomationManager(QObject):
    """Central automation routing service.

    Responsibilities:
    - Registry of all AutomatableParameters
    - Registry of AutomationLanes (timeline breakpoint data)
    - Signal hub: requestShowAutomation(parameter_id) from any widget
    - Tick function: called per playback frame to apply automation

    Usage from widget:
        # Widget fires signal:
        automation_manager.request_show_automation.emit(param.parameter_id)
        # AutomationLanePanel catches it and opens the lane

    Modular: Does NOT depend on ArrangerCanvas or specific widgets.

    Safe FX mirror (v0.0.20.260):
    - Some FX parameters use their RTParamStore key directly as parameter_id
      (e.g. ``afx:...`` / ``afxchain:...``).
    - These should still affect audio even when the corresponding widget is not
      currently instantiated or connected.
    - Therefore the manager mirrors active automation values directly into the
      RT store for known RT-key prefixes, while the usual Qt signal path keeps
      visible widgets in sync.
    """

    # Signal: a widget requests to show automation for parameter_id
    request_show_automation = pyqtSignal(str)  # parameter_id
    # Signal: a parameter's effective value changed
    parameter_changed = pyqtSignal(str, float)  # parameter_id, new_value
    # Signal: automation lane data changed
    lane_data_changed = pyqtSignal(str)  # parameter_id

    def __init__(self, parent: QObject = None, rt_params: Any = None):
        super().__init__(parent)
        self._parameters: Dict[str, AutomatableParameter] = {}
        self._lanes: Dict[str, AutomationLane] = {}
        self._rt_params = rt_params
        # v0.0.20.433: References for CC→Automation recording in Fast Path
        self._transport = None  # TransportService (for current_beat)
        self._project = None    # ProjectService (for track.automation_mode)

    def set_transport(self, transport) -> None:
        """Inject transport reference for automation recording (v0.0.20.433)."""
        self._transport = transport

    def set_project(self, project) -> None:
        """Inject project reference for automation recording (v0.0.20.433)."""
        self._project = project

    # --- Parameter registration ---

    def register_parameter(
        self,
        parameter_id: str,
        name: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        default_val: float = 0.0,
        track_id: str = "",
        **kwargs,
    ) -> AutomatableParameter:
        """Register (or retrieve) an automatable parameter."""
        if parameter_id in self._parameters:
            return self._parameters[parameter_id]
        param = AutomatableParameter(
            parameter_id=parameter_id,
            name=name,
            min_val=min_val,
            max_val=max_val,
            default_val=default_val,
            track_id=track_id,
            **kwargs,
        )
        param.add_listener(lambda v, pid=parameter_id: self.parameter_changed.emit(pid, v))
        self._parameters[parameter_id] = param
        return param

    def get_parameter(self, parameter_id: str) -> Optional[AutomatableParameter]:
        return self._parameters.get(parameter_id)

    def get_parameters_for_track(self, track_id: str) -> List[AutomatableParameter]:
        return [p for p in self._parameters.values() if p.track_id == track_id]

    def unregister_parameter(self, parameter_id: str) -> None:
        self._parameters.pop(parameter_id, None)
        self._lanes.pop(parameter_id, None)

    # --- Lane management ---

    def get_or_create_lane(self, parameter_id: str, track_id: str = "", param_name: str = "") -> AutomationLane:
        if parameter_id in self._lanes:
            return self._lanes[parameter_id]
        lane = AutomationLane(
            parameter_id=parameter_id,
            track_id=track_id or (self._parameters.get(parameter_id, None) or AutomatableParameter("", "")).track_id,
            param_name=param_name or (self._parameters.get(parameter_id, None) or AutomatableParameter("", "")).name,
        )
        self._lanes[parameter_id] = lane
        return lane

    def get_lane(self, parameter_id: str) -> Optional[AutomationLane]:
        return self._lanes.get(parameter_id)

    def get_lanes_for_track(self, track_id: str) -> List[AutomationLane]:
        return [l for l in self._lanes.values() if l.track_id == track_id]

    def remove_lane(self, parameter_id: str) -> None:
        self._lanes.pop(parameter_id, None)

    def copy_automation_range(self, track_id: str, src_start: float, src_end: float, dst_start: float) -> int:
        """v0.0.20.442: Copy automation breakpoints from one time range to another.

        Used when clips are duplicated (Ctrl+D) or Ctrl+Drag copied.
        Copies all breakpoints in [src_start, src_end) from all lanes of the
        given track to dst_start + (beat - src_start).

        Returns number of points copied.
        """
        if src_end <= src_start:
            return 0
        offset = dst_start - src_start
        total = 0
        for lane in self.get_lanes_for_track(track_id):
            new_pts = []
            for p in lane.points:
                if src_start <= p.beat < src_end:
                    bp = BreakPoint(
                        beat=p.beat + offset,
                        value=p.value,
                        curve_type=p.curve_type,
                        bezier_cx=p.bezier_cx,
                        bezier_cy=p.bezier_cy,
                    )
                    new_pts.append(bp)
            if new_pts:
                lane.points.extend(new_pts)
                lane.sort_points()
                total += len(new_pts)
                try:
                    self.lane_data_changed.emit(lane.parameter_id)
                except Exception:
                    pass
        return total

    # --- Playback tick ---

    def _mirror_to_rt_store(self, parameter_id: str, value: float) -> None:
        """Best-effort direct RTParamStore sync for FX-style parameter ids.

        This is intentionally narrow and only mirrors ids that are already RT
        keys in the current architecture. Internal instrument parameters keep
        using their dedicated widget/engine routes.
        """
        try:
            rt = getattr(self, '_rt_params', None)
            pid = str(parameter_id or '')
            if rt is None or not pid:
                return
            if not (pid.startswith('afx:') or pid.startswith('afxchain:')):
                return
            if hasattr(rt, 'set_param'):
                rt.set_param(pid, float(value))
        except Exception:
            pass

    def tick(self, beat: float) -> None:
        """Called per playback frame. Applies automation values from lanes to parameters.

        This is called from the GUI thread (via transport timer), NOT from the audio thread.
        The RTParamStore bridge (in AutomationPlaybackService) writes to the audio thread.
        """
        for pid, lane in self._lanes.items():
            if not lane.enabled or not lane.points:
                continue
            param = self._parameters.get(pid)
            if param is None:
                continue
            # Sample the lane at current beat
            norm_val = lane.interpolate(beat)
            if norm_val is not None:
                # Lane values are normalized 0..1 — convert to param range
                actual = param.from_normalized(norm_val)
                param.set_automation_value(actual)
                # v0.0.20.434: Only mirror to RT store if no widget listeners exist.
                # When listeners exist (e.g. Gain widget), the signal chain
                # param → parameter_changed → widget._on_automation_changed → _apply_rt()
                # already writes the CORRECT format to RT (e.g. dB→linear conversion).
                # Calling _mirror_to_rt_store AFTER the signal chain would OVERWRITE
                # the correct value with the raw parameter-range value (e.g. dB instead
                # of linear), causing massive volume bugs.
                if not param._listeners:
                    self._mirror_to_rt_store(pid, actual)

    def clear_automation_values(self) -> None:
        """Clear all automation overrides (e.g. when transport stops)."""
        for pid, param in self._parameters.items():
            param.set_automation_value(None)
            # v0.0.20.434: Same guard as tick() — only mirror if no widget listeners
            if not param._listeners:
                try:
                    self._mirror_to_rt_store(pid, param.get_effective_value())
                except Exception:
                    pass

    # --- Serialization (to/from project) ---

    def export_lanes(self) -> Dict[str, dict]:
        """Export all lanes as JSON-safe dict."""
        return {pid: lane.to_dict() for pid, lane in self._lanes.items()}

    def import_lanes(self, data: Dict[str, dict]) -> None:
        """Import lanes from project data."""
        self._lanes.clear()
        if not isinstance(data, dict):
            return
        for pid, lane_data in data.items():
            if isinstance(lane_data, dict):
                try:
                    self._lanes[str(pid)] = AutomationLane.from_dict(lane_data)
                except Exception:
                    continue

    # --- Legacy bridge (for existing automation_lanes dict) ---

    def import_legacy_lanes(self, automation_lanes: dict) -> None:
        """Import from old Project.automation_lanes format.

        Old format: automation_lanes[track_id][param_name] = [{"beat": ..., "value": ...}, ...]
        New format: _lanes[parameter_id] = AutomationLane(...)
        """
        if not isinstance(automation_lanes, dict):
            return
        for track_id, params in automation_lanes.items():
            if not isinstance(params, dict):
                continue
            for param_name, points_data in params.items():
                pid = f"trk:{track_id}:{param_name}"
                pts = []
                if isinstance(points_data, list):
                    for p in points_data:
                        if isinstance(p, dict):
                            pts.append(BreakPoint(
                                beat=float(p.get("beat", 0.0)),
                                value=float(p.get("value", 0.0)),
                            ))
                elif isinstance(points_data, dict) and "points" in points_data:
                    # Newer sub-format with points key
                    for p in points_data.get("points", []):
                        if isinstance(p, dict):
                            pts.append(BreakPoint(
                                beat=float(p.get("beat", 0.0)),
                                value=float(p.get("value", 0.0)),
                            ))
                if pts:
                    lane = AutomationLane(
                        parameter_id=pid,
                        track_id=str(track_id),
                        param_name=str(param_name),
                        points=pts,
                    )
                    lane.sort_points()
                    self._lanes[pid] = lane

    # ── MIDI CC dispatch (v0.0.20.399) ──

    def handle_midi_message(self, msg) -> None:
        """Route MIDI CC to any learned widget (CompactKnob, QSlider, QSpinBox).

        Called from the MIDI input signal. Handles:
        1. MIDI Learn mode (assigns next CC to waiting widget)
        2. CC dispatch to mapped widgets (visual + engine update)

        v0.0.20.399: Universal — works for CompactKnob AND FX QSlider/QSpinBox.
        """
        try:
            mtype = getattr(msg, "type", "")
        except Exception:
            return
        if mtype != "control_change":
            return

        ch = int(getattr(msg, "channel", 0))
        cc = int(getattr(msg, "control", 0))
        val = int(getattr(msg, "value", 0))

        # MIDI Learn mode: assign CC to waiting widget
        learn_widget = getattr(self, "_midi_learn_knob", None)
        if learn_widget is not None:
            self._midi_learn_knob = None
            try:
                if hasattr(learn_widget, "_on_midi_learn_cc"):
                    # CompactKnob path
                    learn_widget._on_midi_learn_cc(ch, cc)
                else:
                    # Generic QSlider/QSpinBox path (from _install_automation_menu)
                    learn_widget._midi_cc_mapping = (int(ch), int(cc))
                    cc_listeners = getattr(self, "_midi_cc_listeners", None)
                    if cc_listeners is None:
                        self._midi_cc_listeners = {}
                        cc_listeners = self._midi_cc_listeners
                    cc_listeners[(int(ch), int(cc))] = learn_widget

                    # v0.0.20.423: Save to persistent registry (survives widget rebuilds).
                    # When DevicePanel rebuilds, the new widget re-registers using this.
                    _pid = getattr(learn_widget, '_pydaw_param_id', None)
                    if _pid:
                        persistent = getattr(self, '_persistent_cc_map', None)
                        if persistent is None:
                            self._persistent_cc_map = {}
                            persistent = self._persistent_cc_map
                        persistent[str(_pid)] = (int(ch), int(cc))

                # Clear red border
                try:
                    learn_widget.setStyleSheet('')
                except Exception:
                    pass
            except Exception:
                pass
            return

        # Dispatch to mapped widgets
        cc_listeners = getattr(self, "_midi_cc_listeners", None)
        if not cc_listeners:
            return
        widget = cc_listeners.get((ch, cc))
        if widget is not None:
            try:
                if hasattr(widget, "handle_midi_cc"):
                    # CompactKnob
                    widget.handle_midi_cc(val)
                elif hasattr(widget, "setRange"):
                    # QSlider / QSpinBox — scale CC 0-127 to widget range
                    lo = widget.minimum()
                    hi = widget.maximum()
                    scaled = lo + (val / 127.0) * (hi - lo)
                    widget.setValue(int(round(scaled)))
                elif hasattr(widget, "setValue"):
                    widget.setValue(int(round((val / 127.0) * 100.0)))
            except Exception:
                pass

            # v0.0.20.433: Write automation breakpoint for Fast Path MIDI Learn
            # This bridges the gap: CC→widget was visual+audio only,
            # now it also records into automation lanes when mode is write/touch/latch.
            try:
                self._write_cc_automation(widget, val)
            except Exception:
                pass

    # ── CC → Automation Recording (v0.0.20.433) ──

    def _write_cc_automation(self, widget, val_0_127: int) -> None:
        """Write an automation breakpoint when a MIDI Learn CC changes a widget.

        v0.0.20.435: PERFORMANCE FIX — no sort_points() during recording
        (beats are monotonically increasing during playback, so append is in-order).
        UI repaint is throttled to max 8 Hz via _cc_ui_dirty flag + timer.

        Only writes if:
        - Transport + Project references are available
        - Widget has a _pydaw_param_id or _parameter_id (automation target)
        - Track's automation_mode is write/touch/latch
        """
        transport = self._transport
        project = self._project
        if transport is None or project is None:
            return

        # Get parameter_id from widget — check both attributes:
        # _pydaw_param_id: set by _install_automation_menu (FX slider/knob widgets)
        # _parameter_id:   set by CompactKnob (instrument knobs like Bach Orgel)
        param_id = getattr(widget, '_pydaw_param_id', None)
        if not param_id:
            param_id = getattr(widget, '_parameter_id', None)
        if not param_id:
            return
        param_id = str(param_id)

        # Parse track_id from parameter_id — all formats have track_id at position [1]:
        #   trk:{track_id}:bach_orgel:cut
        #   afx:{track_id}:{device_id}:gain
        #   afx:{track_id}:{device_id}:lv2:{symbol}
        #   afx:{track_id}:{device_id}:ladspa:{port}
        #   afx:{track_id}:{device_id}:vst3:{param}
        #   afxchain:{track_id}:wet_gain
        parts = param_id.split(":", 2)
        if len(parts) < 2:
            return
        prefix = parts[0]
        if prefix not in ("trk", "afx", "afxchain"):
            return
        track_id = parts[1]
        if not track_id:
            return

        # Find track and check automation mode
        try:
            proj = getattr(project, "ctx", None)
            if proj:
                proj = getattr(proj, "project", None)
            if not proj:
                proj = getattr(project, "project", None)
            if not proj:
                return
            tracks = getattr(proj, "tracks", []) or []
            trk = next((t for t in tracks if getattr(t, "id", "") == track_id), None)
            if not trk:
                return
            mode = getattr(trk, "automation_mode", "off")
            if mode not in ("write", "touch", "latch"):
                return
        except Exception:
            return

        # Get current beat position
        beat = float(getattr(transport, "current_beat", 0.0))

        # Normalize CC value to 0..1
        norm_val = max(0.0, min(1.0, val_0_127 / 127.0))

        # Write to AutomationManager lane (PRIMARY store — UI reads this)
        try:
            lane = self.get_or_create_lane(
                param_id,
                track_id=track_id,
                param_name=parts[2] if len(parts) >= 3 else "",
            )
            bp = BreakPoint(beat=beat, value=float(norm_val), curve_type=CurveType.LINEAR)
            lane.points.append(bp)
            # v0.0.20.435: NO sort_points() here — during playback, beat is
            # monotonically increasing so append is already in-order.
            # Sorting will happen once on playback stop / project save.
            # Cap points to prevent unbounded growth during long record sessions
            if len(lane.points) > 4000:
                lane.points = lane.points[-3000:]
            # v0.0.20.435: Throttled UI notification — set dirty flag, timer flushes
            dirty = getattr(self, '_cc_ui_dirty_pids', None)
            if dirty is None:
                self._cc_ui_dirty_pids = set()
                dirty = self._cc_ui_dirty_pids
                # Create throttle timer on first use (max 8 Hz UI updates)
                try:
                    from PyQt6.QtCore import QTimer
                    t = QTimer(self)
                    t.setInterval(125)  # 8 Hz
                    t.timeout.connect(self._flush_cc_ui)
                    t.start()
                    self._cc_ui_timer = t
                except Exception:
                    pass
            dirty.add(param_id)
            # v0.0.20.440: Track which lanes were recorded for auto-thinning on stop
            rec = getattr(self, '_recorded_lane_pids', None)
            if rec is None:
                self._recorded_lane_pids = set()
                rec = self._recorded_lane_pids
            rec.add(param_id)
        except Exception:
            pass

        # v0.0.20.435: Skip legacy store write during recording — deferred to save.
        # Writing + sorting the legacy dict on every CC was a major perf drain.

    def _flush_cc_ui(self) -> None:
        """v0.0.20.435: Throttled UI update for CC automation recording."""
        dirty = getattr(self, '_cc_ui_dirty_pids', None)
        if not dirty:
            return
        pids = list(dirty)
        dirty.clear()
        for pid in pids:
            try:
                self.lane_data_changed.emit(pid)
            except Exception:
                pass

    def thin_recorded_lanes(self, epsilon: float = 0.015) -> int:
        """v0.0.20.441: Auto-thin recorded lanes — DEFERRED to avoid GUI freeze.

        Schedules thinning via QTimer.singleShot so it doesn't block the
        transport stop event chain. Each lane is thinned one at a time with
        small delays between to keep the GUI responsive.
        """
        recorded = getattr(self, '_recorded_lane_pids', None)
        if not recorded:
            return 0
        pids = list(recorded)
        recorded.clear()
        if not pids:
            return 0

        # Deferred: thin one lane per timer tick (50ms apart)
        try:
            from PyQt6.QtCore import QTimer

            def _thin_next():
                if not pids:
                    return
                pid = pids.pop(0)
                lane = self._lanes.get(pid)
                if lane and len(lane.points) > 3:
                    lane.sort_points()
                    lane.thin(epsilon)
                    try:
                        self.lane_data_changed.emit(pid)
                    except Exception:
                        pass
                # Schedule next lane if any remain
                if pids:
                    QTimer.singleShot(30, _thin_next)

            QTimer.singleShot(50, _thin_next)
        except Exception:
            pass
        return 0  # Can't return count synchronously anymore

    # --- v0.0.20.644: Automation Snapshot (AP9 Phase 9C) ---

    def snapshot_automation(self, track_id: str, beat: float) -> Dict[str, float]:
        """Capture current state of all parameters on a track as a snapshot.

        Creates a breakpoint at the given beat for every parameter that
        has a current value. Useful as a starting point for automation.

        Args:
            track_id: Track to snapshot
            beat: Beat position to place the breakpoints

        Returns:
            Dict of parameter_id → current normalized value
        """
        snapshot: Dict[str, float] = {}
        for pid, param in self._parameters.items():
            if param.track_id != track_id:
                continue
            norm = param.get_normalized()
            snapshot[pid] = norm
            # Create or update lane with a single breakpoint at this beat
            lane = self.get_or_create_lane(
                pid, track_id=track_id, param_name=param.name)
            bp = BreakPoint(beat=beat, value=norm, curve_type=CurveType.LINEAR)
            lane.points.append(bp)
            lane.sort_points()
        return snapshot

    def copy_clip_automation(self, track_id: str,
                              src_start: float, src_end: float,
                              dst_start: float) -> int:
        """Copy automation from one clip region to another (AP9 Phase 9C).

        Used when duplicating clips — their automation should follow.

        Args:
            track_id: Track containing the automation
            src_start: Source region start beat
            src_end: Source region end beat
            dst_start: Destination start beat

        Returns:
            Number of breakpoints copied
        """
        offset = dst_start - src_start
        count = 0
        for lane in self.get_lanes_for_track(track_id):
            new_points = []
            for bp in lane.points:
                if src_start <= bp.beat <= src_end:
                    new_bp = BreakPoint(
                        beat=bp.beat + offset,
                        value=bp.value,
                        curve_type=bp.curve_type,
                        bezier_cx=bp.bezier_cx,
                        bezier_cy=bp.bezier_cy,
                    )
                    new_points.append(new_bp)
                    count += 1
            lane.points.extend(new_points)
            if new_points:
                lane.sort_points()
        return count

    def set_lane_mode(self, parameter_id: str, mode: str) -> bool:
        """Set automation mode for a lane (AP9 Phase 9B).

        Args:
            parameter_id: Target lane
            mode: "absolute", "relative", or "trim"

        Returns:
            True if lane exists and was updated
        """
        lane = self._lanes.get(parameter_id)
        if lane is None:
            return False
        if mode not in ("absolute", "relative", "trim"):
            return False
        lane.automation_mode = mode
        try:
            self.lane_data_changed.emit(parameter_id)
        except Exception:
            pass
        return True

    def get_lane_mode(self, parameter_id: str) -> str:
        """Get automation mode for a lane."""
        lane = self._lanes.get(parameter_id)
        if lane is None:
            return "absolute"
        return lane.automation_mode
