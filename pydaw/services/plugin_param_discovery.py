# -*- coding: utf-8 -*-
"""Plugin Parameter Automation Discovery & Registration (AP9 Phase 9A).

v0.0.20.644: Discovers all automatable parameters from plugins on a track
and registers them with the AutomationManager.

Features:
- Query VST3/CLAP/LV2 plugins for parameter lists via get_param_infos()
- Introspect built-in FX RT param keys
- Register discovered parameters with AutomationManager
- Per-parameter "arm" state for targeted write-mode recording
- Parameter name display in automation lane headers

Usage:
    discovery = PluginParamDiscovery(automation_manager, rt_params)
    params = discovery.discover_track_parameters(track, chain_fx)
    # params is a list of DiscoveredParam with all info for automation
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


@dataclass
class DiscoveredParam:
    """A discovered automatable plugin parameter."""
    parameter_id: str     # unique ID for AutomationManager (e.g. "afx:trk1:dev1:cutoff")
    name: str             # display name (e.g. "Cutoff")
    plugin_name: str      # parent plugin name (e.g. "Compressor")
    device_id: str        # device instance ID
    track_id: str         # parent track ID
    min_val: float = 0.0
    max_val: float = 1.0
    default_val: float = 0.0
    unit: str = ""        # optional unit string (dB, Hz, %, etc.)
    is_armed: bool = False  # write-mode armed for this specific parameter
    rt_key: str = ""      # RT param store key for direct engine access
    plugin_param_index: int = -1  # plugin-internal param index


# ---------------------------------------------------------------------------
# Built-in FX Parameter Definitions
# ---------------------------------------------------------------------------

# Map: plugin_id → list of (param_suffix, name, min, max, default, unit)
_BUILTIN_FX_PARAMS: Dict[str, List[tuple]] = {
    # Phase 8A — Essential FX
    "chrono.fx.eq5": [
        (f"band{i}_{p}", f"Band {i} {n}", lo, hi, d, u)
        for i in range(5)
        for p, n, lo, hi, d, u in [
            ("freq", "Freq", 20.0, 20000.0, [60, 400, 1000, 3000, 10000][min(i, 4)], "Hz"),
            ("gain_db", "Gain", -24.0, 24.0, 0.0, "dB"),
            ("q", "Q", 0.1, 10.0, 1.0, ""),
        ]
    ],
    "chrono.fx.compressor": [
        ("threshold_db", "Threshold", -60.0, 0.0, -20.0, "dB"),
        ("ratio", "Ratio", 1.0, 20.0, 4.0, ":1"),
        ("attack_ms", "Attack", 0.1, 100.0, 10.0, "ms"),
        ("release_ms", "Release", 10.0, 1000.0, 100.0, "ms"),
        ("knee_db", "Knee", 0.0, 24.0, 6.0, "dB"),
        ("makeup_db", "Makeup", 0.0, 36.0, 0.0, "dB"),
        ("mix", "Mix", 0.0, 1.0, 1.0, ""),
    ],
    "chrono.fx.reverb": [
        ("decay", "Decay", 0.0, 1.0, 0.5, ""),
        ("damping", "Damping", 0.0, 1.0, 0.5, ""),
        ("pre_delay_ms", "Pre-Delay", 0.0, 200.0, 10.0, "ms"),
        ("mix", "Mix", 0.0, 1.0, 0.3, ""),
    ],
    "chrono.fx.delay2": [
        ("time_ms", "Time", 1.0, 2000.0, 375.0, "ms"),
        ("feedback", "Feedback", 0.0, 0.95, 0.4, ""),
        ("mix", "Mix", 0.0, 1.0, 0.3, ""),
        ("ping_pong", "Ping-Pong", 0.0, 1.0, 0.0, ""),
        ("filter_freq", "Filter", 200.0, 20000.0, 8000.0, "Hz"),
    ],
    "chrono.fx.peak_limiter": [
        ("ceiling_db", "Ceiling", -12.0, 0.0, -0.3, "dB"),
        ("release_ms", "Release", 1.0, 200.0, 50.0, "ms"),
        ("gain_db", "Gain", -12.0, 36.0, 0.0, "dB"),
    ],
    # Phase 8B — Creative FX
    "chrono.fx.chorus": [
        ("rate_hz", "Rate", 0.1, 10.0, 1.5, "Hz"),
        ("depth_ms", "Depth", 0.1, 20.0, 5.0, "ms"),
        ("voices", "Voices", 1.0, 6.0, 2.0, ""),
        ("mix", "Mix", 0.0, 1.0, 0.5, ""),
    ],
    "chrono.fx.flanger": [
        ("rate_hz", "Rate", 0.05, 5.0, 0.3, "Hz"),
        ("depth_ms", "Depth", 0.1, 10.0, 3.0, "ms"),
        ("feedback", "Feedback", 0.0, 0.95, 0.6, ""),
        ("mix", "Mix", 0.0, 1.0, 0.5, ""),
    ],
    "chrono.fx.distortion_plus": [
        ("drive", "Drive", 0.0, 1.0, 0.5, ""),
        ("tone", "Tone", 0.0, 1.0, 0.5, ""),
        ("mix", "Mix", 0.0, 1.0, 1.0, ""),
    ],
    "chrono.fx.tremolo": [
        ("rate_hz", "Rate", 0.1, 20.0, 4.0, "Hz"),
        ("depth", "Depth", 0.0, 1.0, 0.7, ""),
        ("stereo_offset", "Stereo", 0.0, 1.0, 0.0, ""),
        ("mix", "Mix", 0.0, 1.0, 1.0, ""),
    ],
    "chrono.fx.filter_plus": [
        ("rate_hz", "Rate", 0.01, 10.0, 0.5, "Hz"),
        ("depth", "Depth", 0.0, 1.0, 0.7, ""),
        ("feedback", "Feedback", 0.0, 0.95, 0.5, ""),
        ("mix", "Mix", 0.0, 1.0, 0.5, ""),
    ],
    # Phase 8C — Utility FX
    "chrono.fx.gate": [
        ("threshold_db", "Threshold", -80.0, 0.0, -40.0, "dB"),
        ("attack_ms", "Attack", 0.01, 50.0, 0.5, "ms"),
        ("hold_ms", "Hold", 0.0, 500.0, 50.0, "ms"),
        ("release_ms", "Release", 1.0, 2000.0, 100.0, "ms"),
        ("range_db", "Range", -80.0, -1.0, -80.0, "dB"),
        ("mix", "Mix", 0.0, 1.0, 1.0, ""),
    ],
    "chrono.fx.de_esser": [
        ("frequency", "Frequency", 2000.0, 16000.0, 6500.0, "Hz"),
        ("threshold_db", "Threshold", -40.0, 0.0, -20.0, "dB"),
        ("range_db", "Range", 0.0, 24.0, 6.0, "dB"),
    ],
    "chrono.fx.stereo_widener": [
        ("width", "Width", 0.0, 2.0, 1.0, ""),
        ("mid_gain_db", "Mid Gain", -12.0, 12.0, 0.0, "dB"),
        ("side_gain_db", "Side Gain", -12.0, 12.0, 0.0, "dB"),
        ("mix", "Mix", 0.0, 1.0, 1.0, ""),
    ],
    "chrono.fx.utility": [
        ("gain_db", "Gain", -96.0, 36.0, 0.0, "dB"),
        ("pan", "Pan", -1.0, 1.0, 0.0, ""),
        ("phase_invert_l", "Phase L", 0.0, 1.0, 0.0, ""),
        ("phase_invert_r", "Phase R", 0.0, 1.0, 0.0, ""),
        ("mono", "Mono", 0.0, 1.0, 0.0, ""),
    ],
}


# ---------------------------------------------------------------------------
# Discovery Service
# ---------------------------------------------------------------------------

class PluginParamDiscovery:
    """Discovers and registers automatable parameters from track plugins."""

    def __init__(self, automation_manager: Any = None, rt_params: Any = None):
        self._am = automation_manager
        self._rt_params = rt_params
        # Per-parameter arm state: parameter_id → bool
        self._armed: Dict[str, bool] = {}

    def discover_track_parameters(self, track: Any, chain_fx: Any = None) -> List[DiscoveredParam]:
        """Discover all automatable parameters on a track.

        Walks through the track's audio FX chain and queries each device
        for its parameters.

        Args:
            track: Track model object (needs .id, .audio_fx_chain)
            chain_fx: Optional pre-built ChainFx instance

        Returns:
            List of DiscoveredParam
        """
        track_id = str(getattr(track, 'id', '') or getattr(track, 'track_id', ''))
        result: List[DiscoveredParam] = []

        # Get device specs from track model
        devices_spec = []
        try:
            chain = getattr(track, 'audio_fx_chain', None)
            if isinstance(chain, dict):
                devices_spec = chain.get('devices', []) or []
            elif isinstance(chain, list):
                devices_spec = chain
        except Exception:
            pass

        for dev_spec in devices_spec:
            if not isinstance(dev_spec, dict):
                continue
            try:
                pid = str(dev_spec.get('plugin_id', '') or dev_spec.get('type', ''))
                did = str(dev_spec.get('id', '') or pid)
                dev_name = str(dev_spec.get('name', pid) or pid)
                enabled = dev_spec.get('enabled', True)

                if not pid:
                    continue

                # 1. Built-in FX: use static param definitions
                if pid in _BUILTIN_FX_PARAMS:
                    prefix = f"afx:{track_id}:{did}:"
                    for suffix, name, min_v, max_v, def_v, unit in _BUILTIN_FX_PARAMS[pid]:
                        param_id = prefix + suffix
                        dp = DiscoveredParam(
                            parameter_id=param_id,
                            name=name,
                            plugin_name=dev_name,
                            device_id=did,
                            track_id=track_id,
                            min_val=min_v,
                            max_val=max_v,
                            default_val=def_v,
                            unit=unit,
                            rt_key=param_id,
                        )
                        result.append(dp)

                # 2. External plugins: query get_param_infos() from live instance
                elif chain_fx is not None:
                    result.extend(self._discover_from_live_chain(
                        chain_fx, did, dev_name, track_id, pid))

            except Exception as e:
                _log.debug("Param discovery error for device %s: %s", dev_spec, e)

        return result

    def _discover_from_live_chain(self, chain_fx: Any, device_id: str,
                                   device_name: str, track_id: str,
                                   plugin_id: str) -> List[DiscoveredParam]:
        """Query live plugin instances for parameter info."""
        result = []
        try:
            devices = getattr(chain_fx, 'devices', []) or []
            for dev in devices:
                # Match device by checking device_id attribute
                dev_did = getattr(dev, 'device_id', getattr(dev, '_device_id', ''))
                if not dev_did:
                    # Try matching by plugin type
                    dev_pid = getattr(dev, 'plugin_id', getattr(dev, '_plugin_id', ''))
                    if dev_pid != plugin_id:
                        continue

                # Check for get_param_infos() method (VST3/CLAP/LV2)
                if hasattr(dev, 'get_param_infos'):
                    try:
                        infos = dev.get_param_infos()
                        for idx, info in enumerate(infos):
                            param_name = getattr(info, 'name', f'Param {idx}')
                            param_id_val = getattr(info, 'param_id', idx)
                            min_v = float(getattr(info, 'min_value', getattr(info, 'min', 0.0)))
                            max_v = float(getattr(info, 'max_value', getattr(info, 'max', 1.0)))
                            def_v = float(getattr(info, 'default_value', getattr(info, 'default', 0.0)))
                            unit = str(getattr(info, 'unit', ''))

                            # Construct unique parameter_id
                            p_id = f"plugin:{track_id}:{device_id}:{param_id_val}"
                            rt_key = f"afx:{track_id}:{device_id}:p{idx}"

                            dp = DiscoveredParam(
                                parameter_id=p_id,
                                name=param_name,
                                plugin_name=device_name,
                                device_id=device_id,
                                track_id=track_id,
                                min_val=min_v,
                                max_val=max_v,
                                default_val=def_v,
                                unit=unit,
                                rt_key=rt_key,
                                plugin_param_index=idx,
                            )
                            result.append(dp)
                    except Exception as e:
                        _log.debug("get_param_infos() failed for %s: %s", device_name, e)
        except Exception:
            pass
        return result

    def register_discovered_params(self, params: List[DiscoveredParam]) -> int:
        """Register discovered parameters with the AutomationManager.

        Args:
            params: List from discover_track_parameters()

        Returns:
            Number of newly registered parameters
        """
        if self._am is None:
            return 0

        count = 0
        for dp in params:
            try:
                # Check if already registered
                existing = self._am.get_parameter(dp.parameter_id)
                if existing is not None:
                    continue

                self._am.register_parameter(
                    parameter_id=dp.parameter_id,
                    name=f"{dp.plugin_name}: {dp.name}",
                    min_val=dp.min_val,
                    max_val=dp.max_val,
                    default_val=dp.default_val,
                    track_id=dp.track_id,
                )
                count += 1
            except Exception as e:
                _log.debug("Failed to register param %s: %s", dp.parameter_id, e)
        return count

    # --- Arm/Disarm for write automation ---

    def set_armed(self, parameter_id: str, armed: bool = True) -> None:
        """Arm or disarm a parameter for write-mode automation recording."""
        self._armed[parameter_id] = armed

    def is_armed(self, parameter_id: str) -> bool:
        """Check if a parameter is armed for automation recording."""
        return self._armed.get(parameter_id, False)

    def get_armed_params(self) -> List[str]:
        """Return list of all armed parameter IDs."""
        return [pid for pid, armed in self._armed.items() if armed]

    def disarm_all(self) -> None:
        """Disarm all parameters."""
        self._armed.clear()

    def disarm_track(self, track_id: str) -> None:
        """Disarm all parameters for a specific track."""
        to_remove = [pid for pid in self._armed if f":{track_id}:" in pid]
        for pid in to_remove:
            self._armed.pop(pid, None)

    # --- Utility ---

    def get_param_display_name(self, parameter_id: str, params: List[DiscoveredParam] = None) -> str:
        """Get a human-readable display name for a parameter ID."""
        if params:
            for dp in params:
                if dp.parameter_id == parameter_id:
                    return f"{dp.plugin_name} → {dp.name}"
        # Fallback: parse the parameter_id
        parts = parameter_id.split(":")
        if len(parts) >= 4:
            return parts[-1].replace("_", " ").title()
        return parameter_id

    def get_params_grouped_by_plugin(self, params: List[DiscoveredParam]) -> Dict[str, List[DiscoveredParam]]:
        """Group discovered params by plugin name for UI display."""
        groups: Dict[str, List[DiscoveredParam]] = {}
        for dp in params:
            key = f"{dp.device_id}:{dp.plugin_name}"
            groups.setdefault(key, []).append(dp)
        return groups
